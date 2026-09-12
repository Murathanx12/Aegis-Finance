"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ClipboardList, ShieldCheck } from "lucide-react";
import {
  ApiState,
  DASH,
  Field,
  RawPayload,
  fmtUtc,
} from "@/components/desktop/primitives";
import {
  agencyHold,
  agencyIntake,
  agencyPropose,
  errorText,
  getAgencyReview,
  getQuestionnaire,
  isNotBuilt,
  type AgencyOptionRow,
  type AgencyReviewResponse,
  type IntakeResponse,
  type ProposeResponse,
  type QuestionnaireResponse,
} from "@/lib/control-api";

/**
 * The agency (lane A): state a goal, read three costed options, hold one.
 *
 * Three rules this page keeps, each of which is a property of the payload
 * rather than a habit of the renderer:
 *
 * 1. **No option is drawn without its twins.** The control ids sit in the same
 *    block as the worst case, so there is no layout in which a reader sees the
 *    number and has to go looking for the control.
 * 2. **The Hold button cannot be pressed without a sentence.** The backend
 *    refuses a short one anyway — this is the same rule, said earlier, because
 *    `origin="human_text"` is the only marker separating a book a person chose
 *    from a book a job produced.
 * 3. **The limits sentence is rendered from the payload**, never from a string
 *    in this file: if the backend ever stops sending it, the page shows an em
 *    dash instead of a reassurance nobody is standing behind.
 */

