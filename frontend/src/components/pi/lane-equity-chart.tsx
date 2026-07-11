"use client";

import { useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer,
  Tooltip, Legend, ReferenceLine,
} from "recharts";
import type { PITrackRecordResponse } from "@/lib/api";

// All 7 lanes — book lanes and the ATR trial included, so every seeded lane
// the API returns actually renders (the old 4-entry map silently dropped 3).
export const LANE_STYLE: Record<string, { label: string; color: string }> = {
  conservative: { label: "Conservative", color: "#3b82f6" },
  balanced: { label: "Balanced", color: "#f59e0b" },
  aggressive: { label: "Aggressive", color: "#ef4444" },
  // Frozen equal-weight control trial (config v2): same mandate as Balanced,
  // optimizer is the only difference — the forward delta isolates HRP.
  "balanced-ew-control": { label: "EW Control", color: "#2dd4bf" },
  mirror: { label: "Mirror (rules on Murat's book)", color: "#a855f7" },
  conviction: { label: "Conviction (Murat's calls)", color: "#ec4899" },
  "conservative-atr": { label: "Conservative+ATR (exit trial)", color: "#84cc16" },
};

export const BENCH_STYLE: Record<string, { label: string; color: string }> = {
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

export function LaneEquityChart({
  data,
  height = 420,
}: {
  data: PITrackRecordResponse;
  height?: number;
}) {
  // Memoized: sibling queries on the dev dashboard re-render this component
  // without changing `data` — re-merging the full series each tick is waste.
  const rows = useMemo(() => mergeSeries(data), [data]);
  const boundaries = useMemo(() => segmentBoundaries(data), [data]);
  // Only draw lanes/benchmarks that actually have data
  const laneKeys = Object.keys(LANE_STYLE).filter(
    (k) => (data.lanes[k] ?? []).length > 0,
  );
  const benchKeys = Object.keys(BENCH_STYLE).filter((k) =>
    Object.prototype.hasOwnProperty.call(data.benchmarks, k),
  );

  return (
    <ResponsiveContainer width="100%" height={height}>
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

        {data.inception_date && (
          <ReferenceLine
            x={data.inception_date}
            stroke="var(--muted-foreground)"
            strokeDasharray="2 4"
            label={{ value: "inception", fontSize: 10, fill: "var(--muted-foreground)" }}
          />
        )}

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
        {benchKeys.map((key) => (
          <Line
            key={key}
            type="monotone"
            dataKey={key}
            stroke={BENCH_STYLE[key].color}
            strokeWidth={1.25}
            strokeDasharray="5 4"
            dot={false}
            connectNulls
          />
        ))}
        {/* Lanes: solid, prominent, dot on the (possibly intraday) last point */}
        {laneKeys.map((key) => (
          <Line
            key={key}
            type="monotone"
            dataKey={key}
            stroke={LANE_STYLE[key].color}
            strokeWidth={2}
            dot={{ r: 2.5 }}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
