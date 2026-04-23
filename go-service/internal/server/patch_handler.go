package server

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"github.com/sachit/sql-query-assistant/go-service/internal/agent"
	"github.com/sachit/sql-query-assistant/go-service/internal/agent/nodes"
	"github.com/sachit/sql-query-assistant/go-service/internal/cancel"
	"github.com/sachit/sql-query-assistant/go-service/internal/logger"
	"github.com/sachit/sql-query-assistant/go-service/internal/models"
	"github.com/sachit/sql-query-assistant/go-service/internal/schema"
)

// PatchRequest mirrors server.py:PatchRequest for /query/patch.
type PatchRequest struct {
	ThreadID       string                  `json:"thread_id" binding:"required"`
	UserQuestion   string                  `json:"user_question"`
	PatchOperation models.PatchOperation   `json:"patch_operation" binding:"required"`
	ExecutedPlan   *models.PlannerOutput   `json:"executed_plan" binding:"required"`
	FilteredSchema []map[string]any        `json:"filtered_schema"`
	ChatSessionID  string                  `json:"chat_session_id,omitempty"`
	DBID           string                  `json:"db_id,omitempty"`
}

// patchHandler streams SSE events while applying a patch operation to a
// previously-executed plan and re-running it. Same event vocabulary as
// /query/stream so the frontend's progress UI works without changes.
func (s *Server) patchHandler(c *gin.Context) {
	var req PatchRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	sseHeaders(c)

	pageSession := cancel.ValidateSessionID(c.GetHeader("x-page-session"))
	ctx := logger.WithFields(c.Request.Context(),
		"thread_id", req.ThreadID, "page_session", pageSession,
		"endpoint", "/query/patch")
	cancelCtx, releaseCancel := s.cancels.Register(ctx, pageSession)
	defer releaseCancel()

	if !sendSSE(c, "status", SSEStatusEvent{
		Type:        "status",
		NodeName:    "request_received",
		NodeStatus:  "completed",
		NodeMessage: "Patch request received",
	}) {
		return
	}

	// Apply the patch first (no DB needed). Bad patches fail fast as a 400-style
	// SSE error event without ever opening a database connection.
	filteredSchema := mapsToSchemaTables(req.FilteredSchema)
	patched, err := nodes.ApplyPatch(req.ExecutedPlan, req.PatchOperation, filteredSchema)
	if err != nil {
		sendSSE(c, "error", SSEErrorEvent{Detail: err.Error()})
		return
	}

	st := &agent.State{
		UserQuestion:   req.UserQuestion,
		DBID:           req.DBID,
		ChatSessionID:  req.ChatSessionID,
		FilteredSchema: filteredSchema,
		PlannerOutput:  patched,
	}

	statusCh := make(chan agent.StatusUpdate, 64)
	doneCh := make(chan *agent.State, 1)
	go func() {
		final := agent.RunPatch(cancelCtx, st, patched, func(u agent.StatusUpdate) {
			statusCh <- u
		})
		close(statusCh)
		doneCh <- final
	}()

	for u := range statusCh {
		if !sendSSE(c, "status", SSEStatusEvent{
			Type:         "status",
			NodeName:     u.Node,
			NodeStatus:   u.Status,
			NodeMessage:  u.Message,
			NodeMetadata: u.Meta,
		}) {
			for range statusCh {
			}
			<-doneCh
			return
		}
	}

	final := <-doneCh

	if len(final.Errors) > 0 && len(final.Result) == 0 && final.Query == "" {
		sendSSE(c, "error", SSEErrorEvent{Detail: final.Errors[len(final.Errors)-1]})
		return
	}
	sendSSE(c, "complete", stateToResponse(final, req.ThreadID, ""))
}

// mapsToSchemaTables converts the loosely-typed JSON schema the frontend sends
// back (in the patch request) into the strongly-typed schema the SQL emitter
// and modification options need. Only fields the patch flow actually reads
// (table_name, columns) are populated; FK metadata is dropped because patch
// can't introduce new joins.
func mapsToSchemaTables(in []map[string]any) []schema.Table {
	out := make([]schema.Table, 0, len(in))
	for _, t := range in {
		name, _ := t["table_name"].(string)
		if name == "" {
			continue
		}
		tbl := schema.Table{TableName: name}
		if cols, ok := t["columns"].([]any); ok {
			for _, raw := range cols {
				cm, _ := raw.(map[string]any)
				if cm == nil {
					continue
				}
				col := schema.Column{}
				col.ColumnName, _ = cm["column_name"].(string)
				col.DataType, _ = cm["data_type"].(string)
				col.IsNullable, _ = cm["is_nullable"].(bool)
				if col.ColumnName != "" {
					tbl.Columns = append(tbl.Columns, col)
				}
			}
		}
		out = append(out, tbl)
	}
	return out
}
