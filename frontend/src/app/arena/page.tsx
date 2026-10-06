"use client";

/**
 * /arena — the Paper Arena (chunk C19, 2026-10-07; review fixes F5/F9).
 *
 * Every paper account and frozen book with its family, strategy, inception, sessions
 * graded, return against SPY over ITS OWN window, evidence label and twin/control marker.
 * The page LEADS with the C3 top line and the twin-collapsed counts: "N ahead of SPY" is
 * never shown alone (twins re-price a parent, controls are controls, books holding the
 * same names are one bet). Winners are books with enough sessions to rank; younger books
 * sit in their own panel and are not evidence. Owner-personal books are not served.
 *
 * Read-only: GET /api/arena/v1/latest (newest ROI + book_dna receipts) and
 * GET /api/arena/v1/stories (C11 decision stories, PC-PAPER only).
 */

import React, { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowDown, ArrowUp, Brain, Compass, FlaskConical, Hourglass, Swords, Trophy, TrendingDown } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { getArenaLatest, getArenaStories, type ArenaBook, type ArenaResponse } from "@/lib/api";
import {
  EvidenceBadge, EvidenceLadder, LoadError, Missing, MissingList, ReceiptStrip, SourceNote, StaleBanner,
  num, signTone,
} from "@/components/legibility/receipts";

const ROI_SRC = "paper_accounts_roi";
const DNA_SRC = "book_dna";

function CategoryMark({ b }: { b: ArenaBook }) {
  if (b.category === "twin")
    return <Badge variant="outline" className="text-[10px] border-sky-500/40 text-sky-700 dark:text-sky-300">TWIN{b.twin_kind ? ` · ${b.twin_kind}` : ""}</Badge>;
  if (b.category === "control")
    return <Badge variant="outline" className="text-[10px] border-amber-500/40 text-amber-700 dark:text-amber-300">CONTROL</Badge>;
  if (b.category === "strategy")
    return <Badge variant="outline" className="text-[10px]">STRATEGY</Badge>;
  return <Missing why={b.missing_because?.evidence_label ?? "no category"} />;
}

function Pp({ v, why }: { v: number | null; why?: string }) {
  if (v == null) return <Missing why={why} />;
  return <span className={`tabular-nums ${signTone(v)}`}>{num(v, 2, true)} pp</span>;
}

function Quote({ label, text, src }: { label: string; text: string | null; src: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      {text ? <p className="mt-1 text-sm leading-relaxed">{text}</p> : <p className="mt-1 text-sm"><Missing why="not in the receipts" /></p>}
      <SourceNote>{src}</SourceNote>
    </div>
  );
}

function Stat({ label, value, src }: { label: string; value: React.ReactNode; src: string }) {
  return (
    <div className="rounded-lg border border-border p-3">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="text-lg font-semibold tabular-nums">{value}</div>
      <div className="text-[10px] font-mono text-muted-foreground break-words">{src}</div>
    </div>
  );
}

type SortKey = "vs_spy_pp" | "return_pct" | "sessions_graded" | "account";

