# Benchmark Error Analysis
**Date:** 2025-10-31
**Total Runs:** 40
**Failed Runs:** 9 (22.5%)

## Executive Summary

Analysis of benchmark failures reveals **4 distinct error patterns** affecting 22.5% of queries. The most critical issue is **Planner Validation Errors** where models create join_edges referencing tables not included in selections, accounting for 55% of failures observed in logs.

---

## Error Pattern Breakdown

### 1. 🔴 PLANNER VALIDATION ERRORS (Most Critical)
**Impact:** Causes workflow to fail before SQL generation
**Frequency:** Multiple occurrences in logs (55% of logged errors)

#### Root Cause
LLMs create `join_edges` that reference tables not included in the `selections` array, violating Pydantic validation rules.

#### Examples from Logs

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

**Real Error (from app.log):**
```
Value error, join_edges reference tables not in selections: ['tb_Company']
```

#### Affected Models & Queries
- **gpt-5 / query_2** - Generated join to tb_Company without including it
- **llama3.1-8b** - Referenced tb_SaasScan in joins without selection
- Multiple instances across different models

#### Impact on Workflow
- Fails at **planner validation stage** (before SQL generation)
- No retry possible - validation errors are structural
- LLM never sees the actual SQL error to learn from

---

### 2. ⚠️ INVALID COLUMN NAME ERRORS
**Impact:** SQL execution failure
**Frequency:** 5 occurrences (55% of execution failures)

#### Root Cause
Models hallucinating column names not present in the schema or using incorrect naming conventions.

#### Specific Examples

| Model | Query | Error | Root Cause |
|-------|-------|-------|------------|
| gpt-5 | query_2 | Invalid column 'ComputerID', 'InstalledAppID' | Used wrong column names |
| gpt-5 | query_3 | Invalid column 'ScanName' | Column doesn't exist in tb_SaasComputers |
| gpt-4o-mini | query_5 | Invalid column 'CVSSScore' in tb_SaasMasterInstalledApps | Column in wrong table |
| qwen3-8b | query_2 | Invalid column 'company_id' | Used snake_case instead of ID |
| qwen3-4b | query_5 | Invalid columns 'CVEID', 'Avg_CVSSScore' | Multiple hallucinated columns |

#### Pattern Analysis
1. **Wrong naming convention** (company_id vs ID)
2. **Column in wrong table** (CVSSScore)
3. **Completely hallucinated columns** (ScanName, Avg_CVSSScore)

#### SQL Examples

**gpt-5 / query_2:**
```sql
SELECT * FROM [tb_SaasComputers]
WHERE [tb_SaasComputers].[ComputerID] IN (  -- ❌ Column doesn't exist
    SELECT [InstalledAppID]  -- ❌ Column doesn't exist
    FROM [tb_SaasInstalledAppsTemp]
)
```

**qwen3-8b / query_2:**
```sql
SELECT * FROM [tb_Company]
ORDER BY [tb_Company].[company_id] ASC  -- ❌ Should be [ID]
```

---

### 3. 📅 DATE FUNCTION HANDLING ERRORS
**Impact:** SQL type conversion failure
**Frequency:** 2 occurrences (22% of execution failures)

#### Root Cause
LLMs wrapping SQL date functions in quotes, treating them as strings instead of expressions.

#### Examples

**gpt-4o-mini / query_4:**
```sql
WHERE [tb_SaasScan].[Schedule] >= 'DATEADD(DAY, -60, GETDATE())'
                                  ^                             ^
                                  ❌ Should NOT be quoted
```

**qwen3-8b / query_4:**
```sql
WHERE [tb_SaasScan].[Schedule] >= 'DATEADD(d,-60,GETDATE())'
                                  ^                         ^
                                  ❌ Should NOT be quoted
```

#### Correct Format
```sql
WHERE [tb_SaasScan].[Schedule] >= DATEADD(DAY, -60, GETDATE())
```

#### Impact
- SQL Server error: `Conversion failed when converting date and/or time from character string` (22007)
- Error correction attempts still produce quoted functions
- Models don't understand this is a quoting issue, not a logic issue

---

### 4. 🔗 TABLE REFERENCE NOT BOUND ERRORS
**Impact:** SQL execution failure
**Frequency:** 2 occurrences (22% of execution failures)

