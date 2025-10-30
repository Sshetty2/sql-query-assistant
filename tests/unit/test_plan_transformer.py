"""Unit tests for plan transformer (plan patching)."""

import pytest
from agent.transform_plan import (
    validate_column_exists,
    get_column_type,
    is_column_in_filters,
    map_type_to_value_type,
    apply_add_column,
    apply_remove_column,
    apply_modify_order_by,
    apply_modify_limit,
    apply_patch_operation,
)


@pytest.fixture
def sample_schema():
    """Sample schema for testing."""
    return [
        {
            "table_name": "tb_Company",
            "columns": [
                {
                    "column_name": "ID",
                    "data_type": "bigint",
                    "is_nullable": False,
                    "is_primary_key": True,
                },
                {
                    "column_name": "Name",
                    "data_type": "nvarchar",
                    "is_nullable": True,
                    "is_primary_key": False,
                },
                {
                    "column_name": "Status",
                    "data_type": "nvarchar",
                    "is_nullable": True,
                    "is_primary_key": False,
                },
                {
                    "column_name": "CreatedOn",
                    "data_type": "datetime",
                    "is_nullable": False,
                    "is_primary_key": False,
                },
                {
                    "column_name": "Revenue",
                    "data_type": "decimal",
                    "is_nullable": True,
                    "is_primary_key": False,
                },
            ],
        },
        {
            "table_name": "tb_Users",
            "columns": [
                {
                    "column_name": "UserID",
                    "data_type": "bigint",
                    "is_nullable": False,
                    "is_primary_key": True,
                },
                {
                    "column_name": "Email",
                    "data_type": "nvarchar",
                    "is_nullable": False,
                    "is_primary_key": False,
                },
                {
                    "column_name": "CompanyID",
                    "data_type": "bigint",
                    "is_nullable": True,
                    "is_primary_key": False,
                },
            ],
        },
    ]


@pytest.fixture
def sample_plan():
    """Sample query plan for testing."""
    return {
        "decision": "proceed",
        "intent_summary": "Get company names and IDs",
        "selections": [
            {
                "table": "tb_Company",
                "alias": "c",
                "confidence": 0.9,
                "reason": "Contains company information",
                "include_only_for_join": False,
                "columns": [
                    {
                        "table": "tb_Company",
                        "column": "ID",
                        "role": "projection",
                        "reason": "Primary key",
                        "value_type": "integer",
                    },
                    {
                        "table": "tb_Company",
                        "column": "Name",
                        "role": "projection",
                        "reason": "Company name requested",
                        "value_type": "string",
                    },
                    {
                        "table": "tb_Company",
                        "column": "Status",
                        "role": "filter",
                        "reason": "Used in filter",
                        "value_type": "string",
                    },
                ],
                "filters": [
                    {
                        "table": "tb_Company",
                        "column": "Status",
                        "op": "=",
                        "value": "Active",
                        "source_text": "active companies",
                        "comment": "Filter to active companies only",
                    }
                ],
            }
        ],
        "global_filters": [],
        "join_edges": [],
        "order_by": [
            {
                "table": "tb_Company",
                "column": "Name",
                "direction": "ASC"
            }
        ],
        "limit": 100,
        "ambiguities": [],
        "confidence": 0.9,
    }


class TestValidateColumnExists:
    """Test column validation against schema."""

    def test_valid_column(self, sample_schema):
        """Test validation of existing column."""
        assert validate_column_exists("tb_Company", "Name", sample_schema)

    def test_valid_column_case_insensitive(self, sample_schema):
        """Test case-insensitive column validation."""
        assert validate_column_exists("TB_COMPANY", "name", sample_schema)

    def test_invalid_column(self, sample_schema):
        """Test validation of non-existent column."""
        assert not validate_column_exists("tb_Company", "InvalidColumn", sample_schema)

    def test_invalid_table(self, sample_schema):
        """Test validation with non-existent table."""
        assert not validate_column_exists("tb_Invalid", "Name", sample_schema)


