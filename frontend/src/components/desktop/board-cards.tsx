"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiState, DASH, Field, RawPayload, fmtBytes } from "@/components/desktop/primitives";
import {
  errorText,
  getAppLog,
  getCoverage,
  getFile,
  getFleet,
  getLeaderboard,
  getLedger,
  getMorning,
  getTree,
  getUniverse,
  runMorning,
  type AppLogResponse,
  type CoverageResponse,
  type FileResponse,
  type FleetResponse,
  type LeaderboardResponse,
  type CalibrationReport,
  type LedgerResponse,
  type MorningResponse,
  type MorningStep,
  type TreeResponse,
  type UniverseResponse,
} from "@/lib/control-api";

/**
 * THE DEVELOPER BOARD (O4) — the cards below the services block.
 *
 * ONE RULE, and it is the reason this file exists rather than a dashboard
 * template: every number is printed with the path of the receipt it came from,
 * or it is an em dash. There is no third option — no "—" that is really a zero,
 * no rounded stand-in, no number whose provenance is "the code computed it
 * somewhere". A card that cannot name its source prints the dash and says why.
 */

function n(v: unknown, digits = 2): string {
  return typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : DASH;
}

function Receipt({ path }: { path: string | null | undefined }) {
  if (!path) return null;
  return (
    <p className="mt-2 break-all font-mono text-[10px] text-muted-foreground">{path}</p>
  );
}

// ------------------------------------------------------------------ universe

export function UniverseCard() {
  const { data, error, isLoading } = useQuery<UniverseResponse>({
    queryKey: ["control", "board", "universe"],
    queryFn: () => getUniverse({ limit: 1 }),
  });
  return (
    <Card>
      <CardHeader className="pb-2 flex flex-row items-center justify-between">
        <CardTitle className="text-sm">Universe</CardTitle>
        <Link href="/desktop/universe">
          <Button size="sm" variant="ghost">
            open
          </Button>
        </Link>
      </CardHeader>
      <CardContent>
        {error ? (
          <ApiState error={error} what="the universe" />
        ) : isLoading ? (
          <Skeleton className="h-14 w-full" />
        ) : (
          <>
            <p className="text-2xl font-semibold tabular-nums">
              {typeof data?.universe_rows === "number" ? data.universe_rows : DASH}
            </p>
            <p className="text-xs text-muted-foreground">names in the tracker universe</p>
            <Field label="vintage" value={data?.universe_day ?? null} mono />
            <Receipt path={data?.universe_source} />
          </>
        )}
      </CardContent>
    </Card>
  );
}

// -------------------------------------------------------------------- ledger

