package server

import "github.com/sachit/sql-query-assistant/go-service/internal/models"

// QueryRequest mirrors server.py:QueryRequest. JSON tags match exactly so the
// React frontend can hit either service without a payload change.
type QueryRequest struct {
	Prompt        string `json:"prompt" binding:"required,max=10000"`
	SortOrder     string `json:"sort_order,omitempty"`
	ResultLimit   int    `json:"result_limit,omitempty"`
	TimeFilter    string `json:"time_filter,omitempty"`
	ChatSessionID string `json:"chat_session_id,omitempty"`
	DBID          string `json:"db_id,omitempty"`
}

// QueryResponse mirrors server.py:QueryResponse for the MVP fields. Post-MVP
// fields (modification_options, data_summary, narrative, etc.) are omitted —
// they get added when those nodes are ported.
type QueryResponse struct {
	Messages                 []string               `json:"messages"`
	UserQuestion             string                 `json:"user_question"`
	Query                    string                 `json:"query"`
	Result                   []map[string]any       `json:"result"`
	SortOrder                string                 `json:"sort_order"`
	ResultLimit              int                    `json:"result_limit"`
	TimeFilter               string                 `json:"time_filter"`
	LastStep                 string                 `json:"last_step"`
	ErrorIteration           int                    `json:"error_iteration"`
	RefinementIteration      int                    `json:"refinement_iteration"`
	CorrectionHistory        []string               `json:"correction_history"`
	RefinementHistory        []string               `json:"refinement_history"`
	TablesUsed               []string               `json:"tables_used"`
	ThreadID                 string                 `json:"thread_id,omitempty"`
	QueryID                  string                 `json:"query_id,omitempty"`
	PlannerOutput            *models.PlannerOutput  `json:"planner_output,omitempty"`
	NeedsClarification       bool                   `json:"needs_clarification"`
	ClarificationSuggestions []string               `json:"clarification_suggestions"`
	ExecutedPlan             *models.PlannerOutput  `json:"executed_plan,omitempty"`
	FilteredSchema           []map[string]any       `json:"filtered_schema,omitempty"`
	TotalRecordsAvailable    int                    `json:"total_records_available,omitempty"`
	DataSummary              *models.DataSummary       `json:"data_summary,omitempty"`
	ModificationOptions      *models.ModificationOptions `json:"modification_options,omitempty"`
	QueryNarrative           string                    `json:"query_narrative,omitempty"`
}

// SSEStatusEvent is the payload of a `status` SSE event. Field set matches
// server.py's status dict exactly.
type SSEStatusEvent struct {
	Type         string         `json:"type"`
	NodeName     string         `json:"node_name"`
	NodeStatus   string         `json:"node_status"`
	NodeMessage  string         `json:"node_message,omitempty"`
	NodeLogs     []string       `json:"node_logs,omitempty"`
	LogLevel     string         `json:"log_level,omitempty"`
	NodeMetadata map[string]any `json:"node_metadata,omitempty"`
}

// SSEErrorEvent is the payload of an `error` SSE event.
type SSEErrorEvent struct {
	Detail string `json:"detail"`
}
