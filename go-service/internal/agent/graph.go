package agent

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"

	"github.com/sachit/sql-query-assistant/go-service/internal/agent/nodes"
	"github.com/sachit/sql-query-assistant/go-service/internal/db"
	"github.com/sachit/sql-query-assistant/go-service/internal/models"
	"github.com/sachit/sql-query-assistant/go-service/internal/schema"
)

// MaxErrorIterations and MaxRefinementIterations bound the two feedback loops.
// Match the Python defaults (RETRY_COUNT=3, REFINE_COUNT=3).
const (
	MaxErrorIterations      = 3
	MaxRefinementIterations = 3
)

// StatusUpdate is emitted at every node boundary so HTTP/SSE callers can
// stream progress. Keep the field set narrow — full state goes in the final
// response, not in every status event.
type StatusUpdate struct {
	Node    string         `json:"node"`
	Status  string         `json:"status"` // "running" | "completed" | "error"
	Message string         `json:"message,omitempty"`
	Meta    map[string]any `json:"meta,omitempty"`
}

// StatusFn is the orchestrator's callback for streaming. nil to disable.
type StatusFn func(StatusUpdate)

// RunQuery executes the full workflow against `state` until cleanup. The
// returned State is the final state regardless of success or failure; check
// state.LastStep, state.PlannerOutput.Decision, state.Errors to interpret.
//
// Routing rules (mirror agent/create_agent.py):
//   - planner.decision == "terminate" → cleanup
//   - SQL exec error + iteration < MAX → handle_error → planner
//   - empty result + iteration < MAX → refine_query → planner
//   - otherwise → cleanup
//
// We run each node in sequence and use plain branching instead of a state
// graph library — see POST_MVP.md for the rationale on skipping Eino.
func RunQuery(ctx context.Context, st *State, status StatusFn) *State {
	logger := slog.With("user_question", st.UserQuestion)
	emit := func(node, statusName, msg string, meta map[string]any) {
		if status != nil {
			status(StatusUpdate{Node: node, Status: statusName, Message: msg, Meta: meta})
		}
		logger.Info("node", "node", node, "status", statusName, "message", msg)
	}
	fail := func(node string, err error) *State {
		emit(node, "error", err.Error(), nil)
		st.Errors = append(st.Errors, fmt.Sprintf("%s: %s", node, err))
		st.LastStep = node
		cleanup(st)
		return st
	}
	// cancelledAt returns a finalized State if the request was cancelled.
	// We check this between nodes so a /cancel call stops the workflow within
	// one node boundary rather than waiting for the next LLM round-trip.
	cancelledAt := func(node string) *State {
		if ctx.Err() != nil {
			emit(node, "error", "cancelled", nil)
			st.Errors = append(st.Errors, "cancelled")
			st.LastStep = node
			st.TerminationReason = "cancelled by client"
			cleanup(st)
			return st
		}
		return nil
	}

	// initialize_connection
	emit("initialize_connection", "running", "opening database", nil)
	conn, err := db.Open(st.DBID)
	if err != nil {
		return fail("initialize_connection", err)
	}
	st.DBConn = conn
	emit("initialize_connection", "completed", "", nil)

	// analyze_schema
	emit("analyze_schema", "running", "introspecting schema", nil)
	tables, err := schema.IntrospectSQLite(ctx, conn)
	if err != nil {
		return fail("analyze_schema", err)
	}
	st.Schema = tables
	emit("analyze_schema", "completed", fmt.Sprintf("%d tables", len(tables)), nil)

	// filter_schema
	emit("filter_schema", "running", "selecting relevant tables", nil)
	fout, err := nodes.FilterSchema(ctx, nodes.FilterSchemaInput{
		Schema:       st.Schema,
		UserQuestion: st.UserQuestion,
	})
	if err != nil {
		return fail("filter_schema", err)
	}
	st.FilteredSchema = fout.FilteredSchema
	st.TruncatedSchema = fout.TruncatedSchema
	emit("filter_schema", "completed", fmt.Sprintf("%d tables selected", len(fout.SelectedTables)),
		map[string]any{"selected_tables": fout.SelectedTables})

	// infer_foreign_keys — optional node, only runs when INFER_FOREIGN_KEYS=true.
	// Augments the filtered schema with inferred FKs for production schemas
	// that lack explicit constraints.
	if nodes.InferForeignKeysEnabled() {
		emit("infer_foreign_keys", "running", "inferring FKs from naming patterns", nil)
		augmented, err := nodes.InferForeignKeys(ctx, st.FilteredSchema, st.Schema)
		if err != nil {
			// Non-fatal: log and continue with the original filtered schema.
			emit("infer_foreign_keys", "error", err.Error(), nil)
		} else {
			st.FilteredSchema = augmented
			emit("infer_foreign_keys", "completed", "", nil)
		}
	}

	// format_schema_markdown — prefer truncated for the planner, fall back
	// to filtered then full so prompts always have something to work with.
	schemaForPrompt := st.TruncatedSchema
	if len(schemaForPrompt) == 0 {
		schemaForPrompt = st.FilteredSchema
	}
	if len(schemaForPrompt) == 0 {
		schemaForPrompt = st.Schema
	}
	st.SchemaMarkdown = nodes.FormatSchemaMarkdown(schemaForPrompt)
	emit("format_schema_markdown", "completed", "", nil)
	if s := cancelledAt("format_schema_markdown"); s != nil {
		return s
	}

	// Planning loop — pre_planner → planner → audit → check_clarification.
	// On SQL execution error or empty result, generate feedback and loop back.
	for {
		if s := cancelledAt("pre_planner"); s != nil {
			return s
		}
		emit("pre_planner", "running", "creating strategy", nil)
		strategy, prePlanPrompt, err := nodes.PrePlanner(ctx, nodes.PrePlannerInput{
			UserQuestion:       st.UserQuestion,
			SchemaMarkdown:     st.SchemaMarkdown,
			SortOrder:          string(st.SortOrder),
			ResultLimit:        st.ResultLimit,
			TimeFilter:         string(st.TimeFilter),
			ErrorFeedback:      st.ErrorFeedback,
			RefinementFeedback: st.RefinementFeedback,
			PreviousStrategy:   st.PrePlanStrategy,
		})
		if err != nil {
			return fail("pre_planner", err)
		}
		st.PrePlanStrategy = strategy
		st.ErrorFeedback = ""
		st.RefinementFeedback = ""
		emit("pre_planner", "completed", "",
			withPrompt(map[string]any{"strategy_preview": preview(strategy, 500)}, prePlanPrompt))

		emit("planner", "running", "structuring plan", nil)
		plan, plannerPrompt, err := nodes.Planner(ctx, nodes.PlannerInput{
			UserQuestion:   st.UserQuestion,
			Strategy:       st.PrePlanStrategy,
			SchemaMarkdown: st.SchemaMarkdown,
		})
		if err != nil {
			return fail("planner", err)
		}
		st.PlannerOutput = plan
		emit("planner", "completed", string(plan.Decision),
			withPrompt(plannerMeta(plan), plannerPrompt))

		emit("plan_audit", "running", "validating plan", nil)
		audit := nodes.PlanAudit(plan, schemaToMaps(st.Schema))
		if len(audit.Issues) > 0 {
			emit("plan_audit", "completed", fmt.Sprintf("%d issues (non-blocking)", len(audit.Issues)),
				map[string]any{"issues": audit.Issues})
		} else {
			emit("plan_audit", "completed", "no issues", nil)
		}

		// check_clarification
		decision := nodes.CheckClarification(plan)
		if decision == nodes.DecideTerminate {
			st.TerminationReason = plan.TerminationReason
			emit("check_clarification", "completed", "terminate", nil)
			cleanup(st)
			return st
		}
		if decision == nodes.DecideClarify {
			st.NeedsClarification = true
			st.ClarificationSuggestions = plan.Ambiguities
		}
		emit("check_clarification", "completed", string(plan.Decision), nil)

		if s := cancelledAt("generate_query"); s != nil {
			return s
		}
		// generate_query
		emit("generate_query", "running", "emitting SQL", nil)
		query, err := nodes.GenerateQuery(plan, sqliteDialectIfTestDB(st))
		if err != nil {
			return fail("generate_query", err)
		}
		st.Query = query
		emit("generate_query", "completed", "", map[string]any{"query": query})

		// execute_query
		emit("execute_query", "running", "running SQL", nil)
		rows, execErr := nodes.ExecuteQuery(ctx, st.DBConn, st.Query)

		if execErr != nil {
			st.Errors = append(st.Errors, execErr.Error())
			emit("execute_query", "error", execErr.Error(), nil)
			if st.ErrorIteration >= MaxErrorIterations {
				st.LastStep = "execute_query"
				st.TerminationReason = "max error iterations exhausted"
				cleanup(st)
				return st
			}
			st.ErrorIteration++
			emit("handle_error", "running", "generating correction feedback", nil)
			feedback, hePrompt, err := nodes.HandleError(ctx, nodes.HandleErrorInput{
				UserQuestion:   st.UserQuestion,
				Strategy:       st.PrePlanStrategy,
				Query:          st.Query,
				ErrorMessage:   execErr.Error(),
				SchemaMarkdown: st.SchemaMarkdown,
			})
			if err != nil {
				return fail("handle_error", err)
			}
			st.ErrorFeedback = feedback
			st.CorrectionHistory = append(st.CorrectionHistory, feedback)
			emit("handle_error", "completed", "", withPrompt(map[string]any{
				"iteration":      st.ErrorIteration,
				"max_iterations": MaxErrorIterations,
				"error_preview":  preview(execErr.Error(), 200),
			}, hePrompt))
			continue // loop back to pre_planner
		}

		st.Result = rows
		st.TotalRecordsAvailable = len(rows)
		emit("execute_query", "completed", fmt.Sprintf("%d rows", len(rows)), nil)
		if s := cancelledAt("execute_query"); s != nil {
			return s
		}

		// generate_data_summary — pure deterministic stats per column.
		// Runs even on empty results so the frontend always gets a shape.
		emit("generate_data_summary", "running", "computing column stats", nil)
		st.DataSummary = nodes.ComputeDataSummary(st.Result, &st.TotalRecordsAvailable)
		emit("generate_data_summary", "completed", fmt.Sprintf("%d cols", st.DataSummary.ColumnCount), nil)

		// generate_modification_options — UI options for plan patching.
		// Pure deterministic; reads PlannerOutput + filtered schema.
		emit("generate_modification_options", "running", "building UI options", nil)
		st.ModificationOptions = nodes.GenerateModificationOptions(st.PlannerOutput, st.FilteredSchema)
		emit("generate_modification_options", "completed",
			fmt.Sprintf("%d tables", len(st.ModificationOptions.Tables)), nil)

		// generate_query_narrative — only when chat is active. Avoids paying
		// for an LLM call we'd never use and matches Python's gating.
		if st.ChatSessionID != "" && len(st.Result) > 0 {
			emit("generate_query_narrative", "running", "writing AI summary", nil)
			narrative, narrPrompt, err := nodes.GenerateQueryNarrative(ctx, nodes.NarrativeInput{
				UserQuestion: st.UserQuestion,
				Query:        st.Query,
				Result:       st.Result,
				DataSummary:  st.DataSummary,
			})
			if err != nil {
				// Narrative is optional — log and continue rather than fail the whole query.
				st.Errors = append(st.Errors, "generate_query_narrative: "+err.Error())
				emit("generate_query_narrative", "error", err.Error(), nil)
			} else {
				st.QueryNarrative = narrative
				emit("generate_query_narrative", "completed", "",
					withPrompt(map[string]any{"narrative_preview": preview(narrative, 300)}, narrPrompt))
			}
		}

		if len(rows) == 0 {
			if st.RefinementIteration >= MaxRefinementIterations {
				st.LastStep = "execute_query"
				st.TerminationReason = "max refinement iterations exhausted (still no rows)"
				cleanup(st)
				return st
			}
			st.RefinementIteration++
			emit("refine_query", "running", "generating refinement feedback", nil)
			feedback, refPrompt, err := nodes.RefineQuery(ctx, nodes.RefineQueryInput{
				UserQuestion:   st.UserQuestion,
				Strategy:       st.PrePlanStrategy,
				Query:          st.Query,
				SchemaMarkdown: st.SchemaMarkdown,
			})
			if err != nil {
				return fail("refine_query", err)
			}
			st.RefinementFeedback = feedback
			st.RefinementHistory = append(st.RefinementHistory, feedback)
			emit("refine_query", "completed", "", withPrompt(map[string]any{
				"iteration":      st.RefinementIteration,
				"max_iterations": MaxRefinementIterations,
			}, refPrompt))
			continue // loop back to pre_planner
		}

		// Success path
		st.LastStep = "execute_query"
		cleanup(st)
		return st
	}
}

