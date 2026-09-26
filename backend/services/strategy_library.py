"""Aegis does not distinguish OUR strategy from SOMEONE ELSE'S. Only useful from useless.

Novelty matters for the paper. It does not matter for the portfolio. If plain
cross-sectional momentum beats our neural network, the money goes to momentum.

WHAT THIS LIBRARY IS FOR
========================
Three things, and the third is the one that is easy to skip:

1. **Stop rediscovering.** Value, momentum, quality and trend are not research
   questions this programme should be spending its scarce holdout windows on.
   They are baselines. A mechanism the factory finds has to beat them, and it
   cannot beat what has not been implemented.
2. **Price the wheel rather than dismiss it.** McLean & Pontiff measured 97
   published cross-sectional predictors: about 26% lower out-of-sample and
   about 58% lower post-publication. The lesson is NOT "published strategies do
   not work" — it is "the published backtest overstates the opportunity, by
   roughly this much, on average". A prior, not a verdict.
3. **Keep the claim and the measurement in different fields.** This is the part
   that goes wrong. A `claimed_gross_annual` from a paper and an Aegis-measured
   return look identical once they are both floats in a table, and six weeks
   later nobody remembers which column was evidence. Here they are separate
   fields, and `best_available_performance` REFUSES to fall back from the
   measured one to the claimed one.

WHY A PUBLISHED NUMBER IS NOT EVIDENCE HERE
===========================================
It was produced by someone else's code on someone else's data with someone
else's universe, survivorship handling and cost model. Quoting it as if it were
an Aegis result would be `synthetic performance is never alpha evidence` wearing
a citation. So `reproduction_status` starts at NOT_ATTEMPTED and the library
will say so, loudly, in every report until somebody runs it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class Source(str, Enum):
    """Where the idea came from. Not a quality ranking — a provenance label."""
    PUBLISHED_ACADEMIC = "PUBLISHED_ACADEMIC"
    PUBLIC_PRACTITIONER = "PUBLIC_PRACTITIONER"
    DISCOVERED_BY_AEGIS = "DISCOVERED_BY_AEGIS"


class Reproduction(str, Enum):
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    IN_PROGRESS = "IN_PROGRESS"
    REPRODUCED = "REPRODUCED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ClaimIsNotEvidence(RuntimeError):
    """Someone asked for a measurement and only a claim exists."""


class RateNotDeclared(RuntimeError):
    """A net figure or a survivor count was requested without its cost rate."""


#: The rates every net figure is reported across. A single rate is a point
#: estimate of an ASSUMPTION, and N25 measured what that costs: the count of
#: predictors detectable and positive in the liquid tercile is 4 / 3 / 1 / 0 at
#: 0 / 5 / 10 / 20bp. "Exactly one" was quoted for two sessions as a fact about
#: the panel and it was a fact about 10bp.
DEFAULT_GRID_BPS: tuple[float, ...] = (0.0, 2.0, 5.0, 10.0, 20.0, 30.0, 50.0)


@dataclass
class Performance:
    """One measured window. Every field is nullable and none is inferred."""
    start: str | None = None
    end: str | None = None
    gross_annual_return: float | None = None
    net_annual_return: float | None = None
    sharpe: float | None = None
    annual_turnover: float | None = None
    max_drawdown: float | None = None
    n_months: int | None = None
    cost_bps_per_side: float | None = None
    note: str = ""
    #: Standard error of the ANNUAL figure, so detectability can be recomputed
    #: at any rate. Costs shift the estimate and leave its dispersion alone,
    #: which is why the whole grid is exact arithmetic rather than a re-run.
    se_annual: float | None = None
    mde_annual: float | None = None

    # ── the rate-conditioned layer ─────────────────────────────────────────
    def net_at(self, bps: float | None) -> float:
        """Net annual return at an explicitly named cost rate.

        `bps=None` RAISES. That is the whole point of this method existing
        beside `net_annual_return`: a net figure with no rate attached reads as
        a property of the strategy, and it is a property of an assumption.
        """
        if bps is None:
            raise RateNotDeclared(
                f"net return requested with no cost rate. Net is a function of "
                f"the rate, not a property of the strategy — measured on our "
                f"own panel the tradable survivor count is 4/3/1/0 at "
                f"0/5/10/20bp. Name the rate.")
        if self.gross_annual_return is None or self.annual_turnover is None:
            raise ClaimIsNotEvidence(
                "net_at needs a measured gross return AND a measured turnover; "
                "one of them is absent, and inferring either is the "
                "substitution this library refuses.")
        return self.gross_annual_return - self.annual_turnover * bps / 1e4

    def detectable_at(self, bps: float | None) -> bool:
        """|net(rate)| >= MDE. Tested on NET because net is the claim."""
        if self.mde_annual is None:
            raise ClaimIsNotEvidence(
                "detectability needs the measurement's own MDE; without it "
                "this would be an opinion about a number.")
        return abs(self.net_at(bps)) >= self.mde_annual

    def net_table(self, grid: tuple[float, ...] = DEFAULT_GRID_BPS) -> dict:
        """The default emission: every net figure with its rate beside it."""
        return {b: self.net_at(b) for b in grid}


@dataclass
class StrategySpec:
    """A strategy, its provenance, what its authors claimed, what we measured."""

    name: str
    family: str
    source: Source
    #: Free text, deliberately: a citation that has to parse is a citation
    #: somebody will omit.
    citation: str
    #: The three dates that make decay computable. `original_sample_end` is the
    #: one that matters most and the one most often missing from a summary.
    publication_date: str | None = None
    original_sample_start: str | None = None
    original_sample_end: str | None = None

    universe: str = ""
    rebalance: str = ""
    #: Enough to re-implement without the paper open. If this cannot be written
    #: down, the strategy is not specified and cannot be reproduced or refuted.
    construction: str = ""
    capacity_note: str = ""

    #: WHAT THE AUTHORS CLAIMED. Never an Aegis result. Never a fallback.
    claimed: Performance = field(default_factory=Performance)

    #: WHAT AEGIS MEASURED, in three windows, because decay is the question.
    #: in_sample      — the authors' own window, re-run on our data
    #: post_sample    — after their sample ended, before publication
    #: post_publication — after publication, where the crowding shows up
    in_sample: Performance | None = None
    post_sample: Performance | None = None
    post_publication: Performance | None = None

    reproduction_status: Reproduction = Reproduction.NOT_ATTEMPTED
    reproduction_note: str = ""
    priority: str = ""

    # ── the guard ──────────────────────────────────────────────────────────
    def measured(self, window: str = "post_publication") -> Performance:
        """The measured window, or a refusal. NEVER the claim.

        The whole failure mode this library exists to prevent is a claimed
        number silently standing in for a measured one, so there is no
        `or self.claimed` anywhere in this method and there must not be.
        """
        p = getattr(self, window, None)
        if p is None:
            raise ClaimIsNotEvidence(
                f"{self.name}: no Aegis measurement for `{window}` "
                f"(reproduction_status={self.reproduction_status.value}). The "
                f"published claim is NOT a substitute — it came from other "
                f"code, other data, another universe and another cost model.")
        return p

    def decay(self) -> dict:
        """Post-publication vs the authors' own window, ON OUR DATA BOTH TIMES.

        Deliberately NOT `measured / claimed`: that ratio confounds decay with
        every difference between their pipeline and ours — universe, survivorship
        handling, cost model, weighting. Comparing our in-sample to our
        post-publication holds the pipeline fixed, so what is left is closer to
        the thing McLean & Pontiff were measuring.
        """
        if self.in_sample is None or self.post_publication is None:
            return {"decay": None, "why": (
                "needs BOTH an Aegis in-sample and an Aegis post-publication "
                "measurement; a claim cannot stand in for either half")}
        a = self.in_sample.gross_annual_return
        b = self.post_publication.gross_annual_return
        if a is None or b is None or a == 0:
            return {"decay": None, "why": "a window carries no gross return"}
        return {
            "decay": 1.0 - (b / a),
            "in_sample_gross": a, "post_publication_gross": b,
            "mclean_pontiff_prior": 0.58,
            "why": ("fraction of OUR in-sample return not present in OUR "
                    "post-publication window. McLean & Pontiff's average "
                    "post-publication decline across 97 predictors was ~58%, "
                    "which is a PRIOR to compare against, not a target."),
        }

    def as_dict(self) -> dict:
        d = asdict(self)
        d["source"] = self.source.value
        d["reproduction_status"] = self.reproduction_status.value
        return d


# ─────────────────────────────────────────────────────────────────────────────
# V1 SEED. Claims transcribed from the literature; NOTHING here is measured.
#
# Priority follows cost survivability rather than headline returns. But the
# version of that prior these priorities were assigned under was the FOLK one —
# "low turnover survives" — and N25 measured it on our own panel and it is
# false here:
#
#     low turnover   median gross 0.31%   median net@10bp  -0.20%
#     mid turnover   median gross 1.20%   median net@10bp  +0.52%
#     high turnover  median gross 1.51%   median net@10bp  -1.05%
#
# Low turnover LOSES to the middle band, because it has almost no gross edge to
# protect. Novy-Marx & Velikov's actual result is about survival CONDITIONAL on
# having an edge; turnover erodes a numerator and cannot supply one. The costs
# story holds for the high-turnover band and says nothing useful about a
# strategy whose gross return is already near zero.
#
# These priorities are therefore NOT re-sorted on the measurement — a priority
# tuned to a result is a result wearing a plan. They stand as declared, with
# the correction recorded beside them.
# ─────────────────────────────────────────────────────────────────────────────
SEED: list[StrategySpec] = [
    StrategySpec(
        name="TSMOM — time-series momentum",
        family="trend", source=Source.PUBLISHED_ACADEMIC,
        citation="Moskowitz, Ooi & Pedersen (2012), JFE — 'Time Series Momentum'",
        publication_date="2012-05-01", original_sample_start="1965-01-01",
        original_sample_end="2009-12-31",
        universe="58 liquid futures (equity index, FX, commodity, bond)",
        rebalance="monthly",
        construction=("long if the past-12-month excess return is positive, "
                      "short if negative; size each position inversely to its "
                      "own ex-ante volatility so no market dominates the book"),
        capacity_note="futures; high capacity. Our version must be an EQUITY "
                      "analogue — we hold no futures account — and that is a "
                      "different test, not the same one with different tickers.",
        claimed=Performance(note="significant abnormal returns at 1-12 month "
                                 "horizons across all 58 instruments; the "
                                 "later century-long study reports positive "
                                 "performance in every decade since 1880"),
        priority="A"),

    StrategySpec(
        name="QMJ — quality minus junk",
        family="quality", source=Source.PUBLISHED_ACADEMIC,
        citation="Asness, Frazzini & Pedersen (2019), RAS — 'Quality Minus Junk'",
        publication_date="2013-10-01", original_sample_start="1957-01-01",
        original_sample_end="2016-12-31",
        universe="US + 24 developed markets", rebalance="monthly",
        construction=("rank on profitability, growth and safety; long the top "
                      "quality decile, short the bottom, within size groups"),
        capacity_note="low turnover, large-cap tilted — high capacity",
        claimed=Performance(note="significant risk-adjusted returns in the US "
                                 "and in 24 of 24 countries"),
        priority="A"),

    StrategySpec(
        name="Profitability (gross profits / assets)",
        family="quality", source=Source.PUBLISHED_ACADEMIC,
        citation="Novy-Marx (2013), JFE — 'The Other Side of Value'",
        publication_date="2013-04-01", original_sample_start="1963-01-01",
        original_sample_end="2010-12-31",
        universe="US equities", rebalance="annual",
        construction="long high gross-profits-to-assets, short low, size-neutral",
        capacity_note="ANNUAL rebalance — among the highest-capacity anomalies "
                      "in the Novy-Marx & Velikov cost taxonomy",
        claimed=Performance(annual_turnover=0.3),
        priority="A"),

    StrategySpec(
        name="HML — book-to-market value",
        family="value", source=Source.PUBLISHED_ACADEMIC,
        citation="Fama & French (1993, 2015)",
        publication_date="1993-01-01", original_sample_start="1963-01-01",
        original_sample_end="1991-12-31",
        universe="US equities", rebalance="annual (June)",
        construction="long high book-to-market, short low, within size groups",
        capacity_note="annual rebalance, high capacity",
        claimed=Performance(annual_turnover=0.25),
        priority="A"),

    StrategySpec(
        name="UMD — cross-sectional momentum (12-1)",
        family="momentum", source=Source.PUBLISHED_ACADEMIC,
        citation="Jegadeesh & Titman (1993); Novy-Marx & Velikov (2016) on costs",
        publication_date="1993-03-01", original_sample_start="1965-01-01",
        original_sample_end="1989-12-31",
        universe="US equities", rebalance="monthly",
        construction=("rank on the return from t-12 to t-1 months, skipping "
                      "the most recent month; long the top decile, short the "
                      "bottom"),
        capacity_note="MONTHLY rebalance and high turnover — this is the one "
                      "the cost literature says is hardest to monetize, so it "
                      "is implemented WITH the turnover control rather than as "
                      "the textbook version",
        claimed=Performance(annual_turnover=2.0),
        priority="A/B"),

    StrategySpec(
        name="BAB — betting against beta",
        family="defensive", source=Source.PUBLISHED_ACADEMIC,
        citation=("Frazzini & Pedersen (2014), JFE; and the critique — "
                  "Novy-Marx & Velikov (2022), 'Betting against betting "
                  "against beta'"),
        publication_date="2014-01-01", original_sample_start="1926-01-01",
        original_sample_end="2012-03-31",
        universe="US equities and other asset classes", rebalance="monthly",
        construction=("long low-beta, short high-beta, each leg levered to "
                      "beta 1. IMPORTED WITH ITS DECOMPOSITION, never the "
                      "headline alone: the critique shows heavy exposure to "
                      "very small stocks and to profitability/investment, so "
                      "Aegis must decide how much is beta and how much is "
                      "microcap weighting, quality, and construction mechanics"),
        capacity_note="the original construction's microcap exposure is the "
                      "capacity problem, and it is also the reason the alpha "
                      "may not be about beta at all",
        claimed=Performance(note="significant positive risk-adjusted returns "
                                 "in 18 of 19 international markets"),
        priority="B"),

    StrategySpec(
        name="Low-volatility / defensive equity",
        family="defensive", source=Source.PUBLIC_PRACTITIONER,
        citation="widely implemented; MSCI/S&P minimum-volatility indices",
        publication_date=None,
        universe="US large cap", rebalance="quarterly",
        construction="long the lowest trailing-volatility quintile, long-only",
        capacity_note="long-only and quarterly — implementable at our size, "
                      "and the one strategy here Murat could actually run",
        priority="B"),

    StrategySpec(
        name="Short-term reversal (1-month)",
        family="reversal", source=Source.PUBLISHED_ACADEMIC,
        citation="Jegadeesh (1990); Lehmann (1990)",
        publication_date="1990-07-01", original_sample_start="1934-01-01",
        original_sample_end="1987-12-31",
        universe="US equities", rebalance="monthly",
        construction="long last month's losers, short last month's winners",
        capacity_note="the highest-turnover strategy in this list. The cost "
                      "taxonomy suggests most of its gross return does not "
                      "survive; carried BECAUSE it is the clearest test of "
                      "whether our cost model is honest",
        claimed=Performance(annual_turnover=12.0),
        priority="C"),

    StrategySpec(
        name="PEAD — post-earnings-announcement drift",
        family="event", source=Source.PUBLISHED_ACADEMIC,
        citation=("Bernard & Thomas (1989); and the modern evidence — "
                  "Martineau (2022) on the disappearance in large caps"),
        publication_date="1989-01-01", original_sample_start="1974-01-01",
        original_sample_end="1986-12-31",
        universe="US equities", rebalance="event-driven",
        construction=("long the top standardised-unexpected-earnings decile "
                      "for ~60 days after the announcement, short the bottom. "
                      "IMPORTED AS A CONDITIONAL QUESTION, NOT A STRATEGY: the "
                      "modern evidence says the unconditional large-cap drift "
                      "is attenuated or gone, so what G4 tests is WHICH "
                      "conditions retain it, not whether to run it"),
        capacity_note="event-driven, concentrated in earnings season; the cost "
                      "literature finds drift concentrated in the names where "
                      "trading costs are highest, which is not a coincidence",
        priority="B — conditional only"),

    StrategySpec(
        name="Volatility targeting",
        family="risk", source=Source.PUBLIC_PRACTITIONER,
        citation="widely used; Moreira & Muir (2017) 'Volatility-Managed "
                 "Portfolios' is the academic version",
        publication_date="2017-08-01",
        universe="any", rebalance="monthly",
        construction=("scale exposure inversely to recent realised variance. "
                      "A SIZING rule rather than a selection rule, which is the "
                      "layer §59 says our slice can resolve: risk is measured "
                      "~30x closer than return on identical data, and THAT "
                      "RATIO is what reproduces. The '~4 years' figure this "
                      "field used to carry was WITHDRAWN on 2026-08-17 — it "
                      "rested on a single crisis. N22 then measured the "
                      "forward question directly: 0 of 8 cells resolvable on "
                      "the 74 reserved months, so the claim is permanently "
                      "screen-grade on this corpus."),
        capacity_note="applies to whatever it wraps",
        priority="A — it is the sizing layer, not a stock picker"),
]


#: Which OSAP predictor implements which seeded strategy. `None` means no
#: faithful implementation exists in the data we hold, and the library refuses
#: rather than substituting a cousin under the original's name.
IMPLEMENTED_BY: dict[str, str | None] = {
    "UMD — cross-sectional momentum (12-1)": "Mom12m",
    "HML — book-to-market value": "BM",
    "Profitability (gross profits / assets)": "GP",
    "PEAD — post-earnings-announcement drift": "EarningsSurprise",
    "Low-volatility / defensive equity": "RealizedVol",
    "BAB — betting against beta": "BetaFP",
    "Short-term reversal (1-month)": "__own_1m_reversal",
    "TSMOM — time-series momentum": "__own_tsmom",
    "QMJ — quality minus junk": None,
    "Volatility targeting": None,
}


class MeasurementUnavailable(RuntimeError):
    """Someone asked to load measurements and the run has not happened."""


def load_measured(path, *, window: str = "post_publication") -> list[StrategySpec]:
    """Attach an Aegis measurement run to COPIES of the seeded specs.

    Copies, not the module-level SEED: a library that mutates itself on import
    makes `measured()` succeed or refuse depending on what ran earlier in the
    process, and the whole point of that method is that it is predictable.

    REFUSES on a missing file rather than returning the unmeasured seed. An
    unmeasured library that looks measured is the exact confusion this module
    was written to prevent, and "the file was not there" is not a reason to
    quietly hand back claims.
    """
    import copy
    import json
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        raise MeasurementUnavailable(
            f"no measurement at {p}. The seeded specs carry CLAIMS only; "
            f"returning them as though a run had happened is the substitution "
            f"this library exists to refuse. Run the measurement first.")
    payload = json.loads(p.read_text(encoding="utf-8"))
    results = payload.get("results", payload)
    screens = payload.get("screens", {})
    out = []
    for spec in SEED:
        s = copy.deepcopy(spec)
        col = IMPLEMENTED_BY.get(s.name)
        r = results.get(col) if col else None
        if r is None or r.get("refused") or r.get("insufficient"):
            s.reproduction_status = Reproduction.FAILED if col else \
                Reproduction.NOT_ATTEMPTED
            s.reproduction_note = (
                "no faithful implementation in the data we hold" if not col
                else f"{col} not measurable on this window")
            out.append(s)
            continue
        perf = Performance(
            start=str(payload.get("window", "")).split("..")[0],
            end=str(payload.get("window", "")).split("..")[-1],
            gross_annual_return=r.get("gross_annual"),
            net_annual_return=r.get("net_annual"),
            sharpe=r.get("sharpe"), n_months=r.get("n_months"),
            annual_turnover=(None if r.get("monthly_turnover") is None
                             else 12 * r["monthly_turnover"]),
            cost_bps_per_side=screens.get("cost_bps_per_crossing"),
            se_annual=r.get("se_annual"), mde_annual=r.get("mde_annual"),
            note=(f"equal-weighted decile spread on the CRSP panel; "
                  f"break-even {r.get('breakeven_bps')}bp/crossing. "
                  f"Detectability is rate-conditioned — call "
                  f"`detectable_at(bps)`; the stored `net_annual_return` is "
                  f"the figure at "
                  f"{screens.get('cost_bps_per_crossing')}bp and nothing else."))
        setattr(s, window, perf)
        s.reproduction_status = Reproduction.PARTIAL
        s.reproduction_note = (
            "implemented from OSAP characteristics on our own return panel — "
            "our universe, our weighting, our cost model, not the authors'. "
            "2006-2019 is post-publication for this strategy, so this is the "
            "DECAYED number and there is no matching in-sample half: the "
            "authors' window predates our panel.")
        out.append(s)
    return out


def rate_table(specs: list[StrategySpec], *,
               window: str = "post_publication",
               grid: tuple[float, ...] = DEFAULT_GRID_BPS) -> dict:
    """THE DEFAULT EMISSION: every strategy's net across the whole grid.

    Returned instead of a single-rate table because a single-rate table is what
    produced "exactly one detectable net in the liquid tercile" — true at 10bp,
    quoted as a fact about the panel, and 4/3/1/0 across 0/5/10/20.
    """
    rows = []
    for s in specs:
        try:
            p = s.measured(window)
            rows.append({"name": s.name, "family": s.family,
                         "turnover": p.annual_turnover,
                         "gross": p.gross_annual_return,
                         "net": p.net_table(grid),
                         "detectable": {b: p.detectable_at(b) for b in grid}
                         if p.mde_annual is not None else None})
        except (ClaimIsNotEvidence, RateNotDeclared) as e:
            rows.append({"name": s.name, "family": s.family,
                         "unmeasured": str(e).split(".")[0]})
    return {"grid_bps": list(grid), "window": window, "rows": rows,
            "note": "net is a function of the rate; there is no scalar form."}


def factory_bar(specs: list[StrategySpec], bps: float | None = None, *,
                window: str = "post_publication") -> float | None:
    """The best net a published strategy delivers — AT A NAMED RATE.

    `bps=None` RAISES rather than defaulting to 10. The bar is what a new
    mechanism has to beat, so a bar carrying an unstated cost assumption sets
    the whole factory's threshold from a number nobody chose on purpose.
    """
    if bps is None:
        raise RateNotDeclared(
            "the factory bar was requested with no cost rate. The bar is the "
            "threshold every new mechanism is judged against, and it moves with "
            "the rate — name it, or read `rate_table()` instead of a scalar.")
    best = None
    for s in specs:
        try:
            v = s.measured(window).net_at(bps)
        except (ClaimIsNotEvidence, RateNotDeclared):
            continue
        if v is not None and (best is None or v > best):
            best = v
    return best


def by_priority() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for s in SEED:
        out.setdefault(s.priority or "unset", []).append(s.name)
    return out


def status_report() -> dict:
    """Say plainly that nothing here is evidence yet."""
    return {
        "n_strategies": len(SEED),
        "by_source": {s.value: sum(1 for x in SEED if x.source is s)
                      for s in Source},
        "by_reproduction": {r.value: sum(1 for x in SEED
                                         if x.reproduction_status is r)
                            for r in Reproduction},
        "n_with_any_aegis_measurement": sum(
            1 for s in SEED if any((s.in_sample, s.post_sample,
                                    s.post_publication))),
        "by_priority": by_priority(),
        "warning": ("Every performance figure in this library is a CLAIM from "
                    "its source. None has been reproduced on our data. A "
                    "claim is a candidate and a prior; it is never an Aegis "
                    "result, and `measured()` refuses rather than falling "
                    "back to it."),
    }


# ═════════════════════════════════════════════════════════════════════════════
# THE RULE LIBRARY AND ITS BACKTEST ENGINE (2026-09-26, spec chunk 3b)
# ═════════════════════════════════════════════════════════════════════════════
#
# The block above is the LITERATURE catalogue: what other people claimed, kept
# apart from what we measured. This block is the other half Murat asked for on
# 2026-09-26 ("100 backtests ... list the top 10 ... if Aegis had existed in
# 2020"): every strategy DEFINED ONCE as a single rule over the existing monthly
# panel, backtested the same way as every other, and ranked honestly by
# `scripts/night_backtest_factory.py`.
#
# What a rule may and may not do:
#   * ONE line over columns that already exist on the panel (price/volume
#     features from the survivorship-free bars, SEC fundamentals joined on
#     `filed`, dated analyst revisions strictly before the decision date). No
#     new data collector -- a catalogue row that would need one is recorded in
#     `NOT_REACHABLE` with the input it lacks.
#   * Higher score = buy. NaN = not selectable. Selection is the top-k of the
#     rule's universe, equal weight, net of the band round trip.
#   * `first_registered_utc` is when the RULE was written down. Every number
#     over months before it is HINDSIGHT (a backtest of a rule chosen by people
#     who had seen those months) and is labelled so; only months after it are
#     quotable. That is "no backfilled forward evidence", applied to the
#     library itself.

import hashlib as _hashlib
import json as _json
import math as _math
from typing import Callable as _Callable

import numpy as _np
import pandas as _pd

#: When the seed below was written. Every rule in `RULES` carries it.
REGISTERED_2026_09_26 = "2026-09-26T02:00:00+00:00"
#: When the chunk-D expansion (insider, 8-K, short interest, rating/lead-chase
#: flow, analyst skill, sector-relative, regime-gated, weighted) was written.
REGISTERED_2026_09_26_PM = "2026-09-26T09:00:00+00:00"

# ── THE SEALED SPLIT (declared 2026-09-26 in code, BEFORE the first run on it) ─
#
# Murat, chunk D: "every row prints dev return, SPY, sealed/OOS return ... the
# objective is MAXIMISE SEALED NET RETURN". The split is a constant, not an
# argument, so no run can move it after looking.
#
# A monthly period belongs to the window its ENTRY session is in (entry = the
# session after the decision date), so the period decided on 2023-12-29 and
# earned in January 2024 is SEALED, not development.
#
# HONEST NOTE, printed on every board: "sealed" means declared-before-this-run,
# not unseen. Every rule was written in 2026 by people who lived 2024-2026, and
# the 2026-09-26 02:00 board printed full-sample numbers that include it. The
# sealed window is 2024-01 -> the last completed month (~32 monthly blocks, not
# the 21 the brief assumed), so its DSR is printed beside every sealed number.
DEV_END = "2023-12-31"
SEALED_START = "2024-01-01"
#: the second sealed window: the last 126 sessions. The engine is monthly, so it
#: is realised as the last RECENT_PERIODS completed monthly periods (126/21).
RECENT_SESSIONS = 126
RECENT_PERIODS = 6

#: What the 2024-> window IS (review 2026-09-26 chunks D+E, adjudicated): the
#: split was declared in code before the ranking, but every rule was written in
#: 2026 by people who lived 2024-26 and the board RANKS on it. It is a selection
#: window, not a holdout. Every board, README and BRIDGE line uses this label;
#: "sealed"/"OOS" never appears without it. (Field names stay `sealed_*` for
#: receipt compatibility -- the label is what a reader sees.)
SELECTION_WINDOW_LABEL = "2024-26 selection window (split declared, data seen)"
#: z for a two-sided 5% test at 80% power (1.96 + 0.84): the MDE multiplier.
MDE_Z = 2.8

#: Construction rules the engine knows. Equal weight is the default; the other
#: two are the SIZ-04 / risk-parity construction variants.
WEIGHT_RULES = ("equal", "inv_vol", "inv_amihud")

#: The breadth cells every rule is evaluated at. The WORST of them is printed
#: beside the rule's own k: a result that exists only at k=10 is a result about
#: ten names, not about the rule.
BREADTH_K: tuple = (10, 20, 50)

#: A t on horizon-wide blocks must clear this before a row is anything but a
#: PRODUCT_EXPERIMENT observation (Harvey, Liu & Zhu 2016, RFS).
HLZ_T_BAR = 3.0


def _band_costs() -> dict:
    """Round trip by liquidity band, from the ranker -- one toll, one source."""
    from backend.services import xs_ranker as XR
    return dict(XR.COST_BPS_BY_BAND)


class RuleInputMissing(RuntimeError):
    """A rule was asked to run on a panel that lacks a column it reads.

    Refuses rather than scoring NaN everywhere: a rule whose input is absent
    selects nothing, and "selected nothing" reads as a flat strategy rather
    than a broken one.
    """


def check_costs(cost_scale: float, zero_cost_diagnostic: bool) -> None:
    """The portfolio farm's zero-cost refusal, INHERITED rather than retyped.

    Builds a farm `Policy` at the declared scale of the band toll, so the one
    place that decides whether a frictionless run is legal decides it here
    too. `PolicyError` propagates unchanged.
    """
    from backend.services.portfolio_farm.policy import Policy
    one_way_mid = _band_costs()["mid"] / 2.0
    Policy(transaction_cost_bps=float(cost_scale) * one_way_mid, slippage_bps=0.0,
           zero_cost_diagnostic=bool(zero_cost_diagnostic))


def _mdv(p):
    return p["median_dollar_vol"]


#: Universe rules, all on TRAILING median dollar volume at the decision date.
UNIVERSES: dict = {
    "all": lambda p: p["eligible"],
    "mega": lambda p: p["eligible"] & (_mdv(p) >= 1e9),
    "large": lambda p: p["eligible"] & (_mdv(p) >= 1e8),
    "mid_plus": lambda p: p["eligible"] & (_mdv(p) >= 2e7),
    "mid": lambda p: p["eligible"] & (_mdv(p) >= 2e7) & (_mdv(p) < 1e8),
    "small": lambda p: p["eligible"] & (_mdv(p) < 2e7),
}

#: The same rules in words, for a second engine that does not import this file.
UNIVERSE_TEXT: dict = {
    "all": "eligible",
    "mega": "eligible & median_dollar_vol_63d >= 1e9",
    "large": "eligible & median_dollar_vol_63d >= 1e8",
    "mid_plus": "eligible & median_dollar_vol_63d >= 2e7",
    "mid": "eligible & 2e7 <= median_dollar_vol_63d < 1e8",
    "small": "eligible & median_dollar_vol_63d < 2e7",
}
ELIGIBLE_TEXT = ("trades on the decision date; xs_ranker MIN_PRICE <= close <= MAX_PRICE; "
                 "median 63-session dollar volume >= xs_ranker.MIN_MEDIAN_DOLLAR_VOL; >= "
                 "xs_ranker.MIN_HISTORY_SESSIONS sessions of history; not an ETF/index proxy; "
                 "vol_63 and mom_63 defined")


@dataclass(frozen=True)
class Strategy:
    """One rule. Everything a nightly backtest needs, nothing it could tune."""

    id: str
    family: str
    description: str
    #: panel (long, one row per (date, symbol)) -> Series of scores, same index.
    signal: _Callable
    universe_rule: str = "all"
    k: int = 20
    #: months between rebalances; the book is held (and marked monthly) between.
    hold_months: int = 1
    rebalance: str = "month-end close; enter at the next session's open"
    weight_rule: str = "equal"
    #: "ours" or "literature:<catalogue id> <citation>".
    source: str = "ours"
    first_registered_utc: str = REGISTERED_2026_09_26
    caveat: str = ""
    #: the paper's own number, verbatim from the catalogue. NEVER ours.
    literature_reported: str = ""
    #: controls are printed, never ranked, never counted as trials.
    control: bool = False
    #: 1.0 = the band costs as measured. 0.0 is refused unless declared.
    cost_scale: float = 1.0
    zero_cost_diagnostic: bool = False
    #: one line: WHY it should pay (risk premium, behavioural error, friction).
    #: A library rule without one is filled from `FAMILY_REASON` at registration.
    economic_reason: str = ""
    #: a panel column that is the same for every name on a date (e.g.
    #: `mkt_trend_up`); where it is <= 0 the book goes to CASH (earning 0 --
    #: T-bills are NOT credited, a conservative choice stated here).
    regime_gate: str | None = None
    #: the rule's input has no history on this panel (thesis cards, investigator
    #: p, live snapshots): it is registered and gets a forward book, and the
    #: factory REFUSES to backtest it rather than scoring an empty past.
    forward_only: bool = False
    #: calendar months (1-12) of the DECISION date on which the book rebalances.
    #: None = every `hold_months` periods from the first selectable date (the
    #: original engine). Set only on the rebalance-offset controls.
    rebalance_months: tuple | None = None

    def __post_init__(self) -> None:
        check_costs(self.cost_scale, self.zero_cost_diagnostic)
        if self.weight_rule not in WEIGHT_RULES:
            raise ValueError(f"{self.id}: weight_rule {self.weight_rule!r} not in {WEIGHT_RULES}")
        if self.universe_rule not in UNIVERSES:
            raise RuleInputMissing(
                f"{self.id}: universe {self.universe_rule!r} is not declared; "
                f"known: {sorted(UNIVERSES)}")
        if self.k < 1 or self.hold_months < 1:
            raise ValueError(f"{self.id}: k and hold_months must be >= 1")

    @property
    def requires(self) -> tuple:
        extra = (self.regime_gate,) if self.regime_gate else ()
        return tuple(getattr(self.signal, "requires", ())) + extra

    @property
    def shape(self) -> str:
        """The signal's structure with every numeric threshold stripped."""
        return str(getattr(self.signal, "shape", f"opaque:{self.id}"))

    def signature(self) -> str:
        """What makes a rule DIFFERENT: signal structure, universe, holding,
        weighting, regime gate. Deliberately NOT k and NOT any threshold -- two
        rules with the same signature are one rule at two settings."""
        sig = [self.shape, f"u={self.universe_rule}", f"h={self.hold_months}",
               f"w={self.weight_rule}", f"g={self.regime_gate or '-'}"]
        if self.rebalance_months:
            sig.append("rm=" + ",".join(str(m) for m in self.rebalance_months))
        return "|".join(sig)

    @property
    def kind(self) -> str:
        """`control` (printed, never ranked, never a trial) or `rule`."""
        return "control" if self.control else "rule"

    def fingerprint(self) -> str:
        body = {"id": self.id, "family": self.family, "d": self.description,
                "u": self.universe_rule, "k": self.k, "h": self.hold_months,
                "w": self.weight_rule, "r": list(self.requires),
                "c": self.cost_scale, "z": self.zero_cost_diagnostic,
                "reg": self.first_registered_utc}
        if self.regime_gate:
            body["g"] = self.regime_gate
        if self.rebalance_months:
            body["rm"] = list(self.rebalance_months)
        return _hashlib.sha256(_json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]

    def meta(self) -> dict:
        return {"id": self.id, "family": self.family,
                "description": self.description,
                "universe_rule": self.universe_rule, "k": self.k,
                "hold_months": self.hold_months, "rebalance": self.rebalance,
                "weight_rule": self.weight_rule, "source": self.source,
                "first_registered_utc": self.first_registered_utc,
                "requires": list(self.requires), "caveat": self.caveat,
                "literature_reported": self.literature_reported,
                "economic_reason": self.economic_reason,
                "regime_gate": self.regime_gate, "shape": self.shape,
                "forward_only": self.forward_only,
                "signature": self.signature(),
                "control": self.control, "kind": self.kind,
                "rebalance_months": list(self.rebalance_months) if self.rebalance_months else None,
                "fingerprint": self.fingerprint()}


