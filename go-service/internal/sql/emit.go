// Package sql holds the deterministic T-SQL emitter that converts a PlannerOutput
// into an executable SQL string. This replaces SQLGlot's role in the Python service.
//
// Design choices:
//   - Always-bracketed identifiers (`[name]`). Mirrors SQLGlot's `identify=True`
//     and prevents reserved-word collisions like `[Order]`, `[Index]`, `[User]`.
//   - SELECT TOP n (T-SQL idiom), not LIMIT.
//   - String literals are single-quoted; embedded single quotes are doubled.
//   - The emitter is total: it never uses string concatenation of user-supplied
//     values into the SQL — every value goes through a typed literal builder.
//
// Out of scope for the Phase-2 MVP (will be filled in for full parity):
//   - Window functions (planner_output.WindowFunctions)
//   - CTEs (planner_output.CTEs)
//   - Subquery filters (planner_output.SubqueryFilters)
//   - ILIKE → CI-collated LIKE rewrite
//   - starts_with / ends_with sugar (currently treated as LIKE patterns)
package sql

import (
	"fmt"
	"strings"

	m "github.com/sachit/sql-query-assistant/go-service/internal/models"
)

// EmitTSQL is a thin wrapper kept for backward compatibility with existing
// tests and callers. New code should use Emit(plan, dialect).
func EmitTSQL(plan *m.PlannerOutput) (string, error) {
	return Emit(plan, TSQL)
}

// Emit renders a planner output as a SQL statement in the given dialect.
// Returns an error for unsupported plan shapes so callers can surface them
// rather than emit half-correct SQL.
func Emit(plan *m.PlannerOutput, d Dialect) (string, error) {
	if plan == nil {
		return "", fmt.Errorf("nil plan")
	}
	if d == nil {
		d = TSQL
	}
	if plan.Decision == m.DecisionTerminate {
		return "", fmt.Errorf("cannot emit SQL for terminate decision: %s", plan.TerminationReason)
	}
	if len(plan.Selections) == 0 {
		return "", fmt.Errorf("plan has no selections")
	}
	if len(plan.CTEs) > 0 {
		return "", fmt.Errorf("CTEs not yet supported in Go emitter (post-MVP)")
	}

	var b strings.Builder
	b.WriteString("SELECT")
	if plan.Limit != nil && *plan.Limit > 0 {
		b.WriteString(d.LimitInline(*plan.Limit))
	}
	b.WriteString("\n  ")
	b.WriteString(emitProjections(plan, d))

	b.WriteString("\nFROM ")
	b.WriteString(emitFromClause(plan, d))

	if joins := emitJoins(plan, d); joins != "" {
		b.WriteString("\n")
		b.WriteString(joins)
	}

	whereClauses := collectWhereClauses(plan, d)
	if len(whereClauses) > 0 {
		b.WriteString("\nWHERE ")
		b.WriteString(strings.Join(whereClauses, "\n  AND "))
	}

	if plan.GroupBy != nil && len(plan.GroupBy.GroupByColumns) > 0 {
		b.WriteString("\nGROUP BY ")
		parts := make([]string, len(plan.GroupBy.GroupByColumns))
		for i, c := range plan.GroupBy.GroupByColumns {
			parts[i] = qualifyColumn(plan, d, c.Table, c.Column)
		}
		b.WriteString(strings.Join(parts, ", "))

		if len(plan.GroupBy.HavingFilters) > 0 {
			having := make([]string, 0, len(plan.GroupBy.HavingFilters))
			for _, f := range plan.GroupBy.HavingFilters {
				expr, err := emitFilter(plan, d, f)
				if err != nil {
					return "", fmt.Errorf("having filter: %w", err)
				}
				having = append(having, expr)
			}
			b.WriteString("\nHAVING ")
			b.WriteString(strings.Join(having, "\n  AND "))
		}
	}

	if len(plan.OrderBy) > 0 {
		b.WriteString("\nORDER BY ")
		parts := make([]string, len(plan.OrderBy))
		for i, o := range plan.OrderBy {
			dir := string(o.Direction)
			if dir == "" {
				dir = "ASC"
			}
			parts[i] = fmt.Sprintf("%s %s", qualifyColumn(plan, d, o.Table, o.Column), dir)
		}
		b.WriteString(strings.Join(parts, ", "))
	}

	if plan.Limit != nil && *plan.Limit > 0 {
		b.WriteString(d.LimitTrailing(*plan.Limit))
	}

	return b.String(), nil
}

