package nodes

import (
	"math"
	"testing"

	"github.com/sachit/sql-query-assistant/go-service/internal/models"
)

// Edge-case tests for ApplyPatch — fills the gap surfaced by the test
// coverage audit. Existing transform_plan_test.go covers the happy paths;
// this file covers boundary conditions Python's test_plan_transformer.py
// also exercises but Go was missing.

func TestApplyPatch_RemoveColumn_DropsFromGroupBy(t *testing.T) {
	plan := &models.PlannerOutput{
		Decision: models.DecisionProceed,
		Selections: []models.TableSelection{
			{
				Table: "invoices",
				Columns: []models.SelectedColumn{
					{Table: "invoices", Column: "CustomerId", Role: "projection"},
					{Table: "invoices", Column: "Total", Role: "projection"},
				},
			},
		},
		GroupBy: &models.GroupBySpec{
			GroupByColumns: []models.SelectedColumn{
				{Table: "invoices", Column: "CustomerId"},
				{Table: "invoices", Column: "Total"},
			},
			Aggregates: []models.AggregateFunction{
				{Function: models.AggCount, Table: "invoices", Column: "*", Alias: "n"},
			},
		},
	}
	got, err := ApplyPatch(plan, models.PatchOperation{
		Operation: "remove_column",
		Table:     "invoices",
		Column:    "Total",
	}, nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, c := range got.GroupBy.GroupByColumns {
		if c.Column == "Total" {
			t.Errorf("Total should be removed from GROUP BY, found: %+v", got.GroupBy.GroupByColumns)
		}
	}
}

func TestApplyPatch_RemoveColumn_LastColumnInTable(t *testing.T) {
	// Removing the last projected column on a table is allowed — the
	// resulting plan would emit `SELECT *` from the projection fallback.
	plan := samplePlan()
	got, err := ApplyPatch(plan, models.PatchOperation{
		Operation: "remove_column",
		Table:     "customers",
		Column:    "FirstName",
	}, sampleSchema())
	if err != nil {
		t.Fatal(err)
	}
	got, err = ApplyPatch(got, models.PatchOperation{
		Operation: "remove_column",
		Table:     "customers",
		Column:    "LastName",
	}, sampleSchema())
	if err != nil {
		t.Fatal(err)
	}
	if len(got.Selections[0].Columns) != 0 {
		t.Errorf("expected empty column list after removing both, got: %+v", got.Selections[0].Columns)
	}
}

func TestApplyPatch_AddColumn_PreservesOrderByAndLimit(t *testing.T) {
	// Adding a column shouldn't disturb other plan fields.
	plan := samplePlan()
	originalOrder := append([]models.OrderByColumn(nil), plan.OrderBy...)
	originalLimit := *plan.Limit

	got, err := ApplyPatch(plan, models.PatchOperation{
		Operation: "add_column",
		Table:     "customers",
		Column:    "Email",
	}, sampleSchema())
	if err != nil {
		t.Fatal(err)
	}
	if len(got.OrderBy) != len(originalOrder) || got.OrderBy[0] != originalOrder[0] {
		t.Errorf("ORDER BY clobbered: got %+v want %+v", got.OrderBy, originalOrder)
	}
	if got.Limit == nil || *got.Limit != originalLimit {
		t.Errorf("LIMIT clobbered: got %v want %d", got.Limit, originalLimit)
	}
}

func TestApplyPatch_ModifyOrderBy_DuplicatesPreserved(t *testing.T) {
	// We don't dedupe — the planner is responsible for sane input.
	// Two entries on the same column become two ORDER BY clauses, which
	// the database will reject. This test pins down current behavior so
	// changes to the dedup policy are deliberate.
	plan := samplePlan()
	got, err := ApplyPatch(plan, models.PatchOperation{
		Operation: "modify_order_by",
		OrderBy: []models.OrderByColumn{
			{Table: "customers", Column: "FirstName", Direction: models.SortAsc},
			{Table: "customers", Column: "FirstName", Direction: models.SortDesc},
		},
	}, sampleSchema())
	if err != nil {
		t.Fatal(err)
	}
	if len(got.OrderBy) != 2 {
		t.Errorf("expected duplicates preserved, got %d entries", len(got.OrderBy))
	}
}

func TestApplyPatch_ModifyLimit_BoundaryCases(t *testing.T) {
	// Pin down the validation surface.
	cases := []struct {
		name      string
		limit     int
		expectErr bool
	}{
		{"positive", 100, false},
		{"one", 1, false},
		{"max int", math.MaxInt32, false},
		{"zero rejected", 0, true},
		{"negative rejected", -1, true},
		{"large negative rejected", -math.MaxInt32, true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := ApplyPatch(samplePlan(), models.PatchOperation{
				Operation: "modify_limit",
				Limit:     intp(tc.limit),
			}, sampleSchema())
			if tc.expectErr && err == nil {
				t.Errorf("expected error for limit=%d, got none", tc.limit)
			}
			if !tc.expectErr && err != nil {
				t.Errorf("unexpected error for limit=%d: %v", tc.limit, err)
			}
		})
	}
}

func TestApplyPatch_ModifyOrderBy_AlreadySortedNoOp(t *testing.T) {
	// Replacing order_by with an identical list is fine — the result equals
	// the input. We don't try to detect "no-op" edits.
	plan := samplePlan()
	original := append([]models.OrderByColumn(nil), plan.OrderBy...)
	got, err := ApplyPatch(plan, models.PatchOperation{
		Operation: "modify_order_by",
		OrderBy:   original,
	}, sampleSchema())
	if err != nil {
		t.Fatal(err)
	}
	if len(got.OrderBy) != len(original) {
		t.Errorf("got %d entries, want %d", len(got.OrderBy), len(original))
	}
	for i := range original {
		if got.OrderBy[i] != original[i] {
			t.Errorf("entry %d differs: got %+v want %+v", i, got.OrderBy[i], original[i])
		}
	}
}
