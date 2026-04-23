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

// TestQueryStream_ReturnsQueryID is the regression test for the bug where
// /query/stream's `complete` event was missing the query_id. The frontend's
// chat panel needs both thread_id AND query_id to know it should route
// follow-ups via /query/chat instead of starting a fresh query.
//
// Without this, every chat message lands at /query/stream, which is exactly
// what the user reported in the production logs.
func TestQueryStream_ReturnsQueryID(t *testing.T) {
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

	// Find the complete event.
	var completeData []byte
	for _, e := range events {
		if e.Event == "complete" {
			completeData = []byte(e.Data)
			break
		}
	}
	if completeData == nil {
		t.Fatalf("no complete event in stream (%d events)", len(events))
	}

	var qr QueryResponse
	if err := json.Unmarshal(completeData, &qr); err != nil {
		t.Fatalf("decode complete: %v", err)
	}

	if qr.ThreadID == "" {
		t.Errorf("thread_id missing from complete event")
	}
	if qr.QueryID == "" {
		t.Errorf("query_id missing from complete event — frontend chat panel will route follow-ups to /query/stream instead of /query/chat")
	}
	t.Logf("thread_id=%s query_id=%s", qr.ThreadID, qr.QueryID)
}