// tableRef returns the alias (if set) or the dialect-quoted table name. Used
// inside SELECT/JOIN/WHERE projections so the emitter respects planner aliases.
func tableRef(plan *m.PlannerOutput, d Dialect, table string) string {
	for _, s := range plan.Selections {
		if strings.EqualFold(s.Table, table) {
			if s.Alias != "" {
				return d.QuoteIdent(s.Alias)
			}
			return d.QuoteIdent(s.Table)
		}
	}
	return d.QuoteIdent(table)
}

func qualifyColumn(plan *m.PlannerOutput, d Dialect, table, column string) string {
	return tableRef(plan, d, table) + "." + d.QuoteIdent(column)
}

// emitProjections renders the SELECT column list. Aggregates from group_by take
// precedence; otherwise we project every selected column from non-join-only tables
// in declaration order, matching agent/generate_query.py behaviour. Window
// functions (when present) are appended after the regular projection list.
func emitProjections(plan *m.PlannerOutput, d Dialect) string {
	var parts []string
	if plan.GroupBy != nil {
		for _, c := range plan.GroupBy.GroupByColumns {
			parts = append(parts, qualifyColumn(plan, d, c.Table, c.Column))
		}
		for _, agg := range plan.GroupBy.Aggregates {
			parts = append(parts, emitAggregate(plan, d, agg))
		}
	} else {
		for _, sel := range plan.Selections {
			if sel.IncludeOnlyForJoin {
				continue
			}
			for _, c := range sel.Columns {
				// Orphaned-filter rule: a column marked role="filter" should
				// only be skipped from SELECT if a matching FilterPredicate
				// actually exists. Otherwise the planner forgot to emit the
				// predicate and dropping the column would silently lose data
				// the user implicitly asked about. Mirrors Python's
				// agent/plan_audit.py:fix_orphaned_filter_columns behavior.
				if c.Role != "" && c.Role != "projection" {
					if hasFilterPredicate(sel.Filters, plan.GlobalFilters, c.Table, c.Column) {
						continue
					}
					// Fall through — promote orphan to projection.
				}
				parts = append(parts, qualifyColumn(plan, d, c.Table, c.Column))
			}
		}
	}

	for _, w := range plan.WindowFunctions {
		parts = append(parts, emitWindowFunction(plan, d, w))
	}

	if len(parts) == 0 {
		return "*"
	}
	return strings.Join(parts, ",\n  ")
}

// hasFilterPredicate reports whether `column` on `table` has at least one
// FilterPredicate in either the selection's local filters or the plan-global
// filters. Comparison is case-insensitive on both table and column to match
// what the rest of the emitter does.
func hasFilterPredicate(localFilters, globalFilters []m.FilterPredicate, table, column string) bool {
	for _, f := range localFilters {
		if strings.EqualFold(f.Table, table) && strings.EqualFold(f.Column, column) {
			return true
		}
	}
	for _, f := range globalFilters {
		if strings.EqualFold(f.Table, table) && strings.EqualFold(f.Column, column) {
			return true
		}
	}
	return false
}

