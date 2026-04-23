package models

// PatchOperation mirrors the dict the React frontend sends in PatchRequest.
// Only one of the four operation types is used per request; the unused fields
// stay at their zero values.
//
// Mirrors agent/transform_plan.py:apply_patch_operation's `operation` dict.
type PatchOperation struct {
	Operation string `json:"operation"` // add_column | remove_column | modify_order_by | modify_limit

	// add_column / remove_column
	Table  string `json:"table,omitempty"`
	Column string `json:"column,omitempty"`

	// modify_order_by
	OrderBy []OrderByColumn `json:"order_by,omitempty"`

	// modify_limit (pointer so the JSON shape can distinguish 0 from "absent")
	Limit *int `json:"limit,omitempty"`
}
