package nodes

import (
	"context"
	"fmt"
	"strings"

	"github.com/sachit/sql-query-assistant/go-service/internal/schema"
)

// AnalyzeSchema runs against an open *sql.DB and returns the introspected schema.
// Wraps schema.IntrospectSQLite for the Phase-1 SQLite path. SQL Server support
// will land alongside the go-mssqldb wiring in Phase 6.
func AnalyzeSchema(ctx context.Context, conn interface {
	// Avoids importing database/sql in this file just for the type.
}) ([]schema.Table, error) {
	type sqliteConn interface {
		QueryContext(ctx context.Context, q string, args ...any) (any, error)
	}
	_ = sqliteConn(nil) // doc-only
	return nil, fmt.Errorf("AnalyzeSchema is wired through the orchestrator using *sql.DB")
}

// FormatSchemaMarkdown renders a list of tables to a compact markdown the LLM
// can consume. Mirrors agent/format_schema_markdown.py:format_schema_to_markdown
// with a simpler, single-section layout (we don't have the domain-specific
// metadata that the Python service interleaves).
func FormatSchemaMarkdown(tables []schema.Table) string {
	var b strings.Builder
	b.WriteString("# DATABASE SCHEMA\n\n")

	// Tables with FKs first — same ordering as Python so prompts diff cleanly.
	withFK := make([]schema.Table, 0, len(tables))
	withoutFK := make([]schema.Table, 0, len(tables))
	for _, t := range tables {
		if len(t.ForeignKeys) > 0 {
			withFK = append(withFK, t)
		} else {
			withoutFK = append(withoutFK, t)
		}
	}
	all := append(withFK, withoutFK...)

	for _, t := range all {
		fmt.Fprintf(&b, "## %s\n\n", t.TableName)
		if t.Metadata != nil && t.Metadata.PrimaryKey != "" {
			fmt.Fprintf(&b, "**Primary Key:** %s\n\n", t.Metadata.PrimaryKey)
		}
		if len(t.Columns) > 0 {
			b.WriteString("### Columns\n\n")
			b.WriteString("| Column Name | Data Type |\n")
			b.WriteString("|-------------|-----------|\n")
			for _, c := range t.Columns {
				fmt.Fprintf(&b, "| %s | %s |\n", c.ColumnName, c.DataType)
			}
			b.WriteString("\n")
		}
		if len(t.ForeignKeys) > 0 {
			b.WriteString("### Foreign Keys\n\n")
			for _, fk := range t.ForeignKeys {
				toCol := resolveFKColumn(fk, all)
				fmt.Fprintf(&b, "- **%s** → `%s.%s`\n", fk.ForeignKey, fk.PrimaryKeyTable, toCol)
			}
			b.WriteString("\n")
		}
		b.WriteString("---\n\n")
	}
	return b.String()
}

// resolveFKColumn mirrors Python's resolve_foreign_key_column:
// 1. explicit primary_key_column from FK
// 2. referenced table's metadata.primary_key
// 3. column with same name in referenced table
// 4. fall back to "ID"
func resolveFKColumn(fk schema.ForeignKey, all []schema.Table) string {
	if fk.PrimaryKeyColumn != "" {
		return fk.PrimaryKeyColumn
	}
	for _, t := range all {
		if t.TableName != fk.PrimaryKeyTable {
			continue
		}
		if t.Metadata != nil && t.Metadata.PrimaryKey != "" {
			return t.Metadata.PrimaryKey
		}
		for _, c := range t.Columns {
			if c.ColumnName == fk.ForeignKey {
				return c.ColumnName
			}
		}
	}
	return "ID"
}
