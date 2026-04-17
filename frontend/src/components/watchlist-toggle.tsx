"use client";

import * as React from "react";
import { Star } from "lucide-react";
import { cn } from "@/lib/utils";
import { useWatchlist } from "@/hooks/use-watchlist";

/**
 * Star icon that toggles a ticker's watchlist membership.
 * Drop into any stock header / card that has a ticker.
 */
export function WatchlistToggle({
  ticker,
  size = "md",
  className,
}: {
  ticker: string;
  size?: "sm" | "md";
  className?: string;
}) {
  const { has, toggle, ready } = useWatchlist();
  if (!ready) return <span className={cn("h-5 w-5", className)} aria-hidden />;
  const inList = has(ticker);
  const iconSize = size === "sm" ? "h-4 w-4" : "h-5 w-5";

  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        toggle(ticker);
      }}
      title={inList ? `Remove ${ticker} from watchlist` : `Add ${ticker} to watchlist`}
      aria-pressed={inList}
      className={cn(
        "inline-flex items-center justify-center rounded-md p-1 transition-colors",
        inList
          ? "text-amber-500 hover:text-amber-400"
          : "text-muted-foreground hover:text-foreground",
        className,
      )}
    >
      <Star className={cn(iconSize, inList && "fill-current")} />
    </button>
  );
}