function BookDrawer({ book, onClose }: { book: ArenaBook | null; onClose: () => void }) {
  const isPc = book?.family === "pc_paper";
  const stories = useQuery({
    queryKey: ["arena", "stories"], queryFn: () => getArenaStories(), retry: false, enabled: !!book && isPc,
  });
  return (
    <Sheet open={!!book} onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent side="right" className="w-full sm:max-w-xl overflow-y-auto">
        {book && (
          <div className="space-y-4 p-4">
            <SheetTitle className="break-words font-mono text-base">{book.account}</SheetTitle>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Badge variant="secondary">{book.family}</Badge>
              <CategoryMark b={book} />
              <EvidenceBadge label={book.evidence_label} rung={book.evidence_rung} why={book.evidence_why} />
            </div>
            {book.evidence_why && <p className="text-xs text-muted-foreground">label reason: {book.evidence_why}</p>}
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-sm">
              <dt className="text-muted-foreground">Strategy</dt><dd className="break-words">{book.strategy ?? <Missing why={book.missing_because?.strategy} />}</dd>
              <dt className="text-muted-foreground">Inception</dt><dd>{book.inception ?? <Missing why="not in the receipt" />}</dd>
              <dt className="text-muted-foreground">Last mark</dt><dd>{book.last_mark ?? "—"} {book.mark_status ? `(${book.mark_status})` : ""}</dd>
              <dt className="text-muted-foreground">Sessions graded</dt><dd>{book.sessions_graded ?? <Missing why={book.missing_because?.sessions_graded} />}</dd>
              <dt className="text-muted-foreground">Return</dt><dd className={signTone(book.return_pct)}>{book.return_pct == null ? <Missing why={book.missing_because?.vs_spy_pp} /> : `${num(book.return_pct, 2, true)}%`}</dd>
              <dt className="text-muted-foreground">SPY, same window</dt><dd>{book.spy_same_window_pct == null ? "—" : `${num(book.spy_same_window_pct, 2, true)}%`} {book.spy_base ? <span className="text-[11px] text-muted-foreground">({book.spy_base})</span> : null}</dd>
              <dt className="text-muted-foreground">vs SPY</dt><dd><Pp v={book.vs_spy_pp} why={book.missing_because?.vs_spy_pp} /></dd>
              <dt className="text-muted-foreground">Beta vs SPY</dt><dd>{book.beta_vs_spy == null ? <Missing why={book.missing_because?.beta_vs_spy} /> : `${num(book.beta_vs_spy)} (n=${book.beta_n_obs ?? "?"})`}</dd>
              <dt className="text-muted-foreground">Cash</dt><dd>{book.cash_fraction == null ? <Missing why={book.missing_because?.cash_fraction} /> : `${(100 * book.cash_fraction).toFixed(1)}% of the book`}</dd>
              {book.twin_of && (<><dt className="text-muted-foreground">Twin of</dt><dd className="break-words font-mono text-xs">{book.twin_of}</dd></>)}
            </dl>
            {book.error_type && (
              <div className="rounded border border-red-600/30 bg-red-500/5 p-2 text-sm">
                <div className="font-medium">Loser error type: <span className="font-mono">{book.error_type}</span></div>
                {book.error_why && <p className="text-xs text-muted-foreground">{book.error_why}</p>}
              </div>
            )}
            {book.subwindows && book.subwindows.length > 0 && (
              <div>
                <div className="text-xs font-medium">Sub-windows (excess vs SPY)</div>
                <ul className="text-xs">
                  {book.subwindows.map((w) => (
                    <li key={w.from}>{w.from} → {w.to}: <span className={signTone(w.excess_pp)}>{num(w.excess_pp, 2, true)} pp</span></li>
                  ))}
                </ul>
              </div>
            )}
            <div>
              <div className="text-xs font-medium">Holdings ({book.n_holdings ?? "?"})</div>
              {book.holdings.length ? (
                <div className="mt-1 flex flex-wrap gap-1">
                  {book.holdings.map((h) => (
                    <span key={h.ticker} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">
                      {h.ticker}{h.weight != null ? ` ${(100 * h.weight).toFixed(1)}%` : ""}
                    </span>
                  ))}
                </div>
              ) : <p className="text-xs"><Missing why="no holdings in book_dna for this row" /></p>}
              {book.holdings_source && <SourceNote>{book.holdings_source}</SourceNote>}
            </div>
            {book.source && <SourceNote>{book.source}</SourceNote>}
            <div className="border-t border-border pt-3">
              <div className="text-sm font-medium">Decision stories (C11)</div>
              {!isPc && <p className="text-xs text-muted-foreground">Decision stories are frozen for the PC-PAPER plan only; this book has none by construction.</p>}
              {isPc && stories.isLoading && <Skeleton className="h-16 w-full" />}
              {isPc && stories.error && <LoadError what="Decision stories" err={stories.error} />}
              {isPc && stories.data && (
                <div className="space-y-2">
                  <StaleBanner receipts={stories.data.receipts} />
                  <p className="text-xs text-muted-foreground">{stories.data.n_decisions} decisions in {stories.data.month}; newest 20 shown.</p>
                  <ul className="space-y-1.5">
                    {stories.data.stories.slice(0, 20).map((s) => (
                      <li key={s.decision_id} className="rounded border border-border p-2 text-xs">
                        <div className="flex flex-wrap justify-between gap-1">
                          <span className="font-mono font-semibold">{s.ticker} · {s.action}{s.abstention ? " (abstention)" : ""}</span>
                          <span className="text-muted-foreground">{s.session}</span>
                        </div>
                        {s.reason && <p className="text-muted-foreground">{s.reason}</p>}
                        {s.alternatives.length > 0 && (
                          <p className="text-muted-foreground">alternatives frozen: {s.alternatives.map((a) => a.alt).join(", ")}</p>
                        )}
                      </li>
                    ))}
                  </ul>
                  {stories.data.regret ? (
                    <div className="overflow-x-auto">
                      <div className="text-xs font-medium">Regret at h5 ({stories.data.regret.run_id})</div>
                      {stories.data.regret.h5_table.length ? (
                        <table className="w-full text-xs">
                          <thead><tr className="text-left text-muted-foreground"><th>cohort</th><th>names</th><th>vs SPY bps</th><th>t</th><th>date blocks</th><th>MDE</th></tr></thead>
                          <tbody>
                            {stories.data.regret.h5_table.map((r) => (
                              <tr key={r.cohort}><td className="font-mono">{r.cohort}</td><td>{num(r.mean_names, 1)}</td>
                                <td className={signTone(r.mean_net_excess_vs_spy_bps)}>{num(r.mean_net_excess_vs_spy_bps, 1, true)}</td>
                                <td>{num(r.t_vs_spy)}</td><td>{r.n_date_blocks}</td><td>{num(r.mde_bps, 1)}</td></tr>
                            ))}
                          </tbody>
                        </table>
                      ) : <p className="text-xs"><Missing why={stories.data.regret.missing_because ?? undefined} /></p>}
                    </div>
                  ) : <p className="text-xs"><Missing why="no regret receipt yet" /></p>}
                  <ReceiptStrip receipts={stories.data.receipts} />
                </div>
              )}
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

function BookList({ books, onPick, empty }: { books: ArenaBook[]; onPick: (b: ArenaBook) => void; empty: string }) {
  if (!books.length) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <ul className="divide-y divide-border/50">
      {books.map((b) => (
        <li key={b.account} className="py-1.5">
          <div className="flex items-center justify-between gap-2">
            <button className="min-w-0 truncate text-left font-mono text-xs hover:underline" onClick={() => onPick(b)}>{b.account}</button>
            <span className="flex shrink-0 items-center gap-2 text-xs">
              <Pp v={b.vs_spy_pp} />
              {b.error_type ? <Badge variant="outline" className="font-mono text-[10px]">{b.error_type}</Badge>
                : <EvidenceBadge label={b.evidence_label} rung={b.evidence_rung} why={b.evidence_why} />}
            </span>
          </div>
          {b.error_why && <p className="text-[11px] text-muted-foreground line-clamp-2" title={b.error_why}>{b.error_why}</p>}
        </li>
      ))}
    </ul>
  );
}

function Panels({ d, onPick }: { d: ArenaResponse; onPick: (b: ArenaBook) => void }) {
  const min = d.numbers.min_sessions_to_rank;
  const [showYoung, setShowYoung] = useState(false);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2 text-base"><Trophy className="h-4 w-4" /> Ahead of SPY with ≥ {min} sessions</CardTitle></CardHeader>
        <CardContent>
          <p className="mb-2 text-xs text-muted-foreground">Strategy books only (twins and controls excluded), at least {min} graded sessions. {d.numbers.n_strategy_ge_min_sessions} strategy books are that old.</p>
          <BookList books={d.winners} onPick={onPick} empty={`No strategy book with ≥ ${min} sessions is ahead of SPY.`} />
          <SourceNote>{DNA_SRC}.books (category=strategy, sessions_graded ≥ {min}, excess &gt; 0)</SourceNote>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2 text-base"><TrendingDown className="h-4 w-4" /> Losers, with the error type</CardTitle></CardHeader>
        <CardContent>
          <p className="mb-2 text-xs text-muted-foreground">Studied as hard as winners: each loser names what kind of error it was.</p>
          <BookList books={d.losers} onPick={onPick} empty={d.missing_because.book_dna ?? "book_dna listed no losers"} />
          <SourceNote>{DNA_SRC}.losers</SourceNote>
        </CardContent>
      </Card>
      <Card className="lg:col-span-2 border-dashed">
        <CardHeader className="pb-2">
          <CardTitle className="flex flex-wrap items-center gap-2 text-base"><Hourglass className="h-4 w-4" /> Short-lived books ahead of SPY (not evidence)
            <button className="ml-auto text-xs font-normal underline" onClick={() => setShowYoung((v) => !v)}>{showYoung ? "hide" : `show ${d.short_lived.length}`}</button>
          </CardTitle>
        </CardHeader>
        {showYoung && (
          <CardContent>
            <p className="mb-2 text-xs text-muted-foreground">Fewer than {min} sessions: a few weeks cannot separate skill from noise. Listed so nothing is hidden, not to be ranked.</p>
            <BookList books={d.short_lived} onPick={onPick} empty="None." />
          </CardContent>
        )}
      </Card>
    </div>
  );
}

export default function ArenaPage() {
  const q = useQuery({ queryKey: ["arena", "latest"], queryFn: getArenaLatest, retry: 1, refetchInterval: 10 * 60_000 });
  const [family, setFamily] = useState("all");
  const [label, setLabel] = useState("all");
  const [category, setCategory] = useState("all");
  const [twinsLast, setTwinsLast] = useState(true);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "vs_spy_pp", desc: true });
  const [picked, setPicked] = useState<ArenaBook | null>(null);
  const d = q.data;

  const rows = useMemo(() => {
    if (!d) return [];
    const s = search.trim().toLowerCase();
    const out = d.books.filter((b) =>
      (family === "all" || b.family === family) &&
      (label === "all" || (b.evidence_rung ?? "NO_LABEL") === label) &&
      (category === "all" || (b.category ?? "unknown") === category) &&
      (!s || b.account.toLowerCase().includes(s) || (b.strategy ?? "").toLowerCase().includes(s)));
    const rank = (b: ArenaBook) => (b.category === "strategy" ? 0 : b.category === "control" ? 1 : b.category === "twin" ? 2 : 3);
    const k = sort.key;
    out.sort((a, b) => {
      if (twinsLast && rank(a) !== rank(b)) return rank(a) - rank(b);
      if (k === "account") return sort.desc ? b.account.localeCompare(a.account) : a.account.localeCompare(b.account);
      const av = a[k] as number | null, bv = b[k] as number | null;
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return sort.desc ? bv - av : av - bv;
    });
    return out;
  }, [d, family, label, category, search, sort, twinsLast]);

  const Th = ({ k, children }: { k?: SortKey; children: React.ReactNode }) => (
    <th className="sticky top-0 z-10 bg-background py-2 pr-3 text-left text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
      {k ? (
        <button className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => setSort((p) => ({ key: k, desc: p.key === k ? !p.desc : true }))}>
          {children}{sort.key === k ? (sort.desc ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />) : null}
        </button>
      ) : children}
    </th>
  );

  return (
    <div className="space-y-5 animate-slide-up">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-3xl">
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight"><Swords className="h-6 w-6" /> Paper Arena</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Every paper account and frozen book, graded against SPY over its own window. Everything here runs under
            PRODUCT_EXPERIMENT: nothing on this page is a claim of skill.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <Link href="/opportunities" className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 hover:bg-muted"><Compass className="h-3.5 w-3.5" /> What the books hold: Opportunity Explorer</Link>
          <Link href="/theory-lab" className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 hover:bg-muted"><FlaskConical className="h-3.5 w-3.5" /> Theory Lab</Link>
          <Link href="/brain" className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 hover:bg-muted"><Brain className="h-3.5 w-3.5" /> Optimus Brain</Link>
        </div>
      </div>

      {q.isLoading && <Skeleton className="h-40 w-full" />}
      {q.error && <LoadError what="Paper Arena" err={q.error} />}

      {d && (
        <>
          <StaleBanner receipts={d.receipts} />
          {d.receipt_choice.served_is_nobroker && (
            <div role="alert" className="flex items-start gap-2 rounded-lg border border-amber-600/40 bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-300">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /><span>{d.receipt_choice.line}</span>
            </div>
          )}
          <Quote label="Top line (verbatim)" text={d.top.top_line} src={`${ROI_SRC}.aggregate.top_line`} />
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label={`Ahead of SPY with ≥ ${d.numbers.min_sessions_to_rank} sessions`} value={d.numbers.n_ahead_dense ?? "—"} src={`${ROI_SRC}.aggregate.n_ahead_dense`} />
            <Stat label="Strategy books ahead (twins & controls removed)" value={d.numbers.n_ahead_strategy ?? "—"} src={`${ROI_SRC}.aggregate.n_ahead_strategy`} />
            <Stat label="…which are this many holdings clusters" value={d.numbers.n_holdings_clusters_ahead ?? "—"} src={`${DNA_SRC} (Jaccard ${d.numbers.jaccard_threshold ?? "?"})`} />
            <Stat label="…and this many ex-ante bets" value={d.numbers.effective_bets_exante == null ? "—" : `${d.numbers.effective_bets_exante} (${d.numbers.effective_bets_exante_spy_residual ?? "?"} net of SPY)`} src={`${DNA_SRC}.exante_bets, ${d.numbers.exante_n_books ?? "?"} books`} />
          </div>
          <Quote label="Collapse line (verbatim, C3)" text={d.top.collapse_line} src={`${ROI_SRC}.aggregate.collapse_line`} />
          {d.top.evidence_density_line && (
            <p className="rounded-md border border-amber-600/30 bg-amber-500/5 p-2 text-sm">{d.top.evidence_density_line} <SourceNote>{ROI_SRC}.aggregate.evidence_density_line</SourceNote></p>
          )}
          <EvidenceLadder ladder={d.evidence_ladder} />

          <Panels d={d} onPick={setPicked} />

          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-base">Holdings clusters (books that are one bet)</CardTitle></CardHeader>
            <CardContent>
              <p className="mb-2 text-xs text-muted-foreground">
                Cluster count by Jaccard threshold: {Object.entries(d.numbers.cluster_count_sensitivity ?? {}).map(([k, v]) => `${k} → ${v}`).join(" · ") || "n/a"}.
                Most common names in strategy winners: {(d.numbers.most_frequent_names ?? []).map((m) => `${m.ticker} (${m.n_books}/${m.of})`).join(", ") || "n/a"}.
              </p>
              {d.clusters.length === 0 ? <p className="text-sm"><Missing why={d.missing_because.book_dna ?? "no clusters in book_dna"} /></p> : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead><tr className="text-left text-muted-foreground"><th className="pr-3">#</th><th className="pr-3">books</th><th className="pr-3">shared basket</th><th className="pr-3">mean excess</th><th>members</th></tr></thead>
                    <tbody>
                      {d.clusters.slice(0, 12).map((c) => (
                        <tr key={c.cluster_id} className="border-t border-border/40 align-top">
                          <td className="pr-3">{c.cluster_id}</td><td className="pr-3">{c.n}</td>
                          <td className="pr-3 font-mono">{c.shared_basket.join(", ")}</td>
                          <td className={`pr-3 ${signTone(c.excess_pp_mean)}`}>{num(c.excess_pp_mean, 2, true)} pp</td>
                          <td className="font-mono text-[11px] text-muted-foreground">{c.members.join(", ")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <SourceNote>{DNA_SRC}.holdings_clusters</SourceNote>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-base">Every book ({rows.length} of {d.books.length})</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <select aria-label="Family" className="rounded border border-border bg-background px-2 py-1" value={family} onChange={(e) => setFamily(e.target.value)}>
                  <option value="all">All families</option>
                  {Object.entries(d.filters.families).map(([f, n]) => <option key={f} value={f}>{f} ({n})</option>)}
                </select>
                <select aria-label="Evidence label" className="rounded border border-border bg-background px-2 py-1" value={label} onChange={(e) => setLabel(e.target.value)}>
                  <option value="all">All labels</option>
                  {Object.entries(d.filters.labels).map(([l, n]) => <option key={l} value={l}>{l} ({n})</option>)}
                </select>
                <select aria-label="Category" className="rounded border border-border bg-background px-2 py-1" value={category} onChange={(e) => setCategory(e.target.value)}>
                  <option value="all">Strategy, twin and control</option>
                  {Object.entries(d.filters.categories).map(([c, n]) => <option key={c} value={c}>{c} ({n})</option>)}
                </select>
                <label className="inline-flex items-center gap-1 text-xs"><input type="checkbox" checked={twinsLast} onChange={(e) => setTwinsLast(e.target.checked)} /> twins and controls last</label>
                <input aria-label="Search" placeholder="search account or strategy" className="min-w-0 flex-1 rounded border border-border bg-background px-2 py-1" value={search} onChange={(e) => setSearch(e.target.value)} />
              </div>
              <div className="max-h-[70vh] overflow-auto rounded border border-border/50">
                <table className="w-full text-sm">
                  <thead>
                    <tr>
                      <Th k="account">Book</Th><Th>Family</Th><Th>Kind</Th><Th>Strategy</Th><Th>Inception</Th>
                      <Th k="sessions_graded">Sessions</Th><Th k="return_pct">Return</Th><Th>SPY (own window)</Th>
                      <Th k="vs_spy_pp">vs SPY</Th><Th>Evidence</Th><Th>Mark</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((b) => {
                      const dim = b.category === "twin" || b.category === "control";
                      return (
                        <tr key={`${b.account}-${b.book_id ?? ""}`} className={`cursor-pointer border-t border-border/40 hover:bg-muted/40 ${dim ? "opacity-60" : ""}`} onClick={() => setPicked(b)}>
                          <td className="max-w-[16rem] truncate py-1.5 pr-3 font-mono text-xs" title={b.account}>{b.account}</td>
                          <td className="pr-3 text-xs">{b.family}</td>
                          <td className="pr-3"><CategoryMark b={b} /></td>
                          <td className="max-w-[14rem] truncate pr-3 text-xs" title={b.strategy ?? ""}>{b.strategy ?? <Missing why={b.missing_because?.strategy} />}</td>
                          <td className="whitespace-nowrap pr-3 text-xs">{b.inception ?? "—"}</td>
                          <td className="pr-3 tabular-nums">{b.sessions_graded ?? "—"}</td>
                          <td className={`pr-3 tabular-nums ${signTone(b.return_pct)}`}>{b.return_pct == null ? "—" : `${num(b.return_pct, 2, true)}%`}</td>
                          <td className="pr-3 tabular-nums">{b.spy_same_window_pct == null ? "—" : `${num(b.spy_same_window_pct, 2, true)}%`}</td>
                          <td className="whitespace-nowrap pr-3"><Pp v={b.vs_spy_pp} why={b.missing_because?.vs_spy_pp} /></td>
                          <td className="pr-3"><EvidenceBadge label={b.evidence_label} rung={b.evidence_rung} why={b.evidence_why ?? b.missing_because?.evidence_label} /></td>
                          <td className={`whitespace-nowrap pr-3 text-[11px] ${b.mark_status && b.mark_status !== "LIVE" ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground"}`}>
                            {b.mark_status ?? "—"}{b.mark_age_days != null ? ` · ${b.mark_age_days} d` : ""}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <SourceNote>{DNA_SRC}.books joined to {ROI_SRC}.rows by account; twins and controls are dimmed; click a row for its detail</SourceNote>
            </CardContent>
          </Card>

          {d.top.read_me_first && <p className="text-xs text-muted-foreground">{d.top.read_me_first} {d.top.book_dna_read_me_first}</p>}
          <MissingList missing={d.missing_because} />
          <ReceiptStrip receipts={d.receipts} />
          <BookDrawer book={picked} onClose={() => setPicked(null)} />
        </>
      )}
    </div>
  );
}
