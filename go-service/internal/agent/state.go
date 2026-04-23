// Package agent holds the workflow state and orchestrator. Nodes are in
// internal/agent/nodes; this file defines the State that flows between them.
package agent

import (
	"database/sql"

	"github.com/sachit/sql-query-assistant/go-service/internal/models"
	"github.com/sachit/sql-query-assistant/go-service/internal/schema"
)

// SortOrder mirrors agent/state.py:sort_order. "Default" means the planner picks.
type SortOrder string

const (
	SortDefault    SortOrder = "Default"
	SortAscending  SortOrder = "Ascending"
	SortDescending SortOrder = "Descending"
)

// TimeFilter mirrors agent/state.py:time_filter.
type TimeFilter string

const (
	TimeAll    TimeFilter = "All Time"
	TimeDay    TimeFilter = "Last 24 Hours"
	TimeWeek   TimeFilter = "Last 7 Days"
	TimeMonth  TimeFilter = "Last 30 Days"
	TimeYear   TimeFilter = "Last Year"
)

// State is the workflow's mutable bag. Only the fields the MVP reads or writes
// are present — the Python TypedDict has many more, all optional, that will
// be added as post-MVP nodes are ported.
type State struct {
	// Inputs
	UserQuestion string
	DBID         string
	SortOrder    SortOrder
	ResultLimit  int
	TimeFilter   TimeFilter

	// Connection lives across nodes; cleanup closes it.
	DBConn *sql.DB

	// Schema progression: full -> filtered -> truncated (column-pruned) -> markdown
	Schema          []schema.Table
	FilteredSchema  []schema.Table
	TruncatedSchema []schema.Table
	SchemaMarkdown  string

	// Two-stage planning
	PrePlanStrategy string
	PlannerOutput   *models.PlannerOutput

	// SQL + execution
	Query                 string
	Result                []map[string]any
	TotalRecordsAvailable int

	// Audit + clarification
	NeedsClarification       bool
	ClarificationSuggestions []string

	// Feedback loops (strategy-first error correction)
	ErrorFeedback        string
	RefinementFeedback   string
	ErrorIteration       int
	RefinementIteration  int
	CorrectionHistory    []string
	RefinementHistory    []string

	// Bookkeeping
	LastStep          string
	TerminationReason string
	Errors            []string

	// Phase 9 outputs (populated after a successful execute_query)
	DataSummary         *models.DataSummary
	ModificationOptions *models.ModificationOptions
	QueryNarrative      string
	ChatSessionID       string
}
