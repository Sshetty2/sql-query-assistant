package nodes

import (
	"testing"
)

func TestComputeDataSummary_Empty(t *testing.T) {
	got := ComputeDataSummary(nil, nil)
	if got.RowCount != 0 || got.ColumnCount != 0 {
		t.Errorf("expected empty summary, got %+v", got)
	}
}

func TestComputeDataSummary_Numeric(t *testing.T) {
	rows := []map[string]any{
		{"price": 10.0}, {"price": 20.0}, {"price": 30.0}, {"price": nil},
	}
	got := ComputeDataSummary(rows, nil)
	if got.RowCount != 4 {
		t.Fatalf("row_count got %d want 4", got.RowCount)
	}
	col := got.Columns["price"]
	if col.Type != "numeric" {
		t.Fatalf("type got %q want numeric", col.Type)
	}
	if col.NullCount != 1 {
		t.Errorf("null_count got %d want 1", col.NullCount)
	}
	if col.DistinctCount != 3 {
		t.Errorf("distinct_count got %d want 3", col.DistinctCount)
	}
	if *col.Min != 10 || *col.Max != 30 || *col.Avg != 20 || *col.Median != 20 || *col.Sum != 60 {
		t.Errorf("numeric stats wrong: %+v", col)
	}
}

func TestComputeDataSummary_Text(t *testing.T) {
	rows := []map[string]any{
		{"city": "NYC"}, {"city": "LA"}, {"city": "NYC"}, {"city": "SF"},
	}
	got := ComputeDataSummary(rows, nil)
	col := got.Columns["city"]
	if col.Type != "text" {
		t.Fatalf("type got %q want text", col.Type)
	}
	if *col.MinLength != 2 || *col.MaxLength != 3 {
		t.Errorf("length stats: min=%d max=%d", *col.MinLength, *col.MaxLength)
	}
	if len(col.TopValues) == 0 || col.TopValues[0].Value != "NYC" || col.TopValues[0].Count != 2 {
		t.Errorf("top_values wrong: %+v", col.TopValues)
	}
}

func TestComputeDataSummary_Datetime(t *testing.T) {
	rows := []map[string]any{
		{"ts": "2026-01-01"},
		{"ts": "2026-01-15T12:00:00"},
		{"ts": "2026-01-31"},
	}
	got := ComputeDataSummary(rows, nil)
	col := got.Columns["ts"]
	if col.Type != "datetime" {
		t.Fatalf("type got %q want datetime", col.Type)
	}
	if col.MinDatetime != "2026-01-01" {
		t.Errorf("min_datetime got %q", col.MinDatetime)
	}
	if col.MaxDatetime != "2026-01-31" {
		t.Errorf("max_datetime got %q", col.MaxDatetime)
	}
	if *col.RangeDays < 29 || *col.RangeDays > 31 {
		t.Errorf("range_days got %v want ~30", *col.RangeDays)
	}
}

func TestComputeDataSummary_Boolean(t *testing.T) {
	rows := []map[string]any{
		{"active": true}, {"active": false}, {"active": true},
	}
	got := ComputeDataSummary(rows, nil)
	col := got.Columns["active"]
	if col.Type != "boolean" {
		t.Errorf("type got %q want boolean", col.Type)
	}
	if col.Min != nil || col.MinLength != nil {
		t.Errorf("boolean column should not have numeric/text stats: %+v", col)
	}
}

func TestComputeDataSummary_TotalRecordsAvailable(t *testing.T) {
	total := 1000
	rows := []map[string]any{{"x": 1.0}}
	got := ComputeDataSummary(rows, &total)
	if got.TotalRecordsAvailable == nil || *got.TotalRecordsAvailable != 1000 {
		t.Errorf("total_records_available not preserved: %v", got.TotalRecordsAvailable)
	}
}

func TestDetectColumnType_Mixed(t *testing.T) {
	// 2 numeric, 1 text → numeric wins
	if got := detectColumnType([]any{1.0, 2.0, "abc"}); got != "numeric" {
		t.Errorf("got %q want numeric", got)
	}
	// All datetime strings
	if got := detectColumnType([]any{"2026-01-01", "2026-02-01"}); got != "datetime" {
		t.Errorf("got %q want datetime", got)
	}
	// Empty
	if got := detectColumnType([]any{}); got != "null" {
		t.Errorf("got %q want null", got)
	}
}

// TestDetectColumnType_MajorityWins covers the case where a column has values
// of more than one type — the most common wins. Mirrors Python's
// test_data_summary.py:test_majority_type_wins.
func TestDetectColumnType_MajorityWins(t *testing.T) {
	cases := []struct {
		name   string
		values []any
		want   string
	}{
		{"3 text 1 numeric → text", []any{"a", "b", "c", 1.0}, "text"},
		{"1 text 3 numeric → numeric", []any{"a", 1.0, 2.0, 3.0}, "numeric"},
		{"1 datetime 3 text → text", []any{"2026-01-01", "a", "b", "c"}, "text"},
		{"all bools → boolean", []any{true, false, true}, "boolean"},
		{"numeric strings count as numeric", []any{"1", "2", "3"}, "numeric"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := detectColumnType(tc.values); got != tc.want {
				t.Errorf("got %q want %q (input: %v)", got, tc.want, tc.values)
			}
		})
	}
}

// TestComputeDataSummary_HighPrecisionDecimals covers tests/unit/test_decimal_serialization.py.
// Decimals from a SQL Server NUMERIC column round-trip through JSON as float64;
// we want to confirm the summary doesn't lose precision in min/max/sum.
func TestComputeDataSummary_HighPrecisionDecimals(t *testing.T) {
	rows := []map[string]any{
		{"price": 19.99},
		{"price": 0.01},
		{"price": 1234.5678},
	}
	got := ComputeDataSummary(rows, nil)
	col := got.Columns["price"]
	if col == nil || col.Type != "numeric" {
		t.Fatalf("expected numeric column, got: %+v", col)
	}
	if *col.Min != 0.01 {
		t.Errorf("min got %v want 0.01", *col.Min)
	}
	if *col.Max != 1234.5678 {
		t.Errorf("max got %v want 1234.5678", *col.Max)
	}
	// Sum of 19.99 + 0.01 + 1234.5678 = 1254.5678 — round to 4 decimals.
	want := 1254.5678
	if *col.Sum != want {
		t.Errorf("sum got %v want %v", *col.Sum, want)
	}
}

// TestComputeDataSummary_AllNullColumn — when every row in a column is null,
// we still emit a column entry with Type="null" so the frontend doesn't have
// to special-case missing columns.
func TestComputeDataSummary_AllNullColumn(t *testing.T) {
	rows := []map[string]any{
		{"x": nil}, {"x": nil}, {"x": nil},
	}
	got := ComputeDataSummary(rows, nil)
	col := got.Columns["x"]
	if col == nil {
		t.Fatal("expected column entry even when all-null")
	}
	if col.Type != "null" {
		t.Errorf("type got %q want null", col.Type)
	}
	if col.NullCount != 3 {
		t.Errorf("null_count got %d want 3", col.NullCount)
	}
}
