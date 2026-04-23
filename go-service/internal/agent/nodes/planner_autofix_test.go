package nodes

import (
	"strings"
	"testing"

	"github.com/sachit/sql-query-assistant/go-service/internal/models"
)

// Mirrors tests/unit/test_planner_auto_fix.py — verifies that tables referenced
// by join_edges but missing from selections get auto-added with
// include_only_for_join=true. This is the most common planner mistake.

func tableNamesFromSelections(p *models.PlannerOutput) []string {
	out := make([]string, len(p.Selections))
	for i, s := range p.Selections {
		out[i] = s.Table
	}
	return out
}

func TestAutoFixJoinEdges_AddsMissingTables(t *testing.T) {
	plan := &models.PlannerOutput{
		Selections: []models.TableSelection{
			{Table: "customers"},
		},
		JoinEdges: []models.JoinEdge{
			{FromTable: "customers", ToTable: "invoices"},
		},
	}
	autoFixJoinEdges(plan)
	got := strings.Join(tableNamesFromSelections(plan), ",")
	if !strings.Contains(got, "invoices") {
		t.Errorf("missing 'invoices' added to selections; got: %s", got)
	}
	// Auto-added entries must be marked join-only so they aren't projected.
	for _, sel := range plan.Selections {
		if sel.Table == "invoices" && !sel.IncludeOnlyForJoin {
			t.Errorf("auto-added table should be IncludeOnlyForJoin=true")
		}
	}
}

func TestAutoFixJoinEdges_MultipleMissing(t *testing.T) {
	plan := &models.PlannerOutput{
		Selections: []models.TableSelection{
			{Table: "a"},
		},
		JoinEdges: []models.JoinEdge{
			{FromTable: "a", ToTable: "b"},
			{FromTable: "b", ToTable: "c"},
			{FromTable: "c", ToTable: "d"},
		},
	}
	autoFixJoinEdges(plan)
	if len(plan.Selections) != 4 {
		t.Errorf("expected 4 selections after auto-fix, got %d (%v)",
			len(plan.Selections), tableNamesFromSelections(plan))
	}
}

func TestAutoFixJoinEdges_NoChangesNeeded(t *testing.T) {
	plan := &models.PlannerOutput{
		Selections: []models.TableSelection{
			{Table: "a"}, {Table: "b"},
		},
		JoinEdges: []models.JoinEdge{
			{FromTable: "a", ToTable: "b"},
		},
	}
	autoFixJoinEdges(plan)
	if len(plan.Selections) != 2 {
		t.Errorf("no auto-fix expected, got %d selections", len(plan.Selections))
	}
}

func TestAutoFixJoinEdges_EmptyJoinEdges(t *testing.T) {
	plan := &models.PlannerOutput{
		Selections: []models.TableSelection{{Table: "a"}},
	}
	autoFixJoinEdges(plan)
	if len(plan.Selections) != 1 {
		t.Errorf("no joins → no fix, got %d selections", len(plan.Selections))
	}
}

func TestAutoFixJoinEdges_PreservesExistingMetadata(t *testing.T) {
	plan := &models.PlannerOutput{
		Selections: []models.TableSelection{
			{Table: "a", Confidence: 0.95, Reason: "primary"},
		},
		JoinEdges: []models.JoinEdge{
			{FromTable: "a", ToTable: "b"},
		},
	}
	autoFixJoinEdges(plan)
	for _, s := range plan.Selections {
		if s.Table == "a" && (s.Confidence != 0.95 || s.Reason != "primary") {
			t.Errorf("existing selection metadata clobbered: %+v", s)
		}
	}
}

func TestAutoFixJoinEdges_CaseInsensitiveDeduplication(t *testing.T) {
	// Selections use mixed case; planner shouldn't add "Customers" if "customers" exists.
	plan := &models.PlannerOutput{
		Selections: []models.TableSelection{
			{Table: "Customers"},
		},
		JoinEdges: []models.JoinEdge{
			{FromTable: "customers", ToTable: "invoices"},
		},
	}
	autoFixJoinEdges(plan)
	for _, name := range tableNamesFromSelections(plan) {
		// Only one customers entry should exist (case-insensitive).
		count := 0
		for _, n := range tableNamesFromSelections(plan) {
			if strings.EqualFold(n, name) {
				count++
			}
		}
		if count > 1 {
			t.Errorf("duplicate selection for %s (case-insensitive): %v", name, tableNamesFromSelections(plan))
			break
		}
	}
}
