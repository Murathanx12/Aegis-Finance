"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft, AlertTriangle, Clock3 } from "lucide-react";
import Link from "next/link";
import { piGetTrackRecord } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { LANE_STYLE, LaneEquityChart } from "@/components/pi/lane-equity-chart";
import { LaneStatsCI } from "@/components/pi/lane-stats-ci";

export default function TrackRecordPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.pi.trackRecord,
    queryFn: piGetTrackRecord,
    staleTime: 5 * 60 * 1000, // re-marks hourly during market hours
    refetchInterval: 10 * 60 * 1000,
  });

  const hasData = Object.values(data?.lanes ?? {}).some((l) => l.length > 0);

  return (
    <div className="space-y-6 animate-slide-up" suppressHydrationWarning>
      <div className="flex items-center gap-3" suppressHydrationWarning>
        <Link href="/portfolio-intelligence">
          <Button variant="ghost" size="icon"><ArrowLeft className="h-4 w-4" /></Button>
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold tracking-tight">Live Track Record</h1>
          <p className="text-sm text-muted-foreground">
            Forward paper-portfolio NAV, marked from real prices since{" "}
            {data?.inception_date ?? "inception"}
            {data?.age_days != null && ` — day ${data.age_days}`}.
            This is the canonical record; backtests live on the methodology pages.
          </p>
        </div>
        {data && (
          <Badge variant={data.all_fresh ? "outline" : "destructive"}>
            {data.all_fresh ? "fresh" : "STALE"}
          </Badge>
        )}
      </div>

      {/* Stale-data warning — loud, never silent */}
      {data && !data.all_fresh && (
        <Card className="border-red-500/40 bg-red-500/5">
          <CardContent className="py-3 flex items-center gap-2 text-sm text-red-400">
            <AlertTriangle className="h-4 w-4" />
            <span>
              NAV data is stale: expected a mark for {data.expected_nav_date}.
              The line below ends before the last trading day — treat the tail
              as missing, not flat.
            </span>
          </CardContent>
        </Card>
      )}

      {/* F-019: "too early" is a first-class display state, not a footnote.
          Calibration numbers come from the 73-year mandate replay
          (docs/research/LONG_HORIZON_MANDATES_2026-07-18.md). */}
      {data?.age_days != null && data.age_days < 730 && (
        <Card className="border-amber-500/30 bg-amber-500/5">
          <CardContent className="py-3 space-y-1 text-xs">
            <p className="font-medium flex items-center gap-2 text-amber-500">
              <Clock3 className="h-3.5 w-3.5" />
              Too early to read: day {data.age_days} of a 24-month minimum
              window ({Math.max(1, Math.round((data.age_days / 730) * 100))}%
              elapsed).
            </p>
            <p className="text-muted-foreground">
              At this age, differences between lanes — including the largest
              one on this board — are noise, not skill. The first
              pre-registered decision date is 2027-06-10 (TRIAL-001, HRP vs
              equal-weight); nothing is judged before its date. For scale: in
              a 73-year replay of these same mandates, every one of them spent
              3&ndash;6 consecutive <em>years</em> below a prior peak at least
              once and still compounded. A few weeks of NAV cannot rank the
              lanes.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Intraday re-mark notice — honesty about today's moving point */}
      {data?.intraday_date && (
        <Card className="border-blue-500/30 bg-blue-500/5">
          <CardContent className="py-3 flex items-center gap-2 text-xs text-blue-400/90">
            <Clock3 className="h-3.5 w-3.5" />
            <span>
              Today&rsquo;s point ({data.intraday_date}) is provisional: it
              re-marks hourly during market hours and becomes final at the
              16:30 ET close. Movement in the last point is the market, not noise.
            </span>
          </CardContent>
        </Card>
      )}

      {isLoading && <Skeleton className="h-96" />}

      {error && (
        <Card className="border-red-500/30">
          <CardContent className="py-4 text-sm text-red-400">
            Failed to load track record: {(error as Error).message}
          </CardContent>
        </Card>
      )}

      {data && !hasData && (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No NAV history yet — the record starts accruing at the first
            mark-to-market after inception.
          </CardContent>
        </Card>
      )}

      {data && hasData && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">
              Lanes vs benchmarks (normalized to $100k at inception)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <LaneEquityChart data={data} />
            <p className="text-[11px] text-muted-foreground mt-2">
              {data.benchmark_note} Per-point config versions mark track-record
              segments; rule changes always start a new labeled segment.
              No skill claims before 24 months of tracked decisions.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Per-lane summary cards */}
      {data && hasData && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {Object.entries(LANE_STYLE).map(([key, s]) => {
            const pts = data.lanes[key] ?? [];
            if (pts.length === 0) return (
              <Card key={key}>
                <CardContent className="py-4 text-xs text-muted-foreground">
                  {s.label}: no NAV rows yet
                </CardContent>
              </Card>
            );
            const last = pts[pts.length - 1];
            const delta = (last.value / 100_000 - 1) * 100;
            return (
              <Card key={key}>
                <CardContent className="py-4">
                  <p className="text-xs uppercase tracking-wide" style={{ color: s.color }}>
                    {s.label}
                  </p>
                  <p className="text-xl font-bold tabular-nums">
                    ${last.value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </p>
                  <p className={`text-xs tabular-nums ${delta >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                    {delta >= 0 ? "+" : ""}{delta.toFixed(3)}% since inception
                    {data.intraday_date === last.date && " · intraday"}
                  </p>
                  <LaneStatsCI laneId={key} />
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
