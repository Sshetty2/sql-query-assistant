"""Tests for enhanced 3-stage schema filtering."""

import pytest
from unittest.mock import Mock, patch
from agent.filter_schema import (
    expand_with_foreign_keys,
    load_foreign_keys,
    filter_schema,
)


def test_expand_with_foreign_keys():
    """Test that foreign key expansion adds referenced tables."""
    # Mock data
    selected_tables = [
        {"table_name": "tb_SaasComputers", "columns": []},
    ]

    all_tables = [
        {"table_name": "tb_SaasComputers", "columns": []},
        {"table_name": "tb_Company", "columns": []},
        {"table_name": "tb_SaasNetworkDomain", "columns": []},
        {"table_name": "tb_SaasScan", "columns": []},
        {"table_name": "tb_OtherTable", "columns": []},
    ]

    foreign_keys_data = [
        {
            "table_name": "tb_SaasComputers",
            "foreign_keys": [
                {"foreign_key": "CompanyID", "primary_key_table": "tb_Company"},
                {"foreign_key": "NetworkID", "primary_key_table": "tb_SaasNetworkDomain"},
                {"foreign_key": "ScanID", "primary_key_table": "tb_SaasScan"},
            ],
        },
        {"table_name": "tb_Company", "foreign_keys": []},
        {"table_name": "tb_SaasNetworkDomain", "foreign_keys": []},
        {"table_name": "tb_SaasScan", "foreign_keys": []},
    ]

    result = expand_with_foreign_keys(selected_tables, all_tables, foreign_keys_data)

    # Should include original table plus 3 foreign key referenced tables
    result_names = {table["table_name"] for table in result}
    assert result_names == {
        "tb_SaasComputers",
        "tb_Company",
        "tb_SaasNetworkDomain",
        "tb_SaasScan",
    }


def test_expand_with_foreign_keys_no_expansion_needed():
    """Test expansion when no foreign keys exist."""
    selected_tables = [{"table_name": "tb_Company", "columns": []}]

    all_tables = [
        {"table_name": "tb_Company", "columns": []},
        {"table_name": "tb_OtherTable", "columns": []},
    ]

    foreign_keys_data = [
        {"table_name": "tb_Company", "foreign_keys": []},
    ]

    result = expand_with_foreign_keys(selected_tables, all_tables, foreign_keys_data)

    # Should only include the original table
    result_names = {table["table_name"] for table in result}
    assert result_names == {"tb_Company"}


def test_expand_with_foreign_keys_multiple_selected_tables():
    """Test expansion with multiple selected tables."""
    selected_tables = [
        {"table_name": "tb_SaasComputers", "columns": []},
        {"table_name": "tb_SaasInstalledAppsTemp", "columns": []},
    ]

    all_tables = [
        {"table_name": "tb_SaasComputers", "columns": []},
        {"table_name": "tb_SaasInstalledAppsTemp", "columns": []},
        {"table_name": "tb_Company", "columns": []},
        {"table_name": "tb_SaasScan", "columns": []},
    ]

    foreign_keys_data = [
        {
            "table_name": "tb_SaasComputers",
            "foreign_keys": [
                {"foreign_key": "CompanyID", "primary_key_table": "tb_Company"},
            ],
        },
        {
            "table_name": "tb_SaasInstalledAppsTemp",
            "foreign_keys": [
                {"foreign_key": "ScanID", "primary_key_table": "tb_SaasScan"},
            ],
        },
    ]

    result = expand_with_foreign_keys(selected_tables, all_tables, foreign_keys_data)

    # Should include both selected tables plus their foreign key references
    result_names = {table["table_name"] for table in result}
    assert result_names == {
        "tb_SaasComputers",
        "tb_SaasInstalledAppsTemp",
        "tb_Company",
        "tb_SaasScan",
    }


def test_expand_with_foreign_keys_handles_missing_referenced_table():
    """Test that expansion handles gracefully when referenced table doesn't exist."""
    selected_tables = [
        {"table_name": "tb_TestTable", "columns": []},
    ]

    all_tables = [
        {"table_name": "tb_TestTable", "columns": []},
    ]

    foreign_keys_data = [
        {
            "table_name": "tb_TestTable",
            "foreign_keys": [
                {"foreign_key": "MissingID", "primary_key_table": "tb_MissingTable"},
            ],
        },
    ]

    result = expand_with_foreign_keys(selected_tables, all_tables, foreign_keys_data)

    # Should only include the original table (missing reference ignored)
    result_names = {table["table_name"] for table in result}
    assert result_names == {"tb_TestTable"}


