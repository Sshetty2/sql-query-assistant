"""Deterministically fix invalid column names in planner output."""

from typing import Optional
from utils.logger import get_logger

logger = get_logger()


def find_closest_column(target_column: str, table_name: str, schema: list[dict]) -> Optional[str]:
    """
    Find the closest matching column name in a table.

    Uses multiple strategies:
    1. Exact match (case-insensitive)
    2. Suffix match (e.g., CompanyName → Name)
    3. Contains match (e.g., CompanyName contains Name)
    4. Levenshtein distance for typos

    Args:
        target_column: The invalid column name
        table_name: The table to search in
        schema: Database schema

    Returns:
        Closest matching column name, or None
    """
    # Find the table in schema
    table_cols = None
    for table_schema in schema:
        if table_schema.get("table_name") == table_name:
            table_cols = [col.get("column_name") for col in table_schema.get("columns", [])]
            break

    if not table_cols:
        return None

    target_lower = target_column.lower()

    # Strategy 1: Exact match (case-insensitive)
    for col in table_cols:
        if col.lower() == target_lower:
            return col

    # Strategy 2: Suffix match (CompanyName → Name)
    # Common pattern: LLM adds table prefix to column name
    if target_lower.startswith(table_name.lower().replace("tb_", "")):
        # Try removing the prefix
        suffix = target_column[len(table_name.replace("tb_", "")):]
        for col in table_cols:
            if col.lower() == suffix.lower():
                logger.info(f"Found suffix match: {target_column} → {col}")
                return col

    # Strategy 3: Target ends with actual column name
    # CompanyName → Name (target ends with "Name")
    for col in table_cols:
        if target_lower.endswith(col.lower()):
            logger.info(f"Found ending match: {target_column} → {col}")
            return col

    # Strategy 4: Target contains actual column name
    for col in table_cols:
        if col.lower() in target_lower:
            logger.info(f"Found contains match: {target_column} → {col}")
            return col

    # Strategy 5: Levenshtein distance for typos
    try:
        from difflib import get_close_matches
        matches = get_close_matches(target_column, table_cols, n=1, cutoff=0.6)
        if matches:
            logger.info(f"Found fuzzy match: {target_column} → {matches[0]}")
            return matches[0]
    except Exception as e:
        logger.warning(f"Fuzzy matching failed: {e}")

    return None


def fix_invalid_column(table: str, column: str, schema: list[dict]) -> tuple[str, bool]:
    """
    Fix a single invalid column reference.

    Returns:
        (corrected_column_name, was_fixed)
    """
    # First check if column exists (might be valid)
    for table_schema in schema:
        if table_schema.get("table_name") == table:
            columns = [col.get("column_name") for col in table_schema.get("columns", [])]
            if column in columns:
                return column, False  # Valid, no fix needed

    # Column doesn't exist, find closest match
    closest = find_closest_column(column, table, schema)

    if closest:
        logger.info(f"Fixed invalid column: {table}.{column} → {table}.{closest}")
        return closest, True
    else:
        logger.warning(f"Could not find replacement for invalid column: {table}.{column}")
        return column, False  # Keep original (will fail later but at least we tried)


def fix_plan_columns(plan_dict: dict, schema: list[dict]) -> tuple[dict, list[str]]:
    """
    Deterministically fix invalid column names in plan.

    Scans all column references and replaces invalid ones with closest matches.

    Args:
        plan_dict: Planner output dictionary
        schema: Database schema

    Returns:
        (fixed_plan_dict, list_of_fixes_applied)
    """
    fixes = []

    # Fix columns in selections
    for selection in plan_dict.get("selections", []):
        table = selection.get("table")

        for col_info in selection.get("columns", []):
            original_col = col_info.get("column")
            col_table = col_info.get("table", table)  # Use selection table if not specified

            fixed_col, was_fixed = fix_invalid_column(col_table, original_col, schema)

            if was_fixed:
                col_info["column"] = fixed_col
                fixes.append(f"Selection column: {col_table}.{original_col} → {col_table}.{fixed_col}")

        # Fix columns in filters
        for filter_pred in selection.get("filters", []):
            original_col = filter_pred.get("column")
            filter_table = filter_pred.get("table", table)

            fixed_col, was_fixed = fix_invalid_column(filter_table, original_col, schema)

            if was_fixed:
                filter_pred["column"] = fixed_col
                fixes.append(f"Filter column: {filter_table}.{original_col} → {filter_table}.{fixed_col}")

    # Fix columns in join_edges
    for edge in plan_dict.get("join_edges", []):
        from_table = edge.get("from_table")
        from_column = edge.get("from_column")

        fixed_col, was_fixed = fix_invalid_column(from_table, from_column, schema)
        if was_fixed:
            edge["from_column"] = fixed_col
            fixes.append(f"Join from: {from_table}.{from_column} → {from_table}.{fixed_col}")

        to_table = edge.get("to_table")
        to_column = edge.get("to_column")

        fixed_col, was_fixed = fix_invalid_column(to_table, to_column, schema)
        if was_fixed:
            edge["to_column"] = fixed_col
            fixes.append(f"Join to: {to_table}.{to_column} → {to_table}.{fixed_col}")

    # Fix columns in global_filters
    for filter_pred in plan_dict.get("global_filters", []):
        filter_table = filter_pred.get("table")
        original_col = filter_pred.get("column")

        fixed_col, was_fixed = fix_invalid_column(filter_table, original_col, schema)

        if was_fixed:
            filter_pred["column"] = fixed_col
            fixes.append(f"Global filter: {filter_table}.{original_col} → {filter_table}.{fixed_col}")

    # Fix columns in GROUP BY
    group_by = plan_dict.get("group_by")
    if group_by:
        for col_info in group_by.get("group_by_columns", []):
            table = col_info.get("table")
            original_col = col_info.get("column")

            fixed_col, was_fixed = fix_invalid_column(table, original_col, schema)

            if was_fixed:
                col_info["column"] = fixed_col
                fixes.append(f"GROUP BY: {table}.{original_col} → {table}.{fixed_col}")

        # Fix columns in aggregates
        for agg in group_by.get("aggregates", []):
            if agg.get("column"):  # COUNT(*) has None
                table = agg.get("table")
                original_col = agg.get("column")

                fixed_col, was_fixed = fix_invalid_column(table, original_col, schema)

                if was_fixed:
                    agg["column"] = fixed_col
                    fixes.append(f"Aggregate: {table}.{original_col} → {table}.{fixed_col}")

        # Fix columns in HAVING filters
        for having_filter in group_by.get("having_filters", []):
            table = having_filter.get("table")
            original_col = having_filter.get("column")

            fixed_col, was_fixed = fix_invalid_column(table, original_col, schema)

            if was_fixed:
                having_filter["column"] = fixed_col
                fixes.append(f"HAVING: {table}.{original_col} → {table}.{fixed_col}")

    # Fix columns in ORDER BY
    for order_info in plan_dict.get("order_by", []):
        table = order_info.get("table")
        original_col = order_info.get("column")

        fixed_col, was_fixed = fix_invalid_column(table, original_col, schema)

        if was_fixed:
            order_info["column"] = fixed_col
            fixes.append(f"ORDER BY: {table}.{original_col} → {table}.{fixed_col}")

    if fixes:
        logger.info(f"Applied {len(fixes)} column name fixes", extra={"fixes": fixes})

    return plan_dict, fixes
