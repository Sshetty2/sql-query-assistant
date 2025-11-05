"""Audit and validate query plans before SQL generation."""

from langchain_core.messages import AIMessage
from utils.logger import get_logger
from utils.stream_utils import emit_node_status
from utils.debug_utils import save_debug_file
from agent.state import State

logger = get_logger()


def filter_schema_to_plan_tables(
    plan_dict: dict, full_schema: list[dict]
) -> list[dict]:
    """
    Filter schema to only include tables referenced in the plan.

    This dramatically reduces the schema size for LLM audit.

    Args:
        plan_dict: The planner output dictionary
        full_schema: The complete schema (filtered_schema from state)

    Returns:
        Filtered schema containing only tables used in the plan
    """
    # Collect all table names from the plan
    table_names = set()

    # From selections
    for selection in plan_dict.get("selections", []):
        table_names.add(selection.get("table"))

    # From join_edges
    for edge in plan_dict.get("join_edges", []):
        table_names.add(edge.get("from_table"))
        table_names.add(edge.get("to_table"))

    # Filter schema
    filtered = [
        table_schema
        for table_schema in full_schema
        if table_schema.get("table_name") in table_names
    ]

    logger.debug(
        f"Filtered schema from {len(full_schema)} to {len(filtered)} tables",
        extra={"plan_tables": list(table_names)},
    )

    return filtered


def validate_column_exists(
    table_name: str, column_name: str, schema: list[dict]
) -> bool:
    """Check if a column exists in a table."""
    for table_schema in schema:
        if table_schema.get("table_name") == table_name:
            columns = [
                col.get("column_name") for col in table_schema.get("columns", [])
            ]
            return column_name in columns
    return False


def validate_table_exists(table_name: str, schema: list[dict]) -> bool:
    """Check if a table exists in schema."""
    return any(table.get("table_name") == table_name for table in schema)


def validate_selections(plan_dict: dict, schema: list[dict]) -> list[str]:
    """
    Validate that all selections reference existing tables and columns.

    Returns:
        List of validation issues
    """
    issues = []

    for selection in plan_dict.get("selections", []):
        table_name = selection.get("table")

        # FIRST: Validate table exists in schema
        if not validate_table_exists(table_name, schema):
            issues.append(
                f"Table '{table_name}' does not exist in schema. "
                f"Remove this table from the plan or check schema for correct table name."
            )
            continue  # Skip column validation for non-existent tables

        columns = selection.get("columns", [])

        for col_info in columns:
            column = col_info.get("column")
            col_table = col_info.get(
                "table", table_name
            )  # Should match selection table

            # Verify column exists
            if not validate_column_exists(col_table, column, schema):
                issues.append(
                    f"Column '{column}' does not exist in table '{col_table}'. "
                    f"Check schema for correct column name."
                )

    return issues


def validate_join_edges(plan_dict: dict, schema: list[dict]) -> list[str]:
    """
    Validate that all join columns exist in their respective tables.

    Returns:
        List of validation issues
    """
    issues = []

    for edge in plan_dict.get("join_edges", []):
        from_table = edge.get("from_table")
        from_column = edge.get("from_column")
        to_table = edge.get("to_table")
        to_column = edge.get("to_column")

        # FIRST: Validate tables exist in schema
        if not validate_table_exists(from_table, schema):
            issues.append(
                f"JOIN from_table '{from_table}' does not exist in schema. "
                f"Remove this join or check schema for correct table name."
            )
            continue  # Skip column validation for non-existent table

        if not validate_table_exists(to_table, schema):
            issues.append(
                f"JOIN to_table '{to_table}' does not exist in schema. "
                f"Remove this join or check schema for correct table name."
            )
            continue  # Skip column validation for non-existent table

        # Validate from_column exists
        if not validate_column_exists(from_table, from_column, schema):
            issues.append(
                f"JOIN column '{from_column}' does not exist in table '{from_table}'. "
                f"Common issue: Foreign key names may differ from primary keys (e.g., TagID → ID)."
            )

        # Validate to_column exists
        if not validate_column_exists(to_table, to_column, schema):
            issues.append(
                f"JOIN column '{to_column}' does not exist in table '{to_table}'. "
                f"Common issue: Foreign key names may differ from primary keys (e.g., TagID → ID)."
            )

    return issues