class TestGetColumnType:
    """Test retrieving column data types."""

    def test_get_integer_type(self, sample_schema):
        """Test getting integer column type."""
        col_type = get_column_type("tb_Company", "ID", sample_schema)
        assert col_type == "bigint"

    def test_get_string_type(self, sample_schema):
        """Test getting string column type."""
        col_type = get_column_type("tb_Company", "Name", sample_schema)
        assert col_type == "nvarchar"

    def test_get_datetime_type(self, sample_schema):
        """Test getting datetime column type."""
        col_type = get_column_type("tb_Company", "CreatedOn", sample_schema)
        assert col_type == "datetime"

    def test_get_type_case_insensitive(self, sample_schema):
        """Test case-insensitive type retrieval."""
        col_type = get_column_type("TB_COMPANY", "name", sample_schema)
        assert col_type == "nvarchar"

    def test_get_type_invalid_column(self, sample_schema):
        """Test getting type of non-existent column."""
        col_type = get_column_type("tb_Company", "Invalid", sample_schema)
        assert col_type is None


class TestMapTypeToValueType:
    """Test SQL type to value_type mapping."""

    def test_integer_types(self):
        """Test integer type mapping."""
        assert map_type_to_value_type("bigint") == "integer"
        assert map_type_to_value_type("int") == "integer"
        assert map_type_to_value_type("smallint") == "integer"
        assert map_type_to_value_type("serial") == "integer"

    def test_number_types(self):
        """Test number type mapping."""
        assert map_type_to_value_type("decimal") == "number"
        assert map_type_to_value_type("float") == "number"
        assert map_type_to_value_type("double") == "number"
        assert map_type_to_value_type("numeric") == "number"

    def test_string_types(self):
        """Test string type mapping."""
        assert map_type_to_value_type("nvarchar") == "string"
        assert map_type_to_value_type("varchar") == "string"
        assert map_type_to_value_type("char") == "string"
        assert map_type_to_value_type("text") == "string"

    def test_boolean_types(self):
        """Test boolean type mapping."""
        assert map_type_to_value_type("bit") == "boolean"
        assert map_type_to_value_type("boolean") == "boolean"

    def test_datetime_types(self):
        """Test datetime type mapping."""
        assert map_type_to_value_type("datetime") == "datetime"
        assert map_type_to_value_type("timestamp") == "datetime"

    def test_date_types(self):
        """Test date type mapping."""
        assert map_type_to_value_type("date") == "date"

    def test_unknown_types(self):
        """Test unknown type mapping."""
        assert map_type_to_value_type("geography") == "unknown"
        assert map_type_to_value_type("xml") == "unknown"


class TestIsColumnInFilters:
    """Test checking if column is used in filters."""

    def test_column_in_table_filters(self, sample_plan):
        """Test detecting column in table-level filters."""
        assert is_column_in_filters("tb_Company", "Status", sample_plan)

    def test_column_not_in_filters(self, sample_plan):
        """Test detecting column not in filters."""
        assert not is_column_in_filters("tb_Company", "Name", sample_plan)

    def test_column_in_global_filters(self):
        """Test detecting column in global filters."""
        plan = {
            "selections": [],
            "global_filters": [
                {
                    "table": "tb_Company",
                    "column": "Status",
                    "op": "=",
                    "value": "Active",
                }
            ],
        }
        assert is_column_in_filters("tb_Company", "Status", plan)

    def test_column_in_having_filters(self):
        """Test detecting column in HAVING filters."""
        plan = {
            "selections": [],
            "global_filters": [],
            "group_by": {
                "group_by_columns": [],
                "aggregates": [],
                "having_filters": [
                    {
                        "table": "tb_Company",
                        "column": "Revenue",
                        "op": ">",
                        "value": 1000000,
                    }
                ],
            },
        }
        assert is_column_in_filters("tb_Company", "Revenue", plan)


