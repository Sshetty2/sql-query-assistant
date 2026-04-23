package sql

import (
	"strings"
	"testing"

	m "github.com/sachit/sql-query-assistant/go-service/internal/models"
)

// Mirrors tests/unit/test_advanced_sql_generation.py's subquery-filter
// case. Covers IN, NOT IN, EXISTS, NOT EXISTS variants.

func basicSubqueryPlan(op string) *m.PlannerOutput {
	return &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{
				Table: "customers",
				Columns: []m.SelectedColumn{
					{Table: "customers", Column: "FirstName", Role: "projection"},
				},
			},
		},
		SubqueryFilters: []m.SubqueryFilter{
			{
				Op:             op,
				OuterTable:     "customers",
				OuterColumn:    "CustomerId",
				SubqueryTable:  "invoices",
				SubqueryColumn: "CustomerId",
				SubqueryFilters: []m.FilterPredicate{
					{Table: "invoices", Column: "Total", Op: m.OpGt, Value: 100.0},
				},
			},
		},
	}
}

func TestEmitSubquery_IN(t *testing.T) {
	got, err := EmitTSQL(basicSubqueryPlan("in"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "[customers].[CustomerId] IN (SELECT [invoices].[CustomerId] FROM [invoices] WHERE [invoices].[Total] > 100)") {
		t.Errorf("expected IN-subquery, got:\n%s", got)
	}
}

func TestEmitSubquery_NotIN(t *testing.T) {
	got, err := EmitTSQL(basicSubqueryPlan("not_in"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "[customers].[CustomerId] NOT IN (SELECT") {
		t.Errorf("expected NOT IN, got:\n%s", got)
	}
}

func TestEmitSubquery_Exists(t *testing.T) {
	got, err := EmitTSQL(basicSubqueryPlan("exists"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "EXISTS (SELECT [invoices].[CustomerId]") {
		t.Errorf("expected EXISTS-subquery, got:\n%s", got)
	}
	if strings.Contains(got, "IN (SELECT") {
		t.Errorf("EXISTS should not contain IN clause, got:\n%s", got)
	}
}

func TestEmitSubquery_NotExists(t *testing.T) {
	got, err := EmitTSQL(basicSubqueryPlan("not_exists"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "NOT EXISTS (SELECT") {
		t.Errorf("expected NOT EXISTS, got:\n%s", got)
	}
}

func TestEmitSubquery_NoInnerFilters(t *testing.T) {
	// The OUTER WHERE clause still appears (it carries the IN-subquery itself).
	// Only the inner SELECT should lack a WHERE.
	plan := basicSubqueryPlan("in")
	plan.SubqueryFilters[0].SubqueryFilters = nil
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "IN (SELECT [invoices].[CustomerId] FROM [invoices])") {
		t.Errorf("expected unfiltered subquery, got:\n%s", got)
	}
	// Confirm the inner SELECT has no WHERE.
	if strings.Contains(got, "FROM [invoices] WHERE") {
		t.Errorf("inner subquery should have no WHERE, got:\n%s", got)
	}
}

func TestEmitSubquery_CombinedWithRegularFilter(t *testing.T) {
	plan := basicSubqueryPlan("in")
	plan.Selections[0].Filters = []m.FilterPredicate{
		{Table: "customers", Column: "Country", Op: m.OpEq, Value: "USA"},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "[customers].[Country] = 'USA'") {
		t.Errorf("regular filter missing, got:\n%s", got)
	}
	if !strings.Contains(got, "IN (SELECT") {
		t.Errorf("subquery filter missing, got:\n%s", got)
	}
	// Both clauses should be ANDed in WHERE.
	if !strings.Contains(got, " AND ") {
		t.Errorf("expected AND between filters, got:\n%s", got)
	}
}
