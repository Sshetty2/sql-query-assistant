"""Conversational data assistant for answering questions about query results.

Uses LangChain LCEL chains with in-memory conversation history to provide
a chat interface for exploring and understanding query results.

Supports an agentic loop where the LLM can invoke tools (e.g., run_query)
to re-execute queries when the user's question cannot be answered from
the current result set.
"""

import json
import os
import threading
from typing import Generator, Optional

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from agent.chat_tools import CHAT_TOOLS, SUGGEST_ONLY_TOOLS
from utils.llm_factory import get_chat_llm, get_model_for_stage
from utils.logger import get_logger
from utils.stream_utils import emit_node_status

# Debug directory — always write chat debug files (no flag gating)
_DEBUG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "debug")


def _write_debug(filename: str, content: str) -> None:
    """Write content to a debug file (always, no gating)."""
    try:
        os.makedirs(_DEBUG_DIR, exist_ok=True)
        path = os.path.join(_DEBUG_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        logger.debug(f"Failed to write debug file {filename}: {e}")

logger = get_logger()

# In-memory conversation store: session_id -> InMemoryChatMessageHistory
_chat_sessions: dict[str, InMemoryChatMessageHistory] = {}
_chat_lock = threading.Lock()

# Tool call budget tracking: session_id -> count of tool calls used
_tool_call_counts: dict[str, int] = {}
MAX_TOOL_CALLS = int(os.getenv("MAX_CHAT_TOOL_CALLS", "3"))

_CHAT_COMMON_INTRO = """\
This is a SQL Query Assistant — a tool that converts natural language \
questions into SQL queries and runs them against a database. The user has just run a query \
and is now exploring the results with follow-up questions.

Here's what you have to work with:
- The original question and the SQL query that was executed
- Database schema context (tables, columns, and relationships involved)
- The query plan (how the system decided which tables and joins to use)
- Statistical summary of all result columns (exact numbers — counts, averages, ranges, etc.)
- A representative sample of the raw data

Please help the user understand their results:
- Answer statistical questions using the summary data (counts, averages, distributions)
- Identify patterns or trends visible in the data
- Explain what the results show in plain language
- Point out notable values like outliers, dominant categories, or date ranges
- Use schema context to clarify what columns represent and how tables relate
- Reference the query plan to explain why certain tables or joins were chosen

A few guidelines:
- Be concise and direct. Use actual numbers from the summary when answering.
- Don't fabricate data — only reference what's in the summary or sample.
- When citing specific values, quote them from the data provided.
- Format your responses using Markdown: use **bold** for key numbers and terms, \
bullet lists for multiple points, and short paragraphs. Keep it scannable."""

CHAT_SYSTEM_PROMPT = _CHAT_COMMON_INTRO + """

**Tool usage — act, don't ask:**
When a user's message implies a query change or a new data request, \
**use the appropriate tool immediately**. Do NOT ask "would you like me to…", \
"should I run a query?", or "shall I revise the SQL?" — just do it. \
The UI will prompt the user for confirmation where needed.
- **suggest_revision**: Use when the user asks to **modify, tweak, or filter \
the current query** (e.g., "add a WHERE clause", "sort by date", \
"remove the LIMIT", "add a column", "change the join"). \
Write the complete revised SQL and a short explanation of what changed. \
The user will review it before execution.
- **run_query**: Use when the user asks about **completely different data** \
that requires a new query from scratch (different tables, different question).
- When writing revised SQL, always produce a complete, executable query — \
not a diff or fragment. Base it on the current SQL shown in the data context.
- **Only write SELECT queries.** Never produce INSERT, UPDATE, DELETE, DROP, \
CREATE, ALTER, or any other data-modifying statement.

## Data Context:
{data_context}"""

CHAT_SYSTEM_PROMPT_SUGGEST_ONLY = _CHAT_COMMON_INTRO + """

**Tool usage — act, don't ask:**
When the user's message implies a query change, **use the tool immediately**. \
Do NOT ask "would you like me to…" or "shall I revise?" — just do it. \
The UI will prompt the user for confirmation.
- You can no longer run new queries, but you can still suggest revisions \
to the current SQL query using the **suggest_revision** tool.
- If the user asks to **modify, tweak, or filter the current query**, \
use the **suggest_revision** tool with complete revised SQL and an explanation.
- If the user asks about completely different data, let them know they should \
run a new query from the main input.
- **Only write SELECT queries.** Never produce INSERT, UPDATE, DELETE, DROP, \
CREATE, ALTER, or any other data-modifying statement.

## Data Context:
{data_context}"""

CHAT_SYSTEM_PROMPT_NO_TOOLS = _CHAT_COMMON_INTRO + """

- You don't have query tools available right now. \
If the user asks about data that isn't in the current result set, \
let them know what's missing and suggest they run a new query from the main input.

## Data Context:
{data_context}"""


def _format_schema_context(filtered_schema: list[dict]) -> str:
    """Format filtered schema into a concise context block.

    Shows each table with its columns and foreign key relationships.
    """
    lines = []
    for table in filtered_schema:
        table_name = table.get("table_name", "?")
        columns = table.get("columns", [])
        col_names = [
            f"{c.get('column_name', '?')} ({c.get('data_type', '?')})"
            for c in columns[:20]  # cap at 20 columns per table
        ]
        line = f"- **{table_name}**: {', '.join(col_names)}"
        if len(columns) > 20:
            line += f" ... (+{len(columns) - 20} more)"
        lines.append(line)

        # Foreign keys
        fks = table.get("foreign_keys", [])
        for fk in fks:
            from_col = fk.get("from_column", "?")
            to_table = fk.get("to_table", "?")
            to_col = fk.get("to_column", "?")
            lines.append(f"  FK: {table_name}.{from_col} -> {to_table}.{to_col}")

    return "\n".join(lines)


def _format_plan_context(planner_output: dict) -> str:
    """Format planner output into a concise context block."""
    lines = []

    # Decision and reason
    decision = planner_output.get("decision", "proceed")
    reason = planner_output.get("reason")
    if reason:
        lines.append(f"- Decision: {decision} — {reason}")

    # Tables selected
    selections = planner_output.get("selections", [])
    for sel in selections:
        table = sel.get("table", "?")
        cols = [c.get("name", "?") for c in sel.get("columns", [])]
        filters = sel.get("filters", [])
        line = f"- {table}: columns=[{', '.join(cols)}]"
        if filters:
            filter_strs = [
                f"{f.get('column', '?')} {f.get('operator', '?')} {f.get('value', '?')}"
                for f in filters
            ]
            line += f", filters=[{'; '.join(filter_strs)}]"
        lines.append(line)

    # Joins
    joins = planner_output.get("join_edges", [])
    for j in joins:
        lines.append(
            f"- JOIN: {j.get('from_table', '?')}.{j.get('from_column', '?')} = "
            f"{j.get('to_table', '?')}.{j.get('to_column', '?')}"
        )

    # Aggregations
    aggs = planner_output.get("aggregations", [])
    if aggs:
        agg_strs = [
            f"{a.get('function', '?')}({a.get('table', '?')}.{a.get('column', '?')})"
            for a in aggs
        ]
        lines.append(f"- Aggregations: {', '.join(agg_strs)}")

    # Order by / limit
    order_by = planner_output.get("order_by", [])
    if order_by:
        ord_strs = [
            f"{o.get('table', '?')}.{o.get('column', '?')} {o.get('direction', 'ASC')}"
            for o in order_by
        ]
        lines.append(f"- ORDER BY: {', '.join(ord_strs)}")

    limit = planner_output.get("limit")
    if limit:
        lines.append(f"- LIMIT: {limit}")

    return "\n".join(lines)


def prepare_data_context(
    result_json: str,
    data_summary: dict,
    sql_query: str,
    user_question: str,
    max_sample_rows: int = 15,
    filtered_schema: list[dict] | None = None,
    planner_output: dict | None = None,
) -> str:
    """Build a concise context string for the LLM from query results.

    Includes the original question, SQL, schema context, query plan,
    summary statistics, and a representative data sample.

    Args:
        result_json: JSON string of query results.
        data_summary: Summary dict from compute_data_summary.
        sql_query: The SQL query that produced these results.
        user_question: The original natural language question.
        max_sample_rows: Max rows to include in the sample.
        filtered_schema: Optional filtered schema (tables/columns/FKs used).
        planner_output: Optional planner output (query plan decisions).

    Returns:
        Formatted context string for injection into the system prompt.
    """
    parts = []

    # Original question and SQL
    parts.append(f"### Original Question\n{user_question}")
    parts.append(f"### SQL Query\n```sql\n{sql_query}\n```")

    # Schema context
    if filtered_schema:
        parts.append("### Database Schema (tables used)")
        parts.append(_format_schema_context(filtered_schema))

    # Query plan
    if planner_output:
        parts.append("### Query Plan")
        parts.append(_format_plan_context(planner_output))

    # Summary statistics
    if data_summary:
        parts.append("### Summary Statistics")
        parts.append(
            f"- Rows in result: {data_summary.get('row_count', 0)}"
        )
        total = data_summary.get("total_records_available")
        if total and total != data_summary.get("row_count"):
            parts.append(
                f"- Total records available (before LIMIT): {total}"
            )
        parts.append(
            f"- Columns: {data_summary.get('column_count', 0)}"
        )

        for col_name, col_stats in data_summary.get("columns", {}).items():
            col_type = col_stats.get("type", "unknown")
            null_count = col_stats.get("null_count", 0)
            distinct = col_stats.get("distinct_count", 0)

            line = f"\n**{col_name}** (type: {col_type}, distinct: {distinct}, nulls: {null_count})"
            parts.append(line)

            if col_type == "numeric":
                stats = []
                for key in ["min", "max", "avg", "median", "sum"]:
                    val = col_stats.get(key)
                    if val is not None:
                        stats.append(f"{key}={val}")
                if stats:
                    parts.append(f"  {', '.join(stats)}")

            elif col_type == "text":
                top = col_stats.get("top_values", [])
                if top:
                    top_str = ", ".join(
                        f'"{tv["value"]}" ({tv["count"]}x)' for tv in top[:5]
                    )
                    parts.append(f"  Top values: {top_str}")

            elif col_type == "datetime":
                dt_min = col_stats.get("min")
                dt_max = col_stats.get("max")
                range_d = col_stats.get("range_days")
                if dt_min and dt_max:
                    parts.append(f"  Range: {dt_min} to {dt_max} ({range_d} days)")

    # Representative data sample
    try:
        rows = json.loads(result_json) if isinstance(result_json, str) else result_json
        if rows and isinstance(rows, list):
            parts.append("### Data Sample")

            if len(rows) <= max_sample_rows:
                sample = rows
                parts.append(f"(All {len(rows)} rows shown)")
            else:
                head = rows[:10]
                tail = rows[-5:]
                sample = head + tail
                parts.append(
                    f"(Showing first 10 + last 5 of {len(rows)} rows)"
                )

            # Format as pipe-delimited table
            if sample:
                cols = list(sample[0].keys())
                header = " | ".join(cols)
                sep = " | ".join("-" * min(len(c), 20) for c in cols)
                parts.append(header)
                parts.append(sep)

                for i, row in enumerate(sample):
                    vals = []
                    for c in cols:
                        v = row.get(c)
                        if v is None:
                            vals.append("NULL")
                        else:
                            s = str(v)
                            if len(s) > 50:
                                s = s[:47] + "..."
                            vals.append(s)
                    parts.append(" | ".join(vals))

                    # Add separator between head and tail
                    if len(rows) > max_sample_rows and i == 9:
                        parts.append("... (rows omitted) ...")

    except (json.JSONDecodeError, TypeError):
        pass

    return "\n".join(parts)


def _get_session_history(session_id: str) -> InMemoryChatMessageHistory:
    """Get or create an in-memory chat history for a session.

    Used as the history_factory for RunnableWithMessageHistory.
    """
    with _chat_lock:
        if session_id not in _chat_sessions:
            _chat_sessions[session_id] = InMemoryChatMessageHistory()
        return _chat_sessions[session_id]


def get_chat_chain(data_context: str) -> RunnableWithMessageHistory:
    """Create a LangChain LCEL chain with conversation memory.

    Args:
        data_context: Pre-built context string from prepare_data_context.

    Returns:
        RunnableWithMessageHistory wrapping the chat chain.
    """
    model_name = get_model_for_stage("chat")
    # Fall back to strategy model if no chat-specific model is configured
    if not model_name:
        model_name = get_model_for_stage("strategy")
    llm = get_chat_llm(model_name=model_name, temperature=0.3)

    prompt = ChatPromptTemplate.from_messages([
        ("system", CHAT_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}"),
    ])

    chain = prompt | llm

    return RunnableWithMessageHistory(
        chain,
        _get_session_history,
        input_messages_key="input",
        history_messages_key="history",
    )


def stream_chat(
    session_id: str,
    message: str,
    data_context: str,
) -> Generator[str, None, None]:
    """Stream a chat response about query results.

    Uses LangChain's RunnableWithMessageHistory to automatically manage
    conversation turns in the in-memory store.

    Args:
        session_id: Unique session identifier (e.g., "{thread_id}:{query_id}").
        message: The user's chat message.
        data_context: Pre-built context string from prepare_data_context.

    Yields:
        String chunks of the LLM response.
    """
    chain = get_chat_chain(data_context)

    config = {"configurable": {"session_id": session_id}}

    for chunk in chain.stream(
        {"input": message, "data_context": data_context},
        config=config,
    ):
        if hasattr(chunk, "content") and chunk.content:
            yield chunk.content


def clear_chat_session(session_id: str) -> None:
    """Remove a chat session from the in-memory store.

    Call this when the user explicitly resets the conversation.

    Args:
        session_id: The session identifier to clear.
    """
    with _chat_lock:
        if session_id in _chat_sessions:
            del _chat_sessions[session_id]
            logger.debug(f"Cleared chat session: {session_id}")
        if session_id in _tool_call_counts:
            del _tool_call_counts[session_id]
            logger.debug(f"Cleared tool call count for session: {session_id}")


# ---------------------------------------------------------------------------
# Agentic chat loop (tool-calling)
# ---------------------------------------------------------------------------


def _get_tool_calls_remaining(session_id: str) -> int:
    """Return how many tool calls this session has left."""
    with _chat_lock:
        used = _tool_call_counts.get(session_id, 0)
    return max(0, MAX_TOOL_CALLS - used)


def stream_chat_agentic(
    session_id: str,
    message: str,
    data_context: str,
    thread_id: str,
    query_id: str,
    db_id: str | None = None,
) -> Generator[dict, None, None]:
    """Agentic chat loop that can invoke tools (e.g., run_query).

    Instead of a simple prompt-LLM chain, this function:
    1. Builds messages with system prompt + history + user message
    2. Binds tools if tool budget remaining, else uses plain LLM
    3. Calls LLM via invoke() (not stream) for reliable tool call detection
    4. If response has tool_calls: executes the tool, yields events, loops
    5. If text response: yields the final text

    Args:
        session_id: Chat session identifier.
        message: The user's message.
        data_context: Pre-built context string from prepare_data_context.
        thread_id: Thread ID for query execution.
        query_id: Query ID for the current result set.
        db_id: Optional demo database ID for query execution.

    Yields:
        Dicts with "type" key:
        - {"type": "token", "content": "..."} — full text response
        - {"type": "tool_start", "tool": "run_query", "input": {...}}
        - {"type": "tool_result", "result": <QueryResult dict>}
        - {"type": "complete", "content": "...", "tool_calls_remaining": N}
    """
    from agent.query_database import query_database
    from agent.generate_data_summary import compute_data_summary
    from server import build_query_response

    model_name = get_model_for_stage("chat")
    if not model_name:
        model_name = get_model_for_stage("strategy")
    llm = get_chat_llm(model_name=model_name, temperature=0.3)

    # Get conversation history
    history = _get_session_history(session_id)

    # Build current data context into system prompt
    tools_remaining = _get_tool_calls_remaining(session_id)

    if tools_remaining > 0:
        system_content = CHAT_SYSTEM_PROMPT.format(data_context=data_context)
    else:
        system_content = CHAT_SYSTEM_PROMPT_SUGGEST_ONLY.format(data_context=data_context)

    # Assemble messages: system + history + new user message
    messages = [{"role": "system", "content": system_content}]
    for hist_msg in history.messages:
        if isinstance(hist_msg, HumanMessage):
            messages.append({"role": "user", "content": hist_msg.content})
        elif isinstance(hist_msg, AIMessage):
            messages.append({"role": "assistant", "content": hist_msg.content})
        elif isinstance(hist_msg, ToolMessage):
            # Include tool messages in history for continuity
            messages.append(hist_msg)

    messages.append({"role": "user", "content": message})

    # Add user message to history
    history.add_message(HumanMessage(content=message))

    current_data_context = data_context

    # Agentic loop — keep going until LLM returns text (no tool calls)
    # Extra headroom: suggest_revision calls don't count against budget
    max_iterations = MAX_TOOL_CALLS + 3  # safety cap
    for _iteration in range(max_iterations):
        # Bind tools: full set if budget allows, suggest_revision-only otherwise
        tools_remaining = _get_tool_calls_remaining(session_id)
        if tools_remaining > 0:
            bound_llm = llm.bind_tools(CHAT_TOOLS)
        else:
            bound_llm = llm.bind_tools(SUGGEST_ONLY_TOOLS)

        # Call LLM (invoke, not stream, for reliable tool call detection)
        logger.info(
            f"[chat-agent] Loop iteration {_iteration}: "
            f"messages={len(messages)}, tools_bound={tools_remaining > 0}"
        )
        try:
            response = bound_llm.invoke(messages)
        except Exception as e:
            logger.error(f"[chat-agent] LLM invoke error: {e}", exc_info=True)
            yield {"type": "error", "detail": str(e)}
            return

        has_tool_calls = bool(getattr(response, "tool_calls", None))
        content_type = type(response.content).__name__ if hasattr(response, "content") else "N/A"
        logger.info(
            f"[chat-agent] Loop iteration {_iteration} complete: "
            f"tool_calls={has_tool_calls}, content_type={content_type}"
        )

        # Check if the LLM wants to call a tool
        tool_calls = getattr(response, "tool_calls", None)
        if tool_calls and len(tool_calls) > 0:
            tool_call = tool_calls[0]  # Handle one tool call at a time
            tool_name = tool_call.get("name", "")
            tool_args = tool_call.get("args", {})
            tool_call_id = tool_call.get("id", "")

            logger.info(
                f"[chat-agent] Tool call: {tool_name}({tool_args}) "
                f"[remaining={tools_remaining}]"
            )

            if tool_name == "suggest_revision":
                revised_sql = tool_args.get("revised_sql", "")
                explanation = tool_args.get("explanation", "")

                logger.info(
                    f"[chat-agent] suggest_revision: {explanation[:80]}..."
                )

                # Yield suggest_revision event to frontend
                yield {
                    "type": "suggest_revision",
                    "revised_sql": revised_sql,
                    "explanation": explanation,
                }

                # Do NOT increment tool call counter (lightweight, no DB call)

                # Build a ToolMessage to inform the LLM the suggestion was shown
                tool_result_text = (
                    "The revised SQL has been shown to the user for review. "
                    "They will decide whether to execute it. "
                    "Provide a brief summary of the changes you proposed."
                )

                # Append to messages for next iteration
                messages.append(response)
                messages.append(
                    ToolMessage(
                        content=tool_result_text,
                        tool_call_id=tool_call_id,
                    )
                )

                # Continue loop — LLM will summarize the suggestion
                continue

            elif tool_name == "run_query" and tools_remaining > 0:
                query_text = tool_args.get("query", "")

                # Yield tool_start event
                yield {
                    "type": "tool_start",
                    "tool": "run_query",
                    "input": {"query": query_text},
                }

                # Execute the query via streaming mode and collect the
                # final "complete" event.  query_database is always a
                # generator (Python treats any function with `yield`
                # as a generator), so we must iterate to get results.
                #
                # We pass chat_session_id=None to skip narrative
                # generation — the chat agent will summarize the
                # results itself in the next LLM turn.
                try:
                    output = None
                    for update in query_database(
                        query_text,
                        stream_updates=True,
                        chat_session_id=None,
                        db_id=db_id,
                    ):
                        if update.get("type") == "complete":
                            output = update
                        elif update.get("node_name"):
                            # Forward workflow status events to the frontend
                            yield {
                                "type": "status",
                                "node_name": update.get("node_name"),
                                "node_status": update.get("node_status"),
                                "node_message": update.get("node_message"),
                                "node_metadata": update.get("node_metadata"),
                            }

                    if output is None:
                        raise RuntimeError(
                            "Query workflow completed without producing a result"
                        )

                    state = output["state"]

                    # Ensure data_summary is populated before building
                    # the response (workflow may skip it for empty results).
                    new_result = state.get("result", "")
                    new_result_json = (
                        new_result if isinstance(new_result, str)
                        else json.dumps(new_result)
                    )
                    new_summary = state.get("data_summary")
                    if not new_summary:
                        total_records = state.get("total_records_available")
                        new_summary = compute_data_summary(
                            new_result_json, total_records
                        )
                        state["data_summary"] = new_summary

                    query_response = build_query_response(state, output)

                    # Yield tool_result with full QueryResult
                    yield {
                        "type": "tool_result",
                        "result": query_response,
                    }

                    # Increment tool call counter
                    with _chat_lock:
                        _tool_call_counts[session_id] = (
                            _tool_call_counts.get(session_id, 0) + 1
                        )
                    current_data_context = prepare_data_context(
                        result_json=new_result_json,
                        data_summary=new_summary or {},
                        sql_query=state.get("query", ""),
                        user_question=query_text,
                        filtered_schema=state.get("filtered_schema"),
                        planner_output=state.get("planner_output"),
                    )

                    # Build an informative tool result so the LLM can
                    # answer immediately without needing to re-query.
                    row_count = new_summary.get("row_count", 0) if new_summary else 0
                    sql_query = state.get("query", "")

                    # Include a data sample (first 10 rows) in the tool result
                    data_preview = ""
                    try:
                        rows = json.loads(new_result_json) if isinstance(new_result_json, str) else new_result_json
                        if rows and isinstance(rows, list):
                            sample = rows[:10]
                            cols = list(sample[0].keys())
                            header = " | ".join(cols)
                            lines = [header]
                            for row in sample:
                                vals = [str(row.get(c, "NULL"))[:40] for c in cols]
                                lines.append(" | ".join(vals))
                            if len(rows) > 10:
                                lines.append(f"... ({len(rows) - 10} more rows)")
                            data_preview = "\n".join(lines)
                    except (json.JSONDecodeError, TypeError):
                        pass

                    tool_result_text = (
                        f"Query executed successfully.\n"
                        f"SQL: {sql_query}\n"
                        f"Rows returned: {row_count}\n"
                    )
                    if data_preview:
                        tool_result_text += f"\nResults:\n{data_preview}\n"
                    if row_count == 0:
                        tool_result_text += (
                            "\nThe query returned no results. The system "
                            "already attempted refinement. Do NOT call "
                            "run_query again for this question — instead, "
                            "explain to the user that no matching data was "
                            "found and suggest they rephrase their question."
                        )
                    else:
                        tool_result_text += (
                            "\nThe system prompt has been updated with full "
                            "statistics and data context. Use the results "
                            "above to answer the user's question."
                        )

                    logger.info(
                        f"[chat-agent] Tool result: {row_count} rows, "
                        f"SQL: {sql_query[:80]}..."
                    )

                except Exception as e:
                    logger.error(f"Tool execution error: {e}", exc_info=True)
                    tool_result_text = (
                        f"Query execution failed: {str(e)}"
                    )
                    # Notify the frontend so it can show recovery options
                    yield {
                        "type": "tool_error",
                        "detail": str(e),
                        "query": query_text,
                    }
                    # Still increment to prevent infinite retries
                    with _chat_lock:
                        _tool_call_counts[session_id] = (
                            _tool_call_counts.get(session_id, 0) + 1
                        )

                # Append assistant tool call + tool result to messages for next iteration
                messages.append(response)
                messages.append(
                    ToolMessage(
                        content=tool_result_text,
                        tool_call_id=tool_call_id,
                    )
                )

                # Update system prompt with new data context
                new_tools_remaining = _get_tool_calls_remaining(session_id)
                if new_tools_remaining > 0:
                    messages[0] = {
                        "role": "system",
                        "content": CHAT_SYSTEM_PROMPT.format(
                            data_context=current_data_context
                        ),
                    }
                else:
                    messages[0] = {
                        "role": "system",
                        "content": CHAT_SYSTEM_PROMPT_SUGGEST_ONLY.format(
                            data_context=current_data_context
                        ),
                    }

                # Continue the loop — LLM will now summarize the tool result
                continue
            else:
                # Unknown tool — treat as text response
                logger.warning(f"Unknown tool call: {tool_name}")
        # No tool calls — this is a text response.
        # Anthropic can return content as a list of blocks after tool-use
        # exchanges, e.g. [{"type": "text", "text": "..."}].  Normalise
        # to a plain string.
        raw_content = response.content if hasattr(response, "content") else str(response)
        if isinstance(raw_content, list):
            # Extract text from content blocks
            parts = []
            for block in raw_content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    parts.append(block)
            content = "".join(parts)
            logger.info(
                f"[chat-agent] Normalised list content ({len(raw_content)} blocks) "
                f"to string ({len(content)} chars)"
            )
        else:
            content = raw_content

        logger.info(
            f"[chat-agent] Text response ready ({len(content)} chars), "
            f"yielding token + complete events"
        )

        # Save to history
        history.add_message(AIMessage(content=content))

        # Yield text and complete
        yield {"type": "token", "content": content}
        yield {
            "type": "complete",
            "content": content,
            "suggest_new_query": False,
            "suggested_query": None,
            "tool_calls_remaining": _get_tool_calls_remaining(session_id),
        }
        logger.info("[chat-agent] Agentic loop finished, all events yielded")
        return

    # Exhausted iterations without a text response — shouldn't happen
    logger.error("Agentic chat loop exhausted without producing a text response")
    yield {
        "type": "complete",
        "content": "I was unable to produce a response. Please try again.",
        "suggest_new_query": False,
        "suggested_query": None,
        "tool_calls_remaining": _get_tool_calls_remaining(session_id),
    }


# ---------------------------------------------------------------------------
# Auto-narrative generation (called from the LangGraph workflow)
# ---------------------------------------------------------------------------

NARRATIVE_USER_PROMPT = (
    "Please provide a brief summary of these query results in the context of "
    "the user's original question. Highlight key findings, notable patterns, "
    "and any important numbers. Keep it concise — 2-4 sentences."
)


def _get_chat_llm_for_narrative():
    """Get the LLM instance for narrative generation."""
    model_name = get_model_for_stage("chat")
    if not model_name:
        model_name = get_model_for_stage("strategy")
    return get_chat_llm(model_name=model_name, temperature=0.3)


def generate_narrative(data_context: str, session_id: str) -> str:
    """Generate a one-shot narrative summary of query results.

    Calls the LLM once (non-streaming) and seeds the conversation history
    so follow-up chat messages have context.

    Args:
        data_context: Pre-built context string from prepare_data_context.
        session_id: Session ID for conversation continuity.

    Returns:
        The narrative string.
    """
    llm = _get_chat_llm_for_narrative()

    system_msg = CHAT_SYSTEM_PROMPT.format(data_context=data_context)
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": NARRATIVE_USER_PROMPT},
    ]

    response = llm.invoke(messages)
    narrative = response.content if hasattr(response, "content") else str(response)

    # Seed the conversation history so follow-up chat sees this exchange
    history = _get_session_history(session_id)
    history.add_message(HumanMessage(content=NARRATIVE_USER_PROMPT))
    history.add_message(AIMessage(content=narrative))

    return narrative


