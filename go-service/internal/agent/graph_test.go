package agent

import (
	"context"
	"encoding/json"
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

// TestRunQuery_E2E runs the full workflow end-to-end against demo_db_1 with
// USE_TEST_DB=true. Skipped without API keys.
func TestRunQuery_E2E(t *testing.T) {
	loadRepoEnv(t)
	if testing.Short() {
		t.Skip("short mode")
	}
	if os.Getenv("OPENAI_API_KEY") == "" {
		t.Skip("OPENAI_API_KEY not set")
	}
	if os.Getenv("ANTHROPIC_API_KEY") == "" && os.Getenv("OPENAI_API_KEY") == "" {
		t.Skip("no chat API keys")
	}

	// Force test-DB mode so the orchestrator opens the SQLite demo files.
	if err := os.Setenv("USE_TEST_DB", "true"); err != nil {
		t.Fatalf("setenv: %v", err)
	}
	defer os.Unsetenv("USE_TEST_DB")

	st := &State{
		UserQuestion: "List the 5 most expensive tracks. Include track name and unit price.",
		DBID:         "demo_db_1",
		SortOrder:    SortDefault,
		ResultLimit:  5,
		TimeFilter:   TimeAll,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 120*time.Second)
	defer cancel()

	statusEvents := []StatusUpdate{}
	final := RunQuery(ctx, st, func(u StatusUpdate) {
		statusEvents = append(statusEvents, u)
	})

	t.Logf("emitted %d status events; last step: %s", len(statusEvents), final.LastStep)
	t.Logf("strategy: %s", truncate(final.PrePlanStrategy, 200))
	t.Logf("query: %s", final.Query)
	t.Logf("rows: %d", len(final.Result))
	if len(final.Result) > 0 {
		first, _ := json.Marshal(final.Result[0])
		t.Logf("first row: %s", first)
	}
	if len(final.Errors) > 0 {
		t.Logf("errors: %v", final.Errors)
	}

	if final.PlannerOutput == nil {
		t.Fatalf("expected planner output, got nil")
	}
	if final.Query == "" {
		t.Fatalf("expected non-empty query")
	}
	// Soft assertion: with retries, we should usually get rows for this
	// straightforward question. If we didn't, surface the iteration counts.
	if len(final.Result) == 0 {
		t.Errorf("expected rows; error_iter=%d refinement_iter=%d termination=%q",
			final.ErrorIteration, final.RefinementIteration, final.TerminationReason)
	} else if len(final.Result) > 5 {
		t.Errorf("expected ≤5 rows (LIMIT 5), got %d", len(final.Result))
	}
}

func truncate(s string, n int) string {
	s = strings.TrimSpace(s)
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}
