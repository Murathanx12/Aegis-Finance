"use client";

import { useState, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowRight, TrendingUp } from "lucide-react";
import { InfoTooltip } from "@/components/info-tooltip";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from "recharts";
import { projectSavings, type SavingsProjection } from "@/lib/api";

function loadSettings(): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem("aegis_retirement");
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveSettings(settings: Record<string, string>) {
  localStorage.setItem("aegis_retirement", JSON.stringify(settings));
}

function MetricCard({ label, value, sub, tooltip }: { label: string; value: string; sub?: string; tooltip?: string }) {
  return (
    <div className="rounded-lg bg-muted/30 p-4">
      <p className="text-[10px] text-muted-foreground uppercase tracking-wide">
        {label}
        {tooltip && <InfoTooltip text={tooltip} />}
      </p>
      <p className="text-lg font-bold tabular-nums">{value}</p>
      {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  );
}

export default function RetirementPage() {
  const [currentAge, setCurrentAge] = useState("25");
  const [targetAge, setTargetAge] = useState("65");
  const [monthly, setMonthly] = useState("500");
  const [savings, setSavings] = useState("0");
  const [risk, setRisk] = useState("moderate");
  const [inflation, setInflation] = useState("2.5");
  const [targetAmount, setTargetAmount] = useState("1000000");

  const savingsMutation = useMutation({
    mutationFn: (params: Parameters<typeof projectSavings>[0]) => projectSavings(params),
  });

  const result = savingsMutation.data ?? null;
  const loading = savingsMutation.isPending;
  const error = savingsMutation.error ? (savingsMutation.error as Error).message : null;

  // Load from localStorage
  useEffect(() => {
    const s = loadSettings();
    if (s.currentAge) setCurrentAge(s.currentAge);
    if (s.targetAge) setTargetAge(s.targetAge);
    if (s.monthly) setMonthly(s.monthly);
    if (s.savings) setSavings(s.savings);
    if (s.risk) setRisk(s.risk);
    if (s.inflation) setInflation(s.inflation);
    if (s.targetAmount) setTargetAmount(s.targetAmount);
  }, []);

  const calculate = () => {
    const params = {
      current_age: parseInt(currentAge) || 25,
      target_age: parseInt(targetAge) || 65,
      monthly_contribution: parseFloat(monthly) || 0,
      current_savings: parseFloat(savings) || 0,
      risk_level: risk,
      inflation_rate: (parseFloat(inflation) || 2.5) / 100,
      target_amount: parseFloat(targetAmount) || 1000000,
    };

    // Save to localStorage
    saveSettings({ currentAge, targetAge, monthly, savings, risk, inflation, targetAmount });

    savingsMutation.mutate(params);
  };

  const riskOptions = [
    { value: "conservative", label: "Conservative", rate: "5%" },
    { value: "moderate", label: "Moderate", rate: "7%" },
    { value: "aggressive", label: "Aggressive", rate: "9%" },
  ];

  const fmt = (n: number) => n >= 1_000_000
    ? `$${(n / 1_000_000).toFixed(1)}M`
    : n >= 1000
    ? `$${(n / 1000).toFixed(0)}K`
    : `$${n.toFixed(0)}`;

  return (
    <div className="space-y-6 animate-slide-up">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Retirement Calculator</h1>
        <p className="text-sm text-muted-foreground">
          Project your savings growth with compound interest
        </p>
      </div>

      <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-2.5 flex items-center gap-2 text-xs text-amber-400/80">
        <span>Educational tool only. Projections assume constant returns and contributions. Actual results will vary significantly.</span>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Your Details
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Age inputs */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <label className="text-sm font-medium mb-1 block">Current Age</label>
              <input
                type="number" value={currentAge} onChange={(e) => setCurrentAge(e.target.value)}
                min="1" max="100"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Target Age</label>
              <input
                type="number" value={targetAge} onChange={(e) => setTargetAge(e.target.value)}
                min="2" max="120"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Monthly ($)</label>
              <input
                type="number" value={monthly} onChange={(e) => setMonthly(e.target.value)}
                min="0" step="50"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Current Savings ($)</label>
              <input
                type="number" value={savings} onChange={(e) => setSavings(e.target.value)}
                min="0" step="1000"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
          </div>

          {/* Risk tolerance */}
          <div>
            <p className="text-sm font-medium mb-2">
              Risk Tolerance (Expected Return)
              <InfoTooltip text="Higher expected returns come with higher volatility. Conservative assumes bonds + some stocks (~5%), moderate is a balanced portfolio (~7%), aggressive is mostly stocks (~10%). Historical S&P 500 average is ~10% nominal." />
            </p>
            <div className="grid grid-cols-3 gap-3">
              {riskOptions.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setRisk(opt.value)}
                  className={`rounded-lg border p-3 text-left transition-colors ${
                    risk === opt.value
                      ? "border-primary bg-primary/10"
                      : "border-border hover:border-muted-foreground/30"
                  }`}
                >
                  <p className="text-sm font-medium">{opt.label}</p>
                  <p className="text-xs text-muted-foreground">{opt.rate} annual</p>
                </button>
              ))}
            </div>
          </div>

          {/* Advanced */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium mb-1 block">
                Inflation Rate (%)
                <InfoTooltip text="Inflation erodes purchasing power over time. The Fed targets 2% annually. A $1M portfolio at retirement will buy less than $1M today — the 'real' value adjusts for this." />
              </label>
              <input
                type="number" value={inflation} onChange={(e) => setInflation(e.target.value)}
                min="0" max="20" step="0.1"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Target Amount ($)</label>
              <input
                type="number" value={targetAmount} onChange={(e) => setTargetAmount(e.target.value)}
                min="1000" step="10000"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
          </div>

          <Button onClick={calculate} disabled={loading} className="w-full sm:w-auto">
            {loading ? "Calculating..." : "Calculate Projection"}
            {!loading && <ArrowRight className="h-4 w-4 ml-1" />}
          </Button>
        </CardContent>
      </Card>

      {loading && (
        <div className="space-y-4">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      )}

      {error && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-4 text-sm text-red-400">{error}</div>
      )}

      {result && !loading && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <MetricCard
              label="Final Balance (Nominal)"
              value={fmt(result.summary.final_nominal)}
              sub={`${(result.summary.nominal_rate * 100).toFixed(0)}% annual return`}
              tooltip="The total dollar amount at retirement before adjusting for inflation. This is what you'd see in your account."
            />
            <MetricCard
              label="Final Balance (Real)"
              value={fmt(result.summary.final_real)}
              sub={`After ${(result.summary.inflation_rate * 100).toFixed(1)}% inflation`}
              tooltip="Your balance in today's purchasing power. This is what your money will actually buy — the more honest number."
            />
            <MetricCard
              label="Total Contributed"
              value={fmt(result.summary.total_contributed)}
            />
            <MetricCard
              label="Investment Growth"
              value={fmt(result.summary.total_growth)}
              sub={`${((result.summary.total_growth / Math.max(result.summary.total_contributed, 1)) * 100).toFixed(0)}% gain`}
            />
          </div>

          {/* Target status */}
          <Card>
            <CardContent className="p-4">
              {result.target.met ? (
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-full bg-emerald-500/20 flex items-center justify-center">
                    <TrendingUp className="h-5 w-5 text-emerald-400" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-emerald-400">
                      Target of {fmt(result.target.amount)} reached at age {result.target.met_at_age}!
                    </p>
                    <p className="text-xs text-muted-foreground">
                      That&apos;s {result.target.years_to_target} years from now
                    </p>
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-full bg-amber-500/20 flex items-center justify-center">
                    <TrendingUp className="h-5 w-5 text-amber-400" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-amber-400">
                      Target of {fmt(result.target.amount)} not reached by age {targetAge}
                    </p>
                    {result.target.required_monthly !== null && (
                      <p className="text-xs text-muted-foreground">
                        You need ${result.target.required_monthly.toLocaleString(undefined, { maximumFractionDigits: 0 })}/month to reach your target
                      </p>
                    )}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Growth chart */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Projected Growth Over Time
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={350}>
                <AreaChart data={result.projections}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="age" tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} label={{ value: "Age", position: "insideBottom", offset: -5, fill: "var(--muted-foreground)" }} />
                  <YAxis
                    tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
                    tickFormatter={(v) => v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(1)}M` : `$${(v / 1000).toFixed(0)}K`}
                  />
                  <Tooltip
                    contentStyle={{ backgroundColor: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--foreground)" }}
                    formatter={(v) => [`$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`, ""]}
                    labelFormatter={(l) => `Age ${l}`}
                  />
                  <ReferenceLine y={result.target.amount} stroke="#f59e0b" strokeDasharray="3 3" label={{ value: `Target: ${fmt(result.target.amount)}`, fill: "#f59e0b", fontSize: 11 }} />
                  <Area type="monotone" dataKey="total_contributed" stroke="#6366f1" fill="#6366f1" fillOpacity={0.1} name="Contributed" />
                  <Area type="monotone" dataKey="nominal_balance" stroke="#22c55e" fill="#22c55e" fillOpacity={0.15} name="Nominal" />
                  <Area type="monotone" dataKey="real_balance" stroke="#63b4ff" fill="#63b4ff" fillOpacity={0.1} name="Real (inflation-adj)" strokeDasharray="5 3" />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Milestones */}
          {result.milestones.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Key Milestones
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                  {result.milestones.map((m) => (
                    <div key={m.amount} className="rounded-lg bg-muted/30 p-3 text-center">
                      <p className="text-sm font-bold text-primary">{fmt(m.amount)}</p>
                      <p className="text-xs text-muted-foreground">at age {m.age}</p>
                      <p className="text-[10px] text-muted-foreground">({m.year} years)</p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
