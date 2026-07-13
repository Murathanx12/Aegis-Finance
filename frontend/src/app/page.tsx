"use client";

import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { getMarketStatus, getMacroIndicators, getSP500Projection, getSectors, getMarketSignal, getCrossAssetDashboard } from "@/lib/api";
import type { CrossAssetDashboard } from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";
import { MarketBanner } from "@/components/dashboard/market-banner";
import { CrashGauge } from "@/components/dashboard/crash-gauge";
import { SP500Chart } from "@/components/dashboard/sp500-chart";
import { MacroCards } from "@/components/dashboard/macro-cards";
import { SectorHeatmap } from "@/components/dashboard/sector-heatmap";
import { SignalBadge } from "@/components/dashboard/signal-badge";
import { HeroSection } from "@/components/dashboard/hero-section";
import { DailyBriefCard } from "@/components/dashboard/daily-brief-card";
import { ErrorCard } from "@/components/error-card";
import { DisclaimerBanner } from "@/components/disclaimer-banner";
import { InfoTooltip } from "@/components/info-tooltip";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const REFRESH_INTERVAL = 300_000; // 5 minutes

function timeAgo(ts: number): string {
  const diff = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (diff < 10) return "just now";
  if (diff < 60) return `${diff}s ago`;
  const min = Math.floor(diff / 60);
  return `${min}m ${diff % 60}s ago`;
}

