"""Tool definitions for the conversational data assistant.

Every chat reply is a `respond` tool call. The optional `revised_sql` +
`explanation` fields let the agent bundle a SQL revision into the same
call whenever the reply involves SQL changes. `run_query` is separate —
it re-runs the pipeline end-to-end for genuinely new questions.
"""

from langchain_core.tools import tool


@tool
def run_query(query: str) -> str:
    """Run a natural language query against the database and return results.

    Use this when the user asks something that CANNOT be answered from the
    current result set — different tables, different time range, or a
    fundamentally different question.

    Args:
        query: Natural language question about the database
    """
    # Execution is handled by the agentic loop in chat_agent.py,
    # not by this function body. The @tool decorator is used purely
    # for schema generation so the LLM knows the tool signature.
    pass


@tool
def respond(
    message: str,
    revised_sql: str | None = None,
    explanation: str | None = None,
) -> str:
    """Reply to the user. This is the ONLY way to respond — every turn ends with a respond call.

    Always set `message` to your user-facing reply (markdown).

    Include `revised_sql` + `explanation` WHENEVER the reply involves or could involve
    a SQL change — fixing a data-quality issue, adding/removing a column, changing a
    filter, correcting a join, adjusting sorting, or proposing any other SQL improvement.
    Never describe a problem with the SQL without proposing the fix in the same call.
    If you include `revised_sql`, you must also include `explanation`.

    Omit `revised_sql` and `explanation` only for pure-commentary replies that don't
    touch the SQL (answering a question from the data, acknowledgments, etc.).

    Args:
        message: Your response text to the user (markdown). Summarize findings and explain changes.
        revised_sql: Optional — a complete revised SELECT query, ready to execute as-is.
            Required iff the reply involves a SQL change.
        explanation: Optional — one-line summary of what changed in the SQL.
            Required iff revised_sql is set.
    """
    # Execution is handled by the agentic loop in chat_agent.py,
    # not by this function body.
    pass


CHAT_TOOLS = [run_query, respond]
RESPOND_ONLY_TOOLS = [respond]
