"""Generate a SQL query deterministically from planner output using SQLGlot."""

import os
import re
from typing import List, Dict
from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from sqlglot import exp, parse_one

from agent.state import State
from utils.logger import get_logger, log_execution_time

load_dotenv()
logger = get_logger()


def get_database_context():
    """Get database-specific context."""
    is_test_db = os.getenv("USE_TEST_DB", "").lower() == "true"
    return {
        "type": "SQLite" if is_test_db else "SQL Server",
        "is_sqlite": is_test_db,
        "is_sql_server": not is_test_db,
        "dialect": "sqlite" if is_test_db else "tsql",  # SQLGlot dialects
    }


def parse_planner_output(planner_output):
    """Parse planner output into dict format."""
    if isinstance(planner_output, dict):
        return planner_output
    else:
        # It's a Pydantic model - use model_dump()
        return planner_output.model_dump() if planner_output else {}


def _column_has_filter_predicate(
    table_name: str, column_name: str, table_selection: Dict, planner_output: Dict
) -> bool:
    """
    Check if a column has an actual filter predicate in the plan.

    This helps detect "orphaned filter columns" - columns marked as role="filter"
    but with no corresponding filter predicate created by the planner.

    Args:
        table_name: Name of the table
        column_name: Name of the column
        table_selection: The table selection dict from the plan
        planner_output: The full planner output dict

    Returns:
        True if a filter predicate exists for this column, False otherwise
    """
    # Check table-level filters
    for filter_pred in table_selection.get("filters", []):
        if (
            filter_pred.get("table") == table_name
            and filter_pred.get("column") == column_name
        ):
            return True

    # Check global filters
    for filter_pred in planner_output.get("global_filters", []):
        if (
            filter_pred.get("table") == table_name
            and filter_pred.get("column") == column_name
        ):
            return True

    # Check HAVING filters (if GROUP BY exists)
    group_by = planner_output.get("group_by")
    if group_by:
        for having_filter in group_by.get("having_filters", []):
            if (
                having_filter.get("table") == table_name
                and having_filter.get("column") == column_name
            ):
                return True

    # Check subquery filters
    for subquery_filter in planner_output.get("subquery_filters", []):
        # Check both outer and subquery references
        if (
            subquery_filter.get("outer_table") == table_name
            and subquery_filter.get("outer_column") == column_name
        ) or (
            subquery_filter.get("subquery_table") == table_name
            and subquery_filter.get("subquery_column") == column_name
        ):
            return True

        # Check filters within the subquery
        for sub_filter in subquery_filter.get("subquery_filters", []):
            if (
                sub_filter.get("table") == table_name
                and sub_filter.get("column") == column_name
            ):
                return True

    return False


def is_sql_expression(column_value: str) -> bool:
    """
    Detect if a column value is a SQL expression vs. a simple column name.

    Returns True if the column contains SQL operators or functions.
    """
    if not column_value:
        return False

    # Check for common SQL expression indicators
    sql_patterns = [
        r"\(",  # Function calls or parentheses
        r"\*",  # Multiplication
        r"\+",  # Addition
        r"-",  # Subtraction (but not in column names)
        r"/",  # Division
        r"COALESCE",  # COALESCE function
        r"CASE",  # CASE expressions
        r"CAST",  # CAST function
        r"CONCAT",  # String concatenation
    ]

    for pattern in sql_patterns:
        if re.search(pattern, column_value, re.IGNORECASE):
            return True

    return False


def parse_and_rewrite_expression(
    expression_str: str, alias_map: Dict, db_context: Dict = None
) -> exp.Expression:
    """
    Parse a SQL expression string and rewrite table references with aliases.

    Args:
        expression_str: SQL expression string (e.g., "COALESCE(t.col, 0) * t.col2")
        alias_map: Mapping of table names to aliases
        db_context: Optional database context for dialect-specific parsing

    Returns:
        SQLGlot expression with table aliases applied
    """
    # Get the appropriate dialect
    dialect = "sqlite" if db_context and db_context.get("is_sqlite") else "tsql"

    try:
        # Parse the expression using SQLGlot
        parsed_expr = parse_one(expression_str, dialect=dialect)

        # Recursively rewrite table references in the expression
        def rewrite_tables(node):
            if isinstance(node, exp.Column):
                # Replace table name with alias if it exists
                if node.table:
                    # Get the table identifier string
                    table_str = (
                        node.table if isinstance(node.table, str) else node.table.this
                    )
                    if table_str in alias_map:
                        # Update to use the alias
                        node.set("table", exp.Identifier(this=alias_map[table_str]))
            return node

        # Transform all nodes in the expression tree recursively
        parsed_expr = parsed_expr.transform(rewrite_tables, copy=False)

        return parsed_expr
    except Exception as e:
        logger.warning(f"Failed to parse expression '{expression_str}': {e}")
        logger.warning("Falling back to treating it as a simple column name")
        # Fallback: treat as simple column (this shouldn't happen often)
        return exp.Column(this=expression_str)


def build_aggregate_expression(
    agg: Dict, alias_map: Dict, db_context: Dict = None
) -> exp.Expression:
    """
    Build an aggregate function expression.

    Supports both simple column references and complex SQL expressions.

    Args:
        agg: AggregateFunction dict
        alias_map: Mapping of table names to aliases
        db_context: Optional database context for dialect-specific handling

    Returns:
        SQLGlot aggregate expression with alias
    """
    function = agg.get("function")
    table = agg.get("table")
    column = agg.get("column")
    output_alias = agg.get("alias")

    table_alias = alias_map.get(table, table)

    # Helper to build column expression (simple or complex)
    def build_column_expr():
        if column is None:
            return exp.Star()
        elif is_sql_expression(column):
            # Column contains a SQL expression - parse it
            logger.info(
                f"[EXPRESSION DETECTED] Parsing complex expression in aggregate: {column}"
            )
            result = parse_and_rewrite_expression(column, alias_map, db_context)
            logger.info(
                f"[EXPRESSION PARSED] Result: {result.sql(dialect=db_context.get('dialect', 'sqlite') if db_context else 'sqlite')}"  # noqa: E501
            )  # noqa: E501
            return result
        else:
            # Simple column reference
            logger.info(
                f"[SIMPLE COLUMN] Using simple column: {column} with table: {table_alias}"
            )
            return exp.Column(this=column, table=table_alias)

    # Build the aggregate expression
    if function == "COUNT" and column is None:
        # COUNT(*)
        agg_expr = exp.Count(this=exp.Star())
    elif function == "COUNT":
        # COUNT(column) or COUNT(expression)
        col_expr = build_column_expr()
        agg_expr = exp.Count(this=col_expr)
    elif function == "COUNT_DISTINCT":
        # COUNT(DISTINCT column) or COUNT(DISTINCT expression)
        col_expr = build_column_expr()
        agg_expr = exp.Count(this=col_expr, distinct=True)
    elif function == "SUM":
        col_expr = build_column_expr()
        agg_expr = exp.Sum(this=col_expr)
    elif function == "AVG":
        col_expr = build_column_expr()
        agg_expr = exp.Avg(this=col_expr)
    elif function == "MIN":
        col_expr = build_column_expr()
        agg_expr = exp.Min(this=col_expr)
    elif function == "MAX":
        col_expr = build_column_expr()
        agg_expr = exp.Max(this=col_expr)
    else:
        # Fallback - generic aggregate
        col_expr = build_column_expr()
        agg_expr = exp.Anonymous(this=function, expressions=[col_expr])

    # Add alias to the aggregate
    if output_alias:
        return exp.Alias(this=agg_expr, alias=output_alias)

    return agg_expr


