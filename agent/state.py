"""State object for the SQL agent."""

from typing import Annotated, TypedDict, Optional, Any
from langgraph.graph.message import AnyMessage, add_messages


class State(TypedDict):
    """State object type for the SQL agent."""

    messages: Annotated[list[AnyMessage], add_messages]

    # Conversation history fields
    user_questions: list[str]  # History of all user questions in conversation
    user_question: str  # Current/latest user question (convenience field)
    is_continuation: bool  # Flag to indicate if continuing from previous query

    # Schema and planning
    schema: list[dict]  # Holds full schema information (JSON format)
    filtered_schema: Optional[list[dict]]  # Holds filtered schema (top-k relevant tables)
    schema_markdown: Optional[str]  # Schema formatted as markdown for LLM readability
    planner_outputs: list[dict[str, Any]]  # History of planner outputs
    planner_output: Optional[dict[str, Any]]  # Current/latest planner output (convenience field)

    # Query history and current query
    queries: list[str]  # History of all generated SQL queries
    query: str  # Current/latest generated SQL query (convenience field)
    result: str  # Holds query execution result

    # Router mode for conversational flow
    router_mode: Optional[str]  # "update" | "rewrite" | None
    router_instructions: Optional[str]  # Instructions from router to planner

    # Query preferences
    sort_order: str  # Holds sort order preference
    result_limit: int  # Holds result limit preference
    time_filter: str  # Holds time filter preference

    # Workflow tracking
    last_step: str  # Holds current step in the workflow
    corrected_queries: list[str]  # Corrected query if error occurred (deprecated - use corrected_plans)
    corrected_plans: list[dict[str, Any]]  # Holds the corrected plans if query error occurred
    refined_queries: list[str]  # Refined queries if no results (deprecated - use refined_plans)
    refined_plans: list[dict[str, Any]]  # Holds the refined plans if query returned no results
    retry_count: int  # Number of retries
    refined_count: int  # Number of times the query has been refined
    column_removal_count: int  # Number of times invalid columns have been removed inline
    removed_columns: list[str]  # List of columns that were removed due to being invalid
    error_history: list[str]  # List of errors encountered
    error_reasoning: list[str]  # List of reasoning for each error correction
    refined_reasoning: list[str]  # List of reasoning for each refinement
    last_attempt_time: Optional[str]  # Last time the query was attempted