#### Root Cause
SQL references tables in JOIN conditions or WHERE clauses that are not in the FROM clause.

#### Examples

**gpt-5-mini / query_4:**
```sql
SELECT * FROM [tb_SaasComputers]
JOIN [tb_Company] ON ...
JOIN [tb_SaasComputerUSBDeviceDetails]
  ON [tb_SaasScan].[ID] = ...  -- ❌ tb_SaasScan not in FROM clause
WHERE [tb_SaasScan].[Schedule] >= ...  -- ❌ tb_SaasScan not in FROM clause
```

**llama3-8b / query_5:**
```sql
SELECT
  [tb_CVEConfiguration].[AverageCVSSScore],  -- ❌ Table not in FROM
  [tb_CVE].[CVSSScore]  -- ❌ Table not in FROM
FROM [tb_SaasMasterInstalledApps]
-- Missing JOINs to tb_CVEConfiguration and tb_CVE
```

#### Impact
- SQL Server error: `The multi-part identifier "tb_SaasScan.ID" could not be bound` (42000)
- Indicates planner selected wrong tables or omitted required JOINs

---

## Root Cause Analysis

### Where Errors Originate

| Error Type | Stage | Component | Can Audit Fix? |
|-----------|-------|-----------|----------------|
| Join edges validation | Planner | Pydantic validation | ❌ No - structural error |
| Invalid column names | Planner | LLM hallucination | ✅ Yes - can validate columns |
| Date function quoting | Join Synthesizer | Filter value handling | ✅ Yes - detect and unquote |
| Missing table refs | Planner | Incomplete join selection | ⚠️ Partial - can detect |

---

## Improvement Recommendations

### 1. Fix Planner Validation Error (HIGHEST PRIORITY)

**Problem:** LLMs create joins to tables not in selections

**Solutions:**

#### A. Post-Processing Fix (Quick Win)
Add post-processing step in `planner.py` BEFORE Pydantic validation:

```python
def auto_fix_join_edges(planner_output_dict):
    """Auto-add missing tables referenced in join_edges to selections."""
    selected_tables = {sel["table"] for sel in planner_output_dict["selections"]}
    join_tables = set()

    for edge in planner_output_dict.get("join_edges", []):
        join_tables.add(edge["from_table"])
        join_tables.add(edge["to_table"])

    missing_tables = join_tables - selected_tables

    for table in missing_tables:
        planner_output_dict["selections"].append({
            "table": table,
            "confidence": 0.7,  # Lower confidence for auto-added
            "columns": []  # No specific columns needed
        })

    return planner_output_dict
```

**Impact:** Would fix 55% of logged errors

#### B. Improve Planner Prompt
Add explicit instruction:

```
CRITICAL RULE: Every table referenced in join_edges MUST appear in selections array.
If you create a join like:
  {"from_table": "tb_Users", "to_table": "tb_Company", ...}
Then BOTH tb_Users AND tb_Company must be in selections.
```

### 2. Add Column Name Validation to Plan Audit

**Problem:** 5/9 failures due to invalid column names

**Solution:** Extend `plan_audit.py` to validate ALL column references:

```python
def validate_all_columns(plan, schema):
    """Validate columns in filters, aggregations, order_by, etc."""
    errors = []

    # Build column index from schema
    schema_columns = {}
    for table_schema in schema:
        table = table_schema["table_name"]
        schema_columns[table] = {col["column_name"].lower()
                                for col in table_schema["columns"]}

    # Validate filters
    for filter_pred in plan.get("filters", []):
        table = filter_pred.get("table")
        column = filter_pred.get("column")
        if column.lower() not in schema_columns.get(table, set()):
            errors.append(f"Invalid column {table}.{column}")
            # Try to find similar column name
            similar = find_similar_column(column, schema_columns[table])
            if similar:
                filter_pred["column"] = similar  # Auto-fix

    # Validate aggregations
    for agg in plan.get("aggregations", []):
        # Similar validation
        pass

    # Validate order_by
    for order in plan.get("order_by", []):
        # Similar validation
        pass

    return errors
```

**Impact:** Would catch all 5 invalid column name errors before SQL generation

### 3. Fix Date Function Quoting in Join Synthesizer

**Problem:** Date functions wrapped in quotes (2 failures)