def build_window_function_expression(
    window_func: Dict, alias_map: Dict
) -> exp.Expression:
    """
    Build a window function expression.

    Args:
        window_func: WindowFunction dict
        alias_map: Mapping of table names to aliases

    Returns:
        SQLGlot window function expression with alias
    """
    function = window_func.get("function")
    partition_by = window_func.get("partition_by", [])
    order_by = window_func.get("order_by", [])
    output_alias = window_func.get("alias")

    # Build partition by columns
    partition_exprs = []
    for col_info in partition_by:
        table = col_info.get("table")
        column = col_info.get("column")
        table_alias = alias_map.get(table, table)
        partition_exprs.append(exp.Column(this=column, table=table_alias))

    # Build order by columns
    order_exprs = []
    for order_col in order_by:
        table = order_col.get("table")
        column = order_col.get("column")
        direction = order_col.get("direction", "ASC")
        table_alias = alias_map.get(table, table)
        col_expr = exp.Column(this=column, table=table_alias)
        order_exprs.append(exp.Ordered(this=col_expr, desc=(direction == "DESC")))

    # Build the window function
    if function == "ROW_NUMBER":
        func_expr = exp.RowNumber()
    elif function == "RANK":
        func_expr = exp.Rank()
    elif function == "DENSE_RANK":
        func_expr = exp.DenseRank()
    elif function in ["SUM", "AVG", "COUNT", "MIN", "MAX"]:
        # Aggregate window functions need a column
        # For now, assume we need to look it up from context
        # This is simplified - may need enhancement
        func_expr = exp.Anonymous(this=function)
    else:
        # Generic window function
        func_expr = exp.Anonymous(this=function)

    # Build OVER clause
    # window_spec = exp.Window(
    #     partition_by=partition_exprs if partition_exprs else None,
    #     order=exp.Order(expressions=order_exprs) if order_exprs else None,
    # )

    # Combine function with OVER
    window_expr = exp.Window(
        this=func_expr,
        partition_by=partition_exprs if partition_exprs else None,
        order=exp.Order(expressions=order_exprs) if order_exprs else None,
    )

    # Add alias
    if output_alias:
        return exp.Alias(this=window_expr, alias=output_alias)

    return window_expr


def build_select_columns(
    selections: List[Dict],
    db_context: Dict,
    planner_output: Dict,
    group_by_spec: Dict = None,
    window_functions: List[Dict] = None,
    alias_map: Dict = None,
) -> List[exp.Expression]:
    """
    Build SELECT column expressions from table selections.

    Args:
        selections: List of TableSelection dicts
        db_context: Database context
        planner_output: Full planner output dict (for filter predicate checks)
        group_by_spec: Optional GroupBySpec dict for aggregations
        window_functions: Optional list of WindowFunction dicts
        alias_map: Optional alias mapping

    Returns:
        List of SQLGlot column expressions
    """
    columns = []

    # If we have GROUP BY, handle it specially
    if group_by_spec:
        # Add GROUP BY columns first
        for col_info in group_by_spec.get("group_by_columns", []):
            table = col_info.get("table")
            column = col_info.get("column")
            table_alias = alias_map.get(table, table) if alias_map else table
            col_expr = exp.Column(this=column, table=table_alias)
            columns.append(col_expr)

        # Add aggregates
        for agg in group_by_spec.get("aggregates", []):
            agg_expr = build_aggregate_expression(agg, alias_map or {}, db_context)
            columns.append(agg_expr)
    else:
        # Regular projection columns
        for table_selection in selections:
            table_name = table_selection.get("table")
            alias = table_selection.get("alias") or table_name  # Handle None/null
            table_columns = table_selection.get("columns", [])

            # Filter to only projection columns (not filter-only columns)
            # HEURISTIC FIX: If a column has role="filter" but no corresponding filter predicate
            # exists in the plan, treat it as a projection column instead.
            #
            # Observed behavior: User query "List all applications tagged with security risk"
            # - Planner marked TagName as role="filter"
            # - But planner FORGOT to create the filter predicate (filters: [], global_filters: [])
            # - Result: TagName was neither displayed NOR filtered on!
            #
            # This heuristic ensures filter columns are at least visible if the filter is missing.
            projection_columns = []
            for col in table_columns:
                if col.get("role") == "projection":
                    projection_columns.append(col)
                elif col.get("role") == "filter":
                    # Check if this filter column has an actual filter predicate
                    col_name = col.get("column")
                    has_filter = _column_has_filter_predicate(
                        table_name, col_name, table_selection, planner_output
                    )
                    if not has_filter:
                        # Orphaned filter column - treat as projection
                        logger.info(
                            f"Column {table_name}.{col_name} has role='filter' but no filter predicate exists. "
                            f"Treating as projection column to ensure visibility.",
                            extra={"table": table_name, "column": col_name},
                        )
                        projection_columns.append(col)

            for col_info in projection_columns:
                col_name = col_info.get("column")

                # Create column reference with table alias
                col_expr = exp.Column(this=col_name, table=alias)
                columns.append(col_expr)

    # Add window functions if any
    if window_functions:
        for window_func in window_functions:
            window_expr = build_window_function_expression(window_func, alias_map or {})
            columns.append(window_expr)

    # If no columns specified, select all
    if not columns:
        columns = [exp.Star()]

    return columns


def build_table_expression(selections: List[Dict]) -> exp.Table:
    """
    Build the FROM table expression.

    Args:
        selections: List of TableSelection dicts

    Returns:
        SQLGlot Table expression for the first table
    """
    if not selections:
        raise ValueError("No tables in selections")

    first_table = selections[0]
    table_name = first_table.get("table")
    alias = first_table.get("alias") or table_name  # Handle None/null

    # Create table with alias if different from table name
    if alias and alias != table_name:
        return exp.Table(this=table_name, alias=alias)
    else:
        return exp.Table(this=table_name)


def translate_join_type(join_type_str: str) -> str:
    """Translate join type to SQLGlot join kind."""
    join_map = {
        "inner": "INNER",
        "left": "LEFT",
        "right": "RIGHT",
        "full": "FULL",
    }
    return join_map.get(join_type_str.lower(), "INNER")


def build_join_expressions(
    join_edges: List[Dict], selections: List[Dict]
) -> List[exp.Join]:
    """
    Build JOIN expressions from join edges.

    Args:
        join_edges: List of JoinEdge dicts
        selections: List of TableSelection dicts for alias lookup

    Returns:
        List of SQLGlot Join expressions
    """
    joins = []

    # Create alias lookup (handle None/null aliases)
    alias_map = {}
    for sel in selections:
        table = sel.get("table")
        alias = sel.get("alias")
        # If alias is None or empty, use table name
        alias_map[table] = alias if alias else table

    for edge in join_edges:
        from_table = edge.get("from_table")
        from_column = edge.get("from_column")
        to_table = edge.get("to_table")
        to_column = edge.get("to_column")
        join_type = edge.get("join_type", "inner")

        # Get aliases
        from_alias = alias_map.get(from_table, from_table)
        to_alias = alias_map.get(to_table, to_table)

        # Build join condition: from_table.from_column = to_table.to_column
        left_col = exp.Column(this=from_column, table=from_alias)
        right_col = exp.Column(this=to_column, table=to_alias)
        join_condition = exp.EQ(this=left_col, expression=right_col)

        # Create table expression for the join
        if to_alias and to_alias != to_table:
            join_table = exp.Table(
                this=to_table, alias=exp.TableAlias(this=exp.Identifier(this=to_alias))
            )
        else:
            join_table = exp.Table(this=to_table)

        # Create join - use appropriate join kind
        join_kind_str = translate_join_type(join_type)

        # Build the join expression properly
        join_expr = exp.Join(this=join_table, on=join_condition, kind=join_kind_str)

        joins.append(join_expr)

    return joins


