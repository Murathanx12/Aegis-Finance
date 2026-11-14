"use client";

/**
 * "Aegis file on <TICKER>" -- everything this PC holds on one ticker (CH-22):
 * our own collected news as distinct stories (every source, newest first, with both the
 * published and collected time when they differ, the number of copies, how each was
 * tagged and whether the headline is ABOUT the company or only mentions it), the frozen
 * forecasts (open and resolved, with outcome), the next calendar dates, related names
 * (with how they were ranked), and every source's age (dead ones in red).
 *
 * Desktop only: rendered only in the desktop build (`CONTROL_PLANE_BUILD`); there an
 * unreachable backend or a damaged index is SHOWN, never hidden. An absent field prints
 * the em dash, never a stand-in.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiState, DASH, ageLabel, fmtUtc } from "@/components/desktop/primitives";
import {
  CONTROL_PLANE_BUILD,
  errorText,
  getTickerHub,
  getTickerNews,
  isUnknownSymbol,
  type HubCoverage,
  type HubForecast,
  type HubNewsRow,
  type HubTier,
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
  text_token: "ticker symbol",
  name_match: "name match",
};

function num(v: number | null | undefined, digits = 2): string {
  return v == null || !Number.isFinite(v) ? DASH : v.toFixed(digits);
}

/** The index status line: red for DEGRADED (with each named problem), amber for STALE /
 *  NO_INDEX, and every source past its limit in red. Shared with the /news page. */
export function CoverageNotes({ cov }: { cov: HubCoverage | undefined }) {
  if (!cov) return null;
  const red = cov.status === "DEGRADED";
  return (
    <div className="space-y-1 text-xs">
      {cov.detail ? <p className={red ? "text-destructive font-medium" : "text-amber-400"}>{cov.detail}</p> : null}
      {red && cov.problems?.length ? (
        <ul className="list-disc pl-4 text-destructive">
          {cov.problems.map((p) => (
            <li key={p} className="font-mono">
              {p}
            </li>
          ))}
        </ul>
      ) : null}
      {cov.stale_sources?.length ? (
        <p className="text-destructive">
          sources with no new rows past their limit:{" "}
          {cov.stale_sources
            .map((s) => `${s.source}: no rows since ${s.newest_utc ? s.newest_utc.slice(0, 10) : DASH}`)
            .join(" · ")}
        </p>
      ) : null}
    </div>
  );
}

export function SourceAges({ cov }: { cov: HubCoverage | undefined }) {
  if (!cov?.sources?.length) return null;
  return (
    <details className="text-[11px]">
      <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
        newest row per source ({cov.sources.length} sources, {cov.stale_sources?.length ?? 0} stale)
      </summary>
      <ul className="mt-1 grid grid-cols-1 sm:grid-cols-2 gap-x-6">
        {cov.sources.map((s) => (
          <li key={s.source} className={s.stale ? "text-destructive" : "text-muted-foreground"}>
            <span className="font-mono">{s.source}</span> {fmtUtc(s.newest_utc)} (
            {s.age_hours == null ? DASH : `${s.age_hours} h`}, limit {s.limit_hours} h)
          </li>
        ))}
      </ul>
    </details>
  );
}

