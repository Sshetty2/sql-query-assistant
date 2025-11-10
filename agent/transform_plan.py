"""Plan transformer for applying deterministic patches to query plans."""

import copy
from typing import Any, Dict, List, Optional
from database.connection import get_pyodbc_connection
from utils.logger import get_logger
from utils.stream_utils import emit_node_status, log_and_stream

logger = get_logger()


def validate_column_exists(
    table: str, column: str, schema: List[Dict[str, Any]]
) -> bool:
    """
    Validate that a column exists in the schema.

    Args:
        table: Table name
        column: Column name
        schema: Database schema

    Returns:
        True if column exists, False otherwise
    """
    for table_schema in schema:
        if table_schema["table_name"].lower() == table.lower():
            for col in table_schema["columns"]:
                if col["column_name"].lower() == column.lower():
                    return True
    return False


def get_column_type(
    table: str, column: str, schema: List[Dict[str, Any]]
) -> Optional[str]:
    """
    Get the data type of a column from schema.

    Args:
        table: Table name
        column: Column name
        schema: Database schema

    Returns:
        Data type string or None if not found
    """
    for table_schema in schema:
        if table_schema["table_name"].lower() == table.lower():
            for col in table_schema["columns"]:
                if col["column_name"].lower() == column.lower():
                    return col["data_type"]
    return None


def is_column_in_filters(table: str, column: str, plan: Dict[str, Any]) -> bool:
    """
    Check if a column is used in any filter predicates.

    Args:
        table: Table name
        column: Column name
        plan: Query plan

    Returns:
        True if column is used in filters, False otherwise
    """
    # Check table-level filters
    for selection in plan.get("selections", []):
        if selection["table"].lower() == table.lower():
            for filter_pred in selection.get("filters", []):
                if filter_pred["column"].lower() == column.lower():
                    return True

    # Check global filters
    for filter_pred in plan.get("global_filters", []):
        if (
            filter_pred["table"].lower() == table.lower()
            and filter_pred["column"].lower() == column.lower()
        ):
            return True

    # Check GROUP BY having filters
    group_by = plan.get("group_by")
    if group_by:
        for filter_pred in group_by.get("having_filters", []):
            if (
                filter_pred["table"].lower() == table.lower()
                and filter_pred["column"].lower() == column.lower()
            ):
                return True

    return False


def map_type_to_value_type(sql_type: str) -> str:
    """
    Map SQL data type to PlannerOutput value_type.

    Args:
        sql_type: SQL data type (e.g., 'bigint', 'nvarchar', 'datetime')

    Returns:
        Value type: 'string', 'number', 'integer', 'boolean', 'date', 'datetime', 'unknown'
    """
    sql_type_lower = sql_type.lower()

    if "int" in sql_type_lower or "serial" in sql_type_lower:
        return "integer"
    elif (
        "float" in sql_type_lower
        or "double" in sql_type_lower
        or "decimal" in sql_type_lower
        or "numeric" in sql_type_lower
    ):  # noqa: E501
        return "number"
    elif "bool" in sql_type_lower or "bit" in sql_type_lower:
        return "boolean"
    elif "datetime" in sql_type_lower or "timestamp" in sql_type_lower:
        return "datetime"
    elif "date" in sql_type_lower:
        return "date"
    elif (
        "char" in sql_type_lower
        or "text" in sql_type_lower
        or "varchar" in sql_type_lower
        or "nvarchar" in sql_type_lower
    ):  # noqa: E501
        return "string"
    else:
        return "unknown"


