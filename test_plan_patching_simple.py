"""
Simple test script for plan patching functionality (Windows-compatible).

This script tests the complete plan patching workflow without fancy Unicode.
"""

import os
import json
from dotenv import load_dotenv
from agent.query_database import query_database

# Load environment variables
load_dotenv()

# Ensure we use test database
os.environ["USE_TEST_DB"] = "true"


def print_section(title):
    """Print a section header."""
    print(f"\n{'=' * 80}")
    print(f"{title}")
    print('=' * 80)


def test_1_initial_query():
    """Test 1: Execute initial query."""
    print_section("TEST 1: Initial Query Execution")

    print("Executing query: 'Show me all tracks with their genre'")

    response = query_database(
        "Show me all tracks with their genre",
        result_limit=0,
        thread_id=None
    )

    state = response["state"]

    # Check for successful execution
    assert state.get("query"), "ERROR: No SQL query generated"
    assert state.get("result"), "ERROR: No results returned"
    assert state.get("executed_plan"), "ERROR: No executed plan saved"
    assert state.get("modification_options"), "ERROR: No modification options generated"

    print("[PASS] Query executed successfully")

    # Display SQL (first 200 chars)
    sql = state['query'][:200]
    print(f"\nGenerated SQL: {sql}...")

    # Display result count
    result_data = json.loads(state["result"])
    print(f"Results: {len(result_data)} rows returned")

    # Display plan summary
    plan = state["executed_plan"]
    print("\nPlan Summary:")
    print(f"  Intent: {plan.get('intent_summary', 'N/A')}")
    print(f"  Tables: {', '.join([s['table'] for s in plan.get('selections', [])])}")

    # Display modification options summary
    options = state["modification_options"]
    tables = options.get("tables", {})
    print("\nModification Options:")
    print(f"  Available tables: {', '.join(tables.keys())}")

    return state


def test_2_add_column(initial_state):
    """Test 2: Add a column via patching."""
    print_section("TEST 2: Add Column (Composer)")

    executed_plan = initial_state["executed_plan"]
    filtered_schema = initial_state["filtered_schema"]
    thread_id = initial_state["thread_id"]

    # Find the Track table
    track_table = next((s for s in executed_plan["selections"] if "track" in s["table"].lower()), None)
    assert track_table, "ERROR: Track table not found in plan"

    table_name = track_table["table"]
    print(f"Adding column 'Composer' to table '{table_name}'")

    # Create patch operation
    patch_op = {
        "operation": "add_column",
        "table": table_name,
        "column": "Composer"
    }

    # Execute patch
    response = query_database(
        "Show me all tracks with their genre",
        patch_operation=patch_op,
        executed_plan=executed_plan,
        filtered_schema=filtered_schema,
        thread_id=thread_id
    )

    state = response["state"]

    # Verify column was added
    assert state.get("query"), "ERROR: No SQL query generated"
    assert "Composer" in state["query"], "ERROR: Composer column not in SQL"

    print("[PASS] Column added successfully")

    # Display results
    result_data = json.loads(state["result"])
    print(f"Results: {len(result_data)} rows returned")

    # Verify Composer column exists in results
    if result_data:
        assert "Composer" in result_data[0], "ERROR: Composer column not in results"
        print("[PASS] Composer column appears in results")
        print(f"  Sample: {result_data[0].get('Composer', 'N/A')}")

    return state


def test_3_remove_column(previous_state):
    """Test 3: Remove a column via patching."""
    print_section("TEST 3: Remove Column (Composer)")

    executed_plan = previous_state["executed_plan"]
    filtered_schema = previous_state["filtered_schema"]
    thread_id = previous_state["thread_id"]

    # Find the Track table
    track_table = next((s for s in executed_plan["selections"] if "track" in s["table"].lower()), None)
    table_name = track_table["table"]

    print(f"Removing column 'Composer' from table '{table_name}'")

    # Create patch operation
    patch_op = {
        "operation": "remove_column",
        "table": table_name,
        "column": "Composer"
    }

    # Execute patch
    response = query_database(
        "Show me all tracks with their genre",
        patch_operation=patch_op,
        executed_plan=executed_plan,
        filtered_schema=filtered_schema,
        thread_id=thread_id
    )

    state = response["state"]

    # Verify column was removed
    assert state.get("query"), "ERROR: No SQL query generated"

    print("[PASS] Column removed successfully")

    # Display results
    result_data = json.loads(state["result"])
    print(f"Results: {len(result_data)} rows returned")

    # Verify Composer column is gone from results
    if result_data:
        assert "Composer" not in result_data[0], "ERROR: Composer column still in results"
        print("[PASS] Composer column removed from results")

    return state


