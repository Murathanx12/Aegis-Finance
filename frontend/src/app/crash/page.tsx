"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useApi } from "@/hooks/use-api";
import { getCrashPrediction, getTickerCrash } from "@/lib/api";
import type { TickerCrash } from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { InfoTooltip } from "@/components/info-tooltip";
import { ErrorCard } from "@/components/error-card";
import { DisclaimerBanner } from "@/components/disclaimer-banner";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine,
} from "recharts";

function CrashGaugeLarge({ value, label }: { value: number; label: string }) {
  const pct = Math.min(value / 100, 1);
  const color =
    pct > 0.5 ? "text-red-500" : pct > 0.3 ? "text-amber-500" : pct > 0.15 ? "text-yellow-500" : "text-emerald-500";
  const radius = 70;
  const circumference = Math.PI * radius;
  const offset = circumference * (1 - pct);

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 160 90" className="w-44 h-24" role="img" aria-label={`${label} crash probability: ${value.toFixed(1)}%`}>
        <path d="M 10 80 A 70 70 0 0 1 150 80" fill="none" stroke="currentColor" strokeWidth="12" className="text-muted/20" />
        <path d="M 10 80 A 70 70 0 0 1 150 80" fill="none" stroke="currentColor" strokeWidth="12"
          strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round" className={color} />
      </svg>
      <p className={`-mt-3 text-4xl font-bold tabular-nums ${color}`}>{value.toFixed(1)}%</p>
      <p className="mt-1 text-sm text-muted-foreground uppercase tracking-wide">{label}</p>
    </div>
  );
}

