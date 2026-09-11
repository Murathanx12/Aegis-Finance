"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertTriangle, Cpu, RefreshCw, Server, Square } from "lucide-react";
import {
  ApiState,
  DASH,
  Field,
  RawPayload,
  ageLabel,
  fmtBytes,
  fmtUtc,
} from "@/components/desktop/primitives";
import {
  clearStopFile,
  errorText,
  getBalances,
  getLlama,
  getServices,
  startLlama,
  stopLlama,
  stopPid,
  type LlamaActionResponse,
  type LlamaStatus,
  type ServicesResponse,
} from "@/lib/control-api";
import { BoardCards } from "@/components/desktop/board-cards";

/**
 * The local model has FOUR states, and only one of them is "up".
 *
 * `listening` is the port being bound; `ready` is `/health` answering 200. A
 * 30B-A3B at Q4 is ~18.6 GB and binds the port seconds before it can answer, so
 * `listening && !ready` is LOADING. Rendering that as "up" is how a page tells
 * the user a request will work when it will not — the house failure mode,
 * dressed as a green badge.
 */
type LlamaPhase = "ready" | "loading" | "down" | "unknown";

function phaseOf(st: LlamaStatus | undefined): LlamaPhase {
  if (!st) return "unknown";
  if (st.ready) return "ready";
  if (st.listening) return "loading";
  return "down";
}

function PhaseBadge({ phase }: { phase: LlamaPhase }) {
  if (phase === "ready") return <Badge>ready</Badge>;
  if (phase === "loading")
    return <Badge variant="secondary">loading the model</Badge>;
  if (phase === "down") return <Badge variant="outline">not running</Badge>;
  return <Badge variant="outline">unknown</Badge>;
}

function vramLabel(st: LlamaStatus | undefined): string | null {
  const v = st?.vram;
  if (!v) return null;
  const used = typeof v.used_mib === "number" ? v.used_mib : null;
  const total = typeof v.total_mib === "number" ? v.total_mib : null;
  if (used == null && total == null) return null;
  const gb = (m: number) => `${(m / 1024).toFixed(2)} GB`;
  const pair =
    used != null && total != null
      ? `${gb(used)} of ${gb(total)}`
      : used != null
        ? gb(used)
        : `${gb(total as number)} total`;
  return v.gpu ? `${pair} · ${v.gpu}` : pair;
}

/**
 * Start / stop the local model.
 *
 * The stop path is deliberately two-step for a FOREIGN server. `POST
 * /llama/stop` on a process Aegis did not start returns a 200 carrying
 * `needs_confirmation: true` and a `detail` saying what is about to be killed —
 * it may be several GB into somebody else's job. This panel shows that detail
 * and only then offers the re-post with `allow_foreign=true`. The refusal is not
 * an obstacle to route around; it is the sentence the user has to read.
 */
