"""Unit tests for validating table references in query plans."""

import pytest
from agent.plan_audit import validate_table_references


class TestValidateTableReferences:
    """Test the validate_table_references function."""

    def test_valid_plan_no_issues(self):
        """Test that a valid plan with all referenced tables in selections passes."""
        plan = {
            "selections": [
                {"table": "tb_Users", "columns": []},
                {"table": "tb_Company", "columns": []},
            ],
            "global_filters": [
                {"table": "tb_Users", "column": "IsActive", "op": "=", "value": True}
            ],
            "order_by": [
                {"table": "tb_Company", "column": "Name", "direction": "ASC"}
            ],
        }

        issues = validate_table_references(plan)
        assert len(issues) == 0

    def test_filter_references_missing_table(self):
        """Test detection of filter referencing table not in selections."""
        plan = {
            "selections": [
                {"table": "tb_Users", "columns": []},
            ],
            "global_filters": [
                {"table": "tb_Company", "column": "Name", "op": "=", "value": "Acme"}  # Missing table
            ],
        }

        issues = validate_table_references(plan)
        assert len(issues) == 1
        assert "tb_Company" in issues[0]
        assert "not included in selections" in issues[0]

    def test_order_by_references_missing_table(self):
        """Test detection of ORDER BY referencing table not in selections."""
        plan = {
            "selections": [
                {"table": "tb_Users", "columns": []},
            ],
            "order_by": [
                {"table": "tb_Company", "column": "Name", "direction": "ASC"}  # Missing table
            ],
        }

        issues = validate_table_references(plan)
        assert len(issues) == 1
        assert "tb_Company" in issues[0]

    def test_group_by_column_references_missing_table(self):
        """Test detection of GROUP BY column referencing table not in selections."""
        plan = {
            "selections": [
                {"table": "tb_Sales", "columns": []},
            ],
            "group_by": {
                "group_by_columns": [
                    {"table": "tb_Company", "column": "Name"}  # Missing table
                ],
                "aggregates": [
                    {"function": "SUM", "table": "tb_Sales", "column": "Amount", "alias": "TotalSales"}
                ],
            },
        }

        issues = validate_table_references(plan)
        assert len(issues) == 1
        assert "tb_Company" in issues[0]

    def test_aggregate_references_missing_table(self):
        """Test detection of aggregate referencing table not in selections."""
        plan = {
            "selections": [
                {"table": "tb_Company", "columns": []},
            ],
            "group_by": {
                "group_by_columns": [
                    {"table": "tb_Company", "column": "Name"}
                ],
                "aggregates": [
                    {"function": "COUNT", "table": "tb_Sales", "column": "ID", "alias": "SaleCount"}  # Missing
                ],
            },
        }

        issues = validate_table_references(plan)
        assert len(issues) == 1
        assert "tb_Sales" in issues[0]

    def test_having_filter_references_missing_table(self):
        """Test detection of HAVING filter referencing table not in selections."""
        plan = {
            "selections": [
                {"table": "tb_Sales", "columns": []},
            ],
            "group_by": {
                "group_by_columns": [
                    {"table": "tb_Sales", "column": "ProductID"}
                ],
                "aggregates": [
                    {"function": "COUNT", "table": "tb_Sales", "column": "ID", "alias": "SaleCount"}
                ],
                "having_filters": [
                    {"table": "tb_Company", "column": "Region", "op": "=", "value": "North"}  # Missing
                ],
            },
        }

        issues = validate_table_references(plan)
        assert len(issues) == 1
        assert "tb_Company" in issues[0]

    def test_table_level_filter_references_missing_table(self):
        """Test detection of table-level filter referencing different table."""
        plan = {
            "selections": [
                {
                    "table": "tb_Users",
                    "columns": [],
                    "filters": [
                        {"table": "tb_Company", "column": "IsActive", "op": "=", "value": True}  # Wrong table
                    ],
                },
            ],
        }

        issues = validate_table_references(plan)
        assert len(issues) == 1
        assert "tb_Company" in issues[0]

    def test_multiple_missing_tables(self):
        """Test detection of multiple missing table references."""
        plan = {
            "selections": [
                {"table": "tb_Users", "columns": []},
            ],
            "global_filters": [
                {"table": "tb_Company", "column": "Name", "op": "=", "value": "Acme"},
                {"table": "tb_Products", "column": "Category", "op": "=", "value": "Software"},
            ],
            "order_by": [
                {"table": "tb_Sales", "column": "Amount", "direction": "DESC"}
            ],
        }

        issues = validate_table_references(plan)
        assert len(issues) == 3
        # Should detect all three missing tables
        missing_tables = [issue for issue in issues]
        assert any("tb_Company" in issue for issue in missing_tables)
        assert any("tb_Products" in issue for issue in missing_tables)
        assert any("tb_Sales" in issue for issue in missing_tables)

    def test_empty_plan(self):
        """Test that an empty plan doesn't cause errors."""
        plan = {
            "selections": [],
        }

        issues = validate_table_references(plan)
        assert len(issues) == 0

    def test_plan_with_no_optional_fields(self):
        """Test plan with only selections and no other fields."""
        plan = {
            "selections": [
                {"table": "tb_Users", "columns": []},
            ],
        }

        issues = validate_table_references(plan)
        assert len(issues) == 0

    def test_window_function_references_missing_table(self):
        """Test detection of window function referencing table not in selections."""
        plan = {
            "selections": [
                {"table": "tb_Sales", "columns": []},
            ],
            "window_functions": [
                {
                    "function": "ROW_NUMBER",
                    "table": "tb_Company",  # Missing table
                    "column": "Revenue",
                    "alias": "CompanyRank",
                }
            ],
        }

        issues = validate_table_references(plan)
        assert len(issues) == 1
        assert "tb_Company" in issues[0]

    def test_subquery_filter_references_missing_tables(self):
        """Test detection of subquery filter referencing missing tables."""
        plan = {
            "selections": [
                {"table": "tb_Users", "columns": []},
            ],
            "subquery_filters": [
                {
                    "outer_table": "tb_Users",
                    "outer_column": "CompanyID",
                    "subquery_table": "tb_Company",  # Missing table
                    "subquery_column": "ID",
                }
            ],
        }

        issues = validate_table_references(plan)
        assert len(issues) == 1
        assert "tb_Company" in issues[0]


