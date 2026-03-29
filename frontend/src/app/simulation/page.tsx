"use client";

import { useApi } from "@/hooks/use-api";
import { getSP500Projection, getScenarios } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTooltip } from "@/components/info-tooltip";
import { ErrorCard } from "@/components/error-card";
import { DisclaimerBanner } from "@/components/disclaimer-banner";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts";

function ProjectionChart({ data }: { data: ReturnType<typeof getSP500Projection> extends Promise<infer T> ? T : never }) {
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
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
        <XAxis dataKey="year" tick={{ fill: "#888", fontSize: 11 }}
          label={{ value: "Years", position: "bottom", fill: "#888", fontSize: 11, offset: -5 }} />
        <YAxis tick={{ fill: "#888", fontSize: 11 }}
          tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : `${v}`} />
        <Tooltip
          contentStyle={{ backgroundColor: "#1e1e2e", border: "1px solid #333", borderRadius: 8 }}
          labelFormatter={(v) => `Year ${v}`}
          formatter={(v) => [`$${Number(v).toLocaleString()}`, ""]}
        />
        <Area type="monotone" dataKey="p95" stackId="band" stroke="none" fill="rgba(99,180,255,0.06)" name="95th" />
        <Area type="monotone" dataKey="p75" stackId="band2" stroke="none" fill="rgba(99,180,255,0.10)" name="75th" />
        <Area type="monotone" dataKey="p50" stroke="#63b4ff" strokeWidth={2} fill="rgba(99,180,255,0.12)" name="Median" />
        <Area type="monotone" dataKey="p25" stackId="band3" stroke="none" fill="rgba(99,180,255,0.10)" name="25th" />
        <Area type="monotone" dataKey="p5" stackId="band4" stroke="none" fill="rgba(99,180,255,0.06)" name="5th" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function ScenarioTable({ scenarios }: { scenarios: { name: string; weight: number; median_return: number; p05_return: number; p95_return: number; prob_loss: number }[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-muted-foreground">
            <th className="py-2 pr-4">Scenario</th>
            <th className="py-2 pr-4 text-right">Weight</th>
            <th className="py-2 pr-4 text-right">Median Return</th>
            <th className="py-2 pr-4 text-right hidden sm:table-cell">Range (5-95th)</th>
            <th className="py-2 text-right">P(Loss)</th>
          </tr>
        </thead>
        <tbody>
          {scenarios.map((sc) => (
            <tr key={sc.name} className="border-b border-border/50 hover:bg-muted/20 transition-colors">
              <td className="py-2.5 pr-4 font-medium">{sc.name}</td>
              <td className="py-2.5 pr-4 text-right tabular-nums">{(sc.weight * 100).toFixed(0)}%</td>
              <td className={`py-2.5 pr-4 text-right tabular-nums font-medium ${sc.median_return >= 0 ? "text-emerald-400" : "text-red-400"}`}>
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

export default function SimulationPage() {
  const projection = useApi(() => getSP500Projection(10000, 5));
  const scenarios = useApi(getScenarios);

  return (
    <div className="space-y-6 animate-slide-up">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Monte Carlo Simulation</h1>
        <p className="text-sm text-muted-foreground">
          Jump-diffusion simulation with Merton compensator, 7 scenario-weighted paths
        </p>
      </div>

      <DisclaimerBanner />

      {/* Summary Stats */}
      {projection.data && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Card>
            <CardContent className="p-3">
              <p className="text-[10px] text-muted-foreground uppercase flex items-center">
                Median 5Y Return
                <InfoTooltip text="The 50th percentile total return across all simulations. Half of simulated outcomes are above this, half below." />
              </p>
              <p className={`text-xl font-bold tabular-nums ${projection.data.median_total_return >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                {projection.data.median_total_return >= 0 ? "+" : ""}{projection.data.median_total_return}%
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-3">
              <p className="text-[10px] text-muted-foreground uppercase flex items-center">
                Annual Return
                <InfoTooltip text="Annualized median return (geometric CAGR). This is what you'd earn per year if returns were smooth." />
              </p>
              <p className="text-xl font-bold tabular-nums">{projection.data.median_annual_return}%</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-3">
              <p className="text-[10px] text-muted-foreground uppercase flex items-center">
                P(Loss) 5Y
                <InfoTooltip text="Probability of negative total return over 5 years. Based on the fraction of simulations ending below the starting price." />
              </p>
              <p className="text-xl font-bold tabular-nums text-amber-400">{projection.data.prob_loss}%</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-3">
              <p className="text-[10px] text-muted-foreground uppercase flex items-center">
                95th Percentile
                <InfoTooltip text="The optimistic tail — only 5% of simulations end higher than this price." />
              </p>
              <p className="text-xl font-bold tabular-nums">${projection.data.p95_final?.toLocaleString(undefined, { maximumFractionDigits: 0 })}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Main Chart */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
            S&P 500 — 5-Year Projection (10,000 Simulations)
            <InfoTooltip text="Fan chart showing percentile bands (5th-25th-50th-75th-95th) from Monte Carlo simulation with jump-diffusion dynamics, GJR-GARCH volatility, and HMM regime blending." />
          </CardTitle>
          {projection.data && (
            <p className="text-xs text-muted-foreground">
              Start: ${projection.data.start_price.toLocaleString(undefined, { maximumFractionDigits: 0 })} |
              Median final: ${projection.data.median_final.toLocaleString(undefined, { maximumFractionDigits: 0 })} |
              5th-95th: ${projection.data.p05_final.toLocaleString(undefined, { maximumFractionDigits: 0 })} - ${projection.data.p95_final.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </p>
          )}
        </CardHeader>
        <CardContent>
          {projection.loading ? (
            <Skeleton className="h-[400px] w-full" />
          ) : projection.data ? (
            <ProjectionChart data={projection.data} />
          ) : null}
        </CardContent>
      </Card>

      {/* Scenario Breakdown */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
            Scenario Breakdown
            <InfoTooltip text="Each scenario runs independent Monte Carlo simulations with different drift and volatility assumptions. Weights are dynamically adjusted based on current ML crash probability, VIX level, and yield curve." />
          </CardTitle>
        </CardHeader>
        <CardContent>
          {scenarios.loading ? (
            <Skeleton className="h-64 w-full" />
          ) : scenarios.data?.scenarios ? (
            <ScenarioTable scenarios={scenarios.data.scenarios} />
          ) : null}
        </CardContent>
      </Card>

      {(projection.error || scenarios.error) && (
        <ErrorCard
          message={projection.error || scenarios.error || "Unknown error"}
          onRetry={() => { projection.refetch(); scenarios.refetch(); }}
        />
      )}
    </div>
  );
}
