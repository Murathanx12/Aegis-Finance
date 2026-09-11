"use client";

import { useSyncExternalStore } from "react";
import { getComputing, subscribeComputing, type ComputingProgress } from "./computing";

/**
 * How far along the heavy endpoint at `path` is, or null when nothing is
 * computing. Returns null on the server and on the first client render, which
 * is what a static export needs — the value only ever appears after a fetch.
 */
export function useComputing(path: string): ComputingProgress | null {
  return useSyncExternalStore(
    subscribeComputing,
    () => getComputing(path),
    () => null,
  );
}
