"use client";

/**
 * /theory-lab — the Theory Lab (chunk C19, 2026-10-07).
 *
 * Every hypothesis and theory cell with its state (HYPOTHESIS / EARLY_SUPPORT /
 * CONDITIONAL_SUPPORT / STRENGTHENING / WEAKENING / REGIME_SPECIFIC / FALSIFIED /
 * RETIRED / INVALID_EXPERIMENT), mapped from hyp_lab verdicts plus the `powered`
 * flag: an UNPOWERED negative is never FALSIFIED. Family posteriors, declaration
 * hashes and run ids; the four-column twin boards (sticky vs basket); the honest
 * sentence on CRSP alpha. Negative results are listed, not hidden.
 *
 * Read-only: GET /api/legibility/v1/theory-lab.
 */

import React, { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Brain, Compass, FlaskConical, LineChart, Swords } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { getTheoryLab, type BoardKind, type TheoryLabResponse, type TheoryRow, type TwinBoard } from "@/lib/api";
import {
  LoadError, Missing, MissingList, ReceiptStrip, SourceNote, StaleBanner, num, pctFrac, signTone,
} from "@/components/legibility/receipts";

const STATE_TONE: Record<string, string> = {
  HYPOTHESIS: "border-zinc-500/40 text-zinc-700 dark:text-zinc-300",
  UNINFORMATIVE: "border-zinc-400/50 text-zinc-600 dark:text-zinc-400 border-dashed",
  FALSIFIED_VARIANT: "border-red-500/40 text-red-700 dark:text-red-300",
  EARLY_SUPPORT: "border-sky-500/40 text-sky-700 dark:text-sky-300",
  CONDITIONAL_SUPPORT: "border-sky-600/50 text-sky-800 dark:text-sky-300",
  STRENGTHENING: "border-emerald-600/50 text-emerald-700 dark:text-emerald-300",
  WEAKENING: "border-amber-600/50 text-amber-700 dark:text-amber-300",
  REGIME_SPECIFIC: "border-violet-500/50 text-violet-700 dark:text-violet-300",
  FALSIFIED: "border-red-600/50 text-red-700 dark:text-red-400",
  RETIRED: "border-zinc-400/40 text-zinc-500",
  INVALID_EXPERIMENT: "border-orange-600/50 text-orange-700 dark:text-orange-300",
};

const COL_LABEL: Record<string, string> = {
  pure_selection: "gross / gross (pure selection)",
  fair_twin_net: "net / net (vs fair twin)",
  net_minus_market: "net − market",
  twin_full_round_trip_UPPER_BOUND: "upper bound (twin pays full round trip)",
};
const WINDOWS = ["full", "design", "validate", "late"] as const;

function StateBadge({ s }: { s: string }) {
  return <Badge variant="outline" className={`font-mono text-[10px] ${STATE_TONE[s] ?? ""}`}>{s}</Badge>;
}

