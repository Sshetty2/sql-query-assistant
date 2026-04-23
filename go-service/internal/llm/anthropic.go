package llm

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/anthropics/anthropic-sdk-go"
	"github.com/anthropics/anthropic-sdk-go/option"
)

type anthropicClient struct {
	client anthropic.Client
	model  string
}

func newAnthropicClient(apiKey, model string) *anthropicClient {
	c := anthropic.NewClient(option.WithAPIKey(apiKey))
	return &anthropicClient{client: c, model: model}
}

// splitSystemAndConversation pulls out leading system messages because Anthropic's
// Messages API takes them as a separate top-level argument, unlike OpenAI.
func splitSystemAndConversation(msgs []Message) (system string, convo []anthropic.MessageParam) {
	for _, m := range msgs {
		if m.Role == RoleSystem {
			if system != "" {
				system += "\n\n"
			}
			system += m.Content
			continue
		}
		role := anthropic.MessageParamRoleUser
		if m.Role == RoleAssistant {
			role = anthropic.MessageParamRoleAssistant
		}
		convo = append(convo, anthropic.MessageParam{
			Role:    role,
			Content: []anthropic.ContentBlockParamUnion{anthropic.NewTextBlock(m.Content)},
		})
	}
	return system, convo
}

func (a *anthropicClient) Chat(ctx context.Context, msgs []Message) (string, error) {
	system, convo := splitSystemAndConversation(msgs)
	params := anthropic.MessageNewParams{
		Model:     anthropic.Model(a.model),
		MaxTokens: 4096,
		Messages:  convo,
	}
	if system != "" {
		params.System = []anthropic.TextBlockParam{{Text: system}}
	}

	resp, err := a.client.Messages.New(ctx, params)
	if err != nil {
		return "", fmt.Errorf("anthropic chat: %w", err)
	}
	var text string
	for _, block := range resp.Content {
		if block.Type == "text" {
			text += block.Text
		}
	}
	return text, nil
}

// StructuredOutput coerces Anthropic into a JSON shape via forced tool use:
// we declare a single tool whose input_schema is the caller's JSON schema, set
// tool_choice to that tool, and decode the resulting tool_use input as the
// structured payload. This matches what langchain-anthropic does under the hood.
func (a *anthropicClient) StructuredOutput(ctx context.Context, msgs []Message, schema any, schemaName string, out any) error {
	system, convo := splitSystemAndConversation(msgs)

	// The SDK accepts a typed ToolInputSchemaParam, but its Properties field is
	// `any`, so we can pass our generated JSON schema map directly. We strip the
	// $schema key because Anthropic rejects unknown top-level keys in input_schema.
	schemaMap, ok := schema.(map[string]any)
	if !ok {
		// Round-trip via JSON to coerce arbitrary structs into a map.
		raw, err := json.Marshal(schema)
		if err != nil {
			return fmt.Errorf("marshal schema: %w", err)
		}
		if err := json.Unmarshal(raw, &schemaMap); err != nil {
			return fmt.Errorf("unmarshal schema: %w", err)
		}
	}
	delete(schemaMap, "$schema")
	delete(schemaMap, "$id")

	props, _ := schemaMap["properties"].(map[string]any)
	requiredAny, _ := schemaMap["required"].([]any)
	required := make([]string, 0, len(requiredAny))
	for _, r := range requiredAny {
		if s, ok := r.(string); ok {
			required = append(required, s)
		}
	}

	tool := anthropic.ToolParam{
		Name:        schemaName,
		Description: anthropic.String("Return the requested structured output. Use this tool to respond."),
		InputSchema: anthropic.ToolInputSchemaParam{
			Properties: props,
			Required:   required,
		},
	}
	// Pass the raw schema for any extra fields (definitions, additionalProperties, etc).
	tool.InputSchema.SetExtraFields(schemaMap)

	params := anthropic.MessageNewParams{
		Model:     anthropic.Model(a.model),
		MaxTokens: 8192,
		Messages:  convo,
		Tools: []anthropic.ToolUnionParam{
			{OfTool: &tool},
		},
		ToolChoice: anthropic.ToolChoiceUnionParam{
			OfTool: &anthropic.ToolChoiceToolParam{Name: schemaName},
		},
	}
	if system != "" {
		params.System = []anthropic.TextBlockParam{{Text: system}}
	}

	resp, err := a.client.Messages.New(ctx, params)
	if err != nil {
		return fmt.Errorf("anthropic structured: %w", err)
	}
	for _, block := range resp.Content {
		if block.Type == "tool_use" && block.Name == schemaName {
			if err := json.Unmarshal([]byte(block.Input), out); err != nil {
				return fmt.Errorf("decode tool_use input: %w (raw: %s)", err, string(block.Input))
			}
			return nil
		}
	}
	return fmt.Errorf("anthropic structured: no matching tool_use block in response")
}

