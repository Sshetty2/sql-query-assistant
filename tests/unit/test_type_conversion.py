"""Unit tests for defensive type conversion in SQL generation."""

import pytest
from sqlglot import exp

from agent.generate_query import (
    infer_value_type,
    create_typed_literal,
    build_filter_expression,
    format_filter_condition,
)


class TestValueTypeInference:
    """Test the infer_value_type function."""

    def test_null_values(self):
        """Test NULL value inference."""
        assert infer_value_type(None) == 'null'
        assert infer_value_type('NULL') == 'null'
        assert infer_value_type('null') == 'null'

    def test_boolean_values(self):
        """Test boolean value inference."""
        assert infer_value_type(True) == 'boolean'
        assert infer_value_type(False) == 'boolean'
        assert infer_value_type('true') == 'boolean'
        assert infer_value_type('false') == 'boolean'
        assert infer_value_type('True') == 'boolean'
        assert infer_value_type('False') == 'boolean'

    def test_numeric_values(self):
        """Test numeric value inference."""
        # String '0' and '1' should be treated as numbers for BIT compatibility
        assert infer_value_type('0') == 'number'
        assert infer_value_type('1') == 'number'
        assert infer_value_type(0) == 'number'
        assert infer_value_type(1) == 'number'
        assert infer_value_type(42) == 'number'
        assert infer_value_type(3.14) == 'number'
        assert infer_value_type('42') == 'number'
        assert infer_value_type('3.14') == 'number'
        assert infer_value_type('9.0') == 'number'

    def test_string_values(self):
        """Test string value inference."""
        assert infer_value_type('hello') == 'string'
        assert infer_value_type('Critical') == 'string'
        assert infer_value_type('CRITICAL') == 'string'
        assert infer_value_type('%login%') == 'string'
        assert infer_value_type('') == 'string'


class TestTypedLiteralCreation:
    """Test the create_typed_literal function."""

    def test_null_literal(self):
        """Test NULL literal creation."""
        literal = create_typed_literal(None)
        assert isinstance(literal, exp.Null)

        literal = create_typed_literal('NULL')
        assert isinstance(literal, exp.Null)

    def test_boolean_literal(self):
        """Test boolean literal creation (converted to 1/0 for BIT)."""
        # Python booleans
        literal = create_typed_literal(True)
        assert isinstance(literal, exp.Literal)
        assert literal.sql() == '1'

        literal = create_typed_literal(False)
        assert isinstance(literal, exp.Literal)
        assert literal.sql() == '0'

        # String booleans
        literal = create_typed_literal('true')
        assert literal.sql() == '1'

        literal = create_typed_literal('false')
        assert literal.sql() == '0'

    def test_numeric_literal(self):
        """Test numeric literal creation."""
        # Integer
        literal = create_typed_literal(0)
        assert isinstance(literal, exp.Literal)
        assert literal.sql() == '0'

        literal = create_typed_literal(42)
        assert literal.sql() == '42'

        # Float
        literal = create_typed_literal(3.14)
        assert literal.sql() == '3.14'

        # String numbers (for BIT columns: '0', '1')
        literal = create_typed_literal('0')
        assert literal.sql() == '0'

        literal = create_typed_literal('1')
        assert literal.sql() == '1'

        # String decimals
        literal = create_typed_literal('9.0')
        assert literal.sql() == '9.0'

    def test_string_literal(self):
        """Test string literal creation."""
        literal = create_typed_literal('hello')
        assert isinstance(literal, exp.Literal)
        assert literal.sql() == "'hello'"

        literal = create_typed_literal('Critical')
        assert literal.sql() == "'Critical'"


class TestBuildFilterExpression:
    """Test the build_filter_expression function with proper type handling."""

    def test_bit_column_equality(self):
        """Test BIT column equality with 0/1 values."""
        filter_pred = {
            'table': 'tb_Test',
            'column': 'IsDeleted',
            'op': '=',
            'value': 0
        }
        alias_map = {'tb_Test': 'tb_Test'}

        expr = build_filter_expression(filter_pred, alias_map)
        sql = expr.sql(dialect='tsql')

        # Should be: tb_Test.IsDeleted = 0 (not '0')
        assert '= 0' in sql or '= 0' in sql.replace(' ', '')
        assert "'0'" not in sql

    def test_bit_column_equality_string_value(self):
        """Test BIT column equality with string '0'/'1' values."""
        filter_pred = {
            'table': 'tb_Test',
            'column': 'IsDeleted',
            'op': '=',
            'value': '0'
        }
        alias_map = {'tb_Test': 'tb_Test'}

        expr = build_filter_expression(filter_pred, alias_map)
        sql = expr.sql(dialect='tsql')

        # Should be: tb_Test.IsDeleted = 0 (not '0')
        assert '= 0' in sql or '= 0' in sql.replace(' ', '')
        assert "'0'" not in sql

    def test_numeric_comparison(self):
        """Test numeric comparison operators."""
        filter_pred = {
            'table': 'tb_CVE',
            'column': 'CVSSScore',
            'op': '>=',
            'value': 9.0
        }
        alias_map = {'tb_CVE': 'tb_CVE'}

        expr = build_filter_expression(filter_pred, alias_map)
        sql = expr.sql(dialect='tsql')

        # Should be: tb_CVE.CVSSScore >= 9.0 (not '9.0')
        assert '>= 9' in sql or '>= 9.0' in sql
        assert "'9" not in sql

    def test_string_in_operator(self):
        """Test IN operator with string values."""
        filter_pred = {
            'table': 'tb_CVE',
            'column': 'Priority',
            'op': 'in',
            'value': ['Critical', 'CRITICAL', 'critical']
        }
        alias_map = {'tb_CVE': 'tb_CVE'}

        expr = build_filter_expression(filter_pred, alias_map)
        sql = expr.sql(dialect='tsql')

        # Should have quoted strings
        assert "'Critical'" in sql or '"Critical"' in sql
        assert 'IN' in sql.upper()

    def test_in_operator_with_null(self):
        """Test IN operator with NULL values (should convert to OR IS NULL)."""
        filter_pred = {
            'table': 'tb_Test',
            'column': 'IsDeleted',
            'op': 'in',
            'value': [0, None]
        }
        alias_map = {'tb_Test': 'tb_Test'}

        expr = build_filter_expression(filter_pred, alias_map)
        sql = expr.sql(dialect='tsql')

        # Should be: (col IN (0) OR col IS NULL)
        assert 'IS NULL' in sql.upper()
        assert 'OR' in sql.upper()

    def test_in_operator_only_null(self):
        """Test IN operator with only NULL value."""
        filter_pred = {
            'table': 'tb_Test',
            'column': 'IsDeleted',
            'op': 'in',
            'value': [None]
        }
        alias_map = {'tb_Test': 'tb_Test'}

        expr = build_filter_expression(filter_pred, alias_map)
        sql = expr.sql(dialect='tsql')

        # Should be: col IS NULL (not IN)
        assert 'IS NULL' in sql.upper()
        assert 'IN' not in sql.upper() or 'IN (' not in sql.upper()


