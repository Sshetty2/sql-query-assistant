"""Unit tests for modification options generator."""

import pytest
from agent.generate_modification_options import (
    get_selected_columns_map,
    get_table_columns_from_schema,
    generate_modification_options,
    format_modification_options_for_display,
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
                    }
                ],
            }
        ],
        "global_filters": [],
        "join_edges": [],
        "order_by": [{"table": "tb_Company", "column": "Name", "direction": "ASC"}],
        "limit": 100,
        "ambiguities": [],
        "confidence": 0.9,
    }


@pytest.fixture
def multi_table_plan():
    """Sample plan with multiple tables."""
    return {
        "decision": "proceed",
        "intent_summary": "Get companies with their users",
        "selections": [
            {
                "table": "tb_Company",
                "alias": "c",
                "confidence": 0.9,
                "columns": [
                    {
                        "table": "tb_Company",
                        "column": "ID",
                        "role": "projection",
                        "value_type": "integer",
                    },
                    {
                        "table": "tb_Company",
                        "column": "Name",
                        "role": "projection",
                        "value_type": "string",
                    },
                ],
                "filters": [],
            },
            {
                "table": "tb_Users",
                "alias": "u",
                "confidence": 0.9,
                "columns": [
                    {
                        "table": "tb_Users",
                        "column": "UserID",
                        "role": "projection",
                        "value_type": "integer",
                    },
                    {
                        "table": "tb_Users",
                        "column": "Email",
                        "role": "projection",
                        "value_type": "string",
                    },
                ],
                "filters": [],
            },
        ],
        "join_edges": [
            {
                "from_table": "tb_Users",
                "from_column": "CompanyID",
                "to_table": "tb_Company",
                "to_column": "ID",
                "join_type": "inner",
            }
        ],
        "order_by": [{"table": "tb_Company", "column": "Name", "direction": "DESC"}],
        "limit": 50,
    }


class TestGetSelectedColumnsMap:
    """Test building selected columns map from plan."""

    def test_simple_plan(self, sample_plan):
        """Test mapping columns from simple plan."""
        column_map = get_selected_columns_map(sample_plan)

        assert "tb_Company" in column_map
        assert "ID" in column_map["tb_Company"]
        assert "Name" in column_map["tb_Company"]
        assert "Status" in column_map["tb_Company"]

        # Check roles
        assert column_map["tb_Company"]["ID"]["role"] == "projection"
        assert column_map["tb_Company"]["Name"]["role"] == "projection"
        assert column_map["tb_Company"]["Status"]["role"] == "filter"

    def test_multi_table_plan(self, multi_table_plan):
        """Test mapping columns from multi-table plan."""
        column_map = get_selected_columns_map(multi_table_plan)

        assert "tb_Company" in column_map
        assert "tb_Users" in column_map

        # Check Company columns
        assert "ID" in column_map["tb_Company"]
        assert "Name" in column_map["tb_Company"]

        # Check Users columns
        assert "UserID" in column_map["tb_Users"]
        assert "Email" in column_map["tb_Users"]

    def test_empty_plan(self):
        """Test mapping columns from empty plan."""
        plan = {"selections": []}
        column_map = get_selected_columns_map(plan)

        assert column_map == {}

    def test_table_with_no_columns(self):
        """Test mapping table with no columns (join-only table)."""
        plan = {
            "selections": [
                {
                    "table": "tb_Company",
                    "include_only_for_join": True,
                    "columns": [],
                }
            ]
        }
        column_map = get_selected_columns_map(plan)

        assert "tb_Company" in column_map
        assert len(column_map["tb_Company"]) == 0


class TestGetTableColumnsFromSchema:
    """Test retrieving table columns from schema."""

    def test_get_columns_existing_table(self, sample_schema):
        """Test getting columns for existing table."""
        columns = get_table_columns_from_schema("tb_Company", sample_schema)

        assert len(columns) == 5
        column_names = [col["column_name"] for col in columns]
        assert "ID" in column_names
        assert "Name" in column_names
        assert "Status" in column_names
        assert "CreatedOn" in column_names
        assert "Revenue" in column_names

    def test_get_columns_case_insensitive(self, sample_schema):
        """Test case-insensitive table lookup."""
        columns = get_table_columns_from_schema("TB_COMPANY", sample_schema)
        assert len(columns) == 5

    def test_get_columns_non_existent_table(self, sample_schema):
        """Test getting columns for non-existent table."""
        columns = get_table_columns_from_schema("tb_Invalid", sample_schema)
        assert columns == []

    def test_column_metadata_preserved(self, sample_schema):
        """Test that column metadata is preserved."""
        columns = get_table_columns_from_schema("tb_Company", sample_schema)

        id_col = next(col for col in columns if col["column_name"] == "ID")
        assert id_col["data_type"] == "bigint"
        assert id_col["is_primary_key"] is True
        assert id_col["is_nullable"] is False


