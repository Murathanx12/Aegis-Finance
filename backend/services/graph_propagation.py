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

AND THEN THE UNIVERSE KILLED IT — READ THIS BEFORE REGISTERING A BOOK
====================================================================
The vendor can supply the data. The data cannot supply a graph.

Measured on the live 179-name universe 2026-08-24: at the licensed
`min_shared=1` the co-coverage graph is **100.0% dense** -- all 176 names with
coverage are peers of all 175 others, because every major bank covers every
mega-cap. In a complete graph

    peer_eq_i = (S - r_i) / (n - 1)

which is a strictly decreasing function of the name's own return. Measured
corr(peer_eq, own_ret) = **-1.0000, sd 0.0000** over 200 random return draws.
The ranking is EXACTLY short-horizon reversal, and short-horizon winner-chasing
is a Holm-surviving ANTI-signal in this programme. Emitting it would not be a
weak selector; it would be a harmful one.

Sparsifying by requiring more shared brokers does not rescue it. The
correlation only becomes small around 8-12 shared firms (density 77% -> 29%),
and by then 11-45% of the universe is unrankable -- and more importantly, "an
edge requires 10 shared brokerages" is NOT the mechanism the screen validated.
`peer_shared` (count-weighted edges) was an arm in that screen and it did not
beat `peer_eq`. There is no evidence for the sparsified version.

WHY THE SCREEN NEVER SAW THIS. It ran on thousands of CRSP names where a median
ANALYST covers 4 firms, so co-coverage was SELECTIVE and an edge carried
information. AMENDMENT-3 established that firm-level attribution works -- but
still on that universe, where a firm graph is sparse RELATIVE TO ITS SIZE. A
179-name mega-cap universe is the one place the mechanism cannot work.

So `assert_graph_informative` refuses, and the book is NOT registrable against
this universe. The signal is not refuted; it needs names whose coverage is
selective, which means going down-cap, not adding a parameter.
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


#: Above this share of possible edges, `peer_eq` is arithmetically close to
#: minus the name's own return and carries no graph information. Measured on
#: the live 179-name universe 2026-08-24: density 100.0% at the licensed
#: `min_shared=1`, and corr(peer_eq, own_ret) = -1.0000 with sd 0.0000 over 200
#: random return draws. Density 77% still gives -0.12; it only reaches -0.06
#: near 52%. The bar is set at 0.60 -- comfortably inside the region where the
#: correlation is small, and far from the region where it is total.
MAX_EDGE_DENSITY: float = 0.60

#: How much anti-correlation with own return is tolerable before the ranking is
#: just reversal. Checked directly rather than inferred from density, because
#: density is a proxy and this is the thing that actually matters.
MAX_ABS_OWN_RETURN_CORR: float = 0.25


class GraphDegenerate(RuntimeError):
    """The graph is so dense that `peer_eq` is no longer a graph signal.

    If every name is linked to every other, then

        peer_eq_i = (S - r_i) / (n - 1)

    which is a strictly DECREASING linear function of the name's own return.
    The ranking is then exactly the reverse of own return -- short-horizon
    reversal wearing a graph as a costume, and short-horizon winner-chasing is
    a Holm-surviving ANTI-signal in this programme. A degenerate graph is not a
    weak signal, it is a harmful one, so it is refused rather than emitted.
    """


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
        # `not peers` is not redundant with the min_peers test: a caller
        # measuring raw graph structure passes min_peers=0, and `0 < 0` is
        # False, so an isolated name fell through to a division by zero.
        if not peers or len(peers) < min_peers:
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


