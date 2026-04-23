package sql

import (
	"strings"
	"testing"

	m "github.com/sachit/sql-query-assistant/go-service/internal/models"
)

// Mirrors tests/unit/test_type_conversion.py — verifies emitLiteral renders
// each value type the planner can produce. JSON unmarshal always yields
// float64 for numbers, so we exercise float64 explicitly.

func TestEmitLiteral_AllTypes(t *testing.T) {
	cases := []struct {
		name string
		in   any
		want string
	}{
		{"nil → NULL", nil, "NULL"},
		{"bool true → 1", true, "1"},
		{"bool false → 0", false, "0"},
		{"float whole → integer", float64(42), "42"},
		{"float fractional → exact", float64(3.14), "3.14"},
		{"string simple", "hello", "'hello'"},
		{"string with apostrophe", "O'Brien", "'O''Brien'"},
		{"string empty", "", "''"},
		{"int64 literal", int64(99), "99"},
		{"int literal", int(7), "7"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := emitLiteral(tc.in)
			if err != nil {
				t.Fatalf("err: %v", err)
			}
			if got != tc.want {
				t.Errorf("got %q want %q", got, tc.want)
			}
		})
	}
}

func TestEmitLiteral_UnsupportedType(t *testing.T) {
	if _, err := emitLiteral(struct{ X int }{X: 1}); err == nil {
		t.Error("expected error for unsupported type")
	}
}

// TestEmitTSQL_NullFilters verifies IS NULL / IS NOT NULL never produce a
// literal value (`= NULL` is always false in SQL — must use IS NULL).
func TestEmitTSQL_NullFilters(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{
				Table:   "t",
				Columns: []m.SelectedColumn{{Table: "t", Column: "x", Role: "projection"}},
				Filters: []m.FilterPredicate{
					{Table: "t", Column: "DeletedAt", Op: m.OpIsNull},
					{Table: "t", Column: "UpdatedAt", Op: m.OpIsNotNull},
				},
			},
		},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "IS NULL") {
		t.Errorf("expected IS NULL clause: %s", got)
	}
	if !strings.Contains(got, "IS NOT NULL") {
		t.Errorf("expected IS NOT NULL clause: %s", got)
	}
	if strings.Contains(got, "= NULL") {
		t.Errorf("never emit '= NULL': %s", got)
	}
}

// TestEmitTSQL_BooleanEqualityValue covers a SQL Server BIT column compared
// against true/false from the planner. Mirrors test_bit_column_equality from
// tests/unit/test_type_conversion.py.
func TestEmitTSQL_BooleanEqualityValue(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{
				Table:   "users",
				Columns: []m.SelectedColumn{{Table: "users", Column: "Email", Role: "projection"}},
				Filters: []m.FilterPredicate{
					{Table: "users", Column: "IsActive", Op: m.OpEq, Value: true},
				},
			},
		},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	// SQL Server BIT columns accept 0/1 — emitter renders bool as 1/0, not 'true'/'false'.
	if !strings.Contains(got, "[users].[IsActive] = 1") {
		t.Errorf("expected [IsActive] = 1, got: %s", got)
	}
}

// TestEmitTSQL_DateLiteralFromString — when the planner provides a string
// like '2026-01-01', the emitter quotes it as a string literal. SQL Server
// accepts string-form dates in implicit-conversion contexts. Mirrors
// test_create_date_literal_sql_server from test_date_filters.py.
func TestEmitTSQL_DateLiteralFromString(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{
				Table:   "events",
				Columns: []m.SelectedColumn{{Table: "events", Column: "Name", Role: "projection"}},
				Filters: []m.FilterPredicate{
					{Table: "events", Column: "EventDate", Op: m.OpGte, Value: "2026-01-01"},
				},
			},
		},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "[events].[EventDate] >= '2026-01-01'") {
		t.Errorf("expected date literal: %s", got)
	}
}

// TestEmitTSQL_BetweenWithDates — date range filter via BETWEEN.
func TestEmitTSQL_BetweenWithDates(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{
				Table:   "logs",
				Columns: []m.SelectedColumn{{Table: "logs", Column: "Message", Role: "projection"}},
				Filters: []m.FilterPredicate{
					{Table: "logs", Column: "CreatedAt", Op: m.OpBetween, Value: []any{"2026-01-01", "2026-01-31"}},
				},
			},
		},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "BETWEEN '2026-01-01' AND '2026-01-31'") {
		t.Errorf("expected BETWEEN with dates: %s", got)
	}
}

// TestEmitTSQL_DecimalSerialization — float values that aren't whole numbers
// must round-trip exactly. Mirrors tests/unit/test_decimal_serialization.py.
func TestEmitTSQL_DecimalSerialization(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{
				Table:   "products",
				Columns: []m.SelectedColumn{{Table: "products", Column: "Name", Role: "projection"}},
				Filters: []m.FilterPredicate{
					{Table: "products", Column: "Price", Op: m.OpGt, Value: 19.99},
				},
			},
		},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "> 19.99") {
		t.Errorf("expected decimal preserved: %s", got)
	}
}

// TestDialect_SQLiteVsTSQL_LimitPlacement verifies that the same plan
// produces TOP-style SQL for T-SQL and trailing LIMIT-style SQL for SQLite.
// Mirrors tests/unit/test_dialect_compatibility.py.
func TestDialect_SQLiteVsTSQL_LimitPlacement(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{
				Table:   "tracks",
				Columns: []m.SelectedColumn{{Table: "tracks", Column: "Name", Role: "projection"}},
			},
		},
		Limit: intp(5),
	}

	tsql, err := Emit(plan, TSQL)
	if err != nil {
		t.Fatalf("tsql emit: %v", err)
	}
	sqlite, err := Emit(plan, SQLite)
	if err != nil {
		t.Fatalf("sqlite emit: %v", err)
	}

	if !strings.Contains(tsql, "SELECT TOP 5") {
		t.Errorf("T-SQL should emit SELECT TOP 5, got:\n%s", tsql)
	}
	if strings.Contains(tsql, "LIMIT") {
		t.Errorf("T-SQL should NOT emit LIMIT, got:\n%s", tsql)
	}
	if strings.Contains(sqlite, "TOP") {
		t.Errorf("SQLite should NOT emit TOP, got:\n%s", sqlite)
	}
	if !strings.Contains(sqlite, "LIMIT 5") {
		t.Errorf("SQLite should emit LIMIT 5, got:\n%s", sqlite)
	}
}
