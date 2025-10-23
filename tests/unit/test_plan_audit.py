"""Unit tests for plan audit validation logic."""

import pytest
from agent.plan_audit import (
    validate_column_exists,
    validate_selections,
    validate_join_edges,
    validate_filters,
    validate_group_by,
    filter_schema_to_plan_tables,
    run_deterministic_checks,
    fix_group_by_completeness,
    fix_having_filters,
)


@pytest.fixture
def sample_schema():
    """Sample schema for testing."""
    return [
        {
            "table_name": "tb_Company",
            "columns": [
                {"column_name": "ID", "data_type": "bigint"},
                {"column_name": "Name", "data_type": "nvarchar"},
                {"column_name": "CompanyID", "data_type": "bigint"},
            ]
        },
        {
            "table_name": "tb_Users",
            "columns": [
                {"column_name": "ID", "data_type": "bigint"},
                {"column_name": "UserID", "data_type": "nvarchar"},
                {"column_name": "CompanyID", "data_type": "bigint"},
                {"column_name": "Email", "data_type": "nvarchar"},
            ]
        },
        {
            "table_name": "tb_SoftwareTagsAndColors",
            "columns": [
                {"column_name": "ID", "data_type": "bigint"},
                {"column_name": "TagName", "data_type": "nvarchar"},
                {"column_name": "CompanyID", "data_type": "bigint"},
            ]
        },
    ]


class TestValidateColumnExists:
    """Test column existence validation."""

    def test_column_exists(self, sample_schema):
        """Test that existing column is found."""
        assert validate_column_exists("tb_Company", "ID", sample_schema) is True
        assert validate_column_exists("tb_Company", "Name", sample_schema) is True

    def test_column_not_exists(self, sample_schema):
        """Test that non-existent column is not found."""
        assert validate_column_exists("tb_Company", "TagID", sample_schema) is False
        assert validate_column_exists("tb_Company", "NonExistent", sample_schema) is False

    def test_table_not_exists(self, sample_schema):
        """Test that column in non-existent table is not found."""
        assert validate_column_exists("tb_NonExistent", "ID", sample_schema) is False


class TestValidateSelections:
    """Test selection validation."""

    def test_valid_selections(self, sample_schema):
        """Test that valid selections pass."""
        plan = {
            "selections": [
                {
                    "table": "tb_Company",
                    "columns": [
                        {"table": "tb_Company", "column": "ID"},
                        {"table": "tb_Company", "column": "Name"},
                    ]
                }
            ]
        }
        issues = validate_selections(plan, sample_schema)
        assert len(issues) == 0

    def test_invalid_column_in_selection(self, sample_schema):
        """Test that invalid column is detected."""
        plan = {
            "selections": [
                {
                    "table": "tb_Company",
                    "columns": [
                        {"table": "tb_Company", "column": "ID"},
                        {"table": "tb_Company", "column": "TagID"},  # Doesn't exist
                    ]
                }
            ]
        }
        issues = validate_selections(plan, sample_schema)
        assert len(issues) == 1
        assert "TagID" in issues[0]
        assert "tb_Company" in issues[0]


class TestValidateJoinEdges:
    """Test join validation."""

    def test_valid_join(self, sample_schema):
        """Test that valid join passes."""
        plan = {
            "join_edges": [
                {
                    "from_table": "tb_Users",
                    "from_column": "CompanyID",
                    "to_table": "tb_Company",
                    "to_column": "ID",
                }
            ]
        }
        issues = validate_join_edges(plan, sample_schema)
        assert len(issues) == 0

    def test_invalid_from_column(self, sample_schema):
        """Test that invalid from_column is detected."""
        plan = {
            "join_edges": [
                {
                    "from_table": "tb_Users",
                    "from_column": "TagID",  # Doesn't exist
                    "to_table": "tb_Company",
                    "to_column": "ID",
                }
            ]
        }
        issues = validate_join_edges(plan, sample_schema)
        assert len(issues) == 1
        assert "TagID" in issues[0]
        assert "tb_Users" in issues[0]

    def test_invalid_to_column(self, sample_schema):
        """Test that invalid to_column is detected."""
        plan = {
            "join_edges": [
                {
                    "from_table": "tb_Users",
                    "from_column": "CompanyID",
                    "to_table": "tb_SoftwareTagsAndColors",
                    "to_column": "TagID",  # Doesn't exist
                }
            ]
        }
        issues = validate_join_edges(plan, sample_schema)
        assert len(issues) == 1
        assert "TagID" in issues[0]
        assert "tb_SoftwareTagsAndColors" in issues[0]

    def test_both_columns_invalid(self, sample_schema):
        """Test that both invalid columns are detected."""
        plan = {
            "join_edges": [
                {
                    "from_table": "tb_Users",
                    "from_column": "FakeID",  # Doesn't exist
                    "to_table": "tb_Company",
                    "to_column": "TagID",  # Doesn't exist
                }
            ]
        }
        issues = validate_join_edges(plan, sample_schema)
        assert len(issues) == 2


