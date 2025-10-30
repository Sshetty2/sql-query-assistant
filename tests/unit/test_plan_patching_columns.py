"""
Unit tests for plan patching - Column modifications (add_column, remove_column).

Tests cover:
- Adding single and multiple columns
- Removing columns with different roles (projection vs filter)
- Error handling for invalid columns/tables
- Edge cases and validation
"""

import pytest
from agent.transform_plan import apply_patch_operation


@pytest.fixture
def sample_plan():
    """Sample plan with tracks and genres tables."""
    return {
        "intent_summary": "Show tracks with genres",
        "decision": "proceed",
        "selections": [
            {
                "table": "tracks",
                "alias": "t",
                "columns": [
                    {"table": "tracks", "column": "TrackId", "role": "projection"},
                    {"table": "tracks", "column": "Name", "role": "projection"},
                    {"table": "tracks", "column": "GenreId", "role": "filter"}
                ]
            },
            {
                "table": "genres",
                "alias": "g",
                "columns": [
                    {"table": "genres", "column": "GenreId", "role": "filter"},
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


@pytest.fixture
def sample_schema():
    """Sample schema for tracks and genres tables."""
    return [
        {
            "table_name": "tracks",
            "columns": [
                {"column_name": "TrackId", "data_type": "INTEGER"},
                {"column_name": "Name", "data_type": "NVARCHAR"},
                {"column_name": "AlbumId", "data_type": "INTEGER"},
                {"column_name": "GenreId", "data_type": "INTEGER"},
                {"column_name": "Composer", "data_type": "NVARCHAR"},
                {"column_name": "Milliseconds", "data_type": "INTEGER"},
                {"column_name": "Bytes", "data_type": "INTEGER"},
                {"column_name": "UnitPrice", "data_type": "NUMERIC"}
            ]
        },
        {
            "table_name": "genres",
            "columns": [
                {"column_name": "GenreId", "data_type": "INTEGER"},
                {"column_name": "Name", "data_type": "NVARCHAR"}
            ]
        }
    ]


class TestAddColumn:
    """Tests for add_column operation."""

    def test_add_single_column(self, sample_plan, sample_schema):
        """Test adding a single column to a table."""
        patch = {
            "operation": "add_column",
            "table": "tracks",
            "column": "Composer"
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        # Find tracks table
        tracks_selection = next(s for s in result["selections"] if s["table"] == "tracks")
        column_names = [c["column"] for c in tracks_selection["columns"]]

        assert "Composer" in column_names
        composer_col = next(c for c in tracks_selection["columns"] if c["column"] == "Composer")
        assert composer_col["role"] == "projection"

    def test_add_multiple_columns_sequentially(self, sample_plan, sample_schema):
        """Test adding multiple columns one by one."""
        # Add Composer
        patch1 = {"operation": "add_column", "table": "tracks", "column": "Composer"}
        result1 = apply_patch_operation(sample_plan, patch1, sample_schema)

        # Add Milliseconds
        patch2 = {"operation": "add_column", "table": "tracks", "column": "Milliseconds"}
        result2 = apply_patch_operation(result1, patch2, sample_schema)

        tracks_selection = next(s for s in result2["selections"] if s["table"] == "tracks")
        column_names = [c["column"] for c in tracks_selection["columns"]]

        assert "Composer" in column_names
        assert "Milliseconds" in column_names

    def test_add_column_to_different_table(self, sample_plan, sample_schema):
        """Test adding a column to a different table in the plan."""
        # genres table only has GenreId (filter) and Name (projection)
        # This should work since genres is in the schema
        patch = {
            "operation": "add_column",
            "table": "genres",
            "column": "GenreId"  # Already exists as filter, should work
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        genres_selection = next(s for s in result["selections"] if s["table"] == "genres")
        # GenreId should now be projection (promoted from filter)
        genreid_col = next(c for c in genres_selection["columns"] if c["column"] =="GenreId")
        assert genreid_col["role"] == "projection"

    def test_add_column_already_selected(self, sample_plan, sample_schema):
        """Test adding a column that's already selected (should be idempotent)."""
        patch = {
            "operation": "add_column",
            "table": "tracks",
            "column": "Name"  # Already selected
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        tracks_selection = next(s for s in result["selections"] if s["table"] == "tracks")
        name_columns = [c for c in tracks_selection["columns"] if c["column"] =="Name"]

        # Should still have only one Name column
        assert len(name_columns) == 1
        assert name_columns[0]["role"] == "projection"

    def test_add_column_invalid_column(self, sample_plan, sample_schema):
        """Test adding a column that doesn't exist in schema."""
        patch = {
            "operation": "add_column",
            "table": "tracks",
            "column": "NonExistentColumn"
        }

        with pytest.raises(ValueError, match="Column NonExistentColumn does not exist"):
            apply_patch_operation(sample_plan, patch, sample_schema)

    def test_add_column_invalid_table(self, sample_plan, sample_schema):
        """Test adding a column to a table that doesn't exist."""
        patch = {
            "operation": "add_column",
            "table": "nonexistent_table",
            "column": "SomeColumn"
        }

        # Will fail on column validation first (column doesn't exist in schema)
        with pytest.raises(ValueError, match="does not exist"):
            apply_patch_operation(sample_plan, patch, sample_schema)

    def test_add_column_promotes_filter_to_projection(self, sample_plan, sample_schema):
        """Test adding a column that exists as filter-only (should promote to projection)."""
        # GenreId is filter-only in tracks
        patch = {
            "operation": "add_column",
            "table": "tracks",
            "column": "GenreId"
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        tracks_selection = next(s for s in result["selections"] if s["table"] == "tracks")
        genreid_col = next(c for c in tracks_selection["columns"] if c["column"] =="GenreId")

        # Should be promoted to projection
        assert genreid_col["role"] == "projection"


class TestRemoveColumn:
    """Tests for remove_column operation."""

    def test_remove_single_column(self, sample_plan, sample_schema):
        """Test removing a single projection column."""
        patch = {
            "operation": "remove_column",
            "table": "tracks",
            "column": "Name"
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        tracks_selection = next(s for s in result["selections"] if s["table"] == "tracks")
        column_names = [c["column"] for c in tracks_selection["columns"] if c["role"] == "projection"]

        assert "Name" not in column_names

    def test_remove_column_used_in_filter(self, sample_plan, sample_schema):
        """Test removing a column that's used in filters (should change to filter role)."""
        # First add a filter using GenreId to selection-level filters
        tracks_selection = next(s for s in sample_plan["selections"] if s["table"] == "tracks")
        tracks_selection["filters"] = [{
            "column": "GenreId",
            "operator": "=",
            "value": "1"
        }]

        patch = {
            "operation": "remove_column",
            "table": "tracks",
            "column": "GenreId"
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        tracks_selection = next(s for s in result["selections"] if s["table"] == "tracks")
        genreid_col = next((c for c in tracks_selection["columns"] if c["column"] =="GenreId"), None)

        # Should still exist but with filter role
        assert genreid_col is not None
        assert genreid_col["role"] == "filter"

    def test_remove_multiple_columns(self, sample_plan, sample_schema):
        """Test removing multiple columns sequentially."""
        # Add extra columns first
        patch_add1 = {"operation": "add_column", "table": "tracks", "column": "Composer"}
        result1 = apply_patch_operation(sample_plan, patch_add1, sample_schema)

        patch_add2 = {"operation": "add_column", "table": "tracks", "column": "Milliseconds"}
        result2 = apply_patch_operation(result1, patch_add2, sample_schema)

        # Now remove them
        patch_remove1 = {"operation": "remove_column", "table": "tracks", "column": "Composer"}
        result3 = apply_patch_operation(result2, patch_remove1, sample_schema)

        patch_remove2 = {"operation": "remove_column", "table": "tracks", "column": "Milliseconds"}
        result4 = apply_patch_operation(result3, patch_remove2, sample_schema)

        tracks_selection = next(s for s in result4["selections"] if s["table"] == "tracks")
        projection_columns = [c["column"] for c in tracks_selection["columns"] if c["role"] == "projection"]

        assert "Composer" not in projection_columns
        assert "Milliseconds" not in projection_columns

    def test_remove_nonexistent_column(self, sample_plan, sample_schema):
        """Test removing a column that doesn't exist in the selection."""
        patch = {
            "operation": "remove_column",
            "table": "tracks",
            "column": "Composer"  # Not in current selection
        }

        # Should raise ValueError
        with pytest.raises(ValueError, match="Column Composer not found"):
            apply_patch_operation(sample_plan, patch, sample_schema)

    def test_remove_last_projection_column(self, sample_plan, sample_schema):
        """Test removing columns until only filter columns remain."""
        # Remove Name from tracks
        patch1 = {"operation": "remove_column", "table": "tracks", "column": "Name"}
        result1 = apply_patch_operation(sample_plan, patch1, sample_schema)

        # Remove TrackId from tracks
        patch2 = {"operation": "remove_column", "table": "tracks", "column": "TrackId"}
        result2 = apply_patch_operation(result1, patch2, sample_schema)

        tracks_selection = next(s for s in result2["selections"] if s["table"] == "tracks")
        projection_columns = [c for c in tracks_selection["columns"] if c["role"] == "projection"]

        # Should have no projection columns left
        assert len(projection_columns) == 0

        # But should still have filter columns
        filter_columns = [c for c in tracks_selection["columns"] if c["role"] == "filter"]
        assert len(filter_columns) > 0


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_case_insensitive_column_names(self, sample_plan, sample_schema):
        """Test that column names are handled case-insensitively."""
        patch = {
            "operation": "add_column",
            "table": "tracks",
            "column": "composer"  # lowercase
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        tracks_selection = next(s for s in result["selections"] if s["table"] == "tracks")
        # Should find Composer (proper case)
        composer_col = next((c for c in tracks_selection["columns"] if c["column"].lower() == "composer"), None)
        assert composer_col is not None

    def test_empty_plan(self, sample_schema):
        """Test applying patch to plan with no selections."""
        empty_plan = {
            "intent_summary": "Empty plan",
            "decision": "proceed",
            "selections": [],
            "join_edges": [],
            "filters": [],
            "order_by": [],
            "limit": None
        }

        patch = {
            "operation": "add_column",
            "table": "tracks",
            "column": "Name"
        }

        with pytest.raises(ValueError, match="Table tracks not found in plan selections"):
            apply_patch_operation(empty_plan, patch, sample_schema)

    def test_plan_immutability(self, sample_plan, sample_schema):
        """Test that original plan is not modified."""
        import copy
        original_plan = copy.deepcopy(sample_plan)

        patch = {
            "operation": "add_column",
            "table": "tracks",
            "column": "Composer"
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        # Original plan should be unchanged
        assert sample_plan == original_plan
        # Result should be different
        assert result != original_plan
