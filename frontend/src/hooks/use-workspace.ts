"use client";

import * as React from "react";

/**
 * Bloomberg-style tile workspace — a persisted grid of up-to-6 "tiles" where
 * each tile is a function code (optionally with a ticker). Users drop their
 * favourite views into a single dashboard.
 *
 * Storage: localStorage (no server round trip). Cleared only on explicit
 * reset from the UI.
 */

export type WorkspaceTile = {
  id: string;
  functionCode: string;
  ticker?: string;
  /** User-chosen short label shown above the tile. */
  label?: string;
};

export type Workspace = {
  layout: "2x2" | "3x2" | "2x3";
  tiles: WorkspaceTile[];
};

const STORAGE_KEY = "aegis.workspace.v1";
const DEFAULT_WORKSPACE: Workspace = {
  layout: "2x2",
  tiles: [
    { id: "t1", functionCode: "DASH", label: "Market Overview" },
    { id: "t2", functionCode: "PORT", label: "Portfolio" },
    { id: "t3", functionCode: "CRASH", label: "Crash Risk" },
    { id: "t4", functionCode: "NI", label: "News" },
  ],
};

function readStorage(): Workspace {
  if (typeof window === "undefined") return DEFAULT_WORKSPACE;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_WORKSPACE;
    const parsed = JSON.parse(raw) as Workspace;
    if (!parsed.tiles || !Array.isArray(parsed.tiles)) return DEFAULT_WORKSPACE;
    return parsed;
  } catch {
    return DEFAULT_WORKSPACE;
  }
}

function writeStorage(ws: Workspace) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ws));
  } catch {
    // quota exceeded or private mode — silently ignore
  }
}

export function useWorkspace() {
  const [workspace, setWorkspace] = React.useState<Workspace>(DEFAULT_WORKSPACE);
  const [ready, setReady] = React.useState(false);

  // Hydrate after mount so SSR output doesn't mismatch
  React.useEffect(() => {
    setWorkspace(readStorage());
    setReady(true);
  }, []);

  const save = React.useCallback((ws: Workspace) => {
    setWorkspace(ws);
    writeStorage(ws);
  }, []);

  const updateTile = React.useCallback(
    (id: string, patch: Partial<WorkspaceTile>) => {
      setWorkspace((prev) => {
        const next: Workspace = {
          ...prev,
          tiles: prev.tiles.map((t) => (t.id === id ? { ...t, ...patch } : t)),
        };
        writeStorage(next);
        return next;
      });
    },
    [],
  );

  const addTile = React.useCallback((tile: Omit<WorkspaceTile, "id">) => {
    setWorkspace((prev) => {
      const id = `t${Date.now().toString(36)}`;
      const next: Workspace = {
        ...prev,
        tiles: [...prev.tiles, { ...tile, id }].slice(0, 6),
      };
      writeStorage(next);
      return next;
    });
  }, []);

  const removeTile = React.useCallback((id: string) => {
    setWorkspace((prev) => {
      const next: Workspace = {
        ...prev,
        tiles: prev.tiles.filter((t) => t.id !== id),
      };
      writeStorage(next);
      return next;
    });
  }, []);

  const setLayout = React.useCallback((layout: Workspace["layout"]) => {
    setWorkspace((prev) => {
      const next: Workspace = { ...prev, layout };
      writeStorage(next);
      return next;
    });
  }, []);

  const reset = React.useCallback(() => save(DEFAULT_WORKSPACE), [save]);

  return {
    workspace,
    ready,
    updateTile,
    addTile,
    removeTile,
    setLayout,
    reset,
  };
}
