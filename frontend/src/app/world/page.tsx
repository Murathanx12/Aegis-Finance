"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { FunctionBadge } from "@/components/function-badge";
import { getWorldMarkets, WorldMarketRow } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ArrowUp, ArrowDown, Globe } from "lucide-react";

/**
 * Bloomberg WEI — global indices, FX, commodities, yields in a heat grid.
 * Data refreshes every 5 min (server cache); the client re-polls every 2 min
 * so the UI stays close-to-live when a user lingers on the page.
 */
export default function WorldMarketsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["world-markets"],
    queryFn: getWorldMarkets,
    refetchInterval: 2 * 60 * 1000,
    staleTime: 60 * 1000,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Globe className="h-6 w-6 text-primary" />
            <h1 className="text-2xl font-bold tracking-tight">World Markets</h1>
            <FunctionBadge code="WEI" />
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Live-ish snapshot of major indices, FX pairs, commodities, and sovereign yields. Refreshes every 2 min.
          </p>
        </div>
        {data && (
          <div className="text-right text-xs text-muted-foreground">
            <div className="font-mono">{data.counts.total_fetched}/{data.counts.total_attempted} fetched</div>
          </div>
        )}
      </div>

      {error && (
        <Card className="p-4 border-destructive/40 bg-destructive/5">
          <p className="text-sm text-destructive">
            Couldn&apos;t load world markets. The server may be prewarming — try again in a few seconds.
          </p>
        </Card>
      )}

      {isLoading && (
        <div className="grid gap-6">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
      )}

      {data && (
        <>
          <MoversRow gainers={data.top_gainers} losers={data.top_losers} />
          <Section title="Global Indices" rows={data.indices} showRegions />
          <Section title="FX Majors & EM" rows={data.fx} showRegions />
          <Section title="Commodities" rows={data.commodities} showRegions />
          <Section title="US Treasury Yields" rows={data.yields} />
        </>
      )}
    </div>
  );
}

function MoversRow({ gainers, losers }: { gainers: WorldMarketRow[]; losers: WorldMarketRow[] }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card className="p-4">
        <div className="flex items-center gap-2 mb-3">
          <ArrowUp className="h-4 w-4 text-emerald-500" />
          <h2 className="text-sm font-semibold">Top Gainers</h2>
        </div>
        <div className="space-y-1">
          {gainers.length === 0 && (
            <p className="text-xs text-muted-foreground">No data.</p>
          )}
          {gainers.map((g) => (
            <MoverRow key={`g-${g.ticker}`} row={g} direction="up" />
          ))}
        </div>
      </Card>
      <Card className="p-4">
        <div className="flex items-center gap-2 mb-3">
          <ArrowDown className="h-4 w-4 text-rose-500" />
          <h2 className="text-sm font-semibold">Top Losers</h2>
        </div>
        <div className="space-y-1">
          {losers.length === 0 && (
            <p className="text-xs text-muted-foreground">No data.</p>
          )}
          {losers.map((l) => (
            <MoverRow key={`l-${l.ticker}`} row={l} direction="down" />
          ))}
        </div>
      </Card>
    </div>
  );
}

function MoverRow({ row, direction }: { row: WorldMarketRow; direction: "up" | "down" }) {
  return (
    <div className="flex items-center justify-between py-1 text-sm">
      <span className="flex-1 truncate">{row.name}</span>
      <span
        className={cn(
          "font-mono tabular-nums text-xs",
          direction === "up" ? "text-emerald-500" : "text-rose-500",
        )}
      >
        {row.change_pct !== null ? `${row.change_pct >= 0 ? "+" : ""}${row.change_pct.toFixed(2)}%` : "—"}
      </span>
    </div>
  );
}

function Section({
  title,
  rows,
  showRegions = false,
}: {
  title: string;
  rows: WorldMarketRow[];
  showRegions?: boolean;
}) {
  const byRegion = React.useMemo(() => {
    if (!showRegions) return { all: rows };
    const g: Record<string, WorldMarketRow[]> = {};
    for (const r of rows) {
      g[r.region] = g[r.region] ?? [];
      g[r.region].push(r);
    }
    return g;
  }, [rows, showRegions]);

  return (
    <Card className="p-4">
      <h2 className="text-sm font-semibold mb-3">{title}</h2>
      {Object.entries(byRegion).map(([region, items]) => (
        <div key={region} className="mb-4 last:mb-0">
          {showRegions && (
            <h3 className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
              {region}
            </h3>
          )}
          <div className="grid gap-1 grid-cols-1 sm:grid-cols-2 md:grid-cols-3">
            {items.map((row) => (
              <Tile key={row.ticker} row={row} />
            ))}
          </div>
        </div>
      ))}
    </Card>
  );
}

function Tile({ row }: { row: WorldMarketRow }) {
  const pct = row.change_pct;
  const colour = pct === null
    ? "bg-muted/30 border-border"
    : pct > 1
    ? "bg-emerald-500/15 border-emerald-500/30"
    : pct > 0
    ? "bg-emerald-500/5 border-emerald-500/20"
    : pct > -1
    ? "bg-rose-500/5 border-rose-500/20"
    : "bg-rose-500/15 border-rose-500/30";

  return (
    <div
      className={cn(
        "rounded-md border px-2.5 py-1.5 flex items-center justify-between gap-2",
        colour,
      )}
      title={`${row.ticker} — ${row.source}`}
    >
      <span className="flex-1 min-w-0">
        <span className="block text-xs font-medium truncate">{row.name}</span>
        <span className="block text-[10px] font-mono text-muted-foreground truncate">
          {row.ticker}
        </span>
      </span>
      <span className="text-right flex-shrink-0">
        <span className="block text-xs font-mono tabular-nums">
          {formatPrice(row.price, row.category)}
        </span>
        {pct !== null && (
          <span
            className={cn(
              "block text-[10px] font-mono tabular-nums",
              pct >= 0 ? "text-emerald-500" : "text-rose-500",
            )}
          >
            {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
          </span>
        )}
      </span>
    </div>
  );
}

function formatPrice(price: number, category: WorldMarketRow["category"]) {
  if (category === "fx") return price.toFixed(4);
  if (category === "yield") return `${price.toFixed(3)}%`;
  if (category === "commodity") return price.toFixed(2);
  return price >= 1000 ? price.toFixed(0) : price.toFixed(2);
}
