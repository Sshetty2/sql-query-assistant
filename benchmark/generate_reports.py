"""
Report Generator

Generates comprehensive analysis reports from benchmark results.
"""

import os
import json
from typing import List, Dict, Any
from datetime import datetime

from benchmark.config.model_configs import MODELS


class ReportGenerator:
    """Generates markdown reports from benchmark results."""

    def __init__(self, results_timestamp_dir: str):
        self.results_dir = results_timestamp_dir
        self.reports_dir = os.path.join(results_timestamp_dir, "reports")
        os.makedirs(self.reports_dir, exist_ok=True)

        # Load all metrics
        self.all_metrics = self._load_all_metrics()

    def _load_all_metrics(self) -> List[Dict[str, Any]]:
        """Load all metrics.json files from results directory."""
        all_metrics = []

        for model_dir in os.listdir(self.results_dir):
            model_path = os.path.join(self.results_dir, model_dir)

            if not os.path.isdir(model_path) or model_dir == "reports":
                continue

            for query_dir in os.listdir(model_path):
                query_path = os.path.join(model_path, query_dir)

                if not os.path.isdir(query_path):
                    continue

                metrics_file = os.path.join(query_path, "metrics.json")
                if os.path.exists(metrics_file):
                    with open(metrics_file, "r", encoding="utf-8") as f:
                        metrics = json.load(f)
                        all_metrics.append(metrics)

        print(f" Loaded {len(all_metrics)} metric files")
        return all_metrics

    def generate_benchmark_summary(self):
        """Generate overall benchmark summary report."""
        report = []
        report.append("# LLM Benchmark Results\n")
        report.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # Executive Summary
        report.append("## Executive Summary\n\n")
        total_runs = len(self.all_metrics)
        successful_runs = len([m for m in self.all_metrics if m.get("success")])
        models_tested = len(set(m["model_name"] for m in self.all_metrics))
        queries_tested = len(set(m["query_id"] for m in self.all_metrics))

        report.append(f"- **Total Runs:** {total_runs}\n")
        report.append(
            f"- **Successful Runs:** {successful_runs} ({successful_runs/total_runs*100:.1f}%)\n"
        )
        report.append(f"- **Models Tested:** {models_tested}\n")
        report.append(f"- **Queries Tested:** {queries_tested}\n")
        report.append("- **Planner Complexity:** Minimal (all models)\n\n")

        # Overall Performance Table
        report.append("## Overall Performance\n\n")
        report.append(
            "| Model | Category | Avg Time (s) | Success Rate | Avg Quality Score | Avg Tokens | Est. Cost/Query |\n"  # noqa: E501
        )
        report.append(
            "|-------|----------|--------------|--------------|-------------------|------------|------------------|\n"
        )

        # Group by model
        model_stats = {}
        for model_name in sorted(set(m["model_name"] for m in self.all_metrics)):
            model_metrics = [
                m for m in self.all_metrics if m["model_name"] == model_name
            ]

            avg_time = sum(
                m.get("execution_time_seconds", 0) for m in model_metrics
            ) / len(model_metrics)
            success_rate = (
                len([m for m in model_metrics if m.get("success")])
                / len(model_metrics)
                * 100
            )
            avg_quality = sum(m.get("quality_score", 0) for m in model_metrics) / len(
                model_metrics
            )
            avg_tokens = sum(
                m.get("token_usage", {}).get("total_tokens", 0) for m in model_metrics
            ) / len(model_metrics)
            avg_cost = sum(m.get("estimated_cost_usd", 0) for m in model_metrics) / len(
                model_metrics
            )

            category = MODELS.get(model_name, {}).get("category", "unknown")

            report.append(
                f"| {model_name} | {category} | {avg_time:.2f} | {success_rate:.0f}% | {avg_quality:.0f}/100 | {avg_tokens:.0f} | ${avg_cost:.6f} |\n"  # noqa: E501
            )

            model_stats[model_name] = {
                "avg_time": avg_time,
                "success_rate": success_rate,
                "avg_quality": avg_quality,
                "avg_tokens": avg_tokens,
                "avg_cost": avg_cost,
            }

        report.append("\n")

        # Key Findings
        report.append("## Key Findings\n\n")

        # Best overall (by quality score)
        best_model = max(model_stats.items(), key=lambda x: x[1]["avg_quality"])
        report.append(
            f"- **Best Overall Quality:** {best_model[0]} ({best_model[1]['avg_quality']:.0f}/100)\n"
        )

        # Fastest
        fastest_model = min(model_stats.items(), key=lambda x: x[1]["avg_time"])
        report.append(
            f"- **Fastest:** {fastest_model[0]} ({fastest_model[1]['avg_time']:.2f}s)\n"
        )

        # Best value (quality/cost for remote, quality/time for local)
        remote_models = {
            k: v
            for k, v in model_stats.items()
            if MODELS.get(k, {}).get("category") == "remote"
        }
        if remote_models:
            best_value_remote = max(
                remote_models.items(),
                key=lambda x: x[1]["avg_quality"] / max(x[1]["avg_cost"], 0.000001),
            )
            report.append(
                f"- **Best Value (Remote):** {best_value_remote[0]} ({best_value_remote[1]['avg_quality']:.0f} quality / ${best_value_remote[1]['avg_cost']:.6f})\n"  # noqa: E501
            )

        local_models = {
            k: v
            for k, v in model_stats.items()
            if MODELS.get(k, {}).get("category") == "local"
        }
        if local_models:
            best_local = max(local_models.items(), key=lambda x: x[1]["avg_quality"])
            report.append(
                f"- **Best Local Model:** {best_local[0]} ({best_local[1]['avg_quality']:.0f}/100)\n"
            )

        report.append("\n")

        # Query-by-Query Breakdown
        report.append("## Query-by-Query Breakdown\n\n")

        for query_id in sorted(set(m["query_id"] for m in self.all_metrics)):
            report.append(f"### {query_id}\n\n")
            report.append("| Model | Success | Time (s) | Quality | Tokens | Cost |\n")
            report.append("|-------|---------|----------|---------|--------|------|\n")

            query_metrics = [m for m in self.all_metrics if m["query_id"] == query_id]
            for m in sorted(
                query_metrics, key=lambda x: x.get("quality_score", 0), reverse=True
            ):
                success = "" if m.get("success") else "X"
                time_val = m.get("execution_time_seconds", 0)
                quality = m.get("quality_score", 0)
                tokens = m.get("token_usage", {}).get("total_tokens", 0)
                cost = m.get("estimated_cost_usd", 0)

                report.append(
                    f"| {m['model_name']} | {success} | {time_val:.2f} | {quality}/100 | {tokens} | ${cost:.6f} |\n"
                )

            report.append("\n")

        # Save report
        report_file = os.path.join(self.reports_dir, "benchmark_summary.md")
        with open(report_file, "w", encoding="utf-8") as f:
            f.writelines(report)

        print(f" Generated benchmark summary: {report_file}")
        return report_file

    def generate_model_comparison(self):
        """Generate detailed model comparison report."""
        report = []
        report.append("# Model Comparison Report\n\n")

        # Group by query for detailed comparison
        for query_id in sorted(set(m["query_id"] for m in self.all_metrics)):
            report.append(f"## {query_id}\n\n")

            query_metrics = [m for m in self.all_metrics if m["query_id"] == query_id]

            # Load SQL comparison for each model
            for m in query_metrics:
                model_name = m["model_name"]
                report.append(f"### {model_name}\n\n")

                # Load SQL comparison if available
                comparison_file = os.path.join(
                    self.results_dir, model_name, query_id, "sql_comparison.json"
                )
                if os.path.exists(comparison_file):
                    with open(comparison_file, "r", encoding="utf-8") as f:
                        comparison = json.load(f)

                    report.append(
                        f"**Quality Score:** {comparison.get('quality_score', 0)}/100\n\n"
                    )
                    report.append(
                        f"**Generated SQL:**\n```sql\n{comparison.get('generated_sql', 'N/A')}\n```\n\n"
                    )
                    report.append(f"{comparison.get('differences_summary', '')}\n\n")
                else:
                    report.append("*No SQL comparison available*\n\n")

                report.append("---\n\n")

        # Save report
        report_file = os.path.join(self.reports_dir, "model_comparison.md")
        with open(report_file, "w", encoding="utf-8") as f:
            f.writelines(report)

        print(f" Generated model comparison: {report_file}")
        return report_file

    def generate_recommendations(self):
        """Generate recommendations report."""
        report = []
        report.append("# Recommendations\n\n")

        # Calculate model statistics
        model_stats = {}
        for model_name in set(m["model_name"] for m in self.all_metrics):
            model_metrics = [
                m for m in self.all_metrics if m["model_name"] == model_name
            ]

            avg_quality = sum(m.get("quality_score", 0) for m in model_metrics) / len(
                model_metrics
            )
            avg_time = sum(
                m.get("execution_time_seconds", 0) for m in model_metrics
            ) / len(model_metrics)
            avg_cost = sum(m.get("estimated_cost_usd", 0) for m in model_metrics) / len(
                model_metrics
            )
            success_rate = len([m for m in model_metrics if m.get("success")]) / len(
                model_metrics
            )

            model_stats[model_name] = {
                "avg_quality": avg_quality,
                "avg_time": avg_time,
                "avg_cost": avg_cost,
                "success_rate": success_rate,
                "category": MODELS.get(model_name, {}).get("category", "unknown"),
            }

        # Production Use
        report.append("## Best Model for Production Use\n\n")
        best_production = max(
            model_stats.items(),
            key=lambda x: (x[1]["success_rate"], x[1]["avg_quality"]),
        )
        report.append(f"**Recommended:** {best_production[0]}\n\n")
        report.append(f"- Quality Score: {best_production[1]['avg_quality']:.0f}/100\n")
        report.append(
            f"- Success Rate: {best_production[1]['success_rate']*100:.0f}%\n"
        )
        report.append(f"- Avg Time: {best_production[1]['avg_time']:.2f}s\n")
        report.append(f"- Cost/Query: ${best_production[1]['avg_cost']:.6f}\n\n")

        # Cost-Conscious
        report.append("## Best for Cost-Conscious Applications\n\n")
        local_stats = {k: v for k, v in model_stats.items() if v["category"] == "local"}
        if local_stats:
            best_local = max(local_stats.items(), key=lambda x: x[1]["avg_quality"])
            report.append(f"**Recommended:** {best_local[0]} (Free/Local)\n\n")
            report.append(f"- Quality Score: {best_local[1]['avg_quality']:.0f}/100\n")
            report.append(f"- Success Rate: {best_local[1]['success_rate']*100:.0f}%\n")
            report.append(f"- Avg Time: {best_local[1]['avg_time']:.2f}s\n\n")

        # Speed Priority
        report.append("## Best for Speed Priority\n\n")
        fastest = min(model_stats.items(), key=lambda x: x[1]["avg_time"])
        report.append(f"**Recommended:** {fastest[0]}\n\n")
        report.append(f"- Avg Time: {fastest[1]['avg_time']:.2f}s\n")
        report.append(f"- Quality Score: {fastest[1]['avg_quality']:.0f}/100\n\n")

        # Configuration Recommendations
        report.append("## Configuration Recommendations\n\n")
        report.append("Based on these benchmark results:\n\n")
        report.append(
            "1. **All models used PLANNER_COMPLEXITY=minimal** - This level is sufficient for most queries\n"
        )
        report.append(
            "2. **Success rates varied** - Consider fallback strategies for less reliable models\n"
        )
        report.append(
            "3. **Cost varies significantly** - Local models provide zero-cost alternative with acceptable quality\n\n"
        )

        # Save report
        report_file = os.path.join(self.reports_dir, "recommendations.md")
        with open(report_file, "w", encoding="utf-8") as f:
            f.writelines(report)

        print(f" Generated recommendations: {report_file}")
        return report_file

    def generate_all_reports(self):
        """Generate all reports."""
        print("\n" + "=" * 80)
        print("Generating Reports")
        print("=" * 80 + "\n")

        self.generate_benchmark_summary()
        self.generate_model_comparison()
        self.generate_recommendations()

        print(f"\n All reports generated in: {self.reports_dir}\n")


def main():
    """Main entry point."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python generate_reports.py <results_timestamp_dir>")
        print(
            "Example: python generate_reports.py benchmark/results/2025-10-31_14-30-00"
        )
        sys.exit(1)

    results_dir = sys.argv[1]

    if not os.path.exists(results_dir):
        print(f"Error: Results directory not found: {results_dir}")
        sys.exit(1)

    generator = ReportGenerator(results_dir)
    generator.generate_all_reports()


if __name__ == "__main__":
    main()
