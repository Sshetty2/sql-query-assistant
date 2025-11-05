"""Entry point for query chain"""

from typing import Optional, Dict, Any
from langchain_core.messages import HumanMessage
from agent.create_agent import create_sql_agent
from utils.thread_manager import (
    create_thread,
    save_query_state,
    get_latest_query_state,
)
from utils.logger import get_logger
from utils.debug_utils import clear_debug_files

logger = get_logger("query_database")


def _create_base_state(
    thread_id: str,
    question: str,
    sort_order: str,
    result_limit: int,
    time_filter: str,
) -> Dict[str, Any]:
    """Create base state dictionary with default values.

    Args:
        thread_id: Thread identifier
        question: User's question
        sort_order: Sort order preference
        result_limit: Result limit
        time_filter: Time filter preference

    Returns:
        Base state dictionary
    """
    return {
        # Thread management
        "thread_id": thread_id,
        # Conversation history
        "messages": [HumanMessage(content=question)],
        "user_questions": [question],
        "user_question": question,
        # Schema and planning (will be populated by workflow)
        "schema": [],
        "planner_outputs": [],
        "planner_output": None,
        "filtered_schema": None,
        "schema_markdown": None,
        # Query state
        "queries": [],
        "query": "",
        "result": "",
        # Router state
        "router_mode": None,
        "router_instructions": None,
        # Query preferences
        "sort_order": sort_order,
        "result_limit": result_limit,
        "time_filter": time_filter,
        # Workflow tracking
        "last_step": "start_query_pipeline",
        "error_iteration": 0,
        "refinement_iteration": 0,
        "column_removal_count": 0,
        "removed_columns": [],
        "last_attempt_time": None,
        "needs_clarification": False,
        "clarification_suggestions": [],
        "correction_history": [],
        "refinement_history": [],
        # Patch-specific fields
        "patch_requested": False,
        "current_patch_operation": None,
        "patch_history": [],
        "executed_plan": None,
        "modification_options": None,
    }


