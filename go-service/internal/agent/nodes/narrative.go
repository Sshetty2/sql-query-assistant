package nodes

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/sachit/sql-query-assistant/go-service/internal/llm"
	"github.com/sachit/sql-query-assistant/go-service/internal/models"
)

// NarrativeInput is the slice of state the narrative node needs.
// Pulled out so the function stays trivially testable.
type NarrativeInput struct {
	UserQuestion string
	Query        string
	Result       []map[string]any
	DataSummary  *models.DataSummary
}

// NarrativeOutput is the narrative text plus an optional SQL revision the
// model surfaces when it notices a data-quality issue.
type NarrativeOutput struct {
	Narrative string
	Revision  *models.NarrativeRevision
}

// narrativeRespondTool is a local copy of the chat-agent `respond` tool shape
// so the narrative node can surface a revision inline. Kept here to avoid a
// cyclic import between agent/nodes and internal/chat.
func narrativeRespondTool() llm.ToolDef {
	return llm.ToolDef{
		Name: "respond",
		Description: "Return your narrative summary. Set message to the summary text. " +
			"If you notice a data-quality issue with the SQL (Cartesian product, missing filter, " +
			"wrong join, results that don't match the question), also set revised_sql + explanation " +
			"with a corrected SELECT query.",
		InputSchema: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"message": map[string]any{
					"type":        "string",
					"description": "2-4 sentence narrative summary of the results.",
				},
				"revised_sql": map[string]any{
					"type":        "string",
					"description": "Optional. A complete corrected SELECT query.",
				},
				"explanation": map[string]any{
					"type":        "string",
					"description": "Optional. One-line diff summary. Required when revised_sql is set.",
				},
			},
			"required": []any{"message"},
		},
	}
}

// GenerateQueryNarrative writes a 2-4 sentence summary of the query result.
// Mirrors agent/chat_agent.py:generate_narrative — including the optional
// revision the LLM may attach when it spots a data-quality issue.
//
// Returns a zero-value NarrativeOutput without calling the LLM when there's
// nothing useful to summarize. Otherwise returns (output, promptContext, nil).
// Falls back to Chat (no tools) for providers that don't support ChatWithTools
// so Ollama deployments still get a narrative (minus the revision path).
func GenerateQueryNarrative(ctx context.Context, in NarrativeInput) (NarrativeOutput, *PromptContext, error) {
	if len(in.Result) == 0 {
		return NarrativeOutput{}, nil, nil
	}

	client, err := llm.NewForStage(llm.StageChat)
	if err != nil {
		return NarrativeOutput{}, nil, fmt.Errorf("narrative llm: %w", err)
	}

	system := `You summarize SQL query results for a non-technical reader.
Rules:
- Reference what the user asked.
- Highlight key numbers, patterns, or unusual values.
- 2-4 sentences. No SQL, no markdown bullet lists.
- If the data looks suspicious (Cartesian product, all NULLs, off-by-many counts), say so plainly.
- Always reply by calling the respond tool with your summary in message.
- If you notice a data-quality issue with the SQL, include revised_sql + explanation in the same call.`

	// Trim the row sample so the prompt stays small. 5 rows is what the Python
	// service uses; matches the data preview in the UI.
	sampleRows := in.Result
	if len(sampleRows) > 5 {
		sampleRows = sampleRows[:5]
	}
	sampleJSON, _ := json.MarshalIndent(sampleRows, "", "  ")
	summaryJSON, _ := json.MarshalIndent(in.DataSummary, "", "  ")

	var b strings.Builder
	fmt.Fprintf(&b, "## User Question\n%s\n\n", in.UserQuestion)
	fmt.Fprintf(&b, "## SQL Run\n```sql\n%s\n```\n\n", in.Query)
	fmt.Fprintf(&b, "## Data Summary\n```json\n%s\n```\n\n", summaryJSON)
	fmt.Fprintf(&b, "## First %d Rows\n```json\n%s\n```\n", len(sampleRows), sampleJSON)

	msgs := []llm.Message{
		{Role: llm.RoleSystem, Content: system},
		{Role: llm.RoleUser, Content: b.String()},
	}

	resp, err := client.ChatWithTools(ctx, msgs, []llm.ToolDef{narrativeRespondTool()})
	if err != nil {
		// Ollama (and anything else without tool support) reports "not
		// implemented". Fall back to a plain Chat call so the narrative
		// still appears — just without the optional revision.
		if strings.Contains(err.Error(), "not implemented") {
			narrative, chatErr := client.Chat(ctx, msgs)
			if chatErr != nil {
				return NarrativeOutput{}, nil, chatErr
			}
			return NarrativeOutput{Narrative: narrative},
				promptContextFromMessages(msgs, llm.ModelForStage(llm.StageChat)),
				nil
		}
		return NarrativeOutput{}, nil, err
	}

	out := NarrativeOutput{Narrative: resp.Content}
	for _, tc := range resp.ToolCalls {
		if tc.Name != "respond" {
			continue
		}
		var args struct {
			Message     string `json:"message"`
			RevisedSQL  string `json:"revised_sql"`
			Explanation string `json:"explanation"`
		}
		if err := json.Unmarshal(tc.Input, &args); err != nil {
			continue
		}
		// The respond message is authoritative when present — it was written
		// specifically as the narrative.
		if strings.TrimSpace(args.Message) != "" {
			out.Narrative = args.Message
		}
		if args.RevisedSQL != "" {
			explanation := args.Explanation
			if explanation == "" {
				explanation = "SQL revision"
			}
			out.Revision = &models.NarrativeRevision{
				RevisedSQL:  args.RevisedSQL,
				Explanation: explanation,
			}
		}
		break
	}

	return out, promptContextFromMessages(msgs, llm.ModelForStage(llm.StageChat)), nil
}
