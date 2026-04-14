import json
import os
import re
import threading
import time as _time
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, Literal, List, Any, Dict
from dotenv import load_dotenv
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


# ---------------------------------------------------------------------------
# Workflow cancellation registry
# ---------------------------------------------------------------------------
# Maps page_session_id -> (threading.Event, created_at_monotonic)
MAX_ACTIVE_SESSIONS = 200
_SESSION_STALE_SECONDS = 600  # 10 minutes

_active_sessions: dict[str, tuple[threading.Event, float]] = {}
_sessions_lock = threading.Lock()


def register_session(session_id: str) -> threading.Event:
    """Register a workflow for cancellation tracking. Returns a cancel event."""
    cancel_event = threading.Event()
    now = _time.monotonic()
    with _sessions_lock:
        # Evict stale sessions (older than 10 minutes)
        stale_cutoff = now - _SESSION_STALE_SECONDS
        stale_keys = [k for k, (_, t) in _active_sessions.items() if t < stale_cutoff]
        for k in stale_keys:
            evt, _ = _active_sessions.pop(k)
            evt.set()
        # Evict oldest if still at capacity
        if len(_active_sessions) >= MAX_ACTIVE_SESSIONS:
            oldest_key = min(_active_sessions, key=lambda k: _active_sessions[k][1])
            evt, _ = _active_sessions.pop(oldest_key)
            evt.set()
        old = _active_sessions.get(session_id)
        if old:
            old[0].set()  # Cancel previous request in same session
        _active_sessions[session_id] = (cancel_event, now)
    logger.info(
        f"Registered session {session_id[:8]}... (active: {len(_active_sessions)})"
    )
    return cancel_event


def cancel_session(session_id: str) -> bool:
    """Cancel a running workflow by session ID. Returns True if found."""
    with _sessions_lock:
        entry = _active_sessions.pop(session_id, None)
    if entry:
        entry[0].set()
        return True
    return False


def unregister_session(session_id: str):
    """Remove session from registry (normal completion)."""
    with _sessions_lock:
        _active_sessions.pop(session_id, None)


# Expected format: 64-char hex string (crypto.randomBytes(32).toString("hex"))
_PAGE_SESSION_RE = re.compile(r"^[0-9a-f]{64}$")


