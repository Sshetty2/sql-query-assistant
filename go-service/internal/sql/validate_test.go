package sql

import "testing"

func TestIsSelectOnly_Accepts(t *testing.T) {
	good := []string{
		"SELECT 1",
		"select * from customers",
		"  SELECT FirstName FROM customers WHERE Country = 'USA'  ",
		"WITH foo AS (SELECT 1) SELECT * FROM foo",
		"SELECT * FROM t -- a trailing comment",
		"SELECT * FROM t /* block comment */ WHERE x = 1",
		"SELECT * FROM t;",   // single trailing semicolon allowed
		"SELECT * FROM t;  ", // with trailing whitespace
	}
	for _, q := range good {
		if err := IsSelectOnly(q); err != nil {
			t.Errorf("expected accept, got reject for %q: %v", q, err)
		}
	}
}

func TestIsSelectOnly_Rejects(t *testing.T) {
	cases := []struct {
		name  string
		query string
	}{
		{"empty", ""},
		{"whitespace", "   "},
		{"insert", "INSERT INTO t VALUES (1)"},
		{"update", "UPDATE t SET x=1"},
		{"delete", "DELETE FROM t"},
		{"drop", "DROP TABLE t"},
		{"alter", "ALTER TABLE t ADD COLUMN x INT"},
		{"create", "CREATE TABLE t (x INT)"},
		{"truncate", "TRUNCATE TABLE t"},
		{"exec", "EXEC sp_help 't'"},
		{"two statements", "SELECT 1; SELECT 2"},
		{"select then insert", "SELECT 1; INSERT INTO t VALUES (1)"},
		{"comment hiding insert", "SELECT 1 /* comment */; /* */ INSERT INTO t VALUES (1)"},
		{"line comment hiding update", "SELECT 1 -- nothing\n;UPDATE t SET x=1"},
		{"non-select start", "EXPLAIN SELECT * FROM t"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if err := IsSelectOnly(tc.query); err == nil {
				t.Errorf("expected reject, got accept for: %s", tc.query)
			}
		})
	}
}

func TestIsSelectOnly_WordBoundary(t *testing.T) {
	// Substrings that contain a banned keyword as a substring should NOT trip
	// the boundary-aware check. e.g. `CREATED_AT` contains CREATE; `DROPDOWN`
	// contains DROP; `UPDATER` contains UPDATE.
	good := []string{
		"SELECT CREATED_AT FROM logs",
		"SELECT DROPDOWN_VALUE FROM forms",
		"SELECT UPDATER FROM audit",
	}
	for _, q := range good {
		if err := IsSelectOnly(q); err != nil {
			t.Errorf("word-boundary false positive for %q: %v", q, err)
		}
	}
}