def test_load_foreign_keys():
    """Test that foreign keys can be loaded from JSON file."""
    foreign_keys = load_foreign_keys()

    # Should return a list (may be empty if file doesn't exist)
    assert isinstance(foreign_keys, list)

    # If file exists, should have expected structure
    if foreign_keys:
        assert "table_name" in foreign_keys[0]
        assert "foreign_keys" in foreign_keys[0]


@patch("agent.filter_schema.Chroma")
@patch("agent.filter_schema.get_embedding_model")
@patch("utils.llm_factory.get_chat_llm")
@patch("agent.filter_schema.load_foreign_keys")
def test_filter_schema_three_stage_process(
    mock_load_fks, mock_get_llm, mock_get_embedding, mock_chroma
):
    """Test that filter_schema executes all three stages correctly."""
    # Mock state
    state = {
        "schema": [
            {"table_name": "tb_Table1", "metadata": {"description": "Table 1"}},
            {"table_name": "tb_Table2", "metadata": {"description": "Table 2"}},
            {"table_name": "tb_Table3", "metadata": {"description": "Table 3"}},
        ],
        "user_question": "Test query",
    }

    # Mock Stage 1: Vector search returns 2 candidates
    mock_doc1 = Mock()
    mock_doc1.metadata = state["schema"][0]
    mock_doc2 = Mock()
    mock_doc2.metadata = state["schema"][1]

    mock_vs_instance = Mock()
    mock_vs_instance.similarity_search.return_value = [mock_doc1, mock_doc2]
    mock_chroma.from_documents.return_value = mock_vs_instance

    # Mock Stage 2: LLM selects 1 table as relevant
    mock_llm_output = Mock()
    mock_assessment = Mock()
    mock_assessment.table_name = "tb_Table1"
    mock_assessment.is_relevant = True
    mock_assessment.reasoning = "Relevant for the query"
    mock_assessment.relevant_columns = []  # Empty list means no column filtering
    mock_llm_output.selected_tables = [mock_assessment]

    mock_structured_llm = Mock()
    mock_structured_llm.invoke.return_value = mock_llm_output

    mock_llm = Mock()
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mock_get_llm.return_value = mock_llm

    # Mock Stage 3: Foreign keys (no expansion in this test)
    mock_load_fks.return_value = [{"table_name": "tb_Table1", "foreign_keys": []}]

    # Execute
    result = filter_schema(state)

    # Verify both schemas are returned
    assert "filtered_schema" in result
    assert "truncated_schema" in result
    assert len(result["filtered_schema"]) == 1
    assert len(result["truncated_schema"]) == 1
    assert result["filtered_schema"][0]["table_name"] == "tb_Table1"
    assert result["truncated_schema"][0]["table_name"] == "tb_Table1"
    assert result["last_step"] == "filter_schema"

    # Verify filtered_schema has all columns (for modification options)
    # Verify truncated_schema may have filtered columns (for planner context)
    # In this test with no relevant_columns specified, both should be the same

    # Verify all stages were called
    mock_chroma.from_documents.assert_called_once()
    mock_vs_instance.similarity_search.assert_called_once()
    mock_structured_llm.invoke.assert_called_once()
    mock_load_fks.assert_called_once()


@patch("agent.filter_schema.Chroma")
@patch("agent.filter_schema.get_embedding_model")
@patch("utils.llm_factory.get_chat_llm")
@patch("agent.filter_schema.load_foreign_keys")
def test_filter_schema_column_filtering(
    mock_load_fks, mock_get_llm, mock_get_embedding, mock_chroma
):
    """Test that filter_schema creates both filtered_schema (all columns) and truncated_schema (selected columns)."""
    # Mock state with tables that have multiple columns
    state = {
        "schema": [
            {
                "table_name": "tb_Users",
                "metadata": {"description": "User table"},
                "columns": [
                    {"column_name": "UserID", "data_type": "int"},
                    {"column_name": "UserName", "data_type": "varchar"},
                    {"column_name": "Email", "data_type": "varchar"},
                    {"column_name": "Phone", "data_type": "varchar"},
                    {"column_name": "Address", "data_type": "varchar"},
                ],
            }
        ],
        "user_question": "Show me user names and emails",
    }

    # Mock Stage 1: Vector search returns the user table
    mock_doc = Mock()
    mock_doc.metadata = state["schema"][0]

    mock_vs_instance = Mock()
    mock_vs_instance.similarity_search.return_value = [mock_doc]
    mock_chroma.from_documents.return_value = mock_vs_instance

    # Mock Stage 2: LLM selects only UserName and Email columns
    mock_llm_output = Mock()
    mock_assessment = Mock()
    mock_assessment.table_name = "tb_Users"
    mock_assessment.is_relevant = True
    mock_assessment.reasoning = "Contains user data"
    mock_assessment.relevant_columns = ["UserID", "UserName", "Email"]  # Only 3 of 5 columns
    mock_llm_output.selected_tables = [mock_assessment]

    mock_structured_llm = Mock()
    mock_structured_llm.invoke.return_value = mock_llm_output

    mock_llm = Mock()
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mock_get_llm.return_value = mock_llm

    # Mock Stage 3: No FK expansion
    mock_load_fks.return_value = [{"table_name": "tb_Users", "foreign_keys": []}]

    # Execute
    result = filter_schema(state)

    # Verify both schemas exist
    assert "filtered_schema" in result
    assert "truncated_schema" in result

    # Get the schemas
    filtered_schema = result["filtered_schema"]
    truncated_schema = result["truncated_schema"]

    # Both should have the same table
    assert len(filtered_schema) == 1
    assert len(truncated_schema) == 1
    assert filtered_schema[0]["table_name"] == "tb_Users"
    assert truncated_schema[0]["table_name"] == "tb_Users"

    # filtered_schema should have ALL 5 columns (for modification options)
    filtered_columns = [col["column_name"] for col in filtered_schema[0]["columns"]]
    assert len(filtered_columns) == 5
    assert set(filtered_columns) == {"UserID", "UserName", "Email", "Phone", "Address"}

    # truncated_schema should have ONLY 3 selected columns (for planner context)
    truncated_columns = [col["column_name"] for col in truncated_schema[0]["columns"]]
    assert len(truncated_columns) == 3
    assert set(truncated_columns) == {"UserID", "UserName", "Email"}

    # truncated_schema should be marked as column_filtered
    assert truncated_schema[0].get("column_filtered") is True


