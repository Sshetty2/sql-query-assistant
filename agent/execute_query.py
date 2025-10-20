"""Execute the SQL query and return the result."""

import json
from datetime import datetime, date
from decimal import Decimal
from agent.state import State
from langchain_core.messages import AIMessage


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="ignore")
    raise TypeError(f"Type {type(obj)} not serializable")


def execute_query(state: State, db_connection):
    """Execute the SQL query and return the result."""
    cursor = None
    try:
        query = state["query"]
        cursor = db_connection.cursor()
        cursor.execute(query)
        results = cursor.fetchall()

        # Post-process results into JSON format
        columns = [column[0] for column in cursor.description]
        data = [dict(zip(columns, row)) for row in results]
        json_result = json.dumps(data, default=json_serial)

        cursor.close()

        # Append current query to queries list for conversation history
        queries = state.get("queries", [])
        if query not in queries:  # Avoid duplicates
            queries = queries + [query]

        return {
            **state,
            "messages": [AIMessage(content="Query Successfully Executed")],
            "result": json_result,
            "queries": queries,
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
