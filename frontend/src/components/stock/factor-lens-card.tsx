"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { InfoTooltip } from "@/components/info-tooltip";
import { getFactorDecomposition } from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";

/**
 * Factor Lens (F-018): the presentation the paywalled incumbents dropped —
 * FF5+Momentum loadings WITH t-stats, what each factor actually earned
 * (loading x realized premium), and rolling 1y loadings so regime shifts
 * are visible. Premiums are historical averages over the regression
 * window, never forecasts, and the card says so.
 */

const FACTOR_LABELS: Record<string, string> = {
  "Mkt-RF": "Market",
  SMB: "Size (small-cap)",
  HML: "Value",
  RMW: "Profitability",
  CMA: "Investment",
  Mom: "Momentum",
};

const ROLLING_COLORS: Record<string, string> = {
  "Mkt-RF": "#8884d8",
  Mom: "#f59e0b",
  HML: "#10b981",
};

export function FactorLensCard({ ticker }: { ticker: string }) {
  const { data } = useQuery({
    queryKey: queryKeys.stock.factorLens(ticker),
    queryFn: () => getFactorDecomposition(ticker),
    staleTime: staleTimes.stock,
    retry: 1,
  });

  if (!data || !data.factors) return null;

  const r2pct = data.r_squared != null ? data.r_squared * 100 : null;
  const alphaPct = data.alpha_annual != null ? data.alpha_annual * 100 : null;
  const rolling = data.rolling;
  const rollingRows =
    rolling && Array.isArray(rolling.dates)
      ? rolling.dates.map((d, i) => {
          const row: Record<string, string | number> = { date: d };
          for (const f of Object.keys(ROLLING_COLORS)) {
            const series = rolling[f];
            if (Array.isArray(series) && typeof series[i] === "number") {
              row[f] = series[i] as number;
            }
          }
          return row;
        })
      : [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-medium text-muted-foreground flex items-center">
          Factor Lens (FF5 + Momentum)
          <InfoTooltip text="Which academic factors explain this stock's returns. Loadings from daily OLS; t-stat above ~2 means the exposure is statistically real. 'Earned' = loading x that factor's realized premium over the same window — history, not a forecast." />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-4 text-sm flex-wrap">
          <span className="text-muted-foreground">
            Alpha:{" "}
            <span
              className={`font-bold ${(alphaPct ?? 0) > 0 ? "text-emerald-400" : "text-red-400"}`}
            >
              {alphaPct != null && alphaPct > 0 ? "+" : ""}
              {alphaPct?.toFixed(1)}%/yr
            </span>
            {!data.alpha_significant && (
              <span className="text-xs text-muted-foreground ml-1">
                (not statistically significant)
              </span>
            )}
          </span>
          <span className="text-muted-foreground">
            R²: <span className="font-bold">{r2pct?.toFixed(0)}%</span>
          </span>
          <span className="text-muted-foreground">
            {data.observations} obs
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-muted-foreground border-b border-border/50">
                <th className="text-left py-1 font-medium">Factor</th>
                <th className="text-right py-1 font-medium">Loading</th>
                <th className="text-right py-1 font-medium">t-stat</th>
                <th className="text-right py-1 font-medium">Earned /yr</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.factors).map(([name, f]) => {
                const contrib =
                  f.contribution_annual != null
                    ? f.contribution_annual * 100
                    : null;
                return (
                  <tr key={name} className="border-b border-border/30">
                    <td className="py-1">
                      {FACTOR_LABELS[name] ?? name}
                      {f.significant && (
                        <span className="text-emerald-400 ml-0.5">*</span>
                      )}
                    </td>
                    <td className="text-right tabular-nums">
                      {f.loading.toFixed(2)}
                    </td>
                    <td className="text-right tabular-nums text-muted-foreground">
                      {f.t_stat != null ? f.t_stat.toFixed(1) : "—"}
                    </td>
                    <td
                      className={`text-right tabular-nums ${
                        (contrib ?? 0) > 0
                          ? "text-emerald-400"
                          : contrib != null
                            ? "text-red-400"
                            : ""
                      }`}
                    >
                      {contrib != null
                        ? `${contrib > 0 ? "+" : ""}${contrib.toFixed(1)}%`
                        : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {rollingRows.length >= 4 && (
          <div>
            <p className="text-[11px] text-muted-foreground mb-1">
              Rolling 1-year loadings (monthly steps) — exposures drift;
              a static number hides it:
            </p>
            <div className="h-28">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={rollingRows} margin={{ top: 2, right: 4, bottom: 0, left: -20 }}>
                  <XAxis dataKey="date" tick={{ fontSize: 9 }} minTickGap={40} />
                  <YAxis tick={{ fontSize: 9 }} width={40} />
                  <Tooltip
                    contentStyle={{ fontSize: 11 }}
                    formatter={(v, n) => [
                      typeof v === "number" ? v.toFixed(2) : String(v),
                      FACTOR_LABELS[String(n)] ?? String(n),
                    ]}
                  />
                  {Object.entries(ROLLING_COLORS).map(([f, color]) => (
                    <Line
                      key={f}
                      type="monotone"
                      dataKey={f}
                      stroke={color}
                      dot={false}
                      strokeWidth={1.5}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        <p className="text-[11px] text-muted-foreground">
          * = statistically significant (p &lt; 0.05). Premiums are what each
          factor actually returned over this window — not a prediction.
          Data: Kenneth French Data Library. Educational, not advice.
        </p>
      </CardContent>
    </Card>
  );
}
