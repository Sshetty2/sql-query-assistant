"""Test handling of SQL expressions in aggregates, filters, and ORDER BY."""

import pytest
from agent.generate_query import (
    is_sql_expression,
    parse_and_rewrite_expression,
    build_aggregate_expression,
    build_filter_expression,
)


class TestExpressionDetection:
    """Test detection of SQL expressions vs simple column names."""

    def test_simple_column_not_expression(self):
        """Simple column names should not be detected as expressions."""
        assert not is_sql_expression("CustomerId")
        assert not is_sql_expression("FirstName")
        assert not is_sql_expression("total_revenue")

    def test_multiplication_is_expression(self):
        """Multiplication should be detected as expression."""
        assert is_sql_expression("UnitPrice * Quantity")
        assert is_sql_expression("invoice_items.UnitPrice * invoice_items.Quantity")

    def test_function_call_is_expression(self):
        """Function calls should be detected as expressions."""
        assert is_sql_expression("COALESCE(UnitPrice, 0)")
        assert is_sql_expression("CAST(Price AS DECIMAL)")
        assert is_sql_expression("CONCAT(FirstName, ' ', LastName)")

    def test_complex_expression(self):
        """Complex expressions should be detected."""
        expr = "COALESCE(invoice_items.UnitPrice, 0) * COALESCE(invoice_items.Quantity, 0)"
        assert is_sql_expression(expr)

    def test_arithmetic_operations(self):
        """Arithmetic operations should be detected."""
        assert is_sql_expression("Price + Tax")
        assert is_sql_expression("Total - Discount")
        assert is_sql_expression("Price / Quantity")


class TestExpressionParsing:
    """Test parsing and rewriting of SQL expressions."""

    def test_parse_simple_multiplication(self):
        """Test parsing simple multiplication."""
        alias_map = {"items": "i"}
        db_context = {"is_sqlite": True}

        expr_str = "items.UnitPrice * items.Quantity"
        parsed = parse_and_rewrite_expression(expr_str, alias_map, db_context)

        # Check that expression was parsed successfully
        assert parsed is not None

    def test_parse_coalesce_multiplication(self):
        """Test parsing COALESCE with multiplication."""
        alias_map = {"invoice_items": "ii"}
        db_context = {"is_sqlite": True}

        expr_str = "COALESCE(invoice_items.UnitPrice, 0) * COALESCE(invoice_items.Quantity, 0)"
        parsed = parse_and_rewrite_expression(expr_str, alias_map, db_context)

        # Check that expression was parsed successfully
        assert parsed is not None


class TestAggregateExpressions:
    """Test aggregate functions with expressions."""

    def test_simple_sum(self):
        """Test SUM with simple column."""
        agg = {
            "function": "SUM",
            "table": "invoices",
            "column": "Total",
            "alias": "total_sum",
        }
        alias_map = {"invoices": "i"}
        db_context = {"is_sqlite": True}

        result = build_aggregate_expression(agg, alias_map, db_context)

        # Should generate: SUM(i.Total) AS total_sum
        assert result is not None
        sql = result.sql(dialect="sqlite")
        assert "SUM" in sql
        assert "total_sum" in sql

    def test_sum_with_expression(self):
        """Test SUM with complex expression."""
        agg = {
            "function": "SUM",
            "table": "invoice_items",
            "column": "COALESCE(invoice_items.UnitPrice, 0) * COALESCE(invoice_items.Quantity, 0)",
            "alias": "total_revenue",
        }
        alias_map = {"invoice_items": "ii"}
        db_context = {"is_sqlite": True}

        result = build_aggregate_expression(agg, alias_map, db_context)

        # Should generate: SUM(COALESCE(...) * COALESCE(...)) AS total_revenue
        assert result is not None
        sql = result.sql(dialect="sqlite")
        assert "SUM" in sql
        assert "COALESCE" in sql
        assert "total_revenue" in sql
        # Should NOT have table prefix before COALESCE
        assert "ii.COALESCE" not in sql
        assert '"ii"."COALESCE' not in sql

    def test_avg_with_expression(self):
        """Test AVG with expression."""
        agg = {
            "function": "AVG",
            "table": "orders",
            "column": "orders.Total * orders.TaxRate",
            "alias": "avg_taxed_total",
        }
        alias_map = {"orders": "o"}
        db_context = {"is_sqlite": True}

        result = build_aggregate_expression(agg, alias_map, db_context)

        assert result is not None
        sql = result.sql(dialect="sqlite")
        assert "AVG" in sql
        assert "avg_taxed_total" in sql


