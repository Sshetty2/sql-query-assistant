from agent.state import State
from langchain_core.messages import AIMessage

import pyodbc

def execute_query(state: State, tools, db_connection):
    """Execute the SQL query and return the result."""
    try:
        query = state["query"]
        cursor = db_connection.cursor()
        cursor.execute(query)
        result = cursor.fetchall()
        cursor.close()

        return {
            "messages": [AIMessage(content=f"Query Successfully Executed")],
            "result": result,
            "query": query,
            "sort_order": state["sort_order"],
            "result_limit": state["result_limit"],
            "time_filter": state["time_filter"],
            "current_step": "Executing Query"
        }
    except Exception as e:
        if cursor:
            cursor.close()
        return {
            "messages": [AIMessage(content=f"Error executing query: {e}")],
            "current_step": "Error in Query Execution"
        }