function LocalAiCard({ services }: { services: ServicesResponse | undefined }) {
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState<LlamaActionResponse | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const llama = useQuery({
    queryKey: ["desktop", "llama"],
    queryFn: getLlama,
    // 3s while the weights load, so "loading" turns into "ready" on its own.
    refetchInterval: (q) => (q.state.data?.listening && !q.state.data?.ready ? 3_000 : 10_000),
    retry: false,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["desktop", "llama"] });
    qc.invalidateQueries({ queryKey: ["desktop", "services"] });
  };

  const start = useMutation({
    mutationFn: startLlama,
    onSuccess: (d) => {
      setNote(
        [d.action, d.reason, d.note, d.waited_s != null ? `waited ${d.waited_s}s` : null]
          .filter(Boolean)
          .join(" — ") || "start requested",
      );
      invalidate();
    },
    onError: (e) => setNote(`start failed — ${errorText(e)}`),
  });

  const stop = useMutation({
    mutationFn: (allowForeign: boolean) => stopLlama(allowForeign),
    onSuccess: (d) => {
      if (d.needs_confirmation) {
        // Not an error and not a stop: a question, held until it is answered.
        setConfirm(d);
        setNote(null);
        return;
      }
      setConfirm(null);
      setNote(
        [d.action, d.reason, d.note, d.escalated_to_force ? "escalated to force" : null]
          .filter(Boolean)
          .join(" — ") || "stop requested",
      );
      invalidate();
    },
    onError: (e) => {
      setConfirm(null);
      setNote(`stop failed — ${errorText(e)}`);
    },
  });

  const st = llama.data;
  const phase = phaseOf(st);
  const probe = services?.local_gguf;
  const foreign = st?.foreign ?? null;
  const vram = vramLabel(st);

  return (
    <Card>
      <CardHeader className="border-b">
        <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
          <Cpu className="size-4" /> Local AI
          <PhaseBadge phase={phase} />
          {foreign ? <Badge variant="destructive">foreign process</Badge> : null}
          {st?.started_by_aegis ? <Badge variant="outline">started by Aegis</Badge> : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        {phase === "loading" ? (
          <p className="mb-2 rounded-md bg-muted/40 px-2 py-1.5 text-[11px] text-muted-foreground">
            The port is bound but <span className="font-mono">/health</span> has not
            returned 200 yet: the weights are still loading. Requests sent now will
            fail. This panel re-checks every 3 seconds.
          </p>
        ) : null}

        <Field label="URL" value={st?.url ?? probe?.url ?? null} mono />
        <Field label="Model" value={st?.model ?? null} mono />
        <Field label="PID" value={st?.pid ?? null} mono />
        <Field label="Started" value={st?.started_utc ? fmtUtc(st.started_utc) : null} />
        <Field label="VRAM" value={vram} />
        <Field
          label="Model file on disk"
          value={
            st == null ? null : st.model_present ? (
              <Badge variant="outline">present</Badge>
            ) : (
              <Badge variant="destructive">missing</Badge>
            )
          }
          title={st?.model_path}
        />
        <Field
          label="llama-server binary"
          value={
            st == null ? null : st.binary_present ? (
              <Badge variant="outline">present</Badge>
            ) : (
              <Badge variant="destructive">missing</Badge>
            )
          }
          title={st?.binary_path}
        />
        <Field label="MoE layers kept on CPU" value={st?.n_cpu_moe ?? null} />
        <Field label="Detail" value={st?.detail ?? probe?.detail ?? null} />

        {foreign ? (
          <p className="mt-2 flex gap-1.5 text-[11px] text-muted-foreground">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
            <span>
              Something is serving on this port that Aegis did not start. It may be
              several GB into a job that is not ours, so stopping it needs an explicit
              confirmation rather than one click.
            </span>
          </p>
        ) : null}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={start.isPending || st?.listening === true}
            onClick={() => start.mutate()}
            title={
              st?.listening
                ? "a server is already on this port; a second copy of the weights would fit in neither"
                : undefined
            }
          >
            {start.isPending ? "starting…" : "Start"}
          </Button>

          <Button
            size="sm"
            variant={foreign ? "destructive" : "outline"}
            disabled={stop.isPending || st?.listening === false}
            onClick={() => stop.mutate(false)}
          >
            <Square className="size-3.5" />
            {stop.isPending
              ? "stopping…"
              : foreign
                ? "Stop — started outside Aegis"
                : "Stop local AI"}
          </Button>
        </div>

        {confirm ? (
          <div className="mt-3 space-y-2 rounded-lg border border-destructive/40 p-2">
            <p className="text-[11px] text-destructive">
              {confirm.detail ?? confirm.reason ?? "the backend asked for confirmation"}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="xs"
                variant="destructive"
                disabled={stop.isPending}
                onClick={() => stop.mutate(true)}
              >
                Stop it anyway
              </Button>
              <Button size="xs" variant="ghost" onClick={() => setConfirm(null)}>
                Leave it running
              </Button>
            </div>
          </div>
        ) : null}

        <div className="mt-2 space-y-1">
          <ApiState error={llama.error} what="Local AI status" />
          {note ? (
            <p className="text-[11px] font-mono text-muted-foreground break-all">{note}</p>
          ) : null}
        </div>
        <RawPayload data={st ?? probe} label="raw local-AI payload" />
      </CardContent>
    </Card>
  );
}