def apply_add_column(
    plan: Dict[str, Any], table: str, column: str, schema: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Add a column to the plan's projection list.

    Args:
        plan: Query plan
        table: Table name
        column: Column name to add
        schema: Database schema for validation

    Returns:
        Modified plan

    Raises:
        ValueError: If column doesn't exist or table not in plan
    """
    # Validate column exists
    if not validate_column_exists(table, column, schema):
        raise ValueError(f"Column {column} does not exist in table {table}")

    # Find the table selection
    table_found = False
    for selection in plan.get("selections", []):
        if selection["table"].lower() == table.lower():
            table_found = True

            # Check if column already exists
            for col in selection.get("columns", []):
                if col["column"].lower() == column.lower():
                    # If column exists but is filter-only, change to projection
                    if col["role"] == "filter":
                        logger.info(
                            f"Changing column {column} role from 'filter' to 'projection'"
                        )
                        col["role"] = "projection"
                        return plan
                    else:
                        logger.warning(f"Column {column} already in projection list")
                        return plan

            # Add new column to projection
            col_type = get_column_type(table, column, schema)
            value_type = map_type_to_value_type(col_type) if col_type else "unknown"

            new_column = {
                "table": table,
                "column": column,
                "role": "projection",
                "reason": "Added via plan patching",
                "value_type": value_type,
            }
            selection.setdefault("columns", []).append(new_column)
            logger.info(f"Added column {column} to table {table} projection")
            break

    if not table_found:
        raise ValueError(f"Table {table} not found in plan selections")

    return plan


def apply_remove_column(
    plan: Dict[str, Any], table: str, column: str
) -> Dict[str, Any]:
    """
    Remove a column from the plan's projection list.

    If the column is used in filters, change its role to 'filter' instead of removing it.

    Args:
        plan: Query plan
        table: Table name
        column: Column name to remove

    Returns:
        Modified plan

    Raises:
        ValueError: If table not found or column not in projection
    """
    # Find the table selection
    table_found = False
    column_found = False

    for selection in plan.get("selections", []):
        if selection["table"].lower() == table.lower():
            table_found = True

            # Check if column is used in filters
            column_in_filters = is_column_in_filters(table, column, plan)

            # Find and remove/modify the column
            columns = selection.get("columns", [])
            for i, col in enumerate(columns):
                if col["column"].lower() == column.lower():
                    column_found = True

                    if column_in_filters:
                        # Column used in filters - change role instead of removing
                        logger.info(
                            f"Column {column} used in filters, changing role to 'filter'"
                        )
                        col["role"] = "filter"
                    else:
                        # Column not used in filters - safe to remove
                        logger.info(f"Removing column {column} from table {table}")
                        columns.pop(i)

                    break
            break

    if not table_found:
        raise ValueError(f"Table {table} not found in plan selections")

    if not column_found:
        raise ValueError(f"Column {column} not found in table {table} columns")

    return plan


def apply_modify_order_by(
    plan: Dict[str, Any], order_by: List[Dict[str, Any]], schema: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Modify the ORDER BY clause of the plan.

    Args:
        plan: Query plan
        order_by: New ORDER BY specification, list of dicts with:
            - table: str
            - column: str
            - direction: "ASC" | "DESC"
        schema: Database schema for validation

    Returns:
        Modified plan

    Raises:
        ValueError: If any column doesn't exist
    """
    # Validate all columns exist
    for order_spec in order_by:
        table = order_spec["table"]
        column = order_spec["column"]
        if not validate_column_exists(table, column, schema):
            raise ValueError(f"Column {column} does not exist in table {table}")

        # Validate direction
        direction = order_spec.get("direction", "ASC")
        if direction not in ["ASC", "DESC"]:
            raise ValueError(
                f"Invalid sort direction: {direction}. Must be 'ASC' or 'DESC'"
            )

    # Replace ORDER BY
    plan["order_by"] = order_by
    logger.info(f"Updated ORDER BY to {len(order_by)} column(s)")

    return plan


def apply_modify_limit(plan: Dict[str, Any], limit: int) -> Dict[str, Any]:
    """
    Modify the LIMIT clause of the plan.

    Args:
        plan: Query plan
        limit: New row limit (must be positive integer)

    Returns:
        Modified plan

    Raises:
        ValueError: If limit is invalid
    """
    if not isinstance(limit, int) or limit <= 0:
        raise ValueError(f"Invalid limit: {limit}. Must be a positive integer")

    plan["limit"] = limit
    logger.info(f"Updated LIMIT to {limit}")

    return plan


def apply_patch_operation(
    plan: Dict[str, Any], operation: Dict[str, Any], schema: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Apply a single patch operation to a query plan.

    Args:
        plan: Query plan to modify
        operation: Patch operation dict with structure:
            {
                "operation": "add_column" | "remove_column" | "modify_order_by" | "modify_limit",
                "table": str (for add_column, remove_column),
                "column": str (for add_column, remove_column),
                "order_by": list (for modify_order_by),
                "limit": int (for modify_limit)
            }
        schema: Database schema for validation

    Returns:
        Modified plan dict

    Raises:
        ValueError: If operation is invalid or fails validation
    """
    # Deep copy to avoid modifying original
    modified_plan = copy.deepcopy(plan)

    op_type = operation.get("operation")

    if op_type == "add_column":
        table = operation.get("table")
        column = operation.get("column")
        if not table or not column:
            raise ValueError(
                "add_column operation requires 'table' and 'column' fields"
            )
        modified_plan = apply_add_column(modified_plan, table, column, schema)

    elif op_type == "remove_column":
        table = operation.get("table")
        column = operation.get("column")
        if not table or not column:
            raise ValueError(
                "remove_column operation requires 'table' and 'column' fields"
            )
        modified_plan = apply_remove_column(modified_plan, table, column)

    elif op_type == "modify_order_by":
        order_by = operation.get("order_by")
        if order_by is None:
            raise ValueError("modify_order_by operation requires 'order_by' field")
        modified_plan = apply_modify_order_by(modified_plan, order_by, schema)

    elif op_type == "modify_limit":
        limit = operation.get("limit")
        if limit is None:
            raise ValueError("modify_limit operation requires 'limit' field")
        modified_plan = apply_modify_limit(modified_plan, limit)

    else:
        raise ValueError(
            f"Unknown operation type: {op_type}. "
            f"Supported: add_column, remove_column, modify_order_by, modify_limit"
        )

    return modified_plan


def transform_plan_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph workflow node that applies plan patches.

    Args:
        state: Workflow state

    Returns:
        Updated state with modified planner_output
    """
    emit_node_status("transform_plan", "running", "Applying plan modifications")

    log_and_stream(logger, "transform_plan", "Transform Plan Node started")

    # Ensure database connection exists (needed for patch operations that skip initialize_connection)
    if not state.get("db_connection"):
        log_and_stream(logger, "transform_plan", "Creating database connection for patch operation")
        try:
            db_connection = get_pyodbc_connection()
            state = {**state, "db_connection": db_connection}
        except Exception as e:
            log_and_stream(
                logger,
                "transform_plan",
                f"Failed to create database connection: {str(e)}",
                level="error"
            )
            return {
                **state,
                "patch_requested": False,
                "messages": state.get("messages", [])
                + [{"role": "assistant", "content": f"Error: Could not create database connection: {str(e)}"}],
            }

    # Get required state
    current_patch = state.get("current_patch_operation")
    executed_plan = state.get("executed_plan")
    filtered_schema = state.get("filtered_schema")

    if not current_patch:
        log_and_stream(logger, "transform_plan", "No patch operation provided", level="error")
        return {
            **state,
            "patch_requested": False,
            "messages": state.get("messages", [])
            + [{"role": "assistant", "content": "Error: No patch operation specified"}],
        }

    if not executed_plan:
        log_and_stream(logger, "transform_plan", "No executed plan found - cannot apply patch", level="error")
        return {
            **state,
            "patch_requested": False,
            "messages": state.get("messages", [])
            + [
                {
                    "role": "assistant",
                    "content": "Error: No executed plan found to patch",
                }
            ],
        }

    if not filtered_schema:
        log_and_stream(logger, "transform_plan", "No schema available for validation", level="error")
        return {
            **state,
            "patch_requested": False,
            "messages": state.get("messages", [])
            + [
                {
                    "role": "assistant",
                    "content": "Error: No schema available for validation",
                }
            ],
        }

    try:
        # Apply the patch operation
        log_and_stream(logger, "transform_plan", f"Applying patch operation: {current_patch.get('operation')}")
        modified_plan = apply_patch_operation(
            executed_plan, current_patch, filtered_schema
        )

        # Update state with modified plan
        patch_history = state.get("patch_history", [])
        patch_history.append(current_patch)

        log_and_stream(logger, "transform_plan", "Plan patched successfully, proceeding to SQL generation")

        emit_node_status("transform_plan", "completed")

        return {
            **state,
            "planner_output": modified_plan,  # This will be used for SQL generation
            "patch_history": patch_history,
            "patch_requested": False,  # Reset flag
            "current_patch_operation": None,  # Clear current patch
        }

    except Exception as e:
        log_and_stream(logger, "transform_plan", f"Error applying patch: {str(e)}", level="error", exc_info=True)
        emit_node_status("transform_plan", "error")
        return {
            **state,
            "patch_requested": False,
            "current_patch_operation": None,
            "messages": state.get("messages", [])
            + [{"role": "assistant", "content": f"Error applying patch: {str(e)}"}],
        }
