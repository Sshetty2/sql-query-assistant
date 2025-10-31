"""Tests for date filter handling in query generation."""

import pytest
from agent.generate_query import (
    infer_value_type,
    create_typed_literal,
    format_filter_condition,
)
from sqlglot import exp


class TestDateValueTypeInference:
    """Test date/datetime value type inference."""

    def test_infer_date_type(self):
        """Test inference of date format (YYYY-MM-DD)."""
        assert infer_value_type("2025-10-31") == "date"
        assert infer_value_type("2025-01-01") == "date"
        assert infer_value_type("2023-12-31") == "date"

    def test_infer_datetime_type(self):
        """Test inference of datetime format (YYYY-MM-DD HH:MM:SS)."""
        assert infer_value_type("2025-10-31 14:30:00") == "datetime"
        assert infer_value_type("2025-01-01 00:00:00") == "datetime"
        assert infer_value_type("2023-12-31 23:59:59") == "datetime"

    def test_infer_datetime_with_microseconds(self):
        """Test inference of datetime format with microseconds."""
        assert infer_value_type("2025-10-31 14:30:00.123456") == "datetime"
        assert infer_value_type("2025-01-01 00:00:00.000000") == "datetime"

    def test_infer_non_date_strings(self):
        """Test that non-date strings are correctly identified."""
        # Not dates
        assert infer_value_type("2025-10-31T14:30:00") == "string"  # ISO 8601 with T
        assert infer_value_type("10/31/2025") == "string"  # US format
        assert infer_value_type("31-10-2025") == "string"  # UK format
        # Note: We don't validate date ranges (2025-13-01 would match pattern)
        # This is acceptable since the LLM should provide valid dates
        assert infer_value_type("not a date") == "string"

    def test_infer_numeric_types(self):
        """Test that numeric types are still correctly identified."""
        assert infer_value_type(123) == "number"
        assert infer_value_type(45.67) == "number"
        assert infer_value_type("123") == "number"
        assert infer_value_type("45.67") == "number"

    def test_infer_boolean_types(self):
        """Test that boolean types are still correctly identified."""
        assert infer_value_type(True) == "boolean"
        assert infer_value_type(False) == "boolean"
        assert infer_value_type("true") == "boolean"
        assert infer_value_type("false") == "boolean"


class TestDateLiteralCreation:
    """Test date literal creation for SQLGlot."""

    def test_create_date_literal_sql_server(self):
        """Test date literal creation for SQL Server."""
        db_context = {"is_sqlite": False, "is_sql_server": True}
        literal = create_typed_literal("2025-10-31", db_context)

        # Should be a CAST expression
        assert isinstance(literal, exp.Cast)
        sql = literal.sql(dialect="tsql")
        assert "CAST" in sql
        assert "'2025-10-31'" in sql
        assert "DATE" in sql

    def test_create_datetime_literal_sql_server(self):
        """Test datetime literal creation for SQL Server."""
        db_context = {"is_sqlite": False, "is_sql_server": True}
        literal = create_typed_literal("2025-10-31 14:30:00", db_context)

        # Should be a CAST expression
        assert isinstance(literal, exp.Cast)
        sql = literal.sql(dialect="tsql")
        assert "CAST" in sql
        assert "'2025-10-31 14:30:00'" in sql
        assert "DATETIME" in sql

    def test_create_date_literal_sqlite(self):
        """Test date literal creation for SQLite (stored as text)."""
        db_context = {"is_sqlite": True, "is_sql_server": False}
        literal = create_typed_literal("2025-10-31", db_context)

        # Should be a simple string literal
        assert isinstance(literal, exp.Literal)
        sql = literal.sql(dialect="sqlite")
        assert sql == "'2025-10-31'"

    def test_create_datetime_literal_sqlite(self):
        """Test datetime literal creation for SQLite (stored as text)."""
        db_context = {"is_sqlite": True, "is_sql_server": False}
        literal = create_typed_literal("2025-10-31 14:30:00", db_context)

        # Should be a simple string literal
        assert isinstance(literal, exp.Literal)
        sql = literal.sql(dialect="sqlite")
        assert sql == "'2025-10-31 14:30:00'"

    def test_create_numeric_literal_still_works(self):
        """Test that numeric literals still work correctly."""
        literal = create_typed_literal(123)
        assert isinstance(literal, exp.Literal)
        sql = literal.sql()
        assert sql == "123"

    def test_create_string_literal_still_works(self):
        """Test that string literals still work correctly."""
        literal = create_typed_literal("hello world")
        assert isinstance(literal, exp.Literal)
        sql = literal.sql()
        assert sql == "'hello world'"