def validate_filters(plan_dict: dict, schema: list[dict]) -> list[str]:
    """
    Validate that filter columns exist in their tables.

    Returns:
        List of validation issues
    """
    issues = []

    # Check table-level filters
    for selection in plan_dict.get("selections", []):
        filters = selection.get("filters", [])

        for filter_pred in filters:
            filter_table = filter_pred.get("table")
            filter_column = filter_pred.get("column")

            # Validate table exists first
            if not validate_table_exists(filter_table, schema):
                issues.append(
                    f"Filter table '{filter_table}' does not exist in schema. "
                    f"Remove this filter or check schema for correct table name."
                )
                continue

            if not validate_column_exists(filter_table, filter_column, schema):
                issues.append(
                    f"Filter column '{filter_column}' does not exist in table '{filter_table}'."
                )

    # Check global filters
    for filter_pred in plan_dict.get("global_filters", []):
        filter_table = filter_pred.get("table")
        filter_column = filter_pred.get("column")

        # Validate table exists first
        if not validate_table_exists(filter_table, schema):
            issues.append(
                f"Global filter table '{filter_table}' does not exist in schema. "
                f"Remove this filter or check schema for correct table name."
            )
            continue

        if not validate_column_exists(filter_table, filter_column, schema):
            issues.append(
                f"Global filter column '{filter_column}' does not exist in table '{filter_table}'."
            )

    # Check HAVING filters
    group_by = plan_dict.get("group_by")
    if group_by:
        for having_filter in group_by.get("having_filters", []):
            having_table = having_filter.get("table")
            having_column = having_filter.get("column")

            # Validate table exists first
            if not validate_table_exists(having_table, schema):
                issues.append(
                    f"HAVING filter table '{having_table}' does not exist in schema. "
                    f"Remove this filter or check schema for correct table name."
                )
                continue

            if not validate_column_exists(having_table, having_column, schema):
                issues.append(
                    f"HAVING filter column '{having_column}' does not exist in table '{having_table}'. "
                    f"Common issue: Column may be in a different joined table."
                )

    return issues


def validate_group_by(plan_dict: dict, schema: list[dict]) -> list[str]:
    """
    Validate that GROUP BY columns exist.

    Returns:
        List of validation issues
    """
    issues = []

    group_by = plan_dict.get("group_by")
    if not group_by:
        return issues

    for col_info in group_by.get("group_by_columns", []):
        table = col_info.get("table")
        column = col_info.get("column")

        if not validate_column_exists(table, column, schema):
            issues.append(
                f"GROUP BY column '{column}' does not exist in table '{table}'."
            )

    return issues


def fix_group_by_completeness(plan_dict: dict) -> dict:
    """
    Automatically fix GROUP BY completeness by adding missing projection columns.

    This is a deterministic fix - when aggregations are present, all projection
    columns must be in GROUP BY. This is a SQL requirement, not a preference.

    Args:
        plan_dict: The planner output dictionary

    Returns:
        Modified plan_dict with complete GROUP BY
    """
    group_by = plan_dict.get("group_by")

    # Only fix if we have aggregations
    if not group_by or not group_by.get("aggregates"):
        return plan_dict

    # Collect all projection columns
    projection_cols = []
    for selection in plan_dict.get("selections", []):
        # Skip tables marked as join-only
        if selection.get("include_only_for_join"):
            continue

        for col in selection.get("columns", []):
            if col.get("role") == "projection":
                projection_cols.append({"table": col["table"], "column": col["column"]})

    # Get existing GROUP BY columns
    existing_group_by = group_by.get("group_by_columns", [])
    existing_set = {(col["table"], col["column"]) for col in existing_group_by}

    # Add missing projection columns
    for proj_col in projection_cols:
        key = (proj_col["table"], proj_col["column"])
        if key not in existing_set:
            existing_group_by.append(proj_col)
            logger.debug(
                f"Auto-added {proj_col['table']}.{proj_col['column']} to GROUP BY",
                extra={"column": proj_col},
            )

    # Update plan
    group_by["group_by_columns"] = existing_group_by
    plan_dict["group_by"] = group_by

    return plan_dict


