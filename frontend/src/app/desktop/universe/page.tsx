"use client";

import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiState, DASH, RawPayload } from "@/components/desktop/primitives";
import { getUniverse, type UniverseResponse, type UniverseRow } from "@/lib/control-api";

/**
 * THE UNIVERSE, UNCAPPED (O8).
 *
 * Murat, 2026-09-11: "I want it to show all the stocks — first time I opened I
 * saw the 3,000+, and all of our reviews + analyst reviews."
 *
 * The header prints `rows shown / rows in universe` and BOTH numbers come from
 * the same file on the same request, so a page that has quietly lost 2,900
 * names cannot look complete. Search and sort are SERVER-side across the whole
 * set — a client-side filter over one page would search 100 names and look like
 * it searched three thousand.
 *
 * Every cell is a measured value or an em dash. `last_event` is em dashes on
 * purpose until lane L2 lands; `last_review` is a sentence WE wrote, shown with
 * the receipt it came from and nothing else.
 */

const PAGE = 100;

const SORTS: { key: string; label: string }[] = [
  { key: "upside", label: "Upside" },
  { key: "p_beat", label: "P(beat)" },
  { key: "consensus", label: "Consensus" },
  { key: "dollar_volume", label: "$ volume" },
  { key: "market_cap", label: "Market cap" },
  { key: "ret_12m", label: "12m return" },
  { key: "symbol", label: "Symbol" },
];

function pct(v: number | null | undefined, digits = 1): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  return `${(v * 100).toFixed(digits)}%`;
}

function num(v: number | null | undefined, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  return v.toFixed(digits);
}

