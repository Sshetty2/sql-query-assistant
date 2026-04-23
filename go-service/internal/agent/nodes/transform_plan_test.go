package nodes

import (
	"testing"

	"github.com/sachit/sql-query-assistant/go-service/internal/models"
	"github.com/sachit/sql-query-assistant/go-service/internal/schema"
)

func samplePlan() *models.PlannerOutput {
	return &models.PlannerOutput{
		Decision: models.DecisionProceed,
		Selections: []models.TableSelection{
			{
				Table: "customers",
				Columns: []models.SelectedColumn{
					{Table: "customers", Column: "FirstName", Role: "projection"},
					{Table: "customers", Column: "LastName", Role: "projection"},
				},
			},
		},
		OrderBy: []models.OrderByColumn{
			{Table: "customers", Column: "LastName", Direction: models.SortAsc},
		},
		Limit: intp(10),
	}
}

func sampleSchema() []schema.Table {
	return []schema.Table{
		{
			TableName: "customers",
			Columns: []schema.Column{
				{ColumnName: "CustomerId", DataType: "INTEGER"},
				{ColumnName: "FirstName", DataType: "NVARCHAR(40)"},
				{ColumnName: "LastName", DataType: "NVARCHAR(40)"},
				{ColumnName: "Email", DataType: "NVARCHAR(60)"},
			},
		},
	}
}

func TestApplyPatch_AddColumn(t *testing.T) {
	plan := samplePlan()
	got, err := ApplyPatch(plan, models.PatchOperation{
		Operation: "add_column",
		Table:     "customers",
		Column:    "Email",
	}, sampleSchema())
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(got.Selections[0].Columns) != 3 {
		t.Errorf("expected 3 columns after add, got %d", len(got.Selections[0].Columns))
	}
	// Original plan must be untouched (deep clone).
	if len(plan.Selections[0].Columns) != 2 {
		t.Errorf("original plan was mutated: %d cols", len(plan.Selections[0].Columns))
	}
}

func TestApplyPatch_AddColumn_Idempotent(t *testing.T) {
	plan := samplePlan()
	got, err := ApplyPatch(plan, models.PatchOperation{
		Operation: "add_column",
		Table:     "customers",
		Column:    "FirstName", // already there
	}, sampleSchema())
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(got.Selections[0].Columns) != 2 {
		t.Errorf("re-adding existing column should be a no-op, got %d cols", len(got.Selections[0].Columns))
	}
}

func TestApplyPatch_AddColumn_RejectsUnknown(t *testing.T) {
	if _, err := ApplyPatch(samplePlan(), models.PatchOperation{
		Operation: "add_column",
		Table:     "customers",
		Column:    "NotARealColumn",
	}, sampleSchema()); err == nil {
		t.Error("expected error for unknown column")
	}
}

func TestApplyPatch_RemoveColumn(t *testing.T) {
	plan := samplePlan()
	got, err := ApplyPatch(plan, models.PatchOperation{
		Operation: "remove_column",
		Table:     "customers",
		Column:    "LastName",
	}, sampleSchema())
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(got.Selections[0].Columns) != 1 {
		t.Errorf("expected 1 column after remove, got %d", len(got.Selections[0].Columns))
	}
	// Removing a column that's also in ORDER BY should drop it from order_by too.
	if len(got.OrderBy) != 0 {
		t.Errorf("expected order_by cleared (the only entry was the removed column), got %v", got.OrderBy)
	}
}

func TestApplyPatch_ModifyOrderBy(t *testing.T) {
	plan := samplePlan()
	got, err := ApplyPatch(plan, models.PatchOperation{
		Operation: "modify_order_by",
		OrderBy: []models.OrderByColumn{
			{Table: "customers", Column: "FirstName", Direction: models.SortDesc},
		},
	}, sampleSchema())
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(got.OrderBy) != 1 || got.OrderBy[0].Column != "FirstName" || got.OrderBy[0].Direction != models.SortDesc {
		t.Errorf("order_by not replaced: %+v", got.OrderBy)
	}
}

func TestApplyPatch_ModifyOrderBy_Clear(t *testing.T) {
	got, err := ApplyPatch(samplePlan(), models.PatchOperation{
		Operation: "modify_order_by",
		OrderBy:   nil,
	}, sampleSchema())
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(got.OrderBy) != 0 {
		t.Errorf("expected order_by cleared, got %v", got.OrderBy)
	}
}

func TestApplyPatch_ModifyLimit(t *testing.T) {
	got, err := ApplyPatch(samplePlan(), models.PatchOperation{
		Operation: "modify_limit",
		Limit:     intp(50),
	}, sampleSchema())
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if got.Limit == nil || *got.Limit != 50 {
		t.Errorf("limit not updated: %v", got.Limit)
	}
}

func TestApplyPatch_ModifyLimit_RejectsNonPositive(t *testing.T) {
	if _, err := ApplyPatch(samplePlan(), models.PatchOperation{
		Operation: "modify_limit",
		Limit:     intp(0),
	}, sampleSchema()); err == nil {
		t.Error("expected error for limit=0")
	}
	if _, err := ApplyPatch(samplePlan(), models.PatchOperation{
		Operation: "modify_limit",
		Limit:     intp(-5),
	}, sampleSchema()); err == nil {
		t.Error("expected error for negative limit")
	}
}

func TestApplyPatch_UnknownOp(t *testing.T) {
	if _, err := ApplyPatch(samplePlan(), models.PatchOperation{
		Operation: "delete_table",
	}, sampleSchema()); err == nil {
		t.Error("expected error for unknown operation")
	}
}

func TestApplyPatch_NilPlan(t *testing.T) {
	if _, err := ApplyPatch(nil, models.PatchOperation{Operation: "modify_limit", Limit: intp(5)}, nil); err == nil {
		t.Error("expected error for nil plan")
	}
}
