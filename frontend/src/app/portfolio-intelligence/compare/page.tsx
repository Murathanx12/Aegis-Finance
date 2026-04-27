"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ArrowLeft, Shield, TrendingUp, Zap,
} from "lucide-react";
import { InfoTooltip } from "@/components/info-tooltip";
import Link from "next/link";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Tooltip, Legend,
} from "recharts";
import {
  piGetReplay,
  type PIReplayResult,
} from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";

const LANES = ["conservative", "balanced", "aggressive"] as const;
const LANE_COLORS: Record<string, string> = {
  conservative: "#3b82f6",
  balanced: "#f59e0b",
  aggressive: "#ef4444",
};
const LANE_LABELS: Record<string, string> = {
  conservative: "Conservative",
  balanced: "Balanced",
  aggressive: "Aggressive",
};

function MetricCell({ value, format, positive }: { value: number | null; format: "pct" | "num"; positive?: boolean }) {
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
  const [selected, setSelected] = useState<Set<string>>(new Set(LANES));

  const queries = Object.fromEntries(
    LANES.map((lane) => [
      lane,
      // eslint-disable-next-line react-hooks/rules-of-hooks
      useQuery({
        queryKey: queryKeys.pi.replay(lane),
        queryFn: () => piGetReplay(lane),
        staleTime: staleTimes.pi,
      }),
    ])
  );

  const isLoading = LANES.some((l) => queries[l].isLoading);
  const results: Record<string, PIReplayResult | null> = Object.fromEntries(
    LANES.map((l) => [l, queries[l].data ?? null])
  );

  const toggleLane = (lane: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(lane)) next.delete(lane);
      else next.add(lane);
      return next;
    });
  };

  // Merge equity curves for overlay chart
  const mergedCurve = mergeCurves(results, selected);

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="flex items-center gap-3">
        <Link href="/portfolio-intelligence">
          <Button variant="ghost" size="icon"><ArrowLeft className="h-4 w-4" /></Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Compare Portfolios</h1>
          <p className="text-sm text-muted-foreground">
            Side-by-side comparison of all reference lanes
          </p>
        </div>
      </div>

      {/* Lane Toggle */}
      <div className="flex gap-2 flex-wrap">
        {LANES.map((lane) => (
          <Button
            key={lane}
            variant={selected.has(lane) ? "default" : "outline"}
            size="sm"
            onClick={() => toggleLane(lane)}
            style={selected.has(lane) ? { backgroundColor: LANE_COLORS[lane] } : {}}
          >
            {LANE_LABELS[lane]}
          </Button>
        ))}
      </div>

      {/* Survivorship Disclaimer */}
      <Card className="border-amber-500/30 bg-amber-500/5">
        <CardContent className="py-3">
          <p className="text-xs text-amber-400/80">
            Historical replay performance reflects backtested rebalancing over 2021-2025 using a
            fixed universe. Results may be inflated by survivorship bias if the universe was
            selected from current index constituents. See docs/replay_diagnostics_v1.md for details.
          </p>
        </CardContent>
      </Card>

      {isLoading && (
        <div className="space-y-4">
          <Skeleton className="h-80" />
          <Skeleton className="h-48" />
        </div>
      )}

      {!isLoading && (
        <>
          {/* Metrics Table */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Performance Metrics (5-Year Replay)</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-muted-foreground text-xs border-b border-border/40">
                      <th className="text-left py-2 px-3">Lane</th>
                      <th className="text-right py-2 px-3">Total Return</th>
                      <th className="text-right py-2 px-3">Ann. Return</th>
                      <th className="text-right py-2 px-3">Ann. Vol</th>
                      <th className="text-right py-2 px-3">
                        Sharpe
                        <InfoTooltip text="Risk-adjusted return (Rf = 4%)" />
                      </th>
                      <th className="text-right py-2 px-3">Max DD</th>
                      <th className="text-right py-2 px-3">Rebalances</th>
                      <th className="text-right py-2 px-3">Turnover</th>
                      <th className="text-right py-2 px-3">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {LANES.filter((l) => selected.has(l)).map((lane) => {
                      const r = results[lane];
                      const m = r?.metrics;
                      return (
                        <tr key={lane} className="border-b border-border/20 hover:bg-muted/20">
                          <td className="py-2 px-3">
                            <div className="flex items-center gap-2">
                              <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: LANE_COLORS[lane] }} />
                              <span className="font-medium">{LANE_LABELS[lane]}</span>
                            </div>
                          </td>
                          <MetricCell value={m?.total_return ?? null} format="pct" positive />
                          <MetricCell value={m?.annualized_return ?? null} format="pct" positive />
                          <MetricCell value={m?.annualized_volatility ?? null} format="pct" />
                          <MetricCell value={m?.sharpe_ratio ?? null} format="num" positive />
                          <MetricCell value={m?.max_drawdown ?? null} format="pct" />
                          <td className="py-2 px-3 text-right tabular-nums">{r?.total_rebalances ?? "—"}</td>
                          <MetricCell value={r?.total_turnover ?? null} format="pct" />
                          <td className="py-2 px-3 text-right tabular-nums text-muted-foreground">
                            {r?.total_cost_bps != null ? `${r.total_cost_bps.toFixed(1)} bps` : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {/* Overlaid Equity Curves */}
          {mergedCurve.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Equity Curves (Overlaid)</CardTitle>
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
                      tickFormatter={(d) => d.slice(0, 7)}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
                      tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                    />
                    <Tooltip
                      contentStyle={{ backgroundColor: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--foreground)" }}
                      labelFormatter={(d) => d}
                      formatter={(v, name) => [
                        `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
                        LANE_LABELS[String(name)] || String(name),
                      ]}
                    />
                    <Legend
                      formatter={(value) => LANE_LABELS[value] || value}
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
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Crash Guard Summary</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 md:grid-cols-3">
                {LANES.filter((l) => selected.has(l)).map((lane) => {
                  const r = results[lane];
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
        </>
      )}
    </div>
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
    (a.date as string).localeCompare(b.date as string)
  );
}
