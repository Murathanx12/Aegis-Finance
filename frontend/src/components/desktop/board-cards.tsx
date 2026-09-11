"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiState, DASH, Field, RawPayload, fmtBytes } from "@/components/desktop/primitives";
import {
  getAppLog,
  getFile,
  getFleet,
  getLeaderboard,
  getLedger,
  getTree,
  getUniverse,
  type AppLogResponse,
  type FileResponse,
  type FleetResponse,
  type LeaderboardResponse,
  type LedgerResponse,
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
            <p className="mt-2 text-[10px] text-muted-foreground">{data?.graded_note}</p>
            <Receipt path={data?.path} />
            <RawPayload data={data} />
          </>
        )}
      </CardContent>
    </Card>
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
      <UniverseCard />
      <LedgerCard />
      <FleetSummaryCard />
      <NightCard />
      <CodeCard />
      <AppLogCard />
    </div>
  );
}
