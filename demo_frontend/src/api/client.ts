import type {
  QueryRequest,
  PatchRequest,
  ExecuteSQLRequest,
  StatusEvent,
  QueryResult,
  ChatRequest,
  ChatTokenEvent,
  ChatToolStartEvent,
  ChatToolErrorEvent,
  ChatCompleteEvent,
  ChatSuggestRevisionEvent,
  DemoDatabase,
  SchemaTable,
} from "./types";
import { validateQueryResult } from "./schemas";

// All API calls go through the /api proxy on the same origin.
// In production, the Node server proxies /api/* to the backend via Railway private networking.
// In development, Vite's dev server proxy handles the same routing.

declare global {
  interface Window {
    __CSRF_TOKEN__?: string;
  }
}

/**
 * Get the CSRF token injected by the Express server.
 * In development (Vite dev server), no token is injected — the proxy skips validation.
 */
function getCsrfToken(): string | undefined {
  return window.__CSRF_TOKEN__;
}

/**
 * Build standard headers for all API requests.
 * Includes CSRF token (for Express validation) and page session ID
 * (for backend workflow cancellation tracking).
 */
function getApiHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const token = getCsrfToken();
  if (token) {
    headers["X-CSRF-Token"] = token;
    headers["X-Page-Session"] = token;
  }
  return headers;
}

// ---------------------------------------------------------------------------
// Cancel stale backend workflows on page reload
// ---------------------------------------------------------------------------
// Each page load gets a unique CSRF token. If sessionStorage has a different
// (old) token, a workflow from the previous page load may still be running.
const PREV_SESSION_KEY = "page_session_id";
const currentToken = getCsrfToken();

if (currentToken) {
  const prev = sessionStorage.getItem(PREV_SESSION_KEY);
  if (prev && prev !== currentToken) {
    // Fire-and-forget: cancel any running workflow from the old session
    fetch("/api/cancel", {
      method: "POST",
      headers: {
        ...getApiHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ session_id: prev }),
    }).catch(() => {}); // Best-effort — ignore failures
  }
  sessionStorage.setItem(PREV_SESSION_KEY, currentToken);
}

interface StreamCallbacks {
  onStatus: (event: StatusEvent) => void;
  onComplete: (result: QueryResult) => void;
  onError: (error: string) => void;
}

/**
 * Parse an SSE text stream into individual events.
 * SSE format: "event: <type>\ndata: <json>\n\n"
 */
function parseSSEEvents(
  buffer: string
): { events: Array<{ type: string; data: string }>; remaining: string } {
  const events: Array<{ type: string; data: string }> = [];
  const parts = buffer.split("\n\n");
  const remaining = parts.pop() || "";

  for (const part of parts) {
    if (!part.trim()) continue;

    const lines = part.split("\n");
    let eventType = "";
    let data = "";

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        eventType = line.slice(7);
      } else if (line.startsWith("data: ")) {
        data = line.slice(6);
      }
    }

    if (eventType && data) {
      events.push({ type: eventType, data });
    }
  }

  return { events, remaining };
}

/**
 * Map abort reasons and network errors to user-friendly messages.
 */
function handleStreamError(
  err: Error,
  controller: AbortController,
  callbacks: { onError: (error: string) => void },
) {
  if (err.name === "AbortError") {
    const reason = controller.signal.reason;
    if (reason === "connection_timeout") {
      callbacks.onError(
        "Unable to reach the server. Please check that the backend is running and try again."
      );
    } else if (reason === "idle_timeout") {
      callbacks.onError(
        "The server stopped responding. The query may have timed out. Please try again."
      );
    }
    // User-initiated cancel — no error shown
    return;
  }

  // Normalize browser network errors
  if (
    err.message === "Failed to fetch" ||
    err.message === "NetworkError when attempting to fetch resource." ||
    err.message === "Load failed"
  ) {
    callbacks.onError(
      "Unable to connect to the server. Please check that the backend is running."
    );
    return;
  }

  callbacks.onError(err.message);
}

/**
 * Stream a POST-based SSE request with connection and idle timeouts.
 * Uses fetch + ReadableStream because EventSource only supports GET.
 */
