package models

// TableRelevance mirrors models/table_selection.py:TableRelevance.
// Used as the structured-output schema for the Stage-3 LLM in filter_schema.
type TableRelevance struct {
	TableName       string   `json:"table_name" jsonschema:"description=The exact table name being assessed"`
	IsRelevant      bool     `json:"is_relevant" jsonschema:"description=Whether this table is needed to answer the user's query"`
	Reasoning       string   `json:"reasoning" jsonschema:"description=Brief explanation of why this table is or isn't relevant"`
	RelevantColumns []string `json:"relevant_columns" jsonschema:"description=Exact column names from the table's 'Available columns' list. Do NOT invent column names. Empty if no columns are relevant."`
}

// TableSelectionOutput mirrors models/table_selection.py:TableSelectionOutput.
type TableSelectionOutput struct {
	SelectedTables []TableRelevance `json:"selected_tables" jsonschema:"description=Per-table relevance assessments. Mark relevant only if directly needed to answer the query."`
}
