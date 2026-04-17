"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { FunctionBadge } from "@/components/function-badge";
import { useWatchlist, WatchlistEntry } from "@/hooks/use-watchlist";
import { getWorldMarkets, WorldMarketRow } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Plus, X, Star, ArrowRight } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function WatchlistPage() {
  const { entries, ready, add, remove } = useWatchlist();
  const [input, setInput] = React.useState("");
  const [addError, setAddError] = React.useState<string | null>(null);

  const onAdd = () => {
    setAddError(null);
    if (!input.trim()) return;
    const ok = add(input, undefined);
    if (!ok) {
      setAddError("Invalid ticker. Use symbols like AAPL, BRK.B, ^GSPC.");
      return;
    }
    setInput("");
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Star className="h-5 w-5 text-amber-500" />
            <h1 className="text-2xl font-bold tracking-tight">Watchlist</h1>
            <FunctionBadge code="WATCH" title="Watchlist — not yet in command palette" />
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Tickers you want to follow. Stored locally — never leaves your browser.
            Click any row for full analysis.
          </p>
        </div>
        <div className="text-right text-xs text-muted-foreground">
          <div className="font-mono">{entries.length}/50 tickers</div>
        </div>
      </div>

      <Card className="p-4">
        <div className="flex items-center gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value.toUpperCase())}
            onKeyDown={(e) => {
              if (e.key === "Enter") onAdd();
            }}
            placeholder="Add ticker (e.g. AAPL, NVDA, ^GSPC)…"
            className="flex-1 bg-transparent border rounded-md border-border px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <Button onClick={onAdd} size="sm">
            <Plus className="h-4 w-4 mr-1" />
            Add
          </Button>
        </div>
        {addError && <p className="text-xs text-destructive mt-2">{addError}</p>}
      </Card>

      {!ready && (
        <div className="grid gap-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-14" />
          ))}
        </div>
      )}

      {ready && entries.length === 0 && (
        <Card className="p-8 text-center">
          <p className="text-sm text-muted-foreground">
            Your watchlist is empty. Add a ticker above or visit any{" "}
            <Link href="/stock" className="text-primary underline underline-offset-2">
              stock page
            </Link>{" "}
            to add it from there.
          </p>
        </Card>
      )}

      {ready && entries.length > 0 && (
        <div className="space-y-2">
          {entries.map((entry) => (
            <WatchlistRow key={entry.ticker} entry={entry} onRemove={remove} />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * One row — ticker + live quote via the world-markets cache (if present) or
 * a quick /api/stock/{ticker} price fetch. Keeps it lightweight: no per-row
 * full analysis request.
 */
function WatchlistRow({
  entry,
  onRemove,
}: {
  entry: WatchlistEntry;
  onRemove: (ticker: string) => void;
}) {
  // Try world-markets first — it's a single request that may contain this ticker.
  const { data: worldData } = useQuery({
    queryKey: ["world-markets"],
    queryFn: getWorldMarkets,
    staleTime: 60_000,
  });

  const fromWorld: WorldMarketRow | undefined = React.useMemo(() => {
    if (!worldData) return undefined;
    const all = [
      ...worldData.indices,
      ...worldData.fx,
      ...worldData.commodities,
      ...worldData.yields,
    ];
    return all.find((r) => r.ticker.toUpperCase() === entry.ticker);
  }, [worldData, entry.ticker]);

  // Fall back to per-ticker fetch only when world-markets doesn't have it
  const { data: realtime } = useQuery({
    queryKey: ["realtime", entry.ticker],
    queryFn: () =>
      fetch(`${API_BASE}/api/realtime/${encodeURIComponent(entry.ticker)}`)
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
    enabled: !fromWorld,
    staleTime: 60_000,
  });

  const price = fromWorld?.price ?? realtime?.price ?? null;
  const changePct = fromWorld?.change_pct ?? realtime?.change_pct ?? null;

  return (
    <Card className="p-3 flex items-center gap-3 hover:bg-accent/30 transition-colors">
      <div className="flex-1 min-w-0">
        <Link
          href={`/stock/${encodeURIComponent(entry.ticker)}`}
          className="flex items-center gap-2 group"
        >
          <span className="font-mono font-semibold tracking-wide text-sm">
            {entry.ticker}
          </span>
          <ArrowRight className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
        </Link>
        {entry.note && (
          <p className="text-xs text-muted-foreground mt-0.5 truncate">{entry.note}</p>
        )}
      </div>

      <div className="text-right">
        <div className="text-sm font-mono tabular-nums">
          {price !== null ? price.toFixed(2) : <span className="text-muted-foreground">—</span>}
        </div>
        {changePct !== null && (
          <div
            className={cn(
              "text-xs font-mono tabular-nums",
              changePct >= 0 ? "text-emerald-500" : "text-rose-500",
            )}
          >
            {changePct >= 0 ? "+" : ""}
            {changePct.toFixed(2)}%
          </div>
        )}
      </div>

      <button
        onClick={() => onRemove(entry.ticker)}
        className="p-1 text-muted-foreground hover:text-destructive transition-colors"
        aria-label={`Remove ${entry.ticker}`}
      >
        <X className="h-4 w-4" />
      </button>
    </Card>
  );
}
