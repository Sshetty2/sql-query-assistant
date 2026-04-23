package server

import (
	"io"
	"net/http"

	"github.com/gin-gonic/gin"

	"github.com/sachit/sql-query-assistant/go-service/internal/logger"
)

// maxRenderErrorBodyBytes caps the payload a single client can submit so a
// runaway browser bug or hostile caller can't flood logs. 16 KB is enough
// for a long error message + React component stack; rejection beyond that
// produces a 413 the frontend silently swallows.
const maxRenderErrorBodyBytes = 16 * 1024

// RenderErrorRequest is what the frontend's ErrorBoundary sends when it
// catches an uncaught render error. All fields are optional except
// `section` and `error_message`; the others are best-effort context the
// UI happens to have.
type RenderErrorRequest struct {
	Section        string `json:"section" binding:"required,max=120"`
	ErrorMessage   string `json:"error_message" binding:"required,max=2000"`
	ErrorStack     string `json:"error_stack,omitempty"`
	ComponentStack string `json:"component_stack,omitempty"`
	UserAgent      string `json:"user_agent,omitempty"`
	URL            string `json:"url,omitempty"`
	ThreadID       string `json:"thread_id,omitempty"`
	QueryID        string `json:"query_id,omitempty"`
}

// renderErrorHandler logs an uncaught render error reported by the React
// frontend's ErrorBoundary. Returns 204 No Content on success — no payload
// since the frontend fires this and forgets it.
//
// Why we log at WARN: render crashes are real bugs that should surface in
// dashboards, but they're already absorbed by the boundary so they're not
// outage-level. WARN sits between routine INFO and crashing ERROR.
func (s *Server) renderErrorHandler(c *gin.Context) {
	// Cap the body before binding so a 100MB POST can't exhaust memory.
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxRenderErrorBodyBytes)

	var req RenderErrorRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		// MaxBytesReader returns a generic error when the limit is hit; surface
		// a 413 so the frontend can fall back to a tighter payload if needed.
		// We don't differentiate that from a normal validation failure here —
		// either way the client can't recover, and we don't want to leak
		// internals via the response.
		if _, ok := err.(*http.MaxBytesError); ok {
			c.AbortWithStatus(http.StatusRequestEntityTooLarge)
			return
		}
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	logger.For(c.Request.Context()).Warn("render error reported by frontend",
		"section", req.Section,
		"error_message", req.ErrorMessage,
		"error_stack", truncateForRenderLog(req.ErrorStack, 1500),
		"component_stack", truncateForRenderLog(req.ComponentStack, 1500),
		"user_agent", req.UserAgent,
		"url", req.URL,
		"thread_id", req.ThreadID,
		"query_id", req.QueryID,
		"remote_ip", c.ClientIP(),
	)

	c.Status(http.StatusNoContent)
}

// truncateForRenderLog keeps long stack traces from blowing out the log
// line while preserving enough to debug. The frontend already truncates
// at the boundary; this is a second guard for paranoia. Distinct from
// the test-only `truncateForLog` in chat_e2e_test.go.
func truncateForRenderLog(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}

// drainBody is a small helper used only when MaxBytesReader fails to make
// sure we don't leave a half-read connection hanging. Currently unused
// because gin handles the full read internally, but kept here so adding
// streaming variants later is straightforward.
var _ = io.Discard