def fix_having_filters(plan_dict: dict) -> dict:
    """
    Fix HAVING filters that reference non-aggregated columns not in GROUP BY.

    HAVING clause can only reference:
    1. Columns in GROUP BY
    2. Aggregate functions

    Non-aggregated columns should be in WHERE clause instead.

    Args:
        plan_dict: The planner output dictionary

    Returns:
        Modified plan_dict with corrected filters
    """
    group_by = plan_dict.get("group_by")

    # Only process if we have GROUP BY with HAVING filters
    if not group_by or not group_by.get("having_filters"):
        return plan_dict

    # Get columns in GROUP BY
    group_by_cols = set()
    for col in group_by.get("group_by_columns", []):
        group_by_cols.add((col["table"], col["column"]))

    # Get aggregated columns
    aggregated_cols = set()
    for agg in group_by.get("aggregates", []):
        if agg.get("column"):  # COUNT(*) has None
            aggregated_cols.add((agg["table"], agg["column"]))

    # Check each HAVING filter
    having_filters = group_by.get("having_filters", [])
    valid_having = []
    moved_to_where = []

    for filter_pred in having_filters:
        filter_table = filter_pred.get("table")
        filter_column = filter_pred.get("column")
        filter_key = (filter_table, filter_column)

        # Check if this filter references a GROUP BY column or aggregate
        if filter_key in group_by_cols or filter_key in aggregated_cols:
            # Valid HAVING filter
            valid_having.append(filter_pred)
        else:
            # Invalid - move to WHERE (global_filters)
            moved_to_where.append(filter_pred)
            logger.info(
                f"Moved HAVING filter to WHERE: {filter_table}.{filter_column} "
                f"(not in GROUP BY or aggregate)",
                extra={"filter": filter_pred},
            )

    # Update plan
    if moved_to_where:
        # Move invalid HAVING filters to global_filters
        plan_dict.setdefault("global_filters", []).extend(moved_to_where)
        group_by["having_filters"] = valid_having
        plan_dict["group_by"] = group_by

    return plan_dict


def validate_table_references(plan_dict: dict) -> list[str]:
    """
    Validate that all tables referenced in the plan are included in selections.

    This detects cases where filters, order_by, aggregations, etc. reference
    tables that aren't in the FROM clause, which causes SQL errors like:
    "The multi-part identifier 'tb_Table.Column' could not be bound"

    Args:
        plan_dict: The planner output dictionary

    Returns:
        List of validation issues for missing table references
    """
    issues = []

    # Get all selected tables
    selected_tables = {sel.get("table") for sel in plan_dict.get("selections", [])}

    # Track all tables referenced in various parts of the plan
    referenced_tables = set()

    # Check filters (both table-level and global)
    for selection in plan_dict.get("selections", []):
        for filter_pred in selection.get("filters", []):
            table = filter_pred.get("table")
            if table:
                referenced_tables.add(table)

    for filter_pred in plan_dict.get("global_filters", []):
        table = filter_pred.get("table")
        if table:
            referenced_tables.add(table)

    # Check ORDER BY
    for order_by in plan_dict.get("order_by", []):
        table = order_by.get("table")
        if table:
            referenced_tables.add(table)

    # Check GROUP BY
    group_by = plan_dict.get("group_by")
    if group_by:
        # Check group_by_columns
        for col in group_by.get("group_by_columns", []):
            table = col.get("table")
            if table:
                referenced_tables.add(table)

        # Check aggregates
        for agg in group_by.get("aggregates", []):
            table = agg.get("table")
            if table:
                referenced_tables.add(table)

        # Check HAVING filters
        for having_filter in group_by.get("having_filters", []):
            table = having_filter.get("table")
            if table:
                referenced_tables.add(table)

    # Check window functions (if they exist in full planner output)
    for window_func in plan_dict.get("window_functions", []):
        table = window_func.get("table")
        if table:
            referenced_tables.add(table)

    # Check subquery filters (if they exist)
    for subquery_filter in plan_dict.get("subquery_filters", []):
        outer_table = subquery_filter.get("outer_table")
        subquery_table = subquery_filter.get("subquery_table")
        if outer_table:
            referenced_tables.add(outer_table)
        if subquery_table:
            referenced_tables.add(subquery_table)

    # Find missing tables
    missing_tables = referenced_tables - selected_tables

    if missing_tables:
        for table in sorted(missing_tables):
            issues.append(
                f"Table '{table}' is referenced in filters/order_by/aggregations "
                f"but not included in selections. This will cause SQL error: "
                f"'The multi-part identifier could not be bound'. "
                f"Add '{table}' to selections or remove references to it."
            )
            logger.warning(
                f"Missing table reference detected: {table}",
                extra={
                    "missing_table": table,
                    "selected_tables": list(selected_tables),
                    "referenced_tables": list(referenced_tables),
                },
            )

    return issues


