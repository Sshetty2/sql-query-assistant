package models

// ModificationOptions mirrors the dict produced by
// agent/generate_modification_options.py:generate_modification_options.
// The frontend reads this exact shape to render add/remove column buttons,
// the ORDER BY picker, and the LIMIT slider.
type ModificationOptions struct {
	Tables           map[string]TableOptions `json:"tables"`
	CurrentOrderBy   []OrderByColumn         `json:"current_order_by"`
	CurrentLimit     *int                    `json:"current_limit"`
	SortableColumns  []SortableColumn        `json:"sortable_columns"`
}

type TableOptions struct {
	Alias   string         `json:"alias,omitempty"`
	Columns []ColumnOption `json:"columns"`
}

type ColumnOption struct {
	Name         string `json:"name"`
	DisplayName  string `json:"display_name"`
	Type         string `json:"type"`
	Selected     bool   `json:"selected"`
	Role         string `json:"role,omitempty"`
	IsPrimaryKey bool   `json:"is_primary_key"`
	IsNullable   bool   `json:"is_nullable"`
}

type SortableColumn struct {
	Table       string `json:"table"`
	Column      string `json:"column"`
	Type        string `json:"type"`
	DisplayName string `json:"display_name"`
}

// OrderByColumn intentionally duplicates the OrderByColumn type from
// planner_output.go because the JSON shapes happen to be identical and
// having them be distinct structs would just push noise to callers.
//
// Keeping a re-declaration in this file would cause a duplicate-symbol error,
// so we reuse the existing type by alias here.
type orderByColumnAlias = OrderByColumn