def unquote_sql_functions(value):
    """
    Detect and unquote SQL functions that have been incorrectly wrapped in quotes.

    LLMs sometimes wrap SQL function calls in quotes, treating them as strings
    instead of expressions. For example:
    - 'DATEADD(DAY, -60, GETDATE())' → DATEADD(DAY, -60, GETDATE())
    - 'GETDATE()' → GETDATE()
    - 'CAST(...)' → CAST(...)

    This function detects these patterns and removes the outer quotes.

    Args:
        value: The value to check and potentially unquote

    Returns:
        Unquoted value if it was a quoted SQL function, otherwise original value
    """
    if not isinstance(value, str):
        return value

    # Pattern matches: 'FUNCTION_NAME(...)' with any content inside parentheses
    # Examples:
    #   'DATEADD(DAY, -60, GETDATE())' ✓
    #   'GETDATE()' ✓
    #   'CAST(x AS INT)' ✓
    #   'normal string' ✗ (no parentheses)
    #   '2025-10-31' ✗ (no parentheses)

    # Check if value is quoted and contains a function call pattern
    # Pattern: string starts with quote, has uppercase letters/underscore, has parentheses, ends with quote
    # Note: \(.*\) allows empty parentheses or any content
    function_pattern = r"^'([A-Z_][A-Z0-9_]*\s*\(.*\))'$"
    match = re.match(function_pattern, value, re.IGNORECASE)

    if match:
        unquoted = match.group(1)
        logger.info(
            "Unquoting SQL function expression",
            extra={
                "original_value": value,
                "unquoted_value": unquoted
            }
        )
        return unquoted

    return value


def infer_value_type(value) -> str:
    """
    Infer the SQL type of a value for proper literal generation.

    Returns: 'null', 'boolean', 'number', 'date', 'datetime', or 'string'

    Args:
        value: The value to infer type for

    Returns:
        Type string: 'null', 'boolean', 'number', 'date', 'datetime', or 'string'
    """
    # Handle None/NULL
    if value is None:
        return "null"

    # Handle boolean values (Python bool)
    if isinstance(value, bool):
        return "boolean"

    # Handle numeric values (int, float)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"

    # Handle string representations of common SQL types
    if isinstance(value, str):
        # Check for NULL string
        if value.upper() == "NULL":
            return "null"

        # Check for datetime format: YYYY-MM-DD HH:MM:SS (with optional microseconds)
        # Patterns: 2025-10-31 14:30:00 or 2025-10-31 14:30:00.123456
        datetime_pattern = r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(\.\d+)?$"
        if re.match(datetime_pattern, value):
            return "datetime"

        # Check for date format: YYYY-MM-DD
        date_pattern = r"^\d{4}-\d{2}-\d{2}$"
        if re.match(date_pattern, value):
            return "date"

        # Check for boolean strings (case-insensitive)
        if value.lower() in ("true", "false", "0", "1"):
            # If it's '0' or '1', treat as number for BIT compatibility
            if value in ("0", "1"):
                return "number"
            return "boolean"

        # Try to parse as number
        try:
            float(value)
            return "number"
        except (ValueError, TypeError):
            pass

    # Default to string
    return "string"


def create_typed_literal(value, db_context: Dict = None) -> exp.Expression:
    """
    Create a properly typed SQLGlot literal based on value type.

    This ensures BIT columns get numeric 0/1, not string '0'/'1', and
    dates/datetimes get proper SQL date/datetime literals.

    Args:
        value: The value to convert to a literal
        db_context: Optional database context for dialect-specific handling

    Returns:
        SQLGlot Literal expression with correct type
    """
    value_type = infer_value_type(value)

    if value_type == "null":
        return exp.Null()
    elif value_type == "boolean":
        # Convert boolean to 1/0 for SQL Server BIT compatibility
        if isinstance(value, bool):
            return exp.Literal.number(1 if value else 0)
        elif isinstance(value, str):
            # Handle string booleans
            if value.lower() == "true":
                return exp.Literal.number(1)
            elif value.lower() == "false":
                return exp.Literal.number(0)
        return exp.Literal.number(1 if value else 0)
    elif value_type == "number":
        # Handle numeric types
        if isinstance(value, str):
            # Parse string to appropriate numeric type
            try:
                if "." in value:
                    return exp.Literal.number(float(value))
                else:
                    return exp.Literal.number(int(value))
            except ValueError:
                # Fallback to string if parsing fails
                return exp.Literal.string(str(value))
        return exp.Literal.number(value)
    elif value_type == "date":
        # ISO date format: YYYY-MM-DD
        # SQL Server: CAST('2025-10-31' AS DATE)
        # SQLite: '2025-10-31' (stores as text)
        is_sqlite = db_context and db_context.get("is_sqlite", False)
        if is_sqlite:
            # SQLite stores dates as text
            return exp.Literal.string(str(value))
        else:
            # SQL Server: CAST('2025-10-31' AS DATE)
            return exp.Cast(
                this=exp.Literal.string(str(value)), to=exp.DataType.build("DATE")
            )
    elif value_type == "datetime":
        # ISO datetime format: YYYY-MM-DD HH:MM:SS
        # SQL Server: CAST('2025-10-31 14:30:00' AS DATETIME)
        # SQLite: '2025-10-31 14:30:00' (stores as text)
        is_sqlite = db_context and db_context.get("is_sqlite", False)
        if is_sqlite:
            # SQLite stores datetimes as text
            return exp.Literal.string(str(value))
        else:
            # SQL Server: CAST('2025-10-31 14:30:00' AS DATETIME)
            return exp.Cast(
                this=exp.Literal.string(str(value)), to=exp.DataType.build("DATETIME")
            )
    else:
        # String type
        return exp.Literal.string(str(value))


def is_column_reference(value: str) -> bool:
    """
    Check if a value looks like a column reference (e.g., 'table.column').

    Args:
        value: The value to check

    Returns:
        True if the value appears to be a column reference
    """
    if not isinstance(value, str):
        return False

    # Check if it matches the pattern: word.word (table.column)
    # This helps detect when a filter value is actually a column reference
    import re

    pattern = r"^[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*$"
    return bool(re.match(pattern, value))


def parse_column_reference(value: str, alias_map: Dict) -> exp.Column:
    """
    Parse a column reference like 'table.column' into a Column expression.

    Args:
        value: The column reference string (e.g., 'tb_Users.CompanyID')
        alias_map: Mapping of table names to aliases

    Returns:
        SQLGlot Column expression
    """
    parts = value.split(".")
    if len(parts) == 2:
        table_name, column_name = parts
        # Use alias if available
        table_ref = alias_map.get(table_name, table_name)
        return exp.Column(this=column_name, table=table_ref)
    else:
        # Fallback to treating as simple column
        return exp.Column(this=value)


