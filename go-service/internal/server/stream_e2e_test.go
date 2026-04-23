package server

import (
	"bufio"
	"bytes"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/joho/godotenv"
)

func loadRepoEnv(t *testing.T) {
	_, here, _, _ := runtime.Caller(0)
	envPath := filepath.Join(filepath.Dir(here), "..", "..", "..", ".env")
	if err := godotenv.Load(envPath); err != nil {
		t.Logf("no .env loaded (%s): %v", envPath, err)
	}
}

// sseEvent is a parsed Server-Sent Event from a streaming response body.
type sseEvent struct {
	Event string
	Data  string
}

// readSSE consumes a stream of `event:`/`data:` blocks until EOF or context.
// We don't validate ordering of fields within a block — SSE allows either.
func readSSE(r io.Reader) ([]sseEvent, error) {
	var events []sseEvent
	br := bufio.NewReader(r)
	var current sseEvent
	for {
		line, err := br.ReadString('\n')
		if line != "" {
			line = strings.TrimRight(line, "\r\n")
			switch {
			case strings.HasPrefix(line, "event: "):
				current.Event = strings.TrimPrefix(line, "event: ")
			case strings.HasPrefix(line, "data: "):
				if current.Data != "" {
					current.Data += "\n"
				}
				current.Data += strings.TrimPrefix(line, "data: ")
			case line == "":
				if current.Event != "" || current.Data != "" {
					events = append(events, current)
					current = sseEvent{}
				}
			}
		}
		if err != nil {
			if current.Event != "" || current.Data != "" {
				events = append(events, current)
			}
			if err == io.EOF {
				return events, nil
			}
			return events, err
		}
	}
}

func TestQueryStream_LiveE2E(t *testing.T) {
	loadRepoEnv(t)
	if testing.Short() {
		t.Skip("short mode")
	}
	if os.Getenv("OPENAI_API_KEY") == "" {
		t.Skip("OPENAI_API_KEY required for embeddings")
	}
	_ = os.Setenv("USE_TEST_DB", "true")
	defer os.Unsetenv("USE_TEST_DB")

	// Quiet logger so test output isn't dominated by node-progress lines.
	silentLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := New(silentLogger)
	ts := httptest.NewServer(srv.Handler())
	defer ts.Close()

	body := bytes.NewBufferString(`{"prompt":"List the 3 most expensive tracks. Include track name and unit price.","db_id":"demo_db_1","result_limit":3}`)
	req, err := http.NewRequest("POST", ts.URL+"/query/stream", body)
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")

	client := &http.Client{Timeout: 180 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("do: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		raw, _ := io.ReadAll(resp.Body)
		t.Fatalf("status %d, body: %s", resp.StatusCode, raw)
	}
	if ct := resp.Header.Get("Content-Type"); !strings.Contains(ct, "text/event-stream") {
		t.Errorf("content-type got %q want text/event-stream", ct)
	}

	events, err := readSSE(resp.Body)
	if err != nil {
		t.Fatalf("read sse: %v", err)
	}
	t.Logf("received %d events", len(events))

	// Sanity expectations:
	// 1. First event is the request_received ack.
	// 2. We see a `complete` event last (or `error` on hard failure).
	// 3. At least one node-status event between them.
	if len(events) == 0 {
		t.Fatal("no SSE events received")
	}

	first := events[0]
	if first.Event != "status" {
		t.Errorf("first event = %q, want status", first.Event)
	}
	var ack SSEStatusEvent
	if err := json.Unmarshal([]byte(first.Data), &ack); err != nil {
		t.Fatalf("decode first event: %v", err)
	}
	if ack.NodeName != "request_received" {
		t.Errorf("first event node_name = %q, want request_received", ack.NodeName)
	}

	last := events[len(events)-1]
	if last.Event != "complete" && last.Event != "error" {
		t.Errorf("last event = %q, want complete or error", last.Event)
	}

	statusCount := 0
	nodeNames := map[string]bool{}
	for _, e := range events {
		if e.Event == "status" {
			statusCount++
			var s SSEStatusEvent
			if err := json.Unmarshal([]byte(e.Data), &s); err == nil {
				nodeNames[s.NodeName] = true
			}
		}
	}
	t.Logf("status events: %d, distinct nodes seen: %d", statusCount, len(nodeNames))
	for n := range nodeNames {
		t.Logf("  - %s", n)
	}

	// Must have visited the core nodes if the workflow completed.
	if last.Event == "complete" {
		var resp QueryResponse
		if err := json.Unmarshal([]byte(last.Data), &resp); err != nil {
			t.Fatalf("decode complete: %v", err)
		}
		t.Logf("query: %s", resp.Query)
		t.Logf("rows: %d (last_step=%s)", len(resp.Result), resp.LastStep)
		if resp.Query == "" {
			t.Error("expected non-empty SQL in complete event")
		}
		for _, want := range []string{"analyze_schema", "filter_schema", "planner", "execute_query"} {
			if !nodeNames[want] {
				t.Errorf("missing expected node %q in status events", want)
			}
		}
	}
}
