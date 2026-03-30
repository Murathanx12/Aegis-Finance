"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getSP500Projection, getScenarios,
} from "@/lib/api";
import type { SP500Projection } from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTooltip } from "@/components/info-tooltip";
import { ErrorCard } from "@/components/error-card";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar, Cell,
} from "recharts";

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
    <ResponsiveContainer width="100%" height={400}>
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
      <table className="w-full text-sm" aria-label="Scenario breakdown">
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

/* ── Scenario Weight Bar Chart ────────────────────────────────── */

function ScenarioWeightChart({ scenarios }: { scenarios: { name: string; weight: number; median_return: number }[] }) {
  const data = scenarios.map((sc) => ({
    name: sc.name.length > 15 ? sc.name.slice(0, 14) + "..." : sc.name,
    fullName: sc.name,
    weight: Math.round(sc.weight * 100),
    return: sc.median_return,
  }));

  return (
    <ResponsiveContainer width="100%" height={250}>
      <BarChart data={data} margin={{ left: 10, right: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" tick={{ fill: "var(--muted-foreground)", fontSize: 10 }} />
        <YAxis tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
        <Tooltip
          contentStyle={{ backgroundColor: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--foreground)" }}
          formatter={(v, _name, entry) => {
            const p = (entry as { payload?: { fullName?: string; return?: number } })?.payload;
            return [`${v}% weight | ${(p?.return ?? 0) >= 0 ? "+" : ""}${p?.return ?? 0}% return`, p?.fullName ?? ""];
          }}
        />
        <Bar dataKey="weight" radius={[4, 4, 0, 0]}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.return >= 0 ? "#22c55e" : "#ef4444"} fillOpacity={0.7} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ── Metric Card ──────────────────────────────────────────────── */

function MetricCard({ label, value, suffix, color, tooltip }: { label: string; value: string | number; suffix?: string; color?: string; tooltip?: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs text-muted-foreground uppercase font-medium flex items-center">
          {label}
          {tooltip && <InfoTooltip text={tooltip} />}
        </p>
        <p className={`text-2xl font-bold tabular-nums mt-1 ${color || ""}`}>
          {value}{suffix}
        </p>
      </CardContent>
    </Card>
  );
}

/* ── Main Page ───────────────────────────────────────────────── */

export default function SimulationPage() {
  const [nSims, setNSims] = useState(10000);
  const [years, setYears] = useState(5);

  const projQuery = useQuery({
    queryKey: queryKeys.simulation.sp500(nSims, years),
    queryFn: () => getSP500Projection(nSims, years),
    staleTime: staleTimes.simulation,
  });
  const scenQuery = useQuery({
    queryKey: queryKeys.simulation.scenarios,
    queryFn: getScenarios,
    staleTime: staleTimes.simulation,
  });

  const proj = projQuery.data;

  return (
    <div className="space-y-8 animate-slide-up">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Monte Carlo Simulation</h1>
        <p className="text-base text-muted-foreground mt-1">
          Jump-diffusion Monte Carlo projection with scenario weighting, GARCH volatility, and Merton jump compensator
        </p>
      </div>

      <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-2.5 text-xs text-amber-400/80">
        Simulations are probabilistic projections, not predictions. Past performance does not guarantee future results.
      </div>

      {/* Controls */}
      <div className="flex flex-wrap gap-4 items-end">
        <div>
          <p className="text-xs text-muted-foreground mb-1.5 font-medium">Simulation Paths</p>
          <div className="flex gap-1 rounded-lg bg-muted/50 p-1">
            {[5000, 10000, 25000, 50000].map((n) => (
              <button
                key={n}
                onClick={() => setNSims(n)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                  nSims === n ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {(n / 1000).toFixed(0)}K
              </button>
            ))}
          </div>
        </div>
        <div>
          <p className="text-xs text-muted-foreground mb-1.5 font-medium">Forecast Horizon</p>
          <div className="flex gap-1 rounded-lg bg-muted/50 p-1">
            {[1, 3, 5, 10].map((y) => (
              <button
                key={y}
                onClick={() => setYears(y)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                  years === y ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {y}Y
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Fan Chart ─────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-medium text-muted-foreground flex items-center">
            S&P 500 — {years}-Year Projection ({nSims.toLocaleString()} paths)
            <InfoTooltip text={`Fan chart showing percentile bands (5th, 25th, 50th, 75th, 95th) from ${nSims.toLocaleString()} Monte Carlo simulations with jump-diffusion dynamics, GARCH-estimated volatility, and scenario weighting.`} />
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
            <Skeleton className="h-[400px] w-full" />
          ) : proj ? (
            <ProjectionChart data={proj} />
          ) : null}
        </CardContent>
      </Card>

      {/* ── Key Metrics ───────────────────────────────────────── */}
      {proj && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <MetricCard
            label={`Median ${years}Y Return`}
            value={`${proj.median_total_return >= 0 ? "+" : ""}${proj.median_total_return}`}
            suffix="%"
            color={proj.median_total_return >= 0 ? "text-emerald-400" : "text-red-400"}
            tooltip={`Median total return across ${nSims.toLocaleString()} simulated paths`}
          />
          <MetricCard
            label="Annual Return"
            value={proj.median_annual_return}
            suffix="%"
            tooltip="Compound annual growth rate (median path)"
          />
          <MetricCard
            label={`P(Loss) ${years}Y`}
            value={proj.prob_loss}
            suffix="%"
            color="text-amber-400"
            tooltip={`Probability that S&P 500 is lower in ${years} years than today`}
          />
          <MetricCard
            label="95th Percentile"
            value={`$${proj.p95_final?.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
            tooltip="Best-case scenario (95th percentile of final prices)"
          />
        </div>
      )}

      {/* ── Scenarios ─────────────────────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-medium text-muted-foreground flex items-center">
              Scenario Breakdown
              <InfoTooltip text="Each scenario runs independent Monte Carlo simulations. Weights are dynamically adjusted based on current VIX, yield curve, ML crash probability, and recession indicators." />
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
              Scenario Weights
              <InfoTooltip text="Visual distribution of scenario weights. Green = positive return, Red = negative return." />
            </CardTitle>
          </CardHeader>
          <CardContent>
            {scenQuery.isLoading ? (
              <Skeleton className="h-[250px] w-full" />
            ) : scenQuery.data?.scenarios ? (
              <ScenarioWeightChart scenarios={scenQuery.data.scenarios} />
            ) : null}
          </CardContent>
        </Card>
      </div>

      {/* ── Methodology ───────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-medium text-muted-foreground">
            Methodology
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 text-sm">
            <div className="rounded-lg bg-muted/30 p-3">
              <p className="font-medium text-xs uppercase text-muted-foreground tracking-wide">Price Dynamics</p>
              <p className="mt-1">Jump-diffusion GBM with Merton 1976 compensator. Student-t innovations from GARCH-estimated degrees of freedom for fat tails.</p>
            </div>
            <div className="rounded-lg bg-muted/30 p-3">
              <p className="font-medium text-xs uppercase text-muted-foreground tracking-wide">Volatility</p>
              <p className="mt-1">GJR-GARCH(1,1) with skewed Student-t innovations. Ornstein-Uhlenbeck dynamics with leverage effect (rho = -0.7).</p>
            </div>
            <div className="rounded-lg bg-muted/30 p-3">
              <p className="font-medium text-xs uppercase text-muted-foreground tracking-wide">Scenarios</p>
              <p className="mt-1">7 scenarios weighted by ML crash probability, VIX level, yield curve slope, and recession indicators. Weights re-normalize dynamically.</p>
            </div>
            <div className="rounded-lg bg-muted/30 p-3">
              <p className="font-medium text-xs uppercase text-muted-foreground tracking-wide">Mean Reversion</p>
              <p className="mt-1">Calibrated from drawdown recovery data. Asymmetric: stronger pull from below fair value (0.08) than from above (0.04).</p>
            </div>
            <div className="rounded-lg bg-muted/30 p-3">
              <p className="font-medium text-xs uppercase text-muted-foreground tracking-wide">Block Bootstrap</p>
              <p className="mt-1">21-day overlapping blocks preserve volatility clustering and serial correlation in historical residuals.</p>
            </div>
            <div className="rounded-lg bg-muted/30 p-3">
              <p className="font-medium text-xs uppercase text-muted-foreground tracking-wide">Validation</p>
              <p className="mt-1">Realism checks: 2-15% annual return, 10-30% vol, 30-90% crash frequency, kurtosis &gt; 3 (fat tails).</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {(projQuery.error || scenQuery.error) && (
        <ErrorCard
          message={(projQuery.error as Error)?.message || (scenQuery.error as Error)?.message || "Unknown error"}
          onRetry={() => { projQuery.refetch(); scenQuery.refetch(); }}
        />
      )}
    </div>
  );
}