class TestValidateFilters:
    """Test filter validation."""

    def test_valid_table_filter(self, sample_schema):
        """Test that valid table filter passes."""
        plan = {
            "selections": [
                {
                    "table": "tb_Company",
                    "filters": [
                        {"table": "tb_Company", "column": "Name", "op": "=", "value": "Test"}
                    ]
                }
            ],
            "global_filters": [],
        }
        issues = validate_filters(plan, sample_schema)
        assert len(issues) == 0

    def test_invalid_filter_column(self, sample_schema):
        """Test that invalid filter column is detected."""
        plan = {
            "selections": [
                {
                    "table": "tb_Company",
                    "filters": [
                        {"table": "tb_Company", "column": "TagName", "op": "=", "value": "Test"}  # Doesn't exist
                    ]
                }
            ],
            "global_filters": [],
        }
        issues = validate_filters(plan, sample_schema)
        assert len(issues) == 1
        assert "TagName" in issues[0]

    def test_valid_having_filter(self, sample_schema):
        """Test that valid HAVING filter passes."""
        plan = {
            "selections": [],
            "global_filters": [],
            "group_by": {
                "having_filters": [
                    {"table": "tb_Company", "column": "ID", "op": ">", "value": 100}
                ]
            }
        }
        issues = validate_filters(plan, sample_schema)
        assert len(issues) == 0

    def test_invalid_having_filter_column(self, sample_schema):
        """Test that invalid HAVING column is detected."""
        plan = {
            "selections": [],
            "global_filters": [],
            "group_by": {
                "having_filters": [
                    {"table": "tb_Company", "column": "Impact", "op": "=", "value": "Critical"}  # Doesn't exist
                ]
            }
        }
        issues = validate_filters(plan, sample_schema)
        assert len(issues) == 1
        assert "Impact" in issues[0]


class TestValidateGroupBy:
    """Test GROUP BY validation."""

    def test_valid_group_by(self, sample_schema):
        """Test that valid GROUP BY passes."""
        plan = {
            "group_by": {
                "group_by_columns": [
                    {"table": "tb_Company", "column": "ID"},
                    {"table": "tb_Company", "column": "Name"},
                ]
            }
        }
        issues = validate_group_by(plan, sample_schema)
        assert len(issues) == 0

    def test_invalid_group_by_column(self, sample_schema):
        """Test that invalid GROUP BY column is detected."""
        plan = {
            "group_by": {
                "group_by_columns": [
                    {"table": "tb_Company", "column": "ID"},
                    {"table": "tb_Company", "column": "TagID"},  # Doesn't exist
                ]
            }
        }
        issues = validate_group_by(plan, sample_schema)
        assert len(issues) == 1
        assert "TagID" in issues[0]


class TestFilterSchemaToPlanTables:
    """Test schema filtering."""

    def test_filter_to_plan_tables(self, sample_schema):
        """Test that schema is filtered to only plan tables."""
        plan = {
            "selections": [
                {"table": "tb_Company"},
                {"table": "tb_Users"},
            ],
            "join_edges": []
        }
        filtered = filter_schema_to_plan_tables(plan, sample_schema)
        assert len(filtered) == 2
        table_names = [t["table_name"] for t in filtered]
        assert "tb_Company" in table_names
        assert "tb_Users" in table_names
        assert "tb_SoftwareTagsAndColors" not in table_names

    def test_filter_includes_join_tables(self, sample_schema):
        """Test that join tables are included."""
        plan = {
            "selections": [
                {"table": "tb_Company"},
            ],
            "join_edges": [
                {"from_table": "tb_Company", "to_table": "tb_Users"}
            ]
        }
        filtered = filter_schema_to_plan_tables(plan, sample_schema)
        assert len(filtered) == 2
        table_names = [t["table_name"] for t in filtered]
        assert "tb_Company" in table_names
        assert "tb_Users" in table_names


