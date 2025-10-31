"""Tests for SQL Server reserved keyword handling in query generation."""

from agent.generate_query import build_sql_query, get_database_context


def test_reserved_keyword_index_is_quoted():
    """Test that reserved keyword 'Index' is properly quoted in SQL Server."""
    # Planner output with reserved keyword "Index"
    plan_dict = {
        "selections": [
            {
                "table": "tb_SaasComputerDiskDriveDetails",
                "alias": None,
                "columns": [
                    {"column": "ID", "role": "projection"},
                    {"column": "Index", "role": "projection"},  # Reserved keyword
                    {"column": "Name", "role": "projection"},
                ],
                "filters": [],
            }
        ],
        "join_edges": [],
        "global_filters": [],
        "group_by": None,
        "window_functions": [],
        "subquery_filters": [],
    }

    # Mock state
    state = {
        "sort_order": "Default",
        "result_limit": 100,
        "time_filter": "All Time",
    }

    # Get SQL Server context
    db_context = get_database_context()

    # Generate query
    sql = build_sql_query(plan_dict, state, db_context)

    # Verify that "Index" is quoted with square brackets
    assert "[Index]" in sql, f"Reserved keyword 'Index' should be quoted. SQL: {sql}"

    # Verify other columns are also quoted (identify=True quotes all identifiers)
    assert "[ID]" in sql
    assert "[Name]" in sql

    print(f"Generated SQL:\n{sql}")


def test_multiple_reserved_keywords():
    """Test that multiple reserved keywords are properly quoted."""
    plan_dict = {
        "selections": [
            {
                "table": "TestTable",
                "alias": None,
                "columns": [
                    {"column": "Index", "role": "projection"},     # Reserved
                    {"column": "Order", "role": "projection"},     # Reserved
                    {"column": "Key", "role": "projection"},       # Reserved
                    {"column": "Table", "role": "projection"},     # Reserved
                    {"column": "RegularColumn", "role": "projection"},  # Not reserved
                ],
                "filters": [],
            }
        ],
        "join_edges": [],
        "global_filters": [],
        "group_by": None,
        "window_functions": [],
        "subquery_filters": [],
    }

    state = {
        "sort_order": "Default",
        "result_limit": 100,
        "time_filter": "All Time",
    }

    db_context = get_database_context()
    sql = build_sql_query(plan_dict, state, db_context)

    # All reserved keywords should be quoted
    assert "[Index]" in sql
    assert "[Order]" in sql
    assert "[Key]" in sql
    assert "[Table]" in sql
    assert "[RegularColumn]" in sql  # All columns are quoted with identify=True

    print(f"Generated SQL:\n{sql}")


def test_reserved_keyword_in_filter():
    """Test that reserved keywords in WHERE clauses are properly quoted."""
    plan_dict = {
        "selections": [
            {
                "table": "tb_Test",
                "alias": None,
                "columns": [
                    {"column": "ID", "role": "projection"},
                    {"column": "Index", "role": "filter"},  # Reserved keyword in filter
                ],
                "filters": [
                    {"table": "tb_Test", "column": "Index", "op": "=", "value": "1"}
                ],
            }
        ],
        "join_edges": [],
        "global_filters": [],
        "group_by": None,
        "window_functions": [],
        "subquery_filters": [],
    }

    state = {
        "sort_order": "Default",
        "result_limit": 100,
        "time_filter": "All Time",
    }

    db_context = get_database_context()
    sql = build_sql_query(plan_dict, state, db_context)

    # Reserved keyword in WHERE clause should be quoted
    assert "[Index]" in sql
    assert "WHERE" in sql.upper()

    print(f"Generated SQL:\n{sql}")


if __name__ == "__main__":
    test_reserved_keyword_index_is_quoted()
    test_multiple_reserved_keywords()
    test_reserved_keyword_in_filter()
    print("\n✅ All reserved keyword tests passed!")
