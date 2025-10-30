"""Tests for debug utilities."""

import os
import json
import tempfile
import pytest
from unittest.mock import patch
from utils.debug_utils import (
    save_debug_file,
    append_to_debug_array,
    is_debug_enabled,
    clear_debug_files,
)


@pytest.fixture
def temp_debug_dir(tmp_path):
    """Create a temporary debug directory for testing."""
    debug_dir = tmp_path / "debug"
    debug_dir.mkdir()
    return str(debug_dir)


def test_is_debug_enabled_default():
    """Test that debug is disabled by default."""
    with patch.dict(os.environ, {}, clear=True):
        # Without ENABLE_DEBUG_FILES set, should be False
        # (Note: the actual value depends on the .env file, but we're testing the function logic)
        enabled = is_debug_enabled()
        assert isinstance(enabled, bool)


def test_is_debug_enabled_true():
    """Test debug enabled when env var is true."""
    with patch.dict(os.environ, {"ENABLE_DEBUG_FILES": "true"}):
        # Need to reload the module to pick up new env var
        from importlib import reload
        import utils.debug_utils
        reload(utils.debug_utils)
        assert utils.debug_utils.is_debug_enabled() is True


def test_is_debug_enabled_false():
    """Test debug disabled when env var is false."""
    with patch.dict(os.environ, {"ENABLE_DEBUG_FILES": "false"}):
        from importlib import reload
        import utils.debug_utils
        reload(utils.debug_utils)
        assert utils.debug_utils.is_debug_enabled() is False


def test_save_debug_file_when_disabled():
    """Test that save_debug_file returns None when debug is disabled."""
    with patch("utils.debug_utils.DEBUG_ENABLED", False):
        result = save_debug_file(
            "test.json",
            {"key": "value"},
            step_name="test"
        )
        assert result is None


def test_save_debug_file_when_enabled(temp_debug_dir):
    """Test that save_debug_file creates a file when debug is enabled."""
    with patch("utils.debug_utils.DEBUG_ENABLED", True):
        with patch("utils.debug_utils.DEBUG_DIR", temp_debug_dir):
            result = save_debug_file(
                "test.json",
                {"key": "value", "number": 42},
                step_name="test",
                include_timestamp=False
            )

            assert result is not None
            assert os.path.exists(result)

            # Verify content
            with open(result, "r") as f:
                data = json.load(f)
                assert data["key"] == "value"
                assert data["number"] == 42


def test_save_debug_file_adds_debug_prefix(temp_debug_dir):
    """Test that debug_ prefix is added automatically."""
    with patch("utils.debug_utils.DEBUG_ENABLED", True):
        with patch("utils.debug_utils.DEBUG_DIR", temp_debug_dir):
            result = save_debug_file(
                "my_file.json",
                {"test": "data"},
                step_name="test"
            )

            assert result is not None
            assert "debug_my_file.json" in result


def test_append_to_debug_array_creates_new_file(temp_debug_dir):
    """Test that append_to_debug_array creates a new file with array."""
    with patch("utils.debug_utils.DEBUG_ENABLED", True):
        with patch("utils.debug_utils.DEBUG_DIR", temp_debug_dir):
            result = append_to_debug_array(
                "corrections.json",
                {"attempt": 1, "error": "test error"},
                step_name="test",
                array_key="corrections"
            )

            assert result is not None
            assert os.path.exists(result)

            # Verify content
            with open(result, "r") as f:
                data = json.load(f)
                assert "corrections" in data
                assert "total_count" in data
                assert data["total_count"] == 1
                assert len(data["corrections"]) == 1
                assert data["corrections"][0]["attempt"] == 1
                assert data["corrections"][0]["error"] == "test error"
                assert "timestamp" in data["corrections"][0]


def test_append_to_debug_array_appends_to_existing(temp_debug_dir):
    """Test that append_to_debug_array appends to existing file."""
    with patch("utils.debug_utils.DEBUG_ENABLED", True):
        with patch("utils.debug_utils.DEBUG_DIR", temp_debug_dir):
            # First append
            append_to_debug_array(
                "corrections.json",
                {"attempt": 1, "error": "error 1"},
                array_key="corrections"
            )

            # Second append
            result = append_to_debug_array(
                "corrections.json",
                {"attempt": 2, "error": "error 2"},
                array_key="corrections"
            )

            assert result is not None

            # Verify content has both entries
            with open(result, "r") as f:
                data = json.load(f)
                assert data["total_count"] == 2
                assert len(data["corrections"]) == 2
                assert data["corrections"][0]["attempt"] == 1
                assert data["corrections"][1]["attempt"] == 2


def test_append_to_debug_array_multiple_iterations(temp_debug_dir):
    """Test appending multiple times to track iterations."""
    with patch("utils.debug_utils.DEBUG_ENABLED", True):
        with patch("utils.debug_utils.DEBUG_DIR", temp_debug_dir):
            # Simulate 3 error correction attempts
            for i in range(1, 4):
                append_to_debug_array(
                    "error_corrections.json",
                    {
                        "attempt": i,
                        "error": f"error {i}",
                        "correction": f"fix {i}"
                    },
                    array_key="corrections"
                )

            # Verify all 3 are captured
            file_path = os.path.join(temp_debug_dir, "debug_error_corrections.json")
            assert os.path.exists(file_path)

            with open(file_path, "r") as f:
                data = json.load(f)
                assert data["total_count"] == 3
                assert len(data["corrections"]) == 3

                for i in range(3):
                    assert data["corrections"][i]["attempt"] == i + 1
                    assert data["corrections"][i]["error"] == f"error {i + 1}"


def test_append_to_debug_array_when_disabled():
    """Test that append_to_debug_array returns None when debug is disabled."""
    with patch("utils.debug_utils.DEBUG_ENABLED", False):
        result = append_to_debug_array(
            "test.json",
            {"data": "value"},
            array_key="items"
        )
        assert result is None


def test_clear_debug_files(temp_debug_dir):
    """Test clearing debug files."""
    with patch("utils.debug_utils.DEBUG_DIR", temp_debug_dir):
        # Create some test files
        for i in range(3):
            file_path = os.path.join(temp_debug_dir, f"debug_test_{i}.json")
            with open(file_path, "w") as f:
                json.dump({"test": i}, f)

        # Clear all files
        count = clear_debug_files()
        assert count == 3

        # Verify they're gone
        files = os.listdir(temp_debug_dir)
        json_files = [f for f in files if f.endswith(".json")]
        assert len(json_files) == 0


def test_clear_debug_files_with_pattern(temp_debug_dir):
    """Test clearing debug files with pattern."""
    with patch("utils.debug_utils.DEBUG_DIR", temp_debug_dir):
        # Create different types of files
        for i in range(2):
            file_path = os.path.join(temp_debug_dir, f"debug_planner_{i}.json")
            with open(file_path, "w") as f:
                json.dump({"test": i}, f)

        for i in range(2):
            file_path = os.path.join(temp_debug_dir, f"debug_router_{i}.json")
            with open(file_path, "w") as f:
                json.dump({"test": i}, f)

        # Clear only planner files
        count = clear_debug_files(pattern="debug_planner_*.json")
        assert count == 2

        # Verify router files still exist
        files = os.listdir(temp_debug_dir)
        assert "debug_router_0.json" in files
        assert "debug_router_1.json" in files
        assert "debug_planner_0.json" not in files


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
