"use client";

/**
 * "Aegis file on <TICKER>" -- everything this PC holds on one ticker (CH-22):
 * our own collected news (every source, newest first, with how each row was tagged
 * and the typed event when the world digest typed it), the frozen forecasts (open
 * and resolved, with outcome), the next calendar dates, and related names.
 *
 * Local only. The route answers 403 off the desktop shell, so on the public site
 * this renders NOTHING (no error card, no empty frame). An absent field prints the
 * em dash, never a stand-in.
 */

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiState, DASH, ageLabel, fmtUtc } from "@/components/desktop/primitives";
import {
  getTickerHub,
  hubUnavailable,
  isNotBuilt,
  type HubForecast,
  type HubNewsRow,
  type TickerHubResponse,
} from "@/lib/control-api";

const TABS = ["News", "Forecasts", "Calendar", "Related"] as const;
type Tab = (typeof TABS)[number];

const METHOD_LABEL: Record<string, string> = {
  source_field: "source field",
  sec_cik: "SEC CIK",
  reader_lane: "reader lane",
  reader_search: "reader search",
  digest_typed: "digest",
  text_token: "ticker token",
  name_match: "name match",
};

function num(v: number | null | undefined, digits = 2): string {
  return v == null || !Number.isFinite(v) ? DASH : v.toFixed(digits);
}

export function NewsRows({ rows, focus }: { rows: HubNewsRow[]; focus?: string }) {
  if (!rows.length) return <p className="text-sm text-muted-foreground">No rows in this window.</p>;
  return (
    <ul className="divide-y divide-border/30">
      {rows.map((r) => {
        const methods = r.tagged_by ?? Array.from(new Set(r.tags.map((t) => t.m)));
        const others = r.tags.map((t) => t.t).filter((t) => t !== focus);
        return (
          <li key={r.id} className="py-2">
            <div className="flex flex-wrap items-baseline gap-x-2 text-xs text-muted-foreground">
              <span className="font-mono">{fmtUtc(r.first_seen_utc)}</span>
              <span>{r.publisher ?? DASH}</span>
              <span className="opacity-60">({r.source})</span>
              {r.event?.event_type ? (
                <Badge variant="outline" className="text-[10px]">
                  {r.event.event_type}
                </Badge>
              ) : null}
            </div>
            {r.url ? (
              <a
                href={r.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-medium hover:text-primary transition-colors line-clamp-2"
              >
                {r.title ?? DASH}
              </a>
            ) : (
              <p className="text-sm font-medium line-clamp-2">{r.title ?? DASH}</p>
            )}
            <p className="text-[11px] text-muted-foreground">
              tagged by: {methods.map((m) => METHOD_LABEL[m] ?? m).join(", ") || DASH}
              {others.length ? <> · also: {others.slice(0, 8).join(", ")}</> : null}
              {r.event?.topic ? <> · topic: {r.event.topic}</> : null}
            </p>
          </li>
        );
      })}
    </ul>
  );
}

function ForecastTable({ rows, resolved }: { rows: HubForecast[]; resolved: boolean }) {
  if (!rows.length) return <p className="text-sm text-muted-foreground">None.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-muted-foreground">
          <tr className="text-left">
            <th className="py-1 pr-2">made</th>
            <th className="py-1 pr-2">observable</th>
            <th className="py-1 pr-2">p</th>
            <th className="py-1 pr-2">horizon</th>
            {resolved ? (
              <>
                <th className="py-1 pr-2">resolved</th>
                <th className="py-1 pr-2">outcome</th>
                <th className="py-1 pr-2">realised</th>
                <th className="py-1 pr-2">brier</th>
              </>
            ) : (
              <th className="py-1 pr-2">resolves after</th>
            )}
            <th className="py-1 pr-2">by</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 100).map((f, i) => (
            <tr key={f.id ?? i} className="border-t border-border/20" title={f.thesis ?? undefined}>
              <td className="py-1 pr-2 font-mono">{f.made_at ? f.made_at.slice(0, 10) : DASH}</td>
              <td className="py-1 pr-2">
                {f.observable ?? DASH}
                {f.threshold != null ? ` (${f.threshold})` : ""}
              </td>
              <td className="py-1 pr-2 tabular-nums">{num(f.probability)}</td>
              <td className="py-1 pr-2">{f.horizon_days != null ? `${f.horizon_days}d` : DASH}</td>
              {resolved ? (
                <>
                  <td className="py-1 pr-2 font-mono">{f.resolved_at ?? DASH}</td>
                  <td className="py-1 pr-2">{f.outcome ?? DASH}</td>
                  <td className="py-1 pr-2 tabular-nums">
                    {f.realised_return == null ? DASH : `${(f.realised_return * 100).toFixed(1)}%`}
                  </td>
                  <td className="py-1 pr-2 tabular-nums">{num(f.brier, 3)}</td>
                </>
              ) : (
                <td className="py-1 pr-2 font-mono">{f.resolves_after ?? DASH}</td>
              )}
              <td className="py-1 pr-2">{f.specialist ?? f.model ?? DASH}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 100 ? (
        <p className="mt-1 text-[11px] text-muted-foreground">showing 100 of {rows.length}</p>
      ) : null}
    </div>
  );
}