function streamSSE(
  url: string,
  body: unknown,
  callbacks: StreamCallbacks,
  { connectionTimeoutMs = 30_000, idleTimeoutMs = 300_000 } = {},
): AbortController {
  const controller = new AbortController();
  let connectionTimer: ReturnType<typeof setTimeout> | undefined;
  let idleTimer: ReturnType<typeof setTimeout> | undefined;

  const clearTimers = () => {
    clearTimeout(connectionTimer);
    clearTimeout(idleTimer);
  };

  const headers: Record<string, string> = {
    ...getApiHeaders(),
    "Content-Type": "application/json",
  };

  // Abort if the initial connection takes too long
  connectionTimer = setTimeout(() => {
    controller.abort("connection_timeout");
  }, connectionTimeoutMs);

  fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (response) => {
      clearTimeout(connectionTimer);

      if (!response.ok) {
        const text = await response.text();
        callbacks.onError(`HTTP ${response.status}: ${text}`);
        return;
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let receivedComplete = false;

      // Rolling idle timeout — resets on every chunk
      const resetIdleTimer = () => {
        clearTimeout(idleTimer);
        idleTimer = setTimeout(() => {
          controller.abort("idle_timeout");
        }, idleTimeoutMs);
      };

      resetIdleTimer();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        resetIdleTimer();
        buffer += decoder.decode(value, { stream: true });
        const { events, remaining } = parseSSEEvents(buffer);
        buffer = remaining;

        for (const event of events) {
          try {
            const parsed = JSON.parse(event.data);

            if (event.type === "status") {
              callbacks.onStatus(parsed as StatusEvent);
            } else if (event.type === "complete") {
              receivedComplete = true;
              callbacks.onComplete(validateQueryResult(parsed) as QueryResult);
            } else if (event.type === "error") {
              callbacks.onError(parsed.detail || "Unknown error");
            }
          } catch {
            callbacks.onError(`Failed to parse event: ${event.data}`);
          }
        }
      }

      clearTimeout(idleTimer);

      // Flush remaining buffer after stream ends
      if (buffer.trim()) {
        const { events } = parseSSEEvents(buffer + "\n\n");
        for (const event of events) {
          try {
            const parsed = JSON.parse(event.data);
            if (event.type === "complete") {
              receivedComplete = true;
              callbacks.onComplete(validateQueryResult(parsed) as QueryResult);
            } else if (event.type === "error") {
              callbacks.onError(parsed.detail || "Unknown error");
            }
          } catch {
            // Ignore unparseable trailing data
          }
        }
      }

      // If stream ended without a complete event, signal error
      if (!receivedComplete) {
        callbacks.onError(
          "The server closed the connection before the query completed. This may indicate a server error or timeout."
        );
      }
    })
    .catch((err: Error) => {
      clearTimers();
      handleStreamError(err, controller, callbacks);
    });

  return controller;
}

/**
 * Stream a natural language query execution via SSE.
 * Returns an AbortController to cancel the request.
 */
export function streamQuery(
  request: QueryRequest,
  callbacks: StreamCallbacks
): AbortController {
  return streamSSE("/api/query/stream", request, callbacks);
}

/**
 * Stream a plan patch re-execution via SSE.
 * Returns an AbortController to cancel the request.
 */
export function streamPatch(
  request: PatchRequest,
  callbacks: StreamCallbacks
): AbortController {
  return streamSSE("/api/query/patch", request, callbacks);
}

/**
 * Execute raw SQL directly and stream results via SSE.
 * Used for approved SQL revisions from the chat agent.
 * Returns an AbortController to cancel the request.
 */
export function streamExecuteSQL(
  request: ExecuteSQLRequest,
  callbacks: StreamCallbacks
): AbortController {
  return streamSSE("/api/query/execute-sql", request, callbacks);
}

// ---------------------------------------------------------------------------
// Database registry
// ---------------------------------------------------------------------------

/**
 * Fetch the list of available demo databases.
 * Returns an empty array when the backend is in SQL Server mode.
 */
export async function fetchDatabases(): Promise<DemoDatabase[]> {
  const res = await fetch("/api/databases", { headers: getApiHeaders() });
  if (!res.ok) {
    throw new Error(`Server returned ${res.status}`);
  }
  return res.json();
}

/**
 * Fetch the introspected schema for a specific demo database.
 */
