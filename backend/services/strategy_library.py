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
# Priority follows the cost-survivability evidence rather than the headline
# returns: Novy-Marx & Velikov found that low-turnover anomalies are the ones
# that survive trading costs, and that high-turnover ones are much harder to
# monetize. So size/value/profitability rank above anything that trades weekly,
# regardless of gross Sharpe.
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
                      "This is a SIZING rule rather than a selection rule, "
                      "which is the layer §59 says our slice can actually "
                      "resolve — its effect on risk is measurable in ~4 years "
                      "where a return effect would need ~95"),
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
            note=(f"equal-weighted decile spread on the CRSP panel; "
                  f"break-even {r.get('breakeven_bps')}bp/crossing; "
                  f"detectable net = {r.get('detectable')}"))
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
