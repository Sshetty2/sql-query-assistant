"""
Unit tests for plan patching - Integration scenarios.

Tests cover:
- Sequential patch application (column → sort → limit)
- Multiple patches of the same type
- Undo/redo workflows
- Complex multi-table scenarios
- Batch processing
- Error recovery
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
                    {"table": "tracks", "column": "Name", "role": "projection"}
                ]
            }
        ],
        "join_edges": [],
        "order_by": [],
        "limit": None
    }


@pytest.fixture
def multi_table_plan():
    """Sample plan with tracks and genres tables joined."""
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


class TestSequentialPatches:
    """Tests for applying multiple patches sequentially."""

    def test_add_column_then_sort_by_it(self, sample_plan, sample_schema):
        """Test adding a column then sorting by it."""
        # Step 1: Add Milliseconds column
        patch1 = {
            "operation": "add_column",
            "table": "tracks",
            "column": "Milliseconds"
        }
        result1 = apply_patch_operation(sample_plan, patch1, sample_schema)

        # Step 2: Sort by Milliseconds
        patch2 = {
            "operation": "modify_order_by",
            "order_by": [
                {"table": "tracks", "column": "Milliseconds", "direction": "DESC"}
            ]
        }
        result2 = apply_patch_operation(result1, patch2, sample_schema)

        # Verify both modifications applied
        tracks = next(s for s in result2["selections"] if s["table"] == "tracks")
        column_names = [c["column"] for c in tracks["columns"] if c["role"] == "projection"]

        assert "Milliseconds" in column_names
        assert len(result2["order_by"]) == 1
        assert result2["order_by"][0]["column"] == "Milliseconds"
        assert result2["order_by"][0]["direction"] == "DESC"

    def test_add_column_sort_limit(self, sample_plan, sample_schema):
        """Test complete workflow: add column → sort → limit."""
        # Step 1: Add Composer
        patch1 = {"operation": "add_column", "table": "tracks", "column": "Composer"}
        result1 = apply_patch_operation(sample_plan, patch1, sample_schema)

        # Step 2: Add Milliseconds
        patch2 = {"operation": "add_column", "table": "tracks", "column": "Milliseconds"}
        result2 = apply_patch_operation(result1, patch2, sample_schema)

        # Step 3: Sort by Milliseconds DESC
        patch3 = {
            "operation": "modify_order_by",
            "order_by": [{"table": "tracks", "column": "Milliseconds", "direction": "DESC"}]
        }
        result3 = apply_patch_operation(result2, patch3, sample_schema)

        # Step 4: Add LIMIT 10
        patch4 = {"operation": "modify_limit", "limit": 10}
        result4 = apply_patch_operation(result3, patch4, sample_schema)

        # Verify all modifications
        tracks = next(s for s in result4["selections"] if s["table"] == "tracks")
        column_names = [c["column"] for c in tracks["columns"] if c["role"] == "projection"]

        assert "Composer" in column_names
        assert "Milliseconds" in column_names
        assert len(result4["order_by"]) == 1
        assert result4["order_by"][0]["column"] == "Milliseconds"
        assert result4["limit"] == 10

    def test_modify_sort_then_limit(self, sample_plan, sample_schema):
        """Test sorting then limiting results."""
        # Step 1: Sort by Name ASC
        patch1 = {
            "operation": "modify_order_by",
            "order_by": [{"table": "tracks", "column": "Name", "direction": "ASC"}]
        }
        result1 = apply_patch_operation(sample_plan, patch1, sample_schema)

        # Step 2: Limit to 50
        patch2 = {"operation": "modify_limit", "limit": 50}
        result2 = apply_patch_operation(result1, patch2, sample_schema)

        assert len(result2["order_by"]) == 1
        assert result2["order_by"][0]["column"] == "Name"
        assert result2["limit"] == 50

    def test_change_limit_then_sort_then_change_limit_again(self, sample_plan, sample_schema):
        """Test modifying limit, adding sort, then changing limit again."""
        # Step 1: Set limit to 100
        patch1 = {"operation": "modify_limit", "limit": 100}
        result1 = apply_patch_operation(sample_plan, patch1, sample_schema)
        assert result1["limit"] == 100

        # Step 2: Add sorting
        patch2 = {
            "operation": "modify_order_by",
            "order_by": [{"table": "tracks", "column": "Name", "direction": "ASC"}]
        }
        result2 = apply_patch_operation(result1, patch2, sample_schema)

        # Step 3: Change limit to 25
        patch3 = {"operation": "modify_limit", "limit": 25}
        result3 = apply_patch_operation(result2, patch3, sample_schema)

        # Final limit should be 25, sort should remain
        assert result3["limit"] == 25
        assert len(result3["order_by"]) == 1


class TestUndoRedoWorkflows:
    """Tests for undo/redo-like workflows."""

    def test_add_then_remove_column(self, sample_plan, sample_schema):
        """Test adding a column then removing it (undo)."""
        # Add Composer
        patch1 = {"operation": "add_column", "table": "tracks", "column": "Composer"}
        result1 = apply_patch_operation(sample_plan, patch1, sample_schema)

        tracks = next(s for s in result1["selections"] if s["table"] == "tracks")
        column_names = [c["column"] for c in tracks["columns"] if c["role"] == "projection"]
        assert "Composer" in column_names

        # Remove Composer (undo)
        patch2 = {"operation": "remove_column", "table": "tracks", "column": "Composer"}
        result2 = apply_patch_operation(result1, patch2, sample_schema)

        tracks = next(s for s in result2["selections"] if s["table"] == "tracks")
        column_names = [c["column"] for c in tracks["columns"] if c["role"] == "projection"]
        assert "Composer" not in column_names

    def test_set_limit_then_change_limit(self, sample_plan, sample_schema):
        """Test setting limit then changing it."""
        # Set limit
        patch1 = {"operation": "modify_limit", "limit": 50}
        result1 = apply_patch_operation(sample_plan, patch1, sample_schema)
        assert result1["limit"] == 50

        # Change limit to different value
        patch2 = {"operation": "modify_limit", "limit": 100}
        result2 = apply_patch_operation(result1, patch2, sample_schema)
        assert result2["limit"] == 100

    def test_add_sort_then_remove_sort(self, sample_plan, sample_schema):
        """Test adding sorting then removing it."""
        # Add sorting
        patch1 = {
            "operation": "modify_order_by",
            "order_by": [{"table": "tracks", "column": "Name", "direction": "ASC"}]
        }
        result1 = apply_patch_operation(sample_plan, patch1, sample_schema)
        assert len(result1["order_by"]) == 1

        # Remove sorting
        patch2 = {"operation": "modify_order_by", "order_by": []}
        result2 = apply_patch_operation(result1, patch2, sample_schema)
        assert result2["order_by"] == []


class TestMultipleModificationsSameType:
    """Tests for applying multiple patches of the same type."""

    def test_add_multiple_columns_sequentially(self, sample_plan, sample_schema):
        """Test adding several columns one by one."""
        columns_to_add = ["Composer", "Milliseconds", "UnitPrice", "AlbumId"]

        result = sample_plan
        for column in columns_to_add:
            patch = {"operation": "add_column", "table": "tracks", "column": column}
            result = apply_patch_operation(result, patch, sample_schema)

        tracks = next(s for s in result["selections"] if s["table"] == "tracks")
        column_names = [c["column"] for c in tracks["columns"] if c["role"] == "projection"]

        for column in columns_to_add:
            assert column in column_names

    def test_remove_multiple_columns_sequentially(self, sample_plan, sample_schema):
        """Test removing multiple columns one by one."""
        # First add some columns
        patch1 = {"operation": "add_column", "table": "tracks", "column": "Composer"}
        result1 = apply_patch_operation(sample_plan, patch1, sample_schema)

        patch2 = {"operation": "add_column", "table": "tracks", "column": "Milliseconds"}
        result2 = apply_patch_operation(result1, patch2, sample_schema)

        # Now remove them
        patch3 = {"operation": "remove_column", "table": "tracks", "column": "Composer"}
        result3 = apply_patch_operation(result2, patch3, sample_schema)

        patch4 = {"operation": "remove_column", "table": "tracks", "column": "Milliseconds"}
        result4 = apply_patch_operation(result3, patch4, sample_schema)

        tracks = next(s for s in result4["selections"] if s["table"] == "tracks")
        column_names = [c["column"] for c in tracks["columns"] if c["role"] == "projection"]

        assert "Composer" not in column_names
        assert "Milliseconds" not in column_names

    def test_change_sort_multiple_times(self, sample_plan, sample_schema):
        """Test changing sort order multiple times."""
        # Sort by Name ASC
        patch1 = {
            "operation": "modify_order_by",
            "order_by": [{"table": "tracks", "column": "Name", "direction": "ASC"}]
        }
        result1 = apply_patch_operation(sample_plan, patch1, sample_schema)

        # Add Milliseconds column first
        patch_add = {"operation": "add_column", "table": "tracks", "column": "Milliseconds"}
        result1b = apply_patch_operation(result1, patch_add, sample_schema)

        # Change to sort by Milliseconds DESC
        patch2 = {
            "operation": "modify_order_by",
            "order_by": [{"table": "tracks", "column": "Milliseconds", "direction": "DESC"}]
        }
        result2 = apply_patch_operation(result1b, patch2, sample_schema)

        # Change to multi-column sort
        patch3 = {
            "operation": "modify_order_by",
            "order_by": [
                {"table": "tracks", "column": "Name", "direction": "ASC"},
                {"table": "tracks", "column": "Milliseconds", "direction": "DESC"}
            ]
        }
        result3 = apply_patch_operation(result2, patch3, sample_schema)

        # Final sort should be multi-column
        assert len(result3["order_by"]) == 2
        assert result3["order_by"][0]["column"] == "Name"
        assert result3["order_by"][1]["column"] == "Milliseconds"


class TestMultiTableIntegration:
    """Tests for complex scenarios with multiple tables."""

    def test_add_columns_from_different_tables(self, multi_table_plan, sample_schema):
        """Test adding columns from both tables in a join."""
        # Add column from tracks
        patch1 = {"operation": "add_column", "table": "tracks", "column": "Composer"}
        result1 = apply_patch_operation(multi_table_plan, patch1, sample_schema)

        # Add GenreId as projection (promote from filter)
        patch2 = {"operation": "add_column", "table": "genres", "column": "GenreId"}
        result2 = apply_patch_operation(result1, patch2, sample_schema)

        # Verify both additions
        tracks = next(s for s in result2["selections"] if s["table"] == "tracks")
        genres = next(s for s in result2["selections"] if s["table"] == "genres")

        tracks_cols = [c["column"] for c in tracks["columns"] if c["role"] == "projection"]
        genres_cols = [c["column"] for c in genres["columns"] if c["role"] == "projection"]

        assert "Composer" in tracks_cols
        assert "GenreId" in genres_cols

    def test_sort_by_different_tables(self, multi_table_plan, sample_schema):
        """Test sorting by columns from different tables."""
        patch = {
            "operation": "modify_order_by",
            "order_by": [
                {"table": "genres", "column": "Name", "direction": "ASC"},
                {"table": "tracks", "column": "Name", "direction": "ASC"}
            ]
        }

        result = apply_patch_operation(multi_table_plan, patch, sample_schema)

        assert len(result["order_by"]) == 2
        assert result["order_by"][0]["table"] == "genres"
        assert result["order_by"][1]["table"] == "tracks"

    def test_complete_workflow_multi_table(self, multi_table_plan, sample_schema):
        """Test complete workflow with multiple tables."""
        # Step 1: Add Composer to tracks
        patch1 = {"operation": "add_column", "table": "tracks", "column": "Composer"}
        result1 = apply_patch_operation(multi_table_plan, patch1, sample_schema)

        # Step 2: Remove genres.Name
        patch2 = {"operation": "remove_column", "table": "genres", "column": "Name"}
        result2 = apply_patch_operation(result1, patch2, sample_schema)

        # Step 3: Sort by tracks.Name
        patch3 = {
            "operation": "modify_order_by",
            "order_by": [{"table": "tracks", "column": "Name", "direction": "ASC"}]
        }
        result3 = apply_patch_operation(result2, patch3, sample_schema)

        # Step 4: Limit to 20
        patch4 = {"operation": "modify_limit", "limit": 20}
        result4 = apply_patch_operation(result3, patch4, sample_schema)

        # Verify all modifications
        tracks = next(s for s in result4["selections"] if s["table"] == "tracks")
        genres = next(s for s in result4["selections"] if s["table"] == "genres")

        tracks_cols = [c["column"] for c in tracks["columns"] if c["role"] == "projection"]
        genres_cols = [c["column"] for c in genres["columns"] if c["role"] == "projection"]

        assert "Composer" in tracks_cols
        assert "Name" not in genres_cols
        assert len(result4["order_by"]) == 1
        assert result4["limit"] == 20


class TestBatchScenarios:
    """Tests simulating batch patch application."""

    def test_batch_five_modifications(self, sample_plan, sample_schema):
        """Test applying 5 modifications in sequence (simulating batch)."""
        patches = [
            {"operation": "add_column", "table": "tracks", "column": "Composer"},
            {"operation": "add_column", "table": "tracks", "column": "Milliseconds"},
            {"operation": "add_column", "table": "tracks", "column": "UnitPrice"},
            {
                "operation": "modify_order_by",
                "order_by": [{"table": "tracks", "column": "Milliseconds", "direction": "DESC"}]
            },
            {"operation": "modify_limit", "limit": 15}
        ]

        result = sample_plan
        for patch in patches:
            result = apply_patch_operation(result, patch, sample_schema)

        # Verify all modifications applied
        tracks = next(s for s in result["selections"] if s["table"] == "tracks")
        column_names = [c["column"] for c in tracks["columns"] if c["role"] == "projection"]

        assert "Composer" in column_names
        assert "Milliseconds" in column_names
        assert "UnitPrice" in column_names
        assert len(result["order_by"]) == 1
        assert result["order_by"][0]["column"] == "Milliseconds"
        assert result["limit"] == 15

    def test_batch_add_remove_cycle(self, sample_plan, sample_schema):
        """Test batch with add/remove cycles."""
        patches = [
            {"operation": "add_column", "table": "tracks", "column": "Composer"},
            {"operation": "add_column", "table": "tracks", "column": "Milliseconds"},
            {"operation": "remove_column", "table": "tracks", "column": "Name"},
            {"operation": "add_column", "table": "tracks", "column": "UnitPrice"},
            {"operation": "remove_column", "table": "tracks", "column": "Composer"}
        ]

        result = sample_plan
        for patch in patches:
            result = apply_patch_operation(result, patch, sample_schema)

        tracks = next(s for s in result["selections"] if s["table"] == "tracks")
        column_names = [c["column"] for c in tracks["columns"] if c["role"] == "projection"]

        # Final state: TrackId, Milliseconds, UnitPrice (removed Name and Composer)
        assert "TrackId" in column_names
        assert "Name" not in column_names
        assert "Composer" not in column_names
        assert "Milliseconds" in column_names
        assert "UnitPrice" in column_names


class TestComplexWorkflows:
    """Tests for realistic complex user workflows."""

    def test_exploration_workflow(self, sample_plan, sample_schema):
        """Test user exploring data: add columns, sort, limit, then refine."""
        # Initial exploration: add several columns
        patch1 = {"operation": "add_column", "table": "tracks", "column": "Composer"}
        result1 = apply_patch_operation(sample_plan, patch1, sample_schema)

        patch2 = {"operation": "add_column", "table": "tracks", "column": "Milliseconds"}
        result2 = apply_patch_operation(result1, patch2, sample_schema)

        patch3 = {"operation": "add_column", "table": "tracks", "column": "UnitPrice"}
        result3 = apply_patch_operation(result2, patch3, sample_schema)

        # Sort by Milliseconds to see longest tracks
        patch4 = {
            "operation": "modify_order_by",
            "order_by": [{"table": "tracks", "column": "Milliseconds", "direction": "DESC"}]
        }
        result4 = apply_patch_operation(result3, patch4, sample_schema)

        # Limit to top 10
        patch5 = {"operation": "modify_limit", "limit": 10}
        result5 = apply_patch_operation(result4, patch5, sample_schema)

        # User decides they don't need Composer, remove it
        patch6 = {"operation": "remove_column", "table": "tracks", "column": "Composer"}
        result6 = apply_patch_operation(result5, patch6, sample_schema)

        # Final verification
        tracks = next(s for s in result6["selections"] if s["table"] == "tracks")
        column_names = [c["column"] for c in tracks["columns"] if c["role"] == "projection"]

        assert "Composer" not in column_names
        assert "Milliseconds" in column_names
        assert "UnitPrice" in column_names
        assert result6["limit"] == 10
        assert result6["order_by"][0]["column"] == "Milliseconds"

    def test_refinement_workflow(self, sample_plan, sample_schema):
        """Test user refining query: start simple, add details progressively."""
        # Start with basic query (already has TrackId, Name)
        result = sample_plan

        # Add price to compare
        patch1 = {"operation": "add_column", "table": "tracks", "column": "UnitPrice"}
        result = apply_patch_operation(result, patch1, sample_schema)

        # Sort by price to find expensive tracks
        patch2 = {
            "operation": "modify_order_by",
            "order_by": [{"table": "tracks", "column": "UnitPrice", "direction": "DESC"}]
        }
        result = apply_patch_operation(result, patch2, sample_schema)

        # Limit to top 5
        patch3 = {"operation": "modify_limit", "limit": 5}
        result = apply_patch_operation(result, patch3, sample_schema)

        # Change mind, want to see cheapest instead
        patch4 = {
            "operation": "modify_order_by",
            "order_by": [{"table": "tracks", "column": "UnitPrice", "direction": "ASC"}]
        }
        result = apply_patch_operation(result, patch4, sample_schema)

        # Increase limit to top 20
        patch5 = {"operation": "modify_limit", "limit": 20}
        result = apply_patch_operation(result, patch5, sample_schema)

        # Final state
        assert result["order_by"][0]["direction"] == "ASC"
        assert result["limit"] == 20


class TestEdgeCasesIntegration:
    """Tests for edge cases in integrated scenarios."""

    def test_remove_all_projections_then_add_back(self, sample_plan, sample_schema):
        """Test removing all projection columns then adding some back."""
        # Remove Name
        patch1 = {"operation": "remove_column", "table": "tracks", "column": "Name"}
        result1 = apply_patch_operation(sample_plan, patch1, sample_schema)

        # Remove TrackId
        patch2 = {"operation": "remove_column", "table": "tracks", "column": "TrackId"}
        result2 = apply_patch_operation(result1, patch2, sample_schema)

        # Should have no projection columns now
        tracks = next(s for s in result2["selections"] if s["table"] == "tracks")
        projection_cols = [c for c in tracks["columns"] if c["role"] == "projection"]
        assert len(projection_cols) == 0

        # Add back Composer and Milliseconds
        patch3 = {"operation": "add_column", "table": "tracks", "column": "Composer"}
        result3 = apply_patch_operation(result2, patch3, sample_schema)

        patch4 = {"operation": "add_column", "table": "tracks", "column": "Milliseconds"}
        result4 = apply_patch_operation(result3, patch4, sample_schema)

        # Should have new projection columns
        tracks = next(s for s in result4["selections"] if s["table"] == "tracks")
        column_names = [c["column"] for c in tracks["columns"] if c["role"] == "projection"]
        assert "Composer" in column_names
        assert "Milliseconds" in column_names

    def test_sort_by_column_not_in_projection(self, sample_schema):
        """Test sorting by a column that's not in projection."""
        # Create plan with Milliseconds as filter-only
        plan = {
            "intent_summary": "Show tracks",
            "decision": "proceed",
            "selections": [
                {
                    "table": "tracks",
                    "alias": "t",
                    "columns": [
                        {"name": "TrackId", "role": "projection"},
                        {"name": "Name", "role": "projection"},
                        {"name": "Milliseconds", "role": "filter"}
                    ]
                }
            ],
            "join_edges": [],
            "filters": [],
            "order_by": [],
            "limit": None
        }

        # Try to sort by Milliseconds (exists but not projection)
        patch = {
            "operation": "modify_order_by",
            "order_by": [{"table": "tracks", "column": "Milliseconds", "direction": "DESC"}]
        }

        result = apply_patch_operation(plan, patch, sample_schema)

        # Should work - sorting by filter column is valid
        assert len(result["order_by"]) == 1
        assert result["order_by"][0]["column"] == "Milliseconds"

    def test_plan_immutability_through_chain(self, sample_plan, sample_schema):
        """Test that original plan remains unchanged through chain of patches."""
        import copy
        original_plan = copy.deepcopy(sample_plan)

        # Apply chain of patches
        patch1 = {"operation": "add_column", "table": "tracks", "column": "Composer"}
        result1 = apply_patch_operation(sample_plan, patch1, sample_schema)

        patch2 = {"operation": "modify_order_by", "order_by": [{"table": "tracks", "column": "Name", "direction": "ASC"}]}  # noqa: E501
        result2 = apply_patch_operation(result1, patch2, sample_schema)

        patch3 = {"operation": "modify_limit", "limit": 50}
        result3 = apply_patch_operation(result2, patch3, sample_schema)

        # Original should be completely unchanged
        assert sample_plan == original_plan

        # Each intermediate result should be different
        assert result1 != original_plan
        assert result2 != result1
        assert result3 != result2
