"""Test the inline column removal functionality."""

from agent.execute_query import parse_invalid_column_name, remove_column_from_query


def test_parse_column_name():
    """Test parsing invalid column names from error messages."""
    # Test SQL Server error message format
    error_msg = (
        "('42S22', \"[42S22] [Microsoft][ODBC Driver 17 for SQL Server]"
        "[SQL Server]Invalid column name 'OS'. (207) (SQLExecDirectW)\")"
    )

    column_name = parse_invalid_column_name(error_msg)
    print(f"[PASS] Parsed column name: '{column_name}'")
    assert column_name == "OS", f"Expected 'OS', got '{column_name}'"

    # Test with different column name
    error_msg2 = "Invalid column name 'UserStatus'."
    column_name2 = parse_invalid_column_name(error_msg2)
    print(f"[PASS] Parsed column name: '{column_name2}'")
    assert column_name2 == "UserStatus"

    # Test with no match
    error_msg3 = "Some other error"
    column_name3 = parse_invalid_column_name(error_msg3)
    print(f"[PASS] No column name found: {column_name3}")
    assert column_name3 is None


def test_remove_column():
    """Test removing columns from SQL queries."""
    # Test removing a simple column
    query1 = "SELECT Name, OS, Version FROM Products WHERE Active = 1"
    modified1 = remove_column_from_query(query1, "OS")
    print(f"\nOriginal: {query1}")
    print(f"Modified: {modified1}")
    assert "OS" not in modified1
    assert "Name" in modified1
    assert "Version" in modified1
    print("[PASS] Successfully removed 'OS' column")

    # Test removing a column with table prefix
    query2 = "SELECT p.Name, p.OS, p.Version FROM Products AS p"
    modified2 = remove_column_from_query(query2, "OS")
    print(f"\nOriginal: {query2}")
    print(f"Modified: {modified2}")
    assert "OS" not in modified2 or "p.OS" not in modified2
    print("[PASS] Successfully removed 'OS' column with table prefix")

    # Test with aliased column
    query3 = "SELECT Name, OS AS OperatingSystem, Version FROM Products"
    modified3 = remove_column_from_query(query3, "OS")
    print(f"\nOriginal: {query3}")
    print(f"Modified: {modified3}")
    assert "OS" not in modified3 or "OperatingSystem" not in modified3
    print("[PASS] Successfully removed aliased 'OS' column")


if __name__ == "__main__":
    print("Testing column name parsing...")
    test_parse_column_name()

    print("\n" + "="*60)
    print("Testing column removal from queries...")
    test_remove_column()

    print("\n" + "="*60)
    print("[SUCCESS] All tests passed!")
