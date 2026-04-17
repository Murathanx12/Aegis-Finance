"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Small badge showing when data was last refreshed + a quick hint on
 * expected staleness. Builds trust — users should never wonder whether
 * they're looking at live vs 15-min-delayed vs EOD data.
 */
export function DataFreshness({
  source,
  updatedAt,
  expectedStaleSeconds,
  className,
}: {
  source?: string;
  updatedAt?: Date | number | string;
  expectedStaleSeconds?: number;
  className?: string;
}) {
  const [now, setNow] = React.useState<number>(() => Date.now());

  React.useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  const updated = updatedAt ? new Date(updatedAt).getTime() : undefined;
  const ageSec = updated ? Math.max(0, (now - updated) / 1000) : undefined;

  let tone: "fresh" | "stale" | "unknown" = "unknown";
  if (ageSec !== undefined && expectedStaleSeconds !== undefined) {
    tone = ageSec <= expectedStaleSeconds ? "fresh" : "stale";
  } else if (ageSec !== undefined) {
    tone = "fresh";
  }

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-wider",
        tone === "fresh" && "text-emerald-500/80",
        tone === "stale" && "text-amber-500/80",
        tone === "unknown" && "text-muted-foreground",
        className,
      )}
      title={
        updated
          ? `Source: ${source ?? "unknown"} · updated ${new Date(updated).toLocaleString()}`
          : "Freshness unknown"
      }
    >
      <span
        className={cn(
          "inline-block h-1.5 w-1.5 rounded-full",
          tone === "fresh" && "bg-emerald-500 animate-pulse",
          tone === "stale" && "bg-amber-500",
          tone === "unknown" && "bg-muted-foreground/50",
        )}
        aria-hidden
      />
      {source && <span>{source}</span>}
      {ageSec !== undefined && <span>· {formatAge(ageSec)}</span>}
    </span>
  );
}

function formatAge(sec: number): string {
  if (sec < 60) return `${Math.round(sec)}s ago`;
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.round(sec / 3600)}h ago`;
  return `${Math.round(sec / 86400)}d ago`;
}
