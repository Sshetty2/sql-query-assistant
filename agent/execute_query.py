"""Execute the SQL query and return the result."""

import json
import re
import pyodbc
import sqlglot
from sqlglot import exp

from datetime import datetime, date
from decimal import Decimal
from agent.state import State
from langchain_core.messages import AIMessage
from utils.logger import get_logger, log_execution_time

logger = get_logger()

# Maximum number of times we'll automatically remove invalid columns
MAX_COLUMN_REMOVALS = 3


def parse_invalid_column_name(error_message: str) -> str | None:
    """
    Parse the invalid column name from a SQL Server error message.

    Example error message:
    "[42S22] [Microsoft][ODBC Driver 17 for SQL Server][SQL Server]Invalid column name 'OS'. (207) (SQLExecDirectW)"

    Returns:
        The invalid column name, or None if not found
    """
    # Pattern to match "Invalid column name 'COLUMN_NAME'"
    pattern = r"Invalid column name '([^']+)'"
    match = re.search(pattern, error_message, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def remove_column_from_query(query: str, column_name: str) -> str | None:
    """
    Remove a specific column from the SELECT clause of a SQL query.

    Args:
        query: The SQL query string
        column_name: The column name to remove

    Returns:
        The modified query string, or None if the column couldn't be removed
    """
    if not sqlglot:
        logger.warning("sqlglot not available, cannot remove column from query")
        return None

    try:
        # Parse the query
        parsed = sqlglot.parse_one(query, read="tsql")

        # Find all SELECT expressions
        for select in parsed.find_all(exp.Select):
            # Get the current expressions in the SELECT clause
            expressions = select.expressions

            # Filter out the invalid column
            # Column might be referenced as just the name or with table alias
            new_expressions = []
            for expr in expressions:
                # Get the column name from the expression
                # Handle cases like: column_name, table.column_name, column_name AS alias
                column_text = expr.sql(dialect="tsql")

                # Check if this expression references the invalid column
                # Use word boundaries to match the exact column name
                if not re.search(
                    rf"\b{re.escape(column_name)}\b", column_text, re.IGNORECASE
                ):
                    new_expressions.append(expr)
                else:
                    logger.debug(f"Removing expression: {column_text}")

            # If we removed all columns, we can't proceed
            if not new_expressions:
                logger.warning("Cannot remove column - it's the only column in SELECT")
                return None

            # Update the SELECT with the filtered expressions
            select.set("expressions", new_expressions)

        # Generate the modified query
        modified_query = parsed.sql(dialect="tsql")
        return modified_query

    except Exception as e:
        logger.error(f"Error removing column from query: {str(e)}", exc_info=True)
        return None


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

    # Defensive check: ensure query is not None or empty
    if query is None or (isinstance(query, str) and not query.strip()):
        error_msg = (
            "Cannot execute query: query is None or empty. "
            "This indicates a bug in the workflow routing or query generation."
        )
        logger.error(error_msg, extra={"state_keys": list(state.keys())})
        return {
            **state,
            "result": None,
            "messages": state["messages"] + [AIMessage(content=f"Error: {error_msg}")],
        }

    logger.info(
        "Starting query execution", extra={"query": query}
    )  # Log first 200 chars

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
                "result_size_bytes": len(json_result),
            },
        )

        return {
            **state,
            "messages": [AIMessage(content="Query Successfully Executed")],
            "query": query,  # Explicitly include the (possibly modified) query
            "result": json_result,
            "queries": queries,
            "last_step": "execute_query",
            "last_attempt_time": datetime.now().isoformat(),
        }
    except Exception as e:
        if cursor:
            cursor.close()

        # Check if this is an "Invalid column name" error that we can fix inline
        is_column_error = False
        error_code = None

        if pyodbc and isinstance(e, pyodbc.ProgrammingError):
            # Extract error code from the exception
            # pyodbc.ProgrammingError: ('42S22', "[42S22] ... Invalid column name 'X' ...")
            if len(e.args) >= 1:
                error_code = e.args[0]

            if error_code == "42S22":  # Invalid column name
                is_column_error = True

        # Handle inline column removal if applicable
        if is_column_error:
            column_removal_count = state.get("column_removal_count", 0)

            # Parse the invalid column name from the error message
            error_message = str(e)
            invalid_column = parse_invalid_column_name(error_message)

            if invalid_column and column_removal_count < MAX_COLUMN_REMOVALS:
                # Try to remove the invalid column
                modified_query = remove_column_from_query(query, invalid_column)

                if modified_query:
                    # Successfully removed the column, log warning and retry
                    removal_msg = (
                        f"Removed invalid column '{invalid_column}' from query "
                        f"(attempt {column_removal_count + 1}/{MAX_COLUMN_REMOVALS})"
                    )
                    logger.warning(
                        removal_msg,
                        extra={
                            "original_query": query,
                            "modified_query": modified_query,
                            "invalid_column": invalid_column,
                            "removal_count": column_removal_count + 1,
                        },
                    )

                    # Update state with the modified query and incremented counter
                    removed_columns = state.get("removed_columns", [])
                    updated_state = {
                        **state,
                        "query": modified_query,
                        "column_removal_count": column_removal_count + 1,
                        "removed_columns": removed_columns + [invalid_column],
                    }

                    # Recursively call execute_query with the modified state
                    return execute_query(updated_state, db_connection)

            # If we couldn't remove the column or hit the limit, treat as regular error
            if column_removal_count >= MAX_COLUMN_REMOVALS:
                logger.error(
                    f"Hit maximum column removal limit ({MAX_COLUMN_REMOVALS}) for invalid column errors",
                    extra={
                        "query": query,
                        "error": str(e),
                        "removed_columns": state.get("removed_columns", []),
                    },
                )

        # Regular error handling for all other errors or when inline fix failed
        error_history = state["error_history"]
        error_history.append(str(e))

        logger.error(
            "Query execution failed",
            exc_info=True,
            extra={"query": query, "error": str(e)},
        )

        return {
            **state,
            "messages": [AIMessage(content=f"Error executing query: {e}")],
            "query": query,
            "last_step": "execute_query",
            "result": None,
            "error_history": error_history,
            "last_attempt_time": datetime.now().isoformat(),
        }
