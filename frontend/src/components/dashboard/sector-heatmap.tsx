"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTooltip } from "@/components/info-tooltip";
import type { SectorsResponse } from "@/lib/api";

function colorForReturn(pct: number): string {
  if (pct > 40) return "bg-emerald-600/80 text-white";
  if (pct > 20) return "bg-emerald-500/60 text-white";
  if (pct > 0) return "bg-emerald-500/30 text-emerald-200";
  if (pct > -10) return "bg-red-500/30 text-red-200";
  return "bg-red-600/60 text-white";
}

export function SectorHeatmap({ data }: { data: SectorsResponse | null }) {
  if (!data) {
    return (
      <Card>
        <CardHeader><CardTitle>Sector Heatmap</CardTitle></CardHeader>
        <CardContent><Skeleton className="h-48 w-full" /></CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
          Sector Expected Returns (5Y)
          <InfoTooltip text="5-year expected total returns for each S&P 500 sector, computed from Monte Carlo simulation with sector-specific beta, momentum, and volatility adjustments." />
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
          {data.sectors.map((sector) => (
            <div
              key={sector.name}
              className={`rounded-lg p-3 transition-colors ${colorForReturn(sector.sim_total_return)}`}
            >
              <p className="text-xs font-medium truncate">{sector.name}</p>
              <p className="text-lg font-bold tabular-nums">
                {sector.sim_total_return >= 0 ? "+" : ""}{sector.sim_total_return.toFixed(1)}%
              </p>
              <p className="text-[10px] opacity-70">
                Beta {sector.beta.toFixed(2)} | Crash {sector.crash_prob.toFixed(0)}%
              </p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
