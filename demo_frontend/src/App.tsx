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
import { AlertCircle } from "lucide-react";
import { streamExecuteSQL } from "@/api/client";
import type { ChatMessage, QueryResult, StatusEvent } from "@/api/types";

function App() {
  const resultStore = useResultStore();
  const convs = useConversations(resultStore.removeMany);
  const { status, steps, result, error, execute, updateResult, setSteps, reset: resetQuery, cancel } = useQuery();
  const db = useDatabase();

  // Track whether steps need clearing for the next tool query
  const needsStepsClearRef = useRef(false);

  // Memoize chat options to keep a stable reference
  const chatOptions = useMemo(
    () => ({
      onToolStart: () => {
        // Clear stale result and mark steps for clearing
        needsStepsClearRef.current = true;
        resetQuery();
      },
      onToolResult: (toolResult: QueryResult) => {
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
    [updateResult, resetQuery, resultStore, convs.activeId, convs.addResultId, setSteps]
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

  // Auto-start a new conversation when the user switches databases
  const prevDbIdRef = useRef(db.activeDbId);
  useEffect(() => {
    // Skip the initial mount — only react to actual user-driven switches
    if (prevDbIdRef.current === db.activeDbId) return;
    prevDbIdRef.current = db.activeDbId;
    if (!db.activeDbId) return;
    // Reset chat and left panel, start a fresh conversation for the new database
    chat.reset();
    resetQuery();
    convs.create();
  }, [db.activeDbId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Get active session ID (from active conversation, or create one)
  const getSessionId = useCallback(() => {
    if (convs.activeId) return convs.activeId;
    // Auto-create a conversation if none active
    const conv = convs.create();
    return conv.id;
  }, [convs]);

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
      execute(
        {
          prompt: query,
          chat_session_id: sessionId,
          ...(db.activeDbId ? { db_id: db.activeDbId } : {}),
        },
        (queryResult) => {
          // Store result for click-to-view
          const resultId = resultStore.store(queryResult);
          if (convs.activeId) {
            convs.addResultId(convs.activeId, resultId);
          }
          // Add inline data summary + narrative to chat
          if (queryResult.data_summary) {
            chat.appendDataSummary(queryResult.data_summary, resultId, queryResult.query);
          }
          if (queryResult.query_narrative) {
            chat.appendAssistantMessage(queryResult.query_narrative);
          }
        }
      );
      // Auto-name the conversation from the first query.
      // Use sessionId (not convs.activeId) because React state may not have
      // flushed yet when getSessionId() just created a new conversation.
      convs.autoName(sessionId, query);
    },
    [execute, getSessionId, convs, chat, db.activeDbId, resultStore]
  );

  const handleResetConversation = useCallback(() => {
    const sessionId = convs.activeId ?? "";
    chat.resetConversation(sessionId);
    resetQuery();
    convs.create();
  }, [chat, convs, resetQuery]);

  const handleNewConversation = useCallback(() => {
    chat.reset();
    resetQuery();
    convs.create();
  }, [chat, convs, resetQuery]);

  const handleSwitchConversation = useCallback(
    (id: string) => {
      convs.switchTo(id);
      resetQuery();
      const conv = convs.conversations.find((c) => c.id === id);
      if (conv) {
        chat.restoreMessages(conv.messages);
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
    [convs, chat, resultStore, updateResult, resetQuery]
  );

  const handleDeleteConversation = useCallback(
    (id: string) => {
      convs.remove(id);
      if (id === convs.activeId) {
        chat.reset();
        resetQuery();
      }
    },
    [convs, chat, resetQuery]
  );

  const handleClearAllConversations = useCallback(() => {
    convs.clearAll();
    chat.reset();
    resetQuery();
  }, [convs, chat, resetQuery]);

  const handleResultClick = useCallback(
    (resultId: string) => {
      const storedResult = resultStore.get(resultId);
      if (storedResult) {
        updateResult(storedResult);
      }
    },
    [resultStore, updateResult]
  );

  const handleExecuteRevision = useCallback(() => {
    const revision = chat.acceptRevision();
    if (!revision || !result?.thread_id || !result?.query_id) return;

    const { thread_id, query_id } = result;

    // Clear old result while revision executes
    resetQuery();

    // Show progress
    needsStepsClearRef.current = false;
    setSteps([{
      type: "status" as const,
      node_name: "execute_sql",
      node_status: "running" as const,
      node_message: "Executing revised SQL",
    }]);

    streamExecuteSQL(
      {
        sql: revision.sql,
        thread_id,
        query_id,
        ...(db.activeDbId ? { db_id: db.activeDbId } : {}),
      },
      {
        onStatus: (event) => {
          setSteps((prev) => [...prev, event]);
        },
        onComplete: (queryResult) => {
          updateResult(queryResult);
          // Store result for click-to-view
          const rid = resultStore.store(queryResult);
          if (convs.activeId) {
            convs.addResultId(convs.activeId, rid);
          }
          // Add confirmation message in chat
          const rowCount = queryResult.data_summary?.row_count ?? queryResult.result?.length ?? 0;
          const colCount = queryResult.data_summary?.column_count ?? 0;
          const toolResultMsg: ChatMessage = {
            role: "tool_result",
            content: `Revision executed: ${rowCount} rows, ${colCount} columns`,
            resultId: rid,
            dataSummary: queryResult.data_summary ?? undefined,
            query: queryResult.query ?? undefined,
          };
          chat.appendMessage(toolResultMsg);

          // Trigger agent response about the updated results
          if (queryResult.thread_id && queryResult.query_id) {
            chat.send(
              queryResult.thread_id,
              queryResult.query_id,
              `Revised query executed: ${rowCount} rows, ${colCount} columns. Briefly summarize what changed.`,
              convs.activeId ?? undefined,
              db.activeDbId ?? undefined,
            );
          }
        },
        onError: (err) => {
          const errorMsg: ChatMessage = {
            role: "tool_error",
            content: `Revision execution failed: ${err}`,
            failedQuery: revision.sql,
          };
          chat.appendMessage(errorMsg);
        },
      }
    );
  }, [chat, result, db.activeDbId, resultStore, convs, updateResult, resetQuery, setSteps]);

  const handleDismissRevision = useCallback(() => {
    chat.dismissRevision();
  }, [chat]);

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
            {db.connectionError && (
              <Card className="border-destructive">
                <CardContent className="py-4 flex items-center gap-3">
                  <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0" />
                  <p className="text-sm text-destructive">{db.connectionError}</p>
                </CardContent>
              </Card>
            )}

            {db.databases.length > 0 && db.schema.length > 0 && (
              <SchemaERD
                schema={db.schema}
                dbName={db.databases.find((d) => d.id === db.activeDbId)?.name ?? ""}
              />
            )}

            <QueryInput
              onSubmit={(prompt) => handleNewQuery(prompt)}
              disabled={status === "streaming"}
              onCancel={cancel}
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
          dbId={db.activeDbId}
          messages={chat.messages}
          streamingContent={chat.streamingContent}
          status={chat.status}
          error={chat.error}
          suggestedQuery={chat.suggestedQuery}
          pendingRevision={chat.pendingRevision}
          onSend={chat.send}
          onNewQuery={handleNewQuery}
          onReset={handleResetConversation}
          onResultClick={handleResultClick}
          onExecuteRevision={handleExecuteRevision}
          onDismissRevision={handleDismissRevision}
          conversations={convs.conversations}
          activeConversationId={convs.activeId}
          onNewConversation={handleNewConversation}
          onSwitchConversation={handleSwitchConversation}
          onDeleteConversation={handleDeleteConversation}
          onRenameConversation={convs.rename}
          onClearAllConversations={handleClearAllConversations}
        />
      </div>
    </div>
  );
}

export default App;