def assert_graph_informative(coverage: dict[str, frozenset[str]],
                             scores: dict[str, float],
                             returns: dict[str, float]) -> dict:
    """Refuse a graph that has collapsed into cross-sectional demeaning.

    WHY THIS EXISTS AND THE SCREEN NEVER NEEDED IT. The screen ran on thousands
    of CRSP names where a median ANALYST covers 4 firms, so co-coverage was
    SELECTIVE and an edge meant something. The live universe is 179 mega-caps
    where every major bank covers nearly everything: measured 2026-08-24, the
    graph is 100.0% dense and every name is a peer of every other. Coverage
    that is universal carries no information about which names are related.

    So this is not a tuning knob. It is the difference between the mechanism
    the screen licensed and an anti-signal with the same name.
    """
    names = [t for t in coverage if coverage[t]]
    n = len(names)
    if n < 3:
        raise GraphDegenerate(f"only {n} names carry coverage")

    total = sum(len(coverage[t] & coverage[u]) > 0
                for t in names for u in names if t != u)
    density = total / (n * (n - 1))

    common = [t for t in scores if t in returns]
    corr = 0.0
    if len(common) >= 5:
        xs = [scores[t] for t in common]
        ys = [returns[t] for t in common]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        dx = sum((a - mx) ** 2 for a in xs) ** 0.5
        dy = sum((b - my) ** 2 for b in ys) ** 0.5
        corr = num / (dx * dy) if dx and dy else 0.0

    report = {"n_names": n, "edge_density": round(density, 4),
              "corr_with_own_return": round(corr, 4),
              "max_edge_density": MAX_EDGE_DENSITY,
              "max_abs_own_return_corr": MAX_ABS_OWN_RETURN_CORR}

    if density > MAX_EDGE_DENSITY:
        raise GraphDegenerate(
            f"edge density {density:.1%} exceeds {MAX_EDGE_DENSITY:.0%}: with "
            f"{n} names nearly every pair shares a covering brokerage, so "
            f"peer_eq is (S - r_i)/(n-1) — the reverse of own return, not a "
            f"graph signal. Measured corr with own return {corr:+.3f}. This "
            f"universe needs names whose coverage is SELECTIVE.")
    if abs(corr) > MAX_ABS_OWN_RETURN_CORR:
        raise GraphDegenerate(
            f"peer_eq correlates {corr:+.3f} with the name's OWN return "
            f"(bar {MAX_ABS_OWN_RETURN_CORR}); the ranking is reversal, not "
            f"propagation")
    return report


def graph_beats_null(coverage: dict[str, frozenset[str]], *,
                     n_draws: int = 10, seed: int = 20260824) -> dict:
    """Does this coverage graph concentrate MORE than its own degree-preserving
    null? The precondition that transports; density and own-return correlation
    do not.

    WHY THE OLD GATES ARE PROXIES
    =============================
    `assert_graph_informative` refuses above 60% density. Measured 2026-08-24
    (`GRAPH-BACKBONE-1/2`), a degree-preserving null on this same coverage
    predicts **95.8%** density against the observed 100.0% — so density near
    1.0 is what RANDOM coverage looks like when 176 names each draw ~17 firms
    from a pool of 94. The number that read as "the data cannot supply a graph"
    was mostly a fact about `min_shared=1`, which on this universe admits pairs
    whose overlap (median expected 3.43 shared brokers) is BELOW chance.

    That also says why the licensed parameter does not travel. "At least one
    shared broker" means something different where the median name has 4
    covering firms than where it has 17. "More shared brokers than the null
    predicts" means the same thing in both, and carries no parameter at all.

    WHAT THIS MEASURES
    ==================
    The effective peer count n_eff = (sum w)^2 / sum w^2 under
    significance-weighted edges (w = -log10 p from the same hypergeometric
    test), against the same construction on graphs that preserve BOTH degree
    sequences. A graph whose neighbourhoods are no more concentrated than
    chance cannot discriminate between peers, however its edges are drawn.

    THE LIVE ANSWER, and it is not the one density gave. The real graph IS
    distinguishable from its null -- z = -10.6, which is not a near miss in
    either direction -- and the effect is economically nil: n_eff 151.8 against
    a null 156.4 out of 175 possible peers. Real, highly significant, and 97%
    of the way to random. That is an equivalence result, not a failure to
    reject, and it is a far stronger negative than the density heuristic it
    replaces.

    Cheap enough to run on any candidate universe BEFORE paying for it.
    """
    import numpy as np

    names = sorted(t for t in coverage if coverage[t])
    if len(names) < 10:
        raise GraphDegenerate(f"only {len(names)} names carry coverage")
    cov = {t: coverage[t] for t in names}

    def _neff(c):
        from scipy.stats import hypergeom
        pool = {}
        for t, firms in c.items():
            for f in firms:
                pool[f] = pool.get(f, 0) + 1
        N = len(pool)
        by_firm: dict[str, list[str]] = {}
        for t in names:
            for f in c[t]:
                by_firm.setdefault(f, []).append(t)
        shared: dict[str, dict[str, int]] = {t: {} for t in names}
        for members in by_firm.values():
            for i, a in enumerate(members):
                for b in members[i + 1:]:
                    shared[a][b] = shared[a].get(b, 0) + 1
                    shared[b][a] = shared[b].get(a, 0) + 1
        vals = []
        for t in names:
            ks = np.asarray([shared[t][u] for u in shared[t]])
            if not ks.size:
                continue
            kb = np.asarray([len(c[u]) for u in shared[t]])
            p = hypergeom.sf(ks - 1, N, len(c[t]), kb)
            w = -np.log10(np.clip(p, 1e-300, None))
            w = w[w > 0]
            if w.size:
                vals.append(float(w.sum() ** 2 / (w ** 2).sum()))
        return float(np.median(vals)) if vals else 0.0

    def _shuffle(c, rng):
        sets = {t: set(f) for t, f in c.items()}
        edges = [(t, f) for t, fs in sets.items() for f in fs]
        m = len(edges)
        for _ in range(10 * m):
            i, j = int(rng.integers(0, m)), int(rng.integers(0, m))
            (t1, f1), (t2, f2) = edges[i], edges[j]
            if i == j or t1 == t2 or f1 == f2:
                continue
            if f2 in sets[t1] or f1 in sets[t2]:
                continue
            sets[t1].discard(f1); sets[t1].add(f2)
            sets[t2].discard(f2); sets[t2].add(f1)
            edges[i], edges[j] = (t1, f2), (t2, f1)
        return {t: frozenset(v) for t, v in sets.items()}

    import numpy as _np
    obs = _neff(cov)
    draws = [_neff(_shuffle(cov, _np.random.default_rng(seed + d)))
             for d in range(n_draws)]
    mean = float(_np.mean(draws))
    sd = float(_np.std(draws, ddof=1)) if len(draws) > 1 else 0.0
    ratio = obs / mean if mean else 1.0
    return {
        "n_names": len(names),
        "n_eff_observed": round(obs, 3),
        "n_eff_null_mean": round(mean, 3),
        "n_eff_null_sd": round(sd, 4),
        "z": round((obs - mean) / sd, 2) if sd else None,
        "ratio_to_null": round(ratio, 4),
        "bar": NEFF_RATIO_BAR,
        # NOT "indistinguishable": the live z is -8.9, so the structure is
        # emphatically distinguishable. It is NEGLIGIBLE. Labelling a z of -9
        # "indistinguishable" would be the same error as reading 17 covering
        # firms as a rich graph -- a word that contradicts its own number.
        "verdict": ("DISCRIMINATES" if ratio <= NEFF_RATIO_BAR
                    else "NEGLIGIBLE_VS_NULL"),
        "reading": ("a significant z with a ratio near 1.0 means the structure "
                    "is real and negligible -- detectable, and 97% of the way "
                    "to a random graph. Significance is not size."),
    }


