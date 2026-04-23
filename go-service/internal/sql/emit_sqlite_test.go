package sql

import (
	"strings"
	"testing"

	m "github.com/sachit/sql-query-assistant/go-service/internal/models"
)

// SQLite-specific emitter tests. The bulk of the emitter is tested in
// emit_test.go (T-SQL); this file focuses on dialect-divergent behavior:
// LIMIT placement and the absence of TOP.

func TestEmitSQLite_BasicSelect(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{
				Table:   "tracks",
				Columns: []m.SelectedColumn{{Table: "tracks", Column: "Name", Role: "projection"}},
			},
		},
	}
	got, err := Emit(plan, SQLite)
	if err != nil {
		t.Fatal(err)
	}
	want := `SELECT
  [tracks].[Name]
FROM [tracks]`
	if normalize(got) != normalize(want) {
		t.Errorf("SQLite SELECT mismatch:\ngot:  %s\nwant: %s", got, want)
	}
}

func TestEmitSQLite_LimitTrailing(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{
				Table:   "tracks",
				Columns: []m.SelectedColumn{{Table: "tracks", Column: "Name", Role: "projection"}},
			},
		},
		Limit: intp(10),
	}
	got, err := Emit(plan, SQLite)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "LIMIT 10") {
		t.Errorf("expected trailing LIMIT 10, got:\n%s", got)
	}
	if strings.Contains(got, "TOP") {
		t.Errorf("SQLite must not emit TOP, got:\n%s", got)
	}
	// LIMIT should appear AFTER ORDER BY-style trailers (we have none here, so just check it's last).
	if !strings.HasSuffix(strings.TrimSpace(got), "LIMIT 10") {
		t.Errorf("LIMIT should be the final line, got:\n%s", got)
	}
}

func TestEmitSQLite_LimitWithOrderBy(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{
				Table:   "tracks",
				Columns: []m.SelectedColumn{{Table: "tracks", Column: "Name", Role: "projection"}},
			},
		},
		OrderBy: []m.OrderByColumn{
			{Table: "tracks", Column: "UnitPrice", Direction: m.SortDesc},
		},
		Limit: intp(5),
	}
	got, err := Emit(plan, SQLite)
	if err != nil {
		t.Fatal(err)
	}
	want := `SELECT
  [tracks].[Name]
FROM [tracks]
ORDER BY [tracks].[UnitPrice] DESC
LIMIT 5`
	if normalize(got) != normalize(want) {
		t.Errorf("SQLite ORDER BY + LIMIT mismatch:\ngot:  %s\nwant: %s", got, want)
	}
}

func TestEmitSQLite_NoLimitWhenZero(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{
				Table:   "tracks",
				Columns: []m.SelectedColumn{{Table: "tracks", Column: "Name", Role: "projection"}},
			},
		},
		Limit: intp(0),
	}
	got, err := Emit(plan, SQLite)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(got, "LIMIT") {
		t.Errorf("zero-limit should produce no LIMIT clause, got:\n%s", got)
	}
}

func TestDialectByName(t *testing.T) {
	cases := map[string]string{
		"tsql":      "tsql",
		"":          "tsql",
		"sqlite":    "sqlite",
		"postgres":  "tsql", // unknown → safe default
		"mysql":     "tsql",
	}
	for in, want := range cases {
		got := DialectByName(in).Name()
		if got != want {
			t.Errorf("DialectByName(%q) = %q, want %q", in, got, want)
		}
	}
}
