"use client";

/**
 * /journal — Mode A: Murat's own decisions, graded (roadmap H2 · T2/H4 · H5).
 *
 * Mode A (the human decides, the machine assists) and Mode B (the machine
 * decides, the human audits) are one system at two authority levels, and Mode A
 * is how Mode B gets its labels. This page is the human half of that ledger.
 *
 * Three design rules, each of them a rule this programme has already paid for:
 *
 *  1. THE GATE IS THE FIRST THING ON THE PAGE. Under 20 fully graded rows there
 *     is no P&L number anywhere on this screen — the banner says "a receipt,
 *     not a result" and the scoreboard shows PROCESS metrics only. A page that
 *     shows a mean return over six rows teaches its reader to believe it.
 *  2. A COUNTERFACTUAL WITH NO PRICE IS SHOWN AS "NOT AVAILABLE", NEVER AS 0%.
 *     The `market` paper account that holds SPY has no key in this environment,
 *     so the benchmark leg is computed from price data and names its source in
 *     the row. "SPY was flat" and "we never asked" render differently here.
 *  3. THE GRADER SHOWS ITS OWN KNOWN-ANSWER BATTERY. A grader nobody has seen
 *     produce the right regret on a constructed example is not a grader, so the
 *     planted cases are on the page rather than in a document.
 */

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Database,
  FlaskConical,
  Scale,
  ShieldAlert,
} from "lucide-react";

import {
  getJournalDecisions,
  getJournalGrades,
  getJournalKnownAnswer,
  getJournalOverview,
  type JournalGrade,
  type JournalLeg,
} from "@/lib/api";

const CF_LABEL: Record<string, string> = {
  held_to_horizon: "Held to horizon",
  held_to_next_review: "Held to next review",
  engine_pick_same_day: "Engine's own pick",
  spy: "SPY",
};

const TAX_TONE: Record<string, string> = {
  CAPTURED: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  BOUGHT_SOLD_EARLY: "bg-amber-500/10 text-amber-400 border-amber-500/30",
  RANKED_NOT_BOUGHT: "bg-orange-500/10 text-orange-400 border-orange-500/30",
  GENERATED_NOT_RANKED: "bg-rose-500/10 text-rose-400 border-rose-500/30",
  NOT_OBSERVED: "bg-red-500/10 text-red-400 border-red-500/30",
  UNCLASSIFIED: "bg-zinc-500/10 text-zinc-400 border-zinc-500/30",
};

function pct(x: number | null | undefined) {
  if (x === null || x === undefined || Number.isNaN(x)) return null;
  return `${x >= 0 ? "+" : ""}${(100 * x).toFixed(2)}%`;
}

function Num({ v }: { v: number | null | undefined }) {
  const s = pct(v);
  if (s === null) {
    return (
      <span
        className="text-zinc-500 italic"
        title="No declared price source could answer. This is NOT zero."
      >
        n/a
      </span>
    );
  }
  return <span className={v! >= 0 ? "text-emerald-400" : "text-rose-400"}>{s}</span>;
}

function Card({
  title,
  icon,
  children,
  tone = "",
}: {
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
  tone?: string;
}) {
  return (
    <section className={`rounded-lg border border-zinc-800 bg-zinc-950/60 p-4 ${tone}`}>
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold tracking-wide text-zinc-200">
        {icon}
        {title}
      </h2>
      {children}
    </section>
  );
}

function LegCell({ leg, regret }: { leg?: JournalLeg; regret?: number | null }) {
  if (!leg) return <td className="px-2 py-1 text-zinc-600">—</td>;
  return (
    <td className="px-2 py-1 whitespace-nowrap" title={leg.reason ?? `source: ${leg.source}`}>
      <Num v={leg.ret} />
      {regret !== null && regret !== undefined && (
        <span className="ml-1 text-[10px] text-zinc-500">(r {pct(regret)})</span>
      )}
      <div className="text-[10px] text-zinc-600">{leg.source}</div>
    </td>
  );
}

