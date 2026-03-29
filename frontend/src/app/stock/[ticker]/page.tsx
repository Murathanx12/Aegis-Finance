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
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine,
  AreaChart, Area,
} from "recharts";
import type { StockAnalysis } from "@/lib/api";

function MetricCard({ label, value, suffix, color }: { label: string; value: string | number; suffix?: string; color?: string }) {
  return (
    <div className="rounded-lg bg-muted/30 p-3">
      <p className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</p>
      <p className={`text-lg font-bold tabular-nums ${color || ""}`}>
        {value}{suffix}
      </p>
    </div>
  );
}

function ShapWaterfall({ features }: { features: { feature: string; shap_value: number; feature_value: number | null }[] }) {
  const data = features.slice(0, 10).map((f) => ({
    name: f.feature.replace(/_/g, " "),
    value: f.shap_value,
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data} layout="vertical" margin={{ left: 110, right: 20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
        <XAxis type="number" tick={{ fill: "#888", fontSize: 11 }} />
        <YAxis type="category" dataKey="name" tick={{ fill: "#aaa", fontSize: 11 }} width={100} />
        <Tooltip
          contentStyle={{ backgroundColor: "#1e1e2e", border: "1px solid #333", borderRadius: 8 }}
          formatter={(v) => [Number(v).toFixed(4), "SHAP"]}
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

  // Build quarterly price bands
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
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            12-Month Price Expectations
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
        <CardTitle className="text-sm font-medium text-muted-foreground">
          Analyst Consensus ({total} analysts)
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
    <div className="space-y-6">
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
            <MetricCard label="Expected Return (5Y)" value={`${stock.data.expected_return >= 0 ? "+" : ""}${stock.data.expected_return.toFixed(1)}`} suffix="%" color={stock.data.expected_return >= 0 ? "text-emerald-400" : "text-red-400"} />
            <MetricCard label="Median Return" value={`${stock.data.median_return >= 0 ? "+" : ""}${stock.data.median_return.toFixed(1)}`} suffix="%" />
            <MetricCard label="Volatility" value={stock.data.volatility.toFixed(1)} suffix="%" />
            <MetricCard label="Beta" value={stock.data.beta.toFixed(2)} />
            <MetricCard label="Sharpe Ratio" value={stock.data.sharpe.toFixed(2)} color={stock.data.sharpe > 0.5 ? "text-emerald-400" : stock.data.sharpe > 0 ? "text-amber-400" : "text-red-400"} />
            <MetricCard label="P(Loss) 5Y" value={stock.data.prob_loss_5y.toFixed(1)} suffix="%" color={stock.data.prob_loss_5y > 30 ? "text-red-400" : "text-emerald-400"} />
            <MetricCard label="Avg Max Drawdown" value={stock.data.avg_max_drawdown.toFixed(1)} suffix="%" color="text-red-400" />
          </div>

          {/* Price Range */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">5-Year Price Range (Monte Carlo)</CardTitle>
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
        </>
      ) : stock.error ? (
        <Card className="border-red-500/30">
          <CardContent className="p-4 text-sm text-red-400">
            Could not analyze {upperTicker}: {stock.error}
          </CardContent>
        </Card>
      ) : null}

      {/* Price Expectations */}
      {stock.data?.analyst_targets && (
        <PriceExpectations stock={stock.data} />
      )}

      {/* Analyst Recommendations */}
      {stock.data?.recommendations && (
        <AnalystConsensus recommendations={stock.data.recommendations} />
      )}

      {/* Top Holders */}
      {stock.data?.holders?.top_holders && stock.data.holders.top_holders.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Top Institutional Holders
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
                    <tr key={i} className="border-b border-border/30">
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

      {/* Earnings */}
      {stock.data?.earnings && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Earnings</CardTitle>
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

      {/* SHAP */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">
            SHAP — Market Crash Risk Factors
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
