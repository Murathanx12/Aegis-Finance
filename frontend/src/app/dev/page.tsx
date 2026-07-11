"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertTriangle, Brain, ExternalLink, FlaskConical } from "lucide-react";
import Link from "next/link";
import {
  getHealthFull, piGetRegistry, piGetTrackRecord,
} from "@/lib/api";
import { LANE_STYLE, LaneEquityChart } from "@/components/pi/lane-equity-chart";

const BRAIN_URL = "https://optimus-brain-alpha.vercel.app";

function uptimeLabel(s: number) {
  if (s < 3600) return `${Math.round(s / 60)}m`;
  if (s < 86400) return `${(s / 3600).toFixed(1)}h`;
  return `${(s / 86400).toFixed(1)}d`;
}

export default function DevDashboard() {
  const health = useQuery({
    queryKey: ["dev", "health-full"],
    queryFn: getHealthFull,
    refetchInterval: 5 * 60 * 1000,
  });
  const track = useQuery({
    queryKey: ["dev", "track-record"],
    queryFn: piGetTrackRecord,
    staleTime: 5 * 60 * 1000,
  });
  const registry = useQuery({
    queryKey: ["dev", "registry"],
    queryFn: piGetRegistry,
    staleTime: 10 * 60 * 1000,
  });

  const h = health.data;
  const warnings = h?.recent_warnings ?? [];

  return (
    <div className="space-y-6 animate-slide-up">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dev Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Everything the operator should track: live deploy health, the seven
          paper lanes, the experiment registry, and the brain.
        </p>
      </div>

      {/* Health row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Card>
          <CardContent className="py-4">
            <p className="text-xs text-muted-foreground uppercase">Deploy</p>
            <p className="text-lg font-bold font-mono">
              {h ? h.deploy.commit.slice(0, 7) : "…"}
            </p>
            <p className="text-xs text-muted-foreground">
              {h ? `up ${uptimeLabel(h.deploy.uptime_seconds)} · cache ${h.deploy.cache_status}` : ""}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <p className="text-xs text-muted-foreground uppercase">Scheduler</p>
            <p className="text-lg font-bold">
              {h ? (h.scheduler.running ? "running" : "DOWN") : "…"}
            </p>
            <p className="text-xs text-muted-foreground">
              {h ? `${h.scheduler.n_jobs} jobs` : ""}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <p className="text-xs text-muted-foreground uppercase">NAV freshness</p>
            <p className="text-lg font-bold">
              {h?.scheduler?.nav ? (h.scheduler.nav.all_fresh ? "all fresh" : "STALE") : "…"}
            </p>
            <p className="text-xs text-muted-foreground">
              day {h?.track_record?.age_days ?? "…"} of the record
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <p className="text-xs text-muted-foreground uppercase">LLM budget</p>
            <p className="text-lg font-bold tabular-nums">
              {h?.llm ? `${h.llm.calls_today}/${h.llm.daily_cap}` : "…"}
            </p>
            <p className="text-xs text-muted-foreground">
              {h?.llm ? (h.llm.breaker_active ? "breaker TRIPPED" : `provider: ${h.llm.provider}`) : ""}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <p className="text-xs text-muted-foreground uppercase">Warnings</p>
            <p className={`text-lg font-bold ${warnings.length > 10 ? "text-red-400" : ""}`}>
              {h ? warnings.length : "…"}
            </p>
            <p className="text-xs text-muted-foreground">last 50 kept</p>
          </CardContent>
        </Card>
      </div>

      {/* Paper lanes equity curves */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">
            Paper lanes — live forward NAV (all seeded lanes + benchmarks)
          </CardTitle>
        </CardHeader>
        <CardContent>
          {track.isLoading && <Skeleton className="h-96" />}
          {track.data && <LaneEquityChart data={track.data} />}
          {h?.track_record?.lanes && (
            <div className="flex flex-wrap gap-2 mt-3">
              {Object.entries(h.track_record.lanes).map(([id, lane]) => (
                <span key={id} className="inline-flex items-center gap-1.5 rounded-md bg-muted/40 px-2 py-1 text-xs tabular-nums">
                  <i
                    className="inline-block w-2 h-2 rounded-full"
                    style={{ background: LANE_STYLE[id]?.color ?? "#888" }}
                  />
                  {LANE_STYLE[id]?.label ?? id}:{" "}
                  {lane.since_inception_pct == null ? (
                    <span className="text-muted-foreground">no NAV yet</span>
                  ) : (
                    <span className={lane.since_inception_pct >= 0 ? "text-emerald-400" : "text-red-400"}>
                      {lane.since_inception_pct >= 0 ? "+" : ""}{lane.since_inception_pct.toFixed(2)}%
                    </span>
                  )}
                </span>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Experiment registry */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2">
            <FlaskConical className="h-4 w-4" />
            Experiment registry
            {registry.data && (
              <Badge variant="outline">{registry.data.cumulative_trials} cumulative trials</Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {registry.isLoading && <Skeleton className="h-40" />}
          {registry.data && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs uppercase text-muted-foreground border-b border-border">
                    <th className="text-left py-2 pr-3">#</th>
                    <th className="text-left py-2 pr-3">Trial</th>
                    <th className="text-left py-2 pr-3">Lane</th>
                    <th className="text-left py-2 pr-3">Verdict</th>
                    <th className="text-left py-2">Registered</th>
                  </tr>
                </thead>
                <tbody>
                  {registry.data.trials.map((t) => (
                    <tr key={t.id} className="border-b border-border/50">
                      <td className="py-2 pr-3 tabular-nums">{t.id}</td>
                      <td className="py-2 pr-3 font-mono text-xs">{t.param}</td>
                      <td className="py-2 pr-3">{t.lane_id ?? "—"}</td>
                      <td className="py-2 pr-3">
                        <Badge variant="outline">{t.verdict}</Badge>
                      </td>
                      <td className="py-2 text-xs text-muted-foreground">
                        {t.created_at?.slice(0, 10)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Recent warnings */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            Recent warnings (prod log buffer)
          </CardTitle>
        </CardHeader>
        <CardContent>
          {warnings.length === 0 && (
            <p className="text-sm text-muted-foreground">No recent warnings.</p>
          )}
          <div className="space-y-1.5 max-h-72 overflow-y-auto">
            {warnings.map((w, i) => (
              <div key={i} className="text-xs font-mono rounded bg-muted/30 px-2 py-1.5">
                <span className="text-muted-foreground">{w.ts?.slice(11, 19)}</span>{" "}
                <span className={w.level === "ERROR" ? "text-red-400" : "text-amber-400"}>
                  {w.level}
                </span>{" "}
                <span className="text-muted-foreground">{w.logger}</span> — {w.message}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Links */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <a href={BRAIN_URL} target="_blank" rel="noreferrer">
          <Card className="hover:border-primary/50 transition-colors h-full">
            <CardContent className="py-4 flex items-center gap-3">
              <Brain className="h-5 w-5" />
              <div>
                <p className="font-semibold text-sm">Optimus Brain map</p>
                <p className="text-xs text-muted-foreground">
                  interactive knowledge map <ExternalLink className="inline h-3 w-3" />
                </p>
              </div>
            </CardContent>
          </Card>
        </a>
        <Link href="/portfolio-intelligence/track-record">
          <Card className="hover:border-primary/50 transition-colors h-full">
            <CardContent className="py-4">
              <p className="font-semibold text-sm">Full track record</p>
              <p className="text-xs text-muted-foreground">the canonical forward record</p>
            </CardContent>
          </Card>
        </Link>
        <Link href="/portfolio-intelligence/risk-watch">
          <Card className="hover:border-primary/50 transition-colors h-full">
            <CardContent className="py-4">
              <p className="font-semibold text-sm">Risk Watch</p>
              <p className="text-xs text-muted-foreground">fragility, candidates, alerts</p>
            </CardContent>
          </Card>
        </Link>
      </div>
    </div>
  );
}
