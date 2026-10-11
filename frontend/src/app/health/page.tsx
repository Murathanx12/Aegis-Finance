"use client";

/**
 * /health — System Health (chunk C19, 2026-10-07).
 *
 * The newest health probe receipt: every row grouped by verdict with its fine
 * state, the age of each row's evidence from the producer's own stamp, the
 * process census (C14), the task-owner table (which receipt proves each
 * scheduled task) and the "same output for X h" rows highlighted. The one-line
 * summary at the top is byte-identical to the daily pass's health line.
 *
 * Read-only: GET /api/legibility/v1/system-health.
 */

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, Brain, Cpu, Repeat } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getSystemHealth, getHealthFullWithSubsystems, type HealthProbeRow, type ServiceAlarm } from "@/lib/api";
import { currentPanelLight, currentServiceLight } from "@/lib/service-alarm";
import {
  LoadError, Missing, MissingList, ReceiptStrip, SourceNote, StaleBanner, fmtAgeSeconds,
} from "@/components/legibility/receipts";

const VERDICT_TONE: Record<string, string> = {
  DEAD: "text-red-700 dark:text-red-400",
  STALE: "text-red-700 dark:text-red-400",
  REFUSED: "text-red-700 dark:text-red-400",
  UNKNOWN: "text-amber-700 dark:text-amber-400",
  STOPPED_BY_OPERATOR: "text-sky-700 dark:text-sky-400",
  ALIVE: "text-emerald-700 dark:text-emerald-400",
};

const LIGHT_TONE: Record<string, string> = {
  RED: VERDICT_TONE.DEAD, AMBER: VERDICT_TONE.UNKNOWN,
  BLUE: VERDICT_TONE.STOPPED_BY_OPERATOR, GREEN: VERDICT_TONE.ALIVE,
};

function alarmTone(alarm: ServiceAlarm | undefined, current: boolean, now: number) {
  return LIGHT_TONE[currentServiceLight({ alarm }, current, now)];
}

function groupTone(rows: HealthProbeRow[], current: boolean, now: number) {
  const lights = rows.map((r) => currentServiceLight(r, current, now));
  if (lights.includes("RED")) return LIGHT_TONE.RED;
  if (!current || lights.includes("AMBER")) return LIGHT_TONE.AMBER;
  if (lights.includes("BLUE")) return LIGHT_TONE.BLUE;
  return rows.length ? LIGHT_TONE.GREEN : LIGHT_TONE.AMBER;
}

