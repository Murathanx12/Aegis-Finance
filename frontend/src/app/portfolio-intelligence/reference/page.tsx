"use client";

import { useSearchParams } from "next/navigation";
import { useState, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  ArrowLeft, Shield, TrendingUp, Zap, AlertTriangle, CheckCircle2,
} from "lucide-react";
import { InfoTooltip } from "@/components/info-tooltip";
import Link from "next/link";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Tooltip,
  PieChart, Pie, Cell,
} from "recharts";
import {
  piGetReplay,
  type PIReplayResult, type PIRebalanceEvent,
} from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";

const PIE_COLORS = [
  "#63b4ff", "#22c55e", "#f59e0b", "#ef4444", "#a855f7",
  "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16",
];

const LANE_META: Record<string, { label: string; icon: typeof Shield; color: string; bg: string; alloc: string }> = {
  conservative: { label: "Conservative", icon: Shield, color: "text-blue-400", bg: "bg-blue-500/10", alloc: "40% Equity / 50% Bond / 10% Alt" },
  balanced: { label: "Balanced", icon: TrendingUp, color: "text-amber-400", bg: "bg-amber-500/10", alloc: "70% Equity / 25% Bond / 5% Alt" },
  aggressive: { label: "Aggressive", icon: Zap, color: "text-red-400", bg: "bg-red-500/10", alloc: "95% Equity / 5% Bond / 0% Alt" },
};

function MetricCard({ label, value, suffix, color, tooltip }: {
  label: string; value: string | number; suffix?: string; color?: string; tooltip?: string;
}) {
  return (
    <div className="rounded-lg bg-muted/30 p-3">
      <p className="text-[10px] text-muted-foreground uppercase tracking-wide flex items-center gap-1">
        {label}
        {tooltip && <InfoTooltip text={tooltip} />}
      </p>
      <p className={`text-lg font-bold tabular-nums ${color || ""}`}>
        {value}{suffix}
      </p>
    </div>
  );
}

function ReferencePageContent() {
  const searchParams = useSearchParams();
  const initialLane = searchParams.get("lane") || "conservative";
  const [activeLane, setActiveLane] = useState(initialLane);

  const { data: replay, isLoading, error } = useQuery({
    queryKey: queryKeys.pi.replay(activeLane),
    queryFn: () => piGetReplay(activeLane),
    staleTime: staleTimes.pi,
  });

  const meta = LANE_META[activeLane] || LANE_META.conservative;
  const LaneIcon = meta.icon;

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="flex items-center gap-3">
        <Link href="/portfolio-intelligence">
          <Button variant="ghost" size="icon"><ArrowLeft className="h-4 w-4" /></Button>
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <LaneIcon className={`h-6 w-6 ${meta.color}`} />
            {meta.label} Reference Portfolio
          </h1>
          <p className="text-sm text-muted-foreground">{meta.alloc}</p>
        </div>
      </div>

      {/* Lane Tabs */}
      <div className="flex gap-2">
        {Object.entries(LANE_META).map(([id, m]) => (
          <Button
            key={id}
            variant={activeLane === id ? "default" : "outline"}
            size="sm"
            onClick={() => setActiveLane(id)}
          >
            <m.icon className="h-4 w-4 mr-1" />
            {m.label}
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
          <Card className="border-blue-500/30 bg-blue-500/5">
            <CardContent className="py-3">
              <p className="text-xs text-blue-400/80">
                Running 5-year walk-forward replay on real Yahoo Finance data. First call
                fetches ~80 tickers and runs ~260 weekly rebalances — typically 30-60 seconds.
                Result is cached for 30 minutes.
              </p>
            </CardContent>
          </Card>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-20" />)}
          </div>
          <Skeleton className="h-64" />
        </div>
      )}

      {error && (
        <Card className="border-red-500/30">
          <CardContent className="py-4 text-sm text-red-400">
            Failed to load replay data: {(error as Error).message}
          </CardContent>
        </Card>
      )}

      {replay && <ReplayResults data={replay} />}
    </div>
  );
}

export default function ReferencePage() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <ReferencePageContent />
    </Suspense>
  );
}

