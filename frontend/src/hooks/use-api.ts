"use client";

import { useState, useEffect, useCallback, useRef } from "react";

interface UseApiOptions {
  refreshInterval?: number; // ms — auto-refetch interval
}

interface UseApiResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = [], options?: UseApiOptions): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const retryCount = useRef(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetcher();
      setData(result);
      retryCount.current = 0;
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown error";

      // Auto-retry once on network/timeout errors
      if (retryCount.current < 1 && (message.includes("fetch") || message.includes("network") || message.includes("timeout"))) {
        retryCount.current++;
        setTimeout(() => load(), 2000);
        return;
      }

      // Friendly error messages
      if (message.includes("404")) {
        setError("Not found. The ticker may be delisted or invalid.");
      } else if (message.includes("422")) {
        setError("Invalid input. Check the ticker format.");
      } else if (message.includes("429")) {
        setError("Rate limited. Please wait a moment and try again.");
      } else if (message.includes("500")) {
        setError("Server error. The backend may be processing — try again shortly.");
      } else if (message.includes("fetch") || message.includes("Failed")) {
        setError("Cannot reach the API. Make sure the backend is running on port 8000.");
      } else {
        setError(message);
      }
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    load();
  }, [load]);

  // Auto-refresh interval
  useEffect(() => {
    if (!options?.refreshInterval) return;
    const id = setInterval(() => {
      load();
    }, options.refreshInterval);
    return () => clearInterval(id);
  }, [load, options?.refreshInterval]);

  return { data, loading, error, refetch: load };
}
