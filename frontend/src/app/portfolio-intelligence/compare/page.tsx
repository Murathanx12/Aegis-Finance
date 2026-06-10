"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ArrowLeft,
} from "lucide-react";
import { InfoTooltip } from "@/components/info-tooltip";
import { MethodologyBanner } from "@/components/methodology-banner";
import Link from "next/link";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Tooltip, Legend,
} from "recharts";
import {
  piGetReplay,
  piGetCompare,
  type PIReplayResult,
  type PIMetricPack,
} from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";

const LANES = ["conservative", "balanced", "aggressive"] as const;
const BENCHMARKS = ["SPY", "AGG", "60-40"] as const;
const LANE_COLORS: Record<string, string> = {
  conservative: "#3b82f6",
  balanced: "#f59e0b",
  aggressive: "#ef4444",
  SPY: "#94a3b8",
  AGG: "#64748b",
  "60-40": "#475569",
};
const LANE_LABELS: Record<string, string> = {
  conservative: "Conservative",
  balanced: "Balanced",
  aggressive: "Aggressive",
  SPY: "SPY",
  AGG: "AGG",
  "60-40": "60/40",
};
const PERIODS = ["1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "ALL"] as const;
type Period = typeof PERIODS[number];

function MetricCell({ value, format, positive }: { value: number | null | undefined; format: "pct" | "num"; positive?: boolean }) {
  if (value == null) return <td className="py-2 px-3 text-right text-muted-foreground">—</td>;

  let display: string;
  let color = "";
  if (format === "pct") {
    display = `${(value * 100).toFixed(1)}%`;
    if (positive !== undefined) {
      color = (positive ? value > 0 : value < 0) ? "text-emerald-400" : value === 0 ? "" : "text-red-400";
    }
  } else {
    display = value.toFixed(2);
    if (positive !== undefined && value > 0.5) color = "text-emerald-400";
  }

  return <td className={`py-2 px-3 text-right tabular-nums font-medium ${color}`}>{display}</td>;
}

export default function ComparePage() {
  const [period, setPeriod] = useState<Period>("3Y");
  const [selected, setSelected] = useState<Set<string>>(
    new Set([...LANES, ...BENCHMARKS])
  );

  // Compare endpoint — gives us lane MetricPacks + benchmark MetricPacks for the table
  const compareQ = useQuery({
    queryKey: [...queryKeys.pi.compare, period],
    queryFn: () => piGetCompare([...LANES], period),
    staleTime: staleTimes.pi,
  });

  // Replay endpoints — used for the equity-curve overlay (always 5y replay).
  // Calling each useQuery explicitly to avoid Rules of Hooks violation.
  const conservativeQ = useQuery({
    queryKey: queryKeys.pi.replay("conservative"),
    queryFn: () => piGetReplay("conservative"),
    staleTime: staleTimes.pi,
  });
  const balancedQ = useQuery({
    queryKey: queryKeys.pi.replay("balanced"),
    queryFn: () => piGetReplay("balanced"),
    staleTime: staleTimes.pi,
  });
  const aggressiveQ = useQuery({
    queryKey: queryKeys.pi.replay("aggressive"),
    queryFn: () => piGetReplay("aggressive"),
    staleTime: staleTimes.pi,
  });

  const replayResults: Record<string, PIReplayResult | null> = {
    conservative: conservativeQ.data ?? null,
    balanced: balancedQ.data ?? null,
    aggressive: aggressiveQ.data ?? null,
  };
  const replayLoading = conservativeQ.isLoading || balancedQ.isLoading || aggressiveQ.isLoading;

  const toggleLane = (lane: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(lane)) next.delete(lane);
      else next.add(lane);
      return next;
    });
  };

  const mergedCurve = mergeCurves(replayResults, selected);

  const compareData = compareQ.data;
  const compareLanes = compareData?.lanes ?? {};
  const compareBenchmarks = compareData?.benchmarks ?? {};

  const compareError = compareQ.error ? (compareQ.error as Error).message : null;

  return (
    <div className="space-y-6 animate-slide-up" suppressHydrationWarning>
      <div className="flex items-center gap-3" suppressHydrationWarning>
        <Link href="/portfolio">
          <Button variant="ghost" size="icon"><ArrowLeft className="h-4 w-4" /></Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Compare Portfolios — Methodology (Backtested)
          </h1>
          <p className="text-sm text-muted-foreground">
            Simulated comparison of reference lanes vs SPY, AGG, and 60/40 &mdash; not the live track record
          </p>
        </div>
      </div>

      {/* Period Selector */}
      <div className="flex gap-2 flex-wrap items-center">
        <span className="text-xs text-muted-foreground mr-1">Period:</span>
        {PERIODS.map((p) => (
          <Button
            key={p}
            variant={period === p ? "default" : "outline"}
            size="sm"
            onClick={() => setPeriod(p)}
          >
            {p}
          </Button>
        ))}
      </div>

      {/* Toggle */}
      <div className="flex gap-2 flex-wrap">
        {[...LANES, ...BENCHMARKS].map((id) => (
          <Button
            key={id}
            variant={selected.has(id) ? "default" : "outline"}
            size="sm"
            onClick={() => toggleLane(id)}
            style={selected.has(id) ? { backgroundColor: LANE_COLORS[id] } : {}}
          >
            {LANE_LABELS[id] ?? id}
          </Button>
        ))}
      </div>

      {/* Methodology label — copy governed by docs/TRACK_RECORD_POLICY.md */}
      <MethodologyBanner />

      {compareError && (
        <Card className="border-red-500/30">
          <CardContent className="py-4 text-sm text-red-400">
            Compare failed: {compareError}
          </CardContent>
        </Card>
      )}

      {compareQ.isLoading && (
        <Card className="border-blue-500/30 bg-blue-500/5">
          <CardContent className="py-4 space-y-3">
            <p className="text-sm text-blue-400 font-medium">
              Computing performance metrics for 3 lanes + SPY/AGG/60-40 over {period}…
            </p>
            <p className="text-xs text-muted-foreground">
              Cold first call runs 3 walk-forward replays plus 3 benchmark fetches.
              Typical cold time: 2-5 minutes. Result is cached for 30 minutes thereafter.
              The equity-curve overlay below will appear separately as each lane finishes.
            </p>
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-5/6" />
          </CardContent>
        </Card>
      )}

      {compareData && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">
              Backtested Metrics ({compareData.start_date} to {compareData.end_date})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-muted-foreground text-xs border-b border-border/40">
                    <th className="text-left py-2 px-3">Portfolio</th>
                    <th className="text-right py-2 px-3">Total Return</th>
                    <th className="text-right py-2 px-3">Ann. Return</th>
                    <th className="text-right py-2 px-3">Ann. Vol</th>
                    <th className="text-right py-2 px-3">
                      Sharpe
                      <InfoTooltip text="Risk-adjusted return (Rf = 4%)" />
                    </th>
                    <th className="text-right py-2 px-3">Max DD</th>
                  </tr>
                </thead>
                <tbody>
                  {LANES.filter((l) => selected.has(l)).map((lane) => (
                    <MetricRow
                      key={lane}
                      label={LANE_LABELS[lane]}
                      colorDot={LANE_COLORS[lane]}
                      metrics={compareLanes[lane] ?? null}
                    />
                  ))}
                  {BENCHMARKS.filter((b) => selected.has(b)).map((bench) => (
                    <MetricRow
                      key={bench}
                      label={LANE_LABELS[bench] ?? bench}
                      colorDot={LANE_COLORS[bench]}
                      metrics={compareBenchmarks[bench] ?? null}
                      muted
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Equity Curves (5-year replay overlay — period selector does not apply) */}
      {replayLoading && (
        <Card>
          <CardHeader><CardTitle className="text-sm">Equity Curves (5-year backtested replay)</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            <p className="text-xs text-muted-foreground">
              Loading replay data for{" "}
              {[
                conservativeQ.isLoading ? "Conservative" : null,
                balancedQ.isLoading ? "Balanced" : null,
                aggressiveQ.isLoading ? "Aggressive" : null,
              ].filter(Boolean).join(", ")}
              …
            </p>
            <Skeleton className="h-64 w-full" />
          </CardContent>
        </Card>
      )}
      {!replayLoading && mergedCurve.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Equity Curves (5-year backtested replay)</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={350}>
              <AreaChart data={mergedCurve}>
                <defs>
                  {LANES.filter((l) => selected.has(l)).map((lane) => (
                    <linearGradient key={lane} id={`grad-${lane}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={LANE_COLORS[lane]} stopOpacity={0.15} />
                      <stop offset="95%" stopColor={LANE_COLORS[lane]} stopOpacity={0} />
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis
                  dataKey="date"
                  tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
                  tickFormatter={(d) => (typeof d === "string" ? d.slice(0, 7) : "")}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
                  tickFormatter={(v) => `$${(Number(v) / 1000).toFixed(0)}k`}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--foreground)" }}
                  labelFormatter={(d) => String(d ?? "")}
                  formatter={(v, name) => {
                    const safeName = name == null ? "" : String(name);
                    const num = v == null ? 0 : Number(v);
                    return [
                      `$${num.toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
                      LANE_LABELS[safeName] ?? safeName,
                    ];
                  }}
                />
                <Legend
                  formatter={(value) => {
                    const safe = value == null ? "" : String(value);
                    return LANE_LABELS[safe] ?? safe;
                  }}
                />
                {LANES.filter((l) => selected.has(l)).map((lane) => (
                  <Area
                    key={lane}
                    type="monotone"
                    dataKey={lane}
                    stroke={LANE_COLORS[lane]}
                    fill={`url(#grad-${lane})`}
                    strokeWidth={2}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Crash Guard Summary */}
      {!replayLoading && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Crash Guard Summary (5-year replay)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 md:grid-cols-3">
              {LANES.filter((l) => selected.has(l)).map((lane) => {
                const r = replayResults[lane];
                return (
                  <div key={lane} className="flex items-center justify-between rounded-lg bg-muted/30 p-3">
                    <div className="flex items-center gap-2">
                      <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: LANE_COLORS[lane] }} />
                      <span className="text-sm font-medium">{LANE_LABELS[lane]}</span>
                    </div>
                    <Badge variant={r?.crash_guard_activations ? "destructive" : "secondary"}>
                      {r?.crash_guard_activations ?? 0} activations
                    </Badge>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function MetricRow({
  label, colorDot, metrics, muted = false,
}: {
  label: string;
  colorDot: string;
  metrics: PIMetricPack | null;
  muted?: boolean;
}) {
  return (
    <tr className={`border-b border-border/20 hover:bg-muted/20 ${muted ? "text-muted-foreground" : ""}`}>
      <td className="py-2 px-3">
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: colorDot }} />
          <span className="font-medium">{label}</span>
        </div>
      </td>
      <MetricCell value={metrics?.total_return ?? null} format="pct" positive />
      <MetricCell value={metrics?.annualized_return ?? null} format="pct" positive />
      <MetricCell value={metrics?.annualized_volatility ?? null} format="pct" />
      <MetricCell value={metrics?.sharpe_ratio ?? null} format="num" positive />
      <MetricCell value={metrics?.max_drawdown ?? null} format="pct" />
    </tr>
  );
}

function mergeCurves(
  results: Record<string, PIReplayResult | null>,
  selected: Set<string>,
): Record<string, unknown>[] {
  const dateMap = new Map<string, Record<string, unknown>>();

  for (const lane of LANES) {
    if (!selected.has(lane)) continue;
    const r = results[lane];
    if (!r) continue;
    for (const pt of r.equity_curve) {
      if (!dateMap.has(pt.date)) {
        dateMap.set(pt.date, { date: pt.date });
      }
      dateMap.get(pt.date)![lane] = pt.value;
    }
  }

  return Array.from(dateMap.values()).sort((a, b) =>
    String(a.date).localeCompare(String(b.date))
  );
}
