package nodes

import "github.com/sachit/sql-query-assistant/go-service/internal/llm"

// PromptContext carries the exact LLM input a node sent so the orchestrator
// can attach it to the `node_metadata.prompt_context` SSE field. The frontend's
// PromptViewer renders this in markdown so the user can audit what was sent.
//
// JSON shape mirrors the Python service's `prompt_context` dict so the React
// `PromptViewer` component works identically against either backend.
type PromptContext struct {
	Messages []PromptMessage `json:"messages"`
	Model    string          `json:"model,omitempty"`
}

// PromptMessage is one role/content pair, JSON-tagged to match Python's output.
type PromptMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// promptContextFromMessages converts an internal []llm.Message slice into the
// wire-format PromptContext the frontend consumes. Pulled into a helper so
// every node uses the same conversion.
func promptContextFromMessages(msgs []llm.Message, model string) *PromptContext {
	out := &PromptContext{
		Messages: make([]PromptMessage, len(msgs)),
		Model:    model,
	}
	for i, m := range msgs {
		out.Messages[i] = PromptMessage{Role: string(m.Role), Content: m.Content}
	}
	return out
}
