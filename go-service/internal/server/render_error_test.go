package server

import (
	"bytes"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// TestRenderError_Accepts verifies the happy path: a typical ErrorBoundary
// payload returns 204 with no body.
func TestRenderError_Accepts(t *testing.T) {
	silent := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := New(silent)
	ts := httptest.NewServer(srv.Handler())
	defer ts.Close()

	body := bytes.NewBufferString(`{
		"section": "Results table",
		"error_message": "Cannot convert undefined or null to object",
		"error_stack": "TypeError: Cannot convert ...\n    at ResultsTable",
		"component_stack": "\n    in ResultsTable\n    in App",
		"user_agent": "Mozilla/5.0 ...",
		"url": "http://localhost:8001/",
		"thread_id": "abc-123",
		"query_id": "def-456"
	}`)

	resp, err := http.Post(ts.URL+"/log/render-error", "application/json", body)
	if err != nil {
		t.Fatalf("post: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusNoContent {
		raw, _ := io.ReadAll(resp.Body)
		t.Errorf("status got %d want 204; body: %s", resp.StatusCode, raw)
	}
}

// TestRenderError_RejectsMissingFields exercises the validator. Missing
// required fields should produce 400, not silent acceptance.
func TestRenderError_RejectsMissingFields(t *testing.T) {
	silent := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := New(silent)
	ts := httptest.NewServer(srv.Handler())
	defer ts.Close()

	cases := []struct {
		name, body string
	}{
		{"empty body", `{}`},
		{"no error_message", `{"section":"X"}`},
		{"no section", `{"error_message":"oops"}`},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			resp, err := http.Post(ts.URL+"/log/render-error", "application/json", bytes.NewBufferString(tc.body))
			if err != nil {
				t.Fatalf("post: %v", err)
			}
			defer resp.Body.Close()
			if resp.StatusCode != http.StatusBadRequest {
				t.Errorf("got %d want 400", resp.StatusCode)
			}
		})
	}
}

// TestRenderError_RejectsOversizedBody verifies the 16 KB cap. A body
// approaching that limit must succeed; a 100 KB body must be rejected
// with 413 (preventing log-flood DoS).
func TestRenderError_RejectsOversizedBody(t *testing.T) {
	silent := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := New(silent)
	ts := httptest.NewServer(srv.Handler())
	defer ts.Close()

	// 50KB stack trace — exceeds 16 KB cap.
	huge := strings.Repeat("a", 50*1024)
	body := bytes.NewBufferString(`{"section":"X","error_message":"oops","error_stack":"` + huge + `"}`)

	resp, err := http.Post(ts.URL+"/log/render-error", "application/json", body)
	if err != nil {
		t.Fatalf("post: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusRequestEntityTooLarge {
		t.Errorf("got %d want 413", resp.StatusCode)
	}
}
