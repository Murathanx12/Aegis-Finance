"use client";

// Investment Committee — the graceful-degradation book (NIGHT-13 ruling §2).
// Section order mirrors the CLI page: ranking gate → evidence coverage → top
// opportunities → THE BOOK → capital tabs → honesty (ruin BESIDE dream).

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Landmark, ShieldCheck, AlertTriangle, Scale, CheckCircle2,
} from "lucide-react";
import {
  getInvestmentCommittee,
  type ICCommitteeResponse, type ICComposedBook, type ICPosition,
} from "@/lib/api";
import { fmtMoney } from "@/lib/format";

const CAPITAL_TABS = [
  { key: "10000", label: "$10k" },
  { key: "40000", label: "$40k" },
  { key: "1000000", label: "$1m" },
];

function pct(v: number | null | undefined, digits = 1): string {
  return v == null ? "—" : `${(100 * v).toFixed(digits)}%`;
}

function SourceBadge({ source }: { source: ICPosition["source"] }) {
  return source === "evidence-led" ? (
    <Badge className="bg-emerald-600/15 text-emerald-700 dark:text-emerald-400 border-emerald-600/30">
      evidence-led
    </Badge>
  ) : (
    <Badge variant="outline" className="text-muted-foreground">
      benchmark-core
    </Badge>
  );
}

