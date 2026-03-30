"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useApi } from "@/hooks/use-api";
import {
  getCrashPrediction, getTickerCrash,
  getSP500Projection, getScenarios,
} from "@/lib/api";
import type { TickerCrash, SP500Projection } from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { InfoTooltip } from "@/components/info-tooltip";
import { ErrorCard } from "@/components/error-card";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine,
  AreaChart, Area,
} from "recharts";

/* ── Crash Gauge ─────────────────────────────────────────────── */

function CrashGauge({ value, label }: { value: number; label: string }) {
  const pct = Math.min(value / 100, 1);
  const color =
    pct > 0.5 ? "text-red-500" : pct > 0.3 ? "text-amber-500" : pct > 0.15 ? "text-yellow-500" : "text-emerald-500";
  const radius = 70;
  const circumference = Math.PI * radius;
  const offset = circumference * (1 - pct);

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 160 90" className="w-40 h-22" role="img" aria-label={`${label} crash probability: ${value.toFixed(1)}%`}>
        <path d="M 10 80 A 70 70 0 0 1 150 80" fill="none" stroke="currentColor" strokeWidth="12" className="text-muted/20" />
        <path d="M 10 80 A 70 70 0 0 1 150 80" fill="none" stroke="currentColor" strokeWidth="12"
          strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round" className={color} />
      </svg>
      <p className={`-mt-3 text-3xl font-bold tabular-nums ${color}`}>{value.toFixed(1)}%</p>
      <p className="mt-1 text-sm text-muted-foreground uppercase tracking-wide">{label}</p>
    </div>
  );
}

/* ── SHAP Chart ──────────────────────────────────────────────── */