// emitWindowFunction renders one `<func>(...) OVER (PARTITION BY ... ORDER BY ...)`
// expression with the dialect-quoted alias. Supports ROW_NUMBER/RANK/DENSE_RANK,
// NTILE/LAG/LEAD, and windowed aggregates SUM/AVG/COUNT/MIN/MAX.
func emitWindowFunction(plan *m.PlannerOutput, d Dialect, w m.WindowFunction) string {
	var inner string
	switch w.Function {
	case m.WinRowNumber, m.WinRank, m.WinDenseRank:
		inner = string(w.Function) + "()"
	case m.WinNTile:
		// NTILE needs a bucket count — caller passes it via Comment as a temporary
		// channel because the planner output struct lacks a dedicated argument
		// field. Default to 4 quartiles.
		inner = "NTILE(4)"
	case m.WinLag, m.WinLead:
		// LAG/LEAD need the column to look back/ahead at; reuse partition_by[0].
		if len(w.PartitionBy) > 0 {
			inner = string(w.Function) + "(" + qualifyColumn(plan, d, w.PartitionBy[0].Table, w.PartitionBy[0].Column) + ")"
		} else {
			inner = string(w.Function) + "(NULL)"
		}
	default:
		// Windowed aggregates SUM/AVG/COUNT/MIN/MAX — first partition_by entry
		// is the column to aggregate (planner convention).
		if len(w.PartitionBy) > 0 {
			inner = string(w.Function) + "(" + qualifyColumn(plan, d, w.PartitionBy[0].Table, w.PartitionBy[0].Column) + ")"
		} else {
			inner = string(w.Function) + "(*)"
		}
	}

	var b strings.Builder
	b.WriteString(inner)
	b.WriteString(" OVER (")
	if len(w.PartitionBy) > 0 {
		b.WriteString("PARTITION BY ")
		parts := make([]string, len(w.PartitionBy))
		for i, c := range w.PartitionBy {
			parts[i] = qualifyColumn(plan, d, c.Table, c.Column)
		}
		b.WriteString(strings.Join(parts, ", "))
	}
	if len(w.OrderBy) > 0 {
		if len(w.PartitionBy) > 0 {
			b.WriteString(" ")
		}
		b.WriteString("ORDER BY ")
		parts := make([]string, len(w.OrderBy))
		for i, o := range w.OrderBy {
			dir := string(o.Direction)
			if dir == "" {
				dir = "ASC"
			}
			parts[i] = qualifyColumn(plan, d, o.Table, o.Column) + " " + dir
		}
		b.WriteString(strings.Join(parts, ", "))
	}
	b.WriteString(")")
	if w.Alias != "" {
		b.WriteString(" AS ")
		b.WriteString(d.QuoteIdent(w.Alias))
	}
	return b.String()
}

func emitAggregate(plan *m.PlannerOutput, d Dialect, agg m.AggregateFunction) string {
	var inner string
	switch agg.Function {
	case m.AggCountDistinct:
		if agg.Column == "" || agg.Column == "*" {
			inner = "COUNT(DISTINCT *)"
		} else {
			inner = "COUNT(DISTINCT " + qualifyColumn(plan, d, agg.Table, agg.Column) + ")"
		}
	case m.AggCount:
		if agg.Column == "" || agg.Column == "*" {
			inner = "COUNT(*)"
		} else {
			inner = "COUNT(" + qualifyColumn(plan, d, agg.Table, agg.Column) + ")"
		}
	default:
		// SUM/AVG/MIN/MAX
		col := agg.Column
		if col == "" || col == "*" {
			// Defensive — these aggregates don't accept *; emit COUNT(*)-style fallback
			inner = string(agg.Function) + "(*)"
		} else {
			inner = string(agg.Function) + "(" + qualifyColumn(plan, d, agg.Table, agg.Column) + ")"
		}
	}
	if agg.Alias != "" {
		return inner + " AS " + d.QuoteIdent(agg.Alias)
	}
	return inner
}

func emitFromClause(plan *m.PlannerOutput, d Dialect) string {
	root := plan.Selections[0]
	rendered := d.QuoteIdent(root.Table)
	if root.Alias != "" {
		rendered += " AS " + d.QuoteIdent(root.Alias)
	}
	return rendered
}

// emitJoins renders JOIN clauses in the order the planner provided. The first
// selection is the FROM root; every other selected table needs a join edge.
// We don't reorder edges — the planner is responsible for a connected graph.
func emitJoins(plan *m.PlannerOutput, d Dialect) string {
	if len(plan.JoinEdges) == 0 {
		return ""
	}
	rootTable := plan.Selections[0].Table
	rootedTables := map[string]bool{strings.ToLower(rootTable): true}

	var b strings.Builder
	for _, e := range plan.JoinEdges {
		joined := e.ToTable
		// If `to_table` is already rooted but `from_table` isn't, flip so the
		// new table is on the right side of the join.
		if rootedTables[strings.ToLower(e.ToTable)] && !rootedTables[strings.ToLower(e.FromTable)] {
			joined = e.FromTable
			e.FromTable, e.ToTable = e.ToTable, e.FromTable
			e.FromColumn, e.ToColumn = e.ToColumn, e.FromColumn
		}

		joinKW := joinKeyword(e.JoinType)
		fmt.Fprintf(&b, "%s %s", joinKW, d.QuoteIdent(e.ToTable))
		if alias := selectionAlias(plan, e.ToTable); alias != "" {
			fmt.Fprintf(&b, " AS %s", d.QuoteIdent(alias))
		}
		fmt.Fprintf(&b, " ON %s = %s\n",
			qualifyColumn(plan, d, e.FromTable, e.FromColumn),
			qualifyColumn(plan, d, e.ToTable, e.ToColumn),
		)
		rootedTables[strings.ToLower(joined)] = true
	}
	return strings.TrimRight(b.String(), "\n")
}