def _validate_page_session(raw: str | None) -> str | None:
    """Return the page session ID if it matches expected format, else None."""
    if raw and _PAGE_SESSION_RE.match(raw):
        return raw
    return None


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
    message_contents = [msg.content for msg in state.get("messages", [])]
    parsed_result = parse_query_result(state.get("result"))
    tables_used = [table["table_name"] for table in state.get("schema", [])]

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
        "data_summary": state.get("data_summary"),
        "query_narrative": state.get("query_narrative"),
    }


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    """Represents a natural language query request for SQL generation."""

    prompt: str = Field(
        ...,  # Required
        max_length=10000,
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

    chat_session_id: Optional[str] = Field(
        default=None,
        title="Chat Session ID",
        description="Frontend session ID for conversation continuity. Generated per browser session.",
    )

    db_id: Optional[str] = Field(
        default=None,
        title="Database ID",
        description="Demo database identifier (e.g. 'demo_db_1', 'demo_db_2'). Only used when USE_TEST_DB=true.",
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
    chat_session_id: Optional[str] = Field(
        default=None, description="Frontend session ID for conversation continuity"
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
    data_summary: Optional[Dict[str, Any]] = Field(
        default=None, description="Deterministic statistics computed from query results"
    )
    query_narrative: Optional[str] = Field(
        default=None, description="AI-generated narrative summary of query results"
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
    from agent.query_database import query_database

    try:
        output = query_database(
            request.prompt,
            sort_order=request.sort_order,
            result_limit=request.result_limit,
            time_filter=request.time_filter,
            chat_session_id=request.chat_session_id,
            db_id=request.db_id,
        )

        state = output["state"]
        return build_query_response(state, output)

    except Exception as e:
        logger.error(f"Query error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")


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
async def stream_query(request: QueryRequest, raw_request: Request):
    """Stream query execution progress via Server-Sent Events."""
    page_session = _validate_page_session(raw_request.headers.get("x-page-session"))
    logger.info(
        f"[stream] x-page-session header: {page_session[:8] + '...' if page_session else 'MISSING'}"
    )

    def event_generator():
        from agent.query_database import query_database

        cancel_event = register_session(page_session) if page_session else None
        try:
            stream = query_database(
                request.prompt,
                sort_order=request.sort_order,
                result_limit=request.result_limit,
                time_filter=request.time_filter,
                stream_updates=True,
                chat_session_id=request.chat_session_id,
                db_id=request.db_id,
                cancel_event=cancel_event,
                skip_modification_options=True,
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
                        "node_metadata": update.get("node_metadata"),
                    }
                    yield f"event: status\ndata: {json.dumps(event_data)}\n\n"

        except Exception as e:
            logger.error(f"Stream error: {str(e)}", exc_info=True)
            error_data = json.dumps({"type": "error", "detail": "Query failed. Please try rephrasing your question."})
            yield f"event: error\ndata: {error_data}\n\n"
        finally:
            if page_session:
                unregister_session(page_session)

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
async def patch_query(request: PatchRequest, raw_request: Request):
    """Apply a plan patch and stream re-execution via SSE."""
    page_session = _validate_page_session(raw_request.headers.get("x-page-session"))

    def event_generator():
        from agent.query_database import query_database

        cancel_event = register_session(page_session) if page_session else None
        try:
            stream = query_database(
                request.user_question,
                patch_operation=request.patch_operation,
                executed_plan=request.executed_plan,
                filtered_schema=request.filtered_schema,
                thread_id=request.thread_id,
                stream_updates=True,
                chat_session_id=request.chat_session_id,
                cancel_event=cancel_event,
                skip_modification_options=True,
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
                        "node_metadata": update.get("node_metadata"),
                    }
                    yield f"event: status\ndata: {json.dumps(event_data)}\n\n"

        except Exception as e:
            logger.error(f"Patch stream error: {str(e)}", exc_info=True)
            error_data = json.dumps({"type": "error", "detail": "Patch failed. Please try again."})
            yield f"event: error\ndata: {error_data}\n\n"
        finally:
            if page_session:
                unregister_session(page_session)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Chat endpoint — conversational data assistant
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Request model for chatting about query results."""

    thread_id: str = Field(description="Thread ID from the original query")
    query_id: str = Field(description="Query ID for the specific result set")
    message: str = Field(description="User's chat message about the results")
    session_id: Optional[str] = Field(
        default=None,
        description="Frontend session ID for conversation memory. Falls back to thread_id:query_id if not provided.",
    )
    db_id: Optional[str] = Field(
        default=None,
        description="Demo database ID. When set, the chat agent's run_query tool uses this database.",
    )


class ChatResetRequest(BaseModel):
    """Request model for resetting chat conversation memory."""

    session_id: str = Field(description="Session ID to clear from memory")


@app.post(
    "/query/chat",
    summary="Chat About Query Results via SSE",
    description="""
    Send a message about existing query results and receive a streamed LLM response.
    The chat agent can invoke tools (e.g., run_query) to fetch new data when needed.

    Event types:
    - `token`: A chunk of the response text {"content": "..."}
    - `tool_start`: Agent is executing a tool {"tool": "run_query", "input": {"query": "..."}}
    - `tool_result`: New query results from tool execution (full QueryResult shape)
    - `complete`: Final response with metadata {"content": "...", "tool_calls_remaining": N, ...}
    - `error`: Error details {"detail": "..."}
    """,
)
async def chat_query(request: ChatRequest):
    """Chat about query results via Server-Sent Events (agentic loop)."""
    from agent.chat_agent import (
        prepare_data_context,
        stream_chat_agentic,
    )
    from agent.generate_data_summary import compute_data_summary
    from utils.thread_manager import get_query_state

    def event_generator():
        try:
            # Load query state from thread storage
            state = get_query_state(request.thread_id, request.query_id)
            if not state:
                error_data = json.dumps(
                    {"detail": "Query not found for the given thread_id and query_id"}
                )
                yield f"event: error\ndata: {error_data}\n\n"
                return

            result_json = state.get("result", "")
            data_summary = state.get("data_summary")
            sql_query = state.get("query", "")
            user_question = state.get("user_question", "")

            if not result_json:
                error_data = json.dumps({"detail": "No results found for this query"})
                yield f"event: error\ndata: {error_data}\n\n"
                return

            # Compute summary on the fly if missing (backward compatibility)
            if not data_summary:
                total_records = state.get("total_records_available")
                data_summary = compute_data_summary(result_json, total_records)

            # Build context for the agentic loop
            session_id = request.session_id or f"{request.thread_id}:{request.query_id}"
            context = prepare_data_context(
                result_json,
                data_summary,
                sql_query,
                user_question,
                filtered_schema=state.get("filtered_schema"),
                planner_output=state.get("planner_output"),
            )

            # Stream events from the agentic loop
            for event in stream_chat_agentic(
                session_id=session_id,
                message=request.message,
                data_context=context,
                thread_id=request.thread_id,
                query_id=request.query_id,
                db_id=request.db_id,
            ):
                event_type = event.get("type", "")
                logger.info(f"[chat-sse] Emitting event: {event_type}")

                if event_type == "token":
                    content_preview = (
                        event["content"][:80] if event["content"] else "(empty)"
                    )
                    logger.info(f"[chat-sse] token: {content_preview!r}...")
                    token_data = json.dumps({"content": event["content"]})
                    yield f"event: token\ndata: {token_data}\n\n"

                elif event_type == "tool_start":
                    logger.info(
                        f"[chat-sse] tool_start: {event['tool']}({event['input']})"
                    )
                    tool_data = json.dumps(
                        {
                            "tool": event["tool"],
                            "input": event["input"],
                        }
                    )
                    yield f"event: tool_start\ndata: {tool_data}\n\n"

                elif event_type == "tool_result":
                    ds = (event.get("result") or {}).get("data_summary")
                    row_count = ds.get("row_count", "?") if ds else "?"
                    logger.info(f"[chat-sse] tool_result: {row_count} rows")
                    result_data = json.dumps(event["result"], default=str)
                    yield f"event: tool_result\ndata: {result_data}\n\n"

                elif event_type == "complete":
                    content_len = len(event.get("content", ""))
                    remaining = event.get("tool_calls_remaining", 0)
                    logger.info(
                        f"[chat-sse] complete: {content_len} chars, {remaining} tool calls remaining"
                    )
                    complete_data = json.dumps(
                        {
                            "content": event.get("content", ""),
                            "suggest_new_query": event.get("suggest_new_query", False),
                            "suggested_query": event.get("suggested_query"),
                            "tool_calls_remaining": event.get(
                                "tool_calls_remaining", 0
                            ),
                        }
                    )
                    yield f"event: complete\ndata: {complete_data}\n\n"

                elif event_type == "suggest_revision":
                    logger.info(
                        f"[chat-sse] suggest_revision: "
                        f"{event.get('explanation', '?')[:80]}"
                    )
                    suggest_data = json.dumps({
                        "revised_sql": event.get("revised_sql", ""),
                        "explanation": event.get("explanation", ""),
                    })
                    yield f"event: suggest_revision\ndata: {suggest_data}\n\n"

                elif event_type == "status":
                    event_data = {
                        "type": "status",
                        "node_name": event.get("node_name"),
                        "node_status": event.get("node_status"),
                        "node_message": event.get("node_message"),
                        "node_metadata": event.get("node_metadata"),
                    }
                    yield f"event: status\ndata: {json.dumps(event_data)}\n\n"

                elif event_type == "tool_error":
                    logger.warning(f"[chat-sse] tool_error: {event.get('detail', '?')}")
                    tool_err_data = json.dumps(
                        {
                            "detail": event.get("detail", "Unknown error"),
                            "query": event.get("query", ""),
                        }
                    )
                    yield f"event: tool_error\ndata: {tool_err_data}\n\n"

                elif event_type == "error":
                    logger.error(f"[chat-sse] error: {event.get('detail', '?')}")
                    error_data = json.dumps(
                        {"detail": event.get("detail", "Unknown error")}
                    )
                    yield f"event: error\ndata: {error_data}\n\n"

            logger.info("[chat-sse] Event generator finished")

        except Exception as e:
            logger.error(f"Chat stream error: {str(e)}", exc_info=True)
            error_data = json.dumps({"detail": "Chat request failed. Please try again."})
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
    "/query/chat/reset",
    summary="Reset Chat Conversation",
    description="Clear the in-memory conversation history for a given session.",
)
async def reset_chat(request: ChatResetRequest):
    """Clear chat session memory."""
    from agent.chat_agent import clear_chat_session

    clear_chat_session(request.session_id)
    return {"status": "ok", "session_id": request.session_id}


# ---------------------------------------------------------------------------
# Execute raw SQL (for approved chat revisions)
# ---------------------------------------------------------------------------


class ExecuteSQLRequest(BaseModel):
    """Request model for executing raw SQL directly."""

    sql: str = Field(
        ...,
        max_length=50000,
        description="The SQL query to execute directly",
    )
    thread_id: str = Field(description="Thread ID for state persistence")
    query_id: str = Field(description="Query ID for the current context")
    db_id: Optional[str] = Field(
        default=None,
        description="Demo database identifier",
    )


@app.post(
    "/query/execute-sql",
    summary="Execute Raw SQL via SSE",
    description="""
    Execute a raw SQL query directly against the database and stream results.
    Used for approved SQL revisions from the chat agent.
    Only SELECT statements are allowed.

    Event types:
    - `status`: Execution progress
    - `complete`: Full QueryResult
    - `error`: Error details
    """,
)
async def execute_sql(request: ExecuteSQLRequest):
    """Execute raw SQL and stream results via SSE."""

    def event_generator():
        try:
            from database.connection import get_pyodbc_connection
            from agent.generate_data_summary import compute_data_summary
            from agent.execute_query import json_serial
            from utils.thread_manager import get_query_state, save_query_state

            # Validate: SELECT only
            from utils.sql_safety import validate_select_only
            validate_select_only(request.sql)

            # Emit status: executing
            status_data = json.dumps({
                "type": "status",
                "node_name": "execute_sql",
                "node_status": "running",
                "node_message": "Executing SQL query",
            })
            yield f"event: status\ndata: {status_data}\n\n"

            # Open database connection and execute
            conn = get_pyodbc_connection(request.db_id)
            try:
                cursor = conn.cursor()
                cursor.execute(request.sql)
                columns = [col[0] for col in cursor.description]
                results = cursor.fetchall()
                data = [dict(zip(columns, row)) for row in results]
                total_count = len(data)
                json_result = json.dumps(data, default=json_serial)
                cursor.close()
            finally:
                conn.close()

            # Compute data summary
            data_summary = compute_data_summary(json_result, total_count)

            # Load original state to preserve schema/plan context
            original_state = (
                get_query_state(request.thread_id, request.query_id) or {}
            )

            # Build minimal state for the response
            state = {
                "messages": [],
                "user_question": original_state.get("user_question", ""),
                "query": request.sql,
                "result": json_result,
                "sort_order": "Default",
                "result_limit": 0,
                "time_filter": "All Time",
                "last_step": "execute_sql",
                "error_iteration": 0,
                "refinement_iteration": 0,
                "correction_history": [],
                "refinement_history": [],
                "last_attempt_time": datetime.now().isoformat(),
                "schema": original_state.get("schema", []),
                "planner_output": original_state.get("planner_output"),
                "executed_plan": original_state.get("executed_plan"),
                "filtered_schema": original_state.get("filtered_schema"),
                "needs_clarification": False,
                "clarification_suggestions": [],
                "modification_options": None,
                "total_records_available": total_count,
                "data_summary": data_summary,
                "query_narrative": None,
                "thread_id": request.thread_id,
            }

            # Save the new query state
            new_query_id = save_query_state(
                request.thread_id,
                state["user_question"],
                state,
            )

            # Build response
            response_data = build_query_response(
                state,
                {"thread_id": request.thread_id, "query_id": new_query_id},
            )

            # Emit completed status
            done_data = json.dumps({
                "type": "status",
                "node_name": "execute_sql",
                "node_status": "completed",
                "node_message": f"Query returned {total_count} rows",
            })
            yield f"event: status\ndata: {done_data}\n\n"

            yield f"event: complete\ndata: {json.dumps(response_data, default=str)}\n\n"

        except ValueError as ve:
            logger.warning(f"Execute SQL validation error: {ve}")
            error_data = json.dumps({"detail": str(ve)})
            yield f"event: error\ndata: {error_data}\n\n"
        except Exception as e:
            logger.error(f"Execute SQL error: {str(e)}", exc_info=True)
            error_data = json.dumps(
                {"detail": f"SQL execution failed: {str(e)}"}
            )
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


# ---------------------------------------------------------------------------
# Workflow cancellation
# ---------------------------------------------------------------------------


class CancelRequest(BaseModel):
    """Request model for cancelling a running workflow."""

    session_id: str = Field(description="Page session ID to cancel")


@app.post("/cancel", summary="Cancel Running Workflow")
async def cancel_running(request: CancelRequest):
    """Cancel any running workflow associated with the given page session."""
    found = cancel_session(request.session_id)
    logger.info(
        f"Cancel request for session {request.session_id[:8]}...: "
        f"{'found' if found else 'not found'}"
    )
    return {"status": "cancelled" if found else "not_found"}


# ---------------------------------------------------------------------------
# Database registry endpoints (multi-DB demo mode)
# ---------------------------------------------------------------------------


@app.get(
    "/databases",
    summary="List Demo Databases",
    description="Returns the list of available demo databases. Empty list if USE_TEST_DB is false.",
)
async def list_databases():
    """Return available demo databases from the registry."""
    if os.getenv("USE_TEST_DB", "").lower() != "true":
        return []

    registry_path = os.path.join(
        os.path.dirname(__file__), "databases", "registry.json"
    )
    if not os.path.exists(registry_path):
        return []

    with open(registry_path, "r") as f:
        return json.load(f)


@app.get(
    "/databases/{db_id}/schema",
    summary="Get Database Schema",
    description="Introspect and return the full schema for a demo database.",
)
async def get_database_schema(db_id: str):
    """Return introspected schema for a specific demo database."""
    from database.connection import get_demo_db_path
    from database.introspection import introspect_schema

    try:
        db_path = get_demo_db_path(db_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        schema = introspect_schema(conn)
        return schema
    finally:
        conn.close()


@app.get("/", summary="Health Check", description="Returns the API status.")
def health_check():
    return {"message": "SQL Query Assistant API is running!"}
