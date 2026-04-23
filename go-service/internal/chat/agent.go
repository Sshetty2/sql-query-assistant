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
			tools = RespondOnlyTools()
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

		// If the model calls `respond`, its `message` field is the user-facing
		// reply — any loose text on resp.Content is preamble we should suppress.
		// Otherwise fall back to resp.Content (legacy plain-text path; also the
		// safety net if the model ignored the contract).
		respondMessage := ""
		respondCalled := false
		for _, tc := range resp.ToolCalls {
			if tc.Name == RespondToolName {
				respondCalled = true
				var args struct {
					Message string `json:"message"`
				}
				_ = json.Unmarshal(tc.Input, &args)
				respondMessage = args.Message
				break
			}
		}

		if !respondCalled && resp.Content != "" {
			sess.Messages = append(sess.Messages, llm.Message{
				Role:    llm.RoleAssistant,
				Content: resp.Content,
			})
			out <- Event{Type: "token", Content: resp.Content}
		}

		// Process each tool call in order. Each one fires its own SSE events.
		// We track whether run_query fired AND captured rows so we can
		// synthesize a fallback respond below if the model forgot to.
		runQueryFired := false
		var runQuerySummary string
		for _, tc := range resp.ToolCalls {
			log.Info("chat tool dispatch",
				"tool", tc.Name,
				"input_head", head(string(tc.Input), 200),
			)
			switch tc.Name {
			case RunQueryToolName:
				runQueryFired = true
				if !a.handleRunQuery(ctx, tc, sess, dataCtx, out) {
					return
				}
				sess.ToolCallCount++
				// Pull the most recent row count off the session to seed
				// the fallback message. handleRunQuery appends a synthetic
				// assistant message describing the run; reuse its text.
				if n := len(sess.Messages); n > 0 {
					runQuerySummary = sess.Messages[n-1].Content
				}
			case RespondToolName:
				a.handleRespond(tc, sess, out)
				// Doesn't increment ToolCallCount — matches Python.
			default:
				log.Warn("unknown tool requested", "tool", tc.Name)
				out <- Event{Type: "tool_error", Tool: tc.Name, Detail: "unknown tool"}
			}
		}

		// Fallback: when run_query fired without an accompanying respond, the
		// user would otherwise see the new SQL/rows but no chat message. Emit
		// a synthetic respond so the chat thread isn't dead-air. The proper
		// fix is multi-turn tool conversations (see POST_MVP); this keeps the
		// UX intact in the meantime.
		if runQueryFired && !respondCalled {
			fallback := runQuerySummary
			if fallback == "" {
				fallback = "Ran a follow-up query — see the SQL and rows above."
			}
			a.emitSyntheticRespond(fallback, sess, out)
			respondMessage = fallback
			respondCalled = true
		}

		completeContent := resp.Content
		if respondCalled {
			completeContent = respondMessage
		}

		log.Info("chat turn complete",
			"new_tool_call_count", sess.ToolCallCount,
			"respond_called", respondCalled,
			"text_emitted", completeContent != "",
			"tools_dispatched", len(resp.ToolCalls),
		)
		out <- Event{
			Type:               "complete",
			Content:            completeContent,
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

// handleRespond processes the terminal `respond` tool call. When revised_sql
// is present it also emits a `suggest_revision` event so the frontend renders
// the revision card; the `message` text is always appended to session history
// and streamed back to the user via a token event emitted separately by the
// main loop (we also ensure it lands in the `complete` event's Content).
func (a *Agent) handleRespond(tc llm.ToolCall, sess *Session, out chan<- Event) {
	var args struct {
		Message     string `json:"message"`
		RevisedSQL  string `json:"revised_sql"`
		Explanation string `json:"explanation"`
	}
	if err := json.Unmarshal(tc.Input, &args); err != nil {
		out <- Event{Type: "tool_error", Tool: tc.Name, Detail: "invalid args: " + err.Error()}
		return
	}

	// If the model gave us SQL without an explanation, synthesize one so the
	// revision card still renders — better than swallowing the SQL.
	if args.RevisedSQL != "" && args.Explanation == "" {
		args.Explanation = "SQL revision"
	}

	if args.RevisedSQL != "" {
		out <- Event{
			Type:        "suggest_revision",
			Content:     args.Message,
			RevisedSQL:  args.RevisedSQL,
			Explanation: args.Explanation,
		}
	}

	// Stream the message as a token event for typewriter parity with the
	// previous plain-text path. The main loop's terminal `complete` event
	// will repeat the content, matching the Python service.
	if args.Message != "" {
		out <- Event{Type: "token", Content: args.Message}
	}

	sess.Messages = append(sess.Messages, llm.Message{
		Role:    llm.RoleAssistant,
		Content: args.Message,
	})
}

// emitSyntheticRespond produces the same wire events handleRespond would for
// a model that fired run_query but skipped the terminal respond call. Used
// as a safety net so the chat thread isn't dead-air. The text is also
// appended to session history so the next user turn sees it.
func (a *Agent) emitSyntheticRespond(message string, sess *Session, out chan<- Event) {
	out <- Event{Type: "token", Content: message}
	sess.Messages = append(sess.Messages, llm.Message{
		Role:    llm.RoleAssistant,
		Content: message,
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

# How to respond — read carefully

Every chat turn ends with exactly one call to the ` + "`respond`" + ` tool. There is no plain-text reply mode — text emitted outside of ` + "`respond`" + ` will not reach the user.

## respond(message, revised_sql?, explanation?)
- ` + "`message`" + ` (required): your reply, in markdown. 2-4 sentences. Concrete with numbers, grounded in the data shown.
- ` + "`revised_sql`" + ` (optional): a complete revised SELECT query.
- ` + "`explanation`" + ` (optional, required when ` + "`revised_sql`" + ` is set): one-line summary of what changed in the SQL.

**Include ` + "`revised_sql`" + ` + ` + "`explanation`" + ` whenever the reply involves — or could involve — a SQL change.** That covers:
- "revise/fix/change/adjust/rewrite/improve the query"
- "add a column for X", "remove the Y column", "filter by Z"
- "what would the query look like if…"
- "I want to also see the artist's name" (implies adding a column)
- "I can't see X" → if X is a column that could plausibly be added, include the revision

**Never describe a SQL problem without proposing the fix in the same call.** If you notice the query is wrong, revise it — don't just complain about it.

Omit ` + "`revised_sql`" + ` / ` + "`explanation`" + ` only for pure-commentary replies that don't touch the SQL: answering a question from the data, acknowledgments, greetings.

## run_query(query)
Use ONLY when the user asks for data that's COMPLETELY different from what's on screen — different question, different aggregation, a table the current SQL doesn't touch.
Trigger phrases:
- "how many tracks are in the database?" (count not on screen)
- "what about for USA customers?" (different filter than the run query)
- "show me the genres instead" (different table)

After ` + "`run_query`" + ` returns, summarize the new results by calling ` + "`respond`" + `.

**Hard rule:** If the user's intent could be satisfied by tweaking the current SQL, use ` + "`respond`" + ` with a ` + "`revised_sql`" + ` — never ` + "`run_query`" + `.

# Revised SQL rules
- Produce a complete, executable query — not a diff or fragment.
- Base it on the current SQL shown in the data context.
- Only SELECT — never INSERT, UPDATE, DELETE, DROP, CREATE, or ALTER.

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