#: A graph must concentrate to at most this fraction of its own null's
#: effective peer count. Measured live 2026-08-24: 0.97 -- nowhere near, so the
#: verdict does not hinge on where this sits.
NEFF_RATIO_BAR = 0.80


# ── health ──────────────────────────────────────────────────────────────────


def health() -> dict:
    """Health surface. A module with no health row is a module nobody can see
    fail; `alpaca_mirror_status` was one for a week (2026-08-24)."""
    return {
        "book_id": CONTRACT["book_id"],
        "licence": CONTRACT["licence"],
        "contract_hash": contract_hash(),
        "status": "BLOCKED_GRAPH_NEGLIGIBLE_VS_NULL",
        "reason": (
            "the live 176-name graph concentrates 97% as much as its own "
            "degree-preserving null (n_eff 151.8 vs 156.4 +- 0.5, z -10.6): "
            "the structure is REAL and economically nil. Weighting does fix "
            "the reversal identity that the first verdict measured -- "
            "significance-weighted edges reach corr -0.234 with own return at "
            "100% of the universe still rankable, which no min_shared value "
            "achieved -- so the mechanism is not blocked by density. It is "
            "blocked by the graph having nothing to say. "
            "docs/FINDING_2026-08-24_GRAPH_BACKBONE.md"),
        "superseded_reason": (
            "BLOCKED_UNIVERSE_TOO_DENSE, 2026-08-24 morning. 100.0% density "
            "read as proof of no graph; a degree-preserving null on the same "
            "coverage predicts 95.8%, so that number was a fact about "
            "min_shared=1 (which admits pairs whose overlap is BELOW chance on "
            "a 94-firm pool) rather than about the data. The verdict was "
            "right; its reason was a count reported without the question it "
            "answers."),
        "also_blocked_by": (
            "sequencing: the ten seeds written 2026-08-21 migrate to per-book "
            "identity only on their next arena pass, and adding any book to "
            "arena_books_v1.yaml before that makes assert_config_current "
            "refuse to run AND refuse to migrate, for all ten."),
        "measured": {
            "edge_density": 1.0,
            "corr_peer_eq_with_own_return": -1.0,
            "universe_n": 176,
        },
        "licensed_by": CONTRACT["licensed_by"]["trial"],
    }
