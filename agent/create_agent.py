"""Create the SQL agent."""

import os
from typing import Literal
from langgraph.graph import StateGraph, END, START
from langchain_core.messages import AIMessage
from dotenv import load_dotenv

from agent.analyze_schema import analyze_schema
from agent.filter_schema import filter_schema
from agent.infer_foreign_keys import infer_foreign_keys_node
from agent.format_schema_markdown import convert_schema_to_markdown
from agent.pre_planner import create_preplan_strategy
from agent.execute_query import execute_query
from agent.planner import plan_query
from agent.plan_audit import plan_audit
from agent.check_clarification import check_clarification
from agent.generate_query import generate_query
from agent.handle_tool_error import handle_tool_error
from agent.refine_query import refine_query
from agent.transform_plan import transform_plan_node
from agent.generate_modification_options import generate_modification_options_node

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
) -> Literal["analyze_schema", "transform_plan"]:
    """
    Route from START.

    - If patch_requested=True: route directly to transform_plan (skip analysis/planning)
    - Otherwise: analyze schema for new query

    NOTE: Conversational router disabled for now. We always fetch fresh schema
    since we don't persist it in state anymore (to avoid inflating saved state).
    The router wasn't working well anyway - will revisit later.
    """
    # Check if this is a patch operation
    if state.get("patch_requested"):
        logger.info("Patch requested, routing directly to transform_plan")
        return "transform_plan"

    # Normal flow: analyze schema for new query
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


def route_from_plan_audit(
    state: State,
) -> Literal["check_clarification"]:
    """
    Route from plan_audit - always continue to check_clarification.

    NOTE: Audit feedback loop is currently DISABLED. The audit still validates
    and logs issues, but doesn't block execution. This allows:
    1. Planner.py auto-fix logic to handle corrections
    2. Real SQL execution to reveal actual errors (via error_feedback)
    3. Refinement to handle empty results (via refinement_feedback)

    Audit feedback can be re-enabled later if needed by uncommenting the
    conditional routing logic below.
    """
    # DISABLED: Audit feedback loop
    # if state.get("needs_termination"):
    #     logger.warning("Plan audit triggered termination, routing to cleanup")
    #     return "cleanup"
    #
    # if state.get("audit_feedback"):
    #     logger.info("Plan audit generated feedback, routing back to pre_planner for correction")
    #     return "pre_planner"

    # Always continue to clarification check (audit doesn't block)
    if state.get("audit_feedback"):
        logger.info(
            "Plan audit found issues but continuing to execution (audit feedback disabled)"
        )
    else:
        logger.debug("Plan audit passed, routing to check_clarification")

    return "check_clarification"


def route_from_handle_error(
    state: State,
) -> Literal["planner", "cleanup"]:
    """
    Route from handle_error based on revised strategy.

    - If needs_termination=True: route to cleanup (iteration limit reached)
    - If revised_strategy is set: route to planner (bypassing pre-planner)
    """
    if state.get("needs_termination"):
        logger.warning("Error handling triggered termination, routing to cleanup")
        return "cleanup"

    if state.get("revised_strategy"):
        logger.info(
            "Error handler generated revised strategy, routing directly to planner (bypassing pre-planner)"
        )
        return "planner"

    # Should not reach here, but default to cleanup
    logger.error("Unexpected state in route_from_handle_error, defaulting to cleanup")
    return "cleanup"


def route_from_refine_query(
    state: State,
) -> Literal["planner", "cleanup"]:
    """
    Route from refine_query based on revised strategy.

    - If needs_termination=True: route to cleanup (iteration limit reached)
    - If revised_strategy is set: route to planner (bypassing pre-planner)
    """
    if state.get("needs_termination"):
        logger.warning("Query refinement triggered termination, routing to cleanup")
        return "cleanup"

    if state.get("revised_strategy"):
        logger.info(
            "Refinement generated revised strategy, routing directly to planner (bypassing pre-planner)"
        )
        return "planner"

    # Should not reach here, but default to cleanup
    logger.error("Unexpected state in route_from_refine_query, defaulting to cleanup")
    return "cleanup"


def route_from_execute_query(
    state: State,
) -> Literal[
    "transform_plan",
    "generate_modification_options",
    "handle_error",
    "refine_query",
    "cleanup",
]:
    """
    Route from execute_query based on patch_requested flag and query result.

    - If patch_requested=True: route to transform_plan
    - Otherwise: route based on query result (error/refine/success)
    """
    # Check if plan patching was requested
    if state.get("patch_requested"):
        logger.info("Plan patch requested, routing to transform_plan")
        return "transform_plan"

    # Otherwise use the existing should_continue logic
    messages = state["messages"]
    last_message = messages[-1]
    error_iteration = state.get("error_iteration", 0)
    refinement_iteration = state.get("refinement_iteration", 0)
    result = state["result"]

    env_retry_count = int(os.getenv("ERROR_CORRECTION_COUNT")) if os.getenv("ERROR_CORRECTION_COUNT") else 3
    env_refine_count = (
        int(os.getenv("REFINE_COUNT")) if os.getenv("REFINE_COUNT") else 2
    )
    none_result = is_none_result(result)
    has_error = "Error" in last_message.content

    # Handle errors - try error correction first
    if has_error and error_iteration < env_retry_count:
        return "handle_error"

    # If we hit max retries with errors, try refinement as last resort
    if (
        has_error
        and error_iteration >= env_retry_count
        and refinement_iteration < env_refine_count
    ):
        logger.info(
            "Max error correction retries reached, routing to refinement as fallback"
        )
        return "refine_query"

    # If result is None and refinement is not exhausted, refine
    if none_result and refinement_iteration < env_refine_count:
        return "refine_query"

    # Success - generate modification options before cleanup
    logger.info("Query executed successfully, routing to generate_modification_options")
    return "generate_modification_options"