# ── signal helpers: every rule is one line over these ───────────────────────

def _need(p, cols) -> None:
    missing = [c for c in cols if c not in p.columns]
    if missing:
        raise RuleInputMissing(
            f"panel lacks {missing}; the rule cannot be scored. A rule over a "
            f"column that is absent selects nothing, and nothing looks flat.")


def col(name: str, sign: float = 1.0):
    """Score = sign * column."""
    def f(p):
        _need(p, (name,))
        return sign * p[name].astype(float)
    f.requires = (name,)
    f.shape = f"col({name},{'+' if sign >= 0 else '-'})"
    return f


def rank_of(p, name: str, sign: float = 1.0):
    """Within-date percentile rank of sign*column (NaN stays NaN)."""
    _need(p, (name,))
    return (sign * p[name].astype(float)).groupby(p["date"]).rank(pct=True)


def combo(*legs):
    """Average of within-date ranks; a name needs EVERY leg to be scored."""
    names = tuple(n for n, _s in legs)

    def f(p):
        _need(p, names)
        acc = None
        for n, s in legs:
            r = rank_of(p, n, s)
            acc = r if acc is None else acc + r
        return acc / len(legs)
    f.requires = names
    f.shape = "combo(" + ",".join(sorted(f"{n}{'+' if s >= 0 else '-'}" for n, s in legs)) + ")"
    return f


def gated(base, gate_col: str, lo: float | None = None, hi: float | None = None):
    """`base` scores only where lo <= gate_col <= hi (a filter, not a rank)."""
    def f(p):
        _need(p, (gate_col,))
        s = base(p)
        g = p[gate_col].astype(float)
        m = g.notna()
        if lo is not None:
            m &= g >= lo
        if hi is not None:
            m &= g <= hi
        return s.where(m)
    f.requires = tuple(getattr(base, "requires", ())) + (gate_col,)
    # the bound VALUES are thresholds and are stripped; which side is bounded
    # is a different economic claim ("at least one raise" vs "no raise") and stays
    f.shape = (f"gated({getattr(base, 'shape', '?')},{gate_col},"
               f"{'lo' if lo is not None else ''}{'hi' if hi is not None else ''})")
    return f


