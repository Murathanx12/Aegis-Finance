"use client";

/**
 * /brain — the Optimus brain, as a page (chunk C4, 2026-10-06).
 *
 * The owner: "fix the Optimus brain showcase page (make it visually appealing)
 * and the NN showcase, which is bugging right now". Root cause found the same
 * day: the deployed site called `<site>/[SENSITIVE]/api/...` for EVERY request
 * (a redaction placeholder sat in the API-URL build variable), and the backend
 * echoed no CORS origin for the site. Every card here rendered its empty state.
 * Both are fixed at the source (`lib/api.ts` resolveApiBase, `backend/main.py`
 * origins); this page is the visual half.
 *
 * EXISTING ENDPOINTS ONLY, NO NUMBER INVENTED:
 *  - /api/health/full -> `subsystems`: every long-running part of the brain,
 *    each verdict derived from evidence its producer wrote.
 *  - /api/ic/decisions: today's decision contract and the decision ledger's
 *    lifecycle counts (404 = the engine has not said what it would buy today).
 *  - /api/optimus/digest: the newest learning digest (404 = none written yet).
 * A 404 is printed as the fact it is, never as zeros.
 *
 * v2 (2026-10-07, spec docs/design/OPTIMUS_CREATIVE_TOOL_LIBRARY_2026-10-07.md §2):
 *  - /api/legibility/v1/brain -> the belief state board (StateBoard.tsx) replaces the old
 *    link out to the force-directed "optimus-brain-alpha" showcase (a SEPARATE repo, not
 *    touched here) for the belief/scenario/regime content; everything below the board
 *    (health, decisions, learning digest) is unchanged, just moved down.
 */

import React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity, AlertTriangle, Brain, CheckCircle2, CircleDashed, CircleSlash, Cpu,
  ExternalLink, GitBranch, Network, PauseCircle, XCircle,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  getBrainState, getDecisionContract, getHealthFullWithSubsystems, getOptimusDigest,
  type SubsystemRow,
} from "@/lib/api";
import StateBoard from "./StateBoard";
import { RegimeStrip, ScenarioStrip, WhatChanged } from "./BrainStrips";

const BRAIN_MAP_URL = "https://optimus-brain-alpha.vercel.app";

const VERDICT: Record<string, { tone: string; dot: string; icon: typeof CheckCircle2; label: string }> = {
  ALIVE: { tone: "text-emerald-700 dark:text-emerald-400", dot: "bg-emerald-500", icon: CheckCircle2, label: "alive" },
  STALE: { tone: "text-amber-700 dark:text-amber-400", dot: "bg-amber-500", icon: AlertTriangle, label: "stale" },
  DEAD: { tone: "text-red-700 dark:text-red-400", dot: "bg-red-500", icon: XCircle, label: "dead" },
  REFUSED: { tone: "text-red-700 dark:text-red-400", dot: "bg-red-500", icon: CircleSlash, label: "refused" },
  STOPPED_BY_OPERATOR: { tone: "text-sky-700 dark:text-sky-400", dot: "bg-sky-500", icon: PauseCircle, label: "stopped by operator" },
  UNKNOWN: { tone: "text-zinc-600 dark:text-zinc-400", dot: "bg-zinc-400", icon: CircleDashed, label: "unknown" },
};

/** Which probes belong to which part of the brain. A probe not listed lands in "Plumbing". */
const GROUPS: { title: string; icon: typeof Brain; blurb: string; match: (n: string) => boolean }[] = [
  {
    title: "Memory", icon: Brain,
    blurb: "The Optimus corpus the sessions read before they act.",
    match: (n) => n === "optimus_brain",
  },
  {
    title: "Neural-net lab", icon: Network,
    blurb: "The nightly NN refit and its scheduler: does tonight's head beat last night's on a fixed month?",
    match: (n) => n === "lab_loop:nn_lab" || n === "task:AegisNNLabNightly" || n === "task:AegisHypLabNightly",
  },
  {
    title: "Learning", icon: GitBranch,
    blurb: "Grading forecasts and books, the review, and the policy state the night may change.",
    match: (n) => ["learn_rota", "forecast_grader", "book_grader", "policy_state", "u_review", "forecast_ledger",
      "u_forecast", "backtest_leaderboard", "iif1_night"].includes(n),
  },
  {
    title: "Decisions", icon: Activity,
    blurb: "What the engine would buy today and whether that contract was written.",
    match: (n) => ["decision_contract", "u_plan", "ranking", "u_funnel", "accrual_canary", "live_market_loop", "daily_pass"].includes(n),
  },
  {
    title: "Senses", icon: Cpu,
    blurb: "The collectors: bars, news, social, the browser reader and the local model.",
    match: (n) => n === "bars_panel" || n.startsWith("news") || n.startsWith("social") || n.startsWith("openclaw")
      || n.startsWith("dowjones") || n.startsWith("llama"),
  },
];

