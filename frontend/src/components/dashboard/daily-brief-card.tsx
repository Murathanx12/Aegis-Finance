"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { getDailyBrief } from "@/lib/api";
import { useWatchlist } from "@/hooks/use-watchlist";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTooltip } from "@/components/info-tooltip";
import { Newspaper } from "lucide-react";

function loadHoldingTickers(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem("aegis_holdings");
    const holdings = raw ? JSON.parse(raw) : [];
    return Array.isArray(holdings)
      ? holdings.map((h: { ticker?: string }) => h?.ticker).filter((t): t is string => typeof t === "string")
      : [];
  } catch {
    return [];
  }
}

function MoveChip({ label, pct }: { label: string; pct: number | null }) {
  const color =
    pct == null ? "text-muted-foreground" : pct >= 0 ? "text-emerald-400" : "text-red-400";
  return (
    <span className="inline-flex items-baseline gap-1 rounded-md bg-muted/40 px-2 py-1 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className={`font-semibold tabular-nums ${color}`}>
        {pct == null ? "—" : `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`}
      </span>
    </span>
  );
}

export function DailyBriefCard() {
  const { entries, ready } = useWatchlist();

  const tickers = useMemo(() => {
    const fromWatchlist = entries.map((e) => e.ticker);
    const merged = [...new Set([...fromWatchlist, ...loadHoldingTickers()])];
    return merged.filter((t) => !t.startsWith("^")).slice(0, 15);
  }, [entries]);

  const { data, isLoading, error } = useQuery({
    queryKey: ["daily-brief", tickers.join(",")],
    queryFn: () => getDailyBrief(tickers),
    enabled: ready,
    staleTime: 15 * 60_000,
  });

  if (!ready || isLoading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-medium text-muted-foreground flex items-center gap-2">
            <Newspaper className="h-4 w-4" /> Today&apos;s Brief
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-24 w-full" />
        </CardContent>
      </Card>
    );
  }
  if (error || !data) return null; // the brief is additive — never block the dashboard

  const s = data.summary;
  return (
    <Card className="animate-fade-in">
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-medium text-muted-foreground flex items-center">
          <Newspaper className="h-4 w-4 mr-2" />
          Today&apos;s Brief
          <InfoTooltip
            text="What moved today (indices, oil, gold, rates, VIX), the geopolitical news read, and how it touched the tickers in your watchlist and portfolio. Descriptive context, not advice."
            beginnerText="A quick morning-paper summary: what happened in markets today and what it might mean for the stocks you follow."
          />
          {s?.sentiment && (
            <span className={`ml-auto text-xs font-semibold uppercase tracking-wide ${
              s.sentiment === "bullish" ? "text-emerald-400" :
              s.sentiment === "bearish" ? "text-red-400" : "text-amber-400"
            }`}>
              {s.sentiment}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Market tape */}
        <div className="flex flex-wrap gap-2">
          {data.market.map((m) => (
            <MoveChip key={m.ticker} label={m.label} pct={m.change_1d_pct} />
          ))}
        </div>

        {s && (
          <div className="space-y-2 text-sm leading-relaxed">
            <p>
              <span className="font-semibold text-muted-foreground">What happened: </span>
              {s.what_happened}
            </p>
            <p>
              <span className="font-semibold text-muted-foreground">Your stocks: </span>
              {s.impact_on_holdings}
            </p>
            <p>
              <span className="font-semibold text-muted-foreground">Risks to watch: </span>
              {s.risks_to_watch}
            </p>
          </div>
        )}

        {/* User tickers */}
        {data.your_tickers.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {data.your_tickers.map((t) => (
              <Link key={t.ticker} href={`/stock/${encodeURIComponent(t.ticker)}`}>
                <MoveChip label={t.ticker} pct={t.change_1d_pct} />
              </Link>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            Add stocks to your <Link href="/watchlist" className="underline">watchlist</Link> or{" "}
            <Link href="/portfolio" className="underline">portfolio</Link> to see how the day
            touched them.
          </p>
        )}

        <p className="text-[11px] text-muted-foreground/70">{data.disclaimer}</p>
      </CardContent>
    </Card>
  );
}
