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

logger = get_logger("query_database")


def query_database(
    question: str,
    sort_order="Default",
    result_limit=0,
    time_filter="All Time",
    thread_id: Optional[str] = None,
    previous_state: Optional[Dict[str, Any]] = {},
):
    """Run the query workflow for a given question.

    Args:
        question: The user's natural language question
        sort_order: Sort order preference (Default, Ascending, Descending)
        result_limit: Maximum number of results to return
        time_filter: Time filter preference (All Time, Last 7 Days, etc.)
        thread_id: Optional thread ID for continuing a conversation. If None, creates new thread.
        previous_state: Optional previous state (if not provided, will load from thread)

    Returns:
        Dict with 'state' (final state), 'thread_id', and 'query_id'
    """
    # Create agent (this also creates a database connection)
    # The connection will be stored in the agent's closure and passed to nodes
    agent, db_connection = create_sql_agent()

    # Determine if this is a new thread or continuation
    if thread_id is None:
        # New conversation - create new thread
        thread_id = create_thread(question)

        # Build full initial state for new thread
        initial_state = {
            # Thread management
            "thread_id": thread_id,
            # Conversation history
            "messages": [HumanMessage(content=question)],
            "user_questions": [question],
            "user_question": question,
            # NOTE: is_continuation removed - we always analyze schema now
            # Schema and planning (will be populated by workflow)
            "schema": previous_state.get("schema", []),
            "planner_outputs": [],
            "planner_output": None,
            "filtered_schema": previous_state.get("filtered_schema", []),
            "schema_markdown": previous_state.get("schema_markdown", ""),
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
            "retry_count": 0,
            "refined_count": 0,
            "column_removal_count": 0,
            "removed_columns": [],
            "error_history": [],
            "error_reasoning": [],
            "last_attempt_time": None,
            "refined_queries": [],
            "refined_reasoning": [],
            "corrected_queries": [],
            "corrected_plans": [],
            "refined_plans": [],
            "needs_clarification": False,
            "clarification_suggestions": [],
        }
    else:
        # Continuation - load previous state if not provided
        if previous_state is None:
            previous_state = get_latest_query_state(thread_id)

        if previous_state:
            # Build state from previous execution
            user_questions = previous_state.get("user_questions", [])
            user_questions.append(question)

            initial_state = {
                # Thread management
                "thread_id": thread_id,
                # Conversation history
                "messages": previous_state.get("messages", [])
                + [HumanMessage(content=question)],
                "user_questions": user_questions,
                "user_question": question,  # Latest question
                # NOTE: is_continuation removed - we always analyze schema now
                # (no longer carrying over schema since we don't persist it)
                "schema": [],  # Will be populated fresh by analyze_schema
                "filtered_schema": None,
                "schema_markdown": None,
                "planner_outputs": previous_state.get("planner_outputs", []),
                "planner_output": previous_state.get("planner_output"),
                # Carry over query history
                "queries": previous_state.get("queries", []),
                "query": previous_state.get("query", ""),
                "result": "",  # Reset result for new query
                # Query preferences (use new values if provided, else carry over)
                "sort_order": sort_order,
                "result_limit": result_limit,
                "time_filter": time_filter,
                # Workflow tracking (reset for new iteration)
                "last_step": "start_query_pipeline",
                "retry_count": 0,
                "refined_count": 0,
                "column_removal_count": 0,
                "removed_columns": [],
                "error_history": [],
                "error_reasoning": [],
                "last_attempt_time": None,
                "refined_queries": [],
                "refined_reasoning": [],
                "corrected_queries": [],
                "corrected_plans": [],
                "refined_plans": [],
                "needs_clarification": False,
                "clarification_suggestions": [],
            }
        else:
            # No previous state found, treat as new thread
            initial_state = {
                # Thread management
                "thread_id": thread_id,
                # Conversation history
                "messages": [HumanMessage(content=question)],
                "user_questions": [question],
                "user_question": question,
                # NOTE: is_continuation and router fields removed
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
                # Query preferences
                "sort_order": sort_order,
                "result_limit": result_limit,
                "time_filter": time_filter,
                # Workflow tracking
                "last_step": "start_query_pipeline",
                "retry_count": 0,
                "refined_count": 0,
                "column_removal_count": 0,
                "removed_columns": [],
                "error_history": [],
                "error_reasoning": [],
                "last_attempt_time": None,
                "refined_queries": [],
                "refined_reasoning": [],
                "corrected_queries": [],
                "corrected_plans": [],
                "refined_plans": [],
                "needs_clarification": False,
                "clarification_suggestions": [],
            }

    # Execute workflow with guaranteed connection cleanup
    try:
        result = agent.invoke(initial_state)

        # Save the result state to thread
        query_id = save_query_state(thread_id, question, result)

        # Return state, thread_id, and query_id
        return {
            "state": result,
            "thread_id": thread_id,
            "query_id": query_id,
        }
    finally:
        # CRITICAL: Always close the database connection, even if an exception occurred
        # This prevents connection leaks when errors happen before the cleanup node
        # NOTE: In normal flow, the cleanup node already closes the connection,
        # but this ensures cleanup even if workflow is interrupted by an exception
        try:
            if db_connection and hasattr(db_connection, 'close'):
                # Check if connection is still open (pyodbc connections have a 'closed' attribute)
                if hasattr(db_connection, 'closed') and db_connection.closed:
                    logger.debug("Database connection already closed by cleanup node")
                else:
                    db_connection.close()
                    logger.debug("Database connection closed successfully in finally block")
        except Exception as e:
            # This is okay - connection might already be closed by cleanup node
            logger.debug(f"Connection cleanup in finally block (connection may already be closed): {str(e)}")
