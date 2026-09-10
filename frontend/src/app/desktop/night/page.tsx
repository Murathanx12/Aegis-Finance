"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Play, Square } from "lucide-react";
import {
  ApiState,
  DASH,
  Field,
  ageLabel,
  fmtBytes,
} from "@/components/desktop/primitives";
import {
  clearStopFile,
  errorText,
  getJobs,
  getLeaderboard,
  getRunLog,
  getServices,
  runJob,
  runNight,
  stopPid,
  type ControlRun,
} from "@/lib/control-api";

const NIGHT_HOURS = 4;

/**
 * The leaderboard is a markdown file the night factory writes. It is rendered as
 * text, not parsed into numbers: parsing it here would create a second copy of
 * every headline number, and a number belongs to its receipt.
 */
function LeaderboardCard() {
  const lb = useQuery({
    queryKey: ["desktop", "leaderboard"],
    queryFn: getLeaderboard,
    refetchInterval: 30_000,
    retry: false,
  });

  return (
    <Card>
      <CardHeader className="border-b">
        <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
          Leaderboard
          {lb.data?.receipts?.length != null ? (
            <Badge variant="outline">{lb.data.receipts.length} receipts</Badge>
          ) : null}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {lb.isLoading ? <Skeleton className="h-40" /> : null}
        <ApiState error={lb.error} what="Leaderboard" />
        {lb.data && lb.data.markdown == null ? (
          <p className="text-xs text-muted-foreground">
            No LEADERBOARD.md at{" "}
            <span className="font-mono">{lb.data.path}</span> yet — the night factory
            writes it. Nothing is shown in its place.
          </p>
        ) : null}
        {lb.data?.markdown ? (
          <pre className="max-h-[28rem] overflow-auto rounded-md bg-muted/40 p-3 text-[11px] leading-relaxed font-mono whitespace-pre">
            {lb.data.markdown}
          </pre>
        ) : null}
        {lb.data?.receipts?.length ? (
          <details className="mt-3">
            <summary className="cursor-pointer text-[11px] text-muted-foreground hover:text-foreground">
              receipt files
            </summary>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {lb.data.receipts.map((r) => (
                <Badge key={r} variant="outline" className="font-mono text-[10px]">
                  {r}
                </Badge>
              ))}
            </div>
          </details>
        ) : null}
      </CardContent>
    </Card>
  );
}

function LogView({ pid, job }: { pid: number; job: string | null }) {
  const [follow, setFollow] = useState(true);
  const boxRef = useRef<HTMLPreElement | null>(null);

  const log = useQuery({
    queryKey: ["desktop", "run-log", pid],
    queryFn: () => getRunLog(pid),
    refetchInterval: 2_000,
    retry: false,
  });

  useEffect(() => {
    if (follow && boxRef.current) {
      boxRef.current.scrollTop = boxRef.current.scrollHeight;
    }
  }, [log.data?.tail, follow]);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" className="font-mono">
          pid {pid}
        </Badge>
        <Badge variant="outline" className="font-mono">
          {job ?? log.data?.job ?? DASH}
        </Badge>
        {log.data ? (
          log.data.alive ? (
            <Badge>alive</Badge>
          ) : (
            <Badge variant="secondary">exited</Badge>
          )
        ) : null}
        <Button
          size="xs"
          variant={follow ? "default" : "outline"}
          onClick={() => setFollow((f) => !f)}
        >
          {follow ? "following" : "follow"}
        </Button>
        <span className="text-[11px] text-muted-foreground font-mono break-all">
          {log.data?.log ?? ""}
        </span>
      </div>
      <ApiState error={log.error} what="Run log" />
      <pre
        ref={boxRef}
        className="h-80 overflow-auto rounded-md bg-muted/40 p-3 text-[11px] leading-relaxed font-mono whitespace-pre-wrap"
      >
        {log.data?.tail === "" ? "(log file is empty)" : (log.data?.tail ?? "")}
      </pre>
      <p className="text-[11px] text-muted-foreground">
        Tail of the process&apos;s own stdout, polled every 2s. A job that writes its
        receipt only at exit shows nothing here but its log — that is the log, not the
        result.
      </p>
    </div>
  );
}