def within_top(base, rank_col: str, frac: float, sign: float = 1.0):
    """`base` scores only among names in the top `frac` of rank_col (per date)."""
    def f(p):
        r = rank_of(p, rank_col, sign)
        return base(p).where(r >= 1.0 - frac)
    f.requires = tuple(getattr(base, "requires", ())) + (rank_col,)
    f.shape = f"within_top({getattr(base, 'shape', '?')},{rank_col}{'+' if sign >= 0 else '-'})"
    return f


def sector_rel(base):
    """`base` re-expressed as its percentile WITHIN (date, gsector).

    The long-only realisation of "neutral of sector": the top-k is then the
    names most extreme relative to their own sector, not the sector that
    happens to lead. Needs the `gsector` column (static GICS map -- caveat).
    """
    def f(p):
        _need(p, ("gsector",))
        s = base(p)
        g = p["gsector"]
        return s.groupby([p["date"], g]).rank(pct=True).where(g.notna())
    f.requires = tuple(getattr(base, "requires", ())) + ("gsector",)
    f.shape = f"sector_rel({getattr(base, 'shape', '?')})"
    return f


def seeded_noise(seed: int):
    """A deterministic random score per (date, symbol): the random-k control.

    Hash-based rather than an rng stream, so the control does not depend on row
    order and a re-run the same day draws the same names (idempotence).
    """
    def f(p):
        key = p["symbol"].astype(str) + "|" + p["date"].astype(str) + f"|{seed}"
        h = _pd.util.hash_pandas_object(key, index=False).to_numpy(dtype="uint64")
        return _pd.Series((h % 1_000_003).astype(float), index=p.index)
    f.requires = ()
    f.shape = f"noise({seed})"
    return f


def rank_band(base, lo: int, hi: int, universe: str = "all"):
    """`base` scores only for names ranked lo..hi (1 = best) on its own date.

    Ranks are taken among the rule's universe with the engine's own order
    (score descending, then the per-(date, symbol) tiebreak hash), so a top-k
    over the result is exactly the base rule's picks lo..hi. The control for
    "is the ORDERING inside the top informative, or is the edge the universe
    the sort is drawn from?" (review 2026-09-26 Q5).
    """
    def f(p):
        s = base(p).astype(float)
        m = UNIVERSES[universe](p).fillna(False).astype(bool) & _np.isfinite(s)
        df = _pd.DataFrame({"d": p["date"].to_numpy(), "s": -s.to_numpy(),
                            "tb": _tiebreak(p)}, index=p.index)[m.to_numpy()]
        df = df.sort_values(["d", "s", "tb"], kind="mergesort")
        r = df.groupby("d", sort=False).cumcount() + 1
        keep = r.index[((r >= lo) & (r <= hi)).to_numpy()]
        return s.where(s.index.isin(keep))
    f.requires = tuple(getattr(base, "requires", ()))
    f.shape = f"rank_band({getattr(base, 'shape', '?')},{lo}-{hi})"
    return f


class ThresholdVariant(ValueError):
    """A rule whose only difference from a registered one is a threshold or k.

    Murat, chunk D: "no trivial threshold variants". Two rules with the same
    `signature()` are ONE economic claim tried twice, and the second try is a
    trial the DSR must pay for without learning anything new.
    """


def register(library: list, rule: "Strategy") -> "Strategy":
    """Append `rule` unless its id or its signature is already registered."""
    for r in library:
        if r.id == rule.id:
            raise ValueError(f"duplicate rule id {rule.id!r}")
        if not rule.control and not r.control and r.signature() == rule.signature():
            raise ThresholdVariant(
                f"{rule.id} REFUSED: same signature as {r.id} ({rule.signature()}); "
                f"it differs only by a threshold or k. Register a different mechanism, "
                f"universe, holding economics, weighting or regime gate instead.")
    if not rule.economic_reason:
        from dataclasses import replace as _replace
        rule = _replace(rule, economic_reason=FAMILY_REASON.get(rule.family, ""))
    library.append(rule)
    return rule


# ── the seed: >= 100 rules ───────────────────────────────────────────────────
#
# Literature ids (MOM-01 ...) are row ids of
# `docs/research_notes/2026-09-26/research_strategy_library.md`; their reported
# numbers are copied verbatim into `literature_reported` and stay CLAIMS.

_FLOW_CAVEAT = ("survivor-selected: the revision parquet was pulled in 2026-09 "
                "for names alive then (64 of 1,784 dead symbols carry history), "
                "so the covered universe under-represents deaths")
_FUND_CAVEAT = ("SEC facts joined on `filed` + 2 days, never on `end`; annual "
                "flows only; a filing older than 460 days is NaN")
_BOTH = _FLOW_CAVEAT + "; " + _FUND_CAVEAT


def _lit(cid: str, cite: str) -> str:
    return f"literature:{cid} {cite}"


#: One line per family: WHY a rule of this family should pay. A rule may carry
#: its own `economic_reason`; otherwise registration fills it from here.
FAMILY_REASON: dict = {
    "momentum": "investors under-react to news that arrives gradually; winners keep winning for 3-12 months",
    "trend": "slow-moving capital and herding keep prices above their long average trending",
    "reversal": "liquidity providers are paid to absorb short-horizon overreaction and price pressure",
    "low_risk": "leverage-constrained investors bid up high-beta/lottery names, leaving low-risk names cheap",
    "size_liquidity": "holders of illiquid/neglected names demand a premium for the cost of exiting",
    "seasonality": "recurring demand at the same calendar month (earnings, flows, dividends) repeats",
    "quality": "the market under-prices durable profitability because it is boring and slow to show",
    "investment": "firms that grow assets aggressively over-invest; the market extrapolates growth too far",
    "inflection": "a margin/revenue turn is under-weighted until it shows in several reports",
    "revision_flow": "analyst target revisions diffuse slowly; the price catches up to the revision",
    "combination": "two signals with different errors average out each other's noise",
    "analyst_rating": "rating changes carry private analyst work; the market under-reacts to the change",
    "lead_chase": "a raise made BEFORE the price moved is information; a raise after the move is chasing",
    "analyst_skill": "some brokers' revisions are persistently more informative; weight the skilled ones",
    "analyst_dispersion": "with short-sale constraints the optimists set the price when opinions differ",
    "flow_momentum": "revisions and price that AGREE are less likely noise than either alone",
    "insider": "insiders buy with private information; open-market purchases are costly signals",
    "earnings_event": "announcements concentrate information and attention; drift and pre-event premia follow",
    "filing_event": "material 8-K events are under-processed by the market between earnings dates",
    "short_interest": "shorts are informed and costly; heavily shorted names under-perform, covering signals relief",
    "fund_inflection": "accelerating revenue and margin changes are extrapolated too slowly by the market",
    "sector_relative": "ranking within sector keeps the stock-specific signal and drops the sector bet",
    "regime_gated": "cross-sectional premia crash in bear markets; a market trend filter sidesteps the crash",
    "weighted": "risk-balanced weights stop the most volatile names from dominating a noisy signal",
    "overnight": "overnight and intraday returns are set by different clienteles; the tug of war persists",
    "diversified_combo": "signals from different data sources fail at different times; averaging diversifies",
    "control": "none: a random draw, the bar for luck",
}

#: Rules removed from the seed on 2026-09-26 PM because they are a THRESHOLD of
#: a registered rule (Murat: "no trivial threshold variants"). `register`
#: would refuse them today; they are named here so the removal is not silent.
RETIRED_THRESHOLD_VARIANTS: dict = {
    "flow_rule_min2": "flow_rule with the n_firms floor at 2 instead of 3 (same signature)",
    "flow_rule_min5": "flow_rule with the n_firms floor at 5 instead of 3 (same signature)",
}


