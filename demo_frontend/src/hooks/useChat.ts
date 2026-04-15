import { useState, useRef, useCallback } from "react";
import { streamChat, resetChat } from "@/api/client";
import type { ChatMessage, ChatCompleteEvent, ChatToolErrorEvent, DataSummary, QueryResult, StatusEvent } from "@/api/types";

export type ChatStatus = "idle" | "streaming" | "tool_running" | "complete" | "error";

export interface PendingRevision {
  sql: string;
  explanation: string;
}

interface UseChatOptions {
  /** Called when the agent executes a tool and gets new query results. */
  onToolResult?: (result: QueryResult) => void;
  /** Called to store a result and get back a resultId. */
  storeResult?: (result: QueryResult) => string;
  /** Called when the agent starts executing a tool. */
  onToolStart?: () => void;
  /** Called when a workflow status event arrives during tool execution. */
  onStatus?: (event: StatusEvent) => void;
}

export function useChat(options: UseChatOptions = {}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingContent, setStreamingContent] = useState("");
  const [status, setStatus] = useState<ChatStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [suggestedQuery, setSuggestedQuery] = useState<string | null>(null);
  const [toolCallsRemaining, setToolCallsRemaining] = useState<number | null>(null);
  const [pendingRevision, setPendingRevision] = useState<PendingRevision | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const send = useCallback(
    (threadId: string, queryId: string, message: string, sessionId?: string, dbId?: string) => {
      // Cancel any in-flight request
      controllerRef.current?.abort();

      // Add user message immediately for display
      const userMsg: ChatMessage = { role: "user", content: message };
      setMessages((prev) => [...prev, userMsg]);
      setStreamingContent("");
      setStatus("streaming");
      setError(null);
      setSuggestedQuery(null);
      setPendingRevision(null);

      controllerRef.current = streamChat(
        {
          thread_id: threadId,
          query_id: queryId,
          message,
          session_id: sessionId,
          ...(dbId ? { db_id: dbId } : {}),
        },
        {
          onToken: (event) => {
            setStreamingContent((prev) => prev + event.content);
          },
          onComplete: (result: ChatCompleteEvent) => {
            const assistantMsg: ChatMessage = {
              role: "assistant",
              content: result.content,
            };
            setMessages((prev) => [...prev, assistantMsg]);
            setStreamingContent("");
            setStatus("complete");
            setToolCallsRemaining(result.tool_calls_remaining ?? null);
            if (result.suggest_new_query && result.suggested_query) {
              setSuggestedQuery(result.suggested_query);
            }
          },
          onToolStart: (event) => {
            setStatus("tool_running");
            setStreamingContent("");
            const toolMsg: ChatMessage = {
              role: "tool_start",
              content: `Running query: ${event.input.query}`,
            };
            setMessages((prev) => [...prev, toolMsg]);
            options.onToolStart?.();
          },
          onToolResult: (result: QueryResult) => {
            setStatus("streaming"); // Back to streaming — LLM will summarize
            // Store result and create a tool_result message
            const resultId = options.storeResult?.(result);
            const rowCount = result.data_summary?.row_count ?? result.result?.length ?? 0;
            const colCount = result.data_summary?.column_count ?? 0;
            const toolResultMsg: ChatMessage = {
              role: "tool_result",
              content: `Query complete: ${rowCount} rows, ${colCount} columns`,
              resultId,
              dataSummary: result.data_summary ?? undefined,
              query: result.query ?? undefined,
            };
            setMessages((prev) => [...prev, toolResultMsg]);
            // Notify parent to update main panel
            options.onToolResult?.(result);
          },
          onToolError: (event: ChatToolErrorEvent) => {
            // Tool failed — add an error message to chat but don't stop
            // the stream; the LLM will continue with an error explanation.
            const toolErrMsg: ChatMessage = {
              role: "tool_error",
              content: `Query failed: ${event.detail}`,
              failedQuery: event.query,
            };
            setMessages((prev) => [...prev, toolErrMsg]);
            setStatus("streaming"); // LLM will explain the error next
          },
          onSuggestRevision: (event) => {
            const revisionMsg: ChatMessage = {
              role: "suggest_revision",
              content: event.explanation,
              revisedSql: event.revised_sql,
            };
            setMessages((prev) => [...prev, revisionMsg]);
            setPendingRevision({
              sql: event.revised_sql,
              explanation: event.explanation,
            });
          },
          onStatus: (event) => {
            options.onStatus?.(event);
          },
          onError: (err) => {
            setError(err);
            setStatus("error");
            setStreamingContent("");
          },
        }
      );
    },
    [options]
  );

  /** Append a user message directly (e.g., from the main query input). */
  const appendUserMessage = useCallback((content: string) => {
    const msg: ChatMessage = { role: "user", content };
    setMessages((prev) => [...prev, msg]);
  }, []);

  /** Append an assistant message directly (e.g., auto-generated narrative). */
  const appendAssistantMessage = useCallback((content: string) => {
    const msg: ChatMessage = { role: "assistant", content };
    setMessages((prev) => [...prev, msg]);
  }, []);

  /** Append an arbitrary message to the chat. */
  const appendMessage = useCallback((msg: ChatMessage) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  /** Append an inline data summary message (e.g., when initial query completes). */
  const appendDataSummary = useCallback(
    (summary: DataSummary, resultId: string, sql: string) => {
      const msg: ChatMessage = {
        role: "data_summary",
        content: `${summary.row_count} rows, ${summary.column_count} columns`,
        dataSummary: summary,
        resultId,
        query: sql,
      };
      setMessages((prev) => [...prev, msg]);
    },
    []
  );

  /** Surface a revision suggestion externally (e.g., from narrative generation). */
  const suggestRevision = useCallback((sql: string, explanation: string) => {
    const msg: ChatMessage = { role: "suggest_revision", content: explanation, revisedSql: sql };
    setMessages((prev) => [...prev, msg]);
    setPendingRevision({ sql, explanation });
  }, []);

  /** Accept the pending revision and return it. Clears pending state. */
  const acceptRevision = useCallback((): PendingRevision | null => {
    const revision = pendingRevision;
    setPendingRevision(null);
    return revision;
  }, [pendingRevision]);

  /** Dismiss the pending revision without executing. */
  const dismissRevision = useCallback(() => {
    setPendingRevision(null);
  }, []);

  /** Clear local messages only (no server call). */
  const reset = useCallback(() => {
    controllerRef.current?.abort();
    setMessages([]);
    setStreamingContent("");
    setStatus("idle");
    setError(null);
    setSuggestedQuery(null);
    setToolCallsRemaining(null);
    setPendingRevision(null);
  }, []);

  /** Clear both local messages and server-side conversation memory. */
  const resetConversation = useCallback((sessionId: string) => {
    controllerRef.current?.abort();
    setMessages([]);
    setStreamingContent("");
    setStatus("idle");
    setError(null);
    setSuggestedQuery(null);
    setToolCallsRemaining(null);
    setPendingRevision(null);
    resetChat(sessionId).catch(() => {
      // Best-effort: server memory will expire naturally
    });
  }, []);

  /** Restore messages from a saved conversation. */
  const restoreMessages = useCallback((savedMessages: ChatMessage[]) => {
    setMessages(savedMessages);
    setStreamingContent("");
    setStatus("idle");
    setError(null);
    setSuggestedQuery(null);
    setPendingRevision(null);
  }, []);

  return {
    messages,
    streamingContent,
    status,
    error,
    suggestedQuery,
    toolCallsRemaining,
    pendingRevision,
    send,
    appendUserMessage,
    appendAssistantMessage,
    appendMessage,
    appendDataSummary,
    suggestRevision,
    acceptRevision,
    dismissRevision,
    reset,
    resetConversation,
    restoreMessages,
  };
}
