package nodes

import (
	"context"
	"fmt"
	"strings"

	"github.com/sachit/sql-query-assistant/go-service/internal/llm"
)

// HandleErrorInput collects what the error-correction node needs.
type HandleErrorInput struct {
	UserQuestion   string
	Strategy       string
	Query          string
	ErrorMessage   string
	SchemaMarkdown string
}

// HandleError analyses a SQL execution error and produces feedback for the
// pre-planner to use on its next attempt. Mirrors agent/handle_tool_error.py:
// the output is strategic guidance, not a JSON patch.
//
// Returns (feedback, promptContext, error). PromptContext lets the orchestrator
// surface the exact LLM input through the SSE status events.
func HandleError(ctx context.Context, in HandleErrorInput) (string, *PromptContext, error) {
	client, err := llm.NewForStage(llm.StageErrorCorrection)
	if err != nil {
		return "", nil, err
	}

	system := `# Error Correction

A SQL query produced by the planner pipeline failed at execution. Your job is to
write a short feedback note for the pre-planner so it can correct the strategy
on the next attempt.

Output format (plain text, no JSON):
**What went wrong:** <one-line root cause — wrong column, wrong join, wrong type, etc.>
**How to fix the strategy:** <specific tables/columns to change. Be concrete.>

Keep it under 150 words. Reference exact table/column names from the schema.`

	var b strings.Builder
	if in.SchemaMarkdown != "" {
		b.WriteString(in.SchemaMarkdown)
		b.WriteString("\n\n")
	}
	fmt.Fprintf(&b, "## User Question\n%s\n\n", in.UserQuestion)
	fmt.Fprintf(&b, "## Previous Strategy\n%s\n\n", in.Strategy)
	fmt.Fprintf(&b, "## Generated SQL\n```sql\n%s\n```\n\n", in.Query)
	fmt.Fprintf(&b, "## Error\n%s\n", in.ErrorMessage)

	msgs := []llm.Message{
		{Role: llm.RoleSystem, Content: system},
		{Role: llm.RoleUser, Content: b.String()},
	}
	feedback, err := client.Chat(ctx, msgs)
	if err != nil {
		return "", nil, err
	}
	return feedback, promptContextFromMessages(msgs, llm.ModelForStage(llm.StageErrorCorrection)), nil
}

// RefineQueryInput drives the empty-results feedback loop.
type RefineQueryInput struct {
	UserQuestion   string
	Strategy       string
	Query          string
	SchemaMarkdown string
}

// RefineQuery analyses why a SQL query returned no rows and produces feedback
// for the pre-planner. Mirrors agent/refine_query.py — strategy-first.
//
// Returns (feedback, promptContext, error).
func RefineQuery(ctx context.Context, in RefineQueryInput) (string, *PromptContext, error) {
	client, err := llm.NewForStage(llm.StageRefinement)
	if err != nil {
		return "", nil, err
	}

	system := `# Empty-Result Refinement

A SQL query produced by the planner pipeline executed successfully but returned
zero rows. Your job is to write a short feedback note for the pre-planner so it
can broaden the strategy on the next attempt.

Output format (plain text, no JSON):
**Why no rows:** <one line: filters too restrictive, wrong columns, etc.>
**How to broaden:** <specific filters to relax or change. Be concrete.>

Keep it under 150 words.`

	var b strings.Builder
	if in.SchemaMarkdown != "" {
		b.WriteString(in.SchemaMarkdown)
		b.WriteString("\n\n")
	}
	fmt.Fprintf(&b, "## User Question\n%s\n\n", in.UserQuestion)
	fmt.Fprintf(&b, "## Previous Strategy\n%s\n\n", in.Strategy)
	fmt.Fprintf(&b, "## Generated SQL\n```sql\n%s\n```\n", in.Query)

	msgs := []llm.Message{
		{Role: llm.RoleSystem, Content: system},
		{Role: llm.RoleUser, Content: b.String()},
	}
	feedback, err := client.Chat(ctx, msgs)
	if err != nil {
		return "", nil, err
	}
	return feedback, promptContextFromMessages(msgs, llm.ModelForStage(llm.StageRefinement)), nil
}
