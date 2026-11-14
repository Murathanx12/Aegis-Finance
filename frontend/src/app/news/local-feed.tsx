"use client";

/**
 * Our own collected news, filtered by ticker, sector and source, as distinct stories
 * (CH-22). Backed by `/api/control/news/feed`, which answers only on the desktop shell;
 * the card is rendered only in the desktop build (`CONTROL_PLANE_BUILD`), and there an
 * unreachable backend, a damaged index and dead sources are shown, in red.
 */

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ApiState, DASH, ageLabel, fmtUtc } from "@/components/desktop/primitives";
import { CONTROL_PLANE_BUILD, getNewsFeed, isUnknownSymbol, type HubTier } from "@/lib/control-api";
import { CoverageNotes, NewsRows, SourceAges } from "@/app/stock/[ticker]/aegis-file";

export function LocalNewsFeed() {
  const [tickerInput, setTickerInput] = useState("");
  const [ticker, setTicker] = useState("");
  const [sector, setSector] = useState("");
  const [source, setSource] = useState("");
  const [days, setDays] = useState(7);
  const [tier, setTier] = useState<HubTier>("about");
  const { data, error, isFetching } = useQuery({
    queryKey: ["news-feed", ticker, sector, source, days, tier],
    queryFn: () => getNewsFeed({ ticker, sector, source, days, limit: 200, tier }),
    enabled: CONTROL_PLANE_BUILD,
    retry: false,
    staleTime: 60_000,
  });
  if (!CONTROL_PLANE_BUILD) return null;
  const cov = data?.coverage;
  const tone =
    cov?.status === "OK" ? "" : cov?.status === "DEGRADED" ? "text-destructive border-destructive/50" : "text-amber-400 border-amber-500/40";
  const pickTicker = (t: string) => {
    setTickerInput(t);
    setTicker(t);
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-medium text-muted-foreground flex flex-wrap items-center gap-2">
          Our collected news
          {cov ? (
            <Badge variant="outline" className={`text-[10px] ${tone}`}>
              index {cov.status} · built {ageLabel(cov.index_built_utc)}
            </Badge>
          ) : null}
          {isFetching ? <span className="text-[11px] font-normal">loading…</span> : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <form
          className="flex flex-wrap items-center gap-2 text-xs"
          onSubmit={(e) => {
            e.preventDefault();
            setTicker(tickerInput.trim().toUpperCase());
          }}
        >
          <input
            aria-label="ticker"
            placeholder="ticker, e.g. NVDA"
            value={tickerInput}
            onChange={(e) => setTickerInput(e.target.value)}
            className="w-32 rounded-md border border-border bg-background px-2 py-1 font-mono uppercase"
          />
          <select
            aria-label="sector"
            value={sector}
            onChange={(e) => setSector(e.target.value)}
            className="rounded-md border border-border bg-background px-1.5 py-1"
          >
            <option value="">all sectors</option>
            {(data?.sectors ?? []).map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select
            aria-label="source"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="rounded-md border border-border bg-background px-1.5 py-1"
          >
            <option value="">all sources</option>
            {(data?.facets.source ?? []).map((s) => (
              <option key={s.key} value={s.key}>
                {s.key} ({s.n})
              </option>
            ))}
            {source && !(data?.facets.source ?? []).some((s) => s.key === source) ? (
              <option value={source}>{source}</option>
            ) : null}
          </select>
          <select
            aria-label="window"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-md border border-border bg-background px-1.5 py-1"
          >
            {[1, 7, 30, 90].map((d) => (
              <option key={d} value={d}>
                {d} days
              </option>
            ))}
          </select>
          <select
            aria-label="tier"
            value={tier}
            onChange={(e) => setTier(e.target.value as HubTier)}
            className="rounded-md border border-border bg-background px-1.5 py-1"
          >
            <option value="about">headline names the company</option>
            <option value="all">+ mentions</option>
          </select>
          <button type="submit" className="rounded-md bg-primary/15 px-2.5 py-1 text-primary">
            filter
          </button>
          {ticker || sector || source ? (
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground"
              onClick={() => {
                setTickerInput("");
                setTicker("");
                setSector("");
                setSource("");
              }}
            >
              clear
            </button>
          ) : null}
          {ticker ? (
            <Link href={`/stock/${ticker}`} className="ml-auto text-primary hover:underline">
              open the {ticker} file
            </Link>
          ) : null}
        </form>
        {error && isUnknownSymbol(error) ? (
          <p className="text-xs text-muted-foreground">{ticker} is not in the issuer table.</p>
        ) : (
          <ApiState error={error} what="news feed" />
        )}
        <CoverageNotes cov={cov} />
        {data ? (
          <>
            <div className="flex flex-wrap gap-1 text-[11px]">
              {data.facets.ticker.slice(0, 25).map((f) => (
                <button
                  key={f.key}
                  type="button"
                  title={f.name ?? undefined}
                  onClick={() => pickTicker(f.key)}
                  className={`rounded border px-1.5 py-0.5 font-mono ${
                    f.key === ticker ? "border-primary text-primary" : "border-border/50 hover:border-primary"
                  }`}
                >
                  {f.key} {f.n}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap gap-1 text-[11px] text-muted-foreground">
              {data.facets.sector.slice(0, 15).map((f) => (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => setSector(f.key)}
                  className={`rounded px-1.5 py-0.5 ${f.key === sector ? "text-primary" : "hover:text-foreground"}`}
                >
                  {f.key} {f.n}
                </button>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground">
              {data.n_rows} tagged rows in {data.days} days (facet counts are rows) · {data.n_returned} distinct
              stories shown{data.truncated ? ` from the newest ${data.n_rows_scanned} rows` : ""} · index built{" "}
              {fmtUtc(cov?.index_built_utc ?? null)} · untagged share at the last build{" "}
              {cov?.untagged_share_last_build == null
                ? DASH
                : `${(cov.untagged_share_last_build * 100).toFixed(0)}%`}{" "}
              (untagged rows are not listed here)
            </p>
            <NewsRows rows={data.rows} focus={data.filters.ticker ?? undefined} />
            <SourceAges cov={cov} />
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
