// Package llm abstracts the OpenAI / Anthropic / Ollama chat APIs behind a
// minimal interface that mirrors utils/llm_factory.py's responsibilities:
// chat, structured output, streaming, and embeddings, with stage-aware model
// routing controlled by the same env vars the Python service uses.
package llm

import (
	"context"
	"fmt"
	"os"
	"strings"
)

type Role string

const (
	RoleSystem    Role = "system"
	RoleUser      Role = "user"
	RoleAssistant Role = "assistant"
)

type Message struct {
	Role    Role
	Content string
}

// StreamChunk is emitted for every incremental token by Stream(). The terminal
// chunk has Done=true; err may be non-nil instead of a chunk on transport failure.
type StreamChunk struct {
	Delta string
	Done  bool
}

// Client is the provider-agnostic surface used by every workflow node.
//
// Structured output:
//   The schema argument is a JSON Schema describing the desired payload.
//   For OpenAI we pass it as response_format=json_schema; for Anthropic we
//   coerce it through forced tool-use. The implementation must JSON-decode
//   the model's reply into `out` before returning.
type Client interface {
	Chat(ctx context.Context, msgs []Message) (string, error)
	StructuredOutput(ctx context.Context, msgs []Message, schema any, schemaName string, out any) error
	Stream(ctx context.Context, msgs []Message) (<-chan StreamChunk, error)
	// ChatWithTools is the chat-agent entry point: optional tool calls plus
	// optional text content. The returned ToolCallResponse normalizes the
	// shape across providers so callers don't branch on Anthropic vs OpenAI.
	ChatWithTools(ctx context.Context, msgs []Message, tools []ToolDef) (*ToolCallResponse, error)
}

// ToolDef describes one tool the LLM may call. The InputSchema is a JSON
// Schema describing the tool's argument object.
type ToolDef struct {
	Name        string
	Description string
	InputSchema map[string]any
}

// ToolCall is one invocation the LLM emitted. Input is raw JSON that the
// caller decodes against the tool's known schema.
type ToolCall struct {
	ID    string
	Name  string
	Input []byte
}

// ToolCallResponse normalizes a chat-with-tools turn. Either Content or
// ToolCalls (or both) may be populated; an empty response is unusual but
// not an error.
type ToolCallResponse struct {
	Content   string
	ToolCalls []ToolCall
}

// Embedder is split out because not every chat provider does embeddings.
// Today only OpenAI is wired; Ollama could implement this later.
type Embedder interface {
	Embed(ctx context.Context, texts []string) ([][]float32, error)
}

// modelRegistry mirrors utils/llm_factory.py:MODEL_REGISTRY.
// Keys are user-facing aliases; values map to (provider, real model name).
var modelRegistry = map[string]struct {
	provider string
	model    string
}{
	// Anthropic
	"claude-sonnet-4-5": {"anthropic", "claude-sonnet-4-5-20250929"},
	"claude-haiku-4-5":  {"anthropic", "claude-haiku-4-5-20251001"},
	"claude-opus-4-1":   {"anthropic", "claude-opus-4-1-20250805"},
	// OpenAI
	"gpt-5":       {"openai", "gpt-5"},
	"gpt-5-mini":  {"openai", "gpt-5-mini"},
	"gpt-5-nano":  {"openai", "gpt-5-nano"},
	"gpt-4o":      {"openai", "gpt-4o"},
	"gpt-4o-mini": {"openai", "gpt-4o-mini"},
	"o3":          {"openai", "o3"},
	"o3-mini":     {"openai", "o3-mini"},
	"o1-mini":     {"openai", "o1-mini"},
}

// ResolveModel returns (provider, real model name) for an alias or raw model name.
// Falls back to prefix-based inference (claude→anthropic, gpt/o1/o3→openai),
// matching utils/llm_factory.py:get_provider_for_model.
func ResolveModel(name string) (provider, model string) {
	if entry, ok := modelRegistry[name]; ok {
		return entry.provider, entry.model
	}
	switch {
	case strings.HasPrefix(name, "claude"):
		return "anthropic", name
	case strings.HasPrefix(name, "gpt"), strings.HasPrefix(name, "o1"), strings.HasPrefix(name, "o3"):
		return "openai", name
	}
	return "openai", name
}

// Stage names match the Python service's get_model_for_stage stage labels.
type Stage string

const (
	StageStrategy        Stage = "strategy"
	StagePlanning        Stage = "planning"
	StageFiltering       Stage = "filtering"
	StageErrorCorrection Stage = "error_correction"
	StageRefinement      Stage = "refinement"
	StageChat            Stage = "chat"
)

// ModelForStage returns the configured model name for a workflow stage, honoring
// USE_LOCAL_LLM and the LOCAL_MODEL_* / REMOTE_MODEL_* env vars. Mirrors
// utils/llm_factory.py:get_model_for_stage including the strategy-fallback for chat.
func ModelForStage(stage Stage) string {
	useLocal := strings.EqualFold(os.Getenv("USE_LOCAL_LLM"), "true")
	prefix := "REMOTE_MODEL_"
	if useLocal {
		prefix = "LOCAL_MODEL_"
	}

	envName := prefix + strings.ToUpper(string(stage))
	if v := os.Getenv(envName); v != "" {
		return v
	}
	// chat falls back to strategy, matching Python.
	if stage == StageChat {
		if v := os.Getenv(prefix + "STRATEGY"); v != "" {
			return v
		}
	}
	// Final fallback: AI_MODEL.
	return os.Getenv("AI_MODEL")
}

// New returns a Client for the given model name, routed through the configured
// provider. Requires the matching API key env var to be set.
//
// When USE_LOCAL_LLM=true, the provider is forced to Ollama regardless of the
// model name's prefix — local models like `llama3:8b` or `gpt-oss:20b` don't
// match our alias registry but should always go to Ollama in local mode.
func New(modelName string) (Client, error) {
	if strings.EqualFold(os.Getenv("USE_LOCAL_LLM"), "true") {
		return newOllamaClient(modelName)
	}

	provider, realModel := ResolveModel(modelName)
	switch provider {
	case "anthropic":
		key := os.Getenv("ANTHROPIC_API_KEY")
		if key == "" {
			return nil, fmt.Errorf("ANTHROPIC_API_KEY not set (model %s)", modelName)
		}
		return newAnthropicClient(key, realModel), nil
	case "openai":
		key := os.Getenv("OPENAI_API_KEY")
		if key == "" {
			return nil, fmt.Errorf("OPENAI_API_KEY not set (model %s)", modelName)
		}
		return newOpenAIClient(key, realModel), nil
	case "ollama":
		return newOllamaClient(realModel)
	}
	return nil, fmt.Errorf("unknown provider %q for model %q", provider, modelName)
}

// NewForStage is the typical entry point used by workflow nodes.
func NewForStage(stage Stage) (Client, error) {
	model := ModelForStage(stage)
	if model == "" {
		return nil, fmt.Errorf("no model configured for stage %s", stage)
	}
	return New(model)
}

// NewEmbedder returns an Embedder for the given embedding model name.
// Only OpenAI embeddings are wired; pass "" to default to text-embedding-3-small.
func NewEmbedder(modelName string) (Embedder, error) {
	if modelName == "" {
		modelName = os.Getenv("EMBEDDING_MODEL")
		if modelName == "" {
			modelName = "text-embedding-3-small"
		}
	}
	key := os.Getenv("OPENAI_API_KEY")
	if key == "" {
		return nil, fmt.Errorf("OPENAI_API_KEY not set (embedder %s)", modelName)
	}
	return newOpenAIEmbedder(key, modelName), nil
}
