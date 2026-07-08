"use client";

/**
 * Risk Watch — the descriptive fragility surface (canon A3: live visibility).
 *
 * Renders what the engine last PERSISTED (fast reads, never a live recompute):
 * the structural-fragility composite, the candidate inputs collecting forward
 * (not in the composite until a trial admits them), and the alert log.
 * Everything here measures fragility; nothing predicts crashes or orders.
 */

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Activity, BellRing } from "lucide-react";

import { piGetRiskWatch } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

function levelVariant(level?: string): "default" | "secondary" | "destructive" | "outline" {
  if (!level) return "outline";
  if (level.startsWith("high")) return "destructive";
  if (level.startsWith("elevated")) return "default";
  return "secondary";
}

export default function RiskWatchPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.pi.riskWatch,
    queryFn: piGetRiskWatch,
    staleTime: 10 * 60 * 1000,
    refetchInterval: 30 * 60 * 1000,
  });

  const frag = data?.fragility;
  const candidates = data?.candidate_readings ?? {};
  const alerts = data?.alerts ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/portfolio-intelligence">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="h-4 w-4 mr-1" /> Portfolio Intelligence
          </Button>
        </Link>
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <Activity className="h-5 w-5" /> Risk Watch
        </h1>
      </div>

      {isLoading && <Skeleton className="h-96" />}
      {error && (
        <Card>
          <CardContent className="pt-4 text-sm text-destructive">
            {(error as Error).message}
          </CardContent>
        </Card>
      )}

      {data && (
        <>
          <p className="text-sm text-muted-foreground">{data.disclaimer}</p>

          {/* Composite */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Structural fragility (last persisted reading)
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {frag?.composite == null ? (
                <p className="text-sm text-muted-foreground">
                  No persisted reading yet — the daily check writes one each cycle.
                </p>
              ) : (
                <>
                  <div className="flex items-center gap-3">
                    <span className="text-3xl font-semibold">
                      {frag.composite.toFixed(2)}
                    </span>
                    <Badge variant={levelVariant(frag.level)}>{frag.level}</Badge>
                    <span className="text-xs text-muted-foreground">
                      {frag.n_inputs} inputs · evaluated{" "}
                      {frag.evaluated_at?.slice(0, 16).replace("T", " ")}
                    </span>
                  </div>
                  {frag.components && (
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(frag.components).map(([k, v]) => (
                        <Badge key={k} variant="outline">
                          {k}: {v == null ? "—" : Number(v).toFixed(2)}
                        </Badge>
                      ))}
                    </div>
                  )}
                  <p className="text-xs text-muted-foreground">{frag.label}</p>
                </>
              )}
            </CardContent>
          </Card>

          {/* Candidates */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Candidate inputs (collecting forward — NOT in the composite)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-muted-foreground border-b border-border">
                      <th className="py-2 pr-3">Candidate</th>
                      <th className="py-2 pr-3">Status</th>
                      <th className="py-2 pr-3 text-right">Latest value</th>
                      <th className="py-2">As of</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(candidates).map(([name, c]) => (
                      <tr key={name} className="border-b border-border/50">
                        <td className="py-2 pr-3 font-medium">{name}</td>
                        <td className="py-2 pr-3">
                          <Badge
                            variant={c.status === "collected" ? "secondary" : "outline"}
                          >
                            {c.status}
                          </Badge>
                        </td>
                        <td className="py-2 pr-3 text-right">
                          {c.value == null ? "—" : Number(c.value).toFixed(3)}
                        </td>
                        <td className="py-2">{c.as_of ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {/* Alerts */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                <BellRing className="h-4 w-4" /> Alerts (change events, 48h cooldown)
              </CardTitle>
            </CardHeader>
            <CardContent>
              {alerts.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No alerts yet — rules fire on regime changes and fragility
                  moves at the daily check.
                </p>
              ) : (
                <ul className="space-y-2">
                  {alerts.map((a) => (
                    <li key={a.id} className="text-sm">
                      <span className="text-muted-foreground mr-2">
                        {a.created_at?.slice(0, 16).replace("T", " ")}
                      </span>
                      <Badge variant="outline" className="mr-2">
                        {a.rule}
                      </Badge>
                      {a.message}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
