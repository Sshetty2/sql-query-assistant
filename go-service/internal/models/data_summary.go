package models

// DataSummary mirrors the dict shape produced by
// agent/generate_data_summary.py:compute_data_summary. The frontend reads
// this exact shape, so JSON tags and field semantics must match Python.
type DataSummary struct {
	RowCount              int                       `json:"row_count"`
	TotalRecordsAvailable *int                      `json:"total_records_available"`
	ColumnCount           int                       `json:"column_count"`
	Columns               map[string]*ColumnSummary `json:"columns"`
}

// ColumnSummary holds per-column stats. The set of populated fields depends
// on `Type` — numeric columns get min/max/avg/median/sum, text gets length
// stats + top_values, datetime gets min/max/range_days. We use pointers for
// numeric stats so a legitimate 0 (e.g. min=0) survives JSON serialization.
type ColumnSummary struct {
	Type          string `json:"type"` // numeric | text | datetime | boolean | null
	NullCount     int    `json:"null_count"`
	DistinctCount int    `json:"distinct_count"`

	// Numeric
	Min    *float64 `json:"min,omitempty"`
	Max    *float64 `json:"max,omitempty"`
	Avg    *float64 `json:"avg,omitempty"`
	Median *float64 `json:"median,omitempty"`
	Sum    *float64 `json:"sum,omitempty"`

	// Text
	MinLength  *int             `json:"min_length,omitempty"`
	MaxLength  *int             `json:"max_length,omitempty"`
	AvgLength  *float64         `json:"avg_length,omitempty"`
	TopValues  []TopValueEntry  `json:"top_values,omitempty"`

	// Datetime — reuse Min/Max as ISO strings via the dedicated fields
	// to avoid type collision with the numeric pointers above.
	MinDatetime string   `json:"min_datetime,omitempty"`
	MaxDatetime string   `json:"max_datetime,omitempty"`
	RangeDays   *float64 `json:"range_days,omitempty"`
}

// TopValueEntry is one of up to five most-common values for a text column.
type TopValueEntry struct {
	Value string `json:"value"`
	Count int    `json:"count"`
}
