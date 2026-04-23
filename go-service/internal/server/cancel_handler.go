package server

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"github.com/sachit/sql-query-assistant/go-service/internal/cancel"
)

// CancelRequest mirrors server.py:CancelRequest. The session_id is the same
// per-tab page-session ID the frontend sends in the x-page-session header on
// /query/stream — that's how the cancel finds the in-flight workflow.
type CancelRequest struct {
	SessionID string `json:"session_id" binding:"required"`
}

// cancelHandler triggers cancellation for an in-flight workflow.
// Mirrors server.py /cancel (lines 887-901).
//
// Returns 200 with {"cancelled": true|false}; 400 on missing/invalid session_id.
// We return 200 even when the session isn't found because the frontend often
// fires cancel speculatively (e.g. on tab close) and shouldn't see error toasts
// for the common case where the request already completed.
func (s *Server) cancelHandler(c *gin.Context) {
	var req CancelRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}
	id := cancel.ValidateSessionID(req.SessionID)
	if id == "" {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid session_id format (need 64-char hex)"})
		return
	}
	cancelled := s.cancels.Cancel(id)
	c.JSON(http.StatusOK, gin.H{"cancelled": cancelled})
}