class TestDateFilterConditions:
    """Test date filter condition formatting (string-based path)."""

    def test_format_date_filter_sql_server(self):
        """Test date filter formatting for SQL Server."""
        db_context_sql_server = {
            "is_sqlite": False,
            "is_sql_server": True,
            "type": "SQL Server",
            "dialect": "tsql",
        }

        condition = format_filter_condition(
            "tb_Users",
            "CreatedOn",
            ">=",
            "2025-10-01",
            db_context=db_context_sql_server,
        )
        assert "tb_Users.CreatedOn >= CAST('2025-10-01' AS DATE)" in condition

    def test_format_datetime_filter_sql_server(self):
        """Test datetime filter formatting for SQL Server."""
        db_context_sql_server = {
            "is_sqlite": False,
            "is_sql_server": True,
            "type": "SQL Server",
            "dialect": "tsql",
        }

        condition = format_filter_condition(
            "tb_Logins",
            "LoginDate",
            ">",
            "2025-10-31 14:30:00",
            db_context=db_context_sql_server,
        )
        assert (
            "tb_Logins.LoginDate > CAST('2025-10-31 14:30:00' AS DATETIME)" in condition
        )

    def test_format_date_filter_sqlite(self):
        """Test date filter formatting for SQLite."""
        db_context_sqlite = {
            "is_sqlite": True,
            "is_sql_server": False,
            "type": "SQLite",
            "dialect": "sqlite",
        }

        condition = format_filter_condition(
            "users", "created_on", ">=", "2025-10-01", db_context=db_context_sqlite
        )
        assert "users.created_on >= '2025-10-01'" in condition
        # SQLite doesn't use CAST
        assert "CAST" not in condition

    def test_format_date_between_filter(self):
        """Test BETWEEN filter with dates."""
        db_context_sql_server = {
            "is_sqlite": False,
            "is_sql_server": True,
            "type": "SQL Server",
            "dialect": "tsql",
        }

        condition = format_filter_condition(
            "tb_Events",
            "EventDate",
            "between",
            ["2025-10-01", "2025-10-31"],
            db_context=db_context_sql_server,
        )
        assert "tb_Events.EventDate BETWEEN" in condition
        assert "CAST('2025-10-01' AS DATE)" in condition
        assert "CAST('2025-10-31' AS DATE)" in condition


class TestDateFilterIntegration:
    """Integration tests for date filters in query generation."""

    def test_date_filter_in_planner_output(self):
        """Test that a planner output with date filters generates correct SQL."""
        from agent.generate_query import build_sql_query

        # Create a minimal planner output with date filter
        planner_output = {
            "decision": "proceed",
            "intent_summary": "Get logins from last 30 days",
            "selections": [
                {
                    "table": "tb_Logins",
                    "alias": None,
                    "confidence": 0.9,
                    "columns": [
                        {
                            "table": "tb_Logins",
                            "column": "LoginDate",
                            "role": "projection",
                            "value_type": "date",
                        },
                        {
                            "table": "tb_Logins",
                            "column": "UserName",
                            "role": "projection",
                            "value_type": "string",
                        },
                    ],
                    "filters": [
                        {
                            "table": "tb_Logins",
                            "column": "LoginDate",
                            "op": ">=",
                            "value": "2025-10-01",
                        }
                    ],
                }
            ],
            "global_filters": [],
            "join_edges": [],
            "ambiguities": [],
        }

        # Create minimal state
        state = {
            "user_question": "Show me logins from the last 30 days",
            "sort_order": "Default",
            "result_limit": 0,
            "time_filter": "All Time",
        }

        # Build SQL (using SQLite for simpler testing)
        db_context = {
            "is_sqlite": True,
            "is_sql_server": False,
            "type": "SQLite",
            "dialect": "sqlite",
        }
        sql = build_sql_query(planner_output, state, db_context)

        # Check that date filter is present (may have escaped quotes in SQL)
        assert "LoginDate" in sql
        assert "2025-10-01" in sql
        assert ">=" in sql
        assert "tb_Logins" in sql


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
