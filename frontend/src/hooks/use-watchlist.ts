"use client";

import * as React from "react";

/**
 * Browser-local watchlist — a simple ordered list of ticker symbols the
 * user wants to track. Kept intentionally separate from the Portfolio
 * (holdings) so users can watch names they don't own.
 */

const STORAGE_KEY = "aegis.watchlist.v1";
const MAX_TICKERS = 50;

export type WatchlistEntry = {
  ticker: string;
  addedAt: number;
  note?: string;
};

function read(): WatchlistEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((e): e is WatchlistEntry => e && typeof e.ticker === "string");
  } catch {
    return [];
  }
}

function write(entries: WatchlistEntry[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
    window.dispatchEvent(new Event("aegis-watchlist-changed"));
  } catch {
    // quota exhausted — silent
  }
}

export function useWatchlist() {
  const [entries, setEntries] = React.useState<WatchlistEntry[]>([]);
  const [ready, setReady] = React.useState(false);

  React.useEffect(() => {
    setEntries(read());
    setReady(true);

    const onChange = () => setEntries(read());
    // React to changes from another tab or another hook instance
    window.addEventListener("storage", onChange);
    window.addEventListener("aegis-watchlist-changed", onChange);
    return () => {
      window.removeEventListener("storage", onChange);
      window.removeEventListener("aegis-watchlist-changed", onChange);
    };
  }, []);

  const add = React.useCallback((ticker: string, note?: string) => {
    const t = ticker.trim().toUpperCase();
    if (!/^[A-Z0-9.\-^]{1,10}$/.test(t)) return false;
    setEntries((prev) => {
      if (prev.some((e) => e.ticker === t)) return prev;
      const next = [...prev, { ticker: t, addedAt: Date.now(), note }].slice(0, MAX_TICKERS);
      write(next);
      return next;
    });
    return true;
  }, []);

  const remove = React.useCallback((ticker: string) => {
    const t = ticker.toUpperCase();
    setEntries((prev) => {
      const next = prev.filter((e) => e.ticker !== t);
      write(next);
      return next;
    });
  }, []);

  const toggle = React.useCallback(
    (ticker: string) => {
      const t = ticker.toUpperCase();
      setEntries((prev) => {
        const has = prev.some((e) => e.ticker === t);
        const next = has
          ? prev.filter((e) => e.ticker !== t)
          : [...prev, { ticker: t, addedAt: Date.now() }].slice(0, MAX_TICKERS);
        write(next);
        return next;
      });
    },
    [],
  );

  const updateNote = React.useCallback((ticker: string, note: string) => {
    const t = ticker.toUpperCase();
    setEntries((prev) => {
      const next = prev.map((e) => (e.ticker === t ? { ...e, note } : e));
      write(next);
      return next;
    });
  }, []);

  const clear = React.useCallback(() => {
    setEntries([]);
    write([]);
  }, []);

  const has = React.useCallback(
    (ticker: string) => entries.some((e) => e.ticker === ticker.toUpperCase()),
    [entries],
  );

  return { entries, ready, add, remove, toggle, updateNote, clear, has };
}
