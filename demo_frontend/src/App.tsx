import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useQuery } from "@/hooks/useQuery";
import { useChat } from "@/hooks/useChat";
import { useResultStore } from "@/hooks/useResultStore";
import { useConversations } from "@/hooks/useConversations";
import { useDatabase } from "@/hooks/useDatabase";
import { QueryInput } from "@/components/QueryInput";
import { WorkflowProgress } from "@/components/WorkflowProgress";
import { SqlViewer } from "@/components/SqlViewer";
import { ResultsTable } from "@/components/ResultsTable";
import { ChatPanel } from "@/components/ChatPanel";
import { DatabaseSelector } from "@/components/DatabaseSelector";
import { SchemaERD } from "@/components/SchemaERD";
import { Card, CardContent } from "@/components/ui/card";
import type { QueryResult, StatusEvent } from "@/api/types";

function App() {
  const resultStore = useResultStore();
  const convs = useConversations(resultStore.removeMany);
  const { status, steps, result, error, execute, updateResult, setSteps } = useQuery();
  const db = useDatabase();
  const lastNarrativeRef = useRef<string | null>(null);

  // Track whether a result was set by a tool call (vs main query pipeline)
  const isToolResultRef = useRef(false);
  // Track whether steps need clearing for the next tool query
  const needsStepsClearRef = useRef(false);

  // Memoize chat options to keep a stable reference
  const chatOptions = useMemo(
    () => ({
      onToolStart: () => {
        // Mark that steps should be cleared on the first status event
        needsStepsClearRef.current = true;
      },
      onToolResult: (toolResult: QueryResult) => {
        // Flag so the result useEffect skips (tool results are handled by useChat)
        isToolResultRef.current = true;
        // Update main panel with new results
        updateResult(toolResult);
      },
      storeResult: (toolResult: QueryResult): string => {
        const id = resultStore.store(toolResult);
        // Track result in active conversation
        if (convs.activeId) {
          convs.addResultId(convs.activeId, id);
        }
        return id;
      },
      onStatus: (event: StatusEvent) => {
        // Clear old steps on the first status event of a new tool query
        if (needsStepsClearRef.current) {
          needsStepsClearRef.current = false;
          setSteps([event]);
        } else {
          setSteps((prev) => [...prev, event]);
        }
      },
    }),
    [updateResult, resultStore, convs.activeId, convs.addResultId, setSteps]
  );

  const chat = useChat(chatOptions);

  // --- Resizable panel ---
  const [chatWidthPct, setChatWidthPct] = useState(20);
  const dragging = useRef(false);

  const onMouseDown = useCallback(() => {
    dragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      const pct = ((window.innerWidth - e.clientX) / window.innerWidth) * 100;
      setChatWidthPct(Math.min(50, Math.max(15, pct)));
    };
    const onMouseUp = () => {
      if (dragging.current) {
        dragging.current = false;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      }
    };
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, []);

  // Get active session ID (from active conversation, or create one)
  const getSessionId = useCallback(() => {
    if (convs.activeId) return convs.activeId;
    // Auto-create a conversation if none active
    const conv = convs.create();
    return conv.id;
  }, [convs]);

  // When a new query result arrives from the MAIN pipeline, add inline data summary + narrative to chat.
  // Tool results are handled separately by the useChat callbacks (onToolResult/storeResult).
  const lastResultRef = useRef<string | null>(null);
  useEffect(() => {
    if (!result) return;
    // Skip tool results — already handled by useChat.onToolResult
    if (isToolResultRef.current) {
      isToolResultRef.current = false;
      return;
    }
    // Deduplicate: use query + row count as identity
    const resultIdentity = `${result.query}::${result.data_summary?.row_count}`;
    if (resultIdentity === lastResultRef.current) return;
    lastResultRef.current = resultIdentity;

    // Store result for click-to-view
    const resultId = resultStore.store(result);
    if (convs.activeId) {
      convs.addResultId(convs.activeId, resultId);
    }

    // Add inline data summary message
    if (result.data_summary) {
      chat.appendDataSummary(result.data_summary, resultId, result.query);
    }

    // Add narrative as assistant message
    const narrative = result.query_narrative;
    if (narrative) {
      lastNarrativeRef.current = narrative;
      chat.appendAssistantMessage(narrative);
    }
  }, [result]); // eslint-disable-line react-hooks/exhaustive-deps

  // Persist messages to active conversation whenever they change
  useEffect(() => {
    if (convs.activeId && chat.messages.length > 0) {
      convs.updateMessages(convs.activeId, chat.messages);
    }
  }, [chat.messages]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleNewQuery = useCallback(
    (query: string) => {
      const sessionId = getSessionId();
      // Show user prompt in the chat timeline
      chat.appendUserMessage(query);
      execute({
        prompt: query,
        chat_session_id: sessionId,
        ...(db.activeDbId ? { db_id: db.activeDbId } : {}),
      });
      // Auto-name the conversation from the first query.
      // Use sessionId (not convs.activeId) because React state may not have
      // flushed yet when getSessionId() just created a new conversation.
      convs.autoName(sessionId, query);
    },
    [execute, getSessionId, convs, chat]
  );

  const handleResetConversation = useCallback(() => {
    const sessionId = convs.activeId ?? "";
    chat.resetConversation(sessionId);
    lastNarrativeRef.current = null;
    lastResultRef.current = null;
    // Create a fresh conversation
    convs.create();
  }, [chat, convs]);

  const handleNewConversation = useCallback(() => {
    chat.reset();
    lastNarrativeRef.current = null;
    lastResultRef.current = null;
    convs.create();
  }, [chat, convs]);

  const handleSwitchConversation = useCallback(
    (id: string) => {
      convs.switchTo(id);
      const conv = convs.conversations.find((c) => c.id === id);
      if (conv) {
        chat.restoreMessages(conv.messages);
        lastNarrativeRef.current = null;
        lastResultRef.current = null;
        // Restore the latest result from this conversation if available
        if (conv.resultIds.length > 0) {
          const latestId = conv.resultIds[conv.resultIds.length - 1];
          const storedResult = resultStore.get(latestId);
          if (storedResult) {
            updateResult(storedResult);
          }
        }
      }
    },
    [convs, chat, resultStore, updateResult]
  );

  const handleDeleteConversation = useCallback(
    (id: string) => {
      convs.remove(id);
      if (id === convs.activeId) {
        chat.reset();
        lastNarrativeRef.current = null;
        lastResultRef.current = null;
      }
    },
    [convs, chat]
  );

  const handleResultClick = useCallback(
    (resultId: string) => {
      const storedResult = resultStore.get(resultId);
      if (storedResult) {
        updateResult(storedResult);
      }
    },
    [resultStore, updateResult]
  );

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Main content */}
      <div className="flex-1 min-w-0 overflow-y-auto">
        <div className="mx-auto max-w-7xl px-2 py-8">
          <header className="mb-6">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
                  SQL Query Assistant
                </h1>
                <p className="mt-1 text-sm text-muted-foreground max-w-2xl">
                  An LLM-powered workflow for complex multi-table queries — joins, aggregations, and
                  filters across large schemas. Designed to be embedded as a RAG tool for conversational agents.
                </p>
              </div>
              {db.databases.length > 0 && (
                <DatabaseSelector
                  databases={db.databases}
                  activeDbId={db.activeDbId}
                  onSelect={db.setActiveDbId}
                />
              )}
            </div>
          </header>

          <div className="space-y-6">
            {db.databases.length > 0 && db.schema.length > 0 && (
              <SchemaERD
                schema={db.schema}
                dbName={db.databases.find((d) => d.id === db.activeDbId)?.name ?? ""}
              />
            )}

            <QueryInput
              onSubmit={(prompt) => handleNewQuery(prompt)}
              disabled={status === "streaming"}
              activeDbId={db.activeDbId}
            />

            {steps.length > 0 && (
              <WorkflowProgress steps={steps} isStreaming={status === "streaming" || chat.status === "tool_running"} />
            )}

            {error && (
              <Card className="border-destructive">
                <CardContent className="py-4">
                  <p className="text-sm text-destructive">{error}</p>
                </CardContent>
              </Card>
            )}

            {result && (
              <div className="space-y-4">
                <SqlViewer sql={result.query} />
                <ResultsTable
                  data={result.result}
                  totalRecords={result.total_records_available}
                />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Resize handle */}
      <div
        onMouseDown={onMouseDown}
        className="w-1 cursor-col-resize bg-border hover:bg-primary/40 active:bg-primary/60 transition-colors flex-shrink-0"
      />

      {/* Chat panel — always visible */}
      <div
        className="flex-shrink-0 overflow-hidden"
        style={{ width: `${chatWidthPct}%` }}
      >
        <ChatPanel
          threadId={result?.thread_id ?? null}
          queryId={result?.query_id ?? null}
          sessionId={convs.activeId ?? ""}
          messages={chat.messages}
          streamingContent={chat.streamingContent}
          status={chat.status}
          error={chat.error}
          suggestedQuery={chat.suggestedQuery}
          onSend={chat.send}
          onNewQuery={handleNewQuery}
          onReset={handleResetConversation}
          onResultClick={handleResultClick}
          conversations={convs.conversations}
          activeConversationId={convs.activeId}
          onNewConversation={handleNewConversation}
          onSwitchConversation={handleSwitchConversation}
          onDeleteConversation={handleDeleteConversation}
          onRenameConversation={convs.rename}
        />
      </div>
    </div>
  );
}

export default App;
