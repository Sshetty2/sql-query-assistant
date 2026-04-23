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

	"github.com/sachit/sql-query-assistant/go-service/internal/models"
)

// TestPatch_E2E proves the patch round-trip works end-to-end against a real
// demo DB: build a plan in code (no LLM needed), POST a remove_column patch,
// and verify the SSE stream completes with fewer columns in the result.
//
// We don't go through the full /query → /query/patch flow because that would
// pull in two LLM calls. The pure patch handler doesn't need them.
func TestPatch_E2E(t *testing.T) {
	if testing.Short() {
		t.Skip("short mode")
	}
	_ = os.Setenv("USE_TEST_DB", "true")
	defer os.Unsetenv("USE_TEST_DB")

	silentLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := New(silentLogger)
	ts := httptest.NewServer(srv.Handler())
	defer ts.Close()

	// Hand-built plan: SELECT FirstName, LastName, Email FROM customers WHERE Country='USA' LIMIT 5
	originalPlan := models.PlannerOutput{
		Decision: models.DecisionProceed,
		Selections: []models.TableSelection{
			{
				Table: "customers",
				Columns: []models.SelectedColumn{
					{Table: "customers", Column: "FirstName", Role: "projection"},
					{Table: "customers", Column: "LastName", Role: "projection"},
					{Table: "customers", Column: "Email", Role: "projection"},
				},
				Filters: []models.FilterPredicate{
					{Table: "customers", Column: "Country", Op: models.OpEq, Value: "USA"},
				},
			},
		},
		Limit: intpHelper(5),
	}

	// Filtered schema must include the columns the patch can manipulate.
	filteredSchema := []map[string]any{
		{
			"table_name": "customers",
			"columns": []any{
				map[string]any{"column_name": "CustomerId", "data_type": "INTEGER", "is_nullable": false},
				map[string]any{"column_name": "FirstName", "data_type": "NVARCHAR(40)", "is_nullable": false},
				map[string]any{"column_name": "LastName", "data_type": "NVARCHAR(40)", "is_nullable": false},
				map[string]any{"column_name": "Email", "data_type": "NVARCHAR(60)", "is_nullable": true},
				map[string]any{"column_name": "Country", "data_type": "NVARCHAR(40)", "is_nullable": true},
			},
		},
	}

	body, _ := json.Marshal(PatchRequest{
		ThreadID:     "test-thread-1",
		UserQuestion: "List USA customers",
		PatchOperation: models.PatchOperation{
			Operation: "remove_column",
			Table:     "customers",
			Column:    "Email",
		},
		ExecutedPlan:   &originalPlan,
		FilteredSchema: filteredSchema,
		DBID:           "demo_db_1",
	})

	req, _ := http.NewRequest("POST", ts.URL+"/query/patch", bytes.NewReader(body))
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
	t.Logf("received %d events", len(events))

	last := events[len(events)-1]
	if last.Event != "complete" {
		t.Fatalf("expected last event 'complete', got %q (%s)", last.Event, last.Data)
	}
	var qr QueryResponse
	if err := json.Unmarshal([]byte(last.Data), &qr); err != nil {
		t.Fatalf("decode complete: %v", err)
	}

	t.Logf("emitted SQL after patch:\n%s", qr.Query)

	// remove_column should have stripped Email from the SELECT list.
	if strings.Contains(strings.ToLower(qr.Query), "[email]") {
		t.Errorf("Email column should not appear in SQL after remove_column patch:\n%s", qr.Query)
	}
	if !strings.Contains(qr.Query, "[FirstName]") || !strings.Contains(qr.Query, "[LastName]") {
		t.Errorf("expected FirstName + LastName to remain, got:\n%s", qr.Query)
	}
	if len(qr.Result) == 0 {
		t.Error("expected non-empty result rows")
	}
	// data_summary should also be present (Phase 9 wiring through patch path).
	if qr.DataSummary == nil {
		t.Error("expected data_summary in patch response")
	}
}

func intpHelper(i int) *int { return &i }
