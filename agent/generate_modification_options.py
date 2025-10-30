"""Generate modification options for plan patching UI."""

import re
from typing import Any, Dict, List, Optional
from utils.logger import get_logger

logger = get_logger()


def format_column_name_for_display(column_name: str) -> str:
    """
    Convert database column names to friendly display names.

    Handles common naming patterns:
    - PascalCase: UpdatedBy → Updated By
    - snake_case: SW_Edition → SW Edition
    - Mixed: CompanyID → Company ID
    - Acronyms: ID, FK, PK remain uppercase

    Args:
        column_name: Raw database column name

    Returns:
        Friendly display name
    """
    if not column_name:
        return column_name

    # Handle snake_case: replace underscores with spaces
    if '_' in column_name:
        # Split by underscore and join with spaces
        parts = column_name.split('_')
        # Keep acronyms uppercase, title case others
        formatted_parts = []
        for part in parts:
            if not part:  # Skip empty parts
                continue
            # Keep all-caps parts as-is (likely acronyms like FK, PK, SW)
            if part.isupper():
                formatted_parts.append(part)
            else:
                # Title case everything else, including 'id' -> 'Id'
                formatted_parts.append(part.title())
        return ' '.join(formatted_parts)

    # Handle PascalCase: insert spaces before capital letters
    # Special handling for common suffixes like ID, FK, PK
    result = column_name

    # Insert space before capital letters (except at start)
    result = re.sub(r'(?<!^)(?=[A-Z][a-z])', ' ', result)

    # Handle acronyms at end (e.g., CompanyID → Company ID)
    result = re.sub(r'([a-z])([A-Z]+)$', r'\1 \2', result)

    # Handle consecutive capitals followed by lowercase (e.g., XMLParser → XML Parser)
    result = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', result)

    return result


