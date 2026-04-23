package chat

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"

	"github.com/sachit/sql-query-assistant/go-service/internal/agent"
	"github.com/sachit/sql-query-assistant/go-service/internal/llm"
	"github.com/sachit/sql-query-assistant/go-service/internal/logger"
	"github.com/sachit/sql-query-assistant/go-service/internal/models"
)

// head and trimSession are local helpers for log-friendly previews. The
// middleware in internal/server has the same shape but lives in a different
// package; duplicating the 6 LOC keeps the chat package import-free of the
// HTTP layer.
func head(s string, max int) string {
	s = strings.ReplaceAll(s, "\n", " ")
	if len(s) <= max {
		return s
	}
	return s[:max] + "…"
}

func trimSession(s string) string {
	if s == "" {
		return ""
	}
	if len(s) > 8 {
		return s[:8] + "…"
	}
	return s
}

// Event is the shape the chat agent emits to its consumer (an SSE handler).
// `Type` matches the SSE `event:` value the frontend expects:
//
//	token, tool_start, tool_result, suggest_revision, complete, tool_error,
//	status, error
//
// One field per event type is populated; consumers branch on Type.
type Event struct {
	Type string `json:"type"`

	// `token`
	Content string `json:"content,omitempty"`

	// `tool_start`
	Tool      string         `json:"tool,omitempty"`
	ToolInput map[string]any `json:"input,omitempty"`

	// `tool_result`
	ToolResult any `json:"result,omitempty"`

	// `suggest_revision`
	RevisedSQL  string `json:"revised_sql,omitempty"`
	Explanation string `json:"explanation,omitempty"`

	// `complete`
	ToolCallsRemaining int    `json:"tool_calls_remaining,omitempty"`
	SuggestNewQuery    bool   `json:"suggest_new_query,omitempty"`
	SuggestedQuery     string `json:"suggested_query,omitempty"`

	// `tool_error`, `error`
	Detail string `json:"detail,omitempty"`
}

// DataContext is what the chat agent needs to know about the most recent
// query when generating responses or running follow-up queries.
type DataContext struct {
	UserQuestion   string
	Query          string
	Result         []map[string]any
	DataSummary    *models.DataSummary
	PlannerOutput  *models.PlannerOutput
	FilteredSchema []map[string]any
	DBID           string
}

// QueryRunner abstracts how the chat agent re-runs the full pipeline. We keep
// it as an interface so tests can mock it without spinning up databases.
//
// In production this is a thin adapter around agent.RunQuery that builds a
// fresh agent.State from the caller's user-question + DBID.
type QueryRunner interface {
	Run(ctx context.Context, userQuestion, dbID string) (*agent.State, error)
}

// Agent ties together the session storage, LLM client, and a query runner.
// One Agent per server instance; per-request state lives in the Sessions map.
type Agent struct {
	Sessions    *Sessions
	QueryRunner QueryRunner
}

func NewAgent(sessions *Sessions, runner QueryRunner) *Agent {
	return &Agent{Sessions: sessions, QueryRunner: runner}
}

// maxToolCalls reads MAX_CHAT_TOOL_CALLS from env (default 3) — same name
// the Python service uses.
func maxToolCalls() int {
	if v := os.Getenv("MAX_CHAT_TOOL_CALLS"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			return n
		}
	}
	return 3
}