function ReplayResults({ data }: { data: PIReplayResult }) {
  const { metrics, equity_curve, rebalance_log, crash_guard_activations, total_rebalances, total_turnover, total_cost_bps } = data;

  return (
    <div className="space-y-4">
      {/* Metrics Grid */}
      {metrics && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard
            label="Total Return"
            value={`${(metrics.total_return * 100).toFixed(1)}%`}
            color={metrics.total_return >= 0 ? "text-emerald-400" : "text-red-400"}
          />
          <MetricCard
            label="Ann. Return"
            value={`${(metrics.annualized_return * 100).toFixed(1)}%`}
          />
          <MetricCard
            label="Ann. Volatility"
            value={`${(metrics.annualized_volatility * 100).toFixed(1)}%`}
          />
          <MetricCard
            label="Sharpe"
            value={metrics.sharpe_ratio?.toFixed(2) ?? "N/A"}
            tooltip="Risk-adjusted return (Rf = 4%)"
            color={metrics.sharpe_ratio && metrics.sharpe_ratio > 0.5 ? "text-emerald-400" : ""}
          />
          <MetricCard
            label="Sortino"
            value={metrics.sortino_ratio?.toFixed(2) ?? "N/A"}
            tooltip="Downside risk-adjusted return"
          />
          <MetricCard
            label="Max Drawdown"
            value={`${(metrics.max_drawdown * 100).toFixed(1)}%`}
            color="text-red-400"
          />
          <MetricCard
            label="Rebalances"
            value={total_rebalances}
          />
          <MetricCard
            label="Total Turnover"
            value={`${(total_turnover * 100).toFixed(0)}%`}
          />
        </div>
      )}

      {/* Summary Stats Row */}
      <div className="flex gap-4 flex-wrap text-sm">
        <div className="flex items-center gap-1.5">
          {crash_guard_activations > 0 ? (
            <AlertTriangle className="h-4 w-4 text-amber-400" />
          ) : (
            <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
          )}
          <span>
            Crash guard: <span className="font-medium tabular-nums">{crash_guard_activations}</span> activations
          </span>
        </div>
        <div className="text-muted-foreground">
          Transaction costs: <span className="font-medium tabular-nums">{total_cost_bps.toFixed(1)} bps</span>
        </div>
        <div className="text-muted-foreground">
          Period: {data.start_date} to {data.end_date}
        </div>
      </div>

      {/* Equity Curve */}
      {equity_curve.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm">Equity Curve</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={equity_curve}>
                <defs>
                  <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                  </linearGradient>
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
                  formatter={(v) => [`$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`, "Value"]}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="hsl(var(--primary))"
                  fill="url(#eqGrad)"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Rebalance Log */}
      {rebalance_log.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">
              Rebalance Log ({rebalance_log.length} events)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-muted-foreground border-b border-border/40">
                    <th className="text-left py-2 px-2">Date</th>
                    <th className="text-left py-2 px-2">Reason</th>
                    <th className="text-right py-2 px-2">Turnover</th>
                    <th className="text-right py-2 px-2">Cost</th>
                    <th className="text-right py-2 px-2">Crash Prob</th>
                    <th className="text-center py-2 px-2">Overlay</th>
                    <th className="text-right py-2 px-2">Portfolio $</th>
                  </tr>
                </thead>
                <tbody>
                  {rebalance_log.slice(0, 20).map((event, i) => (
                    <RebalanceRow key={i} event={event} />
                  ))}
                </tbody>
              </table>
              {rebalance_log.length > 20 && (
                <p className="text-xs text-muted-foreground mt-2 text-center">
                  Showing 20 of {rebalance_log.length} events
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function RebalanceRow({ event }: { event: PIRebalanceEvent }) {
  return (
    <tr className="border-b border-border/20 hover:bg-muted/20">
      <td className="py-1.5 px-2 tabular-nums">{event.date}</td>
      <td className="py-1.5 px-2">
        <Badge variant="outline" className="text-[10px]">{event.reason}</Badge>
      </td>
      <td className="py-1.5 px-2 text-right tabular-nums">{(event.turnover * 100).toFixed(1)}%</td>
      <td className="py-1.5 px-2 text-right tabular-nums">${event.cost.toFixed(2)}</td>
      <td className="py-1.5 px-2 text-right tabular-nums">
        {event.crash_prob != null ? `${(event.crash_prob * 100).toFixed(0)}%` : "—"}
      </td>
      <td className="py-1.5 px-2 text-center">
        {event.overlay_armed ? (
          <Badge variant="destructive" className="text-[10px]">ARMED</Badge>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="py-1.5 px-2 text-right tabular-nums font-medium">
        ${event.portfolio_value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
      </td>
    </tr>
  );
}
