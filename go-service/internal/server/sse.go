package server

import (
	"encoding/json"
	"fmt"
	"net/http"

	"github.com/gin-gonic/gin"
)

// sseHeaders sets the standard SSE response headers. Mirrors the values
// server.py uses for /query/stream so any reverse-proxy quirks (X-Accel-Buffering)
// behave identically.
func sseHeaders(c *gin.Context) {
	h := c.Writer.Header()
	h.Set("Content-Type", "text/event-stream")
	h.Set("Cache-Control", "no-cache")
	h.Set("Connection", "keep-alive")
	h.Set("X-Accel-Buffering", "no")
	c.Writer.WriteHeader(http.StatusOK)
}

// sendSSE writes one event and flushes immediately so the client sees it
// without buffering. Returns true on success; false means the client closed
// the connection (the caller should stop the workflow).
func sendSSE(c *gin.Context, event string, payload any) bool {
	data, err := json.Marshal(payload)
	if err != nil {
		// Marshaling our own structs shouldn't fail; if it does we still try to
		// send a textual hint so the client doesn't sit waiting silently.
		data = []byte(fmt.Sprintf(`{"detail":"marshal error: %s"}`, err))
	}
	if _, err := fmt.Fprintf(c.Writer, "event: %s\ndata: %s\n\n", event, data); err != nil {
		return false
	}
	flusher, ok := c.Writer.(http.Flusher)
	if !ok {
		return false
	}
	flusher.Flush()
	return true
}
