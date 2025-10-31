"""Unit tests for unquoting SQL functions in filter values."""

import pytest
from agent.generate_query import unquote_sql_functions, format_filter_condition


class TestUnquoteSqlFunctions:
    """Test the unquote_sql_functions utility."""

    def test_unquote_dateadd_function(self):
        """Test unquoting DATEADD function."""
        value = "'DATEADD(DAY, -60, GETDATE())'"
        result = unquote_sql_functions(value)
        assert result == "DATEADD(DAY, -60, GETDATE())"

    def test_unquote_getdate_function(self):
        """Test unquoting GETDATE function."""
        value = "'GETDATE()'"
        result = unquote_sql_functions(value)
        assert result == "GETDATE()"

    def test_unquote_cast_function(self):
        """Test unquoting CAST function."""
        value = "'CAST(SomeColumn AS INT)'"
        result = unquote_sql_functions(value)
        assert result == "CAST(SomeColumn AS INT)"

    def test_unquote_datediff_function(self):
        """Test unquoting DATEDIFF function."""
        value = "'DATEDIFF(day, StartDate, EndDate)'"
        result = unquote_sql_functions(value)
        assert result == "DATEDIFF(day, StartDate, EndDate)"

    def test_unquote_complex_nested_function(self):
        """Test unquoting nested function calls."""
        value = "'DATEADD(d,-60,GETDATE())'"
        result = unquote_sql_functions(value)
        assert result == "DATEADD(d,-60,GETDATE())"

    def test_preserve_normal_quoted_strings(self):
        """Test that normal quoted strings are not unquoted."""
        value = "'normal string'"
        result = unquote_sql_functions(value)
        assert result == "'normal string'"

    def test_preserve_dates(self):
        """Test that date strings are not unquoted."""
        value = "'2025-10-31'"
        result = unquote_sql_functions(value)
        assert result == "'2025-10-31'"

    def test_preserve_datetimes(self):
        """Test that datetime strings are not unquoted."""
        value = "'2025-10-31 14:30:00'"
        result = unquote_sql_functions(value)
        assert result == "'2025-10-31 14:30:00'"

    def test_preserve_unquoted_strings(self):
        """Test that unquoted strings pass through unchanged."""
        value = "GETDATE()"
        result = unquote_sql_functions(value)
        assert result == "GETDATE()"

    def test_preserve_numbers(self):
        """Test that numbers pass through unchanged."""
        assert unquote_sql_functions(123) == 123
        assert unquote_sql_functions(45.67) == 45.67

    def test_preserve_none(self):
        """Test that None passes through unchanged."""
        assert unquote_sql_functions(None) is None

    def test_preserve_booleans(self):
        """Test that booleans pass through unchanged."""
        assert unquote_sql_functions(True) is True
        assert unquote_sql_functions(False) is False

    def test_case_insensitive_function_names(self):
        """Test that function detection is case-insensitive."""
        assert unquote_sql_functions("'DATEADD()'") == "DATEADD()"
        assert unquote_sql_functions("'dateadd()'") == "dateadd()"
        assert unquote_sql_functions("'DateAdd()'") == "DateAdd()"

    def test_underscore_in_function_names(self):
        """Test functions with underscores in names."""
        value = "'MY_CUSTOM_FUNCTION(arg1, arg2)'"
        result = unquote_sql_functions(value)
        assert result == "MY_CUSTOM_FUNCTION(arg1, arg2)"

    def test_function_with_spaces(self):
        """Test function with spaces before parentheses."""
        value = "'GETDATE ()'"
        result = unquote_sql_functions(value)
        assert result == "GETDATE ()"