def _rules() -> list:
    S = Strategy
    R: list = []

    def add(s):
        register(R, s)
    JT = "Jegadeesh & Titman 1993, JF"
    FL = "flow_rule_score"
    # ---------------------------------------------------------------- momentum
    add(S("mom_12_1", "momentum", "12-1 month return (skip the latest month)",
          col("mom_252_21"), source=_lit("MOM-01", JT),
          literature_reported="~1%/mo raw, 1965-1989 NYSE/AMEX (decile L/S)"))
    add(S("mom_12_1_large", "momentum", "12-1 momentum, large+mega band",
          col("mom_252_21"), "large",
          source=_lit("MOM-09", "practitioner liquidity-screened momentum")))
    add(S("mom_12_1_mega", "momentum", "12-1 momentum, mega band (>= $1B/day)",
          col("mom_252_21"), "mega", source=_lit("SIZ-06", "derived; the mega-cap as sensor")))
    add(S("mom_12_1_mid", "momentum", "12-1 momentum, mid band", col("mom_252_21"), "mid"))
    add(S("mom_12_1_small", "momentum", "12-1 momentum, small band (small + momentum)",
          col("mom_252_21"), "small", source=_lit("SIZ-03", "size/momentum double sort")))
    add(S("mom_12_1_q", "momentum", "12-1 momentum, rebalanced quarterly",
          col("mom_252_21"), hold_months=3))
    add(S("mom_6_1", "momentum", "6-1 month return", col("mom_126_21"),
          source=_lit("MOM-02", JT), literature_reported="weaker than 12-1, still positive"))
    add(S("mom_6_1_large", "momentum", "6-1 momentum, large+mega", col("mom_126_21"), "large"))
    add(S("mom_6_1_q", "momentum", "6-1 momentum, quarterly", col("mom_126_21"), hold_months=3))
    add(S("mom_3_1", "momentum", "3-1 month return", col("mom_63_21"),
          source=_lit("MOM-03", "textbook variant"),
          literature_reported="weakest classic window"))
    add(S("mom_12m", "momentum", "12-month return, no skip", col("mom_252")))
    add(S("mom_6m", "momentum", "6-month return, no skip", col("mom_126")))
    add(S("mom_12_7", "momentum", "intermediate momentum, months t-12..t-6",
          col("mom_252_126"), source=_lit("MOM-08", "Novy-Marx 2012, JFE"),
          literature_reported="t-12..t-7 beats t-6..t-2 in-sample"))
    add(S("hi52", "momentum", "price / 52-week high (nearness to the high)",
          col("px_vs_52w_high"), source=_lit("MOM-04", "George & Hwang 2004, JF"),
          literature_reported="comparable to 12-1; Quantpedia #0088 11.75%/yr OOS"))
    add(S("hi52_large", "momentum", "52-week-high nearness, large+mega",
          col("px_vs_52w_high"), "large"))
    add(S("hi52_q", "momentum", "52-week-high nearness, quarterly",
          col("px_vs_52w_high"), hold_months=3))
    add(S("resid_mom_63", "momentum", "63-session return net of beta x market",
          col("resid_mom_63"), source=_lit("MOM-05", "Blitz, Huij & Martens 2011"),
          literature_reported="lower turnover, similar Sharpe to raw momentum"))
    add(S("resid_mom_12_1", "momentum", "12-1 residual (beta-adjusted) return",
          col("resid_mom_12_1")))
    add(S("resid_mom_12_1_large", "momentum", "12-1 residual momentum, large+mega",
          col("resid_mom_12_1"), "large"))
    add(S("frog_in_pan", "momentum",
          "rank-avg: 12-1 momentum, continuous information (low ID)",
          combo(("mom_252_21", 1), ("info_discreteness", -1)),
          source=_lit("MOM-11", "Da, Gurun & Warachka 2014, RFS"),
          literature_reported="gradual-information momentum beats discrete-jump momentum"))
    add(S("up_days_12m", "momentum", "share of up days over the 12-1 window",
          col("up_days_12_1")))
    add(S("trend_ma50_200", "trend", "50-day MA / 200-day MA (golden-cross strength)",
          col("ma50_vs_ma200"),
          source=_lit("RET-01", "technical canon; Brock, Lakonishok & LeBaron 1992"),
          literature_reported="edge, if any, at the index level (LOW as stock selection)"))
    add(S("px_vs_ma200", "trend", "price / 200-day MA", col("px_vs_ma200")))
    add(S("px_vs_ma200_large", "trend", "price / 200-day MA, large+mega",
          col("px_vs_ma200"), "large"))
    # ---------------------------------------------------------------- reversal
    add(S("rev_1m", "reversal", "last month's losers (-21 session return)",
          col("mom_21", -1), source=_lit("REV-06", "Jegadeesh 1990; Fama & French 1996"),
          literature_reported="small but positive monthly; weak global replicator (JKP)"))
    add(S("rev_1m_large", "reversal", "1-month reversal, large+mega", col("mom_21", -1), "large"))
    add(S("rev_1m_small", "reversal", "1-month reversal, small band",
          col("mom_21", -1), "small", source=_lit("REV-04", "extension of REV-01/02")))
    add(S("rev_5d", "reversal", "last week's losers (-5 session return)", col("rev_5", -1),
          source=_lit("REV-02", "Lo & MacKinlay 1990"),
          literature_reported="contrarian profits, partly bid-ask bounce"))
    add(S("rev_5d_large", "reversal", "1-week reversal, large+mega", col("rev_5", -1), "large"))
    add(S("buy_the_dip", "reversal", "deepest 63-session drawdown, large+mega",
          col("max_drawdown_63", -1), "large", source=_lit("RET-03", "retail canon"),
          literature_reported="LOW; overlaps REV/LV"))
    add(S("rev_in_winners", "reversal", "1-month losers among the top-half 12-1 winners",
          within_top(col("mom_21", -1), "mom_252_21", 0.5),
          source=_lit("MOM-12", "practitioner composite")))
    # ---------------------------------------------------------------- low risk
    add(S("lowvol_21", "low_risk", "lowest 21-session volatility", col("vol_21", -1),
          source=_lit("LV-01", "Ang, Hodrick, Xing & Zhang 2006, JF"),
          literature_reported="low idio-vol stocks earn higher average returns"))
    add(S("lowvol_63", "low_risk", "lowest 63-session volatility", col("vol_63", -1)))
    add(S("lowvol_63_large", "low_risk", "lowest 63-session vol, large+mega",
          col("vol_63", -1), "large"))
    add(S("lowvol_63_q", "low_risk", "lowest 63-session vol, quarterly", col("vol_63", -1),
          hold_months=3, source=_lit("LV-02", "same literature, lower turnover")))
    add(S("lowvol_252", "low_risk", "lowest 252-session volatility", col("vol_252", -1)))
    add(S("lowvol_252_large", "low_risk", "lowest 252-session vol, large+mega",
          col("vol_252", -1), "large"))
    add(S("lowvol_252_mega", "low_risk", "lowest 252-session vol, mega band",
          col("vol_252", -1), "mega"))
    add(S("lowbeta", "low_risk", "lowest 252-session beta", col("beta_252", -1),
          source=_lit("LV-03", "Frazzini & Pedersen 2014, JFE"),
          literature_reported=("US BAB Sharpe 0.78 1926-2012; FF3 alpha 0.73%/mo t 7.39 "
                               "(levered L/S; ours is long-only and unlevered)")))
    add(S("lowbeta_large", "low_risk", "lowest 252-session beta, large+mega",
          col("beta_252", -1), "large", source=_lit("LV-08", "BAB restricted to large/mega")))
    add(S("low_idio_63", "low_risk", "lowest idiosyncratic (residual) vol, 63 sessions",
          col("idio_vol_63", -1)))
    add(S("low_idio_63_large", "low_risk", "lowest idiosyncratic vol, large+mega",
          col("idio_vol_63", -1), "large"))
    add(S("low_max", "low_risk", "lowest max daily return over 21 sessions (anti-lottery)",
          col("max_ret_21", -1), source="literature:MAX Bali, Cakici & Whitelaw 2011, JFE",
          literature_reported="high-MAX stocks underperform (~1%/mo spread in-sample)"))
    add(S("low_max_large", "low_risk", "lowest MAX, large+mega", col("max_ret_21", -1), "large"))
    add(S("skew_high", "low_risk", "least negative 63-session skew", col("skew_63"),
          source=_lit("LV-06", "Harvey & Siddique 2000, JF"),
          literature_reported="co-skewness priced in-sample"))
    add(S("shallow_dd", "low_risk", "shallowest 63-session drawdown", col("max_drawdown_63"),
          source=_lit("LV-05", "practitioner path-quality overlay")))
    add(S("vol_compression", "low_risk", "lowest vol_21 / vol_63", col("vol_ratio", -1),
          source=_lit("LV-04", "practitioner overlay")))
    # ------------------------------------------------------ size and liquidity
    add(S("illiquid", "size_liquidity", "highest Amihud illiquidity", col("amihud"),
          source=_lit("SIZ-01", "Amihud 2002, JFM"),
          literature_reported="illiquidity premium; OUR §59: the edge IS the illiquidity, costs eat it"))
    add(S("illiquid_mid_plus", "size_liquidity", "highest Amihud among mid+ names",
          col("amihud"), "mid_plus"))
    add(S("small_dv", "size_liquidity", "lowest dollar volume (size proxy)",
          col("dollar_vol_log", -1), source=_lit("SIZ-02", "Banz 1981, JFE"),
          literature_reported="flat-to-negative in the US since the 1980s"))
    add(S("small_not_illiquid", "size_liquidity", "lowest dollar volume within the mid band",
          col("dollar_vol_log", -1), "mid", source=_lit("SIZ-05", "derived from §59")))
    add(S("big_dv", "size_liquidity", "highest dollar volume (mega-cap proxy)",
          col("dollar_vol_log")))
    add(S("turnover_surge", "size_liquidity", "5-day / 63-day dollar volume surge",
          col("turnover_surge")))
    add(S("quiet_volume", "size_liquidity", "lowest 5-day / 63-day dollar volume (neglect)",
          col("turnover_surge", -1)))
    # ---------------------------------------------------------------- seasonal
    add(S("seasonality_hs", "seasonality",
          "mean same-calendar-month return over the prior 1-5 years",
          col("seas_same_month"), source=_lit("SEAS-08", "Heston & Sadka 2008, JFE"),
          literature_reported="Quantpedia #0125: 8.60%/yr, 12.20% vol OOS"))
    add(S("seasonality_hs_large", "seasonality", "same-month seasonality, large+mega",
          col("seas_same_month"), "large"))
    add(S("seasonality_1y", "seasonality", "same calendar month, last year only",
          col("seas_lag12")))
    # ----------------------------------------------------------------- quality
    NM = "Novy-Marx 2013, JFE"
    add(S("gp_at", "quality", "gross profits / assets", col("gp_at"),
          source=_lit("QUAL-01", NM), caveat=_FUND_CAVEAT,
          literature_reported="PMU 0.31%/mo t 2.49; FF3-adj 0.52%/mo t 4.49 (1963-2010)"))
    add(S("gp_at_large", "quality", "gross profitability, large+mega", col("gp_at"), "large",
          caveat=_FUND_CAVEAT))
    add(S("gp_at_q", "quality", "gross profitability, quarterly", col("gp_at"),
          hold_months=3, caveat=_FUND_CAVEAT))
    add(S("ope_be", "quality", "operating income / book equity", col("ope_be"),
          source=_lit("QUAL-04", "Fama & French 2015 (RMW)"), caveat=_FUND_CAVEAT,
          literature_reported="RMW leg of FF5; JKP profitability theme replicates 82.4%"))
    add(S("roe", "quality", "net income / book equity", col("ni_be"), caveat=_FUND_CAVEAT))
    add(S("cash_rich", "quality", "cash / assets", col("cash_at"), caveat=_FUND_CAVEAT))
    add(S("low_debt", "quality", "lowest debt / assets", col("debt_at", -1), caveat=_FUND_CAVEAT))
    add(S("gross_margin", "quality", "gross margin level", col("gross_margin"),
          caveat=_FUND_CAVEAT))
    add(S("margin_expansion", "quality", "year-over-year gross-margin change", col("gm_chg"),
          source=_lit("QUAL-02", "Novy-Marx derivative"), caveat=_FUND_CAVEAT))
    add(S("quality_composite", "quality", "rank-avg: gp_at, ope_be, low debt, low 252d vol",
          combo(("gp_at", 1), ("ope_be", 1), ("debt_at", -1), ("vol_252", -1)),
          source=_lit("QUAL-05", "Asness, Frazzini & Pedersen 2019, RAS (QMJ)"),
          caveat=_FUND_CAVEAT,
          literature_reported="AQR QMJ live Sharpe ~0.3-0.4 net (not re-verified)"))
    add(S("quality_composite_large", "quality", "QMJ-style composite, large+mega",
          combo(("gp_at", 1), ("ope_be", 1), ("debt_at", -1), ("vol_252", -1)), "large",
          caveat=_FUND_CAVEAT))
    # -------------------------------------------------------------- investment
    add(S("low_asset_growth", "investment", "lowest year-over-year asset growth",
          col("at_gr1", -1), source=_lit("INV-01", "Cooper, Gulen & Schill 2008, JF"),
          caveat=_FUND_CAVEAT,
          literature_reported="Quantpedia #0052: 20.84%/yr OOS; concentrated in small caps"))
    add(S("low_asset_growth_large", "investment", "lowest asset growth, large+mega",
          col("at_gr1", -1), "large", caveat=_FUND_CAVEAT))
    # -------------------------------------------------------------- inflection
    infl = gated(gated(col("inflection"), "rev_gr", lo=0.0), "gm_chg", lo=0.0)
    add(S("revenue_growth", "inflection", "year-over-year revenue growth", col("rev_gr"),
          source=_lit("INFL-02", "derived single-leg inflection"), caveat=_FUND_CAVEAT))
    add(S("inflection", "inflection", "revenue growth x margin change, both positive",
          infl, source=_lit("INFL-01", "spec's named row; cf. Piotroski 2000 F-score"),
          caveat=_FUND_CAVEAT,
          literature_reported="OUR §63: the archetype showed no dose-response"))
    add(S("inflection_large", "inflection", "inflection, large+mega", infl, "large",
          caveat=_FUND_CAVEAT))
    # ---------------------------------------------------------- revision flow
    AR = "Womack 1996, JF"
    add(S("flow_rule", "revision_flow",
          "net_raises x n_firms over 90d, >= 3 firms (the month-end rule)",
          gated(col(FL), "n_firms", lo=3), caveat=_FLOW_CAVEAT,
          source="ours (scripts/revision_flow_sweep.py THE RULE)"))
    add(S("flow_rule_large", "revision_flow", "the month-end rule, large+mega",
          gated(col(FL), "n_firms", lo=3), "large", caveat=_FLOW_CAVEAT))
    add(S("flow_rule_q", "revision_flow", "the month-end rule, quarterly",
          gated(col(FL), "n_firms", lo=3), hold_months=3, caveat=_FLOW_CAVEAT))
    add(S("net_raises", "revision_flow", "raises minus lowers over 90 days",
          col("net_raises"), source=_lit("AREV-01", AR), caveat=_FLOW_CAVEAT,
          literature_reported="post-revision drift, strongest on the sell side"))
    add(S("n_firms_acting", "revision_flow", "distinct firms acting over 90 days (attention)",
          col("n_firms"), source=_lit("AREV-02", "Gleason & Lee 2003, TAR"),
          caveat=_FLOW_CAVEAT))
    add(S("target_change", "revision_flow", "median target change over 90 days",
          col("median_target_change"), source=_lit("AREV-03", "Brav & Lehavy 2003, JF"),
          caveat=_FLOW_CAVEAT,
          literature_reported="target revisions predict incrementally over EPS revisions"))
    add(S("net_raises_30d", "revision_flow", "raises minus lowers over 30 days",
          col("net_raises_30"), caveat=_FLOW_CAVEAT))
    add(S("net_raises_180d", "revision_flow", "raises minus lowers over 180 days",
          col("net_raises_180"), caveat=_FLOW_CAVEAT))
    add(S("flow_acceleration", "revision_flow", "30d net raises minus a third of 90d",
          col("flow_accel"), source=_lit("AREV-04/09", "Jegadeesh & Kim 2006, JFM"),
          caveat=_FLOW_CAVEAT))
    add(S("mom_no_downgrades", "revision_flow",
          "12-1 momentum among covered names with net_raises >= 0",
          gated(col("mom_252_21"), "net_raises", lo=0.0),
          source=_lit("AREV-07", "practitioner downgrade-avoidance overlay"),
          caveat=_FLOW_CAVEAT))
    # ------------------------------------------------------------ combinations
    add(S("mom_lowvol", "combination", "rank-avg: 12-1 momentum, low 252d vol",
          combo(("mom_252_21", 1), ("vol_252", -1))))
    add(S("mom_lowvol_large", "combination", "momentum + low vol, large+mega",
          combo(("mom_252_21", 1), ("vol_252", -1)), "large"))
    add(S("mom_gp", "combination", "rank-avg: 12-1 momentum, gross profitability",
          combo(("mom_252_21", 1), ("gp_at", 1)),
          source=_lit("COMB-02", "Novy-Marx four-factor logic"), caveat=_FUND_CAVEAT))
    add(S("mom_gp_large", "combination", "momentum + profitability, large+mega",
          combo(("mom_252_21", 1), ("gp_at", 1)), "large", caveat=_FUND_CAVEAT))
    add(S("gp_lowvol", "combination", "rank-avg: gross profitability, low 252d vol",
          combo(("gp_at", 1), ("vol_252", -1)),
          source=_lit("LV-07", "Asness, Frazzini & Pedersen 2019"), caveat=_FUND_CAVEAT))
    add(S("gp_lowvol_large", "combination", "profitability + low vol, large+mega",
          combo(("gp_at", 1), ("vol_252", -1)), "large", caveat=_FUND_CAVEAT))
    add(S("mom_gp_lowvol", "combination", "rank-avg: momentum, profitability, low vol",
          combo(("mom_252_21", 1), ("gp_at", 1), ("vol_252", -1)), caveat=_FUND_CAVEAT))
    add(S("hi52_gp", "combination", "rank-avg: 52-week-high nearness, profitability",
          combo(("px_vs_52w_high", 1), ("gp_at", 1)), caveat=_FUND_CAVEAT))
    add(S("residmom_lowidio", "combination", "rank-avg: residual 12-1 momentum, low idio vol",
          combo(("resid_mom_12_1", 1), ("idio_vol_63", -1))))
    add(S("mom_low_ag", "combination", "rank-avg: momentum, low asset growth",
          combo(("mom_252_21", 1), ("at_gr1", -1)),
          source=_lit("INV-03", "Hou, Xue & Zhang 2015 (q-factors)"), caveat=_FUND_CAVEAT))
    add(S("gp_low_ag", "combination", "rank-avg: profitability, low asset growth",
          combo(("gp_at", 1), ("at_gr1", -1)), caveat=_FUND_CAVEAT))
    add(S("mom_flow", "combination", "rank-avg: 12-1 momentum, net raises",
          combo(("mom_252_21", 1), ("net_raises", 1)),
          source=_lit("AREV-06", "Chan, Jegadeesh & Lakonishok 1996, JF"),
          caveat=_FLOW_CAVEAT,
          literature_reported="combined signal beats either alone in-sample"))
    add(S("gp_flow", "combination", "rank-avg: profitability, net raises",
          combo(("gp_at", 1), ("net_raises", 1)), caveat=_BOTH))
    add(S("inflection_flow", "combination", "rank-avg: inflection, net raises (do analysts lag?)",
          combo(("inflection", 1), ("net_raises", 1)), source=_lit("INFL-04", "derived"),
          caveat=_BOTH))
    add(S("seas_mom", "combination", "rank-avg: same-month seasonality, 12-1 momentum",
          combo(("seas_same_month", 1), ("mom_252_21", 1))))
    add(S("lowbeta_gp", "combination", "rank-avg: low beta, profitability",
          combo(("beta_252", -1), ("gp_at", 1)), caveat=_FUND_CAVEAT))
    add(S("mom_rev", "combination", "rank-avg: 12-1 momentum, 1-month reversal",
          combo(("mom_252_21", 1), ("mom_21", -1))))
    add(S("small_gp_mom", "combination", "rank-avg: momentum, profitability, small band",
          combo(("mom_252_21", 1), ("gp_at", 1)), "small",
          source=_lit("COMB-06", "triple sort"), caveat=_FUND_CAVEAT))
    add(S("lowvol_hi52", "combination", "rank-avg: low 252d vol, 52-week-high nearness",
          combo(("vol_252", -1), ("px_vs_52w_high", 1))))
    add(S("rev5_lowvol_large", "combination", "rank-avg: 1-week reversal, low vol, large+mega",
          combo(("rev_5", -1), ("vol_63", -1)), "large"))
    add(S("trend_quality", "combination", "rank-avg: price/200d MA, profitability, low debt",
          combo(("px_vs_ma200", 1), ("gp_at", 1), ("debt_at", -1)), caveat=_FUND_CAVEAT))
    add(S("margin_mom", "combination", "rank-avg: margin expansion, 6-1 momentum",
          combo(("gm_chg", 1), ("mom_126_21", 1)), caveat=_FUND_CAVEAT))
    add(S("cash_lowvol", "combination", "rank-avg: cash-rich, low vol",
          combo(("cash_at", 1), ("vol_252", -1)), caveat=_FUND_CAVEAT))
    add(S("roe_mom_large", "combination", "rank-avg: ROE, momentum, large+mega",
          combo(("ni_be", 1), ("mom_252_21", 1)), "large", caveat=_FUND_CAVEAT))
    add(S("frog_large", "combination", "frog-in-the-pan momentum, large+mega",
          combo(("mom_252_21", 1), ("info_discreteness", -1)), "large"))
    add(S("lowmax_mom", "combination", "rank-avg: low MAX, 12-1 momentum",
          combo(("max_ret_21", -1), ("mom_252_21", 1))))
    add(S("flow_lowvol", "combination", "rank-avg: net raises, low vol",
          combo(("net_raises", 1), ("vol_252", -1)), caveat=_FLOW_CAVEAT))
    _expansion(add)
    _expansion_note(add)
    # ---------------------------------------------------------------- controls
    for sd in (1, 2, 3):
        add(S(f"random_{sd}", "control", f"random k names each month (hash seed {sd})",
              seeded_noise(sd), control=True))
    add(S("random_large", "control", "random k names each month, large+mega",
          seeded_noise(7), "large", control=True))
    _diagnostic_controls(add)
    return R


#: Registered 2026-09-26 evening from the adjudicated review of chunks D+E.
REGISTERED_2026_09_26_REVIEW = "2026-09-26T09:20:00+00:00"
#: The quarterly offsets of `mom_12_1_q` (decision-date months).
QUARTER_OFFSETS = {"jajo": (1, 4, 7, 10), "fman": (2, 5, 8, 11), "mjsd": (3, 6, 9, 12)}


def _diagnostic_controls(add) -> None:
    """Three $0 controls (kind: control -- printed beside the rules, never
    ranked, never counted as trials). Each answers one question the review
    asked of a row the board would otherwise be read on:

    * `skill_mom_ranks_21_40` -- `skill_mom`'s picks ranked 21-40. If they earn
      what 1-20 earn, the ordering is uninformative and the edge is the
      covered-momentum universe.
    * `unskilled_mom` -- `skill_mom` built from raises by the NON-skilled firms
      only. The direct skill test: `skill_mom - unskilled_mom` by year, with
      2025 excluded (CLAUDE.md rule 11).
    * `mom_12_1_q_{jajo,fman,mjsd}` -- the board's best-DSR row at each of its
      three quarterly offsets. If the advantage over monthly `mom_12_1` lives
      in one offset, it is calendar timing plus free rebalancing.
    """
    S = Strategy
    MOM = "mom_252_21"
    reg = REGISTERED_2026_09_26_REVIEW
    add(S("skill_mom_ranks_21_40", "diagnostic_control",
          "skill_mom's picks ranked 21-40 (the same rank-avg of skilled-firm net raises and 12-1 momentum)",
          rank_band(combo(("skill_net_raises_90", 1), (MOM, 1)), 21, 40),
          control=True, first_registered_utc=reg, caveat=_FLOW_CAVEAT,
          economic_reason="control: is the ordering inside the top informative"))
    add(S("unskilled_mom", "diagnostic_control",
          "rank-avg: net raises by the NON-skilled firms only, 12-1 momentum",
          combo(("unskilled_net_raises_90", 1), (MOM, 1)),
          control=True, first_registered_utc=reg, caveat=_FLOW_CAVEAT,
          economic_reason="control: skill_mom without the skill filter's firms"))
    for tag, months in QUARTER_OFFSETS.items():
        add(S(f"mom_12_1_q_{tag}", "diagnostic_control",
              f"12-1 momentum, quarterly, rebalanced at decision months {list(months)}",
              col(MOM), hold_months=3, rebalance_months=months, control=True,
              first_registered_utc=reg,
              economic_reason="control: is mom_12_1_q's edge one calendar offset"))


def is_random_control(row_or_rule) -> bool:
    """The LUCK BAR: the random-k controls only (family `control`), never the
    diagnostic controls, whose returns are a rule's returns."""
    fam = (row_or_rule.get("family") if isinstance(row_or_rule, dict)
           else getattr(row_or_rule, "family", None))
    return fam == "control"


def dev_selected_sealed_evaluated(rows: list, *, n_blocks: int | None = None,
                                  tops: tuple = (10, 20, 50)) -> dict:
    """The one honest out-of-sample number a backtest board already contains.

    Pick the top-n rules on the DEV window only (dev net CAGR minus SPY), then
    read those same rules on the 2024-26 selection window. The dev rank never
    saw 2024-26 (it is still hindsight -- every rule was written in 2026 -- but
    it is not selected ON the window it is evaluated on). Plus the Spearman
    correlation of dev rank vs 2024-26 rank across every rule, the count good
    in both windows, and the MDE of a `n_blocks`-month window.

    Controls are excluded. Ties sort by id, so the block is deterministic.
    """
    cand = [r for r in rows if not r.get("control")
            and r.get("dev_vs_spy") is not None and r.get("sealed_vs_spy") is not None]
    out: dict = {"label": SELECTION_WINDOW_LABEL, "n_rules": len(cand),
                 "selection": ("top-n by dev_vs_spy (dev net CAGR - SPY CAGR, entry <= "
                               f"{DEV_END}); evaluated on sealed_vs_spy (entry >= {SEALED_START})")}
    if not cand:
        return {**out, "status": "REFUSED", "why": "no rule carries both dev and 2024-26 numbers"}
    ranked = sorted(cand, key=lambda r: (-r["dev_vs_spy"], r["id"]))
    for n in tops:
        sel = ranked[:n]
        v = _np.array([r["sealed_vs_spy"] for r in sel], dtype=float)
        out[f"top_{n}"] = {"n": len(sel), "ids": [r["id"] for r in sel],
                           "mean_selection_window_vs_spy": float(v.mean()),
                           "median_selection_window_vs_spy": float(_np.median(v)),
                           "n_beat_spy": int((v > 0).sum()),
                           "mean_dev_vs_spy": float(_np.mean([r["dev_vs_spy"] for r in sel]))}
    dv = _np.array([r["dev_vs_spy"] for r in cand], dtype=float)
    sv = _np.array([r["sealed_vs_spy"] for r in cand], dtype=float)
    if len(cand) >= 3:
        from scipy.stats import spearmanr
        rho, pv = spearmanr(dv, sv)
        rho, pv = float(rho), float(pv)
    else:
        rho, pv = float("nan"), None
    out["spearman_dev_vs_selection_window"] = {"rho": rho, "p_value": pv, "n": len(cand)}
    both = [r for r in cand if r["dev_vs_spy"] > 0 and r["sealed_vs_spy"] > 0]
    strict = [r for r in both
              if (r.get("top5_months_share_of_log_return") is not None
                  and r["top5_months_share_of_log_return"] < 0.6)
              and (r.get("max_dd") is not None and r["max_dd"] > -0.40)]
    out["n_beat_spy_in_both_windows"] = len(both)
    out["n_beat_spy_in_both_windows_top5_lt_0_6_dd_gt_m40"] = len(strict)
    sig = []
    for r in cand:
        m, ir = r.get("mean_active_monthly"), r.get("information_ratio_annual")
        if m is not None and ir is not None and _np.isfinite(ir) and abs(ir) > 1e-9:
            s_ = abs(m * _np.sqrt(12.0) / ir)
            if _np.isfinite(s_) and s_ > 0:
                sig.append(s_)
    nb = int(n_blocks or max((r.get("n_sealed_months") or 0) for r in cand) or 0)
    if sig and nb >= 2:
        s_med = float(_np.median(sig))
        se = s_med / _np.sqrt(nb)
        out["mde"] = {"active_sigma_monthly_median": s_med, "n_blocks": nb,
                      "se_monthly": float(se), "mde_monthly_80pct_power": float(MDE_Z * se),
                      "mde_annualised_simple": float(MDE_Z * se * 12),
                      "basis": ("median across rules of |mean_active_monthly * sqrt(12) / IR_annual| "
                                "(the full-window monthly active sigma); SE = sigma / sqrt(blocks); "
                                "MDE = 2.8 SE (two-sided 5%, 80% power)")}
    else:
        out["mde"] = {"status": "UNKNOWN", "why": f"{len(sig)} sigmas, {nb} blocks"}
    t10 = out.get("top_10") or {}
    md = out["mde"]
    out["sentence"] = (
        f"Choosing the top {t10.get('n')} rules by dev (pre-2024) results alone gave "
        f"{t10.get('mean_selection_window_vs_spy', 0)*100:+.1f} pp/yr mean vs SPY in the "
        f"{SELECTION_WINDOW_LABEL} (median {t10.get('median_selection_window_vs_spy', 0)*100:+.1f} pp; "
        f"{t10.get('n_beat_spy')} of {t10.get('n')} beat SPY); dev-to-2024-26 rank Spearman "
        f"{rho:.2f} over {len(cand)} rules; {len(both)} rules beat SPY in both windows"
        + (f"; the MDE of a {md['n_blocks']}-block window at 80% power is "
           f"{md['mde_monthly_80pct_power']*100:.1f}%/month" if "mde_monthly_80pct_power" in md else "")
        + ".")
    return out


