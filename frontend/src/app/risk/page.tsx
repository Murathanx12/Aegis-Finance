"use client";

// M6 — the page Murat actually uses.
//
// The routed research line finished and it terminated in measured negatives:
// return prediction does not clear its bar (206 published predictors, median
// -0.12%/yr net on our own panel), M4 refused to spend its confirmation window,
// and risk control resolves ~30x sooner than return on identical data.
//
// So this page shows an EXPOSURE, not a stock to buy. Every benefit statement
// is rendered from the backend's `claim` object, whose `established` flag is
// `|effect| >= MDE` decided when the measurement ran — there is no prose path
// that can promise something the measurement did not deliver.

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertTriangle, ShieldCheck, Info } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine, Cell,
} from "recharts";
import {
  getRiskLayerExposure, type Holding, type RiskClaim,
} from "@/lib/api";

const PERSONALITIES = ["preservation", "balanced", "aggressive", "extreme_growth"];

function loadHoldings(): Holding[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem("aegis_holdings");
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

/** Weights from shares x price — the same book every other page reads. */
function toWeights(holdings: Holding[]): { ticker: string; weight: number }[] {
  const vals = holdings.map((h) => ({
    ticker: h.ticker,
    value: (h.shares || 0) * (h.current_price || 0),
  })).filter((v) => v.value > 0);
  const total = vals.reduce((s, v) => s + v.value, 0);
  if (total <= 0) return [];
  return vals.map((v) => ({ ticker: v.ticker, weight: v.value / total }));
}

const pct = (x: number, d = 1) => `${(x * 100).toFixed(d)}%`;

/** A claim renders as measured or as NOT ESTABLISHED. There is no third style,
 *  because a hedged sentence reads as a weak yes and this must read as a no. */
function ClaimRow({ c }: { c: RiskClaim }) {
  const has = c.effect !== null && c.mde !== null;
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border/40 py-2 last:border-0">
      <div className="min-w-0">
        <p className="text-sm font-medium">
          {c.outcome.replace(/_/g, " ")}
          <span className="text-muted-foreground font-normal"> vs {c.comparator}</span>
        </p>
        <p className="text-[11px] text-muted-foreground leading-snug">{c.note}</p>
      </div>
      <div className="shrink-0 text-right">
        {has ? (
          <p className="tabular-nums text-sm font-semibold">
            {c.effect! > 0 ? "+" : ""}{c.effect!.toFixed(2)}
            <span className="text-[10px] text-muted-foreground"> {c.units}</span>
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">—</p>
        )}
        {has && (
          <p className="text-[10px] text-muted-foreground tabular-nums">
            MDE {c.mde!.toFixed(2)}
          </p>
        )}
        <Badge
          variant={c.established ? "default" : "outline"}
          className={`mt-1 text-[10px] ${c.established ? "" : "text-muted-foreground"}`}
        >
          {c.established ? "measured" : "not established"}
        </Badge>
      </div>
    </div>
  );
}

