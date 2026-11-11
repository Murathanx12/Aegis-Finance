"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ApiState,
  DASH,
  Field,
  RawPayload,
  YesNo,
} from "@/components/desktop/primitives";
import {
  errorText,
  getReader,
  readerOff,
  readerOn,
  type ReaderStamp,
  type ReaderStatus,
} from "@/lib/control-api";
import { cn } from "@/lib/utils";

/**
 * The web reader: ONE switch (CH-22b, 2026-11-11).
 *
 * This page replaces the separate "Aegis Reader" program. OFF writes the
 * supervisor's own pause file and kills nothing; ON removes only a pause this
 * app wrote and asks the keeper to start a supervisor if none is alive. A pause
 * someone else wrote is shown and never removed from here.
 *
 * Every number is read from the reader's own status files. A stamp older than
 * the freshness limit is printed as STALE, never as the current state.
 */

const RUNNING = new Set([
  "READING", "STARTING", "REPAIRING", "STALLED", "WAITING_FOR_CAP",
  "WAITING_FOR_RESOURCES", "QUEUE_EMPTY", "REFILLING", "PAUSED",
]);

function ago(st: ReaderStamp | undefined | null): string {
  if (!st || st.age_s == null) return st?.freshness?.toLowerCase() ?? DASH;
  const a = Math.max(0, st.age_s);
  const txt = a < 90 ? `${Math.round(a)} s ago` : a < 5400 ? `${Math.round(a / 60)} min ago`
    : `${(a / 3600).toFixed(1)} h ago`;
  return st.freshness === "FRESH" ? txt : `${txt} (${st.freshness.toLowerCase()})`;
}

function StateBadge({ s }: { s: ReaderStatus }) {
  const tone = RUNNING.has(s.actual)
    ? s.actual === "READING" ? "default" : "secondary"
    : s.actual === "STOP_REQUESTED" || s.actual === "STOPPED" ? "outline" : "destructive";
  return <Badge variant={tone}>{s.actual.replace(/_/g, " ").toLowerCase()}</Badge>;
}

function Switch({ on, busy, onToggle }: { on: boolean; busy: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label="Reader on or off"
      disabled={busy}
      onClick={onToggle}
      className={cn(
        "relative inline-flex h-8 w-16 shrink-0 items-center rounded-full border transition-colors",
        "focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        "disabled:cursor-wait disabled:opacity-60",
        on ? "border-primary bg-primary" : "border-border bg-muted",
      )}
    >
      <span
        className={cn(
          "inline-block size-6 rounded-full bg-background shadow transition-transform",
          on ? "translate-x-9" : "translate-x-1",
        )}
      />
    </button>
  );
}

