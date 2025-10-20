"""Entry point for query chain"""

from typing import Optional, Dict, Any
from langchain_core.messages import HumanMessage
from agent.create_agent import create_sql_agent


def query_database(
    question: str,
    sort_order="Default",
    result_limit=0,
    time_filter="All Time",
    previous_state: Optional[Dict[str, Any]] = None,
):
    """Run the query workflow for a given question.

    Args:
        question: The user's natural language question
        sort_order: Sort order preference (Default, Ascending, Descending)
        result_limit: Maximum number of results to return
        time_filter: Time filter preference (All Time, Last 7 Days, etc.)
        previous_state: Optional previous state for conversational continuations

    Returns:
        The final state after workflow execution
    """
    agent = create_sql_agent()

    if previous_state:
        # Continuation of existing conversation
        # Carry over state from previous execution
        user_questions = previous_state.get("user_questions", [])
        user_questions.append(question)

        initial_state = {
            # Conversation history
            "messages": previous_state.get("messages", [])
            + [HumanMessage(content=question)],
            "user_questions": user_questions,
            "user_question": question,  # Latest question
            "is_continuation": True,
            # Carry over schema and planning state
            "schema": previous_state.get("schema", []),
            "planner_outputs": previous_state.get("planner_outputs", []),
            "planner_output": previous_state.get("planner_output"),
            # Carry over query history
            "queries": previous_state.get("queries", []),
            "query": previous_state.get("query", ""),
            "result": "",  # Reset result for new query
            # Router state (will be set by router)
            "router_mode": None,
            "router_instructions": None,
            # Query preferences (use new values if provided, else carry over)
            "sort_order": sort_order,
            "result_limit": result_limit,
            "time_filter": time_filter,
            # Workflow tracking (reset for new iteration)
            "last_step": "start_query_pipeline",
            "retry_count": 0,
            "refined_count": 0,
            "error_history": [],
            "last_attempt_time": None,
            "refined_queries": [],
            "refined_reasoning": [],
            "corrected_queries": [],
        }
    else:
        # New conversation
        initial_state = {
            # Conversation history
            "messages": [HumanMessage(content=question)],
            "user_questions": [question],
            "user_question": question,
            "is_continuation": False,
            # Schema and planning
            "schema": [],
            "planner_outputs": [],
            "planner_output": None,
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
            "error_history": [],
            "last_attempt_time": None,
            "refined_queries": [],
            "refined_reasoning": [],
            "corrected_queries": [],
        }

    result = agent.invoke(initial_state)

    return result
