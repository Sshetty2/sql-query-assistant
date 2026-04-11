import { useState, useRef, useEffect } from "react";
import {
  Send,
  ChevronDown,
  ChevronRight,
  Sparkles,
  RotateCcw,
  Loader2,
  Database,
  Check,
  Plus,
  Trash2,
  Pencil,
  MessageSquare,
  AlertTriangle,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { ChatMessage, DataSummary } from "@/api/types";
import type { ChatStatus } from "@/hooks/useChat";
import type { Conversation } from "@/hooks/useConversations";

interface ChatPanelProps {
  threadId: string | null;
  queryId: string | null;
  sessionId: string;
  messages: ChatMessage[];
  streamingContent: string;
  status: ChatStatus;
  error: string | null;
  suggestedQuery: string | null;
  onSend: (threadId: string, queryId: string, message: string, sessionId?: string) => void;
  onNewQuery: (query: string) => void;
  onReset: () => void;
  onResultClick?: (resultId: string) => void;
  // Conversation props
  conversations: Conversation[];
  activeConversationId: string | null;
  onNewConversation: () => void;
  onSwitchConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
  onRenameConversation: (id: string, name: string) => void;
}

function ColumnStats({ summary }: { summary: DataSummary }) {
  return (
    <div className="mt-2 space-y-1.5">
      {Object.entries(summary.columns).map(([name, col]) => (
        <div key={name} className="text-xs">
          <div className="flex items-center gap-1.5">
            <Badge variant="outline" className="text-[10px] font-mono px-1 py-0">
              {col.type}
            </Badge>
            <span className="font-medium">{name}</span>
            <span className="text-muted-foreground">
              ({col.distinct_count} distinct
              {col.null_count > 0 && `, ${col.null_count} nulls`})
            </span>
          </div>
          {col.type === "numeric" && col.min != null && (
            <div className="mt-0.5 pl-2 text-muted-foreground">
              min={col.min}, max={col.max}, avg={col.avg}
            </div>
          )}
          {col.type === "text" && col.top_values && col.top_values.length > 0 && (
            <div className="mt-0.5 pl-2 text-muted-foreground truncate">
              Top: {col.top_values.slice(0, 3).map((tv) => `"${tv.value}"`).join(", ")}
            </div>
          )}
          {col.type === "datetime" && col.min && (
            <div className="mt-0.5 pl-2 text-muted-foreground">
              {col.min} to {col.max} ({col.range_days}d)
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function InlineDataSummary({
  summary,
  sql,
  resultId,
  onResultClick,
}: {
  summary: DataSummary;
  sql?: string;
  resultId?: string;
  onResultClick?: (resultId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const canClick = resultId && onResultClick;

  return (
    <div className="flex justify-start">
      <div
        className={`max-w-[85%] rounded-lg border border-violet-200 dark:border-violet-800 bg-violet-50 dark:bg-violet-950/30 px-3 py-2 text-sm ${
          canClick ? "cursor-pointer hover:bg-violet-100 dark:hover:bg-violet-950/50 transition-colors" : ""
        }`}
        onClick={() => canClick && onResultClick(resultId)}
      >
        <div className="flex items-center gap-2 text-violet-700 dark:text-violet-300">
          <Database className="size-3.5" />
          <button
            className="flex items-center gap-1 font-medium text-xs hover:underline"
            onClick={(e) => {
              e.stopPropagation();
              setExpanded(!expanded);
            }}
          >
            {expanded ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
            {summary.row_count} rows, {summary.column_count} columns
            {summary.total_records_available &&
              summary.total_records_available !== summary.row_count && (
                <span className="text-[10px] text-violet-500 dark:text-violet-400">
                  {" "}(of {summary.total_records_available} total)
                </span>
              )}
          </button>
        </div>

        {expanded && (
          <>
            <ColumnStats summary={summary} />
            {sql && (
              <div className="mt-2 rounded bg-violet-100 dark:bg-violet-900/40 px-2 py-1 text-[10px] font-mono text-violet-700 dark:text-violet-300 overflow-x-auto whitespace-pre-wrap">
                {sql}
              </div>
            )}
          </>
        )}

        {canClick && (
          <p className="mt-1 text-[10px] text-violet-500 dark:text-violet-400">
            Click to view these results
          </p>
        )}
      </div>
    </div>
  );
}

function ToolStartMessage({ content, isActive }: { content: string; isActive: boolean }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-lg bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 px-3 py-2 text-sm">
        <div className="flex items-center gap-2 text-blue-700 dark:text-blue-300">
          {isActive ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Check className="size-3.5" />
          )}
          <span className="font-medium text-xs">{isActive ? "Executing query" : "Query submitted"}</span>
        </div>
        <p className="mt-1 text-xs text-blue-600 dark:text-blue-400">{content}</p>
      </div>
    </div>
  );
}

function ToolResultMessage({
  content,
  resultId,
  dataSummary,
  sql,
  onResultClick,
}: {
  content: string;
  resultId?: string;
  dataSummary?: DataSummary;
  sql?: string;
  onResultClick?: (resultId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const canClick = resultId && onResultClick;
  return (
    <div className="flex justify-start">
      <div
        className={`max-w-[85%] rounded-lg bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 px-3 py-2 text-sm ${
          canClick ? "cursor-pointer hover:bg-green-100 dark:hover:bg-green-950/50 transition-colors" : ""
        }`}
        onClick={() => canClick && onResultClick(resultId)}
      >
        <div className="flex items-center gap-2 text-green-700 dark:text-green-300">
          <Check className="size-3.5" />
          <Database className="size-3.5" />
          {dataSummary ? (
            <button
              className="flex items-center gap-1 font-medium text-xs hover:underline"
              onClick={(e) => {
                e.stopPropagation();
                setExpanded(!expanded);
              }}
            >
              {expanded ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
              {content}
            </button>
          ) : (
            <span className="font-medium text-xs">{content}</span>
          )}
        </div>

        {expanded && dataSummary && (
          <>
            <ColumnStats summary={dataSummary} />
            {sql && (
              <div className="mt-2 rounded bg-green-100 dark:bg-green-900/40 px-2 py-1 text-[10px] font-mono text-green-700 dark:text-green-300 overflow-x-auto whitespace-pre-wrap">
                {sql}
              </div>
            )}
          </>
        )}

        {canClick && (
          <p className="mt-1 text-[10px] text-green-600 dark:text-green-400">
            Click to view these results
          </p>
        )}
        {resultId && !onResultClick && (
          <p className="mt-1 text-[10px] text-muted-foreground">
            Results no longer available
          </p>
        )}
      </div>
    </div>
  );
}

function ToolErrorMessage({
  content,
  failedQuery,
  onRetry,
  onReset,
}: {
  content: string;
  failedQuery?: string;
  onRetry?: (query: string) => void;
  onReset: () => void;
}) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 px-3 py-2 text-sm">
        <div className="flex items-center gap-2 text-red-700 dark:text-red-300">
          <AlertTriangle className="size-3.5" />
          <span className="font-medium text-xs">Query failed</span>
        </div>
        <p className="mt-1 text-xs text-red-600 dark:text-red-400">{content}</p>
        <div className="mt-2 flex gap-2">
          {failedQuery && onRetry && (
            <Button
              size="sm"
              variant="outline"
              className="h-6 text-xs px-2"
              onClick={() => onRetry(failedQuery)}
            >
              <RefreshCw className="size-3 mr-1" />
              Retry as new query
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="h-6 text-xs px-2"
            onClick={onReset}
          >
            <RotateCcw className="size-3 mr-1" />
            New conversation
          </Button>
        </div>
      </div>
    </div>
  );
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function ChatPanel({
  threadId,
  queryId,
  sessionId,
  messages,
  streamingContent,
  status,
  error,
  suggestedQuery,
  onSend,
  onNewQuery,
  onReset,
  onResultClick,
  conversations,
  activeConversationId,
  onNewConversation,
  onSwitchConversation,
  onDeleteConversation,
  onRenameConversation,
}: ChatPanelProps) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const canSend = input.trim() && status !== "streaming" && status !== "tool_running";

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || status === "streaming" || status === "tool_running") return;

    if (threadId && queryId) {
      // Follow-up: use chat agent for context-aware conversation
      onSend(threadId, queryId, trimmed, sessionId);
    } else {
      // No query yet: execute as a new query via the main pipeline
      onNewQuery(trimmed);
    }
    setInput("");
  };

  const isBusy = status === "streaming" || status === "tool_running";

  const handleStartRename = (e: React.MouseEvent, id: string, currentName: string) => {
    e.preventDefault();
    e.stopPropagation();
    setRenamingId(id);
    setRenameValue(currentName);
  };

  const handleConfirmRename = () => {
    if (renamingId && renameValue.trim()) {
      onRenameConversation(renamingId, renameValue.trim());
    }
    setRenamingId(null);
    setRenameValue("");
  };

  return (
    <div className="flex h-full flex-col border-l border-border bg-background">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2 min-w-0">
          <Sparkles className="size-4 text-primary flex-shrink-0" />
          <h2 className="text-sm font-semibold truncate">Data Assistant</h2>
        </div>

        <div className="flex items-center gap-1">
          {/* Conversation dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-xs" title="Conversations">
                <MessageSquare className="size-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              <DropdownMenuItem onClick={onNewConversation}>
                <Plus className="size-3.5 mr-2" />
                New conversation
              </DropdownMenuItem>
              {conversations.length > 0 && <DropdownMenuSeparator />}
              {conversations.map((conv) => (
                <DropdownMenuItem
                  key={conv.id}
                  className="flex items-center justify-between gap-2 group"
                  onClick={() => onSwitchConversation(conv.id)}
                >
                  <div className="flex-1 min-w-0">
                    {renamingId === conv.id ? (
                      <input
                        className="w-full text-xs bg-transparent border-b border-primary outline-none"
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleConfirmRename();
                          if (e.key === "Escape") setRenamingId(null);
                        }}
                        onBlur={handleConfirmRename}
                        onClick={(e) => e.stopPropagation()}
                        autoFocus
                      />
                    ) : (
                      <>
                        <div className="flex items-center gap-1.5">
                          {conv.id === activeConversationId && (
                            <div className="size-1.5 rounded-full bg-primary flex-shrink-0" />
                          )}
                          <span className="text-xs truncate">{conv.name}</span>
                        </div>
                        <span className="text-[10px] text-muted-foreground">
                          {timeAgo(conv.lastMessageAt)}
                        </span>
                      </>
                    )}
                  </div>
                  <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      className="p-0.5 hover:text-primary"
                      onClick={(e) => handleStartRename(e, conv.id, conv.name)}
                      title="Rename"
                    >
                      <Pencil className="size-3" />
                    </button>
                    <button
                      className="p-0.5 hover:text-destructive"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        onDeleteConversation(conv.id);
                      }}
                      title="Delete"
                    >
                      <Trash2 className="size-3" />
                    </button>
                  </div>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          <Button
            variant="ghost"
            size="icon-xs"
            onClick={onReset}
            title="New conversation"
          >
            <RotateCcw className="size-3.5" />
          </Button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && !streamingContent && (
          <p className="text-sm text-muted-foreground text-center mt-8">
            Ask a question about your data in plain English
          </p>
        )}

        {messages.map((msg, i) => {
          if (msg.role === "data_summary" && msg.dataSummary) {
            return (
              <InlineDataSummary
                key={i}
                summary={msg.dataSummary}
                sql={msg.query}
                resultId={msg.resultId}
                onResultClick={onResultClick}
              />
            );
          }
          if (msg.role === "tool_start") {
            // Check if a subsequent message indicates the tool has completed
            const hasFollowUp = messages.slice(i + 1).some(
              (m) => m.role === "tool_result" || m.role === "tool_error"
            );
            return <ToolStartMessage key={i} content={msg.content} isActive={!hasFollowUp} />;
          }
          if (msg.role === "tool_result") {
            return (
              <ToolResultMessage
                key={i}
                content={msg.content}
                resultId={msg.resultId}
                dataSummary={msg.dataSummary}
                sql={msg.query}
                onResultClick={onResultClick}
              />
            );
          }
          if (msg.role === "tool_error") {
            return (
              <ToolErrorMessage
                key={i}
                content={msg.content}
                failedQuery={msg.failedQuery}
                onRetry={onNewQuery}
                onReset={onReset}
              />
            );
          }
          return (
            <div
              key={i}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-foreground"
                }`}
              >
                {msg.content}
              </div>
            </div>
          );
        })}

        {/* Streaming content */}
        {streamingContent && (
          <div className="flex justify-start">
            <div className="max-w-[85%] rounded-lg bg-muted px-3 py-2 text-sm text-foreground whitespace-pre-wrap">
              {streamingContent}
              <span className="inline-block w-1.5 h-4 bg-foreground/50 animate-pulse ml-0.5 align-text-bottom" />
            </div>
          </div>
        )}

        {/* Tool running indicator (when no streaming content yet) */}
        {status === "tool_running" && !streamingContent && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" />
              <span>Running query...</span>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <Card className="border-destructive">
            <CardContent className="py-2 px-3">
              <p className="text-xs text-destructive">{error}</p>
            </CardContent>
          </Card>
        )}

        {/* Suggested query */}
        {suggestedQuery && (
          <Card className="border-primary/30">
            <CardContent className="py-2 px-3 space-y-2">
              <p className="text-xs text-muted-foreground">
                This can't be answered from the current results. Try:
              </p>
              <p className="text-sm font-medium">{suggestedQuery}</p>
              <Button
                size="sm"
                variant="default"
                onClick={() => onNewQuery(suggestedQuery)}
              >
                Run this query
              </Button>
            </CardContent>
          </Card>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form
        onSubmit={handleSubmit}
        className="border-t border-border px-4 py-3 flex gap-2"
      >
        <Input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={threadId ? "Ask about your results..." : "Ask a question..."}
          disabled={isBusy}
          className="flex-1"
        />
        <Button
          type="submit"
          size="icon"
          disabled={!canSend}
        >
          <Send className="size-4" />
        </Button>
      </form>
    </div>
  );
}