function ShapChart({ features }: { features: { feature: string; shap_value: number; feature_value: number | null }[] }) {
  const data = features.map((f) => ({
    name: f.feature.replace(/_/g, " ").replace(/fred /g, ""),
    value: f.shap_value,
  }));

  return (
    <ResponsiveContainer width="100%" height={Math.max(220, data.length * 28)}>
      <BarChart data={data} layout="vertical" margin={{ left: 120, right: 20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis type="number" tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
        <YAxis type="category" dataKey="name" tick={{ fill: "var(--foreground)", fontSize: 12 }} width={110} />
        <Tooltip
          contentStyle={{ backgroundColor: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--foreground)" }}
          formatter={(v) => [Number(v).toFixed(4), "SHAP"]}
        />
        <ReferenceLine x={0} stroke="var(--muted-foreground)" />
        <Bar dataKey="value" radius={[0, 4, 4, 0]}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.value > 0 ? "#ef4444" : "#22c55e"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ── Projection Fan Chart ────────────────────────────────────── */

function ProjectionChart({ data }: { data: SP500Projection }) {
  const { percentile_paths } = data;
  const p5 = percentile_paths.p5 || [];
  const p25 = percentile_paths.p25 || [];
  const p50 = percentile_paths.p50 || [];
  const p75 = percentile_paths.p75 || [];
  const p95 = percentile_paths.p95 || [];

  const chartData = p50.map((_, i) => ({
    year: ((i * 5) / 252).toFixed(1),
    p5: Math.round(p5[i] || 0),
    p25: Math.round(p25[i] || 0),
    p50: Math.round(p50[i] || 0),
    p75: Math.round(p75[i] || 0),
    p95: Math.round(p95[i] || 0),
  }));

  return (
    <ResponsiveContainer width="100%" height={350}>
      <AreaChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="year" tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
          label={{ value: "Years", position: "bottom", fill: "var(--muted-foreground)", fontSize: 11, offset: -5 }} />
        <YAxis tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
          tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : `${v}`} />
        <Tooltip
          contentStyle={{ backgroundColor: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--foreground)" }}
          labelFormatter={(v) => `Year ${v}`}
          formatter={(v) => [`$${Number(v).toLocaleString()}`, ""]}
        />
        <Area type="monotone" dataKey="p95" stackId="band" stroke="none" fill="rgba(99,180,255,0.06)" name="95th" />
        <Area type="monotone" dataKey="p75" stackId="band2" stroke="none" fill="rgba(99,180,255,0.10)" name="75th" />
        <Area type="monotone" dataKey="p50" stroke="#3b82f6" strokeWidth={2} fill="rgba(99,180,255,0.12)" name="Median" />
        <Area type="monotone" dataKey="p25" stackId="band3" stroke="none" fill="rgba(99,180,255,0.10)" name="25th" />
        <Area type="monotone" dataKey="p5" stackId="band4" stroke="none" fill="rgba(99,180,255,0.06)" name="5th" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/* ── Scenario Table ──────────────────────────────────────────── */

function ScenarioTable({ scenarios }: { scenarios: { name: string; weight: number; median_return: number; p05_return: number; p95_return: number; prob_loss: number; description?: string }[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" aria-label="Scenario breakdown table">
        <thead>
          <tr className="border-b border-border text-left text-muted-foreground">
            <th className="py-2 pr-4" scope="col">Scenario</th>
            <th className="py-2 pr-4 text-right" scope="col">Weight</th>
            <th className="py-2 pr-4 text-right" scope="col">Median Return</th>
            <th className="py-2 pr-4 text-right hidden sm:table-cell" scope="col">Range (5-95th)</th>
            <th className="py-2 text-right" scope="col">P(Loss)</th>
          </tr>
        </thead>
        <tbody>
          {scenarios.map((sc) => (
            <tr key={sc.name} className="border-b border-border/50 hover:bg-muted/20 transition-colors">
              <td className="py-2.5 pr-4">
                <span className="font-medium">{sc.name}</span>
                {sc.description && <p className="text-xs text-muted-foreground mt-0.5">{sc.description}</p>}
              </td>
              <td className="py-2.5 pr-4 text-right tabular-nums">{(sc.weight * 100).toFixed(0)}%</td>
              <td className={`py-2.5 pr-4 text-right tabular-nums font-semibold ${sc.median_return >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                {sc.median_return >= 0 ? "+" : ""}{sc.median_return}%
              </td>
              <td className="py-2.5 pr-4 text-right tabular-nums text-muted-foreground hidden sm:table-cell">
                {sc.p05_return}% to {sc.p95_return >= 0 ? "+" : ""}{sc.p95_return}%
              </td>
              <td className="py-2.5 text-right tabular-nums">{sc.prob_loss}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Ticker Crash Card ───────────────────────────────────────── */

function TickerCrashCard() {
  const [ticker, setTicker] = useState("");
  const [submitted, setSubmitted] = useState("");
  const { data, loading, error } = useApi<TickerCrash>(
    () => submitted ? getTickerCrash(submitted) : Promise.resolve(null as unknown as TickerCrash),
    [submitted]
  );

  const riskColors: Record<string, string> = {
    high: "bg-red-500/15 text-red-400 border-red-500/30",
    elevated: "bg-amber-500/15 text-amber-400 border-amber-500/30",
    normal: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-medium text-muted-foreground flex items-center">
          Per-Ticker Crash Risk
          <InfoTooltip text="Beta-adjusted crash probability for individual stocks. Higher beta = higher crash risk relative to the market." />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={(e) => { e.preventDefault(); setSubmitted(ticker.toUpperCase()); }} className="flex gap-2">
          <label htmlFor="ticker-crash-input" className="sr-only">Stock ticker</label>
          <input
            id="ticker-crash-input"
            type="text"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            placeholder="Enter ticker (e.g. NVDA)"
            className="flex-1 rounded-md border border-border bg-background px-4 py-3 text-base placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <Button type="submit" disabled={!ticker.trim()}>Analyze</Button>
        </form>

        {loading && submitted && <Skeleton className="h-24 w-full" />}
        {error && <p className="text-sm text-red-500" role="alert">{error}</p>}

        {data && !loading && (
          <div className="space-y-3 animate-fade-in">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold text-base">{data.name}</p>
                <p className="text-sm text-muted-foreground">${data.current_price?.toFixed(2)} | Beta: {data.beta?.toFixed(2)}</p>
              </div>
              <Badge variant="outline" className={riskColors[data.risk_level] || riskColors.normal}>
                {data.risk_level}
              </Badge>
            </div>
            <div className="grid grid-cols-3 gap-3">
              {Object.entries(data.ticker_crash_probs || {})
                .sort(([a], [b]) => {
                  const ORDER: Record<string, number> = { "3m": 0, "6m": 1, "12m": 2 };
                  return (ORDER[a] ?? 99) - (ORDER[b] ?? 99);
                })
                .map(([h, prob]) => (
                <div key={h} className="text-center rounded-lg bg-muted/30 p-2">
                  <p className="text-xs text-muted-foreground uppercase">{h}</p>
                  <p className={`text-lg font-bold tabular-nums ${prob > 30 ? "text-red-500" : prob > 20 ? "text-amber-500" : "text-emerald-500"}`}>
                    {prob}%
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ── Main Page ───────────────────────────────────────────────── */

export default function OutlookPage() {
  const crashQuery = useQuery({
    queryKey: queryKeys.crash.prediction("3m", true),
    queryFn: () => getCrashPrediction("3m", true),
    staleTime: staleTimes.crash,
  });
  const projQuery = useQuery({
    queryKey: queryKeys.simulation.sp500(10000, 5),
    queryFn: () => getSP500Projection(10000, 5),
    staleTime: staleTimes.simulation,
  });
  const scenQuery = useQuery({
    queryKey: queryKeys.simulation.scenarios,
    queryFn: getScenarios,
    staleTime: staleTimes.simulation,
  });

  const crash = crashQuery.data;
  const proj = projQuery.data;

  return (
    <div className="space-y-8 animate-slide-up">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Market Outlook</h1>
        <p className="text-base text-muted-foreground mt-1">
          Crash probability, Monte Carlo simulation, and scenario analysis — all in one view
        </p>
      </div>

      {crash?.status === "model_not_trained" && (
        <Card className="border-amber-500/30 bg-amber-500/10">
          <CardContent className="p-4 text-sm text-amber-400">
            Crash model not yet trained. Run: <code className="bg-amber-100 px-1.5 py-0.5 rounded">python -m engine.training.train_crash_model</code>
          </CardContent>
        </Card>
      )}

      {/* ── Row 1: Crash Gauges + S&P 500 Fan Chart ─────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <Card className="xl:col-span-1">
          <CardHeader>
            <CardTitle className="text-base font-medium text-muted-foreground flex items-center">
              Crash Probability
              <InfoTooltip text="Probability of S&P 500 experiencing a 20%+ drawdown within each time horizon." />
            </CardTitle>
          </CardHeader>
          <CardContent>
            {crashQuery.isLoading ? (
              <div className="flex flex-col items-center gap-6">
                <Skeleton className="h-28 w-40" />
                <Skeleton className="h-28 w-40" />
                <Skeleton className="h-28 w-40" />
              </div>
            ) : crash?.probabilities ? (
              <div className="flex flex-col items-center gap-4">
                {Object.entries(crash.probabilities)
                  .sort(([a], [b]) => {
                    const ORDER: Record<string, number> = { "3m": 0, "6m": 1, "12m": 2 };
                    return (ORDER[a] ?? 99) - (ORDER[b] ?? 99);
                  })
                  .map(([h, prob]) => (
                    <CrashGauge key={h} value={prob} label={h} />
                  ))}
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle className="text-base font-medium text-muted-foreground flex items-center">
              S&P 500 — 5-Year Projection
              <InfoTooltip text="Fan chart from 10,000 Monte Carlo simulations with jump-diffusion, scenario weighting, and GARCH volatility." />
            </CardTitle>
            {proj && (
              <p className="text-xs text-muted-foreground">
                Start: ${proj.start_price.toLocaleString(undefined, { maximumFractionDigits: 0 })} |
                Median: ${proj.median_final.toLocaleString(undefined, { maximumFractionDigits: 0 })} |
                Range: ${proj.p05_final.toLocaleString(undefined, { maximumFractionDigits: 0 })} – ${proj.p95_final.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </p>
            )}
          </CardHeader>
          <CardContent>
            {projQuery.isLoading ? (
              <Skeleton className="h-[350px] w-full" />
            ) : proj ? (
              <ProjectionChart data={proj} />
            ) : null}
          </CardContent>
        </Card>
      </div>

      {/* ── Row 2: Key Metrics ───────────────────────────────── */}
      {proj && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground uppercase font-medium">Median 5Y Return</p>
              <p className={`text-2xl font-bold tabular-nums mt-1 ${proj.median_total_return >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                {proj.median_total_return >= 0 ? "+" : ""}{proj.median_total_return}%
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground uppercase font-medium">Annual Return</p>
              <p className="text-2xl font-bold tabular-nums mt-1">{proj.median_annual_return}%</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground uppercase font-medium">P(Loss) 5Y</p>
              <p className="text-2xl font-bold tabular-nums mt-1 text-amber-400">{proj.prob_loss}%</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground uppercase font-medium">95th Percentile</p>
              <p className="text-2xl font-bold tabular-nums mt-1">
                ${proj.p95_final?.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── Row 3: Scenarios + SHAP ──────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-medium text-muted-foreground flex items-center">
              Scenario Breakdown
              <InfoTooltip text="Each scenario runs independent Monte Carlo simulations. Weights are dynamically adjusted based on ML crash probability, VIX, and yield curve." />
            </CardTitle>
          </CardHeader>
          <CardContent>
            {scenQuery.isLoading ? (
              <Skeleton className="h-64 w-full" />
            ) : scenQuery.data?.scenarios ? (
              <ScenarioTable scenarios={scenQuery.data.scenarios} />
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base font-medium text-muted-foreground flex items-center">
              SHAP Feature Importance (3M)
              <InfoTooltip text="SHAP values show how much each feature pushes crash probability up (red) or down (green)." />
            </CardTitle>
          </CardHeader>
          <CardContent>
            {crashQuery.isLoading ? (
              <Skeleton className="h-64 w-full" />
            ) : crash?.explanation?.top_features ? (
              <ShapChart features={crash.explanation.top_features} />
            ) : (
              <p className="text-sm text-muted-foreground text-center py-8">
                Train the crash model to see feature importance.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Row 4: Per-Ticker + Validation ────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <TickerCrashCard />

        {crash?.external_validation && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base font-medium text-muted-foreground flex items-center">
                External Consensus
                <InfoTooltip text="Cross-checks our model against LEI, SLOOS, Fed Funds, and Consumer Sentiment." />
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm">Direction</span>
                <Badge variant="outline" className={
                  crash.external_validation.consensus_direction === "BEARISH"
                    ? "bg-red-500/15 text-red-400 border-red-500/30"
                    : crash.external_validation.consensus_direction === "BULLISH"
                      ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                      : "bg-blue-500/15 text-blue-400 border-blue-500/30"
                }>
                  {crash.external_validation.consensus_direction}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm">Engine Agreement</span>
                <span className={`text-lg font-bold tabular-nums ${crash.external_validation.engine_agreement > 60 ? "text-emerald-400" : crash.external_validation.engine_agreement > 40 ? "text-amber-400" : "text-red-400"}`}>
                  {crash.external_validation.engine_agreement}%
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                {Object.entries(crash.external_validation.signals).map(([key, val]) => (
                  <div key={key} className="flex justify-between rounded bg-muted/50 px-2 py-1.5">
                    <span className="text-muted-foreground uppercase">{key}</span>
                    <span className="font-medium">{val}</span>
                  </div>
                ))}
              </div>
              {crash.external_validation.divergence_alerts.length > 0 && (
                <div className="space-y-1 mt-2">
                  {crash.external_validation.divergence_alerts.map((alert, i) => (
                    <p key={i} className="text-xs text-amber-400 bg-amber-500/10 rounded px-2 py-1" role="alert">
                      {alert}
                    </p>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {crash?.regime_validation && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base font-medium text-muted-foreground flex items-center">
                Regime Confirmation
                <InfoTooltip text="Multi-check validation: 200-day SMA, breadth, and institutional consensus." />
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm">Current Regime</span>
                <Badge variant="outline">{crash.regime_validation.regime}</Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm">Status</span>
                <Badge variant="outline" className={
                  crash.regime_validation.confirmed
                    ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                    : "bg-amber-500/15 text-amber-400 border-amber-500/30"
                }>
                  {crash.regime_validation.confirmed ? "CONFIRMED" : "UNCONFIRMED"} ({crash.regime_validation.confidence})
                </Badge>
              </div>
              <div className="space-y-1.5">
                {Object.entries(crash.regime_validation.checks).map(([check, passed]) => (
                  <div key={check} className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground capitalize">{check.replace(/_/g, " ")}</span>
                    <span className={passed ? "text-emerald-400" : "text-red-400"}>
                      {passed ? "Pass" : "Fail"}
                    </span>
                  </div>
                ))}
              </div>
              {crash.regime_validation.notes.length > 0 && (
                <div className="space-y-1 mt-2">
                  {crash.regime_validation.notes.slice(0, 3).map((note, i) => (
                    <p key={i} className="text-xs text-muted-foreground bg-muted/30 rounded px-2 py-1">{note}</p>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {(crashQuery.error || projQuery.error || scenQuery.error) && (
        <ErrorCard
          message={(crashQuery.error as Error)?.message || (projQuery.error as Error)?.message || (scenQuery.error as Error)?.message || "Unknown error"}
          onRetry={() => { crashQuery.refetch(); projQuery.refetch(); scenQuery.refetch(); }}
        />
      )}
    </div>
  );
}