function HostTable({ s }: { s: ReaderStatus }) {
  const byHost = s.pages.ok_60m_by_host ?? {};
  const classes = s.supervisor.classes_60m_by_host ?? {};
  const hosts = Array.from(new Set([...Object.keys(byHost), ...Object.keys(classes)]));
  hosts.sort((a, b) => (byHost[b] ?? 0) - (byHost[a] ?? 0) || a.localeCompare(b));
  if (!hosts.length) {
    return <p className="text-xs text-muted-foreground">{DASH} no page in the last hour</p>;
  }
  return (
    <table className="w-full text-[11px]">
      <thead>
        <tr className="border-b border-border text-left text-muted-foreground">
          <th className="py-1 pr-2 font-medium">host</th>
          <th className="py-1 pr-2 text-right font-medium">OK, 60 min</th>
          <th className="py-1 font-medium">other outcomes (supervisor, 60 min)</th>
        </tr>
      </thead>
      <tbody>
        {hosts.map((h) => {
          const other = Object.entries(classes[h] ?? {}).filter(([k]) => k !== "OK");
          return (
            <tr key={h} className="border-b border-border/40 last:border-0">
              <td className="py-1 pr-2 font-mono">{h}</td>
              <td className="py-1 pr-2 text-right tabular-nums">{byHost[h] ?? 0}</td>
              <td className="py-1 text-muted-foreground">
                {other.length ? other.map(([k, v]) => `${k.toLowerCase()} ${v}`).join(" · ") : DASH}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default function ReaderPage() {
  const qc = useQueryClient();
  const [note, setNote] = useState<string | null>(null);
  const q = useQuery<ReaderStatus>({
    queryKey: ["control", "reader"],
    queryFn: getReader,
    refetchInterval: 10_000,
  });
  const after = (s: ReaderStatus | null | undefined) => {
    if (s) qc.setQueryData(["control", "reader"], s);
    qc.invalidateQueries({ queryKey: ["control", "reader"] });
  };
  const on = useMutation({
    mutationFn: readerOn,
    onSuccess: (d) => {
      setNote(`ON: ${d.action.replace(/_/g, " ")}. ${d.detail}`);
      after(d.status);
    },
    onError: (e) => {
      setNote(`ON refused: ${errorText(e)}`);
      after(null);
    },
  });
  const off = useMutation({
    mutationFn: readerOff,
    onSuccess: (d) => {
      setNote(`OFF: ${d.result.replace(/_/g, " ").toLowerCase()}. ${d.detail}`);
      after(d.status);
    },
    onError: (e) => {
      setNote(`OFF refused: ${errorText(e)}`);
      after(null);
    },
  });
  const s = q.data;
  const busy = on.isPending || off.isPending;

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="lg:col-span-2">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Web reader</CardTitle>
        </CardHeader>
        <CardContent>
          {q.error ? (
            <ApiState error={q.error} what="the reader status" />
          ) : q.isLoading || !s ? (
            <Skeleton className="h-24 w-full" />
          ) : (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-4">
                <Switch
                  on={s.desired === "ON"}
                  busy={busy}
                  onToggle={() => (s.desired === "ON" ? off.mutate() : on.mutate())}
                />
                <div className="space-y-1">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="font-medium">Switch: {s.desired}</span>
                    <StateBadge s={s} />
                    {busy ? (
                      <span className="text-xs text-muted-foreground">
                        {on.isPending ? "checking for a live supervisor…" : "writing the pause…"}
                      </span>
                    ) : null}
                  </div>
                  <p className="text-sm">{s.actual_words}</p>
                </div>
                {s.desired === "ON" && !RUNNING.has(s.actual) && s.actual !== "STOP_REQUESTED" ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => on.mutate()}
                    className="rounded-lg border border-border px-2.5 py-1 text-xs hover:bg-muted disabled:opacity-50"
                  >
                    Check and start
                  </button>
                ) : null}
              </div>
              <p className="rounded-md bg-muted/40 p-2 text-xs text-muted-foreground">
                What will happen: {s.what_will_happen}
              </p>
              {s.stop_marker.present && s.stop_marker.owner !== "this_app" ? (
                <div className="rounded-md border border-border p-2 text-xs">
                  <span className="font-medium">
                    Pause held by{" "}
                    {s.stop_marker.owner === "retired_controller"
                      ? "the retired Aegis Reader program (this app may lift it)"
                      : "someone else (not removed from here)"}
                  </span>
                  <pre className="mt-1 whitespace-pre-wrap font-mono text-[10px] text-muted-foreground">
                    {s.stop_marker.content || "(empty file)"}
                  </pre>
                </div>
              ) : null}
              {note ? (
                <p className="break-words font-mono text-[10px] text-muted-foreground">{note}</p>
              ) : null}
            </div>
          )}
        </CardContent>
      </Card>

      {s ? (
        <>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Pages</CardTitle>
            </CardHeader>
            <CardContent>
              <Field label="OK pages, last 10 min" value={s.pages.ok_10m ?? s.supervisor.pages_ok_10m ?? null} />
              <Field label="OK pages, last 60 min" value={s.pages.ok_60m ?? s.supervisor.pages_ok_60m ?? null} />
              <Field label="last successful page" value={ago(s.pages.last_ok)} />
              <Field label="reading now (hosts)" value={(s.supervisor.current_hosts ?? []).join(", ") || null} />
              <Field label="next action" value={s.supervisor.next_action ?? null} />
              <Field label="last error" value={s.supervisor.last_error ?? null} />
              <div className="mt-3">
                <HostTable s={s} />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Machine</CardTitle>
            </CardHeader>
            <CardContent>
              <Field label="supervisor status written" value={ago(s.supervisor.stamp)} />
              <Field label="supervisor pid (as logged)" value={s.supervisor_log.supervisor_pid_as_logged ?? null} mono />
              <Field label="supervisor started" value={ago(s.supervisor_log.started).replace(/ \(stale\)$/, "")} />
              {s.supervisor_log.ended_why ? (
                <Field label="last run ended" value={`${ago(s.supervisor_log.ended).replace(/ \(stale\)$/, "")}: ${s.supervisor_log.ended_why}`} />
              ) : null}
              <Field label="pool pid (as reported)" value={s.pool.status.pid_as_reported ?? s.supervisor.pool_pid_as_reported ?? null} mono />
              <Field label="pool status written" value={ago(s.pool.status.stamp)} />
              <Field
                label="free disk"
                value={s.disk.free_gb == null ? null : `${s.disk.free_gb} GB (supervisor stops under ${s.disk.floor_gb ?? DASH} GB)`}
              />
              <Field label="free RAM (as reported)" value={s.supervisor.free_ram_gb == null ? null : `${s.supervisor.free_ram_gb} GB`} />
              <div className="flex items-baseline justify-between py-1">
                <span className="text-xs text-muted-foreground">OpenClaw gateway port {s.gateway.port ?? ""}</span>
                <YesNo v={s.gateway.answers} yes="answers" no="no answer" />
              </div>
              <div className="flex items-baseline justify-between py-1">
                <span className="text-xs text-muted-foreground">dedicated Chrome port {s.chrome.port ?? ""}</span>
                <YesNo v={s.chrome.answers} yes="answers" no="no answer" />
              </div>
              <div className="flex items-baseline justify-between py-1">
                <span className="text-xs text-muted-foreground">HANDOFF_PC present</span>
                <YesNo v={s.handoff_present} yes="yes" no="absent" />
              </div>
              <Field label="IIF quiet window now" value={s.iif_quiet_now == null ? null : s.iif_quiet_now ? "yes (16:45-17:05)" : "no"} />
              <RawPayload data={s} />
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}
