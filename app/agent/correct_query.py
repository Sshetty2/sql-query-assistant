from langchain_openai import ChatOpenAI
from langchain.schema import AIMessage
from typing import Any
from dotenv import load_dotenv
import os


load_dotenv()

def handle_tool_error(state) -> dict:
    """Handle errors from query execution by getting LLM to analyze and suggest fixes."""
    error_message = state["messages"][-1].content
    original_query = state["query"]
    schema = state["schema"]

    prompt = f"""The following SQL query generated an error:
    {original_query}

    Error message:
    {error_message}

    Database schema:
    {schema}

    Please analyze the error and suggest a corrected query. Return ONLY the corrected SQL query without any explanation or formatting.
    The query should still include 'FOR JSON AUTO' and be wrapped in a select statement that returns json.
    
    Important: Return ONLY the raw SQL query without any markdown formatting, quotes, or code blocks.
    For example, instead of:
    ```sql
    SELECT * FROM table
    ```
    Just return:
    SELECT * FROM table
    """

    llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL"), temperature=.3)
    corrected_query = llm.invoke(prompt).content.strip()

    return {
        "messages": [AIMessage(content="Generated corrected SQL query")],
        "query": corrected_query,
        "corrected_query": original_query,
        "schema": state["schema"],
        "sort_order": state["sort_order"],
        "result_limit": state["result_limit"],
        "time_filter": state["time_filter"],
        "current_step": "Correcting Query"
    }