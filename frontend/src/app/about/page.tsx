"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { InfoTooltip } from "@/components/info-tooltip";

const METHODOLOGY = [
  {
    title: "Monte Carlo Simulation",
    description: "Jump-diffusion model (Merton 1976) with GJR-GARCH(1,1) stochastic volatility and 3-state Hidden Markov Model regime blending. 10,000 paths across 7 probability-weighted scenarios.",
    details: [
      "Variance drag correctly accounted for (geometric drift, no double-counting Ito correction)",
      "Merton jump compensator ensures E[S_T] = S0 * exp(mu * T) even with jumps",
      "Return cap at 300% over 5 years prevents unrealistic outliers",
      "Mean reversion activated when prices deviate 20%+ from fair value",
    ],
  },
  {
    title: "Crash Prediction",
    description: "LightGBM + Logistic Regression ensemble (70/30 blend) with isotonic calibration. 25-30 features selected via LASSO from 208 candidates.",
    details: [
      "3-month, 6-month, and 12-month horizons",
      "Walk-forward backtesting with zero data leakage",
      "Target: Brier Score ≤ 0.05 (random = 0.25, climatology ~0.12)",
      "Crash defined as 20%+ drawdown from recent peak",
    ],
  },
  {
    title: "Risk Scoring",
    description: "9-factor composite z-score combining VIX, yield curve, credit spreads, momentum exhaustion, short-term volatility, gold/stock ratio, market breadth, and small-cap divergence.",
    details: [
      "Range: -4 (very low risk) to +4 (extreme risk)",
      "Above 2.0 = elevated stress, triggers scenario weight adjustments",
      "Factors weighted by historical predictive power",
    ],
  },
  {
    title: "Regime Detection",
    description: "Multi-check regime classification (Bull/Bear/Volatile/Neutral) validated against 200-day SMA, market breadth, and institutional consensus.",
    details: [
      "Prevents false bear signals during temporary corrections",
      "Regime feeds into Monte Carlo scenario weights and drift adjustments",
    ],
  },
];

const LIMITATIONS = [
  "All predictions are probabilistic estimates with significant uncertainty",
  "Past performance does not guarantee future results",
  "Model assumes stationarity that may not hold during structural breaks",
  "Crash prediction has limited positive predictive power (rare events are inherently hard to predict)",
  "Yahoo Finance data may have gaps, especially for smaller or international tickers",
  "FRED data updates with lag (some series are monthly or quarterly)",
  "Jump-diffusion model cannot capture all market dynamics (correlations, sector contagion)",
  "No transaction costs, taxes, or slippage modeled",
];

const CHART_GUIDE = [
  { name: "Fan Charts", description: "Width shows uncertainty. The blue line is the median (50th percentile). Shaded bands show 5th-25th-75th-95th percentile ranges. Wider bands = more uncertainty." },
  { name: "SHAP Waterfall", description: "Red bars push crash probability UP (more risk). Green bars push it DOWN (less risk). Length shows magnitude of impact. Features sorted by absolute importance." },
  { name: "Sector Heatmap", description: "Color intensity shows expected return magnitude. Greener = higher expected return. Red = negative expected return. Based on Monte Carlo with sector-specific parameters." },
  { name: "Crash Gauges", description: "Semicircle gauge showing crash probability. Green (0-15%) = low risk, Yellow (15-30%) = moderate, Amber (30-50%) = elevated, Red (50%+) = high. Probabilities should increase with time horizon (3m < 6m < 12m)." },
  { name: "Correlation Matrix", description: "Red (>0.7) = highly correlated (move together, less diversification). Green (0-0.4) = moderate. Blue (<0) = negatively correlated (good for diversification)." },
];

export default function AboutPage() {
  return (
    <div className="space-y-8 animate-slide-up max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">About Aegis Finance</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Methodology, chart reading guide, known limitations, and credits
        </p>
      </div>

      {/* Methodology */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold">Methodology</h2>
        {METHODOLOGY.map((m) => (
          <Card key={m.title}>
            <CardHeader>
              <CardTitle className="text-sm font-medium">{m.title}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">{m.description}</p>
              <ul className="space-y-1">
                {m.details.map((d, i) => (
                  <li key={i} className="text-xs text-muted-foreground flex gap-2">
                    <span className="text-primary shrink-0">-</span>
                    {d}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Chart Reading Guide */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold">How to Read the Charts</h2>
        <Card>
          <CardContent className="p-4 space-y-4">
            {CHART_GUIDE.map((c) => (
              <div key={c.name}>
                <p className="text-sm font-medium">{c.name}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{c.description}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Limitations */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold">Known Limitations</h2>
        <Card>
          <CardContent className="p-4">
            <ul className="space-y-2">
              {LIMITATIONS.map((l, i) => (
                <li key={i} className="text-sm text-muted-foreground flex gap-2">
                  <span className="text-amber-400 shrink-0">-</span>
                  {l}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      {/* Data Sources */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold">Data Sources</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Card>
            <CardContent className="p-4">
              <p className="text-sm font-medium">Yahoo Finance</p>
              <p className="text-xs text-muted-foreground mt-1">
                Prices, VIX, sector ETFs, treasuries, analyst targets, fundamentals. Updated hourly (cached).
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-sm font-medium">FRED (Federal Reserve)</p>
              <p className="text-xs text-muted-foreground mt-1">
                22+ macro series: yield curve, unemployment, CPI, NFCI, initial claims, LEI, SLOOS. Cached 24hr.
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-sm font-medium">GDELT</p>
              <p className="text-xs text-muted-foreground mt-1">
                Global event tone, volume, conflict scores for news intelligence. On request.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Credits */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold">Credits</h2>
        <Card>
          <CardContent className="p-4 space-y-2">
            <p className="text-sm text-muted-foreground">
              Built by <span className="text-foreground font-medium">Murathan</span> as a research project combining quantitative finance with modern web development.
            </p>
            <div className="flex flex-wrap gap-2 mt-3">
              <Badge variant="outline">Next.js 14</Badge>
              <Badge variant="outline">FastAPI</Badge>
              <Badge variant="outline">LightGBM</Badge>
              <Badge variant="outline">SHAP</Badge>
              <Badge variant="outline">GJR-GARCH</Badge>
              <Badge variant="outline">HMM</Badge>
              <Badge variant="outline">shadcn/ui</Badge>
              <Badge variant="outline">Recharts</Badge>
              <Badge variant="outline">Tailwind CSS</Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-3">
              Open source under the MIT License.
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Disclaimer */}
      <Card className="border-amber-500/20 bg-amber-500/5">
        <CardContent className="p-4">
          <p className="text-sm font-medium text-amber-400">Disclaimer</p>
          <p className="text-xs text-amber-400/80 mt-1">
            Aegis Finance is an educational tool. It is not financial advice. All predictions are probabilistic estimates with significant uncertainty. Past performance does not guarantee future results. Always consult a qualified financial advisor before making investment decisions.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
