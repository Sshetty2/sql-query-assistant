"""
Validate Ground Truth SQL

Tests all ground truth SQL queries against the actual database
to ensure they execute successfully before running benchmarks.
"""

import os
import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.connection import get_pyodbc_connection
from benchmark.config.benchmark_settings import QUERIES_DIR


def validate_ground_truth_sql():
    """Validate all ground truth SQL queries."""

    print("\n" + "="*80)
    print("VALIDATING GROUND TRUTH SQL QUERIES")
    print("="*80 + "\n")

    # Load all queries
    query_dirs = [d for d in os.listdir(QUERIES_DIR) if os.path.isdir(os.path.join(QUERIES_DIR, d))]
    query_dirs.sort()

    results = []

    for query_dir in query_dirs:
        query_json_path = os.path.join(QUERIES_DIR, query_dir, "query.json")
        ground_truth_path = os.path.join(QUERIES_DIR, query_dir, "ground_truth.sql")

        if not os.path.exists(query_json_path) or not os.path.exists(ground_truth_path):
            print(f"WARNING: Skipping {query_dir} - missing files")
            continue

        # Load query metadata
        with open(query_json_path, 'r', encoding='utf-8') as f:
            query_data = json.load(f)

        # Load ground truth SQL
        with open(ground_truth_path, 'r', encoding='utf-8') as f:
            ground_truth_sql = f.read()

        query_id = query_data['query_id']
        print(f"\n{'='*80}")
        print(f"Testing: {query_id}")
        print(f"Query: {query_data['natural_language_query']}")
        print(f"{'='*80}")
        print(f"\nSQL:\n{ground_truth_sql}\n")

        # Test the SQL
        try:
            conn = get_pyodbc_connection()
            cursor = conn.cursor()

            # Execute query
            cursor.execute(ground_truth_sql)
            rows = cursor.fetchall()

            # Get column names
            columns = [column[0] for column in cursor.description] if cursor.description else []

            cursor.close()
            conn.close()

            row_count = len(rows)

            print(f"SUCCESS")
            print(f"  Rows returned: {row_count}")
            print(f"  Columns: {', '.join(columns)}")

            # Show sample rows (first 3)
            if rows and len(rows) > 0:
                print(f"\n  Sample rows (first 3):")
                for i, row in enumerate(rows[:3], 1):
                    print(f"    {i}. {dict(zip(columns, row))}")

            results.append({
                "query_id": query_id,
                "success": True,
                "row_count": row_count,
                "columns": columns
            })

        except Exception as e:
            print(f"FAILED")
            print(f"  Error: {str(e)}")

            results.append({
                "query_id": query_id,
                "success": False,
                "error": str(e)
            })

    # Summary
    print(f"\n{'='*80}")
    print("VALIDATION SUMMARY")
    print(f"{'='*80}")

    total = len(results)
    passed = len([r for r in results if r['success']])
    failed = total - passed

    print(f"\nTotal Queries: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed == 0:
        print(f"\nAll ground truth SQL queries are valid!")
        print(f"You can proceed with the benchmark run.")
    else:
        print(f"\nWARNING: Some queries failed. Please fix the ground truth SQL before running benchmarks.")
        print(f"\nFailed queries:")
        for r in results:
            if not r['success']:
                print(f"  - {r['query_id']}: {r.get('error', 'Unknown error')}")

    print(f"{'='*80}\n")

    return results


if __name__ == "__main__":
    validate_ground_truth_sql()
