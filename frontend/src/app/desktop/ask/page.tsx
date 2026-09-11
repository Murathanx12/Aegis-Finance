"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { BookOpen, Power, Send, ShieldOff } from "lucide-react";
import { ApiState, DASH, RawPayload } from "@/components/desktop/primitives";
import {
  ask,
  errorText,
  getLlama,
  getMorning,
  isNotBuilt,
  type AskResponse,
  type MorningResponse,
} from "@/lib/control-api";

interface Turn {
  id: number;
  question: string;
  data: AskResponse | null;
  error: string | null;
}

/** The assistant's authority, as the endpoint itself states it. */
const AUTHORITY_FALLBACK =
  "READER ONLY: this endpoint cannot run, seal, arm or order anything";

export default function AskAegisPage() {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const nextId = useRef(1);
  const endRef = useRef<HTMLDivElement | null>(null);

  const llama = useQuery({
    queryKey: ["desktop", "llama"],
    queryFn: getLlama,
    refetchInterval: 15_000,
    retry: false,
  });

  // TODAY'S BRIEF (O5 -> O6). The morning's own receipt, loaded when the page
  // opens, so "what do you think happens today?" has something behind it before
  // it is asked. When the morning has not run the panel says so and points at
  // the button rather than leaving the reader to wonder.
  const morning = useQuery<MorningResponse>({
    queryKey: ["control", "morning"],
    queryFn: () => getMorning(),
    retry: false,
  });
  const forecastStep = (morning.data?.steps ?? []).find((s) => s.step === "forecasts");
  const forecastRows = Array.isArray(forecastStep?.rows)
    ? (forecastStep?.rows as Array<Record<string, unknown>>)
    : [];

  const st = llama.data;
  // Same three-state reading as the Services page: bound is not ready.
  const phase = st == null ? "unknown" : st.ready ? "ready" : st.listening ? "loading" : "down";

  // The local model's files. `model_present === false` is the one case a start
  // button cannot fix, and the refusal already says so — offering to start a
  // server whose weights are not on disk is a button that can only fail.
  const filesPresent = st == null || (st.model_present !== false && st.binary_present !== false);

  const send = useMutation({
    mutationFn: ({ q, start }: { q: string; start: boolean }) => ask(q, { start }),
    onMutate: ({ q }) => {
      const id = nextId.current++;
      setTurns((t) => [...t, { id, question: q, data: null, error: null }]);
      return { id };
    },
    onSuccess: (data, _q, ctx) => {
      setTurns((t) => t.map((x) => (x.id === ctx?.id ? { ...x, data } : x)));
    },
    onError: (e, _q, ctx) => {
      setTurns((t) => t.map((x) => (x.id === ctx?.id ? { ...x, error: errorText(e) } : x)));
    },
  });

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const submit = (start = false) => {
    const q = question.trim();
    if (!q || send.isPending) return;
    setQuestion("");
    send.mutate({ q, start });
  };

  /** Re-send a question that was refused, this time asking for a start. */
  const retryWithStart = (q: string) => {
    if (send.isPending) return;
    send.mutate({ q, start: true });
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="border-b">
          <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
            <BookOpen className="size-4" /> Ask Aegis
            {phase === "ready" ? (
              <Badge>local model ready</Badge>
            ) : phase === "loading" ? (
              <Badge variant="secondary">loading the model</Badge>
            ) : phase === "down" ? (
              <Badge variant="outline">local model not running</Badge>
            ) : (
              <Badge variant="outline">local model: unknown</Badge>
            )}
            {st?.model ? (
              <Badge variant="outline" className="font-mono">
                {st.model}
              </Badge>
            ) : null}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="flex gap-1.5 rounded-lg border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            <ShieldOff className="mt-0.5 size-3.5 shrink-0" />
            <span>
              <strong className="text-foreground">This is a READER of receipts.</strong>{" "}
              It explains what is written on disk and where a number came from. It
              cannot run a job, seal a verdict, arm a lane, size a position or place an
              order — the control plane it talks to has no broker import, and an AST
              test keeps it that way. No LLM holds authority over capital here. Treat
              every answer as a pointer to the receipt, not as the receipt.
            </span>
          </p>

          {/* Today's brief, from the morning receipt. Rows or an em dash — never
              a sentence generated here, which would be a forecast in no ledger. */}
          <div className="rounded-lg border border-border bg-muted/20 px-3 py-2 text-xs">
            <p className="mb-1 font-medium text-foreground">Today&rsquo;s brief</p>
            {morning.isLoading ? (
              <p className="text-muted-foreground">loading the morning receipt…</p>
            ) : morning.data?.ran === false || !morning.data ? (
              <p className="text-muted-foreground">
                {DASH} the morning has not run today. Run it from the board and this
                panel fills with the forecast rows it wrote.
              </p>
            ) : forecastRows.length === 0 ? (
              <p className="text-muted-foreground">
                {DASH} the morning ran ({morning.data.date} run {morning.data.run}) and
                wrote no forecast row.{" "}
                {String(forecastStep?.reason ?? "")}
              </p>
            ) : (
              <ul className="space-y-0.5 font-mono text-[11px] text-muted-foreground">
                {forecastRows.map((r, i) => (
                  <li key={i}>
                    {String(r.lane)} beats {String(r.benchmark)}
                    {r.benchmark_is_fallback ? " (an index, not a twin)" : ""}: p ={" "}
                    {String(r.probability)} · {String(r.basis)} ·{" "}
                    {String(r.n_paired_days)} paired sessions
                  </li>
                ))}
              </ul>
            )}
            {morning.data?.path_rel ? (
              <p className="mt-1 break-all font-mono text-[10px] text-muted-foreground">
                {morning.data.path_rel}
              </p>
            ) : null}
          </div>

          <div className="space-y-3">
            {turns.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No questions asked yet in this session.
              </p>
            ) : null}

            {turns.map((t) => {
              const d = t.data;
              const refused = d != null && d.ok === false;
              const sources = Array.isArray(d?.context_sources) ? d.context_sources : [];
              return (
                <div key={t.id} className="space-y-1.5">
                  <div className="rounded-lg bg-muted/40 px-3 py-2 text-xs">
                    <span className="text-muted-foreground">you · </span>
                    {t.question}
                  </div>
                  <div className="rounded-lg border border-border px-3 py-2 text-xs">
                    <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                      <span>answered by</span>
                      <span className="font-mono text-foreground">
                        {d?.model ?? (refused ? "nothing — refused" : st?.model ?? DASH)}
                      </span>
                      {d?.backend ? (
                        <Badge variant="outline" className="font-mono text-[10px]">
                          {d.backend}
                        </Badge>
                      ) : null}
                      {typeof d?.cost_usd === "number" ? (
                        <span>· ${d.cost_usd.toFixed(4)}</span>
                      ) : null}
                      {d?.context_truncated ? (
                        <Badge variant="secondary" className="text-[10px]">
                          context truncated
                        </Badge>
                      ) : null}
                      {d?.tool ? (
                        <Badge variant="outline" className="font-mono text-[10px]">
                          tool: {d.tool}
                          {d.tool_arg ? ` ${d.tool_arg}` : ""}
                        </Badge>
                      ) : null}
                      {d?.answered_by === "ledger" ? (
                        <Badge variant="outline" className="text-[10px]">
                          from the ledger — no model called
                        </Badge>
                      ) : null}
                    </div>

                    {t.error ? (
                      <p className="text-destructive">{t.error}</p>
                    ) : refused ? (
                      // A refusal is GUIDANCE, not a failure: the model is not up
                      // yet and the fix is one tab away.
                      <div className="space-y-2 rounded-md bg-muted/40 px-2 py-1.5">
                        <p className="text-muted-foreground">
                          {d?.refusal ??
                            "the local model is not ready, so no answer was produced"}
                        </p>
                        {typeof d?.waited_s === "number" && d.waited_s > 0 ? (
                          <p className="text-[11px] text-muted-foreground">
                            waited {d.waited_s}s for the model to answer /health
                            {d.started ? " after starting it" : ""}.
                          </p>
                        ) : null}
                        {filesPresent && d?.started !== true ? (
                          <Button
                            size="xs"
                            variant="outline"
                            disabled={send.isPending}
                            onClick={() => retryWithStart(t.question)}
                          >
                            <Power className="size-3.5" />
                            Start the local model and ask again
                          </Button>
                        ) : null}
                        <Button size="xs" variant="outline" asChild>
                          <Link href="/desktop">Start the local model on the Services page</Link>
                        </Button>
                      </div>
                    ) : d?.answer ? (
                      <p className="whitespace-pre-wrap leading-relaxed">{d.answer}</p>
                    ) : d ? (
                      <p className="text-muted-foreground">
                        The endpoint answered with no text under{" "}
                        <span className="font-mono">answer</span> — the full payload is
                        below.
                      </p>
                    ) : (
                      <p className="text-muted-foreground">thinking…</p>
                    )}

                    {d?.authority ? (
                      <p className="mt-2 border-t border-border/60 pt-1.5 text-[11px] font-medium text-muted-foreground">
                        {d.authority}
                      </p>
                    ) : d?.answer ? (
                      <p className="mt-2 border-t border-border/60 pt-1.5 text-[11px] font-medium text-muted-foreground">
                        {AUTHORITY_FALLBACK}
                      </p>
                    ) : null}

                    {d?.routed_because ? (
                      <p className="mt-1 text-[11px] text-muted-foreground">
                        routed because {d.routed_because}
                      </p>
                    ) : null}

                    {sources.length ? (
                      <details className="mt-2">
                        <summary className="cursor-pointer text-[11px] text-muted-foreground hover:text-foreground">
                          {sources.length} receipt{sources.length === 1 ? "" : "s"} were the
                          only source of numbers
                        </summary>
                        <div className="mt-1.5 flex flex-wrap gap-1.5">
                          {sources.map((s) => (
                            <Badge
                              key={String(s)}
                              variant="outline"
                              className="font-mono text-[10px]"
                            >
                              {String(s)}
                            </Badge>
                          ))}
                        </div>
                      </details>
                    ) : null}

                    {d ? <RawPayload data={d} /> : null}
                  </div>
                </div>
              );
            })}
            <div ref={endRef} />
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
            className="flex gap-2"
          >
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. what does the G3 receipt say about the drawdown refusals?"
              className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              aria-label="question"
            />
            <Button type="submit" disabled={!question.trim() || send.isPending}>
              <Send className="size-3.5" />
              {send.isPending ? "asking…" : "Ask"}
            </Button>
            {phase === "down" && filesPresent ? (
              // One click instead of two pages: the endpoint starts the server
              // and waits for it before answering. It is a separate button
              // because starting a multi-GB model is a decision, not a default.
              <Button
                type="button"
                variant="outline"
                disabled={!question.trim() || send.isPending}
                onClick={() => submit(true)}
                title="starts llama-server, waits up to 90s for it to load, then answers"
              >
                <Power className="size-3.5" />
                Start the local model and ask
              </Button>
            ) : null}
          </form>

          {phase === "down" || phase === "loading" ? (
            <p className="text-[11px] text-muted-foreground">
              {phase === "loading"
                ? "The model is still loading; a question sent now will be refused with the same message."
                : "The local model is not running. "}
              {phase === "down" ? (
                <Link href="/desktop" className="underline underline-offset-2">
                  Start it on the Services page.
                </Link>
              ) : null}
            </p>
          ) : null}

          <ApiState error={send.error} what="Ask" />
          {isNotBuilt(send.error) ? (
            <p className="text-xs text-muted-foreground">
              <span className="font-mono">POST /api/control/ask</span> has not landed
              yet. This page has no model of its own and answers nothing locally.
            </p>
          ) : null}
          <ApiState error={llama.error} what="Local AI status" />
        </CardContent>
      </Card>
    </div>
  );
}