function TheoryTable({ rows }: { rows: TheoryRow[] }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="max-h-[70vh] overflow-auto rounded border border-border/50">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground">
            {["State", "Theory", "Family", "Verdict", "Powered", "Confirm mean (t, MDE)", "Run / declaration"].map((h) => (
              <th key={h} className="sticky top-0 z-10 bg-background py-2 pr-3">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const id = r.hyp_id ?? `row-${i}`;
            return (
              <React.Fragment key={id}>
                <tr className="cursor-pointer border-t border-border/40 align-top hover:bg-muted/40" onClick={() => setOpen(open === id ? null : id)}>
                  <td className="py-1.5 pr-3"><StateBadge s={r.state} /></td>
                  <td className="max-w-[22rem] pr-3"><div className="line-clamp-2">{r.title ?? <Missing why="untitled row" />}</div><div className="font-mono text-[10px] text-muted-foreground">{r.hyp_id}</div></td>
                  <td className="pr-3 text-xs">{r.family}</td>
                  <td className="pr-3 font-mono text-[11px]">{r.verdict ?? r.status ?? "—"}</td>
                  <td className="pr-3 text-xs">{r.verdict ? (r.powered ? "yes" : "no") : "—"}</td>
                  <td className="whitespace-nowrap pr-3 text-xs tabular-nums">
                    {r.confirm_mean == null ? "—" : <><span className={signTone(r.confirm_mean)}>{num(r.confirm_mean, 4, true)}</span> ({num(r.confirm_t)}, {num(r.confirm_mde, 4)})</>}
                  </td>
                  <td className="pr-3 font-mono text-[10px] text-muted-foreground">{r.run_id ?? "—"}<br />{r.declaration_sha256 ? `${r.declaration_sha256.slice(0, 16)}…` : ""}</td>
                </tr>
                {open === id && (
                  <tr className="bg-muted/30"><td colSpan={7} className="space-y-1 p-3 text-xs">
                    <p><b>Why this state:</b> {r.state_rule}</p>
                    {r.mechanism && <p><b>Mechanism:</b> {r.mechanism}</p>}
                    {r.precursor && <p><b>Precursor:</b> {r.precursor}</p>}
                    {r.refutation && <p><b>Falsifier:</b> {r.refutation}</p>}
                    {r.reason && <p><b>Verdict reason:</b> {r.reason}</p>}
                    {r.reread_of && <p><b>Re-read of:</b> {r.reread_of} (counts 0 in the family posterior)</p>}
                    {r.receipts.length > 0 && <SourceNote>{r.receipts.join(" · ")}</SourceNote>}
                  </td></tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function BoardTable({ board, window }: { board: TwinBoard; window: (typeof WINDOWS)[number] }) {
  const [onlyT2, setOnlyT2] = useState(false);
  const cols = board.four_columns ?? Object.keys(COL_LABEL);
  const rows = useMemo(() => {
    const r = board.rows.filter((x) => !onlyT2 || (x.columns.fair_twin_net?.[window]?.t ?? 0) >= 2);
    return [...r].sort((a, b) => (b.columns.fair_twin_net?.[window]?.t ?? -99) - (a.columns.fair_twin_net?.[window]?.t ?? -99));
  }, [board, window, onlyT2]);
  return (
    <div className="space-y-2">
      <label className="inline-flex items-center gap-1 text-xs"><input type="checkbox" checked={onlyT2} onChange={(e) => setOnlyT2(e.target.checked)} /> only rules with net/net t ≥ 2 in this window</label>
      <div className="max-h-[60vh] overflow-auto rounded border border-border/50">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-muted-foreground">
              <th className="sticky top-0 z-10 bg-background py-2 pr-3">Rule</th>
              {cols.map((c) => <th key={c} className="sticky top-0 z-10 bg-background py-2 pr-3">{COL_LABEL[c] ?? c}<div className="font-normal">%/mo (t)</div></th>)}
              <th className="sticky top-0 z-10 bg-background py-2 pr-3">Turnover</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.rule} className="border-t border-border/30">
                <td className="pr-3 font-mono">{r.rule}<div className="text-[10px] text-muted-foreground">{r.family}{r.status !== "OK" ? ` · ${r.status}: ${r.reason ?? ""}` : ""}</div>
                  {r.source_run && <div className="text-[10px] text-amber-700 dark:text-amber-400" title={r.superseded_why ?? ""}>values from {r.source_run} (supersedes the {r.superseded_in} row)</div>}</td>
                {cols.map((c) => {
                  const v = r.columns[c]?.[window];
                  return (
                    <td key={c} className={`whitespace-nowrap pr-3 tabular-nums ${c.includes("UPPER") ? "text-muted-foreground" : ""}`}>
                      {v?.mean_monthly == null ? "—" : <><span className={c.includes("UPPER") ? "" : signTone(v.mean_monthly)}>{pctFrac(v.mean_monthly, 2, true)}</span> ({num(v.t)})</>}
                    </td>
                  );
                })}
                <td className="pr-3">{num(r.turnover, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-muted-foreground">{board.upper_bound_note}. Cost convention: {board.cost_convention}.</p>
      <SourceNote>{board.summary_file} · {board.rows_file}{board.other_boards_not_served.length ? ` (not served: ${board.other_boards_not_served.join(", ")})` : ""}</SourceNote>
    </div>
  );
}

function Boards({ d, kind, setKind }: { d: TheoryLabResponse; kind: BoardKind; setKind: (k: BoardKind) => void }) {
  const [win, setWin] = useState<(typeof WINDOWS)[number]>("validate");
  const board = d.boards[kind];
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-base">Library rules on CRSP: the four columns</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <div className="rounded border border-amber-600/40 bg-amber-500/5 p-3 text-sm">
          <div className="font-medium">{d.crsp.sentence ?? <Missing why={d.crsp.missing_because} />}</div>
          {d.crsp.counts_from_board && (
            <p className="mt-1 text-xs text-muted-foreground">
              Board {d.crsp.counts_from_board.board}: {d.crsp.counts_from_board.fair_twin_t_ge_2} of {d.crsp.counts_from_board.n_ok} scored rules reach net/net t ≥ 2;
              {" "}{d.crsp.counts_from_board.net_minus_market_validate_t_ge_2} beat the market in validation
              {d.crsp.counts_from_board.beats_fair_twin_and_market_validate?.length ? ` (${d.crsp.counts_from_board.beats_fair_twin_and_market_validate.join(", ")})` : ""}.
            </p>
          )}
          {d.crsp.source && <SourceNote>{d.crsp.source}</SourceNote>}
        </div>
        <div className="flex flex-wrap gap-2 text-sm">
          <div className="inline-flex overflow-hidden rounded border border-border" role="group" aria-label="Twin kind">
            {(["sticky", "basket"] as const).map((k) => (
              <button key={k} className={`px-3 py-1 ${kind === k ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`} onClick={() => setKind(k)}>{k} twin</button>
            ))}
          </div>
          <select aria-label="Window" className="rounded border border-border bg-background px-2 py-1" value={win} onChange={(e) => setWin(e.target.value as (typeof WINDOWS)[number])}>
            {WINDOWS.map((w) => <option key={w} value={w}>{w}{d.boards[kind]?.windows?.[w] ? ` (${(d.boards[kind]?.windows?.[w] ?? []).map((x) => x ?? "…").join(" → ")})` : ""}</option>)}
          </select>
        </div>
        {!board ? <p className="text-sm"><Missing why={d.missing_because[kind === "sticky" ? "twin_board_STK" : "twin_board_FT"]} /></p>
          : !board.rows_served ? <p className="text-sm text-muted-foreground">Loading the {kind} board&apos;s {board.n_rows} rows…</p>
          : <BoardTable board={board} window={win} />}
        {board?.supersessions_applied?.length ? (
          <p className="text-[11px] text-amber-700 dark:text-amber-400">
            Row supersessions applied: {board.supersessions_applied.map((x) => `${x.rules.join(", ")} from ${x.supplement_run}`).join("; ")}. The writer&apos;s summary counts above are from before them.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

export default function TheoryLabPage() {
  const [kind, setKind] = useState<BoardKind>("sticky");
  const q = useQuery({ queryKey: ["theory-lab", kind], queryFn: () => getTheoryLab(kind), retry: 1, refetchInterval: 15 * 60_000, placeholderData: (prev) => prev });
  const d = q.data;
  const [state, setState] = useState("all");
  const [family, setFamily] = useState("all");
  const rows = useMemo(() => (d?.theories ?? []).filter((r) => (state === "all" || r.state === state) && (family === "all" || r.family === family)), [d, state, family]);
  const families = useMemo(() => Array.from(new Set((d?.theories ?? []).map((r) => r.family))).sort(), [d]);
  const negatives = (d?.theories ?? []).filter((r) => ["FALSIFIED", "FALSIFIED_VARIANT", "WEAKENING"].includes(r.state));
  const sc = d?.state_counts ?? {};
  const untested = sc.HYPOTHESIS ?? 0;
  const unpowered = sc.UNINFORMATIVE ?? 0;
  const tested = (d?.theories.length ?? 0) - untested - unpowered - (sc.RETIRED ?? 0) - (sc.INVALID_EXPERIMENT ?? 0);

  return (
    <div className="space-y-5 animate-slide-up">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-3xl">
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight"><FlaskConical className="h-6 w-6" /> Theory Lab</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Every theory has a mechanism, a precursor observable before the move and a falsifier, or it is not a hypothesis yet.
            Negative results are listed here, not hidden.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <Link href="/brain" className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 hover:bg-muted"><Brain className="h-3.5 w-3.5" /> Optimus Brain (the memory these came from)</Link>
          <Link href="/opportunities" className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 hover:bg-muted"><Compass className="h-3.5 w-3.5" /> Opportunity Explorer</Link>
          <Link href="/arena" className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 hover:bg-muted"><Swords className="h-3.5 w-3.5" /> Paper Arena</Link>
          <Link href="/forecast-lab" className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 hover:bg-muted"><LineChart className="h-3.5 w-3.5" /> Forecast Lab</Link>
        </div>
      </div>
      {q.isLoading && <Skeleton className="h-40 w-full" />}
      {q.error && <LoadError what="Theory Lab" err={q.error} />}
      {d && (
        <>
          <StaleBanner receipts={d.receipts} />
          <div className="flex flex-wrap gap-1.5">
            {d.states.map((s) => (
              <button key={s} onClick={() => setState(state === s ? "all" : s)} className={`rounded ${state === s ? "ring-2 ring-primary" : ""}`}>
                <span className={`inline-block rounded border px-2 py-1 font-mono text-[11px] ${STATE_TONE[s] ?? ""}`}>{s} · {d.state_counts[s] ?? 0}</span>
              </button>
            ))}
          </div>
          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="rounded border border-border p-2"><div className="text-lg font-semibold">{tested}</div><div className="text-[11px] text-muted-foreground">tested with a decisive or powered result</div></div>
            <div className="rounded border border-dashed border-border p-2"><div className="text-lg font-semibold">{unpowered}</div><div className="text-[11px] text-muted-foreground">tested without power (UNINFORMATIVE)</div></div>
            <div className="rounded border border-border p-2"><div className="text-lg font-semibold">{untested}</div><div className="text-[11px] text-muted-foreground">untested (HYPOTHESIS)</div></div>
          </div>
          <p className="text-xs text-muted-foreground">{d.powered_rule}.</p>
          <details className="text-xs">
            <summary className="cursor-pointer">How a hyp_lab verdict becomes a state</summary>
            <table className="mt-1 w-full"><tbody>
              {d.state_map.map((m) => <tr key={m.input} className="border-t border-border/30"><td className="pr-3 font-mono">{m.input}</td><td>{m.state}</td></tr>)}
            </tbody></table>
          </details>

          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-base">Theories ({rows.length} of {d.theories.length})</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              <select aria-label="Family" className="rounded border border-border bg-background px-2 py-1 text-sm" value={family} onChange={(e) => setFamily(e.target.value)}>
                <option value="all">All families</option>
                {families.map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
              <TheoryTable rows={rows} />
              <SourceNote>hyp_lab/ledger.jsonl (folded by hyp_lab.load_state) + hyp_lab/theory_*_DECLARATION/RESULTS_*.json</SourceNote>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-base">Negative results ({negatives.length})</CardTitle>
              <p className="text-xs text-muted-foreground">FALSIFIED, FALSIFIED_VARIANT and WEAKENING only. The {d.n_uninformative} UNINFORMATIVE rows were tested without power: they are not negatives.</p></CardHeader>
            <CardContent>
              {negatives.length === 0 ? <p className="text-sm text-muted-foreground">None in this ledger.</p> : (
                <ul className="divide-y divide-border/40 text-sm">
                  {negatives.map((r, i) => (
                    <li key={r.hyp_id ?? i} className="flex flex-wrap items-baseline justify-between gap-2 py-1.5">
                      <span className="min-w-0"><StateBadge s={r.state} /> {r.title}</span>
                      <span className="text-xs text-muted-foreground">{r.verdict}{r.verdict ? (r.powered ? ", powered" : ", unpowered") : ""}</span>
                    </li>
                  ))}
                </ul>
              )}
              <SourceNote>hyp_lab ledger; the longer list of closed ideas lives in {d.links.negative_results_doc}</SourceNote>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-base">Family posteriors</CardTitle></CardHeader>
            <CardContent>
              <p className="mb-2 text-xs text-muted-foreground">
                Beta({d.family_prior.join(", ")}) prior on P(a member is positive). A positive counts +1; a FAILED_VARIANT counts +1 failure only when powered;
                CANNOT_DISTINGUISH and re-reads count 0. The budget weight shrinks a family&apos;s share of the next generation round; it never closes one.
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground"><th className="pr-3">Family</th><th className="pr-3">P(positive)</th><th className="pr-3">Rows</th><th className="pr-3">Positive</th><th className="pr-3">Failed (powered)</th><th className="pr-3">Cannot distinguish</th><th>Budget weight</th></tr></thead>
                  <tbody>
                    {d.families.map((f) => (
                      <tr key={f.family} className="border-t border-border/40">
                        <td className="pr-3 font-mono text-xs">{f.family}</td>
                        <td className="pr-3"><span className="inline-flex items-center gap-2"><span className="inline-block h-2 w-20 rounded bg-muted"><span className="block h-2 rounded bg-sky-600" style={{ width: `${Math.min(100, 100 * f.p_positive)}%` }} /></span>{num(f.p_positive, 3)}</span></td>
                        <td className="pr-3">{f.n_rows}</td><td className="pr-3">{f.CONDITIONAL_POSITIVE}</td>
                        <td className="pr-3">{f.FAILED_VARIANT} ({num(f.failed_powered, 1)})</td><td className="pr-3">{f.CANNOT_DISTINGUISH}</td><td>{num(f.budget_weight, 2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <SourceNote>hyp_lab.family_record over the folded ledger</SourceNote>
            </CardContent>
          </Card>

          <Boards d={d} kind={kind} setKind={setKind} />
          <MissingList missing={d.missing_because} />
          <ReceiptStrip receipts={d.receipts} />
        </>
      )}
    </div>
  );
}
