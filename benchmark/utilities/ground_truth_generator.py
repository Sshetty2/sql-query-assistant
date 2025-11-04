"""
Ground Truth Generator

This utility helps generate ground truth SQL queries for benchmark test cases.
It runs the workflow once to get the filtered schema, then allows Claude to
craft optimal SQL based on that schema.
"""

from agent.query_database import query_database
from database.connection import get_pyodbc_connection
from benchmark.config.benchmark_settings import DEBUG_DIR, QUERIES_DIR

import os
import sys
import json
from typing import Dict, Any
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class GroundTruthGenerator:
    """Generates ground truth SQL queries for benchmark test cases."""

    def __init__(self):
        self.debug_dir = DEBUG_DIR

    def run_workflow_for_schema(self, query: str) -> Dict[str, Any]:
        """
        Run the workflow once to generate filtered schema markdown.

        Args:
            query: Natural language query

        Returns:
            Dictionary containing schema markdown and other debug info
        """
        print(f"\n{'='*80}")
        print("Running workflow to generate filtered schema...")
        print(f"Query: {query}")
        print(f"{'='*80}\n")

        # Run the workflow
        try:
            result = query_database(query)

            # Load the generated schema markdown
            schema_file = os.path.join(self.debug_dir, "debug_schema_markdown.md")
            schema_markdown = ""
            if os.path.exists(schema_file):
                with open(schema_file, "r", encoding="utf-8") as f:
                    schema_markdown = f.read()

            # Load the planner output
            planner_file = os.path.join(
                self.debug_dir, "debug_generated_planner_output.json"
            )
            planner_output = None
            if os.path.exists(planner_file):
                with open(planner_file, "r", encoding="utf-8") as f:
                    planner_output = json.load(f)

            # Load the generated SQL
            sql_file = os.path.join(self.debug_dir, "debug_generated_sql.json")
            generated_sql = ""
            if os.path.exists(sql_file):
                with open(sql_file, "r", encoding="utf-8") as f:
                    sql_data = json.load(f)
                    generated_sql = sql_data.get("query", "")

            return {
                "success": True,
                "schema_markdown": schema_markdown,
                "planner_output": planner_output,
                "generated_sql": generated_sql,
                "result": result,
            }

        except Exception as e:
            print(f"X Error running workflow: {e}")
            return {"success": False, "error": str(e)}

    def save_query_template(
        self,
        query_id: str,
        natural_language_query: str,
        description: str,
        complexity: str,
        schema_markdown: str,
        ground_truth_sql: str = "",
        expected_tables: list = None,
        expected_joins: list = None,
    ):
        """
        Save a query template to the queries directory.

        Args:
            query_id: Unique identifier for the query (e.g., "query_1")
            natural_language_query: The natural language query
            description: Description of what the query tests
            complexity: Complexity level (e.g., "semi-complex")
            schema_markdown: Filtered schema markdown
            ground_truth_sql: The optimal SQL query (ground truth)
            expected_tables: List of expected table names
            expected_joins: List of expected join relationships
        """
        query_dir = os.path.join(QUERIES_DIR, query_id)
        os.makedirs(query_dir, exist_ok=True)

        # Save query.json
        query_data = {
            "query_id": query_id,
            "natural_language_query": natural_language_query,
            "description": description,
            "complexity": complexity,
            "expected_tables": expected_tables or [],
            "expected_joins": expected_joins or [],
        }

        with open(os.path.join(query_dir, "query.json"), "w", encoding="utf-8") as f:
            json.dump(query_data, f, indent=2, ensure_ascii=False)

        # Save schema markdown
        with open(
            os.path.join(query_dir, "expected_schema.md"), "w", encoding="utf-8"
        ) as f:
            f.write(schema_markdown)

        # Save ground truth SQL (if provided)
        if ground_truth_sql:
            with open(
                os.path.join(query_dir, "ground_truth.sql"), "w", encoding="utf-8"
            ) as f:
                f.write(ground_truth_sql)

        print(f" Saved query template to {query_dir}")

    def test_ground_truth_sql(self, sql: str) -> Dict[str, Any]:
        """
        Test a ground truth SQL query against the database.

        Args:
            sql: SQL query to test

        Returns:
            Dictionary containing execution results
        """
        print(f"\n{'='*80}")
        print("Testing ground truth SQL...")
        print(f"{'='*80}")
        print(sql)
        print(f"{'='*80}\n")

        try:
            conn = get_pyodbc_connection()
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()

            # Get column names
            columns = (
                [column[0] for column in cursor.description]
                if cursor.description
                else []
            )

            cursor.close()
            conn.close()

            print("SQL executed successfully!")
            print(f" Returned {len(rows)} rows")
            print(f" Columns: {', '.join(columns)}")

            return {
                "success": True,
                "row_count": len(rows),
                "columns": columns,
                "sample_rows": [
                    dict(zip(columns, row)) for row in rows[:5]
                ],  # First 5 rows
            }

        except Exception as e:
            print(f"X Error executing SQL: {e}")
            return {"success": False, "error": str(e)}