// StreamChat runs the agentic loop for one user message and emits events to
// the returned channel. The channel closes when the turn is done (either a
// `complete` or `error` event has been sent).
//
// Loop:
//  1. Append user message to session history.
//  2. Call ChatWithTools with full or suggest-only tools depending on budget.
//  3. If response has tool calls: execute each, emit events, append results,
//     and loop. If suggest_only response: emit `suggest_revision`, then
//     either keep looping or break depending on whether text accompanies it.
//  4. If response is text-only: emit `token` (single chunk) + `complete`.
func (a *Agent) StreamChat(ctx context.Context, sessionID, userMsg string, dataCtx DataContext) <-chan Event {
	out := make(chan Event, 16)

	go func() {
		defer close(out)

		log := logger.For(ctx).With(
			"chat_session", trimSession(sessionID),
			"db_id", dataCtx.DBID,
		)

		sess := a.Sessions.Get(sessionID)
		isNewSession := len(sess.Messages) == 0
		if isNewSession {
			// Seed the conversation with system prompt + data context.
			sess.Messages = append(sess.Messages, llm.Message{
				Role:    llm.RoleSystem,
				Content: chatSystemPrompt(dataCtx),
			})
		}
		sess.Messages = append(sess.Messages, llm.Message{Role: llm.RoleUser, Content: userMsg})

		log.Info("chat turn",
			"user_message", head(userMsg, 200),
			"new_session", isNewSession,
			"history_len", len(sess.Messages),
			"tool_call_count", sess.ToolCallCount,
			"has_data_ctx", dataCtx.Query != "" || len(dataCtx.Result) > 0,
			"data_ctx_query_head", head(dataCtx.Query, 120),
		)

		client, err := llm.NewForStage(llm.StageChat)
		if err != nil {
			log.Error("chat llm init failed", "err", err)
			out <- Event{Type: "error", Detail: "chat llm: " + err.Error()}
			return
		}

		// One LLM call per chat turn. Tool calls run synchronously and the
		// frontend gets the tool_result event directly; we don't loop back to
		// have the model summarize because that requires provider-specific
		// tool_use/tool_result content-block plumbing (Anthropic's API rejects
		// synthetic user messages claiming to be tool results). A second user
		// message in the same chat session naturally produces the followup.
		if ctx.Err() != nil {
			out <- Event{Type: "error", Detail: "cancelled"}
			return
		}

		tools := AllTools()
		if sess.ToolCallCount >= maxToolCalls() {
			tools = SuggestOnlyTools()
		}
		toolNames := make([]string, len(tools))
		for i, t := range tools {
			toolNames[i] = t.Name
		}
		log.Info("chat llm call", "tools_offered", toolNames)

		resp, err := client.ChatWithTools(ctx, sess.Messages, tools)
		if err != nil {
			log.Error("chat llm call failed", "err", err)
			out <- Event{Type: "error", Detail: "chat llm: " + err.Error()}
			return
		}

		// CRITICAL diagnostic: log what the LLM actually picked. If the user
		// said "I can't see the artist" and we see tool_calls=[run_query]
		// here, that's the prompt failing — not a workflow issue.
		pickedTools := make([]string, len(resp.ToolCalls))
		for i, tc := range resp.ToolCalls {
			pickedTools[i] = tc.Name
		}
		log.Info("chat llm response",
			"content_head", head(resp.Content, 200),
			"content_len", len(resp.Content),
			"tool_calls_picked", pickedTools,
		)

		// Append the assistant's reply (text only — we don't persist tool_use
		// blocks because we don't loop). The user's next message will pick up
		// from this point.
		if resp.Content != "" {
			sess.Messages = append(sess.Messages, llm.Message{
				Role:    llm.RoleAssistant,
				Content: resp.Content,
			})
			out <- Event{Type: "token", Content: resp.Content}
		}

		// Process each tool call in order. Each one fires its own SSE events.
		for _, tc := range resp.ToolCalls {
			log.Info("chat tool dispatch",
				"tool", tc.Name,
				"input_head", head(string(tc.Input), 200),
			)
			switch tc.Name {
			case RunQueryToolName:
				if !a.handleRunQuery(ctx, tc, sess, dataCtx, out) {
					return
				}
				sess.ToolCallCount++
			case RespondWithRevisionToolName:
				a.handleRespondWithRevision(tc, sess, out)
				// Doesn't increment ToolCallCount — matches Python.
			default:
				log.Warn("unknown tool requested", "tool", tc.Name)
				out <- Event{Type: "tool_error", Tool: tc.Name, Detail: "unknown tool"}
			}
		}

		log.Info("chat turn complete",
			"new_tool_call_count", sess.ToolCallCount,
			"text_emitted", resp.Content != "",
			"tools_dispatched", len(resp.ToolCalls),
		)
		out <- Event{
			Type:               "complete",
			Content:            resp.Content,
			ToolCallsRemaining: maxToolCalls() - sess.ToolCallCount,
		}
	}()

	return out
}