def by_year_gap(a: dict, b: dict, *, exclude: tuple = ("2025",)) -> dict:
    """Excess-by-year of row `a` minus row `b` (`by_year[y].excess`), with the
    years in `exclude` left out of the sum and printed beside it."""
    ya, yb = a.get("by_year") or {}, b.get("by_year") or {}
    years = sorted(set(ya) & set(yb))
    gap = {y: (ya[y]["excess"] - yb[y]["excess"]) for y in years
           if ya[y].get("excess") is not None and yb[y].get("excess") is not None}
    kept = {y: v for y, v in gap.items() if y not in exclude}
    return {"a": a.get("id"), "b": b.get("id"), "gap_by_year": gap, "excluded": list(exclude),
            "sum_excluding": float(sum(kept.values())) if kept else None,
            "mean_excluding": float(_np.mean(list(kept.values()))) if kept else None,
            "n_years_positive_excluding": int(sum(1 for v in kept.values() if v > 0)),
            "n_years_excluding": len(kept)}


_INS_CAVEAT = ("SEC Form 4 bulk (sec_insider/insider_events_v1), keyed on observed_at_utc = "
               "filing date end-of-day (conservative); symbol via the CRSP stocknames link; "
               "the file ends 2026-07-01, so the last ~2 months carry no new insider rows")
_8K_CAVEAT = ("EDGAR 8-K item codes (edgar_8k/eightk_items), counted strictly before the "
              "decision date on the acceptance date; tickers are EDGAR's CURRENT map, so a "
              "renamed or dead issuer's older filings can be missing")
_EARN_CAVEAT = (_8K_CAVEAT + "; an earnings date is an 8-K item 2.02 filing; the EXPECTED next "
                "print is last year's 2.02 + 364d or the last 2.02 + 91d (Frazzini-Lamont)")
_SI_CAVEAT = ("Compustat sec_shortint (split-adjusted `shortintadj`), available at settlement "
              "`datadate` + 26 calendar days (the receipt measured a 10-26 day publication "
              "lag; 26 is the conservative end); gvkey->symbol via the CURRENT Compustat "
              "ticker, so dead issuers mostly carry no short interest")
_SECTOR_CAVEAT = ("GICS sector is Compustat's CURRENT classification per ticker, applied to "
                  "every past month (static map: a re-classified firm is mislabelled back then)")
_RATING_CAVEAT = _FLOW_CAVEAT + "; ratings/firms from the same yfinance upgrade/downgrade feed"
_REGIME_NOTE = ("regime gate: SPY close vs its own 200-session mean at the decision date; "
                "below it the book is CASH earning 0 (T-bills not credited)")


def _expansion(add) -> None:
    """Chunk D (2026-09-26 PM): new FAMILIES, not new thresholds.

    Every rule here is registered through `register`, which refuses a rule
    whose signature (structure, universe, holding, weighting, regime gate)
    matches one already in the library. Thresholds inside a rule were chosen
    ONCE, from the literature or the obvious unit, and are not swept.
    """
    S = Strategy
    P = REGISTERED_2026_09_26_PM
    MOM = "mom_252_21"

    def E(*a, **kw):
        kw.setdefault("first_registered_utc", P)
        add(S(*a, **kw))

    # ------------------------------------------------ analyst ratings (not targets)
    E("upgrades_net_90", "analyst_rating", "rating upgrades minus downgrades over 90 days",
      col("rating_net_90"), source=_lit("AREV-01", "Womack 1996, JF (recommendation changes)"),
      caveat=_RATING_CAVEAT, economic_reason=(
          "a recommendation CHANGE is costly for the analyst; Womack finds drift for months after it"))
    E("upgrades_net_large", "analyst_rating", "rating upgrades minus downgrades, large+mega",
      col("rating_net_90"), "large", caveat=_RATING_CAVEAT)
    E("initiations_90", "analyst_rating", "new coverage initiations over 90 days (attention arriving)",
      col("initiations_90"), caveat=_RATING_CAVEAT, economic_reason=(
          "new coverage widens the investor base (Merton 1987 neglect premium unwinding)"))
    E("init_mom", "analyst_rating", "rank-avg: initiations, 12-1 momentum",
      combo(("initiations_90", 1), (MOM, 1)), caveat=_RATING_CAVEAT)
    E("mom_no_rating_downgrade", "analyst_rating",
      "12-1 momentum among covered names with NO rating downgrade in 90 days",
      gated(col(MOM), "rating_downgrades_90", hi=0.0), caveat=_RATING_CAVEAT,
      economic_reason="downgrades mark the end of a momentum run; avoiding them avoids the crash names")
    # ---------------------------------------------- lead vs chase raises (review B)
    RB = "docs/reviews/REVIEW_2026-09-25_CHUNK0_THE_DAYS_BUILD.md idea B; Da & Schaumburg 2011"
    E("lead_raises", "lead_chase",
      "target raises made when the stock was flat/down over the 10 sessions before (LEAD)",
      col("lead_raises_90"), source=f"ours ({RB})", caveat=_FLOW_CAVEAT,
      economic_reason="a raise that precedes the price move is the analyst's information, not a reaction")
    E("chase_raises", "lead_chase",
      "target raises made after a > +1 sigma 10-session run-up (CHASE) -- the control arm",
      col("chase_raises_90"), source=f"ours ({RB})", caveat=_FLOW_CAVEAT,
      economic_reason="the falsifier of lead_raises: if chasing pays as much, the lead story is wrong")
    E("lead_raises_large", "lead_chase", "LEAD raises, large+mega", col("lead_raises_90"), "large",
      caveat=_FLOW_CAVEAT)
    E("lead_minus_chase", "lead_chase", "LEAD raises minus CHASE raises over 90 days",
      col("lead_minus_chase_90"), caveat=_FLOW_CAVEAT)
    E("lead_raises_in_losers", "lead_chase",
      "LEAD raises among the bottom-half 63-session performers (raises against the tape)",
      within_top(col("lead_raises_90"), "mom_63", 0.5, sign=-1), caveat=_FLOW_CAVEAT)
    E("lead_gp", "lead_chase", "rank-avg: LEAD raises, gross profitability",
      combo(("lead_raises_90", 1), ("gp_at", 1)), caveat=_BOTH)
    # ------------------------------------------------ analyst skill and first movers
    E("skill_raises", "analyst_skill",
      "net raises by firms whose PAST raises beat SPY over 63 sessions (resolved before the date)",
      col("skill_net_raises_90"), source="literature:C-FAM analyst-skill persistence (Mikhail, Walther & Willis 2004)",
      caveat=_FLOW_CAVEAT)
    E("skill_raises_large", "analyst_skill", "skilled-firm net raises, large+mega",
      col("skill_net_raises_90"), "large", caveat=_FLOW_CAVEAT)
    E("skill_mom", "analyst_skill", "rank-avg: skilled-firm net raises, 12-1 momentum",
      combo(("skill_net_raises_90", 1), (MOM, 1)), caveat=_FLOW_CAVEAT)
    E("first_mover_raises", "analyst_skill",
      "raises that were the FIRST raise on the name in 30 days (the leader, not the herd)",
      col("first_mover_raises_90"), source="literature:C-FAM analyst first-mover (Cooper, Day & Lewis 2001, JFE)",
      caveat=_FLOW_CAVEAT, economic_reason=(
          "lead analysts move prices; followers herd -- the first raise carries the information"))
    E("first_mover_large", "analyst_skill", "first-mover raises, large+mega",
      col("first_mover_raises_90"), "large", caveat=_FLOW_CAVEAT)
    # ------------------------------------------------ dispersion (historical, AREV-10)
    DMS = "Diether, Malloy & Scherbina 2002, JF"
    E("low_target_dispersion", "analyst_dispersion",
      "lowest cross-firm target dispersion (std/mean of each firm's latest target, 180d, >= 3 firms)",
      col("target_cv_180", -1), source=_lit("AREV-10", DMS), caveat=(
          _FLOW_CAVEAT + "; targets as-reported, so a split inside the 180d window mixes bases"),
      literature_reported="high dispersion predicts LOWER returns (short-sale constraints)")
    E("low_target_dispersion_large", "analyst_dispersion", "lowest target dispersion, large+mega",
      col("target_cv_180", -1), "large", caveat=_FLOW_CAVEAT)
    E("low_dispersion_mom", "analyst_dispersion", "rank-avg: low target dispersion, 12-1 momentum",
      combo(("target_cv_180", -1), (MOM, 1)), caveat=_FLOW_CAVEAT)
    # ------------------------------------------------ revision flow x price interactions
    E("flow_in_winners", "flow_momentum", "net raises among the top-half 12-1 winners",
      within_top(col("net_raises"), MOM, 0.5), caveat=_FLOW_CAVEAT)
    E("raises_in_losers", "flow_momentum", "net raises among the bottom-half 63-session performers",
      within_top(col("net_raises"), "mom_63", 0.5, sign=-1), caveat=_FLOW_CAVEAT,
      economic_reason="analysts raising into a falling price are fighting the tape with information")
    E("flow_accel_mom", "flow_momentum", "rank-avg: revision acceleration, 12-1 momentum",
      combo(("flow_accel", 1), (MOM, 1)), caveat=_FLOW_CAVEAT)
    E("target_change_lowvol", "flow_momentum", "rank-avg: median target change, low 252d vol",
      combo(("median_target_change", 1), ("vol_252", -1)), caveat=_FLOW_CAVEAT)
    E("flow_hi52", "flow_momentum", "rank-avg: net raises, 52-week-high nearness",
      combo(("net_raises", 1), ("px_vs_52w_high", 1)), caveat=_FLOW_CAVEAT)
    E("attention_reversal", "flow_momentum", "rank-avg: firms acting (attention), 1-month losers",
      combo(("n_firms", 1), ("mom_21", -1)), caveat=_FLOW_CAVEAT,
      economic_reason="covered names that dropped are the ones where the overreaction gets corrected")
    # ------------------------------------------------------------------ insiders
    CMP = "Cohen, Malloy & Pomorski 2012, JF"
    LL = "Lakonishok & Lee 2001, RFS"
    E("insider_buyers", "insider", "distinct insiders buying in the open market over 90 days",
      col("ins_buyers_90"), source=_lit("INS-03", LL), caveat=_INS_CAVEAT)
    E("insider_cluster_value", "insider",
      "insider buy dollars / median dollar volume, among names with >= 3 buyers in 90d (cluster)",
      gated(col("ins_buy_value_dv_90"), "ins_buyers_90", lo=3), source=_lit("INS-03", LL),
      caveat=_INS_CAVEAT, economic_reason="several insiders spending their own money at once is hard to fake")
    E("insider_opportunistic", "insider",
      "distinct OPPORTUNISTIC (non-routine) insider buyers over 180 days",
      col("ins_opp_buyers_180"), source=_lit("INS-01", CMP), caveat=_INS_CAVEAT,
      literature_reported="opportunistic L/S EW 180bps/mo t 6.07, VW 82bps/mo t 2.15 (1986-2007)")
    E("insider_officer", "insider", "distinct OFFICER open-market buyers over 90 days",
      col("ins_officer_buyers_90"), caveat=_INS_CAVEAT,
      economic_reason="officers see the operating data first; their purchases are the most informed")
    E("insider_net_ratio", "insider", "(buyers - sellers) / (buyers + sellers), 180 days",
      col("ins_net_ratio_180"), caveat=_INS_CAVEAT)
    E("insider_buy_dip", "insider", "rank-avg: insider buyers, deepest 63-session drawdown",
      combo(("ins_buyers_90", 1), ("max_drawdown_63", -1)), caveat=_INS_CAVEAT,
      economic_reason="insiders buying after a fall separate a mispricing from a broken business")
    E("insider_mom", "insider", "rank-avg: insider buyers, 12-1 momentum",
      combo(("ins_buyers_90", 1), (MOM, 1)), caveat=_INS_CAVEAT)
    E("insider_cluster_small", "insider", "insider cluster value, small band (INS-04 vs SIZ-01)",
      gated(col("ins_buy_value_dv_90"), "ins_buyers_90", lo=3), "small",
      source=_lit("INS-04", "derived from " + LL), caveat=_INS_CAVEAT)
    E("insider_buyers_large", "insider", "insider buyers, large+mega (where Lakonishok-Lee find it weak)",
      col("ins_buyers_90"), "large", caveat=_INS_CAVEAT)
    E("insider_flow", "insider", "rank-avg: opportunistic insider buyers, analyst net raises",
      combo(("ins_opp_buyers_180", 1), ("net_raises", 1)),
      source=_lit("INS-05", "natural extension"), caveat=_INS_CAVEAT + "; " + _FLOW_CAVEAT)
    E("insider_opp_mom", "insider", "rank-avg: opportunistic insider buyers, 12-1 momentum",
      combo(("ins_opp_buyers_180", 1), (MOM, 1)), source=_lit("COMB-05", "derived"),
      caveat=_INS_CAVEAT)
    E("inflection_insider", "insider", "rank-avg: inflection, opportunistic insider buyers",
      combo(("inflection", 1), ("ins_opp_buyers_180", 1)), source=_lit("COMB-08", "derived"),
      caveat=_INS_CAVEAT + "; " + _FUND_CAVEAT)
    E("mom_no_insider_selling", "insider",
      "12-1 momentum among names with NO open-market insider sale in 90 days",
      gated(col(MOM), "ins_sellers_90", hi=0.0), source=_lit("INS-02", CMP + " (as an exclusion)"),
      caveat=_INS_CAVEAT, economic_reason="insiders selling into strength is the sell half CMP found stronger")
    # ---------------------------------------------------- earnings events (8-K 2.02)
    E("ear_drift", "earnings_event",
      "earnings-announcement return (3-day, vs SPY) of the latest 8-K 2.02 within 100 days",
      col("ear_last"), source=_lit("PEAD-02", "Brandt, Kishore, Santa-Clara & Venkatachalam 2008"),
      caveat=_EARN_CAVEAT, literature_reported="Quantpedia #0080: 18.36% / 16.12% vol OOS")
    E("ear_drift_large", "earnings_event", "earnings-announcement drift, large+mega",
      col("ear_last"), "large", caveat=_EARN_CAVEAT)
    E("ear_fresh", "earnings_event", "earnings-announcement return, only prints <= 35 days old",
      gated(col("ear_last"), "days_since_earn", hi=35), caveat=_EARN_CAVEAT,
      economic_reason="the drift is strongest in the first weeks after the print")
    E("ear_flow", "earnings_event", "rank-avg: announcement return, net raises (revisions confirm the print)",
      combo(("ear_last", 1), ("net_raises", 1)), caveat=_EARN_CAVEAT + "; " + _FLOW_CAVEAT)
    E("ear_mom", "earnings_event", "rank-avg: announcement return, 12-1 momentum",
      combo(("ear_last", 1), (MOM, 1)), source=_lit("PEAD-03", "Chan, Jegadeesh & Lakonishok 1996"),
      caveat=_EARN_CAVEAT)
    E("eap_mom", "earnings_event",
      "12-1 momentum among names EXPECTED to report in the holding month (embrace the print)",
      gated(col(MOM), "earn_next", lo=1), source=_lit("CAT-04", "Frazzini & Lamont 2007; Barber et al. 2013"),
      caveat=_EARN_CAVEAT, economic_reason="the earnings-announcement premium: attention buying at the print")
    E("eap_avoid_mom", "earnings_event",
      "12-1 momentum among names NOT expected to report in the holding month (avoid the print)",
      gated(col(MOM), "earn_next", hi=0), caveat=_EARN_CAVEAT,
      economic_reason="the falsifier of eap_mom: momentum without event risk")
    E("eap_lowvol", "earnings_event", "lowest 63d vol among names expected to report in the month",
      gated(col("vol_63", -1), "earn_next", lo=1), caveat=_EARN_CAVEAT)
    E("eap_raises", "earnings_event", "net raises among names expected to report in the month",
      gated(col("net_raises"), "earn_next", lo=1), caveat=_EARN_CAVEAT + "; " + _FLOW_CAVEAT)
    E("runup_exit_before", "earnings_event",
      "hold the month BEFORE an expected print, exit before it (rank: last surprise + raises)",
      gated(combo(("ear_last", 1), ("net_raises", 1)), "earn_following", lo=1),
      source="ours (review idea C at monthly resolution: the held month is the pre-print run-up)",
      caveat=_EARN_CAVEAT, economic_reason=(
          "collect the pre-announcement run-up without holding the binary print itself"))
    E("runup_exit_before_large", "earnings_event", "pre-print run-up, exit before, large+mega",
      gated(combo(("ear_last", 1), ("net_raises", 1)), "earn_following", lo=1), "large",
      caveat=_EARN_CAVEAT)
    # ---------------------------------------------------------- other 8-K events
    E("material_agreements", "filing_event", "8-K item 1.01 (material agreements) over 90 days",
      col("n101_90"), source=_lit("CAT-01", "8-K event literature"), caveat=_8K_CAVEAT,
      economic_reason="contracts, partnerships and supply deals are demand news the tape under-reads")
    E("agreements_mom", "filing_event", "rank-avg: material agreements, 12-1 momentum",
      combo(("n101_90", 1), (MOM, 1)), caveat=_8K_CAVEAT)
    E("mom_no_exec_change", "filing_event",
      "12-1 momentum among names with NO 8-K 5.02 (officer departure/appointment) in 180 days",
      gated(col(MOM), "n502_180", hi=0), caveat=_8K_CAVEAT,
      economic_reason="an executive change resets the story; momentum without one is cleaner")
    E("regfd_attention", "filing_event", "8-K item 7.01 (Reg FD: presentations, guidance) over 90 days",
      col("n701_90"), caveat=_8K_CAVEAT,
      economic_reason="firms that court investors attract the attention that moves prices")
    E("filing_intensity", "filing_event", "count of 8-K filings over 90 days (information flow)",
      col("n8k_90"), caveat=_8K_CAVEAT)
    E("distress_free_reversal", "filing_event",
      "1-month losers among names with NO distress 8-K (1.03/2.04/3.01/4.02) in 365 days",
      gated(col("mom_21", -1), "distress_365", hi=0), caveat=_8K_CAVEAT,
      economic_reason="buy the overreaction, but not the names falling for a filed reason")
    # ------------------------------------------------------------ short interest
    HTW = "Hong, Li, Ni, Scheinkman & Yan 2015 (days to cover)"
    E("low_days_to_cover", "short_interest", "lowest short interest / daily share volume",
      col("dtc", -1), source=_lit("RET-07", "Asquith, Pathak & Ritter 2005, JFE; " + HTW),
      caveat=_SI_CAVEAT, literature_reported="Quantpedia long-only 26.80% OOS (claim)")
    E("low_days_to_cover_large", "short_interest", "lowest days-to-cover, large+mega",
      col("dtc", -1), "large", caveat=_SI_CAVEAT)
    E("short_covering", "short_interest", "largest 3-month DECLINE in short interest",
      col("si_chg_3m", -1), caveat=_SI_CAVEAT,
      economic_reason="informed shorts leaving is the removal of a negative view")
    E("low_dtc_mom", "short_interest", "rank-avg: low days-to-cover, 12-1 momentum",
      combo(("dtc", -1), (MOM, 1)), caveat=_SI_CAVEAT)
    E("short_squeeze", "short_interest", "rank-avg: HIGH days-to-cover, last month's winners",
      combo(("dtc", 1), ("mom_21", 1)), caveat=_SI_CAVEAT,
      economic_reason="crowded shorts in a rising name are forced buyers (reflexive, attention layer)")
    E("low_dtc_gp", "short_interest", "rank-avg: low days-to-cover, gross profitability",
      combo(("dtc", -1), ("gp_at", 1)), caveat=_SI_CAVEAT + "; " + _FUND_CAVEAT)
    E("covering_flow", "short_interest", "rank-avg: short covering, analyst net raises",
      combo(("si_chg_3m", -1), ("net_raises", 1)), caveat=_SI_CAVEAT + "; " + _FLOW_CAVEAT)
    # ------------------------------------------------------ fundamental inflection
    E("revenue_acceleration", "fund_inflection", "revenue growth minus revenue growth a year earlier",
      col("rev_accel"), caveat=_FUND_CAVEAT)
    E("rev_accel_margin", "fund_inflection", "rank-avg: revenue acceleration, gross-margin change",
      combo(("rev_accel", 1), ("gm_chg", 1)), source="ours (brief: rev acceleration x margin)",
      caveat=_FUND_CAVEAT)
    E("op_margin_expansion", "fund_inflection", "year-over-year operating-margin change",
      col("om_chg"), caveat=_FUND_CAVEAT)
    E("roa_improvement", "fund_inflection", "year-over-year change in net income / assets",
      col("roa_chg"), source="literature:Piotroski 2000 (F-score delta-ROA leg)", caveat=_FUND_CAVEAT)
    E("profit_turn", "fund_inflection", "ROA change among firms whose net income just turned positive",
      gated(col("roa_chg"), "ni_turn", lo=1), caveat=_FUND_CAVEAT,
      economic_reason="the first profitable year re-rates the holder base (loss-makers are screened out)")
    E("rev_accel_large", "fund_inflection", "revenue acceleration, large+mega",
      col("rev_accel"), "large", caveat=_FUND_CAVEAT)
    E("rev_accel_mom", "fund_inflection", "rank-avg: revenue acceleration, 12-1 momentum",
      combo(("rev_accel", 1), (MOM, 1)), caveat=_FUND_CAVEAT)
    E("deleveraging", "fund_inflection", "largest year-over-year fall in debt / assets",
      col("debt_at_chg", -1), caveat=_FUND_CAVEAT)
    # ------------------------------------------------ sector-relative (long-only neutral)
    for rid, base, cav in (
            ("mom_12_1_secrel", col(MOM), ""),
            ("net_raises_secrel", col("net_raises"), _FLOW_CAVEAT),
            ("gp_at_secrel", col("gp_at"), _FUND_CAVEAT),
            ("lowvol_252_secrel", col("vol_252", -1), ""),
            ("quality_composite_secrel",
             combo(("gp_at", 1), ("ope_be", 1), ("debt_at", -1), ("vol_252", -1)), _FUND_CAVEAT),
            ("mom_flow_secrel", combo((MOM, 1), ("net_raises", 1)), _FLOW_CAVEAT),
            ("frog_secrel", combo((MOM, 1), ("info_discreteness", -1)), ""),
            ("hi52_secrel", col("px_vs_52w_high"), "")):
        E(rid, "sector_relative", f"{rid[:-7]} ranked WITHIN its GICS sector",
          sector_rel(base), caveat="; ".join(x for x in (_SECTOR_CAVEAT, cav) if x))
    E("industry_mom", "sector_relative", "the sector's mean 12-1 momentum (buy names in the best sectors)",
      col("sector_mom"), source=_lit("MOM-06", "Moskowitz & Grinblatt 1999, JF"),
      caveat=_SECTOR_CAVEAT, economic_reason="industry news diffuses slowly across its members")
    E("mom_in_top_sectors", "sector_relative", "12-1 momentum among names in the top-30% sectors",
      within_top(col(MOM), "sector_mom", 0.3), caveat=_SECTOR_CAVEAT)
    # ------------------------------------------ regime-gated versions of the top 10
    # The ten are the 2026-09-26 02:00 board's DSR top-10 -- chosen on a FULL-
    # sample diagnostic, so they are a finding to test, never a prior (the
    # 2026-09-22 lesson). Named so the selection is visible.
    for rid, base, uni, h, cav in (
            ("mom_12_1", col(MOM), "all", 1, ""),
            ("mom_12_1_q", col(MOM), "all", 3, ""),
            ("mom_no_downgrades", gated(col(MOM), "net_raises", lo=0.0), "all", 1, _FLOW_CAVEAT),
            ("net_raises", col("net_raises"), "all", 1, _FLOW_CAVEAT),
            ("big_dv", col("dollar_vol_log"), "all", 1, ""),
            ("mom_12_1_small", col(MOM), "small", 1, ""),
            ("mom_flow", combo((MOM, 1), ("net_raises", 1)), "all", 1, _FLOW_CAVEAT),
            ("trend_quality", combo(("px_vs_ma200", 1), ("gp_at", 1), ("debt_at", -1)), "all", 1,
             _FUND_CAVEAT),
            ("frog_in_pan", combo((MOM, 1), ("info_discreteness", -1)), "all", 1, ""),
            ("inflection_flow", combo(("inflection", 1), ("net_raises", 1)), "all", 1, _BOTH)):
        E(f"{rid}_trend", "regime_gated", f"{rid}, in cash when SPY is below its 200-day mean",
          base, uni, hold_months=h, regime_gate="mkt_trend_up",
          source=_lit("MOM-07", "Moskowitz, Ooi & Pedersen 2012 as a single-name overlay"),
          caveat="; ".join(x for x in (_REGIME_NOTE, cav) if x))
    # ------------------------------------------------- weighting (construction)
    for rid, base, w, cav in (
            ("mom_12_1_ivw", col(MOM), "inv_vol", ""),
            ("gp_at_ivw", col("gp_at"), "inv_vol", _FUND_CAVEAT),
            ("net_raises_ivw", col("net_raises"), "inv_vol", _FLOW_CAVEAT),
            ("quality_composite_ivw",
             combo(("gp_at", 1), ("ope_be", 1), ("debt_at", -1), ("vol_252", -1)), "inv_vol", _FUND_CAVEAT),
            ("mom_flow_ivw", combo((MOM, 1), ("net_raises", 1)), "inv_vol", _FLOW_CAVEAT),
            ("mom_12_1_liqw", col(MOM), "inv_amihud", "")):
        E(rid, "weighted", f"{rid.rsplit('_', 1)[0]}, weights {w} (not equal)", base,
          weight_rule=w, caveat=cav,
          source=(_lit("SIZ-04", "practitioner liquidity-weighted momentum") if w == "inv_amihud"
                  else "ours (risk-parity construction)"))
    # --------------------------------- liquidity-band versions of the top families
    for rid, fam, base, uni, cav in (
            ("net_raises_small", "revision_flow", col("net_raises"), "small", _FLOW_CAVEAT),
            ("net_raises_large", "revision_flow", col("net_raises"), "large", _FLOW_CAVEAT),
            ("mom_no_downgrades_large", "revision_flow", gated(col(MOM), "net_raises", lo=0.0),
             "large", _FLOW_CAVEAT),
            ("mom_no_downgrades_small", "revision_flow", gated(col(MOM), "net_raises", lo=0.0),
             "small", _FLOW_CAVEAT),
            ("frog_small", "combination", combo((MOM, 1), ("info_discreteness", -1)), "small", ""),
            ("trend_quality_large", "combination",
             combo(("px_vs_ma200", 1), ("gp_at", 1), ("debt_at", -1)), "large", _FUND_CAVEAT),
            ("inflection_flow_large", "combination", combo(("inflection", 1), ("net_raises", 1)),
             "large", _BOTH),
            ("mom_flow_small", "combination", combo((MOM, 1), ("net_raises", 1)), "small", _FLOW_CAVEAT),
            ("gp_at_small", "quality", col("gp_at"), "small", _FUND_CAVEAT)):
        E(rid, fam, f"{rid.rsplit('_', 1)[0]} restricted to the {uni} band", base, uni, caveat=cav,
          economic_reason=("the same mechanism where frictions differ: small names carry the "
                           "under-reaction AND the toll; large names carry neither as much"))
    # ------------------------------------------------ overnight / intraday
    E("overnight_mom", "overnight", "12-month sum of overnight (close-to-open) log returns",
      col("ovn_252"), source="literature:Lou, Polk & Skouras 2019, JFE (A Tug of War)")
    E("gap_reversal", "overnight", "1-month losers among names whose moves were gap-driven",
      within_top(col("mom_21", -1), "gap_share_21", 0.3), source=_lit("REV-03", "Lou, Polk & Skouras 2019"))
    # ------------------------------------ rank-average combos chosen by FAMILY DIVERSITY
    # Chosen so that every leg comes from a different data source (price, SEC
    # facts, sell side, Form 4, 8-K, short interest) -- NOT by dev return.
    for rid, legs, cav in (
            ("div_mom_insider_flow", ((MOM, 1), ("ins_buyers_90", 1), ("net_raises", 1)),
             _INS_CAVEAT + "; " + _FLOW_CAVEAT),
            ("div_quality_lowvol_insider", (("gp_at", 1), ("vol_252", -1), ("ins_buyers_90", 1)),
             _FUND_CAVEAT + "; " + _INS_CAVEAT),
            ("div_mom_shorts_quality", ((MOM, 1), ("dtc", -1), ("gp_at", 1)),
             _SI_CAVEAT + "; " + _FUND_CAVEAT),
            ("div_lead_earn_mom", (("lead_raises_90", 1), ("ear_last", 1), (MOM, 1)),
             _FLOW_CAVEAT + "; " + _EARN_CAVEAT),
            ("div_agree_quality_lowvol", (("target_cv_180", -1), ("gp_at", 1), ("vol_252", -1)),
             _FLOW_CAVEAT + "; " + _FUND_CAVEAT),
            ("div_flow_covering_hi52", (("net_raises", 1), ("si_chg_3m", -1), ("px_vs_52w_high", 1)),
             _FLOW_CAVEAT + "; " + _SI_CAVEAT),
            ("div_accel_flow_mom", (("rev_accel", 1), ("net_raises", 1), (MOM, 1)), _BOTH),
            ("div_insider_earn_shorts", (("ins_buyers_90", 1), ("ear_last", 1), ("dtc", -1)),
             _INS_CAVEAT + "; " + _EARN_CAVEAT + "; " + _SI_CAVEAT),
            ("div_skill_mom_quality", (("skill_net_raises_90", 1), (MOM, 1), ("gp_at", 1)), _BOTH),
            ("div_insider_reversal", (("ins_opp_buyers_180", 1), ("mom_21", -1)), _INS_CAVEAT),
            ("div_six_sources", ((MOM, 1), ("gp_at", 1), ("net_raises", 1), ("ins_buyers_90", 1),
                                 ("dtc", -1), ("ear_last", 1)),
             "; ".join((_FUND_CAVEAT, _FLOW_CAVEAT, _INS_CAVEAT, _SI_CAVEAT, _EARN_CAVEAT)))):
        E(rid, "diversified_combo", "rank-avg: " + ", ".join(
            f"{'low ' if s < 0 else ''}{n}" for n, s in legs), combo(*legs), caveat=cav)


