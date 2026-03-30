"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useApi } from "@/hooks/use-api";
import {
  getCrashPrediction, getTickerCrash,
} from "@/lib/api";
import type { TickerCrash } from "@/lib/api";
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

/* ── SHAP Waterfall Chart ──────────────────────────────────────── */

function ShapChart({ features }: { features: { feature: string; shap_value: number; feature_value: number | null }[] }) {
  const data = features.map((f) => ({
    name: f.feature.replace(/_/g, " ").replace(/fred /g, ""),
    value: f.shap_value,
    featureValue: f.feature_value,
  }));

  return (
    <ResponsiveContainer width="100%" height={Math.max(300, data.length * 30)}>
      <BarChart data={data} layout="vertical" margin={{ left: 140, right: 30 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis type="number" tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
        <YAxis type="category" dataKey="name" tick={{ fill: "var(--foreground)", fontSize: 12 }} width={130} />
        <Tooltip
          contentStyle={{ backgroundColor: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--foreground)" }}
          formatter={(v, _, entry) => {
            const val = Number(v);
            const fv = (entry as { payload?: { featureValue?: number | null } })?.payload?.featureValue ?? null;
            return [
              `SHAP: ${val.toFixed(4)}${fv !== null ? ` | Value: ${fv.toFixed(3)}` : ""}`,
              "",
            ];
          }}
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
          <InfoTooltip text="Beta-adjusted crash probability for individual stocks. Higher beta amplifies market crash risk." />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={(e) => { e.preventDefault(); setSubmitted(ticker.toUpperCase()); }} className="flex gap-2">
          <label htmlFor="ticker-crash" className="sr-only">Stock ticker</label>
          <input
            id="ticker-crash"
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

            <div className="text-xs text-muted-foreground mb-2">Market-level crash probabilities</div>
            <div className="grid grid-cols-3 gap-3">
              {Object.entries(data.market_crash_probs || {})
                .sort(([a], [b]) => {
                  const ORDER: Record<string, number> = { "3m": 0, "6m": 1, "12m": 2 };
                  return (ORDER[a] ?? 99) - (ORDER[b] ?? 99);
                })
                .map(([h, prob]) => (
                <div key={`mkt-${h}`} className="text-center rounded-lg bg-muted/20 p-2">
                  <p className="text-[10px] text-muted-foreground uppercase">Mkt {h}</p>
                  <p className="text-sm font-semibold tabular-nums">{prob}%</p>
                </div>
              ))}
            </div>

            <div className="text-xs text-muted-foreground mb-2">Ticker-adjusted crash probabilities</div>
            <div className="grid grid-cols-3 gap-3">
              {Object.entries(data.ticker_crash_probs || {})
                .sort(([a], [b]) => {
                  const ORDER: Record<string, number> = { "3m": 0, "6m": 1, "12m": 2 };
                  return (ORDER[a] ?? 99) - (ORDER[b] ?? 99);
                })
                .map(([h, prob]) => (
                <div key={`tkr-${h}`} className="text-center rounded-lg bg-muted/30 p-2">
                  <p className="text-[10px] text-muted-foreground uppercase">{h}</p>
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

export default function CrashPage() {
  const [horizon, setHorizon] = useState("3m");
  const crashQuery = useQuery({
    queryKey: queryKeys.crash.prediction(horizon, true),
    queryFn: () => getCrashPrediction(horizon, true),
    staleTime: staleTimes.crash,
  });

  const crash = crashQuery.data;

  return (
    <div className="space-y-8 animate-slide-up">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Crash Analysis</h1>
        <p className="text-base text-muted-foreground mt-1">
          ML crash probability, SHAP explainability, external validation, and per-ticker risk
        </p>
      </div>

      <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-2.5 text-xs text-amber-400/80">
        Educational tool only. Crash probabilities are model estimates, not guarantees. Not financial advice.
      </div>

      {crash?.status === "model_not_trained" && (
        <Card className="border-amber-500/30 bg-amber-500/10">
          <CardContent className="p-4 text-sm text-amber-400">
            Crash model not yet trained. Run: <code className="bg-amber-100 dark:bg-amber-900/30 px-1.5 py-0.5 rounded text-xs">python -m engine.training.train_crash_model</code>
          </CardContent>
        </Card>
      )}

      {/* Horizon Selector */}
      <div className="flex gap-1 rounded-lg bg-muted/50 p-1 w-fit">
        {["3m", "6m", "12m"].map((h) => (
          <button
            key={h}
            onClick={() => setHorizon(h)}
            className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              horizon === h
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {h}
          </button>
        ))}
      </div>

      {/* ── Row 1: Crash Gauges ──────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-medium text-muted-foreground flex items-center">
            Crash Probability (20%+ Drawdown)
            <InfoTooltip text="Probability of S&P 500 experiencing a 20%+ drawdown within each time horizon. Model: 70% LightGBM + 30% Logistic Regression with isotonic calibration." />
          </CardTitle>
        </CardHeader>
        <CardContent>
          {crashQuery.isLoading ? (
            <div className="flex justify-center gap-8">
              <Skeleton className="h-28 w-40" />
              <Skeleton className="h-28 w-40" />
              <Skeleton className="h-28 w-40" />
            </div>
          ) : crash?.probabilities ? (
            <div className="flex flex-wrap justify-center gap-8">
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

      {/* ── Row 2: SHAP Explanation ───────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-medium text-muted-foreground flex items-center">
              SHAP Feature Importance ({horizon})
              <InfoTooltip text="SHAP values decompose the prediction into per-feature contributions. Red bars push crash probability UP, green bars push it DOWN. Larger bars = more influence." />
            </CardTitle>
          </CardHeader>
          <CardContent>
            {crashQuery.isLoading ? (
              <Skeleton className="h-[350px] w-full" />
            ) : crash?.explanation?.top_features ? (
              <ShapChart features={crash.explanation.top_features} />
            ) : (
              <p className="text-sm text-muted-foreground text-center py-8">
                Train the crash model to see feature importance.
              </p>
            )}
          </CardContent>
        </Card>

        {/* External Validation + Regime */}
        <div className="space-y-6">
          {crash?.external_validation && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base font-medium text-muted-foreground flex items-center">
                  External Validation
                  <InfoTooltip text="Cross-checks our ML model against independent economic indicators: Leading Economic Index (LEI), Senior Loan Officer Survey (SLOOS), Fed Funds rate, and consumer sentiment." />
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm">Consensus Direction</span>
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
                  <InfoTooltip text="Multi-check validation using 200-day SMA, market breadth, and institutional consensus to confirm or challenge the detected regime." />
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
      </div>

      {/* ── Row 3: Per-Ticker Crash ──────────────────────────── */}
      <TickerCrashCard />

      {crashQuery.error && (
        <ErrorCard
          message={(crashQuery.error as Error)?.message || "Unknown error"}
          onRetry={() => crashQuery.refetch()}
        />
      )}
    </div>
  );
}
