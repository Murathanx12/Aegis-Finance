"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { getStockScreener } from "@/lib/api";
import type { ScreenerStock } from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorCard } from "@/components/error-card";
import { InfoTooltip } from "@/components/info-tooltip";

type SortKey = "ticker" | "current_price" | "expected_return" | "sharpe" | "prob_loss" | "volatility" | "beta";
type SortDir = "asc" | "desc";

const SECTORS = [
  "All",
  "Technology",
  "Healthcare",
  "Financials",
  "Energy",
  "Consumer Disc.",
  "Consumer Staples",
  "Industrials",
  "Utilities",
  "Real Estate",
  "Materials",
  "Communications",
];

function formatCap(cap: number | null): string {
  if (!cap) return "--";
  if (cap >= 1e12) return `$${(cap / 1e12).toFixed(1)}T`;
  if (cap >= 1e9) return `$${(cap / 1e9).toFixed(0)}B`;
  return `$${(cap / 1e6).toFixed(0)}M`;
}

function signalLabel(ret: number, sharpe: number, probLoss: number): { text: string; color: string } {
  if (sharpe >= 0.35 && ret >= 10 && probLoss < 25) return { text: "Buy", color: "text-emerald-400" };
  if (sharpe >= 0.15 && ret >= 5) return { text: "Hold", color: "text-amber-400" };
  if (sharpe < 0.05 || ret < 0 || probLoss > 50) return { text: "Sell", color: "text-red-400" };
  return { text: "Hold", color: "text-amber-400" };
}

