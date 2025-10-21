"""Create the SQL agent."""

import os
from typing import Literal
from langgraph.graph import StateGraph, END, START
from dotenv import load_dotenv

from agent.analyze_schema import analyze_schema
from agent.filter_schema import filter_schema
from agent.format_schema_markdown import convert_schema_to_markdown
from agent.execute_query import execute_query
from agent.planner import plan_query
from agent.generate_query import generate_query
from agent.handle_tool_error import handle_tool_error
from agent.refine_query import refine_query
from agent.conversational_router import conversational_router
from agent.state import State

from database.connection import get_pyodbc_connection

load_dotenv()
use_test_db = os.getenv("USE_TEST_DB").lower() == "true"


def is_none_result(result):
    """Check if the result is None or empty."""
    if result is None:
        return True

    # Result is now a JSON string from execute_query
    if isinstance(result, str):
        try:
            import json
            data = json.loads(result)
            # Check if the data is empty or is an empty list
            return not data or (isinstance(data, list) and len(data) == 0)
        except json.JSONDecodeError:
            return True

    return False


def route_from_start(state: State) -> Literal["conversational_router", "analyze_schema"]:
    """Route from START based on whether this is a continuation."""
    is_continuation = state.get("is_continuation", False)

    if is_continuation:
        return "conversational_router"
    else:
        return "analyze_schema"


def route_from_router(state: State) -> Literal["planner", "execute_query"]:
    """Route from conversational_router based on decision."""
    router_mode = state.get("router_mode")

    if router_mode in ["update", "rewrite"]:
        # Need to go through planner
        return "planner"
    else:
        # Inline revision - query is already set, go straight to execute
        return "execute_query"


def should_continue(state: State) -> Literal["handle_error", "refine_query", "cleanup"]:
    """Determine the next step based on the current state."""

    messages = state["messages"]
    last_message = messages[-1]
    retry_count = state["retry_count"]
    refined_count = state["refined_count"]
    result = state["result"]

    env_retry_count = int(os.getenv("RETRY_COUNT")) if os.getenv("RETRY_COUNT") else 3
    env_refine_count = (
        int(os.getenv("REFINE_COUNT")) if os.getenv("REFINE_COUNT") else 2
    )
    none_result = is_none_result(result)

    # Handle errors
    if "Error" in last_message.content and retry_count < env_retry_count:
        return "handle_error"

    # If result is None and refinement is not exhausted, refine
    if none_result and refined_count < env_refine_count:
        return "refine_query"

    # Default path if no errors/refinements are needed
    return "cleanup"


def create_sql_agent():
    """Create the SQL agent."""
    workflow = StateGraph(State)

    db_connection = get_pyodbc_connection()

    # Add all nodes
    workflow.add_node(
        "analyze_schema", lambda state: analyze_schema(state, db_connection)
    )
    workflow.add_node("filter_schema", filter_schema)
    workflow.add_node("format_schema_markdown", convert_schema_to_markdown)
    workflow.add_node("conversational_router", conversational_router)
    workflow.add_node("planner", plan_query)
    workflow.add_node("generate_query", generate_query)
    workflow.add_node(
        "execute_query", lambda state: execute_query(state, db_connection)
    )
    workflow.add_node("handle_error", handle_tool_error)
    workflow.add_node("cleanup", lambda state: cleanup_connection(state, db_connection))
    workflow.add_node("refine_query", refine_query)

    # Conditional routing from START
    workflow.add_conditional_edges(START, route_from_start)

    # Standard workflow path (new conversations)
    workflow.add_edge("analyze_schema", "filter_schema")
    workflow.add_edge("filter_schema", "format_schema_markdown")
    workflow.add_edge("format_schema_markdown", "planner")
    workflow.add_edge("planner", "generate_query")
    workflow.add_edge("generate_query", "execute_query")

    # Conversational flow path (continuations)
    workflow.add_conditional_edges("conversational_router", route_from_router)

    # Error handling and refinement
    workflow.add_conditional_edges("execute_query", should_continue)
    workflow.add_edge("handle_error", "execute_query")
    workflow.add_edge("refine_query", "execute_query")

    # Cleanup
    workflow.add_edge("cleanup", END)

    return workflow.compile()


def cleanup_connection(state: State, connection):
    """Cleanup node to ensure connection is closed"""

    try:
        connection.close()
    except Exception as e:
        print(f"Error closing connection: {e}")
    return state
