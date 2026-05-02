"use client";

import { useState, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  Trash2, Plus, AlertTriangle, ArrowLeft, ShieldAlert, Info,
} from "lucide-react";
import { InfoTooltip } from "@/components/info-tooltip";
import Link from "next/link";
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
} from "recharts";
import {
  piAnalyzePortfolio,
  type Holding,
  type PISnapshotResponse,
} from "@/lib/api";

const PIE_COLORS = [
  "#63b4ff", "#22c55e", "#f59e0b", "#ef4444", "#a855f7",
  "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16",
  "#06b6d4", "#e11d48", "#8b5cf6",
];

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

function MetricCard({ label, value, suffix, color, tooltip }: {
  label: string; value: string | number; suffix?: string; color?: string; tooltip?: string;
}) {
  return (
    <div className="rounded-lg bg-muted/30 p-3">
      <p className="text-[10px] text-muted-foreground uppercase tracking-wide flex items-center gap-1">
        {label}
        {tooltip && <InfoTooltip text={tooltip} />}
      </p>
      <p className={`text-lg font-bold tabular-nums ${color || ""}`}>
        {value}{suffix}
      </p>
    </div>
  );
}

function RiskFlagCard({ flag }: { flag: { flag_type: string; severity: string; message: string } }) {
  const colors: Record<string, string> = {
    critical: "border-red-500/50 bg-red-500/5 text-red-400",
    warning: "border-amber-500/50 bg-amber-500/5 text-amber-400",
    info: "border-blue-500/50 bg-blue-500/5 text-blue-400",
  };
  const cls = colors[flag.severity] || colors.info;

  return (
    <div className={`rounded-lg border p-3 ${cls}`}>
      <div className="flex items-center gap-2 mb-1">
        {flag.severity === "critical" ? (
          <ShieldAlert className="h-4 w-4" />
        ) : flag.severity === "warning" ? (
          <AlertTriangle className="h-4 w-4" />
        ) : (
          <Info className="h-4 w-4" />
        )}
        <span className="text-xs font-medium uppercase tracking-wide">
          {flag.flag_type}
        </span>
        <Badge variant="outline" className="text-[10px] ml-auto">
          {flag.severity}
        </Badge>
      </div>
      <p className="text-sm">{flag.message}</p>
    </div>
  );
}

