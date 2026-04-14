import { useState, useCallback, useEffect, useRef } from "react";
import { resetChat } from "@/api/client";
import type { ChatMessage } from "@/api/types";

const STORAGE_KEY = "sql-assistant-conversations";

export interface Conversation {
  id: string; // UUID — doubles as chat_session_id for backend
  name: string; // Auto-named from first query, user-editable
  createdAt: string;
  lastMessageAt: string;
  messages: ChatMessage[];
  resultIds: string[]; // References to stored results in localStorage
}

function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as Conversation[];
  } catch {
    return [];
  }
}

function shortTimestamp(): string {
  const now = new Date();
  const month = now.toLocaleString("en-US", { month: "short" });
  const day = now.getDate();
  const time = now.toLocaleString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
  return `${month} ${day}, ${time}`;
}

function saveConversations(conversations: Conversation[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
  } catch {
    console.warn("Failed to save conversations to localStorage");
  }
}

export function useConversations(
  onRemoveResults?: (resultIds: string[]) => void
) {
  const [conversations, setConversations] = useState<Conversation[]>(loadConversations);
  const [activeId, setActiveId] = useState<string | null>(null);

  // Persist whenever conversations change
  const isInitialMount = useRef(true);
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }
    saveConversations(conversations);
  }, [conversations]);

  const active = conversations.find((c) => c.id === activeId) ?? null;

  const create = useCallback((name?: string): Conversation => {
    const now = new Date().toISOString();
    const conv: Conversation = {
      id: crypto.randomUUID(),
      name: name ?? "New conversation",
      createdAt: now,
      lastMessageAt: now,
      messages: [],
      resultIds: [],
    };
    setConversations((prev) => [conv, ...prev]);
    setActiveId(conv.id);
    return conv;
  }, []);

  const switchTo = useCallback((id: string) => {
    setActiveId(id);
  }, []);

  const remove = useCallback(
    (id: string) => {
      setConversations((prev) => {
        const conv = prev.find((c) => c.id === id);
        if (conv && onRemoveResults) {
          onRemoveResults(conv.resultIds);
        }
        const updated = prev.filter((c) => c.id !== id);
        return updated;
      });
      if (activeId === id) {
        setActiveId(null);
      }
      // Best-effort server cleanup
      resetChat(id).catch(() => {});
    },
    [activeId, onRemoveResults]
  );

  const rename = useCallback((id: string, name: string) => {
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? { ...c, name } : c))
    );
  }, []);

  const updateMessages = useCallback(
    (id: string, messages: ChatMessage[]) => {
      setConversations((prev) =>
        prev.map((c) =>
          c.id === id
            ? { ...c, messages, lastMessageAt: new Date().toISOString() }
            : c
        )
      );
    },
    []
  );

  const addResultId = useCallback((id: string, resultId: string) => {
    setConversations((prev) =>
      prev.map((c) =>
        c.id === id
          ? { ...c, resultIds: [...c.resultIds, resultId] }
          : c
      )
    );
  }, []);

  /** Auto-name a conversation from the first query (truncated) with timestamp. */
  const autoName = useCallback((id: string, prompt: string) => {
    const truncated = prompt.length > 50 ? prompt.slice(0, 47) + "..." : prompt;
    const name = `${truncated} · ${shortTimestamp()}`;
    setConversations((prev) =>
      prev.map((c) =>
        c.id === id && c.name === "New conversation" ? { ...c, name } : c
      )
    );
  }, []);

  const clearAll = useCallback(() => {
    // Collect all result IDs for cleanup
    if (onRemoveResults) {
      const allResultIds = conversations.flatMap((c) => c.resultIds);
      if (allResultIds.length > 0) onRemoveResults(allResultIds);
    }
    // Best-effort server cleanup for all sessions
    for (const conv of conversations) {
      resetChat(conv.id).catch(() => {});
    }
    setConversations([]);
    setActiveId(null);
  }, [conversations, onRemoveResults]);

  return {
    conversations,
    active,
    activeId,
    create,
    switchTo,
    remove,
    clearAll,
    rename,
    updateMessages,
    addResultId,
    autoName,
  };
}
