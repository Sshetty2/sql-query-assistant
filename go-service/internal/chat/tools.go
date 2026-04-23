package chat

import "github.com/sachit/sql-query-assistant/go-service/internal/llm"

// RunQueryToolName / RespondToolName are the literal tool identifiers the
// LLM uses. Match Python's agent/chat_tools.py exactly so prompts and
// downstream logic don't diverge.
const (
	RunQueryToolName = "run_query"
	RespondToolName  = "respond"
)

// AllTools is the full tool surface for chat. Used in the early turns when
// the model still has its tool budget.
func AllTools() []llm.ToolDef {
	return []llm.ToolDef{runQueryTool(), respondTool()}
}

// RespondOnlyTools is the reduced surface once the tool budget is exhausted.
// Mirrors the Python service: `respond` doesn't count against the budget
// because it doesn't run a database query.
func RespondOnlyTools() []llm.ToolDef {
	return []llm.ToolDef{respondTool()}
}

func runQueryTool() llm.ToolDef {
	return llm.ToolDef{
		Name: RunQueryToolName,
		Description: `Run a brand new SQL query against the same database. ` +
			`Use when the user asks a follow-up question that needs different data ` +
			`than the original query returned (e.g. a different filter, different table, more rows). ` +
			`After the new results come back, summarize them by calling respond.`,
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

// respondTool is the ONLY way the chat agent replies to the user. Every turn
// ends with a respond call. The revision fields are optional so the same tool
// covers both pure commentary and SQL-revision replies.
func respondTool() llm.ToolDef {
	return llm.ToolDef{
		Name: RespondToolName,
		Description: `Reply to the user. Every chat turn must end with exactly one respond call — ` +
			`text emitted outside of respond will not reach the user. ` +
			`Include revised_sql + explanation whenever the reply involves or could involve a SQL change ` +
			`(data-quality fix, add/remove column, change filter, correct a join, adjust sorting, any improvement). ` +
			`Never describe a SQL problem without proposing the fix in the same call. ` +
			`Omit revised_sql/explanation only for pure commentary that doesn't touch the SQL.`,
		InputSchema: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"message": map[string]any{
					"type":        "string",
					"description": "Your reply to the user, in markdown. Summarize findings and explain any SQL change.",
				},
				"revised_sql": map[string]any{
					"type":        "string",
					"description": "Optional. A complete revised SELECT query, ready to execute. Required whenever the reply involves a SQL change.",
				},
				"explanation": map[string]any{
					"type":        "string",
					"description": "Optional. One-line summary of what changed in the SQL. Required when revised_sql is set.",
				},
			},
			"required": []any{"message"},
		},
	}
}
