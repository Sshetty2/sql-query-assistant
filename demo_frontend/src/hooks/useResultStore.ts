import { useCallback } from "react";
import type { QueryResult } from "@/api/types";

const STORAGE_PREFIX = "sql-assistant-result-";

/**
 * localStorage-based result storage tied to chat messages.
 * Each result is stored as a full QueryResult JSON blob keyed by a UUID.
 */
export function useResultStore() {
  const store = useCallback((result: QueryResult): string => {
    const id = crypto.randomUUID();
    try {
      localStorage.setItem(
        `${STORAGE_PREFIX}${id}`,
        JSON.stringify(result)
      );
    } catch {
      // localStorage might be full — best effort
      console.warn("Failed to store result in localStorage");
    }
    return id;
  }, []);

  const get = useCallback((id: string): QueryResult | null => {
    try {
      const raw = localStorage.getItem(`${STORAGE_PREFIX}${id}`);
      if (!raw) return null;
      return JSON.parse(raw) as QueryResult;
    } catch {
      return null;
    }
  }, []);

  const remove = useCallback((id: string): void => {
    localStorage.removeItem(`${STORAGE_PREFIX}${id}`);
  }, []);

  const removeMany = useCallback((ids: string[]): void => {
    for (const id of ids) {
      localStorage.removeItem(`${STORAGE_PREFIX}${id}`);
    }
  }, []);

  const clear = useCallback((): void => {
    const keys: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key?.startsWith(STORAGE_PREFIX)) {
        keys.push(key);
      }
    }
    for (const key of keys) {
      localStorage.removeItem(key);
    }
  }, []);

  return { store, get, remove, removeMany, clear };
}