class TestFormatFilterConditionUnquoting:
    """Test that format_filter_condition applies unquoting correctly."""

    def test_filter_with_quoted_dateadd(self):
        """Test filter condition with quoted DATEADD function."""
        # Simulate LLM providing quoted DATEADD
        condition = format_filter_condition(
            table_alias="tb_SaasScan",
            column="Schedule",
            op=">=",
            value="'DATEADD(DAY, -60, GETDATE())'",
            db_context={"is_sqlite": False, "is_sql_server": True}
        )

        # Should not double-quote the function
        assert "DATEADD(DAY, -60, GETDATE())" in condition
        assert "'DATEADD" not in condition  # Should not have quoted function

    def test_filter_with_quoted_getdate(self):
        """Test filter condition with quoted GETDATE function."""
        condition = format_filter_condition(
            table_alias="tb_Logins",
            column="LoginDate",
            op=">",
            value="'GETDATE()'",
            db_context={"is_sqlite": False, "is_sql_server": True}
        )

        assert "GETDATE()" in condition
        assert "'GETDATE" not in condition

    def test_filter_with_normal_date_string(self):
        """Test that normal date strings still work correctly."""
        condition = format_filter_condition(
            table_alias="tb_Users",
            column="CreatedOn",
            op=">=",
            value="2025-10-31",
            db_context={"is_sqlite": False, "is_sql_server": True}
        )

        # Date should be properly cast
        assert "CAST('2025-10-31' AS DATE)" in condition

    def test_filter_between_with_quoted_functions(self):
        """Test BETWEEN operator with quoted functions in list."""
        condition = format_filter_condition(
            table_alias="tb_Events",
            column="EventDate",
            op="between",
            value=["'DATEADD(DAY, -30, GETDATE())'", "'GETDATE()'"],
            db_context={"is_sqlite": False, "is_sql_server": True}
        )

        # Both functions should be unquoted
        assert "DATEADD(DAY, -30, GETDATE())" in condition
        assert "GETDATE()" in condition
        assert "'DATEADD" not in condition
        assert "'GETDATE" not in condition

    def test_filter_in_with_mixed_values(self):
        """Test IN operator with mix of normal values and quoted functions."""
        condition = format_filter_condition(
            table_alias="tb_Data",
            column="Status",
            op="in",
            value=["Active", "'GETDATE()'"],
            db_context={"is_sqlite": False, "is_sql_server": True}
        )

        # Normal string should be quoted, function should not
        assert "'Active'" in condition
        assert "GETDATE()" in condition

    def test_filter_preserves_normal_functionality(self):
        """Test that unquoting doesn't break normal filter behavior."""
        # Test various normal cases
        test_cases = [
            ("tb_Users", "Name", "=", "John", None),
            ("tb_Products", "Price", ">", 100, None),
            ("tb_Orders", "IsActive", "=", True, None),
            ("tb_Dates", "CreatedOn", ">=", "2025-01-01", {"is_sql_server": True}),
        ]

        for table, column, op, value, context in test_cases:
            # Should not raise errors
            result = format_filter_condition(table, column, op, value, db_context=context)
            assert len(result) > 0  # Should produce valid SQL


class TestBenchmarkErrorScenarios:
    """Test specific error scenarios from the benchmark analysis."""

    def test_gpt4o_mini_query4_scenario(self):
        """
        Test the specific error from gpt-4o-mini / query_4:
        WHERE [tb_SaasScan].[Schedule] >= 'DATEADD(DAY, -60, GETDATE())'
        """
        # This was causing SQL error: Conversion failed when converting date
        condition = format_filter_condition(
            table_alias="[tb_SaasScan]",
            column="Schedule",
            op=">=",
            value="'DATEADD(DAY, -60, GETDATE())'",
            db_context={"is_sqlite": False, "is_sql_server": True}
        )

        # Should produce valid unquoted function
        assert "DATEADD(DAY, -60, GETDATE())" in condition
        # Should not have the error-causing quoted function
        assert "'DATEADD(DAY, -60, GETDATE())'" not in condition

    def test_qwen3_8b_query4_scenario(self):
        """
        Test the specific error from qwen3-8b / query_4:
        WHERE [tb_SaasScan].[Schedule] >= 'DATEADD(d,-60,GETDATE())'
        """
        condition = format_filter_condition(
            table_alias="[tb_SaasScan]",
            column="Schedule",
            op=">=",
            value="'DATEADD(d,-60,GETDATE())'",
            db_context={"is_sqlite": False, "is_sql_server": True}
        )

        # Should produce valid unquoted function
        assert "DATEADD(d,-60,GETDATE())" in condition
        # Should not have the error-causing quoted function
        assert "'DATEADD(d,-60,GETDATE())'" not in condition