function ShapChart({ features }: { features: { feature: string; shap_value: number; feature_value: number | null }[] }) {
  const data = features.map((f) => ({
    name: f.feature.replace(/_/g, " ").replace(/fred /g, ""),
    value: f.shap_value,
    raw: f.feature_value,
  }));

  return (
    <ResponsiveContainer width="100%" height={Math.max(250, data.length * 30)}>
      <BarChart data={data} layout="vertical" margin={{ left: 120, right: 20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
        <XAxis type="number" tick={{ fill: "#888", fontSize: 11 }} />
        <YAxis type="category" dataKey="name" tick={{ fill: "#aaa", fontSize: 11 }} width={110} />
        <Tooltip
          contentStyle={{ backgroundColor: "#1e1e2e", border: "1px solid #333", borderRadius: 8 }}
          formatter={(v) => [Number(v).toFixed(4), "SHAP"]}
        />
        <ReferenceLine x={0} stroke="#555" />
        <Bar dataKey="value" radius={[0, 4, 4, 0]}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.value > 0 ? "#ef4444" : "#22c55e"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

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
        <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
          Per-Ticker Crash Risk
          <InfoTooltip text="Beta-adjusted crash probability for individual stocks. Higher beta = higher crash risk relative to the market. Based on market crash model + stock-specific beta." />
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
            placeholder="Enter ticker (e.g. AAPL)"
            className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <Button type="submit" size="sm" disabled={!ticker.trim()}>Analyze</Button>
        </form>

        {loading && submitted && <Skeleton className="h-24 w-full" />}
        {error && <p className="text-sm text-red-400" role="alert">{error}</p>}

        {data && !loading && (
          <div className="space-y-3 animate-fade-in">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold">{data.name}</p>
                <p className="text-sm text-muted-foreground">${data.current_price?.toFixed(2)} | Beta: {data.beta?.toFixed(2)}</p>
              </div>
              <Badge variant="outline" className={riskColors[data.risk_level] || riskColors.normal}>
                {data.risk_level}
              </Badge>
            </div>
            <div className="grid grid-cols-3 gap-3">
              {Object.entries(data.ticker_crash_probs || {}).map(([h, prob]) => (
                <div key={h} className="text-center rounded-lg bg-muted/30 p-2">
                  <p className="text-xs text-muted-foreground uppercase">{h}</p>
                  <p className={`text-lg font-bold tabular-nums ${prob > 30 ? "text-red-400" : prob > 20 ? "text-amber-400" : "text-emerald-400"}`}>
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

export default function CrashPage() {
  const { data, isLoading: loading, error, refetch } = useQuery({
    queryKey: queryKeys.crash.prediction("3m", true),
    queryFn: () => getCrashPrediction("3m", true),
    staleTime: staleTimes.crash,
  });

  return (
    <div className="space-y-6 animate-slide-up">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Crash Prediction</h1>
        <p className="text-sm text-muted-foreground">
          Multi-horizon crash probability from LightGBM + Logistic Regression ensemble
        </p>
      </div>

      <DisclaimerBanner />

      {data?.status === "model_not_trained" && (
        <Card className="border-amber-500/30 bg-amber-500/5">
          <CardContent className="p-4 text-sm text-amber-400">
            Crash model not yet trained. Run: <code className="bg-amber-500/10 px-1.5 py-0.5 rounded">python -m engine.training.train_crash_model</code>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
            Market Crash Probability
            <InfoTooltip text="Probability of the S&P 500 experiencing a 20%+ drawdown within each time horizon. The model uses 25-30 features including yield curve, VIX, credit spreads, and leading indicators." />
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center gap-12">
              <Skeleton className="h-32 w-44" />
              <Skeleton className="h-32 w-44" />
              <Skeleton className="h-32 w-44" />
            </div>
          ) : data?.probabilities ? (
            <div className="flex flex-wrap justify-center gap-10">
              {Object.entries(data.probabilities)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([h, prob]) => (
                  <CrashGaugeLarge key={h} value={prob} label={h} />
                ))}
            </div>
          ) : null}
          {data?.last_updated && (
            <p className="mt-4 text-center text-xs text-muted-foreground">Data as of {data.last_updated}</p>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
              SHAP Feature Importance (3M Horizon)
              <InfoTooltip text="SHAP values show how much each feature pushes the crash probability up (red) or down (green). Features are sorted by absolute impact." />
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-64 w-full" />
            ) : data?.explanation?.top_features ? (
              <ShapChart features={data.explanation.top_features} />
            ) : (
              <p className="text-sm text-muted-foreground text-center py-8">
                SHAP explanation unavailable. Train the model first.
              </p>
            )}
          </CardContent>
        </Card>

        <TickerCrashCard />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {data?.external_validation && (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
                External Consensus
                <InfoTooltip text="Cross-checks our crash model against independent economic indicators: Leading Economic Index (LEI), Senior Loan Officer Survey (SLOOS), Fed Funds rate trajectory, and Consumer Sentiment." />
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm">Consensus Direction</span>
                <Badge variant="outline" className={
                  data.external_validation.consensus_direction === "BEARISH"
                    ? "bg-red-500/15 text-red-400 border-red-500/30"
                    : data.external_validation.consensus_direction === "BULLISH"
                      ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                      : "bg-blue-500/15 text-blue-400 border-blue-500/30"
                }>
                  {data.external_validation.consensus_direction}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm">Engine Agreement</span>
                <span className={`text-lg font-bold tabular-nums ${data.external_validation.engine_agreement > 60 ? "text-emerald-400" : data.external_validation.engine_agreement > 40 ? "text-amber-400" : "text-red-400"}`}>
                  {data.external_validation.engine_agreement}%
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                {Object.entries(data.external_validation.signals).map(([key, val]) => (
                  <div key={key} className="flex justify-between rounded bg-muted/30 px-2 py-1.5">
                    <span className="text-muted-foreground uppercase">{key}</span>
                    <span className="font-medium">{val}</span>
                  </div>
                ))}
              </div>
              {data.external_validation.divergence_alerts.length > 0 && (
                <div className="space-y-1 mt-2">
                  {data.external_validation.divergence_alerts.map((alert, i) => (
                    <p key={i} className="text-xs text-amber-400 bg-amber-500/10 rounded px-2 py-1" role="alert">
                      {alert}
                    </p>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {data?.regime_validation && (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
                Regime Confirmation
                <InfoTooltip text="Multi-check validation that confirms or challenges the detected market regime. Checks: 200-day SMA trend, market breadth, and institutional consensus alignment." />
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm">Current Regime</span>
                <Badge variant="outline">{data.regime_validation.regime}</Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm">Status</span>
                <Badge variant="outline" className={
                  data.regime_validation.confirmed
                    ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                    : "bg-amber-500/15 text-amber-400 border-amber-500/30"
                }>
                  {data.regime_validation.confirmed ? "CONFIRMED" : "UNCONFIRMED"} ({data.regime_validation.confidence})
                </Badge>
              </div>
              <div className="space-y-1.5">
                {Object.entries(data.regime_validation.checks).map(([check, passed]) => (
                  <div key={check} className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground capitalize">{check.replace(/_/g, " ")}</span>
                    <span className={passed ? "text-emerald-400" : "text-red-400"}>
                      {passed ? "Pass" : "Fail"}
                    </span>
                  </div>
                ))}
              </div>
              {data.regime_validation.notes.length > 0 && (
                <div className="space-y-1 mt-2">
                  {data.regime_validation.notes.slice(0, 3).map((note, i) => (
                    <p key={i} className="text-xs text-muted-foreground bg-muted/30 rounded px-2 py-1">
                      {note}
                    </p>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {error && <ErrorCard message={(error as Error).message} onRetry={() => refetch()} />}
    </div>
  );
}
