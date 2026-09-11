/**
 * "Computing n/80" — the progress of a heavy endpoint that answered 202.
 *
 * In the packaged desktop app the server's warm loops are off (a laptop should
 * not run a Monte Carlo every ten minutes), so the FIRST request for the
 * 80-ticker screener is the cold compute: about two minutes, against a 45 s
 * fetch timeout. It showed a red error while the work was in fact running, and
 * the retry threw the first attempt's progress away ("stock screener doesn't
 * work", 2026-09-11).
 *
 * The server now answers `202 {state, job, progress}` and `fetchAPI` polls. This
 * store is how the number reaches the page: `fetchAPI` publishes, a component
 * subscribes. Keeping it out of React Query's cache is deliberate — the query
 * is still "loading", and this is a side-channel about the same request, not a
 * second result.
 */

export type ComputingProgress = { done: number; total: number };

const state = new Map<string, ComputingProgress>();
const listeners = new Set<() => void>();
// A stable snapshot per path: `useSyncExternalStore` re-renders forever if
// `getSnapshot` returns a fresh object each call.
const snapshots = new Map<string, ComputingProgress | null>();

function emit() {
  for (const l of listeners) l();
}

export function setComputing(path: string, progress: ComputingProgress | null) {
  const prev = state.get(path);
  if (progress === null) {
    if (prev === undefined) return;
    state.delete(path);
    snapshots.set(path, null);
    emit();
    return;
  }
  if (prev && prev.done === progress.done && prev.total === progress.total) return;
  state.set(path, progress);
  snapshots.set(path, progress);
  emit();
}

export function subscribeComputing(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function getComputing(path: string): ComputingProgress | null {
  if (!snapshots.has(path)) snapshots.set(path, state.get(path) ?? null);
  return snapshots.get(path) ?? null;
}
