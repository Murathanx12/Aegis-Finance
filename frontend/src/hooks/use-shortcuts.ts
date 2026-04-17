"use client";

import { useEffect } from "react";

type ShortcutHandler = (e: KeyboardEvent) => void;

type Binding = {
  /** Match: "k" (just key), "cmd+k" (meta/ctrl + key), "g p" (chord) */
  combo: string;
  handler: ShortcutHandler;
  /** Skip when the user is typing in an input / textarea / contenteditable. */
  allowInInputs?: boolean;
};

/**
 * Global keyboard-shortcut hook.
 *
 * Supports:
 *   - Simple keys:       "?" or "Escape"
 *   - Modifier combos:   "cmd+k" / "ctrl+k" (matches either, cross-platform)
 *   - Two-key chords:    "g p" — user presses g, then p within 1s
 *
 * By default shortcuts are disabled while the user is focused in an input
 * field. Set allowInInputs=true for universal shortcuts (Esc, Cmd+K).
 */
export function useShortcuts(bindings: Binding[]) {
  useEffect(() => {
    let chordPrefix: string | null = null;
    let chordTimer: ReturnType<typeof setTimeout> | null = null;

    const resetChord = () => {
      chordPrefix = null;
      if (chordTimer) {
        clearTimeout(chordTimer);
        chordTimer = null;
      }
    };

    const isTyping = (el: EventTarget | null) => {
      if (!(el instanceof HTMLElement)) return false;
      const tag = el.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
      if (el.isContentEditable) return true;
      return false;
    };

    const matchSimple = (combo: string, e: KeyboardEvent): boolean => {
      const norm = combo.toLowerCase();
      if (norm.includes("+")) {
        const parts = norm.split("+").map((s) => s.trim());
        const key = parts.pop() ?? "";
        const wantCmd = parts.includes("cmd") || parts.includes("ctrl");
        const wantShift = parts.includes("shift");
        const wantAlt = parts.includes("alt");
        if (wantCmd && !(e.metaKey || e.ctrlKey)) return false;
        if (!wantCmd && (e.metaKey || e.ctrlKey)) return false;
        if (wantShift && !e.shiftKey) return false;
        if (wantAlt && !e.altKey) return false;
        return e.key.toLowerCase() === key;
      }
      // Single-key (no modifier)
      if (e.metaKey || e.ctrlKey || e.altKey) return false;
      return e.key === combo || e.key.toLowerCase() === norm;
    };

    const onKey = (e: KeyboardEvent) => {
      for (const b of bindings) {
        if (!b.allowInInputs && isTyping(e.target)) continue;
        const combo = b.combo.toLowerCase();

        // Chord like "g p"
        if (combo.includes(" ") && !combo.includes("+")) {
          const [first, second] = combo.split(/\s+/);
          if (!chordPrefix && e.key.toLowerCase() === first && !e.metaKey && !e.ctrlKey) {
            // Start chord
            chordPrefix = first;
            chordTimer = setTimeout(resetChord, 1000);
            e.preventDefault();
            return;
          }
          if (chordPrefix === first && e.key.toLowerCase() === second) {
            resetChord();
            e.preventDefault();
            b.handler(e);
            return;
          }
        } else if (matchSimple(b.combo, e)) {
          e.preventDefault();
          b.handler(e);
          return;
        }
      }

      // Any unhandled key that's not a chord-prefix cancels the chord
      if (chordPrefix && !e.metaKey && !e.ctrlKey) {
        resetChord();
      }
    };

    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (chordTimer) clearTimeout(chordTimer);
    };
  }, [bindings]);
}
