"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { InfoTooltip } from "@/components/info-tooltip";
import { getStockTwoSided } from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";

/**
 * Bull/bear two-sided card: AI prose arguing BOTH sides of the computed
 * signal. The numbers on this page never come from the AI — it writes
 * around them. Renders nothing when the LLM is unkeyed/capped (disclosed
 * absence beats a fabricated card).
 */
export function TwoSidedCard({ ticker }: { ticker: string }) {
  const { data } = useQuery({
    queryKey: queryKeys.stock.twoSided(ticker),
    queryFn: () => getStockTwoSided(ticker),
    staleTime: staleTimes.simulation, // 1h — backend caches 6h
    retry: 1,
  });

  if (!data || data.status !== "ok") return null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          Two-Sided View
          <InfoTooltip
            text="An AI argues the strongest honest case on each side of the computed signal, grounded only in the signal's own components. The numeric signal is unchanged by this prose — and it never contains advice."
            beginnerText="Every market call has two sides. This shows the best argument FOR what the model sees and the best argument AGAINST it — because a single confident story is how people get fooled."
          />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="rounded-lg border border-emerald-500/25 bg-emerald-500/5 p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-emerald-400 mb-1">
              The bull case
            </p>
            <p className="text-sm leading-relaxed">{data.bull_case}</p>
          </div>
          <div className="rounded-lg border border-red-500/25 bg-red-500/5 p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-red-400 mb-1">
              The bear case
            </p>
            <p className="text-sm leading-relaxed">{data.bear_case}</p>
          </div>
        </div>
        {data.watch_for && (
          <p className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">What would change the picture:</span>{" "}
            {data.watch_for}
          </p>
        )}
        <p className="text-[11px] text-muted-foreground border-t border-border/50 pt-2">
          AI-written prose ({data.provider}) around the computed signal
          {data.signal_action ? ` (${data.signal_action})` : ""} — the numbers
          never come from the AI. Educational, not financial advice.
        </p>
      </CardContent>
    </Card>
  );
}
