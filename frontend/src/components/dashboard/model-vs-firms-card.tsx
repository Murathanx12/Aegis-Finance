"use client";

import { useQuery } from "@tanstack/react-query";
import { getModelVsFirms } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { InfoTooltip } from "@/components/info-tooltip";

/**
 * Our MC S&P 500 expected return next to the published capital-market
 * assumptions of major firms (JPM, Vanguard, BlackRock, ...). The honest
 * takeaway rendered visually: the firms disagree with each other by >5pp —
 * that dispersion IS the margin of error on any long-run forecast.
 */
export function ModelVsFirmsCard() {
  const { data } = useQuery({
    queryKey: ["model-vs-firms"],
    queryFn: getModelVsFirms,
    staleTime: 60 * 60 * 1000,
    retry: 1,
  });
  if (!data || !data.firms?.length) return null;

  const values = data.firms.flatMap((f) => [f.low_pct, f.high_pct]);
  if (data.our_model) values.push(data.our_model.median_annual_pct);
  const min = Math.floor(Math.min(...values)) - 1;
  const max = Math.ceil(Math.max(...values)) + 1;
  const pos = (v: number) => `${((v - min) / (max - min)) * 100}%`;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-medium text-muted-foreground flex items-center">
          Expected Returns: Our Model vs Major Firms
          <InfoTooltip text={data.framing} />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {data.our_model && (
          <div className="flex items-center gap-3">
            <span className="w-44 shrink-0 text-sm font-semibold">
              Aegis MC <span className="text-xs text-muted-foreground font-normal">({data.our_model.horizon})</span>
            </span>
            <div className="relative h-3 flex-1 rounded-full bg-muted/40">
              <div
                className="absolute -top-0.5 h-4 w-2 rounded bg-sky-400"
                style={{ left: pos(data.our_model.median_annual_pct) }}
                title={`${data.our_model.median_annual_pct}%/yr median`}
              />
            </div>
            <span className="w-16 shrink-0 text-right text-sm font-bold tabular-nums text-sky-400">
              {data.our_model.median_annual_pct.toFixed(1)}%
            </span>
          </div>
        )}
        {data.firms.map((f) => (
          <div key={f.firm} className="flex items-center gap-3">
            <span className="w-44 shrink-0 truncate text-sm text-muted-foreground" title={`${f.firm} (${f.horizon}, as of ${f.as_of})${f.note ? ` — ${f.note}` : ""}`}>
              {f.firm} <span className="text-xs">({f.horizon})</span>
            </span>
            <div className="relative h-3 flex-1 rounded-full bg-muted/40">
              {f.low_pct !== f.high_pct ? (
                <div
                  className="absolute top-0 h-3 rounded-full bg-emerald-400/50"
                  style={{ left: pos(f.low_pct), width: `calc(${pos(f.high_pct)} - ${pos(f.low_pct)})` }}
                />
              ) : (
                <div className="absolute -top-0.5 h-4 w-1.5 rounded bg-emerald-400/80" style={{ left: pos(f.low_pct) }} />
              )}
            </div>
            <span className="w-16 shrink-0 text-right text-sm tabular-nums text-muted-foreground">
              {f.low_pct === f.high_pct ? `${f.low_pct.toFixed(1)}%` : `${f.low_pct.toFixed(1)}–${f.high_pct.toFixed(1)}%`}
            </span>
          </div>
        ))}
        <div className="flex justify-between text-xs text-muted-foreground tabular-nums pl-44 pr-16 -mt-1">
          <span>{min}%/yr</span>
          <span>{max}%/yr</span>
        </div>
        <p className="text-xs text-muted-foreground">
          Nominal annualized, horizons as labeled. The spread across firms is the honest
          margin of error on any long-run forecast — including ours. Published figures,
          refreshed on the firms&apos; annual cycle. Educational, not advice.
        </p>
      </CardContent>
    </Card>
  );
}
