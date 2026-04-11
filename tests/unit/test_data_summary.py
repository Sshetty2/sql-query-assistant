"""Unit tests for the data summary module."""

import json
import pytest
from agent.generate_data_summary import compute_data_summary, _detect_column_type


class TestDetectColumnType:
    """Tests for column type detection."""

    def test_numeric_ints(self):
        assert _detect_column_type([1, 2, 3]) == "numeric"

    def test_numeric_floats(self):
        assert _detect_column_type([1.5, 2.3, 3.7]) == "numeric"

    def test_numeric_mixed(self):
        assert _detect_column_type([1, 2.5, 3]) == "numeric"

    def test_text_strings(self):
        assert _detect_column_type(["hello", "world"]) == "text"

    def test_boolean(self):
        assert _detect_column_type([True, False, True]) == "boolean"

    def test_datetime_iso(self):
        assert _detect_column_type(["2024-01-15T10:30:00", "2024-02-20T14:00:00"]) == "datetime"

    def test_datetime_date_only(self):
        assert _detect_column_type(["2024-01-15", "2024-02-20"]) == "datetime"

    def test_empty_returns_null(self):
        assert _detect_column_type([]) == "null"

    def test_numeric_strings(self):
        """Strings that look like numbers should be detected as numeric."""
        assert _detect_column_type(["123", "456.78"]) == "numeric"

    def test_majority_type_wins(self):
        """When types are mixed, the majority type should win."""
        assert _detect_column_type([1, 2, 3, "text"]) == "numeric"


class TestComputeDataSummary:
    """Tests for the main compute_data_summary function."""

    def test_empty_json(self):
        summary = compute_data_summary("[]", None)
        assert summary["row_count"] == 0
        assert summary["column_count"] == 0
        assert summary["columns"] == {}

    def test_invalid_json(self):
        summary = compute_data_summary("not json", None)
        assert summary["row_count"] == 0

    def test_none_input(self):
        summary = compute_data_summary(None, None)
        assert summary["row_count"] == 0

    def test_basic_numeric_column(self):
        data = [{"value": 10}, {"value": 20}, {"value": 30}]
        summary = compute_data_summary(json.dumps(data), 100)

        assert summary["row_count"] == 3
        assert summary["total_records_available"] == 100
        assert summary["column_count"] == 1

        col = summary["columns"]["value"]
        assert col["type"] == "numeric"
        assert col["null_count"] == 0
        assert col["distinct_count"] == 3
        assert col["min"] == 10.0
        assert col["max"] == 30.0
        assert col["avg"] == 20.0
        assert col["median"] == 20.0
        assert col["sum"] == 60.0

    def test_text_column_with_top_values(self):
        data = [
            {"name": "Alice"},
            {"name": "Bob"},
            {"name": "Alice"},
            {"name": "Charlie"},
            {"name": "Alice"},
        ]
        summary = compute_data_summary(json.dumps(data), None)

        col = summary["columns"]["name"]
        assert col["type"] == "text"
        assert col["distinct_count"] == 3
        assert col["null_count"] == 0
        # Top value should be Alice with count 3
        assert col["top_values"][0]["value"] == "Alice"
        assert col["top_values"][0]["count"] == 3

    def test_datetime_column(self):
        data = [
            {"created": "2024-01-01T00:00:00"},
            {"created": "2024-01-15T12:00:00"},
            {"created": "2024-02-01T00:00:00"},
        ]
        summary = compute_data_summary(json.dumps(data), None)

        col = summary["columns"]["created"]
        assert col["type"] == "datetime"
        assert col["min"] == "2024-01-01T00:00:00"
        assert col["max"] == "2024-02-01T00:00:00"
        assert col["range_days"] == 31.0  # ~31 days

    def test_null_handling(self):
        data = [
            {"value": 10},
            {"value": None},
            {"value": 30},
            {"value": None},
        ]
        summary = compute_data_summary(json.dumps(data), None)

        col = summary["columns"]["value"]
        assert col["null_count"] == 2
        assert col["distinct_count"] == 2
        assert col["type"] == "numeric"
        assert col["min"] == 10.0
        assert col["max"] == 30.0

    def test_multiple_columns(self):
        data = [
            {"id": 1, "name": "Alice", "score": 95.5},
            {"id": 2, "name": "Bob", "score": 87.0},
        ]
        summary = compute_data_summary(json.dumps(data), None)

        assert summary["column_count"] == 3
        assert "id" in summary["columns"]
        assert "name" in summary["columns"]
        assert "score" in summary["columns"]
        assert summary["columns"]["id"]["type"] == "numeric"
        assert summary["columns"]["name"]["type"] == "text"
        assert summary["columns"]["score"]["type"] == "numeric"

    def test_boolean_column(self):
        data = [
            {"active": True},
            {"active": False},
            {"active": True},
        ]
        summary = compute_data_summary(json.dumps(data), None)

        col = summary["columns"]["active"]
        assert col["type"] == "boolean"
        assert col["distinct_count"] == 2
        assert col["null_count"] == 0

    def test_all_nulls_column(self):
        data = [
            {"value": None},
            {"value": None},
        ]
        summary = compute_data_summary(json.dumps(data), None)

        col = summary["columns"]["value"]
        assert col["type"] == "null"
        assert col["null_count"] == 2
        assert col["distinct_count"] == 0

    def test_single_row(self):
        data = [{"x": 42}]
        summary = compute_data_summary(json.dumps(data), 1)

        assert summary["row_count"] == 1
        assert summary["total_records_available"] == 1
        col = summary["columns"]["x"]
        assert col["min"] == 42.0
        assert col["max"] == 42.0
        assert col["avg"] == 42.0
        assert col["median"] == 42.0

    def test_text_length_stats(self):
        data = [
            {"name": "Al"},
            {"name": "Bob"},
            {"name": "Charlie"},
        ]
        summary = compute_data_summary(json.dumps(data), None)

        col = summary["columns"]["name"]
        assert col["min_length"] == 2
        assert col["max_length"] == 7

    def test_total_records_passthrough(self):
        data = [{"x": 1}]
        summary = compute_data_summary(json.dumps(data), 5000)
        assert summary["total_records_available"] == 5000

    def test_date_only_detection(self):
        data = [
            {"date": "2024-01-15"},
            {"date": "2024-02-20"},
        ]
        summary = compute_data_summary(json.dumps(data), None)
        assert summary["columns"]["date"]["type"] == "datetime"
