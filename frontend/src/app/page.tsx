"use client";

import { useApi } from "@/hooks/use-api";
import { getMarketStatus, getMacroIndicators, getSP500Projection, getSectors } from "@/lib/api";
import { MarketBanner } from "@/components/dashboard/market-banner";
import { CrashGauge } from "@/components/dashboard/crash-gauge";
import { SP500Chart } from "@/components/dashboard/sp500-chart";
import { MacroCards } from "@/components/dashboard/macro-cards";
import { SectorHeatmap } from "@/components/dashboard/sector-heatmap";
import { ErrorCard } from "@/components/error-card";
import { DisclaimerBanner } from "@/components/disclaimer-banner";
import { InfoTooltip } from "@/components/info-tooltip";

export default function DashboardPage() {
  const market = useApi(getMarketStatus);
  const macro = useApi(getMacroIndicators);
  const projection = useApi(() => getSP500Projection(10000, 5));
  const sectors = useApi(getSectors);

  const anyError = market.error || macro.error || projection.error || sectors.error;

  return (
    <div className="space-y-6 lg:pt-0 pt-2 animate-slide-up">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Real-time market intelligence powered by ML crash prediction
        </p>
      </div>

      <DisclaimerBanner />

      {/* Market Status Banner */}
      <MarketBanner data={market.data} />

      {/* Crash Gauge + SP500 Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <CrashGauge data={market.data} />
        <SP500Chart data={projection.data} />
      </div>

      {/* Macro Indicators */}
      <div>
        <h2 className="text-sm font-medium text-muted-foreground mb-3">
          Macro Indicators
          <InfoTooltip text="Key economic indicators from FRED. Changes shown are 1-month percentage changes. These feed into the 9-factor composite risk score." />
        </h2>
        <MacroCards data={macro.data} />
      </div>

      {/* Sector Heatmap */}
      <SectorHeatmap data={sectors.data} />

      {/* Error display */}
      {anyError && (
        <ErrorCard
          message={market.error || projection.error || macro.error || sectors.error || "Unknown error"}
          onRetry={() => {
            market.refetch();
            macro.refetch();
            projection.refetch();
            sectors.refetch();
          }}
        />
      )}
    </div>
  );
}
