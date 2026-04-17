"use client";

import { cn } from "@/lib/utils";

/**
 * Small Bloomberg-style function-mnemonic badge.
 * Shown on cards and page headers so users learn keyboard shortcuts
 * by exposure. Clicking copies the code to the clipboard.
 */
export function FunctionBadge({
  code,
  className,
  title,
}: {
  code: string;
  className?: string;
  title?: string;
}) {
  const handleClick = () => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(code).catch(() => {});
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      title={title ?? `Function ${code} — click to copy, or press Ctrl+K and type ${code}`}
      className={cn(
        "font-mono text-[10px] tracking-wider uppercase",
        "inline-flex items-center rounded border border-border bg-muted/40 px-1.5 py-0.5",
        "text-muted-foreground hover:text-foreground hover:bg-muted/70 transition-colors",
        className,
      )}
    >
      {code}
    </button>
  );
}
