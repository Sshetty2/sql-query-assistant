"""Create the SQL agent."""

import os
from typing import Literal
from langgraph.graph import StateGraph, END, START
from dotenv import load_dotenv

from agent.analyze_schema import analyze_schema
from agent.execute_query import execute_query
from agent.filter_schema import filter_schema
from agent.generate_query import generate_query
from agent.handle_tool_error import handle_tool_error
from agent.refine_query import refine_query
from agent.state import State

from database.connection import get_pyodbc_connection

load_dotenv()
use_test_db = os.getenv("USE_TEST_DB").lower() == "true"


def is_none_result(result):
    """Check if the result is None."""
    none_result = False

    if result is None:
        return True

    # SQL-lite specific syntax
    if use_test_db:
        if isinstance(result, list) and len(result) > 0:
            first_entry = result[0]
            if len(first_entry) > 0:
                none_result = first_entry[0] == "[]"
        return none_result

    # SQL-Server specific syntax
    if isinstance(result, list) and len(result) > 0:
        first_entry = result[0]
        if len(first_entry) > 0:
            none_result = first_entry[0] is None
    return none_result


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

    workflow.add_node(
        "analyze_schema", lambda state: analyze_schema(state, db_connection)
    )
    workflow.add_node("filter_schema", filter_schema)
    workflow.add_node("generate_query", generate_query)
    workflow.add_node(
        "execute_query", lambda state: execute_query(state, db_connection)
    )
    workflow.add_node("handle_error", handle_tool_error)
    workflow.add_node("cleanup", lambda state: cleanup_connection(state, db_connection))
    workflow.add_node("refine_query", refine_query)

    workflow.add_edge(START, "analyze_schema")
    workflow.add_edge("analyze_schema", "filter_schema")
    workflow.add_edge("filter_schema", "generate_query")
    workflow.add_edge("generate_query", "execute_query")

    workflow.add_conditional_edges("execute_query", should_continue)

    workflow.add_edge("handle_error", "execute_query")
    workflow.add_edge("refine_query", "execute_query")
    workflow.add_edge("cleanup", END)

    return workflow.compile()


def cleanup_connection(state: State, connection):
    """Cleanup node to ensure connection is closed"""

    try:
        connection.close()
    except Exception as e:
        print(f"Error closing connection: {e}")
    return state