def should_continue(state: State) -> Literal["handle_error", "refine_query", "cleanup"]:
    """
    Determine the next step based on the current state.

    NOTE: This function is now called from route_from_execute_query.
    Kept for backwards compatibility but prefer using route_from_execute_query.
    """

    messages = state["messages"]
    last_message = messages[-1]
    error_iteration = state.get("error_iteration", 0)
    refinement_iteration = state.get("refinement_iteration", 0)
    result = state["result"]

    env_retry_count = int(os.getenv("ERROR_CORRECTION_COUNT")) if os.getenv("ERROR_CORRECTION_COUNT") else 3
    env_refine_count = (
        int(os.getenv("REFINE_COUNT")) if os.getenv("REFINE_COUNT") else 2
    )
    none_result = is_none_result(result)
    has_error = "Error" in last_message.content

    # Handle errors - try error correction first
    if has_error and error_iteration < env_retry_count:
        return "handle_error"

    # If we hit max retries with errors, try refinement as last resort
    if (
        has_error
        and error_iteration >= env_retry_count
        and refinement_iteration < env_refine_count
    ):
        logger.info(
            "Max error correction retries reached, routing to refinement as fallback"
        )
        return "refine_query"

    # If result is None and refinement is not exhausted, refine
    if none_result and refinement_iteration < env_refine_count:
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
    workflow.add_node(
        "pre_planner", create_preplan_strategy
    )  # Two-stage planning: strategy generation
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
    # Plan patching nodes
    workflow.add_node("transform_plan", transform_plan_node)
    workflow.add_node(
        "generate_modification_options", generate_modification_options_node
    )

    # Conditional routing from START
    workflow.add_conditional_edges(START, route_from_start)

    # Standard workflow path (new conversations)
    workflow.add_edge("analyze_schema", "filter_schema")
    # Conditional routing from filter_schema based on FK inference flag
    workflow.add_conditional_edges("filter_schema", route_after_filter_schema)
    workflow.add_edge("infer_foreign_keys", "format_schema_markdown")
    # Two-stage planning: format_schema_markdown → pre_planner → planner
    workflow.add_edge("format_schema_markdown", "pre_planner")
    workflow.add_edge("pre_planner", "planner")
    workflow.add_edge("planner", "plan_audit")  # Audit plan before clarification
    # Plan audit (feedback loop DISABLED - always continues to check_clarification)
    workflow.add_edge("plan_audit", "check_clarification")
    workflow.add_conditional_edges("check_clarification", route_after_clarification)
    workflow.add_edge("generate_query", "execute_query")

    # DISABLED: Conversational flow path (continuations)
    # workflow.add_conditional_edges("conversational_router", route_from_router)

    # Error handling and refinement with feedback loops
    workflow.add_conditional_edges("execute_query", route_from_execute_query)
    # Conditional routing from handle_error (feedback loop or terminate)
    workflow.add_conditional_edges("handle_error", route_from_handle_error)
    # Conditional routing from refine_query (feedback loop or terminate)
    workflow.add_conditional_edges("refine_query", route_from_refine_query)

    # Plan patching flow
    workflow.add_edge(
        "transform_plan", "generate_query"
    )  # Patched plan → regenerate SQL
    workflow.add_edge("generate_modification_options", "cleanup")  # Success → cleanup

    # Cleanup
    workflow.add_edge("cleanup", END)

    # Compile with high recursion limit to support feedback loops
    # Default is 25, but we need higher for:
    # - Pre-planner → Planner → Audit → ... (up to 2 iterations)
    # - Error correction loops (up to 3 iterations)
    # - Refinement loops (up to 3 iterations)
    # Set to 100 to be safe (each iteration adds ~10-15 steps)
    return workflow.compile(), db_connection


def cleanup_connection(state: State, connection):
    """Cleanup node to ensure connection is closed and handle termination.

    Handles two scenarios:
    1. Normal completion - query executed successfully
    2. Iteration exhaustion - feedback loops hit iteration limits
    """

    try:
        connection.close()
        logger.debug("Database connection closed successfully")
    except Exception as e:
        logger.error(f"Error closing database connection: {str(e)}", exc_info=True)

    # Check if we're terminating due to iteration exhaustion
    if state.get("needs_termination"):
        termination_reason = state.get(
            "termination_reason", "Unknown termination reason"
        )
        logger.warning(
            "Workflow terminated due to iteration exhaustion",
            extra={"termination_reason": termination_reason},
        )
        # Return state with termination info for UI display
        return {
            **state,
            "schema": [],
            "last_step": "cleanup",
            "messages": [
                AIMessage(content=f"Workflow terminated: {termination_reason}")
            ],
        }

    # Normal cleanup - query succeeded
    logger.debug("Workflow completed successfully")
    # NOTE: schema is not persisted in state anymore - always fetch fresh
    return {**state, "schema": [], "last_step": "cleanup"}
