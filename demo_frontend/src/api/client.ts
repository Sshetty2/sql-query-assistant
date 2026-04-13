import type {
  QueryRequest,
  PatchRequest,
  StatusEvent,
  QueryResult,
  ChatRequest,
  ChatTokenEvent,
  ChatToolStartEvent,
  ChatToolErrorEvent,
  ChatCompleteEvent,
  DemoDatabase,
  SchemaTable,
} from "./types";

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
 * Stream a POST-based SSE request.
 * Uses fetch + ReadableStream because EventSource only supports GET.
 */
function streamSSE(
  url: string,
  body: unknown,
  callbacks: StreamCallbacks
): AbortController {
  const controller = new AbortController();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const csrfToken = getCsrfToken();
  if (csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }

  fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const text = await response.text();
        callbacks.onError(`HTTP ${response.status}: ${text}`);
        return;
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let receivedComplete = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

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
              callbacks.onComplete(parsed as QueryResult);
            } else if (event.type === "error") {
              callbacks.onError(parsed.detail || "Unknown error");
            }
          } catch {
            callbacks.onError(`Failed to parse event: ${event.data}`);
          }
        }
      }

      // Flush remaining buffer after stream ends
      if (buffer.trim()) {
        const { events } = parseSSEEvents(buffer + "\n\n");
        for (const event of events) {
          try {
            const parsed = JSON.parse(event.data);
            if (event.type === "complete") {
              receivedComplete = true;
              callbacks.onComplete(parsed as QueryResult);
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
        callbacks.onError("Stream ended without completing");
      }
    })
    .catch((err: Error) => {
      if (err.name !== "AbortError") {
        callbacks.onError(err.message);
      }
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

// ---------------------------------------------------------------------------
// Database registry
// ---------------------------------------------------------------------------

/**
 * Fetch the list of available demo databases.
 * Returns an empty array when the backend is in SQL Server mode.
 */
export async function fetchDatabases(): Promise<DemoDatabase[]> {
  const headers: Record<string, string> = {};
  const csrfToken = getCsrfToken();
  if (csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }

  const res = await fetch("/api/databases", { headers });
  if (!res.ok) return [];
  return res.json();
}

/**
 * Fetch the introspected schema for a specific demo database.
 */
export async function fetchDatabaseSchema(dbId: string): Promise<SchemaTable[]> {
  const headers: Record<string, string> = {};
  const csrfToken = getCsrfToken();
  if (csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }

  const res = await fetch(`/api/databases/${dbId}/schema`, { headers });
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
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const csrfToken = getCsrfToken();
  if (csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }

  await fetch("/api/query/chat/reset", {
    method: "POST",
    headers,
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

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const csrfToken = getCsrfToken();
  if (csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }

  fetch("/api/query/chat", {
    method: "POST",
    headers,
    body: JSON.stringify(request),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const text = await response.text();
        callbacks.onError(`HTTP ${response.status}: ${text}`);
        return;
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let receivedComplete = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

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
              callbacks.onToolResult?.(parsed as QueryResult);
            } else if (event.type === "tool_error") {
              callbacks.onToolError?.(parsed as ChatToolErrorEvent);
            } else if (event.type === "status") {
              callbacks.onStatus?.(parsed as StatusEvent);
            }
          } catch {
            callbacks.onError(`Failed to parse event: ${event.data}`);
          }
        }
      }

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
              callbacks.onToolResult?.(parsed as QueryResult);
            }
          } catch {
            // Ignore unparseable trailing data
          }
        }
      }

      // If stream ended without a complete event, signal error
      if (!receivedComplete) {
        callbacks.onError("Stream ended without completing");
      }
    })
    .catch((err: Error) => {
      if (err.name !== "AbortError") {
        callbacks.onError(err.message);
      }
    });

  return controller;
}