export default function DashboardPage() {
  const market = useQuery({
    queryKey: queryKeys.market.status,
    queryFn: getMarketStatus,
    staleTime: staleTimes.market,
    refetchInterval: REFRESH_INTERVAL,
  });
  const macro = useQuery({
    queryKey: queryKeys.market.macro,
    queryFn: getMacroIndicators,
    staleTime: staleTimes.market,
    refetchInterval: REFRESH_INTERVAL,
  });
  const projection = useQuery({
    queryKey: queryKeys.simulation.sp500(10000, 5),
    queryFn: () => getSP500Projection(10000, 5),
    staleTime: staleTimes.simulation,
    refetchInterval: REFRESH_INTERVAL,
  });
  const sectors = useQuery({
    queryKey: queryKeys.sectors,
    queryFn: getSectors,
    staleTime: staleTimes.sectors,
    refetchInterval: REFRESH_INTERVAL,
  });
  const signal = useQuery({
    queryKey: queryKeys.market.signal,
    queryFn: getMarketSignal,
    staleTime: staleTimes.market,
    refetchInterval: REFRESH_INTERVAL,
  });
  const crossAsset = useQuery({
    queryKey: queryKeys.analytics.crossAsset,
    queryFn: getCrossAssetDashboard,
    staleTime: staleTimes.market,
    refetchInterval: REFRESH_INTERVAL,
  });

  // Track last refresh time
  const [lastRefresh, setLastRefresh] = useState(Date.now());
  const [agoText, setAgoText] = useState("just now");

  useEffect(() => {
    if (market.data) setLastRefresh(Date.now());
  }, [market.data]);

  useEffect(() => {
    const id = setInterval(() => setAgoText(timeAgo(lastRefresh)), 10_000);
    return () => clearInterval(id);
  }, [lastRefresh]);

  const anyError = market.error || macro.error || projection.error || sectors.error || signal.error || crossAsset.error;

  return (
    <div className="space-y-6 lg:pt-0 pt-2 animate-slide-up">
      <HeroSection data={market.data ?? null} />

      {/* Auto-refresh indicator */}
      <div className="flex items-center justify-end -mt-3">
        <span className="inline-flex items-center gap-1.5 rounded-md border border-border/50 bg-muted/30 px-2 py-1 text-[11px] text-muted-foreground">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
          </span>
          Auto-refreshes every 5 min
          <span className="text-muted-foreground/60 ml-1">&middot; Updated {agoText}</span>
        </span>
      </div>

      <DisclaimerBanner />

      <DailyBriefCard />

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <SignalBadge data={signal.data ?? null} />
        <div className="lg:col-span-3">
          <MarketBanner data={market.data ?? null} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <CrashGauge data={market.data ?? null} />
        <SP500Chart data={projection.data ?? null} />
      </div>

      <div>
        <h2 className="text-base font-medium text-muted-foreground mb-3">
          Macro Indicators
          <InfoTooltip
            text="Key economic indicators from FRED. Changes shown are 1-month percentage changes. These feed into the 9-factor composite risk score."
            beginnerText="These are the vital signs of the economy — like checking a patient's blood pressure and heart rate. They help gauge whether the economy is healthy or stressed."
          />
        </h2>
        <MacroCards data={macro.data ?? null} />
      </div>

      <SectorHeatmap data={sectors.data ?? null} />

      {/* Cross-Asset Macro Regime Dashboard */}
      {crossAsset.data && (
        <div className="space-y-4">
          <h2 className="text-base font-medium text-muted-foreground">
            Cross-Asset Macro Regime
            <InfoTooltip text="Bloomberg MAC3-style analysis: growth x inflation quadrant, risk-on/off score, cross-asset momentum, and intermarket divergences." />
          </h2>

          {/* Macro Weather + RORO + Regime Row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Macro Regime Quadrant */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">Growth x Inflation Regime</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className={`inline-flex items-center rounded-md px-3 py-1.5 text-sm font-bold ${
                    crossAsset.data.macro_regime.quadrant.includes("Goldilocks") ? "bg-emerald-500/15 text-emerald-400" :
                    crossAsset.data.macro_regime.quadrant.includes("Stagflation") ? "bg-red-500/15 text-red-400" :
                    crossAsset.data.macro_regime.quadrant.includes("Reflation") ? "bg-amber-500/15 text-amber-400" :
                    "bg-blue-500/15 text-blue-400"
                  }`}>
                    {crossAsset.data.macro_regime.quadrant}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">{crossAsset.data.macro_regime.description}</p>
                <div className="grid grid-cols-2 gap-2 pt-1">
                  <div className="rounded-lg bg-muted/30 p-2">
                    <p className="text-[10px] text-muted-foreground uppercase">Growth</p>
                    <p className={`text-sm font-bold tabular-nums ${crossAsset.data.macro_regime.growth_score > 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {crossAsset.data.macro_regime.growth_score > 0 ? "+" : ""}{crossAsset.data.macro_regime.growth_score.toFixed(2)}
                    </p>
                  </div>
                  <div className="rounded-lg bg-muted/30 p-2">
                    <p className="text-[10px] text-muted-foreground uppercase">Inflation</p>
                    <p className={`text-sm font-bold tabular-nums ${crossAsset.data.macro_regime.inflation_score > 0.5 ? "text-red-400" : "text-emerald-400"}`}>
                      {crossAsset.data.macro_regime.inflation_score > 0 ? "+" : ""}{crossAsset.data.macro_regime.inflation_score.toFixed(2)}
                    </p>
                  </div>
                </div>
                {crossAsset.data.macro_regime.favored_assets.length > 0 && (
                  <div className="pt-1">
                    <p className="text-[10px] text-muted-foreground uppercase mb-1">Favored Assets</p>
                    <div className="flex flex-wrap gap-1">
                      {crossAsset.data.macro_regime.favored_assets.map((a) => (
                        <Badge key={a} variant="outline" className="text-[10px] text-emerald-400 border-emerald-400/30">{a}</Badge>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Risk-On/Off Score */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">Risk-On / Risk-Off</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center gap-3">
                  <span className={`text-2xl font-bold tabular-nums ${
                    crossAsset.data.risk_on_off.regime === "risk_on" ? "text-emerald-400" :
                    crossAsset.data.risk_on_off.regime === "risk_off" ? "text-red-400" : "text-muted-foreground"
                  }`}>
                    {crossAsset.data.risk_on_off.score.toFixed(2)}
                  </span>
                  <span className={`inline-flex items-center rounded-md px-2 py-1 text-xs font-bold ${
                    crossAsset.data.risk_on_off.regime === "risk_on" ? "bg-emerald-500/15 text-emerald-400" :
                    crossAsset.data.risk_on_off.regime === "risk_off" ? "bg-red-500/15 text-red-400" :
                    "bg-muted/50 text-muted-foreground"
                  }`}>
                    {crossAsset.data.risk_on_off.regime.replace(/_/g, " ").toUpperCase()}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">{crossAsset.data.risk_on_off.interpretation}</p>
                <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      crossAsset.data.risk_on_off.score > 0 ? "bg-emerald-500" : "bg-red-500"
                    }`}
                    style={{
                      width: `${Math.min(100, Math.abs(crossAsset.data.risk_on_off.score) * 50 + 50)}%`,
                      marginLeft: crossAsset.data.risk_on_off.score < 0 ? `${50 - Math.abs(crossAsset.data.risk_on_off.score) * 50}%` : "0",
                    }}
                  />
                </div>
                <div className="flex justify-between text-[10px] text-muted-foreground">
                  <span>Risk-Off</span>
                  <span>Risk-On</span>
                </div>
              </CardContent>
            </Card>

            {/* Macro Weather Summary */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">Market Weather</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <span className={`inline-flex items-center rounded-md px-3 py-1.5 text-sm font-bold ${
                  crossAsset.data.macro_weather.condition === "sunny" || crossAsset.data.macro_weather.condition === "fair" ? "bg-emerald-500/15 text-emerald-400" :
                  crossAsset.data.macro_weather.condition === "stormy" || crossAsset.data.macro_weather.condition === "crisis" ? "bg-red-500/15 text-red-400" :
                  "bg-amber-500/15 text-amber-400"
                }`}>
                  {crossAsset.data.macro_weather.condition.charAt(0).toUpperCase() + crossAsset.data.macro_weather.condition.slice(1)}
                </span>
                <p className="text-xs text-muted-foreground">{crossAsset.data.macro_weather.summary}</p>
                <div className="grid grid-cols-2 gap-2 pt-1">
                  <div className="rounded-lg bg-muted/30 p-2">
                    <p className="text-[10px] text-muted-foreground uppercase">Breadth</p>
                    <p className="text-sm font-bold tabular-nums">
                      {crossAsset.data.breadth.uptrend_count}/{crossAsset.data.breadth.total_assets}
                    </p>
                    <p className="text-[10px] text-muted-foreground">in uptrend</p>
                  </div>
                  <div className="rounded-lg bg-muted/30 p-2">
                    <p className="text-[10px] text-muted-foreground uppercase">Divergences</p>
                    <p className={`text-sm font-bold tabular-nums ${crossAsset.data.macro_weather.n_divergence_alerts > 0 ? "text-amber-400" : ""}`}>
                      {crossAsset.data.macro_weather.n_divergence_alerts}
                    </p>
                    <p className="text-[10px] text-muted-foreground">alerts</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Intermarket Divergence Alerts */}
          {crossAsset.data.intermarket_divergences.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
                  Intermarket Divergence Alerts
                  <InfoTooltip text="Unusual cross-asset divergences that may signal regime transitions or mispricings." />
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {crossAsset.data.intermarket_divergences.map((d, i) => (
                    <div key={i} className={`flex items-start gap-2 rounded-lg p-2 ${
                      d.severity === "high" ? "bg-red-500/5" : d.severity === "medium" ? "bg-amber-500/5" : "bg-muted/20"
                    }`}>
                      <span className={`mt-0.5 h-2 w-2 rounded-full shrink-0 ${
                        d.severity === "high" ? "bg-red-400" : d.severity === "medium" ? "bg-amber-400" : "bg-muted-foreground"
                      }`} />
                      <div>
                        <p className="text-xs font-medium">{d.type}</p>
                        <p className="text-xs text-muted-foreground">{d.message}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Cross-Asset Momentum Table (top 10) */}
          {crossAsset.data.momentum_table.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
                  Cross-Asset Momentum
                  <InfoTooltip text="Multi-timeframe relative strength across equities, bonds, commodities, and currencies. Above SMA200 indicates uptrend." />
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-border text-left text-muted-foreground">
                        <th className="py-1.5 pr-3">Asset</th>
                        <th className="py-1.5 pr-3">Class</th>
                        <th className="py-1.5 pr-3 text-right">1W</th>
                        <th className="py-1.5 pr-3 text-right">1M</th>
                        <th className="py-1.5 pr-3 text-right">3M</th>
                        <th className="py-1.5 pr-3 text-right">6M</th>
                        <th className="py-1.5 text-center">Trend</th>
                      </tr>
                    </thead>
                    <tbody>
                      {crossAsset.data.momentum_table.slice(0, 12).map((row) => (
                        <tr key={row.ticker} className="border-b border-border/30 hover:bg-muted/20 transition-colors">
                          <td className="py-1.5 pr-3 font-medium">{row.name || row.ticker}</td>
                          <td className="py-1.5 pr-3 text-muted-foreground">{row.subclass || row.asset_class}</td>
                          <td className={`py-1.5 pr-3 text-right tabular-nums ${row.return_1w != null ? (row.return_1w >= 0 ? "text-emerald-400" : "text-red-400") : ""}`}>
                            {row.return_1w != null ? `${row.return_1w >= 0 ? "+" : ""}${row.return_1w.toFixed(1)}%` : "-"}
                          </td>
                          <td className={`py-1.5 pr-3 text-right tabular-nums ${row.return_1m != null ? (row.return_1m >= 0 ? "text-emerald-400" : "text-red-400") : ""}`}>
                            {row.return_1m != null ? `${row.return_1m >= 0 ? "+" : ""}${row.return_1m.toFixed(1)}%` : "-"}
                          </td>
                          <td className={`py-1.5 pr-3 text-right tabular-nums ${row.return_3m != null ? (row.return_3m >= 0 ? "text-emerald-400" : "text-red-400") : ""}`}>
                            {row.return_3m != null ? `${row.return_3m >= 0 ? "+" : ""}${row.return_3m.toFixed(1)}%` : "-"}
                          </td>
                          <td className={`py-1.5 pr-3 text-right tabular-nums ${row.return_6m != null ? (row.return_6m >= 0 ? "text-emerald-400" : "text-red-400") : ""}`}>
                            {row.return_6m != null ? `${row.return_6m >= 0 ? "+" : ""}${row.return_6m.toFixed(1)}%` : "-"}
                          </td>
                          <td className="py-1.5 text-center">
                            <span className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${
                              row.above_sma200 ? "bg-emerald-500/15 text-emerald-400" : "bg-red-500/15 text-red-400"
                            }`}>
                              {row.above_sma200 ? "U" : "D"}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {anyError && (
        <ErrorCard
          message={
            (market.error as Error)?.message ||
            (projection.error as Error)?.message ||
            (macro.error as Error)?.message ||
            (sectors.error as Error)?.message ||
            (signal.error as Error)?.message ||
            (crossAsset.error as Error)?.message ||
            "Unknown error"
          }
          onRetry={() => {
            market.refetch();
            macro.refetch();
            projection.refetch();
            sectors.refetch();
            signal.refetch();
            crossAsset.refetch();
          }}
        />
      )}
    </div>
  );
}