def validate_table_connectivity(plan_dict: dict) -> list[str]:
    """
    Validate that all tables in selections are connected via join edges.

    This detects "orphaned" tables that are in selections but have no join
    path connecting them to the rest of the query. This causes SQL to create
    a CROSS JOIN (Cartesian product), which is almost never intended and leads
    to incorrect results or query errors.

    Example of disconnected table issue:
    - Selections: [tb_Company, tb_CVE, tb_SaasComputers]
    - Join edges: [tb_Company <-> tb_SaasComputers]
    - Problem: tb_CVE has no join connecting it! This creates CROSS JOIN.

    Args:
        plan_dict: The planner output dictionary

    Returns:
        List of validation issues for disconnected tables
    """
    issues = []

    # Get all tables from selections
    selected_tables = {sel.get("table") for sel in plan_dict.get("selections", [])}

    # If only one table, no joins needed
    if len(selected_tables) <= 1:
        return issues

    # Get join edges
    join_edges = plan_dict.get("join_edges", [])

    # If multiple tables but no joins, all tables are disconnected
    if len(selected_tables) > 1 and not join_edges:
        issues.append(
            f"Multiple tables in selections ({', '.join(sorted(selected_tables))}) "
            f"but no join edges defined. This will create a CROSS JOIN (Cartesian product). "
            f"Add join edges to connect these tables."
        )
        logger.warning(
            "No join edges found for multi-table query",
            extra={"selected_tables": list(selected_tables)},
        )
        return issues

    # Build adjacency graph from join edges
    # Each table tracks which other tables it's connected to
    adjacency = {table: set() for table in selected_tables}

    for edge in join_edges:
        from_table = edge.get("from_table")
        to_table = edge.get("to_table")

        # Only track joins between selected tables
        if from_table in selected_tables and to_table in selected_tables:
            adjacency[from_table].add(to_table)
            adjacency[to_table].add(from_table)  # Bidirectional

    # Find connected components using DFS
    # Start from the first table and see which tables we can reach
    visited = set()
    start_table = next(iter(selected_tables))  # Pick first table as starting point

    # DFS to find all reachable tables
    def dfs(table):
        if table in visited:
            return
        visited.add(table)
        for neighbor in adjacency[table]:
            dfs(neighbor)

    dfs(start_table)

    # Find disconnected tables (not reachable from start_table)
    disconnected = selected_tables - visited

    if disconnected:
        for table in sorted(disconnected):
            issues.append(
                f"Table '{table}' is in selections but has no join edges connecting it "
                f"to the rest of the query. This will cause a CROSS JOIN (Cartesian product). "
                f"Either add a join edge from '{table}' to another table, or remove '{table}' "
                f"from selections if it's not needed."
            )
            logger.warning(
                f"Disconnected table detected: {table}",
                extra={
                    "disconnected_table": table,
                    "connected_tables": list(visited),
                    "all_selected_tables": list(selected_tables),
                    "adjacency_graph": {k: list(v) for k, v in adjacency.items()},
                },
            )

    return issues


def classify_issue_severity(issue: str) -> str:
    """
    Classify validation issues as 'critical' or 'non-critical'.

    Critical issues are those that will ALWAYS cause SQL errors and cannot be
    recovered from (e.g., hallucinated tables, invalid join columns).
    Non-critical issues might be fixable by SQL execution errors or refinement.

    Args:
        issue: The validation issue text

    Returns:
        'critical' or 'non-critical'
    """
    # Critical: Table doesn't exist in schema (hallucination)
    if "does not exist in schema" in issue.lower():
        return "critical"

    # Critical: JOIN column doesn't exist (will cause immediate SQL error)
    if "join column" in issue.lower() and "does not exist" in issue.lower():
        return "critical"

    # Non-critical: Everything else (column issues, connectivity, etc.)
    return "non-critical"


