"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTooltip } from "@/components/info-tooltip";
import type { StyleBox } from "@/lib/api";

const SIZES = ["Large", "Mid", "Small"] as const;
const STYLES = ["Value", "Blend", "Growth"] as const;

export function StyleBoxCard({ data, loading }: { data: StyleBox | null; loading?: boolean }) {
  if (loading || !data) {
    return (
      <Card>
        <CardHeader><CardTitle className="text-sm">Style Box</CardTitle></CardHeader>
        <CardContent><Skeleton className="h-40 w-full" /></CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          Morningstar Style Box
          <InfoTooltip text="3x3 grid: market cap (Small/Mid/Large) × value-to-growth tilt. Tilt uses peer z-scores on P/E, P/B, dividend yield vs revenue + earnings growth." />
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-[auto_1fr_1fr_1fr] gap-1 text-[11px]">
          <div />
          {STYLES.map((s) => (
            <div key={s} className="text-center text-muted-foreground pb-1">{s}</div>
          ))}
          {SIZES.map((size) => (
            <ContinuedRow key={size} size={size} data={data} />
          ))}
        </div>
        <div className="mt-3 flex items-center justify-between text-xs">
          <span className="font-medium">{data.cell}</span>
          {data.peer_count ? (
            <span className="text-muted-foreground">{data.peer_count} peers</span>
          ) : null}
        </div>
        {data.value_score !== null && data.growth_score !== null ? (
          <div className="mt-1 text-xs text-muted-foreground tabular-nums">
            value z: {data.value_score?.toFixed(2)} · growth z: {data.growth_score?.toFixed(2)}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function ContinuedRow({ size, data }: { size: string; data: StyleBox }) {
  return (
    <>
      <div className="flex items-center justify-end pr-2 text-muted-foreground">{size}</div>
      {STYLES.map((style) => {
        const active = size === data.size && style === data.style;
        return (
          <div
            key={`${size}-${style}`}
            className={
              "aspect-square rounded flex items-center justify-center transition-colors " +
              (active
                ? "bg-emerald-500 text-white"
                : "bg-muted/50 hover:bg-muted")
            }
            aria-label={`${size} ${style}${active ? " (current)" : ""}`}
          >
            {active ? <span className="text-xs font-semibold">●</span> : null}
          </div>
        );
      })}
    </>
  );
}
