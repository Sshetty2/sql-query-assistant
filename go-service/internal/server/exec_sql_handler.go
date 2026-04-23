package server

import (
	"context"
	"net/http"

	"github.com/gin-gonic/gin"

	"github.com/sachit/sql-query-assistant/go-service/internal/agent/nodes"
	"github.com/sachit/sql-query-assistant/go-service/internal/cancel"
	"github.com/sachit/sql-query-assistant/go-service/internal/db"
	"github.com/sachit/sql-query-assistant/go-service/internal/logger"
	emitter "github.com/sachit/sql-query-assistant/go-service/internal/sql"
)

// ExecuteSQLRequest mirrors server.py:ExecuteSQLRequest.
type ExecuteSQLRequest struct {
	SQL      string `json:"sql" binding:"required,max=50000"`
	ThreadID string `json:"thread_id,omitempty"`
	QueryID  string `json:"query_id,omitempty"`
	DBID     string `json:"db_id,omitempty"`
}

// execSQLHandler streams SSE events while running a user-supplied SELECT
// against the same demo / production DB the rest of the workflow uses.
// Mirrors server.py:execute_sql (lines 742-873): SELECT-only validation,
// execute, return rows. Data summary is computed when the Phase-9 node lands.
func (s *Server) execSQLHandler(c *gin.Context) {
	var req ExecuteSQLRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	if err := emitter.IsSelectOnly(req.SQL); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	sseHeaders(c)

	pageSession := cancel.ValidateSessionID(c.GetHeader("x-page-session"))
	ctx := logger.WithFields(c.Request.Context(),
		"thread_id", req.ThreadID, "query_id", req.QueryID,
		"page_session", pageSession, "endpoint", "/query/execute-sql")
	cancelCtx, releaseCancel := s.cancels.Register(ctx, pageSession)
	defer releaseCancel()

	if !sendSSE(c, "status", SSEStatusEvent{
		Type:        "status",
		NodeName:    "execute_sql",
		NodeStatus:  "running",
		NodeMessage: "Executing SQL",
	}) {
		return
	}

	rows, err := executeUserSQL(cancelCtx, req.DBID, req.SQL)
	if err != nil {
		sendSSE(c, "error", SSEErrorEvent{Detail: err.Error()})
		return
	}

	sendSSE(c, "status", SSEStatusEvent{
		Type:        "status",
		NodeName:    "execute_sql",
		NodeStatus:  "completed",
		NodeMessage: rowCountMessage(len(rows)),
	})

	// Compute the same data_summary the main /query path produces so the
	// frontend's preview pane works identically regardless of which endpoint
	// served the SQL.
	totalRows := len(rows)
	summary := nodes.ComputeDataSummary(rows, &totalRows)

	// Build a minimal QueryResponse — the user-supplied SQL bypasses the
	// planner so most plan-shaped fields are intentionally empty. The frontend
	// already handles missing fields for execute-sql.
	resp := QueryResponse{
		Query:                 req.SQL,
		Result:                rows,
		LastStep:              "execute_sql",
		ThreadID:              req.ThreadID,
		QueryID:               req.QueryID,
		TotalRecordsAvailable: totalRows,
		DataSummary:           summary,
	}
	sendSSE(c, "complete", resp)
}

// executeUserSQL opens the right DB, runs the (already validated) SELECT, and
// returns rows. Pulled out so we can reuse it for tests and not duplicate the
// db.Open + nodes.ExecuteQuery boilerplate.
func executeUserSQL(ctx context.Context, dbID, query string) ([]map[string]any, error) {
	conn, err := db.Open(dbID)
	if err != nil {
		return nil, err
	}
	defer conn.Close()
	return nodes.ExecuteQuery(ctx, conn, query)
}

func rowCountMessage(n int) string {
	switch n {
	case 0:
		return "0 rows"
	case 1:
		return "1 row"
	default:
		return formatInt(n) + " rows"
	}
}

// formatInt is intentionally simple — Go's fmt.Sprintf("%d", ...) would do but
// pulling in fmt for one int feels wasteful in this otherwise import-light file.
func formatInt(n int) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}
