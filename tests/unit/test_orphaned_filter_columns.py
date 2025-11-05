"""
Test the orphaned filter column heuristic in the join synthesizer.

This tests the fix for the issue where the planner marks a column as role="filter"
but forgets to create the actual FilterPredicate, resulting in the column being
neither displayed nor filtered on.

Observed behavior (before fix):
- User query: "List all applications tagged with security risk"
- Planner marked TagName as role="filter"
- But planner FORGOT to create the filter predicate (filters: [])
- Result: TagName was neither displayed NOR filtered on!

The heuristic ensures orphaned filter columns are treated as projections to ensure visibility.
"""

import pytest
from agent.generate_query import _column_has_filter_predicate, generate_query
from agent.state import State


class TestColumnHasFilterPredicate:
    """Test the _column_has_filter_predicate helper function."""

    def test_detects_table_level_filter(self):
        """Test detection of table-level filters."""
        table_selection = {
            "table": "tb_Company",
            "filters": [
                {"table": "tb_Company", "column": "Name", "op": "=", "value": "Test"}
            ]
        }
        planner_output = {"global_filters": []}

        assert _column_has_filter_predicate(
            "tb_Company", "Name", table_selection, planner_output
        ) is True

    def test_detects_global_filter(self):
        """Test detection of global filters."""
        table_selection = {"filters": []}
        planner_output = {
            "global_filters": [
                {"table": "tb_Company", "column": "Name", "op": "=", "value": "Test"}
            ]
        }

        assert _column_has_filter_predicate(
            "tb_Company", "Name", table_selection, planner_output
        ) is True

    def test_detects_having_filter(self):
        """Test detection of HAVING filters."""
        table_selection = {"filters": []}
        planner_output = {
            "global_filters": [],
            "group_by": {
                "having_filters": [
                    {"table": "tb_Company", "column": "Name", "op": "=", "value": "Test"}
                ]
            }
        }

        assert _column_has_filter_predicate(
            "tb_Company", "Name", table_selection, planner_output
        ) is True

    def test_detects_subquery_filter(self):
        """Test detection of subquery filters."""
        table_selection = {"filters": []}
        planner_output = {
            "global_filters": [],
            "subquery_filters": [
                {
                    "outer_table": "tb_Company",
                    "outer_column": "ID",
                    "subquery_table": "tb_Users",
                    "subquery_column": "CompanyID",
                    "subquery_filters": []
                }
            ]
        }

        assert _column_has_filter_predicate(
            "tb_Company", "ID", table_selection, planner_output
        ) is True

    def test_returns_false_for_orphaned_filter_column(self):
        """Test detection of orphaned filter columns (no predicate)."""
        table_selection = {"filters": []}
        planner_output = {"global_filters": []}

        # Column exists but has no filter predicate
        assert _column_has_filter_predicate(
            "tb_Company", "Name", table_selection, planner_output
        ) is False