class TestApplyAddColumn:
    """Test adding columns to plan."""

    def test_add_column_success(self, sample_plan, sample_schema):
        """Test successfully adding a new column."""
        modified = apply_add_column(
            sample_plan, "tb_Company", "CreatedOn", sample_schema
        )

        # Check column was added
        columns = modified["selections"][0]["columns"]
        assert any(
            col["column"] == "CreatedOn" and col["role"] == "projection"
            for col in columns
        )

    def test_add_column_invalid(self, sample_plan, sample_schema):
        """Test adding non-existent column raises error."""
        with pytest.raises(ValueError, match="Column Invalid does not exist"):
            apply_add_column(sample_plan, "tb_Company", "Invalid", sample_schema)

    def test_add_column_invalid_table(self, sample_plan, sample_schema):
        """Test adding column to non-existent table raises error."""
        with pytest.raises(ValueError, match="Column Name does not exist in table tb_Invalid"):
            apply_add_column(sample_plan, "tb_Invalid", "Name", sample_schema)

    def test_add_column_already_projection(self, sample_plan, sample_schema):
        """Test adding column that's already in projection."""
        modified = apply_add_column(sample_plan, "tb_Company", "Name", sample_schema)

        # Should not add duplicate
        columns = modified["selections"][0]["columns"]
        name_columns = [col for col in columns if col["column"] == "Name"]
        assert len(name_columns) == 1

    def test_add_column_change_filter_to_projection(self, sample_plan, sample_schema):
        """Test adding column that's currently filter-only changes its role."""
        modified = apply_add_column(sample_plan, "tb_Company", "Status", sample_schema)

        # Status should now be projection
        columns = modified["selections"][0]["columns"]
        status_col = next(col for col in columns if col["column"] == "Status")
        assert status_col["role"] == "projection"

    def test_add_column_preserves_value_type(self, sample_plan, sample_schema):
        """Test that added column gets correct value_type."""
        modified = apply_add_column(
            sample_plan, "tb_Company", "Revenue", sample_schema
        )

        columns = modified["selections"][0]["columns"]
        revenue_col = next(col for col in columns if col["column"] == "Revenue")
        assert revenue_col["value_type"] == "number"  # decimal maps to number


class TestApplyRemoveColumn:
    """Test removing columns from plan."""

    def test_remove_column_success(self, sample_plan):
        """Test successfully removing a column."""
        modified = apply_remove_column(sample_plan, "tb_Company", "Name")

        # Check column was removed
        columns = modified["selections"][0]["columns"]
        assert not any(col["column"] == "Name" for col in columns)

    def test_remove_column_used_in_filter(self, sample_plan):
        """Test removing column used in filter changes role instead."""
        modified = apply_remove_column(sample_plan, "tb_Company", "Status")

        # Status should still exist but with role="filter"
        columns = modified["selections"][0]["columns"]
        status_col = next(col for col in columns if col["column"] == "Status")
        assert status_col["role"] == "filter"

    def test_remove_column_invalid_table(self, sample_plan):
        """Test removing column from non-existent table raises error."""
        with pytest.raises(ValueError, match="Table tb_Invalid not found"):
            apply_remove_column(sample_plan, "tb_Invalid", "Name")

    def test_remove_column_not_in_plan(self, sample_plan):
        """Test removing column not in plan raises error."""
        with pytest.raises(ValueError, match="Column CreatedOn not found"):
            apply_remove_column(sample_plan, "tb_Company", "CreatedOn")