def run_deterministic_checks(
    plan_dict: dict, schema: list[dict]
) -> tuple[list[str], list[str]]:
    """
    Run all deterministic validation checks.

    Returns:
        Tuple of (critical_issues, non_critical_issues)
    """
    all_issues = []

    # Run all validation checks
    all_issues.extend(validate_selections(plan_dict, schema))
    all_issues.extend(validate_join_edges(plan_dict, schema))
    all_issues.extend(validate_filters(plan_dict, schema))
    all_issues.extend(validate_group_by(plan_dict, schema))
    all_issues.extend(validate_table_references(plan_dict))
    all_issues.extend(
        validate_table_connectivity(plan_dict)
    )  # Detect disconnected tables

    # Classify issues by severity
    critical_issues = [
        issue for issue in all_issues if classify_issue_severity(issue) == "critical"
    ]
    non_critical_issues = [
        issue
        for issue in all_issues
        if classify_issue_severity(issue) == "non-critical"
    ]

    return critical_issues, non_critical_issues


def generate_audit_feedback(
    issues: list[str], plan_dict: dict, schema: list[dict]
) -> str:
    """
    Generate concise feedback for pre-planner about validation issues.

    Instead of correcting the plan directly, we generate natural language feedback
    that the pre-planner can use to regenerate a better strategy.

    Args:
        issues: List of validation issues detected
        plan_dict: The planner output dictionary
        schema: Filtered schema for the plan

    Returns:
        Concise feedback text describing what went wrong and what to fix
    """
    # Group issues by type for clearer feedback
    column_issues = [i for i in issues if "does not exist" in i or "Column" in i]
    join_issues = [i for i in issues if "JOIN" in i or "join" in i]
    disconnect_issues = [i for i in issues if "disconnected" in i or "CROSS JOIN" in i]
    reference_issues = [i for i in issues if "referenced" in i and "not included" in i]
    group_by_issues = [i for i in issues if "GROUP BY" in i]

    feedback_parts = []

    if column_issues:
        feedback_parts.append(
            "**Column Validation Errors:**\n"
            + "\n".join(f"- {issue}" for issue in column_issues)
        )

    if disconnect_issues:
        feedback_parts.append(
            "**Table Connectivity Errors:**\n"
            + "\n".join(f"- {issue}" for issue in disconnect_issues)
        )
        feedback_parts.append(
            "\n**Fix**: Check schema foreign_keys to find how to join disconnected tables."
        )

    if join_issues:
        feedback_parts.append(
            "**Join Errors:**\n" + "\n".join(f"- {issue}" for issue in join_issues)
        )

    if reference_issues:
        feedback_parts.append(
            "**Table Reference Errors:**\n"
            + "\n".join(f"- {issue}" for issue in reference_issues)
        )

    if group_by_issues:
        feedback_parts.append(
            "**GROUP BY Errors:**\n"
            + "\n".join(f"- {issue}" for issue in group_by_issues)
        )

    # Add guidance on how to fix
    feedback_parts.append(
        "\n**How to Fix:**\n"
        "1. Review the schema carefully - use EXACT column names (case-sensitive)\n"
        "2. For disconnected tables: Add join edges using foreign_keys from schema\n"
        "3. For wrong columns: Check which table actually contains the column\n"
        "4. For join errors: Foreign keys often join to primary keys with different names"
    )

    return "\n\n".join(feedback_parts)


