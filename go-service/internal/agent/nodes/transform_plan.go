package nodes

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/sachit/sql-query-assistant/go-service/internal/models"
	"github.com/sachit/sql-query-assistant/go-service/internal/schema"
)

// ApplyPatch applies one of four patch operations to an existing plan and
// returns the modified plan. Pure function — no LLM, no IO.
//
// The original plan is never mutated; we deep-clone via JSON round-trip so
// callers can keep a reference to the pre-patch plan for diffing or audit.
//
// Mirrors agent/transform_plan.py:apply_patch_operation.
func ApplyPatch(plan *models.PlannerOutput, op models.PatchOperation, sch []schema.Table) (*models.PlannerOutput, error) {
	if plan == nil {
		return nil, fmt.Errorf("nil plan")
	}

	cloned, err := deepClonePlan(plan)
	if err != nil {
		return nil, fmt.Errorf("clone plan: %w", err)
	}

	switch op.Operation {
	case "add_column":
		if op.Table == "" || op.Column == "" {
			return nil, fmt.Errorf("add_column requires table and column")
		}
		return applyAddColumn(cloned, op.Table, op.Column, sch)
	case "remove_column":
		if op.Table == "" || op.Column == "" {
			return nil, fmt.Errorf("remove_column requires table and column")
		}
		return applyRemoveColumn(cloned, op.Table, op.Column), nil
	case "modify_order_by":
		// nil OrderBy is allowed — it clears ordering.
		return applyModifyOrderBy(cloned, op.OrderBy), nil
	case "modify_limit":
		if op.Limit == nil {
			return nil, fmt.Errorf("modify_limit requires limit")
		}
		if *op.Limit <= 0 {
			return nil, fmt.Errorf("modify_limit: limit must be positive, got %d", *op.Limit)
		}
		cloned.Limit = op.Limit
		return cloned, nil
	}
	return nil, fmt.Errorf("unknown patch operation %q (supported: add_column, remove_column, modify_order_by, modify_limit)", op.Operation)
}

// deepClonePlan round-trips through JSON. Slow vs handwritten copying but
// correct against future plan-shape additions without us remembering to update
// a custom cloner.
func deepClonePlan(p *models.PlannerOutput) (*models.PlannerOutput, error) {
	raw, err := json.Marshal(p)
	if err != nil {
		return nil, err
	}
	var out models.PlannerOutput
	if err := json.Unmarshal(raw, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

func applyAddColumn(plan *models.PlannerOutput, table, column string, sch []schema.Table) (*models.PlannerOutput, error) {
	// Validate the column actually exists in the schema; the planner is
	// allowed to be wrong but the patch UI shouldn't add invalid columns.
	if !columnExists(sch, table, column) {
		return nil, fmt.Errorf("column %s.%s not found in schema", table, column)
	}
	for i, sel := range plan.Selections {
		if !strings.EqualFold(sel.Table, table) {
			continue
		}
		// Idempotent — re-adding an already-present column is a no-op.
		for _, c := range sel.Columns {
			if strings.EqualFold(c.Column, column) {
				return plan, nil
			}
		}
		plan.Selections[i].Columns = append(plan.Selections[i].Columns, models.SelectedColumn{
			Table:  table,
			Column: column,
			Role:   "projection",
		})
		return plan, nil
	}
	// Table wasn't in selections — add it as a new selection.
	plan.Selections = append(plan.Selections, models.TableSelection{
		Table:      table,
		Confidence: 0.7,
		Columns: []models.SelectedColumn{
			{Table: table, Column: column, Role: "projection"},
		},
	})
	return plan, nil
}

func applyRemoveColumn(plan *models.PlannerOutput, table, column string) *models.PlannerOutput {
	for i, sel := range plan.Selections {
		if !strings.EqualFold(sel.Table, table) {
			continue
		}
		filtered := sel.Columns[:0]
		for _, c := range sel.Columns {
			if !strings.EqualFold(c.Column, column) {
				filtered = append(filtered, c)
			}
		}
		plan.Selections[i].Columns = filtered
	}

	// Strip the column from order_by too, otherwise the SQL emitter will sort
	// by something we no longer project.
	if len(plan.OrderBy) > 0 {
		ob := plan.OrderBy[:0]
		for _, o := range plan.OrderBy {
			if !(strings.EqualFold(o.Table, table) && strings.EqualFold(o.Column, column)) {
				ob = append(ob, o)
			}
		}
		plan.OrderBy = ob
	}

	// And from group_by.
	if plan.GroupBy != nil {
		gb := plan.GroupBy.GroupByColumns[:0]
		for _, c := range plan.GroupBy.GroupByColumns {
			if !(strings.EqualFold(c.Table, table) && strings.EqualFold(c.Column, column)) {
				gb = append(gb, c)
			}
		}
		plan.GroupBy.GroupByColumns = gb
	}
	return plan
}

func applyModifyOrderBy(plan *models.PlannerOutput, order []models.OrderByColumn) *models.PlannerOutput {
	if order == nil {
		plan.OrderBy = nil
	} else {
		plan.OrderBy = append([]models.OrderByColumn(nil), order...)
	}
	return plan
}

func columnExists(sch []schema.Table, table, column string) bool {
	for _, t := range sch {
		if !strings.EqualFold(t.TableName, table) {
			continue
		}
		for _, c := range t.Columns {
			if strings.EqualFold(c.ColumnName, column) {
				return true
			}
		}
	}
	return false
}
