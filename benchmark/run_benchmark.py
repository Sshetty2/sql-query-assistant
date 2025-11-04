"""
Main Benchmark Runner

This script orchestrates the entire benchmarking process:
1. Backs up current .env configuration
2. Iterates through all model configurations
3. Runs each query for each model
4. Collects metrics and debug files
5. Generates comparison reports
"""

from agent.query_database import query_database
from benchmark.config.model_configs import MODELS, EXECUTION_ORDER, get_model_config
from benchmark.config.benchmark_settings import (
    QUERIES_DIR,
    RESULTS_TIMESTAMP_DIR,
    DELAY_BETWEEN_RUNS,
    MAX_RETRIES_PER_RUN,
    BENCHMARK_DATE,
)
from benchmark.utilities.env_manager import EnvManager
from benchmark.utilities.metrics_collector import MetricsCollector, copy_debug_files
from benchmark.utilities.sql_comparator import SQLComparator
from database.connection import get_pyodbc_connection

import os
import sys
import json
import time
import traceback
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class BenchmarkRunner:
    """Orchestrates the benchmarking process."""

    def __init__(self):
        self.env_manager = EnvManager()
        self.results_dir = RESULTS_TIMESTAMP_DIR
        self.queries = self._load_queries()
        self.benchmark_summary = {
            "benchmark_date": BENCHMARK_DATE,
            "run_timestamp": datetime.now().isoformat(),
            "models_tested": len(EXECUTION_ORDER),
            "queries_tested": len(self.queries),
            "total_runs": len(EXECUTION_ORDER) * len(self.queries),
            "results": [],
        }

    def _load_queries(self):
        """Load all query configurations."""
        queries = []
        query_dirs = [
            d
            for d in os.listdir(QUERIES_DIR)
            if os.path.isdir(os.path.join(QUERIES_DIR, d))
        ]

        for query_dir in sorted(query_dirs):
            query_json_path = os.path.join(QUERIES_DIR, query_dir, "query.json")
            ground_truth_path = os.path.join(QUERIES_DIR, query_dir, "ground_truth.sql")

            if os.path.exists(query_json_path):
                with open(query_json_path, "r", encoding="utf-8") as f:
                    query_data = json.load(f)

                # Load ground truth SQL
                ground_truth_sql = ""
                if os.path.exists(ground_truth_path):
                    with open(ground_truth_path, "r", encoding="utf-8") as f:
                        ground_truth_sql = f.read()

                query_data["ground_truth_sql"] = ground_truth_sql
                query_data["query_dir"] = query_dir
                queries.append(query_data)

        print(f"Loaded {len(queries)} queries")
        return queries

    def _create_result_directory(self, model_name, query_id):
        """Create directory for storing results."""
        result_dir = os.path.join(self.results_dir, model_name, query_id)
        os.makedirs(result_dir, exist_ok=True)
        return result_dir

    def _execute_query_with_retry(self, query, max_retries=MAX_RETRIES_PER_RUN):
        """Execute query with retry logic."""
        import inspect

        for attempt in range(max_retries):
            try:
                result = query_database(query, stream_updates=False)

                # Handle generator function return value
                # Python makes query_database a generator because it has yield statements,
                # even though we're using return for non-streaming mode
                if inspect.isgenerator(result):
                    try:
                        # Try to get next item (will trigger StopIteration immediately)
                        next(result)
                    except StopIteration as e:
                        # The return value is in the exception's value attribute
                        result = e.value

                # Extract the state from the result
                if isinstance(result, dict) and "state" in result:
                    return result["state"], None
                else:
                    return result, None
            except Exception as e:
                error_msg = f"Attempt {attempt + 1}/{max_retries} failed: {str(e)}"
                print(f"  WARNING: {error_msg}")

                if attempt == max_retries - 1:
                    return None, str(e)

                time.sleep(2**attempt)  # Exponential backoff

        return None, "Max retries exceeded"

    def _test_ground_truth_sql(self, sql):
        """Test ground truth SQL and get row count."""
        try:
            conn = get_pyodbc_connection()
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            row_count = len(rows)
            cursor.close()
            conn.close()
            return row_count, None
        except Exception as e:
            return None, str(e)

    def run_single_benchmark(self, model_name, query_data):
        """Run a single benchmark (one model, one query)."""
        query_id = query_data["query_id"]
        natural_language_query = query_data["natural_language_query"]
        ground_truth_sql = query_data["ground_truth_sql"]

        print(f"\n{'='*80}")
        print(f"Model: {model_name}")
        print(f"Query: {query_id}")
        print(f"NL Query: {natural_language_query}")
        print(f"{'='*80}")

        # Create result directory
        result_dir = self._create_result_directory(model_name, query_id)

        # Initialize metrics collector
        metrics = MetricsCollector(model_name, query_id)
        metrics.start_timer()

        # Execute query
        print("  -> Executing workflow...")
        result, error = self._execute_query_with_retry(natural_language_query)

        metrics.stop_timer()

        # Collect metrics from state
        if result:
            metrics.collect_from_state(result)
        else:
            metrics.metrics["success"] = False
            metrics.metrics["error_message"] = error

        # Collect metrics from debug files
        metrics.collect_from_debug_files()

        # Copy debug files
        print("  -> Copying debug files...")
        copy_debug_files(result_dir)

        # Save metrics
        metrics_file = os.path.join(result_dir, "metrics.json")
        metrics.save_metrics(metrics_file)

        # Compare SQL if successful
        quality_score = 0
        if metrics.metrics["success"] and ground_truth_sql:
            print("  -> Comparing SQL with ground truth...")
            generated_sql = metrics.metrics.get("sql_generated", "")

            if generated_sql:
                # Get ground truth row count
                gt_row_count, gt_error = self._test_ground_truth_sql(ground_truth_sql)

                comparator = SQLComparator(ground_truth_sql, generated_sql)
                comparison_results = comparator.compare_structures()

                quality_score = comparator.calculate_quality_score(
                    sql_executes=True,
                    result_row_count=metrics.metrics.get("result_row_count"),
                    ground_truth_row_count=gt_row_count,
                )

                metrics.metrics["quality_score"] = quality_score
                metrics.metrics["ground_truth_row_count"] = gt_row_count

                # Save comparison results
                comparison_file = os.path.join(result_dir, "sql_comparison.json")
                with open(comparison_file, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "ground_truth_sql": ground_truth_sql,
                            "generated_sql": generated_sql,
                            "comparison_results": comparison_results,
                            "quality_score": quality_score,
                            "differences_summary": comparator.get_differences_summary(),
                        },
                        f,
                        indent=2,
                        ensure_ascii=False,
                    )

                # Re-save metrics with quality score
                metrics.save_metrics(metrics_file)

                print(f"   Quality Score: {quality_score}/100")

        # Print summary
        print(f"   Execution Time: {metrics.metrics['execution_time_seconds']}s")
        print(f"   Success: {metrics.metrics['success']}")
        if metrics.metrics.get("estimated_cost_usd"):
            print(f"   Estimated Cost: ${metrics.metrics['estimated_cost_usd']:.6f}")

        return metrics.get_metrics()

    def run_all_benchmarks(self):
        """Run all benchmarks for all models and all queries."""
        # Create results directory
        os.makedirs(self.results_dir, exist_ok=True)

        # Backup current .env
        print(f"\n{'='*80}")
        print(f"LLM BENCHMARK - {BENCHMARK_DATE}")
        print(f"{'='*80}\n")

        print("Backing up current .env configuration...")
        self.env_manager.backup_env()

        total_runs = len(EXECUTION_ORDER) * len(self.queries)
        completed_runs = 0
        failed_runs = 0

        try:
            # Iterate through models
            for model_name in EXECUTION_ORDER:
                model_config = get_model_config(model_name)

                print(f"\n{'#'*80}")
                print(f"# MODEL: {model_name}")
                print(f"# Category: {MODELS[model_name]['category']}")
                print(f"# Description: {MODELS[model_name]['description']}")
                print(f"{'#'*80}\n")

                # Update .env for this model
                print(f"Switching to {model_name} configuration...")
                self.env_manager.update_env(model_config)

                # Iterate through queries
                for query_data in self.queries:
                    try:
                        # Run benchmark
                        metrics = self.run_single_benchmark(model_name, query_data)
                        self.benchmark_summary["results"].append(metrics)

                        completed_runs += 1

                        # Delay between runs
                        if completed_runs < total_runs:
                            print(
                                f"\n  Waiting Waiting {DELAY_BETWEEN_RUNS}s before next run..."
                            )
                            time.sleep(DELAY_BETWEEN_RUNS)

                    except Exception as e:
                        failed_runs += 1
                        print(f"\n  X FAILED: {str(e)}")
                        print(traceback.format_exc())

                        # Log failure
                        self.benchmark_summary["results"].append(
                            {
                                "model_name": model_name,
                                "query_id": query_data["query_id"],
                                "success": False,
                                "error_message": str(e),
                            }
                        )

        finally:
            # Restore original .env
            print(f"\n{'='*80}")
            print("Restoring original .env configuration...")
            self.env_manager.restore_env()

        # Save benchmark summary
        summary_file = os.path.join(self.results_dir, "benchmark_summary.json")
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(self.benchmark_summary, f, indent=2, ensure_ascii=False)

        # Print final summary
        print(f"\n{'='*80}")
        print("BENCHMARK COMPLETE")
        print(f"{'='*80}")
        print(f"Total Runs: {total_runs}")
        print(f"Completed: {completed_runs}")
        print(f"Failed: {failed_runs}")
        print(f"Success Rate: {(completed_runs / total_runs * 100):.1f}%")
        print(f"\nResults saved to: {self.results_dir}")
        print(f"{'='*80}\n")

        return self.benchmark_summary


def main():
    """Main entry point."""
    print("\n" + "=" * 80)
    print("SQL Query Assistant - LLM Benchmark Runner")
    print("=" * 80 + "\n")

    runner = BenchmarkRunner()
    runner.run_all_benchmarks()

    print("\n Benchmark complete!")
    print(f" Results directory: {runner.results_dir}")


if __name__ == "__main__":
    main()