export default function JournalPage() {
  const [asOf, setAsOf] = useState<string>("");

  const overview = useQuery({ queryKey: ["journal", "overview"], queryFn: getJournalOverview });
  const decisions = useQuery({
    queryKey: ["journal", "decisions"],
    queryFn: () => getJournalDecisions(200),
  });
  const grades = useQuery({
    queryKey: ["journal", "grades", asOf],
    queryFn: () => getJournalGrades(asOf || undefined),
  });
  const battery = useQuery({
    queryKey: ["journal", "known-answer"],
    queryFn: getJournalKnownAnswer,
  });

  const o = overview.data;
  const board = o?.scoreboard;
  const gateMet = board?.gate.met ?? false;
  const lessons: JournalGrade[] = grades.data?.lessons ?? [];

  return (
    <div className="mx-auto max-w-[1400px] space-y-4 p-4">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold text-zinc-100">
          Decision journal — Mode A, graded against four counterfactuals
        </h1>
        <p className="text-xs text-zinc-500">
          {o?.mode ?? "Mode A (human decides) + Mode B (machine decides), one ledger"} ·
          brain <code className="text-zinc-400">{o?.brain ?? "human:murat"}</code> ·{" "}
          {o?.licence ?? "PRODUCT_EXPERIMENT"}
        </p>
      </header>

      {/* ── THE GATE, first ───────────────────────────────────────────── */}
      <div
        className={`rounded-lg border p-4 ${
          gateMet
            ? "border-emerald-600/40 bg-emerald-950/20"
            : "border-amber-600/40 bg-amber-950/20"
        }`}
      >
        <div className="flex items-start gap-3">
          {gateMet ? (
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400" />
          ) : (
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
          )}
          <div className="space-y-1">
            <p className="text-sm font-semibold text-zinc-100">
              {board ? `${board.gate.have} of ${board.gate.need} graded rows` : "loading…"} —{" "}
              <span className={gateMet ? "text-emerald-300" : "text-amber-300"}>
                {board?.claim ?? "a receipt, not a result"}
              </span>
            </p>
            <p className="text-xs text-zinc-400">{board?.gate.rule}</p>
            {!gateMet && board?.pnl_withheld_because && (
              <p className="text-xs text-zinc-500">{board.pnl_withheld_because}</p>
            )}
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {/* ── PROCESS METRICS ───────────────────────────────────────── */}
        <Card title="Process metrics" icon={<Scale className="h-4 w-4 text-zinc-400" />}>
          {board ? (
            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-4 gap-2 text-center">
                {[
                  ["rows", board.n_rows],
                  ["pending", board.n_pending],
                  ["resolved", board.n_resolved],
                  ["4-leg", board.n_fully_graded],
                ].map(([k, v]) => (
                  <div key={String(k)} className="rounded border border-zinc-800 p-2">
                    <div className="text-base font-semibold text-zinc-200">{String(v)}</div>
                    <div className="text-[10px] uppercase text-zinc-500">{String(k)}</div>
                  </div>
                ))}
              </div>
              <div>
                <div className="mb-1 text-[10px] uppercase text-zinc-500">Recall taxonomy</div>
                <div className="flex flex-wrap gap-1">
                  {Object.entries(board.process_metrics.taxonomy_histogram).map(([k, v]) => (
                    <span
                      key={k}
                      title={o?.taxonomy?.[k]}
                      className={`rounded border px-1.5 py-0.5 text-[10px] ${
                        TAX_TONE[k] ?? TAX_TONE.UNCLASSIFIED
                      }`}
                    >
                      {k} {v}
                    </span>
                  ))}
                  {Object.keys(board.process_metrics.taxonomy_histogram).length === 0 && (
                    <span className="text-zinc-600">no graded rows yet</span>
                  )}
                </div>
              </div>
              <div>
                <div className="mb-1 text-[10px] uppercase text-zinc-500">
                  Counterfactual coverage
                </div>
                {Object.entries(board.process_metrics.counterfactual_coverage).map(([k, v]) => (
                  <div key={k} className="flex justify-between text-zinc-400">
                    <span>{CF_LABEL[k] ?? k}</span>
                    <span className="text-zinc-300">
                      {v} / {board.n_resolved}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-xs text-zinc-500">loading…</p>
          )}
        </Card>

        {/* ── PRICE SOURCES + THE BENCHMARK CAVEAT ──────────────────── */}
        <Card
          title="Where the counterfactual prices come from"
          icon={<Database className="h-4 w-4 text-zinc-400" />}
        >
          {o ? (
            <div className="space-y-2 text-xs">
              <ol className="space-y-1">
                {o.price_sources.order.map((name, i) => {
                  const s = o.price_sources.sources[name];
                  const ok = s?.available;
                  return (
                    <li key={name} className="flex items-start gap-2">
                      <span className="text-zinc-600">{i + 1}.</span>
                      <span className="flex-1">
                        <span
                          className={
                            ok === true
                              ? "text-emerald-400"
                              : ok === false
                                ? "text-rose-400"
                                : "text-zinc-400"
                          }
                        >
                          {name}
                        </span>
                        {s?.reason && (
                          <span className="block text-[10px] text-zinc-500">{s.reason}</span>
                        )}
                      </span>
                    </li>
                  );
                })}
              </ol>
              <p className="rounded border border-amber-800/40 bg-amber-950/20 p-2 text-[11px] text-amber-200/80">
                <AlertTriangle className="mr-1 inline h-3 w-3" />
                {o.benchmark.note} Account <code>{o.benchmark.account}</code> (
                {o.benchmark.contract}).
              </p>
              <p className="text-[10px] text-zinc-600">
                session calendar: {o.price_sources.session_calendar}
              </p>
            </div>
          ) : (
            <p className="text-xs text-zinc-500">loading…</p>
          )}
        </Card>

        {/* ── H5: THE TERMINAL MIRROR ───────────────────────────────── */}
        <Card
          title="Execution-repo state (read-only mirror)"
          icon={<Clock className="h-4 w-4 text-zinc-400" />}
        >
          {o?.terminal_mirror ? (
            <div className="space-y-2 text-xs">
              <div className="flex items-center gap-2">
                <span
                  className={`rounded border px-1.5 py-0.5 text-[10px] ${
                    o.terminal_mirror.status === "OK"
                      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
                      : "border-amber-500/30 bg-amber-500/10 text-amber-400"
                  }`}
                >
                  {o.terminal_mirror.status}
                </span>
                {o.terminal_mirror.synced_at_utc && (
                  <span className="text-zinc-500">
                    synced {o.terminal_mirror.synced_at_utc}
                  </span>
                )}
              </div>
              {o.terminal_mirror.reason && (
                <p className="text-[11px] text-zinc-400">{o.terminal_mirror.reason}</p>
              )}
              <div className="space-y-0.5">
                {Object.entries(o.terminal_mirror.kinds).map(([k, files]) => (
                  <div key={k} className="flex justify-between text-zinc-400">
                    <span>{k}</span>
                    <span className="text-zinc-300">{files.length}</span>
                  </div>
                ))}
              </div>
              {o.terminal_mirror.not_mirrored_note && (
                <p className="text-[10px] text-zinc-600">
                  {o.terminal_mirror.not_mirrored_note}
                </p>
              )}
              <code className="block text-[10px] text-zinc-500">
                {o.terminal_mirror.how_to_refresh}
              </code>
            </div>
          ) : (
            <p className="text-xs text-zinc-500">loading…</p>
          )}
        </Card>
      </div>

      {/* ── THE GRADED ROWS ─────────────────────────────────────────── */}
      <Card title="Graded decisions — four counterfactuals each">
        <div className="mb-2 flex items-center gap-2 text-xs">
          <label className="text-zinc-500">as of</label>
          <input
            type="date"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
            className="rounded border border-zinc-800 bg-zinc-900 px-2 py-1 text-zinc-200"
          />
          <span className="text-zinc-600">
            a lesson is withheld until its own row resolved
            {grades.data?.n_withheld ? ` · ${grades.data.n_withheld} withheld` : ""}
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-[10px] uppercase text-zinc-500">
              <tr className="border-b border-zinc-800">
                <th className="px-2 py-1">Name</th>
                <th className="px-2 py-1">Mode</th>
                <th className="px-2 py-1">Decided</th>
                <th className="px-2 py-1">Horizon</th>
                <th className="px-2 py-1">Actual</th>
                {Object.keys(CF_LABEL).map((k) => (
                  <th key={k} className="px-2 py-1">
                    {CF_LABEL[k]}
                  </th>
                ))}
                <th className="px-2 py-1">Taxonomy</th>
              </tr>
            </thead>
            <tbody>
              {lessons.map((g) => (
                <tr key={g.decision_id} className="border-b border-zinc-900">
                  <td className="px-2 py-1 font-medium text-zinc-200">
                    {g.symbol}
                    <div className="text-[10px] text-zinc-600">
                      {g.action} {g.direction}
                    </div>
                  </td>
                  <td className="px-2 py-1">
                    <span className="rounded border border-zinc-700 px-1 text-[10px] text-zinc-400">
                      {g.mode === "A" ? "human" : "machine"}
                    </span>
                  </td>
                  <td className="px-2 py-1 whitespace-nowrap text-zinc-400">{g.decision_day}</td>
                  <td className="px-2 py-1 whitespace-nowrap text-zinc-400">
                    {g.horizon_sessions}s
                    <span className="text-zinc-600"> / min {g.min_normal_hold_sessions}</span>
                  </td>
                  <td className="px-2 py-1">
                    <Num v={g.actual?.ret} />
                  </td>
                  {Object.keys(CF_LABEL).map((k) => (
                    <LegCell
                      key={k}
                      leg={g.counterfactuals?.[k]}
                      regret={g.regret?.[k] ?? null}
                    />
                  ))}
                  <td className="px-2 py-1">
                    <span
                      title={g.taxonomy?.reason}
                      className={`rounded border px-1.5 py-0.5 text-[10px] ${
                        TAX_TONE[g.taxonomy?.state] ?? TAX_TONE.UNCLASSIFIED
                      }`}
                    >
                      {g.taxonomy?.state}
                    </span>
                  </td>
                </tr>
              ))}
              {lessons.length === 0 && (
                <tr>
                  <td colSpan={10} className="px-2 py-6 text-center text-zinc-500">
                    No graded rows yet. The log is deliberately empty: seeding it with
                    invented decisions would put fabricated human labels into the only
                    labelled decision dataset this programme has. Rows arrive from{" "}
                    <code>POST /api/journal/thesis</code> and from the conviction journal
                    when it carries a falsifier and a catalyst.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[10px] text-zinc-600">
          regret = counterfactual − actual; positive means the alternative was better. A leg
          reading <em>n/a</em> had no declared price source — it is not a zero.
        </p>
      </Card>

      {/* ── PENDING ROWS ────────────────────────────────────────────── */}
      <Card title="Pending decisions (written at decision time, resolved at their own horizon)">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-[10px] uppercase text-zinc-500">
              <tr className="border-b border-zinc-800">
                <th className="px-2 py-1">Name</th>
                <th className="px-2 py-1">Source</th>
                <th className="px-2 py-1">Decided</th>
                <th className="px-2 py-1">Resolves</th>
                <th className="px-2 py-1">Next review</th>
                <th className="px-2 py-1">Budget</th>
                <th className="px-2 py-1">Falsifier</th>
              </tr>
            </thead>
            <tbody>
              {(decisions.data?.rows ?? []).map((r) => (
                <tr key={r.decision_id} className="border-b border-zinc-900">
                  <td className="px-2 py-1 font-medium text-zinc-200">{r.symbol}</td>
                  <td className="px-2 py-1 text-zinc-400">{r.source}</td>
                  <td className="px-2 py-1 text-zinc-400">{r.decision_day}</td>
                  <td className="px-2 py-1 text-zinc-300">{r.resolves_on}</td>
                  <td className="px-2 py-1 text-zinc-400">{r.reviews_on}</td>
                  <td className="px-2 py-1 text-zinc-400">{r.loss_budget_ref}</td>
                  <td className="px-2 py-1 text-zinc-500">{r.falsifier}</td>
                </tr>
              ))}
              {(decisions.data?.rows ?? []).length === 0 && (
                <tr>
                  <td colSpan={7} className="px-2 py-4 text-center text-zinc-500">
                    No decisions logged.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* ── THE GRADER'S OWN KNOWN-ANSWER BATTERY ───────────────────── */}
      <Card
        title="Does the grader work? — the planted cases, run live"
        icon={<FlaskConical className="h-4 w-4 text-zinc-400" />}
      >
        {battery.data ? (
          <div className="space-y-2 text-xs">
            <p className={battery.data.all_pass ? "text-emerald-400" : "text-rose-400"}>
              {battery.data.n_pass} / {battery.data.n_cases} planted cases pass
            </p>
            <p className="text-[10px] text-zinc-600">{battery.data.note}</p>
            <div className="max-h-64 overflow-y-auto">
              <table className="w-full text-left">
                <tbody>
                  {battery.data.cases.map((c) => (
                    <tr key={c.case} className="border-b border-zinc-900">
                      <td className="px-2 py-0.5">
                        <span className={c.pass ? "text-emerald-500" : "text-rose-500"}>
                          {c.pass ? "PASS" : "FAIL"}
                        </span>
                      </td>
                      <td className="px-2 py-0.5 font-mono text-[10px] text-zinc-300">
                        {c.case}
                      </td>
                      <td className="px-2 py-0.5 text-[10px] text-zinc-500">{c.catches}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <p className="text-xs text-zinc-500">loading…</p>
        )}
      </Card>

      {/* ── LOSS BUDGETS (invariant 19) ─────────────────────────────── */}
      <Card title="Loss budgets — declared before the first position (invariant 19)">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-[10px] uppercase text-zinc-500">
              <tr className="border-b border-zinc-800">
                <th className="px-2 py-1">ref</th>
                <th className="px-2 py-1">book</th>
                <th className="px-2 py-1">judged at</th>
                <th className="px-2 py-1">expected losers</th>
                <th className="px-2 py-1">note</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(o?.loss_budgets ?? {}).map(([ref, b]) => (
                <tr key={ref} className="border-b border-zinc-900">
                  <td className="px-2 py-1 font-mono text-zinc-300">{ref}</td>
                  <td className="px-2 py-1 text-zinc-400">{b.book}</td>
                  <td className="px-2 py-1 text-zinc-300">{b.positions_judged}</td>
                  <td className="px-2 py-1 text-zinc-300">{b.expected_losers}</td>
                  <td className="px-2 py-1 text-[10px] text-zinc-500">{b.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[10px] text-zinc-600">
          An idea is retired by its book&apos;s scoreboard, never by its own first loss.
        </p>
      </Card>

      {o?.schema_provenance && (
        <p className="text-[10px] text-zinc-600">
          Thesis schema: <code>{o.schema_provenance.upstream}</code>, mirrored verbatim (
          {o.schema_provenance.sha256.slice(0, 16)}…). {o.schema_provenance.note}
        </p>
      )}
    </div>
  );
}