class TestBenchmarkErrorScenarios:
    """Test specific error scenarios from the benchmark analysis."""

    def test_gpt5_mini_query4_scenario(self):
        """
        Test the specific error from gpt-5-mini / query_4:
        SELECT * FROM [tb_SaasComputers]
        JOIN [tb_Company] ON ...
        JOIN [tb_SaasComputerUSBDeviceDetails]
          ON [tb_SaasScan].[ID] = ...  -- tb_SaasScan not in FROM clause
        WHERE [tb_SaasScan].[Schedule] >= ...  -- tb_SaasScan not in FROM clause
        """
        plan = {
            "selections": [
                {"table": "tb_SaasComputers", "columns": []},
                {"table": "tb_Company", "columns": []},
                {"table": "tb_SaasComputerUSBDeviceDetails", "columns": []},
            ],
            "global_filters": [
                {"table": "tb_SaasScan", "column": "Schedule", "op": ">=", "value": "2025-10-01"}
            ],
        }

        issues = validate_table_references(plan)
        assert len(issues) == 1
        assert "tb_SaasScan" in issues[0]
        assert "not included in selections" in issues[0]

    def test_llama3_8b_query5_scenario(self):
        """
        Test the specific error from llama3-8b / query_5:
        SELECT
          [tb_CVEConfiguration].[AverageCVSSScore],  -- Table not in FROM
          [tb_CVE].[CVSSScore]  -- Table not in FROM
        FROM [tb_SaasMasterInstalledApps]
        """
        plan = {
            "selections": [
                {
                    "table": "tb_SaasMasterInstalledApps",
                    "columns": [
                        {"table": "tb_SaasMasterInstalledApps", "column": "Name", "role": "projection"}
                    ],
                },
            ],
            "group_by": {
                "group_by_columns": [],
                "aggregates": [
                    {"function": "AVG", "table": "tb_CVEConfiguration", "column": "AverageCVSSScore", "alias": "AvgScore"},
                    {"function": "AVG", "table": "tb_CVE", "column": "CVSSScore", "alias": "CVEScore"},
                ],
            },
        }

        issues = validate_table_references(plan)
        assert len(issues) == 2
        # Should detect both missing tables
        assert any("tb_CVEConfiguration" in issue for issue in issues)
        assert any("tb_CVE" in issue for issue in issues)

    def test_valid_complex_plan(self):
        """Test a complex but valid plan with many fields."""
        plan = {
            "selections": [
                {"table": "tb_Users", "columns": [], "filters": [
                    {"table": "tb_Users", "column": "IsActive", "op": "=", "value": True}
                ]},
                {"table": "tb_Company", "columns": []},
                {"table": "tb_Sales", "columns": []},
            ],
            "global_filters": [
                {"table": "tb_Company", "column": "Region", "op": "=", "value": "North"}
            ],
            "group_by": {
                "group_by_columns": [
                    {"table": "tb_Company", "column": "Name"}
                ],
                "aggregates": [
                    {"function": "SUM", "table": "tb_Sales", "column": "Amount", "alias": "TotalSales"}
                ],
                "having_filters": [
                    {"table": "tb_Company", "column": "Name", "op": "!=", "value": "Test"}
                ],
            },
            "order_by": [
                {"table": "tb_Company", "column": "Name", "direction": "ASC"}
            ],
        }

        issues = validate_table_references(plan)
        assert len(issues) == 0  # All referenced tables are in selections
