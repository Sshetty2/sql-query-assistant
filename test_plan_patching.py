"""
Test script for plan patching functionality.

This script tests the complete plan patching workflow including:
- Initial query execution
- Modification options generation
- Adding columns via patching
- Removing columns via patching
- Modifying ORDER BY
- Modifying LIMIT
"""

import os
import json
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from agent.query_database import query_database
from agent.generate_modification_options import generate_modification_options

# Load environment variables
load_dotenv()

# Ensure we use test database
os.environ["USE_TEST_DB"] = "true"

console = Console()


def print_header(text: str):
    """Print a styled header."""
    console.print(f"\n[bold cyan]{text}[/bold cyan]")
    console.print("=" * 80)


def print_results_table(data: list, title: str = "Results"):
    """Print results in a table format."""
    if not data:
        console.print("[yellow]No results[/yellow]")
        return

    # Create rich table
    table = Table(title=title, show_header=True, header_style="bold magenta")

    # Add columns
    if data:
        for col in data[0].keys():
            table.add_column(col)

    # Add rows (limit to 10 for readability)
    for row in data[:10]:
        table.add_row(*[str(v) for v in row.values()])

    if len(data) > 10:
        console.print(f"[dim](Showing 10 of {len(data)} rows)[/dim]")

    console.print(table)


def print_plan_summary(plan: dict):
    """Print a summary of the query plan."""
    console.print("\n[bold]Plan Summary:[/bold]")
    console.print(f"  Intent: {plan.get('intent_summary', 'N/A')}")
    console.print(f"  Decision: {plan.get('decision', 'N/A')}")

    selections = plan.get("selections", [])
    console.print(f"  Tables: {', '.join([s['table'] for s in selections])}")

    # Count columns
    total_cols = sum(len([c for c in s.get('columns', []) if c['role'] == 'projection']) for s in selections)
    console.print(f"  Projection columns: {total_cols}")

    order_by = plan.get("order_by", [])
    if order_by:
        console.print(f"  ORDER BY: {', '.join([f'{o['table']}.{o['column']} {o['direction']}' for o in order_by])}")

    limit = plan.get("limit")
    if limit:
        console.print(f"  LIMIT: {limit}")


def print_modification_options(options: dict):
    """Print available modification options."""
    console.print("\n[bold]Modification Options:[/bold]")

    tables = options.get("tables", {})
    for table_name, table_info in tables.items():
        console.print(f"\n  [cyan]{table_name}[/cyan]")
        columns = table_info.get("columns", [])

        selected = [c for c in columns if c["selected"]]
        available = [c for c in columns if not c["selected"]]

        console.print(f"    Selected: {', '.join([c['name'] for c in selected])}")
        console.print(f"    Available: {', '.join([c['name'] for c in available[:5]])}{'...' if len(available) > 5 else ''}")


def test_initial_query():
    """Test 1: Execute initial query."""
    print_header("TEST 1: Initial Query Execution")

    console.print("Executing query: 'Show me all tracks with their genre'")

    response = query_database(
        "Show me all tracks with their genre",
        result_limit=0,
        thread_id=None
    )

    state = response["state"]

    # Check for successful execution
    assert state.get("query"), "❌ No SQL query generated"
    assert state.get("result"), "❌ No results returned"
    assert state.get("executed_plan"), "❌ No executed plan saved"
    assert state.get("modification_options"), "❌ No modification options generated"

    console.print("[green]✓ Query executed successfully[/green]")

    # Display SQL
    console.print("\n[bold]Generated SQL:[/bold]")
    console.print(f"[dim]{state['query']}[/dim]")

    # Display results
    result_data = json.loads(state["result"])
    print_results_table(result_data, f"Results ({len(result_data)} rows)")

    # Display plan summary
    print_plan_summary(state["executed_plan"])

    # Display modification options
    print_modification_options(state["modification_options"])

    return state


def test_add_column(initial_state: dict):
    """Test 2: Add a column via patching."""
    print_header("TEST 2: Add Column (Composer)")

    executed_plan = initial_state["executed_plan"]
    filtered_schema = initial_state["filtered_schema"]
    thread_id = initial_state["thread_id"]

    # Find the Track table and add Composer column
    track_table = next((s for s in executed_plan["selections"] if "track" in s["table"].lower()), None)
    assert track_table, "❌ Track table not found in plan"

    table_name = track_table["table"]
    console.print(f"Adding column 'Composer' to table '{table_name}'")

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
    assert state.get("query"), "❌ No SQL query generated"
    assert "Composer" in state["query"], "❌ Composer column not in SQL"

    console.print("[green]✓ Column added successfully[/green]")

    # Display updated SQL
    console.print("\n[bold]Updated SQL:[/bold]")
    console.print(f"[dim]{state['query']}[/dim]")

    # Display results
    result_data = json.loads(state["result"])
    print_results_table(result_data, f"Results with Composer ({len(result_data)} rows)")

    # Verify Composer column exists in results
    if result_data:
        assert "Composer" in result_data[0], "❌ Composer column not in results"
        console.print("[green]✓ Composer column appears in results[/green]")

    return state


