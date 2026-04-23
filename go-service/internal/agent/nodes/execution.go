package nodes

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/sachit/sql-query-assistant/go-service/internal/models"
	emitter "github.com/sachit/sql-query-assistant/go-service/internal/sql"
)

// GenerateQuery wraps the deterministic SQL emitter. Equivalent to
// agent/generate_query.py:generate_query — no LLM involved.
//
// `dialect` selects the target SQL flavour: "tsql" (default), "sqlite". The
// emitter natively renders the right LIMIT/TOP placement; no post-process
// rewrite is needed.
func GenerateQuery(plan *models.PlannerOutput, dialect string) (string, error) {
	return emitter.Emit(plan, emitter.DialectByName(dialect))
}

// ExecuteQuery runs the SQL against `conn` and returns rows as a slice of
// column→value maps. Mirrors agent/execute_query.py — values are coerced to
// JSON-friendly types on the way out (int64 stays int64, []byte → string).
func ExecuteQuery(ctx context.Context, conn *sql.DB, query string) ([]map[string]any, error) {
	if conn == nil {
		return nil, fmt.Errorf("nil database connection")
	}
	rows, err := conn.QueryContext(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("execute: %w", err)
	}
	defer rows.Close()

	cols, err := rows.Columns()
	if err != nil {
		return nil, err
	}

	out := make([]map[string]any, 0)
	for rows.Next() {
		// Each row needs its own destination slice.
		dest := make([]any, len(cols))
		ptrs := make([]any, len(cols))
		for i := range dest {
			ptrs[i] = &dest[i]
		}
		if err := rows.Scan(ptrs...); err != nil {
			return nil, fmt.Errorf("scan: %w", err)
		}
		row := make(map[string]any, len(cols))
		for i, c := range cols {
			row[c] = normalizeScannedValue(dest[i])
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

// normalizeScannedValue converts driver-specific types (mainly []byte from
// SQLite varchar columns) into something JSON marshallers handle naturally.
func normalizeScannedValue(v any) any {
	switch x := v.(type) {
	case []byte:
		return string(x)
	}
	return v
}
