package nodes

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/sachit/sql-query-assistant/go-service/internal/llm"
	"github.com/sachit/sql-query-assistant/go-service/internal/models"
)

// PrePlannerInput is what the strategy node reads. The orchestrator builds
// it from State so individual nodes stay testable in isolation.
type PrePlannerInput struct {
	UserQuestion       string
	SchemaMarkdown     string
	SortOrder          string
	ResultLimit        int
	TimeFilter         string
	ErrorFeedback      string
	RefinementFeedback string
	PreviousStrategy   string
}

// PrePlanner generates a text-based query strategy. Replaces agent/pre_planner.py.
// We keep the prompt deliberately short — Claude Sonnet 4.6 doesn't need 200
// lines of guardrails for the MVP. Domain-specific tier prompts (`minimal`,
// `standard`, `full`) are deferred to post-MVP.
//
// Returns (strategy, promptContext, error). The PromptContext captures the
// exact system+user messages sent to the LLM so the orchestrator can surface
// them in the SSE status events for the frontend's PromptViewer.
func PrePlanner(ctx context.Context, in PrePlannerInput) (string, *PromptContext, error) {
	client, err := llm.NewForStage(llm.StageStrategy)
	if err != nil {
		return "", nil, err
	}

	var paramLines []string
	if in.SortOrder != "" && in.SortOrder != "Default" {
		paramLines = append(paramLines, "- Sort order: "+in.SortOrder)
	}
	if in.ResultLimit > 0 {
		paramLines = append(paramLines, fmt.Sprintf("- Result limit: %d", in.ResultLimit))
	}
	if in.TimeFilter != "" && in.TimeFilter != "All Time" {
		paramLines = append(paramLines, "- Time filter: "+in.TimeFilter)
	}
	params := strings.Join(paramLines, "\n")
	if params == "" {
		params = "(none)"
	}

	system := fmt.Sprintf(`# Pre-Planning Assistant (Strategy Phase)

You are the first stage of a two-stage SQL query planner. Your job is to read the
database schema and the user's natural-language question, then write a clear
text-based strategy for answering it. The next stage converts your strategy to
structured JSON; the stage after that emits SQL.

Today's date: %s

## Rules

- Use ONLY the exact table and column names from the schema. Do not invent names.
- Identify which tables are needed and how they join.
- Identify projection columns (displayed) vs filter columns (used in WHERE).
- For "last N" / "top N" queries, use ORDER BY + LIMIT — not date filters.
- For relative dates ("last 30 days") compute concrete dates from today's date.
- Keep your plan concise — one paragraph per section.
- Do NOT write SQL. Write plain text only.

## Output sections (use exactly these headings)

### Tables
### Columns
### Joins
### Filters
### Aggregations / Ordering / Limit
### Decision
(one of: proceed, clarify, terminate)`, time.Now().Format("2006-01-02"))

	var userMsg strings.Builder
	if in.SchemaMarkdown != "" {
		userMsg.WriteString(in.SchemaMarkdown)
		userMsg.WriteString("\n\n")
	}
	fmt.Fprintf(&userMsg, "## Parameters\n%s\n\n", params)
	fmt.Fprintf(&userMsg, "## User Query\n%s\n", in.UserQuestion)

	if in.ErrorFeedback != "" {
		fmt.Fprintf(&userMsg, "\n---\n\n## FEEDBACK FROM PREVIOUS ATTEMPT\n\n")
		if in.PreviousStrategy != "" {
			fmt.Fprintf(&userMsg, "**Previous strategy:**\n```\n%s\n```\n\n", in.PreviousStrategy)
		}
		fmt.Fprintf(&userMsg, "**SQL execution error:**\n%s\n\n", in.ErrorFeedback)
		fmt.Fprintf(&userMsg, "Apply ONLY the corrections implied by the error above. Keep the rest of the strategy unchanged.")
	}
	if in.RefinementFeedback != "" {
		fmt.Fprintf(&userMsg, "\n---\n\n## FEEDBACK: PREVIOUS QUERY RETURNED NO ROWS\n\n")
		if in.PreviousStrategy != "" {
			fmt.Fprintf(&userMsg, "**Previous strategy:**\n```\n%s\n```\n\n", in.PreviousStrategy)
		}
		fmt.Fprintf(&userMsg, "**Why it returned no rows:**\n%s\n\n", in.RefinementFeedback)
		fmt.Fprintf(&userMsg, "Broaden the strategy to actually return results.")
	}

	msgs := []llm.Message{
		{Role: llm.RoleSystem, Content: system},
		{Role: llm.RoleUser, Content: userMsg.String()},
	}
	strategy, err := client.Chat(ctx, msgs)
	if err != nil {
		return "", nil, err
	}
	return strategy, promptContextFromMessages(msgs, llm.ModelForStage(llm.StageStrategy)), nil
}

// PlannerInput drives stage two: convert the strategy into a PlannerOutput.
type PlannerInput struct {
	UserQuestion   string
	Strategy       string
	SchemaMarkdown string
}

