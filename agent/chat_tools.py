"""Tool definitions for the conversational data assistant.

Defines tools that the chat agent can invoke during conversation,
enabling it to re-run queries when the user's question cannot be
answered from the current result set, or to respond with SQL revisions
for the user to review before execution.
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
def respond_with_revision(message: str, revised_sql: str, explanation: str) -> str:
    """Respond to the user with a SQL revision suggestion.

    Use this instead of a plain text response whenever your answer involves
    a SQL improvement, fix, or modification. Your message text will be shown
    to the user, and the revised SQL will appear in a reviewable card with
    Execute/Dismiss buttons.

    Prefer this over a plain text response whenever you can improve the SQL —
    e.g., fix a data quality issue, add missing filters, correct joins,
    adjust sorting, add/remove columns, or optimize the query.

    Args:
        message: Your response text to the user (markdown). Summarize findings and explain changes.
        revised_sql: Complete revised SQL query (ready to execute as-is, SELECT only)
        explanation: One-line summary of what changed (shown in the revision card header)
    """
    # Execution is handled by the agentic loop in chat_agent.py,
    # not by this function body.
    pass


CHAT_TOOLS = [run_query, respond_with_revision]
SUGGEST_ONLY_TOOLS = [respond_with_revision]
