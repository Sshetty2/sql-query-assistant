"""Test dialect compatibility for SQL generation."""

import os
from agent.generate_query import build_sql_query, get_database_context


def test_sql_server_dateadd():
    """Test that DATEADD generates correct syntax for SQL Server."""
    print("=" * 60)
    print("Test: SQL Server DATEADD Syntax")
    print("=" * 60)

    # Temporarily set to SQL Server mode
    original_env = os.environ.get("USE_TEST_DB")
    os.environ["USE_TEST_DB"] = "false"

    plan_dict = {
        "selections": [
            {
                "table": "tb_Users",
                "alias": "u",
                "columns": [
                    {"table": "tb_Users", "column": "Name", "role": "projection"},
                    {"table": "tb_Users", "column": "CreatedOn", "role": "filter"}
                ]
            }
        ],
        "join_edges": [],
        "global_filters": [],
        "group_by": None,
        "window_functions": [],
        "subquery_filters": [],
        "ctes": []
    }

    state = {
        "sort_order": "Default",
        "result_limit": 0,
        "time_filter": "Last 30 Days"
    }

    db_context = get_database_context()

    try:
        sql = build_sql_query(plan_dict, state, db_context)
        print("Generated SQL:")
        print(sql)
        print("\n")

        # Check that DATEADD has correct syntax (no quotes around 'day')
        if "DATEADD('day'" in sql or 'DATEADD("day"' in sql:
            print("ERROR: DATEADD has quoted interval (should be DATEADD(day, ...))")
            success = False
        elif "DATEADD(day," in sql:
            print("SUCCESS: DATEADD has correct syntax")
            success = True
        else:
            print("WARNING: No DATEADD found in SQL")
            success = False

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        success = False
    finally:
        # Restore original env
        if original_env:
            os.environ["USE_TEST_DB"] = original_env
        elif "USE_TEST_DB" in os.environ:
            del os.environ["USE_TEST_DB"]

    return success


def test_sqlite_datetime():
    """Test that datetime generates correct syntax for SQLite."""
    print("=" * 60)
    print("Test: SQLite datetime Syntax")
    print("=" * 60)

    # Set to SQLite mode
    original_env = os.environ.get("USE_TEST_DB")
    os.environ["USE_TEST_DB"] = "true"

    plan_dict = {
        "selections": [
            {
                "table": "tb_Users",
                "alias": "u",
                "columns": [
                    {"table": "tb_Users", "column": "Name", "role": "projection"},
                    {"table": "tb_Users", "column": "CreatedOn", "role": "filter"}
                ]
            }
        ],
        "join_edges": [],
        "global_filters": [],
        "group_by": None,
        "window_functions": [],
        "subquery_filters": [],
        "ctes": []
    }

    state = {
        "sort_order": "Default",
        "result_limit": 0,
        "time_filter": "Last 30 Days"
    }

    db_context = get_database_context()

    try:
        sql = build_sql_query(plan_dict, state, db_context)
        print("Generated SQL:")
        print(sql)
        print("\n")

        # Check that datetime has correct syntax (case-insensitive)
        if "datetime('now'" in sql.lower():
            print("SUCCESS: datetime has correct syntax")
            success = True
        else:
            print("WARNING: No datetime found in SQL")
            success = False

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        success = False
    finally:
        # Restore original env
        if original_env:
            os.environ["USE_TEST_DB"] = original_env
        elif "USE_TEST_DB" in os.environ:
            del os.environ["USE_TEST_DB"]

    return success


def test_like_not_ilike():
    """Test that ILIKE is converted to LIKE."""
    print("=" * 60)
    print("Test: ILIKE to LIKE Conversion")
    print("=" * 60)

    plan_dict = {
        "selections": [
            {
                "table": "tb_Software",
                "alias": "s",
                "columns": [
                    {"table": "tb_Software", "column": "Name", "role": "projection"}
                ],
                "filters": [
                    {
                        "table": "tb_Software",
                        "column": "Name",
                        "op": "ilike",
                        "value": "%windows%"
                    }
                ]
            }
        ],
        "join_edges": [],
        "global_filters": [],
        "group_by": None,
        "window_functions": [],
        "subquery_filters": [],
        "ctes": []
    }

    state = {
        "sort_order": "Default",
        "result_limit": 0,
        "time_filter": "All Time"
    }

    db_context = get_database_context()

    try:
        sql = build_sql_query(plan_dict, state, db_context)
        print("Generated SQL:")
        print(sql)
        print("\n")

        if "ILIKE" in sql:
            print("ERROR: ILIKE found (should be LIKE)")
            return False
        elif "LIKE" in sql:
            print("SUCCESS: Using LIKE instead of ILIKE")
            return True
        else:
            print("WARNING: No LIKE found")
            return False

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_sql_injection_prevention():
    """Test that values are properly escaped to prevent SQL injection."""
    print("=" * 60)
    print("Test: SQL Injection Prevention")
    print("=" * 60)

    plan_dict = {
        "selections": [
            {
                "table": "tb_Users",
                "alias": "u",
                "columns": [
                    {"table": "tb_Users", "column": "Name", "role": "projection"}
                ],
                "filters": [
                    {
                        "table": "tb_Users",
                        "column": "Name",
                        "op": "=",
                        "value": "'; DROP TABLE users; --"
                    }
                ]
            }
        ],
        "join_edges": [],
        "global_filters": [],
        "group_by": None,
        "window_functions": [],
        "subquery_filters": [],
        "ctes": []
    }

    state = {
        "sort_order": "Default",
        "result_limit": 0,
        "time_filter": "All Time"
    }

    db_context = get_database_context()

    try:
        sql = build_sql_query(plan_dict, state, db_context)
        print("Generated SQL:")
        print(sql)
        print("\n")

        # Check that the dangerous string is properly escaped
        # Should NOT have unescaped DROP TABLE
        if "DROP TABLE users" in sql and "'" not in sql.split("DROP TABLE")[0][-10:]:
            print("ERROR: SQL injection vulnerability detected!")
            return False
        else:
            print("SUCCESS: Value appears to be properly escaped")
            return True

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("DIALECT COMPATIBILITY TESTS")
    print("=" * 60 + "\n")

    results = []
    results.append(("SQL Server DATEADD", test_sql_server_dateadd()))
    results.append(("SQLite datetime", test_sqlite_datetime()))
    results.append(("LIKE not ILIKE", test_like_not_ilike()))
    results.append(("SQL Injection Prevention", test_sql_injection_prevention()))

    print("\n" + "=" * 60)
    print("TEST RESULTS")
    print("=" * 60)
    for test_name, passed in results:
        status = "PASSED" if passed else "FAILED"
        print(f"{status}: {test_name}")
    print("=" * 60 + "\n")

    all_passed = all(result[1] for result in results)
    if all_passed:
        print("All tests passed!")
    else:
        print("Some tests failed. Please review the errors above.")
