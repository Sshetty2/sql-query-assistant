"""
SQL Comparator

This module compares generated SQL queries against ground truth SQL
and calculates quality scores based on structural and semantic similarity.
"""

import sqlglot
from typing import Dict, List, Any, Tuple
from benchmark.config.benchmark_settings import QUALITY_WEIGHTS


class SQLComparator:
    """Compares generated SQL against ground truth."""

    def __init__(self, ground_truth_sql: str, generated_sql: str):
        self.ground_truth_sql = ground_truth_sql.strip()
        self.generated_sql = generated_sql.strip()
        self.ground_truth_ast = None
        self.generated_ast = None
        self.comparison_results = {}

    def parse_sql(self) -> Tuple[bool, str]:
        """
        Parse both SQL queries using SQLGlot.

        Returns:
            Tuple of (success, error_message)
        """
        try:
            self.ground_truth_ast = sqlglot.parse_one(self.ground_truth_sql, dialect="tsql")
            self.generated_ast = sqlglot.parse_one(self.generated_sql, dialect="tsql")
            return True, ""
        except Exception as e:
            return False, str(e)

    def extract_tables(self, ast) -> List[str]:
        """Extract table names from SQL AST."""
        tables = []
        try:
            for table in ast.find_all(sqlglot.exp.Table):
                table_name = table.name
                if table_name:
                    tables.append(table_name.upper())
        except Exception:
            pass
        return list(set(tables))

    def extract_joins(self, ast) -> List[Dict[str, Any]]:
        """Extract join information from SQL AST."""
        joins = []
        try:
            for join in ast.find_all(sqlglot.exp.Join):
                join_info = {
                    "type": join.kind if hasattr(join, 'kind') else "INNER",
                    "table": str(join.this) if hasattr(join, 'this') else "",
                    "condition": str(join.on) if hasattr(join, 'on') else ""
                }
                joins.append(join_info)
        except Exception:
            pass
        return joins

    def extract_where_conditions(self, ast) -> List[str]:
        """Extract WHERE clause conditions from SQL AST."""
        conditions = []
        try:
            for where in ast.find_all(sqlglot.exp.Where):
                conditions.append(str(where.this))
        except Exception:
            pass
        return conditions

    def extract_aggregations(self, ast) -> List[str]:
        """Extract aggregation functions from SQL AST."""
        aggregations = []
        try:
            for func in ast.find_all(sqlglot.exp.AggFunc):
                aggregations.append(func.sql())
        except Exception:
            pass
        return aggregations

    def extract_group_by(self, ast) -> List[str]:
        """Extract GROUP BY columns from SQL AST."""
        group_by_cols = []
        try:
            for group_by in ast.find_all(sqlglot.exp.Group):
                for expr in group_by.expressions:
                    group_by_cols.append(str(expr))
        except Exception:
            pass
        return group_by_cols

    def extract_order_by(self, ast) -> List[Dict[str, str]]:
        """Extract ORDER BY columns from SQL AST."""
        order_by_cols = []
        try:
            for order in ast.find_all(sqlglot.exp.Order):
                for expr in order.expressions:
                    order_info = {
                        "column": str(expr.this) if hasattr(expr, 'this') else str(expr),
                        "direction": "DESC" if expr.args.get("desc") else "ASC"
                    }
                    order_by_cols.append(order_info)
        except Exception:
            pass
        return order_by_cols

    def compare_structures(self) -> Dict[str, Any]:
        """
        Compare structural elements of both SQL queries.

        Returns:
            Dictionary containing comparison results
        """
        if not self.ground_truth_ast or not self.generated_ast:
            success, error = self.parse_sql()
            if not success:
                return {"error": f"Failed to parse SQL: {error}"}

        # Extract components from both queries
        gt_tables = self.extract_tables(self.ground_truth_ast)
        gen_tables = self.extract_tables(self.generated_ast)

        gt_joins = self.extract_joins(self.ground_truth_ast)
        gen_joins = self.extract_joins(self.generated_ast)

        gt_conditions = self.extract_where_conditions(self.ground_truth_ast)
        gen_conditions = self.extract_where_conditions(self.generated_ast)

        gt_aggregations = self.extract_aggregations(self.ground_truth_ast)
        gen_aggregations = self.extract_aggregations(self.generated_ast)

        gt_group_by = self.extract_group_by(self.ground_truth_ast)
        gen_group_by = self.extract_group_by(self.generated_ast)

        gt_order_by = self.extract_order_by(self.ground_truth_ast)
        gen_order_by = self.extract_order_by(self.generated_ast)

        # Compare components
        self.comparison_results = {
            "tables": {
                "ground_truth": gt_tables,
                "generated": gen_tables,
                "match": set(gt_tables) == set(gen_tables),
                "missing": list(set(gt_tables) - set(gen_tables)),
                "extra": list(set(gen_tables) - set(gt_tables))
            },
            "joins": {
                "ground_truth_count": len(gt_joins),
                "generated_count": len(gen_joins),
                "match": len(gt_joins) == len(gen_joins)
            },
            "conditions": {
                "ground_truth_count": len(gt_conditions),
                "generated_count": len(gen_conditions),
                "match": len(gt_conditions) == len(gen_conditions)
            },
            "aggregations": {
                "ground_truth": gt_aggregations,
                "generated": gen_aggregations,
                "match": set(gt_aggregations) == set(gen_aggregations)
            },
            "group_by": {
                "ground_truth": gt_group_by,
                "generated": gen_group_by,
                "match": set(gt_group_by) == set(gen_group_by)
            },
            "order_by": {
                "ground_truth": gt_order_by,
                "generated": gen_order_by,
                "match": gt_order_by == gen_order_by
            }
        }

        return self.comparison_results

    def calculate_quality_score(
        self,
        sql_executes: bool,
        result_row_count: int = None,
        ground_truth_row_count: int = None
    ) -> int:
        """
        Calculate quality score based on comparison results and execution success.

        Args:
            sql_executes: Whether the generated SQL executed successfully
            result_row_count: Number of rows returned by generated SQL
            ground_truth_row_count: Number of rows returned by ground truth SQL

        Returns:
            Quality score (0-100)
        """
        if not self.comparison_results:
            self.compare_structures()

        score = 0

        # SQL executes without errors (30 points)
        if sql_executes:
            score += QUALITY_WEIGHTS["sql_executes"]

        # Correct tables selected (20 points)
        if self.comparison_results["tables"]["match"]:
            score += QUALITY_WEIGHTS["correct_tables"]
        else:
            # Partial credit based on overlap
            gt_tables = set(self.comparison_results["tables"]["ground_truth"])
            gen_tables = set(self.comparison_results["tables"]["generated"])
            if gt_tables and gen_tables:
                overlap = len(gt_tables & gen_tables) / len(gt_tables)
                score += int(QUALITY_WEIGHTS["correct_tables"] * overlap)

        # Correct joins (20 points)
        if self.comparison_results["joins"]["match"]:
            score += QUALITY_WEIGHTS["correct_joins"]
        else:
            # Partial credit if join counts are close
            gt_count = self.comparison_results["joins"]["ground_truth_count"]
            gen_count = self.comparison_results["joins"]["generated_count"]
            if gt_count > 0:
                similarity = 1 - abs(gt_count - gen_count) / max(gt_count, gen_count)
                score += int(QUALITY_WEIGHTS["correct_joins"] * max(0, similarity))

        # Correct filters (15 points)
        if self.comparison_results["conditions"]["match"]:
            score += QUALITY_WEIGHTS["correct_filters"]
        else:
            # Partial credit if condition counts are close
            gt_count = self.comparison_results["conditions"]["ground_truth_count"]
            gen_count = self.comparison_results["conditions"]["generated_count"]
            if gt_count > 0:
                similarity = 1 - abs(gt_count - gen_count) / max(gt_count, gen_count)
                score += int(QUALITY_WEIGHTS["correct_filters"] * max(0, similarity))

        # Correct aggregations (10 points)
        if self.comparison_results["aggregations"]["match"]:
            score += QUALITY_WEIGHTS["correct_aggregations"]
        else:
            # Partial credit based on overlap
            gt_aggs = set(self.comparison_results["aggregations"]["ground_truth"])
            gen_aggs = set(self.comparison_results["aggregations"]["generated"])
            if gt_aggs and gen_aggs:
                overlap = len(gt_aggs & gen_aggs) / len(gt_aggs)
                score += int(QUALITY_WEIGHTS["correct_aggregations"] * overlap)

        # Similar results (5 points)
        if result_row_count is not None and ground_truth_row_count is not None:
            if result_row_count == ground_truth_row_count:
                score += QUALITY_WEIGHTS["similar_results"]
            elif ground_truth_row_count > 0:
                # Partial credit if row counts are within 20%
                diff_ratio = abs(result_row_count - ground_truth_row_count) / ground_truth_row_count
                if diff_ratio <= 0.2:
                    score += int(QUALITY_WEIGHTS["similar_results"] * (1 - diff_ratio / 0.2))

        return min(100, max(0, score))

    def get_differences_summary(self) -> str:
        """
        Generate a human-readable summary of differences.

        Returns:
            Markdown formatted summary
        """
        if not self.comparison_results:
            self.compare_structures()

        summary = "### SQL Comparison Summary\n\n"

        # Tables
        tables_match = "" if self.comparison_results["tables"]["match"] else "X"
        summary += f"**Tables {tables_match}**\n"
        if not self.comparison_results["tables"]["match"]:
            if self.comparison_results["tables"]["missing"]:
                summary += f"- Missing: {', '.join(self.comparison_results['tables']['missing'])}\n"
            if self.comparison_results["tables"]["extra"]:
                summary += f"- Extra: {', '.join(self.comparison_results['tables']['extra'])}\n"
        summary += "\n"

        # Joins
        joins_match = "" if self.comparison_results["joins"]["match"] else "X"
        summary += f"**Joins {joins_match}**\n"
        summary += f"- Ground truth: {self.comparison_results['joins']['ground_truth_count']} joins\n"
        summary += f"- Generated: {self.comparison_results['joins']['generated_count']} joins\n\n"

        # Aggregations
        aggs_match = "" if self.comparison_results["aggregations"]["match"] else "X"
        summary += f"**Aggregations {aggs_match}**\n"
        if self.comparison_results["aggregations"]["ground_truth"]:
            summary += f"- Ground truth: {', '.join(self.comparison_results['aggregations']['ground_truth'])}\n"
        if self.comparison_results["aggregations"]["generated"]:
            summary += f"- Generated: {', '.join(self.comparison_results['aggregations']['generated'])}\n"

        return summary


if __name__ == "__main__":
    # Test the SQLComparator
    ground_truth = "SELECT * FROM users WHERE age > 18 ORDER BY name"
    generated = "SELECT * FROM users WHERE age > 21 ORDER BY name DESC"

    comparator = SQLComparator(ground_truth, generated)
    results = comparator.compare_structures()
    score = comparator.calculate_quality_score(sql_executes=True)
    print(f"Quality Score: {score}/100")
    print(comparator.get_differences_summary())
