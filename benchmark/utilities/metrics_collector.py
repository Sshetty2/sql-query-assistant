"""
Metrics Collector

This module extracts and collects metrics from workflow execution,
debug files, and state objects.
"""

import json
import os
import time
from typing import Dict, Any
from datetime import datetime
from benchmark.config.benchmark_settings import (
    DEBUG_DIR,
    DEBUG_FILES_TO_COLLECT,
    METRICS_TEMPLATE,
    TOKEN_COSTS,
)


class MetricsCollector:
    """Collects and processes metrics from query execution."""

    def __init__(self, model_name: str, query_id: str):
        self.model_name = model_name
        self.query_id = query_id
        self.metrics = {**METRICS_TEMPLATE}
        self.metrics["model_name"] = model_name
        self.metrics["query_id"] = query_id
        self.metrics["timestamp"] = datetime.now().isoformat()
        self.start_time = None
        self.end_time = None

    def start_timer(self):
        """Start execution timer."""
        self.start_time = time.time()

    def stop_timer(self):
        """Stop execution timer and record duration."""
        if self.start_time:
            self.end_time = time.time()
            self.metrics["execution_time_seconds"] = round(
                self.end_time - self.start_time, 2
            )

    def collect_from_state(self, state: Dict[str, Any]):
        """
        Extract metrics from the workflow state object.

        Args:
            state: The final workflow state
        """
        # Extract basic execution info
        self.metrics["retry_count"] = state.get("error_iteration", 0)
        self.metrics["refinement_count"] = state.get("refinement_iteration", 0)

        # Extract SQL query
        if "query" in state and state["query"]:
            self.metrics["sql_generated"] = state["query"]
            self.metrics["success"] = True

        # Extract error if present
        if "messages" in state and state["messages"]:
            last_message = state["messages"][-1]
            if hasattr(last_message, "content") and "Error" in str(
                last_message.content
            ):
                self.metrics["error_message"] = str(last_message.content)
                self.metrics["success"] = False

        # Extract result info
        if "result" in state and state["result"]:
            result = state["result"]
            if isinstance(result, list):
                self.metrics["result_row_count"] = len(result)
            elif isinstance(result, dict) and "rows" in result:
                self.metrics["result_row_count"] = len(result["rows"])

        # Extract planner output details
        if "planner_output" in state and state["planner_output"]:
            planner_output = state["planner_output"]
            self._extract_planner_details(planner_output)

    def _extract_planner_details(self, planner_output: Any):
        """Extract details from PlannerOutput object."""
        # Tables selected
        if hasattr(planner_output, "selections") and planner_output.selections:
            for selection in planner_output.selections:
                table_name = selection.get("table") or selection.get("table_name")
                if table_name:
                    self.metrics["tables_selected"].append(table_name)

                # Columns
                columns = selection.get("columns", [])
                for col in columns:
                    if isinstance(col, dict):
                        col_name = col.get("name") or col.get("column")
                        if col_name:
                            self.metrics["columns_selected"].append(
                                f"{table_name}.{col_name}"
                            )
                    elif isinstance(col, str):
                        self.metrics["columns_selected"].append(f"{table_name}.{col}")

        # Joins
        if hasattr(planner_output, "join_edges") and planner_output.join_edges:
            for edge in planner_output.join_edges:
                join_info = {
                    "from_table": edge.get("from_table"),
                    "from_column": edge.get("from_column"),
                    "to_table": edge.get("to_table"),
                    "to_column": edge.get("to_column"),
                }
                self.metrics["joins_used"].append(join_info)

        # Filters
        if hasattr(planner_output, "filters") and planner_output.filters:
            for filter_pred in planner_output.filters:
                filter_info = {
                    "table": filter_pred.get("table"),
                    "column": filter_pred.get("column"),
                    "operator": filter_pred.get("operator"),
                    "value": filter_pred.get("value"),
                }
                self.metrics["filters_applied"].append(filter_info)

        # Aggregations
        if hasattr(planner_output, "aggregations") and planner_output.aggregations:
            for agg in planner_output.aggregations:
                self.metrics["aggregations_used"].append(agg)

    def collect_from_debug_files(self):
        """Extract metrics from debug files."""
        # Extract token usage from planner prompt debug file
        planner_prompt_file = os.path.join(DEBUG_DIR, "debug_planner_prompt.json")
        if os.path.exists(planner_prompt_file):
            try:
                with open(planner_prompt_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Count tokens from messages
                    messages = data.get("messages", [])
                    total_input_chars = sum(
                        len(str(msg.get("content", ""))) for msg in messages
                    )
                    # Rough estimate: 1 token ≈ 4 characters
                    self.metrics["token_usage"]["input_tokens"] = total_input_chars // 4
            except Exception as e:
                print(f"WARNING: Warning: Could not extract token usage: {e}")

        # Extract planner output if not already collected
        planner_output_file = os.path.join(
            DEBUG_DIR, "debug_generated_planner_output.json"
        )
        if os.path.exists(planner_output_file):
            try:
                with open(planner_output_file, "r", encoding="utf-8") as f:
                    planner_data = json.load(f)
                    # Estimate output tokens
                    output_chars = len(json.dumps(planner_data))
                    self.metrics["token_usage"]["output_tokens"] = output_chars // 4
            except Exception as e:
                print(f"WARNING: Warning: Could not extract planner output: {e}")

        # Calculate total tokens
        self.metrics["token_usage"]["total_tokens"] = (
            self.metrics["token_usage"]["input_tokens"]
            + self.metrics["token_usage"]["output_tokens"]
        )

        # Extract SQL from debug file if not in state
        if not self.metrics["sql_generated"]:
            sql_file = os.path.join(DEBUG_DIR, "debug_generated_sql.json")
            if os.path.exists(sql_file):
                try:
                    with open(sql_file, "r", encoding="utf-8") as f:
                        sql_data = json.load(f)
                        self.metrics["sql_generated"] = sql_data.get("query", "")
                except Exception as e:
                    print(f"WARNING: Warning: Could not extract SQL: {e}")

    def calculate_cost(self) -> float:
        """
        Calculate estimated API cost based on token usage.

        Returns:
            Estimated cost in USD
        """
        if self.model_name not in TOKEN_COSTS:
            return 0.0

        costs = TOKEN_COSTS[self.model_name]
        input_tokens = self.metrics["token_usage"]["input_tokens"]
        output_tokens = self.metrics["token_usage"]["output_tokens"]

        input_cost = (input_tokens / 1_000_000) * costs["input"]
        output_cost = (output_tokens / 1_000_000) * costs["output"]

        total_cost = input_cost + output_cost
        return round(total_cost, 6)

    def get_metrics(self) -> Dict[str, Any]:
        """Get the collected metrics dictionary."""
        # Add cost calculation
        self.metrics["estimated_cost_usd"] = self.calculate_cost()
        return self.metrics

    def save_metrics(self, output_file: str):
        """
        Save metrics to a JSON file.

        Args:
            output_file: Path to output JSON file
        """
        metrics = self.get_metrics()
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)

        print(f" Saved metrics to {output_file}")


def copy_debug_files(destination_dir: str):
    """
    Copy all debug files to a destination directory.

    Args:
        destination_dir: Directory to copy debug files to
    """
    os.makedirs(destination_dir, exist_ok=True)
    copied_count = 0

    for debug_file in DEBUG_FILES_TO_COLLECT:
        source_path = os.path.join(DEBUG_DIR, debug_file)
        if os.path.exists(source_path):
            dest_path = os.path.join(destination_dir, debug_file)
            try:
                import shutil

                shutil.copy2(source_path, dest_path)
                copied_count += 1
            except Exception as e:
                print(f"WARNING: Warning: Could not copy {debug_file}: {e}")

    print(
        f" Copied {copied_count}/{len(DEBUG_FILES_TO_COLLECT)} debug files to {destination_dir}"
    )


if __name__ == "__main__":
    # Test the MetricsCollector
    collector = MetricsCollector("test-model", "query-1")
    collector.start_timer()
    time.sleep(0.1)  # Simulate work
    collector.stop_timer()
    print(f"Execution time: {collector.metrics['execution_time_seconds']}s")
