"use client";

import { use } from "react";
import Link from "next/link";
import { useApi } from "@/hooks/use-api";
import { getStockAnalysis, getStockShap } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { InfoTooltip } from "@/components/info-tooltip";
import { ErrorCard } from "@/components/error-card";
import { DisclaimerBanner } from "@/components/disclaimer-banner";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine,
  AreaChart, Area, LineChart, Line,
} from "recharts";
import type { StockAnalysis } from "@/lib/api";

function MetricCard({ label, value, suffix, color, tooltip }: { label: string; value: string | number; suffix?: string; color?: string; tooltip?: string }) {
  return (
    <div className="rounded-lg bg-muted/30 p-3">
      <p className="text-[10px] text-muted-foreground uppercase tracking-wide flex items-center">
        {label}
        {tooltip && <InfoTooltip text={tooltip} />}
      </p>
      <p className={`text-lg font-bold tabular-nums ${color || ""}`}>
        {value}{suffix}
      </p>
    </div>
  );
}

function PriceHistoryChart({ data }: { data: { date: string; price: number }[] }) {
  // Sample down for display if too many points
  const step = data.length > 200 ? Math.floor(data.length / 200) : 1;
  const chartData = data.filter((_, i) => i % step === 0 || i === data.length - 1);

  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
        <XAxis
          dataKey="date"
          tick={{ fill: "#888", fontSize: 10 }}
          tickFormatter={(v) => v.slice(0, 7)}
          minTickGap={60}
        />
        <YAxis
          tick={{ fill: "#888", fontSize: 11 }}
          tickFormatter={(v: number) => `$${v.toFixed(0)}`}
          domain={["auto", "auto"]}
        />
        <Tooltip
          contentStyle={{ backgroundColor: "#1e1e2e", border: "1px solid #333", borderRadius: 8 }}
          formatter={(v) => [`$${Number(v).toFixed(2)}`, "Price"]}
          labelFormatter={(l) => l}
        />
        <Area type="monotone" dataKey="price" stroke="#63b4ff" fill="#63b4ff" fillOpacity={0.1} strokeWidth={1.5} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function KeyStatsGrid({ stats, currentPrice }: { stats: Record<string, number | null>; currentPrice: number }) {
  const fmt = (v: number | null | undefined, type: "pct" | "dollar" | "ratio" | "bignum" = "ratio") => {
    if (v == null) return "N/A";
    if (type === "pct") return `${(v * 100).toFixed(1)}%`;
    if (type === "dollar") return v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : v >= 1e6 ? `$${(v / 1e6).toFixed(0)}M` : `$${v.toFixed(0)}`;
    if (type === "bignum") return v >= 1e9 ? `${(v / 1e9).toFixed(1)}B` : v >= 1e6 ? `${(v / 1e6).toFixed(0)}M` : v.toFixed(0);
    return v.toFixed(2);
  };

  const items = [
    { label: "P/E (Trailing)", value: fmt(stats.pe_trailing), tooltip: "Price-to-Earnings ratio using trailing 12-month earnings" },
    { label: "P/E (Forward)", value: fmt(stats.pe_forward), tooltip: "Price-to-Earnings ratio using forward estimated earnings" },
    { label: "P/B Ratio", value: fmt(stats.price_to_book), tooltip: "Price-to-Book ratio. Below 1 may indicate undervaluation" },
    { label: "P/S Ratio", value: fmt(stats.price_to_sales), tooltip: "Price-to-Sales ratio. Lower is generally better" },
    { label: "EV/EBITDA", value: fmt(stats.ev_to_ebitda), tooltip: "Enterprise Value to EBITDA. Common valuation metric" },
    { label: "Div Yield", value: stats.dividend_yield != null ? `${stats.dividend_yield.toFixed(2)}%` : "N/A", tooltip: "Annual dividend yield" },
    { label: "ROE", value: stats.roe != null ? `${(stats.roe * 100).toFixed(1)}%` : "N/A", tooltip: "Return on Equity — how effectively the company uses shareholders' equity" },
    { label: "Profit Margin", value: stats.profit_margin != null ? `${(stats.profit_margin * 100).toFixed(1)}%` : "N/A", tooltip: "Net profit margin" },
    { label: "Revenue", value: fmt(stats.revenue, "dollar"), tooltip: "Total revenue (trailing 12 months)" },
    { label: "Free Cash Flow", value: fmt(stats.free_cash_flow, "dollar"), tooltip: "Free cash flow (trailing 12 months)" },
    { label: "D/E Ratio", value: stats.debt_to_equity != null ? `${stats.debt_to_equity.toFixed(0)}%` : "N/A", tooltip: "Debt-to-Equity ratio. Higher = more leveraged" },
    { label: "52W Range", value: stats.low_52w != null && stats.high_52w != null ? `$${stats.low_52w.toFixed(0)} - $${stats.high_52w.toFixed(0)}` : "N/A", tooltip: "52-week price range (low - high)" },
  ];

  const returnItems = [
    { label: "1M Return", value: stats.return_1m, tooltip: "Price return over the last month" },
    { label: "3M Return", value: stats.return_3m, tooltip: "Price return over the last 3 months" },
    { label: "6M Return", value: stats.return_6m, tooltip: "Price return over the last 6 months" },
    { label: "1Y Return", value: stats.return_1y, tooltip: "Price return over the last year" },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {items.map((item) => (
          <div key={item.label} className="rounded-lg bg-muted/30 p-2.5">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wide flex items-center">
              {item.label}
              {item.tooltip && <InfoTooltip text={item.tooltip} />}
            </p>
            <p className="text-sm font-semibold tabular-nums">{item.value}</p>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-4 gap-3">
        {returnItems.map((item) => (
          <div key={item.label} className="rounded-lg bg-muted/30 p-2.5 text-center">
            <p className="text-[10px] text-muted-foreground uppercase">{item.label}</p>
            <p className={`text-sm font-bold tabular-nums ${item.value != null ? (item.value >= 0 ? "text-emerald-400" : "text-red-400") : ""}`}>
              {item.value != null ? `${item.value >= 0 ? "+" : ""}${item.value.toFixed(1)}%` : "N/A"}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

function AnalystVsModelCard({ stock }: { stock: StockAnalysis }) {
  const targets = stock.analyst_targets;
  if (!targets || targets.mean == null) return null;

  const analystReturn = ((targets.mean / stock.current_price) - 1) * 100;
  const modelReturn = stock.median_return;
  const diff = modelReturn - analystReturn;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
          Analyst vs Model Comparison
          <InfoTooltip text="Compares Wall Street analyst consensus price target (12-month) with our Monte Carlo model's 5-year median projection. Different time horizons and methodologies." />
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-6">
          <div className="text-center space-y-2">
            <p className="text-xs text-muted-foreground uppercase">Analyst Target (12M)</p>
            <p className="text-2xl font-bold tabular-nums">${targets.mean.toFixed(0)}</p>
            <p className={`text-sm font-medium tabular-nums ${analystReturn >= 0 ? "text-emerald-400" : "text-red-400"}`}>
              {analystReturn >= 0 ? "+" : ""}{analystReturn.toFixed(1)}% upside
            </p>
            <div className="text-xs text-muted-foreground">
              Range: ${targets.low?.toFixed(0) ?? "?"} — ${targets.high?.toFixed(0) ?? "?"}
            </div>
          </div>
          <div className="text-center space-y-2">
            <p className="text-xs text-muted-foreground uppercase">MC Model (5Y Median)</p>
            <p className="text-2xl font-bold tabular-nums">{modelReturn >= 0 ? "+" : ""}{modelReturn.toFixed(1)}%</p>
            <p className="text-sm text-muted-foreground">
              ~{(modelReturn / 5).toFixed(1)}%/yr annualized
            </p>
            <div className="text-xs text-muted-foreground">
              5th: ${stock.p05_price.toFixed(0)} — 95th: ${stock.p95_price.toFixed(0)}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ShapWaterfall({ features }: { features: { feature: string; shap_value: number; feature_value: number | null }[] }) {
  const data = features.slice(0, 12).map((f) => ({
    name: f.feature.replace(/_/g, " "),
    value: f.shap_value,
    raw: f.feature_value,
  }));

  return (
    <ResponsiveContainer width="100%" height={Math.max(280, data.length * 28)}>
      <BarChart data={data} layout="vertical" margin={{ left: 120, right: 20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
        <XAxis type="number" tick={{ fill: "#888", fontSize: 11 }} />
        <YAxis type="category" dataKey="name" tick={{ fill: "#aaa", fontSize: 11 }} width={110} />
        <Tooltip
          contentStyle={{ backgroundColor: "#1e1e2e", border: "1px solid #333", borderRadius: 8 }}
          formatter={(v, _name, props) => {
            const raw = props.payload.raw;
            return [
              `SHAP: ${Number(v).toFixed(4)}${raw != null ? ` | Value: ${raw.toFixed(2)}` : ""}`,
              "",
            ];
          }}
        />
        <ReferenceLine x={0} stroke="#555" />
        <Bar dataKey="value" radius={[0, 4, 4, 0]}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.value > 0 ? "#ef4444" : "#22c55e"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function PriceExpectations({ stock }: { stock: StockAnalysis }) {
  const targets = stock.analyst_targets;
  if (!targets || targets.low == null || targets.high == null) return null;

  const current = stock.current_price;
  const low = targets.low;
  const mean = targets.mean ?? targets.median ?? current;
  const high = targets.high;

  const quarters = [
    { label: "Current", bull: current, base: current, bear: current },
    { label: "Q1", bull: current + (high - current) * 0.25, base: current + (mean - current) * 0.25, bear: current + (low - current) * 0.25 },
    { label: "Q2", bull: current + (high - current) * 0.50, base: current + (mean - current) * 0.50, bear: current + (low - current) * 0.50 },
    { label: "Q3", bull: current + (high - current) * 0.75, base: current + (mean - current) * 0.75, bear: current + (low - current) * 0.75 },
    { label: "Q4 (Target)", bull: high, base: mean, bear: low },
  ];

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
            12-Month Price Expectations
            <InfoTooltip text="Bull/Base/Bear cases derived from analyst price targets. Shows interpolated quarterly paths from current price to each target." />
          </CardTitle>
          <div className="flex gap-2">
            <Badge variant="outline" className="text-xs text-emerald-400 border-emerald-400/30">Bull: ${high.toFixed(0)}</Badge>
            <Badge variant="outline" className="text-xs text-blue-400 border-blue-400/30">Base: ${mean.toFixed(0)}</Badge>
            <Badge variant="outline" className="text-xs text-red-400 border-red-400/30">Bear: ${low.toFixed(0)}</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart data={quarters}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis dataKey="label" tick={{ fill: "#888", fontSize: 11 }} />
            <YAxis tick={{ fill: "#888", fontSize: 11 }} tickFormatter={(v) => `$${v.toFixed(0)}`} domain={["auto", "auto"]} />
            <Tooltip
              contentStyle={{ backgroundColor: "#1e1e2e", border: "1px solid #333", borderRadius: 8 }}
              formatter={(v) => [`$${Number(v).toFixed(2)}`, ""]}
            />
            <ReferenceLine y={current} stroke="#666" strokeDasharray="3 3" />
            <Area type="monotone" dataKey="bull" stroke="#22c55e" fill="#22c55e" fillOpacity={0.08} name="Bull Case" />
            <Area type="monotone" dataKey="base" stroke="#63b4ff" fill="#63b4ff" fillOpacity={0.12} name="Base Case" />
            <Area type="monotone" dataKey="bear" stroke="#ef4444" fill="#ef4444" fillOpacity={0.08} name="Bear Case" />
          </AreaChart>
        </ResponsiveContainer>
        <div className="flex justify-between mt-2 text-xs text-muted-foreground">
          <span>Current: ${current.toFixed(2)}</span>
          <span>
            Upside: {((mean / current - 1) * 100).toFixed(1)}% (base) | {((high / current - 1) * 100).toFixed(1)}% (bull)
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

function AnalystConsensus({ recommendations }: { recommendations: { strongBuy: number; buy: number; hold: number; sell: number; strongSell: number } }) {
  const data = [
    { name: "Strong Buy", value: recommendations.strongBuy, color: "#22c55e" },
    { name: "Buy", value: recommendations.buy, color: "#4ade80" },
    { name: "Hold", value: recommendations.hold, color: "#f59e0b" },
    { name: "Sell", value: recommendations.sell, color: "#f97316" },
    { name: "Strong Sell", value: recommendations.strongSell, color: "#ef4444" },
  ];

  const total = data.reduce((s, d) => s + d.value, 0);
  if (total === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
          Analyst Consensus ({total} analysts)
          <InfoTooltip text="Distribution of analyst recommendations. Shows how many analysts rate this stock as Strong Buy, Buy, Hold, Sell, or Strong Sell." />
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={data} layout="vertical" margin={{ left: 80 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis type="number" tick={{ fill: "#888", fontSize: 11 }} />
            <YAxis type="category" dataKey="name" tick={{ fill: "#aaa", fontSize: 11 }} width={75} />
            <Tooltip
              contentStyle={{ backgroundColor: "#1e1e2e", border: "1px solid #333", borderRadius: 8 }}
              formatter={(v) => [v, "Analysts"]}
            />
            <Bar dataKey="value" radius={[0, 4, 4, 0]}>
              {data.map((d, i) => (
                <Cell key={i} fill={d.color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

export default function StockDetailPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = use(params);
  const upperTicker = ticker.toUpperCase();

  const stock = useApi(() => getStockAnalysis(upperTicker), [upperTicker]);
  const shap = useApi(() => getStockShap(upperTicker), [upperTicker]);

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="flex items-center gap-3">
        <Link href="/stock">
          <Button variant="ghost" size="icon"><ArrowLeft className="h-4 w-4" /></Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{upperTicker}</h1>
          {stock.data && (
            <p className="text-sm text-muted-foreground">{stock.data.name} | {stock.data.sector}</p>
          )}
        </div>
        {stock.data && (
          <Badge variant="outline" className="ml-auto text-xs">{stock.data.cap_tier} cap</Badge>
        )}
      </div>

      <DisclaimerBanner />

      {stock.loading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <Card key={i}><CardContent className="p-3"><Skeleton className="h-14 w-full" /></CardContent></Card>
          ))}
        </div>
      ) : stock.data ? (
        <>
          {/* Key Metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <MetricCard label="Current Price" value={`$${stock.data.current_price.toFixed(2)}`} />
            <MetricCard label="Expected Return (5Y)" value={`${stock.data.expected_return >= 0 ? "+" : ""}${stock.data.expected_return.toFixed(1)}`} suffix="%" color={stock.data.expected_return >= 0 ? "text-emerald-400" : "text-red-400"} tooltip="Mean return across all Monte Carlo simulations over 5 years" />
            <MetricCard label="Median Return" value={`${stock.data.median_return >= 0 ? "+" : ""}${stock.data.median_return.toFixed(1)}`} suffix="%" tooltip="50th percentile return. More robust to outliers than the mean" />
            <MetricCard label="Volatility" value={stock.data.volatility.toFixed(1)} suffix="%" tooltip="Annualized historical volatility. Higher = more price swings" />
            <MetricCard label="Beta" value={stock.data.beta.toFixed(2)} tooltip="Sensitivity to market moves. Beta > 1 = amplifies market swings" />
            <MetricCard label="Sharpe Ratio" value={stock.data.sharpe.toFixed(2)} color={stock.data.sharpe > 0.5 ? "text-emerald-400" : stock.data.sharpe > 0 ? "text-amber-400" : "text-red-400"} tooltip="Risk-adjusted return. Above 0.5 = decent, above 1.0 = excellent" />
            <MetricCard label="P(Loss) 5Y" value={stock.data.prob_loss_5y.toFixed(1)} suffix="%" color={stock.data.prob_loss_5y > 30 ? "text-red-400" : "text-emerald-400"} tooltip="Probability of negative total return over 5 years from Monte Carlo" />
            <MetricCard label="Avg Max Drawdown" value={stock.data.avg_max_drawdown.toFixed(1)} suffix="%" color="text-red-400" tooltip="Average worst peak-to-trough decline across all simulations" />
          </div>

          {/* Price History Chart */}
          {stock.data.price_history && stock.data.price_history.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
                  Price History (5Y)
                  <InfoTooltip text="Historical closing prices over the last 5 years. This is the data used to calibrate the Monte Carlo simulation for this stock." />
                </CardTitle>
              </CardHeader>
              <CardContent>
                <PriceHistoryChart data={stock.data.price_history} />
              </CardContent>
            </Card>
          )}

          {/* Price Range */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
                5-Year Price Range (Monte Carlo)
                <InfoTooltip text="5th and 95th percentile prices from Monte Carlo simulation. The white dot shows the current price position within the range." />
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-4">
                <div className="text-center">
                  <p className="text-xs text-muted-foreground">5th</p>
                  <p className="text-lg font-bold text-red-400">${stock.data.p05_price.toFixed(0)}</p>
                </div>
                <div className="flex-1 h-3 bg-gradient-to-r from-red-500/30 via-blue-500/30 to-emerald-500/30 rounded-full relative">
                  <div
                    className="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-white rounded-full border-2 border-primary"
                    style={{
                      left: `${Math.min(100, Math.max(0, ((stock.data.current_price - stock.data.p05_price) / (stock.data.p95_price - stock.data.p05_price)) * 100))}%`,
                    }}
                  />
                </div>
                <div className="text-center">
                  <p className="text-xs text-muted-foreground">95th</p>
                  <p className="text-lg font-bold text-emerald-400">${stock.data.p95_price.toFixed(0)}</p>
                </div>
              </div>
              <div className="flex justify-between mt-2">
                <p className="text-xs text-muted-foreground">
                  PE: {stock.data.pe_ratio?.toFixed(1) ?? "N/A"} | Analyst Target: ${stock.data.analyst_target?.toFixed(0) ?? "N/A"}
                </p>
                <p className="text-xs text-muted-foreground">
                  Drift: {stock.data.capped_drift.toFixed(1)}% (capped from {stock.data.hist_drift.toFixed(1)}%)
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Analyst vs Model Comparison */}
          <AnalystVsModelCard stock={stock.data} />

          {/* Key Statistics */}
          {stock.data.key_stats && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
                  Key Statistics
                  <InfoTooltip text="Fundamental statistics from Yahoo Finance. Valuation ratios, profitability metrics, and recent returns." />
                </CardTitle>
              </CardHeader>
              <CardContent>
                <KeyStatsGrid stats={stock.data.key_stats} currentPrice={stock.data.current_price} />
              </CardContent>
            </Card>
          )}
        </>
      ) : stock.error ? (
        <ErrorCard title={`Could not analyze ${upperTicker}`} message={stock.error} onRetry={stock.refetch} />
      ) : null}

      {/* Price Expectations */}
      {stock.data?.analyst_targets && (
        <PriceExpectations stock={stock.data} />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Analyst Recommendations */}
        {stock.data?.recommendations && (
          <AnalystConsensus recommendations={stock.data.recommendations} />
        )}

        {/* Earnings */}
        {stock.data?.earnings && (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
                Earnings
                <InfoTooltip text="Upcoming earnings date, EPS estimate, and recent earnings surprise history." />
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {stock.data.earnings.next_date && (
                  <div className="rounded-lg bg-muted/30 p-3">
                    <p className="text-[10px] text-muted-foreground uppercase">Next Earnings</p>
                    <p className="text-sm font-bold">{stock.data.earnings.next_date}</p>
                  </div>
                )}
                {stock.data.earnings.estimate !== null && (
                  <div className="rounded-lg bg-muted/30 p-3">
                    <p className="text-[10px] text-muted-foreground uppercase">EPS Estimate</p>
                    <p className="text-sm font-bold">${stock.data.earnings.estimate.toFixed(2)}</p>
                  </div>
                )}
                {stock.data.earnings.surprise_history.length > 0 && (
                  <div className="rounded-lg bg-muted/30 p-3">
                    <p className="text-[10px] text-muted-foreground uppercase">Last Surprise</p>
                    <p className={`text-sm font-bold ${stock.data.earnings.surprise_history[0] >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {stock.data.earnings.surprise_history[0] >= 0 ? "+" : ""}{stock.data.earnings.surprise_history[0].toFixed(1)}%
                    </p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Peer Comparison */}
      {stock.data?.peers && stock.data.peers.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
              Sector Peers ({stock.data.sector})
              <InfoTooltip text="Other stocks in the same sector. Click to analyze any peer." />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {stock.data.peers.map((peer) => (
                <Link key={peer} href={`/stock/${peer}`}>
                  <Button variant="outline" size="sm" className="text-xs">
                    {peer}
                  </Button>
                </Link>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Top Holders */}
      {stock.data?.holders?.top_holders && stock.data.holders.top_holders.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
                Top Institutional Holders
                <InfoTooltip text="Largest institutional shareholders. High institutional ownership often indicates confidence from professional investors." />
              </CardTitle>
              <div className="flex gap-2">
                {stock.data.holders.insider_pct && (
                  <Badge variant="outline" className="text-xs">Insiders: {stock.data.holders.insider_pct}</Badge>
                )}
                {stock.data.holders.institution_pct && (
                  <Badge variant="outline" className="text-xs">Institutions: {stock.data.holders.institution_pct}</Badge>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-muted-foreground">
                    <th className="py-2 pr-4">Holder</th>
                    <th className="py-2 pr-4 text-right">Shares</th>
                    <th className="py-2 text-right">% Outstanding</th>
                  </tr>
                </thead>
                <tbody>
                  {stock.data.holders.top_holders.map((h, i) => (
                    <tr key={i} className="border-b border-border/30 hover:bg-muted/20 transition-colors">
                      <td className="py-2 pr-4 text-sm">{h.name}</td>
                      <td className="py-2 pr-4 text-right tabular-nums">{h.shares.toLocaleString()}</td>
                      <td className="py-2 text-right tabular-nums">{(h.pct * 100).toFixed(2)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* News */}
      {stock.data?.news && stock.data.news.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Recent News</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {stock.data.news.map((item, i) => (
              <div key={i} className="py-2 border-b border-border/30 last:border-0">
                {item.link ? (
                  <a href={item.link} target="_blank" rel="noopener noreferrer" className="text-sm font-medium hover:text-primary transition-colors line-clamp-2">
                    {item.title}
                  </a>
                ) : (
                  <p className="text-sm font-medium line-clamp-2">{item.title}</p>
                )}
                <p className="text-xs text-muted-foreground mt-0.5">{item.publisher}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* SHAP */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
            SHAP — Market Crash Risk Factors
            <InfoTooltip text="SHAP values explain how each macro factor contributes to the crash probability. Red pushes probability up (more risk), green pushes it down (less risk). Feature values shown in tooltips." />
          </CardTitle>
        </CardHeader>
        <CardContent>
          {shap.loading ? (
            <Skeleton className="h-[300px] w-full" />
          ) : shap.data?.top_features ? (
            <>
              <p className="text-sm mb-3">
                Market crash probability: <span className={`font-bold ${(shap.data.crash_prob ?? 0) > 0.3 ? "text-red-400" : "text-emerald-400"}`}>
                  {((shap.data.crash_prob ?? 0) * 100).toFixed(1)}%
                </span> ({shap.data.horizon})
              </p>
              <ShapWaterfall features={shap.data.top_features} />
            </>
          ) : shap.data?.status === "model_not_trained" ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              Crash model not trained. SHAP unavailable.
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
