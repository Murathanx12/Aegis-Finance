"use client";

/**
 * /forecast-lab — the Forecast Lab (chunk C19, 2026-10-07; review fixes F3/F6/F7).
 *
 * The forecast ledger's grades, read from receipts: calibration (predicted vs realised by
 * bucket, each bin with n, a Wilson interval and its date blocks), skill by arm and horizon
 * split MAGNITUDE vs DIRECTION with the BASELINE named beside every number (the reputation
 * receipt scores against the held-out rows' own base rate; the sigma prior against the
 * training half's), trust per arm ("0 until 3 graded dates"), the regime rows with their two
 * baselines, and the nn_lab tournament from the ONE walk-forward run the nightly cites (a newer
 * review rerun is shown apart). No pooled skill is computed on this page.
 *
 * Read-only: GET /api/legibility/v1/forecast-lab.
 */

import React, { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Brain, FlaskConical, LineChart, Swords } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getForecastLab, type CalibBin, type ForecastLabResponse, type WfModelRow } from "@/lib/api";
import {
  LoadError, Missing, MissingList, ReceiptStrip, SourceNote, StaleBanner, fmtAgeHours, num, pctFrac, signTone,
} from "@/components/legibility/receipts";

// Categorical slots 1-3 of the validated default palette (dataviz references/palette.md),
// assigned in fixed order to the observable, never cycled.
const SERIES: Record<string, { light: string; dark: string; label: string }> = {
  abs_move_exceeds: { light: "#2a78d6", dark: "#3987e5", label: "|move| exceeds (magnitude)" },
  beats_benchmark: { light: "#eb6834", dark: "#d95926", label: "beats benchmark" },
  return_sign: { light: "#1baf7a", dark: "#199e70", label: "return sign (direction)" },
};
const OTHER = { light: "#6b6b66", dark: "#a3a299", label: "other" };

function varStyle(s: { light: string; dark: string }) {
  return { ["--l" as string]: s.light, ["--d" as string]: s.dark } as React.CSSProperties;
}

function CalibrationChart({ bins, title }: { bins: CalibBin[]; title: string }) {
  const W = 300, H = 260, P = 34;
  const x = (p: number) => P + p * (W - P - 10);
  const y = (p: number) => H - P - p * (H - P - 10);
  const groups: Record<string, CalibBin[]> = {};
  for (const b of bins) (groups[b.observable] ??= []).push(b);
  const keys = Object.keys(groups);
  return (
    <figure className="min-w-0">
      <figcaption className="mb-1 text-xs font-medium">{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-sm" role="img" aria-label={`Calibration ${title}`}>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t} className="text-muted-foreground">
            <line x1={x(0)} x2={x(1)} y1={y(t)} y2={y(t)} stroke="currentColor" strokeOpacity={0.15} />
            <text x={P - 4} y={y(t) + 3} fontSize={9} textAnchor="end" fill="currentColor">{t}</text>
            <text x={x(t)} y={H - P + 12} fontSize={9} textAnchor="middle" fill="currentColor">{t}</text>
          </g>
        ))}
        <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} className="text-muted-foreground" stroke="currentColor" strokeDasharray="4 3" strokeOpacity={0.6} />
        <text x={x(0.5)} y={H - 4} fontSize={9} textAnchor="middle" className="fill-muted-foreground">predicted probability (bucket mean)</text>
        <text x={10} y={y(0.5)} fontSize={9} textAnchor="middle" transform={`rotate(-90 10 ${y(0.5)})`} className="fill-muted-foreground">realised rate</text>
        {keys.map((k) => {
          const s = SERIES[k] ?? OTHER;
          const pts = groups[k].filter((b) => b.p_mean != null && b.base_rate != null).sort((a, b) => (a.p_mean ?? 0) - (b.p_mean ?? 0));
          return (
            <g key={k} className="[--c:var(--l)] dark:[--c:var(--d)]" style={varStyle(s)}>
              <polyline fill="none" stroke="var(--c)" strokeWidth={2} strokeOpacity={0.7} points={pts.map((b) => `${x(b.p_mean!)},${y(b.base_rate!)}`).join(" ")} />
              {pts.map((b) => (
                <g key={b.bin}>
                  {b.wilson_lo != null && b.wilson_hi != null && (
                    <line x1={x(b.p_mean!)} x2={x(b.p_mean!)} y1={y(b.wilson_lo)} y2={y(b.wilson_hi)} stroke="var(--c)" strokeWidth={1.5} strokeOpacity={b.thin ? 0.35 : 0.8} />
                  )}
                  <circle cx={x(b.p_mean!)} cy={y(b.base_rate!)} r={5} fill={b.thin ? "var(--background, #fff)" : "var(--c)"} stroke="var(--c)" strokeWidth={2}>
                    <title>{`${s.label}, bin ${b.bin}: predicted ${num(b.p_mean, 3)}, realised ${num(b.base_rate, 3)} (Wilson ${num(b.wilson_lo, 3)}–${num(b.wilson_hi, 3)}), n=${b.n} rows, ${b.n_dates ?? "?"} dates, ${b.n_date_blocks ?? "?"} date blocks${b.thin ? " — THIN" : ""}`}</title>
                  </circle>
                </g>
              ))}
            </g>
          );
        })}
      </svg>
      <div className="mt-1 flex flex-wrap gap-3 text-[11px]">
        {keys.map((k) => {
          const s = SERIES[k] ?? OTHER;
          return (
            <span key={k} className="inline-flex items-center gap-1 [--c:var(--l)] dark:[--c:var(--d)]" style={varStyle(s)}>
              <span className="inline-block h-2 w-3 rounded-sm" style={{ background: "var(--c)" }} />{s.label}
            </span>
          );
        })}
        <span className="text-muted-foreground">dashed: perfect calibration · hollow: thin bin · whisker: Wilson 95% on rows</span>
      </div>
    </figure>
  );
}

