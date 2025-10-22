"""Test script for SQLGlot-based SQL generation."""

from agent.generate_query import build_sql_query, get_database_context


def test_basic_select():
    """Test basic SELECT statement generation."""
    print("\n" + "=" * 80)
    print("TEST 1: Basic SELECT")
    print("=" * 80)

    plan_dict = {
        "selections": [
            {
                "table": "Companies",
                "alias": "c",
                "columns": [
                    {"column": "ID", "role": "projection"},
                    {"column": "Name", "role": "projection"},
                ],
                "filters": [],
            }
        ],
        "join_edges": [],
        "global_filters": [],
    }

    state = {"sort_order": "Default", "result_limit": 0, "time_filter": "All Time"}

    db_context = get_database_context()

    sql = build_sql_query(plan_dict, state, db_context)

    print(f"\nGenerated SQL:\n{sql}\n")

    assert "SELECT" in sql
    assert "Companies" in sql
    print("[PASS] Test passed!")


def test_join():
    """Test JOIN generation."""
    print("\n" + "=" * 80)
    print("TEST 2: JOIN")
    print("=" * 80)

    plan_dict = {
        "selections": [
            {
                "table": "Companies",
                "alias": "c",
                "columns": [{"column": "Name", "role": "projection"}],
                "filters": [],
            },
            {
                "table": "Vendors",
                "alias": "v",
                "columns": [{"column": "VendorName", "role": "projection"}],
                "filters": [],
            },
        ],
        "join_edges": [
            {
                "from_table": "Companies",
                "from_column": "VendorID",
                "to_table": "Vendors",
                "to_column": "ID",
                "join_type": "left",
            }
        ],
        "global_filters": [],
    }

    state = {"sort_order": "Default", "result_limit": 0, "time_filter": "All Time"}

    db_context = get_database_context()

    sql = build_sql_query(plan_dict, state, db_context)

    print(f"\nGenerated SQL:\n{sql}\n")

    assert "JOIN" in sql
    assert "VendorID" in sql
    print("[PASS] Test passed!")


def test_filters():
    """Test WHERE clause generation."""
    print("\n" + "=" * 80)
    print("TEST 3: Filters")
    print("=" * 80)

    plan_dict = {
        "selections": [
            {
                "table": "Companies",
                "alias": "c",
                "columns": [{"column": "Name", "role": "projection"}],
                "filters": [
                    {
                        "table": "Companies",
                        "column": "Status",
                        "op": "=",
                        "value": "Active",
                    },
                    {
                        "table": "Companies",
                        "column": "Revenue",
                        "op": ">",
                        "value": 1000000,
                    },
                ],
            }
        ],
        "join_edges": [],
        "global_filters": [],
    }

    state = {"sort_order": "Default", "result_limit": 0, "time_filter": "All Time"}

    db_context = get_database_context()

    sql = build_sql_query(plan_dict, state, db_context)

    print(f"\nGenerated SQL:\n{sql}\n")

    assert "WHERE" in sql
    assert "Status" in sql
    assert "Revenue" in sql
    print("[PASS] Test passed!")


def test_in_operator():
    """Test IN operator."""
    print("\n" + "=" * 80)
    print("TEST 4: IN Operator")
    print("=" * 80)

    plan_dict = {
        "selections": [
            {
                "table": "Companies",
                "alias": "c",
                "columns": [{"column": "Name", "role": "projection"}],
                "filters": [
                    {
                        "table": "Companies",
                        "column": "Type",
                        "op": "in",
                        "value": ["Corporation", "LLC", "Partnership"],
                    }
                ],
            }
        ],
        "join_edges": [],
        "global_filters": [],
    }

    state = {"sort_order": "Default", "result_limit": 0, "time_filter": "All Time"}

    db_context = get_database_context()

    sql = build_sql_query(plan_dict, state, db_context)

    print(f"\nGenerated SQL:\n{sql}\n")

    assert "IN" in sql
    assert "Corporation" in sql
    print("[PASS] Test passed!")


def test_order_and_limit():
    """Test ORDER BY and LIMIT."""
    print("\n" + "=" * 80)
    print("TEST 5: ORDER BY and LIMIT")
    print("=" * 80)

    plan_dict = {
        "selections": [
            {
                "table": "Companies",
                "alias": "c",
                "columns": [{"column": "Name", "role": "projection"}],
                "filters": [],
            }
        ],
        "join_edges": [],
        "global_filters": [],
    }

    state = {"sort_order": "Descending", "result_limit": 10, "time_filter": "All Time"}

    db_context = get_database_context()

    sql = build_sql_query(plan_dict, state, db_context)

    print(f"\nGenerated SQL:\n{sql}\n")

    assert "ORDER BY" in sql or "LIMIT" in sql or "TOP" in sql
    print("[PASS] Test passed!")


def test_complex_query():
    """Test complex query with multiple features."""
    print("\n" + "=" * 80)
    print("TEST 6: Complex Query")
    print("=" * 80)

    plan_dict = {
        "selections": [
            {
                "table": "Companies",
                "alias": "c",
                "columns": [
                    {"column": "ID", "role": "projection"},
                    {"column": "Name", "role": "projection"},
                    {"column": "CreatedOn", "role": "projection"},
                ],
                "filters": [
                    {
                        "table": "Companies",
                        "column": "Status",
                        "op": "=",
                        "value": "Active",
                    }
                ],
            },
            {
                "table": "Vendors",
                "alias": "v",
                "columns": [{"column": "VendorName", "role": "projection"}],
                "filters": [],
            },
            {
                "table": "Products",
                "alias": "p",
                "columns": [{"column": "ProductName", "role": "projection"}],
                "filters": [
                    {
                        "table": "Products",
                        "column": "Price",
                        "op": "between",
                        "value": [100, 500],
                    }
                ],
            },
        ],
        "join_edges": [
            {
                "from_table": "Companies",
                "from_column": "VendorID",
                "to_table": "Vendors",
                "to_column": "ID",
                "join_type": "left",
            },
            {
                "from_table": "Companies",
                "from_column": "ID",
                "to_table": "Products",
                "to_column": "CompanyID",
                "join_type": "inner",
            },
        ],
        "global_filters": [],
    }

    state = {
        "sort_order": "Ascending",
        "result_limit": 50,
        "time_filter": "Last 30 Days",
    }

    db_context = get_database_context()

    sql = build_sql_query(plan_dict, state, db_context)

    print(f"\nGenerated SQL:\n{sql}\n")

    assert "SELECT" in sql
    assert "JOIN" in sql
    assert "WHERE" in sql
    assert "BETWEEN" in sql
    print("[PASS] Test passed!")


def test_all():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("SQLGlot-Based SQL Generation Tests")
    print("=" * 80)

    tests = [
        test_basic_select,
        test_join,
        test_filters,
        test_in_operator,
        test_order_and_limit,
        test_complex_query,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"\n[FAIL] Test failed: {e}")
            import traceback

            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 80)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 80)

    if failed == 0:
        print("\n[PASS] All tests passed!")
    else:
        print(f"\n[FAIL] {failed} test(s) failed")

    return failed == 0


if __name__ == "__main__":
    success = test_all()
    exit(0 if success else 1)