function NightRunsInner() {
  const qc = useQueryClient();
  const params = useSearchParams();
  const [selected, setSelected] = useState<number | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [job, setJob] = useState<string>("");

  const services = useQuery({
    queryKey: ["desktop", "services"],
    queryFn: getServices,
    refetchInterval: 5_000,
    retry: false,
  });
  // The job ids come from `/jobs`, which reads the night queue itself and splits
  // it into tonight's queue and the extras. Nothing here is a typed-in id: only
  // a whitelisted one can be started, so no free text ever reaches a shell.
  const jobs = useQuery({
    queryKey: ["desktop", "jobs"],
    queryFn: getJobs,
    refetchInterval: 60_000,
    retry: false,
  });

  const runs: ControlRun[] = services.data?.runs ?? [];
  const urlPid = Number(params.get("pid"));
  const activePid =
    selected ??
    (Number.isFinite(urlPid) && urlPid > 0 ? urlPid : null) ??
    runs.find((r) => r.alive)?.pid ??
    runs[runs.length - 1]?.pid ??
    null;
  const activeJob = runs.find((r) => r.pid === activePid)?.job ?? null;

  const invalidate = () => qc.invalidateQueries({ queryKey: ["desktop", "services"] });

  const night = useMutation({
    mutationFn: () => runNight(NIGHT_HOURS),
    onSuccess: (d) => {
      setNote(`started ${d.job} as pid ${d.pid}`);
      setSelected(d.pid);
      invalidate();
    },
    onError: (e) => setNote(errorText(e)),
  });
  const one = useMutation({
    mutationFn: (j: string) => runJob(j),
    onSuccess: (d) => {
      setNote(`started ${d.job} as pid ${d.pid}`);
      setSelected(d.pid);
      invalidate();
    },
    onError: (e) => setNote(errorText(e)),
  });
  const stop = useMutation({
    mutationFn: (pid: number) => stopPid(pid, 0),
    onSuccess: (d) => {
      setNote(d.detail);
      invalidate();
    },
    onError: (e) => setNote(errorText(e)),
  });
  const clear = useMutation({
    mutationFn: clearStopFile,
    onSuccess: (d) => {
      setNote(d.cleared ? "STOP file cleared" : "no STOP file was present");
      invalidate();
    },
    onError: (e) => setNote(errorText(e)),
  });

  const queue = jobs.data?.queue ?? [];
  const extra = jobs.data?.extra ?? [];
  // `/jobs` is the source; `/services` carries the same whitelist and is the
  // fallback so the picker is not empty merely because one read failed.
  const fallback = services.data?.jobs_available ?? [];
  const jobsAvailable = queue.length || extra.length ? [...queue, ...extra] : fallback;
  const controlEnabled = services.data?.control_enabled ?? null;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="border-b">
          <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
            Run tonight&apos;s queue
            {controlEnabled === false ? (
              <Badge variant="secondary">control plane read-only</Badge>
            ) : null}
            {services.data?.stop_file_present ? (
              <Badge variant="destructive">STOP file present</Badge>
            ) : null}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button
              disabled={night.isPending || controlEnabled === false}
              onClick={() => night.mutate()}
            >
              <Play className="size-3.5" />
              {night.isPending ? "starting…" : `Run tonight's queue (${NIGHT_HOURS}h budget)`}
            </Button>
            {activePid ? (
              <Button
                variant="outline"
                disabled={stop.isPending}
                onClick={() => stop.mutate(activePid)}
              >
                <Square className="size-3.5" />
                Stop pid {activePid}
              </Button>
            ) : null}
            <Button
              variant="ghost"
              size="sm"
              disabled={clear.isPending}
              onClick={() => clear.mutate()}
              title="a STOP file left behind by an earlier run makes the next queue exit immediately"
            >
              Clear STOP file
            </Button>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <select
              value={job}
              onChange={(e) => setJob(e.target.value)}
              className="h-8 rounded-lg border border-border bg-background px-2 text-xs"
              aria-label="single job"
            >
              <option value="">— run a single job —</option>
              {queue.length ? (
                <optgroup label="tonight's queue">
                  {queue.map((j) => (
                    <option key={j} value={j}>
                      {j}
                    </option>
                  ))}
                </optgroup>
              ) : null}
              {extra.length ? (
                <optgroup label="not in the queue">
                  {extra.map((j) => (
                    <option key={j} value={j}>
                      {j}
                    </option>
                  ))}
                </optgroup>
              ) : null}
              {!queue.length && !extra.length
                ? fallback.map((j) => (
                    <option key={j} value={j}>
                      {j}
                    </option>
                  ))
                : null}
            </select>
            <Button
              size="sm"
              variant="outline"
              disabled={!job || one.isPending || controlEnabled === false}
              onClick={() => one.mutate(job)}
            >
              Run job
            </Button>
            <span className="text-[11px] text-muted-foreground">
              Ids come from the queue itself ({jobsAvailable.length} whitelisted
              {queue.length ? `, ${queue.length} in tonight's queue` : ""}).
            </span>
          </div>
          <ApiState error={jobs.error} what="Jobs" />

          {note ? (
            <p className="text-[11px] font-mono text-muted-foreground break-all">{note}</p>
          ) : null}
          <ApiState error={services.error} what="Services" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="border-b">
          <CardTitle className="text-sm">Live log</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {runs.length ? (
            <div className="flex flex-wrap gap-1.5">
              {runs.map((r) => (
                <Button
                  key={r.pid}
                  size="xs"
                  variant={r.pid === activePid ? "default" : "outline"}
                  onClick={() => setSelected(r.pid)}
                >
                  <span className="font-mono">{r.job}</span>
                  <span className="opacity-60">
                    {r.pid} · {fmtBytes(r.log_size_bytes)} · {ageLabel(r.log_mtime_utc)}
                  </span>
                </Button>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              No run is registered with this control plane, so there is no log to tail.
            </p>
          )}
          {activePid ? <LogView pid={activePid} job={activeJob} /> : null}
        </CardContent>
      </Card>

      <LeaderboardCard />

      <Card>
        <CardHeader className="border-b">
          <CardTitle className="text-sm">Where these numbers live</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1">
          <Field label="Night directory" value={services.data?.night_dir ?? null} mono />
          <Field label="Receipts read from" value={services.data?.night_dir ?? null} mono />
        </CardContent>
      </Card>
    </div>
  );
}

export default function NightRunsPage() {
  // useSearchParams needs a Suspense boundary for the static export build.
  return (
    <Suspense fallback={<Skeleton className="h-64" />}>
      <NightRunsInner />
    </Suspense>
  );
}
