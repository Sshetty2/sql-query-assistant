package server

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"

	"github.com/gin-gonic/gin"

	"github.com/sachit/sql-query-assistant/go-service/internal/agent"
	"github.com/sachit/sql-query-assistant/go-service/internal/cancel"
	"github.com/sachit/sql-query-assistant/go-service/internal/chat"
	"github.com/sachit/sql-query-assistant/go-service/internal/logger"
)

// ChatRequest mirrors server.py:ChatRequest.
type ChatRequest struct {
	ThreadID  string `json:"thread_id"`
	QueryID   string `json:"query_id"`
	Message   string `json:"message" binding:"required"`
	SessionID string `json:"session_id"`
	DBID      string `json:"db_id"`
}

// ChatResetRequest mirrors server.py:ChatResetRequest.
type ChatResetRequest struct {
	SessionID string `json:"session_id" binding:"required"`
}

// chatHandler streams SSE events for one chat turn. Loads the most recent
// query state for the thread (so the agent has data context), then runs the
// agentic loop.
//
// Mirrors server.py:chat_query (lines 547-705).
func (s *Server) chatHandler(c *gin.Context) {
	var req ChatRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	sseHeaders(c)

	pageSession := cancel.ValidateSessionID(c.GetHeader("x-page-session"))
	ctx := logger.WithFields(c.Request.Context(),
		"thread_id", req.ThreadID, "query_id", req.QueryID,
		"chat_session", req.SessionID, "endpoint", "/query/chat")
	cancelCtx, releaseCancel := s.cancels.Register(ctx, pageSession)
	defer releaseCancel()

	dataCtx := s.buildChatDataContext(req)

	sessionID := req.SessionID
	if sessionID == "" {
		// Default to thread:query so subsequent turns find the same session.
		sessionID = req.ThreadID + ":" + req.QueryID
	}

	events := s.chatAgent.StreamChat(cancelCtx, sessionID, req.Message, dataCtx)
	for ev := range events {
		eventName := ev.Type
		if eventName == "" {
			eventName = "status"
		}
		if !sendSSE(c, eventName, ev) {
			// Client disconnected — drain.
			for range events {
			}
			return
		}
	}
}

// chatResetHandler clears a chat session.
// Mirrors server.py:chat_reset (lines 708-718).
func (s *Server) chatResetHandler(c *gin.Context) {
	var req ChatResetRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}
	if s.chatSessions == nil {
		c.JSON(http.StatusOK, gin.H{"reset": false})
		return
	}
	c.JSON(http.StatusOK, gin.H{"reset": s.chatSessions.Reset(req.SessionID)})
}

// buildChatDataContext loads the latest query for the thread (if any) and
// translates it into the chat agent's context shape. Falls back to an empty
// context when nothing is found — the agent will still answer, just without
// the data summary in scope.
func (s *Server) buildChatDataContext(req ChatRequest) chat.DataContext {
	dc := chat.DataContext{DBID: req.DBID}
	if s.threads == nil || req.ThreadID == "" {
		return dc
	}
	q, err := s.threads.GetLatestQueryState(req.ThreadID)
	if err != nil || q == nil {
		return dc
	}
	dc.UserQuestion = q.UserQuestion
	if v, ok := q.State["query"].(string); ok {
		dc.Query = v
	}
	if v, ok := q.State["result"].([]any); ok {
		// JSON round-trip the rows into the strongly-typed shape the chat agent expects.
		raw, _ := json.Marshal(v)
		_ = json.Unmarshal(raw, &dc.Result)
	}
	return dc
}

// liveQueryRunner is the production QueryRunner that calls into the actual
// agent.RunQuery pipeline so the chat's `run_query` tool runs the full
// planner → SQL → execute flow.
type liveQueryRunner struct{}

// Run executes the workflow and surfaces it as an error to the caller when
// the inner pipeline never produced executable SQL — otherwise the chat
// agent would emit a misleadingly-empty tool_result. State is still returned
// so the caller can render whatever partial info is available.
func (liveQueryRunner) Run(ctx context.Context, userQuestion, dbID string) (*agent.State, error) {
	st := &agent.State{
		UserQuestion: userQuestion,
		DBID:         dbID,
		SortOrder:    agent.SortDefault,
		TimeFilter:   agent.TimeAll,
	}
	final := agent.RunQuery(ctx, st, nil)

	// Two failure modes worth surfacing:
	//   1. Pipeline crashed before producing SQL (e.g. plan_audit / generate_query error).
	//   2. Planner decided to clarify/terminate without enough info to act.
	if final.Query == "" {
		if len(final.Errors) > 0 {
			return final, fmt.Errorf("%s", final.Errors[len(final.Errors)-1])
		}
		if final.TerminationReason != "" {
			return final, fmt.Errorf("%s", final.TerminationReason)
		}
		return final, fmt.Errorf("workflow did not produce a SQL query")
	}
	return final, nil
}
