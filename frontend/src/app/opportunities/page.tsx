"use client";

/**
 * /opportunities — the Opportunity Explorer (chunk C4, 2026-10-06).
 *
 * The owner's review of the 2026-09-27 stock-list PDF, in his column order:
 *   1 ticker · 2 weight · 3 sector · 4 price vs analyst targets (low / median / high)
 *   5 why the engine picked it (named services) · 6 dates and news
 *   7-8 insiders, holders, anything else the reader can use.
 *
 * Three rules this page keeps, each one from that review:
 *  - MoveScore (MAGNITUDE) and Direction are separate columns, and a list sorted
 *    by move size is labelled "MAGNITUDE RANKING: not a long list" at the top.
 *  - A foreign ticker shows the company, the exchange and a link, never a bare code.
 *  - A missing field shows WHY it is missing (`missing_because`), never a guess.
 *
 * Read-only: GET /api/opportunities/latest and /api/opportunities/{list_id}.
 */

import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle, ArrowDown, ArrowUp, ArrowUpDown, ChevronDown, ChevronRight,
  Compass, ExternalLink, Info, Rocket,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  getOpportunitiesLatest, getOpportunitiesList,
  type OppRow, type OppListMeta, type OpportunitiesResponse,
} from "@/lib/api";

// ───────────────────────────── formatting ─────────────────────────────

function pct(v: number | null | undefined, digits = 0, signed = false): string {
  if (v == null || Number.isNaN(v)) return "—";
  const s = (100 * v).toFixed(digits);
  return `${signed && v > 0 ? "+" : ""}${s}%`;
}

function money(v: number | null | undefined, cur?: string | null): string {
  if (v == null) return "—";
  const digits = v >= 1000 ? 0 : 2;
  const s = v.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return cur && cur !== "USD" ? `${s} ${cur}` : `$${s}`;
}

