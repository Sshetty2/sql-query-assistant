"""
Global Benchmark Settings

This module defines global configuration for the benchmark system.
"""

import os
from datetime import datetime

# Benchmark metadata
BENCHMARK_DATE = "2025-10-31"
BENCHMARK_VERSION = "1.0"
BENCHMARK_DESCRIPTION = "LLM Model Comparison for SQL Query Generation"

# Paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BENCHMARK_ROOT = os.path.join(PROJECT_ROOT, "benchmark")
QUERIES_DIR = os.path.join(BENCHMARK_ROOT, "queries")
RESULTS_DIR = os.path.join(BENCHMARK_ROOT, "results")
REPORTS_DIR = os.path.join(RESULTS_DIR, "reports")
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")
DEBUG_DIR = os.path.join(PROJECT_ROOT, "debug")

# Create timestamped results directory
TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
RESULTS_TIMESTAMP_DIR = os.path.join(RESULTS_DIR, TIMESTAMP)

# Query configurations
NUM_QUERIES = 5

# Execution settings
DELAY_BETWEEN_RUNS = 5  # seconds
MAX_RETRIES_PER_RUN = 3

# Quality scoring weights (must sum to 100)
QUALITY_WEIGHTS = {
    "sql_executes": 30,
    "correct_tables": 20,
    "correct_joins": 20,
    "correct_filters": 15,
    "correct_aggregations": 10,
    "similar_results": 5
}

# Token cost estimates (USD per 1M tokens)
# These are approximate costs as of Oct 2024
TOKEN_COSTS = {
    "gpt-5": {"input": 2.50, "output": 10.00},  # Estimated
    "gpt-5-mini": {"input": 0.15, "output": 0.60},  # Estimated
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "llama3.1-8b": {"input": 0.00, "output": 0.00},
    "llama3-8b": {"input": 0.00, "output": 0.00},
    "qwen3-8b": {"input": 0.00, "output": 0.00},
    "qwen3-4b": {"input": 0.00, "output": 0.00}
}

# Debug files to collect per run
DEBUG_FILES_TO_COLLECT = [
    "debug_combined_schema_with_metadata.json",
    "debug_embedded_content.json",
    "debug_vector_search_candidates.json",
    "debug_filter_schema_stage2_llm_llm_interaction.json",
    "debug_llm_table_selection.json",
    "debug_fk_expansion_results.json",
    "debug_schema_markdown.md",
    "debug_planner_prompt.json",
    "debug_generated_planner_output.json",
    "debug_generated_sql.json",
    "debug_generated_sql_queries.json",
    "debug_execute_query_input.json",
    "debug_execute_query_result.json"
]

# Report templates
QUERY_TEMPLATE = {
    "query_id": "",
    "natural_language_query": "",
    "description": "",
    "complexity": "",
    "expected_tables": [],
    "expected_joins": [],
    "ground_truth_sql": "",
    "ground_truth_row_count": None
}

METRICS_TEMPLATE = {
    "model_name": "",
    "query_id": "",
    "timestamp": "",
    "success": False,
    "execution_time_seconds": 0.0,
    "sql_generated": "",
    "sql_correct": False,
    "error_message": None,
    "retry_count": 0,
    "refinement_count": 0,
    "tables_selected": [],
    "columns_selected": [],
    "joins_used": [],
    "filters_applied": [],
    "aggregations_used": [],
    "token_usage": {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0
    },
    "quality_score": 0,
    "result_row_count": None
}
