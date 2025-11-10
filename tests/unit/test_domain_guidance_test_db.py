"""Test that domain-specific guidance is skipped when using test database."""

import os
from unittest.mock import patch, mock_open


def test_pre_planner_skips_guidance_with_test_db():
    """Test that pre_planner.load_domain_guidance() returns None when USE_TEST_DB=true."""
    from agent.pre_planner import load_domain_guidance

    with patch.dict(os.environ, {"USE_TEST_DB": "true"}):
        result = load_domain_guidance()
        assert result is None


def test_planner_skips_guidance_with_test_db():
    """Test that planner.load_domain_guidance() returns None when USE_TEST_DB=true."""
    from agent.planner import load_domain_guidance

    with patch.dict(os.environ, {"USE_TEST_DB": "true"}):
        result = load_domain_guidance()
        assert result is None


def test_filter_schema_skips_guidance_with_test_db():
    """Test that filter_schema.load_domain_guidance() returns None when USE_TEST_DB=true."""
    from agent.filter_schema import load_domain_guidance

    with patch.dict(os.environ, {"USE_TEST_DB": "true"}):
        result = load_domain_guidance()
        assert result is None


def test_pre_planner_loads_guidance_without_test_db():
    """Test that pre_planner.load_domain_guidance() attempts to load when USE_TEST_DB=false."""
    from agent.pre_planner import load_domain_guidance

    mock_file_content = "# Test guidance content"

    with patch.dict(os.environ, {"USE_TEST_DB": "false"}):
        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=mock_file_content)):
                result = load_domain_guidance()
                assert result == mock_file_content


def test_planner_loads_guidance_without_test_db():
    """Test that planner.load_domain_guidance() attempts to load when USE_TEST_DB=false."""
    from agent.planner import load_domain_guidance
    import json

    mock_json_content = {"key": "value"}

    with patch.dict(os.environ, {"USE_TEST_DB": "false"}):
        with patch("os.path.exists", return_value=True):
            with patch(
                "builtins.open", mock_open(read_data=json.dumps(mock_json_content))
            ):
                with patch("json.load", return_value=mock_json_content):
                    result = load_domain_guidance()
                    assert result == mock_json_content


def test_filter_schema_loads_guidance_without_test_db():
    """Test that filter_schema.load_domain_guidance() attempts to load when USE_TEST_DB=false."""
    from agent.filter_schema import load_domain_guidance

    mock_file_content = "# Test guidance content"

    with patch.dict(os.environ, {"USE_TEST_DB": "false"}):
        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=mock_file_content)):
                result = load_domain_guidance()
                assert result == mock_file_content


def test_combine_schema_skips_domain_modifications_with_test_db():
    """Test that combine_schema skips domain-specific modifications when USE_TEST_DB=true."""
    from domain_specific_guidance.domain_specific_schema_callback import combine_schema

    test_schema = [
        {
            "table_name": "test_table",
            "columns": [{"column_name": "id", "data_type": "INTEGER"}],
        }
    ]

    with patch.dict(os.environ, {"USE_TEST_DB": "true"}):
        result = combine_schema(test_schema)
        # Should return schema unchanged (no domain-specific modifications)
        assert result == test_schema


def test_combine_schema_applies_modifications_without_test_db():
    """Test that combine_schema applies domain-specific modifications when USE_TEST_DB=false."""
    from domain_specific_guidance.domain_specific_schema_callback import combine_schema

    test_schema = [
        {
            "table_name": "test_table",
            "columns": [
                {"column_name": "id", "data_type": "INTEGER"},
                {"column_name": "IsDeleted", "data_type": "BIT"},  # Should be removed
            ],
        }
    ]

    with patch.dict(os.environ, {"USE_TEST_DB": "false"}):
        # Mock the file loading to return None (no domain files exist)
        with patch(
            "domain_specific_guidance.domain_specific_schema_callback.load_domain_specific_json",
            return_value=None,
        ):
            result = combine_schema(test_schema)
            # Should remove IsDeleted column
            assert len(result[0]["columns"]) == 1
            assert result[0]["columns"][0]["column_name"] == "id"
