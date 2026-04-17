"use client";

import { useState, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { Trash2, Plus, ArrowRight, AlertTriangle, FileDown, FileSpreadsheet } from "lucide-react";
import { InfoTooltip } from "@/components/info-tooltip";
import { downloadPortfolioTearsheet } from "@/lib/api";
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from "recharts";
import {
  AreaChart, Area,
} from "recharts";
import {
  analyzePortfolio, buildPortfolio, projectPortfolio, getStockSignal,
  type Holding, type PortfolioAnalysis, type PortfolioBuilt, type PortfolioProjection, type StockSignal,
} from "@/lib/api";

const PIE_COLORS = [
  "#63b4ff", "#22c55e", "#f59e0b", "#ef4444", "#a855f7",
  "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16",
];

// ── localStorage helpers ──────────────────────────────────

function loadHoldings(): Holding[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem("aegis_holdings");
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveHoldings(holdings: Holding[]) {
  localStorage.setItem("aegis_holdings", JSON.stringify(holdings));
}

// ── Allocation Pie ──────────────────────────────────

function AllocationPie({ data }: { data: { ticker: string; weight: number; value: number }[] }) {
  const chartData = data.map((d) => ({ name: d.ticker, value: d.weight }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          innerRadius={60}
          outerRadius={100}
          dataKey="value"
          nameKey="name"
          label={({ name, value }) => `${name} ${value.toFixed(0)}%`}
          labelLine={false}
        >
          {chartData.map((_, i) => (
            <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{ backgroundColor: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--foreground)" }}
          formatter={(v) => [`${Number(v).toFixed(1)}%`, "Weight"]}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

// ── Correlation Matrix ──────────────────────────────────

function CorrelationMatrix({ data }: { data: { tickers: string[]; matrix: number[][] } }) {
  const { tickers, matrix } = data;

  function corrColor(v: number): string {
    if (v > 0.7) return "bg-red-500/60";
    if (v > 0.4) return "bg-amber-500/40";
    if (v > 0.0) return "bg-emerald-500/20";
    if (v > -0.3) return "bg-blue-500/20";
    return "bg-blue-500/50";
  }

  return (
    <div className="overflow-x-auto">
      <table className="text-xs">
        <thead>
          <tr>
            <th className="p-1" />
            {tickers.map((t) => (
              <th key={t} className="p-1 text-center text-muted-foreground font-medium">{t}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tickers.map((row, i) => (
            <tr key={row}>
              <td className="p-1 text-muted-foreground font-medium">{row}</td>
              {matrix[i].map((val, j) => (
                <td key={j} className={`p-1 text-center tabular-nums rounded ${corrColor(val)}`}>
                  {val.toFixed(2)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Metric Card ──────────────────────────────────

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

// ── Portfolio Analyze Tab ──────────────────────────────────

function PortfolioAnalyzeSection() {
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [newTicker, setNewTicker] = useState("");
  const [newShares, setNewShares] = useState("");
  const [newPrice, setNewPrice] = useState("");
  const [holdingSignals, setHoldingSignals] = useState<Record<string, StockSignal>>({});

  const analyzeMutation = useMutation({
    mutationFn: async (h: Holding[]) => {
      const result = await analyzePortfolio(h);
      // Fetch signals for each unique ticker in parallel
      const uniqueTickers = [...new Set(h.map(x => x.ticker))];
      const signalResults = await Promise.allSettled(
        uniqueTickers.map(t => getStockSignal(t))
      );
      const signals: Record<string, StockSignal> = {};
      signalResults.forEach((res, i) => {
        if (res.status === "fulfilled") signals[uniqueTickers[i]] = res.value;
      });
      setHoldingSignals(signals);
      return result;
    },
  });

  const projectionMutation = useMutation({
    mutationFn: (h: Holding[]) => projectPortfolio(h, 1, 0),
  });

  const analysis = analyzeMutation.data ?? null;
  const projection = projectionMutation.data ?? null;
  const loading = analyzeMutation.isPending;
  const error = analyzeMutation.error ? (analyzeMutation.error as Error).message : null;
  const projLoading = projectionMutation.isPending;

  useEffect(() => {
    setHoldings(loadHoldings());
  }, []);

  const addHolding = () => {
    const ticker = newTicker.trim().toUpperCase();
    const shares = parseFloat(newShares);
    const price = parseFloat(newPrice);
    if (!ticker || isNaN(shares) || shares <= 0 || isNaN(price) || price <= 0) return;

    const updated = [...holdings, { ticker, shares, current_price: price }];
    setHoldings(updated);
    saveHoldings(updated);
    setNewTicker("");
    setNewShares("");
    setNewPrice("");
  };

  const removeHolding = (index: number) => {
    const updated = holdings.filter((_, i) => i !== index);
    setHoldings(updated);
    saveHoldings(updated);
    analyzeMutation.reset();
  };

  const analyze = () => {
    if (holdings.length === 0) return;
    analyzeMutation.mutate(holdings);
  };

  const totalValue = holdings.reduce((acc, h) => acc + h.shares * h.current_price, 0);

  return (
    <div className="space-y-6">
      {/* Add holding form */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Your Holdings
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <input
              type="text"
              value={newTicker}
              onChange={(e) => setNewTicker(e.target.value)}
              placeholder="Ticker"
              className="w-24 rounded-md border border-border bg-background px-4 py-3 text-base placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <input
              type="number"
              value={newShares}
              onChange={(e) => setNewShares(e.target.value)}
              placeholder="Shares"
              min="0"
              step="any"
              className="w-24 rounded-md border border-border bg-background px-4 py-3 text-base placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <input
              type="number"
              value={newPrice}
              onChange={(e) => setNewPrice(e.target.value)}
              placeholder="Price ($)"
              min="0"
              step="0.01"
              className="w-28 rounded-md border border-border bg-background px-4 py-3 text-base placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <Button onClick={addHolding} size="sm" disabled={!newTicker.trim()}>
              <Plus className="h-4 w-4 mr-1" /> Add
            </Button>
          </div>

          {holdings.length > 0 && (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-muted-foreground">
                      <th className="py-2 pr-4">Ticker</th>
                      <th className="py-2 pr-4 text-right">Shares</th>
                      <th className="py-2 pr-4 text-right">Price</th>
                      <th className="py-2 pr-4 text-right">Value</th>
                      <th className="py-2 w-10" />
                    </tr>
                  </thead>
                  <tbody>
                    {holdings.map((h, i) => (
                      <tr key={`${h.ticker}-${i}`} className="border-b border-border/50">
                        <td className="py-2 pr-4 font-medium">{h.ticker}</td>
                        <td className="py-2 pr-4 text-right tabular-nums">{h.shares}</td>
                        <td className="py-2 pr-4 text-right tabular-nums">${h.current_price.toFixed(2)}</td>
                        <td className="py-2 pr-4 text-right tabular-nums">
                          ${(h.shares * h.current_price).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                        </td>
                        <td className="py-2">
                          <button onClick={() => removeHolding(i)} className="text-muted-foreground hover:text-red-400 transition-colors">
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t border-border">
                      <td className="py-2 pr-4 font-medium" colSpan={3}>Total</td>
                      <td className="py-2 pr-4 text-right tabular-nums font-bold">
                        ${totalValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </td>
                      <td />
                    </tr>
                  </tfoot>
                </table>
              </div>

              <Button onClick={analyze} disabled={loading}>
                {loading ? "Analyzing..." : "Analyze Portfolio"}
                {!loading && <ArrowRight className="h-4 w-4 ml-1" />}
              </Button>
            </>
          )}

          {holdings.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-4">
              Add holdings above to analyze your portfolio. Data is saved in your browser.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Analysis Results */}
      {loading && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-4 text-sm text-red-400">{error}</div>
      )}

      {analysis && !loading && (
        <>
          <TearsheetExport holdings={holdings} />
          {/* Metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <MetricCard
              label="Annual Return"
              value={analysis.annual_return?.toFixed(1) ?? "N/A"}
              suffix="%"
              color={analysis.annual_return && analysis.annual_return >= 0 ? "text-emerald-400" : "text-red-400"}
              tooltip="Annualized portfolio return based on historical price data"
            />
            <MetricCard
              label="Annual Volatility"
              value={analysis.annual_volatility?.toFixed(1) ?? "N/A"}
              suffix="%"
              tooltip="Annualized standard deviation of returns. Lower is more stable"
            />
            <MetricCard
              label="Sharpe Ratio"
              value={analysis.sharpe_ratio?.toFixed(2) ?? "N/A"}
              color={analysis.sharpe_ratio && analysis.sharpe_ratio > 0.5 ? "text-emerald-400" : "text-amber-400"}
              tooltip="Return per unit of risk. Above 0.5 is decent, above 1.0 is excellent"
            />
            <MetricCard
              label="Daily VaR (95%)"
              value={analysis.var_95_daily?.toFixed(2) ?? "N/A"}
              suffix="%"
              color="text-red-400"
              tooltip="Value at Risk: worst expected daily loss 95% of the time. A -2% VaR means on 95% of days, your loss will be less than 2%"
            />
            <MetricCard
              label="Daily CVaR (95%)"
              value={analysis.cvar_95_daily?.toFixed(2) ?? "N/A"}
              suffix="%"
              color="text-red-400"
              tooltip="Conditional VaR (Expected Shortfall): average loss in the worst 5% of days. Always worse than VaR"
            />
            <MetricCard
              label="Max Drawdown"
              value={analysis.max_drawdown?.toFixed(1) ?? "N/A"}
              suffix="%"
              color="text-red-400"
              tooltip="Largest peak-to-trough decline in portfolio value historically"
            />
          </div>

          {/* Risk Number + Factor Exposures */}
          {(analysis.risk_number || analysis.factor_exposures) && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {analysis.risk_number && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
                      Portfolio Risk Number
                      <InfoTooltip text="Bloomberg PORT-style composite risk score from 1 (safest) to 100 (riskiest). Based on volatility, beta, max drawdown, VaR, and concentration." />
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="flex items-center gap-4">
                      <div className={`text-4xl font-bold tabular-nums ${
                        analysis.risk_number.risk_number > 70 ? "text-red-400" :
                        analysis.risk_number.risk_number > 40 ? "text-amber-400" : "text-emerald-400"
                      }`}>
                        {analysis.risk_number.risk_number}
                      </div>
                      <div>
                        <Badge variant="outline" className={`text-xs ${
                          analysis.risk_number.category === "aggressive" ? "border-red-500/30 text-red-400" :
                          analysis.risk_number.category === "moderate" ? "border-amber-500/30 text-amber-400" :
                          "border-emerald-500/30 text-emerald-400"
                        }`}>
                          {analysis.risk_number.category}
                        </Badge>
                        <p className="text-xs text-muted-foreground mt-1">
                          Vol: {analysis.risk_number.portfolio_vol.toFixed(1)}% | Beta: {analysis.risk_number.portfolio_beta.toFixed(2)}
                        </p>
                      </div>
                    </div>
                    {/* Risk bar */}
                    <div className="w-full h-2.5 bg-gradient-to-r from-emerald-500/30 via-amber-500/30 to-red-500/30 rounded-full relative">
                      <div
                        className="absolute top-1/2 -translate-y-1/2 w-3.5 h-3.5 bg-white rounded-full border-2 border-primary shadow"
                        style={{ left: `${analysis.risk_number.risk_number}%` }}
                      />
                    </div>
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>Conservative</span>
                      <span>Moderate</span>
                      <span>Aggressive</span>
                    </div>
                  </CardContent>
                </Card>
              )}

              {analysis.factor_exposures && (
                <Card data-advanced>
                  <CardHeader>
                    <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
                      Factor Exposures (FF5)
                      <InfoTooltip text="Fama-French 5-factor decomposition of your portfolio. Shows how much of your returns come from market, size, value, profitability, and investment factors." />
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="flex items-center gap-4 text-sm">
                      {analysis.factor_exposures.alpha_annual != null && (
                        <span className="text-muted-foreground">Alpha: <span className={`font-bold ${analysis.factor_exposures.alpha_annual > 0 ? "text-emerald-400" : "text-red-400"}`}>
                          {analysis.factor_exposures.alpha_annual > 0 ? "+" : ""}{(analysis.factor_exposures.alpha_annual * 100).toFixed(1)}%
                        </span></span>
                      )}
                      {analysis.factor_exposures.r_squared != null && (
                        <span className="text-muted-foreground">R²: <span className="font-bold">{(analysis.factor_exposures.r_squared * 100).toFixed(1)}%</span></span>
                      )}
                      {analysis.factor_exposures.market_beta != null && (
                        <span className="text-muted-foreground">Market β: <span className="font-bold">{analysis.factor_exposures.market_beta.toFixed(2)}</span></span>
                      )}
                    </div>
                    {analysis.factor_exposures.style && (
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(analysis.factor_exposures.style).map(([factor, style]) => (
                          <span key={factor} className="text-xs px-2 py-1 rounded-md bg-muted/50">
                            <span className="text-muted-foreground">{factor}:</span> <span className="font-medium">{style}</span>
                          </span>
                        ))}
                      </div>
                    )}
                    {analysis.factor_exposures.stocks && Object.keys(analysis.factor_exposures.stocks).length > 0 && (
                      <div className="text-xs text-muted-foreground">
                        <p className="mb-1">Per-holding betas:</p>
                        <div className="flex flex-wrap gap-2">
                          {Object.entries(analysis.factor_exposures.stocks).map(([ticker, data]) => (
                            <span key={ticker} className="px-2 py-0.5 rounded bg-muted/30">
                              {ticker}: β={data.market_beta.toFixed(2)}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {/* Stress Test + Drawdown Analysis */}
          {(analysis.stress_test || analysis.portfolio_drawdowns) && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {analysis.stress_test && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
                      Historical Stress Test
                      <InfoTooltip text="How your portfolio would have performed during past market crises" />
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {Object.entries(analysis.stress_test.scenarios).map(([name, s]) => (
                      <div key={name} className="flex justify-between items-center text-sm">
                        <span className="text-muted-foreground truncate mr-2">{name}</span>
                        <span className={`font-mono tabular-nums font-medium ${
                          s.portfolio_drawdown_pct < -30 ? "text-red-400" : s.portfolio_drawdown_pct < -15 ? "text-amber-400" : "text-emerald-400"
                        }`}>
                          {s.portfolio_drawdown_pct.toFixed(1)}%
                        </span>
                      </div>
                    ))}
                    {analysis.stress_test.worst_scenario && (
                      <p className="text-xs text-muted-foreground mt-2 pt-2 border-t border-border/50">
                        Worst case: <span className="text-red-400 font-medium">{analysis.stress_test.worst_scenario}</span> ({analysis.stress_test.worst_drawdown_pct?.toFixed(1)}%)
                      </p>
                    )}
                  </CardContent>
                </Card>
              )}

              {analysis.portfolio_drawdowns && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
                      Drawdown Analysis
                      <InfoTooltip text="Historical drawdowns and recovery statistics for your portfolio" />
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-xs text-muted-foreground">Max Drawdown</p>
                        <p className="text-lg font-bold tabular-nums text-red-400">
                          {analysis.portfolio_drawdowns.max_drawdown_pct != null
                            ? `${analysis.portfolio_drawdowns.max_drawdown_pct.toFixed(1)}%`
                            : "--"}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Current DD</p>
                        <p className={`text-lg font-bold tabular-nums ${
                          (analysis.portfolio_drawdowns.current_drawdown_pct ?? 0) < -10 ? "text-red-400" : "text-emerald-400"
                        }`}>
                          {analysis.portfolio_drawdowns.current_drawdown_pct != null
                            ? `${analysis.portfolio_drawdowns.current_drawdown_pct.toFixed(1)}%`
                            : "0.0%"}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Total Drawdowns</p>
                        <p className="text-lg font-bold tabular-nums">{analysis.portfolio_drawdowns.total_drawdowns}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Avg Recovery</p>
                        <p className="text-lg font-bold tabular-nums">
                          {analysis.portfolio_drawdowns.avg_recovery_days != null
                            ? `${Math.round(analysis.portfolio_drawdowns.avg_recovery_days)}d`
                            : "--"}
                        </p>
                      </div>
                    </div>
                    {analysis.portfolio_drawdowns.rolling_return_1y != null && (
                      <p className="text-xs text-muted-foreground mt-3 pt-2 border-t border-border/50">
                        Rolling 1Y return: <span className={`font-medium ${analysis.portfolio_drawdowns.rolling_return_1y > 0 ? "text-emerald-400" : "text-red-400"}`}>
                          {analysis.portfolio_drawdowns.rolling_return_1y > 0 ? "+" : ""}{analysis.portfolio_drawdowns.rolling_return_1y.toFixed(1)}%
                        </span>
                      </p>
                    )}
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {/* Attribution + MCTR + Benchmark Analytics */}
          {(analysis.attribution_summary || analysis.mctr_summary || analysis.benchmark_analytics) && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Brinson-Fachler Attribution */}
              {analysis.attribution_summary && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
                      Performance Attribution
                      <InfoTooltip text="Brinson-Fachler decomposition: how much of your active return came from allocation (sector bets), selection (stock picking), and interaction effects vs SPY benchmark." />
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Portfolio</span>
                      <span className={`font-bold tabular-nums ${(analysis.attribution_summary.portfolio_return ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                        {analysis.attribution_summary.portfolio_return != null ? `${(analysis.attribution_summary.portfolio_return * 100).toFixed(2)}%` : "--"}
                      </span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Benchmark (SPY)</span>
                      <span className="font-bold tabular-nums">
                        {analysis.attribution_summary.benchmark_return != null ? `${(analysis.attribution_summary.benchmark_return * 100).toFixed(2)}%` : "--"}
                      </span>
                    </div>
                    <Separator />
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Allocation effect</span>
                        <span className={`font-medium tabular-nums ${(analysis.attribution_summary.total_allocation_effect ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                          {analysis.attribution_summary.total_allocation_effect != null ? `${(analysis.attribution_summary.total_allocation_effect * 100).toFixed(2)}%` : "--"}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Selection effect</span>
                        <span className={`font-medium tabular-nums ${(analysis.attribution_summary.total_selection_effect ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                          {analysis.attribution_summary.total_selection_effect != null ? `${(analysis.attribution_summary.total_selection_effect * 100).toFixed(2)}%` : "--"}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Interaction</span>
                        <span className={`font-medium tabular-nums ${(analysis.attribution_summary.total_interaction_effect ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                          {analysis.attribution_summary.total_interaction_effect != null ? `${(analysis.attribution_summary.total_interaction_effect * 100).toFixed(2)}%` : "--"}
                        </span>
                      </div>
                      <Separator />
                      <div className="flex justify-between font-bold">
                        <span>Active Return</span>
                        <span className={`tabular-nums ${(analysis.attribution_summary.total_active_return ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                          {analysis.attribution_summary.total_active_return != null ? `${(analysis.attribution_summary.total_active_return * 100).toFixed(2)}%` : "--"}
                        </span>
                      </div>
                    </div>
                    {analysis.attribution_summary.period && (
                      <p className="text-xs text-muted-foreground">Period: {analysis.attribution_summary.period}</p>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* MCTR Risk Contributors */}
              {analysis.mctr_summary && analysis.mctr_summary.top_risk_contributors?.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
                      Risk Contributors (MCTR)
                      <InfoTooltip text="Marginal Contribution to Risk: which holdings contribute most to portfolio volatility. A holding with high risk contribution relative to its weight is a concentration risk." />
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {analysis.mctr_summary.portfolio_vol != null && (
                      <p className="text-sm text-muted-foreground">
                        Portfolio Vol: <span className="font-bold text-foreground">{(analysis.mctr_summary.portfolio_vol * 100).toFixed(1)}%</span>
                      </p>
                    )}
                    <div className="space-y-2">
                      {analysis.mctr_summary.top_risk_contributors.map((c) => (
                        <div key={c.ticker} className="flex items-center gap-2">
                          <span className="text-sm font-medium w-12">{c.ticker}</span>
                          <div className="flex-1 h-2 bg-muted/30 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                c.risk_contrib_pct > c.weight_pct * 1.5 ? "bg-red-400" :
                                c.risk_contrib_pct > c.weight_pct ? "bg-amber-400" : "bg-emerald-400"
                              }`}
                              style={{ width: `${Math.min(Math.abs(c.risk_contrib_pct), 100)}%` }}
                            />
                          </div>
                          <span className="text-xs tabular-nums text-muted-foreground w-24 text-right">
                            {c.risk_contrib_pct.toFixed(1)}% risk / {c.weight_pct.toFixed(1)}% wt
                          </span>
                        </div>
                      ))}
                    </div>
                    <p className="text-xs text-muted-foreground pt-1 border-t border-border/50">
                      Red = risk contribution &gt; 1.5x weight (concentrated risk)
                    </p>
                  </CardContent>
                </Card>
              )}

              {/* Benchmark Analytics */}
              {analysis.benchmark_analytics && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
                      Benchmark Analytics
                      <InfoTooltip text="How your portfolio compares to SPY. Tracking error measures deviation, information ratio measures skill, active share measures how different your holdings are." />
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {analysis.benchmark_analytics.management_style && (
                      <Badge variant="outline" className="text-xs">
                        {analysis.benchmark_analytics.management_style}
                      </Badge>
                    )}
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      {analysis.benchmark_analytics.tracking_error_pct != null && (
                        <div>
                          <p className="text-xs text-muted-foreground">Tracking Error</p>
                          <p className="font-bold tabular-nums">{analysis.benchmark_analytics.tracking_error_pct.toFixed(2)}%</p>
                        </div>
                      )}
                      {analysis.benchmark_analytics.information_ratio != null && (
                        <div>
                          <p className="text-xs text-muted-foreground">Information Ratio</p>
                          <p className={`font-bold tabular-nums ${analysis.benchmark_analytics.information_ratio > 0 ? "text-emerald-400" : "text-red-400"}`}>
                            {analysis.benchmark_analytics.information_ratio.toFixed(2)}
                          </p>
                        </div>
                      )}
                      {analysis.benchmark_analytics.active_share != null && (
                        <div>
                          <p className="text-xs text-muted-foreground">Active Share</p>
                          <p className="font-bold tabular-nums">
                            {analysis.benchmark_analytics.active_share.toFixed(1)}%
                            {analysis.benchmark_analytics.active_share_label && (
                              <span className="text-xs text-muted-foreground ml-1">({analysis.benchmark_analytics.active_share_label})</span>
                            )}
                          </p>
                        </div>
                      )}
                      {analysis.benchmark_analytics.beta_vs_benchmark != null && (
                        <div>
                          <p className="text-xs text-muted-foreground">Beta vs SPY</p>
                          <p className="font-bold tabular-nums">{analysis.benchmark_analytics.beta_vs_benchmark.toFixed(2)}</p>
                        </div>
                      )}
                      {analysis.benchmark_analytics.up_capture != null && (
                        <div>
                          <p className="text-xs text-muted-foreground">Up Capture</p>
                          <p className={`font-bold tabular-nums ${analysis.benchmark_analytics.up_capture > 100 ? "text-emerald-400" : "text-muted-foreground"}`}>
                            {analysis.benchmark_analytics.up_capture.toFixed(0)}%
                          </p>
                        </div>
                      )}
                      {analysis.benchmark_analytics.down_capture != null && (
                        <div>
                          <p className="text-xs text-muted-foreground">Down Capture</p>
                          <p className={`font-bold tabular-nums ${analysis.benchmark_analytics.down_capture < 100 ? "text-emerald-400" : "text-red-400"}`}>
                            {analysis.benchmark_analytics.down_capture.toFixed(0)}%
                          </p>
                        </div>
                      )}
                    </div>
                    {analysis.benchmark_analytics.insights && analysis.benchmark_analytics.insights.length > 0 && (
                      <div className="pt-2 border-t border-border/50">
                        {analysis.benchmark_analytics.insights.slice(0, 2).map((insight, i) => (
                          <p key={i} className="text-xs text-muted-foreground mt-1">{insight}</p>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {/* Concentration Warning */}
          {analysis.allocations.some(a => a.weight > 40) && (
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-3 flex items-start gap-2 text-xs text-amber-400/90">
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
              <div>
                <p className="font-medium">Concentration Warning</p>
                <p className="mt-0.5 text-amber-400/70">
                  {analysis.allocations.filter(a => a.weight > 40).map(a => a.ticker).join(", ")} makes up more than 40% of your portfolio. Consider diversifying to reduce single-stock risk.
                </p>
              </div>
            </div>
          )}

          {/* Per-Holding Signals */}
          {Object.keys(holdingSignals).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
                  Per-Holding Signals
                  <InfoTooltip text="Buy/Hold/Sell signal for each holding, combining market conditions with stock-specific factors (beta, analyst targets, P/E ratio)." />
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {holdings.map((h, i) => {
                    const sig = holdingSignals[h.ticker];
                    if (!sig || sig.error) return null;
                    return (
                      <div key={`${h.ticker}-${i}`} className={`rounded-lg border p-3 ${
                        sig.action.includes("Buy") ? "border-emerald-200 bg-emerald-50/50" :
                        sig.action.includes("Sell") ? "border-red-200 bg-red-50/50" : "border-amber-200 bg-amber-50/50"
                      }`}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-bold text-sm">{h.ticker}</span>
                          <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                            sig.action.includes("Buy") ? "bg-emerald-100 text-emerald-700" :
                            sig.action.includes("Sell") ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"
                          }`}>{sig.action}</span>
                        </div>
                        <div className="text-xs text-muted-foreground">
                          Confidence: {sig.confidence}% · Score: {sig.composite_score > 0 ? "+" : ""}{sig.composite_score.toFixed(3)}
                        </div>
                        {sig.reasons[0] && (
                          <p className="text-xs text-muted-foreground mt-1 line-clamp-1">{sig.reasons[0]}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Allocation Pie */}
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
                  Portfolio Allocation
                  <InfoTooltip text="Weight of each holding as a percentage of total portfolio value." />
                </CardTitle>
              </CardHeader>
              <CardContent>
                <AllocationPie data={analysis.allocations} />
              </CardContent>
            </Card>

            {/* Correlation Matrix */}
            {analysis.correlation && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
                    Correlation Matrix
                    <InfoTooltip text="Pairwise correlation between holdings. High correlation (red, >0.7) means stocks move together — less diversification benefit. Low/negative (blue) is better for diversification." />
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <CorrelationMatrix data={analysis.correlation} />
                </CardContent>
              </Card>
            )}
          </div>

          {/* 1-Year Projection */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  1-Year Portfolio Projection
                </CardTitle>
                {!projection && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={projLoading}
                    onClick={() => projectionMutation.mutate(holdings)}
                  >
                    {projLoading ? "Projecting..." : "Run Projection"}
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {projLoading && <Skeleton className="h-[250px] w-full" />}
              {projection && !projLoading && !projection.error && (
                <>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                    <MetricCard label="Expected Value" value={`$${projection.expected_final.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
                    <MetricCard label="Expected Return" value={`${projection.expected_return_pct >= 0 ? "+" : ""}${projection.expected_return_pct.toFixed(1)}`} suffix="%" color={projection.expected_return_pct >= 0 ? "text-emerald-400" : "text-red-400"} />
                    <MetricCard label="P(Gain)" value={`${projection.prob_gain.toFixed(0)}`} suffix="%" color={projection.prob_gain > 50 ? "text-emerald-400" : "text-red-400"} />
                    <MetricCard label="10th-90th Range" value={`$${(projection.p10_final / 1000).toFixed(0)}K - $${(projection.p90_final / 1000).toFixed(0)}K`} />
                  </div>
                  <ResponsiveContainer width="100%" height={250}>
                    <AreaChart data={projection.quarterly}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                      <XAxis dataKey="quarter" tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} tickFormatter={(q) => `Q${q}`} />
                      <YAxis tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}K`} />
                      <Tooltip
                        contentStyle={{ backgroundColor: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--foreground)" }}
                        formatter={(v) => [`$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`, ""]}
                        labelFormatter={(q) => `Quarter ${q}`}
                      />
                      <Area type="monotone" dataKey="p90" stroke="transparent" fill="#22c55e" fillOpacity={0.05} name="90th" />
                      <Area type="monotone" dataKey="p75" stroke="transparent" fill="#22c55e" fillOpacity={0.08} name="75th" />
                      <Area type="monotone" dataKey="median" stroke="#63b4ff" fill="#63b4ff" fillOpacity={0.15} strokeWidth={2} name="Median" />
                      <Area type="monotone" dataKey="p25" stroke="transparent" fill="#ef4444" fillOpacity={0.08} name="25th" />
                      <Area type="monotone" dataKey="p10" stroke="transparent" fill="#ef4444" fillOpacity={0.05} name="10th" />
                    </AreaChart>
                  </ResponsiveContainer>
                </>
              )}
              {projection?.error && (
                <p className="text-sm text-red-400">{projection.error}</p>
              )}
              {!projection && !projLoading && (
                <p className="text-sm text-muted-foreground text-center py-8">
                  Click &quot;Run Projection&quot; to simulate your portfolio&apos;s 1-year trajectory
                </p>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

// ── Portfolio Build Tab ──────────────────────────────────

function PortfolioBuildSection() {
  const [risk, setRisk] = useState("moderate");
  const [amount, setAmount] = useState("10000");
  const [horizon, setHorizon] = useState("5y");
  const buildMutation = useMutation({
    mutationFn: () => buildPortfolio(risk, parseFloat(amount) || 10000, horizon),
  });

  const result = buildMutation.data ?? null;
  const loading = buildMutation.isPending;
  const error = buildMutation.error ? (buildMutation.error as Error).message : null;

  const build = () => buildMutation.mutate();

  const riskOptions = [
    { value: "conservative", label: "Conservative", desc: "Capital preservation, bonds & dividends", icon: "🛡️" },
    { value: "moderate", label: "Moderate", desc: "Balanced growth with some protection", icon: "⚖️" },
    { value: "aggressive", label: "Aggressive", desc: "Maximum growth, higher volatility", icon: "🚀" },
  ];

  const horizonOptions = [
    { value: "1y", label: "1 Year", desc: "Short-term" },
    { value: "3y", label: "3 Years", desc: "Medium" },
    { value: "5y", label: "5 Years", desc: "Standard" },
    { value: "10y", label: "10 Years", desc: "Long-term" },
  ];

  const lossScenarios = [
    { risk: "conservative", text: "If my portfolio dropped 10%, I would sell immediately to prevent further losses." },
    { risk: "moderate", text: "If my portfolio dropped 20%, I'd be uncomfortable but hold. I'd sell at -30%." },
    { risk: "aggressive", text: "If my portfolio dropped 30%+, I'd see it as a buying opportunity and add more." },
  ];

  const matchingScenario = lossScenarios.find(s => s.risk === risk);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
            Investment Profile
            <InfoTooltip text="Answer these questions to help us recommend an allocation that matches your risk tolerance, time horizon, and goals. The algorithm uses these inputs to weight equity vs fixed income vs alternatives." />
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-8">
          {/* Risk Tolerance */}
          <div>
            <p className="text-sm font-medium mb-1">1. What is your risk tolerance?</p>
            <p className="text-xs text-muted-foreground mb-3">How much portfolio volatility can you handle emotionally and financially?</p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {riskOptions.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setRisk(opt.value)}
                  className={`rounded-lg border p-4 text-left transition-all ${
                    risk === opt.value
                      ? "border-primary bg-primary/10 ring-1 ring-primary/30"
                      : "border-border hover:border-muted-foreground/30"
                  }`}
                >
                  <p className="text-base font-medium">{opt.label}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{opt.desc}</p>
                </button>
              ))}
            </div>
            {matchingScenario && (
              <p className="text-xs text-muted-foreground mt-2 italic bg-muted/30 rounded px-3 py-2">
                Your profile: &quot;{matchingScenario.text}&quot;
              </p>
            )}
          </div>

          {/* Investment Amount */}
          <div>
            <p className="text-sm font-medium mb-1">2. How much do you want to invest?</p>
            <p className="text-xs text-muted-foreground mb-3">Initial lump sum. You can adjust this later.</p>
            <div className="flex flex-wrap gap-2 mb-2">
              {["1000", "5000", "10000", "25000", "50000", "100000"].map((v) => (
                <button
                  key={v}
                  onClick={() => setAmount(v)}
                  className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                    amount === v ? "bg-primary text-primary-foreground" : "bg-muted/50 hover:bg-muted text-muted-foreground"
                  }`}
                >
                  ${Number(v).toLocaleString()}
                </button>
              ))}
            </div>
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              min="100"
              step="100"
              placeholder="Custom amount"
              className="w-full max-w-xs rounded-md border border-border bg-background px-4 py-3 text-base placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          {/* Time Horizon */}
          <div>
            <p className="text-sm font-medium mb-1">3. When do you need this money?</p>
            <p className="text-xs text-muted-foreground mb-3">Longer horizons allow more aggressive allocations since you can ride out downturns.</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {horizonOptions.map((h) => (
                <button
                  key={h.value}
                  onClick={() => setHorizon(h.value)}
                  className={`rounded-lg border p-3 text-center transition-all ${
                    horizon === h.value
                      ? "border-primary bg-primary/10 ring-1 ring-primary/30"
                      : "border-border hover:border-muted-foreground/30"
                  }`}
                >
                  <p className="text-base font-bold">{h.label}</p>
                  <p className="text-xs text-muted-foreground">{h.desc}</p>
                </button>
              ))}
            </div>
          </div>

          <Separator />

          <Button onClick={build} disabled={loading} size="lg">
            {loading ? "Building..." : "Build My Portfolio"}
            {!loading && <ArrowRight className="h-4 w-4 ml-1" />}
          </Button>
        </CardContent>
      </Card>

      {loading && (
        <div className="space-y-3">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      )}

      {error && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-4 text-sm text-red-400">{error}</div>
      )}

      {result && !loading && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Recommended Allocation
              </CardTitle>
              <Badge variant="outline">{result.risk_tolerance} · {result.time_horizon}</Badge>
            </div>
            <p className="text-xs text-muted-foreground">{result.description}</p>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Pie chart */}
            <AllocationPie
              data={result.holdings.map((h) => ({
                ticker: h.ticker,
                weight: h.weight,
                value: h.dollar_amount,
              }))}
            />

            {/* Holdings table */}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-muted-foreground">
                    <th className="py-2 pr-4">Ticker</th>
                    <th className="py-2 pr-4 text-right">Weight</th>
                    <th className="py-2 pr-4 text-right">Amount</th>
                    <th className="py-2 pr-4 text-right">Shares</th>
                    <th className="py-2 text-right">Price</th>
                  </tr>
                </thead>
                <tbody>
                  {result.holdings.map((h) => (
                    <tr key={h.ticker} className="border-b border-border/50">
                      <td className="py-2.5 pr-4 font-medium">{h.ticker}</td>
                      <td className="py-2.5 pr-4 text-right tabular-nums">{h.weight.toFixed(1)}%</td>
                      <td className="py-2.5 pr-4 text-right tabular-nums">
                        ${h.dollar_amount.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums">{h.shares}</td>
                      <td className="py-2.5 text-right tabular-nums">${h.price.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-border">
                    <td className="py-2 font-medium">Total</td>
                    <td className="py-2 text-right tabular-nums font-bold">100%</td>
                    <td className="py-2 text-right tabular-nums font-bold" colSpan={3}>
                      ${result.investment_amount.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ── Main Page ──────────────────────────────────

export default function PortfolioPage() {
  const [tab, setTab] = useState<"analyze" | "build">("analyze");

  return (
    <div className="space-y-6 animate-slide-up">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Portfolio</h1>
        <p className="text-sm text-muted-foreground">
          Analyze your holdings or build a goal-based allocation
        </p>
      </div>

      <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-2.5 flex items-center gap-2 text-xs text-amber-400/80">
        <span>Educational tool only. Not financial advice. Portfolio suggestions are algorithmic and do not account for your full financial situation.</span>
      </div>

      {/* Tab switcher */}
      <div className="flex gap-1 rounded-lg bg-muted/50 p-1 w-fit">
        <button
          onClick={() => setTab("analyze")}
          className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
            tab === "analyze"
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          Analyze Holdings
        </button>
        <button
          onClick={() => setTab("build")}
          className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
            tab === "build"
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          Build Portfolio
        </button>
      </div>

      {tab === "analyze" ? <PortfolioAnalyzeSection /> : <PortfolioBuildSection />}
    </div>
  );
}

function TearsheetExport({ holdings }: { holdings: Holding[] }) {
  const [busy, setBusy] = useState<"html" | "xlsx" | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const doExport = async (format: "html" | "xlsx") => {
    if (holdings.length === 0) return;
    setBusy(format);
    setErr(null);
    try {
      const blob = await downloadPortfolioTearsheet(holdings, format);
      const url = URL.createObjectURL(blob);
      if (format === "html") {
        window.open(url, "_blank", "noopener");
        // Revoke shortly so the new tab has time to load it
        setTimeout(() => URL.revokeObjectURL(url), 30_000);
      } else {
        const a = document.createElement("a");
        a.href = url;
        a.download = `aegis-tearsheet-${new Date().toISOString().slice(0, 10)}.xlsx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 10_000);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex items-center justify-end gap-2">
      <Button
        size="sm"
        variant="ghost"
        onClick={() => doExport("html")}
        disabled={busy !== null || holdings.length === 0}
        title="Open a one-page tearsheet — use browser File → Print → Save as PDF"
      >
        <FileDown className="h-4 w-4 mr-1.5" />
        {busy === "html" ? "Building…" : "Export HTML"}
      </Button>
      <Button
        size="sm"
        variant="ghost"
        onClick={() => doExport("xlsx")}
        disabled={busy !== null || holdings.length === 0}
        title="Download an Excel workbook with Summary / Holdings / Risk / Factors / Stress sheets"
      >
        <FileSpreadsheet className="h-4 w-4 mr-1.5" />
        {busy === "xlsx" ? "Building…" : "Export Excel"}
      </Button>
      {err && <span className="text-xs text-destructive">{err}</span>}
    </div>
  );
}