function money(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${Math.round(v)}`;
}

function Row({ r }: { r: UniverseRow }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr
        className="border-b border-border/50 hover:bg-muted/40 cursor-pointer"
        onClick={() => setOpen((o) => !o)}
      >
        <td className="py-1.5 pr-3 font-mono font-medium">
          <Link
            href={`/stock/${encodeURIComponent(r.symbol)}`}
            className="hover:underline"
            onClick={(e) => e.stopPropagation()}
          >
            {r.symbol}
          </Link>
        </td>
        <td className="py-1.5 pr-3 text-muted-foreground max-w-[14rem] truncate">
          {r.sector ?? DASH}
        </td>
        <td className="py-1.5 pr-3 text-right tabular-nums">{pct(r.upside)}</td>
        <td className="py-1.5 pr-3 text-right tabular-nums">{num(r.consensus_tracker)}</td>
        <td className="py-1.5 pr-3 text-right tabular-nums">{r.n_analysts ?? DASH}</td>
        <td className="py-1.5 pr-3 text-right tabular-nums">{num(r.p_beat, 3)}</td>
        <td className="py-1.5 pr-3 text-right tabular-nums">{money(r.median_dollar_volume)}</td>
        <td className="py-1.5 pr-3 text-right tabular-nums">{money(r.market_cap_usd)}</td>
        <td className="py-1.5 pr-3">
          {r.books.length === 0 ? (
            <span className="text-muted-foreground">{DASH}</span>
          ) : (
            <span className="flex flex-wrap gap-1">
              {r.books.map((b) => (
                <Badge key={b} variant="outline" className="text-[10px]">
                  {b}
                </Badge>
              ))}
            </span>
          )}
        </td>
        <td className="py-1.5 pr-3 text-muted-foreground">{r.last_event ?? DASH}</td>
        <td className="py-1.5 max-w-[22rem] truncate text-muted-foreground">
          {r.last_review?.sentence ?? DASH}
        </td>
      </tr>
      {open && (
        <tr className="border-b border-border/50 bg-muted/20">
          <td colSpan={11} className="px-3 py-2 text-xs space-y-1">
            <div>
              <span className="text-muted-foreground">engine verdict: </span>
              {r.verdict ?? DASH}
              <span className="text-muted-foreground"> · tracker status: </span>
              {r.tracker_status ?? DASH}
              <span className="text-muted-foreground"> · execution tier: </span>
              {r.execution_tier ?? DASH}
              <span className="text-muted-foreground"> · 12m return: </span>
              {pct(r.ret_12m)}
            </div>
            <div>
              <span className="text-muted-foreground">
                consensus ({r.consensus_scale}):{" "}
              </span>
              {num(r.consensus_tracker)}
              {r.analyst_snapshot ? (
                <>
                  <span className="text-muted-foreground">
                    {" "}
                    · snapshot ({r.analyst_snapshot.scale}):{" "}
                  </span>
                  {num(r.analyst_snapshot.consensus_rating)}{" "}
                  {r.analyst_snapshot.consensus_label ?? ""}
                  <span className="text-muted-foreground"> · target mean: </span>
                  {r.analyst_snapshot.target_mean != null
                    ? `$${r.analyst_snapshot.target_mean.toFixed(2)}`
                    : DASH}
                  <span className="text-muted-foreground">
                    {" "}
                    · {r.analyst_snapshot.source}
                  </span>
                </>
              ) : (
                <span className="text-muted-foreground">
                  {" "}
                  · no local analyst snapshot for this name
                </span>
              )}
            </div>
            {r.last_review ? (
              <div>
                <span className="text-muted-foreground">our last review: </span>
                {r.last_review.sentence}
                <span className="block font-mono text-[10px] text-muted-foreground">
                  {r.last_review.receipt}
                </span>
              </div>
            ) : (
              <div className="text-muted-foreground">
                no receipt in the indexed nights mentions this symbol
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

export default function UniversePage() {
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("upside");
  const [dir, setDir] = useState<"asc" | "desc">("desc");

  const { data, isLoading, error, refetch, isFetching } = useQuery<UniverseResponse>({
    queryKey: ["control", "universe", offset, q, sort, dir],
    queryFn: () => getUniverse({ offset, limit: PAGE, q: q || undefined, sort, dir }),
    // The previous page stays on screen while the next one loads, so paging
    // does not flash the whole table back to skeletons.
    placeholderData: keepPreviousData,
  });

  const total = data?.universe_rows ?? null;
  const matched = data?.n_matched ?? null;
  const shown = data?.rows_shown ?? 0;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="text-base">The universe</CardTitle>
            <p className="text-xs text-muted-foreground">
              {/* rows shown / rows in the file — the two numbers this page exists
                  to keep equal. Both come from the same request. */}
              {data
                ? `showing ${offset + 1}–${offset + shown} of ${matched} matched · ${total} rows in the universe`
                : DASH}
            </p>
            {data?.universe_source && (
              <p className="font-mono text-[10px] text-muted-foreground">
                {data.universe_source}
                {data.universe_day ? ` · vintage ${data.universe_day}` : ""}
              </p>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  setQ(query.trim());
                  setOffset(0);
                }
              }}
              placeholder="symbol contains…"
              aria-label="Search symbols across the whole universe"
              className="h-8 w-44 rounded-md border border-border bg-background px-2 text-sm"
            />
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                setQ(query.trim());
                setOffset(0);
              }}
            >
              Search
            </Button>
            <select
              value={sort}
              onChange={(e) => {
                setSort(e.target.value);
                setOffset(0);
              }}
              aria-label="Sort by"
              className="h-8 rounded-md border border-border bg-background px-2 text-sm"
            >
              {SORTS.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </select>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setDir((d) => (d === "desc" ? "asc" : "desc"));
                setOffset(0);
              }}
            >
              {dir === "desc" ? "↓" : "↑"}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {error ? (
            <div className="space-y-2">
              <ApiState error={error} what="the universe" />
              <Button size="sm" variant="outline" onClick={() => refetch()}>
                Retry
              </Button>
            </div>
          ) : isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 12 }).map((_, i) => (
                <Skeleton key={i} className="h-7 w-full" />
              ))}
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-xs" aria-label="Universe table">
                  <thead>
                    <tr className="border-b border-border text-left text-muted-foreground">
                      <th className="py-1.5 pr-3 font-medium">Symbol</th>
                      <th className="py-1.5 pr-3 font-medium">Sector</th>
                      <th className="py-1.5 pr-3 font-medium text-right">Upside</th>
                      <th className="py-1.5 pr-3 font-medium text-right">Cons.</th>
                      <th className="py-1.5 pr-3 font-medium text-right">Anl.</th>
                      <th className="py-1.5 pr-3 font-medium text-right">P(beat)</th>
                      <th className="py-1.5 pr-3 font-medium text-right">$ vol</th>
                      <th className="py-1.5 pr-3 font-medium text-right">Mkt cap</th>
                      <th className="py-1.5 pr-3 font-medium">Books</th>
                      <th className="py-1.5 pr-3 font-medium">Last event</th>
                      <th className="py-1.5 font-medium">Our last review</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data?.rows ?? []).map((r) => (
                      <Row key={r.symbol} r={r} />
                    ))}
                  </tbody>
                </table>
              </div>
              {shown === 0 && (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  no name in the universe matches {q ? `"${q}"` : "this filter"}
                </p>
              )}
              <div className="mt-3 flex items-center justify-between">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={offset === 0 || isFetching}
                  onClick={() => setOffset((o) => Math.max(0, o - PAGE))}
                >
                  Previous
                </Button>
                <span className="text-xs text-muted-foreground">
                  {matched != null && total != null
                    ? `${matched} matched of ${total} in the universe`
                    : DASH}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={isFetching || matched == null || offset + PAGE >= matched}
                  onClick={() => setOffset((o) => o + PAGE)}
                >
                  Next
                </Button>
              </div>
              <p className="mt-3 text-[11px] text-muted-foreground">
                Consensus is on the tracker&apos;s 5 = STRONG BUY scale; the local
                analyst snapshot in the expanded row is on Yahoo&apos;s 1 = STRONG
                BUY scale, which runs the other way. Both are labelled with their
                scale because a page that prints 1.3 beside 4.2 without saying
                which way is up has published two numbers and no fact. &ldquo;Last
                event&rdquo; is an em dash for every name until lane L2 lands.
              </p>
            </>
          )}
          {data && <RawPayload data={data} />}
        </CardContent>
      </Card>
    </div>
  );
}
