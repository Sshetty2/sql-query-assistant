"""Create the SQL agent."""

import os
from typing import Literal
from langgraph.graph import StateGraph, END, START
from dotenv import load_dotenv

from agent.analyze_schema import analyze_schema
from agent.filter_schema import filter_schema
from agent.infer_foreign_keys import infer_foreign_keys_node
from agent.format_schema_markdown import convert_schema_to_markdown
from agent.execute_query import execute_query
from agent.planner import plan_query
from agent.plan_audit import plan_audit
from agent.check_clarification import check_clarification
from agent.generate_query import generate_query
from agent.handle_tool_error import handle_tool_error
from agent.refine_query import refine_query

# DISABLED: Conversational router commented out for now
# from agent.conversational_router import conversational_router
from agent.state import State
from utils.logger import get_logger

from database.connection import get_pyodbc_connection

load_dotenv()
logger = get_logger()
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


def route_from_start(
    state: State,
) -> Literal["analyze_schema"]:
    """
    Route from START - always analyze schema.

    NOTE: Conversational router disabled for now. We always fetch fresh schema
    since we don't persist it in state anymore (to avoid inflating saved state).
    The router wasn't working well anyway - will revisit later.
    """
    # Always analyze schema (don't skip based on is_continuation)
    return "analyze_schema"


# DISABLED: Conversational router commented out for now
# def route_from_router(state: State) -> Literal["planner"]:
#     """
#     Route from conversational_router based on decision.
#
#     All conversational routing now goes through the planner to ensure
#     SQL is generated safely via the join synthesizer (prevents SQL injection).
#     """
#     # Router always sets router_mode to "update" or "rewrite"
#     # Both go through planner -> join synthesizer pipeline
#     return "planner"


def route_after_clarification(
    state: State,
) -> Literal["generate_query", "cleanup"]:
    """Route after checking for clarification needs.

    - If no planner_output: route to cleanup (planner failed)
    - If decision='terminate': route to cleanup (invalid query)
    - If decision='clarify': proceed to generate_query anyway (model may be overly cautious)
    - If decision='proceed': continue to generate_query
    """
    planner_output = state.get("planner_output")

    if not planner_output:
        logger.error("No planner output available - cannot generate query")
        return "cleanup"

    decision = planner_output.get("decision", "proceed")

    if decision == "terminate":
        termination_reason = planner_output.get(
            "termination_reason", "Query cannot be answered with available schema"
        )
        logger.info(f"Query terminated by planner: {termination_reason}")
        return "cleanup"

    needs_clarification = state.get("needs_clarification", False)
    if needs_clarification:
        logger.info("Clarification flagged but proceeding with query generation anyway")

    # Continue to query generation for 'proceed' and 'clarify' decisions
    return "generate_query"


def route_after_filter_schema(
    state: State,
) -> Literal["infer_foreign_keys", "format_schema_markdown"]:
    """
    Route from filter_schema based on INFER_FOREIGN_KEYS flag.

    - If INFER_FOREIGN_KEYS=true: route to FK inference
    - Otherwise: route directly to format_schema_markdown
    """
    if os.getenv("INFER_FOREIGN_KEYS", "false").lower() == "true":
        logger.info("FK inference enabled, routing to infer_foreign_keys")
        return "infer_foreign_keys"
    else:
        logger.debug("FK inference disabled, routing to format_schema_markdown")
        return "format_schema_markdown"


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
    has_error = "Error" in last_message.content

    # Handle errors - try error correction first
    if has_error and retry_count < env_retry_count:
        return "handle_error"

    # If we hit max retries with errors, try refinement as last resort
    if (
        has_error
        and retry_count >= env_retry_count
        and refined_count < env_refine_count
    ):
        logger.info(
            "Max error correction retries reached, routing to refinement as fallback"
        )
        return "refine_query"

    # If result is None and refinement is not exhausted, refine
    if none_result and refined_count < env_refine_count:
        return "refine_query"

    # Default path if no errors/refinements are needed
    return "cleanup"


def create_sql_agent():
    """Create the SQL agent.

    Returns:
        Tuple of (compiled_workflow, db_connection)
        The connection is returned so it can be closed in a finally block
        if an error occurs before the cleanup node is reached.
    """
    workflow = StateGraph(State)

    db_connection = get_pyodbc_connection()

    # Add all nodes
    workflow.add_node(
        "analyze_schema", lambda state: analyze_schema(state, db_connection)
    )
    workflow.add_node("filter_schema", filter_schema)
    workflow.add_node("infer_foreign_keys", infer_foreign_keys_node)
    workflow.add_node("format_schema_markdown", convert_schema_to_markdown)
    # DISABLED: Conversational router commented out for now
    # workflow.add_node("conversational_router", conversational_router)
    workflow.add_node("planner", plan_query)
    workflow.add_node("plan_audit", plan_audit)  # Audit plan before SQL generation
    workflow.add_node("check_clarification", check_clarification)
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
    # Conditional routing from filter_schema based on FK inference flag
    workflow.add_conditional_edges("filter_schema", route_after_filter_schema)
    workflow.add_edge("infer_foreign_keys", "format_schema_markdown")
    workflow.add_edge("format_schema_markdown", "planner")
    workflow.add_edge("planner", "plan_audit")  # Audit plan before clarification
    workflow.add_edge(
        "plan_audit", "check_clarification"
    )  # Continue to clarification after audit
    workflow.add_conditional_edges("check_clarification", route_after_clarification)
    workflow.add_edge("generate_query", "execute_query")

    # DISABLED: Conversational flow path (continuations)
    # workflow.add_conditional_edges("conversational_router", route_from_router)

    # Error handling and refinement
    workflow.add_conditional_edges("execute_query", should_continue)
    workflow.add_edge("handle_error", "generate_query")
    workflow.add_edge("refine_query", "generate_query")

    # Cleanup
    workflow.add_edge("cleanup", END)

    return workflow.compile(), db_connection


def cleanup_connection(state: State, connection):
    """Cleanup node to ensure connection is closed"""

    try:
        connection.close()
        logger.debug("Database connection closed successfully")
    except Exception as e:
        logger.error(f"Error closing database connection: {str(e)}", exc_info=True)
    # NOTE: schema is not persisted in state anymore - always fetch fresh
    return {**state, "schema": [], "last_step": "cleanup"}
