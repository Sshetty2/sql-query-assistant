"""
Unit tests for plan patching - LIMIT modifications (modify_limit).

Tests cover:
- Adding LIMIT to queries without limits
- Changing existing LIMIT values
- Removing LIMIT
- Edge cases (zero, negative, very large values)
- Validation
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
                {"column_name": "Name", "data_type": "NVARCHAR"}
            ]
        }
    ]


class TestAddLimit:
    """Tests for adding LIMIT to queries."""

    def test_add_limit_to_query_without_limit(self, sample_plan, sample_schema):
        """Test adding LIMIT to a query that doesn't have one."""
        patch = {
            "operation": "modify_limit",
            "limit": 100
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        assert result["limit"] == 100

    def test_add_small_limit(self, sample_plan, sample_schema):
        """Test adding a small LIMIT value."""
        patch = {
            "operation": "modify_limit",
            "limit": 10
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        assert result["limit"] == 10

    def test_add_large_limit(self, sample_plan, sample_schema):
        """Test adding a large LIMIT value."""
        patch = {
            "operation": "modify_limit",
            "limit": 10000
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        assert result["limit"] == 10000

    def test_add_limit_one(self, sample_plan, sample_schema):
        """Test adding LIMIT 1."""
        patch = {
            "operation": "modify_limit",
            "limit": 1
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        assert result["limit"] == 1


class TestModifyLimit:
    """Tests for modifying existing LIMIT."""

    def test_increase_limit(self, sample_plan, sample_schema):
        """Test increasing an existing LIMIT."""
        sample_plan["limit"] = 50

        patch = {
            "operation": "modify_limit",
            "limit": 200
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        assert result["limit"] == 200

    def test_decrease_limit(self, sample_plan, sample_schema):
        """Test decreasing an existing LIMIT."""
        sample_plan["limit"] = 500

        patch = {
            "operation": "modify_limit",
            "limit": 100
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        assert result["limit"] == 100

    def test_change_to_same_value(self, sample_plan, sample_schema):
        """Test changing LIMIT to the same value (idempotent)."""
        sample_plan["limit"] = 100

        patch = {
            "operation": "modify_limit",
            "limit": 100
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        assert result["limit"] == 100


class TestRemoveLimit:
    """Tests for removing LIMIT."""

    def test_remove_limit_with_none(self, sample_plan, sample_schema):
        """Test removing LIMIT by setting it to None."""
        sample_plan["limit"] = 100

        patch = {
            "operation": "modify_limit",
            "limit": None
        }

        # Current implementation rejects None
        with pytest.raises(ValueError):
            apply_patch_operation(sample_plan, patch, sample_schema)

    def test_remove_limit_with_zero(self, sample_plan, sample_schema):
        """Test setting LIMIT to 0 (should reject as invalid)."""
        sample_plan["limit"] = 100

        patch = {
            "operation": "modify_limit",
            "limit": 0
        }

        # Implementation rejects 0 as invalid
        with pytest.raises(ValueError, match="Invalid limit"):
            apply_patch_operation(sample_plan, patch, sample_schema)


class TestEdgeCases:
    """Tests for edge cases and validation."""

    def test_negative_limit(self, sample_plan, sample_schema):
        """Test setting LIMIT to a negative value."""
        patch = {
            "operation": "modify_limit",
            "limit": -10
        }

        # Should either reject or convert to valid value
        try:
            result = apply_patch_operation(sample_plan, patch, sample_schema)
            # If it accepts, should be None or positive
            assert result["limit"] is None or result["limit"] >= 0
        except ValueError:
            # Or it should raise an error
            pass

    def test_very_large_limit(self, sample_plan, sample_schema):
        """Test setting LIMIT to a very large value."""
        patch = {
            "operation": "modify_limit",
            "limit": 999999999
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        assert result["limit"] == 999999999

    def test_float_limit(self, sample_plan, sample_schema):
        """Test setting LIMIT to a float value."""
        patch = {
            "operation": "modify_limit",
            "limit": 10.5
        }

        # Implementation rejects non-integer types
        with pytest.raises(ValueError, match="Invalid limit"):
            apply_patch_operation(sample_plan, patch, sample_schema)

    def test_string_limit(self, sample_plan, sample_schema):
        """Test setting LIMIT to a string value."""
        patch = {
            "operation": "modify_limit",
            "limit": "100"
        }

        # Should either convert to int or reject
        try:
            result = apply_patch_operation(sample_plan, patch, sample_schema)
            # If accepted, should be an int
            assert isinstance(result["limit"], int)
        except (ValueError, TypeError):
            # Or it should raise an error
            pass


class TestLimitWithOtherClauses:
    """Tests for LIMIT in combination with other query clauses."""

    def test_limit_with_order_by(self, sample_plan, sample_schema):
        """Test LIMIT combined with ORDER BY."""
        sample_plan["order_by"] = [
            {"table": "tracks", "column": "Name", "direction": "ASC"}
        ]

        patch = {
            "operation": "modify_limit",
            "limit": 50
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        assert result["limit"] == 50
        assert len(result["order_by"]) == 1

    def test_limit_with_filters(self, sample_plan, sample_schema):
        """Test LIMIT combined with WHERE filters."""
        sample_plan["filters"].append({
            "table": "tracks",
            "column": "Name",
            "operator": "LIKE",
            "value": "%Rock%"
        })

        patch = {
            "operation": "modify_limit",
            "limit": 25
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        assert result["limit"] == 25
        assert len(result["filters"]) == 1

    def test_limit_with_group_by(self, sample_schema):
        """Test LIMIT with GROUP BY aggregation."""
        agg_plan = {
            "intent_summary": "Count tracks by genre",
            "decision": "proceed",
            "selections": [
                {
                    "table": "tracks",
                    "alias": "t",
                    "columns": [
                        {"name": "GenreId", "role": "projection"},
                        {"name": "TrackId", "role": "projection", "aggregate": "COUNT"}
                    ]
                }
            ],
            "join_edges": [],
            "filters": [],
            "group_by": ["GenreId"],
            "order_by": [],
            "limit": None
        }

        patch = {
            "operation": "modify_limit",
            "limit": 10
        }

        result = apply_patch_operation(agg_plan, patch, sample_schema)

        assert result["limit"] == 10
        assert result["group_by"] == ["GenreId"]

    def test_limit_with_complex_query(self, sample_schema):
        """Test LIMIT with multiple clauses (ORDER BY, WHERE, GROUP BY)."""
        complex_plan = {
            "intent_summary": "Complex query",
            "decision": "proceed",
            "selections": [
                {
                    "table": "tracks",
                    "alias": "t",
                    "columns": [
                        {"name": "GenreId", "role": "projection"},
                        {"name": "TrackId", "role": "projection", "aggregate": "COUNT"}
                    ]
                }
            ],
            "join_edges": [],
            "filters": [
                {
                    "table": "tracks",
                    "column": "Milliseconds",
                    "operator": ">",
                    "value": "180000"
                }
            ],
            "group_by": ["GenreId"],
            "order_by": [
                {"table": "tracks", "column": "TrackId", "direction": "DESC"}
            ],
            "limit": None
        }

        patch = {
            "operation": "modify_limit",
            "limit": 5
        }

        result = apply_patch_operation(complex_plan, patch, sample_schema)

        assert result["limit"] == 5
        assert len(result["filters"]) == 1
        assert len(result["order_by"]) == 1
        assert result["group_by"] == ["GenreId"]


class TestPlanImmutability:
    """Tests for ensuring plan immutability."""

    def test_original_plan_unchanged(self, sample_plan, sample_schema):
        """Test that modifying LIMIT doesn't change original plan."""
        import copy
        original_plan = copy.deepcopy(sample_plan)

        patch = {
            "operation": "modify_limit",
            "limit": 100
        }

        result = apply_patch_operation(sample_plan, patch, sample_schema)

        # Original should be unchanged
        assert sample_plan == original_plan
        # Result should have LIMIT
        assert result["limit"] == 100

    def test_multiple_limit_changes(self, sample_plan, sample_schema):
        """Test applying multiple LIMIT changes sequentially."""
        # First change
        patch1 = {"operation": "modify_limit", "limit": 50}
        result1 = apply_patch_operation(sample_plan, patch1, sample_schema)
        assert result1["limit"] == 50

        # Second change
        patch2 = {"operation": "modify_limit", "limit": 100}
        result2 = apply_patch_operation(result1, patch2, sample_schema)
        assert result2["limit"] == 100

        # Third change
        patch3 = {"operation": "modify_limit", "limit": 25}
        result3 = apply_patch_operation(result2, patch3, sample_schema)
        assert result3["limit"] == 25