// RunPatch is the patch-flow analogue of RunQuery. Skips the planner LLM
// calls because the caller already has an executed plan; just transforms the
// plan, regenerates SQL, executes it, and produces the same Phase-9 outputs
// (data summary, modification options) as the main path.
//
// Mirrors the post-execute portion of agent/create_agent.py's transform_plan
// edge → generate_query → execute_query → … → cleanup.
func RunPatch(ctx context.Context, st *State, patched *models.PlannerOutput, status StatusFn) *State {
	logger := slog.With("user_question", st.UserQuestion, "flow", "patch")
	emit := func(node, statusName, msg string, meta map[string]any) {
		if status != nil {
			status(StatusUpdate{Node: node, Status: statusName, Message: msg, Meta: meta})
		}
		logger.Info("node", "node", node, "status", statusName, "message", msg)
	}
	fail := func(node string, err error) *State {
		emit(node, "error", err.Error(), nil)
		st.Errors = append(st.Errors, fmt.Sprintf("%s: %s", node, err))
		st.LastStep = node
		cleanup(st)
		return st
	}

	st.PlannerOutput = patched
	emit("transform_plan", "completed", "patch applied", nil)

	// Open DB connection (the request didn't go through the planning loop).
	emit("initialize_connection", "running", "opening database", nil)
	conn, err := db.Open(st.DBID)
	if err != nil {
		return fail("initialize_connection", err)
	}
	st.DBConn = conn
	emit("initialize_connection", "completed", "", nil)

	emit("generate_query", "running", "emitting SQL", nil)
	query, err := nodes.GenerateQuery(patched, sqliteDialectIfTestDB(st))
	if err != nil {
		return fail("generate_query", err)
	}
	st.Query = query
	emit("generate_query", "completed", "", map[string]any{"query": query})

	emit("execute_query", "running", "running SQL", nil)
	rows, execErr := nodes.ExecuteQuery(ctx, st.DBConn, st.Query)
	if execErr != nil {
		return fail("execute_query", execErr)
	}
	st.Result = rows
	st.TotalRecordsAvailable = len(rows)
	emit("execute_query", "completed", fmt.Sprintf("%d rows", len(rows)), nil)

	st.DataSummary = nodes.ComputeDataSummary(st.Result, &st.TotalRecordsAvailable)
	emit("generate_data_summary", "completed",
		fmt.Sprintf("%d cols", st.DataSummary.ColumnCount), nil)

	st.ModificationOptions = nodes.GenerateModificationOptions(st.PlannerOutput, st.FilteredSchema)
	emit("generate_modification_options", "completed",
		fmt.Sprintf("%d tables", len(st.ModificationOptions.Tables)), nil)

	st.LastStep = "execute_query"
	cleanup(st)
	return st
}

