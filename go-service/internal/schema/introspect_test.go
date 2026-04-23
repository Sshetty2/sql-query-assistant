package schema

import "testing"

func TestCleanDataType(t *testing.T) {
	cases := []struct {
		raw, want string
	}{
		{"NUMERIC(10,2)", "NUMERIC(10, 2)"},
		{"numeric(10, 2)", "NUMERIC(10, 2)"},
		{"int", "INTEGER"},
		{"INT", "INTEGER"},
		{"BLOB SUB_TYPE TEXT", "TEXT"},
		{`NVARCHAR(100) COLLATE "SQL_Latin1_General_CP1_CI_AS"`, "NVARCHAR(100)"},
		{"DATETIME", "DATETIME"},
		{"  varchar(50)  ", "VARCHAR(50)"},
	}
	for _, tc := range cases {
		got := CleanDataType(tc.raw)
		if got != tc.want {
			t.Errorf("CleanDataType(%q) = %q, want %q", tc.raw, got, tc.want)
		}
	}
}
