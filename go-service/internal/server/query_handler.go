package server

import (
	"context"
	"net/http"

	"github.com/gin-gonic/gin"

	"github.com/sachit/sql-query-assistant/go-service/internal/agent"
	"github.com/sachit/sql-query-assistant/go-service/internal/cancel"
	"github.com/sachit/sql-query-assistant/go-service/internal/logger"
	"github.com/sachit/sql-query-assistant/go-service/internal/thread"
)

func (s *Server) registerQueryRoutes() {
	s.engine.POST("/query", s.queryHandler)
	s.engine.POST("/query/stream", s.queryStreamHandler)
}

// buildState turns a parsed QueryRequest into a workflow State seed.
func buildState(req QueryRequest) *agent.State {
	st := &agent.State{
		UserQuestion:  req.Prompt,
		DBID:          req.DBID,
		SortOrder:     agent.SortOrder(req.SortOrder),
		TimeFilter:    agent.TimeFilter(req.TimeFilter),
		ResultLimit:   req.ResultLimit,
		ChatSessionID: req.ChatSessionID,
	}
	if st.SortOrder == "" {
		st.SortOrder = agent.SortDefault
	}
	if st.TimeFilter == "" {
		st.TimeFilter = agent.TimeAll
	}
	return st
}

// stateToResponse normalises an agent.State into the wire-format QueryResponse.
func stateToResponse(st *agent.State, threadID, queryID string) QueryResponse {
	tables := make([]string, len(st.Schema))
	for i, t := range st.Schema {
		tables[i] = t.TableName
	}
	return QueryResponse{
		Messages:                 st.Errors, // MVP: surface errors as messages
		UserQuestion:             st.UserQuestion,
		Query:                    st.Query,
		Result:                   st.Result,
		SortOrder:                string(st.SortOrder),
		ResultLimit:              st.ResultLimit,
		TimeFilter:               string(st.TimeFilter),
		LastStep:                 st.LastStep,
		ErrorIteration:           st.ErrorIteration,
		RefinementIteration:      st.RefinementIteration,
		CorrectionHistory:        st.CorrectionHistory,
		RefinementHistory:        st.RefinementHistory,
		TablesUsed:               tables,
		ThreadID:                 threadID,
		QueryID:                  queryID,
		PlannerOutput:            st.PlannerOutput,
		NeedsClarification:       st.NeedsClarification,
		ClarificationSuggestions: st.ClarificationSuggestions,
		ExecutedPlan:             st.PlannerOutput,
		TotalRecordsAvailable:    st.TotalRecordsAvailable,
		DataSummary:              st.DataSummary,
		ModificationOptions:      st.ModificationOptions,
		QueryNarrative:           st.QueryNarrative,
		NarrativeRevision:        st.NarrativeRevision,
	}
}

// queryHandler is the synchronous entry point — runs the workflow to
// completion and returns the final state as one JSON body. Mirrors
// server.py:process_query.
func (s *Server) queryHandler(c *gin.Context) {
	var req QueryRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	threadID, _ := s.persistThread(c.Request.Context(), req)
	pageSession := cancel.ValidateSessionID(c.GetHeader("x-page-session"))
	ctx := logger.WithFields(c.Request.Context(),
		"thread_id", threadID,
		"page_session", pageSession, "endpoint", "/query")

	cancelCtx, releaseCancel := s.cancels.Register(ctx, pageSession)
	defer releaseCancel()

	st := buildState(req)
	final := agent.RunQuery(cancelCtx, st, nil)

	// Persist final state and CAPTURE the generated query_id so the response
	// can carry it back to the frontend. Without this, the chat panel sees
	// query_id="" and routes follow-ups to /query/stream instead of /query/chat.
	queryID := saveAndReturnQueryID(s.threads, threadID, req.Prompt, final)

	c.JSON(http.StatusOK, stateToResponse(final, threadID, queryID))
}

