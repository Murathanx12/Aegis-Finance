"use client";

import { useApi } from "@/hooks/use-api";
import { getMarketStatus, getMacroIndicators, getSP500Projection, getSectors } from "@/lib/api";
import { MarketBanner } from "@/components/dashboard/market-banner";
import { CrashGauge } from "@/components/dashboard/crash-gauge";
import { SP500Chart } from "@/components/dashboard/sp500-chart";
import { MacroCards } from "@/components/dashboard/macro-cards";
import { SectorHeatmap } from "@/components/dashboard/sector-heatmap";

export default function DashboardPage() {
  const market = useApi(getMarketStatus);
  const macro = useApi(getMacroIndicators);
  const projection = useApi(() => getSP500Projection(10000, 5));
  const sectors = useApi(getSectors);

  return (
    <div className="space-y-6 lg:pt-0 pt-2">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Real-time market intelligence powered by ML crash prediction
        </p>
      </div>

      {/* Market Status Banner */}
      <MarketBanner data={market.data} />

      {/* Crash Gauge + SP500 Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <CrashGauge data={market.data} />
        <SP500Chart data={projection.data} />
      </div>

      {/* Macro Indicators */}
      <div>
        <h2 className="text-sm font-medium text-muted-foreground mb-3">Macro Indicators</h2>
        <MacroCards data={macro.data} />
      </div>

      {/* Sector Heatmap */}
      <SectorHeatmap data={sectors.data} />

      {/* Error display */}
      {(market.error || macro.error || projection.error || sectors.error) && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-4 text-sm text-red-400">
          <p className="font-medium">API Connection Error</p>
          <p className="text-xs mt-1">
            Make sure the backend is running: <code className="bg-red-500/10 px-1 rounded">uvicorn backend.main:app --port 8000</code>
          </p>
          {market.error && <p className="text-xs mt-1">Market: {market.error}</p>}
          {projection.error && <p className="text-xs mt-1">Projection: {projection.error}</p>}
        </div>
      )}
    </div>
  );
}
