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
    error_history = state.get("error_history", [])

    print("original_query", original_query)
    print("error_history", error_history)

    prompt = f"""The following SQL query generated an error; please analyze the error closely and try not to repeat the issue:
    Database schema:
    {schema}

    Original query:
    {original_query}

    Error history:
    {chr(10).join(error_history)}

    Please analyze the error and previous attempts, then suggest a corrected query. Return ONLY the corrected SQL query without any explanation or formatting.

    Important: 
    Return ONLY the raw SQL query without any markdown formatting, quotes, or code blocks.
    For example, instead of:    
    ```sql
    SELECT * FROM table
    ```
    Just return:
    SELECT * FROM table

    Also, please append 'FOR JSON AUTO' to the query to format the result as JSON
    and wrap the query in another select statement that returns json:

    select (
        <query> FOR JSON AUTO
    ) as json
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
        "current_step": "Correcting Query",
        "retry_count": state.get("retry_count", 0),
        "error_history": error_history
    }