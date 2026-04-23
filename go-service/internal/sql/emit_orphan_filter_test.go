package sql

import (
	"strings"
	"testing"

	m "github.com/sachit/sql-query-assistant/go-service/internal/models"
)

// Mirrors tests/unit/test_orphaned_filter_columns.py — when the planner marks
// a column as role="filter" but forgets to emit a FilterPredicate, the
// emitter must NOT silently drop the column from SELECT. Otherwise the user
// loses data they implicitly asked about.
//
// Two correct behaviors are possible:
//   1. Promote the orphan to a projection (what we do — matches Python).
//   2. Detect the orphan in plan_audit and add a placeholder predicate.
//
// We picked (1) because it's defensive and never raises an unfixable error.

func TestEmit_OrphanedFilterColumn_PromotedToProjection(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{
				Table: "customers",
				Columns: []m.SelectedColumn{
					{Table: "customers", Column: "FirstName", Role: "projection"},
					// Orphan: marked filter but no matching FilterPredicate
					{Table: "customers", Column: "LastName", Role: "filter"},
				},
				// Filters list is empty — that's the "orphan" condition
			},
		},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "[customers].[FirstName]") {
		t.Errorf("FirstName should be projected: %s", got)
	}
	if !strings.Contains(got, "[customers].[LastName]") {
		t.Errorf("orphaned LastName (role=filter, no predicate) MUST appear in SELECT to avoid silent data loss: %s", got)
	}
}

func TestEmit_FilterColumnWithPredicate_NotProjected(t *testing.T) {
	// Inverse case: when the column DOES have a matching predicate, it should
	// stay out of SELECT (role=filter is honored).
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{
				Table: "customers",
				Columns: []m.SelectedColumn{
					{Table: "customers", Column: "FirstName", Role: "projection"},
					{Table: "customers", Column: "Country", Role: "filter"},
				},
				Filters: []m.FilterPredicate{
					{Table: "customers", Column: "Country", Op: m.OpEq, Value: "USA"},
				},
			},
		},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "[customers].[FirstName]") {
		t.Errorf("FirstName should be projected: %s", got)
	}
	if strings.Contains(got, "SELECT") && strings.Contains(got, "[customers].[Country]") {
		// Country may appear in the WHERE clause; check it's NOT in SELECT.
		// Crude but effective: count occurrences in the "before FROM" part.
		fromIdx := strings.Index(got, "FROM")
		if fromIdx > 0 && strings.Contains(got[:fromIdx], "[customers].[Country]") {
			t.Errorf("Country (role=filter, with predicate) should NOT be in SELECT: %s", got)
		}
	}
	if !strings.Contains(got, "[customers].[Country] = 'USA'") {
		t.Errorf("WHERE clause for Country missing: %s", got)
	}
}

// TestEmit_OrphanedFilter_GlobalFilterCounts mirrors the case where the
// matching predicate lives in plan.GlobalFilters rather than per-selection.
// The orphan check must look in BOTH places, otherwise we'd promote a column
// the planner deliberately left out of SELECT.
func TestEmit_OrphanedFilter_GlobalFilterCounts(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{
				Table: "customers",
				Columns: []m.SelectedColumn{
					{Table: "customers", Column: "FirstName", Role: "projection"},
					{Table: "customers", Column: "Country", Role: "filter"},
				},
			},
		},
		GlobalFilters: []m.FilterPredicate{
			{Table: "customers", Column: "Country", Op: m.OpEq, Value: "USA"},
		},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	fromIdx := strings.Index(got, "FROM")
	if fromIdx > 0 && strings.Contains(got[:fromIdx], "[customers].[Country]") {
		t.Errorf("Country with global predicate should NOT be in SELECT: %s", got)
	}
}
