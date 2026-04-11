"""Tool definitions for the conversational data assistant.

Defines tools that the chat agent can invoke during conversation,
enabling it to re-run queries when the user's question cannot be
answered from the current result set.
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


CHAT_TOOLS = [run_query]