def build_filter_expression(
    filter_pred: Dict, alias_map: Dict, db_context: Dict = None
) -> exp.Expression:
    """
    Build a WHERE/HAVING condition from a FilterPredicate.

    Supports both simple column references and complex SQL expressions.

    Args:
        filter_pred: FilterPredicate dict
        alias_map: Mapping of table names to aliases
        db_context: Optional database context for dialect-specific handling

    Returns:
        SQLGlot expression for the filter
    """
    table = filter_pred.get("table")
    column = filter_pred.get("column")
    op = filter_pred.get("op")
    value = filter_pred.get("value")

    # Get table alias
    table_alias = alias_map.get(table, table)

    # Create column reference (simple or complex expression)
    if is_sql_expression(column):
        # Column contains a SQL expression - parse it
        logger.debug(f"Parsing complex expression in filter: {column}")
        col_expr = parse_and_rewrite_expression(column, alias_map, db_context)
    else:
        # Simple column reference
        col_expr = exp.Column(this=column, table=table_alias)

    # Build expression based on operator
    if op == "=":
        # Check if value is a column reference instead of a literal
        if is_column_reference(value):
            value_expr = parse_column_reference(value, alias_map)
        else:
            value_expr = create_typed_literal(value, db_context)
        return exp.EQ(this=col_expr, expression=value_expr)
    elif op == "!=":
        # Check if value is a column reference instead of a literal
        if is_column_reference(value):
            value_expr = parse_column_reference(value, alias_map)
        else:
            value_expr = create_typed_literal(value, db_context)
        return exp.NEQ(this=col_expr, expression=value_expr)
    elif op == ">":
        return exp.GT(this=col_expr, expression=create_typed_literal(value, db_context))
    elif op == ">=":
        return exp.GTE(
            this=col_expr, expression=create_typed_literal(value, db_context)
        )
    elif op == "<":
        return exp.LT(this=col_expr, expression=create_typed_literal(value, db_context))
    elif op == "<=":
        return exp.LTE(
            this=col_expr, expression=create_typed_literal(value, db_context)
        )
    elif op == "between":
        if isinstance(value, list) and len(value) == 2:
            return exp.Between(
                this=col_expr,
                low=create_typed_literal(value[0], db_context),
                high=create_typed_literal(value[1], db_context),
            )
    elif op == "in":
        if isinstance(value, list):
            # Handle IN with NULL: col IN (0, NULL) needs to become (col = 0 OR col IS NULL)
            has_null = any(
                v is None or (isinstance(v, str) and v.upper() == "NULL") for v in value
            )
            non_null_values = [
                v
                for v in value
                if v is not None and not (isinstance(v, str) and v.upper() == "NULL")
            ]

            if has_null and non_null_values:
                # Mixed: (col IN (values) OR col IS NULL)
                values = [create_typed_literal(v, db_context) for v in non_null_values]
                in_expr = exp.In(this=col_expr, expressions=values)
                null_expr = exp.Is(this=col_expr, expression=exp.Null())
                return exp.Or(this=in_expr, expression=null_expr)
            elif has_null and not non_null_values:
                # Only NULL: col IS NULL
                return exp.Is(this=col_expr, expression=exp.Null())
            else:
                # No NULL values: standard IN clause
                values = [create_typed_literal(v, db_context) for v in value]
                return exp.In(this=col_expr, expressions=values)
    elif op == "not_in":
        if isinstance(value, list):
            # Handle NOT IN with NULL: col NOT IN (0, NULL) needs special handling
            has_null = any(
                v is None or (isinstance(v, str) and v.upper() == "NULL") for v in value
            )
            non_null_values = [
                v
                for v in value
                if v is not None and not (isinstance(v, str) and v.upper() == "NULL")
            ]

            if has_null and non_null_values:
                # Mixed: (col NOT IN (values) AND col IS NOT NULL)
                values = [create_typed_literal(v, db_context) for v in non_null_values]
                not_in_expr = exp.Not(this=exp.In(this=col_expr, expressions=values))
                not_null_expr = exp.Is(
                    this=col_expr, expression=exp.Null(), inverse=True
                )
                return exp.And(this=not_in_expr, expression=not_null_expr)
            elif has_null and not non_null_values:
                # Only NULL: col IS NOT NULL
                return exp.Is(this=col_expr, expression=exp.Null(), inverse=True)
            else:
                # No NULL values: standard NOT IN clause
                values = [create_typed_literal(v, db_context) for v in value]
                in_expr = exp.In(this=col_expr, expressions=values)
                return exp.Not(this=in_expr)
    elif op == "like":
        return exp.Like(this=col_expr, expression=exp.Literal.string(str(value)))
    elif op == "ilike":
        # SQL Server doesn't support ILIKE - use LIKE instead (case-insensitive by default)
        # SQLite also uses LIKE which is case-insensitive by default
        return exp.Like(this=col_expr, expression=exp.Literal.string(str(value)))
    elif op == "starts_with":
        pattern = f"{value}%"
        return exp.Like(this=col_expr, expression=exp.Literal.string(pattern))
    elif op == "ends_with":
        pattern = f"%{value}"
        return exp.Like(this=col_expr, expression=exp.Literal.string(pattern))
    elif op == "is_null":
        return exp.Is(this=col_expr, expression=exp.Null())
    elif op == "is_not_null":
        return exp.Is(this=col_expr, expression=exp.Null(), inverse=True)

    # Fallback - return basic equality
    return exp.EQ(this=col_expr, expression=exp.Literal.string(str(value)))


def build_subquery_filter_expression(
    subquery_filter: Dict, alias_map: Dict
) -> exp.Expression:
    """
    Build a subquery filter expression (e.g., WHERE col IN (SELECT...)).

    Args:
        subquery_filter: SubqueryFilter dict
        alias_map: Mapping of table names to aliases

    Returns:
        SQLGlot expression for the subquery filter
    """
    outer_table = subquery_filter.get("outer_table")
    outer_column = subquery_filter.get("outer_column")
    op = subquery_filter.get("op")
    subquery_table = subquery_filter.get("subquery_table")
    subquery_column = subquery_filter.get("subquery_column")
    subquery_filters = subquery_filter.get("subquery_filters", [])

    # Build outer column reference
    outer_table_alias = alias_map.get(outer_table, outer_table)
    outer_col_expr = exp.Column(this=outer_column, table=outer_table_alias)

    # Build subquery SELECT
    from sqlglot import select

    subquery_col_expr = exp.Column(this=subquery_column, table=subquery_table)
    subquery = select(subquery_col_expr).from_(subquery_table)

    # Add subquery filters
    for sq_filter in subquery_filters:
        sq_table = sq_filter.get("table")
        sq_column = sq_filter.get("column")
        sq_op = sq_filter.get("op")
        sq_value = sq_filter.get("value")

        # Build condition string for subquery
        # Note: This is in build_subquery_filter_expression which doesn't have db_context
        # For now, pass None (will use default behavior)
        condition = format_filter_condition(
            sq_table, sq_column, sq_op, sq_value, db_context=None
        )
        subquery = subquery.where(condition)

    # Build the IN/NOT IN expression
    if op == "in":
        return exp.In(this=outer_col_expr, expressions=[subquery])
    elif op == "not_in":
        in_expr = exp.In(this=outer_col_expr, expressions=[subquery])
        return exp.Not(this=in_expr)
    elif op == "exists":
        return exp.Exists(this=subquery)
    elif op == "not_exists":
        exists_expr = exp.Exists(this=subquery)
        return exp.Not(this=exists_expr)

    # Fallback
    return exp.In(this=outer_col_expr, expressions=[subquery])


def build_where_clause(
    selections: List[Dict],
    global_filters: List[Dict],
    alias_map: Dict,
    subquery_filters: List[Dict] = None,
    db_context: Dict = None,
) -> exp.Expression:
    """
    Build WHERE clause from table filters, global filters, and subquery filters.

    Args:
        selections: List of TableSelection dicts
        global_filters: List of global FilterPredicate dicts
        alias_map: Mapping of table names to aliases
        subquery_filters: Optional list of SubqueryFilter dicts
        db_context: Optional database context for dialect-specific handling

    Returns:
        SQLGlot WHERE expression (or None if no filters)
    """
    all_conditions = []

    # Collect filters from each table selection
    for table_selection in selections:
        table_filters = table_selection.get("filters", [])
        for filter_pred in table_filters:
            condition = build_filter_expression(filter_pred, alias_map, db_context)
            if condition:
                all_conditions.append(condition)

    # Add global filters
    for filter_pred in global_filters:
        condition = build_filter_expression(filter_pred, alias_map, db_context)
        if condition:
            all_conditions.append(condition)

    # Add subquery filters
    if subquery_filters:
        for sq_filter in subquery_filters:
            condition = build_subquery_filter_expression(sq_filter, alias_map)
            if condition:
                all_conditions.append(condition)

    # Combine with AND
    if not all_conditions:
        return None

    where_expr = all_conditions[0]
    for condition in all_conditions[1:]:
        where_expr = exp.And(this=where_expr, expression=condition)

    return where_expr


