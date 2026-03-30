"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTooltip } from "@/components/info-tooltip";
import type { MarketStatus } from "@/lib/api";

type Mood = "Extreme Fear" | "Fear" | "Caution" | "Neutral" | "Optimism" | "Greed";

interface MoodInfo {
  label: Mood;
  color: string;
  emoji: string;
}

/**
 * Compute a market mood from risk_score, regime, and vix.
 * Risk score range: -4 (low risk) to +4 (extreme risk).
 * Higher composite = more fear.
 */
function computeMood(riskScore: number, regime: string, vix: number | null): MoodInfo {
  // Composite: risk_score is primary, VIX and regime add bias
  let composite = riskScore;

  // VIX contribution: 16 is baseline, scale above/below
  if (vix != null) {
    composite += (vix - 18) / 12; // vix=30 adds ~1, vix=12 subtracts ~0.5
  }

  // Regime nudge
  if (regime === "Bull") composite -= 0.5;
  if (regime === "Bear") composite += 0.5;
  if (regime === "Volatile") composite += 0.3;

  if (composite >= 3) return { label: "Extreme Fear", color: "text-red-500 bg-red-500/15 border-red-500/30", emoji: "!!" };
  if (composite >= 1.5) return { label: "Fear", color: "text-red-400 bg-red-500/10 border-red-500/25", emoji: "!" };
  if (composite >= 0.5) return { label: "Caution", color: "text-amber-400 bg-amber-500/10 border-amber-500/25", emoji: "~" };
  if (composite >= -0.5) return { label: "Neutral", color: "text-blue-400 bg-blue-500/10 border-blue-500/25", emoji: "-" };
  if (composite >= -1.5) return { label: "Optimism", color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/25", emoji: "+" };
  return { label: "Greed", color: "text-emerald-500 bg-emerald-500/15 border-emerald-500/30", emoji: "++" };
}

const REGIME_COLORS: Record<string, string> = {
  Bull: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  Neutral: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  Bear: "bg-red-500/15 text-red-400 border-red-500/30",
  Volatile: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  Unknown: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
};

export function MarketBanner({ data }: { data: MarketStatus | null }) {
  if (!data) {
    return (
      <Card>
        <CardContent className="flex flex-wrap gap-6 p-4">
          <Skeleton className="h-16 w-48" />
          <Skeleton className="h-16 w-32" />
          <Skeleton className="h-16 w-32" />
          <Skeleton className="h-16 w-32" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-4 p-4">
        <div>
          <p className="text-sm text-muted-foreground uppercase tracking-wide">S&P 500</p>
          <p className="text-3xl font-bold tabular-nums">{data.sp500.toLocaleString(undefined, { maximumFractionDigits: 0 })}</p>
          <p className={`text-sm font-medium ${data.sp500_change_1m >= 0 ? "text-emerald-400" : "text-red-400"}`}>
            {data.sp500_change_1m >= 0 ? "+" : ""}{data.sp500_change_1m}% (1M)
          </p>
        </div>

        <div>
          <p className="text-sm text-muted-foreground uppercase tracking-wide flex items-center">
            Regime
            <InfoTooltip text="Market regime detected by analyzing price trends, volatility, and risk indicators. Bull = sustained uptrend, Bear = sustained downtrend, Volatile = high uncertainty." />
          </p>
          <Badge variant="outline" className={REGIME_COLORS[data.regime] || REGIME_COLORS.Unknown}>
            {data.regime}
          </Badge>
        </div>

        <div>
          <p className="text-sm text-muted-foreground uppercase tracking-wide flex items-center">
            VIX
            <InfoTooltip text="CBOE Volatility Index — measures expected 30-day S&P 500 volatility. Below 16 = calm, 16-25 = normal, above 25 = elevated fear." />
          </p>
          <p className="text-2xl font-bold tabular-nums">{data.vix?.toFixed(1) ?? "N/A"}</p>
        </div>

        <div>
          <p className="text-sm text-muted-foreground uppercase tracking-wide flex items-center">
            Risk Score
            <InfoTooltip text="9-factor composite z-score combining VIX, yield curve, credit spreads, momentum, and more. Range: -4 (low risk) to +4 (extreme risk). Above 2.0 = elevated stress." />
          </p>
          <p className={`text-2xl font-bold tabular-nums ${data.risk_score > 2 ? "text-red-400" : data.risk_score > 1 ? "text-amber-400" : "text-emerald-400"}`}>
            {data.risk_score.toFixed(2)}
          </p>
        </div>

        <div>
          <p className="text-sm text-muted-foreground uppercase tracking-wide flex items-center">
            Yield Curve
            <InfoTooltip text="10Y-3M Treasury spread. Negative (inverted) = historically a recession predictor. Positive = normal economic expansion signal." />
          </p>
          <p className={`text-2xl font-bold tabular-nums ${(data.yield_curve ?? 0) < 0 ? "text-red-400" : "text-emerald-400"}`}>
            {data.yield_curve?.toFixed(2) ?? "N/A"}%
          </p>
        </div>

        {/* Market Mood */}
        {(() => {
          const mood = computeMood(data.risk_score, data.regime, data.vix);
          return (
            <div>
              <p className="text-sm text-muted-foreground uppercase tracking-wide flex items-center">
                Market Mood
                <InfoTooltip text="Composite sentiment derived from the 9-factor risk score, VIX level, and detected regime. Ranges from Extreme Fear to Greed." />
              </p>
              <Badge variant="outline" className={mood.color}>
                {mood.label}
              </Badge>
            </div>
          );
        })()}

        {data.net_liquidity && data.net_liquidity.net_liquidity != null && (
          <div>
            <p className="text-sm text-muted-foreground uppercase tracking-wide flex items-center">
              Net Liquidity
              <InfoTooltip text="Fed balance sheet (WALCL) minus Treasury General Account minus Reverse Repo. Rising liquidity is generally bullish for equities." />
            </p>
            <p className="text-2xl font-bold tabular-nums">
              ${data.net_liquidity.net_liquidity.toFixed(2)}T
            </p>
            <p className={`text-xs font-medium ${data.net_liquidity.signal === "BULLISH" ? "text-emerald-400" : data.net_liquidity.signal === "BEARISH" ? "text-red-400" : "text-zinc-400"}`}>
              {data.net_liquidity.signal}
            </p>
          </div>
        )}

        <div className="ml-auto text-right">
          {data.data_quality && (
            <Badge
              variant="outline"
              className={
                data.data_quality.status === "healthy"
                  ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30 mb-1"
                  : data.data_quality.status === "warning"
                    ? "bg-amber-500/15 text-amber-400 border-amber-500/30 mb-1"
                    : "bg-red-500/15 text-red-400 border-red-500/30 mb-1"
              }
            >
              Data: {data.data_quality.status}
            </Badge>
          )}
          <p className="text-xs text-muted-foreground">Last updated</p>
          <p className="text-sm">{data.last_updated}</p>
        </div>
      </CardContent>
    </Card>
  );
}