def test_4_modify_order_by(previous_state):
    """Test 4: Modify ORDER BY via patching."""
    print_section("TEST 4: Modify ORDER BY (Sort by Name DESC)")

    executed_plan = previous_state["executed_plan"]
    filtered_schema = previous_state["filtered_schema"]
    thread_id = previous_state["thread_id"]

    # Find Track table
    track_table = next((s for s in executed_plan["selections"] if "track" in s["table"].lower()), None)
    table_name = track_table["table"]

    print(f"Setting ORDER BY to {table_name}.Name DESC")

    # Create patch operation
    patch_op = {
        "operation": "modify_order_by",
        "order_by": [
            {
                "table": table_name,
                "column": "Name",
                "direction": "DESC"
            }
        ]
    }

    # Execute patch
    response = query_database(
        "Show me all tracks with their genre",
        patch_operation=patch_op,
        executed_plan=executed_plan,
        filtered_schema=filtered_schema,
        thread_id=thread_id
    )

    state = response["state"]

    # Verify ORDER BY was added
    assert state.get("query"), "ERROR: No SQL query generated"
    assert "ORDER BY" in state["query"].upper(), "ERROR: ORDER BY not in SQL"
    assert "DESC" in state["query"].upper(), "ERROR: DESC not in SQL"

    print("[PASS] ORDER BY modified successfully")

    # Display results
    result_data = json.loads(state["result"])
    print(f"Results: {len(result_data)} rows returned (sorted)")

    # Show first few track names
    if len(result_data) >= 3:
        print("  Top 3 tracks (by name DESC):")
        for i in range(3):
            print(f"    {i+1}. {result_data[i].get('Name', 'N/A')}")

    return state


def test_5_modify_limit(previous_state):
    """Test 5: Modify LIMIT via patching."""
    print_section("TEST 5: Modify LIMIT (Limit to 10 rows)")

    executed_plan = previous_state["executed_plan"]
    filtered_schema = previous_state["filtered_schema"]
    thread_id = previous_state["thread_id"]

    print("Setting LIMIT to 10")

    # Create patch operation
    patch_op = {
        "operation": "modify_limit",
        "limit": 10
    }

    # Execute patch
    response = query_database(
        "Show me all tracks with their genre",
        patch_operation=patch_op,
        executed_plan=executed_plan,
        filtered_schema=filtered_schema,
        thread_id=thread_id
    )

    state = response["state"]

    # Verify LIMIT was added
    assert state.get("query"), "ERROR: No SQL query generated"
    result_data = json.loads(state["result"])

    print("[PASS] LIMIT modified successfully")

    # Display results
    print(f"Results: {len(result_data)} rows returned")

    # Verify exactly 10 rows returned
    assert len(result_data) == 10, f"ERROR: Expected 10 rows, got {len(result_data)}"
    print("[PASS] Returned exactly 10 rows")

    return state


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("PLAN PATCHING TEST SUITE")
    print("Testing the complete plan patching workflow")
    print("=" * 80)

    try:
        # Test 1: Initial query
        print("\nRunning Test 1...")
        state1 = test_1_initial_query()

        # Test 2: Add column
        print("\nRunning Test 2...")
        state2 = test_2_add_column(state1)

        # Test 3: Remove column
        print("\nRunning Test 3...")
        state3 = test_3_remove_column(state2)

        # Test 4: Modify ORDER BY
        print("\nRunning Test 4...")
        state4 = test_4_modify_order_by(state3)

        # Test 5: Modify LIMIT
        print("\nRunning Test 5...")
        _ = test_5_modify_limit(state4)

        # Summary
        print("\n" + "=" * 80)
        print("TEST RESULTS SUMMARY")
        print("=" * 80)
        print("\n[PASS] All tests passed successfully!")
        print("\nPlan patching is working correctly:")
        print("  - Initial query execution: PASS")
        print("  - Add column: PASS")
        print("  - Remove column: PASS")
        print("  - Modify ORDER BY: PASS")
        print("  - Modify LIMIT: PASS")
        print("\n" + "=" * 80)

        return 0

    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {str(e)}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
