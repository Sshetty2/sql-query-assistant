"""Generate a SQL query based on the question and schema."""

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage
from agent.state import State

load_dotenv()


def get_sql_return_instructions():
    """Get instructions for returning only the raw SQL query."""
    database_type = "SQLite" if os.getenv("USE_TEST_DB", "").lower() == "true" else "SQL Server"
    return f"""
    The Database is {database_type}.
    Important: Return ONLY the raw SQL query without any markdown formatting, quotes, code blocks, or JSON formatting.
    Do NOT use FOR JSON AUTO or json_object/json_group_array functions.
    For example, instead of:
    ```sql
    SELECT * FROM table
    ```
    Just return:
    SELECT * FROM table
    """


def generate_query(state: State):
    """Generate SQL query based on the question and schema."""
    try:
        question = state["messages"][0].content  # Get the original question
        schema = state["schema"]  # Schema information

        sort_order = state["sort_order"]
        result_limit = state["result_limit"]
        time_filter = state["time_filter"]

        query_modifications = []

        if sort_order != "Default":
            query_modifications.append(
                f"The results should be ordered {sort_order.lower()}"
            )

        if result_limit > 0:
            query_modifications.append(f"Limit the results to {result_limit} records")

        if time_filter != "All Time":
            days_map = {
                "Last 30 Days": 30,
                "Last 60 Days": 60,
                "Last 90 Days": 90,
                "Last Year": 365,
            }
            days = days_map.get(time_filter)
            if days:
                query_modifications.append(
                    f"Filter the results to only include records from the last {days} days "
                    "using appropriate date/timestamp columns"
                )

        modifications_text = "\n".join([f"- {mod}" for mod in query_modifications])

        prompt = f"""Given this truncated database schema:
        {schema}

        Generate a SQL query to answer this question: {question}

        {get_sql_return_instructions()}

        Additional requirements:
        {modifications_text if modifications_text else "None"}
        """

        llm = ChatOpenAI(model=os.getenv("AI_MODEL"), temperature=0.3)
        response = llm.invoke(prompt)

        query = response.content.strip()

        return {
            **state,
            "messages": [AIMessage(content="Generated SQL Query")],
            "query": query,
            "last_step": "generate_query",
        }
    except Exception as e:
        return {
            **state,
            "messages": [AIMessage(content=f"Error generating query: {str(e)}")],
            "last_step": "generate_query",
        }