// ChatWithTools binds the provided tools to a Messages call. Anthropic's
// API can return both text and tool_use content blocks in one response, so
// we surface both in ToolCallResponse.
func (a *anthropicClient) ChatWithTools(ctx context.Context, msgs []Message, tools []ToolDef) (*ToolCallResponse, error) {
	system, convo := splitSystemAndConversation(msgs)

	anthropicTools := make([]anthropic.ToolUnionParam, 0, len(tools))
	for _, t := range tools {
		// Strip $schema/$id like in StructuredOutput — Anthropic rejects unknown
		// top-level keys in input_schema.
		schemaMap := make(map[string]any, len(t.InputSchema))
		for k, v := range t.InputSchema {
			if k == "$schema" || k == "$id" {
				continue
			}
			schemaMap[k] = v
		}
		props, _ := schemaMap["properties"].(map[string]any)
		requiredAny, _ := schemaMap["required"].([]any)
		required := make([]string, 0, len(requiredAny))
		for _, r := range requiredAny {
			if s, ok := r.(string); ok {
				required = append(required, s)
			}
		}
		tool := anthropic.ToolParam{
			Name:        t.Name,
			Description: anthropic.String(t.Description),
			InputSchema: anthropic.ToolInputSchemaParam{
				Properties: props,
				Required:   required,
			},
		}
		tool.InputSchema.SetExtraFields(schemaMap)
		anthropicTools = append(anthropicTools, anthropic.ToolUnionParam{OfTool: &tool})
	}

	params := anthropic.MessageNewParams{
		Model:     anthropic.Model(a.model),
		MaxTokens: 4096,
		Messages:  convo,
		Tools:     anthropicTools,
	}
	if system != "" {
		params.System = []anthropic.TextBlockParam{{Text: system}}
	}

	resp, err := a.client.Messages.New(ctx, params)
	if err != nil {
		return nil, fmt.Errorf("anthropic chat-with-tools: %w", err)
	}

	out := &ToolCallResponse{}
	for _, block := range resp.Content {
		switch block.Type {
		case "text":
			out.Content += block.Text
		case "tool_use":
			out.ToolCalls = append(out.ToolCalls, ToolCall{
				ID:    block.ID,
				Name:  block.Name,
				Input: []byte(block.Input),
			})
		}
	}
	return out, nil
}

func (a *anthropicClient) Stream(ctx context.Context, msgs []Message) (<-chan StreamChunk, error) {
	system, convo := splitSystemAndConversation(msgs)
	params := anthropic.MessageNewParams{
		Model:     anthropic.Model(a.model),
		MaxTokens: 4096,
		Messages:  convo,
	}
	if system != "" {
		params.System = []anthropic.TextBlockParam{{Text: system}}
	}

	stream := a.client.Messages.NewStreaming(ctx, params)
	out := make(chan StreamChunk, 16)
	go func() {
		defer close(out)
		for stream.Next() {
			ev := stream.Current()
			delta, ok := ev.AsAny().(anthropic.ContentBlockDeltaEvent)
			if !ok {
				continue
			}
			td, ok := delta.Delta.AsAny().(anthropic.TextDelta)
			if !ok {
				continue
			}
			if td.Text != "" {
				out <- StreamChunk{Delta: td.Text}
			}
		}
		out <- StreamChunk{Done: true}
	}()
	return out, nil
}