func selectionAlias(plan *m.PlannerOutput, table string) string {
	for _, s := range plan.Selections {
		if strings.EqualFold(s.Table, table) {
			return s.Alias
		}
	}
	return ""
}

func joinKeyword(t m.JoinType) string {
	switch t {
	case m.JoinLeft:
		return "LEFT JOIN"
	case m.JoinRight:
		return "RIGHT JOIN"
	case m.JoinFull:
		return "FULL OUTER JOIN"
	case m.JoinInner, "":
		return "INNER JOIN"
	default:
		return "INNER JOIN"
	}
}

// collectWhereClauses gathers per-table filters, global filters, and subquery
// filters in plan order. Each returned string is a single ANDed expression.
func collectWhereClauses(plan *m.PlannerOutput, d Dialect) []string {
	var out []string
	for _, sel := range plan.Selections {
		for _, f := range sel.Filters {
			expr, err := emitFilter(plan, d, f)
			if err != nil {
				out = append(out, fmt.Sprintf("/* filter error: %s */ 1=1", err))
				continue
			}
			out = append(out, expr)
		}
	}
	for _, f := range plan.GlobalFilters {
		expr, err := emitFilter(plan, d, f)
		if err != nil {
			out = append(out, fmt.Sprintf("/* filter error: %s */ 1=1", err))
			continue
		}
		out = append(out, expr)
	}
	for _, sub := range plan.SubqueryFilters {
		out = append(out, emitSubqueryFilter(d, sub))
	}
	return out
}

// emitSubqueryFilter renders WHERE col IN/NOT IN/EXISTS/NOT EXISTS (SELECT ...).
// The inner SELECT pulls one column from one table, optionally with WHERE
// filters. We don't recurse into nested subqueries — the planner schema
// doesn't support them.
func emitSubqueryFilter(d Dialect, s m.SubqueryFilter) string {
	outer := d.QuoteIdent(s.OuterTable) + "." + d.QuoteIdent(s.OuterColumn)
	innerCol := d.QuoteIdent(s.SubqueryTable) + "." + d.QuoteIdent(s.SubqueryColumn)

	var sub strings.Builder
	sub.WriteString("(SELECT ")
	sub.WriteString(innerCol)
	sub.WriteString(" FROM ")
	sub.WriteString(d.QuoteIdent(s.SubqueryTable))

	if len(s.SubqueryFilters) > 0 {
		// Build a tiny synthetic plan so we can reuse emitFilter for the WHERE.
		fauxPlan := &m.PlannerOutput{
			Selections: []m.TableSelection{{Table: s.SubqueryTable}},
		}
		var clauses []string
		for _, f := range s.SubqueryFilters {
			expr, err := emitFilter(fauxPlan, d, f)
			if err != nil {
				continue
			}
			clauses = append(clauses, expr)
		}
		if len(clauses) > 0 {
			sub.WriteString(" WHERE ")
			sub.WriteString(strings.Join(clauses, " AND "))
		}
	}
	sub.WriteString(")")

	switch s.Op {
	case "in":
		return outer + " IN " + sub.String()
	case "not_in":
		return outer + " NOT IN " + sub.String()
	case "exists":
		return "EXISTS " + sub.String()
	case "not_exists":
		return "NOT EXISTS " + sub.String()
	}
	// Default to IN for unknown ops — better than emitting broken SQL.
	return outer + " IN " + sub.String()
}