class TestApplyModifyOrderBy:
    """Test modifying ORDER BY clause."""

    def test_modify_order_by_single_column(self, sample_plan, sample_schema):
        """Test modifying ORDER BY to single column."""
        new_order_by = [
            {
                "table": "tb_Company",
                "column": "CreatedOn",
                "direction": "DESC"
            }
        ]

        modified = apply_modify_order_by(sample_plan, new_order_by, sample_schema)
        assert modified["order_by"] == new_order_by

    def test_modify_order_by_multiple_columns(self, sample_plan, sample_schema):
        """Test modifying ORDER BY to multiple columns."""
        new_order_by = [
            {"table": "tb_Company", "column": "Status", "direction": "ASC"},
            {"table": "tb_Company", "column": "Name", "direction": "DESC"},
        ]

        modified = apply_modify_order_by(sample_plan, new_order_by, sample_schema)
        assert modified["order_by"] == new_order_by
        assert len(modified["order_by"]) == 2

    def test_modify_order_by_invalid_column(self, sample_plan, sample_schema):
        """Test modifying ORDER BY with invalid column raises error."""
        new_order_by = [
            {"table": "tb_Company", "column": "Invalid", "direction": "ASC"}
        ]

        with pytest.raises(ValueError, match="Column Invalid does not exist"):
            apply_modify_order_by(sample_plan, new_order_by, sample_schema)

    def test_modify_order_by_invalid_direction(self, sample_plan, sample_schema):
        """Test modifying ORDER BY with invalid direction raises error."""
        new_order_by = [
            {"table": "tb_Company", "column": "Name", "direction": "INVALID"}
        ]

        with pytest.raises(ValueError, match="Invalid sort direction"):
            apply_modify_order_by(sample_plan, new_order_by, sample_schema)

    def test_modify_order_by_empty(self, sample_plan, sample_schema):
        """Test clearing ORDER BY clause."""
        modified = apply_modify_order_by(sample_plan, [], sample_schema)
        assert modified["order_by"] == []


class TestApplyModifyLimit:
    """Test modifying LIMIT clause."""

    def test_modify_limit_valid(self, sample_plan):
        """Test modifying LIMIT to valid value."""
        modified = apply_modify_limit(sample_plan, 500)
        assert modified["limit"] == 500

    def test_modify_limit_small_value(self, sample_plan):
        """Test modifying LIMIT to small value."""
        modified = apply_modify_limit(sample_plan, 10)
        assert modified["limit"] == 10

    def test_modify_limit_large_value(self, sample_plan):
        """Test modifying LIMIT to large value."""
        modified = apply_modify_limit(sample_plan, 10000)
        assert modified["limit"] == 10000

    def test_modify_limit_zero(self, sample_plan):
        """Test modifying LIMIT to zero raises error."""
        with pytest.raises(ValueError, match="Must be a positive integer"):
            apply_modify_limit(sample_plan, 0)

    def test_modify_limit_negative(self, sample_plan):
        """Test modifying LIMIT to negative value raises error."""
        with pytest.raises(ValueError, match="Must be a positive integer"):
            apply_modify_limit(sample_plan, -10)

    def test_modify_limit_non_integer(self, sample_plan):
        """Test modifying LIMIT to non-integer raises error."""
        with pytest.raises(ValueError, match="Must be a positive integer"):
            apply_modify_limit(sample_plan, "100")