function DegradationBanner({ reasons }: { reasons: string[] }) {
  if (!reasons.length) return null;
  return (
    <Card className="border-amber-500/40 bg-amber-500/5">
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2 text-amber-700 dark:text-amber-400">
          <AlertTriangle className="h-5 w-5" />
          Why the tilts are small — degradation reasons
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-1.5 text-[15px] text-foreground/90">
          {reasons.map((r, i) => (
            <li key={i} className="flex gap-2">
              <span className="text-amber-600 dark:text-amber-400 shrink-0">·</span>
              <span>{r}</span>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-sm text-muted-foreground">
          A refusal is a finding about the evidence, not a failure of the
          factory. The benchmark core stands regardless.
        </p>
      </CardContent>
    </Card>
  );
}

function RuinBesideDream({ book }: { book: ICComposedBook }) {
  const w = book.wealth;
  if (!w?.available) return null;
  // The two numbers share one bordered container ON PURPOSE — the dream is
  // never rendered without the ruin number beside it.
  return (
    <div className="rounded-xl border border-border p-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-lg bg-emerald-500/10 p-4">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            Dream — P(reach {fmtMoney(w.targets.target_value)} in {w.targets.horizon_months}mo)
          </p>
          <p className="text-3xl font-bold tabular-nums text-emerald-700 dark:text-emerald-400">
            {pct(w.p_reach_target)}
          </p>
        </div>
        <div className="rounded-lg bg-red-500/10 p-4">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            Ruin — P(end below {fmtMoney(w.targets.ruin_value)})
          </p>
          <p className="text-3xl font-bold tabular-nums text-red-700 dark:text-red-400">
            {pct(w.p_below_ruin)}
          </p>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-3 text-[15px]">
        <div>
          <p className="text-xs text-muted-foreground">Median outcome</p>
          <p className="font-semibold tabular-nums">{fmtMoney(w.median)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">5th percentile</p>
          <p className="font-semibold tabular-nums">{fmtMoney(w.p5)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">95th percentile</p>
          <p className="font-semibold tabular-nums">{fmtMoney(w.p95)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Expected max drawdown</p>
          <p className="font-semibold tabular-nums">{pct(w.expected_max_drawdown)}</p>
        </div>
      </div>
      <p className="mt-3 text-sm text-muted-foreground">{w.assumption_note}</p>
    </div>
  );
}

function BookTable({ book }: { book: ICComposedBook }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[15px]">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th className="py-2 pr-3">Ticker</th>
            <th className="py-2 pr-3 text-right">Weight</th>
            <th className="py-2 pr-3 text-right">Dollars</th>
            <th className="py-2 pr-3 text-right">Shares</th>
            <th className="py-2 pr-3">Source</th>
            <th className="py-2">Reason</th>
          </tr>
        </thead>
        <tbody>
          {book.positions.map((p) => (
            <tr key={p.ticker} className="border-b border-border/50 align-top">
              <td className="py-2.5 pr-3 font-mono font-semibold">{p.ticker}</td>
              <td className="py-2.5 pr-3 text-right tabular-nums">{pct(p.weight, 2)}</td>
              <td className="py-2.5 pr-3 text-right tabular-nums">{fmtMoney(p.dollars)}</td>
              <td className="py-2.5 pr-3 text-right tabular-nums">
                {p.shares != null ? p.shares : "—"}
              </td>
              <td className="py-2.5 pr-3"><SourceBadge source={p.source} /></td>
              <td className="py-2.5 text-muted-foreground max-w-md">{p.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function InvestmentCommitteePage() {
  const [activeCapital, setActiveCapital] = useState("40000");
  const { data, isLoading, error } = useQuery<ICCommitteeResponse>({
    queryKey: ["ic", "committee"],
    queryFn: () => getInvestmentCommittee(),
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-96" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }
  if (error || !data) {
    return (
      <Card className="border-red-500/40">
        <CardContent className="py-6 text-[15px]">
          The committee endpoint is unreachable
          {error instanceof Error ? ` — ${error.message}` : ""}. This is a
          transport failure, not an evidence one: the composed book degrades to
          a benchmark core on evidence problems, never to this screen.
        </CardContent>
      </Card>
    );
  }

  const book = data.books[activeCapital] ?? Object.values(data.books)[0];
  const gate = data.registry_gate;
  const rs = data.ranking_summary;

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="flex items-center gap-3">
        <Landmark className="h-7 w-7 text-primary" />
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Investment Committee</h1>
          <p className="text-[15px] text-muted-foreground">
            {data.universe_screened != null
              ? `${data.universe_screened.toLocaleString()} US names screened · `
              : ""}
            benchmark core + evidence-scaled tilts · paper only, not financial advice
          </p>
        </div>
      </div>

      {/* 1 — Ranking gate */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <ShieldCheck className={`h-5 w-5 ${gate?.status === "CLEAN"
              ? "text-emerald-600 dark:text-emerald-400"
              : "text-red-600 dark:text-red-400"}`} />
            Ranking gate: {gate?.status ?? "UNKNOWN"}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5">
          {gate?.error && (
            <p className="text-[15px] text-red-700 dark:text-red-400">{gate.error}</p>
          )}
          {(gate?.invariance_checks ?? []).map((c) => (
            <p key={c.signal_id} className="text-[15px] font-mono">
              <span className="font-semibold">{c.signal_id}</span>{" "}
              <span className="text-muted-foreground">
                {c.grade}/{c.role} · rho={c.spearman_rho} · {c.n_names_moved} moved →{" "}
              </span>
              {c.invariant_holds ? (
                <span className="text-emerald-700 dark:text-emerald-400">
                  cannot reorder the BUY list
                </span>
              ) : (
                <span className="text-red-700 dark:text-red-400">
                  CAN REORDER — VIOLATION
                </span>
              )}
            </p>
          ))}
        </CardContent>
      </Card>

      {/* 2 — Evidence coverage */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Evidence coverage</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-[15px]">
            <span className="font-semibold">{rs.n_with_licensed_evidence}</span> of{" "}
            <span className="font-semibold">{rs.n_candidates}</span> candidates carry
            a signal this programme licenses · {rs.n_buy} BUY · {rs.n_watch} WATCH
          </p>
          {rs.n_candidates > rs.n_with_licensed_evidence && (
            <p className="mt-1 text-[15px] text-muted-foreground">
              The other {rs.n_candidates - rs.n_with_licensed_evidence} are screened,
              liquid and priced — and the engine has nothing it is allowed to say
              about them.
            </p>
          )}
          {!data.funnel_available && (
            <p className="mt-1 text-[15px] text-amber-700 dark:text-amber-400">
              No funnel run available — the page is a pure benchmark core today.
            </p>
          )}
        </CardContent>
      </Card>

      {/* 3 — Top opportunities */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Top opportunities</CardTitle>
        </CardHeader>
        <CardContent>
          {data.top_opportunities.length === 0 ? (
            <p className="text-[15px] text-muted-foreground">
              None — no candidate carries licensed evidence today.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[15px]">
                <thead>
                  <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="py-2 pr-3">#</th>
                    <th className="py-2 pr-3">Ticker</th>
                    <th className="py-2 pr-3">Verdict</th>
                    <th className="py-2 pr-3">Confidence</th>
                    <th className="py-2 pr-3">Grade</th>
                    <th className="py-2 pr-3 text-right">Score</th>
                    <th className="py-2">Led by</th>
                  </tr>
                </thead>
                <tbody>
                  {data.top_opportunities.slice(0, 15).map((o) => (
                    <tr key={o.ticker} className="border-b border-border/50">
                      <td className="py-2 pr-3 tabular-nums">{o.rank}</td>
                      <td className="py-2 pr-3 font-mono font-semibold">{o.ticker}</td>
                      <td className="py-2 pr-3">
                        {o.recommendation === "BUY" ? (
                          <Badge className="bg-emerald-600/15 text-emerald-700 dark:text-emerald-400 border-emerald-600/30">BUY</Badge>
                        ) : (
                          <Badge variant="outline">{o.recommendation}</Badge>
                        )}
                        {o.tied_with > 0 && (
                          <span className="ml-1.5 text-xs text-muted-foreground">
                            tied ×{o.tied_with + 1}
                          </span>
                        )}
                      </td>
                      <td className="py-2 pr-3">{o.confidence}</td>
                      <td className="py-2 pr-3">{o.evidence_grade}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">
                        {o.ranking_score.toFixed(3)}
                      </td>
                      <td className="py-2 text-muted-foreground font-mono text-sm">
                        {o.rank_led_by ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 4+5 — THE BOOK, per capital level */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CardTitle className="text-base flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-primary" />
              The book — {book.template} core ({pct(book.core_weight)}) +
              evidence tilts ({pct(book.tilt_weight)})
            </CardTitle>
            <div className="flex gap-2">
              {CAPITAL_TABS.map((t) => (
                <Button
                  key={t.key}
                  size="sm"
                  variant={activeCapital === t.key ? "default" : "outline"}
                  onClick={() => setActiveCapital(t.key)}
                >
                  {t.label}
                </Button>
              ))}
            </div>
          </div>
          <p className="text-[15px] text-muted-foreground">{book.template_description}</p>
        </CardHeader>
        <CardContent className="space-y-4">
          <DegradationBanner reasons={book.degradation_reasons} />
          <BookTable book={book} />
        </CardContent>
      </Card>

      {/* 6 — Honesty: ruin BESIDE dream, never separated */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Scale className="h-5 w-5 text-primary" />
            Honesty — ruin beside dream
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <RuinBesideDream book={book} />
          <div className="rounded-lg bg-muted/40 p-4">
            <p className="text-[15px] font-semibold">
              {data.honesty.core_and_tilts}
            </p>
          </div>
          <div className="space-y-2 text-sm text-muted-foreground">
            {Object.entries(data.honesty)
              .filter(([k]) => k !== "core_and_tilts")
              .map(([k, v]) => (
                <p key={k}>
                  <span className="font-semibold uppercase text-xs tracking-wide">
                    {k.replaceAll("_", " ")}:
                  </span>{" "}
                  {v}
                </p>
              ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
