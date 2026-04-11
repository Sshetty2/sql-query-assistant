# Chat Architecture

The conversational data assistant lets users ask follow-up questions about query results. When a question can't be answered from the current data, the chat agent autonomously executes a new query and summarizes the fresh results.

## Overview

The chat system is an **agentic loop** built on LangChain with tool-calling. After a main query completes, the LLM generates a narrative summary and seeds a conversation. The user can then ask questions in a side panel — the agent answers from the data context (summary statistics, data sample, schema, query plan) or invokes a `run_query` tool to fetch new data from the database.

```
User message
    |
    v
+---------------------------+
| LLM with tool binding     |
|  (system prompt includes  |
|   data context + history) |
+---------------------------+
    |               |
    v               v
 Text reply     Tool call: run_query("...")
    |               |
    |       +-------v-----------+
    |       | Execute full      |
    |       | query pipeline    |
    |       | (LangGraph)       |
    |       +---------+---------+
    |                 |
    |       +---------v---------+
    |       | Build tool result |
    |       | Update context    |
    |       +---------+---------+
    |                 |
    |       +---------v---------+
    |       | Loop back to LLM  |
    |       | (summarize result)|
    |       +-------------------+
    |               |
    v               v
 Yield SSE events to frontend
```

## Backend

### Chat Agent (`agent/chat_agent.py`)

The core module. Contains:

- **`prepare_data_context()`** — Builds a comprehensive text block for the LLM system prompt from query results, summary statistics, schema, and query plan. This is what the LLM "sees" about the data.
- **`stream_chat_agentic()`** — The agentic loop. Binds tools, invokes the LLM, detects tool calls, executes them, yields SSE events, and loops until the LLM produces a text response.
- **`generate_narrative()` / `generate_query_narrative_node()`** — One-shot LLM call after a main query completes. Produces a 2-4 sentence summary and seeds the conversation history so follow-up chat has context.

**Conversation memory** is in-process (`InMemoryChatMessageHistory` per session). It is **not** persisted to disk — if the server restarts, backend memory is lost. The frontend independently persists messages to `localStorage`.

**Tool call budget**: Each session gets `MAX_CHAT_TOOL_CALLS` (default: 3) tool invocations. After exhaustion, the system prompt switches to a no-tools variant and the LLM can only answer from context.

### Chat Tools (`agent/chat_tools.py`)

Defines a single LangChain `@tool`:

```python
@tool
def run_query(query: str) -> str:
    """Run a natural language query against the database..."""
    pass  # Signature only — execution is handled by the agentic loop
```

The tool definition gives the LLM the schema it needs to generate a tool call. Actual execution happens in `stream_chat_agentic()` where the tool call is intercepted and routed through `query_database()`.

### Data Summary (`agent/generate_data_summary.py`)

Deterministic (no LLM) column-level statistics computed after every successful query:

| Column Type | Statistics |
|-------------|-----------|
| Numeric | min, max, avg, median, sum |
| Text | min/max/avg length, top 5 values with counts |
| Datetime | min, max, range in days |
| All | null count, distinct count |

The summary is stored in workflow state (`data_summary`) and injected into the chat data context so the LLM can answer statistical questions without re-querying.

### Server Endpoints (`server.py`)

**`POST /query/chat`** — SSE streaming chat endpoint.

Request:
```json
{
  "thread_id": "abc-123",
  "query_id": "def-456",
  "message": "What's the average age?",
  "session_id": "optional-custom-id"
}
```

Loads the query state from disk (`thread_states.json`), builds data context, calls `stream_chat_agentic()`, and forwards events as SSE:

| SSE Event | Payload | When |
|-----------|---------|------|
| `token` | `{"content": "..."}` | LLM text chunk |
| `tool_start` | `{"tool": "run_query", "input": {"query": "..."}}` | Agent invokes a tool |
| `status` | `{"node_name": "...", "node_status": "running\|completed", ...}` | Workflow progress during tool execution |
| `tool_result` | Full `QueryResult` object | Tool query completed |
| `tool_error` | `{"detail": "...", "query": "..."}` | Tool execution failed |
| `complete` | `{"content": "...", "tool_calls_remaining": N}` | Final response |
| `error` | `{"detail": "..."}` | Unrecoverable error |