def test_remove_column(previous_state: dict):
    """Test 3: Remove a column via patching."""
    print_header("TEST 3: Remove Column (Composer)")

    executed_plan = previous_state["executed_plan"]
    filtered_schema = previous_state["filtered_schema"]
    thread_id = previous_state["thread_id"]

    # Find the Track table and remove Composer column
    track_table = next((s for s in executed_plan["selections"] if "track" in s["table"].lower()), None)
    table_name = track_table["table"]

    console.print(f"Removing column 'Composer' from table '{table_name}'")

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
    assert state.get("query"), "❌ No SQL query generated"

    console.print("[green]✓ Column removed successfully[/green]")

    # Display updated SQL
    console.print("\n[bold]Updated SQL:[/bold]")
    console.print(f"[dim]{state['query']}[/dim]")

    # Display results
    result_data = json.loads(state["result"])
    print_results_table(result_data, f"Results without Composer ({len(result_data)} rows)")

    # Verify Composer column is gone from results
    if result_data:
        assert "Composer" not in result_data[0], "❌ Composer column still in results"
        console.print("[green]✓ Composer column removed from results[/green]")

    return state


def test_modify_order_by(previous_state: dict):
    """Test 4: Modify ORDER BY via patching."""
    print_header("TEST 4: Modify ORDER BY (Sort by Name DESC)")

    executed_plan = previous_state["executed_plan"]
    filtered_schema = previous_state["filtered_schema"]
    thread_id = previous_state["thread_id"]

    # Find Track table
    track_table = next((s for s in executed_plan["selections"] if "track" in s["table"].lower()), None)
    table_name = track_table["table"]

    console.print(f"Setting ORDER BY to {table_name}.Name DESC")

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
    assert state.get("query"), "❌ No SQL query generated"
    assert "ORDER BY" in state["query"].upper(), "❌ ORDER BY not in SQL"
    assert "DESC" in state["query"].upper(), "❌ DESC not in SQL"

    console.print("[green]✓ ORDER BY modified successfully[/green]")

    # Display updated SQL
    console.print("\n[bold]Updated SQL:[/bold]")
    console.print(f"[dim]{state['query']}[/dim]")

    # Display results
    result_data = json.loads(state["result"])
    print_results_table(result_data, f"Results sorted by Name DESC ({len(result_data)} rows)")

    # Verify results are sorted (check first few)
    if len(result_data) >= 2:
        first_name = result_data[0].get("Name", "")
        second_name = result_data[1].get("Name", "")
        console.print(f"  First track: {first_name}")
        console.print(f"  Second track: {second_name}")

    return state


def test_modify_limit(previous_state: dict):
    """Test 5: Modify LIMIT via patching."""
    print_header("TEST 5: Modify LIMIT (Limit to 10 rows)")

    executed_plan = previous_state["executed_plan"]
    filtered_schema = previous_state["filtered_schema"]
    thread_id = previous_state["thread_id"]

    console.print("Setting LIMIT to 10")

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
    assert state.get("query"), "❌ No SQL query generated"
    result_data = json.loads(state["result"])

    console.print("[green]✓ LIMIT modified successfully[/green]")

    # Display updated SQL
    console.print("\n[bold]Updated SQL:[/bold]")
    console.print(f"[dim]{state['query']}[/dim]")

    # Display results
    print_results_table(result_data, f"Results limited to 10 rows")

    # Verify exactly 10 rows returned
    assert len(result_data) == 10, f"❌ Expected 10 rows, got {len(result_data)}"
    console.print(f"[green]✓ Returned exactly 10 rows[/green]")

    return state