@patch("agent.filter_schema.Chroma")
@patch("agent.filter_schema.get_embedding_model")
@patch("utils.llm_factory.get_chat_llm")
@patch("agent.filter_schema.load_foreign_keys")
def test_filter_schema_case_insensitive_column_matching(
    mock_load_fks, mock_get_llm, mock_get_embedding, mock_chroma
):
    """Test that column filtering works with case-insensitive matching (LLM returns snake_case, schema has PascalCase)."""  # noqa: E501
    # Mock state with PascalCase column names (typical SQL Server naming)
    state = {
        "schema": [
            {
                "table_name": "tb_Users",
                "metadata": {"description": "User table"},
                "columns": [
                    {"column_name": "UserID", "data_type": "int"},  # PascalCase
                    {"column_name": "UserName", "data_type": "varchar"},
                    {"column_name": "EmailAddress", "data_type": "varchar"},
                    {"column_name": "PhoneNumber", "data_type": "varchar"},
                ],
            }
        ],
        "user_question": "Show me user names and emails",
    }

    # Mock Stage 1: Vector search
    mock_doc = Mock()
    mock_doc.metadata = state["schema"][0]
    mock_vs_instance = Mock()
    mock_vs_instance.similarity_search.return_value = [mock_doc]
    mock_chroma.from_documents.return_value = mock_vs_instance

    # Mock Stage 2: LLM returns snake_case column names (common LLM behavior)
    mock_llm_output = Mock()
    mock_assessment = Mock()
    mock_assessment.table_name = "tb_Users"
    mock_assessment.is_relevant = True
    mock_assessment.reasoning = "Contains user data"
    mock_assessment.relevant_columns = [
        "user_id",  # snake_case (LLM style)
        "user_name",
        "email_address",
    ]
    mock_llm_output.selected_tables = [mock_assessment]

    mock_structured_llm = Mock()
    mock_structured_llm.invoke.return_value = mock_llm_output
    mock_llm = Mock()
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mock_get_llm.return_value = mock_llm

    # Mock Stage 3: No FK expansion
    mock_load_fks.return_value = []

    # Execute
    result = filter_schema(state)

    # Verify schemas exist
    assert "filtered_schema" in result
    assert "truncated_schema" in result

    # Get schemas
    filtered_schema = result["filtered_schema"]
    truncated_schema = result["truncated_schema"]

    # filtered_schema should have ALL 4 columns
    filtered_columns = [col["column_name"] for col in filtered_schema[0]["columns"]]
    assert len(filtered_columns) == 4
    assert set(filtered_columns) == {"UserID", "UserName", "EmailAddress", "PhoneNumber"}

    # truncated_schema should have 3 columns that matched case-insensitively
    truncated_columns = [col["column_name"] for col in truncated_schema[0]["columns"]]
    assert len(truncated_columns) == 3
    # Verify the ACTUAL PascalCase names are preserved (not converted to snake_case)
    assert set(truncated_columns) == {"UserID", "UserName", "EmailAddress"}

    # Verify column names are in original PascalCase (not converted)
    assert "UserID" in truncated_columns
    assert "user_id" not in truncated_columns


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
