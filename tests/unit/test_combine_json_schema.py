import json
import pytest
from domain_specific_guidance.combine_json_schema import (
    combine_schema,
    remove_empty_properties,
    load_domain_specific_json,
)
from unittest.mock import patch


@pytest.fixture
def sample_schema():
    return [
        {
            "table_name": "users",
            "columns": [
                {"column_name": "id", "data_type": "integer"},
                {"column_name": "name", "data_type": "string"},
            ],
        }
    ]


@pytest.fixture
def sample_metadata():
    return [
        {
            "table_name": "users",
            "description": "User table",
            "key_columns": "id\nname",
        }
    ]


@pytest.fixture
def sample_foreign_keys():
    return [
        {
            "table_name": "users",
            "foreign_keys": [{"column": "role_id", "references": "roles(id)"}],
        }
    ]


def test_remove_empty_properties():
    input_data = {
        "key1": "",
        "key2": None,
        "key3": "value",
        "key4": {"nested1": "", "nested2": "value"},
        "key5": ["", None, "value"],
    }

    expected = {"key3": "value", "key4": {"nested2": "value"}, "key5": ["value"]}

    assert remove_empty_properties(input_data) == expected


@patch("os.getenv")
def test_combine_schema_with_test_db(mock_getenv):
    mock_getenv.return_value = "true"
    schema = [{"table_name": "test"}]
    result = combine_schema(schema)
    assert result == schema


def test_combine_schema_full(
    sample_schema, sample_metadata, sample_foreign_keys, tmp_path
):
    metadata_file = tmp_path / "domain-specific-table-metadata.json"
    foreign_keys_file = tmp_path / "domain-specific-foreign-keys.json"

    with open(metadata_file, "w") as f:
        json.dump(sample_metadata, f)
    with open(foreign_keys_file, "w") as f:
        json.dump(sample_foreign_keys, f)

    # Mock the current directory to point to tmp_path and USE_TEST_DB=false
    with patch("os.path.dirname", return_value=str(tmp_path)), patch(
        "os.getenv", return_value="false"
    ):
        result = combine_schema(sample_schema)

    assert len(result) == 1
    assert result[0]["table_name"] == "users"
    assert "columns" in result[0]
    assert "metadata" in result[0]
    assert "foreign_keys" in result[0]
    assert result[0]["metadata"]["description"] == "User table"
    assert result[0]["metadata"]["key_columns"] == ["id", "name"]
    # Ensure extraneous fields are removed
    assert "row_count_estimate" not in result[0]["metadata"]
    assert "primary_key" not in result[0]["metadata"]
    assert "primary_key_description" not in result[0]["metadata"]


def test_load_domain_specific_json_file_not_found():
    with patch("os.path.dirname", return_value="/nonexistent"):
        result = load_domain_specific_json("nonexistent_file.json")
        assert result is None


def test_load_domain_specific_json_invalid_json(tmp_path):
    invalid_json_file = tmp_path / "invalid.json"
    with open(invalid_json_file, "w") as f:
        f.write("{invalid json")

    with patch("os.path.dirname", return_value=str(tmp_path)):
        result = load_domain_specific_json("invalid.json")
        assert result is None