class TestRunDeterministicChecks:
    """Test comprehensive validation."""

    def test_all_checks_pass(self, sample_schema):
        """Test that valid plan passes all checks."""
        plan = {
            "selections": [
                {
                    "table": "tb_Company",
                    "columns": [
                        {"table": "tb_Company", "column": "ID"},
                        {"table": "tb_Company", "column": "Name"},
                    ],
                    "filters": [
                        {"table": "tb_Company", "column": "Name", "op": "=", "value": "Test"}
                    ]
                }
            ],
            "join_edges": [],
            "global_filters": [],
            "group_by": None,
        }
        issues = run_deterministic_checks(plan, sample_schema)
        assert len(issues) == 0

    def test_multiple_issues_detected(self, sample_schema):
        """Test that multiple issues across different checks are detected."""
        plan = {
            "selections": [
                {
                    "table": "tb_Company",
                    "columns": [
                        {"table": "tb_Company", "column": "TagID"},  # Issue 1: Invalid selection
                    ],
                    "filters": [
                        {"table": "tb_Company", "column": "Impact", "op": "=", "value": "High"}  # Issue 2: Invalid filter
                    ]
                },
                {
                    "table": "tb_Users",
                    "columns": [
                        {"table": "tb_Users", "column": "Email"},
                    ],
                    "filters": []
                }
            ],
            "join_edges": [
                {
                    "from_table": "tb_Users",
                    "from_column": "TagID",  # Issue 3: Invalid join column
                    "to_table": "tb_Company",
                    "to_column": "ID",
                }
            ],
            "global_filters": [],
            "group_by": {
                "group_by_columns": [
                    {"table": "tb_Company", "column": "FakeID"}  # Issue 4: Invalid GROUP BY
                ]
            },
        }
        issues = run_deterministic_checks(plan, sample_schema)
        assert len(issues) == 4  # Should detect all 4 issues


class TestFixGroupByCompleteness:
    """Test GROUP BY completeness fix."""

    def test_adds_missing_projection_columns(self):
        """Test that missing projection columns are added to GROUP BY."""
        plan = {
            "selections": [
                {
                    "table": "tb_Company",
                    "columns": [
                        {"table": "tb_Company", "column": "ID", "role": "projection"},
                        {"table": "tb_Company", "column": "Name", "role": "projection"},
                    ]
                }
            ],
            "group_by": {
                "aggregates": [
                    {"table": "tb_Users", "column": "ID", "aggregate_func": "COUNT"}
                ],
                "group_by_columns": [
                    {"table": "tb_Company", "column": "ID"}
                    # Missing Name column
                ]
            }
        }

        fixed_plan = fix_group_by_completeness(plan)
        group_by_cols = fixed_plan["group_by"]["group_by_columns"]

        assert len(group_by_cols) == 2
        assert {"table": "tb_Company", "column": "ID"} in group_by_cols
        assert {"table": "tb_Company", "column": "Name"} in group_by_cols

    def test_no_change_when_group_by_complete(self):
        """Test that complete GROUP BY is not modified."""
        plan = {
            "selections": [
                {
                    "table": "tb_Company",
                    "columns": [
                        {"table": "tb_Company", "column": "ID", "role": "projection"},
                    ]
                }
            ],
            "group_by": {
                "aggregates": [
                    {"table": "tb_Users", "column": "ID", "aggregate_func": "COUNT"}
                ],
                "group_by_columns": [
                    {"table": "tb_Company", "column": "ID"}
                ]
            }
        }

        fixed_plan = fix_group_by_completeness(plan)
        group_by_cols = fixed_plan["group_by"]["group_by_columns"]

        assert len(group_by_cols) == 1
        assert {"table": "tb_Company", "column": "ID"} in group_by_cols

    def test_skips_join_only_tables(self):
        """Test that columns from join-only tables are not added to GROUP BY."""
        plan = {
            "selections": [
                {
                    "table": "tb_Company",
                    "columns": [
                        {"table": "tb_Company", "column": "ID", "role": "projection"},
                    ]
                },
                {
                    "table": "tb_Users",
                    "include_only_for_join": True,
                    "columns": [
                        {"table": "tb_Users", "column": "UserID", "role": "projection"},
                    ]
                }
            ],
            "group_by": {
                "aggregates": [
                    {"table": "tb_Users", "column": "ID", "aggregate_func": "COUNT"}
                ],
                "group_by_columns": [
                    {"table": "tb_Company", "column": "ID"}
                ]
            }
        }

        fixed_plan = fix_group_by_completeness(plan)
        group_by_cols = fixed_plan["group_by"]["group_by_columns"]

        # Should not include tb_Users.UserID since it's from a join-only table
        assert len(group_by_cols) == 1
        assert {"table": "tb_Company", "column": "ID"} in group_by_cols

    def test_no_change_when_no_aggregates(self):
        """Test that plans without aggregates are not modified."""
        plan = {
            "selections": [
                {
                    "table": "tb_Company",
                    "columns": [
                        {"table": "tb_Company", "column": "ID", "role": "projection"},
                        {"table": "tb_Company", "column": "Name", "role": "projection"},
                    ]
                }
            ],
            "group_by": None
        }

        fixed_plan = fix_group_by_completeness(plan)
        assert fixed_plan["group_by"] is None

    def test_multiple_tables_with_missing_columns(self):
        """Test fixing GROUP BY with multiple tables and multiple missing columns."""
        plan = {
            "selections": [
                {
                    "table": "tb_Company",
                    "columns": [
                        {"table": "tb_Company", "column": "ID", "role": "projection"},
                        {"table": "tb_Company", "column": "Name", "role": "projection"},
                    ]
                },
                {
                    "table": "tb_Users",
                    "columns": [
                        {"table": "tb_Users", "column": "UserID", "role": "projection"},
                        {"table": "tb_Users", "column": "Email", "role": "projection"},
                    ]
                }
            ],
            "group_by": {
                "aggregates": [
                    {"table": "tb_Users", "column": "ID", "aggregate_func": "COUNT"}
                ],
                "group_by_columns": [
                    {"table": "tb_Company", "column": "ID"}
                    # Missing 3 columns
                ]
            }
        }

        fixed_plan = fix_group_by_completeness(plan)
        group_by_cols = fixed_plan["group_by"]["group_by_columns"]

        assert len(group_by_cols) == 4
        assert {"table": "tb_Company", "column": "ID"} in group_by_cols
        assert {"table": "tb_Company", "column": "Name"} in group_by_cols
        assert {"table": "tb_Users", "column": "UserID"} in group_by_cols
        assert {"table": "tb_Users", "column": "Email"} in group_by_cols


