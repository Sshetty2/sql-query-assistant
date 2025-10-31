# Implementation of Fix #1: Auto-Fix Join Edges Validation

**Date:** 2025-10-31
**Priority:** 🔥🔥🔥 Critical
**Impact:** Prevents 55% of logged errors from benchmark analysis
**Status:** ✅ Implemented and Tested

---

## Problem Statement

The benchmark analysis identified that the most common error pattern was **Planner Validation Errors** where LLMs create `join_edges` referencing tables not included in the `selections` array, violating Pydantic validation rules.

### Example Error
```json
{
  "selections": [{"table": "tb_Users", ...}],
  "join_edges": [{
    "from_table": "tb_Users",
    "to_table": "tb_Company",  // ❌ tb_Company NOT in selections
    ...
  }]
}
```

**Error Message:**
```
Value error, join_edges reference tables not in selections: ['tb_Company']
```

This error accounted for **55% of logged errors** in the benchmark results and affects multiple models (gpt-5, llama3.1-8b, qwen models).

---

## Solution Implemented

### 1. Auto-Fix Function (`agent/planner.py:26-77`)

Created `auto_fix_join_edges()` function that automatically adds missing tables to selections before Pydantic validation:

```python
def auto_fix_join_edges(planner_output_dict: dict) -> dict:
    """
    Auto-add missing tables referenced in join_edges to selections.

    This fixes the most common planner error where LLMs create join_edges
    referencing tables not included in the selections array.
    """
    # Get currently selected tables
    selected_tables = {sel.get("table") for sel in selections if sel.get("table")}

    # Get all tables referenced in join_edges
    join_tables = set()
    for edge in planner_output_dict.get("join_edges", []):
        if edge.get("from_table"):
            join_tables.add(edge["from_table"])
        if edge.get("to_table"):
            join_tables.add(edge["to_table"])

    # Find tables in joins but not in selections
    missing_tables = join_tables - selected_tables

    # Auto-add missing tables to selections
    if missing_tables:
        for table in missing_tables:
            selections.append({
                "table": table,
                "confidence": 0.7,  # Lower confidence for auto-added tables
                "columns": [],  # No specific columns needed
                "include_only_for_join": True,  # Table added only for joining
                "filters": []
            })

    return planner_output_dict
```

### 2. Integration with Planner Retry Loop (`agent/planner.py:1098-1214`)

Modified the planner invocation to detect join_edges validation errors and apply auto-fix:

**Workflow:**
1. Try structured output directly (normal path)
2. If `OutputParserException` with join_edges validation error:
   - Detect the error type using `extract_validation_error_details()`
   - If it's a join_edges error, get raw JSON response
   - Apply `auto_fix_join_edges()` to the JSON
   - Manually validate with Pydantic model
   - Log success and continue

**Key Features:**
- Only makes ONE extra LLM call when auto-fix is needed (not two)
- Only applies auto-fix for join_edges validation errors (not other errors)
- Transparent logging of auto-fix application
- Preserves all retry logic for other error types

---

## Test Coverage

### Unit Tests (`tests/unit/test_planner_auto_fix.py`)

Created 7 comprehensive unit tests:

1. ✅ **test_auto_fix_join_edges_adds_missing_tables** - Basic functionality
2. ✅ **test_auto_fix_join_edges_multiple_missing_tables** - Multiple missing tables
3. ✅ **test_auto_fix_join_edges_no_changes_needed** - No modifications when valid
4. ✅ **test_auto_fix_join_edges_empty_join_edges** - Empty join_edges array
5. ✅ **test_auto_fix_join_edges_missing_join_edges_field** - Missing field handling
6. ✅ **test_auto_fix_join_edges_preserves_existing_selections** - Preservation of existing data
7. ✅ **test_auto_fix_join_edges_bidirectional_joins** - Deduplication of tables

### Integration Tests (`tests/unit/test_planner_auto_fix_integration.py`)

Created 3 integration tests with real Pydantic validation:

1. ✅ **test_auto_fix_prevents_validation_error** - Fixes invalid plans
2. ✅ **test_auto_fix_with_multiple_missing_tables** - Multi-table scenarios
3. ✅ **test_auto_fix_preserves_valid_plans** - Doesn't modify valid plans

### Test Results