def build_group_by_clause(group_by_spec: Dict, alias_map: Dict) -> List[exp.Expression]:
    """
    Build GROUP BY clause from GroupBySpec.

    Args:
        group_by_spec: GroupBySpec dict
        alias_map: Mapping of table names to aliases

    Returns:
        List of SQLGlot column expressions for GROUP BY
    """
    if not group_by_spec:
        return []

    group_by_exprs = []
    for col_info in group_by_spec.get("group_by_columns", []):
        table = col_info.get("table")
        column = col_info.get("column")
        table_alias = alias_map.get(table, table)
        col_expr = exp.Column(this=column, table=table_alias)
        group_by_exprs.append(col_expr)

    return group_by_exprs


def build_having_clause(having_filters: List[Dict], alias_map: Dict) -> exp.Expression:
    """
    Build HAVING clause from having filters.

    Args:
        having_filters: List of FilterPredicate dicts for HAVING clause
        alias_map: Mapping of table names to aliases

    Returns:
        SQLGlot HAVING expression (or None if no filters)
    """
    if not having_filters:
        return None

    all_conditions = []
    for filter_pred in having_filters:
        condition = build_filter_expression(filter_pred, alias_map)
        if condition:
            all_conditions.append(condition)

    if not all_conditions:
        return None

    having_expr = all_conditions[0]
    for condition in all_conditions[1:]:
        having_expr = exp.And(this=having_expr, expression=condition)

    return having_expr


def apply_time_filter(
    query: exp.Select,
    time_filter: str,
    selections: List[Dict],
    alias_map: Dict,
    db_context: Dict,
) -> exp.Select:
    """
    Apply time-based filtering to the query.

    Args:
        query: SQLGlot SELECT expression
        time_filter: Time filter string (e.g., "Last 7 Days", "Last 30 Days")
        selections: List of TableSelection dicts
        alias_map: Mapping of table names to aliases
        db_context: Database context

    Returns:
        Modified SQLGlot SELECT expression
    """
    if time_filter == "All Time":
        return query

    # Find a timestamp column (look for common names)
    timestamp_columns = [
        "CreatedOn",
        "UpdatedOn",
        "Created",
        "Modified",
        "Timestamp",
        "Date",
    ]
    time_column = None
    time_table = None

    for table_selection in selections:
        table_columns = table_selection.get("columns", [])
        for col_info in table_columns:
            col_name = col_info.get("column")
            if col_name in timestamp_columns:
                time_column = col_name
                time_table = table_selection.get("table")
                break
        if time_column:
            break

    if not time_column or not time_table:
        # No timestamp column found, skip time filtering
        return query

    # Calculate date based on filter
    days_map = {
        "Last 7 Days": 7,
        "Last 30 Days": 30,
        "Last 90 Days": 90,
        "Last 365 Days": 365,
    }

    days = days_map.get(time_filter)
    if not days:
        return query

    # Build time filter condition
    table_alias = alias_map.get(time_table, time_table)
    col_expr = exp.Column(this=time_column, table=table_alias)

    if db_context["is_sqlite"]:
        # SQLite: datetime('now', '-N days')
        date_expr = exp.Anonymous(
            this="datetime",
            expressions=[
                exp.Literal.string("now"),
                exp.Literal.string(f"-{days} days"),
            ],
        )
    else:
        # SQL Server: DATEADD(day, -N, GETDATE())
        # Note: 'day' should be an identifier, not a quoted string
        date_expr = exp.Anonymous(
            this="DATEADD",
            expressions=[
                exp.Var(this="day"),  # Use Var for identifier, not Literal.string
                exp.Literal.number(-days),
                exp.Anonymous(this="GETDATE", expressions=[]),
            ],
        )

    time_condition = exp.GTE(this=col_expr, expression=date_expr)

    # Add to WHERE clause
    if query.args.get("where"):
        # Combine with existing WHERE
        existing_where = query.args["where"].this
        new_where = exp.And(this=existing_where, expression=time_condition)
        query.set("where", exp.Where(this=new_where))
    else:
        # Create new WHERE
        query.set("where", exp.Where(this=time_condition))

    return query


def apply_order_and_limit(
    query: exp.Select,
    sort_order: str,
    result_limit: int,
    db_context: Dict,
    selections: List[Dict],
) -> exp.Select:
    """
    Apply ORDER BY and LIMIT/TOP to the query.

    Args:
        query: SQLGlot SELECT expression
        sort_order: Sort order preference
        result_limit: Result limit
        db_context: Database context
        selections: List of TableSelection dicts

    Returns:
        Modified SQLGlot SELECT expression
    """
    # Apply ORDER BY if specified
    if sort_order and sort_order != "Default":
        # Find first projection column for ordering
        first_col = None
        first_table_alias = None

        for table_selection in selections:
            table_columns = table_selection.get("columns", [])
            projection_cols = [
                col for col in table_columns if col.get("role") == "projection"
            ]
            if projection_cols:
                first_col = projection_cols[0].get("column")
                first_table_alias = table_selection.get(
                    "alias", table_selection.get("table")
                )
                break

        if first_col:
            col_expr = exp.Column(this=first_col, table=first_table_alias)
            desc = sort_order.lower() == "descending"
            order_expr = exp.Ordered(this=col_expr, desc=desc)
            query.set("order", exp.Order(expressions=[order_expr]))

    # Apply LIMIT/TOP if specified
    if result_limit and result_limit > 0:
        if db_context["is_sqlite"]:
            # SQLite uses LIMIT
            query.set("limit", exp.Limit(expression=exp.Literal.number(result_limit)))
        else:
            # SQL Server uses TOP (part of SELECT clause)
            # Note: SQLGlot handles this via the 'top' argument in SELECT
            query.set("limit", exp.Limit(expression=exp.Literal.number(result_limit)))

    return query


