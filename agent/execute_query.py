from agent.state import State
from langchain_core.messages import AIMessage

import pyodbc
from datetime import datetime, timedelta

def execute_query(state: State, tools, db_connection):
    """Execute the SQL query and return the result."""
    # Check if we need to enforce a timeout
    last_attempt_time = state.get("last_attempt_time")
    if last_attempt_time:
        # Convert string back to datetime if needed
        if isinstance(last_attempt_time, str):
            last_attempt_time = datetime.fromisoformat(last_attempt_time)
        
        # If less than 20 seconds since last attempt, enforce timeout
        if datetime.now() - last_attempt_time < timedelta(seconds=10):
            return {
                "messages": [AIMessage(content="Rate limit timeout: Please wait before retrying")],
                "current_step": "Rate Limited",
                "query": state["query"],
                "sort_order": state["sort_order"],
                "result_limit": state["result_limit"],
                "time_filter": state["time_filter"],
                "retry_count": state.get("retry_count", 0),
                "error_history": state.get("error_history", []),
                "schema": state["schema"],
                "last_attempt_time": last_attempt_time.isoformat()
            }

    cursor = None
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
            "current_step": "Executing Query",
            "retry_count": state.get("retry_count", 0),
            "error_history": state.get("error_history", []),
            "last_attempt_time": datetime.now().isoformat()
        }
    except Exception as e:
        if cursor:
            cursor.close()
            
        current_retry = state.get("retry_count", 0)
        error_history = state.get("error_history", [])
        error_history.append(str(e))
        
        return {
            "messages": [AIMessage(content=f"Error executing query: {e}")],
            "current_step": "Error in Query Execution",
            "query": state["query"],
            "sort_order": state["sort_order"],
            "result_limit": state["result_limit"],
            "time_filter": state["time_filter"],
            "retry_count": current_retry + 1,
            "error_history": error_history,
            "schema": state["schema"],
            "last_attempt_time": datetime.now().isoformat()
        }