// cleanup closes the DB connection and stamps the final step. Idempotent.
func cleanup(st *State) {
	if st.DBConn != nil {
		_ = st.DBConn.Close()
		st.DBConn = nil
	}
	if st.LastStep == "" {
		st.LastStep = "cleanup"
	}
}

// sqliteDialectIfTestDB inspects DBID — when targeting demo SQLite DBs we want
// the SQLite-flavored output (LIMIT n, no TOP). SQL Server uses default tsql.
func sqliteDialectIfTestDB(st *State) string {
	if st.DBID != "" {
		return "sqlite"
	}
	return ""
}

// schemaToMaps converts the strongly-typed schema slice into the loose map
// shape PlanAudit expects. Round-tripping through JSON keeps both code paths
// honest about the wire format.
func schemaToMaps(tables []schema.Table) []map[string]any {
	raw, err := json.Marshal(tables)
	if err != nil {
		return nil
	}
	var out []map[string]any
	if err := json.Unmarshal(raw, &out); err != nil {
		return nil
	}
	return out
}

// withPrompt attaches a prompt context to an existing metadata map under the
// `prompt_context` key the frontend's PromptViewer reads. Returns the meta
// map so the call sits inline with emit(...) without needing a temp variable.
// nil prompt is a no-op.
func withPrompt(meta map[string]any, p *nodes.PromptContext) map[string]any {
	if p == nil {
		return meta
	}
	if meta == nil {
		meta = map[string]any{}
	}
	meta["prompt_context"] = p
	return meta
}

// preview truncates a string at a reasonable boundary for log/UI previews.
func preview(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max] + "…"
}

// plannerMeta extracts the rendered shape the WorkflowProgress planner
// metadata renderer expects (table_count, join_count, filter_count, etc.).
func plannerMeta(p *models.PlannerOutput) map[string]any {
	if p == nil {
		return nil
	}
	tables := make([]string, 0, len(p.Selections))
	filterCount := 0
	for _, s := range p.Selections {
		tables = append(tables, s.Table)
		filterCount += len(s.Filters)
	}
	filterCount += len(p.GlobalFilters)
	hasAggregation := p.GroupBy != nil
	hasOrderBy := len(p.OrderBy) > 0
	out := map[string]any{
		"intent_summary":  p.IntentSummary,
		"table_count":     len(p.Selections),
		"join_count":      len(p.JoinEdges),
		"filter_count":    filterCount,
		"has_aggregation": hasAggregation,
		"has_order_by":    hasOrderBy,
		"tables":          tables,
	}
	if p.Limit != nil {
		out["limit"] = *p.Limit
	}
	return out
}