def build_sql_query(plan_dict: Dict, state: State, db_context: Dict) -> str:
    """
    Build SQL query from planner output using SQLGlot.

    Args:
        plan_dict: Planner output as dictionary
        state: Agent state
        db_context: Database context

    Returns:
        SQL query string
    """
    from sqlglot import select

    selections = plan_dict.get("selections", [])
    join_edges = plan_dict.get("join_edges", [])
    global_filters = plan_dict.get("global_filters", [])
    group_by_spec = plan_dict.get("group_by")
    window_functions = plan_dict.get("window_functions", [])
    subquery_filters = plan_dict.get("subquery_filters", [])
    # ctes = plan_dict.get("ctes", [])

    if not selections:
        raise ValueError("No table selections in planner output")

    # Check for duplicate tables in selections (potential issue)
    table_names = [sel.get("table") for sel in selections]
    duplicate_tables = [t for t in table_names if table_names.count(t) > 1]
    if duplicate_tables:
        logger.warning(
            f"Duplicate tables in selections: {set(duplicate_tables)}. "
            f"This may cause join issues. Consider using aliases in the planner."
        )

    # Build SELECT column list as strings (with column aliases to avoid duplicates)
    select_cols = []

    # Track column names to detect duplicates
    seen_columns = {}  # {column_name: count}

    # Handle GROUP BY case
    if group_by_spec:
        # Add GROUP BY columns
        for col_info in group_by_spec.get("group_by_columns", []):
            table = col_info.get("table")
            column = col_info.get("column")

            # Add column alias if duplicate
            if column in seen_columns:
                seen_columns[column] += 1
                # Use table name prefix for uniqueness
                col_alias = f"{table}_{column}"
                select_cols.append(f"{table}.{column} AS {col_alias}")
            else:
                seen_columns[column] = 1
                select_cols.append(f"{table}.{column}")

        # Add aggregates
        for agg in group_by_spec.get("aggregates", []):
            function = agg.get("function")
            table = agg.get("table")
            column = agg.get("column")
            output_alias = agg.get("alias")

            if function == "COUNT" and column is None:
                select_cols.append(f"COUNT(*) AS {output_alias}")
            elif function == "COUNT_DISTINCT":
                # Check if column is an expression
                if column and is_sql_expression(column):
                    select_cols.append(f"COUNT(DISTINCT {column}) AS {output_alias}")
                else:
                    select_cols.append(
                        f"COUNT(DISTINCT {table}.{column}) AS {output_alias}"
                    )
            else:
                # Check if column is an expression (no table prefix needed)
                if column and is_sql_expression(column):
                    logger.info(
                        f"[STRING PATH] Detected expression in aggregate: {column}"
                    )
                    select_cols.append(f"{function}({column}) AS {output_alias}")
                else:
                    select_cols.append(
                        f"{function}({table}.{column}) AS {output_alias}"
                    )
    else:
        # Regular projection columns
        for table_selection in selections:
            table_name = table_selection.get("table")
            table_columns = table_selection.get("columns", [])

            # Filter to only projection columns
            # Apply same orphaned filter column heuristic as in SQLGlot path
            projection_columns = []
            for col in table_columns:
                if col.get("role") == "projection":
                    projection_columns.append(col)
                elif col.get("role") == "filter":
                    col_name = col.get("column")
                    has_filter = _column_has_filter_predicate(
                        table_name, col_name, table_selection, plan_dict
                    )
                    if not has_filter:
                        logger.info(
                            f"Column {table_name}.{col_name} has role='filter' but no filter predicate. "
                            f"Treating as projection.",
                            extra={"table": table_name, "column": col_name},
                        )
                        projection_columns.append(col)

            for col_info in projection_columns:
                col_name = col_info.get("column")

                # Check for duplicate column names and add alias if needed
                if col_name in seen_columns:
                    seen_columns[col_name] += 1
                    # Use table name prefix for uniqueness (e.g., CompanyID, ComputerID)
                    # Strip "tb_" prefix if present for cleaner aliases
                    table_prefix = table_name.replace("tb_", "").replace("Saas", "")
                    col_alias = f"{table_prefix}{col_name}"
                    select_cols.append(f"{table_name}.{col_name} AS {col_alias}")
                else:
                    seen_columns[col_name] = 1
                    select_cols.append(f"{table_name}.{col_name}")

    # Add window functions
    for window_func in window_functions:
        function = window_func.get("function")
        partition_by = window_func.get("partition_by", [])
        order_by = window_func.get("order_by", [])
        output_alias = window_func.get("alias")

        # Build PARTITION BY clause
        partition_cols = []
        for col_info in partition_by:
            table = col_info.get("table")
            column = col_info.get("column")
            partition_cols.append(f"{table}.{column}")

        # Build ORDER BY clause
        order_cols = []
        for order_col in order_by:
            table = order_col.get("table")
            column = order_col.get("column")
            direction = order_col.get("direction", "ASC")
            order_cols.append(f"{table}.{column} {direction}")

        # Build OVER clause
        over_parts = []
        if partition_cols:
            over_parts.append(f"PARTITION BY {', '.join(partition_cols)}")
        if order_cols:
            over_parts.append(f"ORDER BY {', '.join(order_cols)}")
        over_clause = f"OVER ({' '.join(over_parts)})" if over_parts else "OVER ()"

        select_cols.append(f"{function}() {over_clause} AS {output_alias}")

    # If no columns specified, select all
    if not select_cols:
        select_cols = ["*"]

    # Build FROM clause (no aliases - just use table name)
    first_table = selections[0]
    table_name = first_table.get("table")

    # Start with SELECT ... FROM
    query = select(*select_cols).from_(table_name)

    # Add JOINs (no aliases - just use table names)
    # Track which tables have been added to the query
    tables_in_query = {table_name}  # Start with the base FROM table

    # Reorder join_edges to ensure proper dependency order
    # Process joins in multiple passes, adding those that connect to existing tables first
    remaining_edges = join_edges.copy()
    ordered_edges = []
    max_iterations = len(remaining_edges) * 2  # Prevent infinite loops
    iteration = 0

    while remaining_edges and iteration < max_iterations:
        iteration += 1
        made_progress = False

        for edge in remaining_edges[:]:  # Create a copy to iterate
            from_table = edge.get("from_table")
            to_table = edge.get("to_table")

            # Check if at least one table is already in query
            if from_table in tables_in_query or to_table in tables_in_query:
                ordered_edges.append(edge)
                remaining_edges.remove(edge)
                made_progress = True

                # Add the new table to tables_in_query for dependency tracking
                if from_table in tables_in_query:
                    tables_in_query.add(to_table)
                else:
                    tables_in_query.add(from_table)

        if not made_progress:
            # No joins could be added - might be disconnected joins or circular dependency
            logger.warning(
                f"Could not order {len(remaining_edges)} joins - they may be disconnected from the base table. "
                f"Remaining: {remaining_edges}"
            )
            # Add remaining joins anyway to avoid losing them
            ordered_edges.extend(remaining_edges)
            break

    # Reset tables_in_query to just the base FROM table for actual join processing
    tables_in_query = {table_name}

    for i, edge in enumerate(ordered_edges):
        from_table = edge.get("from_table")
        from_column = edge.get("from_column")
        to_table = edge.get("to_table")
        to_column = edge.get("to_column")
        join_type = edge.get("join_type", "inner")

        # Determine which table to join (the one NOT already in the query)
        # Handle three cases: both in query, one in query, neither in query
        if from_table in tables_in_query and to_table in tables_in_query:
            # Both tables already in query - skip this join to avoid duplicates
            logger.warning(
                f"Skipping redundant join: both {from_table} and {to_table} already in query. "
                f"This might indicate a complex join pattern that needs aliases."
            )
            continue
        elif to_table in tables_in_query and from_table not in tables_in_query:
            # Join from_table (to_table already exists)
            join_table_name = from_table
            on_condition = f"{to_table}.{to_column} = {from_table}.{from_column}"
        elif from_table in tables_in_query and to_table not in tables_in_query:
            # Join to_table (from_table already exists)
            join_table_name = to_table
            on_condition = f"{from_table}.{from_column} = {to_table}.{to_column}"
        else:
            # Neither table in query yet - this should rarely happen after reordering
            # Add from_table first so it's available for the ON condition
            logger.warning(
                f"Neither {from_table} nor {to_table} in query yet - join reordering may have failed. "
                f"Adding {from_table} to ensure ON condition works."
            )
            join_table_name = from_table
            on_condition = f"{from_table}.{from_column} = {to_table}.{to_column}"
            # Note: to_table will need to be added in a subsequent join

        # Track that this table is now in the query
        tables_in_query.add(join_table_name)

        # Add join based on type
        if join_type.lower() == "left":
            query = query.join(join_table_name, on=on_condition, join_type="left")
        elif join_type.lower() == "right":
            query = query.join(join_table_name, on=on_condition, join_type="right")
        elif join_type.lower() == "full":
            query = query.join(join_table_name, on=on_condition, join_type="full")
        else:  # inner or default
            query = query.join(join_table_name, on=on_condition)

    # Build WHERE conditions
    where_conditions = []

    # Collect filters from each table
    for table_selection in selections:
        table_filters = table_selection.get("filters", [])
        for filter_pred in table_filters:
            table = filter_pred.get("table")
            column = filter_pred.get("column")
            op = filter_pred.get("op")
            value = filter_pred.get("value")

            where_conditions.append(
                format_filter_condition(table, column, op, value, db_context=db_context)
            )

    # Add global filters
    for filter_pred in global_filters:
        table = filter_pred.get("table")
        column = filter_pred.get("column")
        op = filter_pred.get("op")
        value = filter_pred.get("value")

        where_conditions.append(
            format_filter_condition(table, column, op, value, db_context=db_context)
        )

    # Add subquery filters
    for sq_filter in subquery_filters:
        outer_table = sq_filter.get("outer_table")
        outer_column = sq_filter.get("outer_column")
        op = sq_filter.get("op")
        subquery_table = sq_filter.get("subquery_table")
        subquery_column = sq_filter.get("subquery_column")
        subquery_filters_list = sq_filter.get("subquery_filters", [])

        # Build subquery
        subquery_where = []
        for sq_f in subquery_filters_list:
            sq_table = sq_f.get("table")
            sq_column = sq_f.get("column")
            sq_op = sq_f.get("op")
            sq_value = sq_f.get("value")
            subquery_where.append(
                format_filter_condition(
                    sq_table, sq_column, sq_op, sq_value, db_context=db_context
                )
            )

        subquery_str = f"SELECT {subquery_column} FROM {subquery_table}"
        if subquery_where:
            subquery_str += f" WHERE {' AND '.join(subquery_where)}"

        # Add to WHERE conditions
        if op == "in":
            where_conditions.append(f"{outer_table}.{outer_column} IN ({subquery_str})")
        elif op == "not_in":
            where_conditions.append(
                f"{outer_table}.{outer_column} NOT IN ({subquery_str})"
            )

    # Apply WHERE clause
    for condition in where_conditions:
        query = query.where(condition)

    # Apply time filter
    time_filter = state.get("time_filter", "All Time")
    if time_filter != "All Time":
        time_condition = build_time_filter_condition(
            time_filter, selections, db_context
        )
        if time_condition:
            query = query.where(time_condition)

    # Apply GROUP BY
    if group_by_spec:
        group_by_cols = []
        for col_info in group_by_spec.get("group_by_columns", []):
            table = col_info.get("table")
            column = col_info.get("column")
            group_by_cols.append(f"{table}.{column}")

        for col in group_by_cols:
            query = query.group_by(col)

        # Apply HAVING clause if present
        having_filters = group_by_spec.get("having_filters", [])
        if having_filters:
            # Collect aggregate aliases for HAVING clause
            aggregate_aliases = set()
            for agg in group_by_spec.get("aggregates", []):
                alias = agg.get("alias")
                if alias:
                    aggregate_aliases.add(alias)

            having_conditions = []
            for filter_pred in having_filters:
                # For HAVING, the column might be an aggregate alias
                table = filter_pred.get("table")
                column = filter_pred.get("column")
                op = filter_pred.get("op")
                value = filter_pred.get("value")

                having_conditions.append(
                    format_filter_condition(
                        table, column, op, value, aggregate_aliases, db_context
                    )
                )

            for condition in having_conditions:
                query = query.having(condition)

    # Apply ORDER BY
    # Priority: 1) Plan's order_by, 2) State's sort_order
    plan_order_by = plan_dict.get("order_by", [])
    if plan_order_by:
        # Collect aggregate aliases to detect if ORDER BY references an alias
        aggregate_aliases = set()
        if group_by_spec:
            for agg in group_by_spec.get("aggregates", []):
                alias = agg.get("alias")
                if alias:
                    aggregate_aliases.add(alias)

        # Create alias map for expression parsing (maps table names to themselves since no aliases)
        alias_map = {sel.get("table"): sel.get("table") for sel in selections}

        # Use plan's ORDER BY specification
        for order_col_spec in plan_order_by:
            table = order_col_spec.get("table")
            column = order_col_spec.get("column")
            direction = order_col_spec.get("direction", "ASC")

            # Check if column is an alias (don't prefix with table)
            if column in aggregate_aliases:
                order_col = column
            else:
                # Check if it's an expression
                if is_sql_expression(column):
                    # Parse and rewrite the expression
                    logger.debug(f"Parsing complex expression in ORDER BY: {column}")
                    expr = parse_and_rewrite_expression(column, alias_map, db_context)
                    # Build ordered expression
                    ordered_expr = exp.Ordered(this=expr, desc=(direction == "DESC"))
                    query = query.order_by(ordered_expr)
                    continue
                else:
                    # Simple column reference
                    order_col = f"{table}.{column}"

            if direction == "DESC":
                query = query.order_by(f"{order_col} DESC")
            else:
                query = query.order_by(f"{order_col} ASC")
    else:
        # Fall back to state's sort_order (legacy behavior)
        sort_order = state.get("sort_order", "Default")
        if sort_order and sort_order != "Default":
            # Find first projection column for ordering
            first_col = None
            first_table = None

            if group_by_spec:
                # Order by first GROUP BY column
                group_by_columns = group_by_spec.get("group_by_columns", [])
                if group_by_columns:
                    first_col = group_by_columns[0].get("column")
                    first_table = group_by_columns[0].get("table")
            else:
                # Regular ORDER BY
                for table_selection in selections:
                    table_columns = table_selection.get("columns", [])
                    projection_cols = [
                        col for col in table_columns if col.get("role") == "projection"
                    ]
                    if projection_cols:
                        first_col = projection_cols[0].get("column")
                        first_table = table_selection.get("table")
                        break

            if first_col and first_table:
                order_col = f"{first_table}.{first_col}"
                if sort_order.lower() == "descending":
                    query = query.order_by(f"{order_col} DESC")
                else:
                    query = query.order_by(f"{order_col} ASC")

    # Apply LIMIT
    # Priority: 1) Plan's limit, 2) State's result_limit
    plan_limit = plan_dict.get("limit")
    result_limit = state.get("result_limit", 0)

    logger.debug(f"LIMIT DEBUG: plan_limit={plan_limit}, result_limit={result_limit}")
    logger.debug(f"LIMIT DEBUG: plan_dict keys: {list(plan_dict.keys())}")

    if plan_limit and plan_limit > 0:
        # Use plan's LIMIT specification
        logger.info(f"Using plan's LIMIT: {plan_limit}")
        query = query.limit(plan_limit)
    else:
        # Fall back to state's result_limit (legacy behavior)
        if result_limit and result_limit > 0:
            logger.info(f"Using state's result_limit: {result_limit}")
            query = query.limit(result_limit)
        else:
            logger.debug("No LIMIT applied")

    # Convert to SQL string
    dialect = db_context["dialect"]
    # Use identify=True to quote all identifiers (table/column names)
    # This prevents SQL Server reserved keyword errors (e.g., "Index" → "[Index]")
    sql_str = query.sql(dialect=dialect, pretty=True, identify=True)

    return sql_str