def interactive_ground_truth_generation():
    """
    Interactive CLI for generating ground truth queries.
    """
    generator = GroundTruthGenerator()

    print("\n" + "=" * 80)
    print("Ground Truth SQL Generator")
    print("=" * 80 + "\n")

    print("This tool helps generate ground truth SQL for benchmark queries.")
    print("It will:\n")
    print("1. Run the workflow to get filtered schema")
    print("2. Display the schema and workflow-generated SQL")
    print("3. Allow you to provide optimal SQL as ground truth")
    print("4. Test the SQL and save to query directory\n")

    # Get query details
    query_id = input("Query ID (e.g., query_1_complex_user_activity): ").strip()
    natural_language_query = input("Natural language query: ").strip()
    description = input("Description: ").strip()
    complexity = input("Complexity (semi-complex): ").strip() or "semi-complex"

    # Run workflow to get schema
    print("\nRunning workflow to generate filtered schema...")
    result = generator.run_workflow_for_schema(natural_language_query)

    if not result["success"]:
        print(f"X Failed to generate schema: {result.get('error')}")
        return

    print("\n Schema generated successfully!")
    print("\nFiltered Schema Markdown:")
    print("=" * 80)
    print(
        result["schema_markdown"][:500] + "..."
        if len(result["schema_markdown"]) > 500
        else result["schema_markdown"]
    )
    print("=" * 80)

    print("\nWorkflow-Generated SQL:")
    print("=" * 80)
    print(result["generated_sql"])
    print("=" * 80)

    print("\nNow, please provide the optimal SQL (ground truth).")
    print("Press Enter twice when done:\n")

    sql_lines = []
    while True:
        line = input()
        if line == "" and sql_lines and sql_lines[-1] == "":
            break
        sql_lines.append(line)

    ground_truth_sql = "\n".join(sql_lines).strip()

    if not ground_truth_sql:
        print("X No SQL provided. Skipping SQL testing.")
        ground_truth_sql = "-- TODO: Add ground truth SQL"
    else:
        # Test the SQL
        test_result = generator.test_ground_truth_sql(ground_truth_sql)

        if not test_result["success"]:
            print("X SQL failed to execute. Save anyway? (y/n): ", end="")
            if input().lower() != "y":
                return

    # Save the query template
    generator.save_query_template(
        query_id=query_id,
        natural_language_query=natural_language_query,
        description=description,
        complexity=complexity,
        schema_markdown=result["schema_markdown"],
        ground_truth_sql=ground_truth_sql,
    )

    print("\n Ground truth query saved successfully!")


if __name__ == "__main__":
    # Check if we're in interactive mode or providing SQL via argument
    if len(sys.argv) > 1 and sys.argv[1] == "interactive":
        interactive_ground_truth_generation()
    else:
        print("\nGround Truth Generator")
        print("=" * 80)
        print("\nUsage:")
        print("  python -m benchmark.utilities.ground_truth_generator interactive")
        print(
            "\nThis will start an interactive session to generate ground truth queries."
        )
        print()
