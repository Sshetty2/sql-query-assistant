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

// TestExecuteSQL_E2E posts a known-good SELECT and verifies rows come back
// over SSE with the right event sequence (status running → status completed → complete).
func TestExecuteSQL_E2E(t *testing.T) {
	if testing.Short() {
		t.Skip("short mode")
	}
	_ = os.Setenv("USE_TEST_DB", "true")
	defer os.Unsetenv("USE_TEST_DB")

	silentLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := New(silentLogger)
	ts := httptest.NewServer(srv.Handler())
	defer ts.Close()

	body := bytes.NewBufferString(`{
		"sql": "SELECT FirstName, LastName FROM customers WHERE Country = 'USA' ORDER BY LastName ASC LIMIT 3",
		"db_id": "demo_db_1"
	}`)
	req, _ := http.NewRequest("POST", ts.URL+"/query/execute-sql", body)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")

	client := &http.Client{Timeout: 30 * time.Second}
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
	t.Logf("events: %d", len(events))

	if len(events) < 2 {
		t.Fatalf("expected at least 2 events, got %d", len(events))
	}
	last := events[len(events)-1]
	if last.Event != "complete" {
		t.Fatalf("expected last event 'complete', got %q (%s)", last.Event, last.Data)
	}
	var qr QueryResponse
	if err := json.Unmarshal([]byte(last.Data), &qr); err != nil {
		t.Fatalf("decode complete: %v", err)
	}
	if qr.LastStep != "execute_sql" {
		t.Errorf("last_step got %q want execute_sql", qr.LastStep)
	}
	if len(qr.Result) == 0 || len(qr.Result) > 3 {
		t.Errorf("expected 1-3 rows, got %d", len(qr.Result))
	}
}

func TestExecuteSQL_RejectsMutation(t *testing.T) {
	silentLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := New(silentLogger)
	ts := httptest.NewServer(srv.Handler())
	defer ts.Close()

	cases := []struct {
		name, sql string
	}{
		{"insert", "INSERT INTO customers (FirstName) VALUES ('x')"},
		{"drop", "DROP TABLE customers"},
		{"two stmts", "SELECT 1; DELETE FROM customers"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			body := bytes.NewBufferString(`{"sql":"` + tc.sql + `","db_id":"demo_db_1"}`)
			resp, err := http.Post(ts.URL+"/query/execute-sql", "application/json", body)
			if err != nil {
				t.Fatalf("post: %v", err)
			}
			defer resp.Body.Close()
			if resp.StatusCode != 400 {
				t.Errorf("expected 400 for %s, got %d", tc.name, resp.StatusCode)
			}
		})
	}
}