class TestGenerateModificationOptions:
    """Test generating modification options."""

    def test_simple_plan_options(self, sample_plan, sample_schema):
        """Test generating options for simple plan."""
        options = generate_modification_options(sample_plan, sample_schema)

        # Check structure
        assert "tables" in options
        assert "current_order_by" in options
        assert "current_limit" in options
        assert "sortable_columns" in options

        # Check tables
        assert "tb_Company" in options["tables"]
        company = options["tables"]["tb_Company"]
        assert company["alias"] == "c"
        assert len(company["columns"]) == 5  # All 5 columns from schema

        # Check selected status
        columns_dict = {col["name"]: col for col in company["columns"]}
        assert columns_dict["ID"]["selected"] is True
        assert columns_dict["Name"]["selected"] is True
        assert columns_dict["Status"]["selected"] is True
        assert columns_dict["CreatedOn"]["selected"] is False  # Not in plan
        assert columns_dict["Revenue"]["selected"] is False  # Not in plan

        # Check roles
        assert columns_dict["ID"]["role"] == "projection"
        assert columns_dict["Name"]["role"] == "projection"
        assert columns_dict["Status"]["role"] == "filter"
        assert columns_dict["CreatedOn"]["role"] is None
        assert columns_dict["Revenue"]["role"] is None

    def test_current_order_by(self, sample_plan, sample_schema):
        """Test current ORDER BY is extracted correctly."""
        options = generate_modification_options(sample_plan, sample_schema)

        assert len(options["current_order_by"]) == 1
        assert options["current_order_by"][0]["table"] == "tb_Company"
        assert options["current_order_by"][0]["column"] == "Name"
        assert options["current_order_by"][0]["direction"] == "ASC"

    def test_current_limit(self, sample_plan, sample_schema):
        """Test current LIMIT is extracted correctly."""
        options = generate_modification_options(sample_plan, sample_schema)
        assert options["current_limit"] == 100

    def test_sortable_columns(self, sample_plan, sample_schema):
        """Test sortable columns list."""
        options = generate_modification_options(sample_plan, sample_schema)

        sortable = options["sortable_columns"]
        assert len(sortable) == 5  # All 5 Company columns

        # Check structure
        assert all("table" in col for col in sortable)
        assert all("column" in col for col in sortable)
        assert all("type" in col for col in sortable)
        assert all("display_name" in col for col in sortable)

        # Check display names
        display_names = [col["display_name"] for col in sortable]
        assert "tb_Company.ID" in display_names
        assert "tb_Company.Name" in display_names

    def test_multi_table_options(self, multi_table_plan, sample_schema):
        """Test generating options for multi-table plan."""
        options = generate_modification_options(multi_table_plan, sample_schema)

        # Check both tables present
        assert "tb_Company" in options["tables"]
        assert "tb_Users" in options["tables"]

        # Check Company columns
        company_columns = options["tables"]["tb_Company"]["columns"]
        assert len(company_columns) == 5  # All Company columns from schema
        company_names = {col["name"] for col in company_columns}
        assert company_names == {"ID", "Name", "Status", "CreatedOn", "Revenue"}

        # Check Users columns
        user_columns = options["tables"]["tb_Users"]["columns"]
        assert len(user_columns) == 3  # All Users columns from schema
        user_names = {col["name"] for col in user_columns}
        assert user_names == {"UserID", "Email", "CompanyID"}

        # Check sortable columns includes both tables
        sortable = options["sortable_columns"]
        assert len(sortable) == 8  # 5 Company + 3 Users
        sortable_tables = {col["table"] for col in sortable}
        assert sortable_tables == {"tb_Company", "tb_Users"}

    def test_primary_key_metadata(self, sample_plan, sample_schema):
        """Test that primary key metadata is included."""
        options = generate_modification_options(sample_plan, sample_schema)

        company_columns = {
            col["name"]: col for col in options["tables"]["tb_Company"]["columns"]
        }

        assert company_columns["ID"]["is_primary_key"] is True
        assert company_columns["Name"]["is_primary_key"] is False

    def test_nullable_metadata(self, sample_plan, sample_schema):
        """Test that nullable metadata is included."""
        options = generate_modification_options(sample_plan, sample_schema)

        company_columns = {
            col["name"]: col for col in options["tables"]["tb_Company"]["columns"]
        }

        assert company_columns["ID"]["is_nullable"] is False
        assert company_columns["Name"]["is_nullable"] is True

    def test_column_types(self, sample_plan, sample_schema):
        """Test that column data types are included."""
        options = generate_modification_options(sample_plan, sample_schema)

        company_columns = {
            col["name"]: col for col in options["tables"]["tb_Company"]["columns"]
        }

        assert company_columns["ID"]["type"] == "bigint"
        assert company_columns["Name"]["type"] == "nvarchar"
        assert company_columns["CreatedOn"]["type"] == "datetime"
        assert company_columns["Revenue"]["type"] == "decimal"

    def test_plan_with_no_order_by(self, sample_plan, sample_schema):
        """Test plan with no ORDER BY clause."""
        plan = {**sample_plan, "order_by": []}
        options = generate_modification_options(plan, sample_schema)

        assert options["current_order_by"] == []

    def test_plan_with_no_limit(self, sample_plan, sample_schema):
        """Test plan with no LIMIT clause."""
        plan = {**sample_plan}
        del plan["limit"]

        options = generate_modification_options(plan, sample_schema)
        assert options["current_limit"] is None


