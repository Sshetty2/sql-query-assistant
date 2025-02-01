from typing import Annotated, TypedDict, Optional
from langgraph.graph.message import AnyMessage, add_messages

class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    schema: str  # Holds schema information
    query: str  # Holds generated SQL query
    result: str  # Holds query execution result
    sort_order: str  # Holds sort order preference
    result_limit: int  # Holds result limit
    time_filter: str  # Holds time filter preference
    current_step: str  # Holds current step in the workflow
    corrected_query: Optional[str]  # Holds the corrected query if error occurred