function Row({ r, current, now }: { r: HealthProbeRow; current: boolean; now: number }) {
  const light = currentServiceLight(r, current, now);
  return (
    <li className={`py-2 ${r.same_output ? "rounded bg-red-500/10 px-2" : ""}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-mono text-xs font-semibold break-all">{r.name}</span>
        <span className={`whitespace-nowrap text-[11px] ${LIGHT_TONE[light] ?? LIGHT_TONE.AMBER}`}>
          {light} · {r.state}{r.same_output ? " · SAME OUTPUT" : ""} · evidence {r.age_s_now == null ? <Missing why={r.missing_because} /> : `${fmtAgeSeconds(r.age_s_now)} old now`}
          {r.age_s_at_probe != null ? ` (${fmtAgeSeconds(r.age_s_at_probe)} at probe)` : ""}
        </span>
      </div>
      {r.detail && <p className="text-xs text-muted-foreground break-words">{r.detail}</p>}
      {r.proof && <p className="font-mono text-[10px] text-muted-foreground break-all">proof: {r.proof}</p>}
    </li>
  );
}

export default function HealthPage() {
  const q = useQuery({ queryKey: ["system-health"], queryFn: getSystemHealth, retry: 1, refetchInterval: 60_000 });
  const overall = useQuery({ queryKey: ["brain", "health"], queryFn: getHealthFullWithSubsystems, retry: 1, refetchInterval: 60_000 });
  const d = q.data;
  const [showAlive, setShowAlive] = useState(true);
  const [clock, setClock] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 15_000);
    return () => window.clearInterval(timer);
  }, []);
  const generated = d?.generated_utc ? Date.parse(d.generated_utc) : NaN;
  const current = !q.error && d?.observation_current === true && d.alarm?.schema === "health_alarm/1"
    && Number.isFinite(generated) && clock - generated >= -30_000 && clock - generated <= 2 * 3600_000
    && clock - q.dataUpdatedAt >= -30_000 && clock - q.dataUpdatedAt <= 2 * 60_000;
  const overallCurrent = !overall.error && !!overall.data
    && (overall.data.status === "ok" || overall.data.status === "DEGRADED")
    && clock - overall.dataUpdatedAt >= -30_000 && clock - overall.dataUpdatedAt <= 2 * 60_000;
  const overallBroken = overall.data?.status === "DEGRADED";
  const allRows = (d?.groups ?? []).flatMap((g) => g.rows);
  const light = q.error || overall.error || overallBroken || d?.alarm?.light === "RED" ? "RED"
    : currentPanelLight(allRows, d?.alarm, current && overallCurrent, clock);
  return (
    <div className="space-y-5 animate-slide-up">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-3xl">
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight"><Activity className="h-6 w-6" /> System Health</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Every verdict is derived from evidence the producer wrote. A stale output is red even when the process is alive.
          </p>
        </div>
        <Link href="/brain" className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-xs hover:bg-muted"><Brain className="h-3.5 w-3.5" /> Optimus Brain</Link>
      </div>
      {q.isLoading && <Skeleton className="h-40 w-full" />}
      {q.error && <LoadError what="System Health" err={q.error} />}
      {overall.error && <LoadError what="Backend health" err={overall.error} />}
      <div role={light === "RED" || light === "AMBER" ? "alert" : "status"} aria-live="polite"
        className={`rounded-lg border border-current/25 p-3 ${LIGHT_TONE[light] ?? LIGHT_TONE.AMBER}`}>
        <p className="font-semibold">Service control panel · {light}</p>
        <p className="mt-1 text-xs">{q.error || overall.error ? "Health could not be read. Cached activity is unverified."
          : overallBroken ? "The backend reports a fault. Its recorded reasons are below."
          : !overallCurrent ? "No current overall backend observation. Service health is unverified."
          : !current ? "No current verified health observation. Existing fault records remain visible."
          : light === "RED" ? "A service is failed, refused or stalled. Review the named evidence below."
          : light === "AMBER" ? "Service evidence is missing or unavailable."
          : light === "BLUE" ? "One or more services are intentionally paused; they are not active."
          : "Reported services have verified activity or a declared idle period."}</p>
        {(overall.data?.degraded_reasons ?? []).map((reason,i) => <p key={i} className="mt-1 text-xs">{reason}</p>)}
      </div>
      {d && (
        <>
          <StaleBanner receipts={d.receipts} />
          <div className="rounded-lg border border-border bg-card p-3">
            <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Daily pass health line (identical)</div>
            <p className="mt-1 font-mono text-sm break-words">{d.health_line}</p>
            <SourceNote>{d.receipts[0]?.file} · probed {d.generated_utc}</SourceNote>
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            {Object.entries(d.state_counts ?? {}).map(([k, v]) => (
              <span key={k} className="rounded border border-border px-2 py-1 font-mono">{k} {v}</span>
            ))}
          </div>

          {d.same_output_rows.length > 0 && (
            <Card className="border-red-600/40">
              <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2 text-base"><Repeat className="h-4 w-4" /> Same output, no progress ({d.same_output_rows.length})</CardTitle></CardHeader>
              <CardContent><ul>{d.same_output_rows.map((r) => <Row key={r.name} r={r} current={current} now={clock} />)}</ul></CardContent>
            </Card>
          )}
          <p className="text-xs text-muted-foreground">{d.same_output_rule}.</p>

          <Card>
            <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2 text-base"><Cpu className="h-4 w-4" /> Process census (C14)</CardTitle></CardHeader>
            <CardContent>
              {d.process_census.length ? <ul>{d.process_census.map((r) => <Row key={r.name} r={r} current={current} now={clock} />)}</ul>
                : <p className="text-sm"><Missing why={d.missing_because.process_census} /></p>}
            </CardContent>
          </Card>

          {d.groups.map((g) => {
            const hidden = g.verdict === "ALIVE" && !showAlive;
            return (
              <Card key={g.verdict}>
                <CardHeader className="pb-2">
                  <CardTitle className={`flex flex-wrap items-center gap-2 text-base ${groupTone(g.rows,current,clock)}`}>
                    {g.verdict !== "ALIVE" && <AlertTriangle className="h-4 w-4" />}{g.verdict} ({g.n})
                    <span className="text-xs font-normal text-muted-foreground">{Object.entries(g.states).map(([k, v]) => `${k} ${v}`).join(" · ")}</span>
                    {g.verdict === "ALIVE" && <button className="ml-auto text-xs font-normal underline" onClick={() => setShowAlive((v) => !v)}>{showAlive ? "hide" : "show"}</button>}
                  </CardTitle>
                </CardHeader>
                {!hidden && <CardContent><ul className="divide-y divide-border/40">{g.rows.map((r) => <Row key={r.name} r={r} current={current} now={clock} />)}</ul></CardContent>}
              </Card>
            );
          })}

          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-base">Task owners: which receipt proves each scheduled task</CardTitle></CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead><tr className="text-left text-muted-foreground"><th className="pr-3">Task</th><th className="pr-3">State</th><th className="pr-3">Receipt it must write</th><th className="pr-3">Cadence</th><th>Notes</th></tr></thead>
                  <tbody>
                    {d.task_owners.map((t) => (
                      <tr key={t.task} className="border-t border-border/40 align-top">
                        <td className="py-1 pr-3 font-mono">{t.task}</td>
                        <td className={`pr-3 ${alarmTone(t.alarm,current,clock)}`}>{t.state ?? <Missing why={t.missing_because} />}</td>
                        <td className="pr-3 font-mono text-[11px] break-all">{t.receipt}</td>
                        <td className="whitespace-nowrap pr-3">{t.cadence_h} h{t.session_only ? " (sessions)" : ""}</td>
                        <td className="text-muted-foreground">{[t.retired ? "retired" : null, t.registered_only ? "judged only when registered" : null, t.hash_rule_off ? `hash rule off: ${t.hash_rule_off}` : null].filter(Boolean).join("; ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <SourceNote>backend/services/task_receipts.py TASK_RECEIPT + config.HEALTH_TASK_CADENCE_H, joined to the receipt&apos;s task:* rows</SourceNote>
            </CardContent>
          </Card>
          {d.read_me_first && <p className="text-xs text-muted-foreground">{d.read_me_first}</p>}
          <MissingList missing={d.missing_because} />
          <ReceiptStrip receipts={d.receipts} />
        </>
      )}
    </div>
  );
}