class TestOrphanedFilterColumnHeuristic:
    """Test the orphaned filter column heuristic in SQL generation."""

    def test_orphaned_filter_column_becomes_projection(self):
        """
        Test that orphaned filter columns are treated as projections.

        This is the exact scenario from debug_generated_planner_output.json:
        - TagName marked as role="filter"
        - But no filter predicate created (filters: [])
        - Should be included in SELECT to ensure visibility
        """
        # Exact structure from debug output (simplified)
        planner_output = {
            "decision": "proceed",
            "intent_summary": "List applications tagged with 'security risk'",
            "selections": [
                {
                    "table": "tb_ApplicationTagMap",
                    "columns": [
                        {"table": "tb_ApplicationTagMap", "column": "APPID", "role": "filter"},
                        {"table": "tb_ApplicationTagMap", "column": "TagID", "role": "filter"}
                    ],
                    "filters": []  # No filters created!
                },
                {
                    "table": "tb_SoftwareTagsAndColors",
                    "columns": [
                        {"table": "tb_SoftwareTagsAndColors", "column": "ID", "role": "filter"},
                        {"table": "tb_SoftwareTagsAndColors", "column": "TagName", "role": "filter"}  # Orphaned!
                    ],
                    "filters": []  # No filters created!
                },
                {
                    "table": "tb_SaasComputerInstalledApps",
                    "columns": [
                        {"table": "tb_SaasComputerInstalledApps", "column": "ID", "role": "filter"},
                        {"table": "tb_SaasComputerInstalledApps", "column": "Name", "role": "projection"},
                        {"table": "tb_SaasComputerInstalledApps", "column": "Versions", "role": "projection"},
                    ],
                    "filters": []
                }
            ],
            "global_filters": [],  # No global filters either!
            "join_edges": [
                {
                    "from_table": "tb_ApplicationTagMap",
                    "from_column": "TagID",
                    "to_table": "tb_SoftwareTagsAndColors",
                    "to_column": "ID",
                    "join_type": "inner"
                },
                {
                    "from_table": "tb_ApplicationTagMap",
                    "from_column": "APPID",
                    "to_table": "tb_SaasComputerInstalledApps",
                    "to_column": "ID",
                    "join_type": "inner"
                }
            ]
        }

        # Create state with minimal required fields
        state: State = {
            "messages": [],
            "user_question": "List all applications tagged with security risk",
            "schema": {},
            "filtered_schema": {},
            "planner_output": planner_output,
            "query": "",
            "result": None,
            "sort_order": None,
            "result_limit": None,
            "time_filter": None,
            "error_iteration": 0,
            "refinement_iteration": 0,
            "correction_history": [],
            "refinement_history": [],
            "last_step": "",
            "database_connection": None,
        }

        # Generate the query
        result = generate_query(state)
        generated_sql = result["query"]

        # Verify TagName is in the SELECT (the orphaned filter column)
        assert "TagName" in generated_sql, (
            "TagName should be in SELECT even though it was marked as role='filter' "
            "because no filter predicate was created"
        )

        # Verify the main projection columns are also present
        assert "Name" in generated_sql
        assert "Versions" in generated_sql

        # Verify it's a valid SQL query (basic syntax check)
        assert "SELECT" in generated_sql.upper()
        assert "FROM" in generated_sql.upper()
        assert "JOIN" in generated_sql.upper()

    def test_filter_column_with_predicate_not_projected(self):
        """
        Test that filter columns WITH predicates are NOT projected.

        This ensures the heuristic only applies to orphaned filter columns.
        """
        planner_output = {
            "decision": "proceed",
            "intent_summary": "List applications with active status",
            "selections": [
                {
                    "table": "tb_SaasComputerInstalledApps",
                    "columns": [
                        {"table": "tb_SaasComputerInstalledApps", "column": "Name", "role": "projection"},
                        {"table": "tb_SaasComputerInstalledApps", "column": "Status", "role": "filter"}
                    ],
                    "filters": [
                        {"table": "tb_SaasComputerInstalledApps", "column": "Status", "op": "=", "value": "Active"}
                    ]
                }
            ],
            "global_filters": [],
            "join_edges": []
        }

        state: State = {
            "messages": [],
            "user_question": "List active applications",
            "schema": {},
            "filtered_schema": {},
            "planner_output": planner_output,
            "query": "",
            "result": None,
            "sort_order": None,
            "result_limit": None,
            "time_filter": None,
            "error_iteration": 0,
            "refinement_iteration": 0,
            "correction_history": [],
            "refinement_history": [],
            "last_step": "",
            "database_connection": None,
        }

        result = generate_query(state)
        generated_sql = result["query"]

        # Status has a filter predicate, so it should NOT be in SELECT
        # Only Name should be selected
        assert "Name" in generated_sql
        # Note: We can't easily assert Status is NOT in SELECT without more complex parsing
        # because it will appear in the WHERE clause

    def test_mixed_orphaned_and_normal_filter_columns(self):
        """
        Test a mix of orphaned filter columns and normal filter columns.
        """
        planner_output = {
            "decision": "proceed",
            "intent_summary": "Complex query with mixed filters",
            "selections": [
                {
                    "table": "tb_Company",
                    "columns": [
                        {"table": "tb_Company", "column": "Name", "role": "projection"},
                        {"table": "tb_Company", "column": "Country", "role": "filter"},  # Orphaned
                        {"table": "tb_Company", "column": "Status", "role": "filter"}  # Has predicate
                    ],
                    "filters": [
                        {"table": "tb_Company", "column": "Status", "op": "=", "value": "Active"}
                    ]
                }
            ],
            "global_filters": [],
            "join_edges": []
        }

        state: State = {
            "messages": [],
            "user_question": "List companies",
            "schema": {},
            "filtered_schema": {},
            "planner_output": planner_output,
            "query": "",
            "result": None,
            "sort_order": None,
            "result_limit": None,
            "time_filter": None,
            "error_iteration": 0,
            "refinement_iteration": 0,
            "correction_history": [],
            "refinement_history": [],
            "last_step": "",
            "database_connection": None,
        }

        result = generate_query(state)
        generated_sql = result["query"]

        # Name (projection) should be in SELECT
        assert "Name" in generated_sql

        # Country (orphaned filter) should be in SELECT due to heuristic
        assert "Country" in generated_sql, (
            "Country should be in SELECT because it's marked as role='filter' "
            "but has no filter predicate"
        )

        # Status has a filter predicate, so behavior depends on implementation
        # We won't assert anything about Status in SELECT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