export function LedgerCard() {
  const { data, error, isLoading } = useQuery<LedgerResponse>({
    queryKey: ["control", "ledger"],
    queryFn: getLedger,
  });
  const health = (data?.health ?? {}) as Record<string, unknown>;
  const cal = (data?.calibration_by_model ?? {}) as Record<string, unknown>;
  const groups = (cal.groups ?? {}) as Record<string, Record<string, unknown>>;
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Forecast ledger</CardTitle>
      </CardHeader>
      <CardContent>
        {error ? (
          <ApiState error={error} what="the ledger" />
        ) : isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <>
            <div className="flex items-baseline gap-4">
              <div>
                <p className="text-2xl font-semibold tabular-nums">
                  {typeof data?.n_open === "number" ? data.n_open : DASH}
                </p>
                <p className="text-xs text-muted-foreground">open forecasts</p>
              </div>
              <div>
                <p className="text-2xl font-semibold tabular-nums">
                  {typeof data?.graded_last_24h === "number" ? data.graded_last_24h : DASH}
                </p>
                <p className="text-xs text-muted-foreground">graded in 24 h</p>
              </div>
            </div>
            <div className="mt-2">
              <Field
                label="status"
                value={
                  typeof health.status === "string" ? (
                    <Badge variant={health.status === "ok" ? "outline" : "secondary"}>
                      {health.status}
                    </Badge>
                  ) : null
                }
              />
              <Field label="records" value={n(health.n_records, 0)} />
              <Field label="resolved" value={n(health.n_resolved, 0)} />
              <Field label="overdue (actionable)" value={n(health.n_overdue_actionable, 0)} />
            </div>
            <div className="mt-2 border-t border-border pt-2">
              <p className="text-xs text-muted-foreground">Brier by model</p>
              {Object.keys(groups).length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  {DASH}{" "}
                  {typeof cal.reading === "string"
                    ? cal.reading
                    : "nothing has resolved yet"}
                </p>
              ) : (
                Object.entries(groups).map(([model, g]) => (
                  <Field
                    key={model}
                    label={model}
                    value={`${n(g.brier, 4)} (n=${n(g.n, 0)}, climatology ${n(
                      g.climatology_brier,
                      4,
                    )})`}
                    mono
                  />
                ))
              )}
            </div>
            {/* MURPHY'S SPLIT (M4). A flat Brier cannot tell a forecaster
                that always says the base rate (perfectly reliable, zero
                resolution) from one that is genuinely informative. */}
            <div className="mt-3 border-t border-border pt-2">
              <p className="text-xs text-muted-foreground">Calibration</p>
              <div className="mt-1 flex items-start gap-3">
                <ReliabilityDiagram slice={data?.decomposition?.overall} />
                <div className="min-w-0 flex-1">
                  <Field label="reliability (lower is better)"
                         value={n(data?.decomposition?.overall?.reliability, 4)} />
                  <Field label="resolution (higher is better)"
                         value={n(data?.decomposition?.overall?.resolution, 4)} />
                  <Field label="uncertainty (the sample's own base rate)"
                         value={n(data?.decomposition?.overall?.uncertainty, 4)} />
                  <Field label="beats climatology"
                         value={
                           typeof data?.decomposition?.overall?.beats_climatology === "boolean" ? (
                             <Badge variant={data.decomposition.overall.beats_climatology ? "outline" : "secondary"}>
                               {data.decomposition.overall.beats_climatology ? "yes" : "no"}
                             </Badge>
                           ) : null
                         } />
                  <Field label="base-rate control (PIT)"
                         value={`${n(data?.decomposition?.base_rate_row?.brier, 4)} (n=${n(
                           data?.decomposition?.base_rate_row?.n, 0)})`} mono />
                  <Field label="persistence r (quarter to quarter)"
                         value={
                           data?.decomposition?.persistence?.persistence === "ok"
                             ? `${n(data.decomposition.persistence.r, 3)} (${n(
                                 data.decomposition.persistence.n_pairs, 0)} pairs)`
                             : `${DASH} ${data?.decomposition?.persistence?.persistence ?? ""}`
                         } />
                </div>
              </div>
            </div>
            <p className="mt-2 text-[10px] text-muted-foreground">{data?.graded_note}</p>
            <Receipt path={data?.path} />
            <RawPayload data={data} />
          </>
        )}
      </CardContent>
    </Card>
  );
}


/**
 * THE RELIABILITY DIAGRAM (M4), as inline SVG.
 *
 * x = what the forecaster said, y = what happened. The diagonal is perfect
 * calibration; a point above it means the forecaster was UNDER-confident at
 * that level and below it means over-confident. Each point carries its bin's
 * binomial standard error as a vertical whisker, because a bin of eighteen and
 * a bin of eight hundred should not look alike.
 *
 * It draws NOTHING when the decomposition was refused. A curve through four
 * points is a picture of four points.
 */
