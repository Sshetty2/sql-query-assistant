package llm

import (
	"context"
	"database/sql"
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"

	_ "modernc.org/sqlite"

	m "github.com/sachit/sql-query-assistant/go-service/internal/models"
	emitter "github.com/sachit/sql-query-assistant/go-service/internal/sql"
)

// TestEndToEnd_PlanToSQLToRows is the smallest possible proof of the Phase 3
// architecture: ask Claude (via the same factory the workflow nodes will use)
// to plan a query, hand its PlannerOutput to the deterministic emitter, then
// execute the resulting SQL against the demo SQLite DB and read rows back.
//
// The Phase 5 workflow graph will sequence this same flow as
// pre_planner → planner → generate_query → execute_query, but here we exercise
// the seam with one round-trip so regressions in any of the three layers fail
// fast.
func TestEndToEnd_PlanToSQLToRows(t *testing.T) {
	loadRepoEnv(t)
	if testing.Short() {
		t.Skip("skipping live e2e test in -short mode")
	}
	if os.Getenv("ANTHROPIC_API_KEY") == "" && os.Getenv("OPENAI_API_KEY") == "" {
		t.Skip("no API keys")
	}

	client, err := NewForStage(StagePlanning)
	if err != nil {
		t.Skipf("planner client: %v", err)
	}
	schema, err := m.PlannerOutputSchema()
	if err != nil {
		t.Fatalf("schema: %v", err)
	}

	msgs := []Message{
		{Role: RoleSystem, Content: "You are a SQL query planner. Use the provided tool to return a structured plan. Only use exact table and column names from the schema."},
		{Role: RoleUser, Content: `Schema:
- table customers (CustomerId INTEGER PK, FirstName NVARCHAR(40), LastName NVARCHAR(40), Country NVARCHAR(40))

Question: List the first names and last names of every customer in the USA, ordered by LastName ascending. Use decision='proceed'.`},
	}

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	var plan m.PlannerOutput
	if err := client.StructuredOutput(ctx, msgs, schema, "PlannerOutput", &plan); err != nil {
		t.Fatalf("plan: %v", err)
	}
	t.Logf("decision: %s", plan.Decision)
	t.Logf("intent: %s", plan.IntentSummary)

	sqlStr, err := emitter.Emit(&plan, emitter.SQLite)
	if err != nil {
		t.Fatalf("emit: %v", err)
	}
	t.Logf("generated SQL:\n%s", sqlStr)

	_, here, _, _ := runtime.Caller(0)
	dbPath := filepath.Join(filepath.Dir(here), "..", "..", "..", "databases", "demo_db_1.db")
	conn, err := sql.Open("sqlite", dbPath)
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer conn.Close()

	rows, err := conn.QueryContext(ctx, sqlStr)
	if err != nil {
		t.Fatalf("exec: %v\nSQL:\n%s", err, sqlStr)
	}
	defer rows.Close()

	count := 0
	for rows.Next() {
		count++
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("rows.Err: %v", err)
	}
	t.Logf("returned rows: %d", count)
	if count == 0 {
		t.Errorf("expected at least one USA customer; got 0 — possible plan/schema mismatch")
	}
}

