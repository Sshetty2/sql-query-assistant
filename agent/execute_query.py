"""Execute the SQL query and return the result."""

import json
from datetime import datetime, date
from decimal import Decimal
from agent.state import State
from langchain_core.messages import AIMessage
from utils.logger import get_logger, log_execution_time

logger = get_logger()


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
    query = state["query"]
    logger.info("Starting query execution", extra={"query": query[:200]})  # Log first 200 chars

    cursor = None
    try:
        with log_execution_time(logger, "database_query_execution"):
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

        logger.info(
            "Query execution completed",
            extra={
                "row_count": len(data),
                "column_count": len(columns),
                "result_size_bytes": len(json_result)
            }
        )

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

        logger.error(
            "Query execution failed",
            exc_info=True,
            extra={"query": query[:200], "error": str(e)}
        )

        return {
            **state,
            "messages": [AIMessage(content=f"Error executing query: {e}")],
            "last_step": "execute_query",
            "result": None,
            "error_history": error_history,
            "last_attempt_time": datetime.now().isoformat(),
        }
