#!/usr/bin/env python3
"""
Compare inferred foreign keys against ground truth from domain-specific-foreign-keys.json.

This script:
1. Connects to the database (USE_TEST_DB=false for SQL Server)
2. Introspects the schema
3. Simulates a query by filtering to common tables
4. Runs FK inference on filtered tables
5. Compares inferred FKs against ground truth
6. Generates detailed markdown report

Usage:
    python scripts/compare_fk_inference.py [--verbose] [--threshold 0.6] [--output report.md]
"""

import os
import sys
import argparse
import json
from datetime import datetime
from typing import List, Dict, Tuple

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from database.connection import get_pyodbc_connection
from database.introspection import introspect_schema
from database.infer_foreign_keys import infer_foreign_keys
from domain_specific_guidance.combine_json_schema import combine_schema

load_dotenv()


def load_ground_truth() -> Dict[str, List[Dict]]:
    """
    Load ground truth foreign keys from domain-specific-foreign-keys.json.

    Returns:
        Dict mapping table_name to list of FK entries
    """
    fk_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "domain_specific_guidance",
        "domain-specific-foreign-keys.json"
    )

    try:
        with open(fk_path, "r", encoding="utf-8") as f:
            fk_data = json.load(f)

        # Convert to dict for easier lookup
        ground_truth = {}
        for entry in fk_data:
            table_name = entry["table_name"]
            foreign_keys = entry.get("foreign_keys", [])
            ground_truth[table_name] = foreign_keys

        return ground_truth
    except Exception as e:
        print(f"Error loading ground truth: {e}")
        return {}


def simulate_filtered_schema(schema: List[Dict], num_tables: int = 10) -> List[Dict]:
    """
    Simulate schema filtering by selecting a subset of tables.

    For testing purposes, we select tables that are likely to have FKs.

    Args:
        schema: Full database schema
        num_tables: Number of tables to include in filtered set

    Returns:
        Filtered subset of tables
    """
    # Prioritize tables with existing FKs or many ID columns
    def score_table(table):
        score = 0
        # Tables with existing FKs are more interesting
        score += len(table.get("foreign_keys", [])) * 10
        # Tables with ID columns are more interesting
        for col in table.get("columns", []):
            col_name = col["column_name"]
            if "ID" in col_name.upper() or "Id" in col_name:
                score += 1
        return score

    # Sort by score and take top N
    scored_tables = [(table, score_table(table)) for table in schema]
    scored_tables.sort(key=lambda x: x[1], reverse=True)

    filtered = [table for table, score in scored_tables[:num_tables]]

    print(f"\n[Simulated Filtering] Selected {len(filtered)} tables:")
    for table in filtered:
        print(f"  - {table['table_name']}")

    return filtered


def compare_fk_entry(inferred: Dict, ground_truth: Dict) -> bool:
    """
    Compare two FK entries for equivalence.

    Args:
        inferred: Inferred FK entry
        ground_truth: Ground truth FK entry

    Returns:
        True if they match
    """
    return (
        inferred.get("foreign_key") == ground_truth.get("foreign_key") and
        inferred.get("primary_key_table") == ground_truth.get("primary_key_table")
    )


def calculate_metrics(
    inferred_fks: Dict[str, List[Dict]],
    ground_truth_fks: Dict[str, List[Dict]]
) -> Dict:
    """
    Calculate precision, recall, and F1 score.

    Args:
        inferred_fks: Dict mapping table_name to inferred FK list
        ground_truth_fks: Dict mapping table_name to ground truth FK list

    Returns:
        Dict with metrics and detailed results
    """
    results = {
        "correct_inferences": [],      # List of (table, fk) tuples
        "false_positives": [],          # Inferred but wrong
        "false_negatives": [],          # Ground truth but not inferred
        "table_results": {}             # Per-table breakdown
    }

    # Get all tables that appear in either ground truth or inferred
    all_tables = set(inferred_fks.keys()) | set(ground_truth_fks.keys())

    for table_name in all_tables:
        inferred_list = inferred_fks.get(table_name, [])
        ground_truth_list = ground_truth_fks.get(table_name, [])

        # Track per-table results
        table_result = {
            "inferred_count": len(inferred_list),
            "ground_truth_count": len(ground_truth_list),
            "correct": [],
            "false_positive": [],
            "false_negative": []
        }

        # Find correct inferences
        for inferred_fk in inferred_list:
            is_correct = any(
                compare_fk_entry(inferred_fk, gt_fk)
                for gt_fk in ground_truth_list
            )

            if is_correct:
                results["correct_inferences"].append((table_name, inferred_fk))
                table_result["correct"].append(inferred_fk)
            else:
                results["false_positives"].append((table_name, inferred_fk))
                table_result["false_positive"].append(inferred_fk)

        # Find missed inferences (false negatives)
        for gt_fk in ground_truth_list:
            is_inferred = any(
                compare_fk_entry(inferred_fk, gt_fk)
                for inferred_fk in inferred_list
            )

            if not is_inferred:
                results["false_negatives"].append((table_name, gt_fk))
                table_result["false_negative"].append(gt_fk)

        results["table_results"][table_name] = table_result

    # Calculate overall metrics
    total_correct = len(results["correct_inferences"])
    total_inferred = total_correct + len(results["false_positives"])
    total_ground_truth = total_correct + len(results["false_negatives"])

    precision = (total_correct / total_inferred * 100) if total_inferred > 0 else 0
    recall = (total_correct / total_ground_truth * 100) if total_ground_truth > 0 else 0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0

    results["metrics"] = {
        "total_correct": total_correct,
        "total_inferred": total_inferred,
        "total_ground_truth": total_ground_truth,
        "precision": precision,
        "recall": recall,
        "f1_score": f1
    }

    return results


