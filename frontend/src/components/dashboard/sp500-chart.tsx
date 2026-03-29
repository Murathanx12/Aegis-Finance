"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from "recharts";
import { InfoTooltip } from "@/components/info-tooltip";
import type { SP500Projection } from "@/lib/api";

export function SP500Chart({ data }: { data: SP500Projection | null }) {
  if (!data) {
    return (
      <Card className="col-span-2">
        <CardHeader><CardTitle>S&P 500 Projection</CardTitle></CardHeader>
        <CardContent><Skeleton className="h-64 w-full" /></CardContent>
      </Card>
    );
  }

  const { percentile_paths, start_price, forecast_years } = data;
  const p5 = percentile_paths.p5 || [];
  const p25 = percentile_paths.p25 || [];
  const p50 = percentile_paths.p50 || [];
  const p75 = percentile_paths.p75 || [];
  const p95 = percentile_paths.p95 || [];

  const chartData = p50.map((_, i) => {
    const yearFrac = (i * 5) / 252; // 5-day sampling
    return {
      year: yearFrac.toFixed(1),
      p5: Math.round(p5[i] || 0),
      p25: Math.round(p25[i] || 0),
      p50: Math.round(p50[i] || 0),
      p75: Math.round(p75[i] || 0),
      p95: Math.round(p95[i] || 0),
    };
  });

  return (
    <Card className="col-span-2">
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
          S&P 500 — {forecast_years}Y Monte Carlo Projection
          <InfoTooltip text="Fan chart showing 5th-95th percentile price paths from 10,000 jump-diffusion Monte Carlo simulations. The blue line is the median path. Width indicates uncertainty." />
        </CardTitle>
        <div className="flex gap-4 text-sm">
          <span>Median: <strong className="text-emerald-400">{data.median_total_return}%</strong></span>
          <span>Annual: <strong>{data.median_annual_return}%</strong></span>
          <span>P(Loss): <strong className="text-red-400">{data.prob_loss}%</strong></span>
        </div>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis
              dataKey="year"
              tick={{ fill: "#888", fontSize: 11 }}
              label={{ value: "Years", position: "bottom", fill: "#888", fontSize: 11 }}
            />
            <YAxis
              tick={{ fill: "#888", fontSize: 11 }}
              tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}k`}
            />
            <Tooltip
              contentStyle={{ backgroundColor: "#1e1e2e", border: "1px solid #333", borderRadius: 8 }}
              labelFormatter={(v) => `Year ${v}`}
              formatter={(v) => [`$${Number(v).toLocaleString()}`, ""]}
            />
            <Area type="monotone" dataKey="p95" stroke="none" fill="rgba(99,180,255,0.08)" />
            <Area type="monotone" dataKey="p75" stroke="none" fill="rgba(99,180,255,0.12)" />
            <Area type="monotone" dataKey="p50" stroke="#63b4ff" strokeWidth={2} fill="rgba(99,180,255,0.15)" />
            <Area type="monotone" dataKey="p25" stroke="none" fill="rgba(99,180,255,0.12)" />
            <Area type="monotone" dataKey="p5" stroke="none" fill="rgba(99,180,255,0.08)" />
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