def query_database(
    question: str,
    sort_order="Default",
    result_limit=0,
    time_filter="All Time",
    thread_id: Optional[str] = None,
    previous_state: Optional[Dict[str, Any]] = {},
    patch_operation: Optional[Dict[str, Any]] = None,
    executed_plan: Optional[Dict[str, Any]] = None,
    filtered_schema: Optional[list] = None,
    stream_updates: bool = False,
):
    """Run the query workflow for a given question.

    Args:
        question: The user's natural language question
        sort_order: Sort order preference (Default, Ascending, Descending)
        result_limit: Maximum number of results to return
        time_filter: Time filter preference (All Time, Last 7 Days, etc.)
        thread_id: Optional thread ID for continuing a conversation. If None, creates new thread.
        previous_state: Optional previous state (if not provided, will load from thread)
        patch_operation: Optional dict with patch operation (for plan patching)
        executed_plan: Optional executed plan (required if patch_operation provided)
        filtered_schema: Optional filtered schema (required if patch_operation provided)
        stream_updates: If True, yields status updates during execution. If False, returns final result.

    Returns:
        If stream_updates=False: Dict with 'state' (final state), 'thread_id', and 'query_id'
        If stream_updates=True: Generator yielding status updates and final result
    """
    # Clear old debug files from previous runs (only when starting a new workflow)
    # This prevents confusion when looking at debug files
    clear_debug_files()

    # Create agent (this also creates a database connection)
    # The connection will be stored in the agent's closure and passed to nodes
    agent, db_connection = create_sql_agent()

    # Determine if this is a new thread or continuation
    if thread_id is None:
        # New conversation - create new thread
        thread_id = create_thread(question)
        initial_state = _create_base_state(
            thread_id, question, sort_order, result_limit, time_filter
        )

        # Override schema fields if previous_state provided
        if previous_state:
            initial_state["schema"] = previous_state.get("schema", [])
            initial_state["filtered_schema"] = previous_state.get(
                "filtered_schema", None
            )
            initial_state["schema_markdown"] = previous_state.get(
                "schema_markdown", None
            )
    else:
        # Continuation - load previous state if not provided
        if previous_state is None:
            previous_state = get_latest_query_state(thread_id)

        if previous_state:
            # Build state from previous execution
            user_questions = previous_state.get("user_questions", []) + [question]

            initial_state = _create_base_state(
                thread_id, question, sort_order, result_limit, time_filter
            )
            # Override with continuation-specific values
            initial_state.update(
                {
                    "messages": previous_state.get("messages", [])
                    + [HumanMessage(content=question)],
                    "user_questions": user_questions,
                    "planner_outputs": previous_state.get("planner_outputs", []),
                    "planner_output": previous_state.get("planner_output"),
                    "queries": previous_state.get("queries", []),
                    "query": previous_state.get("query", ""),
                }
            )
        else:
            # No previous state found, treat as new thread
            initial_state = _create_base_state(
                thread_id, question, sort_order, result_limit, time_filter
            )

    # Add patch-specific fields if patching is requested
    if patch_operation is not None:
        if executed_plan is None or filtered_schema is None:
            raise ValueError(
                "executed_plan and filtered_schema are required when patch_operation is provided"
            )

        logger.info(f"Patch operation requested: {patch_operation.get('operation')}")

        initial_state.update(
            {
                "patch_requested": True,
                "current_patch_operation": patch_operation,
                "executed_plan": executed_plan,
                "filtered_schema": filtered_schema,
                "planner_output": executed_plan,  # Set as current plan for regeneration
            }
        )

    # Execute workflow with guaranteed connection cleanup
    try:
        if stream_updates:
            # Streaming mode: use both "custom" and "values" stream modes
            # - "custom": gets custom events emitted by nodes (status, logs)
            # - "values": gets the final state after workflow completes
            result = None
            for chunk in agent.stream(
                initial_state,
                config={"recursion_limit": 1000},
                stream_mode=["custom", "values"],
            ):
                # When using stream_mode=["custom", "values"], chunks are tuples:
                # - ("custom", {...}) for custom events from nodes
                # - ("values", {...}) for state updates

                if isinstance(chunk, tuple) and len(chunk) == 2:
                    mode, data = chunk

                    if mode == "custom":
                        # This is a custom event from a node
                        logger.debug(f"Received custom stream event: {data}")
                        yield data
                    elif mode == "values":
                        # This is a state update (final state)
                        result = data
                        logger.debug("Received final state update")
                else:
                    # Fallback for unexpected format
                    logger.warning(f"Unexpected chunk format: {chunk}")
                    result = chunk

            # Validate and finalize result
            if result is None:
                raise RuntimeError("Workflow completed but no final state was produced")
        else:
            # Non-streaming mode: original invoke behavior
            result = agent.invoke(initial_state)

        # Save the result state to thread
        query_id = save_query_state(thread_id, question, result)

        # Return/yield final result
        final_output = {
            "type": "complete",
            "state": result,
            "thread_id": thread_id,
            "query_id": query_id,
        }

        if stream_updates:
            yield final_output
        else:
            return final_output
    finally:
        # CRITICAL: Always close the database connection, even if an exception occurred
        # This prevents connection leaks when errors happen before the cleanup node
        # NOTE: In normal flow, the cleanup node already closes the connection,
        # but this ensures cleanup even if workflow is interrupted by an exception
        try:
            if db_connection and hasattr(db_connection, "close"):
                # Check if connection is still open (pyodbc connections have a 'closed' attribute)
                if hasattr(db_connection, "closed") and db_connection.closed:
                    logger.debug("Database connection already closed by cleanup node")
                else:
                    db_connection.close()
                    logger.debug(
                        "Database connection closed successfully in finally block"
                    )
        except Exception as e:
            # This is okay - connection might already be closed by cleanup node
            logger.debug(
                f"Connection cleanup in finally block (connection may already be closed): {str(e)}"
            )
