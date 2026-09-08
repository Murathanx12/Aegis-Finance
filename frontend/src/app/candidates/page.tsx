"use client";

/**
 * /candidates — the Mode A decision surface (roadmap H1).
 *
 * The machine's candidate list has existed as JSONL on disk since 2026-09-03
 * and has never had a screen. This is that screen: a dense, sortable list a
 * human can work from in the morning — name, why it is a candidate, the
 * analyst band beside our own estimate, the tracker status, and the vintage.
 *
 * Two design rules, both earned:
 *   - The VINTAGE is above the data, not in a footnote. A five-day-old
 *     candidate list rendered as if it were today's is worse than no list.
 *   - A whole-universe REFUSAL is shown as loudly as a number. The starved-seal
 *     incident happened because `d_catalyst` was unreadable on every candidate
 *     and nothing counted it.
 */

import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Clock,
  Filter,
  RefreshCw,
  Search,
  X,
} from "lucide-react";

import {
  getCandidateAllocator,
  getCandidateUniverse,
  getCandidateVintages,
  getCandidateWatchlist,
  type CandidateRow,
  type Vintage,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorCard } from "@/components/error-card";
import { cn } from "@/lib/utils";

const STALE_MS = 5 * 60 * 1000;
const PAGE = 50;

type Tab = "candidates" | "watchlist" | "allocator";

// ── formatting ─────────────────────────────────────────────────────────────

