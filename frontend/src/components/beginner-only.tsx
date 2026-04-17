"use client";

import * as React from "react";
import { useBeginnerMode } from "@/hooks/use-beginner-mode";

/**
 * Conditional renderer for content that should be visible depending on
 * Beginner Mode state. Mirrors the logic used across pages so toggling
 * is one source of truth.
 *
 * <AdvancedOnly> — hide in beginner mode (dense analytics, SHAP, factors)
 * <BeginnerOnly> — show only in beginner mode (plain-English explainers)
 */

export function AdvancedOnly({ children }: { children: React.ReactNode }) {
  const { beginner } = useBeginnerMode();
  if (beginner) return null;
  return <>{children}</>;
}

export function BeginnerOnly({ children }: { children: React.ReactNode }) {
  const { beginner } = useBeginnerMode();
  if (!beginner) return null;
  return <>{children}</>;
}

/**
 * Helper: take a pro label + a plain-English one and pick per mode.
 */
export function ModeLabel({ pro, beginner }: { pro: string; beginner: string }) {
  const { beginner: isBeginner } = useBeginnerMode();
  return <>{isBeginner ? beginner : pro}</>;
}

/**
 * Inline explainer card — renders ONLY in beginner mode, so pros don't
 * see the noise. Keep it short — one sentence, not a lecture.
 */
export function BeginnerHint({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const { beginner } = useBeginnerMode();
  if (!beginner) return null;
  return (
    <div
      className={
        "rounded-md border border-blue-500/20 bg-blue-500/5 px-3 py-2 text-xs text-blue-400/80 " +
        (className ?? "")
      }
    >
      <span className="font-mono uppercase tracking-wider text-blue-400/60 mr-2">Heads-up</span>
      {children}
    </div>
  );
}
