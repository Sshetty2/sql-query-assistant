package llm

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/openai/openai-go/v3"
	"github.com/openai/openai-go/v3/option"
	"github.com/openai/openai-go/v3/shared"
)

type openAIClient struct {
	client openai.Client
	model  string
}

func newOpenAIClient(apiKey, model string) *openAIClient {
	c := openai.NewClient(option.WithAPIKey(apiKey))
	return &openAIClient{client: c, model: model}
}

func toOpenAIMessages(msgs []Message) []openai.ChatCompletionMessageParamUnion {
	out := make([]openai.ChatCompletionMessageParamUnion, 0, len(msgs))
	for _, m := range msgs {
		switch m.Role {
		case RoleSystem:
			out = append(out, openai.SystemMessage(m.Content))
		case RoleAssistant:
			out = append(out, openai.AssistantMessage(m.Content))
		default:
			out = append(out, openai.UserMessage(m.Content))
		}
	}
	return out
}

func (o *openAIClient) Chat(ctx context.Context, msgs []Message) (string, error) {
	resp, err := o.client.Chat.Completions.New(ctx, openai.ChatCompletionNewParams{
		Model:    shared.ChatModel(o.model),
		Messages: toOpenAIMessages(msgs),
	})
	if err != nil {
		return "", fmt.Errorf("openai chat: %w", err)
	}
	if len(resp.Choices) == 0 {
		return "", fmt.Errorf("openai chat: empty choices")
	}
	return resp.Choices[0].Message.Content, nil
}

func (o *openAIClient) StructuredOutput(ctx context.Context, msgs []Message, schema any, schemaName string, out any) error {
	resp, err := o.client.Chat.Completions.New(ctx, openai.ChatCompletionNewParams{
		Model:    shared.ChatModel(o.model),
		Messages: toOpenAIMessages(msgs),
		ResponseFormat: openai.ChatCompletionNewParamsResponseFormatUnion{
			OfJSONSchema: &shared.ResponseFormatJSONSchemaParam{
				JSONSchema: shared.ResponseFormatJSONSchemaJSONSchemaParam{
					Name:   schemaName,
					Schema: schema,
					Strict: openai.Bool(false),
				},
			},
		},
	})
	if err != nil {
		return fmt.Errorf("openai structured: %w", err)
	}
	if len(resp.Choices) == 0 {
		return fmt.Errorf("openai structured: empty choices")
	}
	content := resp.Choices[0].Message.Content
	if err := json.Unmarshal([]byte(content), out); err != nil {
		return fmt.Errorf("decode structured output: %w (raw: %s)", err, content)
	}
	return nil
}

// ChatWithTools binds the provided tools to a Chat Completions call and
// returns a normalized response. Used by the chat agent.
func (o *openAIClient) ChatWithTools(ctx context.Context, msgs []Message, tools []ToolDef) (*ToolCallResponse, error) {
	openaiTools := make([]openai.ChatCompletionToolUnionParam, 0, len(tools))
	for _, t := range tools {
		openaiTools = append(openaiTools, openai.ChatCompletionToolUnionParam{
			OfFunction: &openai.ChatCompletionFunctionToolParam{
				Function: shared.FunctionDefinitionParam{
					Name:        t.Name,
					Description: openai.String(t.Description),
					Parameters:  t.InputSchema,
				},
			},
		})
	}

	resp, err := o.client.Chat.Completions.New(ctx, openai.ChatCompletionNewParams{
		Model:    shared.ChatModel(o.model),
		Messages: toOpenAIMessages(msgs),
		Tools:    openaiTools,
	})
	if err != nil {
		return nil, fmt.Errorf("openai chat-with-tools: %w", err)
	}
	if len(resp.Choices) == 0 {
		return nil, fmt.Errorf("openai chat-with-tools: empty choices")
	}

	out := &ToolCallResponse{Content: resp.Choices[0].Message.Content}
	for _, tc := range resp.Choices[0].Message.ToolCalls {
		// We only handle function-style tool calls today (Responses-API
		// `custom` tools etc. would need separate branches).
		if tc.Function.Name == "" {
			continue
		}
		out.ToolCalls = append(out.ToolCalls, ToolCall{
			ID:    tc.ID,
			Name:  tc.Function.Name,
			Input: []byte(tc.Function.Arguments),
		})
	}
	return out, nil
}

func (o *openAIClient) Stream(ctx context.Context, msgs []Message) (<-chan StreamChunk, error) {
	stream := o.client.Chat.Completions.NewStreaming(ctx, openai.ChatCompletionNewParams{
		Model:    shared.ChatModel(o.model),
		Messages: toOpenAIMessages(msgs),
	})

	out := make(chan StreamChunk, 16)
	go func() {
		defer close(out)
		for stream.Next() {
			chunk := stream.Current()
			if len(chunk.Choices) == 0 {
				continue
			}
			delta := chunk.Choices[0].Delta.Content
			if delta != "" {
				out <- StreamChunk{Delta: delta}
			}
		}
		out <- StreamChunk{Done: true}
	}()
	return out, nil
}

// ---------------------------------------------------------------------------
// Embeddings
// ---------------------------------------------------------------------------

type openAIEmbedder struct {
	client openai.Client
	model  string
}

func newOpenAIEmbedder(apiKey, model string) *openAIEmbedder {
	c := openai.NewClient(option.WithAPIKey(apiKey))
	return &openAIEmbedder{client: c, model: model}
}

func (e *openAIEmbedder) Embed(ctx context.Context, texts []string) ([][]float32, error) {
	if len(texts) == 0 {
		return nil, nil
	}
	resp, err := e.client.Embeddings.New(ctx, openai.EmbeddingNewParams{
		Model: openai.EmbeddingModel(e.model),
		Input: openai.EmbeddingNewParamsInputUnion{OfArrayOfStrings: texts},
	})
	if err != nil {
		return nil, fmt.Errorf("openai embed: %w", err)
	}
	out := make([][]float32, len(resp.Data))
	for i, d := range resp.Data {
		vec := make([]float32, len(d.Embedding))
		for j, f := range d.Embedding {
			vec[j] = float32(f)
		}
		out[i] = vec
	}
	return out, nil
}