def _expansion_note(add) -> None:
    """Merged from `docs/research_notes/2026-09-26/research_library_expansion_and_lean.md`.

    Only the note's rows whose mechanism is not already registered; every other
    row of the note is in `NOTE_BACKLOG` with the reason it was not.
    """
    S = Strategy
    P = REGISTERED_2026_09_26_PM
    MOM = "mom_252_21"
    NOTE = "docs/research_notes/2026-09-26/research_library_expansion_and_lean.md"
    _VOLREG = ("regime: SPY 21-session realised vol vs the terciles of its OWN history up to "
               "the date (expanding, PIT) -- a VIX proxy; no VIX series is on the panel; "
               "off-regime months are CASH earning 0")

    def E(*a, **kw):
        kw.setdefault("first_registered_utc", P)
        add(S(*a, **kw))

    E("mom_in_raised", "flow_momentum", "12-1 momentum among the top third by net raises (revisions as a FILTER)",
      within_top(col(MOM), "net_raises", 1 / 3), source=f"ours ({NOTE} INT-01)", caveat=_FLOW_CAVEAT,
      economic_reason="revisions remove the momentum names the sell side does not believe in")
    E("inflection_mid_plus", "inflection", "inflection restricted to mid+ names (is INFL secretly SIZ?)",
      gated(gated(col("inflection"), "rev_gr", lo=0.0), "gm_chg", lo=0.0), "mid_plus",
      source=f"ours ({NOTE} INT-02)", caveat=_FUND_CAVEAT)
    E("mom_with_insider_buying", "insider",
      "12-1 momentum only among names with an opportunistic insider buy in 180 days",
      gated(col(MOM), "ins_opp_buyers_180", lo=1), source=f"ours ({NOTE} INT-03)", caveat=_INS_CAVEAT,
      economic_reason="insider buying selects WHICH momentum names are informed")
    E("mom_in_high_margin", "combination", "12-1 momentum among the top third by gross margin",
      within_top(col(MOM), "gross_margin", 1 / 3), source=f"ours ({NOTE} INT-05)", caveat=_FUND_CAVEAT,
      economic_reason="profitable momentum survives; unprofitable momentum is the crash leg (Novy-Marx)")
    E("mom_in_calm", "momentum", "12-1 momentum among the calmer half by 21-session vol",
      within_top(col(MOM), "vol_21", 0.5, sign=-1), source=f"ours ({NOTE} INT-06)",
      economic_reason="momentum crashes live in high-volatility names; the calm half keeps the drift")
    E("mom_12_1_bear", "regime_gated", "12-1 momentum ONLY when SPY is below its 200-day mean (control)",
      col(MOM), regime_gate="mkt_trend_down", source=f"ours ({NOTE} REG-02)", caveat=_REGIME_NOTE,
      economic_reason="the control for mom_12_1_trend: Daniel-Moskowitz predict momentum dies here")
    E("quality_in_stress", "regime_gated", "gross profitability, only in high-volatility months",
      col("gp_at"), regime_gate="mkt_stress", source=f"ours ({NOTE} REG-03)",
      caveat=_VOLREG + "; " + _FUND_CAVEAT, economic_reason="flight to quality pays in stress")
    E("lowvol_in_stress", "regime_gated", "lowest 21-session vol, only in high-volatility months",
      col("vol_21", -1), regime_gate="mkt_stress", source=f"ours ({NOTE} REG-04)", caveat=_VOLREG)
    E("insider_in_calm", "regime_gated", "opportunistic insider buyers, only in calm months",
      col("ins_opp_buyers_180"), regime_gate="mkt_calm", source=f"ours ({NOTE} REG-06)",
      caveat=_VOLREG + "; " + _INS_CAVEAT)
    E("reversal_in_stress", "regime_gated", "last week's losers, only in high-volatility months",
      col("rev_5", -1), regime_gate="mkt_stress", source=f"ours ({NOTE} REG-07)", caveat=_VOLREG,
      economic_reason="liquidity provision is paid most after panic selling, when the mechanism is live")
    E("mom_in_calm_markets", "regime_gated", "12-1 momentum, only in calm months",
      col(MOM), regime_gate="mkt_calm", source=f"ours ({NOTE} REG-08)", caveat=_VOLREG)
    E("small_not_illiquid_trend", "regime_gated", "lowest dollar volume within mid band, SPY above 200d",
      col("dollar_vol_log", -1), "mid", regime_gate="mkt_trend_up", source=f"ours ({NOTE} REG-09)",
      caveat=_REGIME_NOTE)
    E("insider_secrel", "sector_relative", "opportunistic insider buyers ranked WITHIN sector",
      sector_rel(col("ins_opp_buyers_180")), source=f"ours ({NOTE} SECN-05)",
      caveat=_SECTOR_CAVEAT + "; " + _INS_CAVEAT)
    E("mom_resid_to_sector", "sector_relative", "12-1 momentum minus its sector's mean 12-1 momentum",
      col("mom_minus_sector"), source=f"ours ({NOTE} SECI-01)", caveat=_SECTOR_CAVEAT)
    E("mom_in_laggard_sectors", "sector_relative",
      "12-1 momentum among names in the bottom third of sectors by LAST MONTH's return",
      within_top(col(MOM), "sector_ret_21", 1 / 3, sign=-1), source=f"ours ({NOTE} SECI-04)",
      caveat=_SECTOR_CAVEAT, economic_reason="sector-level reversal feeding a stock-level continuation pick")
    E("raise_price_gap", "lead_chase", "rank-avg: net raises, LOW 1-month return (analysts moved, price has not)",
      combo(("net_raises", 1), ("mom_21", -1)), source=f"ours ({NOTE} LEAD-03)", caveat=_FLOW_CAVEAT)
    E("cluster_unconfirmed", "lead_chase", "firms acting, among the bottom third by 1-month return",
      within_top(col("n_firms"), "mom_21", 1 / 3, sign=-1), source=f"ours ({NOTE} LEAD-06)",
      caveat=_FLOW_CAVEAT)
    E("insider_before_print", "earnings_event", "insider buyers among names expected to report in the month",
      gated(col("ins_buyers_90"), "earn_next", lo=1), source=f"ours ({NOTE} CATR-06 / EARN-03)",
      caveat=_INS_CAVEAT + "; " + _EARN_CAVEAT,
      economic_reason="insiders pre-positioning ahead of a known event")
    E("inflection_fresh", "earnings_event", "inflection, only where the last print is <= 35 days old",
      gated(col("inflection"), "days_since_earn", hi=35), source=f"ours ({NOTE} EARN-04)",
      caveat=_FUND_CAVEAT + "; " + _EARN_CAVEAT)
    E("insider_unconfirmed", "insider", "insider buyers among names with NO net analyst raise yet",
      gated(col("ins_buyers_90"), "net_raises", hi=0.0), source=f"ours ({NOTE} SEQ-02)",
      caveat=_INS_CAVEAT + "; " + _FLOW_CAVEAT,
      economic_reason="insiders know first; the analysts have not caught up")
    E("insider_then_raise", "insider", "insider buyers among names with a net raise in the last 30 days",
      gated(col("ins_buyers_90"), "net_raises_30", lo=1), source=f"ours ({NOTE} SEQ-01)",
      caveat=_INS_CAVEAT + "; " + _FLOW_CAVEAT)
    E("mom_ex_lottery", "low_risk", "12-1 momentum excluding the top-20% MAX (lottery) names",
      within_top(col(MOM), "max_ret_21", 0.8, sign=-1), source=f"ours ({NOTE} LOT-02)")
    E("skilled_first_movers", "analyst_skill", "first-mover raises by historically skilled firms",
      col("skill_first_mover_90"), source=f"ours ({NOTE} MISC-07)", caveat=_FLOW_CAVEAT)
    E("pricing_power_unwatched", "fund_inflection",
      "rank-avg: margin change, revenue acceleration, LOW dollar volume",
      combo(("gm_chg", 1), ("rev_accel", 1), ("dollar_vol_log", -1)), source=f"ours ({NOTE} MISC-11)",
      caveat=_FUND_CAVEAT, economic_reason="pricing power showing up in a name nobody is watching yet")
    E("margin_turn", "fund_inflection", "gross-margin change, only where it just turned positive",
      gated(col("gm_chg"), "gm_turn", lo=1), source=f"ours ({NOTE} MISC-12)", caveat=_FUND_CAVEAT)
    E("revenue_turn", "fund_inflection", "revenue growth, only where it just turned positive",
      gated(col("rev_gr"), "rev_turn", lo=1), source=f"ours ({NOTE} MISC-13)", caveat=_FUND_CAVEAT)