class TestFormatModificationOptionsForDisplay:
    """Test formatting options for display."""

    def test_format_simple_options(self, sample_plan, sample_schema):
        """Test formatting simple options."""
        options = generate_modification_options(sample_plan, sample_schema)
        formatted = format_modification_options_for_display(options)

        # Check output contains expected sections
        assert "=== Modification Options ===" in formatted
        assert "Available Columns:" in formatted
        assert "tb_Company" in formatted
        assert "Current ORDER BY:" in formatted
        assert "Current LIMIT:" in formatted

        # Check selected columns marked
        assert "[✓] ID" in formatted
        assert "[✓] Name" in formatted
        assert "[ ] CreatedOn" in formatted

        # Check roles shown
        assert "[projection]" in formatted
        assert "[filter]" in formatted

        # Check ORDER BY shown
        assert "tb_Company.Name ASC" in formatted

        # Check LIMIT shown
        assert "Current LIMIT: 100" in formatted

    def test_format_multi_table_options(self, multi_table_plan, sample_schema):
        """Test formatting multi-table options."""
        options = generate_modification_options(multi_table_plan, sample_schema)
        formatted = format_modification_options_for_display(options)

        # Check both tables shown
        assert "tb_Company" in formatted
        assert "tb_Users" in formatted

        # Check aliases shown
        assert "(c)" in formatted
        assert "(u)" in formatted

    def test_format_no_order_by(self, sample_plan, sample_schema):
        """Test formatting when no ORDER BY."""
        plan = {**sample_plan, "order_by": []}
        options = generate_modification_options(plan, sample_schema)
        formatted = format_modification_options_for_display(options)

        assert "Current ORDER BY: None" in formatted

    def test_format_no_limit(self, sample_plan, sample_schema):
        """Test formatting when no LIMIT."""
        plan = {**sample_plan}
        del plan["limit"]
        options = generate_modification_options(plan, sample_schema)
        formatted = format_modification_options_for_display(options)

        assert "Current LIMIT: None" in formatted

    def test_format_primary_key_indicated(self, sample_plan, sample_schema):
        """Test that primary keys are indicated."""
        options = generate_modification_options(sample_plan, sample_schema)
        formatted = format_modification_options_for_display(options)

        assert "(PK)" in formatted  # ID should be marked as PK

    def test_format_sortable_count(self, sample_plan, sample_schema):
        """Test that sortable columns count is shown."""
        options = generate_modification_options(sample_plan, sample_schema)
        formatted = format_modification_options_for_display(options)

        assert "Total sortable columns: 5" in formatted


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_plan_with_table_not_in_schema(self, sample_schema):
        """Test plan referencing table not in schema."""
        plan = {
            "selections": [
                {
                    "table": "tb_Invalid",
                    "columns": [
                        {
                            "table": "tb_Invalid",
                            "column": "Col1",
                            "role": "projection",
                        }
                    ],
                }
            ],
            "order_by": [],
            "limit": None,
        }

        options = generate_modification_options(plan, sample_schema)

        # Should handle gracefully
        assert "tb_Invalid" in options["tables"]
        assert len(options["tables"]["tb_Invalid"]["columns"]) == 0  # No columns from schema

    def test_empty_schema(self, sample_plan):
        """Test with empty schema."""
        options = generate_modification_options(sample_plan, [])

        # Should handle gracefully
        assert "tb_Company" in options["tables"]
        assert len(options["tables"]["tb_Company"]["columns"]) == 0

    def test_plan_with_many_tables(self, sample_schema):
        """Test plan with multiple tables."""
        plan = {
            "selections": [
                {
                    "table": "tb_Company",
                    "columns": [
                        {"table": "tb_Company", "column": "ID", "role": "projection"}
                    ],
                },
                {
                    "table": "tb_Users",
                    "columns": [
                        {"table": "tb_Users", "column": "UserID", "role": "projection"}
                    ],
                },
            ],
            "order_by": [],
            "limit": None,
        }

        options = generate_modification_options(plan, sample_schema)

        assert len(options["tables"]) == 2
        assert "tb_Company" in options["tables"]
        assert "tb_Users" in options["tables"]

    def test_plan_with_multi_column_order_by(self, sample_plan, sample_schema):
        """Test plan with multiple ORDER BY columns."""
        plan = {
            **sample_plan,
            "order_by": [
                {"table": "tb_Company", "column": "Status", "direction": "ASC"},
                {"table": "tb_Company", "column": "Name", "direction": "DESC"},
                {"table": "tb_Company", "column": "CreatedOn", "direction": "ASC"},
            ],
        }

        options = generate_modification_options(plan, sample_schema)

        assert len(options["current_order_by"]) == 3
        assert options["current_order_by"][0]["column"] == "Status"
        assert options["current_order_by"][1]["column"] == "Name"
        assert options["current_order_by"][2]["column"] == "CreatedOn"