// Planner translates the text strategy into a structured PlannerOutput via the
// LLM's structured-output mode. Replaces agent/planner.py for the "full" tier.
//
// Returns (plan, promptContext, error). Same prompt-capture pattern as PrePlanner.
func Planner(ctx context.Context, in PlannerInput) (*models.PlannerOutput, *PromptContext, error) {
	client, err := llm.NewForStage(llm.StagePlanning)
	if err != nil {
		return nil, nil, err
	}
	schemaJSON, err := models.PlannerOutputSchema()
	if err != nil {
		return nil, nil, err
	}

	system := `# Planner (JSON Phase)

You are the second stage of a two-stage SQL query planner. The first stage wrote
a text strategy. Your job is to convert that strategy into a PlannerOutput JSON
object using the provided tool/schema.

Rules:
- Use ONLY exact table and column names from the schema.
- selections must include every table referenced by join_edges.
- For each filter column, include both the column entry (role=filter or projection)
  AND a FilterPredicate.
- decision = "proceed" unless the strategy says otherwise.
- For "last N" queries: set order_by + limit, NOT a date filter.`

	var userMsg strings.Builder
	if in.SchemaMarkdown != "" {
		userMsg.WriteString(in.SchemaMarkdown)
		userMsg.WriteString("\n\n")
	}
	fmt.Fprintf(&userMsg, "## User Query\n%s\n\n", in.UserQuestion)
	fmt.Fprintf(&userMsg, "## Strategy from Pre-Planner\n%s\n", in.Strategy)

	msgs := []llm.Message{
		{Role: llm.RoleSystem, Content: system},
		{Role: llm.RoleUser, Content: userMsg.String()},
	}
	promptCtx := promptContextFromMessages(msgs, llm.ModelForStage(llm.StagePlanning))

	var out models.PlannerOutput
	if err := client.StructuredOutput(ctx, msgs, schemaJSON, "PlannerOutput", &out); err != nil {
		return nil, promptCtx, err
	}

	autoFixJoinEdges(&out)
	return &out, promptCtx, nil
}

// autoFixJoinEdges mirrors agent/planner.py:auto_fix_join_edges. Adds any
// table that join_edges references but selections doesn't, marked join-only.
func autoFixJoinEdges(p *models.PlannerOutput) {
	selected := make(map[string]bool, len(p.Selections))
	for _, s := range p.Selections {
		selected[strings.ToLower(s.Table)] = true
	}
	for _, e := range p.JoinEdges {
		for _, t := range []string{e.FromTable, e.ToTable} {
			if t == "" {
				continue
			}
			key := strings.ToLower(t)
			if !selected[key] {
				p.Selections = append(p.Selections, models.TableSelection{
					Table:              t,
					Confidence:         0.7,
					IncludeOnlyForJoin: true,
				})
				selected[key] = true
			}
		}
	}
}

// PlanAuditResult lists deterministic issues found in the planner output.
// The audit is permissive (mirrors Python's "log but continue" mode) — the SQL
// emitter or the database itself will surface real problems.
type PlanAuditResult struct {
	Issues []string
}

// PlanAudit walks the plan and reports issues that don't require the LLM:
// unknown tables, unknown columns, joins between non-existent columns. For MVP
// we just collect issues and continue — the Python audit feedback loop is
// disabled there too.
func PlanAudit(plan *models.PlannerOutput, fullSchema []map[string]any) PlanAuditResult {
	var out PlanAuditResult
	if plan == nil {
		out.Issues = append(out.Issues, "nil plan")
		return out
	}
	tableLookup := make(map[string]map[string]bool)
	for _, t := range fullSchema {
		name, _ := t["table_name"].(string)
		cols := make(map[string]bool)
		if rawCols, ok := t["columns"].([]any); ok {
			for _, rc := range rawCols {
				if cm, ok := rc.(map[string]any); ok {
					if cn, ok := cm["column_name"].(string); ok {
						cols[strings.ToLower(cn)] = true
					}
				}
			}
		}
		tableLookup[strings.ToLower(name)] = cols
	}
	for _, sel := range plan.Selections {
		cols, ok := tableLookup[strings.ToLower(sel.Table)]
		if !ok {
			out.Issues = append(out.Issues, fmt.Sprintf("unknown table %q", sel.Table))
			continue
		}
		for _, c := range sel.Columns {
			if !cols[strings.ToLower(c.Column)] {
				out.Issues = append(out.Issues, fmt.Sprintf("unknown column %s.%s", sel.Table, c.Column))
			}
		}
	}
	return out
}

// CheckClarification mirrors agent/check_clarification.py: route on the
// planner's `decision` field.
type ClarificationDecision int

const (
	DecideProceed ClarificationDecision = iota
	DecideClarify
	DecideTerminate
)

func CheckClarification(plan *models.PlannerOutput) ClarificationDecision {
	if plan == nil {
		return DecideTerminate
	}
	switch plan.Decision {
	case models.DecisionTerminate:
		return DecideTerminate
	case models.DecisionClarify:
		return DecideClarify
	default:
		return DecideProceed
	}
}
