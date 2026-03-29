"use client";

import { useQuery } from "@tanstack/react-query";
import { getSectors } from "@/lib/api";
import type { SectorResult } from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTooltip } from "@/components/info-tooltip";
import { ErrorCard } from "@/components/error-card";
import { DisclaimerBanner } from "@/components/disclaimer-banner";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from "recharts";

function riskColor(drawdownProb: number): string {
  if (drawdownProb > 95) return "text-red-400";
  if (drawdownProb > 85) return "text-amber-400";
  return "text-emerald-400";
}

function returnColor(ret: number): string {
  if (ret > 30) return "text-emerald-400";
  if (ret > 0) return "text-emerald-300";
  return "text-red-400";
}

function barFill(ret: number): string {
  if (ret > 30) return "#22c55e";
  if (ret > 0) return "#4ade80";
  return "#ef4444";
}

function SectorChart({ sectors }: { sectors: SectorResult[] }) {
  const data = sectors.map((s) => ({
    name: s.name,
    return: s.sim_total_return,
  }));

  return (
    <ResponsiveContainer width="100%" height={360}>
      <BarChart data={data} layout="vertical" margin={{ left: 110, right: 30 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
        <XAxis type="number" tick={{ fill: "#888", fontSize: 11 }} tickFormatter={(v: number) => `${v}%`} />
        <YAxis type="category" dataKey="name" tick={{ fill: "#aaa", fontSize: 12 }} width={100} />
        <Tooltip
          contentStyle={{ backgroundColor: "#1e1e2e", border: "1px solid #333", borderRadius: 8 }}
          formatter={(v) => [`${Number(v).toFixed(1)}%`, "Expected Return"]}
        />
        <Bar dataKey="return" radius={[0, 4, 4, 0]}>
          {data.map((d, i) => (
            <Cell key={i} fill={barFill(d.return)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function SectorTable({ sectors }: { sectors: SectorResult[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" aria-label="Sector rankings table">
        <thead>
          <tr className="border-b border-border text-left text-muted-foreground">
            <th className="py-2 pr-2 w-8" scope="col">#</th>
            <th className="py-2 pr-4" scope="col">Sector</th>
            <th className="py-2 pr-4 text-right" scope="col">Expected Return</th>
            <th className="py-2 pr-4 text-right hidden sm:table-cell" scope="col">Annual</th>
            <th className="py-2 pr-4 text-right hidden md:table-cell" scope="col">Volatility</th>
            <th className="py-2 pr-4 text-right hidden md:table-cell" scope="col">Beta</th>
            <th className="py-2 pr-4 text-right hidden lg:table-cell" scope="col">Mom 6M</th>
            <th className="py-2 pr-4 text-right hidden lg:table-cell" scope="col">Mom 12M</th>
            <th className="py-2 text-right" scope="col">P(20% DD)</th>
          </tr>
        </thead>
        <tbody>
          {sectors.map((s) => (
            <tr key={s.name} className="border-b border-border/50 hover:bg-muted/20 transition-colors">
              <td className="py-2.5 pr-2 tabular-nums text-muted-foreground">{s.rank}</td>
              <td className="py-2.5 pr-4 font-medium">{s.name}</td>
              <td className={`py-2.5 pr-4 text-right tabular-nums font-medium ${returnColor(s.sim_total_return)}`}>
                {s.sim_total_return >= 0 ? "+" : ""}{s.sim_total_return.toFixed(1)}%
              </td>
              <td className={`py-2.5 pr-4 text-right tabular-nums hidden sm:table-cell ${returnColor(s.expected_annual)}`}>
                {s.expected_annual >= 0 ? "+" : ""}{s.expected_annual.toFixed(1)}%
              </td>
              <td className="py-2.5 pr-4 text-right tabular-nums text-muted-foreground hidden md:table-cell">
                {s.sigma.toFixed(1)}%
              </td>
              <td className="py-2.5 pr-4 text-right tabular-nums hidden md:table-cell">
                {s.beta.toFixed(2)}
              </td>
              <td className={`py-2.5 pr-4 text-right tabular-nums hidden lg:table-cell ${s.momentum_6m >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                {s.momentum_6m >= 0 ? "+" : ""}{s.momentum_6m.toFixed(1)}%
              </td>
              <td className={`py-2.5 pr-4 text-right tabular-nums hidden lg:table-cell ${s.momentum_12m >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                {s.momentum_12m >= 0 ? "+" : ""}{s.momentum_12m.toFixed(1)}%
              </td>
              <td className={`py-2.5 text-right tabular-nums ${riskColor(s.crash_prob)}`}>
                {s.crash_prob.toFixed(0)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function SectorsPage() {
  const { data, isLoading: loading, error, refetch } = useQuery({
    queryKey: queryKeys.sectors,
    queryFn: getSectors,
    staleTime: staleTimes.sectors,
  });

  return (
    <div className="space-y-6 animate-slide-up">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Sector Analysis</h1>
        <p className="text-sm text-muted-foreground">
          11 S&P sectors ranked by risk-adjusted expected returns (factor model)
        </p>
      </div>

      <DisclaimerBanner />

      {data?.sectors && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Card>
            <CardContent className="p-3">
              <p className="text-[10px] text-muted-foreground uppercase">Top Sector</p>
              <p className="text-lg font-bold">{data.sectors[0]?.name}</p>
              <p className="text-sm text-emerald-400 tabular-nums">
                +{data.sectors[0]?.sim_total_return.toFixed(1)}%
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-3">
              <p className="text-[10px] text-muted-foreground uppercase">Bottom Sector</p>
              <p className="text-lg font-bold">{data.sectors[data.sectors.length - 1]?.name}</p>
              <p className={`text-sm tabular-nums ${(data.sectors[data.sectors.length - 1]?.sim_total_return ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                {(data.sectors[data.sectors.length - 1]?.sim_total_return ?? 0) >= 0 ? "+" : ""}{data.sectors[data.sectors.length - 1]?.sim_total_return.toFixed(1)}%
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-3">
              <p className="text-[10px] text-muted-foreground uppercase">Sectors Positive</p>
              <p className="text-xl font-bold tabular-nums">
                {data.sectors.filter((s) => s.sim_total_return > 0).length}/{data.count}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-3">
              <p className="text-[10px] text-muted-foreground uppercase flex items-center">
                Avg P(20% DD)
                <InfoTooltip text="Average probability of a 20%+ drawdown occurring at any point during the 5-year simulation. Over long horizons, even healthy markets can experience temporary drawdowns — values of 80-95% are normal for 5-year windows." />
              </p>
              <p className="text-xl font-bold tabular-nums">
                {(data.sectors.reduce((acc, s) => acc + s.crash_prob, 0) / data.count).toFixed(0)}%
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
            Expected 5-Year Total Return by Sector
            <InfoTooltip text="Simulated 5-year total returns using sector-specific Monte Carlo with beta, momentum, and volatility factors. Green bars = positive expected returns, red = negative." />
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-[360px] w-full" />
          ) : data?.sectors ? (
            <SectorChart sectors={data.sectors} />
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
            Sector Rankings
            <InfoTooltip text="Sectors ranked by risk-adjusted expected return. Beta measures market sensitivity, momentum shows recent price trend, P(20% DD) is simulated probability of experiencing a 20%+ drawdown over 5 years." />
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 11 }).map((_, i) => (
                <Skeleton key={i} className="h-8 w-full" />
              ))}
            </div>
          ) : data?.sectors ? (
            <SectorTable sectors={data.sectors} />
          ) : null}
        </CardContent>
      </Card>

      {error && <ErrorCard message={(error as Error).message} onRetry={() => refetch()} />}
    </div>
  );
}
