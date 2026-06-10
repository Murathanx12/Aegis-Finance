"use client";

import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Shield, TrendingUp, Zap, BarChart3, ArrowRight, Wrench,
} from "lucide-react";
import { MethodologyBanner } from "@/components/methodology-banner";

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

      <Link href="/portfolio-intelligence/track-record">
        <Card className="hover:border-primary/40 transition-colors cursor-pointer border-primary/30">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <TrendingUp className="h-5 w-5 text-emerald-400" />
              Live Track Record
              <Badge variant="outline" className="text-[10px]">canonical</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              The forward paper-portfolio NAV of all three lanes vs SPY, AGG,
              and 60/40 — real marks since inception, labeled segments, no
              backtests. This is the record everything else is judged against.
            </p>
            <div className="flex items-center gap-1 mt-3 text-xs text-primary">
              View the record <ArrowRight className="h-3 w-3" />
            </div>
          </CardContent>
        </Card>
      </Link>

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

      <div className="grid gap-4 md:grid-cols-3">
        <Link href="/portfolio-intelligence/my-portfolio">
          <Card className="hover:border-primary/40 transition-colors cursor-pointer h-full">
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

        <Link href="/portfolio">
          <Card className="hover:border-primary/40 transition-colors cursor-pointer h-full">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Wrench className="h-5 w-5 text-primary" />
                Build a Portfolio
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Construct a new portfolio from scratch using risk tolerance, time horizon, and
                goal — Black-Litterman, HRP, or template methods.
              </p>
            </CardContent>
          </Card>
        </Link>

        <Link href="/portfolio-intelligence/compare">
          <Card className="hover:border-primary/40 transition-colors cursor-pointer h-full">
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

      {/* Methodology label — copy governed by docs/TRACK_RECORD_POLICY.md */}
      <MethodologyBanner />
    </div>
  );
}
