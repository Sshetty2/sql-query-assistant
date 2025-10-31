"""Test column reference detection in filter expressions."""

from agent.generate_query import (
    is_column_reference,
    parse_column_reference,
    build_filter_expression,
)


def test_column_reference_detection():
    """Test detection of column references vs literals."""
    print("Testing column reference detection...")

    # Should be detected as column references
    assert is_column_reference("tb_Users.CompanyID") is True
    print("[PASS] 'tb_Users.CompanyID' detected as column reference")

    assert is_column_reference("table.column") is True
    print("[PASS] 'table.column' detected as column reference")

    assert is_column_reference("TableName.ColumnName") is True
    print("[PASS] 'TableName.ColumnName' detected as column reference")

    # Should NOT be detected as column references
    assert is_column_reference("simple_value") is False
    print("[PASS] 'simple_value' NOT detected as column reference")

    assert is_column_reference("123") is False
    print("[PASS] '123' NOT detected as column reference")

    assert is_column_reference("Active") is False
    print("[PASS] 'Active' NOT detected as column reference")

    assert is_column_reference(123) is False
    print("[PASS] Integer value NOT detected as column reference")


def test_parse_column_reference():
    """Test parsing column references."""
    print("\nTesting column reference parsing...")

    alias_map = {"tb_Users": "u", "tb_Company": "c"}

    # Parse with alias
    col_expr = parse_column_reference("tb_Users.CompanyID", alias_map)
    sql = col_expr.sql(dialect="tsql")
    print(f"Parsed 'tb_Users.CompanyID' (with alias): {sql}")
    assert "CompanyID" in sql
    assert "u" in sql  # Should use alias

    # Parse without alias
    col_expr2 = parse_column_reference("tb_Product.Name", {})
    sql2 = col_expr2.sql(dialect="tsql")
    print(f"Parsed 'tb_Product.Name' (no alias): {sql2}")
    assert "Name" in sql2
    assert "tb_Product" in sql2


def test_filter_with_column_reference():
    """Test building filter expressions with column references."""
    print("\nTesting filter expression building...")

    alias_map = {"tb_Users": "u", "tb_Company": "c"}

    # Test filter with literal value
    filter1 = {
        "table": "tb_Company",
        "column": "Status",
        "op": "=",
        "value": "Active",
    }
    expr1 = build_filter_expression(filter1, alias_map)
    sql1 = expr1.sql(dialect="tsql")
    print(f"\nFilter with literal value:\n  {sql1}")
    # Should have quotes around 'Active'
    assert "'Active'" in sql1 or '"Active"' in sql1
    print("[PASS] Literal value is quoted")

    # Test filter with column reference (the problematic case)
    filter2 = {
        "table": "tb_Company",
        "column": "ID",
        "op": "=",
        "value": "tb_Users.CompanyID",
    }
    expr2 = build_filter_expression(filter2, alias_map)
    sql2 = expr2.sql(dialect="tsql")
    print(f"\nFilter with column reference:\n  {sql2}")
    # Should NOT have quotes around column reference
    assert "'tb_Users.CompanyID'" not in sql2
    assert '"tb_Users.CompanyID"' not in sql2
    # Should reference the columns properly
    assert "CompanyID" in sql2
    print("[PASS] Column reference is NOT quoted")

    # Test != operator with column reference
    filter3 = {
        "table": "tb_Users",
        "column": "ManagerID",
        "op": "!=",
        "value": "tb_Users.UserID",
    }
    expr3 = build_filter_expression(filter3, alias_map)
    sql3 = expr3.sql(dialect="tsql")
    print(f"\nFilter with != and column reference:\n  {sql3}")
    assert "'tb_Users.UserID'" not in sql3
    print("[PASS] Column reference in != is NOT quoted")


if __name__ == "__main__":
    print("="*60)
    test_column_reference_detection()
    print("\n" + "="*60)
    test_parse_column_reference()
    print("\n" + "="*60)
    test_filter_with_column_reference()
    print("\n" + "="*60)
    print("[SUCCESS] All tests passed!")
