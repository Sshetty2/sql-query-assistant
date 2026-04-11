"""Generate deterministic data summary statistics from query results.

Pure Python computation — no LLM calls. Computes column-level statistics
from the JSON result string returned by execute_query.
"""

import json
import re
import statistics
from collections import Counter
from typing import Any, Optional

from utils.logger import get_logger
from utils.stream_utils import emit_node_status

logger = get_logger()

# ISO datetime pattern: YYYY-MM-DDTHH:MM:SS (with optional fractional seconds and timezone)
ISO_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$"
)

# Date-only pattern: YYYY-MM-DD
DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _detect_column_type(values: list[Any]) -> str:
    """Detect the dominant type of a column from its non-null values.

    Args:
        values: List of non-null values from the column.

    Returns:
        One of: "numeric", "text", "datetime", "boolean", "null"
    """
    if not values:
        return "null"

    type_counts: Counter = Counter()
    for v in values:
        if isinstance(v, bool):
            type_counts["boolean"] += 1
        elif isinstance(v, (int, float)):
            type_counts["numeric"] += 1
        elif isinstance(v, str):
            if ISO_DATETIME_RE.match(v) or DATE_ONLY_RE.match(v):
                type_counts["datetime"] += 1
            else:
                # Try to detect numeric strings
                try:
                    float(v)
                    type_counts["numeric"] += 1
                except (ValueError, TypeError):
                    type_counts["text"] += 1
        else:
            type_counts["text"] += 1

    if not type_counts:
        return "null"

    # Return the most common type
    return type_counts.most_common(1)[0][0]


def _compute_numeric_stats(values: list) -> dict:
    """Compute statistics for a numeric column."""
    nums = []
    for v in values:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            nums.append(float(v))
        elif isinstance(v, str):
            try:
                nums.append(float(v))
            except (ValueError, TypeError):
                pass

    if not nums:
        return {}

    return {
        "min": min(nums),
        "max": max(nums),
        "avg": round(statistics.mean(nums), 4),
        "median": round(statistics.median(nums), 4),
        "sum": round(sum(nums), 4),
    }


def _compute_text_stats(values: list) -> dict:
    """Compute statistics for a text column."""
    strs = [str(v) for v in values if v is not None]
    if not strs:
        return {}

    lengths = [len(s) for s in strs]
    counter = Counter(strs)
    top_values = [
        {"value": val, "count": count}
        for val, count in counter.most_common(5)
    ]

    return {
        "min_length": min(lengths),
        "max_length": max(lengths),
        "avg_length": round(statistics.mean(lengths), 2),
        "top_values": top_values,
    }


def _parse_datetime(val: str) -> Optional[float]:
    """Parse a datetime string to a timestamp for comparison."""
    from datetime import datetime

    for fmt in [
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]:
        try:
            return datetime.strptime(val.rstrip("Z"), fmt).timestamp()
        except ValueError:
            continue
    return None


def _compute_datetime_stats(values: list) -> dict:
    """Compute statistics for a datetime column."""
    strs = [str(v) for v in values if v is not None]
    timestamps = []
    originals = []
    for s in strs:
        ts = _parse_datetime(s)
        if ts is not None:
            timestamps.append(ts)
            originals.append(s)

    if not timestamps:
        return {}

    min_idx = timestamps.index(min(timestamps))
    max_idx = timestamps.index(max(timestamps))
    range_seconds = max(timestamps) - min(timestamps)

    return {
        "min": originals[min_idx],
        "max": originals[max_idx],
        "range_days": round(range_seconds / 86400, 2),
    }


def compute_data_summary(
    result_json: str, total_records_available: Optional[int] = None
) -> dict:
    """Compute deterministic statistics from query results.

    Args:
        result_json: JSON string of query results (list of dicts).
        total_records_available: Total record count before LIMIT was applied.

    Returns:
        Summary dict with row_count, column_count, total_records_available,
        and per-column statistics.
    """
    try:
        rows = json.loads(result_json)
    except (json.JSONDecodeError, TypeError):
        return {
            "row_count": 0,
            "total_records_available": total_records_available,
            "column_count": 0,
            "columns": {},
        }

    if not rows or not isinstance(rows, list):
        return {
            "row_count": 0,
            "total_records_available": total_records_available,
            "column_count": 0,
            "columns": {},
        }

    # Extract column names from first row
    col_names = list(rows[0].keys()) if rows else []
    row_count = len(rows)

    columns_summary = {}
    for col in col_names:
        all_values = [row.get(col) for row in rows]
        non_null = [v for v in all_values if v is not None]
        null_count = len(all_values) - len(non_null)
        distinct_count = len(set(str(v) for v in non_null))

        col_type = _detect_column_type(non_null)

        col_stats: dict[str, Any] = {
            "type": col_type,
            "null_count": null_count,
            "distinct_count": distinct_count,
        }

        if col_type == "numeric":
            col_stats.update(_compute_numeric_stats(non_null))
        elif col_type == "text":
            col_stats.update(_compute_text_stats(non_null))
        elif col_type == "datetime":
            col_stats.update(_compute_datetime_stats(non_null))

        columns_summary[col] = col_stats

    return {
        "row_count": row_count,
        "total_records_available": total_records_available,
        "column_count": len(col_names),
        "columns": columns_summary,
    }


def generate_data_summary_node(state):
    """LangGraph workflow node that computes data summary after successful query.

    Runs only when results exist. Stores summary in state["data_summary"].
    """
    emit_node_status("generate_data_summary", "running", "Computing data summary")

    result = state.get("result")
    if not result:
        logger.debug("No result to summarize, skipping data summary")
        emit_node_status("generate_data_summary", "completed", "No data to summarize")
        return {**state, "data_summary": None}

    # Check if result is empty
    try:
        data = json.loads(result) if isinstance(result, str) else result
        if not data or (isinstance(data, list) and len(data) == 0):
            logger.debug("Empty result set, skipping data summary")
            emit_node_status("generate_data_summary", "completed", "Empty result set")
            return {**state, "data_summary": None}
    except (json.JSONDecodeError, TypeError):
        logger.debug("Could not parse result, skipping data summary")
        emit_node_status("generate_data_summary", "completed", "Could not parse results")
        return {**state, "data_summary": None}

    result_json = result if isinstance(result, str) else json.dumps(result)
    total_records = state.get("total_records_available")

    summary = compute_data_summary(result_json, total_records)

    logger.info(
        f"Data summary computed: {summary['row_count']} rows, "
        f"{summary['column_count']} columns",
        extra={
            "row_count": summary["row_count"],
            "column_count": summary["column_count"],
            "total_records_available": summary["total_records_available"],
        },
    )

    emit_node_status("generate_data_summary", "completed", "Data summary computed")
    return {**state, "data_summary": summary}