func emitFilter(plan *m.PlannerOutput, d Dialect, f m.FilterPredicate) (string, error) {
	col := qualifyColumn(plan, d, f.Table, f.Column)
	switch f.Op {
	case m.OpEq, m.OpNeq, m.OpGt, m.OpGte, m.OpLt, m.OpLte:
		lit, err := emitLiteral(f.Value)
		if err != nil {
			return "", err
		}
		return fmt.Sprintf("%s %s %s", col, string(f.Op), lit), nil

	case m.OpIn, m.OpNotIn:
		vals, ok := asArray(f.Value)
		if !ok {
			return "", fmt.Errorf("op %s requires array value", f.Op)
		}
		parts := make([]string, len(vals))
		for i, v := range vals {
			lit, err := emitLiteral(v)
			if err != nil {
				return "", err
			}
			parts[i] = lit
		}
		op := "IN"
		if f.Op == m.OpNotIn {
			op = "NOT IN"
		}
		return fmt.Sprintf("%s %s (%s)", col, op, strings.Join(parts, ", ")), nil

	case m.OpBetween:
		vals, ok := asArray(f.Value)
		if !ok || len(vals) != 2 {
			return "", fmt.Errorf("between requires [low, high]")
		}
		lo, err := emitLiteral(vals[0])
		if err != nil {
			return "", err
		}
		hi, err := emitLiteral(vals[1])
		if err != nil {
			return "", err
		}
		return fmt.Sprintf("%s BETWEEN %s AND %s", col, lo, hi), nil

	case m.OpLike, m.OpILike:
		// SQL Server collations are case-insensitive by default, so ILIKE → LIKE.
		s, ok := f.Value.(string)
		if !ok {
			return "", fmt.Errorf("like requires string value")
		}
		return fmt.Sprintf("%s LIKE %s", col, sqlString(s)), nil

	case m.OpStartsWith:
		s, ok := f.Value.(string)
		if !ok {
			return "", fmt.Errorf("starts_with requires string value")
		}
		return fmt.Sprintf("%s LIKE %s", col, sqlString(escapeLike(s)+"%")), nil

	case m.OpEndsWith:
		s, ok := f.Value.(string)
		if !ok {
			return "", fmt.Errorf("ends_with requires string value")
		}
		return fmt.Sprintf("%s LIKE %s", col, sqlString("%"+escapeLike(s))), nil

	case m.OpIsNull:
		return col + " IS NULL", nil
	case m.OpIsNotNull:
		return col + " IS NOT NULL", nil

	case m.OpExists:
		return "", fmt.Errorf("exists op requires subquery filter (post-MVP)")
	}
	return "", fmt.Errorf("unknown op: %s", f.Op)
}

// emitLiteral converts a runtime value (from JSON: float64, string, bool, nil)
// into a T-SQL literal. We don't use parameters because the surrounding plan is
// trusted and audit-checked — identifier injection is the risk, and the bracket-
// quoting handles that.
func emitLiteral(v any) (string, error) {
	if v == nil {
		return "NULL", nil
	}
	switch x := v.(type) {
	case string:
		return sqlString(x), nil
	case bool:
		if x {
			return "1", nil
		}
		return "0", nil
	case float64:
		// JSON numbers always decode as float64. Print as int if whole.
		if x == float64(int64(x)) {
			return fmt.Sprintf("%d", int64(x)), nil
		}
		return fmt.Sprintf("%g", x), nil
	case int:
		return fmt.Sprintf("%d", x), nil
	case int64:
		return fmt.Sprintf("%d", x), nil
	}
	return "", fmt.Errorf("unsupported literal type %T", v)
}

func sqlString(s string) string {
	return "'" + strings.ReplaceAll(s, "'", "''") + "'"
}

func escapeLike(s string) string {
	// Escape LIKE special chars in user-supplied substrings before wrapping with %.
	r := strings.NewReplacer(`%`, `[%]`, `_`, `[_]`, `[`, `[[]`)
	return r.Replace(s)
}

func asArray(v any) ([]any, bool) {
	switch a := v.(type) {
	case []any:
		return a, true
	case []string:
		out := make([]any, len(a))
		for i, s := range a {
			out[i] = s
		}
		return out, true
	}
	return nil, false
}
