"""State object for the SQL agent."""

from typing import Annotated, TypedDict, Optional, Any
from langgraph.graph.message import AnyMessage, add_messages


class State(TypedDict):
    """State object type for the SQL agent."""

    messages: Annotated[list[AnyMessage], add_messages]

    # Thread management
    thread_id: str  # Unique identifier for this conversation thread

    # Conversation history fields
    user_questions: list[str]  # History of all user questions in conversation
    user_question: str  # Current/latest user question (convenience field)
    is_continuation: bool  # Flag to indicate if continuing from previous query

    # Schema and planning
    schema: list[dict]  # Holds full schema information (JSON format)
    filtered_schema: Optional[list[dict]]  # Holds filtered schema (top-k relevant tables with ALL columns - for modification options)
    truncated_schema: Optional[list[dict]]  # Holds truncated schema (filtered tables with ONLY relevant columns - for planner context)
    schema_markdown: Optional[str]  # Schema formatted as markdown for LLM readability
    planner_outputs: list[dict[str, Any]]  # History of planner outputs
    planner_output: Optional[dict[str, Any]]  # Current/latest planner output (convenience field)

    # Query history and current query
    queries: list[str]  # History of all generated SQL queries
    query: str  # Current/latest generated SQL query (convenience field)
    result: str  # Holds query execution result
    total_records_available: Optional[int]  # Total records available before limit applied

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
    needs_clarification: bool  # Flag indicating planner needs clarification
    clarification_suggestions: list[str]  # LLM-generated query rewrite suggestions

    # Plan audit fields
    audit_passed: bool  # Whether plan audit passed validation
    audit_issues: list[str]  # List of issues detected by plan audit
    audit_corrections: list[str]  # List of corrections applied by plan audit
    audit_reasoning: Optional[str]  # Explanation of audit fixes

    # Plan patching fields
    executed_plan: Optional[dict[str, Any]]  # The plan that generated currently displayed results
    executed_query: Optional[str]  # The SQL query that generated currently displayed results
    patch_history: list[dict[str, Any]]  # History of user-applied patch operations
    patch_requested: bool  # Flag to route to transform_plan node
    current_patch_operation: Optional[dict[str, Any]]  # The patch operation to apply
    modification_options: Optional[dict[str, Any]]  # Available modification options for UI
    parent_query_id: Optional[str]  # ID of query that was patched (for lineage tracking)
