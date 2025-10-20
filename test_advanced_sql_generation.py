"""Test advanced SQL generation with aggregations, window functions, etc."""

import json
from agent.generate_query import build_sql_query, get_database_context


def test_group_by_with_aggregates():
    """Test GROUP BY with aggregate functions."""
    print("=" * 60)
    print("Test 1: GROUP BY with Aggregates")
    print("=" * 60)

    plan_dict = {
        "selections": [
            {
                "table": "tb_Sales",
                "alias": "s",
                "columns": [
                    {"table": "tb_Sales", "column": "CompanyID", "role": "filter"}
                ]
            },
            {
                "table": "tb_Company",
                "alias": "c",
                "columns": [
                    {"table": "tb_Company", "column": "Name", "role": "projection"}
                ]
            }
        ],
        "join_edges": [
            {
                "from_table": "tb_Sales",
                "from_column": "CompanyID",
                "to_table": "tb_Company",
                "to_column": "ID",
                "join_type": "left"
            }
        ],
        "global_filters": [],
        "group_by": {
            "group_by_columns": [
                {
                    "table": "tb_Company",
                    "column": "Name",
                    "role": "projection",
                    "value_type": "string"
                }
            ],
            "aggregates": [
                {
                    "function": "SUM",
                    "table": "tb_Sales",
                    "column": "Amount",
                    "alias": "TotalSales"
                },
                {
                    "function": "COUNT",
                    "table": "tb_Sales",
                    "column": "ID",
                    "alias": "SalesCount"
                }
            ],
            "having_filters": []
        },
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
        return True
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_window_function():
    """Test window function (ROW_NUMBER)."""
    print("=" * 60)
    print("Test 2: Window Function (ROW_NUMBER)")
    print("=" * 60)

    plan_dict = {
        "selections": [
            {
                "table": "tb_Users",
                "alias": "u",
                "columns": [
                    {"table": "tb_Users", "column": "Name", "role": "projection"},
                    {"table": "tb_Users", "column": "CompanyID", "role": "filter"},
                    {"table": "tb_Users", "column": "Salary", "role": "projection"}
                ]
            }
        ],
        "join_edges": [],
        "global_filters": [],
        "group_by": None,
        "window_functions": [
            {
                "function": "ROW_NUMBER",
                "partition_by": [
                    {
                        "table": "tb_Users",
                        "column": "CompanyID",
                        "role": "filter",
                        "value_type": "integer"
                    }
                ],
                "order_by": [
                    {
                        "table": "tb_Users",
                        "column": "Salary",
                        "direction": "DESC"
                    }
                ],
                "alias": "Rank"
            }
        ],
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
        return True
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_subquery_filter():
    """Test subquery in filter (WHERE IN)."""
    print("=" * 60)
    print("Test 3: Subquery Filter (WHERE IN)")
    print("=" * 60)

    plan_dict = {
        "selections": [
            {
                "table": "tb_Users",
                "alias": "u",
                "columns": [
                    {"table": "tb_Users", "column": "Name", "role": "projection"},
                    {"table": "tb_Users", "column": "CompanyID", "role": "filter"}
                ]
            }
        ],
        "join_edges": [],
        "global_filters": [],
        "group_by": None,
        "window_functions": [],
        "subquery_filters": [
            {
                "outer_table": "tb_Users",
                "outer_column": "CompanyID",
                "op": "in",
                "subquery_table": "tb_Company",
                "subquery_column": "ID",
                "subquery_filters": [
                    {
                        "table": "tb_Company",
                        "column": "EmployeeCount",
                        "op": ">",
                        "value": 50
                    }
                ]
            }
        ],
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
        return True
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_group_by_with_having():
    """Test GROUP BY with HAVING clause."""
    print("=" * 60)
    print("Test 4: GROUP BY with HAVING")
    print("=" * 60)

    plan_dict = {
        "selections": [
            {
                "table": "tb_Sales",
                "alias": "s",
                "columns": [
                    {"table": "tb_Sales", "column": "CompanyID", "role": "filter"}
                ]
            },
            {
                "table": "tb_Company",
                "alias": "c",
                "columns": [
                    {"table": "tb_Company", "column": "Name", "role": "projection"}
                ]
            }
        ],
        "join_edges": [
            {
                "from_table": "tb_Sales",
                "from_column": "CompanyID",
                "to_table": "tb_Company",
                "to_column": "ID",
                "join_type": "left"
            }
        ],
        "global_filters": [],
        "group_by": {
            "group_by_columns": [
                {
                    "table": "tb_Company",
                    "column": "Name",
                    "role": "projection",
                    "value_type": "string"
                }
            ],
            "aggregates": [
                {
                    "function": "COUNT",
                    "table": "tb_Sales",
                    "column": "ID",
                    "alias": "SalesCount"
                }
            ],
            "having_filters": [
                {
                    "table": "tb_Sales",
                    "column": "SalesCount",
                    "op": ">",
                    "value": 100
                }
            ]
        },
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
        return True
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("ADVANCED SQL GENERATION TESTS")
    print("=" * 60 + "\n")

    results = []
    results.append(("GROUP BY with Aggregates", test_group_by_with_aggregates()))
    results.append(("Window Function", test_window_function()))
    results.append(("Subquery Filter", test_subquery_filter()))
    results.append(("GROUP BY with HAVING", test_group_by_with_having()))

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