function Body({ data, tab }: { data: TickerHubResponse; tab: Tab }) {
  if (tab === "News") return <NewsRows rows={data.news} focus={data.ticker} />;
  if (tab === "Forecasts") {
    const c = data.forecasts.counts;
    return (
      <div className="space-y-4">
        <p className="text-xs text-muted-foreground">
          open {c.open} · resolved {c.resolved} (outcome 1: {c.resolved_outcome_1 ?? DASH}, 0:{" "}
          {c.resolved_outcome_0 ?? DASH}) · void {c.void} · mean Brier {num(c.mean_brier, 3)} over{" "}
          {c.n_brier ?? DASH}. Written before the outcome and graded after it; an observation, not advice.
        </p>
        <div>
          <p className="mb-1 text-xs font-medium">Open</p>
          <ForecastTable rows={data.forecasts.open} resolved={false} />
        </div>
        <div>
          <p className="mb-1 text-xs font-medium">Resolved</p>
          <ForecastTable rows={data.forecasts.resolved} resolved />
        </div>
      </div>
    );
  }
  if (tab === "Calendar") {
    const cal = data.calendar;
    return (
      <div className="space-y-3">
        <p className="text-xs text-muted-foreground">
          forward calendar: {cal.status}
          {cal.label ? ` · ${cal.label}` : ""}
          {cal.last_reported ? ` · last reported ${cal.last_reported}` : ""}
          {cal.error ? ` · ${cal.error}` : ""}
        </p>
        {cal.rows.length ? (
          <ul className="text-sm space-y-1">
            {cal.rows.map((r, i) => (
              <li key={i} className="flex flex-wrap gap-x-2">
                <span className="font-mono">{r.date ?? DASH}</span>
                <span>{r.kind ?? DASH}</span>
                <span className="text-muted-foreground text-xs">
                  {r.confirmation ?? DASH}
                  {r.timing ? ` · ${r.timing}` : ""}
                  {r.days_away != null ? ` · in ${r.days_away}d` : ""}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">No dated row in the horizon.</p>
        )}
        {data.events.length ? (
          <div>
            <p className="mb-1 text-xs font-medium">Event nodes</p>
            <ul className="text-xs space-y-1">
              {data.events.slice(0, 20).map((e) => (
                <li key={`${e.event_id}-${e.role}`}>
                  <span className="font-mono">{fmtUtc(e.first_seen_utc)}</span> · {e.role} ({e.link},{" "}
                  {e.link_quality}) · {e.title ?? e.event_id} · publishers {e.n_publishers ?? DASH}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    );
  }
  return data.related.length ? (
    <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-sm">
      {data.related.map((r) => (
        <li key={`${r.ticker}-${r.link}`} className="flex gap-2">
          <Link href={`/stock/${r.ticker}`} className="font-mono hover:text-primary">
            {r.ticker}
          </Link>
          <span className="truncate">{r.name ?? DASH}</span>
          <span className="text-xs text-muted-foreground">
            {r.link}
            {r.weight != null ? ` ${r.weight}` : ""}
          </span>
        </li>
      ))}
    </ul>
  ) : (
    <p className="text-sm text-muted-foreground">No related names on file.</p>
  );
}

export function AegisFileCard({ ticker }: { ticker: string }) {
  const [tab, setTab] = useState<Tab>("News");
  const [days, setDays] = useState(30);
  const { data, error, isLoading } = useQuery({
    queryKey: ["ticker-hub", ticker, days],
    queryFn: () => getTickerHub(ticker, days),
    enabled: ticker.length > 0,
    retry: false,
    staleTime: 60_000,
  });
  if (!ticker || (error && hubUnavailable(error))) return null;
  if (isLoading) return <Skeleton className="h-40 w-full" />;
  const cov = data?.coverage;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-medium text-muted-foreground flex flex-wrap items-center gap-2">
          Aegis file on {ticker}
          {data?.identity?.name ? <span className="text-xs font-normal">{data.identity.name}</span> : null}
          {data?.identity?.sector ? (
            <Badge variant="outline" className="text-[10px]">
              {data.identity.sector}
            </Badge>
          ) : null}
          {cov ? (
            <Badge
              variant="outline"
              className={`text-[10px] ${cov.status === "OK" ? "" : "text-amber-400 border-amber-500/40"}`}
            >
              index {cov.status} · built {ageLabel(cov.index_built_utc)}
            </Badge>
          ) : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {error && isNotBuilt(error) ? (
          <p className="text-xs text-muted-foreground">
            {ticker} is not in the issuer table, so this PC holds no file on it.
          </p>
        ) : (
          <ApiState error={error} what="ticker hub" />
        )}
        {cov?.detail ? <p className="text-xs text-amber-400">{cov.detail}</p> : null}
        {data ? (
          <>
            <div className="flex flex-wrap items-center gap-1">
              {TABS.map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTab(t)}
                  className={`rounded-md px-2.5 py-1 text-xs ${
                    tab === t ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {t}
                  {t === "News" ? ` (${data.coverage.n_rows})` : ""}
                  {t === "Forecasts" ? ` (${data.forecasts.counts.open + data.forecasts.counts.resolved})` : ""}
                  {t === "Calendar" ? ` (${data.calendar.rows.length})` : ""}
                  {t === "Related" ? ` (${data.related.length})` : ""}
                </button>
              ))}
              <select
                aria-label="window"
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
                className="ml-auto rounded-md border border-border bg-background px-1.5 py-0.5 text-xs"
              >
                {[7, 30, 90].map((d) => (
                  <option key={d} value={d}>
                    {d} days
                  </option>
                ))}
              </select>
            </div>
            {tab === "News" ? (
              <p className="text-[11px] text-muted-foreground">
                {data.coverage.n_rows} rows in {data.days} days
                {data.coverage.truncated ? ` (newest ${data.coverage.n_returned} shown)` : ""} · newest{" "}
                {fmtUtc(data.coverage.newest_utc)} · sources:{" "}
                {Object.entries(data.coverage.sources)
                  .map(([s, n]) => `${s} ${n}`)
                  .join(", ") || DASH}
              </p>
            ) : null}
            <Body data={data} tab={tab} />
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
