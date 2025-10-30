"""
Unit tests for plan patching - ORDER BY modifications (modify_order_by).

Tests cover:
- Adding ORDER BY to queries without sorting
- Changing existing ORDER BY columns and directions
- Multiple column sorting
- Removing ORDER BY
- Validation and error handling
"""

import pytest
from agent.transform_plan import apply_patch_operation


@pytest.fixture
def sample_plan():
    """Sample plan with tracks table."""
    return {
        "intent_summary": "Show tracks",
        "decision": "proceed",
        "selections": [
            {
                "table": "tracks",
                "alias": "t",
                "columns": [
                    {"table": "tracks", "column": "TrackId", "role": "projection"},
                    {"table": "tracks", "column": "Name", "role": "projection"},
                    {"table": "tracks", "column": "Milliseconds", "role": "projection"},
                    {"table": "tracks", "column": "UnitPrice", "role": "projection"}
                ]
            }
        ],
        "join_edges": [],
        "filters": [],
        "order_by": [],
        "limit": None
    }


@pytest.fixture
def sample_schema():
    """Sample schema for tracks table."""
    return [
        {
            "table_name": "tracks",
            "columns": [
                {"column_name": "TrackId", "data_type": "INTEGER"},
                {"column_name": "Name", "data_type": "NVARCHAR"},
                {"column_name": "Milliseconds", "data_type": "INTEGER"},
                {"column_name": "UnitPrice", "data_type": "NUMERIC"}
            ]
        }
    ]


