"use client";

import React, { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { getStockScreener } from "@/lib/api";
import type { ScreenerStock } from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorCard } from "@/components/error-card";
import { InfoTooltip } from "@/components/info-tooltip";

type SortKey = "ticker" | "current_price" | "expected_return" | "sharpe" | "prob_loss" | "volatility" | "beta" | "crash_prob_3m" | "signal_confidence" | "rsi_14" | "momentum_percentile";
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

const SIGNAL_COLORS: Record<string, string> = {
  "Strong Buy": "text-emerald-400",
  "Buy": "text-emerald-400",
  "Hold": "text-amber-400",
  "Sell": "text-red-400",
  "Strong Sell": "text-red-400",
};

function signalLabel(stock: ScreenerStock): { text: string; color: string } {
  // Use real signal engine data if available
  if (stock.signal_action) {
    return {
      text: stock.signal_action,
      color: SIGNAL_COLORS[stock.signal_action] ?? "text-amber-400",
    };
  }
  // Fallback heuristic
  const { expected_return: ret, sharpe, prob_loss: probLoss } = stock;
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

const COMPONENT_LABELS: Record<string, string> = {
  crash_prob: "Crash Risk",
  regime: "Regime",
  valuation: "Valuation",
  momentum: "Momentum",
  mean_reversion: "Mean Rev.",
  external: "External",
  macro_risk: "Macro Risk",
  drawdown: "Drawdown",
  economic_surprise: "Econ Surprise",
  momentum_breadth: "Mom. Breadth",
  insider_trading: "Insider",
  vix_term_structure: "VIX Term",
  systemic_risk: "Systemic",
  market_base: "Mkt Base",
  beta_adjustment: "Beta Adj.",
  analyst_target: "Analyst",
  sector_momentum: "Sector Mom.",
  crash_risk: "Crash Risk",
  options: "Options",
  earnings: "Earnings",
  technical: "Technical",
  insider: "Insider",
};

export default function ScreenerPage() {
  const router = useRouter();
  const [sectorFilter, setSectorFilter] = useState("All");
  const [sortKey, setSortKey] = useState<SortKey>("sharpe");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);

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
                {summaryStocks.filter((s) => signalLabel(s).text === "Buy").length}
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
                    <SortHeader
                      label="Crash 3M"
                      sortKey="crash_prob_3m"
                      currentSort={sortKey}
                      currentDir={sortDir}
                      onSort={handleSort}
                      className="text-right hidden lg:table-cell"
                      tooltip="Stock-adjusted 3-month crash probability from ML model"
                    />
                    <SortHeader
                      label="RSI"
                      sortKey="rsi_14"
                      currentSort={sortKey}
                      currentDir={sortDir}
                      onSort={handleSort}
                      className="text-right hidden xl:table-cell"
                      tooltip="14-day RSI: <30 oversold, >70 overbought"
                    />
                    <th className="py-2 pr-4 text-center hidden xl:table-cell" scope="col">Trend</th>
                    <SortHeader
                      label="Mom%"
                      sortKey="momentum_percentile"
                      currentSort={sortKey}
                      currentDir={sortDir}
                      onSort={handleSort}
                      className="text-right hidden xl:table-cell"
                      tooltip="Cross-sectional momentum percentile (vs 150+ stocks)"
                    />
                    <th className="py-2 pr-4 text-center hidden xl:table-cell" scope="col">Liquidity</th>
                    <th className="py-2 pr-4 text-right hidden sm:table-cell" scope="col">Mkt Cap</th>
                    <SortHeader
                      label="Conf"
                      sortKey="signal_confidence"
                      currentSort={sortKey}
                      currentDir={sortDir}
                      onSort={handleSort}
                      className="text-right hidden sm:table-cell"
                      tooltip="Signal confidence: higher = stronger conviction"
                    />
                    <th className="py-2 text-right" scope="col">Signal</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((s) => {
                    const signal = signalLabel(s);
                    const isExpanded = expandedTicker === s.ticker;
                    const colCount = 16; // total columns
                    return (
                      <React.Fragment key={s.ticker}>
                        <tr
                          onClick={(e) => {
                            if (e.detail === 2) {
                              router.push(`/stock/${s.ticker}`);
                            } else {
                              setExpandedTicker(isExpanded ? null : s.ticker);
                            }
                          }}
                          className={`border-b border-border/50 hover:bg-muted/20 transition-colors cursor-pointer ${isExpanded ? "bg-muted/10" : ""}`}
                        >
                          <td className="py-2.5 pr-4">
                            <span className="font-semibold">{s.ticker}</span>
                            <span className="text-xs text-muted-foreground ml-2 hidden xl:inline">{s.name}</span>
                            <span className="text-[10px] text-muted-foreground ml-1">{isExpanded ? "▾" : "▸"}</span>
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
                          <td className={`py-2.5 pr-4 text-right tabular-nums hidden lg:table-cell ${
                            (s.crash_prob_3m ?? 0) > 15 ? "text-red-400" : (s.crash_prob_3m ?? 0) > 8 ? "text-amber-400" : "text-emerald-400"
                          }`}>
                            {s.crash_prob_3m != null ? `${s.crash_prob_3m.toFixed(1)}%` : "--"}
                          </td>
                          <td className={`py-2.5 pr-4 text-right tabular-nums hidden xl:table-cell ${
                            (s.rsi_14 ?? 50) > 70 ? "text-red-400" : (s.rsi_14 ?? 50) < 30 ? "text-emerald-400" : "text-muted-foreground"
                          }`}>
                            {s.rsi_14 != null ? s.rsi_14.toFixed(0) : "--"}
                          </td>
                          <td className={`py-2.5 pr-4 text-center hidden xl:table-cell text-xs font-medium ${
                            s.trend_direction === "bullish" ? "text-emerald-400" : s.trend_direction === "bearish" ? "text-red-400" : "text-muted-foreground"
                          }`}>
                            {s.trend_direction === "bullish" ? "↑" : s.trend_direction === "bearish" ? "↓" : "—"}
                          </td>
                          <td className={`py-2.5 pr-4 text-right tabular-nums hidden xl:table-cell text-xs ${
                            (s.momentum_percentile ?? 50) > 75 ? "text-emerald-400" : (s.momentum_percentile ?? 50) < 25 ? "text-red-400" : "text-muted-foreground"
                          }`}>
                            {s.momentum_percentile != null ? `${s.momentum_percentile.toFixed(0)}` : "--"}
                          </td>
                          <td className={`py-2.5 pr-4 text-center hidden xl:table-cell text-xs ${
                            s.liquidity_tier === "highly_liquid" ? "text-emerald-400" : s.liquidity_tier === "liquid" ? "text-blue-400" : s.liquidity_tier === "moderate" ? "text-amber-400" : "text-muted-foreground"
                          }`}>
                            {s.liquidity_tier ? s.liquidity_tier.replace("_", " ") : "--"}
                          </td>
                          <td className="py-2.5 pr-4 text-right tabular-nums text-muted-foreground hidden sm:table-cell text-xs">
                            {formatCap(s.market_cap)}
                          </td>
                          <td className={`py-2.5 pr-4 text-right tabular-nums hidden sm:table-cell text-xs ${
                            (s.signal_confidence ?? 0) > 40 ? "text-emerald-400" : (s.signal_confidence ?? 0) > 20 ? "text-amber-400" : "text-muted-foreground"
                          }`}>
                            {s.signal_confidence != null ? `${s.signal_confidence}%` : "--"}
                          </td>
                          <td className={`py-2.5 text-right font-semibold ${signal.color}`}>
                            {signal.text}
                          </td>
                        </tr>
                        {/* Expandable Signal Component Breakdown */}
                        {isExpanded && (
                          <tr className="bg-muted/5 border-b border-border/30">
                            <td colSpan={colCount} className="px-4 py-3">
                              <div className="space-y-2">
                                <div className="flex items-center justify-between">
                                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Signal Component Breakdown</p>
                                  <button
                                    onClick={(e) => { e.stopPropagation(); router.push(`/stock/${s.ticker}`); }}
                                    className="text-xs text-primary hover:underline"
                                  >
                                    Full Analysis →
                                  </button>
                                </div>
                                {s.signal_components && Object.keys(s.signal_components).length > 0 ? (
                                  <div className="flex flex-wrap gap-2">
                                    {Object.entries(s.signal_components)
                                      .sort(([, a], [, b]) => Math.abs(b) - Math.abs(a))
                                      .map(([key, val]) => (
                                        <div key={key} className={`rounded-md px-2.5 py-1.5 text-xs ${
                                          val > 0.1 ? "bg-emerald-500/10 text-emerald-400" :
                                          val < -0.1 ? "bg-red-500/10 text-red-400" :
                                          "bg-muted/30 text-muted-foreground"
                                        }`}>
                                          <span className="text-muted-foreground">{COMPONENT_LABELS[key] ?? key}: </span>
                                          <span className="font-bold tabular-nums">{val > 0 ? "+" : ""}{val.toFixed(2)}</span>
                                        </div>
                                      ))}
                                  </div>
                                ) : (
                                  <div className="flex flex-wrap gap-2">
                                    {s.ta_score != null && (
                                      <div className={`rounded-md px-2.5 py-1.5 text-xs ${s.ta_score > 0 ? "bg-emerald-500/10 text-emerald-400" : s.ta_score < 0 ? "bg-red-500/10 text-red-400" : "bg-muted/30 text-muted-foreground"}`}>
                                        <span className="text-muted-foreground">TA: </span><span className="font-bold tabular-nums">{s.ta_score > 0 ? "+" : ""}{s.ta_score.toFixed(2)}</span>
                                      </div>
                                    )}
                                    {s.options_score != null && (
                                      <div className={`rounded-md px-2.5 py-1.5 text-xs ${s.options_score > 0 ? "bg-emerald-500/10 text-emerald-400" : s.options_score < 0 ? "bg-red-500/10 text-red-400" : "bg-muted/30 text-muted-foreground"}`}>
                                        <span className="text-muted-foreground">Options: </span><span className="font-bold tabular-nums">{s.options_score > 0 ? "+" : ""}{s.options_score.toFixed(2)}</span>
                                      </div>
                                    )}
                                    {s.earnings_score != null && (
                                      <div className={`rounded-md px-2.5 py-1.5 text-xs ${s.earnings_score > 0 ? "bg-emerald-500/10 text-emerald-400" : s.earnings_score < 0 ? "bg-red-500/10 text-red-400" : "bg-muted/30 text-muted-foreground"}`}>
                                        <span className="text-muted-foreground">Earnings: </span><span className="font-bold tabular-nums">{s.earnings_score > 0 ? "+" : ""}{s.earnings_score.toFixed(2)}</span>
                                      </div>
                                    )}
                                    {s.insider_score != null && (
                                      <div className={`rounded-md px-2.5 py-1.5 text-xs ${s.insider_score > 0 ? "bg-emerald-500/10 text-emerald-400" : s.insider_score < 0 ? "bg-red-500/10 text-red-400" : "bg-muted/30 text-muted-foreground"}`}>
                                        <span className="text-muted-foreground">Insider: </span><span className="font-bold tabular-nums">{s.insider_score > 0 ? "+" : ""}{s.insider_score.toFixed(2)}</span>
                                      </div>
                                    )}
                                  </div>
                                )}
                                {/* Extra quick stats row */}
                                <div className="flex flex-wrap gap-3 text-xs text-muted-foreground pt-1">
                                  {s.factor_style && <span>Factor: <span className="text-foreground">{s.factor_style}</span></span>}
                                  {s.factor_alpha != null && <span>Alpha: <span className={s.factor_alpha > 0 ? "text-emerald-400" : "text-red-400"}>{s.factor_alpha > 0 ? "+" : ""}{s.factor_alpha.toFixed(1)}%</span></span>}
                                  {s.dividend_yield != null && s.dividend_yield > 0 && <span>Div: <span className="text-foreground">{s.dividend_yield.toFixed(2)}%</span></span>}
                                  {s.pattern_bias && s.pattern_bias !== "neutral" && <span>Patterns: <span className={s.pattern_bias === "bullish" ? "text-emerald-400" : "text-red-400"}>{s.pattern_bias} ({s.pattern_count})</span></span>}
                                  {s.current_drawdown_pct != null && s.current_drawdown_pct < -5 && <span>Drawdown: <span className="text-red-400">{s.current_drawdown_pct.toFixed(1)}%</span></span>}
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
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
        Click a row to expand signal breakdown. Double-click to view full analysis.
        Not financial advice — for educational purposes only.
      </p>
    </div>
  );
}
