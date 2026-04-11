import { useState, useRef, useCallback } from "react";
import { streamQuery } from "@/api/client";
import type { QueryRequest, StatusEvent, QueryResult } from "@/api/types";

export type QueryStatus = "idle" | "streaming" | "complete" | "error";

export function useQuery() {
  const [status, setStatus] = useState<QueryStatus>("idle");
  const [steps, setSteps] = useState<StatusEvent[]>([]);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const execute = useCallback((request: QueryRequest) => {
    // Cancel any in-flight request
    controllerRef.current?.abort();

    setStatus("streaming");
    setSteps([]);
    setResult(null);
    setError(null);

    controllerRef.current = streamQuery(request, {
      onStatus: (event) => {
        setSteps((prev) => [...prev, event]);
      },
      onComplete: (queryResult) => {
        setResult(queryResult);
        setStatus("complete");
      },
      onError: (err) => {
        console.error("[useQuery] onError:", err);
        setError(err);
        setStatus("error");
      },
    });
  }, []);

  /** Update the displayed result without running a new query (e.g., from tool results). */
  const updateResult = useCallback((newResult: QueryResult) => {
    setResult(newResult);
    setStatus("complete");
  }, []);

  const cancel = useCallback(() => {
    controllerRef.current?.abort();
    setStatus("idle");
  }, []);

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    setStatus("idle");
    setSteps([]);
    setResult(null);
    setError(null);
  }, []);

  return { status, steps, result, error, execute, updateResult, cancel, reset, setSteps };
}
