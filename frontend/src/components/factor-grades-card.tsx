"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTooltip } from "@/components/info-tooltip";
import type { FactorGrades } from "@/lib/api";

const FACTORS: { key: keyof FactorGrades["components"]; label: string }[] = [
  { key: "value", label: "Value" },
  { key: "growth", label: "Growth" },
  { key: "profitability", label: "Profitability" },
  { key: "momentum", label: "Momentum" },
  { key: "revisions", label: "Revisions" },
];

function gradeClass(color?: string) {
  switch (color) {
    case "green": return "bg-emerald-500 text-white";
    case "emerald": return "bg-emerald-400 text-white";
    case "amber": return "bg-amber-400 text-amber-950";
    case "orange": return "bg-orange-400 text-orange-950";
    case "red": return "bg-red-500 text-white";
    default: return "bg-muted text-muted-foreground";
  }
}

export function FactorGradesCard({ data, loading }: { data: FactorGrades | null; loading?: boolean }) {
  if (loading || !data) {
    return (
      <Card>
        <CardHeader><CardTitle className="text-sm">Factor Grades</CardTitle></CardHeader>
        <CardContent><Skeleton className="h-28 w-full" /></CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          Factor Report Card
          <InfoTooltip text="Sector-relative peer percentiles mapped to A+..F letter bands. Five factors: Value (cheap), Growth (revenue + EPS), Profitability (ROE, margins), Momentum (3/6/12m), Revisions (analyst + financial strength)." />
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-3 mb-3">
          <div className={`rounded-xl px-4 py-2 font-bold text-lg tabular-nums ${gradeClass(data.overall_color)}`}>
            {data.overall_grade ?? "—"}
          </div>
          <div className="text-xs text-muted-foreground">
            Overall{data.overall_percentile !== null ? ` · ${data.overall_percentile.toFixed(0)}th peer percentile` : null}
          </div>
        </div>
        <div className="grid grid-cols-5 gap-2">
          {FACTORS.map(({ key, label }) => {
            const c = data.components[key];
            return (
              <div key={key} className="text-center">
                <div className={`mx-auto rounded-md px-2 py-1 font-semibold tabular-nums ${gradeClass(c?.color)}`}>
                  {c?.grade ?? "—"}
                </div>
                <p className="mt-1 text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