class TestFormatFilterCondition:
    """Test the format_filter_condition function with proper type handling."""

    def test_bit_column_equality(self):
        """Test BIT column equality in string-based SQL generation."""
        condition = format_filter_condition('tb_Test', 'IsDeleted', '=', 0)

        # Should be: tb_Test.IsDeleted = 0 (not '0')
        assert "= 0" in condition
        assert "'0'" not in condition

    def test_bit_column_equality_string_value(self):
        """Test BIT column equality with string value."""
        condition = format_filter_condition('tb_Test', 'IsDeleted', '=', '0')

        # Should be: tb_Test.IsDeleted = 0 (not '0')
        assert "= 0" in condition
        assert "'0'" not in condition

    def test_numeric_comparison(self):
        """Test numeric comparison."""
        condition = format_filter_condition('tb_CVE', 'CVSSScore', '>=', 9.0)

        # Should be: tb_CVE.CVSSScore >= 9.0 (not '9.0')
        assert ">= 9" in condition
        assert "'>= 9" not in condition

    def test_string_equality(self):
        """Test string equality."""
        condition = format_filter_condition('tb_CVE', 'Priority', '=', 'Critical')

        # Should be: tb_CVE.Priority = 'Critical'
        assert "= 'Critical'" in condition

    def test_in_operator_with_numbers(self):
        """Test IN operator with numeric values."""
        condition = format_filter_condition('tb_Test', 'IsDeleted', 'in', [0, 1])

        # Should be: tb_Test.IsDeleted IN (0, 1) (not '0', '1')
        assert "IN (0, 1)" in condition
        assert "'0'" not in condition

    def test_in_operator_with_strings(self):
        """Test IN operator with string values."""
        condition = format_filter_condition('tb_CVE', 'Priority', 'in', ['Critical', 'High'])

        # Should be: tb_CVE.Priority IN ('Critical', 'High')
        assert "IN ('Critical', 'High')" in condition

    def test_in_operator_with_null(self):
        """Test IN operator with NULL values."""
        condition = format_filter_condition('tb_Test', 'IsDeleted', 'in', [0, None])

        # Should be: (tb_Test.IsDeleted IN (0) OR tb_Test.IsDeleted IS NULL)
        assert "IS NULL" in condition
        assert "OR" in condition
        assert "IN (0)" in condition

    def test_in_operator_only_null(self):
        """Test IN operator with only NULL."""
        condition = format_filter_condition('tb_Test', 'IsDeleted', 'in', [None])

        # Should be: tb_Test.IsDeleted IS NULL
        assert "IS NULL" in condition
        assert "IN" not in condition or "IN (" not in condition


class TestRealWorldScenarios:
    """Test real-world scenarios from the CVE query bug."""

    def test_cve_query_filters(self):
        """Test the exact filters from the CVE query that caused the error."""
        # tb_SaasComputers.IsDeleted = 0
        condition1 = format_filter_condition('tb_SaasComputers', 'IsDeleted', '=', 0)
        assert "= 0" in condition1
        assert "'0'" not in condition1

        # tb_SaasComputerCVEMap.IsDeleted = 0
        condition2 = format_filter_condition('tb_SaasComputerCVEMap', 'IsDeleted', '=', 0)
        assert "= 0" in condition2
        assert "'0'" not in condition2

        # tb_CVE.CVSSScore >= 9.0
        condition3 = format_filter_condition('tb_CVE', 'CVSSScore', '>=', 9.0)
        assert ">= 9" in condition3
        assert "'9" not in condition3

        # tb_CVE.Priority IN ('Critical', 'CRITICAL', 'critical')
        condition4 = format_filter_condition('tb_CVE', 'Priority', 'in', ['Critical', 'CRITICAL', 'critical'])
        assert "IN (" in condition4
        assert "'Critical'" in condition4

        # tb_CVE.IsDeleted IN (0, null)
        condition5 = format_filter_condition('tb_CVE', 'IsDeleted', 'in', [0, None])
        assert "IS NULL" in condition5
        assert "OR" in condition5
        assert "IN (0)" in condition5 or "IN (0 )" in condition5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