def format_filter_condition(
    table_alias: str,
    column: str,
    op: str,
    value,
    aggregate_aliases=None,
    db_context: Dict = None,
) -> str:
    """
    Format a filter condition as a SQL string with proper escaping.

    Note: This uses basic SQL escaping (single quote doubling).
    For production use, parameterized queries are preferred.

    Args:
        table_alias: Table name or alias
        column: Column name, expression, or aggregate alias
        op: Operator (=, >, <, etc.)
        value: Filter value
        aggregate_aliases: Set of aggregate alias names (for HAVING clauses)
        db_context: Optional database context for dialect-specific handling
    """
    # Unquote SQL functions if value is a quoted function expression
    # This fixes LLMs wrapping functions like 'DATEADD(...)' in quotes
    value = unquote_sql_functions(value)

    # Check if column is an expression or aggregate alias (don't prefix with table)
    if is_sql_expression(column):
        # Complex expression - use as-is
        col_ref = column
    elif aggregate_aliases and column in aggregate_aliases:
        # Aggregate alias - use as-is
        col_ref = column
    else:
        # Simple column - prefix with table
        col_ref = f"{table_alias}.{column}"

    def escape_string(s):
        """Escape single quotes in SQL strings by doubling them."""
        if s is None:
            return "NULL"
        return str(s).replace("'", "''")

    def format_value(v):
        """Format a value with proper type handling, including dates."""
        # Unquote SQL functions before type inference
        # This handles both single values and values in lists (IN, NOT IN, BETWEEN)
        v = unquote_sql_functions(v)

        # Check if value is a SQL expression (function call) after unquoting
        # If it was unquoted, it's now a raw SQL expression that should be used as-is
        if isinstance(v, str) and re.match(r'^[A-Z_][A-Z0-9_]*\s*\(.*\)$', v, re.IGNORECASE):
            # This is a SQL function expression - return as-is without quoting
            return v

        value_type = infer_value_type(v)

        if value_type == "null":
            return "NULL"
        elif value_type == "date":
            # ISO date format: YYYY-MM-DD
            # SQL Server: CAST('2025-10-31' AS DATE)
            # SQLite: '2025-10-31' (stores as text)
            is_sqlite = db_context and db_context.get("is_sqlite", False)
            if is_sqlite:
                return f"'{escape_string(v)}'"
            else:
                return f"CAST('{escape_string(v)}' AS DATE)"
        elif value_type == "datetime":
            # ISO datetime format: YYYY-MM-DD HH:MM:SS
            # SQL Server: CAST('2025-10-31 14:30:00' AS DATETIME)
            # SQLite: '2025-10-31 14:30:00' (stores as text)
            is_sqlite = db_context and db_context.get("is_sqlite", False)
            if is_sqlite:
                return f"'{escape_string(v)}'"
            else:
                return f"CAST('{escape_string(v)}' AS DATETIME)"
        elif value_type == "number" or value_type == "boolean":
            # Numeric and boolean values: no quotes
            if isinstance(v, bool):
                return "1" if v else "0"
            elif isinstance(v, str) and v in ("0", "1"):
                return v  # Keep as-is
            elif isinstance(v, str):
                try:
                    # Parse string to number
                    float(v)
                    return v
                except ValueError:
                    # If parsing fails, quote it as string
                    return f"'{escape_string(v)}'"
            else:
                return str(v)
        else:
            # String values: quoted
            return f"'{escape_string(v)}'"

    if op == "=":
        return f"{col_ref} = {format_value(value)}"
    elif op == "!=":
        return f"{col_ref} != {format_value(value)}"
    elif op == ">":
        return f"{col_ref} > {format_value(value)}"
    elif op == ">=":
        return f"{col_ref} >= {format_value(value)}"
    elif op == "<":
        return f"{col_ref} < {format_value(value)}"
    elif op == "<=":
        return f"{col_ref} <= {format_value(value)}"
    elif op == "between":
        if isinstance(value, list) and len(value) == 2:
            return f"{col_ref} BETWEEN {format_value(value[0])} AND {format_value(value[1])}"
    elif op == "in":
        if isinstance(value, list):
            # Handle IN with NULL: col IN (0, NULL) needs to become (col = 0 OR col IS NULL)
            has_null = any(
                v is None or (isinstance(v, str) and v.upper() == "NULL") for v in value
            )
            non_null_values = [
                v
                for v in value
                if v is not None and not (isinstance(v, str) and v.upper() == "NULL")
            ]

            if has_null and non_null_values:
                # Mixed: (col IN (values) OR col IS NULL)
                values_str = ", ".join([format_value(v) for v in non_null_values])
                return f"({col_ref} IN ({values_str}) OR {col_ref} IS NULL)"
            elif has_null and not non_null_values:
                # Only NULL: col IS NULL
                return f"{col_ref} IS NULL"
            else:
                # No NULL values: standard IN clause
                values_str = ", ".join([format_value(v) for v in value])
                return f"{col_ref} IN ({values_str})"
    elif op == "not_in":
        if isinstance(value, list):
            # Handle NOT IN with NULL: col NOT IN (0, NULL) needs special handling
            has_null = any(
                v is None or (isinstance(v, str) and v.upper() == "NULL") for v in value
            )
            non_null_values = [
                v
                for v in value
                if v is not None and not (isinstance(v, str) and v.upper() == "NULL")
            ]

            if has_null and non_null_values:
                # Mixed: (col NOT IN (values) AND col IS NOT NULL)
                values_str = ", ".join([format_value(v) for v in non_null_values])
                return f"({col_ref} NOT IN ({values_str}) AND {col_ref} IS NOT NULL)"
            elif has_null and not non_null_values:
                # Only NULL: col IS NOT NULL
                return f"{col_ref} IS NOT NULL"
            else:
                # No NULL values: standard NOT IN clause
                values_str = ", ".join([format_value(v) for v in value])
                return f"{col_ref} NOT IN ({values_str})"
    elif op == "like":
        return f"{col_ref} LIKE '{escape_string(value)}'"
    elif op == "ilike":
        # SQL Server doesn't support ILIKE - use LIKE instead (case-insensitive by default)
        return f"{col_ref} LIKE '{escape_string(value)}'"
    elif op == "starts_with":
        return f"{col_ref} LIKE '{escape_string(value)}%'"
    elif op == "ends_with":
        return f"{col_ref} LIKE '%{escape_string(value)}'"
    elif op == "is_null":
        return f"{col_ref} IS NULL"
    elif op == "is_not_null":
        return f"{col_ref} IS NOT NULL"

    # Fallback - use proper type handling
    return f"{col_ref} = {format_value(value)}"


