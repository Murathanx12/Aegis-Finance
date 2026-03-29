"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { MacroResponse } from "@/lib/api";

const KEY_INDICATORS = [
  "T10Y2Y", "VIXCLS", "BAMLH0A0HYM2", "ICSA",
  "NFCI", "UNRATE", "FEDFUNDS", "UMCSENT",
];

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
    .map((key) => ({ key, ...data.indicators[key] }))
    .filter((ind) => ind.name);

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {indicators.map((ind) => (
        <Card key={ind.key}>
          <CardContent className="p-3">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wide truncate">
              {ind.name}
            </p>
            <p className="text-lg font-semibold tabular-nums">{ind.value?.toFixed(2)}</p>
            {ind.change_1m_pct != null && (
              <p className={`text-xs tabular-nums ${ind.change_1m_pct >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                {ind.change_1m_pct >= 0 ? "+" : ""}{ind.change_1m_pct}% (1M)
              </p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