function ReliabilityDiagram({ slice }: { slice: CalibrationReport["overall"] }) {
  const bins = slice?.bins ?? [];
  if (!slice || slice.decomposition !== "ok" || bins.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        {DASH} {slice?.reason ?? "no decomposition yet"}
      </p>
    );
  }
  const S = 160;
  const pad = 18;
  const x = (v: number) => pad + v * (S - 2 * pad);
  const y = (v: number) => S - pad - v * (S - 2 * pad);
  return (
    <svg
      viewBox={`0 0 ${S} ${S}`}
      className="h-40 w-40"
      role="img"
      aria-label="Reliability diagram: forecast probability against realised outcome rate"
    >
      <rect x={pad} y={pad} width={S - 2 * pad} height={S - 2 * pad}
            fill="none" stroke="currentColor" strokeOpacity={0.18} />
      <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)}
            stroke="currentColor" strokeOpacity={0.3} strokeDasharray="3 3" />
      {bins.map((b) => (
        <g key={b.bin_id}>
          <line
            x1={x(b.mean_forecast)}
            y1={y(Math.max(0, b.mean_outcome - b.outcome_se))}
            x2={x(b.mean_forecast)}
            y2={y(Math.min(1, b.mean_outcome + b.outcome_se))}
            stroke="currentColor"
            strokeOpacity={0.45}
          />
          <circle cx={x(b.mean_forecast)} cy={y(b.mean_outcome)} r={2.5}
                  fill="currentColor" />
        </g>
      ))}
      <text x={pad} y={S - 4} fontSize={7} fill="currentColor" fillOpacity={0.6}>
        said
      </text>
      <text x={2} y={pad + 6} fontSize={7} fill="currentColor" fillOpacity={0.6}>
        happened
      </text>
    </svg>
  );
}

// --------------------------------------------------------------------- fleet

