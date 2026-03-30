"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { LineChart, Line, ResponsiveContainer } from "recharts";
import type { MacroResponse } from "@/lib/api";

const KEY_INDICATORS: { key: string; label: string }[] = [
  { key: "yield_spread", label: "Yield Spread (10Y-2Y)" },
  { key: "vix_fred", label: "VIX" },
  { key: "hy_oas", label: "HY Credit Spread" },
  { key: "initial_claims", label: "Initial Claims" },
  { key: "nfci", label: "Financial Conditions" },
  { key: "unemployment", label: "Unemployment Rate" },
  { key: "fed_funds", label: "Fed Funds Rate" },
  { key: "consumer_sentiment", label: "Consumer Sentiment" },
];

/** Format macro values smartly based on magnitude */
function fmtValue(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 10_000) return `${(v / 1_000).toFixed(0)}K`;
  if (Math.abs(v) >= 100) return v.toFixed(1);
  return v.toFixed(2);
}

/** Build a tiny 3-point sparkline dataset from current value + 1M change */
function sparklinePoints(value: number, changePct: number | null) {
  if (value == null) return null;
  const pct = changePct ?? 0;
  const prev = value / (1 + pct / 100);
  const mid = (prev + value) / 2;
  return [{ v: prev }, { v: mid }, { v: value }];
}

export function MacroCards({ data }: { data: MacroResponse | null }) {
  if (!data) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <Card key={i}><CardContent className="p-3"><Skeleton className="h-12 w-full" /></CardContent></Card>
        ))}
      </div>
    );
  }

  const indicators = KEY_INDICATORS
    .map((ki) => ({ key: ki.key, label: ki.label, ...data.indicators[ki.key] }))
    .filter((ind) => ind.value != null);

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {indicators.map((ind) => (
        <Card key={ind.key}>
          <CardContent className="p-3">
            <p className="text-xs text-muted-foreground uppercase tracking-wide truncate">
              {ind.label}
            </p>
            <p className="text-xl font-bold tabular-nums">{fmtValue(ind.value)}</p>
            <div className="flex items-end justify-between gap-2">
              {ind.change_1m_pct != null && (
                <p className={`text-xs tabular-nums ${ind.change_1m_pct >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                  {ind.change_1m_pct >= 0 ? "+" : ""}{ind.change_1m_pct}% (1M)
                </p>
              )}
              {(() => {
                const pts = sparklinePoints(ind.value, ind.change_1m_pct);
                if (!pts) return null;
                const color = (ind.change_1m_pct ?? 0) >= 0 ? "#34d399" : "#f87171";
                return (
                  <div className="h-5 w-12 shrink-0">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={pts}>
                        <Line type="monotone" dataKey="v" stroke={color} strokeWidth={1.5} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                );
              })()}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
