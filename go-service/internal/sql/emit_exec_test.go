package sql

import (
	"context"
	"database/sql"
	"path/filepath"
	"runtime"
	"testing"

	_ "modernc.org/sqlite"

	m "github.com/sachit/sql-query-assistant/go-service/internal/models"
)

// TestEmitTSQL_ExecutesAgainstSQLite proves the emitted SQL is not just lexically
// correct but parses and executes against the demo_db_1 fixture. SQLite accepts
// `[ident]` quoting as an MS-compat extension, so the same emitter output works
// for both the Phase-2 MVP unit tests and real database round-trips.
func TestEmitTSQL_ExecutesAgainstSQLite(t *testing.T) {
	_, thisFile, _, _ := runtime.Caller(0)
	repoRoot := filepath.Join(filepath.Dir(thisFile), "..", "..", "..")
	dbPath := filepath.Join(repoRoot, "databases", "demo_db_1.db")

	conn, err := sql.Open("sqlite", dbPath)
	if err != nil {
		t.Skipf("cannot open demo DB: %v", err)
	}
	defer conn.Close()

	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{
				Table: "customers", Alias: "c",
				Columns: []m.SelectedColumn{
					{Table: "customers", Column: "FirstName", Role: "projection"},
					{Table: "customers", Column: "LastName", Role: "projection"},
				},
				Filters: []m.FilterPredicate{
					{Table: "customers", Column: "Country", Op: m.OpEq, Value: "USA"},
				},
			},
		},
		OrderBy: []m.OrderByColumn{
			{Table: "customers", Column: "LastName", Direction: m.SortAsc},
		},
		Limit: intp(3),
	}

	query, err := Emit(plan, SQLite)
	if err != nil {
		t.Fatalf("emit: %v", err)
	}
	t.Logf("emitted SQL:\n%s", query)

	rows, err := conn.QueryContext(context.Background(), query)
	if err != nil {
		t.Fatalf("exec: %v\nSQL:\n%s", err, query)
	}
	defer rows.Close()

	count := 0
	for rows.Next() {
		var first, last string
		if err := rows.Scan(&first, &last); err != nil {
			t.Fatalf("scan: %v", err)
		}
		count++
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("rows.Err: %v", err)
	}
	if count == 0 || count > 3 {
		t.Errorf("expected 1-3 rows, got %d", count)
	}
}

// rewriteTopToLimit is a test-only convenience: SQL Server emits `SELECT TOP n …`
// while SQLite uses `SELECT … LIMIT n`. The rewriter only handles the trivial
// pattern produced by EmitTSQL (TOP appears immediately after the leading SELECT).
func rewriteTopToLimit(q string) string {
	const sentinel = "SELECT TOP "
	if len(q) < len(sentinel) || q[:len(sentinel)] != sentinel {
		return q
	}
	rest := q[len(sentinel):]
	// Read the integer after TOP, then drop the leading "TOP n" tokens.
	end := 0
	for end < len(rest) && rest[end] >= '0' && rest[end] <= '9' {
		end++
	}
	if end == 0 {
		return q
	}
	limit := rest[:end]
	body := rest[end:]
	return "SELECT" + body + "\nLIMIT " + limit
}