function usd(v: number | null | undefined): string {
  if (v == null) return "—";
  const a = Math.abs(v);
  if (a >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `$${(v / 1e3).toFixed(0)}k`;
  return `$${v.toFixed(0)}`;
}

function day(s: string | null | undefined): string {
  return s ? String(s).slice(0, 10) : "—";
}

/** A missing value, with its reason on hover — never an empty cell. */
function Missing({ why }: { why?: string }) {
  return (
    <span className="text-muted-foreground/70 italic cursor-help" title={why ?? "no receipt"}>
      n/a
    </span>
  );
}

function ExtLink({ href, children, className = "" }: { href: string; children: React.ReactNode; className?: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      onClick={(e) => e.stopPropagation()}
      className={`inline-flex items-center gap-1 text-sky-700 dark:text-sky-400 hover:underline ${className}`}
    >
      {children}
      <ExternalLink className="h-3 w-3 shrink-0" />
    </a>
  );
}

// ───────────────────────────── cells ─────────────────────────────

const DIR_TONE: Record<string, string> = {
  UP: "bg-emerald-600/15 text-emerald-700 dark:text-emerald-400 border-emerald-600/30",
  DOWN: "bg-red-600/15 text-red-700 dark:text-red-400 border-red-600/30",
  NEUTRAL: "bg-zinc-500/10 text-zinc-700 dark:text-zinc-300 border-zinc-500/30",
  MIXED: "bg-amber-500/15 text-amber-800 dark:text-amber-300 border-amber-500/30",
};

function DirectionCell({ r }: { r: OppRow }) {
  const d = r.direction;
  if (!d) return <Missing why={r.missing_because.direction} />;
  const tip = [
    d.consensus ? `consensus: ${d.consensus}` : "no consensus rating",
    d.revision_sign == null ? "no 90-day revisions" :
      `revisions: ${r.revision?.net_raises_90d ?? 0} net raises (${r.revision?.n_firms_90d ?? 0} firms)`,
    d.single_source ? "single source" : "",
  ].filter(Boolean).join(" · ");
  return (
    <span title={tip}>
      <Badge className={DIR_TONE[d.label] ?? DIR_TONE.NEUTRAL}>{d.label}</Badge>
      {d.single_source && <span className="ml-1 text-[10px] text-muted-foreground">1 src</span>}
    </span>
  );
}

function MoveCell({ r }: { r: OppRow }) {
  const m = r.move_score;
  if (!m) return <Missing why={r.missing_because.move_score} />;
  const w = Math.min(100, (m.expected_abs_move_21s / 0.3) * 100);
  return (
    <div className="min-w-[72px]" title={`±${pct(m.expected_abs_move_21s, 1)} expected size of the move over 21 sessions (bars to ${m.bars_to}). Magnitude only.`}>
      <span className="tabular-nums">±{pct(m.expected_abs_move_21s, 1)}</span>
      <div className="mt-1 h-1 rounded bg-muted">
        <div className="h-1 rounded bg-violet-500/70" style={{ width: `${w}%` }} />
      </div>
    </div>
  );
}

/** Price against the analysts' low / median / high, as one readable strip. */
function TargetCell({ r }: { r: OppRow }) {
  const a = r.analyst;
  const p = r.price;
  if (!a) {
    return (
      <div className="text-xs">
        <div className="tabular-nums font-medium">{p ? money(p.value, p.currency) : "—"}</div>
        <Missing why={r.missing_because.analyst} />
      </div>
    );
  }
  const lo = a.low, hi = a.high, med = a.median;
  const px = p?.value ?? a.snapshot_price;
  const vals = [lo, hi, med, px].filter((x): x is number => x != null);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const at = (v: number) => `${((v - min) / span) * 100}%`;
  const up = r.upside;
  const medUp = up?.median;
  return (
    <div className="min-w-[180px] text-xs">
      <div className="flex items-baseline justify-between gap-2">
        <span className="tabular-nums font-medium">{p ? money(p.value, p.currency) : "—"}</span>
        <span
          className={`tabular-nums font-semibold ${medUp == null ? "" : medUp >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400"}`}
          title={up ? `upside to the median target, ${up.basis}` : r.missing_because.upside}
        >
          {medUp == null ? "—" : `${pct(medUp, 0, true)} to median`}
        </span>
      </div>
      {lo != null && hi != null && (
        <div className="relative my-1.5 h-2 rounded bg-muted" aria-hidden>
          <div className="absolute top-0 h-2 rounded bg-sky-500/25" style={{ left: at(lo), width: `calc(${at(hi)} - ${at(lo)})` }} />
          {med != null && <div className="absolute -top-0.5 h-3 w-0.5 bg-sky-600 dark:bg-sky-400" style={{ left: at(med) }} />}
          {px != null && <div className="absolute -top-1 h-4 w-1 rounded bg-foreground" style={{ left: at(px) }} title="last price" />}
        </div>
      )}
      <div className="flex justify-between tabular-nums text-muted-foreground">
        <span title="lowest target">L {money(lo, p?.currency)}</span>
        <span title="median target">M {money(med, p?.currency)}</span>
        <span title="highest target">H {money(hi, p?.currency)}</span>
      </div>
      <div className="text-[10px] text-muted-foreground">
        {a.n != null ? `${a.n} analysts` : "analyst count n/a"}
        {a.consensus ? ` · ${a.consensus.replace(/_/g, " ")}` : ""}
      </div>
    </div>
  );
}

function TickerCell({ r }: { r: OppRow }) {
  return (
    <div className="min-w-[150px]">
      <div className="flex items-center gap-1.5 flex-wrap">
        <ExtLink href={r.links.yahoo ?? "#"} className="font-mono font-semibold text-foreground dark:text-foreground">
          {r.ticker}
        </ExtLink>
        {r.lane === "HIGH_RISK_INNOVATION" && (
          <Badge className="bg-fuchsia-600/15 text-fuchsia-700 dark:text-fuchsia-300 border-fuchsia-600/30" title={r.risk_flags.join(" · ")}>
            <Rocket className="h-3 w-3" /> High-Risk Innovation
          </Badge>
        )}
        {r.lane === "BENCHMARK" && <Badge variant="outline">benchmark</Badge>}
        {r.eligibility?.startsWith("EXCLUDED") && (
          <Badge className="bg-zinc-500/15 text-zinc-700 dark:text-zinc-300 border-zinc-500/30" title="excluded by the v3.2 eligibility rule; shown, not hidden">
            excluded
          </Badge>
        )}
      </div>
      <div className="text-xs text-foreground/80 leading-tight mt-0.5" title={r.company_name_source ?? ""}>
        {r.company_name ?? <Missing why={r.missing_because.company_name} />}
      </div>
      <div className="text-[10px] text-muted-foreground">
        {r.exchange ?? "exchange n/a"}
        {r.is_foreign && r.currency ? ` · ${r.currency}` : ""}
      </div>
    </div>
  );
}

function nextCatalyst(r: OppRow) {
  return r.catalysts.length ? r.catalysts[0] : null;
}

function insiderNet(r: OppRow): number | null {
  return r.insiders ? r.insiders.buy_usd - r.insiders.sell_usd : null;
}

// ───────────────────────────── expanded row ─────────────────────────────

function Detail({ r }: { r: OppRow }) {
  const linkRow: [string, string | null | undefined][] = [
    ["Yahoo quote", r.links.yahoo],
    ["Yahoo analysts", r.links.yahoo_analysts],
    ["MarketWatch", r.links.marketwatch],
    ["MarketWatch analysts", r.links.marketwatch_analysts],
    ["Benzinga", r.links.benzinga],
    ["SEC EDGAR", r.links.edgar],
  ];
  return (
    <div className="grid gap-4 p-4 md:grid-cols-2 xl:grid-cols-3 text-sm bg-muted/30">
      <section>
        <h4 className="text-xs uppercase tracking-wide text-muted-foreground mb-1.5">Why the engine picked it</h4>
        {r.why_picked.length ? (
          <ul className="space-y-2">
            {r.why_picked.map((w, i) => (
              <li key={i}>
                <p>{w.reason}</p>
                <p className="text-[11px] text-muted-foreground">service: {w.service}</p>
              </li>
            ))}
          </ul>
        ) : <Missing why={r.missing_because.why_picked} />}
        <h4 className="text-xs uppercase tracking-wide text-muted-foreground mt-3 mb-1">What would prove it wrong</h4>
        <p>{r.falsifier ?? <Missing why={r.missing_because.falsifier} />}</p>
        <p className="mt-2 text-xs text-muted-foreground">
          Horizon: {r.horizon ?? "none declared"} · Evidence: <b>{r.evidence.label}</b>
          {r.evidence.sessions != null ? ` (${r.evidence.sessions} sessions)` : ""} — {r.evidence.note}
        </p>
        {r.risk_flags.length > 0 && (
          <p className="mt-2 text-xs text-fuchsia-700 dark:text-fuchsia-300">Risk flags: {r.risk_flags.join(" · ")}</p>
        )}
      </section>

      <section>
        <h4 className="text-xs uppercase tracking-wide text-muted-foreground mb-1.5">Dates</h4>
        {r.catalysts.length ? (
          <ul className="space-y-1.5">
            {r.catalysts.map((c, i) => (
              <li key={i}>
                <span className="font-mono tabular-nums">{c.date}</span>{" "}
                <span className="font-medium">{c.kind}</span>
                {c.detail ? <span className="text-muted-foreground"> — {c.detail}</span> : null}
                {c.url && <> {" "}<ExtLink href={c.url}>source</ExtLink></>}
                <div className="text-[11px] text-muted-foreground">{c.source}</div>
              </li>
            ))}
          </ul>
        ) : <Missing why={r.missing_because.catalysts} />}
        <h4 className="text-xs uppercase tracking-wide text-muted-foreground mt-3 mb-1.5">News</h4>
        {r.news.length ? (
          <ul className="space-y-1.5">
            {r.news.map((n, i) => (
              <li key={i}>
                <ExtLink href={n.url}>{n.title || n.url}</ExtLink>
                <div className="text-[11px] text-muted-foreground">
                  {day(n.published_utc ?? n.first_seen_utc)} · {n.source}
                </div>
              </li>
            ))}
          </ul>
        ) : <Missing why={r.missing_because.news} />}
      </section>

      <section>
        <h4 className="text-xs uppercase tracking-wide text-muted-foreground mb-1.5">Insiders (SEC Form 4, open market)</h4>
        {r.insiders ? (
          <>
            <p className="tabular-nums">
              {r.insiders.n_buys} buys ({usd(r.insiders.buy_usd)}) · {r.insiders.n_sells} sells ({usd(r.insiders.sell_usd)})
              · {r.insiders.n_insiders} people · {r.insiders.n_10b5_1} under a 10b5-1 plan · last {r.insiders.window_days} days
            </p>
            <ul className="mt-1 space-y-1 text-xs">
              {r.insiders.recent.map((t, i) => (
                <li key={i}>
                  <span className={t.side === "BUY" ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400"}>{t.side}</span>{" "}
                  {t.owner} ({t.role}) · {usd(t.value_usd)} · traded {day(t.transaction_date)}
                  {t.rule_10b5_1 ? " · 10b5-1" : ""}
                  {t.url && <> {" "}<ExtLink href={t.url}>filing</ExtLink></>}
                </li>
              ))}
            </ul>
          </>
        ) : <Missing why={r.missing_because.insiders} />}
        <h4 className="text-xs uppercase tracking-wide text-muted-foreground mt-3 mb-1">Short interest (FINRA)</h4>
        {r.short_interest ? (
          <p className="tabular-nums text-xs">
            {r.short_interest.short_qty?.toLocaleString() ?? "—"} shares short on {r.short_interest.settlement_date}
            {r.short_interest.change_pct != null ? ` (${r.short_interest.change_pct > 0 ? "+" : ""}${r.short_interest.change_pct.toFixed(1)}% vs prior)` : ""}
            {r.short_interest.days_to_cover != null ? ` · ${r.short_interest.days_to_cover.toFixed(1)} days to cover` : ""}
          </p>
        ) : <Missing why={r.missing_because.short_interest} />}
        {r.politicians && (
          <>
            <h4 className="text-xs uppercase tracking-wide text-muted-foreground mt-3 mb-1">Members of Congress (House PTRs)</h4>
            <ul className="text-xs space-y-1">
              {r.politicians.recent.map((p, i) => (
                <li key={i}>
                  {p.member} · {p.tx_type} · traded {day(p.trade_date)}, disclosed {day(p.disclosure_date)} · {usd(p.amount_lo)}–{usd(p.amount_hi)}
                  {p.url && <> {" "}<ExtLink href={p.url}>PTR</ExtLink></>}
                </li>
              ))}
            </ul>
          </>
        )}
        {r.revision && (
          <p className="mt-3 text-xs text-muted-foreground">
            Analyst target revisions, last 90 days: {r.revision.net_raises_90d ?? 0} net raises across {r.revision.n_firms_90d ?? 0} firms,
            median change {pct(r.revision.median_target_change_90d, 1, true)}.
          </p>
        )}
        <h4 className="text-xs uppercase tracking-wide text-muted-foreground mt-3 mb-1">Links</h4>
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
          {linkRow.filter(([, u]) => u).map(([label, u]) => <ExtLink key={label} href={u as string}>{label}</ExtLink>)}
        </div>
        {Object.keys(r.missing_because).length > 0 && (
          <details className="mt-3 text-[11px] text-muted-foreground">
            <summary className="cursor-pointer">Why some fields are empty ({Object.keys(r.missing_because).length})</summary>
            <ul className="mt-1 space-y-0.5">
              {Object.entries(r.missing_because).map(([k, v]) => <li key={k}><b>{k}</b>: {v}</li>)}
            </ul>
          </details>
        )}
      </section>
    </div>
  );
}

// ───────────────────────────── sorting ─────────────────────────────

type SortKey = "default" | "ticker" | "weight" | "sector" | "upside" | "move" | "direction" | "catalyst" | "insiders" | "analysts";

const DIR_ORDER: Record<string, number> = { UP: 3, MIXED: 2, NEUTRAL: 1, DOWN: 0 };

function sortValue(r: OppRow, k: SortKey): number | string | null {
  switch (k) {
    case "ticker": return r.ticker;
    case "weight": return r.weight ?? r.list_score;
    case "sector": return r.sector ?? r.theme;
    case "upside": return r.upside?.median ?? null;
    case "move": return r.move_score?.expected_abs_move_21s ?? null;
    case "direction": return r.direction ? DIR_ORDER[r.direction.label] ?? null : null;
    case "catalyst": return nextCatalyst(r)?.date ?? null;
    case "insiders": return insiderNet(r);
    case "analysts": return r.analyst?.n ?? null;
    default: return null;
  }
}

function Th({ label, k, sort, setSort, className = "", title }: {
  label: string; k: SortKey; sort: { k: SortKey; dir: 1 | -1 };
  setSort: (s: { k: SortKey; dir: 1 | -1 }) => void; className?: string; title?: string;
}) {
  const active = sort.k === k;
  const Icon = !active ? ArrowUpDown : sort.dir === 1 ? ArrowUp : ArrowDown;
  return (
    <th className={`sticky top-0 z-10 bg-background py-2 pr-3 text-left font-medium ${className}`} title={title}>
      <button
        className={`inline-flex items-center gap-1 uppercase tracking-wide text-[11px] ${active ? "text-foreground" : "text-muted-foreground"} hover:text-foreground`}
        onClick={() => setSort({ k, dir: active ? ((-sort.dir) as 1 | -1) : (k === "ticker" || k === "sector" || k === "catalyst" ? 1 : -1) })}
      >
        {label} <Icon className="h-3 w-3" />
      </button>
    </th>
  );
}

// ───────────────────────────── page ─────────────────────────────

const LANES = [
  { key: "ALL", label: "All lanes" },
  { key: "CORE", label: "Core" },
  { key: "HIGH_RISK_INNOVATION", label: "High-Risk Innovation" },
  { key: "BENCHMARK", label: "Benchmark" },
];

function ListSwitcher({ lists, value, onChange }: { lists: OppListMeta[]; value: string; onChange: (id: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2">
      {lists.map((l) => {
        const active = l.list_id === value;
        return (
          <button
            key={l.list_id}
            onClick={() => onChange(l.list_id)}
            className={`rounded-lg border px-3 py-1.5 text-left text-sm transition-colors ${active
              ? "border-primary bg-primary/10 text-foreground"
              : "border-border hover:bg-muted text-muted-foreground"}`}
            title={l.label ?? l.source ?? ""}
          >
            <span className="font-medium">{l.title}</span>
            <span className="ml-1.5 text-xs tabular-nums opacity-70">{l.n_rows ?? ""}</span>
            {l.magnitude_ranking && <span className="ml-1.5 text-[10px] font-semibold text-amber-700 dark:text-amber-400">MAGNITUDE</span>}
          </button>
        );
      })}
    </div>
  );
}

export default function OpportunitiesPage() {
  const [listId, setListId] = useState<string | null>(null);
  const [sector, setSector] = useState("ALL");
  const [horizon, setHorizon] = useState("ALL");
  const [lane, setLane] = useState("ALL");
  const [minAnalysts, setMinAnalysts] = useState(0); // OFF by default (owner: do not hide thin coverage)
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<{ k: SortKey; dir: 1 | -1 }>({ k: "default", dir: 1 });
  const [open, setOpen] = useState<Record<string, boolean>>({});

  const latest = useQuery({ queryKey: ["opportunities", "latest"], queryFn: getOpportunitiesLatest, staleTime: 10 * 60_000 });
  const activeId = listId ?? latest.data?.list?.list_id ?? null;
  const picked = useQuery({
    queryKey: ["opportunities", "list", activeId],
    queryFn: () => getOpportunitiesList(activeId as string),
    enabled: !!activeId && activeId !== latest.data?.list?.list_id,
    staleTime: 10 * 60_000,
  });
  const resp: OpportunitiesResponse | undefined =
    activeId && activeId !== latest.data?.list?.list_id ? picked.data : latest.data;
  const list = resp?.list ?? null;

  const sectors = useMemo(() => {
    const s = new Set<string>();
    list?.rows.forEach((r) => s.add(r.sector ?? (r.theme ? `theme: ${r.theme}` : "unknown")));
    return ["ALL", ...Array.from(s).sort()];
  }, [list]);
  const horizons = useMemo(() => {
    const s = new Set<string>();
    list?.rows.forEach((r) => s.add(r.horizon ?? "none declared"));
    return ["ALL", ...Array.from(s).sort()];
  }, [list]);

  const rows = useMemo(() => {
    if (!list) return [];
    const needle = q.trim().toLowerCase();
    let out = list.rows.filter((r) => {
      const sec = r.sector ?? (r.theme ? `theme: ${r.theme}` : "unknown");
      if (sector !== "ALL" && sec !== sector) return false;
      if (horizon !== "ALL" && (r.horizon ?? "none declared") !== horizon) return false;
      if (lane !== "ALL" && r.lane !== lane) return false;
      if (minAnalysts > 0 && (r.analyst?.n ?? 0) < minAnalysts) return false;
      if (needle && !(`${r.ticker} ${r.company_name ?? ""}`.toLowerCase().includes(needle))) return false;
      return true;
    });
    if (sort.k !== "default") {
      out = [...out].sort((a, b) => {
        const va = sortValue(a, sort.k), vb = sortValue(b, sort.k);
        if (va == null && vb == null) return 0;
        if (va == null) return 1;   // missing values always sink, whichever way
        if (vb == null) return -1;
        return (va < vb ? -1 : va > vb ? 1 : 0) * sort.dir;
      });
    }
    return out;
  }, [list, sector, horizon, lane, minAnalysts, q, sort]);

  const switchList = (id: string) => {
    setListId(id);
    setSector("ALL"); setHorizon("ALL"); setLane("ALL"); setOpen({});
    setSort({ k: "default", dir: 1 });
  };

  const err = (latest.error ?? picked.error) as Error | null;
  const isBook = list?.kind === "book";

  return (
    <div className="space-y-5 animate-slide-up">
      <div>
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Compass className="h-6 w-6" /> Opportunity Explorer
        </h1>
        <p className="text-sm text-muted-foreground max-w-3xl">
          Every list the engine produced, in one sortable table: who the company is, how much it is held,
          where the price sits against the analysts, why it was picked and by which service, what is coming,
          and what insiders are doing. Click a row for the reasons, the news and the filings.
        </p>
        {resp && (
          <p className="mt-1 text-xs text-muted-foreground">
            Receipt <span className="font-mono">{resp.receipt_file}</span> · built {resp.generated_utc?.slice(0, 16).replace("T", " ")} UTC
            · {resp.licence}
          </p>
        )}
      </div>

      {/* legend: magnitude vs direction, in two sentences */}
      <Card>
        <CardContent className="py-4 grid gap-3 md:grid-cols-3 text-sm">
          <div>
            <p className="font-semibold flex items-center gap-1.5"><span className="inline-block h-2 w-4 rounded bg-violet-500/70" /> MoveScore (magnitude)</p>
            <p className="text-muted-foreground">How far the stock may move over the next 21 trading sessions, up or down, from its own recent volatility. It says how big, never which way.</p>
          </div>
          <div>
            <p className="font-semibold flex items-center gap-1.5"><Badge className={DIR_TONE.UP}>UP</Badge> Direction</p>
            <p className="text-muted-foreground">The analysts&apos; consensus rating plus whether their price targets were raised or cut over 90 days. It never comes from volatility.</p>
          </div>
          <div>
            <p className="font-semibold flex items-center gap-1.5"><Rocket className="h-4 w-4 text-fuchsia-600 dark:text-fuchsia-400" /> High-Risk Innovation</p>
            <p className="text-muted-foreground">Fewer than 5 analysts, a 21-session move of 15% or more, an &quot;against&quot; card, or a binary FDA/trial date. Shown in the list with its flags, not hidden.</p>
          </div>
        </CardContent>
      </Card>

      {latest.isLoading && <Skeleton className="h-96" />}
      {err && (
        <Card className="border-red-500/40 bg-red-500/5">
          <CardContent className="py-4 text-sm">
            <p className="font-semibold text-red-700 dark:text-red-400 flex items-center gap-2"><AlertTriangle className="h-4 w-4" /> Could not load the explorer</p>
            <p className="text-muted-foreground mt-1">{err.message}</p>
          </CardContent>
        </Card>
      )}

      {resp && (
        <>
          <ListSwitcher lists={resp.lists} value={activeId ?? ""} onChange={switchList} />

          {list && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{list.title}</CardTitle>
                <p className="text-xs text-muted-foreground">
                  {list.kind} · as of {list.asof ?? "—"}
                  {list.benchmark ? ` · benchmark ${list.benchmark}` : ""}
                  {list.horizon ? ` · horizon ${list.horizon}` : ""}
                  {list.book_id ? ` · book_id ${list.book_id}` : ""}
                  {" · source "}<span className="font-mono">{list.source}</span>
                </p>
                {list.label && (
                  <div className={`mt-2 rounded-lg border px-3 py-2 text-sm flex gap-2 ${list.magnitude_ranking
                    ? "border-amber-500/50 bg-amber-500/10 text-amber-900 dark:text-amber-200"
                    : "border-border bg-muted/40 text-foreground/90"}`}>
                    {list.magnitude_ranking ? <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" /> : <Info className="h-4 w-4 shrink-0 mt-0.5" />}
                    <span>{list.label}</span>
                  </div>
                )}
              </CardHeader>
              <CardContent>
                {/* filters */}
                <div className="flex flex-wrap items-end gap-3 mb-3 text-sm">
                  <label className="flex flex-col gap-1">
                    <span className="text-[11px] uppercase tracking-wide text-muted-foreground">Search</span>
                    <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="ticker or company"
                      className="h-8 w-44 rounded-md border border-border bg-background px-2" />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[11px] uppercase tracking-wide text-muted-foreground">Sector</span>
                    <select value={sector} onChange={(e) => setSector(e.target.value)} className="h-8 max-w-[220px] rounded-md border border-border bg-background px-2">
                      {sectors.map((s) => <option key={s} value={s}>{s === "ALL" ? "All sectors" : s}</option>)}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[11px] uppercase tracking-wide text-muted-foreground">Horizon</span>
                    <select value={horizon} onChange={(e) => setHorizon(e.target.value)} className="h-8 max-w-[260px] rounded-md border border-border bg-background px-2">
                      {horizons.map((s) => <option key={s} value={s}>{s === "ALL" ? "All horizons" : s}</option>)}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[11px] uppercase tracking-wide text-muted-foreground">Lane</span>
                    <select value={lane} onChange={(e) => setLane(e.target.value)} className="h-8 rounded-md border border-border bg-background px-2">
                      {LANES.map((l) => <option key={l.key} value={l.key}>{l.label}</option>)}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1" title="0 = off. The owner asked not to hide thin-coverage names by default.">
                    <span className="text-[11px] uppercase tracking-wide text-muted-foreground">Min analysts</span>
                    <input type="number" min={0} max={60} value={minAnalysts}
                      onChange={(e) => setMinAnalysts(Math.max(0, Number(e.target.value) || 0))}
                      className="h-8 w-20 rounded-md border border-border bg-background px-2 tabular-nums" />
                  </label>
                  <span className="text-xs text-muted-foreground ml-auto tabular-nums">
                    {rows.length} of {list.rows.length} rows
                    {list.n_high_risk_innovation ? ` · ${list.n_high_risk_innovation} High-Risk Innovation` : ""}
                  </span>
                </div>

                {/* the table: sticky header, scrolls inside the card */}
                <div className="max-h-[75vh] overflow-auto rounded-lg border border-border">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="sticky top-0 z-10 bg-background w-6" />
                        <Th label="Ticker" k="ticker" sort={sort} setSort={setSort} />
                        <Th label={isBook ? "Weight" : "Rank / score"} k="weight" sort={sort} setSort={setSort} className="text-right" />
                        <Th label="Sector" k="sector" sort={sort} setSort={setSort} />
                        <Th label="Price vs targets" k="upside" sort={sort} setSort={setSort} title="sorted by upside to the median target" />
                        <th className="sticky top-0 z-10 bg-background py-2 pr-3 text-left text-[11px] uppercase tracking-wide font-medium text-muted-foreground">Why picked</th>
                        <Th label="Next date / news" k="catalyst" sort={sort} setSort={setSort} />
                        <Th label="Insiders" k="insiders" sort={sort} setSort={setSort} title="net open-market Form 4 dollars, last 180 days" />
                        <Th label="Coverage" k="analysts" sort={sort} setSort={setSort} title="analyst count; short interest" />
                        <Th label="MoveScore" k="move" sort={sort} setSort={setSort} title="MAGNITUDE: expected size of the 21-session move, either way" />
                        <Th label="Direction" k="direction" sort={sort} setSort={setSort} title="consensus + 90-day revisions; never from volatility" />
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => {
                        const key = `${r.list_id}:${r.ticker}`;
                        const isOpen = !!open[key];
                        const nc = nextCatalyst(r);
                        const net = insiderNet(r);
                        return (
                          <React.Fragment key={key}>
                            <tr
                              className={`border-b border-border/50 align-top cursor-pointer hover:bg-muted/40 ${isOpen ? "bg-muted/30" : ""}`}
                              onClick={() => setOpen((o) => ({ ...o, [key]: !o[key] }))}
                            >
                              <td className="py-2.5 pl-2 text-muted-foreground">
                                {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                              </td>
                              <td className="py-2.5 pr-3"><TickerCell r={r} /></td>
                              <td className="py-2.5 pr-3 text-right tabular-nums whitespace-nowrap">
                                {r.weight != null ? pct(r.weight, 1)
                                  : r.rank != null ? <span>#{r.rank}<div className="text-[10px] text-muted-foreground">{pct(r.list_score, 1, true)}</div></span>
                                  : r.list_score != null ? <span className="text-muted-foreground">{pct(r.list_score, 0, true)}</span>
                                  : <Missing why={r.missing_because.weight} />}
                              </td>
                              <td className="py-2.5 pr-3 text-xs max-w-[150px]">
                                {r.sector ?? (r.theme ? <span className="text-muted-foreground">theme: {r.theme}</span> : <Missing why={r.missing_because.sector} />)}
                              </td>
                              <td className="py-2.5 pr-3"><TargetCell r={r} /></td>
                              <td className="py-2.5 pr-3 text-xs max-w-[280px]">
                                {r.why_picked[0] ? (
                                  <>
                                    <p className="line-clamp-3">{r.why_picked[0].reason}</p>
                                    <p className="text-[10px] text-muted-foreground mt-0.5 line-clamp-1">{r.why_picked[0].service}
                                      {r.why_picked.length > 1 ? ` · +${r.why_picked.length - 1} more` : ""}</p>
                                  </>
                                ) : <Missing why={r.missing_because.why_picked} />}
                              </td>
                              <td className="py-2.5 pr-3 text-xs max-w-[220px]">
                                {nc ? (
                                  <p><span className="font-mono tabular-nums">{nc.date}</span> <span className="text-muted-foreground">{nc.kind}</span></p>
                                ) : <Missing why={r.missing_because.catalysts} />}
                                {r.news[0] ? (
                                  <div className="mt-1 line-clamp-2"><ExtLink href={r.news[0].url}>{r.news[0].title || "news"}</ExtLink></div>
                                ) : null}
                                {r.news.length > 1 && <p className="text-[10px] text-muted-foreground">+{r.news.length - 1} more news</p>}
                              </td>
                              <td className="py-2.5 pr-3 text-xs whitespace-nowrap tabular-nums">
                                {r.insiders ? (
                                  <>
                                    <span className={net! >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400"}>
                                      net {net! >= 0 ? "+" : "−"}{usd(Math.abs(net!))}
                                    </span>
                                    <div className="text-[10px] text-muted-foreground">{r.insiders.n_buys} buy · {r.insiders.n_sells} sell</div>
                                  </>
                                ) : <Missing why={r.missing_because.insiders} />}
                              </td>
                              <td className="py-2.5 pr-3 text-xs whitespace-nowrap tabular-nums">
                                {r.analyst?.n != null ? `${r.analyst.n} analysts` : <Missing why={r.missing_because["analyst.n"] ?? r.missing_because.analyst} />}
                                <div className="text-[10px] text-muted-foreground">
                                  {r.short_interest?.days_to_cover != null ? `${r.short_interest.days_to_cover.toFixed(1)}d to cover` : ""}
                                  {r.politicians ? ` · ${r.politicians.n} Congress trade${r.politicians.n === 1 ? "" : "s"}` : ""}
                                </div>
                              </td>
                              <td className="py-2.5 pr-3"><MoveCell r={r} /></td>
                              <td className="py-2.5 pr-3"><DirectionCell r={r} /></td>
                            </tr>
                            {isOpen && (
                              <tr className="border-b border-border">
                                <td colSpan={11} className="p-0">
                                  {/* pinned to the visible width of the scroll box, so a wide table never pushes the details off-screen */}
                                  <div className="sticky left-0" style={{ width: "min(1180px, calc(100vw - 340px))", minWidth: "320px" }}>
                                    <Detail r={r} />
                                  </div>
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        );
                      })}
                      {rows.length === 0 && (
                        <tr><td colSpan={11} className="py-8 text-center text-muted-foreground">No row matches these filters.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
                <p className="mt-2 text-[11px] text-muted-foreground">
                  Every external link opens in a new tab. An &quot;n/a&quot; carries its reason on hover; the expanded row lists them all.
                  Price is the last close on the bars panel; targets are the newest analyst snapshot.
                </p>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
