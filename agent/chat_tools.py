"""Tool definitions for the conversational data assistant.

Defines tools that the chat agent can invoke during conversation,
enabling it to re-run queries when the user's question cannot be
answered from the current result set, or to suggest SQL revisions
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
def suggest_revision(revised_sql: str, explanation: str) -> str:
    """Suggest a revised SQL query for the user to review before execution.

    Use this when the user asks to modify, tweak, or improve the current
    SQL query — e.g., add/remove columns, change filters, adjust sorting,
    or fix an issue. The revised SQL will be shown to the user for approval
    before it is executed. Do NOT use run_query for query modifications.

    Args:
        revised_sql: The complete revised SQL query (ready to execute as-is)
        explanation: Brief explanation of what changed and why
    """
    # Execution is handled by the agentic loop in chat_agent.py,
    # not by this function body.
    pass


CHAT_TOOLS = [run_query, suggest_revision]
SUGGEST_ONLY_TOOLS = [suggest_revision]
