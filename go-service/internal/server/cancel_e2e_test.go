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

// TestCancel_E2E starts a real query, waits a moment, then sends a /cancel
// for the same page session and verifies the stream terminates within one
// node boundary (i.e. produces an error/cancelled SSE event before normal completion).
//
// Skipped when API keys are missing or in -short mode — the test depends on
// the LLM/embedding round-trips taking long enough that cancellation can
// reliably happen mid-flight.
func TestCancel_E2E(t *testing.T) {
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

	// Use a 64-hex page session ID (matches Python's regex).
	pageSession := strings.Repeat("c", 64)

	body := bytes.NewBufferString(`{"prompt":"List the 5 most expensive tracks","db_id":"demo_db_1","result_limit":5}`)
	req, err := http.NewRequest("POST", ts.URL+"/query/stream", body)
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")
	req.Header.Set("x-page-session", pageSession)

	client := &http.Client{Timeout: 60 * time.Second}

	// Fire the cancel after a short delay — long enough that the workflow
	// has registered its session, short enough that we cancel mid-pipeline.
	go func() {
		time.Sleep(2 * time.Second)
		cancelBody := bytes.NewBufferString(`{"session_id":"` + pageSession + `"}`)
		cancelReq, _ := http.NewRequest("POST", ts.URL+"/cancel", cancelBody)
		cancelReq.Header.Set("Content-Type", "application/json")
		resp, err := client.Do(cancelReq)
		if err != nil {
			t.Errorf("cancel request: %v", err)
			return
		}
		defer resp.Body.Close()
		var out map[string]any
		_ = json.NewDecoder(resp.Body).Decode(&out)
		t.Logf("/cancel response: %v", out)
	}()

	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("stream request: %v", err)
	}
	defer resp.Body.Close()

	events, err := readSSE(resp.Body)
	if err != nil {
		t.Fatalf("read sse: %v", err)
	}
	t.Logf("received %d events", len(events))

	// Expect to see at least one "error" status with message "cancelled" OR an
	// `error` event itself before a `complete`. If we got `complete` (full
	// success), the cancellation didn't take effect — fail.
	sawCancelled := false
	sawComplete := false
	for _, e := range events {
		if e.Event == "error" {
			t.Logf("error event: %s", e.Data)
			sawCancelled = true
		}
		if e.Event == "status" {
			var s SSEStatusEvent
			if err := json.Unmarshal([]byte(e.Data), &s); err == nil {
				if s.NodeStatus == "error" && strings.Contains(s.NodeMessage, "cancel") {
					sawCancelled = true
				}
			}
		}
		if e.Event == "complete" {
			sawComplete = true
		}
	}

	if !sawCancelled && sawComplete {
		t.Errorf("workflow completed despite /cancel — cancellation didn't fire. events=%d", len(events))
	} else if !sawCancelled && !sawComplete {
		t.Errorf("neither cancellation nor completion observed. events=%d", len(events))
	}
}

// TestCancelHandler_BadRequest exercises the validation paths of POST /cancel
// without spinning up the rest of the server.
func TestCancelHandler_BadRequest(t *testing.T) {
	silentLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := New(silentLogger)
	ts := httptest.NewServer(srv.Handler())
	defer ts.Close()

	cases := []struct {
		name     string
		body     string
		wantCode int
	}{
		{"empty body", `{}`, http.StatusBadRequest},
		{"non-hex session", `{"session_id":"not-hex"}`, http.StatusBadRequest},
		{"too short", `{"session_id":"abcd"}`, http.StatusBadRequest},
		{"valid but unknown", `{"session_id":"` + strings.Repeat("d", 64) + `"}`, http.StatusOK},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			resp, err := http.Post(ts.URL+"/cancel", "application/json", bytes.NewBufferString(tc.body))
			if err != nil {
				t.Fatalf("post: %v", err)
			}
			defer resp.Body.Close()
			if resp.StatusCode != tc.wantCode {
				raw, _ := io.ReadAll(resp.Body)
				t.Errorf("got %d, want %d (body: %s)", resp.StatusCode, tc.wantCode, raw)
			}
		})
	}
}
