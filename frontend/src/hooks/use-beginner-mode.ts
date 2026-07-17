"use client";

import { createContext, useContext, useState, useEffect, useCallback } from "react";

// V4 (2026-07-17): "beginner mode" grew into the casual/advanced UI switch.
// CASUAL is the default for new visitors — the dense analytics surfaces are
// an opt-in, not a hazing ritual. `beginner === true` now means casual mode;
// the legacy name is kept so every existing consumer works unchanged.
const STORAGE_KEY = "aegis-ui-mode"; // "casual" | "advanced"
const LEGACY_KEY = "aegis-beginner-mode"; // pre-V4 boolean, migrated once

export type UiMode = "casual" | "advanced";

interface BeginnerModeContextType {
  beginner: boolean; // true === casual mode
  toggle: () => void;
}

export const BeginnerModeContext = createContext<BeginnerModeContextType>({
  beginner: true,
  toggle: () => {},
});

export function useBeginnerMode() {
  return useContext(BeginnerModeContext);
}

/** Preferred V4 API: the same context, in casual/advanced vocabulary. */
export function useUiMode(): { mode: UiMode; toggle: () => void } {
  const { beginner, toggle } = useBeginnerMode();
  return { mode: beginner ? "casual" : "advanced", toggle };
}

export function useBeginnerModeState(): BeginnerModeContextType {
  // Casual by default; the stored choice is applied after mount (SSR-safe).
  const [beginner, setBeginner] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "casual") {
      setBeginner(true);
      return;
    }
    if (stored === "advanced") {
      setBeginner(false);
      return;
    }
    // One-time migration: an explicit pre-V4 choice must not flip under the
    // user. Old beginner=true → casual; old beginner=false → advanced
    // (they had the full surface and chose to keep it).
    const legacy = localStorage.getItem(LEGACY_KEY);
    if (legacy === "true") {
      localStorage.setItem(STORAGE_KEY, "casual");
      setBeginner(true);
    } else if (legacy === "false") {
      localStorage.setItem(STORAGE_KEY, "advanced");
      setBeginner(false);
    }
    // No stored value at all: first visit → casual default, nothing persisted
    // until the user actually chooses.
  }, []);

  const toggle = useCallback(() => {
    setBeginner((prev) => {
      const next = !prev;
      localStorage.setItem(STORAGE_KEY, next ? "casual" : "advanced");
      return next;
    });
  }, []);

  return { beginner, toggle };
}
