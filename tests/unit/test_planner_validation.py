"""Unit tests for planner validation logic."""

import pytest
from agent.planner import validate_group_by_completeness


class TestValidateGroupByCompleteness:
    """Test suite for GROUP BY completeness validation."""

    def test_valid_plan_with_proper_group_by(self):
        """Test that a valid plan with all projection columns in GROUP BY passes."""
        plan = {
            "selections": [
                {
                    "table": "tb_Company",
                    "include_only_for_join": False,
                    "columns": [
                        {
                            "table": "tb_Company",
                            "column": "ID",
                            "role": "projection",
                        },
                        {
                            "table": "tb_Company",
                            "column": "Name",
                            "role": "projection",
                        },
                    ],
                },
                {
                    "table": "tb_Sales",
                    "include_only_for_join": False,
                    "columns": [
                        {"table": "tb_Sales", "column": "ID", "role": "filter"}
                    ],
                },
            ],
            "group_by": {
                "group_by_columns": [
                    {"table": "tb_Company", "column": "ID", "role": "projection"},
                    {"table": "tb_Company", "column": "Name", "role": "projection"},
                ],
                "aggregates": [
                    {
                        "function": "COUNT",
                        "table": "tb_Sales",
                        "column": "ID",
                        "alias": "SalesCount",
                    }
                ],
            },
        }

        issues = validate_group_by_completeness(plan)
        assert len(issues) == 0, "Valid plan should have no validation issues"

    def test_missing_name_in_group_by(self):
        """Test that missing Name column in GROUP BY is detected (the original bug)."""
        plan = {
            "selections": [
                {
                    "table": "tb_SaasNetworkDomain",
                    "include_only_for_join": False,
                    "columns": [
                        {
                            "table": "tb_SaasNetworkDomain",
                            "column": "ID",
                            "role": "projection",
                        },
                        {
                            "table": "tb_SaasNetworkDomain",
                            "column": "Name",
                            "role": "projection",
                        },
                    ],
                },
            ],
            "group_by": {
                "group_by_columns": [
                    {
                        "table": "tb_SaasNetworkDomain",
                        "column": "ID",
                        "role": "projection",
                    }
                ],
                "aggregates": [
                    {
                        "function": "COUNT",
                        "table": "tb_SaasComputers",
                        "column": "ID",
                        "alias": "ComputerCount",
                    }
                ],
            },
        }

        issues = validate_group_by_completeness(plan)
        assert len(issues) == 1, "Should detect missing Name column in GROUP BY"
        assert "tb_SaasNetworkDomain.Name" in issues[0]
        assert "not in group_by_columns" in issues[0]

    def test_plan_without_group_by(self):
        """Test that plans without GROUP BY pass validation (no aggregates)."""
        plan = {
            "selections": [
                {
                    "table": "tb_Users",
                    "include_only_for_join": False,
                    "columns": [
                        {"table": "tb_Users", "column": "ID", "role": "projection"},
                        {"table": "tb_Users", "column": "Name", "role": "projection"},
                        {"table": "tb_Users", "column": "Email", "role": "projection"},
                    ],
                }
            ],
            "group_by": None,
        }

        issues = validate_group_by_completeness(plan)
        assert len(issues) == 0, "Plans without GROUP BY should pass validation"

    def test_plan_with_empty_aggregates(self):
        """Test that plans with group_by but no aggregates pass validation."""
        plan = {
            "selections": [
                {
                    "table": "tb_Company",
                    "include_only_for_join": False,
                    "columns": [
                        {"table": "tb_Company", "column": "ID", "role": "projection"},
                        {"table": "tb_Company", "column": "Name", "role": "projection"},
                    ],
                }
            ],
            "group_by": {"group_by_columns": [], "aggregates": []},
        }

        issues = validate_group_by_completeness(plan)
        assert len(issues) == 0, "Plans with empty aggregates should pass validation"

    def test_join_only_tables_ignored(self):
        """Test that join-only tables are excluded from validation."""
        plan = {
            "selections": [
                {
                    "table": "tb_Company",
                    "include_only_for_join": False,
                    "columns": [
                        {"table": "tb_Company", "column": "ID", "role": "projection"},
                        {"table": "tb_Company", "column": "Name", "role": "projection"},
                    ],
                },
                {
                    "table": "tb_Bridge",
                    "include_only_for_join": True,  # Join-only table
                    "columns": [
                        {
                            "table": "tb_Bridge",
                            "column": "CompanyID",
                            "role": "projection",
                        }
                    ],
                },
            ],
            "group_by": {
                "group_by_columns": [
                    {"table": "tb_Company", "column": "ID", "role": "projection"},
                    {"table": "tb_Company", "column": "Name", "role": "projection"},
                ],
                "aggregates": [
                    {"function": "COUNT", "table": "tb_Sales", "column": "ID"}
                ],
            },
        }

        issues = validate_group_by_completeness(plan)
        assert (
            len(issues) == 0
        ), "Join-only tables should be excluded from validation"

    def test_multiple_missing_columns(self):
        """Test detection of multiple missing columns in GROUP BY."""
        plan = {
            "selections": [
                {
                    "table": "tb_Product",
                    "include_only_for_join": False,
                    "columns": [
                        {"table": "tb_Product", "column": "ID", "role": "projection"},
                        {"table": "tb_Product", "column": "Name", "role": "projection"},
                        {
                            "table": "tb_Product",
                            "column": "Category",
                            "role": "projection",
                        },
                    ],
                }
            ],
            "group_by": {
                "group_by_columns": [
                    {"table": "tb_Product", "column": "ID", "role": "projection"}
                ],
                "aggregates": [{"function": "SUM", "table": "tb_Sales", "column": "Amount"}],
            },
        }

        issues = validate_group_by_completeness(plan)
        assert len(issues) == 2, "Should detect both missing columns"
        issue_text = " ".join(issues)
        assert "tb_Product.Name" in issue_text
        assert "tb_Product.Category" in issue_text

    def test_filter_columns_not_required_in_group_by(self):
        """Test that filter-only columns don't need to be in GROUP BY."""
        plan = {
            "selections": [
                {
                    "table": "tb_Company",
                    "include_only_for_join": False,
                    "columns": [
                        {"table": "tb_Company", "column": "ID", "role": "projection"},
                        {"table": "tb_Company", "column": "Name", "role": "projection"},
                        {
                            "table": "tb_Company",
                            "column": "IsActive",
                            "role": "filter",
                        },  # Filter only
                    ],
                }
            ],
            "group_by": {
                "group_by_columns": [
                    {"table": "tb_Company", "column": "ID", "role": "projection"},
                    {"table": "tb_Company", "column": "Name", "role": "projection"},
                    # IsActive NOT in GROUP BY (it's just a filter)
                ],
                "aggregates": [{"function": "COUNT", "table": "tb_Sales", "column": "ID"}],
            },
        }

        issues = validate_group_by_completeness(plan)
        assert (
            len(issues) == 0
        ), "Filter-only columns should not be required in GROUP BY"

    def test_multiple_tables_with_projections(self):
        """Test validation across multiple tables with projection columns."""
        plan = {
            "selections": [
                {
                    "table": "tb_Company",
                    "include_only_for_join": False,
                    "columns": [
                        {"table": "tb_Company", "column": "ID", "role": "projection"},
                        {"table": "tb_Company", "column": "Name", "role": "projection"},
                    ],
                },
                {
                    "table": "tb_Department",
                    "include_only_for_join": False,
                    "columns": [
                        {
                            "table": "tb_Department",
                            "column": "Name",
                            "role": "projection",
                        }
                    ],
                },
            ],
            "group_by": {
                "group_by_columns": [
                    {"table": "tb_Company", "column": "ID", "role": "projection"},
                    {"table": "tb_Company", "column": "Name", "role": "projection"},
                    {"table": "tb_Department", "column": "Name", "role": "projection"},
                ],
                "aggregates": [
                    {"function": "COUNT", "table": "tb_Employee", "column": "ID"}
                ],
            },
        }

        issues = validate_group_by_completeness(plan)
        assert (
            len(issues) == 0
        ), "All projection columns from both tables are in GROUP BY"

    def test_empty_selections(self):
        """Test that empty selections don't cause errors."""
        plan = {
            "selections": [],
            "group_by": {
                "group_by_columns": [],
                "aggregates": [{"function": "COUNT", "table": "tb_Sales", "column": "ID"}],
            },
        }

        issues = validate_group_by_completeness(plan)
        assert len(issues) == 0, "Empty selections should not cause validation errors"

    def test_plan_with_no_columns(self):
        """Test that tables with no columns don't cause issues."""
        plan = {
            "selections": [
                {
                    "table": "tb_Company",
                    "include_only_for_join": False,
                    "columns": [],  # No columns
                }
            ],
            "group_by": {
                "group_by_columns": [],
                "aggregates": [{"function": "COUNT", "table": "tb_Sales", "column": "ID"}],
            },
        }

        issues = validate_group_by_completeness(plan)
        assert len(issues) == 0, "Tables with no columns should not cause issues"
