package sql

import "fmt"

// Dialect captures the per-target differences in our otherwise-shared SQL
// emitter. Two implementations live alongside this file:
//   - tsqlDialect (SQL Server): SELECT TOP n + bracket quoting
//   - sqliteDialect: SELECT … LIMIT n at the end
//
// Both still bracket every identifier ([name]) — SQLite accepts brackets as a
// Microsoft-compat extension and using the same shape avoids divergence
// between the SQL we show in the UI and the SQL we execute against demo DBs.
type Dialect interface {
	// QuoteIdent wraps an identifier so reserved keywords can't break the query.
	QuoteIdent(name string) string
	// LimitInline is rendered immediately after `SELECT` (T-SQL: " TOP n").
	// Returns "" for dialects that put LIMIT at the end.
	LimitInline(n int) string
	// LimitTrailing is appended to the end of the query (SQLite: "LIMIT n").
	// Returns "" for dialects that put it inline.
	LimitTrailing(n int) string
	// Name is used in error messages and tests.
	Name() string
}

// DialectByName returns the dialect for a string name. Unknown / empty maps
// to T-SQL (the default) since SQL Server is the production target.
func DialectByName(name string) Dialect {
	switch name {
	case "sqlite":
		return SQLite
	case "tsql", "":
		return TSQL
	}
	// Unknown dialect — fall back rather than fail; emitter callers shouldn't
	// have to special-case names. T-SQL is the safest default.
	return TSQL
}

// ---------------------------------------------------------------------------
// T-SQL
// ---------------------------------------------------------------------------

type tsqlDialect struct{}

// TSQL is the SQL Server dialect. Emits SELECT TOP n with bracket quoting.
var TSQL Dialect = tsqlDialect{}

func (tsqlDialect) Name() string { return "tsql" }

func (tsqlDialect) QuoteIdent(name string) string {
	// `]` inside an identifier must be doubled — same convention SQL Server uses.
	out := make([]byte, 0, len(name)+2)
	out = append(out, '[')
	for i := 0; i < len(name); i++ {
		if name[i] == ']' {
			out = append(out, ']', ']')
		} else {
			out = append(out, name[i])
		}
	}
	out = append(out, ']')
	return string(out)
}

func (tsqlDialect) LimitInline(n int) string {
	if n <= 0 {
		return ""
	}
	return fmt.Sprintf(" TOP %d", n)
}

func (tsqlDialect) LimitTrailing(int) string { return "" }

// ---------------------------------------------------------------------------
// SQLite
// ---------------------------------------------------------------------------

type sqliteDialect struct{}

// SQLite is the SQLite dialect. Emits LIMIT n trailing; still uses bracket
// quoting (SQLite accepts `[name]` as a MS-compat shorthand).
var SQLite Dialect = sqliteDialect{}

func (sqliteDialect) Name() string { return "sqlite" }

func (sqliteDialect) QuoteIdent(name string) string {
	// Same bracket scheme as T-SQL — keeps emitted SQL consistent across dialects
	// and avoids changing the strings we show in the UI based on which DB we hit.
	return TSQL.QuoteIdent(name)
}

func (sqliteDialect) LimitInline(int) string { return "" }

func (sqliteDialect) LimitTrailing(n int) string {
	if n <= 0 {
		return ""
	}
	return fmt.Sprintf("\nLIMIT %d", n)
}
