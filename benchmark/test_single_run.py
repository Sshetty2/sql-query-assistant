"""
Test Single Benchmark Run

Tests the benchmark infrastructure with just one model and one query.
"""

from benchmark.run_benchmark import BenchmarkRunner
from benchmark.config.model_configs import MODELS
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_single_run(model_name=None, query_index=None):
    """Test with a single model and single query."""

    print("\n" + "=" * 80)
    print("TESTING BENCHMARK INFRASTRUCTURE")
    print("=" * 80 + "\n")

    # Choose a model to test
    if model_name is None:
        print("Available models:")
        for i, (name, config) in enumerate(MODELS.items(), 1):
            print(f"{i}. {name} ({config['category']}) - {config['description']}")

        choice = input(f"\nSelect model to test (1-{len(MODELS)}): ").strip()

        try:
            model_index = int(choice) - 1
            model_name = list(MODELS.keys())[model_index]
        except (ValueError, IndexError):
            print("Invalid choice. Using gpt-4o-mini as default.")
            model_name = "gpt-4o-mini"

    if model_name not in MODELS:
        print(f"Unknown model: {model_name}. Using gpt-4o-mini as default.")
        model_name = "gpt-4o-mini"

    print(f"\nSelected: {model_name}\n")

    # Initialize runner
    runner = BenchmarkRunner()

    # Show available queries
    if query_index is None:
        print("Available queries:")
        for i, query in enumerate(runner.queries, 1):
            print(
                f"{i}. {query['query_id']} - {query['natural_language_query'][:80]}..."
            )

        query_choice = input(
            f"\nSelect query to test (1-{len(runner.queries)}): "
        ).strip()

        try:
            query_index = int(query_choice) - 1
        except (ValueError, IndexError):
            print("Invalid choice. Using first query as default.")
            query_index = 0

    try:
        query_data = runner.queries[query_index]
    except IndexError:
        print("Invalid query index. Using first query as default.")
        query_data = runner.queries[0]

    print(f"\nSelected: {query_data['query_id']}\n")

    # Backup .env
    print("Backing up .env...")
    runner.env_manager.backup_env()

    try:
        # Update config for selected model
        from benchmark.config.model_configs import get_model_config

        model_config = get_model_config(model_name)

        print(f"Switching to {model_name} configuration...")
        runner.env_manager.update_env(model_config)

        # Run single benchmark
        print("\nRunning benchmark...")
        metrics = runner.run_single_benchmark(model_name, query_data)

        # Print summary
        print(f"\n{'='*80}")
        print("TEST RESULTS")
        print(f"{'='*80}")
        print(f"Model: {metrics['model_name']}")
        print(f"Query: {metrics['query_id']}")
        print(f"Success: {metrics['success']}")
        print(f"Execution Time: {metrics['execution_time_seconds']}s")
        print(f"Quality Score: {metrics.get('quality_score', 'N/A')}/100")
        print(f"Tokens Used: {metrics['token_usage']['total_tokens']}")
        print(f"Estimated Cost: ${metrics.get('estimated_cost_usd', 0):.6f}")

        if not metrics["success"]:
            print(f"\nError: {metrics.get('error_message', 'Unknown error')}")

        print(
            f"\nResults saved to: {runner.results_dir}/{model_name}/{query_data['query_id']}/"
        )
        print(f"{'='*80}\n")

        # Ask if user wants to proceed with full benchmark (only in interactive mode)
        if sys.stdin.isatty():
            proceed = (
                input("\nTest successful! Run full benchmark for all models? (y/n): ")
                .strip()
                .lower()
            )

            if proceed == "y":
                print("\nStarting full benchmark...")
                runner.run_all_benchmarks()
            else:
                print("\nTest complete. You can run the full benchmark later with:")
                print("  python -m benchmark.run_benchmark")
        else:
            print("\nTest complete. You can run the full benchmark with:")
            print("  python -m benchmark.run_benchmark")

    finally:
        # Restore .env
        print("\nRestoring original .env...")
        runner.env_manager.restore_env()
        print(" Done!\n")


if __name__ == "__main__":
    import sys

    # Parse command-line arguments
    model_name = None
    query_idx = None

    if len(sys.argv) > 1:
        model_name = sys.argv[1]
    if len(sys.argv) > 2:
        try:
            query_idx = int(sys.argv[2]) - 1  # Convert to 0-indexed
        except ValueError:
            query_idx = 0

    # Default to gpt-4o-mini and query 1 if no args provided and non-interactive
    if model_name is None and not sys.stdin.isatty():
        print("Non-interactive mode detected. Using defaults: gpt-4o-mini, query 1")
        model_name = "gpt-4o-mini"
        query_idx = 0

    test_single_run(model_name, query_idx)