def build_time_filter_condition(
    time_filter: str, selections: List[Dict], db_context: Dict
) -> str:
    """Build time filter condition as SQL string."""
    # Find timestamp column
    timestamp_columns = [
        "CreatedOn",
        "UpdatedOn",
        "Created",
        "Modified",
        "Timestamp",
        "Date",
    ]
    time_column = None
    time_table = None

    for table_selection in selections:
        table_columns = table_selection.get("columns", [])
        for col_info in table_columns:
            col_name = col_info.get("column")
            if col_name in timestamp_columns:
                time_column = col_name
                time_table = table_selection.get("table")
                break
        if time_column:
            break

    if not time_column or not time_table:
        return None

    # Calculate days
    days_map = {
        "Last 7 Days": 7,
        "Last 30 Days": 30,
        "Last 90 Days": 90,
        "Last 365 Days": 365,
    }

    days = days_map.get(time_filter)
    if not days:
        return None

    col_ref = f"{time_table}.{time_column}"

    if db_context["is_sqlite"]:
        return f"{col_ref} >= datetime('now', '-{days} days')"
    else:
        # SQL Server: DATEADD doesn't use quotes around date part
        return f"{col_ref} >= DATEADD(day, -{days}, GETDATE())"


def generate_query(state: State):
    """Generate SQL query deterministically from planner output using SQLGlot."""
    logger.info("Starting SQL query generation")

    try:
        planner_output = state["planner_output"]

        if not planner_output:
            logger.warning("No planner output available for query generation")
            return {
                **state,
                "messages": [AIMessage(content="Error: No planner output available")],
                "last_step": "generate_query",
            }

        # Parse planner output to dict
        plan_dict = parse_planner_output(planner_output)

        # Get database context
        db_context = get_database_context()

        # Build SQL query using SQLGlot with execution time tracking
        with log_execution_time(logger, "build_sql_query"):
            query = build_sql_query(plan_dict, state, db_context)

        # Debug: Save generated SQL
        from utils.debug_utils import save_debug_file, append_to_debug_array

        save_debug_file(
            "generated_sql.json",
            {"sql": query, "dialect": db_context.get("dialect", "unknown")},
            step_name="generate_query",
        )

        # Debug: Track SQL query in the queries array
        error_iteration = state.get("error_iteration", 0)
        refinement_iteration = state.get("refinement_iteration", 0)

        if error_iteration > 0:
            step_type = "error_correction_regenerated"
        elif refinement_iteration > 0:
            step_type = "refinement_regenerated"
        else:
            step_type = "initial_generation"

        append_to_debug_array(
            "generated_sql_queries.json",
            {
                "step": step_type,
                "sql": query,
                "error_iteration": error_iteration,
                "refinement_iteration": refinement_iteration,
                "status": "generated",
            },
            step_name="generate_query",
            array_key="queries",
        )

        logger.info(
            "SQL query generation completed",
            extra={"query_length": len(query), "database_type": db_context["type"]},
        )

        return {
            **state,
            "messages": [
                AIMessage(
                    content="Generated SQL query deterministically from execution plan"
                )
            ],
            "query": query,
            "last_step": "generate_query",
        }

    except Exception as e:
        logger.error(f"Error generating SQL query: {str(e)}", exc_info=True)

        return {
            **state,
            "messages": [AIMessage(content=f"Error generating query: {str(e)}")],
            "last_step": "generate_query",
        }