```
tests/unit/test_planner_auto_fix.py::test_auto_fix_join_edges_adds_missing_tables PASSED
tests/unit/test_planner_auto_fix.py::test_auto_fix_join_edges_multiple_missing_tables PASSED
tests/unit/test_planner_auto_fix.py::test_auto_fix_join_edges_no_changes_needed PASSED
tests/unit/test_planner_auto_fix.py::test_auto_fix_join_edges_empty_join_edges PASSED
tests/unit/test_planner_auto_fix.py::test_auto_fix_join_edges_missing_join_edges_field PASSED
tests/unit/test_planner_auto_fix.py::test_auto_fix_join_edges_preserves_existing_selections PASSED
tests/unit/test_planner_auto_fix.py::test_auto_fix_join_edges_bidirectional_joins PASSED
=========================== 7 passed ===========================

tests/unit/test_planner_auto_fix_integration.py::test_auto_fix_prevents_validation_error PASSED
tests/unit/test_planner_auto_fix_integration.py::test_auto_fix_with_multiple_missing_tables PASSED
tests/unit/test_planner_auto_fix_integration.py::test_auto_fix_preserves_valid_plans PASSED
=========================== 3 passed ===========================
```

**Full Test Suite:** 317 tests passed (no existing tests broken)

---

## Expected Impact

Based on the benchmark error analysis:

| Metric | Before | After (Estimated) |
|--------|---------|-------------------|
| Success Rate | 77.5% | ~90% |
| Planner Validation Errors | 55% of logged errors | 0% |
| Total Error Reduction | - | ~12.5 percentage points |

### Affected Queries from Benchmark

This fix should resolve errors for:
- **gpt-5 / query_2** - Generated join to tb_Company without including it
- **llama3.1-8b / multiple queries** - Referenced tb_SaasScan in joins without selection
- Multiple instances across different models

---

## Logging and Observability

When auto-fix is applied, the system logs:

```json
{
  "level": "INFO",
  "message": "Auto-fixing join_edges: Adding missing tables to selections",
  "extra": {
    "missing_tables": ["tb_Company"],
    "selected_tables": ["tb_Users"],
    "join_tables": ["tb_Users", "tb_Company"]
  }
}
```

And on success:
```json
{
  "level": "INFO",
  "message": "Successfully applied auto-fix and validated planner output",
  "extra": {
    "retry_attempt": 1
  }
}
```

---

## Implementation Details

### Files Modified

1. **agent/planner.py**
   - Added `auto_fix_join_edges()` function (lines 26-77)
   - Modified planner retry loop to detect and apply auto-fix (lines 1142-1214)
   - Added import for `is_using_ollama` (line 14)

### Files Created

1. **tests/unit/test_planner_auto_fix.py** - Unit tests for auto-fix function
2. **tests/unit/test_planner_auto_fix_integration.py** - Integration tests with Pydantic

### Design Decisions

1. **Auto-added tables marked as join-only**: `include_only_for_join=True`
2. **Lower confidence for auto-added tables**: 0.7 instead of LLM's confidence
3. **Empty columns array**: Auto-added tables don't specify columns
4. **Transparent logging**: All auto-fix applications are logged for debugging
5. **Fallback to retry**: If auto-fix fails, normal retry logic continues

---

## Next Steps

### Validation

To validate this fix reduces errors:

1. **Re-run failed benchmark queries** with auto-fix enabled:
   - gpt-5 / query_2, query_3
   - llama3.1-8b / (queries with join_edges errors)
   - qwen models / (queries with join_edges errors)

2. **Full benchmark re-run** to measure overall success rate improvement

3. **Monitor production logs** for auto-fix application frequency

### Remaining Fixes from ERROR_ANALYSIS.md

- ~~Fix #2: Column name validation~~ (User noted this already exists)
- **Fix #3: Unquote date functions** (22% impact, Low effort)
- **Fix #4: Detect missing table references** (22% impact, Medium effort)

---

## Conclusion

Successfully implemented Fix #1 (auto-fix join_edges validation) with:
- ✅ 55% expected error reduction
- ✅ 10 new tests (all passing)
- ✅ No breaking changes to existing functionality
- ✅ Transparent logging and observability
- ✅ Minimal performance impact (one extra LLM call only when needed)

This fix addresses the most critical error pattern identified in the benchmark analysis and should significantly improve the overall success rate from 77.5% toward the target of 95%+.