class TestAddOrderBy:
    """Tests for adding ORDER BY to queries."""

    def test_add_single_column_asc(self, sample_plan, sample_schema):
        """Test adding simple ascending ORDER BY."""
        patch = {
            "operation": "modify_order_by",
            "order_by": [
                {"table": "tracks", "column": "Name", "direction": "ASC"}
            ]
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        assert len(result["order_by"]) == 1
        assert result["order_by"][0]["table"] == "tracks"
        assert result["order_by"][0]["column"] == "Name"
        assert result["order_by"][0]["direction"] == "ASC"

    def test_add_single_column_desc(self, sample_plan, sample_schema):
        """Test adding descending ORDER BY."""
        patch = {
            "operation": "modify_order_by",
            "order_by": [
                {"table": "tracks", "column": "Milliseconds", "direction": "DESC"}
            ]
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        assert len(result["order_by"]) == 1
        assert result["order_by"][0]["column"] == "Milliseconds"
        assert result["order_by"][0]["direction"] == "DESC"

    def test_add_multiple_columns(self, sample_plan, sample_schema):
        """Test adding ORDER BY with multiple columns."""
        patch = {
            "operation": "modify_order_by",
            "order_by": [
                {"table": "tracks", "column": "Name", "direction": "ASC"},
                {"table": "tracks", "column": "Milliseconds", "direction": "DESC"}
            ]
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        assert len(result["order_by"]) == 2
        assert result["order_by"][0]["column"] == "Name"
        assert result["order_by"][0]["direction"] == "ASC"
        assert result["order_by"][1]["column"] == "Milliseconds"
        assert result["order_by"][1]["direction"] == "DESC"


class TestModifyOrderBy:
    """Tests for modifying existing ORDER BY."""

    def test_change_sort_column(self, sample_plan, sample_schema):
        """Test changing which column is used for sorting."""
        # First add ORDER BY Name
        sample_plan["order_by"] = [
            {"table": "tracks", "column": "Name", "direction": "ASC"}
        ]

        # Change to ORDER BY Milliseconds
        patch = {
            "operation": "modify_order_by",
            "order_by": [
                {"table": "tracks", "column": "Milliseconds", "direction": "ASC"}
            ]
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        assert len(result["order_by"]) == 1
        assert result["order_by"][0]["column"] == "Milliseconds"

    def test_change_sort_direction(self, sample_plan, sample_schema):
        """Test changing sort direction from ASC to DESC."""
        # Start with ASC
        sample_plan["order_by"] = [
            {"table": "tracks", "column": "Name", "direction": "ASC"}
        ]

        # Change to DESC
        patch = {
            "operation": "modify_order_by",
            "order_by": [
                {"table": "tracks", "column": "Name", "direction": "DESC"}
            ]
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        assert result["order_by"][0]["direction"] == "DESC"

    def test_add_secondary_sort(self, sample_plan, sample_schema):
        """Test adding a secondary sort column."""
        # Start with single column sort
        sample_plan["order_by"] = [
            {"table": "tracks", "column": "Name", "direction": "ASC"}
        ]

        # Add secondary sort
        patch = {
            "operation": "modify_order_by",
            "order_by": [
                {"table": "tracks", "column": "Name", "direction": "ASC"},
                {"table": "tracks", "column": "TrackId", "direction": "ASC"}
            ]
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        assert len(result["order_by"]) == 2
        assert result["order_by"][1]["column"] == "TrackId"


class TestRemoveOrderBy:
    """Tests for removing ORDER BY."""

    def test_remove_order_by_empty_list(self, sample_plan, sample_schema):
        """Test removing ORDER BY by providing empty list."""
        # Start with ORDER BY
        sample_plan["order_by"] = [
            {"table": "tracks", "column": "Name", "direction": "ASC"}
        ]

        # Remove by providing empty list
        patch = {
            "operation": "modify_order_by",
            "order_by": []
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        assert result["order_by"] == []

    def test_remove_order_by_null(self, sample_plan, sample_schema):
        """Test removing ORDER BY by providing null."""
        # Start with ORDER BY
        sample_plan["order_by"] = [
            {"table": "tracks", "column": "Name", "direction": "ASC"}
        ]

        # Remove by providing None (implementation rejects None)
        patch = {
            "operation": "modify_order_by",
            "order_by": None
        }

        # Implementation requires order_by field to not be None
        with pytest.raises(ValueError):
            apply_patch_operation(sample_plan, patch, sample_schema)


class TestOrderByValidation:
    """Tests for ORDER BY validation."""

    def test_order_by_invalid_column(self, sample_plan, sample_schema):
        """Test ORDER BY with column not in schema."""
        patch = {
            "operation": "modify_order_by",
            "order_by": [
                {"table": "tracks", "column": "NonExistentColumn", "direction": "ASC"}
            ]
        }

        with pytest.raises(ValueError, match="Column NonExistentColumn does not exist"):
            apply_patch_operation(sample_plan, patch, sample_schema)

    def test_order_by_invalid_table(self, sample_plan, sample_schema):
        """Test ORDER BY with table not in schema."""
        patch = {
            "operation": "modify_order_by",
            "order_by": [
                {"table": "nonexistent_table", "column": "Name", "direction": "ASC"}
            ]
        }

        with pytest.raises(ValueError, match="does not exist"):
            apply_patch_operation(sample_plan, patch, sample_schema)

    def test_order_by_invalid_direction(self, sample_plan, sample_schema):
        """Test ORDER BY with invalid direction."""
        patch = {
            "operation": "modify_order_by",
            "order_by": [
                {"table": "tracks", "column": "Name", "direction": "INVALID"}
            ]
        }

        # Implementation validates direction
        with pytest.raises(ValueError, match="Invalid sort direction"):
            apply_patch_operation(sample_plan, patch, sample_schema)


class TestMultiTableOrderBy:
    """Tests for ORDER BY with multiple tables."""

    def test_order_by_from_different_tables(self, sample_schema):
        """Test ORDER BY using columns from different joined tables."""
        multi_table_plan = {
            "intent_summary": "Show tracks with genres",
            "decision": "proceed",
            "selections": [
                {
                    "table": "tracks",
                    "alias": "t",
                    "columns": [
                        {"table": "tracks", "column": "TrackId", "role": "projection"},
                        {"table": "tracks", "column": "Name", "role": "projection"}
                    ]
                },
                {
                    "table": "genres",
                    "alias": "g",
                    "columns": [
                        {"table": "genres", "column": "Name", "role": "projection"}
                    ]
                }
            ],
            "join_edges": [
                {
                    "from_table": "tracks",
                    "from_column": "GenreId",
                    "to_table": "genres",
                    "to_column": "GenreId",
                    "join_type": "INNER"
                }
            ],
            "filters": [],
            "order_by": [],
            "limit": None
        }

        # Add genres table to schema
        multi_schema = sample_schema + [
            {
                "table_name": "genres",
                "columns": [
                    {"column_name": "GenreId", "data_type": "INTEGER"},
                    {"column_name": "Name", "data_type": "NVARCHAR"}
                ]
            }
        ]

        # Order by tracks.Name then genres.Name
        patch = {
            "operation": "modify_order_by",
            "order_by": [
                {"table": "tracks", "column": "Name", "direction": "ASC"},
                {"table": "genres", "column": "Name", "direction": "ASC"}
            ]
        }

        result = apply_patch_operation(multi_table_plan, patch, multi_schema)

        assert len(result["order_by"]) == 2
        assert result["order_by"][0]["table"] == "tracks"
        assert result["order_by"][1]["table"] == "genres"


class TestEdgeCases:
    """Tests for edge cases."""

    def test_order_by_with_aggregates(self, sample_schema):
        """Test ORDER BY with aggregated columns."""
        agg_plan = {
            "intent_summary": "Count tracks by genre",
            "decision": "proceed",
            "selections": [
                {
                    "table": "tracks",
                    "alias": "t",
                    "columns": [
                        {"table": "tracks", "column": "GenreId", "role": "projection"},
                        {"table": "tracks", "column": "TrackId", "role": "projection", "aggregate": "COUNT"}
                    ]
                }
            ],
            "join_edges": [],
            "filters": [],
            "group_by": ["GenreId"],
            "order_by": [],
            "limit": None
        }

        # Order by the aggregate
        patch = {
            "operation": "modify_order_by",
            "order_by": [
                {"table": "tracks", "column": "TrackId", "direction": "DESC"}
            ]
        }

        result = apply_patch_operation(agg_plan, patch, sample_schema)

        assert len(result["order_by"]) == 1
        assert result["order_by"][0]["column"] == "TrackId"

    def test_plan_immutability(self, sample_plan, sample_schema):
        """Test that original plan is not modified."""
        import copy
        original_plan = copy.deepcopy(sample_plan)

        patch = {
            "operation": "modify_order_by",
            "order_by": [
                {"table": "tracks", "column": "Name", "direction": "DESC"}
            ]
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        # Original should be unchanged
        assert sample_plan == original_plan
        # Result should have ORDER BY
        assert len(result["order_by"]) == 1