export default function MyPortfolioPage() {
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [newTicker, setNewTicker] = useState("");
  const [newShares, setNewShares] = useState("");
  const [newPrice, setNewPrice] = useState("");

  const analyzeMutation = useMutation({
    mutationFn: (h: Holding[]) => piAnalyzePortfolio(h),
  });

  const analysis = analyzeMutation.data ?? null;
  const loading = analyzeMutation.isPending;
  const error = analyzeMutation.error ? (analyzeMutation.error as Error).message : null;

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

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="flex items-center gap-3">
        <Link href="/portfolio-intelligence">
          <Button variant="ghost" size="icon"><ArrowLeft className="h-4 w-4" /></Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">My Portfolio</h1>
          <p className="text-sm text-muted-foreground">
            Analyze your real holdings — concentration, factors, risks
          </p>
        </div>
      </div>

      {/* Holdings Input */}
      {/* TODO(phase-5.5): add separate cost-basis input, render de-emphasized per SPEC §9 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Holdings</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2 flex-wrap">
            <input
              type="text"
              placeholder="Ticker"
              value={newTicker}
              onChange={(e) => setNewTicker(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addHolding()}
              className="w-24 rounded-md border border-border bg-background px-3 py-2 text-sm"
            />
            <input
              type="number"
              placeholder="Shares"
              value={newShares}
              onChange={(e) => setNewShares(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addHolding()}
              className="w-24 rounded-md border border-border bg-background px-3 py-2 text-sm"
            />
            <input
              type="number"
              placeholder="Current Price"
              value={newPrice}
              onChange={(e) => setNewPrice(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addHolding()}
              className="w-32 rounded-md border border-border bg-background px-3 py-2 text-sm"
            />
            <Button size="sm" onClick={addHolding} disabled={!newTicker.trim()}>
              <Plus className="h-4 w-4 mr-1" /> Add
            </Button>
          </div>

          {holdings.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-muted-foreground text-xs">
                    <th className="text-left py-1 px-2">Ticker</th>
                    <th className="text-right py-1 px-2">Shares</th>
                    <th className="text-right py-1 px-2">Price</th>
                    <th className="text-right py-1 px-2">Value</th>
                    <th className="w-8" />
                  </tr>
                </thead>
                <tbody>
                  {holdings.map((h, i) => (
                    <tr key={i} className="border-t border-border/40">
                      <td className="py-1.5 px-2 font-medium">{h.ticker}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums">{h.shares}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums text-muted-foreground text-xs">
                        ${h.current_price.toFixed(2)}
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums font-medium">
                        ${(h.shares * h.current_price).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </td>
                      <td className="py-1.5 px-1">
                        <button onClick={() => removeHolding(i)} className="text-muted-foreground hover:text-red-400 transition-colors">
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="flex items-center gap-3 pt-2">
            <Button onClick={analyze} disabled={holdings.length === 0 || loading}>
              {loading ? "Analyzing..." : "Analyze Portfolio"}
            </Button>
            <span className="text-xs text-muted-foreground">
              {holdings.length} holding{holdings.length !== 1 ? "s" : ""}
            </span>
          </div>

          {error && (
            <p className="text-sm text-red-400">{error}</p>
          )}
        </CardContent>
      </Card>

      {loading && (
        <div className="grid gap-4 md:grid-cols-2">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}><CardContent className="py-8"><Skeleton className="h-32 w-full" /></CardContent></Card>
          ))}
        </div>
      )}

      {analysis && <AnalysisResults data={analysis} />}
    </div>
  );
}

function AnalysisResults({ data }: { data: PISnapshotResponse }) {
  const { metrics, flags, weights } = data;
  const sectorExposure = metrics?.sector_exposure ?? {};
  const factorExposure = metrics?.factor_exposure ?? {};

  const weightData = Object.entries(weights)
    .filter(([, w]) => w > 0.001)
    .sort(([, a], [, b]) => b - a)
    .map(([ticker, w]) => ({ name: ticker, value: w * 100 }));

  const sectorData = Object.entries(sectorExposure)
    .filter(([, w]) => w > 0)
    .sort(([, a], [, b]) => b - a);

  const factorData = Object.entries(factorExposure).map(([name, val]) => ({
    factor: name,
    value: val,
  }));

  return (
    <div className="space-y-4">
      {/* Metrics */}
      {metrics && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard
            label="Total Return"
            value={`${(metrics.total_return * 100).toFixed(1)}%`}
            color={metrics.total_return >= 0 ? "text-emerald-400" : "text-red-400"}
          />
          <MetricCard
            label="Ann. Volatility"
            value={`${(metrics.annualized_volatility * 100).toFixed(1)}%`}
          />
          <MetricCard
            label="Sharpe"
            value={metrics.sharpe_ratio?.toFixed(2) ?? "N/A"}
            tooltip="Risk-adjusted return (Rf = 4%)"
            color={metrics.sharpe_ratio && metrics.sharpe_ratio > 0.5 ? "text-emerald-400" : ""}
          />
          <MetricCard
            label="Max Drawdown"
            value={`${(metrics.max_drawdown * 100).toFixed(1)}%`}
            color="text-red-400"
          />
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {/* Allocation Pie */}
        <Card>
          <CardHeader><CardTitle className="text-sm">Allocation</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie
                  data={weightData}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={90}
                  dataKey="value"
                  nameKey="name"
                  label={({ name, value }) => value > 3 ? `${name} ${value.toFixed(0)}%` : ""}
                  labelLine={false}
                >
                  {weightData.map((_, i) => (
                    <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--foreground)" }}
                  formatter={(v) => [`${Number(v).toFixed(1)}%`, "Weight"]}
                />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Factor Radar */}
        {factorData.length > 0 && (
          <Card>
            <CardHeader><CardTitle className="text-sm">Factor Exposure</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={240}>
                <RadarChart data={factorData}>
                  <PolarGrid stroke="var(--border)" />
                  <PolarAngleAxis dataKey="factor" tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} />
                  <PolarRadiusAxis tick={false} axisLine={false} />
                  <Radar
                    dataKey="value"
                    stroke="hsl(var(--primary))"
                    fill="hsl(var(--primary))"
                    fillOpacity={0.2}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Sector Exposure */}
      {sectorData.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm">Sector Exposure</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-2">
              {sectorData.map(([sector, weight]) => (
                <div key={sector} className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground w-28 shrink-0">{sector}</span>
                  <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary/70 rounded-full"
                      style={{ width: `${Math.min(weight * 100, 100)}%` }}
                    />
                  </div>
                  <span className="text-xs tabular-nums w-12 text-right">
                    {(weight * 100).toFixed(1)}%
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Risk Flags */}
      {flags && flags.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm">Risk Flags</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {flags.map((flag, i) => (
              <RiskFlagCard key={i} flag={flag} />
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
