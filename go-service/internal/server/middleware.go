package server

import (
	"bytes"
	"io"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/sachit/sql-query-assistant/go-service/internal/logger"
)

// requestLogger logs every HTTP request at INFO with method, path, status,
// duration, and (for POSTs) a small head of the body. This is the single
// most useful diagnostic for "is the frontend even calling the endpoint I
// think it's calling?" — if a chat reply triggered the SQL pipeline, this
// log shows whether the request hit /query/chat or /query/stream.
//
// We cap body logging at 512 bytes per request to keep log volume bounded.
func requestLogger() gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()

		// Capture a body snippet for POST/PATCH/PUT — but ONLY for our own
		// API endpoints, never for /databases/{...}/schema or other reads.
		var bodyHead string
		if shouldLogBody(c.Request.Method, c.FullPath()) {
			body, _ := io.ReadAll(c.Request.Body)
			c.Request.Body = io.NopCloser(bytes.NewReader(body)) // restore for handler
			bodyHead = head(string(body), 512)
		}

		c.Next()

		log := logger.For(c.Request.Context())
		log.Info("http",
			"method", c.Request.Method,
			"path", c.FullPath(),
			"status", c.Writer.Status(),
			"duration_ms", time.Since(start).Milliseconds(),
			"body_head", bodyHead,
			"page_session", trimSession(c.GetHeader("x-page-session")),
		)
	}
}

func shouldLogBody(method, path string) bool {
	if method == "GET" {
		return false
	}
	// Avoid logging arbitrary request bodies for routes that aren't ours;
	// gin's c.FullPath() is "" for unknown routes.
	return strings.HasPrefix(path, "/query") || path == "/cancel"
}

func head(s string, max int) string {
	s = strings.ReplaceAll(s, "\n", " ")
	if len(s) <= max {
		return s
	}
	return s[:max] + "…"
}

// trimSession returns "abcdef12…" for a 64-char hex session, "" for empty,
// and the raw value for anything malformed (so we notice).
func trimSession(s string) string {
	if s == "" {
		return ""
	}
	if len(s) > 8 {
		return s[:8] + "…"
	}
	return s
}