export function FleetSummaryCard() {
  const { data, error, isLoading } = useQuery<FleetResponse>({
    queryKey: ["control", "fleet"],
    queryFn: getFleet,
  });
  const agg = data?.aggregate;
  return (
    <Card>
      <CardHeader className="pb-2 flex flex-row items-center justify-between">
        <CardTitle className="text-sm">Fleet vs {data?.benchmark?.symbol ?? "SPY"}</CardTitle>
        <Link href="/desktop/fleet">
          <Button size="sm" variant="ghost">
            open
          </Button>
        </Link>
      </CardHeader>
      <CardContent>
        {error ? (
          <ApiState error={error} what="the fleet" />
        ) : isLoading ? (
          <Skeleton className="h-20 w-full" />
        ) : (
          <>
            <Field label="lanes" value={data?.lanes?.length ?? null} />
            <Field label="age (days)" value={data?.age_days ?? null} />
            <Field label="mean daily excess %" value={n(agg?.mean_daily_excess_pct, 4)} />
            {/* The standard error is printed BESIDE the mean, always. A daily
                excess without its SE is a number with no width, and at four
                sessions the honest answer is that nothing is estimable yet. */}
            <Field label="se daily excess %" value={n(agg?.se_daily_excess_pct, 4)} />
            <Field label="t" value={n(agg?.t_stat, 2)} />
            <Field
              label="estimable"
              value={
                typeof agg?.estimable === "boolean" ? (
                  <Badge variant={agg.estimable ? "outline" : "secondary"}>
                    {agg.estimable ? "yes" : "not yet"}
                  </Badge>
                ) : null
              }
            />
            {agg?.why_not_estimable && (
              <p className="mt-1 text-[11px] text-muted-foreground">{agg.why_not_estimable}</p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------------- night

export function NightCard() {
  const { data, error, isLoading } = useQuery<LeaderboardResponse>({
    queryKey: ["control", "leaderboard"],
    queryFn: getLeaderboard,
  });
  const head = (data?.markdown ?? "").split("\n").slice(0, 12).join("\n");
  return (
    <Card>
      <CardHeader className="pb-2 flex flex-row items-center justify-between">
        <CardTitle className="text-sm">Last night</CardTitle>
        <Link href="/desktop/night">
          <Button size="sm" variant="ghost">
            open
          </Button>
        </Link>
      </CardHeader>
      <CardContent>
        {error ? (
          <ApiState error={error} what="the leaderboard" />
        ) : isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : data?.markdown ? (
          <>
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-muted/40 p-2 font-mono text-[11px]">
              {head}
            </pre>
            <Field label="receipts" value={data.receipts?.length ?? null} />
            <Receipt path={data.path} />
          </>
        ) : (
          <p className="text-xs text-muted-foreground">
            {DASH} no LEADERBOARD.md in {data?.path ?? "the night directory"}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// ----------------------------------------------------------------- code tree

export function CodeCard() {
  const [root, setRoot] = useState("scripts");
  const [path, setPath] = useState<string | null>(null);
  const tree = useQuery<TreeResponse>({
    queryKey: ["control", "tree", root],
    queryFn: () => getTree(root),
  });
  const file = useQuery<FileResponse>({
    queryKey: ["control", "file", path],
    queryFn: () => getFile(path as string),
    enabled: !!path,
  });
  return (
    <Card className="lg:col-span-2">
      <CardHeader className="pb-2 flex flex-row items-center justify-between gap-2">
        <CardTitle className="text-sm">Code</CardTitle>
        <select
          value={root}
          onChange={(e) => {
            setRoot(e.target.value);
            setPath(null);
          }}
          aria-label="Code root"
          className="h-8 rounded-md border border-border bg-background px-2 text-xs"
        >
          {(tree.data?.roots ?? [root]).map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </CardHeader>
      <CardContent>
        {tree.error ? (
          <ApiState error={tree.error} what="the code tree" />
        ) : tree.isLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : (
          <div className="grid gap-3 md:grid-cols-[16rem_1fr]">
            <div className="max-h-72 overflow-auto rounded-md border border-border">
              <p className="sticky top-0 bg-background px-2 py-1 text-[11px] text-muted-foreground">
                {tree.data?.n_files ?? DASH} files
              </p>
              <ul className="text-[11px]">
                {(tree.data?.files ?? []).map((f) => (
                  <li key={f.path}>
                    <button
                      onClick={() => setPath(f.path)}
                      disabled={f.too_big}
                      title={f.too_big ? `${fmtBytes(f.bytes)} — over the viewer cap` : f.path}
                      className={`w-full px-2 py-0.5 text-left font-mono hover:bg-muted/60 ${
                        path === f.path ? "bg-muted" : ""
                      } ${f.too_big ? "text-muted-foreground line-through" : ""}`}
                    >
                      {f.name}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              {!path ? (
                <p className="text-xs text-muted-foreground">
                  pick a file. It is served read-only from this checkout, with the
                  last three commits that touched it.
                </p>
              ) : file.error ? (
                <ApiState error={file.error} what={path} />
              ) : file.isLoading ? (
                <Skeleton className="h-64 w-full" />
              ) : (
                <>
                  <div className="mb-1 text-[11px] text-muted-foreground">
                    {file.data?.lines ?? DASH} lines · {fmtBytes(file.data?.bytes)}
                  </div>
                  {file.data?.commits?.length ? (
                    <ul className="mb-2 font-mono text-[10px] text-muted-foreground">
                      {file.data.commits.map((c) => (
                        <li key={c}>{c}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mb-2 text-[10px] text-muted-foreground">
                      {DASH} {file.data?.git_note ?? "no commit history available"}
                    </p>
                  )}
                  <pre className="max-h-72 overflow-auto rounded-md bg-muted/40 p-2 font-mono text-[11px] leading-relaxed">
                    {file.data?.text}
                  </pre>
                  <Receipt path={file.data?.path} />
                </>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------- morning

/**
 * ONE CLICK = MORNING (O5).
 *
 * The table below is the receipt, not a summary of it: one row per DECLARED
 * step, in declared order, with the step's own five-valued status. A step that
 * refused shows the precondition it named. `nothing_to_do` is rendered
 * differently from `ok` on purpose — "it ran and there was nothing" and "it ran
 * and here are the counts" are different facts, and a green tick on both is how
 * a card starts lying quietly.
 */
const STATUS_TONE: Record<string, "ok" | "quiet" | "warn"> = {
  ok: "ok",
  nothing_to_do: "quiet",
  skipped: "quiet",
  refused: "warn",
  error: "warn",
};

function StepStatus({ status }: { status: string }) {
  const tone = STATUS_TONE[status] ?? "quiet";
  return (
    <Badge
      variant={tone === "ok" ? "outline" : tone === "warn" ? "destructive" : "secondary"}
      className="font-mono text-[10px]"
    >
      {status}
    </Badge>
  );
}

function stepDetail(row: MorningStep): string {
  const bits: string[] = [];
  for (const k of ["n_written", "n_symbols", "headlines", "n_lanes", "due",
                   "newly_resolved", "rows_on_day", "n_sources_with_rows"]) {
    const v = row[k];
    if (typeof v === "number") bits.push(`${k} ${v}`);
  }
  const why = row.reason ?? row.note;
  if (typeof why === "string" && why) bits.push(why);
  return bits.join(" · ");
}

export function MorningCard() {
  const qc = useQueryClient();
  const [note, setNote] = useState<string | null>(null);
  const latest = useQuery<MorningResponse>({
    queryKey: ["control", "morning"],
    queryFn: () => getMorning(),
  });
  const run = useMutation({
    mutationFn: () => runMorning(true),
    onSuccess: (d) => {
      setNote(`run ${d.run ?? "?"} finished in ${d.elapsed_s ?? "?"}s`);
      qc.setQueryData(["control", "morning"], { ...d, ran: true });
      qc.invalidateQueries({ queryKey: ["control", "ledger"] });
    },
    onError: (e) => setNote(`refused — ${errorText(e)}`),
  });
  const d = latest.data;
  const steps = d?.steps ?? [];
  return (
    <Card className="lg:col-span-2">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm">Morning</CardTitle>
        <Button size="sm" onClick={() => run.mutate()} disabled={run.isPending}>
          {run.isPending ? "running…" : "Run the morning"}
        </Button>
      </CardHeader>
      <CardContent>
        {latest.error ? (
          <ApiState error={latest.error} what="the morning receipt" />
        ) : latest.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : d?.ran === false ? (
          <p className="text-xs text-muted-foreground">
            {DASH} {d.note}
            <span className="mt-1 block font-mono text-[10px]">
              {(d.declared_steps ?? []).join(" → ")}
            </span>
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-baseline gap-3 text-xs text-muted-foreground">
              <span>
                {d?.date ?? DASH} · run {d?.run ?? DASH} ·{" "}
                {typeof d?.elapsed_s === "number" ? `${d.elapsed_s}s` : DASH}
              </span>
            </div>
            <table className="mt-2 w-full text-[11px]">
              <tbody>
                {steps.map((row) => (
                  <tr key={row.step} className="border-b border-border/50 align-top">
                    <td className="py-1 pr-2 font-mono">{row.step}</td>
                    <td className="py-1 pr-2">
                      <StepStatus status={row.status} />
                    </td>
                    <td className="py-1 text-muted-foreground">{stepDetail(row)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Receipt path={d?.path_rel ?? d?.path} />
            <RawPayload data={d} />
          </>
        )}
        {note ? (
          <p className="mt-2 break-all font-mono text-[10px] text-muted-foreground">{note}</p>
        ) : null}
        {run.isPending ? (
          <p className="mt-2 text-[11px] text-muted-foreground">
            It pulls the news, builds the digest, marks every lane, writes one forecast
            row per lane and grades what is due. Minutes, not seconds.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------- app log

export function AppLogCard() {
  const { data, error, isLoading } = useQuery<AppLogResponse>({
    queryKey: ["control", "app-log"],
    queryFn: () => getAppLog(200),
    refetchInterval: 15_000,
  });
  return (
    <Card className="lg:col-span-2">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">App log</CardTitle>
      </CardHeader>
      <CardContent>
        {error ? (
          <ApiState error={error} what="the app log" />
        ) : isLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : data?.exists ? (
          <>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-md bg-muted/40 p-2 font-mono text-[11px]">
              {(data.lines ?? []).join("\n")}
            </pre>
            <Field
              label="lines"
              value={`${data.lines?.length ?? 0} of ${data.n_lines_total ?? DASH}`}
            />
            <Receipt path={data.path} />
          </>
        ) : (
          <p className="text-xs text-muted-foreground">
            {DASH} {data?.note ?? "no log"}
            <span className="block font-mono text-[10px]">{data?.path}</span>
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export function BoardCards() {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <MorningCard />
      <UniverseCard />
      <CoverageCard />
      <LedgerCard />
      <FleetSummaryCard />
      <NightCard />
      <CodeCard />
      <AppLogCard />
    </div>
  );
}

// ------------------------------------------------------------- N-F coverage

/**
 * THE COVERAGE CARD (N-F).
 *
 * "Asia first" was a sentence in four documents and a number in none. This card
 * is the number: rows per region, rows today, the age of the newest row, and
 * the sources that are RED or were never pulled — named, because a region that
 * shows zero because nobody ran the pull and a region that shows zero because
 * its feed died are different problems with the same appearance.
 *
 * Two display rules follow the board's one rule (every number names its
 * receipt, or it is an em dash):
 *
 * - a source with `label_source: false` is drawn with a muted `breadth` badge.
 *   Those rows may never label a return (invariant 20), and the card is where a
 *   reader is most likely to forget that.
 * - `NEVER_PULLED` is its own state, distinct from `NO_ROWS` and from `RED`.
 */

function ageLabel(hours: number | null | undefined): string {
  if (typeof hours !== "number" || !Number.isFinite(hours)) return DASH;
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  if (hours < 48) return `${hours.toFixed(1)}h`;
  return `${(hours / 24).toFixed(1)}d`;
}

const SOURCE_STATUS_TONE: Record<string, string> = {
  OK: "text-emerald-600 dark:text-emerald-400",
  RED: "text-red-600 dark:text-red-400",
  STALE: "text-amber-600 dark:text-amber-400",
  REFUSED: "text-amber-600 dark:text-amber-400",
  NO_ROWS: "text-muted-foreground",
  NEVER_PULLED: "text-muted-foreground",
  NOT_IMPLEMENTED: "text-muted-foreground",
};

export function CoverageCard() {
  const [open, setOpen] = useState(false);
  const { data, error, isLoading } = useQuery<CoverageResponse>({
    queryKey: ["control", "coverage"],
    queryFn: getCoverage,
    refetchInterval: 60_000,
  });

  const pullable = (data?.sources ?? []).filter((s) => s.implemented);
  const shown = open ? pullable : pullable.filter((s) => s.rows_total > 0 || s.status === "RED");

  return (
    <Card className="lg:col-span-2">
      <CardHeader className="pb-2 flex flex-row items-center justify-between">
        <CardTitle className="text-sm">News coverage</CardTitle>
        <Button size="sm" variant="ghost" onClick={() => setOpen((v) => !v)}>
          {open ? "only active" : "all sources"}
        </Button>
      </CardHeader>
      <CardContent>
        {error ? (
          <ApiState error={error} what="news coverage" />
        ) : isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : !data?.available ? (
          <p className="text-xs text-muted-foreground">
            {DASH} {data?.error ?? "the source registry could not be read"}
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
              <div>
                <p className="text-2xl font-semibold tabular-nums">
                  {data.totals?.rows_total?.toLocaleString() ?? DASH}
                </p>
                <p className="text-xs text-muted-foreground">corpus rows</p>
              </div>
              <div>
                <p className="text-2xl font-semibold tabular-nums">
                  {data.asia_first?.rows_total?.toLocaleString() ?? DASH}
                </p>
                <p className="text-xs text-muted-foreground">
                  from Asia ({(data.asia_first?.regions ?? []).join(" ") || DASH})
                </p>
              </div>
              <div>
                <p className="text-2xl font-semibold tabular-nums">
                  {data.totals?.rows_today?.toLocaleString() ?? DASH}
                </p>
                <p className="text-xs text-muted-foreground">today</p>
              </div>
            </div>

            <div className="mt-2 flex flex-wrap gap-2">
              <Badge variant="outline">
                {data.totals?.implemented ?? DASH}/{data.totals?.sources ?? DASH} sources pullable
              </Badge>
              <Badge variant="outline">
                {(data.totals?.label_sources ?? []).length} may label a return
              </Badge>
              {typeof data.totals?.mean_resolution_rate === "number" ? (
                <Badge variant="outline">
                  {(data.totals.mean_resolution_rate * 100).toFixed(0)}% resolved to a symbol
                </Badge>
              ) : null}
              {(data.totals?.red ?? []).length ? (
                <Badge variant="destructive">{(data.totals?.red ?? []).length} RED</Badge>
              ) : null}
            </div>

            {shown.length ? (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-[11px]">
                  <thead className="text-muted-foreground">
                    <tr className="text-left">
                      <th className="py-1 pr-3 font-normal">source</th>
                      <th className="py-1 pr-3 font-normal">region</th>
                      <th className="py-1 pr-3 text-right font-normal">rows</th>
                      <th className="py-1 pr-3 text-right font-normal">today</th>
                      <th className="py-1 pr-3 text-right font-normal">age</th>
                      <th className="py-1 pr-3 text-right font-normal">resolved</th>
                      <th className="py-1 font-normal">status</th>
                    </tr>
                  </thead>
                  <tbody className="font-mono">
                    {shown.map((s) => (
                      <tr key={s.id} className="border-t border-border/40">
                        <td className="py-1 pr-3">
                          {s.id}
                          {s.label_source ? null : (
                            <span className="ml-1 text-[9px] text-muted-foreground">breadth</span>
                          )}
                        </td>
                        <td className="py-1 pr-3">{s.region}</td>
                        <td className="py-1 pr-3 text-right tabular-nums">
                          {s.rows_total.toLocaleString()}
                        </td>
                        <td className="py-1 pr-3 text-right tabular-nums">{s.rows_today}</td>
                        <td className="py-1 pr-3 text-right tabular-nums">
                          {ageLabel(s.last_row_age_hours)}
                        </td>
                        <td className="py-1 pr-3 text-right tabular-nums">
                          {typeof s.resolution_rate === "number"
                            ? `${(s.resolution_rate * 100).toFixed(0)}%`
                            : DASH}
                        </td>
                        <td className={`py-1 ${SOURCE_STATUS_TONE[s.status] ?? ""}`}>
                          {s.status}
                          {s.flags.length ? (
                            <span className="ml-1 text-[9px] text-muted-foreground">
                              {s.flags[0].slice(0, 60)}
                            </span>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="mt-3 text-xs text-muted-foreground">
                {DASH} no source has written a row yet. Run{" "}
                <code className="font-mono">python -m scripts.news_pull --source all --resume</code>
                {(data.totals?.never_pulled ?? []).length
                  ? ` — ${(data.totals?.never_pulled ?? []).length} sources have never been pulled.`
                  : null}
              </p>
            )}

            <p className="mt-2 text-[10px] text-muted-foreground">
              {data.analyst_snapshots?.days ?? 0} analyst snapshot day(s)
              {data.analyst_snapshots?.series_starts
                ? `, series starts ${data.analyst_snapshots.series_starts}`
                : ""}
              {" · "}
              name table names {String(data.name_table?.named_symbols ?? DASH)} of{" "}
              {String(data.name_table?.issuer_rows ?? DASH)} symbols
            </p>
            <Receipt path={data.corpus_dir} />
          </>
        )}
      </CardContent>
    </Card>
  );
}
