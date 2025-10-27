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

    # Debug: Save query execution input
    from utils.debug_utils import save_debug_file
    save_debug_file(
        "execute_query_input.json",
        {
            "query": query,
            "retry_count": state.get("retry_count", 0),
            "refined_count": state.get("refined_count", 0),
        },
        step_name="execute_query",
        include_timestamp=True
    )

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

        # Debug: Save query execution result
        save_debug_file(
            "execute_query_result.json",
            {
                "query": query,
                "row_count": len(data),
                "columns": columns,
                "sample_data": data[:5] if len(data) > 5 else data,  # Save first 5 rows as sample
            },
            step_name="execute_query",
            include_timestamp=True
        )

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

        # Debug: Track successful SQL query
        from utils.debug_utils import append_to_debug_array
        append_to_debug_array(
            "generated_sql_queries.json",
            {
                "step": "successful_execution",
                "sql": query,
                "row_count": len(data),
                "column_count": len(columns),
                "status": "success"
            },
            step_name="execute_query",
            array_key="queries"
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

        # Column removal disabled - it only removes from SELECT but errors often in JOIN/WHERE
        # Let error correction handle column issues by fixing the plan instead
        if is_column_error:
            error_message = str(e)
            invalid_column = parse_invalid_column_name(error_message)

            if invalid_column:
                logger.warning(
                    f"Invalid column '{invalid_column}' detected. "
                    f"Skipping inline removal - letting error correction fix the plan.",
                    extra={"query": query, "invalid_column": invalid_column}
                )

        # Note: Column removal logic disabled because it's incomplete
        # - Only removes from SELECT clause, not JOIN/WHERE/GROUP BY
        # - Often causes infinite loops when column appears in multiple clauses
        # - Error correction can fix the underlying plan issue instead

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