class TestFixHavingFilters:
    """Test HAVING filter migration to WHERE."""

    def test_moves_non_aggregated_having_to_where(self):
        """Test that HAVING filters on non-aggregated columns move to WHERE."""
        plan = {
            "selections": [
                {
                    "table": "tb_Company",
                    "columns": [
                        {"table": "tb_Company", "column": "ID", "role": "projection"},
                    ]
                }
            ],
            "global_filters": [],
            "group_by": {
                "group_by_columns": [
                    {"table": "tb_Company", "column": "ID"}
                ],
                "aggregates": [
                    {"table": "tb_Users", "column": "ID", "function": "COUNT", "alias": "user_count"}
                ],
                "having_filters": [
                    {"table": "tb_Company", "column": "Name", "op": "=", "value": "Test"}  # Not in GROUP BY!
                ]
            }
        }

        fixed_plan = fix_having_filters(plan)

        # HAVING filter should be moved to global_filters
        assert len(fixed_plan["global_filters"]) == 1
        assert fixed_plan["global_filters"][0]["column"] == "Name"

        # HAVING filters should be empty now
        assert len(fixed_plan["group_by"]["having_filters"]) == 0

    def test_keeps_valid_having_filters(self):
        """Test that HAVING filters on GROUP BY columns or aggregates stay in HAVING."""
        plan = {
            "selections": [],
            "global_filters": [],
            "group_by": {
                "group_by_columns": [
                    {"table": "tb_Company", "column": "ID"}
                ],
                "aggregates": [
                    {"table": "tb_Users", "column": "ID", "function": "COUNT", "alias": "user_count"}
                ],
                "having_filters": [
                    {"table": "tb_Company", "column": "ID", "op": ">", "value": 100},  # In GROUP BY - valid
                    {"table": "tb_Users", "column": "ID", "op": ">", "value": 5}  # Aggregated - valid
                ]
            }
        }

        fixed_plan = fix_having_filters(plan)

        # Both filters should stay in HAVING
        assert len(fixed_plan["group_by"]["having_filters"]) == 2
        assert len(fixed_plan.get("global_filters", [])) == 0

    def test_no_change_when_no_having_filters(self):
        """Test that plans without HAVING filters are unchanged."""
        plan = {
            "selections": [],
            "global_filters": [],
            "group_by": {
                "group_by_columns": [
                    {"table": "tb_Company", "column": "ID"}
                ],
                "aggregates": [
                    {"table": "tb_Users", "column": "ID", "function": "COUNT", "alias": "user_count"}
                ],
                "having_filters": []
            }
        }

        fixed_plan = fix_having_filters(plan)
        assert len(fixed_plan["group_by"]["having_filters"]) == 0
        assert len(fixed_plan.get("global_filters", [])) == 0

    def test_no_change_when_no_group_by(self):
        """Test that plans without GROUP BY are unchanged."""
        plan = {
            "selections": [],
            "global_filters": [],
            "group_by": None
        }

        fixed_plan = fix_having_filters(plan)
        assert fixed_plan["group_by"] is None
