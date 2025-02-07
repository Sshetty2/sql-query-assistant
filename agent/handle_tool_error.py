from langchain_openai import ChatOpenAI
from langchain.schema import AIMessage
from typing import Any
from agent.generate_query import get_json_format_instructions, get_sql_return_instructions
from dotenv import load_dotenv
import os

load_dotenv()

def handle_tool_error(state) -> dict:
    """Handle errors from query execution by getting LLM to analyze and suggest fixes."""
    error_message = state["messages"][-1].content
    original_query = state["query"]
    schema = state["schema"]
    error_history = state.get("error_history", [])
    json_instructions = get_json_format_instructions()
    sql_return_instructions = get_sql_return_instructions()

    prompt = f"""The following SQL query generated an error; please analyze the error closely and try not to repeat the issue:
    Database schema:
    {schema}

    Original query:
    {original_query}

    Error history:
    {chr(10).join(error_history)}

    Please analyze the error and previous attempts, then suggest a corrected query. Return ONLY the corrected SQL query without any explanation or formatting.

    {json_instructions}

    {sql_return_instructions}
    """

    llm = ChatOpenAI(model=os.getenv("AI_MODEL"), temperature=.3)
    corrected_query = llm.invoke(prompt).content.strip()

    return {
        **state,
        "messages": [AIMessage(content="Generated corrected SQL query")],
        "query": corrected_query,
        "corrected_queries": state["corrected_queries"] + [original_query],
        "last_step": "handle_tool_error",
    }