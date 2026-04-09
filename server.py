import json
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, Literal, List, Any, Dict
from dotenv import load_dotenv
from agent.query_database import query_database
from utils.logger import get_logger

load_dotenv()
logger = get_logger()

SORT_ORDER_OPTIONS = Literal["Default", "Ascending", "Descending"]
TIME_FILTER_OPTIONS = Literal[
    "All Time", "Last 24 Hours", "Last 7 Days", "Last 30 Days", "Last Year"
]

# No CORS middleware needed — the API is not publicly accessible.
# All requests come through the frontend's Node proxy via Railway private networking.
app = FastAPI(
    title="SQL Query Assistant API",
    description="""
    This API converts natural language queries into SQL queries and executes them on an SQL Server database.
    - Supports **sorting, result limits, and time filters** for enhanced querying.
    - Uses **LangChain-powered SQL generation** for natural language understanding.
    """,
    version="2.0.0",
    contact={},
)


def parse_query_result(result):
    """Parse the query result from JSON string."""
    try:
        if not result:
            return None

        # Result is now a JSON string from execute_query
        if isinstance(result, str):
            return json.loads(result)

        return result
    except json.JSONDecodeError as e:
        logger.error(
            f"Error parsing query result: {str(e)}",
            exc_info=True,
            extra={"result": result},
        )
        return None


def build_query_response(state: dict, metadata: dict = None) -> dict:
    """Transform workflow state into API response shape.

    Args:
        state: The final workflow state dict from query_database.
        metadata: Optional dict with thread_id, query_id from the workflow output.

    Returns:
        Dict matching the QueryResponse schema.
    """
    message_contents = [
        msg.content for msg in state.get("messages", [])
    ]
    parsed_result = parse_query_result(state.get("result"))
    tables_used = [
        table["table_name"] for table in state.get("schema", [])
    ]

    return {
        "messages": message_contents,
        "user_question": state.get("user_question", ""),
        "query": state.get("query", ""),
        "result": parsed_result,
        "sort_order": state.get("sort_order", "Default"),
        "result_limit": state.get("result_limit", 0),
        "time_filter": state.get("time_filter", "All Time"),
        "last_step": state.get("last_step", ""),
        "error_iteration": state.get("error_iteration", 0),
        "refinement_iteration": state.get("refinement_iteration", 0),
        "correction_history": state.get("correction_history", []),
        "refinement_history": state.get("refinement_history", []),
        "last_attempt_time": state.get("last_attempt_time"),
        "tables_used": tables_used,
        "thread_id": metadata.get("thread_id") if metadata else state.get("thread_id"),
        "query_id": metadata.get("query_id") if metadata else None,
        # Fields needed for plan patching and interactive modification
        "planner_output": state.get("planner_output"),
        "needs_clarification": state.get("needs_clarification", False),
        "clarification_suggestions": state.get("clarification_suggestions", []),
        "modification_options": state.get("modification_options"),
        "executed_plan": state.get("executed_plan"),
        "filtered_schema": state.get("filtered_schema"),
        "total_records_available": state.get("total_records_available"),
    }


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    """Represents a natural language query request for SQL generation."""

    prompt: str = Field(
        ...,  # Required
        title="Query Prompt",
        description="Natural language query to be converted into SQL.",
        examples=[
            "Show all users who logged in last week",
            "List the top 5 users with the most login attempts",
            "Show all vulnerabilities found in the last 30 days",
        ],
    )
    sort_order: Optional[SORT_ORDER_OPTIONS] = Field(
        default="Default",
        title="Sort Order",
        description="Sorting preference for query results.",
        examples=["Default", "Ascending", "Descending"],
    )
    result_limit: Optional[int] = Field(
        default=0,
        title="Result Limit",
        description="Maximum number of results to return (0 for no limit).",
        ge=0,
        examples=[0, 5, 10, 25, 100],
    )
    time_filter: Optional[TIME_FILTER_OPTIONS] = Field(
        default="All Time",
        title="Time Filter",
        description="Filter results based on a specific time range.",
        examples=[
            "All Time",
            "Last 24 Hours",
            "Last 7 Days",
            "Last 30 Days",
            "Last Year",
        ],
    )

    class Config:
        json_schema_extra = {
            "example": {
                "prompt": "Show me the top 5 users with most login attempts",
                "sort_order": "Descending",
                "result_limit": 5,
                "time_filter": "Last 30 Days",
            }
        }


class PatchRequest(BaseModel):
    """Request model for plan patching (interactive query modification)."""

    thread_id: str = Field(description="Thread ID from the original query")
    user_question: str = Field(description="Original user question")
    patch_operation: Dict[str, Any] = Field(
        description="Patch operation to apply (e.g., add_column, remove_column, modify_order_by, modify_limit)"
    )
    executed_plan: Dict[str, Any] = Field(
        description="The executed plan from the original query result"
    )
    filtered_schema: List[Dict[str, Any]] = Field(
        description="The filtered schema from the original query result"
    )


