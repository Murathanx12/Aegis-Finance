"""TRANSACTION-ENSEMBLE-1 — bounding Murat's record WITHOUT his records.

EVERYTHING THIS MODULE PRODUCES IS SYNTHETIC. No member is his history.

THE LICENSED FORM OF "MAKE UP SENSIBLE DATA"
============================================

Murat's instruction — "make up sensible data, choose the best outcome and
validate it" — cannot be executed literally: fabricating one personal record
and keeping the flattering one is outcome-shopping. The pre-registered form
(`Aegis module/TRIALS/PREREG_TRANSACTION_ENSEMBLE_1.md`, frozen at c5b81aa)
generates MANY transaction histories, each consistent with every anchor in a
DECLARED subset of the record, and adopts only conclusions that hold across
the whole ensemble. The range IS the result. No member is ever promoted,
quoted alone, or labelled "most likely".

THE ANCHORS (frozen inventory)
------------------------------
Always-on (1-6, 10): the two PIT sheets (compositions + the three annotated
exits TVTX@34.4 / ALMS@10 / SLDP@8.1 with dates bounded (2025-11-07,
2026-01-13]); the 12 immutable share counts logged 2026-07-11; QUBT 300/200 as
arms; cash swept 0-30%; the APLT $0.088 and SLNO $53.00 cash takeouts.
Mutually unreconciled (7, 8, 9): "+73.7%/+$15,165 ~1yr", "2025 +115%",
"$25k -> $45k". Members declare a subset of {7,8,9}; the inconsistency is an
ensemble DIMENSION, never resolved by preference.

THE MEMBER MODEL (stated, because every model is an assumption)
---------------------------------------------------------------
A member is a shares-ledger history over the covered price window
(2025-11-07 -> 2026-08-10): constant shares per holding episode, with an
optional second tranche for positions whose final count is known (otherwise
the family would be narrower than the records justify). Purchases are funded
from cash + sale proceeds — a purchase that no cash arrangement can fund is
REJECTED, and rejection counts are reported. Positions whose share count no
source carries are sized relative to the two counts the record does pin at
2025-11-07 (DKNG 150, NTLA 250). Histories with intra-episode trims, invisible
round-trips between sheet dates, or external contributions are OUTSIDE this
family — the doc says so.

THE UNCOVERED GAP
-----------------
Bars start 2025-10-27; anchors 7/8/9 reach back to mid/early 2025. The
uncovered months enter as ONE bounded free parameter per anchor — the book's
return over the gap, bounded by TE_GAP_RETURN_BOUNDS — and every answer
reports how much work the gap does. An anchor satisfiable only by an
implausible gap is INCONSISTENT for that member.

WHAT THIS MAY NOT DO (prereg §5)
--------------------------------
Write into murat_book.yaml / book_lanes.yaml / any lane or ledger; train
anything; overturn CONVICTION-REPLAY-1's UNRESOLVED; claim skill either way.
Output lives only in docs/NIGHT13_ENSEMBLE_NAV.md + its JSON, labelled
SYNTHETIC. NAV marking here is deliberately self-contained (equity + cash
legs) — pm_engine is NOT imported.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from backend.config import (TE_ANCHOR7_DOLLARS, TE_ANCHOR7_END_WINDOW,
                            TE_ANCHOR7_PCT, TE_ANCHOR8_PCT, TE_ANCHOR9_END,
                            TE_ANCHOR9_START, TE_APLT_JAN_MARK,
                            TE_CASH_FRAC_RANGE, TE_DOLLAR_TOL,
                            TE_EXIT_PRICE_TOL, TE_GAP_RETURN_BOUNDS,
                            TE_MAGNITUDE_CLASS_EDGES, TE_MASTER_SEED,
                            TE_MAX_ATTEMPTS_PER_MEMBER, TE_MEMBERS_PER_ARM,
                            TE_QUBT_ARMS, TE_SUBSETS, TE_TAKEOUT_TREATMENTS,
                            TE_TRANCHE_INITIAL_FRAC, TE_TRANCHE_PROB,
                            TE_WAR_WINDOW, TE_WEIGHT_MULT_RANGE, TE_WINDOW)
from backend.services.conviction_prices import CORPORATE_ACTIONS, load_prices
from backend.services.conviction_sheets import load_sheet

logger = logging.getLogger(__name__)

DATA = Path(__file__).resolve().parents[1] / "data"
CONVICTION_SNAPSHOT = DATA / "conviction_decisions_snapshot.json"

W0 = pd.Timestamp(TE_WINDOW[0])          # 2025-11-07, first pinned book
JAN = pd.Timestamp("2026-01-13")         # second sheet
LOG = pd.Timestamp("2026-07-11")         # conviction log share counts
END = pd.Timestamp(TE_WINDOW[1])         # 2026-08-10
DEC31 = pd.Timestamp("2025-12-31")
APLT_TAKEOUT = pd.Timestamp(CORPORATE_ACTIONS["APLT"].effective)

#: Anchor-7 implied dollar levels: +$15,165 at +73.7% => start ~$20,577.
ANCHOR7_START_D = TE_ANCHOR7_DOLLARS / TE_ANCHOR7_PCT
ANCHOR7_END_D = ANCHOR7_START_D * (1.0 + TE_ANCHOR7_PCT)


# ─────────────────────────────── data shapes ────────────────────────────────

@dataclass
class Episode:
    """One holding episode: constant shares from entry to exit (exclusive)."""
    ticker: str
    shares: float
    entry: pd.Timestamp                  # first day the shares are held
    exit: pd.Timestamp | None            # day proceeds land; None = held to END
    entry_kind: str                      # initial | promotion | entry | tranche | reinvest
    exit_kind: str | None = None         # known_price | demotion | exit | takeout | wash
    exit_price: float | None = None      # stated fill for the 3 annotated exits
    entry_funded: bool = False           # True => a cash purchase at entry close
    deferred_days: int = 0               # entry pushed later to find funding


@dataclass
class Member:
    """One SYNTHETIC transaction history. Never his; never quoted alone."""
    index: int
    seed: list
    declared: tuple                      # declared subset of {7,8,9}
    qubt_arm: float
    cash0_frac: float
    takeout_treatment: str
    aplt_drop: pd.Timestamp              # sampled APLT 0.80 -> 0.09 date
    episodes: list = field(default_factory=list)
    cash0: float = 0.0
    nav: pd.Series | None = None
    cash: pd.Series | None = None
    satisfied: tuple = ()                # every anchor of {7,8,9} that holds
    diagnostics: dict = field(default_factory=dict)


class Ctx:
    """Frozen inputs shared by every member: panel, books, feasible days."""

    def __init__(self, panel: pd.DataFrame | None = None):
        self.panel = panel if panel is not None else load_prices()
        self.panel = self.panel.sort_index()
        self.days = self.panel.index
        self.px = self.panel.ffill()     # closes, ffilled within the window

        nov = load_sheet("2025-11-07")
        jan = load_sheet("2026-01-13")
        self.nov_book = [h.ticker for h in nov.portfolio]                 # 13
        self.known_exits = {h.ticker: float(h.sold_at)
                            for h in jan.portfolio if h.sold_at}          # 3
        jan_names = [h.ticker for h in jan.portfolio]
        self.jan_live = [t for t in jan_names if t not in self.known_exits]

        raw = json.loads(CONVICTION_SNAPSHOT.read_text(encoding="utf-8"))
        self.log_shares = {str(r["ticker"]).upper(): float(r["shares_delta"])
                           for r in raw["decisions"]
                           if str(r["action"]).lower() == "enter"}        # 12
        self.log_marks = {str(r["ticker"]).upper(): float(r["price"])
                          for r in raw["decisions"]}

        s_nov, s_jan, s_log = set(self.nov_book), set(self.jan_live), set(self.log_shares)
        self.demotions = sorted((s_nov - set(jan_names)))       # exited Nov->Jan, no annotation
        self.promotions = sorted(s_jan - s_nov)                 # entered Nov->Jan
        self.exits_jan_jul = sorted(s_jan - s_log - {"APLT"})   # exited Jan->Jul at market
        self.entries_jan_jul = sorted(s_log - s_jan)            # entered Jan->Jul

        # sanity — these are the record's own facts, asserted not assumed
        assert len(self.nov_book) == 13 and len(self.log_shares) == 12
        assert self.known_exits == {"TVTX": 34.4, "ALMS": 10.0, "SLDP": 8.1}
        assert "APLT" in self.jan_live

        d = self.days
        self.days_nov_jan = d[(d > W0) & (d <= JAN)]
        self.days_jan_jul = d[(d > JAN) & (d < LOG)]

        #: Days on which each annotated exit is PRICE-CONSISTENT. The panel is
        #: adjusted CLOSES from a different source than his sheet: his own Nov
        #: marks sit up to 24% from the same-day panel close (SLDP 8.5 vs
        #: 6.86), so a flat close tolerance would manufacture an infeasibility
        #: out of a data-basis mismatch. The tolerance is therefore MEASURED
        #: per name: max(TE_EXIT_PRICE_TOL, the demonstrated sheet-vs-panel
        #: mismatch on the Nov sheet date) — his own record calibrates how far
        #: his recorded prices sit from this panel; nothing is invented.
        nov_marks = {h.ticker: float(h.price) for h in nov.portfolio if h.price}
        self.exit_price_tol: dict[str, float] = {}
        self.exit_feasible: dict[str, pd.DatetimeIndex] = {}
        for tkr, fill in self.known_exits.items():
            basis = abs(nov_marks[tkr] - float(self.px.at[W0, tkr])) \
                / float(self.px.at[W0, tkr])
            tol = max(TE_EXIT_PRICE_TOL, basis)
            close = self.px[tkr].reindex(self.days_nov_jan)
            ok = self.days_nov_jan[(close.sub(fill).abs() / fill) <= tol]
            self.exit_price_tol[tkr] = tol
            self.exit_feasible[tkr] = ok
            if len(ok) == 0:
                raise ValueError(
                    f"{tkr}: no trading day in (2025-11-07, 2026-01-13] has a "
                    f"close within {tol:.0%} of the stated fill {fill} — "
                    f"anchor 3 would be unsatisfiable by construction")

        #: Reference position value: the ONLY two Nov-book names whose July
        #: share counts survive to 2025-11-07 in this family (DKNG, NTLA).
        self.vref = float(np.median([
            self.log_shares["DKNG"] * self.px.at[W0, "DKNG"],
            self.log_shares["NTLA"] * self.px.at[W0, "NTLA"]]))

        #: EW buy-and-hold curve of his 13 Nov picks (the CONVICTION-REPLAY-1
        #: selection benchmark), with APLT on the fixed three-mark convention
        #: (0.80 Nov sheet -> 0.09 Jan sheet -> 0.088 takeout). Terminal value
        #: matches the parent trial's +34.6%; mid-window values are labelled
        #: reconstructed.
        px_b = self.px.copy()
        px_b["APLT"] = _aplt_path(self.days, JAN)
        rel = px_b.loc[W0:, self.nov_book]
        self.ew_curve = (rel / rel.iloc[0]).mean(axis=1)        # 1.0 at W0


def _aplt_path(days: pd.DatetimeIndex, drop: pd.Timestamp) -> pd.Series:
    """APLT synthetic path: 0.80 until `drop`, Jan mark until takeout, cash after.

    There are NO surviving bars; the only observed marks are his two sheets and
    the takeout. The drop date is a sampled dimension because the collapse
    happened at an unknown point inside Nov->Jan.
    """
    s = pd.Series(0.80, index=days, dtype=float)
    s.loc[days >= drop] = TE_APLT_JAN_MARK
    s.loc[days >= APLT_TAKEOUT] = CORPORATE_ACTIONS["APLT"].cash_per_share
    return s


# ───────────────────────────── member generation ────────────────────────────

def _sample_dates(rng: np.random.Generator, pool: pd.DatetimeIndex, n: int = 1):
    idx = rng.choice(len(pool), size=n, replace=True)
    return [pool[int(i)] for i in idx]


def sample_member(index: int, declared: tuple, qubt_arm: float,
                  ctx: Ctx, rng: np.random.Generator) -> tuple[Member | None, str | None]:
    """One generation ATTEMPT. Returns (member, None) or (None, reject_reason).

    A rejection means the sampled history violated an anchor in its declared
    subset (or could not be funded); the caller counts every reason.
    """
    m = Member(
        index=index, seed=[TE_MASTER_SEED, index], declared=tuple(declared),
        qubt_arm=qubt_arm,
        cash0_frac=float(rng.uniform(*TE_CASH_FRAC_RANGE)),
        takeout_treatment=str(rng.choice(TE_TAKEOUT_TREATMENTS)),
        aplt_drop=_sample_dates(rng, ctx.days_nov_jan)[0])

    eps: list[Episode] = []
    buys: list[Episode] = []             # need funding, may defer within window

    def tranche(tkr: str, total: float, entry: pd.Timestamp,
                window_end: pd.Timestamp) -> float:
        """Maybe split a known-final-count position into two tranches.
        Returns the initial share count; queues the top-up as a funded buy."""
        if rng.random() >= TE_TRANCHE_PROB:
            return total
        f = float(rng.uniform(*TE_TRANCHE_INITIAL_FRAC))
        later = ctx.days[(ctx.days > entry) & (ctx.days < window_end)]
        if len(later) == 0 or f >= 0.999:
            return total
        top = Episode(tkr, total * (1 - f), _sample_dates(rng, later)[0], None,
                      "tranche", entry_funded=True)
        buys.append(top)
        return total * f

    # 1) Nov book. Known counts: DKNG/NTLA (log counts reach back — the family
    #    assumption). Everything else sampled around vref.
    for tkr in ctx.nov_book:
        if tkr in ("DKNG", "NTLA"):
            sh = tranche(tkr, ctx.log_shares[tkr], W0, LOG)
            eps.append(Episode(tkr, sh, W0, None, "initial"))
            continue
        value = ctx.vref * float(rng.uniform(*TE_WEIGHT_MULT_RANGE))
        p0 = float(ctx.px.at[W0, tkr]) if tkr != "APLT" else 0.80
        sh = value / p0
        if tkr in ctx.known_exits:                       # TVTX / ALMS / SLDP
            d = _sample_dates(rng, ctx.exit_feasible[tkr])[0]
            eps.append(Episode(tkr, sh, W0, d, "initial", "known_price",
                               ctx.known_exits[tkr]))
        elif tkr in ctx.demotions:                       # market exit by Jan
            d = _sample_dates(rng, ctx.days_nov_jan)[0]
            eps.append(Episode(tkr, sh, W0, d, "initial", "demotion"))
        elif tkr == "APLT":
            eps.append(Episode(tkr, sh, W0, APLT_TAKEOUT, "initial", "takeout"))
        else:                                            # MSTR, FSLR -> Jan-Jul exit
            d = _sample_dates(rng, ctx.days_jan_jul)[0]
            eps.append(Episode(tkr, sh, W0, d, "initial", "exit"))

    # 2) Promotions entered (W0, JAN]. July-book names carry log counts (QUBT
    #    by arm); ELF exits Jan->Jul with a sampled count.
    for tkr in ctx.promotions:
        d = _sample_dates(rng, ctx.days_nov_jan)[0]
        if tkr in ctx.log_shares:
            total = m.qubt_arm if tkr == "QUBT" else ctx.log_shares[tkr]
            sh = tranche(tkr, total, d, LOG)
            buys.append(Episode(tkr, sh, d, None, "promotion", entry_funded=True))
        else:                                            # ELF
            xd = _sample_dates(rng, ctx.days_jan_jul)[0]
            value = ctx.vref * float(rng.uniform(*TE_WEIGHT_MULT_RANGE))
            sh = value / float(ctx.px.at[d, tkr])
            buys.append(Episode(tkr, sh, d, xd, "promotion", "exit",
                               entry_funded=True))

    # 3) Jan->Jul entries at log counts.
    for tkr in ctx.entries_jan_jul:
        d = _sample_dates(rng, ctx.days_jan_jul)[0]
        sh = tranche(tkr, ctx.log_shares[tkr], d, LOG)
        buys.append(Episode(tkr, sh, d, None, "entry", entry_funded=True))

    m.episodes = eps + buys

    reason = _fund_and_mark(m, ctx)
    if reason:
        return None, reason

    # 4) declared-subset anchors — the point of the whole exercise
    m.satisfied, gaps = _check_soft_anchors(m, ctx)
    m.diagnostics.update(gaps)
    for a in m.declared:
        if a not in m.satisfied:
            return None, f"anchor{a}_" + gaps.get(f"anchor{a}_fail", "violated")
    return m, None


def _fund_and_mark(m: Member, ctx: Ctx) -> str | None:
    """Run the cash ledger day by day, then mark NAV = equity + cash daily.

    Purchases execute at close on their sampled day if cash covers them,
    otherwise defer inside their window (dates are free parameters; a history
    that needs a later entry day is still a consistent history). A purchase no
    arrangement can fund rejects the member — counted, never fudged.
    """
    days = ctx.days[(ctx.days >= W0) & (ctx.days <= END)]
    px = ctx.px
    aplt = _aplt_path(ctx.days, m.aplt_drop)

    def close(tkr: str, d: pd.Timestamp) -> float:
        return float(aplt.loc[d] if tkr == "APLT" else px.at[d, tkr])

    equity0 = sum(e.shares * close(e.ticker, W0)
                  for e in m.episodes if e.entry == W0)
    m.cash0 = m.cash0_frac / (1.0 - m.cash0_frac) * equity0

    pending = sorted([e for e in m.episodes if e.entry_funded],
                     key=lambda e: e.entry)
    sells: dict[pd.Timestamp, list[Episode]] = {}
    for e in m.episodes:
        if e.exit is not None:
            sells.setdefault(e.exit, []).append(e)

    cash = m.cash0
    cash_series = pd.Series(0.0, index=days)
    reinvest: list[Episode] = []
    for d in days:
        for e in sells.get(d, []):
            if e.exit_kind == "takeout":
                proceeds = e.shares * CORPORATE_ACTIONS["APLT"].cash_per_share
                cash += _apply_takeout(m, ctx, d, proceeds, reinvest)
            else:
                fill = e.exit_price if e.exit_price is not None else close(e.ticker, d)
                cash += e.shares * fill
        still: list[Episode] = []
        for e in pending:
            if e.entry > d:
                still.append(e)
                continue
            # a promotion is on the Jan sheet, so its entry may never defer
            # past the sheet date — even when it also has a later exit (ELF)
            window_end = (JAN if e.entry_kind == "promotion"
                          else e.exit if e.exit is not None else LOG)
            cost = e.shares * close(e.ticker, d)
            if cash + 1e-9 >= cost:
                e.deferred_days += int((d - e.entry).days > 0)
                e.entry = d
                cash -= cost
            elif d >= window_end:
                return "cash_infeasible"
            else:
                still.append(e)          # defer to a later day in the window
        pending = still
        cash_series.loc[d] = cash
    if pending:
        return "cash_infeasible"

    m.episodes = m.episodes + reinvest
    shares = pd.DataFrame(0.0, index=days,
                          columns=sorted({e.ticker for e in m.episodes}))
    for e in m.episodes:
        stop = e.exit if e.exit is not None else END + pd.Timedelta(days=1)
        mask = (days >= e.entry) & (days < stop)
        shares.loc[mask, e.ticker] += e.shares

    marks = px.reindex(days)[shares.columns].copy()
    if "APLT" in marks:
        marks["APLT"] = aplt.reindex(days)
    equity = (shares * marks).sum(axis=1)
    m.cash = cash_series
    m.nav = equity + cash_series

    # anchor 6 — the cash band, checked where the record pins the book
    for label, d in (("jan", JAN), ("jul", LOG)):
        frac = float(m.cash.asof(d) / m.nav.asof(d))
        m.diagnostics[f"cash_frac_{label}"] = frac
        if not (-1e-9 <= frac <= TE_CASH_FRAC_RANGE[1] + 1e-9):
            return f"cash_band_{label}"
    return None


def _apply_takeout(m: Member, ctx: Ctx, d: pd.Timestamp, proceeds: float,
                   reinvest: list) -> float:
    """Anchor 10 proceeds treatment. Returns the amount left as idle cash."""
    if m.takeout_treatment == "spy":
        reinvest.append(Episode("SPY", proceeds / float(ctx.px.at[d, "SPY"]),
                                d, None, "reinvest"))
        return 0.0
    if m.takeout_treatment == "pro_rata":
        # Only into positions that EXIT before the log date: the 2026-07-11
        # share counts are an anchor, and slivers added to a July holding
        # would violate it. Slivers in still-live-but-exiting names wash out
        # at their exit. If nothing qualifies, fall back to idle cash.
        live = [e for e in m.episodes
                if e.exit is not None and e.entry <= d < e.exit
                and e.exit_kind in ("exit", "demotion")]
        if not live:
            m.diagnostics["takeout_pro_rata_fell_back_to_cash"] = True
            return proceeds
        vals = np.array([e.shares * float(ctx.px.at[d, e.ticker]) for e in live])
        for e, v in zip(live, vals / vals.sum()):
            reinvest.append(Episode(e.ticker,
                                    proceeds * v / float(ctx.px.at[d, e.ticker]),
                                    d, e.exit, "reinvest", "wash"))
        return 0.0
    return proceeds                      # idle_cash


def _check_soft_anchors(m: Member, ctx: Ctx) -> tuple[tuple, dict]:
    """Anchors 7/8/9 against the member's dollar NAV path.

    The covered window is checked exactly; the uncovered months are ONE
    bounded free parameter (gap return) per anchor, and its required value is
    recorded so the report can say how much work the gap does.
    """
    lo, hi = TE_GAP_RETURN_BOUNDS
    nav0 = float(m.nav.asof(W0))
    out, info = [], {}

    # 7: end level ~ $35,742 on some day in the sweep window; the ~1yr start
    #    (~mid-2025, always pre-coverage) must be reachable at ~$20,577.
    g7 = nav0 / ANCHOR7_START_D - 1.0
    info["anchor7_required_gap"] = g7
    w = m.nav.loc[TE_ANCHOR7_END_WINDOW[0]:TE_ANCHOR7_END_WINDOW[1]]
    hits = w[(w - ANCHOR7_END_D).abs() <= TE_DOLLAR_TOL * ANCHOR7_END_D]
    info["anchor7_end_days_hit"] = int(len(hits))
    if len(hits) == 0:
        info["anchor7_fail"] = "end_level"
    elif not (lo <= g7 <= hi):
        info["anchor7_fail"] = "gap_bounds"
    else:
        out.append(7)

    # 8: calendar-2025 = +115%; covered part is W0 -> last 2025 close.
    r_cov = float(m.nav.asof(DEC31) / nav0) - 1.0
    g8 = (1.0 + TE_ANCHOR8_PCT) / (1.0 + r_cov) - 1.0
    info["anchor8_covered_return"] = r_cov
    info["anchor8_required_gap"] = g8
    if lo <= g8 <= hi:
        out.append(8)
    else:
        info["anchor8_fail"] = "gap_bounds"

    # 9: $45k at the window end; the $25k start is pre-coverage.
    g9 = nav0 / TE_ANCHOR9_START - 1.0
    nav_end = float(m.nav.asof(END))
    info["anchor9_required_gap"] = g9
    info["anchor9_nav_end"] = nav_end
    if abs(nav_end - TE_ANCHOR9_END) > TE_DOLLAR_TOL * TE_ANCHOR9_END:
        info["anchor9_fail"] = "end_level"
    elif not (lo <= g9 <= hi):
        info["anchor9_fail"] = "gap_bounds"
    else:
        out.append(9)
    return tuple(out), info


def validate_member(m: Member, ctx: Ctx) -> list[str]:
    """Every anchor in the member's declared subset, re-checked from scratch.

    The generator calls this on every ACCEPTED member (belt and braces); the
    tests tamper with a member and assert the violation is caught. A member
    violating its declared subset must never survive generation silently.
    """
    v: list[str] = []
    by_t: dict[str, float] = {}
    for e in m.episodes:
        if e.exit is None and e.exit_kind != "wash":
            by_t[e.ticker] = by_t.get(e.ticker, 0.0) + e.shares
    expect = dict(ctx.log_shares)
    expect["QUBT"] = m.qubt_arm
    for tkr, sh in expect.items():
        if abs(by_t.get(tkr, 0.0) - sh) > 1e-6:
            v.append(f"anchor4: {tkr} shares {by_t.get(tkr, 0.0):g} != {sh:g} "
                     f"at the 2026-07-11 log")
    for t in set(by_t) - set(expect) - {"SPY"}:
        v.append(f"anchor4: {t} still held at the log date but absent from it")

    for e in m.episodes:
        if e.exit_kind == "known_price":
            if not (W0 < e.exit <= JAN):
                v.append(f"anchor3: {e.ticker} exit {e.exit.date()} outside "
                         f"(2025-11-07, 2026-01-13]")
            close = float(ctx.px.at[e.exit, e.ticker])
            tol = ctx.exit_price_tol[e.ticker]
            if abs(close - e.exit_price) / e.exit_price > tol:
                v.append(f"anchor3: {e.ticker} stated fill {e.exit_price} is "
                         f"{abs(close - e.exit_price) / e.exit_price:.1%} from "
                         f"the {e.exit.date()} close {close:.2f}")
        if e.entry_kind == "promotion" and e.entry > JAN:
            v.append(f"anchor2: {e.ticker} entered {e.entry.date()}, after the "
                     f"Jan sheet that lists it")

    if not (TE_CASH_FRAC_RANGE[0] <= m.cash0_frac <= TE_CASH_FRAC_RANGE[1]):
        v.append("anchor6: initial cash fraction outside the swept range")
    if m.nav is not None:
        for label, d in (("jan", JAN), ("jul", LOG)):
            frac = float(m.cash.asof(d) / m.nav.asof(d))
            if not (-1e-9 <= frac <= TE_CASH_FRAC_RANGE[1] + 1e-9):
                v.append(f"anchor6: cash fraction {frac:.1%} at {d.date()}")
        sat, _ = _check_soft_anchors(m, ctx)
        for a in m.declared:
            if a not in sat:
                v.append(f"anchor{a}: declared but not satisfied by this history")
    return v


# ───────────────────────────── ensemble runner ──────────────────────────────

def generate_ensemble(ctx: Ctx | None = None, *,
                      members_per_arm: int = TE_MEMBERS_PER_ARM,
                      subsets: tuple = TE_SUBSETS,
                      qubt_arms: tuple = TE_QUBT_ARMS,
                      max_attempts: int = TE_MAX_ATTEMPTS_PER_MEMBER) -> dict:
    """N = len(subsets) x len(qubt_arms) x members_per_arm sampled histories.

    Every (declared subset, QUBT arm) cell gets its own members; every
    rejection is counted by reason; an arm that fills ZERO members is a
    FINDING (that subset of anchors admits no history in this family), not an
    error.
    """
    ctx = ctx or Ctx()
    members: list[Member] = []
    rejections: dict[str, dict[str, int]] = {}
    unfilled: dict[str, int] = {}
    idx = 0
    for declared in subsets:
        for arm in qubt_arms:
            key = f"{{{','.join(map(str, declared))}}}|QUBT{arm:g}"
            rej = rejections.setdefault(key, {})
            for _ in range(members_per_arm):
                rng = np.random.default_rng([TE_MASTER_SEED, idx])
                got = None
                for _a in range(max_attempts):
                    m, reason = sample_member(idx, declared, arm, ctx, rng)
                    if m is not None:
                        bad = validate_member(m, ctx)
                        if bad:      # generator bug, not a sampling outcome
                            raise AssertionError(
                                f"accepted member failed validation: {bad}")
                        got = m
                        break
                    rej[reason] = rej.get(reason, 0) + 1
                if got is None:
                    unfilled[key] = unfilled.get(key, 0) + 1
                else:
                    members.append(got)
                idx += 1
    return {"members": members, "rejections": rejections, "unfilled": unfilled,
            "n_slots": idx, "ctx": ctx}


# ─────────────────────────── per-member evaluation ──────────────────────────

def exit_costs(m: Member, ctx: Ctx) -> dict:
    """Q3 — each annotated exit's cost in NAV terms, for THIS member.

    cost = (what the sold shares would be worth at the window end) minus (what
    the proceeds actually earned riding the member's own subsequent book),
    as a percentage of the member's terminal NAV. Positive = the exit cost
    NAV; negative = the exit saved NAV. This charges the proceeds with the
    return they actually earned, not zero.
    """
    nav_end = float(m.nav.asof(END))
    out = {}
    for e in m.episodes:
        if e.exit_kind != "known_price":
            continue
        held = e.shares * float(ctx.px.at[END, e.ticker])
        proceeds = e.shares * e.exit_price
        book_after = nav_end / float(m.nav.asof(e.exit)) - 1.0
        actual = proceeds * (1.0 + book_after)
        out[e.ticker] = {
            "cost_pts_of_terminal_nav": 100.0 * (held - actual) / nav_end,
            "exit_date": str(e.exit.date()),
        }
    out["total_pts"] = float(sum(d["cost_pts_of_terminal_nav"]
                                 for d in out.values() if isinstance(d, dict)))
    return out


def attribution(m: Member, ctx: Ctx) -> dict:
    """Q1 — decompose each headline the member satisfies, additively in pts:

        headline = selection + weighting/trading + gap(residual)

    selection        = EW buy-and-hold of his 13 Nov picks over the covered
                       part of the headline window (CONVICTION-REPLAY-1's
                       benchmark),
    weighting/trading= member's as-traded covered return minus selection,
    gap              = headline minus the covered as-traded return — the part
                       the uncovered months must supply (includes the cross
                       term; it is a residual attribution, stated as such).
    """
    nav0 = float(m.nav.asof(W0))
    out = {}
    if 7 in m.satisfied:
        w = m.nav.loc[TE_ANCHOR7_END_WINDOW[0]:TE_ANCHOR7_END_WINDOW[1]]
        hits = w[(w - ANCHOR7_END_D).abs() <= TE_DOLLAR_TOL * ANCHOR7_END_D]
        rows = []
        for d in hits.index:            # every feasible end date, no preference
            r_at = float(hits.loc[d]) / nav0 - 1.0
            r_sel = float(ctx.ew_curve.asof(d)) - 1.0
            rows.append({"as_traded": r_at, "selection": r_sel})
        h = 100.0 * TE_ANCHOR7_PCT
        out["headline_73.7"] = _attr_rows(rows, h)
    if 8 in m.satisfied:
        r_at = float(m.nav.asof(DEC31)) / nav0 - 1.0
        r_sel = float(ctx.ew_curve.asof(DEC31)) - 1.0
        out["headline_115"] = _attr_rows(
            [{"as_traded": r_at, "selection": r_sel}], 100.0 * TE_ANCHOR8_PCT)
    return out


def _attr_rows(rows: list[dict], headline_pts: float) -> dict:
    sel = [100 * r["selection"] for r in rows]
    wt = [100 * (r["as_traded"] - r["selection"]) for r in rows]
    gap = [headline_pts - 100 * r["as_traded"] for r in rows]
    rng = lambda x: [float(min(x)), float(max(x))]
    return {"selection_pts": rng(sel), "weighting_trading_pts": rng(wt),
            "gap_pts": rng(gap), "headline_pts": headline_pts}


def as_traded_stats(m: Member) -> dict:
    """Q4 — the bounds FACTORIAL-PM-1 consumes for the B1 as-traded column."""
    nav = m.nav.loc[W0:END]
    dd = float((nav / nav.cummax() - 1.0).min())
    war = m.nav.loc[TE_WAR_WINDOW[0]:TE_WAR_WINDOW[1]]
    war_dd = float((war / war.cummax() - 1.0).min()) if len(war) else float("nan")
    return {
        "total_return": float(nav.asof(END) / nav.asof(W0) - 1.0),
        "max_drawdown": dd, "war_window_drawdown": war_dd,
        "terminal_wealth_ratio": float(nav.asof(END) / nav.asof(W0)),
    }


# ───────────────────────────── the grading rule ─────────────────────────────

def _magnitude_class(x: float) -> str:
    small, large = TE_MAGNITUDE_CLASS_EDGES
    ax = abs(x)
    return "small" if ax < small else ("moderate" if ax < large else "large")


def grade(values_by_subset: dict[str, list[float]], *, unit: str,
          ask: str) -> dict:
    """The frozen rule: `ensemble_robust` iff SIGN and magnitude class agree
    across every member of every maximal consistent subset; else `DATA_NEEDED`
    with the minimal exact ask.

    The output contains ONLY ranges and counts — no member value is ever
    quoted as the answer, no subset is preferred, nothing is 'most likely'.
    """
    pooled = [v for vs in values_by_subset.values() for v in vs]
    counts = {k: len(v) for k, v in values_by_subset.items()}
    if not pooled:
        return {"label": "DATA_NEEDED", "unit": unit, "range": None,
                "member_counts": counts, "minimal_ask": ask,
                "why": "no consistent member produced this quantity"}
    signs = {np.sign(round(v, 9)) for v in pooled}
    classes = {_magnitude_class(v) for v in pooled}
    robust = len(signs) == 1 and len(classes) == 1
    out = {
        "label": "ensemble_robust" if robust else "DATA_NEEDED",
        "unit": unit,
        "range": {"min": float(min(pooled)), "max": float(max(pooled)),
                  "p05": float(np.percentile(pooled, 5)),
                  "p50": float(np.percentile(pooled, 50)),
                  "p95": float(np.percentile(pooled, 95))},
        "n_members": len(pooled),
        "member_counts": counts,
        "sign_classes": sorted({("+" if s > 0 else "-" if s < 0 else "0")
                                for s in signs}),
        "magnitude_classes": sorted(classes),
    }
    if not robust:
        out["minimal_ask"] = ask
    return out


# ─────────────────────────── ensemble aggregation ───────────────────────────

def summarize_member(m: Member, ctx: Ctx) -> dict:
    """Checkpoint row for one member. Raw material, labelled SYNTHETIC —
    never quote one row as the answer; the range across rows is the result."""
    d = m.diagnostics
    return {
        "SYNTHETIC": True,
        "index": m.index, "seed": m.seed,
        "declared": list(m.declared), "satisfied": list(m.satisfied),
        "qubt_arm": m.qubt_arm, "cash0_frac": m.cash0_frac,
        "takeout_treatment": m.takeout_treatment,
        "aplt_drop": str(m.aplt_drop.date()),
        "known_exit_dates": {e.ticker: str(e.exit.date())
                             for e in m.episodes
                             if e.exit_kind == "known_price"},
        "nav": {"2025-11-07": float(m.nav.asof(W0)),
                "2025-12-31": float(m.nav.asof(DEC31)),
                "2026-01-13": float(m.nav.asof(JAN)),
                "2026-07-11": float(m.nav.asof(LOG)),
                "2026-08-10": float(m.nav.asof(END))},
        "cash_frac": {"jan": d.get("cash_frac_jan"),
                      "jul": d.get("cash_frac_jul")},
        "required_gaps": {"7": d.get("anchor7_required_gap"),
                          "8": d.get("anchor8_required_gap"),
                          "9": d.get("anchor9_required_gap")},
        "anchor7_end_days_hit": d.get("anchor7_end_days_hit"),
        "anchor8_covered_return": d.get("anchor8_covered_return"),
        "attribution": attribution(m, ctx),
        "exit_costs": exit_costs(m, ctx),
        "as_traded": as_traded_stats(m),
    }


def _arm_key(m: Member) -> str:
    return "{" + ",".join(map(str, m.declared)) + "}"


def _collect(rows: list[dict], path: list, arm_of: list[str]) -> dict:
    """values-by-arm for grade(): each member contributes every value found
    at `path` (a per-member [min,max] contributes both endpoints, so within-
    member ambiguity must ALSO agree for a conclusion to be robust)."""
    out: dict[str, list] = {}
    for row, arm in zip(rows, arm_of):
        node = row
        try:
            for p in path:
                node = node[p]
        except (KeyError, TypeError):
            continue
        vals = node if isinstance(node, list) else [node]
        out.setdefault(arm, []).extend(float(v) for v in vals)
    return out


ASK_CSV = ("broker CSV export — every transaction (date, ticker, shares, "
           "fill, cash movement) Aug-2025 -> Aug-2026, ~2 minutes")


def answer_questions(ens: dict) -> dict:
    """The frozen Q1-Q4, graded by the frozen rule. Output contains ONLY
    ranges, counts and labels — no member is quoted as the answer."""
    ctx: Ctx = ens["ctx"]
    members: list[Member] = ens["members"]
    rows = [summarize_member(m, ctx) for m in members]
    arms = [_arm_key(m) for m in members]

    # Q1 — headline attribution, one grade per component per headline anchor
    q1 = {}
    for head, key in (("headline_73.7", "headline_73.7"),
                      ("headline_115", "headline_115")):
        comp = {}
        for c in ("selection_pts", "weighting_trading_pts", "gap_pts"):
            comp[c] = grade(_collect(rows, ["attribution", key, c], arms),
                            unit="pts of headline",
                            ask=ASK_CSV + f" — resolves the {c} share of the "
                                          f"{head} headline (Q1)")
        q1[head] = comp
    q1["decomposition"] = ("headline = selection (EW buy-and-hold of his 13 "
                           "Nov picks, covered window) + weighting/trading "
                           "(as-traded minus selection) + gap (the part the "
                           "uncovered pre-2025-11 months must supply; residual, "
                           "includes the cross term)")

    # Q2 — the anchor-consistency matrix
    matrix = {}
    for declared in TE_SUBSETS:
        for arm in TE_QUBT_ARMS:
            key = f"{{{','.join(map(str, declared))}}}|QUBT{arm:g}"
            got = [r for r, m in zip(rows, members)
                   if m.declared == declared and m.qubt_arm == arm]
            entry = {
                "n_accepted": len(got),
                "n_slots": TE_MEMBERS_PER_ARM,
                "admits_a_consistent_history": len(got) > 0,
                "rejections": ens["rejections"].get(key, {}),
                "unfilled_slots": ens["unfilled"].get(key, 0),
            }
            if got:
                for a in ("7", "8", "9"):
                    gs = [r["required_gaps"][a] for r in got
                          if r["required_gaps"][a] is not None
                          and int(a) in r["satisfied"]]
                    if gs:
                        entry[f"required_gap_anchor{a}"] = {
                            "min": float(min(gs)), "max": float(max(gs)),
                            "median": float(np.median(gs)),
                            "bounds": list(TE_GAP_RETURN_BOUNDS)}
            matrix[key] = entry
    witnessed = sorted({tuple(sorted(m.satisfied)) for m in members},
                       key=len, reverse=True)
    q2 = {
        "matrix": matrix,
        "witnessed_satisfied_sets": [list(s) for s in witnessed],
        "maximal_consistent_subset": list(witnessed[0]) if witnessed else [],
        "reading": ("a subset 'admits' if >= 1 sampled history satisfied every "
                    "anchor in it; an empty arm is a finding about the anchors, "
                    "not an error. The required-gap stats say how much work the "
                    "uncovered pre-2025-11 months must do."),
    }

    # Q3 — exit costs in NAV terms
    q3 = {}
    for tkr in ctx.known_exits:
        q3[tkr] = grade(
            _collect(rows, ["exit_costs", tkr, "cost_pts_of_terminal_nav"],
                     arms),
            unit="pts of terminal NAV (positive = the exit cost him)",
            ask=ASK_CSV + f" — pins the {tkr} position size; resolves Q3")
    q3["total"] = grade(_collect(rows, ["exit_costs", "total_pts"], arms),
                        unit="pts of terminal NAV",
                        ask=ASK_CSV + " — resolves Q3's total exit cost")
    q3["definition"] = ("cost = (sold shares held to 2026-08-10) minus (the "
                        "proceeds riding the member's own subsequent book), "
                        "as % of terminal NAV — proceeds are charged with the "
                        "return they actually earned, not zero")

    # Q4 — as-traded bounds for FACTORIAL-PM-1
    q4 = {}
    for stat, unit in (("total_return", "fraction, 2025-11-07 -> 2026-08-10"),
                       ("max_drawdown", "fraction"),
                       ("war_window_drawdown", "fraction"),
                       ("terminal_wealth_ratio", "x")):
        q4[stat] = grade(_collect(rows, ["as_traded", stat], arms),
                         unit=unit,
                         ask=ASK_CSV + f" — pins the as-traded {stat} (Q4)")
    q4["consumer"] = ("FACTORIAL-PM-1 B1 as-traded column: use the RANGE with "
                      "its label, never a point (prereg §1)")

    return {"Q1": q1, "Q2": q2, "Q3": q3, "Q4": q4, "member_rows": rows}