**`POST /query/chat/reset`** — Clears backend session memory and tool call counter.

### Thread State Storage (`utils/thread_manager.py`)

Query results are persisted to `thread_states.json` so the chat endpoint can reload them:

```
thread_states.json
  └─ threads
       └─ {thread_id}
            ├─ original_query
            ├─ created_at
            └─ queries[]
                 ├─ query_id
                 ├─ user_question
                 └─ state (full workflow state: result, schema, plan, summary, ...)
```

The chat endpoint calls `get_query_state(thread_id, query_id)` to load the state that provides data context for the conversation.

## Frontend

### API Client (`demo_frontend/src/api/client.ts`)

`streamChat(request, callbacks)` — POST-based SSE client (EventSource only supports GET, so a custom parser is used). Returns an `AbortController` for cancellation. Dispatches parsed events to typed callbacks:

```typescript
interface ChatStreamCallbacks {
  onToken: (event: ChatTokenEvent) => void;
  onComplete: (result: ChatCompleteEvent) => void;
  onError: (error: string) => void;
  onToolStart?: (event: ChatToolStartEvent) => void;
  onToolResult?: (result: QueryResult) => void;
  onToolError?: (event: ChatToolErrorEvent) => void;
  onStatus?: (event: StatusEvent) => void;
}
```

### Chat Hook (`demo_frontend/src/hooks/useChat.ts`)

React hook managing chat state:

```typescript
status: "idle" | "streaming" | "tool_running" | "complete" | "error"
messages: ChatMessage[]
streamingContent: string  // accumulates tokens during streaming
toolCallsRemaining: number | null
```

Key methods:
- **`send(threadId, queryId, message, sessionId)`** — Sends a message and starts streaming. Status transitions: `idle → streaming → [tool_running → streaming]* → complete`.
- **`appendUserMessage()` / `appendAssistantMessage()` / `appendDataSummary()`** — Direct message injection (used for seeding from main query results).
- **`resetConversation(sessionId)`** — Clears local state and calls `POST /query/chat/reset`.
- **`restoreMessages(saved)`** — Restore from saved conversation.

Accepts `UseChatOptions` for parent integration:
- `onToolResult` — Notify parent when tool produces new results
- `onToolStart` — Notify parent when tool execution begins
- `onStatus` — Forward workflow status events
- `storeResult` — Store result and return an ID for linking

### Conversation Persistence (`demo_frontend/src/hooks/useConversations.ts`)

Manages multiple conversations in `localStorage`:

```typescript
interface Conversation {
  id: string;              // UUID — doubles as chat_session_id
  name: string;            // Auto-named from first query
  createdAt: string;
  lastMessageAt: string;
  messages: ChatMessage[];
  resultIds: string[];     // References to stored QueryResult objects
}
```

Storage key: `"sql-assistant-conversations"`

Methods: `create`, `switchTo`, `remove`, `rename`, `updateMessages`, `addResultId`, `autoName`.

### Result Store (`demo_frontend/src/hooks/useResultStore.ts`)

`localStorage`-based cache for `QueryResult` objects linked from chat messages. Each result is stored under `"sql-assistant-result-{UUID}"`. When a conversation is deleted, its associated results are cleaned up.

### Chat Panel (`demo_frontend/src/components/ChatPanel.tsx`)

The side panel UI. Renders different message types:

| Role | Display |
|------|---------|
| `user` | Right-aligned bubble |
| `assistant` | Left-aligned text with markdown |
| `tool_start` | Blue card with spinner, shows the query being executed |
| `tool_result` | Green card with row/column counts, expandable data summary, click to view results |
| `tool_error` | Red card with error detail |
| `data_summary` | Violet card with column statistics, click to load results in main panel |

Features: auto-scroll, conversation switcher dropdown (rename/delete), tool call budget display, suggested query chips.

### App Integration (`demo_frontend/src/App.tsx`)

Wires everything together:

```
useQuery()          — main query execution (steps, result, status)
useChat(options)    — chat state (messages, streaming, tool handling)
useResultStore()    — result caching
useConversations()  — conversation persistence

chatOptions = {
  onToolStart  → clear workflow steps for fresh progress
  onToolResult → update main panel with new results
  storeResult  → cache result in localStorage
  onStatus     → forward workflow progress to timeline
}
```

When a main query completes:
1. Result is stored via `resultStore.store()`
2. Data summary is injected as a chat message (`appendDataSummary`)
3. Narrative is injected as an assistant message (`appendAssistantMessage`)
4. Conversation is auto-named from the query

When a chat tool query executes:
1. Workflow steps are cleared (`needsStepsClearRef`)
2. Status events stream into the timeline (`WorkflowProgress`)
3. `isStreaming` reflects `chat.status === "tool_running"`
4. Tool result updates the main panel and is stored for click-to-view

## Data Flow

### Main Query → Chat Seeding

```
User submits query via QueryInput
  → useQuery.execute() starts SSE stream to POST /query/stream
  → Backend runs full LangGraph workflow
  → generate_data_summary node computes statistics
  → generate_query_narrative node calls LLM for 2-4 sentence summary
     (also seeds backend conversation memory)
  → SSE complete event returns QueryResult with data_summary + query_narrative
  → App.tsx effect fires:
     1. Store result in localStorage
     2. Inject data_summary message into chat
     3. Inject narrative as assistant message
  → Chat is ready for follow-up questions
```

### Chat Message → Response

```
User types in ChatPanel
  → useChat.send(threadId, queryId, message, sessionId)
  → POST /query/chat with SSE response
  → Backend loads query state from thread_states.json
  → Builds data context (summary + schema + plan + sample)
  → stream_chat_agentic() starts agentic loop:

  LOOP:
    Bind tools (if budget remaining) → Invoke LLM

    IF text response:
      → Yield token + complete events
      → Frontend appends assistant message
      → Conversation persisted to localStorage
      → EXIT LOOP

    IF tool call (run_query):
      → Yield tool_start event
      → Execute query_database() (full pipeline)
      → Yield status events (workflow progress)
      → Yield tool_result event (full QueryResult)
      → Update system prompt with new data context
      → Increment tool call counter
      → CONTINUE LOOP (LLM summarizes results)
```

## Session Lifecycle

```
1. User submits first query
   → Conversation created (UUID = session ID)
   → Query executes, narrative generated, chat seeded

2. User asks follow-up questions
   → Messages sent with session ID
   → Backend maintains in-memory history
   → Frontend persists to localStorage

3. Chat agent uses run_query tool (up to 3 times)
   → New results shown in main panel
   → Stored in localStorage, linked from chat message
   → System prompt updated with fresh data

4. User switches conversation
   → Frontend restores messages from localStorage
   → Latest result loaded into main panel
   → Backend session is separate (new history on first message)

5. User deletes conversation
   → Frontend clears localStorage (messages + results)
   → Backend session cleared via POST /query/chat/reset
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_CHAT_TOOL_CALLS` | `3` | Max tool invocations per chat session |
| `REMOTE_MODEL_CHAT` / `LOCAL_MODEL_CHAT` | Falls back to strategy model | LLM model for chat and narrative |

## File Map

```
Backend:
  agent/chat_agent.py              # Agentic loop, data context, narrative generation
  agent/chat_tools.py              # Tool definitions (run_query)
  agent/generate_data_summary.py   # Deterministic column statistics
  utils/thread_manager.py          # Thread/query state persistence (JSON file)
  server.py                        # /query/chat and /query/chat/reset endpoints

Frontend:
  src/api/client.ts                # streamChat() SSE client
  src/api/types.ts                 # ChatMessage, ChatRequest, ChatCompleteEvent, etc.
  src/hooks/useChat.ts             # Chat state management hook
  src/hooks/useConversations.ts    # Multi-conversation localStorage persistence
  src/hooks/useResultStore.ts      # QueryResult localStorage cache
  src/components/ChatPanel.tsx     # Chat side panel UI
  src/App.tsx                      # Top-level wiring (chat ↔ query ↔ results)
```
