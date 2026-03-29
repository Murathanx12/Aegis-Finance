"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  TrendingUp,
  AlertTriangle,
  Briefcase,
  BarChart3,
  ArrowRight,
} from "lucide-react";
import type { MarketStatus } from "@/lib/api";

const QUICK_LINKS = [
  {
    title: "Stock Analysis",
    description: "ML-powered projections with SHAP explainability",
    href: "/stock",
    icon: TrendingUp,
  },
  {
    title: "Crash Prediction",
    description: "LightGBM + Logistic Regression, 3/6/12-month horizons",
    href: "/crash",
    icon: AlertTriangle,
  },
  {
    title: "Portfolio Builder",
    description: "Goal-based allocation with risk-adjusted returns",
    href: "/portfolio",
    icon: Briefcase,
  },
  {
    title: "Simulation",
    description: "Monte Carlo jump-diffusion with scenario analysis",
    href: "/simulation",
    icon: BarChart3,
  },
];

function StatPill({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <Badge
      variant="outline"
      className={`px-3 py-1 text-xs font-medium gap-1.5 ${color ?? "text-zinc-300 border-zinc-700"}`}
    >
      <span className="text-muted-foreground">{label}</span>
      <span className="font-semibold tabular-nums">{value}</span>
    </Badge>
  );
}

export function HeroSection({ data }: { data: MarketStatus | null }) {
  return (
    <div className="space-y-5">
      {/* Hero header */}
      <div className="space-y-3">
        <div>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight bg-gradient-to-r from-blue-400 via-cyan-400 to-emerald-400 bg-clip-text text-transparent">
            Aegis Finance
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Institutional-grade market intelligence, free and open source
          </p>
        </div>

        {/* Quick stat badges */}
        <div className="flex flex-wrap gap-2">
          {data ? (
            <>
              <StatPill
                label="S&P 500"
                value={data.sp500.toLocaleString(undefined, {
                  maximumFractionDigits: 0,
                })}
                color={
                  data.sp500_change_1m >= 0
                    ? "text-emerald-400 border-emerald-500/30"
                    : "text-red-400 border-red-500/30"
                }
              />
              <StatPill
                label="VIX"
                value={data.vix?.toFixed(1) ?? "N/A"}
                color={
                  (data.vix ?? 0) > 25
                    ? "text-red-400 border-red-500/30"
                    : (data.vix ?? 0) > 16
                      ? "text-amber-400 border-amber-500/30"
                      : "text-emerald-400 border-emerald-500/30"
                }
              />
              <StatPill
                label="Risk"
                value={data.risk_score.toFixed(2)}
                color={
                  data.risk_score > 2
                    ? "text-red-400 border-red-500/30"
                    : data.risk_score > 1
                      ? "text-amber-400 border-amber-500/30"
                      : "text-emerald-400 border-emerald-500/30"
                }
              />
              <StatPill
                label="Regime"
                value={data.regime}
                color={
                  data.regime === "Bull"
                    ? "text-emerald-400 border-emerald-500/30"
                    : data.regime === "Bear"
                      ? "text-red-400 border-red-500/30"
                      : data.regime === "Volatile"
                        ? "text-amber-400 border-amber-500/30"
                        : "text-blue-400 border-blue-500/30"
                }
              />
            </>
          ) : (
            <>
              <Skeleton className="h-6 w-28 rounded-full" />
              <Skeleton className="h-6 w-20 rounded-full" />
              <Skeleton className="h-6 w-24 rounded-full" />
              <Skeleton className="h-6 w-24 rounded-full" />
            </>
          )}
        </div>
      </div>

      {/* Quick links row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {QUICK_LINKS.map((link) => (
          <Link key={link.href} href={link.href}>
            <Card className="h-full transition-colors hover:bg-muted/50 cursor-pointer group">
              <CardContent className="flex items-start gap-3 p-4">
                <div className="rounded-lg bg-muted p-2 shrink-0">
                  <link.icon className="h-4 w-4 text-muted-foreground group-hover:text-foreground transition-colors" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium flex items-center gap-1">
                    {link.title}
                    <ArrowRight className="h-3 w-3 opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all" />
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                    {link.description}
                  </p>
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
