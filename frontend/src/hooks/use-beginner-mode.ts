"use client";

import { createContext, useContext, useState, useEffect, useCallback } from "react";

const STORAGE_KEY = "aegis-beginner-mode";

interface BeginnerModeContextType {
  beginner: boolean;
  toggle: () => void;
}

export const BeginnerModeContext = createContext<BeginnerModeContextType>({
  beginner: false,
  toggle: () => {},
});

export function useBeginnerMode() {
  return useContext(BeginnerModeContext);
}

export function useBeginnerModeState(): BeginnerModeContextType {
  const [beginner, setBeginner] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "true") setBeginner(true);
  }, []);

  const toggle = useCallback(() => {
    setBeginner((prev) => {
      const next = !prev;
      localStorage.setItem(STORAGE_KEY, String(next));
      return next;
    });
  }, []);

  return { beginner, toggle };
}
