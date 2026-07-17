"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTooltip } from "@/components/info-tooltip";
import { getFredEconomicCalendar } from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";

function Stars({ n }: { n: number }) {
  return (
    <span className="text-amber-400/90 text-xs tracking-tight" aria-label={`importance ${n} of 3`}>
      {"★".repeat(n)}
      <span className="text-muted-foreground/30">{"★".repeat(3 - n)}</span>
    </span>
  );
}

function fmtVal(v: number | null): string {
  if (v == null) return "—";
  const abs = Math.abs(v);
  if (abs >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

const DIRECTION_STYLE: Record<string, string> = {
  beat: "text-emerald-400",
  miss: "text-red-400",
  inline: "text-muted-foreground",
};

/**
 * Recent FRED releases: Actual vs our trend proxy vs Previous, with
 * importance stars. The "forecast" is a rolling-median trend computed from
 * the series itself — the note discloses it's not a street consensus.
 */
export function EconomicCalendarCard() {
  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.analytics.economicCalendar,
    queryFn: getFredEconomicCalendar,
    staleTime: staleTimes.market,
  });

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          Economic Calendar — Recent Releases
          <InfoTooltip
            text="Latest FRED prints vs a 12-period rolling-median trend (our consensus proxy — we don't fake a street consensus feed). Beat/miss is relative to trend, sign-adjusted so 'beat' is always economically good news."
            beginnerText="Recent economic report cards. 'Beat' means the number came in better than its recent trend, 'miss' means worse. Stars show how much markets care about each report."
          />
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && <Skeleton className="h-48" />}
        {error && (
          <p className="text-sm text-muted-foreground py-4">
            Economic calendar unavailable right now.
          </p>
        )}
        {data && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm" aria-label="Economic calendar">
                <thead>
                  <tr className="border-b border-border text-left text-muted-foreground text-xs">
                    <th className="py-2 pr-3" scope="col">Release</th>
                    <th className="py-2 pr-3" scope="col">Imp.</th>
                    <th className="py-2 pr-3" scope="col">Date</th>
                    <th className="py-2 pr-3 text-right" scope="col">Actual</th>
                    <th className="py-2 pr-3 text-right" scope="col">
                      Trend<span className="normal-case font-normal text-muted-foreground/70"> (fcst proxy)</span>
                    </th>
                    <th className="py-2 pr-3 text-right" scope="col">Previous</th>
                    <th className="py-2 text-right" scope="col">vs Trend</th>
                  </tr>
                </thead>
                <tbody>
                  {data.releases.map((r) => (
                    <tr key={r.series_id} className="border-b border-border/40">
                      <td className="py-2 pr-3">
                        <span className="font-medium">{r.name}</span>
                        {r.frequency && (
                          <span className="ml-1.5 text-[10px] text-muted-foreground uppercase">{r.frequency}</span>
                        )}
                      </td>
                      <td className="py-2 pr-3"><Stars n={r.importance} /></td>
                      <td className="py-2 pr-3 text-xs text-muted-foreground tabular-nums">{r.date ?? "—"}</td>
                      <td className="py-2 pr-3 text-right tabular-nums font-medium">{fmtVal(r.actual)}</td>
                      <td className="py-2 pr-3 text-right tabular-nums text-muted-foreground">{fmtVal(r.forecast_trend)}</td>
                      <td className="py-2 pr-3 text-right tabular-nums text-muted-foreground">{fmtVal(r.previous)}</td>
                      <td className={`py-2 text-right text-xs font-semibold ${DIRECTION_STYLE[r.direction]}`}>
                        {r.direction === "inline" ? "in line" : r.direction}
                        {r.surprise_pct != null && r.direction !== "inline" && (
                          <span className="ml-1 font-normal tabular-nums opacity-80">
                            ({r.surprise_pct > 0 ? "+" : ""}{r.surprise_pct.toFixed(1)}%)
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-[11px] text-muted-foreground mt-2">{data.note}</p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