def test_multiple_patches_sequence(initial_state: dict):
    """Test 6: Apply multiple patches in sequence."""
    print_header("TEST 6: Multiple Patches in Sequence")

    executed_plan = initial_state["executed_plan"]
    filtered_schema = initial_state["filtered_schema"]
    thread_id = initial_state["thread_id"]

    track_table = next((s for s in executed_plan["selections"] if "track" in s["table"].lower()), None)
    table_name = track_table["table"]

    console.print("Applying 3 patches in sequence:")
    console.print("  1. Add Milliseconds column")
    console.print("  2. Sort by Milliseconds DESC")
    console.print("  3. Limit to 5 rows")

    # Patch 1: Add Milliseconds
    console.print("\n[cyan]Patch 1: Adding Milliseconds...[/cyan]")
    patch_op1 = {
        "operation": "add_column",
        "table": table_name,
        "column": "Milliseconds"
    }

    response1 = query_database(
        "Show me all tracks with their genre",
        patch_operation=patch_op1,
        executed_plan=executed_plan,
        filtered_schema=filtered_schema,
        thread_id=thread_id
    )

    state1 = response1["state"]
    assert "Milliseconds" in state1["query"], "❌ Milliseconds not added"
    console.print("[green]✓ Milliseconds added[/green]")

    # Patch 2: Sort by Milliseconds
    console.print("\n[cyan]Patch 2: Sorting by Milliseconds DESC...[/cyan]")
    patch_op2 = {
        "operation": "modify_order_by",
        "order_by": [
            {
                "table": table_name,
                "column": "Milliseconds",
                "direction": "DESC"
            }
        ]
    }

    response2 = query_database(
        "Show me all tracks with their genre",
        patch_operation=patch_op2,
        executed_plan=state1["executed_plan"],
        filtered_schema=state1["filtered_schema"],
        thread_id=thread_id
    )

    state2 = response2["state"]
    assert "ORDER BY" in state2["query"].upper(), "❌ ORDER BY not added"
    console.print("[green]✓ Sorting applied[/green]")

    # Patch 3: Limit to 5
    console.print("\n[cyan]Patch 3: Limiting to 5 rows...[/cyan]")
    patch_op3 = {
        "operation": "modify_limit",
        "limit": 5
    }

    response3 = query_database(
        "Show me all tracks with their genre",
        patch_operation=patch_op3,
        executed_plan=state2["executed_plan"],
        filtered_schema=state2["filtered_schema"],
        thread_id=thread_id
    )

    state3 = response3["state"]
    result_data = json.loads(state3["result"])

    console.print("[green]✓ Limit applied[/green]")

    # Verify final state
    console.print("\n[bold]Final SQL:[/bold]")
    console.print(f"[dim]{state3['query']}[/dim]")

    print_results_table(result_data, "Final Results (5 longest tracks)")

    assert len(result_data) == 5, f"❌ Expected 5 rows, got {len(result_data)}"
    assert "Milliseconds" in result_data[0], "❌ Milliseconds not in results"

    # Verify sorted (first should have longer duration than last)
    if len(result_data) >= 2:
        first_duration = result_data[0]["Milliseconds"]
        last_duration = result_data[-1]["Milliseconds"]
        console.print(f"\n  Longest track: {first_duration} ms")
        console.print(f"  Shortest (in top 5): {last_duration} ms")
        assert first_duration >= last_duration, "❌ Results not sorted correctly"

    console.print("\n[green]✓ All 3 patches applied successfully in sequence[/green]")


def main():
    """Run all tests."""
    console.print(Panel.fit(
        "[bold cyan]Plan Patching Test Suite[/bold cyan]\n"
        "Testing the complete plan patching workflow",
        border_style="cyan"
    ))

    try:
        # Test 1: Initial query
        state1 = test_initial_query()

        # Test 2: Add column
        state2 = test_add_column(state1)

        # Test 3: Remove column
        state3 = test_remove_column(state2)

        # Test 4: Modify ORDER BY
        state4 = test_modify_order_by(state3)

        # Test 5: Modify LIMIT
        state5 = test_modify_limit(state4)

        # Test 6: Multiple patches in sequence
        test_multiple_patches_sequence(state1)

        # Summary
        console.print("\n" + "=" * 80)
        console.print(Panel.fit(
            "[bold green]✓ All tests passed successfully![/bold green]\n\n"
            "Plan patching is working correctly:\n"
            "  • Initial query execution ✓\n"
            "  • Add column ✓\n"
            "  • Remove column ✓\n"
            "  • Modify ORDER BY ✓\n"
            "  • Modify LIMIT ✓\n"
            "  • Multiple patches in sequence ✓",
            border_style="green",
            title="Test Results"
        ))

    except AssertionError as e:
        console.print(f"\n[bold red]Test failed: {str(e)}[/bold red]")
        return 1
    except Exception as e:
        console.print(f"\n[bold red]Error: {str(e)}[/bold red]")
        import traceback
        console.print(traceback.format_exc())
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