def generate_query_narrative_node(state) -> dict:
    """LangGraph workflow node that generates an AI narrative after query execution.

    Runs after generate_data_summary. Uses the data summary + results
    to produce a conversational explanation of what the query found.
    """
    emit_node_status(
        "generate_query_narrative", "running", "Generating AI summary"
    )

    result = state.get("result")
    data_summary = state.get("data_summary")
    session_id = state.get("chat_session_id")

    # Skip if no results or no session ID
    if not result or not session_id:
        logger.warning(f"Skipping narrative: result={bool(result)}, session_id={session_id!r}")
        emit_node_status(
            "generate_query_narrative", "completed", "Skipped (no data)"
        )
        return {**state, "query_narrative": None}

    try:
        result_json = result if isinstance(result, str) else json.dumps(result)

        # Write data summary to debug
        _write_debug(
            "debug_data_summary.json",
            json.dumps(data_summary or {}, indent=2, default=str),
        )

        data_context = prepare_data_context(
            result_json=result_json,
            data_summary=data_summary or {},
            sql_query=state.get("query", ""),
            user_question=state.get("user_question", ""),
            filtered_schema=state.get("filtered_schema"),
            planner_output=state.get("planner_output"),
        )

        # Write full data context sent to LLM
        _write_debug("debug_chat_data_context.md", data_context)

        narrative = generate_narrative(data_context, session_id)

        # Write generated narrative
        _write_debug("debug_chat_narrative.md", narrative)

        emit_node_status(
            "generate_query_narrative", "completed", "AI summary generated"
        )
        return {**state, "query_narrative": narrative}

    except Exception as e:
        logger.error(f"Error generating narrative: {e}", exc_info=True)
        emit_node_status(
            "generate_query_narrative", "completed", "Summary generation failed"
        )
        return {**state, "query_narrative": None}
