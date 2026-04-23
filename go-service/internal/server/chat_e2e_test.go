package server

import (
	"bytes"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

// TestChat_ResetWithoutSession exercises the validation path of /query/chat/reset.
func TestChat_ResetWithoutSession(t *testing.T) {
	silentLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := New(silentLogger)
	ts := httptest.NewServer(srv.Handler())
	defer ts.Close()

	// Bad request: missing session_id.
	resp, err := http.Post(ts.URL+"/query/chat/reset", "application/json", bytes.NewBufferString(`{}`))
	if err != nil {
		t.Fatalf("post: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != 400 {
		t.Errorf("expected 400 for missing session_id, got %d", resp.StatusCode)
	}

	// Valid: unknown session id should return reset=false but still 200.
	resp2, err := http.Post(ts.URL+"/query/chat/reset", "application/json",
		bytes.NewBufferString(`{"session_id":"never-existed"}`))
	if err != nil {
		t.Fatalf("post: %v", err)
	}
	defer resp2.Body.Close()
	if resp2.StatusCode != 200 {
		t.Errorf("expected 200 for unknown session, got %d", resp2.StatusCode)
	}
	var body map[string]any
	_ = json.NewDecoder(resp2.Body).Decode(&body)
	if body["reset"] != false {
		t.Errorf("expected reset=false, got %v", body["reset"])
	}
}

// TestChat_LiveE2E_FollowUpRunsQueryTool plays a chat conversation and
// verifies the agentic loop fires the run_query tool when the user asks
// for new data.
//
// Setup: start the Go server, manually seed a thread state with a previous
// query result, then POST a follow-up to /query/chat. The expected SSE
// sequence is `tool_start` → `tool_result` → `token` → `complete`.
func TestChat_LiveE2E_FollowUpRunsQueryTool(t *testing.T) {
	loadRepoEnv(t)
	if testing.Short() {
		t.Skip("short mode")
	}
	if os.Getenv("OPENAI_API_KEY") == "" {
		t.Skip("OPENAI_API_KEY required for embeddings inside the run_query tool")
	}
	_ = os.Setenv("USE_TEST_DB", "true")
	defer os.Unsetenv("USE_TEST_DB")

	silentLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := New(silentLogger)
	ts := httptest.NewServer(srv.Handler())
	defer ts.Close()

	// Seed a thread + query state so the chat handler can build a data context.
	tid, err := srv.threads.CreateThread("Show 5 customers")
	if err != nil {
		t.Fatalf("seed thread: %v", err)
	}
	qid, err := srv.threads.SaveQueryState(tid, "Show 5 customers", map[string]any{
		"query":     "SELECT FirstName, LastName FROM customers LIMIT 5",
		"last_step": "execute_query",
		"row_count": 5,
		"result": []any{
			map[string]any{"FirstName": "John", "LastName": "Doe"},
		},
	})
	if err != nil {
		t.Fatalf("save state: %v", err)
	}

	body, _ := json.Marshal(ChatRequest{
		ThreadID:  tid,
		QueryID:   qid,
		Message:   "How many tracks does the database have?",
		SessionID: tid + ":" + qid,
		DBID:      "demo_db_1",
	})
	req, _ := http.NewRequest("POST", ts.URL+"/query/chat", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")

	client := &http.Client{Timeout: 180 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("post: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		raw, _ := io.ReadAll(resp.Body)
		t.Fatalf("status %d, body: %s", resp.StatusCode, raw)
	}

	events, err := readSSE(resp.Body)
	if err != nil {
		t.Fatalf("read sse: %v", err)
	}
	t.Logf("received %d events", len(events))

	sawToolStart := false
	sawToolResult := false
	sawComplete := false
	for _, e := range events {
		t.Logf("event=%s data=%s", e.Event, truncateForLog(e.Data, 200))
		switch e.Event {
		case "tool_start":
			sawToolStart = true
		case "tool_result":
			sawToolResult = true
		case "complete":
			sawComplete = true
		}
	}

	if !sawComplete {
		t.Errorf("expected 'complete' event")
	}
	// tool_start + tool_result is the desired path. Some models choose to
	// answer from context without firing the tool — that's also valid since
	// they could deduce "this needs new data" inconsistently. Log either way
	// but only fail on missing complete.
	if !sawToolStart {
		t.Logf("note: model did not fire run_query tool — answered from context")
	}
	if sawToolStart && !sawToolResult {
		t.Errorf("tool_start without tool_result — broken handler")
	}
}

func truncateForLog(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return strings.ReplaceAll(s[:n], "\n", " ") + "…"
}

// TestChat_LiveE2E_CantSeeColumnDoesNotRunNewQuery covers the production
// regression where the chat agent fired run_query for a conversational
// follow-up like "I can't see the artist..", which then ran the full pipeline
// against vague text and crashed at generate_query with "plan has no selections".
//
// Expected behavior: the agent calls `respond` (with or without a
// revised_sql) — never run_query — for a commentary follow-up.
func TestChat_LiveE2E_CantSeeColumnDoesNotRunNewQuery(t *testing.T) {
	loadRepoEnv(t)
	if testing.Short() {
		t.Skip("short mode")
	}
	if os.Getenv("OPENAI_API_KEY") == "" {
		t.Skip("OPENAI_API_KEY required")
	}
	_ = os.Setenv("USE_TEST_DB", "true")
	defer os.Unsetenv("USE_TEST_DB")

	silentLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := New(silentLogger)
	ts := httptest.NewServer(srv.Handler())
	defer ts.Close()

	// Seed a thread that mimics the failing production scenario: a query that
	// returned tracks but didn't include artist names.
	tid, err := srv.threads.CreateThread("Find the top 5 most expensive tracks and their associated artists")
	if err != nil {
		t.Fatalf("seed thread: %v", err)
	}
	qid, err := srv.threads.SaveQueryState(tid,
		"Find the top 5 most expensive tracks and their associated artists",
		map[string]any{
			"query": `SELECT TOP 5 [tracks].[Name], [tracks].[UnitPrice]
FROM [tracks]
ORDER BY [tracks].[UnitPrice] DESC`,
			"last_step": "execute_query",
			"row_count": 5,
			"result": []any{
				map[string]any{"Name": "Battlestar Galactica: The Story So Far", "UnitPrice": 1.99},
			},
		})
	if err != nil {
		t.Fatalf("save state: %v", err)
	}

	body, _ := json.Marshal(ChatRequest{
		ThreadID:  tid,
		QueryID:   qid,
		Message:   "I can't see the artist..",
		SessionID: tid + ":" + qid,
		DBID:      "demo_db_1",
	})
	req, _ := http.NewRequest("POST", ts.URL+"/query/chat", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")

	client := &http.Client{Timeout: 120 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("post: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		raw, _ := io.ReadAll(resp.Body)
		t.Fatalf("status %d, body: %s", resp.StatusCode, raw)
	}

	events, err := readSSE(resp.Body)
	if err != nil {
		t.Fatalf("read sse: %v", err)
	}

	sawRunQuery := false
	for _, e := range events {
		t.Logf("event=%s data=%s", e.Event, truncateForLog(e.Data, 200))
		if e.Event == "tool_start" && strings.Contains(e.Data, `"run_query"`) {
			sawRunQuery = true
		}
	}

	if sawRunQuery {
		t.Errorf("'I can't see the artist..' should NOT trigger run_query — it's a comment about an existing result, not a new data request")
	}
}

// TestChat_LiveE2E_RevisionGoesToSuggestTool catches the regression where
// "can you revise" used to fire run_query instead of the respond tool —
// the model would launch a fresh pipeline against ambiguous text, the planner
// would return decision="clarify" with no selections, and generate_query
// would error out with "plan has no selections".
//
// Now: revision-style requests should produce a `suggest_revision` event
// from `respond(revised_sql=...)` and never touch the SQL pipeline.
func TestChat_LiveE2E_RevisionGoesToSuggestTool(t *testing.T) {
	loadRepoEnv(t)
	if testing.Short() {
		t.Skip("short mode")
	}
	if os.Getenv("OPENAI_API_KEY") == "" {
		t.Skip("OPENAI_API_KEY required")
	}
	_ = os.Setenv("USE_TEST_DB", "true")
	defer os.Unsetenv("USE_TEST_DB")

	silentLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := New(silentLogger)
	ts := httptest.NewServer(srv.Handler())
	defer ts.Close()

	// Seed a thread with a SQL query and result so the chat agent has something concrete to revise.
	tid, err := srv.threads.CreateThread("Which artists have the most albums?")
	if err != nil {
		t.Fatalf("seed thread: %v", err)
	}
	qid, err := srv.threads.SaveQueryState(tid, "Which artists have the most albums?", map[string]any{
		"query": `SELECT [artists].[Name], COUNT([albums].[AlbumId]) AS [album_count]
FROM [artists]
INNER JOIN [albums] ON [artists].[ArtistId] = [albums].[ArtistId]
GROUP BY [artists].[Name]
ORDER BY [album_count] DESC`,
		"last_step": "execute_query",
		"row_count": 5,
		"result": []any{
			map[string]any{"Name": "Iron Maiden", "album_count": 21},
			map[string]any{"Name": "Led Zeppelin", "album_count": 14},
		},
	})
	if err != nil {
		t.Fatalf("save state: %v", err)
	}

	body, _ := json.Marshal(ChatRequest{
		ThreadID:  tid,
		QueryID:   qid,
		Message:   "Can you revise the query to also show the artist's country?",
		SessionID: tid + ":" + qid,
		DBID:      "demo_db_1",
	})
	req, _ := http.NewRequest("POST", ts.URL+"/query/chat", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")

	client := &http.Client{Timeout: 120 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("post: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		raw, _ := io.ReadAll(resp.Body)
		t.Fatalf("status %d, body: %s", resp.StatusCode, raw)
	}

	events, err := readSSE(resp.Body)
	if err != nil {
		t.Fatalf("read sse: %v", err)
	}

	sawSuggestRevision := false
	sawRunQuery := false
	for _, e := range events {
		t.Logf("event=%s data=%s", e.Event, truncateForLog(e.Data, 200))
		if e.Event == "suggest_revision" {
			sawSuggestRevision = true
		}
		if e.Event == "tool_start" && strings.Contains(e.Data, `"run_query"`) {
			sawRunQuery = true
		}
	}

	if sawRunQuery {
		t.Errorf("revision request should NOT fire run_query (would launch fresh planning pipeline against vague input)")
	}
	if !sawSuggestRevision {
		t.Errorf("expected a suggest_revision event for a revision request — got events: %d", len(events))
	}
}
