"use client";

/**
 * Conviction lane — decision capture (TRIAL-003).
 *
 * Personal UI over the immutable, forward-only decision log: every buy/sell
 * logged here (with rationale + conviction) is applied to the conviction paper
 * lane on the next daily check. Timestamps are server-now (no backdating);
 * corrections append, never edit. This log is the only honest forward test of
 * discretionary stock-picking — no skill claims before 24 months.
 */

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, NotebookPen, ShieldAlert } from "lucide-react";

import {
  piGetConvictionDecisions,
  piLogConvictionDecision,
  type ConvictionDecisionRequest,
} from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const ACTIONS = ["enter", "add", "trim", "exit"] as const;
const MIN_RATIONALE = 50;

const inputCls =
  "rounded-md border border-border bg-background px-3 py-2 text-sm " +
  "placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring";

export default function ConvictionPage() {
  const queryClient = useQueryClient();

  const [ticker, setTicker] = useState("");
  const [action, setAction] = useState<(typeof ACTIONS)[number]>("enter");
  const [shares, setShares] = useState("");
  const [price, setPrice] = useState("");
  const [conviction, setConviction] = useState(3);
  const [rationale, setRationale] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [stopPrice, setStopPrice] = useState("");
  const [exitTrigger, setExitTrigger] = useState("");
  const [lateEntry, setLateEntry] = useState(false);

  const decisionsQuery = useQuery({
    queryKey: queryKeys.pi.convictionDecisions,
    queryFn: () => piGetConvictionDecisions(100),
    staleTime: 60 * 1000,
  });

  const logMutation = useMutation({
    mutationFn: (body: ConvictionDecisionRequest) => piLogConvictionDecision(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pi.convictionDecisions });
      setTicker("");
      setShares("");
      setPrice("");
      setRationale("");
      setTargetPrice("");
      setStopPrice("");
      setExitTrigger("");
      setLateEntry(false);
    },
  });

  const sharesNum = parseFloat(shares);
  const priceNum = parseFloat(price);
  // exit/trim reduce the position: the backend expects a signed shares_delta.
  const signedShares =
    action === "trim" || action === "exit"
      ? -Math.abs(sharesNum)
      : Math.abs(sharesNum);

  const rationaleShort = rationale.trim().length < MIN_RATIONALE;
  const canSubmit =
    ticker.trim().length > 0 &&
    Number.isFinite(sharesNum) &&
    sharesNum !== 0 &&
    Number.isFinite(priceNum) &&
    priceNum > 0 &&
    !rationaleShort &&
    !logMutation.isPending;

  const submit = () => {
    if (!canSubmit) return;
    logMutation.mutate({
      ticker: ticker.trim().toUpperCase(),
      action,
      shares_delta: signedShares,
      price: priceNum,
      rationale: rationale.trim(),
      conviction,
      target_price: targetPrice ? parseFloat(targetPrice) : null,
      stop_price: stopPrice ? parseFloat(stopPrice) : null,
      planned_exit_trigger: exitTrigger.trim() || null,
      late_entry: lateEntry,
    });
  };

  const decisions = decisionsQuery.data?.decisions ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/portfolio-intelligence">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="h-4 w-4 mr-1" /> Portfolio Intelligence
          </Button>
        </Link>
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <NotebookPen className="h-5 w-5" /> Conviction Decisions
        </h1>
      </div>

      <Card>
        <CardContent className="pt-4 text-sm text-muted-foreground flex gap-2">
          <ShieldAlert className="h-4 w-4 mt-0.5 shrink-0" />
          <p>
            This log is <strong>immutable and forward-only</strong>: timestamps are
            set by the server (never backdated), corrections append as new rows, and
            each decision is applied to the conviction paper lane on the next daily
            check. It is the forward test of discretionary stock-picking
            (TRIAL-003) — no skill claims before 24 months of tracked decisions.
          </p>
        </CardContent>
      </Card>

      {/* New decision form */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Log a decision
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <input
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="Ticker"
              className={`w-24 ${inputCls}`}
            />
            <select
              value={action}
              onChange={(e) => setAction(e.target.value as (typeof ACTIONS)[number])}
              className={`w-28 ${inputCls}`}
            >
              {ACTIONS.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
            <input
              type="number"
              value={shares}
              onChange={(e) => setShares(e.target.value)}
              placeholder="Shares"
              min="0"
              step="any"
              className={`w-24 ${inputCls}`}
            />
            <input
              type="number"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              placeholder="Price ($)"
              min="0"
              step="0.01"
              className={`w-28 ${inputCls}`}
            />
            <select
              value={conviction}
              onChange={(e) => setConviction(parseInt(e.target.value, 10))}
              className={`w-36 ${inputCls}`}
            >
              {[1, 2, 3, 4, 5].map((c) => (
                <option key={c} value={c}>
                  Conviction {c}/5
                </option>
              ))}
            </select>
          </div>

          {(action === "trim" || action === "exit") && (
            <p className="text-xs text-muted-foreground">
              {action === "trim" ? "Trim" : "Exit"} logs a negative share delta of{" "}
              {Number.isFinite(sharesNum) ? Math.abs(sharesNum) : "…"} shares.
            </p>
          )}

          <div>
            <textarea
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              placeholder={`Why? Thesis, catalyst, what would prove you wrong… (min ${MIN_RATIONALE} chars — the honest-record discipline)`}
              rows={3}
              className={`w-full ${inputCls}`}
            />
            <p
              className={`text-xs mt-1 ${
                rationaleShort ? "text-destructive" : "text-muted-foreground"
              }`}
            >
              {rationale.trim().length}/{MIN_RATIONALE} chars
            </p>
          </div>

          <div className="flex flex-wrap gap-2 items-center">
            <input
              type="number"
              value={targetPrice}
              onChange={(e) => setTargetPrice(e.target.value)}
              placeholder="Target $ (opt)"
              min="0"
              step="0.01"
              className={`w-32 ${inputCls}`}
            />
            <input
              type="number"
              value={stopPrice}
              onChange={(e) => setStopPrice(e.target.value)}
              placeholder="Stop $ (opt)"
              min="0"
              step="0.01"
              className={`w-32 ${inputCls}`}
            />
            <input
              type="text"
              value={exitTrigger}
              onChange={(e) => setExitTrigger(e.target.value)}
              placeholder="Planned exit trigger (opt)"
              className={`w-64 ${inputCls}`}
            />
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input
                type="checkbox"
                checked={lateEntry}
                onChange={(e) => setLateEntry(e.target.checked)}
              />
              Late entry (action already happened)
            </label>
          </div>

          <div className="flex items-center gap-3">
            <Button onClick={submit} disabled={!canSubmit}>
              {logMutation.isPending ? "Logging…" : "Log decision"}
            </Button>
            {logMutation.isSuccess && (
              <span className="text-sm text-muted-foreground">
                Logged #{logMutation.data.id} at {logMutation.data.timestamp}
              </span>
            )}
            {logMutation.isError && (
              <span className="text-sm text-destructive">
                {(logMutation.error as Error).message}
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Decision log */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Decision log (newest first)
          </CardTitle>
        </CardHeader>
        <CardContent>
          {decisionsQuery.isLoading && <Skeleton className="h-40" />}
          {decisionsQuery.isError && (
            <p className="text-sm text-destructive">
              {(decisionsQuery.error as Error).message}
            </p>
          )}
          {!decisionsQuery.isLoading && decisions.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No decisions logged yet. The lane holds its seeded book until the
              first logged decision.
            </p>
          )}
          {decisions.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-muted-foreground border-b border-border">
                    <th className="py-2 pr-3">When</th>
                    <th className="py-2 pr-3">Ticker</th>
                    <th className="py-2 pr-3">Action</th>
                    <th className="py-2 pr-3 text-right">Δ Shares</th>
                    <th className="py-2 pr-3 text-right">Price</th>
                    <th className="py-2 pr-3">Conv.</th>
                    <th className="py-2">Rationale</th>
                  </tr>
                </thead>
                <tbody>
                  {decisions.map((d) => (
                    <tr key={d.id} className="border-b border-border/50 align-top">
                      <td className="py-2 pr-3 whitespace-nowrap">
                        {d.timestamp?.slice(0, 16).replace("T", " ")}
                        {Boolean(d.late_entry) && (
                          <Badge variant="outline" className="ml-1">
                            late
                          </Badge>
                        )}
                      </td>
                      <td className="py-2 pr-3 font-medium">{d.ticker}</td>
                      <td className="py-2 pr-3">{d.action}</td>
                      <td className="py-2 pr-3 text-right">{d.shares_delta}</td>
                      <td className="py-2 pr-3 text-right">
                        ${Number(d.price).toFixed(2)}
                      </td>
                      <td className="py-2 pr-3">{d.conviction}/5</td>
                      <td className="py-2 max-w-xl whitespace-pre-wrap">
                        {d.rationale}
                        {d.amends_id != null && (
                          <Badge variant="outline" className="ml-1">
                            amends #{d.amends_id}
                          </Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