export default function RiskLayerPage() {
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [personality, setPersonality] = useState("balanced");
  const [targetVol, setTargetVol] = useState(0.15);

  useEffect(() => setHoldings(loadHoldings()), []);
  const weights = useMemo(() => toWeights(holdings), [holdings]);

  const { data, isLoading, error } = useQuery({
    queryKey: ["risk-layer", weights, personality, targetVol],
    queryFn: () => getRiskLayerExposure(weights, {
      personality, target_vol: targetVol,
    }),
    enabled: weights.length > 0,
    staleTime: 10 * 60 * 1000,
  });

  if (weights.length === 0) {
    return (
      <div className="p-6 max-w-3xl">
        <h1 className="text-2xl font-bold">Risk layer</h1>
        <p className="mt-2 text-muted-foreground">
          No holdings saved yet. Add them on the Portfolio page — this book is
          read from your browser and never leaves it.
        </p>
      </div>
    );
  }

  const d = data?.decision;
  const claim = data?.claim;

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold">Risk layer</h1>
        <p className="text-sm text-muted-foreground">
          How much of your book to hold — not what to buy. The research says
          plainly why: nothing published clears +3%/yr net among names you can
          actually trade.
        </p>
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <select
          className="rounded-md border bg-background px-3 py-1.5 text-sm"
          value={personality}
          onChange={(e) => setPersonality(e.target.value)}
        >
          {PERSONALITIES.map((p) => (
            <option key={p} value={p}>{p.replace(/_/g, " ")}</option>
          ))}
        </select>
        <label className="text-sm text-muted-foreground flex items-center gap-2">
          target volatility
          <input
            type="range" min={0.06} max={0.30} step={0.01} value={targetVol}
            onChange={(e) => setTargetVol(parseFloat(e.target.value))}
            className="w-40"
          />
          <span className="tabular-nums w-12">{pct(targetVol, 0)}</span>
        </label>
      </div>

      {error && (
        <Card className="border-amber-500/40">
          <CardContent className="pt-6 flex gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0" />
            <p className="text-sm">{(error as Error).message}</p>
          </CardContent>
        </Card>
      )}

      {isLoading && <Skeleton className="h-40 w-full" />}

      {d && claim && (
        <>
          {/* ── the number, and the one thing that would change it ── */}
          <Card>
            <CardHeader className="pb-2">
              {/* The grade sits ON THE HEADLINE, not below the claims. A
                  "measured" badge at the top with an EXPLORE caveat four cards
                  down is a caveat that gets scrolled past. */}
              <CardTitle className="text-base flex flex-wrap items-center gap-2">
                <ShieldCheck className="h-4 w-4" /> Hold {pct(d.weight, 0)} of your book
                <Badge variant="outline" className="text-[10px] font-normal">
                  {claim.evidence.status}
                </Badge>
                <Badge variant="outline" className="text-[10px] font-normal">
                  k_eff {claim.evidence.k_eff}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm">{data.what_would_change_it.statement}</p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  ["your 60-day volatility", pct(d.realised_vol)],
                  ["target", pct(d.target_vol, 0)],
                  ["cap", pct(d.cap, 0)],
                  ["rest in cash", pct(1 - d.weight, 0)],
                ].map(([k, v]) => (
                  <div key={k} className="rounded-lg bg-muted/30 p-3">
                    <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{k}</p>
                    <p className="text-lg font-bold tabular-nums">{v}</p>
                  </div>
                ))}
              </div>
              {data.unpriced_holdings.length > 0 && (
                <p className="text-xs text-amber-500">
                  Could not price {data.unpriced_holdings.join(", ")} — the
                  exposure above is for the rest of the book, renormalised.
                </p>
              )}
            </CardContent>
          </Card>

          {/* ── what it would have held, and what that cost ── */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">
                The last {data.decision_log.length} decisions, and what each cost or earned
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={data.decision_log}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                  <XAxis dataKey="month" tick={{ fontSize: 10 }} />
                  <YAxis tickFormatter={(v) => `${(v * 100).toFixed(1)}%`} tick={{ fontSize: 10 }} />
                  <Tooltip
                    formatter={(v, n) => [`${(Number(v) * 100).toFixed(2)}%`, String(n)]}
                    labelFormatter={(l) => `month ${l}`}
                  />
                  <ReferenceLine y={0} stroke="currentColor" opacity={0.4} />
                  <Bar dataKey="cost_vs_full" name="vs holding it all">
                    {data.decision_log.map((r, i) => (
                      <Cell key={i} fill={r.cost_vs_full >= 0 ? "#22c55e" : "#ef4444"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <p className="mt-2 text-xs text-muted-foreground">
                Green months are ones where holding less helped; red are ones it
                gave up return. Each bar is scored on the month that
                <em> followed</em> the decision, which is the only version of
                this number you could have acted on.
              </p>
            </CardContent>
          </Card>

          {/* ── the honest claim ── */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">What this is claimed to do</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm">
                Volatility reduced by{" "}
                <strong>{Math.abs(claim.risk_reduced.volatility_pp).toFixed(2)}pp/yr</strong>{" "}
                against buy and hold, and max drawdown by{" "}
                <strong>{Math.abs(claim.not_merely_holding_less.max_drawdown_pp).toFixed(1)}pp</strong>{" "}
                against holding the <em>same average exposure</em> flat — so it is
                not merely holding less.{" "}
                <strong className="text-amber-500">
                  The return effect is not established.
                </strong>
              </p>
              <p className="text-xs text-muted-foreground">
                {claim.return_effect.statement}
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg bg-muted/30 p-3">
                  <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    break-even return sacrifice
                  </p>
                  <p className="text-lg font-bold tabular-nums">
                    {claim.break_even_sacrifice_pct_per_year.toFixed(2)}%/yr
                  </p>
                  <p className="text-xs text-muted-foreground">{claim.break_even_note}</p>
                </div>
                {/* The equivalence half. "We could not tell" is about our
                    instrument; this is about which values are excluded, and
                    only the second is something to decide on. */}
                <div className="rounded-lg bg-muted/30 p-3">
                  <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    upper bound on the sacrifice
                  </p>
                  <p className="text-lg font-bold tabular-nums">
                    {claim.return_effect.bound.upper_95_one_sided_drag_pct.toFixed(2)}%/yr
                    <Badge
                      variant="outline"
                      className={`ml-2 align-middle text-[10px] font-normal ${
                        claim.return_effect.bound.worth_it_across_the_interval
                          ? ""
                          : "text-amber-500"
                      }`}
                    >
                      {claim.return_effect.bound.verdict.replace(/_/g, " ").toLowerCase()}
                    </Badge>
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {claim.return_effect.bound.statement}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* ── every claim, including the negatives, by name ── */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Info className="h-4 w-4" /> The whole evidence record
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-3 text-xs text-muted-foreground">
                {claim.evidence.base_asset}, {claim.evidence.window},{" "}
                {claim.evidence.n_days.toLocaleString()} days, net of{" "}
                {claim.evidence.cost_bps_per_crossing}bp per crossing. Effective
                independent tests across these cells: {claim.evidence.k_eff}.
              </p>
              {/* EXPLORE on its own reads as "confirmation pending". The power
                  check says it is not pending — it is unavailable — and a page
                  that leaves the first impression standing is making a promise
                  about the future that has already been refuted. */}
              <p className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs">
                <strong>Confirmation: {claim.evidence.confirmation}</strong>
                <br />
                <span className="text-muted-foreground">
                  {claim.evidence.confirmation_note}
                </span>
              </p>
              {claim.evidence.claims.map((c) => (
                <ClaimRow key={c.outcome} c={c} />
              ))}
            </CardContent>
          </Card>

          <p className="text-xs text-muted-foreground">
            Educational tool, not financial advice. Measured on a selection
            window. The reserved confirmation window stays unspent — not because
            we are saving it, but because a power check run before spending it
            showed it cannot resolve an effect this size.
          </p>
        </>
      )}
    </div>
  );
}
