"""GRAPH_PROPAGATION_v1 — co-coverage peer return as a live selector.

WHAT THIS IS
============
The only mechanism `ANALYST-COCOVERAGE-GRAPH-1` licensed. Two firms are linked
when the same brokerage covered both in the trailing year; a firm's signal is
the equal-weighted mean of its peers' just-finished month return. High peer
return predicts high own return next month (spillover, not reversal).

IT IS DELIBERATELY THE PLAINEST VERSION. Three refinements were measured and
all three returned zero: reliability-weighted edges (-0.00008 +/- 0.00052, a
precisely measured zero), leader->laggard asymmetry (+0.0025 +/- 0.0037), and
52-week-high conditioning (-0.0006). Nothing fancier earned its place, and the
GNN the programme was pointed at stays unbuilt because the three kinds of
structure a GNN exists to exploit are exactly the three that measured zero.

WHAT LICENSED IT, AND WHAT DID NOT
==================================
Screen `ANALYST-COCOVERAGE-GRAPH-1`, spec_hash 0e1578bd0410653b, 131 months:

    peer_eq                                +0.0227 IC (t 2.35)
    paired vs the firm's OWN momentum      +0.0155     (t 2.57)
    paired vs plain SIC2 industry momentum +0.0088     (t 2.24)
    cross-industry links ONLY              +0.0159     (p 0.043)

The last two are why this is not sector momentum wearing a graph as a costume.

It is a SCREEN, so it licenses BUILDING this, never claiming an edge from it.
Its own IC sits under its own MDE80 (0.0227 vs 0.0271, ~60-70% power): the
honest reading is "worth running forward", not "established".

WHY IT IS ITS OWN BOOK AND NOT A COMPOSITE WEIGHT
=================================================
All ten arena books select on `composite_top_k` over one signal, and
`COMPOSITE_WEIGHTS` coverage is {"1": 206, "6": 1} -- 99.5% of names carry
exactly 12-1 momentum alone. Folding this in as another 0.5 weight would hide
the only thing worth testing: whether its errors are DIFFERENT errors. It
arrives as a separate PRODUCT_EXPERIMENT book or not at all.

THE LIVE PATH, AND THE ONE THING THAT NEARLY BROKE IT
=====================================================
The screen ran on IBES `amaskcd` -- an individual analyst id that exists only
in a WRDS research dataset. Production has yfinance's firm-attributed
upgrades/downgrades. Two amendments closed that gap before a line of this was
written: the effect survives at FIRM granularity (+0.0218, t 3.05) and on
ACTIONS ONLY (+0.0213, t 3.00), which are the two reductions a live feed forces.

Vendor depth was measured 2026-08-24 over the actual 179-name universe: median
14.4 years of history, median 17 covering firms per name in the trailing year
(IBES's median was 14), and 98.3% of names carry a usable graph row.

But three names -- META, WELL, CAT -- returned an EMPTY trailing window and no
error. Their action history is truncated in the vendor's data (META's stopped
2024-09-30 while 62 analysts rate it today, per the live `recommendations`
summary). That is not coverage ceasing; it is the feed lying by omission. A
graph that trusts it drops META out of the ranking silently, which is why
`STALE_FEED_DAYS` is a refusal and not a log line.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── the frozen strategy contract ────────────────────────────────────────────
#
# A PRODUCT_EXPERIMENT needs this BEFORE its first decision: policy, inputs,
# costs, fill convention, objective. No significance gate and no 24-month floor
# apply -- those govern CLAIMS -- but the contract must be tamper-evident, so
# it is hashed and the hash goes in every receipt.
#
# The parameters are NOT free. They are transcribed from the screen that
# licensed the signal; changing one makes this a different mechanism than the
# one with evidence behind it, so each carries where it came from.

CONTRACT: dict[str, Any] = {
    "book_id": "GRAPH_PROPAGATION_v1",
    "licence": "PRODUCT_EXPERIMENT",
    "licensed_by": {
        "trial": "ANALYST-COCOVERAGE-GRAPH-1",
        "spec_hash": "0e1578bd0410653b",
        "primary_ic": 0.0227,
        "t_stat": 2.35,
        "n_effective": "131 MONTHS (date blocks, CANON 58)",
        "mde80": 0.0271,
        "power_note": (
            "observed IC is BELOW its own MDE80, so this is ~60-70% powered. "
            "Licenses building and running forward; never a claim of alpha."),
        "amendments_that_made_it_live": {
            "AMENDMENT-3 firm granularity": "+0.0218 (t 3.05)",
            "AMENDMENT-4 actions only": "+0.0213 (t 3.00)",
        },
    },
    "objective": "terminal wealth under the book's declared personality",
    "selection": "graph_peer_top_k",
    "signal": "peer_eq — equal-weighted mean of DISTINCT peers' month-t return",
    "target": "own return month t+1",
    "direction": "LONG the high peer-return names (spillover, not reversal)",
    # Transcribed from SPEC. `min_shared=1` because the screen's edge is
    # co-coverage EXISTING, not its intensity: `peer_shared` (weighting by the
    # number of shared coverers) was an arm and it did not beat `peer_eq`.
    "coverage_window_months": 12,
    "min_shared_firms": 1,
    "min_peers": 3,
    "rebalance": "monthly_calendar",
    "execution": "next_session_open",
    "transaction_cost_bps": 5,
    "slippage_bps": 1,
    "inputs": {
        "coverage": "yfinance upgrades_downgrades (firm-attributed ACTIONS)",
        "returns": "arena day-state month-over-month total return",
    },
    "refusals": {
        "stale_feed_days": 120,
        "min_usable_fraction": 0.80,
    },
    "what_this_cannot_show": (
        "That the signal is alpha. The screen behind it is an IC screen with "
        "no costs, no capacity and no portfolio construction, and it was "
        "under-powered by its own design."),
}


def contract_hash() -> str:
    """Tamper-evident identity for the frozen contract."""
    return hashlib.sha256(
        json.dumps(CONTRACT, sort_keys=True, separators=(",", ":"),
                   default=str).encode()).hexdigest()[:16]


#: A name whose action feed has been silent this long is not "quietly covered",
#: it is a name the vendor has stopped reporting. Set at 120 days because the
#: measured universe puts the 95th percentile of genuine silence at ~49 days
#: while the three truncated names sat at 675-689. Nothing lands in between,
#: so the threshold is not doing delicate work -- it separates two populations
#: that are three weeks and two years apart.
STALE_FEED_DAYS: int = int(CONTRACT["refusals"]["stale_feed_days"])

#: Below this share of the universe carrying a usable graph row, the ranking is
#: over a DIFFERENT universe wearing the same name. Same reasoning, and the
#: same number, as the arena's `min_priced_fraction`.
MIN_USABLE_FRACTION: float = float(
    CONTRACT["refusals"]["min_usable_fraction"])


class GraphUnavailable(RuntimeError):
    """The graph cannot be built well enough to rank on.

    Raised rather than returning a thin ranking, because a peer signal computed
    over a decimated universe is not a worse version of this signal -- it is a
    different one, and it would be recorded under this book's name.
    """


@dataclass
class CoverageRow:
    ticker: str
    firms: frozenset[str]
    newest_action: Optional[str]
    stale_days: Optional[int]
    status: str                       # OK | STALE | EMPTY | ERROR
    detail: str = ""


@dataclass
class GraphSignal:
    """One month's ranking, plus everything needed to audit it."""
    as_of: str
    contract_hash: str
    scores: dict[str, float] = field(default_factory=dict)
    n_peers: dict[str, int] = field(default_factory=dict)
    excluded: dict[str, str] = field(default_factory=dict)
    usable_fraction: float = 0.0
    universe_n: int = 0

    def to_receipt(self) -> dict:
        return {
            "as_of": self.as_of,
            "book_id": CONTRACT["book_id"],
            "contract_hash": self.contract_hash,
            "licence": CONTRACT["licence"],
            "universe_n": self.universe_n,
            "ranked_n": len(self.scores),
            "usable_fraction": round(self.usable_fraction, 4),
            "excluded": dict(sorted(self.excluded.items())),
            "n_peers_median": (
                sorted(self.n_peers.values())[len(self.n_peers) // 2]
                if self.n_peers else 0),
        }


# ── coverage ────────────────────────────────────────────────────────────────


def read_coverage(ticker: str, as_of, window_months: int | None = None
                  ) -> CoverageRow:
    """Which FIRMS acted on this name inside the trailing window.

    Point-in-time by construction: anything stamped after `as_of` is dropped
    before the window is applied, so a backfilled action cannot inform a
    decision that preceded it.
    """
    import pandas as pd

    win = int(window_months or CONTRACT["coverage_window_months"])
    as_of = pd.Timestamp(as_of)
    if as_of.tz is None:
        as_of = as_of.tz_localize("UTC")

    try:
        import yfinance as yf
        df = yf.Ticker(ticker).upgrades_downgrades
    except Exception as e:                                # pragma: no cover
        return CoverageRow(ticker, frozenset(), None, None, "ERROR",
                           f"{type(e).__name__}: {e}")

    if df is None or not hasattr(df, "empty") or df.empty:
        return CoverageRow(ticker, frozenset(), None, None, "EMPTY",
                           "vendor returned no upgrade/downgrade history")

    df = df.reset_index()
    dcols = [c for c in df.columns if "date" in str(c).lower()]
    if not dcols or "Firm" not in df.columns:
        return CoverageRow(ticker, frozenset(), None, None, "ERROR",
                           f"unexpected columns {list(df.columns)}")

    df["_d"] = pd.to_datetime(df[dcols[0]], utc=True, errors="coerce")
    past = df.dropna(subset=["_d"])
    past = past[past["_d"] <= as_of]
    if past.empty:
        return CoverageRow(ticker, frozenset(), None, None, "EMPTY",
                           "no actions at or before as_of")

    newest = past["_d"].max()
    stale = int((as_of - newest).days)
    if stale > STALE_FEED_DAYS:
        # THE META CASE. The vendor's action history is truncated while the
        # name is still covered by dozens of analysts. Returning an empty peer
        # set here would drop a mega-cap out of the ranking in silence.
        return CoverageRow(
            ticker, frozenset(), str(newest.date()), stale, "STALE",
            f"action feed silent {stale}d (> {STALE_FEED_DAYS}d); the vendor "
            f"has stopped reporting this name, which is not the same as the "
            f"name having no coverage")

    win_lo = as_of - pd.DateOffset(months=win)
    recent = past[past["_d"] >= win_lo]
    firms = frozenset(str(f).strip() for f in recent["Firm"].dropna()
                      if str(f).strip())
    return CoverageRow(ticker, firms, str(newest.date()), stale, "OK")


# ── the graph ───────────────────────────────────────────────────────────────


def peer_scores(coverage: dict[str, frozenset[str]],
                returns: dict[str, float],
                min_shared: int | None = None,
                min_peers: int | None = None,
                ) -> tuple[dict[str, float], dict[str, int]]:
    """`peer_eq` for every name that has enough peers.

    Two names are peers when at least `min_shared` brokerages covered both. The
    score is the EQUAL-weighted mean of those peers' returns -- equal-weighted
    over DISTINCT peers, so two firms linked by five shared brokers count once.

    That distinction is not cosmetic. The screen's first implementation
    accumulated leave-one-out sums per coverer, which silently computes the
    SHARED-COUNT-weighted mean; `peer_eq` and `peer_shared` would have been one
    arm reported as two. They are separate arms here for the same reason.
    """
    min_shared = int(CONTRACT["min_shared_firms"] if min_shared is None
                     else min_shared)
    min_peers = int(CONTRACT["min_peers"] if min_peers is None else min_peers)

    names = [t for t in coverage if t in returns and coverage[t]]
    by_firm: dict[str, list[str]] = {}
    for t in names:
        for f in coverage[t]:
            by_firm.setdefault(f, []).append(t)

    shared: dict[str, dict[str, int]] = {t: {} for t in names}
    for members in by_firm.values():
        if len(members) < 2:
            continue
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                shared[a][b] = shared[a].get(b, 0) + 1
                shared[b][a] = shared[b].get(a, 0) + 1

    scores: dict[str, float] = {}
    n_peers: dict[str, int] = {}
    for t in names:
        peers = [p for p, k in shared[t].items() if k >= min_shared]
        n_peers[t] = len(peers)
        if len(peers) < min_peers:
            continue
        scores[t] = sum(returns[p] for p in peers) / len(peers)
    return scores, n_peers


def build_signal(universe: list[str], returns: dict[str, float], as_of,
                 coverage_reader=read_coverage) -> GraphSignal:
    """The month's ranking, or a refusal.

    `coverage_reader` is injected so this is testable without a vendor.
    """
    import pandas as pd

    as_of_s = str(pd.Timestamp(as_of).date())
    cov: dict[str, frozenset[str]] = {}
    excluded: dict[str, str] = {}

    for t in universe:
        row = coverage_reader(t, as_of)
        if row.status == "OK" and row.firms:
            cov[t] = row.firms
        else:
            excluded[t] = f"{row.status}: {row.detail}" if row.detail \
                else row.status

    scores, n_peers = peer_scores(cov, returns)
    for t in universe:
        if t not in scores and t not in excluded:
            excluded[t] = (
                f"thin: {n_peers.get(t, 0)} peers < {CONTRACT['min_peers']}")

    usable = len(scores) / len(universe) if universe else 0.0
    if usable < MIN_USABLE_FRACTION:
        raise GraphUnavailable(
            f"only {len(scores)}/{len(universe)} names ({usable:.1%}) carry a "
            f"usable graph row, below {MIN_USABLE_FRACTION:.0%}. Ranking this "
            f"cross-section would record a DIFFERENT universe under "
            f"{CONTRACT['book_id']}'s name. Top exclusion reasons: "
            f"{_top_reasons(excluded)}")

    return GraphSignal(as_of=as_of_s, contract_hash=contract_hash(),
                       scores=scores, n_peers=n_peers, excluded=excluded,
                       usable_fraction=usable, universe_n=len(universe))


def _top_reasons(excluded: dict[str, str], k: int = 3) -> str:
    counts: dict[str, int] = {}
    for v in excluded.values():
        counts[v.split(":")[0]] = counts.get(v.split(":")[0], 0) + 1
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:k]
    return ", ".join(f"{r} x{n}" for r, n in top) or "none"


# ── health ──────────────────────────────────────────────────────────────────


def health() -> dict:
    """Health surface. A module with no health row is a module nobody can see
    fail; `alpaca_mirror_status` was one for a week (2026-08-24)."""
    return {
        "book_id": CONTRACT["book_id"],
        "licence": CONTRACT["licence"],
        "contract_hash": contract_hash(),
        "status": "AWAITING_REGISTRATION",
        "reason": (
            "the book cannot enter arena_books_v1.yaml until the ten live "
            "seeds migrate to per-book identity on their next arena pass. "
            "Adding it before then changes the whole-file config_hash, which "
            "is what the LEGACY seeds are verified against, and "
            "assert_config_current refuses to run AND refuses to migrate."),
        "licensed_by": CONTRACT["licensed_by"]["trial"],
    }
