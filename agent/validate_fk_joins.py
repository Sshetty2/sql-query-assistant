"""Validate and auto-fix foreign key join references in strategies."""

import re
from typing import Optional
from utils.logger import get_logger

logger = get_logger()


def extract_join_references(strategy: str) -> list[tuple[str, str, str, str]]:
    """
    Extract join references from strategy text.

    Returns list of tuples: (from_table, from_column, to_table, to_column)

    Example patterns:
    - "Join tb_A with tb_B on tb_A.ID = tb_B.ForeignID"
    - "tb_A.ColumnX = tb_B.ColumnY"
    """
    joins = []

    # Pattern: table.column = table.column
    pattern = r'(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)'

    for match in re.finditer(pattern, strategy, re.IGNORECASE):
        from_table, from_column, to_table, to_column = match.groups()
        joins.append((from_table, from_column, to_table, to_column))

    return joins


def get_table_columns(schema: list[dict], table_name: str) -> set[str]:
    """Get all column names for a table from schema."""
    for table in schema:
        if table.get("table_name") == table_name:
            return {col["column_name"] for col in table.get("columns", [])}
    return set()


def get_foreign_key_mapping(schema: list[dict], table_name: str, fk_column: str) -> Optional[tuple[str, str]]:
    """
    Get the target table and column for a foreign key.

    Returns: (target_table, target_column) or None

    Example:
    - Input: table_name="tb_SaasComputers", fk_column="ScanID"
    - Output: ("tb_SaasScan", "ID")
    """
    for table in schema:
        if table.get("table_name") == table_name:
            for fk in table.get("foreign_keys", []):
                if fk.get("column_name") == fk_column:
                    return (fk.get("foreign_table_name"), fk.get("foreign_column_name"))
    return None


def validate_and_fix_strategy_joins(strategy: str, schema: list[dict]) -> tuple[str, list[str]]:
    """
    Validate join references in strategy and auto-fix invalid column names.

    Returns:
        - Fixed strategy text
        - List of fixes applied (for logging)

    Algorithm:
    1. Extract all join references from strategy
    2. For each join, check if both columns exist
    3. If column doesn't exist, check if it's a FK and find the correct target
    4. Replace invalid references with correct ones
    """
    fixes = []
    joins = extract_join_references(strategy)

    if not joins:
        logger.debug("No join references found in strategy")
        return strategy, fixes

    logger.info(f"Validating {len(joins)} join references in strategy")

    for from_table, from_col, to_table, to_col in joins:
        # Check if columns exist
        from_table_cols = get_table_columns(schema, from_table)
        to_table_cols = get_table_columns(schema, to_table)

        from_col_exists = from_col in from_table_cols
        to_col_exists = to_col in to_table_cols

        # If both columns exist, join is valid
        if from_col_exists and to_col_exists:
            continue

        # Try to fix invalid column reference
        fixed_from = None
        fixed_to = None

        # Check if from_col is actually in to_table (swap needed)
        if not from_col_exists and from_col in to_table_cols:
            # The FK is in the wrong table - check if to_col is the FK
            fk_mapping = get_foreign_key_mapping(schema, to_table, to_col)
            if fk_mapping and fk_mapping[0] == from_table:
                # Correct: swap the columns
                fixed_from = fk_mapping[1]  # Use PK column from from_table
                fixed_to = to_col  # Keep FK column in to_table

                fix_msg = f"Swapped join: {from_table}.{fixed_from} = {to_table}.{fixed_to} (was {from_table}.{from_col} = {to_table}.{to_col})"
                fixes.append(fix_msg)

                # Replace in strategy
                old_pattern = f"{from_table}.{from_col} = {to_table}.{to_col}"
                new_pattern = f"{from_table}.{fixed_from} = {to_table}.{fixed_to}"
                strategy = strategy.replace(old_pattern, new_pattern)
                logger.info(f"Fixed FK join: {fix_msg}")
                continue

        # Check if from_col is a FK that needs resolution
        if not from_col_exists:
            fk_mapping = get_foreign_key_mapping(schema, from_table, from_col)
            if fk_mapping:
                # from_col is a FK, but it's being used in the wrong table
                # The FK should be in from_table, pointing to to_table.PK
                if fk_mapping[0] == to_table:
                    fixed_from = from_col  # FK column (exists in from_table schema)
                    fixed_to = fk_mapping[1]  # PK column in to_table

                    fix_msg = f"Fixed FK target: {from_table}.{fixed_from} = {to_table}.{fixed_to} (was {from_table}.{from_col} = {to_table}.{to_col})"
                    fixes.append(fix_msg)

                    # Replace in strategy
                    old_pattern = f"{from_table}.{from_col} = {to_table}.{to_col}"
                    new_pattern = f"{from_table}.{fixed_from} = {to_table}.{fixed_to}"
                    strategy = strategy.replace(old_pattern, new_pattern)
                    logger.info(f"Fixed FK join: {fix_msg}")
                    continue

        # Check if to_col is a FK that needs resolution
        if not to_col_exists:
            fk_mapping = get_foreign_key_mapping(schema, to_table, to_col)
            if fk_mapping:
                if fk_mapping[0] == from_table:
                    fixed_from = fk_mapping[1]  # PK column in from_table
                    fixed_to = to_col  # FK column (exists in to_table schema)

                    fix_msg = f"Fixed FK source: {from_table}.{fixed_from} = {to_table}.{fixed_to} (was {from_table}.{from_col} = {to_table}.{to_col})"
                    fixes.append(fix_msg)

                    # Replace in strategy
                    old_pattern = f"{from_table}.{from_col} = {to_table}.{to_col}"
                    new_pattern = f"{from_table}.{fixed_from} = {to_table}.{fixed_to}"
                    strategy = strategy.replace(old_pattern, new_pattern)
                    logger.info(f"Fixed FK join: {fix_msg}")
                    continue

        # If we couldn't fix it, log a warning
        if not from_col_exists or not to_col_exists:
            logger.warning(
                f"Invalid join reference found but could not auto-fix: "
                f"{from_table}.{from_col} = {to_table}.{to_col} "
                f"(from_col_exists={from_col_exists}, to_col_exists={to_col_exists})"
            )

    if fixes:
        logger.info(f"Applied {len(fixes)} FK join fixes to strategy")

    return strategy, fixes