// queryStreamHandler is the SSE entry point. Mirrors server.py:stream_query —
// emits an immediate `request_received` ack, then a `status` event per node
// as the workflow advances, then a final `complete` event with the full
// response. On error, emits a single `error` event and ends the stream.
func (s *Server) queryStreamHandler(c *gin.Context) {
	var req QueryRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	sseHeaders(c)

	threadID, _ := s.persistThread(c.Request.Context(), req)
	pageSession := cancel.ValidateSessionID(c.GetHeader("x-page-session"))
	ctx := logger.WithFields(c.Request.Context(),
		"thread_id", threadID,
		"page_session", pageSession, "endpoint", "/query/stream")
	cancelCtx, releaseCancel := s.cancels.Register(ctx, pageSession)
	defer releaseCancel()

	// Immediate ack so the frontend shows progress without waiting for the
	// first node to start (DB introspection can take a moment).
	if !sendSSE(c, "status", SSEStatusEvent{
		Type:        "status",
		NodeName:    "request_received",
		NodeStatus:  "completed",
		NodeMessage: "Query received",
	}) {
		return
	}

	// Capture statuses on a buffered channel so node emission doesn't block on
	// the client. Tunable; 64 is plenty given our 13-node MVP.
	statusCh := make(chan agent.StatusUpdate, 64)
	doneCh := make(chan *agent.State, 1)

	st := buildState(req)
	go func() {
		final := agent.RunQuery(cancelCtx, st, func(u agent.StatusUpdate) {
			statusCh <- u
		})
		close(statusCh)
		doneCh <- final
	}()

	// Forward statuses to the SSE stream until the workflow finishes.
	for u := range statusCh {
		if !sendSSE(c, "status", SSEStatusEvent{
			Type:         "status",
			NodeName:     u.Node,
			NodeStatus:   u.Status,
			NodeMessage:  u.Message,
			NodeMetadata: u.Meta,
		}) {
			// Client gone; drain the channel by reading until closed but stop sending.
			for range statusCh {
			}
			<-doneCh
			return
		}
	}

	final := <-doneCh

	// Capture the generated query_id so the `complete` event can include it.
	// The frontend uses both thread_id AND query_id to decide whether to send
	// follow-ups via /query/chat vs /query/stream.
	queryID := saveAndReturnQueryID(s.threads, threadID, req.Prompt, final)

	if len(final.Errors) > 0 && len(final.Result) == 0 && final.Query == "" {
		// Hard failure (no SQL ever generated) — surface as `error` event.
		sendSSE(c, "error", SSEErrorEvent{Detail: final.Errors[len(final.Errors)-1]})
		return
	}
	sendSSE(c, "complete", stateToResponse(final, threadID, queryID))
}

// persistThread allocates a thread row up-front so subsequent saves (sync or
// streaming) attach to a stable id. Best-effort — failure here doesn't block
// the request. Returns (thread_id, "") because no query has run yet; the
// query_id comes from saveAndReturnQueryID after the workflow completes.
func (s *Server) persistThread(ctx context.Context, req QueryRequest) (string, string) {
	if s.threads == nil {
		return "", ""
	}
	tid, err := s.threads.CreateThread(req.Prompt)
	if err != nil {
		logger.For(ctx).Warn("thread create failed", "err", err)
		return "", ""
	}
	return tid, ""
}

// saveAndReturnQueryID writes the final workflow state to the thread store
// and returns the generated query_id. Returns "" when persistence is disabled
// or the save fails — callers fall back to thread_id-only chat sessions.
//
// CRITICAL: this query_id ends up in the QueryResponse. The frontend's chat
// panel checks `threadId && queryId` to decide whether to send follow-ups
// to /query/chat (chat agent) vs /query/stream (full pipeline). If we
// return "" here, every chat message becomes a fresh top-level query.
func saveAndReturnQueryID(store *thread.Store, threadID, userQuestion string, final *agent.State) string {
	if store == nil || threadID == "" {
		return ""
	}
	qid, err := store.SaveQueryState(threadID, userQuestion, map[string]any{
		"query":     final.Query,
		"last_step": final.LastStep,
		"row_count": len(final.Result),
		"result":    final.Result,
	})
	if err != nil {
		return ""
	}
	return qid
}

// quiet unused-imports complaint when these packages aren't always referenced.
var (
	_ = thread.NewAt
	_ = cancel.NewRegistry
)
