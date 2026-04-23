package server

import (
	"bytes"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"
)

// TestQueryStream_PromptContext verifies the SSE status events for LLM-driven
// nodes (pre_planner, planner) include a `prompt_context.messages` field so
// the frontend's PromptViewer can render the actual LLM input. Mirrors the
// Python service's behavior where every LLM-using node emits prompt context.
func TestQueryStream_PromptContext(t *testing.T) {
	loadRepoEnv(t)
	if testing.Short() {
		t.Skip("short mode")
	}
	if os.Getenv("OPENAI_API_KEY") == "" {
		t.Skip("OPENAI_API_KEY required for embeddings")
	}
	_ = os.Setenv("USE_TEST_DB", "true")
	defer os.Unsetenv("USE_TEST_DB")

	silentLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := New(silentLogger)
	ts := httptest.NewServer(srv.Handler())
	defer ts.Close()

	body := bytes.NewBufferString(`{"prompt":"List 3 customers","db_id":"demo_db_1","result_limit":3}`)
	req, _ := http.NewRequest("POST", ts.URL+"/query/stream", body)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")

	client := &http.Client{Timeout: 120 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("post: %v", err)
	}
	defer resp.Body.Close()

	events, err := readSSE(resp.Body)
	if err != nil {
		t.Fatalf("read sse: %v", err)
	}

	// Walk status events looking for pre_planner/planner with prompt_context.
	nodesWithPrompt := map[string]bool{}
	for _, e := range events {
		if e.Event != "status" {
			continue
		}
		var s SSEStatusEvent
		if err := json.Unmarshal([]byte(e.Data), &s); err != nil {
			continue
		}
		if s.NodeStatus != "completed" {
			continue
		}
		pc, ok := s.NodeMetadata["prompt_context"].(map[string]any)
		if !ok {
			continue
		}
		msgs, ok := pc["messages"].([]any)
		if !ok || len(msgs) == 0 {
			t.Errorf("%s prompt_context has no messages", s.NodeName)
			continue
		}
		// Each message must have role + content.
		for i, raw := range msgs {
			m, ok := raw.(map[string]any)
			if !ok {
				t.Errorf("%s message %d not an object", s.NodeName, i)
				continue
			}
			if m["role"] == nil || m["role"] == "" {
				t.Errorf("%s message %d missing role", s.NodeName, i)
			}
			if m["content"] == nil || m["content"] == "" {
				t.Errorf("%s message %d missing content", s.NodeName, i)
			}
		}
		nodesWithPrompt[s.NodeName] = true
	}

	for _, want := range []string{"pre_planner", "planner"} {
		if !nodesWithPrompt[want] {
			t.Errorf("%s status event missing prompt_context", want)
		}
	}
	t.Logf("nodes that emitted prompt_context: %v", nodesWithPrompt)
}