function SortHeader({
  label,
  sortKey,
  currentSort,
  currentDir,
  onSort,
  className = "",
  tooltip,
}: {
  label: string;
  sortKey: SortKey;
  currentSort: SortKey;
  currentDir: SortDir;
  onSort: (key: SortKey) => void;
  className?: string;
  tooltip?: string;
}) {
  const active = currentSort === sortKey;
  return (
    <th
      className={`py-2 pr-4 cursor-pointer select-none hover:text-foreground transition-colors ${className}`}
      scope="col"
      onClick={() => onSort(sortKey)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        {tooltip && <InfoTooltip text={tooltip} />}
        {active && <span className="text-xs">{currentDir === "asc" ? "\u2191" : "\u2193"}</span>}
      </span>
    </th>
  );
}

export default function ScreenerPage() {
  const router = useRouter();
  const [sectorFilter, setSectorFilter] = useState("All");
  const [sortKey, setSortKey] = useState<SortKey>("sharpe");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: queryKeys.stock.screener,
    queryFn: getStockScreener,
    staleTime: staleTimes.stock,
  });

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "ticker" ? "asc" : "desc");
    }
  };

  const filtered = useMemo(() => {
    if (!data?.stocks) return [];
    let stocks = data.stocks;
    if (sectorFilter !== "All") {
      stocks = stocks.filter((s) => s.sector === sectorFilter);
    }
    return [...stocks].sort((a, b) => {
      const av = a[sortKey] ?? 0;
      const bv = b[sortKey] ?? 0;
      if (typeof av === "string" && typeof bv === "string") {
        return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
      }
      return sortDir === "asc" ? (av as number) - (bv as number) : (bv as number) - (av as number);
    });
  }, [data, sectorFilter, sortKey, sortDir]);

  const summaryStocks = data?.stocks ?? [];

  return (
    <div className="space-y-6 animate-slide-up">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Stock Screener</h1>
        <p className="text-sm text-muted-foreground">
          Top S&P 500 stocks ranked by risk-adjusted 5-year expected return
        </p>
      </div>

      {summaryStocks.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Card>
            <CardContent className="p-3">
              <p className="text-[10px] text-muted-foreground uppercase">Stocks Analyzed</p>
              <p className="text-xl font-bold tabular-nums">{summaryStocks.length}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-3">
              <p className="text-[10px] text-muted-foreground uppercase">Top Sharpe</p>
              <p className="text-lg font-bold">{summaryStocks[0]?.ticker}</p>
              <p className="text-sm text-emerald-400 tabular-nums">{summaryStocks[0]?.sharpe.toFixed(2)}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-3">
              <p className="text-[10px] text-muted-foreground uppercase">Buy Signals</p>
              <p className="text-xl font-bold tabular-nums text-emerald-400">
                {summaryStocks.filter((s) => signalLabel(s.expected_return, s.sharpe, s.prob_loss).text === "Buy").length}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-3">
              <p className="text-[10px] text-muted-foreground uppercase">Avg Expected Return</p>
              <p className="text-xl font-bold tabular-nums">
                {(summaryStocks.reduce((a, s) => a + s.expected_return, 0) / summaryStocks.length).toFixed(1)}%
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Stock Rankings
          </CardTitle>
          <select
            value={sectorFilter}
            onChange={(e) => setSectorFilter(e.target.value)}
            className="rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            aria-label="Filter by sector"
          >
            {SECTORS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 12 }).map((_, i) => (
                <Skeleton key={i} className="h-8 w-full" />
              ))}
            </div>
          ) : filtered.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" aria-label="Stock screener table">
                <thead>
                  <tr className="border-b border-border text-left text-muted-foreground">
                    <SortHeader label="Ticker" sortKey="ticker" currentSort={sortKey} currentDir={sortDir} onSort={handleSort} />
                    <th className="py-2 pr-4 hidden md:table-cell" scope="col">Sector</th>
                    <SortHeader label="Price" sortKey="current_price" currentSort={sortKey} currentDir={sortDir} onSort={handleSort} className="text-right" />
                    <SortHeader
                      label="5Y Return"
                      sortKey="expected_return"
                      currentSort={sortKey}
                      currentDir={sortDir}
                      onSort={handleSort}
                      className="text-right"
                      tooltip="Expected annualized return over 5 years from Monte Carlo simulation"
                    />
                    <SortHeader
                      label="Sharpe"
                      sortKey="sharpe"
                      currentSort={sortKey}
                      currentDir={sortDir}
                      onSort={handleSort}
                      className="text-right"
                      tooltip="Sharpe ratio: return per unit of risk. Higher = better risk-adjusted returns"
                    />
                    <SortHeader
                      label="P(Loss)"
                      sortKey="prob_loss"
                      currentSort={sortKey}
                      currentDir={sortDir}
                      onSort={handleSort}
                      className="text-right"
                      tooltip="Probability of negative total return over 5 years"
                    />
                    <SortHeader label="Vol" sortKey="volatility" currentSort={sortKey} currentDir={sortDir} onSort={handleSort} className="text-right hidden lg:table-cell" />
                    <SortHeader label="Beta" sortKey="beta" currentSort={sortKey} currentDir={sortDir} onSort={handleSort} className="text-right hidden lg:table-cell" />
                    <th className="py-2 pr-4 text-right hidden sm:table-cell" scope="col">Mkt Cap</th>
                    <th className="py-2 text-right" scope="col">Signal</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((s) => {
                    const signal = signalLabel(s.expected_return, s.sharpe, s.prob_loss);
                    return (
                      <tr
                        key={s.ticker}
                        onClick={() => router.push(`/stock/${s.ticker}`)}
                        className="border-b border-border/50 hover:bg-muted/20 transition-colors cursor-pointer"
                      >
                        <td className="py-2.5 pr-4">
                          <span className="font-semibold">{s.ticker}</span>
                          <span className="text-xs text-muted-foreground ml-2 hidden xl:inline">{s.name}</span>
                        </td>
                        <td className="py-2.5 pr-4 text-muted-foreground hidden md:table-cell text-xs">{s.sector}</td>
                        <td className="py-2.5 pr-4 text-right tabular-nums">${s.current_price.toFixed(2)}</td>
                        <td className={`py-2.5 pr-4 text-right tabular-nums font-medium ${s.expected_return >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                          {s.expected_return >= 0 ? "+" : ""}{s.expected_return.toFixed(1)}%
                        </td>
                        <td className={`py-2.5 pr-4 text-right tabular-nums font-medium ${s.sharpe >= 0.35 ? "text-emerald-400" : s.sharpe >= 0.15 ? "text-amber-400" : "text-red-400"}`}>
                          {s.sharpe.toFixed(2)}
                        </td>
                        <td className={`py-2.5 pr-4 text-right tabular-nums ${s.prob_loss > 40 ? "text-red-400" : s.prob_loss > 25 ? "text-amber-400" : "text-emerald-400"}`}>
                          {s.prob_loss.toFixed(1)}%
                        </td>
                        <td className="py-2.5 pr-4 text-right tabular-nums text-muted-foreground hidden lg:table-cell">
                          {s.volatility.toFixed(1)}%
                        </td>
                        <td className="py-2.5 pr-4 text-right tabular-nums hidden lg:table-cell">
                          {s.beta.toFixed(2)}
                        </td>
                        <td className="py-2.5 pr-4 text-right tabular-nums text-muted-foreground hidden sm:table-cell text-xs">
                          {formatCap(s.market_cap)}
                        </td>
                        <td className={`py-2.5 text-right font-semibold ${signal.color}`}>
                          {signal.text}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground py-8 text-center">
              No stocks found for the selected sector.
            </p>
          )}
        </CardContent>
      </Card>

      {error && <ErrorCard message={(error as Error).message} onRetry={() => refetch()} />}

      <p className="text-xs text-muted-foreground text-center">
        Signal is derived from expected return, Sharpe ratio, and loss probability.
        Not financial advice — for educational purposes only.
      </p>
    </div>
  );
}
