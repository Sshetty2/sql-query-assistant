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

// GenerateQueryNarrative writes a 2-4 sentence summary of the query result.
// Mirrors agent/chat_agent.py:generate_narrative — minus the
// `respond_with_revision` tool call, which is a chat-agent concern (Phase 11).
//
// Returns ("", nil, nil) without calling the LLM when there's nothing useful
// to summarize. Otherwise returns (narrative, promptContext, nil).
func GenerateQueryNarrative(ctx context.Context, in NarrativeInput) (string, *PromptContext, error) {
	if len(in.Result) == 0 {
		return "", nil, nil
	}

	client, err := llm.NewForStage(llm.StageChat)
	if err != nil {
		return "", nil, fmt.Errorf("narrative llm: %w", err)
	}

	system := `You summarize SQL query results for a non-technical reader.
Rules:
- Reference what the user asked.
- Highlight key numbers, patterns, or unusual values.
- 2-4 sentences. No SQL, no markdown bullet lists.
- If the data looks suspicious (Cartesian product, all NULLs, off-by-many counts), say so plainly.`

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
	narrative, err := client.Chat(ctx, msgs)
	if err != nil {
		return "", nil, err
	}
	return narrative, promptContextFromMessages(msgs, llm.ModelForStage(llm.StageChat)), nil
}
