package sql

import (
	"strings"
	"testing"

	m "github.com/sachit/sql-query-assistant/go-service/internal/models"
)

// Mirrors tests/unit/test_disconnected_tables.py — covers the SQL gen behavior
// when selections include tables that aren't all reachable via join_edges, or
// queries with a single table, or chained joins. The Python emitter (SQLGlot)
// drops join clauses for unselected tables and produces SELECT against the
// connected subgraph; our emitter follows the same convention.

func TestEmitTSQL_SingleTableNoJoins(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{
				Table:   "tracks",
				Columns: []m.SelectedColumn{{Table: "tracks", Column: "Name", Role: "projection"}},
			},
		},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "FROM [tracks]") {
		t.Errorf("expected FROM [tracks], got: %s", got)
	}
	if strings.Contains(got, "JOIN") {
		t.Errorf("single table should not produce JOIN clause: %s", got)
	}
}

func TestEmitTSQL_TwoTablesWithJoin(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{Table: "albums", Columns: []m.SelectedColumn{{Table: "albums", Column: "Title", Role: "projection"}}},
			{Table: "artists", Columns: []m.SelectedColumn{{Table: "artists", Column: "Name", Role: "projection"}}},
		},
		JoinEdges: []m.JoinEdge{
			{FromTable: "albums", FromColumn: "ArtistId", ToTable: "artists", ToColumn: "ArtistId", JoinType: m.JoinInner},
		},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "INNER JOIN [artists]") {
		t.Errorf("expected INNER JOIN [artists]: %s", got)
	}
	if !strings.Contains(got, "[albums].[ArtistId] = [artists].[ArtistId]") {
		t.Errorf("expected join condition: %s", got)
	}
}

func TestEmitTSQL_ThreeTablesLinearChain(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{Table: "invoice_items", Columns: []m.SelectedColumn{{Table: "invoice_items", Column: "Quantity", Role: "projection"}}},
			{Table: "invoices", IncludeOnlyForJoin: true},
			{Table: "customers", Columns: []m.SelectedColumn{{Table: "customers", Column: "FirstName", Role: "projection"}}},
		},
		JoinEdges: []m.JoinEdge{
			{FromTable: "invoice_items", FromColumn: "InvoiceId", ToTable: "invoices", ToColumn: "InvoiceId", JoinType: m.JoinInner},
			{FromTable: "invoices", FromColumn: "CustomerId", ToTable: "customers", ToColumn: "CustomerId", JoinType: m.JoinInner},
		},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Count(got, "INNER JOIN") != 2 {
		t.Errorf("expected 2 joins, got: %s", got)
	}
}

func TestEmitTSQL_StarTopology(t *testing.T) {
	// Hub table joined to 3 spokes
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{Table: "invoices", Columns: []m.SelectedColumn{{Table: "invoices", Column: "Total", Role: "projection"}}},
			{Table: "customers", Columns: []m.SelectedColumn{{Table: "customers", Column: "FirstName", Role: "projection"}}},
			{Table: "employees", Columns: []m.SelectedColumn{{Table: "employees", Column: "LastName", Role: "projection"}}},
			{Table: "billing_countries", Columns: []m.SelectedColumn{{Table: "billing_countries", Column: "Country", Role: "projection"}}},
		},
		JoinEdges: []m.JoinEdge{
			{FromTable: "invoices", FromColumn: "CustomerId", ToTable: "customers", ToColumn: "CustomerId"},
			{FromTable: "invoices", FromColumn: "SupportRepId", ToTable: "employees", ToColumn: "EmployeeId"},
			{FromTable: "invoices", FromColumn: "BillingCountryId", ToTable: "billing_countries", ToColumn: "Id"},
		},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Count(got, "INNER JOIN") != 3 {
		t.Errorf("expected 3 joins for star topology, got %d:\n%s", strings.Count(got, "INNER JOIN"), got)
	}
}

func TestEmitTSQL_BidirectionalJoin(t *testing.T) {
	// `to_table` is already rooted (FROM clause) but `from_table` isn't.
	// Emitter should flip the edge so the new table goes on the right side.
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{Table: "albums", Columns: []m.SelectedColumn{{Table: "albums", Column: "Title", Role: "projection"}}},
			{Table: "artists", Columns: []m.SelectedColumn{{Table: "artists", Column: "Name", Role: "projection"}}},
		},
		JoinEdges: []m.JoinEdge{
			// "from" is the unrooted table — emitter must flip
			{FromTable: "artists", FromColumn: "ArtistId", ToTable: "albums", ToColumn: "ArtistId", JoinType: m.JoinInner},
		},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "INNER JOIN [artists]") {
		t.Errorf("expected join to add [artists] on the right, got: %s", got)
	}
}

func TestEmitTSQL_LeftJoinPreservesNulls(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{Table: "customers", Columns: []m.SelectedColumn{{Table: "customers", Column: "FirstName", Role: "projection"}}},
			{Table: "invoices", Columns: []m.SelectedColumn{{Table: "invoices", Column: "Total", Role: "projection"}}},
		},
		JoinEdges: []m.JoinEdge{
			{FromTable: "customers", FromColumn: "CustomerId", ToTable: "invoices", ToColumn: "CustomerId", JoinType: m.JoinLeft},
		},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "LEFT JOIN [invoices]") {
		t.Errorf("expected LEFT JOIN: %s", got)
	}
}

func TestEmitTSQL_FullOuterJoin(t *testing.T) {
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{Table: "a", Columns: []m.SelectedColumn{{Table: "a", Column: "x", Role: "projection"}}},
			{Table: "b", Columns: []m.SelectedColumn{{Table: "b", Column: "y", Role: "projection"}}},
		},
		JoinEdges: []m.JoinEdge{
			{FromTable: "a", FromColumn: "k", ToTable: "b", ToColumn: "k", JoinType: m.JoinFull},
		},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "FULL OUTER JOIN") {
		t.Errorf("expected FULL OUTER JOIN: %s", got)
	}
}

func TestEmitTSQL_JoinOnlyTableNotProjected(t *testing.T) {
	// Table marked include_only_for_join should NOT appear in SELECT list.
	plan := &m.PlannerOutput{
		Decision: m.DecisionProceed,
		Selections: []m.TableSelection{
			{Table: "tracks", Columns: []m.SelectedColumn{{Table: "tracks", Column: "Name", Role: "projection"}}},
			{Table: "albums", IncludeOnlyForJoin: true,
				Columns: []m.SelectedColumn{{Table: "albums", Column: "Title", Role: "projection"}}},
		},
		JoinEdges: []m.JoinEdge{
			{FromTable: "tracks", FromColumn: "AlbumId", ToTable: "albums", ToColumn: "AlbumId", JoinType: m.JoinInner},
		},
	}
	got, err := EmitTSQL(plan)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(got, "[albums].[Title]") {
		t.Errorf("join-only table column should not be projected: %s", got)
	}
}
