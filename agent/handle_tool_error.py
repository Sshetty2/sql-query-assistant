"""Handle errors from query execution by having LLM analyze and suggest fixes."""

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.schema import AIMessage
from agent.generate_query import (
    get_json_format_instructions,
    get_sql_return_instructions,
)

load_dotenv()


def handle_tool_error(state) -> dict:
    """Handle errors from query execution by getting LLM to analyze and suggest fixes."""
    error_message = state["messages"][-1].content
    original_query = state["query"]
    schema = state["schema"]
    error_history = state["error_history"][:-1]
    json_instructions = get_json_format_instructions()
    sql_return_instructions = get_sql_return_instructions()

    prompt = f"""The following SQL query generated an error;
    please analyze the error closely and try not to repeat the issue:

    Be sure to check whether or not the column exists in the table you're querying based on the schema.
    Truncated Database schema:
    {schema}

    Erroring query:
    {original_query}

    **Latest error message:**
    {error_message}

    Error history:
    {chr(10).join(error_history)}

    Please analyze the error and previous attempts, then suggest a corrected query.
    Return ONLY the corrected SQL query without any explanation or formatting.

    You may need to remove and time filters from the query which may be causing the error.

    {json_instructions}

    {sql_return_instructions}
    """

    llm = ChatOpenAI(model=os.getenv("AI_MODEL"), temperature=0.3)
    corrected_query = llm.invoke(prompt).content.strip()

    return {
        **state,
        "messages": [AIMessage(content="Generated corrected SQL query")],
        "query": corrected_query,
        "retry_count": state["retry_count"] + 1,
        "corrected_queries": state["corrected_queries"] + [original_query],
        "last_step": "handle_tool_error",
    }