class TestFilterExpressions:
    """Test filter expressions with complex columns."""

    def test_simple_filter(self):
        """Test filter with simple column."""
        filter_pred = {
            "table": "customers",
            "column": "CustomerId",
            "op": "=",
            "value": 1,
        }
        alias_map = {"customers": "c"}
        db_context = {"is_sqlite": True}

        result = build_filter_expression(filter_pred, alias_map, db_context)

        assert result is not None
        sql = result.sql(dialect="sqlite")
        assert "CustomerId" in sql

    def test_filter_with_expression(self):
        """Test filter with complex expression."""
        filter_pred = {
            "table": "invoice_items",
            "column": "COALESCE(invoice_items.UnitPrice, 0) * COALESCE(invoice_items.Quantity, 0)",
            "op": ">",
            "value": 0,
        }
        alias_map = {"invoice_items": "ii"}
        db_context = {"is_sqlite": True}

        result = build_filter_expression(filter_pred, alias_map, db_context)

        assert result is not None
        sql = result.sql(dialect="sqlite")
        assert "COALESCE" in sql
        assert ">" in sql or "GT" in sql
        # Should NOT have table prefix before COALESCE
        assert "ii.COALESCE" not in sql


class TestIntegrationCustomerRevenue:
    """Integration test for the customer revenue query scenario."""

    def test_customer_revenue_aggregate(self):
        """Test the exact scenario from the bug report."""
        # This is the aggregate from the planner output
        agg = {
            "function": "SUM",
            "table": "invoice_items",
            "column": "COALESCE(invoice_items.UnitPrice, 0) * COALESCE(invoice_items.Quantity, 0)",
            "alias": "total_revenue",
        }
        alias_map = {
            "customers": "customers",
            "invoices": "invoices",
            "invoice_items": "invoice_items",
        }
        db_context = {"is_sqlite": True}

        result = build_aggregate_expression(agg, alias_map, db_context)

        sql = result.sql(dialect="sqlite", pretty=True, identify=True)
        print(f"\n\nGenerated SQL:\n{sql}\n")

        # Verify the SQL is valid
        assert "SUM" in sql
        assert "COALESCE" in sql
        assert "total_revenue" in sql

        # Critical: Should NOT have malformed syntax like:
        # "invoice_items"."COALESCE(...)"
        # or "invoice_items".COALESCE(...)
        assert '"invoice_items"."COALESCE' not in sql
        assert '"invoice_items".COALESCE' not in sql
        assert "invoice_items.COALESCE" not in sql

    def test_customer_revenue_having(self):
        """Test HAVING clause with expression."""
        # This is the HAVING filter from the original planner output
        having_filter = {
            "table": "invoice_items",
            "column": "COALESCE(invoice_items.UnitPrice, 0) * COALESCE(invoice_items.Quantity, 0)",
            "op": ">",
            "value": 0,
        }
        alias_map = {
            "customers": "customers",
            "invoices": "invoices",
            "invoice_items": "invoice_items",
        }
        db_context = {"is_sqlite": True}

        result = build_filter_expression(having_filter, alias_map, db_context)

        sql = result.sql(dialect="sqlite", pretty=True, identify=True)
        print(f"\n\nGenerated HAVING SQL:\n{sql}\n")

        # Verify the SQL is valid
        assert "COALESCE" in sql
        assert ">" in sql or "GT" in sql

        # Should NOT have malformed syntax
        assert '"invoice_items"."COALESCE' not in sql
        assert '"invoice_items".COALESCE' not in sql
