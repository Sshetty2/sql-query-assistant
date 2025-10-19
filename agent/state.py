"""State object for the SQL agent."""

from typing import Annotated, TypedDict, Optional, Any
from langgraph.graph.message import AnyMessage, add_messages


class State(TypedDict):
    """State object type for the SQL agent."""

    messages: Annotated[list[AnyMessage], add_messages]
    user_question: str  # Holds user question
    schema: list[dict]  # Holds schema information
    planner_output: Optional[dict[str, Any]]  # Holds the planner output (PlannerOutput as dict)
    query: str  # Holds generated SQL query
    result: str  # Holds query execution result
    sort_order: str  # Holds sort order preference
    result_limit: int  # Holds result limit preference
    time_filter: str  # Holds time filter preference
    last_step: str  # Holds current step in the workflow
    corrected_queries: list[str]  # Holds the corrected query if query error occurred
    refined_queries: list[str]  # Holds the refined queries if query returned no results
    retry_count: int  # Number of retries
    refined_count: int  # Number of times the query has been refined
    error_history: list[str]  # List of errors encountered
    refined_reasoning: list[str]  # List of reasoning for each refinement
    last_attempt_time: Optional[str]  # Last time the query was attempted
