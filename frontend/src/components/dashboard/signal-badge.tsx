"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTooltip } from "@/components/info-tooltip";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { MarketSignal } from "@/lib/api";

const ACTION_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  "Strong Buy": { bg: "bg-emerald-500/15", text: "text-emerald-400", border: "border-emerald-500/30" },
  Buy: { bg: "bg-emerald-500/10", text: "text-emerald-400", border: "border-emerald-500/25" },
  Hold: { bg: "bg-amber-500/15", text: "text-amber-400", border: "border-amber-500/30" },
  Sell: { bg: "bg-red-500/10", text: "text-red-400", border: "border-red-500/25" },
  "Strong Sell": { bg: "bg-red-500/15", text: "text-red-400", border: "border-red-500/30" },
};

function ActionIcon({ action }: { action: string }) {
  if (action.includes("Buy")) return <TrendingUp className="h-5 w-5" />;
  if (action.includes("Sell")) return <TrendingDown className="h-5 w-5" />;
  return <Minus className="h-5 w-5" />;
}

export function SignalBadge({ data }: { data: MarketSignal | null }) {
  if (!data) {
    return (
      <Card>
        <CardContent className="p-5">
          <Skeleton className="h-6 w-32 mb-3" />
          <Skeleton className="h-10 w-40 mb-2" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4 mt-1" />
        </CardContent>
      </Card>
    );
  }

  const style = ACTION_STYLES[data.action] ?? ACTION_STYLES.Hold;

  return (
    <Card className={`${style.border} border-2`}>
      <CardContent className="p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-medium text-muted-foreground">
            Market Signal
            <InfoTooltip
              text="Composite signal from 6 factors: crash probability (25%), regime (20%), valuation (15%), momentum (15%), mean reversion (10%), external consensus (15%). Score ranges from -1 (very bearish) to +1 (very bullish)."
              beginnerText="This is our overall market recommendation based on combining multiple indicators — like getting a second opinion from several different doctors. It tells you whether conditions favor buying, holding, or selling."
            />
          </h3>
          <span className="text-xs text-muted-foreground tabular-nums">
            Score: {data.composite_score > 0 ? "+" : ""}{data.composite_score.toFixed(3)}
          </span>
        </div>

        <div className={`inline-flex items-center gap-2 rounded-lg px-4 py-2.5 ${style.bg} ${style.text} font-bold text-2xl`}>
          <ActionIcon action={data.action} />
          {data.action}
        </div>

        <div className="mt-1 mb-3">
          <span className="text-xs text-muted-foreground">
            Confidence: {data.confidence}%
          </span>
          <div className="w-full h-1.5 bg-muted rounded-full mt-1">
            <div
              className={`h-full rounded-full transition-all ${
                data.action.includes("Buy") ? "bg-emerald-500" :
                data.action.includes("Sell") ? "bg-red-500" : "bg-amber-500"
              }`}
              style={{ width: `${Math.min(data.confidence, 100)}%` }}
            />
          </div>
        </div>

        {data.reasons.length > 0 && (
          <ul className="space-y-1">
            {data.reasons.map((reason, i) => (
              <li key={i} className="text-xs text-muted-foreground flex items-start gap-1.5">
                <span className={`mt-0.5 h-1.5 w-1.5 rounded-full shrink-0 ${
                  data.action.includes("Buy") ? "bg-emerald-400" :
                  data.action.includes("Sell") ? "bg-red-400" : "bg-amber-400"
                }`} />
                {reason}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
