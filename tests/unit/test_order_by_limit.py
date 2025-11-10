"""Tests for ORDER BY and LIMIT support in planner models and query generation."""

import os
from unittest.mock import patch
from agent.generate_query import build_sql_query, get_database_context


def test_plan_with_order_by_and_limit():
    """Test that plan's order_by and limit are used in generated SQL."""
    # Force SQL Server mode for consistent testing
    with patch.dict(os.environ, {"USE_TEST_DB": "false"}):
        plan_dict = {
            "selections": [
                {
                    "table": "tb_Logins",
                    "alias": None,
                    "columns": [
                        {"column": "ID", "role": "projection"},
                        {"column": "UserName", "role": "projection"},
                        {"column": "LoginDate", "role": "projection"},
                    ],
                    "filters": [],
                }
            ],
            "join_edges": [],
            "global_filters": [],
            "group_by": None,
            "window_functions": [],
            "subquery_filters": [],
            # ORDER BY and LIMIT from plan
            "order_by": [
                {"table": "tb_Logins", "column": "LoginDate", "direction": "DESC"}
            ],
            "limit": 10,
        }

        state = {
            "sort_order": "Default",  # Plan should override this
            "result_limit": 100,  # Plan should override this
            "time_filter": "All Time",
        }

        db_context = get_database_context()
        sql = build_sql_query(plan_dict, state, db_context)

        # Verify ORDER BY is present with DESC
        assert "ORDER BY" in sql.upper()
        assert "[LoginDate]" in sql
        assert "DESC" in sql.upper()

        # Verify TOP 10 is used (SQL Server syntax)
        assert "TOP 10" in sql.upper()

    print(f"Generated SQL:\n{sql}")


def test_plan_order_by_multiple_columns():
    """Test ORDER BY with multiple columns."""
    # Force SQL Server mode for consistent testing
    with patch.dict(os.environ, {"USE_TEST_DB": "false"}):
        plan_dict = {
            "selections": [
                {
                    "table": "tb_Customers",
                    "alias": None,
                    "columns": [
                        {"column": "ID", "role": "projection"},
                        {"column": "Name", "role": "projection"},
                        {"column": "Revenue", "role": "projection"},
                        {"column": "Country", "role": "projection"},
                    ],
                    "filters": [],
                }
            ],
            "join_edges": [],
            "global_filters": [],
            "group_by": None,
            "window_functions": [],
            "subquery_filters": [],
            "order_by": [
                {"table": "tb_Customers", "column": "Country", "direction": "ASC"},
                {"table": "tb_Customers", "column": "Revenue", "direction": "DESC"},
            ],
            "limit": 5,
        }

        state = {
            "sort_order": "Default",
            "result_limit": 0,
            "time_filter": "All Time",
        }

        db_context = get_database_context()
        sql = build_sql_query(plan_dict, state, db_context)

        # Verify both ORDER BY columns are present
        assert "ORDER BY" in sql.upper()
        assert "[Country]" in sql
        assert "[Revenue]" in sql

        # Extract the ORDER BY clause to check column order
        order_by_start = sql.upper().find("ORDER BY")
        order_by_clause = sql[order_by_start:]

        # Country should come before Revenue in the ORDER BY clause
        country_pos = order_by_clause.upper().find("[COUNTRY]")
        revenue_pos = order_by_clause.upper().find("[REVENUE]")
        assert country_pos < revenue_pos, "Country should come before Revenue in ORDER BY clause"

        print(f"Generated SQL:\n{sql}")


def test_fallback_to_state_when_no_plan_order_by():
    """Test that state's sort_order and result_limit are used when plan doesn't specify."""
    plan_dict = {
        "selections": [
            {
                "table": "tb_Products",
                "alias": None,
                "columns": [
                    {"column": "ID", "role": "projection"},
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
        # No order_by or limit in plan
        "order_by": [],
        "limit": None,
    }

    state = {
        "sort_order": "Descending",
        "result_limit": 25,
        "time_filter": "All Time",
    }

    db_context = get_database_context()
    sql = build_sql_query(plan_dict, state, db_context)

    # Should use state's sort_order (Descending on first projection column)
    assert "ORDER BY" in sql.upper()
    assert "DESC" in sql.upper()

    # Should use state's result_limit (25)
    assert "LIMIT 25" in sql.upper() or "TOP 25" in sql.upper()

    print(f"Generated SQL:\n{sql}")


def test_plan_limit_without_order_by():
    """Test that plan's limit can be used even without order_by."""
    plan_dict = {
        "selections": [
            {
                "table": "tb_Events",
                "alias": None,
                "columns": [
                    {"column": "ID", "role": "projection"},
                    {"column": "EventName", "role": "projection"},
                ],
                "filters": [],
            }
        ],
        "join_edges": [],
        "global_filters": [],
        "group_by": None,
        "window_functions": [],
        "subquery_filters": [],
        "order_by": [],
        "limit": 50,
    }

    state = {
        "sort_order": "Default",
        "result_limit": 0,
        "time_filter": "All Time",
    }

    db_context = get_database_context()
    sql = build_sql_query(plan_dict, state, db_context)

    # Should have LIMIT from plan
    assert "LIMIT 50" in sql.upper() or "TOP 50" in sql.upper()

    print(f"Generated SQL:\n{sql}")


def test_asc_direction():
    """Test ORDER BY with ASC direction (for 'first N' queries)."""
    # Force SQL Server mode for consistent testing
    with patch.dict(os.environ, {"USE_TEST_DB": "false"}):
        plan_dict = {
            "selections": [
                {
                    "table": "tb_Entries",
                    "alias": None,
                    "columns": [
                        {"column": "ID", "role": "projection"},
                        {"column": "CreatedOn", "role": "projection"},
                    ],
                    "filters": [],
                }
            ],
            "join_edges": [],
            "global_filters": [],
            "group_by": None,
            "window_functions": [],
            "subquery_filters": [],
            "order_by": [
                {"table": "tb_Entries", "column": "CreatedOn", "direction": "ASC"}
            ],
            "limit": 3,
        }

        state = {
            "sort_order": "Default",
            "result_limit": 0,
            "time_filter": "All Time",
        }

        db_context = get_database_context()
        sql = build_sql_query(plan_dict, state, db_context)

        # Verify ASC direction
        assert "ORDER BY" in sql.upper()
        assert "[CreatedOn]" in sql
        assert "ASC" in sql.upper()
        assert "TOP 3" in sql.upper()

        print(f"Generated SQL:\n{sql}")


if __name__ == "__main__":
    test_plan_with_order_by_and_limit()
    test_plan_order_by_multiple_columns()
    test_fallback_to_state_when_no_plan_order_by()
    test_plan_limit_without_order_by()
    test_asc_direction()
    print("\n✅ All ORDER BY and LIMIT tests passed!")