def generate_markdown_report(
    results: Dict,
    config: Dict,
    filtered_tables: List[str]
) -> str:
    """
    Generate detailed markdown report.

    Args:
        results: Results from calculate_metrics()
        config: Configuration dict
        filtered_tables: List of filtered table names

    Returns:
        Markdown report as string
    """
    metrics = results["metrics"]
    report = []

    # Header
    report.append("# Foreign Key Inference Comparison Report\n")
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Configuration
    report.append("## Test Configuration\n")
    report.append(f"- **Database**: {config.get('database', 'Unknown')}")
    report.append(f"- **Filtered tables**: {len(filtered_tables)}")
    report.append(f"- **Confidence threshold**: {config['confidence_threshold']}")
    report.append(f"- **Top-k candidates**: {config['top_k']}\n")

    # Overall metrics
    report.append("## Overall Metrics\n")
    report.append(f"- **Precision**: {metrics['precision']:.1f}% "
                  f"({metrics['total_correct']}/{metrics['total_inferred']} inferred correctly)")
    report.append(f"- **Recall**: {metrics['recall']:.1f}% "
                  f"({metrics['total_correct']}/{metrics['total_ground_truth']} ground truth found)")
    report.append(f"- **F1 Score**: {metrics['f1_score']:.1f}%\n")

    # Per-table results
    report.append("## Detailed Results by Table\n")

    for table_name in sorted(results["table_results"].keys()):
        table_result = results["table_results"][table_name]

        if table_result["inferred_count"] == 0 and table_result["ground_truth_count"] == 0:
            continue  # Skip tables with no FKs

        report.append(f"### {table_name}\n")
        report.append(f"- Ground truth FKs: {table_result['ground_truth_count']}")
        report.append(f"- Inferred FKs: {table_result['inferred_count']}")
        report.append(f"- Correct: {len(table_result['correct'])}")
        report.append(f"- False positives: {len(table_result['false_positive'])}")
        report.append(f"- False negatives: {len(table_result['false_negative'])}\n")

        # Show correct inferences
        if table_result["correct"]:
            report.append("**Correct Inferences:**")
            for fk in table_result["correct"]:
                conf = fk.get("confidence", 0)
                pk_col = fk.get("primary_key_column")
                pk_suffix = f".{pk_col}" if pk_col else ""
                report.append(
                    f"- ✓ {fk['foreign_key']} → {fk['primary_key_table']}{pk_suffix} "
                    f"(conf: {conf:.3f})"
                )
            report.append("")

        # Show false positives
        if table_result["false_positive"]:
            report.append("**False Positives (Incorrect Inferences):**")
            for fk in table_result["false_positive"]:
                conf = fk.get("confidence", 0)
                report.append(
                    f"- ⚠ {fk['foreign_key']} → {fk['primary_key_table']} "
                    f"(conf: {conf:.3f})"
                )
            report.append("")

        # Show false negatives
        if table_result["false_negative"]:
            report.append("**False Negatives (Missed FKs):**")
            for fk in table_result["false_negative"]:
                report.append(
                    f"- ✗ {fk['foreign_key']} → {fk['primary_key_table']} "
                    "(not inferred)"
                )
            report.append("")

    # Summary section
    report.append("## Summary\n")

    if metrics["precision"] >= 80 and metrics["recall"] >= 70:
        report.append("✅ **Excellent performance!** FK inference is working well.\n")
    elif metrics["precision"] >= 70 or metrics["recall"] >= 60:
        report.append("⚠️ **Good performance** with room for improvement.\n")
    else:
        report.append("❌ **Needs improvement.** Consider tuning parameters.\n")

    # Recommendations
    report.append("## Recommendations\n")

    if metrics["precision"] < 80:
        report.append("- Consider **increasing confidence threshold** to reduce false positives")

    if metrics["recall"] < 70:
        report.append("- Consider **decreasing confidence threshold** to find more FKs")
        report.append("- Add special handling for abbreviated IDs (APPID, CDAID)")

    if len(results["false_negatives"]) > 5:
        report.append("- Review missed FKs for common patterns")

    if not report[-1].startswith("-"):
        report.append("- Monitor performance on different query types")

    return "\n".join(report)