function age(s: number | null): string {
  if (s == null) return "age n/a";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${(s / 3600).toFixed(1)} h ago`;
  return `${(s / 86400).toFixed(1)} d ago`;
}

function ProbeRow({ r }: { r: SubsystemRow }) {
  const v = VERDICT[r.verdict] ?? VERDICT.UNKNOWN;
  const Icon = v.icon;
  return (
    <li className="flex items-start gap-2.5 py-2 border-b border-border/40 last:border-0">
      <Icon className={`h-4 w-4 mt-0.5 shrink-0 ${v.tone}`} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-mono text-xs font-semibold truncate">{r.name}</span>
          <span className={`text-[11px] whitespace-nowrap ${v.tone}`}>{v.label} · {age(r.age_s)}</span>
        </div>
        {r.detail && <p className="text-xs text-muted-foreground line-clamp-2" title={r.detail}>{r.detail}</p>}
      </div>
    </li>
  );
}

function StatusError({ what, err }: { what: string; err: unknown }) {
  const msg = err instanceof Error ? err.message : String(err);
  const absent = /\b404\b/.test(msg);
  return (
    <p className={`text-sm ${absent ? "text-muted-foreground" : "text-red-700 dark:text-red-400"}`}>
      {absent ? `${what}: none written yet.` : `${what} could not be read.`}{" "}
      <span className="text-xs text-muted-foreground">{msg}</span>
    </p>
  );
}

export default function BrainPage() {
  const brain = useQuery({ queryKey: ["brain", "state"], queryFn: getBrainState, refetchInterval: 5 * 60_000, retry: false });
  const health = useQuery({ queryKey: ["brain", "health"], queryFn: getHealthFullWithSubsystems, refetchInterval: 5 * 60_000, retry: 1 });
  const decisions = useQuery({ queryKey: ["brain", "decisions"], queryFn: () => getDecisionContract(), retry: false });
  const digest = useQuery({ queryKey: ["brain", "digest"], queryFn: getOptimusDigest, retry: false });

  const sub = health.data?.subsystems;
  const rows = sub?.rows ?? [];
  const grouped = GROUPS.map((g) => ({ ...g, rows: rows.filter((r) => g.match(r.name)) }));
  const claimed = new Set(grouped.flatMap((g) => g.rows.map((r) => r.name)));
  const plumbing = rows.filter((r) => !claimed.has(r.name));
  const counts = sub?.counts ?? {};
  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  const d = decisions.data;
  // Actionable rows first (BUY, WATCH, SELL), then PROBE; one line per ticker.
  const DIR_RANK: Record<string, number> = { BUY: 0, WATCH: 1, SELL: 2, PROBE: 3 };
  const shownDecisions = (() => {
    const seen = new Set<string>();
    return (d?.rows ?? [])
      .filter((r) => r.direction !== "REFUSED")
      .sort((a, b) => (DIR_RANK[a.direction] ?? 9) - (DIR_RANK[b.direction] ?? 9))
      .filter((r) => (seen.has(r.ticker) ? false : (seen.add(r.ticker), true)))
      .slice(0, 8);
  })();
  const g = digest.data;

  return (
    <div className="space-y-6 animate-slide-up">
      {/* hero */}
      <div className="relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-violet-500/10 via-sky-500/5 to-emerald-500/10 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-2xl">
            <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
              <Brain className="h-7 w-7 text-violet-600 dark:text-violet-400" /> Optimus Brain
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              The memory and learning loop behind Aegis: what it remembers, what it graded, what it decided today,
              and whether each part is actually running. Every verdict below comes from a file its producer wrote,
              never from a process saying it is fine.
            </p>
          </div>
          <a href={BRAIN_MAP_URL} target="_blank" rel="noopener noreferrer"
            title="A separate, older showcase (optimus-brain-alpha, different repo): a force-directed graph, not this page's state board"
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background/70 px-3 py-2 text-sm hover:bg-muted">
            <Network className="h-4 w-4" /> Older force-graph showcase <ExternalLink className="h-3 w-3" />
          </a>
        </div>
        {/* verdict strip */}
        <div className="mt-5">
          {health.isLoading && <Skeleton className="h-3 w-full" />}
          {total > 0 && (
            <>
              <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted">
                {Object.entries(counts).filter(([, n]) => n > 0).map(([k, n]) => (
                  <div key={k} className={(VERDICT[k] ?? VERDICT.UNKNOWN).dot} style={{ width: `${(100 * n) / total}%` }}
                    title={`${k}: ${n}`} />
                ))}
              </div>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
                {Object.entries(counts).filter(([, n]) => n > 0).map(([k, n]) => (
                  <span key={k} className="inline-flex items-center gap-1.5">
                    <i className={`inline-block h-2 w-2 rounded-full ${(VERDICT[k] ?? VERDICT.UNKNOWN).dot}`} />
                    <span className="tabular-nums font-semibold">{n}</span> {(VERDICT[k] ?? VERDICT.UNKNOWN).label}
                  </span>
                ))}
                <span className="text-muted-foreground">
                  · {total} probes · read {sub?.generated_utc?.slice(0, 16).replace("T", " ")} UTC ({sub?.source})
                </span>
              </div>
            </>
          )}
          {health.error && <StatusError what="Brain health" err={health.error} />}
          {sub?.error && <p className="text-sm text-red-700 dark:text-red-400">Health block error: {sub.error}</p>}
        </div>
      </div>

      {/* belief state board (v2, 2026-10-07): fixed rings, state-driven motion, every pixel
          traces to a field in /api/legibility/v1/brain. See StateBoard.tsx's header comment
          for why this replaces a force graph. */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2"><Brain className="h-4 w-4" /> Belief state board</CardTitle>
          <p className="text-xs text-muted-foreground">
            Fixed rings (macro / sector-theme / geopolitical), one orb per belief. Motion fires once, only on a
            real state change -- never a continuous loop.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {brain.isLoading && <Skeleton className="h-72" />}
          {brain.error && <StatusError what="Belief state" err={brain.error} />}
          {brain.data && <StateBoard data={brain.data} />}
          {brain.data && (
            <div className="grid gap-4 lg:grid-cols-3">
              <div>
                <p className="text-xs font-semibold mb-1.5">Scenarios (display probability only)</p>
                <ScenarioStrip data={brain.data} />
              </div>
              <div>
                <p className="text-xs font-semibold mb-1.5">Regime rows vs their two baselines</p>
                <RegimeStrip data={brain.data} />
              </div>
              <div>
                <p className="text-xs font-semibold mb-1.5">
                  What changed since the last cycle ({brain.data.belief_updates.length} of up to 40)
                </p>
                <WhatChanged data={brain.data} />
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* health by part of the brain */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {grouped.map((grp) => {
          const Icon = grp.icon;
          return (
            <Card key={grp.title}>
              <CardHeader className="pb-1">
                <CardTitle className="text-sm flex items-center gap-2"><Icon className="h-4 w-4" /> {grp.title}</CardTitle>
                <p className="text-xs text-muted-foreground">{grp.blurb}</p>
              </CardHeader>
              <CardContent>
                {health.isLoading ? <Skeleton className="h-16" /> : grp.rows.length ? (
                  <ul>{grp.rows.map((r) => <ProbeRow key={r.name} r={r} />)}</ul>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    No probe for this part answered on this server{sub?.source === "railway_local" ? " (the website backend does not run the PC loops)" : ""}.
                  </p>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* decision ledger */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2"><Activity className="h-4 w-4" /> Decision ledger: today&apos;s contract</CardTitle>
          </CardHeader>
          <CardContent className="text-sm space-y-3">
            {decisions.isLoading && <Skeleton className="h-24" />}
            {decisions.error && <StatusError what="Today's decision contract" err={decisions.error} />}
            {d && (
              <>
                <p className="text-xs text-muted-foreground">
                  {d.date} · written {d.written_utc?.slice(0, 16).replace("T", " ")} UTC · {d.n_rows} rows · {d.licence}
                </p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(d.count_by_direction ?? {}).map(([k, n]) => (
                    <Badge key={k} variant="outline" className="tabular-nums">{k} {n}</Badge>
                  ))}
                </div>
                {d.ledger?.count_by_state && (
                  <div>
                    <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1.5">Lifecycle, as the ledger records it</p>
                    <ol className="relative border-l border-border pl-4 space-y-2">
                      {Object.entries(d.ledger.count_by_state).map(([state, n]) => (
                        <li key={state}>
                          <span className="absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full border-2 border-background bg-violet-500" />
                          <span className="font-mono text-xs">{state}</span>{" "}
                          <span className="tabular-nums font-semibold">{n}</span>
                        </li>
                      ))}
                    </ol>
                    {d.ledger.note && <p className="mt-2 text-xs text-muted-foreground">{d.ledger.note}</p>}
                  </div>
                )}
                {shownDecisions.length > 0 && (
                  <ul className="text-xs space-y-1">
                    {shownDecisions.map((r) => (
                      <li key={r.decision_id} className="flex gap-2">
                        <Badge variant="outline">{r.direction}</Badge>
                        <span className="font-mono font-semibold">{r.ticker}</span>
                        <span className="text-muted-foreground line-clamp-1">{r.falsifier}</span>
                      </li>
                    ))}
                  </ul>
                )}
                <Link href="/investment-committee" className="text-xs text-sky-700 dark:text-sky-400 hover:underline">
                  The full contract on the Investment Committee page
                </Link>
              </>
            )}
          </CardContent>
        </Card>

        {/* learning digest */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2"><GitBranch className="h-4 w-4" /> Latest learning digest</CardTitle>
          </CardHeader>
          <CardContent className="text-sm space-y-3">
            {digest.isLoading && <Skeleton className="h-24" />}
            {digest.error && <StatusError what="Learning digest" err={digest.error} />}
            {g && (
              <>
                <p className="text-xs text-muted-foreground">
                  {g.day} · generated {g.generated_at?.slice(0, 16).replace("T", " ")} UTC · {g.n_ok} sections with data,
                  {" "}{g.n_ok_empty} empty, {g.unavailable.length} unavailable · documentation only, never a signal
                </p>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(g.section_statuses).map(([name, st]) => {
                    const sec = g.sections[name] ?? {};
                    const facts = Object.entries(sec)
                      .filter(([k, v]) => k !== "status" && (typeof v === "number" || typeof v === "string") && String(v).length < 40)
                      .slice(0, 3);
                    const tone = st === "ok" ? "border-emerald-500/40" : st === "ok_empty" ? "border-border" : "border-amber-500/40";
                    return (
                      <div key={name} className={`rounded-lg border ${tone} p-2.5`}>
                        <p className="text-xs font-semibold flex justify-between"><span>{name}</span><span className="text-muted-foreground font-normal">{st}</span></p>
                        {facts.map(([k, v]) => (
                          <p key={k} className="text-[11px] text-muted-foreground"><span className="font-mono">{k}</span>: <span className="tabular-nums text-foreground">{String(v)}</span></p>
                        ))}
                        {typeof sec.reason === "string" && <p className="text-[11px] text-amber-700 dark:text-amber-400 line-clamp-2">{sec.reason}</p>}
                      </div>
                    );
                  })}
                </div>
              </>
            )}
            <p className="text-[11px] text-muted-foreground">
              The nightly learning reports themselves (<span className="font-mono">learning_reports/report_&lt;day&gt;.json</span>) have no API
              endpoint yet; their health is the &quot;learn_rota&quot; probe in the Learning card above.
            </p>
          </CardContent>
        </Card>
      </div>

      {plumbing.length > 0 && (
        <details className="rounded-xl border border-border p-4">
          <summary className="cursor-pointer text-sm font-semibold">Plumbing and scheduled tasks ({plumbing.length})</summary>
          <ul className="mt-2 grid gap-x-6 md:grid-cols-2">{plumbing.map((r) => <ProbeRow key={r.name} r={r} />)}</ul>
        </details>
      )}
    </div>
  );
}