const pct = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined ? "--" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(digits)}%`;

const num = (v: number | null | undefined, digits = 2) =>
  v === null || v === undefined ? "--" : v.toFixed(digits);

const usd = (v: number | null | undefined) => {
  if (v === null || v === undefined) return "--";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
};

const VERDICT_STYLE: Record<string, string> = {
  admitted_shadow: "border-emerald-500/40 text-emerald-400 bg-emerald-500/10",
  sub_floor: "border-border text-muted-foreground bg-muted/40",
  toxic_ge_5: "border-red-500/40 text-red-400 bg-red-500/10",
  unreadable: "border-amber-500/40 text-amber-400 bg-amber-500/10",
  no_opinion: "border-border text-muted-foreground bg-muted/40",
};

const STATUS_STYLE: Record<string, string> = {
  STRONG_BUY: "border-emerald-500/50 text-emerald-300 bg-emerald-500/15",
  BUY: "border-emerald-500/30 text-emerald-400/90 bg-emerald-500/8",
  WATCH: "border-amber-500/30 text-amber-400 bg-amber-500/10",
  SELL: "border-red-500/30 text-red-400 bg-red-500/10",
};

function Pill({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide whitespace-nowrap",
        className,
      )}
    >
      {children}
    </span>
  );
}

// ── vintage ────────────────────────────────────────────────────────────────

function FreshnessPill({ v }: { v: Vintage }) {
  const tone =
    v.freshness === "FRESH"
      ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10"
      : v.freshness === "STALE"
        ? "border-amber-500/50 text-amber-300 bg-amber-500/15"
        : "border-border text-muted-foreground bg-muted/40";
  return (
    <Pill className={tone}>
      {v.freshness}
      {v.day ? ` · ${v.day}` : ""}
      {v.age_weekdays !== null && v.age_weekdays > 0 ? ` · ${v.age_weekdays}wd` : ""}
    </Pill>
  );
}

/**
 * The vintage strip. Everything on this page is a file with a date on it, and
 * this is where that date lives — above the data, never under it.
 */
function VintageStrip() {
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["candidates", "vintages"],
    queryFn: getCandidateVintages,
    staleTime: STALE_MS,
  });

  if (isLoading) return <Skeleton className="h-24 w-full" />;
  if (!data) return null;

  const stale = data.any_stale || data.worst_freshness !== "FRESH";
  const sources = Object.entries(data.sources);

  return (
    <Card
      className={cn(
        stale ? "border-amber-500/40 bg-amber-500/5" : "border-emerald-500/30 bg-emerald-500/5",
      )}
    >
      <CardContent className="p-3 md:p-4 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          {stale ? (
            <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0" />
          ) : (
            <Clock className="h-4 w-4 text-emerald-400 shrink-0" />
          )}
          <span
            className={cn(
              "text-sm font-semibold",
              stale ? "text-amber-300" : "text-emerald-300",
            )}
          >
            {stale ? "STALE VINTAGE" : "VINTAGE CURRENT"}
          </span>
          <span className="text-xs text-muted-foreground">
            as of {data.as_of_et} (ET) · fresh means at most{" "}
            {sources[0]?.[1]?.fresh_max_age_weekdays ?? 1} weekday behind
          </span>
          <button
            onClick={() => refetch()}
            className="ml-auto inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground"
          >
            <RefreshCw className={cn("h-3 w-3", isFetching && "animate-spin")} />
            reload
          </button>
        </div>

        <div className="flex flex-wrap gap-x-4 gap-y-1.5">
          {sources.map(([name, v]) => (
            <div key={name} className="flex items-center gap-1.5">
              <span className="text-[11px] text-muted-foreground">{name}</span>
              <FreshnessPill v={v} />
              {v.status !== "OK" && (
                <Pill className="border-red-500/40 text-red-400 bg-red-500/10">{v.status}</Pill>
              )}
            </div>
          ))}
        </div>

        {sources
          .filter(([, v]) => v.stale_reason)
          .slice(0, 2)
          .map(([name, v]) => (
            <p key={name} className="text-[11px] leading-relaxed text-amber-400/80">
              <span className="font-medium">{name}:</span> {v.stale_reason}
            </p>
          ))}

        {stale && (
          <details className="text-[11px] text-muted-foreground">
            <summary className="cursor-pointer hover:text-foreground">
              how to refresh
            </summary>
            <div className="mt-1 space-y-0.5 pl-3">
              {Object.entries(data.how_to_refresh).map(([k, cmd]) => (
                <div key={k}>
                  <span className="text-muted-foreground/70">{k}: </span>
                  <code className="rounded bg-muted px-1 py-0.5 text-[10px]">{cmd}</code>
                </div>
              ))}
            </div>
          </details>
        )}

        <p className="text-[10px] text-muted-foreground/70">{data.authority}</p>
      </CardContent>
    </Card>
  );
}

// ── the analyst band, drawn ────────────────────────────────────────────────

/**
 * low ──── mean ──── high, with today's close marked. The point of drawing it
 * is that a mean target alone hides a band that starts below the close.
 */
function BandBar({ row }: { row: CandidateRow }) {
  const { close, target_low: lo, target_mean: mid, target_high: hi } = row.band;
  if (close === null || lo === null || hi === null || hi <= lo) {
    return <span className="text-[11px] text-muted-foreground">--</span>;
  }
  const min = Math.min(lo, close);
  const max = Math.max(hi, close);
  const span = max - min || 1;
  const at = (v: number) => `${((v - min) / span) * 100}%`;
  return (
    <div className="w-32">
      <div className="relative h-1.5 rounded-full bg-muted">
        <div
          className="absolute h-full rounded-full bg-sky-500/35"
          style={{ left: at(lo), width: `${((hi - lo) / span) * 100}%` }}
        />
        {mid !== null && (
          <div
            className="absolute -top-[3px] h-[12px] w-[2px] rounded bg-sky-400"
            style={{ left: at(mid) }}
            title={`mean target ${mid}`}
          />
        )}
        <div
          className="absolute -top-[3px] h-[12px] w-[2px] rounded bg-foreground"
          style={{ left: at(close) }}
          title={`close ${close}`}
        />
      </div>
      <div className="mt-0.5 flex justify-between text-[9px] tabular-nums text-muted-foreground">
        <span>{num(lo)}</span>
        <span className="text-foreground/80">{num(close)}</span>
        <span>{num(hi)}</span>
      </div>
    </div>
  );
}

// ── filters ────────────────────────────────────────────────────────────────

type Filters = {
  verdict: string[];
  status: string[];
  sector: string;
  q: string;
  min_upside: string;
  min_p_beat: string;
  min_dollar_volume: string;
  disagreement_only: boolean;
  catalyst_readable_only: boolean;
};

const EMPTY: Filters = {
  verdict: [],
  status: [],
  sector: "",
  q: "",
  min_upside: "",
  min_p_beat: "",
  min_dollar_volume: "",
  disagreement_only: false,
  catalyst_readable_only: false,
};

function Chip({
  on,
  onClick,
  children,
  className,
}: {
  on: boolean;
  onClick: () => void;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "rounded border px-2 py-1 text-[11px] font-medium transition-colors",
        on
          ? "border-primary/50 bg-primary/15 text-primary"
          : "border-border text-muted-foreground hover:text-foreground",
        className,
      )}
    >
      {children}
    </button>
  );
}

// ── the candidate table ────────────────────────────────────────────────────

const COLUMNS: { key: string; label: string; sortable: boolean; className?: string }[] = [
  { key: "symbol", label: "Name", sortable: true },
  { key: "_why", label: "Why it is a candidate", sortable: false, className: "min-w-[240px]" },
  { key: "upside", label: "Analyst band vs close", sortable: true },
  { key: "p_beat", label: "Our estimate", sortable: true },
  { key: "_status", label: "Tracker", sortable: false },
  { key: "days_to_catalyst", label: "Catalyst", sortable: true },
  { key: "dollar_volume", label: "$ Vol/day", sortable: true },
];

function CandidatesTab() {
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [sort, setSort] = useState("upside");
  const [dir, setDir] = useState<"asc" | "desc">("desc");
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(true);

  const query = useMemo(
    () => ({
      verdict: filters.verdict.join(",") || undefined,
      status: filters.status.join(",") || undefined,
      sector: filters.sector || undefined,
      q: filters.q.trim().toUpperCase() || undefined,
      min_upside: filters.min_upside === "" ? undefined : Number(filters.min_upside) / 100,
      min_p_beat: filters.min_p_beat === "" ? undefined : Number(filters.min_p_beat) / 100,
      min_dollar_volume:
        filters.min_dollar_volume === "" ? undefined : Number(filters.min_dollar_volume) * 1e6,
      disagreement_only: filters.disagreement_only || undefined,
      catalyst_readable_only: filters.catalyst_readable_only || undefined,
      sort,
      dir,
      limit: PAGE,
      offset,
    }),
    [filters, sort, dir, offset],
  );

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["candidates", "universe", query],
    queryFn: () => getCandidateUniverse(query),
    staleTime: STALE_MS,
  });

  const setF = <K extends keyof Filters>(k: K, v: Filters[K]) => {
    setFilters((f) => ({ ...f, [k]: v }));
    setOffset(0);
  };
  const toggle = (k: "verdict" | "status", v: string) => {
    setFilters((f) => ({
      ...f,
      [k]: f[k].includes(v) ? f[k].filter((x) => x !== v) : [...f[k], v],
    }));
    setOffset(0);
  };
  const clickSort = (key: string) => {
    if (key === sort) setDir((d) => (d === "desc" ? "asc" : "desc"));
    else {
      setSort(key);
      setDir("desc");
    }
    setOffset(0);
  };

  if (error) return <ErrorCard message={(error as Error).message} onRetry={() => refetch()} />;

  const facets = data?.facets;
  const refusals = Object.entries(data?.whole_universe_refusals ?? {});
  const gaps = Object.entries(data?.field_readability ?? {}).filter(
    ([k, v]) => k !== "note" && (v?.unreadable ?? 0) > 0,
  );

  return (
    <div className="space-y-3">
      {/* The starved-seal sensor: a whole-universe refusal is a data gap, not a
          market opinion, and it belongs beside the list it silently emptied. */}
      {(refusals.length > 0 || gaps.length > 0) && (
        <Card className="border-amber-500/25 bg-amber-500/5">
          <CardContent className="p-3 space-y-1.5">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-300">
              Refusals on this vintage
            </p>
            {refusals.map(([name, r]) => (
              <p key={name} className="text-[11px] text-amber-400/80">
                <span className="font-medium">{name}</span>: refused on {r.refused_on ?? "?"}/
                {r.of ?? "?"} names — {r.reason ?? "no reason recorded"}
              </p>
            ))}
            {gaps.length > 0 && (
              <p className="text-[11px] text-amber-400/70">
                unreadable fields:{" "}
                {gaps
                  .map(([k, v]) => `${k} ${v.unreadable}/${(v.readable ?? 0) + (v.unreadable ?? 0)}`)
                  .join(" · ")}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-2 pb-2">
          <CardTitle className="text-sm">
            {isLoading ? (
              "Loading…"
            ) : (
              <>
                {data?.n_matched?.toLocaleString()} of {data?.n_scorecards?.toLocaleString()}{" "}
                scorecards
              </>
            )}
          </CardTitle>
          <button
            onClick={() => setShowFilters((s) => !s)}
            className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground"
          >
            <Filter className="h-3 w-3" />
            {showFilters ? "hide filters" : "filters"}
          </button>
        </CardHeader>

        {showFilters && (
          <CardContent className="space-y-2.5 border-t border-border pt-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="w-16 text-[10px] uppercase tracking-wide text-muted-foreground">
                Verdict
              </span>
              {(facets?.verdicts ?? []).map((v) => (
                <Chip key={v} on={filters.verdict.includes(v)} onClick={() => toggle("verdict", v)}>
                  {v}
                </Chip>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="w-16 text-[10px] uppercase tracking-wide text-muted-foreground">
                Tracker
              </span>
              {(facets?.statuses ?? []).map((v) => (
                <Chip key={v} on={filters.status.includes(v)} onClick={() => toggle("status", v)}>
                  {v}
                </Chip>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
                <input
                  value={filters.q}
                  onChange={(e) => setF("q", e.target.value)}
                  placeholder="symbol"
                  className="w-28 rounded border border-border bg-background py-1 pl-7 pr-2 text-[12px] outline-none focus:border-primary/50"
                />
              </div>
              <select
                value={filters.sector}
                onChange={(e) => setF("sector", e.target.value)}
                className="rounded border border-border bg-background px-2 py-1 text-[12px] outline-none focus:border-primary/50"
              >
                <option value="">all sectors</option>
                {(facets?.sectors ?? []).map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <label className="flex items-center gap-1 text-[11px] text-muted-foreground">
                upside ≥
                <input
                  type="number"
                  value={filters.min_upside}
                  onChange={(e) => setF("min_upside", e.target.value)}
                  className="w-16 rounded border border-border bg-background px-1.5 py-1 text-[12px] outline-none focus:border-primary/50"
                />
                %
              </label>
              <label className="flex items-center gap-1 text-[11px] text-muted-foreground">
                P(beat) ≥
                <input
                  type="number"
                  value={filters.min_p_beat}
                  onChange={(e) => setF("min_p_beat", e.target.value)}
                  className="w-16 rounded border border-border bg-background px-1.5 py-1 text-[12px] outline-none focus:border-primary/50"
                />
                %
              </label>
              <label className="flex items-center gap-1 text-[11px] text-muted-foreground">
                $vol ≥
                <input
                  type="number"
                  value={filters.min_dollar_volume}
                  onChange={(e) => setF("min_dollar_volume", e.target.value)}
                  className="w-16 rounded border border-border bg-background px-1.5 py-1 text-[12px] outline-none focus:border-primary/50"
                />
                M
              </label>
              <Chip
                on={filters.disagreement_only}
                onClick={() => setF("disagreement_only", !filters.disagreement_only)}
              >
                engine ≠ learner
              </Chip>
              <Chip
                on={filters.catalyst_readable_only}
                onClick={() => setF("catalyst_readable_only", !filters.catalyst_readable_only)}
              >
                catalyst readable
              </Chip>
              <button
                onClick={() => {
                  setFilters(EMPTY);
                  setOffset(0);
                }}
                className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
              >
                <X className="h-3 w-3" />
                reset
              </button>
            </div>
          </CardContent>
        )}
      </Card>

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="border-b border-border text-left text-[10px] uppercase tracking-wide text-muted-foreground">
                <th className="w-6" />
                {COLUMNS.map((c) => (
                  <th
                    key={c.key}
                    className={cn(
                      "px-2 py-2 font-medium",
                      c.sortable && "cursor-pointer select-none hover:text-foreground",
                      c.className,
                    )}
                    onClick={c.sortable ? () => clickSort(c.key) : undefined}
                  >
                    {c.label}
                    {sort === c.key && <span className="ml-1">{dir === "desc" ? "↓" : "↑"}</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading &&
                Array.from({ length: 12 }).map((_, i) => (
                  <tr key={i} className="border-b border-border/50">
                    <td colSpan={COLUMNS.length + 1} className="px-2 py-2">
                      <Skeleton className="h-5 w-full" />
                    </td>
                  </tr>
                ))}

              {!isLoading && data?.rows.length === 0 && (
                <tr>
                  <td
                    colSpan={COLUMNS.length + 1}
                    className="px-3 py-8 text-center text-muted-foreground"
                  >
                    No name in the {data.vintage.day ?? "current"} vintage matches these filters.
                  </td>
                </tr>
              )}

              {data?.rows.map((r) => {
                const est = r.our_estimate;
                const vs = est.p_beat.vs_base_rate;
                const expanded = open === r.symbol;
                return (
                  <React.Fragment key={r.symbol}>
                    <tr
                      className="cursor-pointer border-b border-border/50 hover:bg-muted/40"
                      onClick={() => setOpen(expanded ? null : r.symbol)}
                    >
                      <td className="px-1 text-muted-foreground">
                        {expanded ? (
                          <ChevronDown className="h-3.5 w-3.5" />
                        ) : (
                          <ChevronRight className="h-3.5 w-3.5" />
                        )}
                      </td>
                      <td className="px-2 py-1.5">
                        <div className="font-semibold">{r.symbol}</div>
                        <div className="truncate text-[10px] text-muted-foreground max-w-[130px]">
                          {r.sector ?? "--"}
                        </div>
                      </td>
                      <td className="px-2 py-1.5">
                        <div className="flex items-center gap-1.5">
                          <Pill
                            className={
                              VERDICT_STYLE[r.reason.verdict ?? ""] ??
                              "border-border text-muted-foreground"
                            }
                          >
                            {r.reason.verdict ?? "--"}
                          </Pill>
                          {r.disagreement.sign_disagreement && (
                            <Pill className="border-violet-500/40 text-violet-300 bg-violet-500/10">
                              disagree
                            </Pill>
                          )}
                          {r.execution.tier !== "FULL" && (
                            <Pill className="border-border text-muted-foreground">
                              {r.execution.tier}
                            </Pill>
                          )}
                        </div>
                        <div className="mt-0.5 line-clamp-2 max-w-[380px] text-[10.5px] leading-snug text-muted-foreground">
                          {r.reason.headline ??
                            r.reason.tracker_reasons[0] ??
                            "no reason recorded"}
                        </div>
                      </td>
                      <td className="px-2 py-1.5">
                        <div className="flex items-center gap-2">
                          <BandBar row={r} />
                          <span
                            className={cn(
                              "tabular-nums text-[11px]",
                              (r.band.upside ?? 0) > 0 ? "text-emerald-400" : "text-red-400",
                            )}
                          >
                            {pct(r.band.upside, 0)}
                          </span>
                        </div>
                        <div className="text-[9px] text-muted-foreground">
                          {r.band.n_analysts ?? "?"} analysts
                          {r.band.band_label ? ` · ${r.band.band_label}` : ""}
                        </div>
                      </td>
                      <td className="px-2 py-1.5">
                        {est.p_beat.debiased === null ? (
                          <span className="text-[10.5px] text-amber-400/80">
                            {est.learner_v1.status ?? "--"}
                          </span>
                        ) : (
                          <>
                            <div className="tabular-nums">{num(est.p_beat.debiased, 3)}</div>
                            <div
                              className={cn(
                                "text-[9.5px] tabular-nums",
                                (vs ?? 0) >= 0 ? "text-emerald-400/80" : "text-red-400/80",
                              )}
                            >
                              {vs === null ? "--" : `${(vs * 100).toFixed(1)}pp`} vs base{" "}
                              {num(est.p_beat.base_rate, 3)}
                            </div>
                          </>
                        )}
                      </td>
                      <td className="px-2 py-1.5">
                        {r.reason.tracker_status ? (
                          <Pill className={STATUS_STYLE[r.reason.tracker_status] ?? ""}>
                            {r.reason.tracker_status}
                          </Pill>
                        ) : (
                          <span className="text-[10px] text-muted-foreground">--</span>
                        )}
                      </td>
                      <td className="px-2 py-1.5 tabular-nums">
                        {r.days_to_catalyst.readable ? (
                          `${num(r.days_to_catalyst.value, 0)}d`
                        ) : (
                          <span className="text-amber-400/70">unreadable</span>
                        )}
                      </td>
                      <td className="px-2 py-1.5 tabular-nums text-muted-foreground">
                        {usd(r.execution.median_dollar_volume)}
                      </td>
                    </tr>

                    {expanded && (
                      <tr className="border-b border-border bg-muted/20">
                        <td />
                        <td colSpan={COLUMNS.length} className="px-2 py-3">
                          <div className="grid gap-4 md:grid-cols-3">
                            <div className="space-y-1">
                              <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
                                Engine
                              </p>
                              {r.reason.engine_reasons.map((x, i) => (
                                <p key={i} className="text-[11px] leading-snug">
                                  {x}
                                </p>
                              ))}
                              <p className="text-[11px] text-muted-foreground">
                                prior 1m {pct(r.our_estimate.engine_prior_1m, 2)} · ratio{" "}
                                {num(r.band.ratio, 3)}
                              </p>
                            </div>
                            <div className="space-y-1">
                              <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
                                Tracker
                              </p>
                              {r.reason.tracker_reasons.map((x, i) => (
                                <p key={i} className="text-[11px] leading-snug">
                                  {x}
                                </p>
                              ))}
                              {r.reason.tracker_blocked_by.map((x, i) => (
                                <p key={i} className="text-[11px] leading-snug text-amber-400/80">
                                  blocked: {x}
                                </p>
                              ))}
                              <p className="text-[11px] text-muted-foreground">
                                12m {pct(r.ret_12m, 0)} · dd60 {pct(r.drawdown_60d, 0)} · cap{" "}
                                {usd(r.market_cap_usd)}
                              </p>
                            </div>
                            <div className="space-y-1">
                              <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
                                Our model
                              </p>
                              <p className="text-[11px] leading-snug">
                                v1 {r.our_estimate.learner_v1.status}
                                {r.our_estimate.learner_v1.score !== null &&
                                  ` · ${num(r.our_estimate.learner_v1.score, 4)}`}
                              </p>
                              {r.our_estimate.learner_v1.reasons.map((x, i) => (
                                <p key={i} className="text-[11px] leading-snug text-amber-400/80">
                                  {x}
                                </p>
                              ))}
                              <p className="text-[11px] leading-snug text-muted-foreground">
                                v2 {r.our_estimate.learner_v2.status}: {r.our_estimate.learner_v2.reason}
                              </p>
                              <p className="text-[11px] leading-snug text-muted-foreground">
                                state {r.our_estimate.state.status}
                              </p>
                              {r.falsifiers.map((f, i) => (
                                <p key={i} className="text-[11px] leading-snug text-sky-400/80">
                                  if {f.field} {f.op} {f.value} → {f.then}
                                </p>
                              ))}
                              <p className="text-[11px]">
                                <Link
                                  href={`/stock/${r.symbol}`}
                                  className="text-primary hover:underline"
                                >
                                  open {r.symbol} →
                                </Link>
                              </p>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>

        {data && data.n_matched > PAGE && (
          <div className="flex items-center justify-between border-t border-border px-3 py-2 text-[11px] text-muted-foreground">
            <span>
              {offset + 1}–{Math.min(offset + PAGE, data.n_matched)} of{" "}
              {data.n_matched.toLocaleString()}
            </span>
            <div className="flex gap-2">
              <button
                disabled={offset === 0}
                onClick={() => setOffset((o) => Math.max(0, o - PAGE))}
                className="rounded border border-border px-2 py-1 disabled:opacity-40 hover:text-foreground"
              >
                prev
              </button>
              <button
                disabled={offset + PAGE >= data.n_matched}
                onClick={() => setOffset((o) => o + PAGE)}
                className="rounded border border-border px-2 py-1 disabled:opacity-40 hover:text-foreground"
              >
                next
              </button>
            </div>
          </div>
        )}
      </Card>

      {data?.conventions?.band_status ? (
        <p className="text-[10.5px] leading-relaxed text-muted-foreground">
          <span className="font-medium">Band caveat: </span>
          {String(data.conventions.band_status)}
        </p>
      ) : null}
    </div>
  );
}

// ── watchlist ──────────────────────────────────────────────────────────────

function WatchlistTab() {
  const [status, setStatus] = useState<string[]>([]);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["candidates", "watchlist", status],
    queryFn: () => getCandidateWatchlist({ status: status.join(",") || undefined, limit: 200 }),
    staleTime: STALE_MS,
  });

  if (error) return <ErrorCard message={(error as Error).message} onRetry={() => refetch()} />;
  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (!data) return null;

  if (data.vintage.status !== "OK") {
    return (
      <Card className="border-amber-500/30 bg-amber-500/5">
        <CardContent className="p-4">
          <p className="text-sm font-medium text-amber-300">
            Watchlist {data.vintage.status}
          </p>
          <p className="mt-1 text-xs text-amber-400/80">{data.vintage.stale_reason}</p>
          <p className="mt-2 text-[11px] text-muted-foreground">
            Source: <code className="rounded bg-muted px-1">{data.vintage.source}</code>
          </p>
        </CardContent>
      </Card>
    );
  }

  const hist = data.status_histogram ?? {};
  const total = Object.values(hist).reduce((a, b) => a + b, 0) || 1;

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">
            {data.n_symbols?.toLocaleString()} names screened ·{" "}
            {data.n_candidates?.toLocaleString()} candidates
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {(["STRONG_BUY", "BUY", "WATCH", "SELL"] as const).map((k) => (
            <button
              key={k}
              onClick={() =>
                setStatus((s) => (s.includes(k) ? s.filter((x) => x !== k) : [...s, k]))
              }
              className="flex w-full items-center gap-2 text-left"
            >
              <span
                className={cn(
                  "w-24 text-[11px] font-medium",
                  status.includes(k) ? "text-primary" : "text-muted-foreground",
                )}
              >
                {k}
              </span>
              <div className="h-3 flex-1 overflow-hidden rounded bg-muted">
                <div
                  className={cn(
                    "h-full rounded",
                    k === "STRONG_BUY"
                      ? "bg-emerald-400"
                      : k === "BUY"
                        ? "bg-emerald-500/60"
                        : k === "WATCH"
                          ? "bg-amber-500/60"
                          : "bg-red-500/60",
                  )}
                  style={{ width: `${((hist[k] ?? 0) / total) * 100}%` }}
                />
              </div>
              <span className="w-14 text-right text-[11px] tabular-nums text-muted-foreground">
                {(hist[k] ?? 0).toLocaleString()}
              </span>
            </button>
          ))}
          <p className="text-[10px] text-muted-foreground/70">
            Click a bar to filter the list. The histogram is the tracker&apos;s own
            screen, not a recommendation.
          </p>
        </CardContent>
      </Card>

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="border-b border-border text-left text-[10px] uppercase tracking-wide text-muted-foreground">
                <th className="px-2 py-2">Name</th>
                <th className="px-2 py-2">Status</th>
                <th className="px-2 py-2">Why</th>
                <th className="px-2 py-2 text-right">Upside</th>
                <th className="px-2 py-2 text-right">Consensus</th>
                <th className="px-2 py-2 text-right">Catalyst</th>
                <th className="px-2 py-2 text-right">$ Vol/day</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.symbol} className="border-b border-border/50 hover:bg-muted/40">
                  <td className="px-2 py-1.5">
                    <Link href={`/stock/${r.symbol}`} className="font-semibold hover:underline">
                      {r.symbol}
                    </Link>
                    <div className="truncate text-[10px] text-muted-foreground max-w-[130px]">
                      {r.sector ?? "--"}
                    </div>
                  </td>
                  <td className="px-2 py-1.5">
                    <Pill className={STATUS_STYLE[r.status ?? ""] ?? ""}>{r.status ?? "--"}</Pill>
                  </td>
                  <td className="max-w-[380px] px-2 py-1.5 text-[10.5px] leading-snug text-muted-foreground">
                    {(r.status_reasons ?? []).join(" · ") || "--"}
                    {(r.status_blocked_by ?? []).length > 0 && (
                      <div className="text-amber-400/80">
                        blocked: {(r.status_blocked_by ?? []).join(" · ")}
                      </div>
                    )}
                  </td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{pct(r.upside, 0)}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{num(r.consensus)}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">
                    {r.days_to_catalyst === undefined || r.days_to_catalyst === null
                      ? "--"
                      : `${r.days_to_catalyst}d`}
                  </td>
                  <td className="px-2 py-1.5 text-right tabular-nums text-muted-foreground">
                    {usd(r.median_dollar_volume)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

// ── allocator ──────────────────────────────────────────────────────────────

function AllocatorTab() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["candidates", "allocator"],
    queryFn: () => getCandidateAllocator(),
    staleTime: STALE_MS,
  });
  const [personality, setPersonality] = useState<string | null>(null);

  if (error) return <ErrorCard message={(error as Error).message} onRetry={() => refetch()} />;
  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (!data) return null;

  if (data.vintage.status !== "OK") {
    return (
      <Card className="border-amber-500/30 bg-amber-500/5">
        <CardContent className="p-4 text-xs text-amber-400/90">
          {data.vintage.stale_reason}
        </CardContent>
      </Card>
    );
  }

  const active = personality ?? data.personalities[0];
  const art = data.artifacts[active];
  const sleeves = (art?.allocations ?? []) as {
    sleeve: string;
    gate?: string;
    weight?: number;
    binding_constraint?: string;
    utility?: number;
  }[];

  return (
    <div className="space-y-3">
      <Card className="border-border">
        <CardContent className="p-3 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            {data.personalities.map((p) => (
              <Chip key={p} on={p === active} onClick={() => setPersonality(p)}>
                {p}
              </Chip>
            ))}
          </div>
          <p className="text-[11px] font-medium text-amber-300">{art?.authority}</p>
          <p className="text-[10px] text-muted-foreground">
            {art?.version} · licence {art?.licence} · day {art?.day}
          </p>
        </CardContent>
      </Card>

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="border-b border-border text-left text-[10px] uppercase tracking-wide text-muted-foreground">
                <th className="px-2 py-2">Sleeve</th>
                <th className="px-2 py-2">Gate</th>
                <th className="px-2 py-2 text-right">Weight</th>
                <th className="px-2 py-2">Binding constraint</th>
              </tr>
            </thead>
            <tbody>
              {sleeves.map((s) => (
                <tr key={s.sleeve} className="border-b border-border/50">
                  <td className="px-2 py-1.5 font-medium">{s.sleeve}</td>
                  <td className="px-2 py-1.5">
                    <Pill
                      className={
                        s.gate === "DEPLOYABLE"
                          ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10"
                          : "border-border text-muted-foreground"
                      }
                    >
                      {s.gate ?? "--"}
                    </Pill>
                  </td>
                  <td className="px-2 py-1.5 text-right tabular-nums">
                    {s.weight === undefined ? "--" : `${(s.weight * 100).toFixed(1)}%`}
                  </td>
                  <td className="px-2 py-1.5 text-[10.5px] leading-snug text-muted-foreground">
                    {s.binding_constraint ?? "--"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

// ── page ───────────────────────────────────────────────────────────────────

export default function CandidatesPage() {
  const [tab, setTab] = useState<Tab>("candidates");

  return (
    <div className="mx-auto max-w-[1600px] space-y-4 p-4 md:p-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Candidates</h1>
        <p className="mt-1 text-xs text-muted-foreground">
          What the machine is looking at, with the reason attached. Read-only: this page
          serves artefacts already on disk and places nothing.
        </p>
      </div>

      <VintageStrip />

      <div className="flex gap-1 border-b border-border">
        {(
          [
            ["candidates", "Candidate list"],
            ["watchlist", "Watchlist"],
            ["allocator", "Allocator"],
          ] as [Tab, string][]
        ).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-[13px] font-medium transition-colors",
              tab === k
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "candidates" && <CandidatesTab />}
      {tab === "watchlist" && <WatchlistTab />}
      {tab === "allocator" && <AllocatorTab />}
    </div>
  );
}
