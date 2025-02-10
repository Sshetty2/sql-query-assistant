"""Execute the SQL query and return the result."""

from datetime import datetime
from agent.state import State
from langchain_core.messages import AIMessage


def execute_query(state: State, db_connection):
    """Execute the SQL query and return the result."""
    try:
        query = state["query"]
        cursor = db_connection.cursor()
        cursor.execute(query)
        result = cursor.fetchall()
        cursor.close()

        return {
            **state,
            "messages": [AIMessage(content="Query Successfully Executed")],
            "result": result,
            "last_step": "execute_query",
            "last_attempt_time": datetime.now().isoformat(),
        }
    except Exception as e:
        if cursor:
            cursor.close()

        error_history = state["error_history"]
        error_history.append(str(e))

        return {
            **state,
            "messages": [AIMessage(content=f"Error executing query: {e}")],
            "last_step": "execute_query",
            "result": None,
            "error_history": error_history,
            "last_attempt_time": datetime.now().isoformat(),
        }