def get_selected_columns_map(plan: Dict[str, Any]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Build a map of selected columns from the plan.

    Args:
        plan: Query plan

    Returns:
        Dict mapping table -> column -> {role, reason, value_type}
    """
    column_map = {}

    for selection in plan.get("selections", []):
        table = selection["table"]
        column_map[table] = {}

        for col in selection.get("columns", []):
            column_name = col["column"]
            column_map[table][column_name] = {
                "role": col["role"],
                "reason": col.get("reason"),
                "value_type": col.get("value_type", "unknown")
            }

    return column_map


def get_table_columns_from_schema(
    table: str,
    schema: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Get all columns for a table from the schema.

    Args:
        table: Table name
        schema: Filtered database schema

    Returns:
        List of column dicts with column_name, data_type, is_nullable, is_primary_key
    """
    for table_schema in schema:
        if table_schema["table_name"].lower() == table.lower():
            return table_schema.get("columns", [])
    return []


def generate_modification_options(
    executed_plan: Dict[str, Any],
    filtered_schema: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Generate UI modification options from executed plan and schema.

    This is a deterministic, schema-based generator (no LLM calls).

    Args:
        executed_plan: The plan that generated current displayed results
        filtered_schema: Available schema information (top-k relevant tables)

    Returns:
        Dict with structure:
        {
            "tables": {
                "tb_Table1": {
                    "alias": "t1",  # Optional alias
                    "columns": [
                        {
                            "name": "Col1",
                            "type": "bigint",
                            "selected": True,
                            "role": "projection",  # or "filter" or None
                            "is_primary_key": True,
                            "is_nullable": False
                        }
                    ]
                }
            },
            "current_order_by": [
                {"table": "tb_Table1", "column": "Col1", "direction": "ASC"}
            ],
            "current_limit": 100,
            "sortable_columns": [
                {"table": "tb_Table1", "column": "Col1", "type": "bigint"},
                {"table": "tb_Table1", "column": "Col2", "type": "nvarchar"}
            ]
        }
    """
    logger.info("Generating modification options from executed plan and schema")

    # Get selected columns map from plan
    selected_map = get_selected_columns_map(executed_plan)

    # Build tables dict with all available columns
    tables_dict = {}
    sortable_columns = []

    for selection in executed_plan.get("selections", []):
        table = selection["table"]
        alias = selection.get("alias")

        # Get all columns for this table from schema
        schema_columns = get_table_columns_from_schema(table, filtered_schema)

        # Build column metadata list
        columns_list = []
        for schema_col in schema_columns:
            col_name = schema_col["column_name"]
            col_type = schema_col["data_type"]
            is_pk = schema_col.get("is_primary_key", False)
            is_nullable = schema_col.get("is_nullable", True)

            # Check if column is selected in plan
            selected = col_name in selected_map.get(table, {})
            role = selected_map.get(table, {}).get(col_name, {}).get("role") if selected else None

            # Format display name for UI
            friendly_name = format_column_name_for_display(col_name)

            column_info = {
                "name": col_name,
                "display_name": friendly_name,
                "type": col_type,
                "selected": selected,
                "role": role,
                "is_primary_key": is_pk,
                "is_nullable": is_nullable
            }
            columns_list.append(column_info)

            # Add to sortable columns (all columns from selected tables)
            sortable_columns.append({
                "table": table,
                "column": col_name,
                "type": col_type,
                "display_name": f"{table}.{friendly_name}"
            })

        tables_dict[table] = {
            "alias": alias,
            "columns": columns_list
        }

    # Extract current ORDER BY
    current_order_by = executed_plan.get("order_by", [])

    # Extract current LIMIT
    current_limit = executed_plan.get("limit")

    # Build result
    result = {
        "tables": tables_dict,
        "current_order_by": current_order_by,
        "current_limit": current_limit,
        "sortable_columns": sortable_columns
    }

    logger.info(
        f"Generated options for {len(tables_dict)} tables, "
        f"{len(sortable_columns)} sortable columns"
    )

    return result


def generate_modification_options_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph workflow node that generates modification options.

    Args:
        state: Workflow state

    Returns:
        Updated state with modification_options
    """
    logger.info("=== Generate Modification Options Node ===")

    executed_plan = state.get("executed_plan")
    filtered_schema = state.get("filtered_schema")

    if not executed_plan:
        logger.warning("No executed plan found - cannot generate modification options")
        return state

    if not filtered_schema:
        logger.warning("No filtered schema found - cannot generate modification options")
        return state

    try:
        options = generate_modification_options(executed_plan, filtered_schema)
        logger.info("Modification options generated successfully")

        return {
            **state,
            "modification_options": options
        }

    except Exception as e:
        logger.error(f"Error generating modification options: {str(e)}", exc_info=True)
        return state


def format_modification_options_for_display(
    options: Dict[str, Any]
) -> str:
    """
    Format modification options as human-readable text for debugging.

    Args:
        options: Modification options dict

    Returns:
        Formatted string
    """
    lines = ["=== Modification Options ===\n"]

    # Tables and columns
    lines.append("Available Columns:")
    for table, table_info in options.get("tables", {}).items():
        alias = table_info.get("alias")
        table_display = f"{table} ({alias})" if alias else table
        lines.append(f"\n  {table_display}:")

        for col in table_info.get("columns", []):
            status = "✓" if col["selected"] else " "
            role = f" [{col['role']}]" if col["role"] else ""
            pk = " (PK)" if col.get("is_primary_key") else ""
            lines.append(
                f"    [{status}] {col['name']} ({col['type']}){role}{pk}"
            )

    # Current ORDER BY
    order_by = options.get("current_order_by", [])
    if order_by:
        lines.append("\n\nCurrent ORDER BY:")
        for order_spec in order_by:
            lines.append(
                f"  {order_spec['table']}.{order_spec['column']} {order_spec.get('direction', 'ASC')}"
            )
    else:
        lines.append("\n\nCurrent ORDER BY: None")

    # Current LIMIT
    limit = options.get("current_limit")
    if limit:
        lines.append(f"\nCurrent LIMIT: {limit}")
    else:
        lines.append("\nCurrent LIMIT: None")

    # Sortable columns count
    sortable = options.get("sortable_columns", [])
    lines.append(f"\n\nTotal sortable columns: {len(sortable)}")

    return "\n".join(lines)