function RunsCard({ services }: { services: ServicesResponse | undefined }) {
  const qc = useQueryClient();
  const [note, setNote] = useState<string | null>(null);

  const stop = useMutation({
    mutationFn: (pid: number) => stopPid(pid, 0),
    onSuccess: (d) => {
      setNote(d.detail);
      qc.invalidateQueries({ queryKey: ["desktop", "services"] });
    },
    onError: (e) => setNote(errorText(e)),
  });
  const clear = useMutation({
    mutationFn: clearStopFile,
    onSuccess: (d) => {
      setNote(d.cleared ? "STOP file cleared" : "no STOP file was present");
      qc.invalidateQueries({ queryKey: ["desktop", "services"] });
    },
    onError: (e) => setNote(errorText(e)),
  });

  const runs = services?.runs ?? [];

  return (
    <Card>
      <CardHeader className="border-b">
        <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
          Registered runs
          <Badge variant="outline">{runs.length} in registry</Badge>
          {services?.stop_file_present ? (
            <Badge variant="destructive">STOP file present</Badge>
          ) : null}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {runs.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            The control plane has no run registered. Nothing was started from this app
            since the backend came up — a job started from a terminal is not in this
            registry, and this page will not signal a PID it did not write down.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-muted-foreground">
                <tr className="border-b border-border/60">
                  <th className="py-1.5 text-left font-medium">Job</th>
                  <th className="py-1.5 text-left font-medium">PID</th>
                  <th className="py-1.5 text-left font-medium">State</th>
                  <th className="py-1.5 text-right font-medium">Log size</th>
                  <th className="py-1.5 text-right font-medium">Last write</th>
                  <th className="py-1.5 text-right font-medium">Started</th>
                  <th className="py-1.5" />
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {runs.map((r) => (
                  <tr key={r.pid} className="border-b border-border/30 last:border-0">
                    <td className="py-1.5 font-mono">{r.job || DASH}</td>
                    <td className="py-1.5 font-mono">{r.pid}</td>
                    <td className="py-1.5">
                      {r.alive == null ? (
                        <Badge variant="outline">unknown</Badge>
                      ) : r.alive ? (
                        <Badge>alive</Badge>
                      ) : (
                        <Badge variant="secondary">exited</Badge>
                      )}
                    </td>
                    <td className="py-1.5 text-right">{fmtBytes(r.log_size_bytes)}</td>
                    <td className="py-1.5 text-right text-muted-foreground">
                      {ageLabel(r.log_mtime_utc)}
                    </td>
                    <td className="py-1.5 text-right text-muted-foreground">
                      {fmtUtc(r.started_utc)}
                    </td>
                    <td className="py-1.5 text-right">
                      <span className="inline-flex gap-1">
                        <Button size="xs" variant="ghost" asChild>
                          <Link href={`/desktop/night?pid=${r.pid}`}>log</Link>
                        </Button>
                        <Button
                          size="xs"
                          variant="outline"
                          disabled={stop.isPending || r.alive === false}
                          onClick={() => stop.mutate(r.pid)}
                        >
                          stop
                        </Button>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            disabled={clear.isPending}
            onClick={() => clear.mutate()}
          >
            Clear STOP file
          </Button>
          <span className="text-[11px] text-muted-foreground">
            Stop writes the queue&apos;s STOP file first, then signals that one PID from
            the registry. Never by image name.
          </span>
        </div>
        {note ? (
          <p className="mt-2 text-[11px] font-mono text-muted-foreground break-all">{note}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

export default function DesktopServicesPage() {
  const services = useQuery({
    queryKey: ["desktop", "services"],
    queryFn: getServices,
    refetchInterval: 5_000,
    retry: false,
  });
  const balances = useQuery({
    queryKey: ["desktop", "balances"],
    queryFn: getBalances,
    refetchInterval: 60_000,
    retry: false,
  });

  const s = services.data;
  const reading = balances.data?.deepseek_balance_last_reading ?? null;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Server className="size-4" /> Backend
              {services.isError ? (
                <Badge variant="destructive">unreachable</Badge>
              ) : s ? (
                <Badge>answering</Badge>
              ) : null}
              <Button
                size="icon-xs"
                variant="ghost"
                className="ml-auto"
                onClick={() => services.refetch()}
                aria-label="refresh"
              >
                <RefreshCw className="size-3" />
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {services.isLoading ? (
              <Skeleton className="h-28" />
            ) : (
              <>
                <Field label="PID" value={s?.backend?.pid} mono />
                <Field label="Repo" value={s?.backend?.cwd} mono />
                <Field
                  label="Control plane"
                  value={
                    s == null ? null : s.control_enabled ? (
                      <Badge>enabled</Badge>
                    ) : (
                      <Badge variant="secondary">read-only</Badge>
                    )
                  }
                />
                <Field label="Night dir" value={s?.night_dir} mono />
                <Field
                  label="STOP file"
                  value={
                    s == null ? null : s.stop_file_present ? (
                      <Badge variant="destructive">present</Badge>
                    ) : (
                      <Badge variant="outline">absent</Badge>
                    )
                  }
                />
                <Field label="Jobs available" value={s?.jobs_available?.length ?? null} />
                <Field label="Server time (UTC)" value={fmtUtc(s?.utc)} />
                <Field
                  label="DeepSeek balance (provider's own line)"
                  value={reading ? JSON.stringify(reading) : null}
                  mono
                  title={balances.data?.source}
                />
                <ApiState error={services.error} what="Services" />
                <ApiState error={balances.error} what="Balances" />
              </>
            )}
          </CardContent>
        </Card>

        <LocalAiCard services={s} />
      </div>

      <RunsCard services={s} />

      {s?.jobs_available?.length ? (
        <Card>
          <CardHeader className="border-b">
            <CardTitle className="text-sm">Whitelisted jobs</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-1.5">
              {s.jobs_available.map((j) => (
                <Badge key={j} variant="outline" className="font-mono">
                  {j}
                </Badge>
              ))}
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground">
              Derived from the night queue itself, not re-typed here. Only these ids can
              be started, and no free text reaches a shell.
            </p>
          </CardContent>
        </Card>
      ) : null}

      {/* THE BOARD (O4). The desktop app's home page is the operator's own
          surface: the universe, the ledger, the fleet with its standard error,
          last night, the code that runs it and the log it writes. Every card
          prints a number with its receipt path, or an em dash. */}
      <BoardCards />
    </div>
  );
}
