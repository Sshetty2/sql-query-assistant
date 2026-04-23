package sql

import (
	"strings"
	"testing"

	m "github.com/sachit/sql-query-assistant/go-service/internal/models"
)

// Mirrors a subset of tests/unit/test_advanced_sql_generation.py — the
// window-function cases the planner most often emits.

func TestEmitWindow_RowNumberOverPartition(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{
				Table: "tracks",
				Columns: []m.SelectedColumn{
					{Table: "tracks", Column: "Name", Role: "projection"},
					{Table: "tracks", Column: "GenreId", Role: "projection"},
				},
			},
		},
		WindowFunctions: []m.WindowFunction{
			{
				Function:    m.WinRowNumber,
				PartitionBy: []m.SelectedColumn{{Table: "tracks", Column: "GenreId"}},
				OrderBy:     []m.OrderByColumn{{Table: "tracks", Column: "UnitPrice", Direction: m.SortDesc}},
				Alias:       "rn",
			},
		},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "ROW_NUMBER() OVER (PARTITION BY [tracks].[GenreId] ORDER BY [tracks].[UnitPrice] DESC) AS [rn]") {
		t.Errorf("expected ROW_NUMBER OVER PARTITION BY ... ORDER BY ..., got:\n%s", got)
	}
}

func TestEmitWindow_RankOnly(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{
				Table:   "t",
				Columns: []m.SelectedColumn{{Table: "t", Column: "x", Role: "projection"}},
			},
		},
		WindowFunctions: []m.WindowFunction{
			{
				Function: m.WinRank,
				OrderBy:  []m.OrderByColumn{{Table: "t", Column: "score", Direction: m.SortDesc}},
				Alias:    "rank_score",
			},
		},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "RANK() OVER (ORDER BY [t].[score] DESC) AS [rank_score]") {
		t.Errorf("expected RANK() OVER (ORDER BY ...), got:\n%s", got)
	}
}

func TestEmitWindow_LagWithPartition(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{
				Table:   "events",
				Columns: []m.SelectedColumn{{Table: "events", Column: "id", Role: "projection"}},
			},
		},
		WindowFunctions: []m.WindowFunction{
			{
				Function:    m.WinLag,
				PartitionBy: []m.SelectedColumn{{Table: "events", Column: "value"}},
				OrderBy:     []m.OrderByColumn{{Table: "events", Column: "ts", Direction: m.SortAsc}},
				Alias:       "prev_value",
			},
		},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "LAG([events].[value]) OVER (PARTITION BY [events].[value] ORDER BY [events].[ts] ASC) AS [prev_value]") {
		t.Errorf("expected LAG with partition, got:\n%s", got)
	}
}

func TestEmitWindow_SumAggregate(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{
				Table:   "sales",
				Columns: []m.SelectedColumn{{Table: "sales", Column: "region", Role: "projection"}},
			},
		},
		WindowFunctions: []m.WindowFunction{
			{
				Function:    m.WinSum,
				PartitionBy: []m.SelectedColumn{{Table: "sales", Column: "amount"}},
				Alias:       "running_sum",
			},
		},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "SUM([sales].[amount]) OVER (PARTITION BY [sales].[amount]) AS [running_sum]") {
		t.Errorf("expected windowed SUM, got:\n%s", got)
	}
}
