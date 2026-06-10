"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft, AlertTriangle, Clock3 } from "lucide-react";
import Link from "next/link";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer,
  Tooltip, Legend, ReferenceLine,
} from "recharts";
import { piGetTrackRecord, type PITrackRecordResponse } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";

const LANE_STYLE: Record<string, { label: string; color: string }> = {
  conservative: { label: "Conservative", color: "#3b82f6" },
  balanced: { label: "Balanced", color: "#f59e0b" },
  aggressive: { label: "Aggressive", color: "#ef4444" },
  // Frozen equal-weight control trial (config v2): same mandate as Balanced,
  // optimizer is the only difference — the forward delta isolates HRP.
  "balanced-ew-control": { label: "EW Control", color: "#2dd4bf" },
};
const BENCH_STYLE: Record<string, { label: string; color: string }> = {
  SPY: { label: "SPY", color: "#94a3b8" },
  AGG: { label: "AGG", color: "#64748b" },
  "60_40": { label: "60/40", color: "#475569" },
};

/** Merge lane + benchmark series into one recharts row per date. */
function mergeSeries(data: PITrackRecordResponse) {
  const byDate = new Map<string, Record<string, number | string>>();
  const add = (key: string, points: { date: string; value: number }[]) => {
    for (const p of points) {
      const row = byDate.get(p.date) ?? { date: p.date };
      row[key] = p.value;
      byDate.set(p.date, row);
    }
  };
  Object.entries(data.lanes).forEach(([k, pts]) => add(k, pts));
  Object.entries(data.benchmarks).forEach(([k, pts]) => add(k, pts));
  return Array.from(byDate.values()).sort((a, b) =>
    String(a.date).localeCompare(String(b.date)),
  );
}

/** Dates where any lane's config_version changes vs its previous point. */
function segmentBoundaries(data: PITrackRecordResponse): string[] {
  const dates = new Set<string>();
  for (const pts of Object.values(data.lanes)) {
    for (let i = 1; i < pts.length; i++) {
      if (
        pts[i].config_version &&
        pts[i - 1].config_version &&
        pts[i].config_version !== pts[i - 1].config_version
      ) {
        dates.add(pts[i].date);
      }
    }
  }
  return Array.from(dates);
}

export default function TrackRecordPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.pi.trackRecord,
    queryFn: piGetTrackRecord,
    staleTime: 5 * 60 * 1000, // re-marks hourly during market hours
    refetchInterval: 10 * 60 * 1000,
  });

  const rows = data ? mergeSeries(data) : [];
  const boundaries = data ? segmentBoundaries(data) : [];
  const hasData = rows.length > 0 && Object.values(data?.lanes ?? {}).some((l) => l.length > 0);

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
            <ResponsiveContainer width="100%" height={420}>
              <LineChart data={rows}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis
                  dataKey="date"
                  tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
                  interval="preserveStartEnd"
                />
                <YAxis
                  domain={["auto", "auto"]}
                  tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
                  tickFormatter={(v) => `$${(Number(v) / 1000).toFixed(1)}k`}
                  width={70}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "var(--card)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    color: "var(--foreground)",
                  }}
                  formatter={(v, name) => [
                    `$${Number(v ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
                    LANE_STYLE[String(name)]?.label ?? BENCH_STYLE[String(name)]?.label ?? String(name),
                  ]}
                />
                <Legend
                  formatter={(value) =>
                    LANE_STYLE[value]?.label ?? BENCH_STYLE[value]?.label ?? value
                  }
                />

                {/* Inception marker */}
                {data.inception_date && (
                  <ReferenceLine
                    x={data.inception_date}
                    stroke="var(--muted-foreground)"
                    strokeDasharray="2 4"
                    label={{ value: "inception", fontSize: 10, fill: "var(--muted-foreground)" }}
                  />
                )}

                {/* Config-version segment boundaries */}
                {boundaries.map((d) => (
                  <ReferenceLine
                    key={d}
                    x={d}
                    stroke="#a855f7"
                    strokeDasharray="4 4"
                    label={{ value: "config change", fontSize: 10, fill: "#a855f7" }}
                  />
                ))}

                {/* Benchmarks first: muted + dashed, underneath the lanes */}
                {Object.entries(BENCH_STYLE).map(([key, s]) => (
                  <Line
                    key={key}
                    type="monotone"
                    dataKey={key}
                    stroke={s.color}
                    strokeWidth={1.25}
                    strokeDasharray="5 4"
                    dot={false}
                    connectNulls
                  />
                ))}
                {/* Lanes: solid, prominent, dot on the (possibly intraday) last point */}
                {Object.entries(LANE_STYLE).map(([key, s]) => (
                  <Line
                    key={key}
                    type="monotone"
                    dataKey={key}
                    stroke={s.color}
                    strokeWidth={2}
                    dot={{ r: 2.5 }}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
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
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
