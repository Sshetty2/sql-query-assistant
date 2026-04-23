package chat

import (
	"encoding/json"
	"testing"

	"github.com/sachit/sql-query-assistant/go-service/internal/llm"
)

// collect drains the channel into a slice so assertions can inspect all
// emitted events in order.
func collect(ch chan Event) []Event {
	close(ch)
	var events []Event
	for ev := range ch {
		events = append(events, ev)
	}
	return events
}

func TestHandleRespond_MessageOnly_EmitsTokenAndNoRevisionEvent(t *testing.T) {
	a := &Agent{}
	sess := &Session{}
	out := make(chan Event, 8)

	input, _ := json.Marshal(map[string]any{"message": "hello there"})
	a.handleRespond(llm.ToolCall{Name: RespondToolName, Input: input}, sess, out)

	events := collect(out)
	if len(events) != 1 {
		t.Fatalf("expected 1 event, got %d: %+v", len(events), events)
	}
	if events[0].Type != "token" || events[0].Content != "hello there" {
		t.Errorf("expected token event with message content, got %+v", events[0])
	}
	if len(sess.Messages) != 1 || sess.Messages[0].Content != "hello there" {
		t.Errorf("expected assistant message appended to session, got %+v", sess.Messages)
	}
}

func TestHandleRespond_WithRevision_EmitsSuggestRevisionThenToken(t *testing.T) {
	a := &Agent{}
	sess := &Session{}
	out := make(chan Event, 8)

	input, _ := json.Marshal(map[string]any{
		"message":     "Added the missing artist column.",
		"revised_sql": "SELECT a.name FROM artists a",
		"explanation": "Add artist.name",
	})
	a.handleRespond(llm.ToolCall{Name: RespondToolName, Input: input}, sess, out)

	events := collect(out)
	if len(events) != 2 {
		t.Fatalf("expected 2 events, got %d: %+v", len(events), events)
	}
	if events[0].Type != "suggest_revision" {
		t.Errorf("first event should be suggest_revision, got %+v", events[0])
	}
	if events[0].RevisedSQL != "SELECT a.name FROM artists a" {
		t.Errorf("revised_sql not propagated: %+v", events[0])
	}
	if events[0].Explanation != "Add artist.name" {
		t.Errorf("explanation not propagated: %+v", events[0])
	}
	if events[1].Type != "token" || events[1].Content != "Added the missing artist column." {
		t.Errorf("second event should be token with message, got %+v", events[1])
	}
}

func TestHandleRespond_RevisionWithoutExplanation_GetsSynthesizedExplanation(t *testing.T) {
	a := &Agent{}
	sess := &Session{}
	out := make(chan Event, 8)

	input, _ := json.Marshal(map[string]any{
		"message":     "Fixed it.",
		"revised_sql": "SELECT 1",
	})
	a.handleRespond(llm.ToolCall{Name: RespondToolName, Input: input}, sess, out)

	events := collect(out)
	var rev *Event
	for i := range events {
		if events[i].Type == "suggest_revision" {
			rev = &events[i]
			break
		}
	}
	if rev == nil {
		t.Fatalf("expected suggest_revision event, got %+v", events)
	}
	if rev.Explanation == "" {
		t.Errorf("expected synthesized explanation when model omits it, got empty")
	}
}

func TestHandleRespond_InvalidArgs_EmitsToolError(t *testing.T) {
	a := &Agent{}
	sess := &Session{}
	out := make(chan Event, 8)

	a.handleRespond(llm.ToolCall{
		Name:  RespondToolName,
		Input: []byte("not json"),
	}, sess, out)

	events := collect(out)
	if len(events) != 1 || events[0].Type != "tool_error" {
		t.Fatalf("expected single tool_error event, got %+v", events)
	}
}

func TestAllTools_ContainsRunQueryAndRespond(t *testing.T) {
	names := map[string]bool{}
	for _, t := range AllTools() {
		names[t.Name] = true
	}
	if !names[RunQueryToolName] || !names[RespondToolName] {
		t.Errorf("AllTools missing expected tools; got %v", names)
	}
	if len(names) != 2 {
		t.Errorf("AllTools should have exactly 2 tools, got %d: %v", len(names), names)
	}
}

func TestRespondOnlyTools_IsJustRespond(t *testing.T) {
	tools := RespondOnlyTools()
	if len(tools) != 1 || tools[0].Name != RespondToolName {
		t.Errorf("RespondOnlyTools should be [respond], got %+v", tools)
	}
}

func TestRespondTool_MessageIsOnlyRequiredField(t *testing.T) {
	tool := respondTool()
	schema := tool.InputSchema
	required, ok := schema["required"].([]any)
	if !ok {
		t.Fatalf("required field missing or wrong type: %T", schema["required"])
	}
	if len(required) != 1 || required[0] != "message" {
		t.Errorf("only `message` should be required, got %v", required)
	}
	props, _ := schema["properties"].(map[string]any)
	for _, field := range []string{"message", "revised_sql", "explanation"} {
		if _, present := props[field]; !present {
			t.Errorf("property %q missing from schema", field)
		}
	}
}