#: Rows of the chunk-D research note that were NOT registered, with the reason.
NOTE_BACKLOG: dict = {
    "INT-04": "covered by raises_in_losers (same interaction, 63d instead of 21d window = a threshold)",
    "INT-07": "FORWARD: target snapshots start 2026-09-24 (the historical CV is low_dispersion_mom)",
    "INT-08": "covered by mom_no_insider_selling", "LEAD-01": "covered by raises_in_losers",
    "LEAD-02": "covered by chase_raises / flow_in_winners", "LEAD-04": "covered by first_mover_raises",
    "LEAD-05": "daily rebalance; the engine is monthly",
    "REG-01": "covered by mom_12_1_trend", "REG-05": "covered by net_raises_trend",
    "REG-10": "a regime ROUTER: deferred until independent selectors exist (CLAUDE.md bottleneck)",
    "SECN-01": "covered by mom_12_1_secrel", "SECN-02": "covered by gp_at_secrel",
    "SECN-03": "covered by net_raises_secrel", "SECN-04": "covered by lowvol_252_secrel",
    "SECN-06": "needs a sector-level rolling 52-week high",
    "SECN-07": "one-per-sector construction is not in the engine",
    "SECN-08": "sector-cap construction is not in the engine", "SECI-02": "covered by mom_in_top_sectors",
    "SECI-03": "one-per-sector construction", "SECI-05": "covered by net_raises_secrel",
    "SECI-06": "sector-cap construction",
    "CATR-01": "daily entry/exit; the monthly analogue is runup_exit_before",
    "CATR-02": "no buyback calendar (check buyback_insider_divergence_v0 first)",
    "CATR-03": "daily exit-before-print; the monthly analogue is runup_exit_before",
    "CATR-04": "an exit overlay needs a daily engine", "CATR-05": "covered by eap_raises",
    "CATR-07": "covered by eap_avoid_mom (monthly)", "CATR-08": "no multi-type catalyst history",
    "EARN-01": "covered by eap_avoid_mom", "EARN-02": "covered by eap_raises",
    "EARN-05": "FORWARD (snapshots)", "EARN-06": "an earnings-week exclusion needs a daily engine",
    "DISP-01": "FORWARD", "DISP-02": "FORWARD", "DISP-03": "FORWARD (target LEVEL is CLOSED, AREV-08)",
    "DISP-04": "FORWARD; the historical CV twin is low_dispersion_mom", "DISP-05": "FORWARD",
    "DISP-06": "FORWARD",
    "SEQ-03": "covered by mom_no_insider_selling", "SEQ-04": "no 13F join on the panel",
    "SEQ-05": "congress: check TRIAL-CONGRESS-IC first; not joined", "SEQ-06": "no 13F join",
    "FOMO-01": "daily hold", "FOMO-02": "daily hold", "FOMO-03": "daily hold",
    "FOMO-04": "left to strategy_library_ext (fomo_reversal)", "FOMO-05": "daily hold + catalyst",
    "FOMO-06": "a within-decile split is a threshold of mom_12_1",
    "FOMO-07": "left to strategy_library_ext",
    "LOT-01": "covered by low_max", "LOT-03": "daily hold", "LOT-04": "daily attention surge",
    "LOT-05": "exclusion screen; covered by mom_ex_lottery",
    "LOT-06": "three stacked conditions (DSR bait)",
    "MISC-01": "13F join exists: strategy_library_ext.inst_breadth_up (corrected 2026-09-26)", "MISC-02": "congress: TRIAL-CONGRESS-IC first",
    "MISC-03": "news corpus ~20 months, not panel-wide", "MISC-04": "FORWARD (thesis cards)",
    "MISC-05": "news corpus + catalyst join", "MISC-06": "covered by skill_raises",
    "MISC-08": "built: strategy_library_ext.cascade_entry_timing (falsifier fired 2026-09-26)", "MISC-09": "no guidance events",
    "MISC-10": "FORWARD (thesis cards)", "MISC-14": "LOW-confidence proxy; not registered",
}


RULES: list = _rules()


def rules(include_controls: bool = True) -> list:
    return [r for r in RULES if include_controls or not r.control]


def rule_by_id(rule_id: str) -> Strategy:
    for r in RULES:
        if r.id == rule_id:
            return r
    raise KeyError(rule_id)


def library_fingerprint(rs: list | None = None) -> str:
    """One hash over every rule's fingerprint: what a checkpoint resumes against."""
    body = [r.fingerprint() for r in (rs if rs is not None else RULES)]
    return _hashlib.sha256("|".join(body).encode()).hexdigest()[:16]


#: Catalogue rows that do NOT become rules, each with the input it lacks. A
#: catalogue row in neither `RULES` nor here would be a row silently dropped.
NOT_REACHABLE: dict = {
    "MOM-10": "beta-neutral L/S needs a short leg; the library is long-only",
    "REV-01": "daily rebalance; the library rebalances monthly",
    "REV-05": "short leg",
    "VAL-01": ("bars are split- AND dividend-adjusted (NVDA closes at 12.68 in 2020-08) "
               "while SEC `shares` is as-filed, so close x shares mis-scales market cap "
               "by every FUTURE split -- look-ahead toward future winners. Refused until "
               "a split-factor table exists"),
    "VAL-02": "same market-cap defect as VAL-01",
    "VAL-03": "same defect, and no EV/EBIT facts",
    "VAL-04": "composite of VAL-01..03", "VAL-05": "needs VAL-01",
    "VAL-06": "tiny-cap net-net universe is not on the panel",
    "INV-02": "net issuance from as-filed shares is split-contaminated (VAL-01)",
    "QUAL-03": "no operating-cash-flow fact, so no accruals",
    "QUAL-06": "duplicate of INFL-01 (`inflection`)",
    "INFL-03": "duplicate of QUAL-02 (`margin_expansion`)",
    "AREV-05": "proprietary analyst-accuracy weights",
    "AREV-08": "target LEVEL is CLOSED/PERVERSE (revision_flow docstring); the change is AREV-03",
    "PEAD-01": "no consensus estimate at announcement (SUE needs it; PEAD-02 uses the price reaction)",
    "PEAD-04": "needs PEAD-01's stale SUE", "PEAD-05": "no buyback calendar",
    "PEAD-06": "no guidance events",
    "INS-06": "market timing",
    "CAT-02": "no PDUFA history (the catalyst YAML is Q4-2026 forward only)",
    "CAT-03": "no index-change calendar",
    "CAT-05": "FORWARD ONLY: thesis cards exist from 2026-09-25",
    "CAT-06": "FORWARD ONLY: investigator p has no history",
    "SEAS-01": "calendar overlay, not k-selection", "SEAS-02": "calendar overlay",
    "SEAS-03": "calendar overlay", "SEAS-04": "calendar overlay",
    "SEAS-05": "calendar overlay", "SEAS-06": "calendar overlay",
    "SEAS-07": "calendar overlay",
    "ATT-01": "FORWARD ONLY", "ATT-02": "FORWARD ONLY", "ATT-03": "FORWARD ONLY",
    "ATT-04": "FORWARD ONLY",
    "COMB-01": "needs VAL-04", "COMB-03": "needs VAL-04",
    "COMB-04": "duplicate of AREV-06 (`mom_flow`)",
    "COMB-07": "meta-router deferred: a router comes after independent selectors exist",
    "RET-02": "duplicate of REV-02 (`rev_5d`)", "RET-04": "duplicate of MOM-04 (`hi52`)",
    "RET-05": "needs VAL", "RET-06": "ETF allocation, not stock selection",
    "RET-08": "duplicate of MOM-04 (`hi52`)",
    "RET-09": "options", "RET-10": "reachable via strategy_library_ext.inst_breadth_up (13F breadth, rdate+45d; corrected 2026-09-26)", "RET-11": "pair construction",
    "RET-12": "market timing", "RET-13": "market timing",
    "RET-14": "market timing (10 observations)",
}

#: Catalogue rows that were NOT reachable on the 02:00 board and ARE now
#: (2026-09-26 PM), with the input that made them so. The re-check the brief
#: asked for, in one place (17 of the 67 rows the 02:00 board could not reach).
BECAME_REACHABLE_2026_09_26_PM: dict = {
    "MOM-06": "Compustat GICS sector (static map) -> `industry_mom`",
    "MOM-07": "SPY vs its 200d mean as a single-name OVERLAY -> the `*_trend` regime-gated rows",
    "REV-03": "open/close bars -> `gap_share_21` -> `gap_reversal`",
    "SIZ-04": "the engine's `inv_amihud` weight rule -> `mom_12_1_liqw`",
    "AREV-10": "the revision parquet's `firm` + `current_target` -> cross-firm target CV",
    "PEAD-02": "EDGAR 8-K item 2.02 dates -> the 3-day announcement return `ear_last`",
    "PEAD-03": "`ear_mom` (announcement return x momentum)",
    "INS-01": "sec_insider `insider_opportunistic_buy` (CMP classification) -> `insider_opportunistic`",
    "INS-02": "as a long-only EXCLUSION -> `mom_no_insider_selling`",
    "INS-03": "sec_insider distinct buyers -> `insider_buyers`, `insider_cluster_value`",
    "INS-04": "`insider_cluster_small`", "INS-05": "`insider_flow`",
    "CAT-01": "EDGAR 8-K item codes -> `material_agreements`",
    "CAT-04": "8-K 2.02 -> expected next print -> `eap_mom` / `eap_avoid_mom`",
    "COMB-05": "`insider_opp_mom`", "COMB-08": "`inflection_insider`",
    "RET-07": "Compustat sec_shortint -> `low_days_to_cover`",
}


# ── the engine ───────────────────────────────────────────────────────────────

def selection_scores(panel, strategy: Strategy):
    """Scores masked to the strategy's universe; NaN = not selectable."""
    s = strategy.signal(panel)
    if not isinstance(s, _pd.Series):
        s = _pd.Series(s, index=panel.index)
    s = s.astype(float)
    mask = UNIVERSES[strategy.universe_rule](panel).fillna(False).astype(bool)
    return s.where(mask & _np.isfinite(s))


def _band_rt(costs: dict, v: float) -> float:
    if v is None or not _np.isfinite(v):
        return costs["small"]
    if v >= 1e9:
        return costs["mega"]
    if v >= 1e8:
        return costs["large"]
    if v >= 2e7:
        return costs["mid"]
    return costs["small"]


def _tiebreak(panel):
    """A deterministic per-(date, symbol) hash: ties in the score are broken at
    random rather than alphabetically (a count feature with many equal values
    would otherwise buy the start of the alphabet). The factory stores it once
    as the `tiebreak` column; small test panels compute it here."""
    if "tiebreak" in panel.columns:
        return panel["tiebreak"].to_numpy(dtype=float)
    key = panel["symbol"].astype(str) + "|" + panel["date"].astype(str) + "|tb"
    h = _pd.util.hash_pandas_object(key, index=False).to_numpy(dtype="uint64")
    return (h % 1_000_003).astype(float)


def _weights(strategy: Strategy, panel, top) -> "_np.ndarray":
    """Target weights for the selected rows `top` (sum 1)."""
    n = len(top)
    if strategy.weight_rule == "equal" or n == 0:
        return _np.full(n, 1.0 / max(n, 1))
    if strategy.weight_rule == "inv_vol":
        x = panel["vol_63"].to_numpy(dtype=float)[top] if "vol_63" in panel.columns else _np.full(n, _np.nan)
        inv = 1.0 / _np.where(_np.isfinite(x) & (x > 0), x, _np.nan)
    else:                                   # inv_amihud: more weight on the liquid names
        x = panel["amihud"].to_numpy(dtype=float)[top] if "amihud" in panel.columns else _np.full(n, _np.nan)
        inv = 1.0 / _np.where(_np.isfinite(x), _np.expm1(_np.clip(x, 1e-6, 50)), _np.nan)
    fill = _np.nanmedian(inv) if _np.isfinite(inv).any() else 1.0
    inv = _np.where(_np.isfinite(inv), inv, fill)
    return inv / inv.sum()


def run_strategy(panel, strategy: Strategy, *, k: int | None = None,
                 scores=None, holdings: list | None = None):
    """Monthly NAV of the rule's equal-weight top-k book, net of band costs.

    `panel` contract: one row per (date, symbol) at each rebalance date, with
    `eligible`, `median_dollar_vol`, `fwd_ret` (entry at the session after
    `date` to entry at the session after the NEXT date, delisting fill already
    applied; NaN on the last, still-open period) and every column the rule
    reads. A held name with no row later (it stopped trading and its fill was
    taken) earns 0, i.e. the weight sits in cash until the next rebalance.

    Cost: each name bought pays half its band round trip on the weight bought,
    each name sold half on the weight sold. Drift between rebalances is not
    traded and not charged -- said here rather than discovered later.

    A `regime_gate` column <= 0 on a date sends the whole book to cash (sold,
    and charged) for that period; cash earns 0. `holdings`, when a list, gets
    one {date, symbols, weights} per rebalance -- the replication file's input.
    """
    k = int(k or strategy.k)
    check_costs(strategy.cost_scale, strategy.zero_cost_diagnostic)
    costs = _band_costs()
    scale = float(strategy.cost_scale)
    sc = scores if scores is not None else selection_scores(panel, strategy)
    dates = _np.sort(panel["date"].unique())
    di = _np.searchsorted(dates, panel["date"].to_numpy())
    order = _np.argsort(di, kind="stable")
    bounds = _np.searchsorted(di[order], _np.arange(len(dates) + 1))
    fwd = panel["fwd_ret"].to_numpy(dtype=float)
    mdv = panel["median_dollar_vol"].to_numpy(dtype=float)
    sym = panel["symbol"].to_numpy()
    scv = sc.to_numpy(dtype=float)
    dl = (panel["delisted_in_period"].to_numpy(dtype=bool)
          if "delisted_in_period" in panel.columns else None)
    tb = _tiebreak(panel)
    gate = None
    if strategy.regime_gate:
        _need(panel, (strategy.regime_gate,))
        gate = panel[strategy.regime_gate].to_numpy(dtype=float)

    rows = []
    held: dict = {}
    held_rt: dict = {}
    start = None
    rmonths = set(strategy.rebalance_months or ())
    for j, d in enumerate(dates):
        idx = order[bounds[j]:bounds[j + 1]]
        if not len(idx) or not _np.isfinite(fwd[idx]).any():
            continue                               # the still-open period
        cand = idx[_np.isfinite(scv[idx])]
        risk_off = False
        if gate is not None:
            gv = gate[idx]
            gv = gv[_np.isfinite(gv)]
            risk_off = bool(len(gv) and gv[0] <= 0)
        rebalance = False
        on_cal = (_pd.Timestamp(d).month in rmonths) if rmonths else None
        if start is None:
            if len(cand) < k or on_cal is False:
                continue
            start, rebalance = j, True
        elif (on_cal if rmonths else (j - start) % strategy.hold_months == 0) and len(cand) >= k:
            rebalance = True
        elif gate is not None and ((risk_off and held) or (not risk_off and not held
                                                             and len(cand) >= k)):
            rebalance = True                       # the gate flipped between rebalances
        cost = turnover = 0.0
        if rebalance:
            if risk_off:
                top = cand[:0]
            else:
                top = cand[_np.lexsort((tb[cand], -scv[cand]))[:k]]
            wts = _weights(strategy, panel, top)
            new = {sym[t]: float(w_) for t, w_ in zip(top, wts)}
            new_rt = {sym[t]: _band_rt(costs, mdv[t]) for t in top}
            if holdings is not None:
                holdings.append({"date": str(_pd.Timestamp(d).date()),
                                 "symbols": [str(sym[t]) for t in top],
                                 "weights": [round(float(w_), 8) for w_ in wts],
                                 "risk_off": risk_off})
            for s_, w in new.items():
                dw = w - held.get(s_, 0.0)
                if dw > 0:
                    cost += dw * new_rt[s_] / 2.0
                    turnover += dw
            for s_, w in held.items():
                dw = w - new.get(s_, 0.0)
                if dw > 0:
                    cost += dw * held_rt.get(s_, costs["small"]) / 2.0
            held, held_rt = new, new_rt
        cost = cost * scale / 1e4
        pos = {sym[t]: t for t in idx}
        gross, n_dead = 0.0, 0
        for s_, w_ in held.items():
            t = pos.get(s_)
            r = fwd[t] if t is not None else _np.nan
            gross += w_ * (float(r) if _np.isfinite(r) else 0.0)
            if dl is not None and t is not None and dl[t]:
                n_dead += 1
        rows.append({"date": _pd.Timestamp(d), "gross": gross, "cost": cost,
                     "net": gross - cost, "turnover": turnover,
                     "n_held": len(held), "n_delisted": n_dead,
                     "rebalanced": rebalance})
    return _pd.DataFrame(rows, columns=["date", "gross", "cost", "net", "turnover",
                                        "n_held", "n_delisted", "rebalanced"])


