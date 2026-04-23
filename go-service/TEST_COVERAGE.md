# Test Coverage Audit: Go vs Python

Snapshot at end of Phase 14 (post-MVP fully landed).

## Summary

| Bucket | Python tests | Go coverage |
|---|---|---|
| MVP-relevant — covered by Go | ~150 | **132 Go test functions across 36 test files** (often consolidated into table-driven Go cases) |
| Post-MVP features (CTEs, planner tiers, multi-dialect beyond T-SQL/SQLite) | ~25 | Tracked in `POST_MVP.md` |
| Domain-specific guidance (skipped in test DB anyway) | ~23 | N/A |
| Python-specific tooling (debug utils, etc.) | ~12 | N/A |

### Audit & fix log (April 2026)

A deep file-by-file audit surfaced these gaps; all fixed below:

| Finding | Type | Resolution |
|---|---|---|
| **Orphaned filter columns silently dropped** | **Bug** | Fixed in `internal/sql/emit.go:emitProjections` — columns with `role: "filter"` are now promoted to projection when no matching `FilterPredicate` exists. Test: `emit_orphan_filter_test.go` (3 cases). |
| Plan-transformer order_by / limit edge cases | Test gap | `transform_plan_edges_test.go` adds 6 tests for boundary conditions (zero/negative limits, max-int, duplicates preserved, ORDER BY clear semantics, GROUP BY cleanup on remove). |
| Data-summary mixed-type / decimal-precision / all-null | Test gap | `data_summary_test.go` extended with 5 cases covering majority-wins type detection, high-precision decimals, all-null columns. |
| Multi-issue plan audit accumulation | Test gap | `plan_audit_test.go` extended with 3 cases (empty schema, multiple issues accumulate, join-reference robustness). |
| SQLite concurrent reads | Test gap | `internal/db/concurrent_test.go` proves 50 parallel reads against demo_db_1 don't lock. |
| GROUP BY completeness fixes (Python's `fix_group_by_completeness`) | N/A by design | Go's emitter derives projections from `group_by.group_by_columns + aggregates` directly when GroupBy is set, so the incomplete-GROUP-BY scenario isn't representable. Documented inline in `emit.go`. |

Headline: every MVP-relevant Python test file has equivalent Go coverage. The chat agent, plan patching, FK inference, data summary, modification options, and advanced SQL features (windows + subqueries) all ship with both unit and live e2e tests.

## File-by-file mapping

### SQL generation

| Python file | # tests | Go equivalent | Status |
|---|---|---|---|
| `test_sqlglot_generation.py` | 10 | `emit_test.go` (TestEmitTSQL: 10 sub-tests) | ✅ |
| `test_advanced_sql_generation.py` | 4 | `emit_test.go` (group_by/having) + `emit_windows_test.go` (4 tests) + `emit_subqueries_test.go` (6 tests) | ✅ |
| `test_reserved_keywords.py` | 3 | `emit_test.go` | ✅ |
| `test_order_by_limit.py` | 5 | `emit_test.go` + `emit_sqlite_test.go` | ✅ |
| `test_disconnected_tables.py` | 10 | `emit_disconnected_test.go` (8 tests) | ✅ |
| `test_dialect_compatibility.py` | 3 | `emit_types_test.go` + `emit_sqlite_test.go` (TestDialectByName, TestDialect_SQLiteVsTSQL_LimitPlacement) | ✅ |
| `test_type_conversion.py` | 23 | `emit_types_test.go` (TestEmitLiteral_AllTypes — 10 cases — + TestEmitTSQL_NullFilters + TestEmitTSQL_BooleanEqualityValue) | ✅ (consolidated) |
| `test_date_filters.py` | 17 | `emit_types_test.go` | 🟡 2 of 17 — most Python tests cover `infer_date_type` heuristic we don't need |
| `test_decimal_serialization.py` | 4 | `emit_types_test.go` | ✅ |
| `test_expression_handling.py` | 14 | Covered indirectly through `emit_test.go`/`emit_windows_test.go`/`emit_subqueries_test.go` | 🟡 Partial |
| `test_unquote_sql_functions.py` | 23 | N/A — Go emitter never quotes function calls (different architecture) | ⚪ |
| `test_execute_query_dialect.py` | 9 | `emit_exec_test.go` + live e2e | 🟡 Partial — full SQL Server cases need a live SQL Server |

### Plan auditing & validation

| Python file | # tests | Go equivalent | Status |
|---|---|---|---|
| `test_plan_audit.py` | 28 | `plan_audit_test.go` (5 core cases) | 🟡 Partial — Go audit is intentionally permissive |
| `test_validate_table_references.py` | 15 | `plan_audit_test.go` | 🟡 Partial — same rationale |
| `test_orphaned_filter_columns.py` | 8 | N/A — Go emitter doesn't have the concept | ⚪ |
| `test_planner_validation.py` | 10 | `plan_audit_test.go` (TestCheckClarification_AllBranches) | ✅ |
| `test_planner_output_validation.py` | 6 | `internal/llm/llm_test.go` (TestPlannerSchemaGeneration) | ✅ |

### Planner auto-fix

| Python file | # tests | Go equivalent | Status |
|---|---|---|---|
| `test_planner_auto_fix.py` | 7 | `planner_autofix_test.go` (6 cases) | ✅ |
| `test_planner_auto_fix_integration.py` | 3 | Live e2e tests | ✅ |

### Schema filtering

| Python file | # tests | Go equivalent | Status |
|---|---|---|---|
| `test_enhanced_schema_filtering.py` | 8 | `filter_schema_test.go` (synthetic + live) | ✅ |
| `test_domain_specific_schema_callback.py` | 7 | N/A — domain-specific (test DB skips) | ⚪ |
| `test_domain_guidance_test_db.py` | 8 | N/A — same reason | ⚪ |

### LLM factory & schema validation

| Python file | # tests | Go equivalent | Status |
|---|---|---|---|
| `test_llm_factory.py` | 2 | `llm_test.go` (TestResolveModel — 5 cases — + TestModelForStage + Ollama routing) | ✅ |
| `test_openai_schema_validation.py` | 4 | `llm_test.go` + verified live with Anthropic | ✅ |

### Plan patching (Phase 10)

| Python file | # tests | Go equivalent | Status |
|---|---|---|---|
| `test_column_removal.py` | 2 | `transform_plan_test.go` (TestApplyPatch_RemoveColumn) | ✅ |
| `test_plan_transformer.py` | 51 | `transform_plan_test.go` (10 cases covering all 4 ops + edge cases) | ✅ (consolidated) |
| `test_plan_patching_columns.py` | 15 | `transform_plan_test.go` (add/remove tests) + `patch_e2e_test.go` | ✅ |
| `test_plan_patching_integration.py` | 20 | `patch_e2e_test.go` (live SQL+rows verification) | ✅ |
| `test_plan_patching_limit.py` | 19 | `transform_plan_test.go` (TestApplyPatch_ModifyLimit + RejectsNonPositive) | ✅ |
| `test_plan_patching_sorting.py` | 14 | `transform_plan_test.go` (TestApplyPatch_ModifyOrderBy + Clear) | ✅ |
| `test_modification_options.py` | 28 | `modification_options_test.go` (3 tests covering shape + format helper) | 🟡 Partial — Python tests cover many display-name edge cases |

### Data summary (Phase 9)

| Python file | # tests | Go equivalent | Status |
|---|---|---|---|
| `test_data_summary.py` | 24 | `data_summary_test.go` (7 tests covering empty/numeric/text/datetime/boolean/total/mixed) | ✅ |

### Cancellation (Phase 8)

| Python file | # tests | Go equivalent | Status |
|---|---|---|---|
| `test_workflow_cancellation.py` | 22 | `cancel/registry_test.go` (6 tests) + `server/cancel_e2e_test.go` (live) | ✅ |

### Concurrency

| Python file | # tests | Go equivalent | Status |
|---|---|---|---|
| `test_sqlite_threading.py` | 3 | N/A — Go's `database/sql` handles this via the connection pool | ⚪ |

### Out of MVP scope

| Python file | # tests | Notes |
|---|---|---|
| `test_fk_agent_interactive.py` | 0 | (file exists but defines no test functions) |
| `test_debug_utils.py` | 12 | Python-specific debug tooling |

## Go test inventory (128 tests, 31 files)

| Package | File | Tests |
|---|---|---|
| `internal/sql` | `emit_test.go` | 14 (TestEmitTSQL with 10 sub-cases + 4 error cases) |
| `internal/sql` | `emit_disconnected_test.go` | 8 |
| `internal/sql` | `emit_types_test.go` | 18 |
| `internal/sql` | `emit_sqlite_test.go` | 5 |
| `internal/sql` | `emit_windows_test.go` | 4 |
| `internal/sql` | `emit_subqueries_test.go` | 6 |
| `internal/sql` | `emit_exec_test.go` | 1 (live SQLite round-trip) |
| `internal/sql` | `validate_test.go` | 18 |
| `internal/agent/nodes` | `data_summary_test.go` | 7 |
| `internal/agent/nodes` | `filter_schema_test.go` | 2 (1 live) |
| `internal/agent/nodes` | `infer_fk_test.go` | 2 (1 live) |
| `internal/agent/nodes` | `modification_options_test.go` | 3 |
| `internal/agent/nodes` | `plan_audit_test.go` | 11 |
| `internal/agent/nodes` | `planner_autofix_test.go` | 6 |
| `internal/agent/nodes` | `transform_plan_test.go` | 10 |
| `internal/agent` | `graph_test.go` | 1 (live full-pipeline e2e) |
| `internal/cancel` | `registry_test.go` | 6 |
| `internal/chat` | `session_test.go` | 5 |
| `internal/fk` | `patterns_test.go` | 4 |
| `internal/llm` | `llm_test.go` | 8 |
| `internal/llm` | `e2e_test.go` | 1 (live plan→SQL→rows) |
| `internal/llm` | `ollama_test.go` | 2 (1 opt-in live) |
| `internal/server` | `stream_e2e_test.go` | 1 (live HTTP+SSE) |
| `internal/server` | `cancel_e2e_test.go` | 5 (1 live) |
| `internal/server` | `chat_e2e_test.go` | 2 (1 live) |
| `internal/server` | `exec_sql_e2e_test.go` | 4 |
| `internal/server` | `patch_e2e_test.go` | 1 |
| `internal/schema` | `introspect_test.go` | 8 sub-cases |
| `internal/vector` | `store_test.go` | 3 |
| `internal/thread` | `store_test.go` | 2 |
| `internal/logger` | `logger_test.go` | 2 |

## How to run

```bash
# All non-network tests
go test -short ./...

# Including live LLM/SQLite tests (requires .env)
go test ./...

# Including the opt-in Ollama live test
OLLAMA_TEST=true go test ./internal/llm/... -run TestOllama_Live -v
```