class QueryResponse(BaseModel):
    """Response model for the query endpoint."""

    messages: List[str] = Field(
        description="List of messages showing the progression of query processing"
    )
    user_question: str = Field(description="Original question asked by the user")
    query: str = Field(description="Final SQL query that was executed")
    result: Optional[Any] = Field(
        description="JSON representation of the query results"
    )
    sort_order: str = Field(description="Sort order used for the query")
    result_limit: int = Field(description="Maximum number of results requested")
    time_filter: str = Field(description="Time filter applied to the query")
    last_step: str = Field(description="Last step executed in the query pipeline")
    error_iteration: int = Field(
        default=0, description="Current error correction iteration"
    )
    refinement_iteration: int = Field(
        default=0, description="Current refinement iteration"
    )
    correction_history: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Structured history of error corrections",
    )
    refinement_history: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Structured history of refinements",
    )
    last_attempt_time: Optional[datetime] = Field(
        description="Timestamp of the last query attempt"
    )
    tables_used: List[str] = Field(
        description="List of database tables referenced in the query"
    )
    thread_id: Optional[str] = Field(
        default=None, description="Thread ID for this query session"
    )
    query_id: Optional[str] = Field(
        default=None, description="Unique query ID within the thread"
    )
    planner_output: Optional[Dict[str, Any]] = Field(
        default=None, description="Structured planner output"
    )
    needs_clarification: bool = Field(
        default=False, description="Whether the query needs clarification"
    )
    clarification_suggestions: List[str] = Field(
        default_factory=list, description="Suggested query rewrites"
    )
    modification_options: Optional[Dict[str, Any]] = Field(
        default=None, description="Available interactive modification options"
    )
    executed_plan: Optional[Dict[str, Any]] = Field(
        default=None, description="The plan that produced the current results"
    )
    filtered_schema: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Filtered schema used for this query"
    )
    total_records_available: Optional[int] = Field(
        default=None, description="Total records available before LIMIT"
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post(
    "/query",
    response_model=QueryResponse,
    summary="Generate and Execute SQL Query from Natural Language",
    description="""
    Converts a natural language question into an executable SQL query and returns the results.

    The endpoint:
    - Analyzes the question and relevant schema
    - Generates an appropriate SQL query
    - Executes the query against the database
    - Refines the query if needed for better results
    - Returns both the query process details and results
    """,
)
async def process_query(request: QueryRequest) -> QueryResponse:
    """Process a natural language query and return both the SQL query and results."""
    try:
        output = query_database(
            request.prompt,
            sort_order=request.sort_order,
            result_limit=request.result_limit,
            time_filter=request.time_filter,
        )

        state = output["state"]
        return build_query_response(state, output)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/query/stream",
    summary="Stream Query Execution via SSE",
    description="""
    Converts a natural language question into SQL and streams execution progress
    via Server-Sent Events (SSE).

    Event types:
    - `status`: Workflow step progress (node_name, node_status, node_message)
    - `complete`: Final query result with full response data
    - `error`: Error details if the workflow fails
    """,
)
async def stream_query(request: QueryRequest):
    """Stream query execution progress via Server-Sent Events."""

    def event_generator():
        try:
            stream = query_database(
                request.prompt,
                sort_order=request.sort_order,
                result_limit=request.result_limit,
                time_filter=request.time_filter,
                stream_updates=True,
            )

            for update in stream:
                if update.get("type") == "complete":
                    state = update["state"]
                    response_data = build_query_response(state, update)
                    yield f"event: complete\ndata: {json.dumps(response_data, default=str)}\n\n"
                else:
                    # Status or log event from workflow nodes
                    event_data = {
                        "type": "status",
                        "node_name": update.get("node_name"),
                        "node_status": update.get("node_status"),
                        "node_message": update.get("node_message"),
                        "node_logs": update.get("node_logs"),
                        "log_level": update.get("log_level"),
                    }
                    yield f"event: status\ndata: {json.dumps(event_data)}\n\n"

        except Exception as e:
            logger.error(f"Stream error: {str(e)}", exc_info=True)
            error_data = json.dumps({"type": "error", "detail": str(e)})
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post(
    "/query/patch",
    summary="Patch and Re-execute Query via SSE",
    description="""
    Apply a plan patch (add/remove columns, modify ORDER BY, adjust LIMIT)
    and stream the re-execution via Server-Sent Events.
    """,
)
async def patch_query(request: PatchRequest):
    """Apply a plan patch and stream re-execution via SSE."""

    def event_generator():
        try:
            stream = query_database(
                request.user_question,
                patch_operation=request.patch_operation,
                executed_plan=request.executed_plan,
                filtered_schema=request.filtered_schema,
                thread_id=request.thread_id,
                stream_updates=True,
            )

            for update in stream:
                if update.get("type") == "complete":
                    state = update["state"]
                    response_data = build_query_response(state, update)
                    yield f"event: complete\ndata: {json.dumps(response_data, default=str)}\n\n"
                else:
                    event_data = {
                        "type": "status",
                        "node_name": update.get("node_name"),
                        "node_status": update.get("node_status"),
                        "node_message": update.get("node_message"),
                        "node_logs": update.get("node_logs"),
                        "log_level": update.get("log_level"),
                    }
                    yield f"event: status\ndata: {json.dumps(event_data)}\n\n"

        except Exception as e:
            logger.error(f"Patch stream error: {str(e)}", exc_info=True)
            error_data = json.dumps({"type": "error", "detail": str(e)})
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/", summary="Health Check", description="Returns the API status.")
def health_check():
    return {"message": "SQL Query Assistant API is running!"}