class TestApplyPatchOperation:
    """Test applying patch operations via unified interface."""

    def test_patch_add_column(self, sample_plan, sample_schema):
        """Test applying add_column patch."""
        operation = {
            "operation": "add_column",
            "table": "tb_Company",
            "column": "Revenue",
        }

        modified = apply_patch_operation(sample_plan, operation, sample_schema)

        # Verify column was added
        columns = modified["selections"][0]["columns"]
        assert any(col["column"] == "Revenue" for col in columns)

    def test_patch_remove_column(self, sample_plan, sample_schema):
        """Test applying remove_column patch."""
        operation = {
            "operation": "remove_column",
            "table": "tb_Company",
            "column": "Name",
        }

        modified = apply_patch_operation(sample_plan, operation, sample_schema)

        # Verify column was removed
        columns = modified["selections"][0]["columns"]
        assert not any(col["column"] == "Name" for col in columns)

    def test_patch_modify_order_by(self, sample_plan, sample_schema):
        """Test applying modify_order_by patch."""
        operation = {
            "operation": "modify_order_by",
            "order_by": [
                {"table": "tb_Company", "column": "CreatedOn", "direction": "DESC"}
            ],
        }

        modified = apply_patch_operation(sample_plan, operation, sample_schema)
        assert modified["order_by"][0]["column"] == "CreatedOn"
        assert modified["order_by"][0]["direction"] == "DESC"

    def test_patch_modify_limit(self, sample_plan, sample_schema):
        """Test applying modify_limit patch."""
        operation = {
            "operation": "modify_limit",
            "limit": 50,
        }

        modified = apply_patch_operation(sample_plan, operation, sample_schema)
        assert modified["limit"] == 50

    def test_patch_unknown_operation(self, sample_plan, sample_schema):
        """Test applying unknown operation raises error."""
        operation = {
            "operation": "invalid_operation",
        }

        with pytest.raises(ValueError, match="Unknown operation type"):
            apply_patch_operation(sample_plan, operation, sample_schema)

    def test_patch_missing_required_fields(self, sample_plan, sample_schema):
        """Test patch with missing required fields raises error."""
        operation = {
            "operation": "add_column",
            # Missing table and column
        }

        with pytest.raises(ValueError, match="requires 'table' and 'column' fields"):
            apply_patch_operation(sample_plan, operation, sample_schema)

    def test_patch_does_not_modify_original(self, sample_plan, sample_schema):
        """Test that patching doesn't modify the original plan."""
        import copy
        original = copy.deepcopy(sample_plan)

        operation = {
            "operation": "modify_limit",
            "limit": 999,
        }

        modified = apply_patch_operation(sample_plan, operation, sample_schema)

        # Original should be unchanged
        assert sample_plan["limit"] == original["limit"]
        assert sample_plan["limit"] != modified["limit"]


class TestMultiplePatches:
    """Test applying multiple patches sequentially."""

    def test_add_and_modify_order_by(self, sample_plan, sample_schema):
        """Test adding column then modifying ORDER BY to use it."""
        # Add Revenue column
        op1 = {
            "operation": "add_column",
            "table": "tb_Company",
            "column": "Revenue",
        }
        plan1 = apply_patch_operation(sample_plan, op1, sample_schema)

        # Sort by Revenue
        op2 = {
            "operation": "modify_order_by",
            "order_by": [
                {"table": "tb_Company", "column": "Revenue", "direction": "DESC"}
            ],
        }
        plan2 = apply_patch_operation(plan1, op2, sample_schema)

        # Verify both changes applied
        columns = plan2["selections"][0]["columns"]
        assert any(col["column"] == "Revenue" for col in columns)
        assert plan2["order_by"][0]["column"] == "Revenue"

    def test_remove_then_add_same_column(self, sample_plan, sample_schema):
        """Test removing then re-adding the same column."""
        # Remove Name
        op1 = {
            "operation": "remove_column",
            "table": "tb_Company",
            "column": "Name",
        }
        plan1 = apply_patch_operation(sample_plan, op1, sample_schema)

        # Re-add Name
        op2 = {
            "operation": "add_column",
            "table": "tb_Company",
            "column": "Name",
        }
        plan2 = apply_patch_operation(plan1, op2, sample_schema)

        # Verify Name is back
        columns = plan2["selections"][0]["columns"]
        name_col = next(col for col in columns if col["column"] == "Name")
        assert name_col["role"] == "projection"

    def test_multiple_column_additions(self, sample_plan, sample_schema):
        """Test adding multiple columns sequentially."""
        # Add CreatedOn
        op1 = {"operation": "add_column", "table": "tb_Company", "column": "CreatedOn"}
        plan1 = apply_patch_operation(sample_plan, op1, sample_schema)

        # Add Revenue
        op2 = {"operation": "add_column", "table": "tb_Company", "column": "Revenue"}
        plan2 = apply_patch_operation(plan1, op2, sample_schema)

        # Verify both added
        columns = plan2["selections"][0]["columns"]
        assert any(col["column"] == "CreatedOn" for col in columns)
        assert any(col["column"] == "Revenue" for col in columns)