def latest_selection(panel, strategy: Strategy, *, k: int | None = None) -> list:
    """Today's top-k (the last date on the panel): what a forward book holds."""
    k = int(k or strategy.k)
    last = panel["date"].max()
    sc = selection_scores(panel, strategy)
    day = sc[(panel["date"] == last).to_numpy()].dropna()
    if len(day) < k:
        raise RuleInputMissing(
            f"{strategy.id}: only {len(day)} selectable names on {last}, need {k}")
    top = day.sort_values(ascending=False, kind="mergesort").head(k)
    syms = panel.loc[top.index, "symbol"]
    mdv = panel.loc[top.index, "median_dollar_vol"]
    return [{"symbol": str(s), "score": float(v), "median_dollar_vol": float(m)}
            for s, v, m in zip(syms, top.values, mdv.values)]


# ── the honest read, printed BEFORE any ranking ──────────────────────────────

def _cagr(r) -> float | None:
    r = _np.asarray(r, dtype=float)
    r = r[_np.isfinite(r)]
    if len(r) == 0:
        return None
    tw = float(_np.prod(1.0 + r))
    if tw <= 0:
        return -1.0
    return tw ** (12.0 / len(r)) - 1.0


def _max_dd(r) -> float | None:
    r = _np.asarray(r, dtype=float)
    r = r[_np.isfinite(r)]
    if len(r) == 0:
        return None
    nav = _np.cumprod(1.0 + r)
    peak = _np.maximum.accumulate(_np.concatenate([[1.0], nav]))[1:]
    return float((nav / peak - 1.0).min())


def _naive(ts) -> "_pd.Timestamp":
    t = _pd.Timestamp(ts)
    return t.tz_convert(None) if t.tzinfo is not None else t


def entry_dates(index) -> "_pd.DatetimeIndex":
    """The entry session of each monthly period (the business day after the
    decision date). The split is applied on THIS, so a December decision whose
    return is earned in January belongs to January's window."""
    return _pd.DatetimeIndex(index) + _pd.offsets.BDay(1)


def split_windows(index) -> dict:
    """Boolean masks over monthly periods: dev / sealed / recent. Constants only."""
    ent = entry_dates(index)
    sealed = _np.asarray(ent >= _pd.Timestamp(SEALED_START))
    dev = _np.asarray(ent <= _pd.Timestamp(DEV_END) + _pd.Timedelta(days=1)) & ~sealed
    recent = _np.zeros(len(ent), dtype=bool)
    if len(ent):
        recent[-min(RECENT_PERIODS, len(ent)):] = True
    return {"dev": dev, "sealed": sealed, "recent": recent}


def _window_stats(net, spy, active) -> dict:
    n = int(len(net))
    if n == 0:
        return {"n_months": 0, "cagr": None, "spy_cagr": None, "vs_spy": None,
                "cum": None, "spy_cum": None, "max_dd": None}
    c, sc = _cagr(net), _cagr(spy.dropna())
    return {"n_months": n, "cagr": c, "spy_cagr": sc,
            "vs_spy": (c - sc) if (c is not None and sc is not None) else None,
            "cum": float(_np.prod(1.0 + net) - 1.0),
            "spy_cum": float(_np.prod(1.0 + spy.dropna()) - 1.0) if spy.notna().any() else None,
            "max_dd": _max_dd(net),
            "active_returns": [float(x) for x in active.dropna().values]}


def evaluate(monthly, spy, *, hold_months: int = 1,
             registered_utc: str = REGISTERED_2026_09_26,
             since: str = "2020-01-01") -> dict:
    """Every number the leaderboard may show about one (rule, k) cell.

    `monthly`: `run_strategy`'s frame. `spy`: the market's return over the SAME
    periods, indexed by the same dates (built from `learner.benchmark`).
    By year first, then leave-one-year-out, the t on horizon-wide blocks,
    Sharpe with its block count, and the since-2020 line -- labelled HINDSIGHT
    for every month before `registered_utc`, with the quotable remainder apart.
    """
    if monthly is None or len(monthly) == 0:
        return {"status": "REFUSED", "why": "no month had k selectable names"}
    m = monthly.set_index("date").sort_index()
    sp = spy.reindex(m.index).astype(float)
    act = m["net"] - sp
    out: dict = {"status": "OK", "n_months": int(len(m)),
                 "span": [str(m.index.min().date()), str(m.index.max().date())],
                 "n_months_without_spy": int(sp.isna().sum())}

    by_year = {}
    for y, g in m.groupby(m.index.year):
        s = sp.reindex(g.index)
        net_y = float(_np.prod(1.0 + g["net"]) - 1.0)
        spy_y = float(_np.prod(1.0 + s.dropna()) - 1.0) if s.notna().any() else None
        by_year[str(y)] = {"net": net_y, "spy": spy_y,
                           "excess": (net_y - spy_y) if spy_y is not None else None,
                           "n_months": int(len(g))}
    out["by_year"] = by_year
    out["by_year_signs"] = "".join(
        "+" if (v["excess"] or 0) > 0 else "-" for v in by_year.values())
    yrs = [str(y) for y in range(2020, 2026)]
    out["positive_excess_years_2020_2025"] = int(sum(
        1 for y in yrs if (by_year.get(y) or {}).get("excess") is not None
        and by_year[y]["excess"] > 0))

    years = m.index.year
    loo = {}
    for y in sorted(set(years)):
        a_ = act[years != y].dropna()
        if len(a_) > 1:
            loo[str(y)] = float(a_.mean())
    out["leave_one_year_out_mean_active"] = loo
    out["loo_worst_mean_active"] = min(loo.values()) if loo else None
    out["loo_worst_dropped_year"] = min(loo, key=loo.get) if loo else None

    a = act.dropna()
    out["active_returns"] = [float(x) for x in a.values]
    out["mean_net_monthly"] = float(m["net"].mean())
    out["mean_active_monthly"] = float(a.mean()) if len(a) else None
    sd = float(m["net"].std(ddof=1)) if len(m) > 1 else float("nan")
    out["sharpe_annual"] = (float(m["net"].mean() / sd * _math.sqrt(12))
                            if _np.isfinite(sd) and sd > 0 else None)
    asd = float(a.std(ddof=1)) if len(a) > 1 else float("nan")
    out["active_sharpe_monthly"] = (float(a.mean() / asd)
                                    if _np.isfinite(asd) and asd > 0 else None)
    out["information_ratio_annual"] = (out["active_sharpe_monthly"] * _math.sqrt(12)
                                       if out["active_sharpe_monthly"] is not None else None)
    out["n_date_blocks"] = int(len(a))
    rb = m[m["rebalanced"].astype(bool)]
    out["mean_turnover_per_rebalance"] = float(rb["turnover"].mean()) if len(rb) else None
    out["mean_cost_bps_per_month"] = float(m["cost"].mean() * 1e4)
    out["n_delisting_fills"] = int(m["n_delisted"].sum())

    # WHICH PART OF THE SAMPLE (CLAUDE.md protocol 11): the first real run had
    # the best 5 of 115 months carrying 44-54% of 12-1 momentum's log return.
    lr = _np.log1p(m["net"].to_numpy(dtype=float))
    tot = float(lr.sum())
    best = _np.sort(lr)[::-1][:5]
    out["top5_months_share_of_log_return"] = float(best.sum() / tot) if tot > 0 else None
    rest = _np.sort(lr)[:-5] if len(lr) > 5 else _np.array([])
    out["cagr_without_best_5_months"] = (float(_np.exp(rest.sum() * 12.0 / len(rest)) - 1.0)
                                         if len(rest) else None)
    sp_full = sp.dropna()
    out["spy_cagr_same_window"] = _cagr(sp_full)

    h = max(1, int(hold_months))
    blk = _np.arange(len(a)) // h
    bret = ((1.0 + a).groupby(blk).prod() - 1.0) if len(a) else a
    out["hold_months"] = h
    out["n_blocks_horizon"] = int(len(bret))
    bs = float(bret.std(ddof=1)) if len(bret) > 2 else 0.0
    out["t_active_horizon_blocks"] = (float(bret.mean() / (bs / _math.sqrt(len(bret))))
                                      if bs > 0 else None)
    out["clears_hlz_t3"] = bool(out["t_active_horizon_blocks"] is not None
                                and out["t_active_horizon_blocks"] >= HLZ_T_BAR)

    reg = _naive(registered_utc)
    s20 = m[m.index >= _pd.Timestamp(since)]
    sp20 = sp.reindex(s20.index).dropna()
    out["hindsight_since_2020"] = {
        "label": (f"HINDSIGHT BACKTEST: the rule was registered "
                  f"{str(registered_utc)[:10]}, after every month here"),
        "n_months": int(len(s20)),
        "cum_net": float(_np.prod(1.0 + s20["net"]) - 1.0) if len(s20) else None,
        "cum_spy": float(_np.prod(1.0 + sp20) - 1.0) if len(sp20) else None,
        "cagr_net": _cagr(s20["net"]),
        "cagr_spy": _cagr(sp20),
        "max_dd_net": _max_dd(s20["net"]),
        "max_dd_spy": _max_dd(sp20),
    }
    # THE SEALED SPLIT (constants DEV_END / SEALED_START / RECENT_PERIODS).
    wins = split_windows(m.index)
    for name in ("dev", "sealed", "recent"):
        mk = wins[name]
        st = _window_stats(m["net"][mk], sp[mk], act[mk])
        out[f"{name}_window"] = {k_: v for k_, v in st.items() if k_ != "active_returns"}
        if name == "sealed":
            out["sealed_active_returns"] = st.get("active_returns", [])
        if st["n_months"]:
            ent = entry_dates(m.index[mk])
            out[f"{name}_window"]["span_entry"] = [str(ent.min().date()), str(ent.max().date())]
    out["dev_cagr"] = out["dev_window"]["cagr"]
    out["dev_spy_cagr"] = out["dev_window"]["spy_cagr"]
    out["dev_vs_spy"] = out["dev_window"]["vs_spy"]
    out["sealed_cagr"] = out["sealed_window"]["cagr"]
    out["sealed_spy_cagr"] = out["sealed_window"]["spy_cagr"]
    out["sealed_vs_spy"] = out["sealed_window"]["vs_spy"]
    out["n_sealed_months"] = out["sealed_window"]["n_months"]
    out["recent_126_return"] = out["recent_window"]["cum"]
    out["recent_126_spy"] = out["recent_window"]["spy_cum"]
    out["recent_126_vs_spy"] = ((out["recent_126_return"] - out["recent_126_spy"])
                                if out["recent_126_spy"] is not None
                                and out["recent_126_return"] is not None else None)
    nm = max(1, len(m))
    out["turnover_annual"] = float(m["turnover"].sum() / nm * 12.0)
    out["cost_bps_paid"] = float(m["cost"].sum() / nm * 12.0 * 1e4)
    out["cost_bps_paid_total"] = float(m["cost"].sum() * 1e4)
    out["max_dd"] = _max_dd(m["net"])

    q = m[m.index >= reg]
    out["quotable_since_registration"] = (
        {"status": "NONE_YET",
         "why": f"registered {str(registered_utc)[:10]}; no completed month since"}
        if len(q) == 0 else
        {"status": "OK", "n_months": int(len(q)),
         "cum_net": float(_np.prod(1.0 + q["net"]) - 1.0),
         "cum_spy": float(_np.prod(1.0 + sp.reindex(q.index).dropna()) - 1.0)})
    return out


def deflate(cells: list, *, n_trials: int | None = None,
            effective_trials: int | None = None) -> None:
    """Attach the deflated Sharpe to every cell IN PLACE, at the count looked at.

    `cells`: dicts carrying `active_returns` (monthly net - SPY, calendar-time
    and non-overlapping). `n_trials` defaults to the number of cells.

    TWO NULLS, AND WHY THE PRIMARY IS THE ANALYTIC ONE (2026-09-26, measured).
    The first night used the dispersion of Sharpe ACROSS THE CELLS as the null
    sd. On this library that sd is inflated by rules that are genuinely,
    structurally negative (vol compression at t -4.6, skew at t -3.9): true
    effect heterogeneity, not selection noise. It put the noise bar at 0.57
    monthly (~2.0 annualised IR), every DSR rounded to 0.000, and a ranking
    over ties is a ranking by name. So:

    * `dsr` (primary, ranks the board): analytic null, V[SR] = 1/(T-1), at
      `n_trials` -- the arithmetic in the research note.
    * `dsr_null_from_library`: the cross-cell dispersion, printed beside it.
    * `dsr_effective`: analytic null at `effective_trials` (the families).
    * `dsr_z`: the z inside the DSR, so ties below display precision still
      order by evidence rather than by id.
    """
    from learner.inference import deflated_sharpe
    live = [c for c in cells if len(c.get("active_returns") or []) >= 8]
    n = int(n_trials or len(live))
    srs = []
    for c in live:
        a = _np.asarray(c["active_returns"], dtype=float)
        a = a[_np.isfinite(a)]
        if len(a) > 1 and a.std(ddof=1) > 0:
            srs.append(float(a.mean() / a.std(ddof=1)))
    for c in cells:
        a = c.get("active_returns") or []
        d = deflated_sharpe(a, n_trials=n)
        c["dsr"] = d.get("dsr")
        c["dsr_z"] = d.get("z")
        c["dsr_sr0_monthly"] = d.get("sharpe_benchmark_sr0")
        c["dsr_verdict"] = d.get("verdict")
        c["dsr_n_trials"] = n
        c["dsr_null_basis"] = "analytic 1/sqrt(T-1)"
        dl = deflated_sharpe(a, n_trials=n, null_sharpes=srs)
        c["dsr_null_from_library"] = dl.get("dsr")
        c["dsr_sr0_monthly_library"] = dl.get("sharpe_benchmark_sr0")
        if effective_trials:
            d2 = deflated_sharpe(a, n_trials=int(effective_trials))
            c["dsr_effective"] = d2.get("dsr")
            c["dsr_effective_n_trials"] = int(effective_trials)
        sa = c.get("sealed_active_returns") or []
        if len(sa) >= 8:
            ds = deflated_sharpe(sa, n_trials=n)
            c["sealed_dsr"] = ds.get("dsr")
            c["sealed_dsr_z"] = ds.get("z")
            c["sealed_sr0_monthly"] = ds.get("sharpe_benchmark_sr0")
        else:
            c["sealed_dsr"] = c["sealed_dsr_z"] = c["sealed_sr0_monthly"] = None


def adoption_status(*, forward_sessions: int, forward_vs_spy: float | None,
                    forward_vs_random: float | None, positive_years: int,
                    min_sessions: int = 63, min_positive_years: int = 4) -> str:
    """The adopt/reject rule, DECLARED in the spec and not tuned later.

    ADOPTED (to EXPLOIT candidacy): >= 63 forward sessions, beats SPY AND its
    random twin net, and >= 4 of 6 backtest years (2020-2025) positive.
    REJECTED: >= 63 sessions and trails BOTH. Otherwise RUNNING.
    """
    if (forward_sessions < min_sessions or forward_vs_spy is None
            or forward_vs_random is None):
        return "RUNNING"
    if forward_vs_spy > 0 and forward_vs_random > 0 and positive_years >= min_positive_years:
        return "ADOPTED"
    if forward_vs_spy < 0 and forward_vs_random < 0:
        return "REJECTED"
    return "RUNNING"


#: Rules that exist ONLY FORWARD on this panel: their inputs have no history
#: here, so they carry the replay's number (CITED, never ours) and get a
#: forward book regardless of the DSR table. Both were named by the 2026-09-26
#: audit (`docs/research_notes/2026-09-26/audit_forecasts_and_learning_since_august.md`)
#: as green in replay and never run forward; freezing them closes that finding.
FORWARD_ONLY: list = [
    {"id": "forecast_dispersion_v1", "family": "analyst_disagreement", "k": 20,
     "description": ("lowest analyst target dispersion, (target_high - target_low) / "
                     "price, from the latest target snapshot per ticker"),
     "source": "literature:AREV-10 Diether, Malloy & Scherbina 2002, JF; replay forecast_dispersion_v1",
     "replay_reported": ("replay forecast_dispersion_v1: +1.02%/month, t 5.65 over 419 month "
                         "blocks, positive in all four eras (CRSP/IBES replay, NOT this panel). "
                         "target_snapshots history on this panel starts 2026-09-24, so there is "
                         "no backtest here; the forward book starts now"),
     "green_replay_never_forward": True,
     "first_registered_utc": REGISTERED_2026_09_26},
    {"id": "book_f_seasonality_11_20_v0", "family": "seasonality", "k": 30,
     "description": ("Book F: same-calendar-month return at year lags 11-20, top tercile "
                     "(the frozen F_seasonality_<month>.json export, top 30)"),
     "source": "literature:SEAS-08 Heston & Sadka 2008; TRIAL-DRAFT-F (UNSIGNED)",
     "replay_reported": ("B_books_efg_replay run01 at the $10M floor: +0.43%/month excess "
                         "net vs its twin, NW t 3.12 over 419 blocks (CRSP replay). The 11-20y "
                         "lags need bars from 2006; this panel starts 2016, so no backtest here"),
     "green_replay_never_forward": True,
     "first_registered_utc": REGISTERED_2026_09_26},
]


# ── rules contributed by a sibling module (chunk C features) ─────────────────
#
# `strategy_library_ext.EXTRA_STRATEGIES` is owned by another builder. It is
# imported when it exists, every entry goes through `register` (so a threshold
# variant of a rule already here is refused and NAMED, not silently dropped),
# and the registered ones are ordinary rules: in `RULES`, in the factory, in
# the DSR cell count. An `attach(panel, W)` function there, if present, is
# what puts its columns on the panel; without it those rules are REFUSED by
# name for the missing column, which is the honest outcome.
EXTRA_REFUSED: dict = {}
EXTRA_SOURCE: str = "absent"


def _load_extra() -> None:
    global EXTRA_SOURCE
    import importlib
    import importlib.util
    if importlib.util.find_spec("backend.services.strategy_library_ext") is None:
        EXTRA_SOURCE = "absent (backend/services/strategy_library_ext.py does not exist)"
        return
    try:
        _ext = importlib.import_module("backend.services.strategy_library_ext")
    except Exception as e:                        # noqa: BLE001 -- printed on every board
        EXTRA_SOURCE = f"IMPORT FAILED: {type(e).__name__}: {e}"
        return
    items = list(getattr(_ext, "EXTRA_STRATEGIES", []) or [])
    EXTRA_SOURCE = f"backend.services.strategy_library_ext ({len(items)} entries)"
    fields = set(Strategy.__dataclass_fields__)
    ctl = [r for r in RULES if r.control]
    for r in ctl:
        RULES.remove(r)
    for it in items:
        rid = getattr(it, "id", None) or (it.get("id") if isinstance(it, dict) else None)
        try:
            s = it if isinstance(it, Strategy) else Strategy(
                **{k_: v for k_, v in dict(it).items() if k_ in fields})
            register(RULES, s)
        except Exception as e:                     # noqa: BLE001 -- named, never silent
            EXTRA_REFUSED[str(rid)] = f"{type(e).__name__}: {e}"
    RULES.extend(ctl)                            # controls stay last


_load_extra()