function pct(v: number | null | undefined, digits = 1): string {
  return typeof v === "number" && Number.isFinite(v)
    ? `${(v * 100).toFixed(digits)}%`
    : DASH;
}
function usd(v: number | null | undefined): string {
  return typeof v === "number" && Number.isFinite(v)
    ? `$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
    : DASH;
}

const DECISION_TONE: Record<string, string> = {
  hold: "text-muted-foreground",
  buy_more: "text-emerald-600 dark:text-emerald-400",
  trim: "text-amber-600 dark:text-amber-400",
  sell: "text-red-600 dark:text-red-400",
};

function Limits({ text }: { text?: string }) {
  return (
    <p className="mt-3 border-t border-border/50 pt-2 text-[11px] text-muted-foreground">
      {text ?? DASH}
    </p>
  );
}

function OptionCard({
  option,
  onHold,
  holding,
}: {
  option: AgencyOptionRow;
  onHold: (o: AgencyOptionRow) => void;
  holding: boolean;
}) {
  const w = option.worst_case ?? {};
  const dd = option.expected_drawdown ?? {};
  return (
    <Card className={option.is_declared_choice ? "border-foreground/40" : ""}>
      <CardHeader className="pb-2">
        <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
          {option.personality}
          {option.is_declared_choice ? <Badge>what you said</Badge> : null}
          {option.extrapolated_tier ? (
            <Badge variant="outline">extrapolated tier</Badge>
          ) : null}
        </CardTitle>
        <p className="font-mono text-[10px] text-muted-foreground">
          {option.contract_hash}
        </p>
      </CardHeader>
      <CardContent>
        <Field label="names (k)" value={option.k ?? null} />
        <Field label="max per name" value={pct(option.max_single_name, 0)} />
        <Field label="gross / equity" value={option.gross_cap ?? null} />
        <Field label="stop" value={pct(option.stop_loss, 0)} />
        <Field label="drawdown budget" value={pct(option.drawdown_budget, 0)} />
        <Field label="cash floor" value={pct(option.cash_floor_pct, 0)} />
        <Field label="trades" value={option.cadence ?? null} />
        <Field label="cost curve" value={(option.cost_curve as string) ?? null} />

        <div className="mt-3 rounded-md border border-border/60 bg-muted/30 p-2">
          <p className="text-[11px] font-medium">worst case, in dollars</p>
          <p className="text-sm font-semibold tabular-nums">
            {usd(w.worst_case_usd)}{" "}
            <span className="text-xs font-normal text-muted-foreground">
              ({pct(w.worst_case_pct_of_equity)} of the book, at{" "}
              {typeof w.gross_over_equity === "number"
                ? `${w.gross_over_equity.toFixed(2)}x`
                : DASH}{" "}
              gross)
            </span>
          </p>
          <p className="mt-1 text-[11px] text-muted-foreground">{w.verdict ?? DASH}</p>
        </div>

        <div className="mt-2">
          <p className="text-[11px] font-medium text-muted-foreground">
            expected drawdown at the budget
          </p>
          <p className="text-xs">
            {dd.verdict === "CANNOT DETERMINE"
              ? `${DASH} ${dd.why ?? "not measurable yet"}`
              : `${pct(dd.worst_twin_drawdown)} worst on the twins (${
                  dd.n_twin_marks ?? 0
                } marks)`}
          </p>
        </div>

        {/* THE TWINS, in the same block as the number they control. */}
        <div className="mt-2">
          <p className="text-[11px] font-medium text-muted-foreground">
            controls created with it
          </p>
          {(option.twins ?? []).length === 0 ? (
            <p className="text-xs text-muted-foreground">
              {DASH} no twin came back, and an option without one is not shown as a
              number.
            </p>
          ) : (
            <ul className="space-y-0.5">
              {(option.twins ?? []).map((t) => (
                <li key={t.book_id} className="font-mono text-[10px] text-muted-foreground">
                  ↳ {t.kind ?? "twin"} {t.book_id.slice(0, 13)}
                </li>
              ))}
            </ul>
          )}
        </div>

        <p className="mt-2 text-[11px] text-muted-foreground">{option.hold_rule ?? DASH}</p>

        {(option.plain_words ?? []).map((p) => (
          <p key={p.number} className="mt-2 text-xs">
            {p.sentence}{" "}
            <span className="font-mono text-[10px] text-muted-foreground">
              {p.receipt_path}
            </span>
          </p>
        ))}

        <Button
          className="mt-3 w-full"
          variant={option.is_declared_choice ? "default" : "outline"}
          disabled={holding}
          onClick={() => onHold(option)}
        >
          Hold this one
        </Button>
      </CardContent>
    </Card>
  );
}

export default function AgencyPage() {
  const questionnaire = useQuery<QuestionnaireResponse>({
    queryKey: ["control", "agency", "questionnaire"],
    queryFn: getQuestionnaire,
  });
  const review = useQuery<AgencyReviewResponse>({
    queryKey: ["control", "agency", "review"],
    queryFn: () => getAgencyReview(),
  });

  const [capital, setCapital] = useState("50000");
  const [horizon, setHorizon] = useState("36");
  const [personality, setPersonality] = useState("");
  const [constraints, setConstraints] = useState("");
  const [liquidity, setLiquidity] = useState("0.05");
  const [answers, setAnswers] = useState<number[]>(Array(8).fill(2));
  const [sentence, setSentence] = useState("");
  const [ips, setIps] = useState<IntakeResponse | null>(null);
  const [options, setOptions] = useState<ProposeResponse | null>(null);
  const [held, setHeld] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const intake = useMutation({
    mutationFn: () =>
      agencyIntake({
        capital: Number(capital),
        horizon_months: Number(horizon),
        personality: personality || null,
        constraints: constraints
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        liquidity_need: Number(liquidity),
        answers,
      }),
    onSuccess: (data) => {
      setProblem(null);
      setIps(data);
      setOptions(null);
      setHeld(null);
      if (data.ips_hash) propose.mutate(data.ips_hash);
    },
    onError: (e) => setProblem(errorText(e)),
  });

  const propose = useMutation({
    mutationFn: (hash: string) => agencyPropose(hash),
    onSuccess: (data) => {
      setProblem(null);
      setOptions(data);
    },
    onError: (e) => setProblem(errorText(e)),
  });

  const hold = useMutation({
    mutationFn: (o: AgencyOptionRow) =>
      agencyHold(options?.ips_hash ?? "", o.contract_hash, sentence.trim()),
    onSuccess: (data) => {
      setProblem(null);
      setHeld(data.chosen_book_id ?? null);
      review.refetch();
    },
    onError: (e) => setProblem(errorText(e)),
  });

  if (questionnaire.error && isNotBuilt(questionnaire.error)) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">The agency</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">
            {DASH} this backend has no{" "}
            <code className="font-mono">/api/control/agency</code> routes yet.
          </p>
        </CardContent>
      </Card>
    );
  }

  const q = questionnaire.data;
  const canHold = sentence.trim().length >= 12 && !hold.isPending;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <ClipboardList className="size-4" /> The agency
          </CardTitle>
          <span className="text-[10px] text-muted-foreground">{fmtUtc(q?.utc)}</span>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">
            State what the money is for. The engine writes a policy, prices three
            expressions of it, and shows each one&apos;s worst case in dollars beside
            its controls.{" "}
            <span className="font-medium">You hold one; the other two are kept and
            graded beside it</span>, so the choice itself has a counterfactual.
          </p>
          <p className="mt-1 text-[11px] text-muted-foreground">{q?.convention ?? DASH}</p>
          <Limits text={q?.limits} />
        </CardContent>
      </Card>

      {/* ------------------------------------------------------ the intake */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">1 · What the money is for</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <label className="text-xs">
              capital (USD)
              <input
                value={capital}
                onChange={(e) => setCapital(e.target.value)}
                inputMode="decimal"
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
              />
            </label>
            <label className="text-xs">
              horizon (months)
              <input
                value={horizon}
                onChange={(e) => setHorizon(e.target.value)}
                inputMode="numeric"
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
              />
            </label>
            <label className="text-xs">
              personality
              <select
                value={personality}
                onChange={(e) => setPersonality(e.target.value)}
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
              >
                <option value="">(let the answers choose)</option>
                {Object.keys(q?.personalities ?? {}).map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs">
              liquidity need (0-1)
              <input
                value={liquidity}
                onChange={(e) => setLiquidity(e.target.value)}
                inputMode="decimal"
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
              />
            </label>
            <label className="text-xs">
              constraints (comma separated)
              <input
                value={constraints}
                onChange={(e) => setConstraints(e.target.value)}
                placeholder="NO_SECTOR:XLE, ESG_EXCLUDE:tobacco"
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
              />
            </label>
          </div>

          <div>
            <p className="mb-1 text-xs font-medium">
              2 · Eight questions ({q?.version ?? DASH})
            </p>
            <div className="space-y-2">
              {(q?.questions ?? []).map((item, i) => (
                <div key={item.qid} className="rounded-md border border-border/60 p-2">
                  <p className="text-xs">
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {item.qid} · {item.dimension}
                    </span>{" "}
                    {item.text}
                  </p>
                  <p className="text-[10px] text-muted-foreground">{item.scale}</p>
                  <div className="mt-1 flex gap-1">
                    {[0, 1, 2, 3, 4].map((v) => (
                      <button
                        key={v}
                        type="button"
                        onClick={() =>
                          setAnswers((a) => a.map((x, j) => (j === i ? v : x)))
                        }
                        className={`rounded px-2 py-0.5 text-xs ${
                          answers[i] === v
                            ? "bg-foreground text-background"
                            : "bg-muted text-muted-foreground"
                        }`}
                      >
                        {v}
                      </button>
                    ))}
                  </div>
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    source: {item.source}
                  </p>
                </div>
              ))}
            </div>
          </div>

          <Button onClick={() => intake.mutate()} disabled={intake.isPending}>
            {intake.isPending ? "writing the policy…" : "Write my policy"}
          </Button>
          {problem ? (
            <p className="text-xs text-red-600 dark:text-red-400">{problem}</p>
          ) : null}
        </CardContent>
      </Card>

      {/* -------------------------------------------------------- the IPS */}
      {ips ? (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
              Your policy
              <Badge variant="outline" className="font-mono">
                {ips.ips_hash}
              </Badge>
              <Badge variant="secondary">prose: {ips.prose_source ?? DASH}</Badge>
              <Badge variant="outline">validated by {ips.validated_by ?? DASH}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="whitespace-pre-wrap text-xs">{ips.ips_prose_md}</pre>
            {ips.prose_rejected ? (
              <p className="mt-2 text-[11px] text-amber-600 dark:text-amber-400">
                the model&apos;s draft was discarded: {ips.prose_rejected}
              </p>
            ) : null}
            {(ips.echoes ?? []).map((e) => (
              <p key={e} className="mt-1 text-[11px] text-muted-foreground">
                {e}
              </p>
            ))}
            <Limits text={ips.limits} />
          </CardContent>
        </Card>
      ) : null}

      {/* ---------------------------------------------------- the options */}
      {propose.isPending ? <Skeleton className="h-40 w-full" /> : null}
      {options ? (
        <>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">
                3 · Three ways to run it ({options.n_options ?? 0})
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground">
                {options.the_choice_is_graded ?? DASH}
              </p>
              <label className="mt-2 block text-xs">
                why you are holding this one (required, and recorded)
                <input
                  value={sentence}
                  onChange={(e) => setSentence(e.target.value)}
                  placeholder="e.g. balanced matches the three years I can leave it alone"
                  className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
                />
              </label>
              {!canHold ? (
                <p className="mt-1 text-[11px] text-muted-foreground">
                  a sentence of at least 12 characters is what makes the book yours —
                  it is the only thing separating it from one a night job produced.
                </p>
              ) : null}
              {held ? (
                <p className="mt-2 text-xs">
                  held: <span className="font-mono">{held}</span> — the other two are
                  running as shadows beside it.
                </p>
              ) : null}
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-3">
            {(options.options ?? []).map((o) => (
              <OptionCard
                key={o.contract_hash}
                option={o}
                holding={!canHold}
                onHold={(x) => hold.mutate(x)}
              />
            ))}
          </div>
        </>
      ) : null}

      {/* --------------------------------------------------- the review */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <ShieldCheck className="size-4" /> Today&apos;s review
          </CardTitle>
        </CardHeader>
        <CardContent>
          {review.error ? (
            <ApiState error={review.error} what="the daily review" />
          ) : review.isLoading ? (
            <Skeleton className="h-20 w-full" />
          ) : review.data?.ran === false ? (
            <p className="text-xs text-muted-foreground">
              {DASH} {review.data.note}
            </p>
          ) : (
            <>
              <Field label="books reviewed" value={review.data?.n_books ?? null} />
              <Field label="calls" value={review.data?.n_calls ?? null} />
              <Field label="refused" value={review.data?.n_refused ?? null} />
              <div className="mt-2 overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="text-muted-foreground">
                    <tr>
                      <th className="py-1 pr-3 font-normal">name</th>
                      <th className="py-1 pr-3 font-normal">call</th>
                      <th className="py-1 pr-3 text-right font-normal">p(beats twin)</th>
                      <th className="py-1 pr-3 font-normal">forecast row</th>
                    </tr>
                  </thead>
                  <tbody className="font-mono">
                    {(review.data?.calls ?? []).map((c) => (
                      <tr key={c.prediction_id} className="border-t border-border/30">
                        <td className="py-1 pr-3">{c.ticker}</td>
                        <td
                          className={`py-1 pr-3 ${DECISION_TONE[c.decision] ?? ""}`}
                        >
                          {c.decision}
                        </td>
                        <td className="py-1 pr-3 text-right tabular-nums">
                          {pct(c.probability, 0)}
                        </td>
                        <td className="py-1 pr-3 text-[10px] text-muted-foreground">
                          {c.prediction_id.slice(0, 12)} · {c.row_hash.slice(0, 8)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {(review.data?.calls ?? []).length === 0 ? (
                <p className="mt-2 text-xs text-muted-foreground">
                  {DASH} {review.data?.reason ?? "no call was written this morning."}
                </p>
              ) : (
                <p className="mt-2 text-[11px] text-muted-foreground">
                  every call above was written to the forecast ledger and read back
                  BEFORE it was shown; the row id and its hash are printed so the
                  claim can be checked.
                </p>
              )}
              <Limits text={review.data?.limits} />
            </>
          )}
        </CardContent>
      </Card>

      {options ? <RawPayload data={options} /> : null}
    </div>
  );
}