function Baseline({ text }: { text: string }) {
  return <span className="text-[11px] text-muted-foreground">vs {text}</span>;
}

function SkillSection({ d }: { d: ForecastLabResponse }) {
  const [showArms, setShowArms] = useState(false);
  const s = d.skill;
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-base">MAGNITUDE vs DIRECTION</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <div className="rounded border border-border p-3 text-sm">
          <div className="font-medium">House finding: {d.house_finding.claim}</div>
          <p className="text-xs text-muted-foreground">{d.house_finding.reading}.</p>
          <ul className="mt-2 space-y-1.5 text-xs">
            {d.house_finding.evidence.map((e, i) => (
              <li key={i} className="border-t border-border/40 pt-1">
                <div className="flex flex-wrap justify-between gap-2">
                  <span className="font-medium">{e.what}</span>
                  <span className="font-mono">
                    {e.value != null && <span className={signTone(e.value)}>{num(e.value, 3, true)} </span>}
                    {e.unit}{e.n != null ? `, n=${e.n}` : ""}
                  </span>
                </div>
                <div className="flex flex-wrap justify-between gap-2"><Baseline text={e.baseline} /><span className="text-[11px] text-muted-foreground">{e.receipt}</span></div>
                {e.sanity_check && <div className="text-[11px] text-muted-foreground">sanity check, not a second fact: {e.sanity_check}</div>}
              </li>
            ))}
          </ul>
        </div>
        {!s ? <p className="text-sm"><Missing why={d.missing_because.skill} /></p> : (
          <>
            <p className="text-xs text-muted-foreground">
              Every skill below is 1 − Brier / climatology on each arm&apos;s later half (made_at order), copied per arm from the receipt.
              Baseline: <b>{s.baseline}</b>. It is NOT the sigma prior&apos;s baseline; do not compare the two number to number.
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                  <th className="pr-3">Kind</th><th className="pr-3">h</th><th className="pr-3">Arms &gt; 0 / scored / listed</th>
                  <th className="pr-3">Best arm</th><th className="pr-3">Worst arm</th><th>Held-out rows</th></tr></thead>
                <tbody>
                  {s.by_kind_horizon.filter((r) => r.kind !== "other").map((r) => (
                    <tr key={`${r.kind}-${r.horizon_days}`} className="border-t border-border/40 align-top">
                      <td className="pr-3 font-medium">{r.kind.toUpperCase()}</td><td className="pr-3">{r.horizon_days}</td>
                      <td className="pr-3">{r.n_arms_positive} / {r.n_arms_scored} / {r.n_arms}</td>
                      <td className="pr-3 text-xs">{r.best_arm ? <><span className="font-mono">{r.best_arm}</span> <span className={signTone(r.best_skill)}>{num(r.best_skill, 3, true)}</span></> : <Missing why="no scored arm" />}</td>
                      <td className="pr-3 text-xs">{r.worst_arm ? <><span className="font-mono">{r.worst_arm}</span> <span className={signTone(r.worst_skill)}>{num(r.worst_skill, 3, true)}</span></> : "—"}</td>
                      <td>{r.n_rows_heldout}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-muted-foreground">{s.n_graded} graded of {s.n_ledger} ledger rows, made {s.made_at_range?.join(" → ")}. Split: {s.split}.</p>
            <button className="text-xs underline" onClick={() => setShowArms((v) => !v)}>{showArms ? "Hide" : "Show"} every arm × observable × horizon ({s.arms_by_observable.length})</button>
            {showArms && (
              <div className="max-h-96 overflow-auto rounded border border-border/50">
                <table className="w-full text-xs">
                  <thead><tr className="text-left text-muted-foreground">{["arm", "observable", "kind", "h", "n held out", "skill"].map((h) => <th key={h} className="sticky top-0 bg-background pr-3">{h}</th>)}</tr></thead>
                  <tbody>
                    {s.arms_by_observable.map((r, i) => (
                      <tr key={i} className="border-t border-border/30">
                        <td className="pr-3 font-mono">{r.arm}</td><td className="pr-3">{r.observable}</td><td className="pr-3">{r.kind}</td>
                        <td className="pr-3">{r.horizon_days}</td><td className="pr-3">{r.n}</td>
                        <td className={signTone(r.skill)}>{r.skill == null ? <Missing why="too few held-out rows" /> : num(r.skill, 3, true)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
        <SourceNote>forecast_reputation.arms_by_observable · learning_report.closing.vol_prior · the cited walk-forward .magnitude</SourceNote>
      </CardContent>
    </Card>
  );
}

function SigmaPrior({ d }: { d: ForecastLabResponse }) {
  const rows = d.sigma_prior;
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-base">The free baseline: the sigma_63 prior</CardTitle></CardHeader>
      <CardContent>
        {!rows?.length ? <p className="text-sm"><Missing why={d.missing_because.sigma_prior} /></p> : (
          <div className="overflow-x-auto">
            <p className="mb-1 text-xs text-muted-foreground">Baseline for both columns: <b>{rows[0].baseline}</b>.</p>
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground"><th className="pr-3">h</th><th className="pr-3">Prior skill</th><th className="pr-3">LLM skill</th><th className="pr-3">Winner</th><th className="pr-3">Days prior wins</th><th>Held out</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.horizon} className="border-t border-border/40">
                    <td className="pr-3">{r.horizon}</td>
                    <td className={`pr-3 tabular-nums ${signTone(r.skill_prior)}`}>{num(r.skill_prior, 3, true)}</td>
                    <td className={`pr-3 tabular-nums ${signTone(r.skill_llm)}`}>{num(r.skill_llm, 3, true)}</td>
                    <td className="pr-3 font-mono">{r.winner ?? "—"}</td>
                    <td className="pr-3">{r.days_prior_wins ?? "—"} / {r.n_days ?? "—"}</td>
                    <td className="text-xs">{r.n_heldout} rows, {r.heldout_from} → {r.heldout_to}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-1 font-mono text-[11px] text-muted-foreground">{rows[0].formula}</p>
          </div>
        )}
        <SourceNote>learning_report.closing.vol_prior</SourceNote>
      </CardContent>
    </Card>
  );
}

function TrustSection({ d }: { d: ForecastLabResponse }) {
  const t = d.trust;
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-base">Trust per arm</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">{t.rule}. Trust can only grow by that rule; an arm with fewer than {t.min_graded_dates} graded dates is at exactly 0.</p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground"><th className="pr-3">Arm</th><th className="pr-3">Control</th><th className="pr-3">Graded dates</th><th className="pr-3">Mean Brier improvement</th><th>Trust</th></tr></thead>
            <tbody>
              {t.news.map((r) => (
                <tr key={r.arm} className="border-t border-border/40">
                  <td className="pr-3 font-mono text-xs">{r.arm}</td><td className="pr-3 text-xs">{r.control}</td>
                  <td className="pr-3">{r.n_dates ?? 0}{r.below_min_dates ? <span className="text-xs text-muted-foreground"> (&lt; {t.min_graded_dates}: trust 0)</span> : null}</td>
                  <td className={`pr-3 ${signTone(r.mean_improvement)}`}>{num(r.mean_improvement, 4, true)}{r.se != null ? ` ± ${num(r.se, 4)}` : ""}</td>
                  <td className="tabular-nums">{num(r.trust, 4)}</td>
                </tr>
              ))}
              {t.nn_lab.map((r) => (
                <tr key={`${r.arm}-${r.horizon}`} className="border-t border-border/40">
                  <td className="pr-3 font-mono text-xs">{r.arm} {r.horizon}</td><td className="pr-3 text-xs">{r.source}</td>
                  <td className="pr-3">{r.graded_dates ?? 0}</td><td className="pr-3 text-xs text-muted-foreground">walk-forward IC {num(r.walk_forward_mean_ic_reported, 4)} (not used)</td>
                  <td className="tabular-nums">{num(r.trust, 4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {d.missing_because.news_trust && <p className="text-xs"><Missing why={d.missing_because.news_trust} /></p>}
        <SourceNote>digest/world_digest_*.shadow.grade · nn_lab nightly .trust</SourceNote>
      </CardContent>
    </Card>
  );
}

function RegimeSection({ d }: { d: ForecastLabResponse }) {
  const r = d.regime;
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-base">Regime rows (C17)</CardTitle></CardHeader>
      <CardContent className="space-y-2 text-sm">
        {!r ? <Missing why={d.missing_because.regime} /> : (
          <>
            <p className="rounded border border-amber-600/30 bg-amber-500/5 p-2">{r.note}</p>
            <p className="text-xs text-muted-foreground">Two baselines, and trust is the smaller of the two: {r.baselines.join("; ")}.</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {(["vs_persistence", "vs_base_rate"] as const).map((k) => (
                <div key={k} className="rounded border border-border p-2 text-xs">
                  <div className="font-medium">{k.replace("_", " ")}</div>
                  <div>graded dates: {String(r[k]?.n_dates ?? 0)} · rows: {String(r[k]?.n_rows ?? 0)} · trust: {String(r[k]?.trust ?? 0)}</div>
                  <div className="text-muted-foreground">{String(r[k]?.note ?? "")}</div>
                </div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">{r.n_fields ?? 0} regime fields · regime write: {String(r.regime_write?.state ?? "n/a")} ({String(r.regime_write?.session_day ?? "")}) · {r.news_tilt_line}</p>
          </>
        )}
        <SourceNote>digest/world_state_*.regime_grade</SourceNote>
      </CardContent>
    </Card>
  );
}

function WfTable({ rows }: { rows: WfModelRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead><tr className="text-left text-muted-foreground"><th className="pr-3">model</th><th className="pr-3">h</th><th className="pr-3">rank IC (t)</th><th className="pr-3">LOYO worst</th><th className="pr-3">top20−random net (t)</th><th>verdict</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.model}-${r.horizon}`} className="border-t border-border/30">
              <td className="pr-3 font-mono">{r.model}</td><td className="pr-3">{r.horizon}</td>
              <td className="pr-3">{num(r.rank_ic, 4)} ({num(r.rank_ic_t)})</td><td className="pr-3">{num(r.rank_ic_loyo_worst, 4)}</td>
              <td className="pr-3">{pctFrac(r.top20_minus_random_net, 2, true)} ({num(r.top20_t)})</td><td className="font-mono">{r.verdict ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TournamentSection({ d }: { d: ForecastLabResponse }) {
  const t = d.tournament;
  if (!t) return <Card><CardContent className="p-4 text-sm"><Missing why={d.missing_because.tournament} /></CardContent></Card>;
  const table = t.nightly_table ?? {};
  const horizons = Object.keys(table);
  const models = Array.from(new Set(horizons.flatMap((h) => Object.keys(table[h] ?? {}))));
  const citedRef = d.receipts.find((r) => r.role?.startsWith("tournament table"));
  return (
    <>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">nn_lab tournament (one walk-forward run: {t.cited_run ?? "n/a"})</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <p className="rounded border border-border p-2 text-sm font-medium">{t.sentence ?? <Missing why={d.missing_because.tournament_sentence} />}</p>
          <p className="text-xs text-muted-foreground">Rule: {t.rule}</p>
          <p className="text-xs">
            Every number on this card comes from <span className="font-mono">{t.nightly_table_receipt ?? "n/a"}</span>, the run the nightly cites
            ({citedRef ? `${fmtAgeHours(citedRef.age_hours)}, ${citedRef.status}` : "age n/a"}). {t.cited_missing_because ? <Missing why={t.cited_missing_because} /> : null}
          </p>
          {horizons.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead><tr className="text-left text-muted-foreground"><th className="pr-3">model</th>{horizons.map((h) => <th key={h} className="pr-3">{h}: rank IC (t) · top20−random</th>)}</tr></thead>
                <tbody>
                  {models.map((m) => (
                    <tr key={m} className="border-t border-border/40">
                      <td className="pr-3 font-mono">{m}</td>
                      {horizons.map((h) => {
                        const c = table[h]?.[m];
                        return <td key={h} className="pr-3 tabular-nums">{c ? `${num(c.rank_ic, 4)} (${num(c.t, 2)}) · ${pctFrac(c.top20_minus_random_net, 2, true)}` : "—"}</td>;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
              {t.nightly_table_note && <p className="text-[11px] text-muted-foreground">{t.nightly_table_note}</p>}
            </div>
          )}
          {t.cited_models.length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer">Every model × horizon of the cited run, with its verdict</summary>
              <div className="mt-2"><WfTable rows={t.cited_models} /></div>
              {t.survivorship_caveat && <p className="mt-1 text-muted-foreground">{t.survivorship_caveat}</p>}
            </details>
          )}
          <SourceNote>nn_lab/receipts/nightly_*.tournament + the walk-forward it cites</SourceNote>
        </CardContent>
      </Card>
      {d.review_rerun && (
        <Card className="border-dashed">
          <CardHeader className="pb-2"><CardTitle className="text-base">Review rerun {d.review_rerun.run_id} (not the tournament)</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            <p className="text-xs text-muted-foreground">{d.review_rerun.label}.</p>
            <details className="text-xs"><summary className="cursor-pointer">Show its table</summary><div className="mt-2"><WfTable rows={d.review_rerun.models} /></div></details>
          </CardContent>
        </Card>
      )}
    </>
  );
}

export default function ForecastLabPage() {
  const q = useQuery({ queryKey: ["forecast-lab"], queryFn: getForecastLab, retry: 1, refetchInterval: 10 * 60_000 });
  const d = q.data;
  return (
    <div className="space-y-5 animate-slide-up">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-3xl">
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight"><LineChart className="h-6 w-6" /> Forecast Lab</h1>
          <p className="mt-1 text-sm text-muted-foreground">How good are the forecasts, graded against what happened, each beside the baseline it must beat.</p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <Link href="/arena" className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 hover:bg-muted"><Swords className="h-3.5 w-3.5" /> Paper Arena</Link>
          <Link href="/theory-lab" className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 hover:bg-muted"><FlaskConical className="h-3.5 w-3.5" /> Theory Lab</Link>
          <Link href="/brain" className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 hover:bg-muted"><Brain className="h-3.5 w-3.5" /> Optimus Brain</Link>
        </div>
      </div>
      {q.isLoading && <Skeleton className="h-40 w-full" />}
      {q.error && <LoadError what="Forecast Lab" err={q.error} />}
      {d && (
        <>
          <StaleBanner receipts={d.receipts} />
          {d.grades && (
            <div className="rounded border border-border p-2 text-sm">
              Ledger: {d.grades.headline} <span className="text-xs text-muted-foreground">(grader health {d.grades.health_status}; {d.grades.distinct_specialists} specialists)</span>
              <SourceNote>night_factory_*/grade_forecasts_*.json</SourceNote>
            </div>
          )}
          <SkillSection d={d} />
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-base">Calibration: predicted vs realised, by bucket</CardTitle></CardHeader>
            <CardContent>
              {!d.calibration ? <Missing why={d.missing_because.calibration} /> : (
                <>
                  {d.calibration_note && <p className="mb-2 text-xs text-muted-foreground">{d.calibration_note}</p>}
                  <div className="grid gap-4 md:grid-cols-2">
                    {Object.entries(d.calibration).map(([h, bins]) => <CalibrationChart key={h} bins={bins} title={`${h} · ${bins[0]?.arm_prefix ?? ""}`} />)}
                  </div>
                  <details className="mt-2 text-xs">
                    <summary className="cursor-pointer">Table view (n, Wilson interval, dates, date blocks)</summary>
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead><tr className="text-left text-muted-foreground">{["h", "observable", "bucket", "predicted", "realised", "Wilson 95%", "rows", "dates", "date blocks"].map((x) => <th key={x} className="pr-3">{x}</th>)}</tr></thead>
                        <tbody>
                          {Object.entries(d.calibration).flatMap(([h, bins]) => bins.map((b) => (
                            <tr key={`${h}-${b.observable}-${b.bin}`} className={`border-t border-border/30 ${b.thin ? "text-muted-foreground" : ""}`}>
                              <td className="pr-3">{h}</td><td className="pr-3">{b.observable}</td><td className="pr-3">{num(b.p_lo, 2)}–{num(b.p_hi, 2)}</td>
                              <td className="pr-3">{num(b.p_mean, 3)}</td><td className="pr-3">{num(b.base_rate, 3)}</td>
                              <td className="pr-3">{num(b.wilson_lo, 3)}–{num(b.wilson_hi, 3)}</td><td className="pr-3">{b.n}</td>
                              <td className="pr-3">{b.n_dates ?? <Missing why={b.blocks_missing_because} />}</td><td>{b.n_date_blocks ?? "—"}</td>
                            </tr>
                          )))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                </>
              )}
              <SourceNote>forecast_reputation.calibration (+ dates reproduced from the writer&apos;s own binning; refused unless every bin&apos;s n matches)</SourceNote>
            </CardContent>
          </Card>
          <SigmaPrior d={d} />
          <TrustSection d={d} />
          <RegimeSection d={d} />
          <TournamentSection d={d} />
          {d.analyst_reputation && (
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-base">Analyst reputation weights (C18)</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm">
                <p className="text-xs text-muted-foreground">{d.analyst_reputation.n_firms} firms, {d.analyst_reputation.n_sectors} sectors, {String(d.analyst_reputation.pit?.claims_resolved_before_asof ?? "?")} resolved claims, as of {d.analyst_reputation.asof}.</p>
                <ul className="list-disc pl-5 text-xs text-muted-foreground">{(d.analyst_reputation.limits ?? []).map((l) => <li key={l}>{l}</li>)}</ul>
                <SourceNote>analyst/reputation_weights_{d.analyst_reputation.month}.json</SourceNote>
              </CardContent>
            </Card>
          )}
          {d.closing && (
            <div className="space-y-1 rounded border border-border p-3 text-xs">
              <p>{d.closing.works}</p><p>{d.closing.does_not}</p>
              <SourceNote>learning_report.closing</SourceNote>
            </div>
          )}
          <MissingList missing={d.missing_because} />
          <ReceiptStrip receipts={d.receipts} />
        </>
      )}
    </div>
  );
}