export function NewsRows({ rows, focus }: { rows: HubNewsRow[]; focus?: string }) {
  if (!rows.length) return <p className="text-sm text-muted-foreground">No stories in this window.</p>;
  return (
    <ul className="divide-y divide-border/30">
      {rows.map((r) => {
        const methods = r.tagged_by ?? Array.from(new Set(r.tags.map((t) => t.m)));
        const others = r.tags.map((t) => t.t).filter((t) => t !== focus);
        const when = r.eff_utc ?? r.first_seen_utc;
        return (
          <li key={r.id} className="py-2">
            <div className="flex flex-wrap items-baseline gap-x-2 text-xs text-muted-foreground">
              <span className="font-mono">{fmtUtc(when)}</span>
              {r.show_both_times ? (
                <span className="text-amber-400">(collected {fmtUtc(r.first_seen_utc)})</span>
              ) : null}
              <span>{r.publisher ?? DASH}</span>
              <span className="opacity-60">({r.source})</span>
              {r.copies && r.copies > 1 ? (
                <span title={(r.sources ?? []).join(", ")}>
                  · {r.copies} copies / {r.sources?.length ?? 1} sources
                </span>
              ) : null}
              {r.tier ? (
                <Badge variant="outline" className="text-[10px]">
                  {r.tier}
                </Badge>
              ) : null}
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
  const [shown, setShown] = useState(100);
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
          {rows.slice(0, shown).map((f, i) => (
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
      {rows.length > shown ? (
        <button
          type="button"
          className="mt-1 text-[11px] text-primary hover:underline"
          onClick={() => setShown((n) => n + 100)}
        >
          showing {shown} of {rows.length} — show 100 more
        </button>
      ) : null}
    </div>
  );
}

function NewsTab({ data, days, tier, setTier }: {
  data: TickerHubResponse;
  days: number;
  tier: HubTier;
  setTier: (t: HubTier) => void;
}) {
  const [extra, setExtra] = useState<HubNewsRow[]>([]);
  const [hasMore, setHasMore] = useState(data.coverage.has_more);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    setExtra([]);
    setHasMore(data.coverage.has_more);
    setErr(null);
  }, [data]);
  const rows = [...data.news, ...extra];
  const more = async () => {
    setLoading(true);
    setErr(null);
    try {
      const page = await getTickerNews(data.ticker, { days, tier, offset: rows.length, limit: 50 });
      setExtra((x) => [...x, ...page.news]);
      setHasMore(page.coverage.has_more);
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setLoading(false);
    }
  };
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
        <span>
          {data.coverage.n_stories} distinct stories ({data.coverage.n_rows} rows) in {data.days} days · newest{" "}
          {fmtUtc(data.coverage.newest_utc)}
        </span>
        <span className="ml-auto inline-flex rounded-md border border-border">
          {(["about", "all"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTier(t)}
              className={`px-2 py-0.5 ${tier === t ? "bg-primary/15 text-primary" : "hover:text-foreground"}`}
            >
              {t === "about" ? `about ${data.ticker} (${data.tier_counts.about} rows)` : `+ mentions (${data.tier_counts.all} rows)`}
            </button>
          ))}
        </span>
      </div>
      <NewsRows rows={rows} focus={data.ticker} />
      {err ? <p className="text-xs text-destructive">{err}</p> : null}
      {hasMore ? (
        <button
          type="button"
          disabled={loading}
          onClick={more}
          className="rounded-md bg-primary/15 px-2.5 py-1 text-xs text-primary disabled:opacity-50"
        >
          {loading ? "loading…" : `load more (${rows.length} of ${data.coverage.n_stories})`}
        </button>
      ) : null}
    </div>
  );
}

function Body({ data, tab, days, tier, setTier }: {
  data: TickerHubResponse;
  tab: Tab;
  days: number;
  tier: HubTier;
  setTier: (t: HubTier) => void;
}) {
  if (tab === "News") return <NewsTab data={data} days={days} tier={tier} setTier={setTier} />;
  if (tab === "Forecasts") {
    const c = data.forecasts.counts;
    return (
      <div className="space-y-4">
        {data.forecasts.status !== "OK" ? (
          <p className="text-xs text-destructive">forecasts: {data.forecasts.status}</p>
        ) : null}
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
    <div className="space-y-2">
      <p className="text-[11px] text-muted-foreground">
        Graph links are ranked by universe-graph weight; {data.related_rank}.
      </p>
      <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-sm">
        {data.related.map((r) => (
          <li key={`${r.ticker}-${r.link}`} className="flex gap-2">
            <Link href={`/stock/${r.ticker}`} className="font-mono hover:text-primary">
              {r.ticker}
            </Link>
            <span className="truncate">{r.name ?? DASH}</span>
            <span className="text-xs text-muted-foreground">
              {r.link}
              {r.link === "same_sector" ? ` · ${r.n ?? 0} co-mentions` : r.weight != null ? ` ${r.weight}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </div>
  ) : (
    <p className="text-sm text-muted-foreground">No related names on file.</p>
  );
}

export function AegisFileCard({ ticker }: { ticker: string }) {
  const [tab, setTab] = useState<Tab>("News");
  const [days, setDays] = useState(30);
  const [tier, setTier] = useState<HubTier>("about");
  const { data, error, isLoading } = useQuery({
    queryKey: ["ticker-hub", ticker, days, tier],
    queryFn: () => getTickerHub(ticker, days, tier),
    enabled: CONTROL_PLANE_BUILD && ticker.length > 0,
    retry: false,
    staleTime: 60_000,
  });
  if (!CONTROL_PLANE_BUILD || !ticker) return null;
  if (isLoading) return <Skeleton className="h-40 w-full" />;
  const cov = data?.coverage;
  const tone =
    cov?.status === "OK" ? "" : cov?.status === "DEGRADED" ? "text-destructive border-destructive/50" : "text-amber-400 border-amber-500/40";
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
            <Badge variant="outline" className={`text-[10px] ${tone}`}>
              index {cov.status} · built {ageLabel(cov.index_built_utc)}
            </Badge>
          ) : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {error && isUnknownSymbol(error) ? (
          <p className="text-xs text-muted-foreground">
            {ticker} is not in the issuer table, so this PC holds no file on it.
          </p>
        ) : (
          <ApiState error={error} what="ticker hub" />
        )}
        <CoverageNotes cov={cov} />
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
                  {t === "News" ? ` (${data.coverage.n_stories})` : ""}
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
            <Body data={data} tab={tab} days={days} tier={tier} setTier={setTier} />
            <SourceAges cov={cov} />
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