def run_comparison(args):
    """Main comparison workflow."""
    print("=" * 70)
    print("FK INFERENCE COMPARISON TEST")
    print("=" * 70)

    # Configuration
    config = {
        "database": os.getenv("DB_NAME", "Unknown"),
        "confidence_threshold": args.threshold,
        "top_k": args.top_k
    }

    print(f"\nConfiguration:")
    print(f"  Confidence threshold: {config['confidence_threshold']}")
    print(f"  Top-k candidates: {config['top_k']}")
    print(f"  Verbose: {args.verbose}")

    # Step 1: Load ground truth
    print("\n[Step 1] Loading ground truth FKs...")
    ground_truth = load_ground_truth()
    total_gt_fks = sum(len(fks) for fks in ground_truth.values())
    print(f"  Loaded ground truth: {len(ground_truth)} tables, {total_gt_fks} FKs")

    # Step 2: Connect to database
    print("\n[Step 2] Connecting to database...")
    try:
        connection = get_pyodbc_connection()
        print("  [PASS] Connected")
    except Exception as e:
        print(f"  [FAIL] Connection failed: {e}")
        return

    # Step 3: Introspect schema
    print("\n[Step 3] Introspecting schema...")
    try:
        schema = introspect_schema(connection)
        print(f"  [PASS] Introspected {len(schema)} tables")

        # NOTE: We intentionally do NOT combine with domain metadata for FK inference testing.
        # Testing showed that table descriptions dilute the table name signal and reduce accuracy.
        # FK inference works best with just table names.
    except Exception as e:
        print(f"  [FAIL] Introspection failed: {e}")
        return
    finally:
        connection.close()

    # Step 4: Simulate filtering
    print("\n[Step 4] Simulating schema filtering...")
    filtered_schema = simulate_filtered_schema(schema, num_tables=args.num_tables)

    # Step 5: Run FK inference
    print("\n[Step 5] Running FK inference...")
    try:
        inferred_schema = infer_foreign_keys(
            filtered_schema=filtered_schema,
            confidence_threshold=config["confidence_threshold"],
            top_k=config["top_k"]
        )
        print("  [PASS] FK inference completed")

        # Extract inferred FKs
        inferred_fks = {}
        for table in inferred_schema:
            table_name = table["table_name"]
            # Only include inferred FKs (not existing ones)
            inferred_list = [
                fk for fk in table.get("foreign_keys", [])
                if fk.get("inferred")
            ]
            if inferred_list:
                inferred_fks[table_name] = inferred_list

        total_inferred = sum(len(fks) for fks in inferred_fks.values())
        print(f"  Inferred {total_inferred} FKs across {len(inferred_fks)} tables")

    except Exception as e:
        print(f"  [FAIL] FK inference failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 6: Compare against ground truth
    print("\n[Step 6] Comparing against ground truth...")

    # Filter ground truth to only tables in filtered schema
    filtered_table_names = {t["table_name"] for t in filtered_schema}
    filtered_ground_truth = {
        table: fks for table, fks in ground_truth.items()
        if table in filtered_table_names
    }

    results = calculate_metrics(inferred_fks, filtered_ground_truth)
    metrics = results["metrics"]

    print(f"  [PASS] Comparison completed")
    print(f"\n  Precision: {metrics['precision']:.1f}%")
    print(f"  Recall: {metrics['recall']:.1f}%")
    print(f"  F1 Score: {metrics['f1_score']:.1f}%")

    # Step 7: Generate report
    print("\n[Step 7] Generating report...")
    filtered_table_names_list = [t["table_name"] for t in filtered_schema]
    report = generate_markdown_report(results, config, filtered_table_names_list)

    # Save report
    output_path = args.output
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"  [PASS] Report saved to: {output_path}")

    # Print summary
    print("\n" + "=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)
    print(f"Precision: {metrics['precision']:.1f}%")
    print(f"Recall: {metrics['recall']:.1f}%")
    print(f"F1 Score: {metrics['f1_score']:.1f}%")
    print(f"\nDetailed report: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Compare inferred FKs against ground truth"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.6,
        help="Confidence threshold (0.0-1.0, default: 0.6)"
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Number of candidate tables to consider (default: 3)"
    )
    parser.add_argument(
        "--num-tables",
        type=int,
        default=10,
        help="Number of tables to include in filtered set (default: 10)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="fk_inference_comparison_report.md",
        help="Output file path (default: fk_inference_comparison_report.md)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )

    args = parser.parse_args()

    try:
        run_comparison(args)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
