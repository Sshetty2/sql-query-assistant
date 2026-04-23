package sql

import (
	"strings"
	"testing"

	m "github.com/sachit/sql-query-assistant/go-service/internal/models"
)

func intp(i int) *int { return &i }

// normalize strips trailing whitespace per line and collapses blank lines so
// tests don't rely on exact column alignment from the emitter's pretty printer.
func normalize(s string) string {
	lines := strings.Split(s, "\n")
	out := lines[:0]
	for _, l := range lines {
		l = strings.TrimRight(l, " \t")
		if l == "" {
			continue
		}
		out = append(out, l)
	}
	return strings.Join(out, "\n")
}

func TestEmitTSQL(t *testing.T) {
	cases := []struct {
		name string
		plan *m.PlannerOutput
		want string
	}{
		{
			name: "single table single column",
			plan: &m.PlannerOutput{
				Decision: m.DecisionProceed,
				Selections: []m.TableSelection{
					{
						Table: "customers",
						Columns: []m.SelectedColumn{
							{Table: "customers", Column: "FirstName", Role: "projection"},
						},
					},
				},
			},
			want: `SELECT
  [customers].[FirstName]
FROM [customers]`,
		},
		{
			name: "reserved keyword column always bracketed",
			plan: &m.PlannerOutput{
				Decision: m.DecisionProceed,
				Selections: []m.TableSelection{
					{
						Table: "Orders",
						Columns: []m.SelectedColumn{
							{Table: "Orders", Column: "Order", Role: "projection"},
							{Table: "Orders", Column: "Index", Role: "projection"},
						},
					},
				},
			},
			want: `SELECT
  [Orders].[Order],
  [Orders].[Index]
FROM [Orders]`,
		},
		{
			name: "join with alias and where",
			plan: &m.PlannerOutput{
				Decision: m.DecisionProceed,
				Selections: []m.TableSelection{
					{
						Table: "customers", Alias: "c",
						Columns: []m.SelectedColumn{{Table: "customers", Column: "Email", Role: "projection"}},
						Filters: []m.FilterPredicate{
							{Table: "customers", Column: "Country", Op: m.OpEq, Value: "USA"},
						},
					},
					{
						Table: "invoices", Alias: "i",
						Columns: []m.SelectedColumn{{Table: "invoices", Column: "Total", Role: "projection"}},
					},
				},
				JoinEdges: []m.JoinEdge{
					{FromTable: "customers", FromColumn: "CustomerId", ToTable: "invoices", ToColumn: "CustomerId", JoinType: m.JoinInner},
				},
			},
			want: `SELECT
  [c].[Email],
  [i].[Total]
FROM [customers] AS [c]
INNER JOIN [invoices] AS [i] ON [c].[CustomerId] = [i].[CustomerId]
WHERE [c].[Country] = 'USA'`,
		},
		{
			name: "left join",
			plan: &m.PlannerOutput{
				Decision: m.DecisionProceed,
				Selections: []m.TableSelection{
					{Table: "a", Columns: []m.SelectedColumn{{Table: "a", Column: "x", Role: "projection"}}},
					{Table: "b", IncludeOnlyForJoin: true},
				},
				JoinEdges: []m.JoinEdge{
					{FromTable: "a", FromColumn: "id", ToTable: "b", ToColumn: "a_id", JoinType: m.JoinLeft},
				},
			},
			want: `SELECT
  [a].[x]
FROM [a]
LEFT JOIN [b] ON [a].[id] = [b].[a_id]`,
		},
		{
			name: "in / not_in / between / like / is_null",
			plan: &m.PlannerOutput{
				Decision: m.DecisionProceed,
				Selections: []m.TableSelection{
					{
						Table: "t",
						Columns: []m.SelectedColumn{{Table: "t", Column: "x", Role: "projection"}},
						Filters: []m.FilterPredicate{
							{Table: "t", Column: "Status", Op: m.OpIn, Value: []any{"open", "pending"}},
							{Table: "t", Column: "Code", Op: m.OpNotIn, Value: []any{1.0, 2.0, 3.0}},
							{Table: "t", Column: "Age", Op: m.OpBetween, Value: []any{18.0, 65.0}},
							{Table: "t", Column: "Name", Op: m.OpLike, Value: "Sam%"},
							{Table: "t", Column: "DeletedAt", Op: m.OpIsNull},
							{Table: "t", Column: "UpdatedAt", Op: m.OpIsNotNull},
						},
					},
				},
			},
			want: `SELECT
  [t].[x]
FROM [t]
WHERE [t].[Status] IN ('open', 'pending')
  AND [t].[Code] NOT IN (1, 2, 3)
  AND [t].[Age] BETWEEN 18 AND 65
  AND [t].[Name] LIKE 'Sam%'
  AND [t].[DeletedAt] IS NULL
  AND [t].[UpdatedAt] IS NOT NULL`,
		},
		{
			name: "starts_with / ends_with / single quote escaping",
			plan: &m.PlannerOutput{
				Decision: m.DecisionProceed,
				Selections: []m.TableSelection{
					{
						Table: "t",
						Columns: []m.SelectedColumn{{Table: "t", Column: "x", Role: "projection"}},
						Filters: []m.FilterPredicate{
							{Table: "t", Column: "Name", Op: m.OpStartsWith, Value: "O'Brien"},
							{Table: "t", Column: "City", Op: m.OpEndsWith, Value: "ville"},
						},
					},
				},
			},
			want: `SELECT
  [t].[x]
FROM [t]
WHERE [t].[Name] LIKE 'O''Brien%'
  AND [t].[City] LIKE '%ville'`,
		},
		{
			name: "group by + aggregates + having + order by + top",
			plan: &m.PlannerOutput{
				Decision: m.DecisionProceed,
				Selections: []m.TableSelection{
					{
						Table: "invoices",
						Columns: []m.SelectedColumn{
							{Table: "invoices", Column: "CustomerId", Role: "projection"},
							{Table: "invoices", Column: "Total", Role: "projection"},
						},
					},
				},
				GroupBy: &m.GroupBySpec{
					GroupByColumns: []m.SelectedColumn{
						{Table: "invoices", Column: "CustomerId", Role: "projection"},
					},
					Aggregates: []m.AggregateFunction{
						{Function: m.AggSum, Table: "invoices", Column: "Total", Alias: "TotalSpent"},
						{Function: m.AggCount, Table: "invoices", Column: "*", Alias: "InvoiceCount"},
					},
					HavingFilters: []m.FilterPredicate{
						{Table: "invoices", Column: "Total", Op: m.OpGt, Value: 100.0},
					},
				},
				OrderBy: []m.OrderByColumn{
					{Table: "invoices", Column: "CustomerId", Direction: m.SortDesc},
				},
				Limit: intp(10),
			},
			want: `SELECT TOP 10
  [invoices].[CustomerId],
  SUM([invoices].[Total]) AS [TotalSpent],
  COUNT(*) AS [InvoiceCount]
FROM [invoices]
GROUP BY [invoices].[CustomerId]
HAVING [invoices].[Total] > 100
ORDER BY [invoices].[CustomerId] DESC`,
		},
		{
			name: "count distinct",
			plan: &m.PlannerOutput{
				Decision: m.DecisionProceed,
				Selections: []m.TableSelection{
					{
						Table:   "t",
						Columns: []m.SelectedColumn{{Table: "t", Column: "id", Role: "projection"}},
					},
				},
				GroupBy: &m.GroupBySpec{
					GroupByColumns: nil,
					Aggregates: []m.AggregateFunction{
						{Function: m.AggCountDistinct, Table: "t", Column: "Email", Alias: "UniqueEmails"},
					},
				},
			},
			want: `SELECT
  COUNT(DISTINCT [t].[Email]) AS [UniqueEmails]
FROM [t]`,
		},
		{
			name: "global filter alongside table filter",
			plan: &m.PlannerOutput{
				Decision: m.DecisionProceed,
				Selections: []m.TableSelection{
					{
						Table:   "t",
						Columns: []m.SelectedColumn{{Table: "t", Column: "x", Role: "projection"}},
						Filters: []m.FilterPredicate{
							{Table: "t", Column: "x", Op: m.OpGt, Value: 0.0},
						},
					},
				},
				GlobalFilters: []m.FilterPredicate{
					{Table: "t", Column: "y", Op: m.OpEq, Value: "z"},
				},
			},
			want: `SELECT
  [t].[x]
FROM [t]
WHERE [t].[x] > 0
  AND [t].[y] = 'z'`,
		},
		{
			name: "identifier with embedded bracket",
			plan: &m.PlannerOutput{
				Decision: m.DecisionProceed,
				Selections: []m.TableSelection{
					{
						Table: "weird]name",
						Columns: []m.SelectedColumn{
							{Table: "weird]name", Column: "col]name", Role: "projection"},
						},
					},
				},
			},
			want: `SELECT
  [weird]]name].[col]]name]
FROM [weird]]name]`,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := EmitTSQL(tc.plan)
			if err != nil {
				t.Fatalf("EmitTSQL error: %v", err)
			}
			if normalize(got) != normalize(tc.want) {
				t.Errorf("SQL mismatch\n--- got ---\n%s\n--- want ---\n%s", got, tc.want)
			}
		})
	}
}

func TestEmitTSQL_Errors(t *testing.T) {
	cases := []struct {
		name string
		plan *m.PlannerOutput
	}{
		{name: "nil", plan: nil},
		{name: "no selections", plan: &m.PlannerOutput{Decision: m.DecisionProceed}},
		{
			name: "terminate decision",
			plan: &m.PlannerOutput{
				Decision:          m.DecisionTerminate,
				TerminationReason: "impossible",
			},
		},
		{
			name: "ctes not supported (post-mvp)",
			plan: &m.PlannerOutput{
				Decision: m.DecisionProceed,
				Selections: []m.TableSelection{
					{Table: "t", Columns: []m.SelectedColumn{{Table: "t", Column: "x", Role: "projection"}}},
				},
				CTEs: []m.CTE{{Name: "foo"}},
			},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if _, err := EmitTSQL(tc.plan); err == nil {
				t.Error("expected error, got nil")
			}
		})
	}
}