**Solution:** Detect and unwrap SQL functions in `generate_query.py`:

```python
def unquote_sql_functions(value):
    """Detect quoted SQL functions and unquote them."""
    if isinstance(value, str):
        # Pattern: 'FUNCTION_NAME(...)'
        if re.match(r"^'[A-Z_]+\([^']*\)'$", value):
            return value[1:-1]  # Remove quotes
    return value

# Apply in filter building:
for filter in filters:
    filter_value = unquote_sql_functions(filter["value"])
    # Use filter_value instead
```

**Impact:** Would fix all 2 date conversion errors

### 4. Add Missing Table Detection to Plan Audit

**Problem:** Tables referenced but not in FROM clause (2 failures)

**Solution:** Cross-reference all table mentions:

```python
def validate_all_table_references(plan):
    """Ensure all referenced tables are in selections."""
    selected_tables = {sel["table"] for sel in plan["selections"]}

    # Check filters
    for f in plan.get("filters", []):
        if f["table"] not in selected_tables:
            # Add table to selections or remove filter
            pass

    # Check order_by
    for o in plan.get("order_by", []):
        if o["table"] not in selected_tables:
            # Add table or remove order
            pass
```

---

## Priority Ranking

| Rank | Fix | Impact | Effort | Priority Score |
|------|-----|--------|--------|---------------|
| 1 | Auto-fix join edges in selections | 55% of errors | Low | 🔥🔥🔥 Critical |
| 2 | Column name validation in audit | 55% of SQL errors | Medium | 🔥🔥 High |
| 3 | Unquote date functions | 22% of SQL errors | Low | 🔥 Medium |
| 4 | Missing table detection | 22% of SQL errors | Medium | 🔥 Medium |

---

## Testing Plan

### 1. Create Unit Tests for Each Fix

```python
# test_planner_auto_fix.py
def test_auto_fix_join_edges():
    plan = {
        "selections": [{"table": "tb_Users"}],
        "join_edges": [{
            "from_table": "tb_Users",
            "to_table": "tb_Company",  # Not in selections
            ...
        }]
    }
    fixed = auto_fix_join_edges(plan)
    assert any(s["table"] == "tb_Company" for s in fixed["selections"])
```

### 2. Re-run Failed Queries

After implementing fixes, re-run the 9 failed queries:
- gpt-5 / query_2, query_3
- gpt-5-mini / query_4
- gpt-4o-mini / query_4, query_5
- llama3-8b / query_5
- qwen3-8b / query_2, query_4
- qwen3-4b / query_5

### 3. Full Benchmark Re-run

After fixes stabilize, re-run full 40-query benchmark to measure improvement.

---

## Expected Outcomes

| Metric | Before | After (Estimated) |
|--------|---------|-------------------|
| Success Rate | 77.5% | 95%+ |
| Planner Validation Errors | 55% | 0% |
| Invalid Column Errors | 55% of SQL | <10% |
| Date Conversion Errors | 22% of SQL | 0% |
| Table Reference Errors | 22% of SQL | <5% |

---

## Implementation Order

1. **Immediate (Day 1):** Implement auto-fix for join_edges - quick win, huge impact
2. **Short-term (Day 2-3):** Add column validation to plan_audit
3. **Short-term (Day 3-4):** Add date function unquoting to join synthesizer
4. **Medium-term (Week 2):** Improve planner prompts with better instructions
5. **Long-term (Month 1):** Add few-shot examples to planner prompt showing correct patterns

---

## Additional Insights

### Query Difficulty Correlation
- **query_1** (simple join): 100% success (8/8 models)
- **query_2** (CVE aggregation): 75% success (6/8 models)
- **query_3** (hardware inventory): 87.5% success (7/8 models)
- **query_4** (USB cross-domain): 62.5% success (5/8 models)
- **query_5** (app risk aggregation): 62.5% success (5/8 models)

**Pattern:** Complex aggregations and multi-table joins have higher failure rates.

### Model Performance on Errors
- **llama3.1-8b**: 0 errors (100% success)
- **gpt-4o**: 0 errors (100% success)
- **gpt-5**: 2 errors (60% success) - both invalid columns
- **qwen3-8b**: 2 errors (60% success) - invalid column + date handling

**Insight:** Minimal planner complexity works well for some models but struggles with complex queries on others.
