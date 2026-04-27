"use client";

import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Shield, TrendingUp, Zap, BarChart3, ArrowRight,
} from "lucide-react";

const LANES = [
  {
    id: "conservative",
    label: "Conservative",
    icon: Shield,
    allocation: "40 / 50 / 10",
    desc: "Capital preservation — lowest equity, highest bonds",
    color: "text-blue-400",
    bg: "bg-blue-500/10",
  },
  {
    id: "balanced",
    label: "Balanced",
    icon: TrendingUp,
    allocation: "70 / 25 / 5",
    desc: "Balanced growth + income with macro views",
    color: "text-amber-400",
    bg: "bg-amber-500/10",
  },
  {
    id: "aggressive",
    label: "Aggressive",
    icon: Zap,
    allocation: "95 / 5 / 0",
    desc: "Maximum growth — full equity universe",
    color: "text-red-400",
    bg: "bg-red-500/10",
  },
];

export default function PortfolioIntelligencePage() {
  return (
    <div className="space-y-8 animate-slide-up">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Portfolio Intelligence</h1>
        <p className="text-muted-foreground mt-1">
          Measure whether conviction adds value over rules-based baselines.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {LANES.map((lane) => (
          <Link key={lane.id} href={`/portfolio-intelligence/reference?lane=${lane.id}`}>
            <Card className="hover:border-primary/40 transition-colors cursor-pointer h-full">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-3">
                  <div className={`rounded-lg p-2 ${lane.bg}`}>
                    <lane.icon className={`h-5 w-5 ${lane.color}`} />
                  </div>
                  <div>
                    <CardTitle className="text-base">{lane.label}</CardTitle>
                    <p className="text-xs text-muted-foreground">
                      Equity / Bond / Alt: {lane.allocation}
                    </p>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">{lane.desc}</p>
                <div className="flex items-center gap-1 mt-3 text-xs text-primary">
                  View details <ArrowRight className="h-3 w-3" />
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Link href="/portfolio-intelligence/my-portfolio">
          <Card className="hover:border-primary/40 transition-colors cursor-pointer">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <BarChart3 className="h-5 w-5 text-primary" />
                Analyze My Portfolio
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Upload your holdings to see concentration risks, factor exposures, and how you
                compare to the three reference portfolios.
              </p>
            </CardContent>
          </Card>
        </Link>

        <Link href="/portfolio-intelligence/compare">
          <Card className="hover:border-primary/40 transition-colors cursor-pointer">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Badge variant="outline" className="text-xs">Side-by-side</Badge>
                Compare All Lanes
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Side-by-side comparison of all reference portfolios, SPY, 60/40,
                and your personal holdings over selectable periods.
              </p>
            </CardContent>
          </Card>
        </Link>
      </div>

      <Card className="border-amber-500/30 bg-amber-500/5">
        <CardContent className="py-4">
          <p className="text-xs text-amber-400/80">
            Historical replay performance reflects backtested rebalancing over 2021-2025 using a
            fixed universe. Results may be inflated by survivorship bias if the universe was
            selected from current index constituents. See docs/replay_diagnostics_v1.md for details.
            This is an educational research tool, not financial advice.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
