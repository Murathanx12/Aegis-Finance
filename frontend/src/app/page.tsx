"use client";

import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { getMarketStatus, getMacroIndicators, getSP500Projection, getSectors, getMarketSignal } from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";
import { MarketBanner } from "@/components/dashboard/market-banner";
import { CrashGauge } from "@/components/dashboard/crash-gauge";
import { SP500Chart } from "@/components/dashboard/sp500-chart";
import { MacroCards } from "@/components/dashboard/macro-cards";
import { SectorHeatmap } from "@/components/dashboard/sector-heatmap";
import { SignalBadge } from "@/components/dashboard/signal-badge";
import { HeroSection } from "@/components/dashboard/hero-section";
import { ErrorCard } from "@/components/error-card";
import { DisclaimerBanner } from "@/components/disclaimer-banner";
import { InfoTooltip } from "@/components/info-tooltip";

const REFRESH_INTERVAL = 300_000; // 5 minutes

function timeAgo(ts: number): string {
  const diff = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (diff < 10) return "just now";
  if (diff < 60) return `${diff}s ago`;
  const min = Math.floor(diff / 60);
  return `${min}m ${diff % 60}s ago`;
}

export default function DashboardPage() {
  const market = useQuery({
    queryKey: queryKeys.market.status,
    queryFn: getMarketStatus,
    staleTime: staleTimes.market,
    refetchInterval: REFRESH_INTERVAL,
  });
  const macro = useQuery({
    queryKey: queryKeys.market.macro,
    queryFn: getMacroIndicators,
    staleTime: staleTimes.market,
    refetchInterval: REFRESH_INTERVAL,
  });
  const projection = useQuery({
    queryKey: queryKeys.simulation.sp500(10000, 5),
    queryFn: () => getSP500Projection(10000, 5),
    staleTime: staleTimes.simulation,
    refetchInterval: REFRESH_INTERVAL,
  });
  const sectors = useQuery({
    queryKey: queryKeys.sectors,
    queryFn: getSectors,
    staleTime: staleTimes.sectors,
    refetchInterval: REFRESH_INTERVAL,
  });
  const signal = useQuery({
    queryKey: queryKeys.market.signal,
    queryFn: getMarketSignal,
    staleTime: staleTimes.market,
    refetchInterval: REFRESH_INTERVAL,
  });

  // Track last refresh time
  const [lastRefresh, setLastRefresh] = useState(Date.now());
  const [agoText, setAgoText] = useState("just now");

  useEffect(() => {
    if (market.data) setLastRefresh(Date.now());
  }, [market.data]);

  useEffect(() => {
    const id = setInterval(() => setAgoText(timeAgo(lastRefresh)), 10_000);
    return () => clearInterval(id);
  }, [lastRefresh]);

  const anyError = market.error || macro.error || projection.error || sectors.error || signal.error;

  return (
    <div className="space-y-6 lg:pt-0 pt-2 animate-slide-up">
      <HeroSection data={market.data ?? null} />

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

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <SignalBadge data={signal.data ?? null} />
        <div className="lg:col-span-3">
          <MarketBanner data={market.data ?? null} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <CrashGauge data={market.data ?? null} />
        <SP500Chart data={projection.data ?? null} />
      </div>

      <div>
        <h2 className="text-base font-medium text-muted-foreground mb-3">
          Macro Indicators
          <InfoTooltip
            text="Key economic indicators from FRED. Changes shown are 1-month percentage changes. These feed into the 9-factor composite risk score."
            beginnerText="These are the vital signs of the economy — like checking a patient's blood pressure and heart rate. They help gauge whether the economy is healthy or stressed."
          />
        </h2>
        <MacroCards data={macro.data ?? null} />
      </div>

      <SectorHeatmap data={sectors.data ?? null} />

      {anyError && (
        <ErrorCard
          message={
            (market.error as Error)?.message ||
            (projection.error as Error)?.message ||
            (macro.error as Error)?.message ||
            (sectors.error as Error)?.message ||
            (signal.error as Error)?.message ||
            "Unknown error"
          }
          onRetry={() => {
            market.refetch();
            macro.refetch();
            projection.refetch();
            sectors.refetch();
            signal.refetch();
          }}
        />
      )}
    </div>
  );
}
