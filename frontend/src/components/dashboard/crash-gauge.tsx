"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTooltip } from "@/components/info-tooltip";
import type { MarketStatus } from "@/lib/api";

function GaugeArc({ value, max = 100 }: { value: number; max?: number }) {
  const pct = Math.min(value / max, 1);
  const color =
    pct > 0.5 ? "text-red-500" : pct > 0.3 ? "text-amber-500" : "text-emerald-500";

  // SVG semicircle gauge
  const radius = 60;
  const circumference = Math.PI * radius;
  const offset = circumference * (1 - pct);

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 140 80" className="w-40 h-20">
        <path
          d="M 10 70 A 60 60 0 0 1 130 70"
          fill="none"
          stroke="currentColor"
          strokeWidth="10"
          className="text-muted/30"
        />
        <path
          d="M 10 70 A 60 60 0 0 1 130 70"
          fill="none"
          stroke="currentColor"
          strokeWidth="10"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className={color}
        />
      </svg>
      <p className={`-mt-2 text-3xl font-bold tabular-nums ${color}`}>
        {value.toFixed(1)}%
      </p>
    </div>
  );
}

export function CrashGauge({ data }: { data: MarketStatus | null }) {
  if (!data) {
    return (
      <Card>
        <CardHeader><CardTitle>Crash Probability</CardTitle></CardHeader>
        <CardContent className="flex justify-center">
          <Skeleton className="h-28 w-40" />
        </CardContent>
      </Card>
    );
  }

  const probs = data.crash_probabilities;
  const horizons = Object.keys(probs).sort();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
          Crash Probability
          <InfoTooltip
            text="Probability of a 20%+ drawdown from current levels over each time horizon. Produced by LightGBM + Logistic Regression ensemble. This is a risk indicator, not a prediction of when a crash will happen."
            beginnerText="How likely is it that the stock market drops 20% or more? Think of it like a weather forecast for market storms. Higher % = higher risk, but it's not guaranteed to happen."
          />
        </CardTitle>
      </CardHeader>
      <CardContent>
        {horizons.length > 0 ? (
          <div className="flex flex-wrap justify-center gap-6">
            {horizons.map((h) => (
              <div key={h} className="text-center">
                <GaugeArc value={probs[h]} />
                <p className="mt-1 text-xs text-muted-foreground uppercase">{h}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-center text-sm text-muted-foreground">
            Model not trained yet. Run the training script first.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
