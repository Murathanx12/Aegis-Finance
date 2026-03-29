"use client";

import { useState, useEffect } from "react";
import { useApi } from "@/hooks/use-api";
import { getMarketStatus, getMacroIndicators, getSP500Projection, getSectors } from "@/lib/api";
import { MarketBanner } from "@/components/dashboard/market-banner";
import { CrashGauge } from "@/components/dashboard/crash-gauge";
import { SP500Chart } from "@/components/dashboard/sp500-chart";
import { MacroCards } from "@/components/dashboard/macro-cards";
import { SectorHeatmap } from "@/components/dashboard/sector-heatmap";
import { HeroSection } from "@/components/dashboard/hero-section";
import { ErrorCard } from "@/components/error-card";
import { DisclaimerBanner } from "@/components/disclaimer-banner";
import { InfoTooltip } from "@/components/info-tooltip";

const REFRESH_INTERVAL = 300_000; // 5 minutes

/** Human-readable "X ago" from a timestamp */
function timeAgo(ts: number): string {
  const diff = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (diff < 10) return "just now";
  if (diff < 60) return `${diff}s ago`;
  const min = Math.floor(diff / 60);
  return `${min}m ${diff % 60}s ago`;
}

export default function DashboardPage() {
  const opts = { refreshInterval: REFRESH_INTERVAL };
  const market = useApi(getMarketStatus, [], opts);
  const macro = useApi(getMacroIndicators, [], opts);
  const projection = useApi(() => getSP500Projection(10000, 5), [], opts);
  const sectors = useApi(getSectors, [], opts);

  // Track last refresh time for the indicator
  const [lastRefresh, setLastRefresh] = useState(Date.now());
  const [agoText, setAgoText] = useState("just now");

  // Update lastRefresh whenever data arrives
  useEffect(() => {
    if (market.data) setLastRefresh(Date.now());
  }, [market.data]);

  // Tick the "ago" display every 10s
  useEffect(() => {
    const id = setInterval(() => setAgoText(timeAgo(lastRefresh)), 10_000);
    return () => clearInterval(id);
  }, [lastRefresh]);

  const anyError = market.error || macro.error || projection.error || sectors.error;

  return (
    <div className="space-y-6 lg:pt-0 pt-2 animate-slide-up">
      <HeroSection data={market.data} />

      {/* Auto-refresh indicator */}
      <div className="flex items-center justify-end -mt-3">
        <span className="inline-flex items-center gap-1.5 rounded-md border border-border/50 bg-muted/30 px-2 py-1 text-[11px] text-muted-foreground">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
          </span>
          Auto-refreshes every 5 min
          <span className="text-muted-foreground/60 ml-1">&middot; Updated {agoText}</span>
        </span>
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
