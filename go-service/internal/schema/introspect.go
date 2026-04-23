package schema

import (
	"context"
	"database/sql"
	"fmt"
	"regexp"
	"strings"
)

// Column matches the dict shape produced by database/introspection.py.
type Column struct {
	ColumnName string `json:"column_name"`
	DataType   string `json:"data_type"`
	IsNullable bool   `json:"is_nullable"`
}

// ForeignKey matches the per-column FK shape from database/introspection.py
// (multi-column FKs are exploded into one entry per column, same as Python).
type ForeignKey struct {
	ForeignKey       string `json:"foreign_key"`
	PrimaryKeyTable  string `json:"primary_key_table"`
	PrimaryKeyColumn string `json:"primary_key_column"`
}

type TableMetadata struct {
	PrimaryKey string `json:"primary_key"`
}

// Table matches the per-table dict produced by database/introspection.py.
// `Metadata` and `ForeignKeys` are omitted when empty/absent so JSON output
// is byte-compatible with the Python service.
type Table struct {
	TableName   string         `json:"table_name"`
	Columns     []Column       `json:"columns"`
	ForeignKeys []ForeignKey   `json:"foreign_keys,omitempty"`
	Metadata    *TableMetadata `json:"metadata,omitempty"`
}

var (
	collateRE = regexp.MustCompile(`(?i)\s+COLLATE\s+(?:"[^"]+"|'[^']+'|\S+)`)
	// Python's SQLAlchemy repr for NUMERIC(10, 2) inserts a space after the comma.
	// Normalise SQLite's compact form so JSON byte-output matches the Python service.
	commaInsideParens = regexp.MustCompile(`,(\S)`)
)

// sqliteTypeAliases maps SQLite affinity-based shorthand types to the canonical
// SQLAlchemy class names so JSON output matches the Python service byte-for-byte.
var sqliteTypeAliases = map[string]string{
	"INT":                "INTEGER",
	"BLOB SUB_TYPE TEXT": "TEXT",
}

// CleanDataType strips COLLATE clauses, collapses whitespace, normalises
// `NUMERIC(10,2)` → `NUMERIC(10, 2)`, uppercases the type, and rewrites a
// handful of SQLite affinity shorthands to match SQLAlchemy's `str(Type)` repr.
func CleanDataType(raw string) string {
	cleaned := collateRE.ReplaceAllString(raw, "")
	cleaned = strings.Join(strings.Fields(cleaned), " ")
	if strings.Contains(cleaned, "(") {
		cleaned = commaInsideParens.ReplaceAllString(cleaned, ", $1")
	}
	cleaned = strings.ToUpper(cleaned)
	if alias, ok := sqliteTypeAliases[cleaned]; ok {
		return alias
	}
	return cleaned
}

// IntrospectSQLite uses SQLite pragma queries to enumerate tables, columns, primary keys,
// and foreign keys in a way that matches the SQLAlchemy inspector output the Python service emits.
func IntrospectSQLite(ctx context.Context, conn *sql.DB) ([]Table, error) {
	tableNames, err := sqliteTableNames(ctx, conn)
	if err != nil {
		return nil, err
	}

	tables := make([]Table, 0, len(tableNames))
	for _, name := range tableNames {
		columns, pkColumns, err := sqliteColumns(ctx, conn, name)
		if err != nil {
			return nil, fmt.Errorf("columns for %s: %w", name, err)
		}
		fks, err := sqliteForeignKeys(ctx, conn, name)
		if err != nil {
			return nil, fmt.Errorf("foreign keys for %s: %w", name, err)
		}

		t := Table{TableName: name, Columns: columns}
		// Python only sets metadata.primary_key when there is a single-column PK.
		if len(pkColumns) == 1 {
			t.Metadata = &TableMetadata{PrimaryKey: pkColumns[0]}
		}
		if len(fks) > 0 {
			t.ForeignKeys = fks
		}
		tables = append(tables, t)
	}
	return tables, nil
}

func sqliteTableNames(ctx context.Context, conn *sql.DB) ([]string, error) {
	rows, err := conn.QueryContext(ctx,
		`SELECT name FROM sqlite_master
		 WHERE type='table' AND name NOT LIKE 'sqlite_%'
		 ORDER BY name`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var names []string
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			return nil, err
		}
		names = append(names, name)
	}
	return names, rows.Err()
}

func sqliteColumns(ctx context.Context, conn *sql.DB, table string) ([]Column, []string, error) {
	// pragma_table_info returns: cid, name, type, notnull, dflt_value, pk
	// Using the table-valued function form is safe against arbitrary table names because
	// it accepts the name as a bound argument (no string concatenation into SQL).
	rows, err := conn.QueryContext(ctx,
		`SELECT name, type, "notnull", pk FROM pragma_table_info(?)`, table)
	if err != nil {
		return nil, nil, err
	}
	defer rows.Close()

	var columns []Column
	type pkCol struct {
		name string
		idx  int
	}
	var pks []pkCol
	for rows.Next() {
		var name, typ string
		var notNull, pk int
		if err := rows.Scan(&name, &typ, &notNull, &pk); err != nil {
			return nil, nil, err
		}
		columns = append(columns, Column{
			ColumnName: name,
			DataType:   CleanDataType(typ),
			IsNullable: notNull == 0,
		})
		if pk > 0 {
			pks = append(pks, pkCol{name: name, idx: pk})
		}
	}
	if err := rows.Err(); err != nil {
		return nil, nil, err
	}

	pkNames := make([]string, len(pks))
	for i, p := range pks {
		pkNames[i] = p.name
		_ = p.idx // composite PK ordering not needed; Python only uses len()==1 case
	}
	return columns, pkNames, nil
}

func sqliteForeignKeys(ctx context.Context, conn *sql.DB, table string) ([]ForeignKey, error) {
	// pragma_foreign_key_list returns: id, seq, table, from, to, on_update, on_delete, match.
	// We emit FKs in pragma's natural (id ASC, seq) order. SQLAlchemy reorders named
	// constraints to match CREATE TABLE declaration order, which would require parsing
	// sqlite_master here — out of scope for MVP since FK list order doesn't change LLM
	// consumption (the markdown formatter doesn't depend on it).
	rows, err := conn.QueryContext(ctx,
		`SELECT "table", "from", "to" FROM pragma_foreign_key_list(?)
		 ORDER BY id, seq`, table)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var fks []ForeignKey
	for rows.Next() {
		var refTable, fromCol string
		var toCol sql.NullString
		if err := rows.Scan(&refTable, &fromCol, &toCol); err != nil {
			return nil, err
		}
		fks = append(fks, ForeignKey{
			ForeignKey:       fromCol,
			PrimaryKeyTable:  refTable,
			PrimaryKeyColumn: toCol.String,
		})
	}
	return fks, rows.Err()
}
