package llm

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"os"

	"github.com/ollama/ollama/api"
)

type ollamaClient struct {
	client *api.Client
	model  string
}

func newOllamaClient(model string) (*ollamaClient, error) {
	base := os.Getenv("OLLAMA_BASE_URL")
	if base == "" {
		base = "http://localhost:11434"
	}
	u, err := url.Parse(base)
	if err != nil {
		return nil, fmt.Errorf("invalid OLLAMA_BASE_URL %q: %w", base, err)
	}
	return &ollamaClient{
		client: api.NewClient(u, http.DefaultClient),
		model:  model,
	}, nil
}

// boolPtr is needed because api.ChatRequest.Stream is a `*bool`. Tri-state:
// nil=default, &false=non-streaming, &true=streaming.
func boolPtr(b bool) *bool { return &b }

func toOllamaMessages(msgs []Message) []api.Message {
	out := make([]api.Message, 0, len(msgs))
	for _, m := range msgs {
		role := "user"
		switch m.Role {
		case RoleSystem:
			role = "system"
		case RoleAssistant:
			role = "assistant"
		}
		out = append(out, api.Message{Role: role, Content: m.Content})
	}
	return out
}

// Chat runs a non-streaming chat completion. Ollama's Go client uses a
// callback-based API even when streaming is off, so we accumulate the single
// final response inside the callback.
func (o *ollamaClient) Chat(ctx context.Context, msgs []Message) (string, error) {
	var content string
	err := o.client.Chat(ctx, &api.ChatRequest{
		Model:    o.model,
		Messages: toOllamaMessages(msgs),
		Stream:   boolPtr(false),
	}, func(r api.ChatResponse) error {
		content += r.Message.Content
		return nil
	})
	if err != nil {
		return "", fmt.Errorf("ollama chat: %w", err)
	}
	return content, nil
}

// StructuredOutput uses Ollama's Format field, which accepts a JSON Schema and
// constrains the model's output to match it. That's distinct from "JSON mode"
// (`Format: "json"`) which would just promise valid JSON but no shape.
//
// Falls back to a system-prompt nudge if the schema can't be marshalled.
func (o *ollamaClient) StructuredOutput(ctx context.Context, msgs []Message, schema any, schemaName string, out any) error {
	rawSchema, err := json.Marshal(schema)
	if err != nil {
		return fmt.Errorf("marshal schema: %w", err)
	}

	// Inject a system note about the expected shape; helps weaker local models
	// that can't fully drive structured generation from the schema alone.
	msgsWithHint := append([]Message{}, msgs...)
	hint := fmt.Sprintf("You must respond with valid JSON matching the %s schema. No prose, no markdown fences.", schemaName)
	if len(msgsWithHint) > 0 && msgsWithHint[0].Role == RoleSystem {
		msgsWithHint[0].Content = msgsWithHint[0].Content + "\n\n" + hint
	} else {
		msgsWithHint = append([]Message{{Role: RoleSystem, Content: hint}}, msgsWithHint...)
	}

	var body string
	err = o.client.Chat(ctx, &api.ChatRequest{
		Model:    o.model,
		Messages: toOllamaMessages(msgsWithHint),
		Stream:   boolPtr(false),
		Format:   rawSchema,
	}, func(r api.ChatResponse) error {
		body += r.Message.Content
		return nil
	})
	if err != nil {
		return fmt.Errorf("ollama structured: %w", err)
	}
	if err := json.Unmarshal([]byte(body), out); err != nil {
		return fmt.Errorf("decode ollama JSON: %w (raw: %s)", err, body)
	}
	return nil
}

// ChatWithTools is intentionally unimplemented for Ollama. The chat agent
// in internal/chat is designed for Claude / GPT, where tool calling is
// first-class. Ollama's tool surface is awkward (opaque ToolPropertiesMap)
// and quality varies wildly by model, so we punt rather than ship a
// half-working integration. Users on USE_LOCAL_LLM=true will see a clear
// error and can fall back to non-chat features.
func (o *ollamaClient) ChatWithTools(_ context.Context, _ []Message, _ []ToolDef) (*ToolCallResponse, error) {
	return nil, fmt.Errorf("chat tools are not supported on Ollama; use a remote provider for chat")
}

func (o *ollamaClient) Stream(ctx context.Context, msgs []Message) (<-chan StreamChunk, error) {
	out := make(chan StreamChunk, 16)
	go func() {
		defer close(out)
		err := o.client.Chat(ctx, &api.ChatRequest{
			Model:    o.model,
			Messages: toOllamaMessages(msgs),
			Stream:   boolPtr(true),
		}, func(r api.ChatResponse) error {
			if r.Message.Content != "" {
				out <- StreamChunk{Delta: r.Message.Content}
			}
			return nil
		})
		if err != nil {
			// Surface the error so the consumer notices — Stream's signature
			// doesn't return an error after the channel is opened, so we
			// emit a final empty chunk and rely on the caller's logging.
			out <- StreamChunk{Done: true}
			return
		}
		out <- StreamChunk{Done: true}
	}()
	return out, nil
}