// handleRunQuery runs the full query pipeline and emits the tool events.
// Returns false if the caller should abort the turn entirely (e.g. the
// runner panic'd in a way we can't recover from). Today this always returns
// true; the bool is kept so future loop-based variants stay drop-in.
func (a *Agent) handleRunQuery(ctx context.Context, tc llm.ToolCall, sess *Session, dataCtx DataContext, out chan<- Event) bool {
	var args struct {
		Query string `json:"query"`
	}
	if err := json.Unmarshal(tc.Input, &args); err != nil || args.Query == "" {
		out <- Event{Type: "tool_error", Tool: tc.Name, Detail: "invalid args"}
		return true
	}

	out <- Event{
		Type:      "tool_start",
		Tool:      tc.Name,
		ToolInput: map[string]any{"query": args.Query},
	}

	if a.QueryRunner == nil {
		out <- Event{Type: "tool_error", Tool: tc.Name, Detail: "no QueryRunner configured"}
		return true
	}

	state, err := a.QueryRunner.Run(ctx, args.Query, dataCtx.DBID)
	if err != nil {
		out <- Event{Type: "tool_error", Tool: tc.Name, Detail: err.Error()}
		return true
	}

	out <- Event{Type: "tool_result", ToolResult: map[string]any{
		"query":     state.Query,
		"row_count": len(state.Result),
		"sample":    sampleRows(state.Result, 5),
	}}

	// Persist a compact note in history so future turns mention this query
	// even though we don't loop back for an immediate summary.
	sess.Messages = append(sess.Messages, llm.Message{
		Role: llm.RoleAssistant,
		Content: fmt.Sprintf("(Ran a follow-up query: %s — returned %d rows.)",
			state.Query, len(state.Result)),
	})
	return true
}

// handleRespondWithRevision emits the revision event and appends a synthetic
// assistant message capturing the suggestion so future turns see it.
func (a *Agent) handleRespondWithRevision(tc llm.ToolCall, sess *Session, out chan<- Event) {
	var args struct {
		Message     string `json:"message"`
		RevisedSQL  string `json:"revised_sql"`
		Explanation string `json:"explanation"`
	}
	if err := json.Unmarshal(tc.Input, &args); err != nil {
		out <- Event{Type: "tool_error", Tool: tc.Name, Detail: "invalid args: " + err.Error()}
		return
	}
	out <- Event{
		Type:        "suggest_revision",
		Content:     args.Message,
		RevisedSQL:  args.RevisedSQL,
		Explanation: args.Explanation,
	}
	sess.Messages = append(sess.Messages, llm.Message{
		Role:    llm.RoleAssistant,
		Content: args.Message,
	})
}

func sampleRows(rows []map[string]any, n int) []map[string]any {
	if len(rows) <= n {
		return rows
	}
	return rows[:n]
}

// chatSystemPrompt builds the system message seeding the conversation. It
// inlines the data context the LLM needs to answer follow-up questions
// without re-fetching anything.
func chatSystemPrompt(dc DataContext) string {
	summaryJSON, _ := json.Marshal(dc.DataSummary)
	sample, _ := json.Marshal(sampleRows(dc.Result, 5))
	planJSON, _ := json.Marshal(dc.PlannerOutput)

	return fmt.Sprintf(`You are a friendly data analyst chatting about a SQL query result.

# Tool selection — read carefully

You have two tools, but **most user messages need NEITHER tool — just reply in plain text.**

Default to plain-text replies for:
- Observations or complaints about the existing result ("I can't see X", "where is the Y column?", "this looks wrong")
- Questions you can answer from the data already shown ("which one is biggest?", "how many rows?")
- Greetings, acknowledgments, follow-up questions about meaning
- Anything ambiguous

**Only use a tool when one of these applies:**

## respond_with_revision (suggest new SQL — do NOT execute)
Use when the user wants the SQL itself to change. Trigger phrases:
- "revise/fix/change/adjust/rewrite/improve the query"
- "add a column for X", "remove the Y column", "filter by Z"
- "what would the query look like if…"
- "I want to also see the artist's name" (implies adding a column)
- "I can't see X" → if X is a column that COULD plausibly be added to the query, suggest adding it via respond_with_revision

Arguments: *message* (friendly explanation), *revised_sql* (the new SQL), *explanation* (one-line diff).

## run_query (run a brand new query end-to-end)
Use ONLY when the user asks for data that's COMPLETELY different from what's on screen — different question, different aggregation, different table the current SQL doesn't touch.
Trigger phrases:
- "how many tracks are in the database?" (count not on screen)
- "what about for USA customers?" (different filter than the run query)
- "show me the genres instead" (different table)

**Hard rule:** If the user's intent could be satisfied by tweaking the current SQL, use respond_with_revision — never run_query.

# Response style
Plain-text replies: 2-4 sentences. Be concrete with numbers. Reference the SQL or rows shown when relevant.

# CONTEXT

User asked: %q

SQL run:
%s

Data summary:
%s

First few rows:
%s

Plan structure:
%s`,
		dc.UserQuestion,
		"```sql\n"+dc.Query+"\n```",
		"```json\n"+string(summaryJSON)+"\n```",
		"```json\n"+string(sample)+"\n```",
		"```json\n"+string(planJSON)+"\n```",
	)
}