export async function fetchDatabaseSchema(dbId: string): Promise<SchemaTable[]> {
  const res = await fetch(`/api/databases/${dbId}/schema`, { headers: getApiHeaders() });
  if (!res.ok) throw new Error(`Failed to fetch schema: ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Chat reset
// ---------------------------------------------------------------------------

/**
 * Reset the server-side chat conversation memory for a session.
 */
export async function resetChat(sessionId: string): Promise<void> {
  await fetch("/api/query/chat/reset", {
    method: "POST",
    headers: { ...getApiHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
}

// ---------------------------------------------------------------------------
// Chat streaming (agentic — supports tool calls)
// ---------------------------------------------------------------------------

interface ChatStreamCallbacks {
  onToken: (event: ChatTokenEvent) => void;
  onComplete: (result: ChatCompleteEvent) => void;
  onError: (error: string) => void;
  onToolStart?: (event: ChatToolStartEvent) => void;
  onToolResult?: (result: QueryResult) => void;
  onToolError?: (event: ChatToolErrorEvent) => void;
  onStatus?: (event: StatusEvent) => void;
  onSuggestRevision?: (event: ChatSuggestRevisionEvent) => void;
}

/**
 * Stream a chat message about query results via SSE.
 * Supports tool_start and tool_result events from the agentic chat loop.
 * Returns an AbortController to cancel the request.
 */
export function streamChat(
  request: ChatRequest,
  callbacks: ChatStreamCallbacks
): AbortController {
  const controller = new AbortController();
  // Chat can involve tool execution, so use longer timeouts
  const connectionTimeoutMs = 45_000;
  const idleTimeoutMs = 300_000;
  let connectionTimer: ReturnType<typeof setTimeout> | undefined;
  let idleTimer: ReturnType<typeof setTimeout> | undefined;

  const clearTimers = () => {
    clearTimeout(connectionTimer);
    clearTimeout(idleTimer);
  };

  const headers: Record<string, string> = {
    ...getApiHeaders(),
    "Content-Type": "application/json",
  };

  connectionTimer = setTimeout(() => {
    controller.abort("connection_timeout");
  }, connectionTimeoutMs);

  fetch("/api/query/chat", {
    method: "POST",
    headers,
    body: JSON.stringify(request),
    signal: controller.signal,
  })
    .then(async (response) => {
      clearTimeout(connectionTimer);

      if (!response.ok) {
        const text = await response.text();
        callbacks.onError(`HTTP ${response.status}: ${text}`);
        return;
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let receivedComplete = false;

      const resetIdleTimer = () => {
        clearTimeout(idleTimer);
        idleTimer = setTimeout(() => {
          controller.abort("idle_timeout");
        }, idleTimeoutMs);
      };

      resetIdleTimer();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        resetIdleTimer();
        buffer += decoder.decode(value, { stream: true });
        const { events, remaining } = parseSSEEvents(buffer);
        buffer = remaining;

        for (const event of events) {
          try {
            const parsed = JSON.parse(event.data);

            if (event.type === "token") {
              callbacks.onToken(parsed as ChatTokenEvent);
            } else if (event.type === "complete") {
              receivedComplete = true;
              callbacks.onComplete(parsed as ChatCompleteEvent);
            } else if (event.type === "error") {
              callbacks.onError(parsed.detail || "Unknown error");
            } else if (event.type === "tool_start") {
              callbacks.onToolStart?.(parsed as ChatToolStartEvent);
            } else if (event.type === "tool_result") {
              callbacks.onToolResult?.(validateQueryResult(parsed) as QueryResult);
            } else if (event.type === "tool_error") {
              callbacks.onToolError?.(parsed as ChatToolErrorEvent);
            } else if (event.type === "suggest_revision") {
              callbacks.onSuggestRevision?.(parsed as ChatSuggestRevisionEvent);
            } else if (event.type === "status") {
              callbacks.onStatus?.(parsed as StatusEvent);
            }
          } catch {
            callbacks.onError(`Failed to parse event: ${event.data}`);
          }
        }
      }

      clearTimeout(idleTimer);

      // Flush remaining buffer after stream ends
      if (buffer.trim()) {
        const { events } = parseSSEEvents(buffer + "\n\n");
        for (const event of events) {
          try {
            const parsed = JSON.parse(event.data);
            if (event.type === "complete") {
              receivedComplete = true;
              callbacks.onComplete(parsed as ChatCompleteEvent);
            } else if (event.type === "error") {
              callbacks.onError(parsed.detail || "Unknown error");
            } else if (event.type === "token") {
              callbacks.onToken(parsed as ChatTokenEvent);
            } else if (event.type === "tool_result") {
              callbacks.onToolResult?.(validateQueryResult(parsed) as QueryResult);
            } else if (event.type === "suggest_revision") {
              callbacks.onSuggestRevision?.(parsed as ChatSuggestRevisionEvent);
            }
          } catch {
            // Ignore unparseable trailing data
          }
        }
      }

      // If stream ended without a complete event, signal error
      if (!receivedComplete) {
        callbacks.onError(
          "The server closed the connection before the query completed. This may indicate a server error or timeout."
        );
      }
    })
    .catch((err: Error) => {
      clearTimers();
      handleStreamError(err, controller, callbacks);
    });

  return controller;
}
