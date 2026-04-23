package chat

import "github.com/sachit/sql-query-assistant/go-service/internal/llm"

// runQueryToolName / respondWithRevisionToolName are the literal tool
// identifiers the LLM uses. Match Python's chat_tools.py exactly so prompts
// and downstream logic don't diverge.
const (
	RunQueryToolName            = "run_query"
	RespondWithRevisionToolName = "respond_with_revision"
)

// AllTools is the full tool surface for chat. Used in the early turns when
// the model still has its tool budget.
func AllTools() []llm.ToolDef {
	return []llm.ToolDef{runQueryTool(), respondWithRevisionTool()}
}

// SuggestOnlyTools is the reduced surface once the tool budget is exhausted.
// Mirrors the Python service: respond_with_revision doesn't count against
// the budget because it doesn't run a database query.
func SuggestOnlyTools() []llm.ToolDef {
	return []llm.ToolDef{respondWithRevisionTool()}
}

func runQueryTool() llm.ToolDef {
	return llm.ToolDef{
		Name: RunQueryToolName,
		Description: `Run a brand new SQL query against the same database. ` +
			`Use when the user asks a follow-up question that needs different data ` +
			`than the original query returned (e.g. a different filter, different table, more rows).`,
		InputSchema: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"query": map[string]any{
					"type":        "string",
					"description": "Natural-language description of the new query — same shape the user would type into the main search box.",
				},
			},
			"required": []any{"query"},
		},
	}
}

func respondWithRevisionTool() llm.ToolDef {
	return llm.ToolDef{
		Name: RespondWithRevisionToolName,
		Description: `Provide a SQL revision suggestion alongside your reply. ` +
			`Use when you spot a problem with the executed SQL (wrong column, missing JOIN, ` +
			`Cartesian product) without re-running it.`,
		InputSchema: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"message": map[string]any{
					"type":        "string",
					"description": "Plain-language summary of what's wrong and what the revision fixes.",
				},
				"revised_sql": map[string]any{
					"type":        "string",
					"description": "The corrected SQL string.",
				},
				"explanation": map[string]any{
					"type":        "string",
					"description": "Short explanation of the diff between old and revised SQL.",
				},
			},
			"required": []any{"message", "revised_sql", "explanation"},
		},
	}
}
