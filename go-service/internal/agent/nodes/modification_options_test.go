package nodes

import (
	"testing"

	"github.com/sachit/sql-query-assistant/go-service/internal/models"
	"github.com/sachit/sql-query-assistant/go-service/internal/schema"
)

func TestFormatColumnNameForDisplay(t *testing.T) {
	cases := map[string]string{
		"UpdatedBy":       "Updated By",
		"SW_Edition":      "SW Edition",
		"CompanyID":       "Company ID",
		"company_id":      "Company Id",
		"XMLParser":       "XML Parser",
		"FK_company":      "FK Company",
		"":                "",
		"id":              "Id",
	}
	for in, want := range cases {
		if got := FormatColumnNameForDisplay(in); got != want {
			t.Errorf("FormatColumnNameForDisplay(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestGenerateModificationOptions_Basic(t *testing.T) {
	plan := &models.PlannerOutput{
		Decision: models.DecisionProceed,
		Selections: []models.TableSelection{
			{
				Table: "customers",
				Columns: []models.SelectedColumn{
					{Table: "customers", Column: "FirstName", Role: "projection"},
					{Table: "customers", Column: "Country", Role: "filter"},
				},
				Filters: []models.FilterPredicate{
					{Table: "customers", Column: "Country", Op: models.OpEq, Value: "USA"},
				},
			},
		},
		OrderBy: []models.OrderByColumn{
			{Table: "customers", Column: "LastName", Direction: models.SortAsc},
		},
		Limit: intp(10),
	}
	sch := []schema.Table{
		{
			TableName: "customers",
			Columns: []schema.Column{
				{ColumnName: "CustomerId", DataType: "INTEGER", IsNullable: false},
				{ColumnName: "FirstName", DataType: "NVARCHAR(40)", IsNullable: false},
				{ColumnName: "LastName", DataType: "NVARCHAR(40)", IsNullable: false},
				{ColumnName: "Country", DataType: "NVARCHAR(40)", IsNullable: true},
			},
		},
	}

	got := GenerateModificationOptions(plan, sch)

	tbl, ok := got.Tables["customers"]
	if !ok {
		t.Fatalf("missing customers table in options")
	}
	if len(tbl.Columns) != 4 {
		t.Errorf("expected 4 columns, got %d", len(tbl.Columns))
	}

	// Check selected/role flags map back correctly.
	bySel := map[string]models.ColumnOption{}
	for _, c := range tbl.Columns {
		bySel[c.Name] = c
	}
	if !bySel["FirstName"].Selected || bySel["FirstName"].Role != "projection" {
		t.Errorf("FirstName flags wrong: %+v", bySel["FirstName"])
	}
	if !bySel["Country"].Selected || bySel["Country"].Role != "filter" {
		t.Errorf("Country flags wrong: %+v", bySel["Country"])
	}
	if bySel["LastName"].Selected {
		t.Errorf("LastName should be unselected (not in plan)")
	}

	if len(got.CurrentOrderBy) != 1 || got.CurrentOrderBy[0].Column != "LastName" {
		t.Errorf("order_by not preserved: %+v", got.CurrentOrderBy)
	}
	if got.CurrentLimit == nil || *got.CurrentLimit != 10 {
		t.Errorf("limit not preserved")
	}
	if len(got.SortableColumns) != 4 {
		t.Errorf("expected 4 sortable columns, got %d", len(got.SortableColumns))
	}
}

func TestGenerateModificationOptions_NilPlan(t *testing.T) {
	got := GenerateModificationOptions(nil, nil)
	if got == nil || len(got.Tables) != 0 {
		t.Errorf("nil plan should yield empty options, got %+v", got)
	}
}

// intp is a small test helper; defined here because the existing
// planner_autofix_test.go doesn't export one.
func intp(i int) *int { return &i }