def plan_audit(state: State):
    """
    Audit the query plan and fix any column/table mismatches.

    Runs deterministic checks first. If validation issues are found, generates
    feedback for pre-planner to regenerate strategy instead of directly patching JSON.
    """
    emit_node_status("plan_audit", "running", "Validating query plan")

    logger.info("Starting plan audit")

    planner_output = state.get("planner_output")
    if not planner_output:
        logger.warning("No planner output to audit")
        return {
            **state,
            "audit_passed": True,
            "audit_issues": [],
            "last_step": "plan_audit",
        }

    # Convert to dict if Pydantic model
    if hasattr(planner_output, "model_dump"):
        plan_dict = planner_output.model_dump()
    else:
        plan_dict = planner_output

    # Skip audit if plan was terminated
    if plan_dict.get("decision") == "terminate":
        logger.info("Plan decision is 'terminate', skipping audit")
        return {
            **state,
            "audit_passed": True,
            "audit_issues": [],
            "last_step": "plan_audit",
        }

    # Get filtered schema (prefer filtered_schema, fallback to full schema)
    full_schema = state.get("filtered_schema") or state.get("schema", [])

    # Filter schema to only plan-relevant tables (reduces LLM context)
    plan_schema = filter_schema_to_plan_tables(plan_dict, full_schema)

    # Deterministically fix common SQL issues
    # These are mechanical fixes that don't require LLM intelligence
    plan_dict = fix_group_by_completeness(plan_dict)
    plan_dict = fix_having_filters(plan_dict)  # Move invalid HAVING filters to WHERE

    # Fix invalid column names (CompanyName → Name, etc.)
    from agent.fix_invalid_columns import fix_plan_columns

    plan_dict, column_fixes = fix_plan_columns(plan_dict, plan_schema)

    if column_fixes:
        logger.info(
            f"Applied {len(column_fixes)} deterministic column name fixes",
            extra={"fixes": column_fixes},
        )

    # Run deterministic checks AFTER fixes
    critical_issues, non_critical_issues = run_deterministic_checks(
        plan_dict, plan_schema
    )
    all_issues = critical_issues + non_critical_issues

    if not all_issues:
        # No issues found - plan is valid (may have fixes applied)
        logger.info("Plan audit passed - no issues detected")
        return {
            **state,
            "messages": [AIMessage(content="Plan audit passed")],
            "planner_output": plan_dict,  # Return plan with fixes applied
            "audit_passed": True,
            "audit_issues": [],
            "audit_corrections": column_fixes,  # Track what was fixed
            "last_step": "plan_audit",
        }

    # CRITICAL ISSUES: Block execution immediately
    if critical_issues:
        logger.error(
            f"Plan audit found {len(critical_issues)} CRITICAL issues - terminating execution",
            extra={"critical_issues": critical_issues},
        )

        # Format critical issues for user
        critical_msg = "\n".join([f"• {issue}" for issue in critical_issues])

        # Note: Critical errors continue to check_clarification where the planner's
        # "decision" field should be "terminate".
        return {
            **state,
            "messages": [
                AIMessage(
                    content=f"Query plan validation failed with critical errors:\n\n{critical_msg}\n\n"
                    f"These are hallucinated tables that do not exist in the database schema. "
                    f"The query cannot be executed."
                )
            ],
            "planner_output": plan_dict,
            "audit_passed": False,
            "audit_issues": all_issues,
            "audit_corrections": column_fixes,
            "last_step": "plan_audit",
        }

    # Non-critical issues only - log them but continue execution (audit feedback loop DISABLED)
    logger.warning(
        f"Plan audit found {len(non_critical_issues)} non-critical issues but continuing to execution",
        extra={"non_critical_issues": non_critical_issues},
    )

    # NOTE: Audit feedback loop is DISABLED. The audit validates and applies deterministic
    # fixes (GROUP BY, HAVING, etc.) but doesn't block execution or generate feedback.
    # This allows:
    # 1. Planner.py auto-fix logic to handle corrections
    # 2. Real SQL execution errors to trigger error_feedback (more valuable)
    # 3. Empty results to trigger refinement_feedback
    #
    # Audit feedback can be re-enabled later by uncommenting the code below.

    # DISABLED: Generate feedback and route back to pre-planner
    # audit_iteration = state.get("audit_iteration", 0)
    # if audit_iteration >= 2:
    #     return {...}  # Would stop iteration after max attempts
    # feedback = generate_audit_feedback(issues, plan_dict, plan_schema)
    # return {..., "audit_feedback": feedback, ...}

    # Continue to execution despite audit issues
    logger.info(
        "Continuing to check_clarification despite audit issues (feedback disabled)"
    )

    # Debug: Save audit issues for inspection
    save_debug_file(
        "audit_issues.json",
        {
            "critical_issues": critical_issues,
            "non_critical_issues": non_critical_issues,
            "all_issues": all_issues,
            "plan": plan_dict,
            "column_fixes_applied": column_fixes,
        },
        step_name="plan_audit",
    )

    # Return plan with deterministic fixes applied, but don't block execution for non-critical issues
    msg = (
        f"Plan audit found {len(non_critical_issues)} non-critical issues "
        f"but continuing to execution"
    )
    emit_node_status("plan_audit", "completed")

    return {
        **state,
        "messages": [AIMessage(content=msg)],
        "planner_output": plan_dict,  # Return plan with fixes applied
        "audit_passed": False,  # Mark as not passed, but don't block
        "audit_issues": all_issues,  # Track all issues for debugging
        "audit_corrections": column_fixes,  # Track what was fixed
        "last_step": "plan_audit",
    }
