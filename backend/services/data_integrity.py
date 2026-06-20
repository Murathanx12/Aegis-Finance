"""
Aegis Finance — Data Integrity Gate
====================================

The honest gate between *falsification-grade* and *sizing-grade* backtests.

WHY THIS EXISTS
---------------
Moving from sector-ETF allocation toward single-stock selection, a backtest is
only as honest as its data. Free price/fundamental feeds (yfinance) have two
defects that manufacture fake alpha:

  1. **Survivorship bias** — they carry only names that still trade today. Every
     stock that went to zero (Lehman, Enron, WaMu, …) is silently absent, so any
     backtest over "the universe" is implicitly a backtest over *the winners*.
  2. **Restated (non-point-in-time) fundamentals** — they serve *today's*
     restated financials, not what was knowable on the trade date. A model that
     "sees" a restatement before it happened is reading the future.

Both inflate measured returns. So we classify every data source:

  - **DIRECTIONAL** — may be used to *kill* a candidate (falsification). Its
    single-stock numbers are directionally informative but NEVER position-sizing
    grade. yfinance is directional.
  - **SIZING** — delisted-inclusive prices AND point-in-time fundamentals. Only
    a SIZING source may produce numbers a real position size can rest on.

A backtest that wants to claim sizing-grade calls `require_sizing_grade(source)`
and `assert_survivorship_safe(survivorship_probe(...))`; either fails LOUD on a
directional source. Directional backtests run freely but stamp their results
`grade=directional` so nothing is mistaken for sizing-grade later.

UPGRADE PATH
------------
The recommended sizing-grade source is **Sharadar SEP/SF1 (via Nasdaq Data
Link)** — delisted-inclusive + as-reported PIT, ~$ low-hundreds/yr. It is already
registered below as SIZING; wiring its fetch adapter + key flips every
single-stock backtest to sizing-grade with no other change. See
docs/DATA_INTEGRITY.md for the adapter contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Callable, Iterable, Optional

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd


class DataGrade(str, Enum):
    """Falsification-grade vs sizing-grade. A backtest inherits its weakest source."""

    DIRECTIONAL = "directional"  # may KILL a candidate; never size a position
    SIZING = "sizing"            # delisted-inclusive + PIT → position-sizing grade


class DataIntegrityError(RuntimeError):
    """Raised when work claims a data grade its source cannot support. Fails loud."""


@dataclass(frozen=True)
class SourceGuarantees:
    """What a data source actually guarantees. Conservative by construction:
    sizing-grade requires BOTH delisted-inclusive prices AND PIT fundamentals."""

    name: str
    survivorship_free: bool
    point_in_time_fundamentals: bool
    notes: str = ""

    @property
    def grade(self) -> DataGrade:
        if self.survivorship_free and self.point_in_time_fundamentals:
            return DataGrade.SIZING
        return DataGrade.DIRECTIONAL


# Registry of source guarantees. A source is DIRECTIONAL unless PROVEN otherwise.
SOURCE_GUARANTEES: dict[str, SourceGuarantees] = {
    "yfinance": SourceGuarantees(
        "yfinance", survivorship_free=False, point_in_time_fundamentals=False,
        notes="No delisted tickers; serves restated fundamentals. Directional only.",
    ),
    "fmp": SourceGuarantees(
        "fmp", survivorship_free=False, point_in_time_fundamentals=False,
        notes="Some delisted coverage; free tier not PIT-clean. Directional.",
    ),
    "alpha_vantage": SourceGuarantees(
        "alpha_vantage", survivorship_free=False, point_in_time_fundamentals=False,
    ),
    "polygon": SourceGuarantees(
        "polygon", survivorship_free=False, point_in_time_fundamentals=False,
        notes="Delisted prices on paid tiers; fundamentals not PIT. Directional.",
    ),
    "finnhub": SourceGuarantees(
        "finnhub", survivorship_free=False, point_in_time_fundamentals=False,
    ),
    # ── Paid clean source — drop-in once the Sharadar/Nasdaq Data Link adapter
    #    + key are wired. SEP (delisted-inclusive prices) + SF1 (as-reported PIT).
    "sharadar": SourceGuarantees(
        "sharadar", survivorship_free=True, point_in_time_fundamentals=True,
        notes="Sharadar SEP/SF1 via Nasdaq Data Link: delisted-inclusive + as-reported PIT.",
    ),
}

# The source the replay/backtest layer uses today.
DEFAULT_PRICE_SOURCE = "yfinance"


def get_guarantees(source: str) -> SourceGuarantees:
    """Guarantees for a source. Unknown sources are assumed DIRECTIONAL (worst case)."""
    g = SOURCE_GUARANTEES.get(source.lower())
    if g is None:
        return SourceGuarantees(
            source, survivorship_free=False, point_in_time_fundamentals=False,
            notes="Unknown source — assumed directional.",
        )
    return g


def data_grade(source: str) -> DataGrade:
    return get_guarantees(source).grade


def is_sizing_grade(source: str) -> bool:
    return data_grade(source) is DataGrade.SIZING


def require_sizing_grade(source: str, context: str = "") -> None:
    """Gate for any backtest claiming sizing-grade results. Fails LOUD on a
    directional source — so a single-stock number can never silently pass as
    position-sizing grade."""
    if not is_sizing_grade(source):
        g = get_guarantees(source)
        where = f" for {context}" if context else ""
        raise DataIntegrityError(
            f"Data source '{source}' is {g.grade.value}-grade, not sizing-grade{where}: "
            f"survivorship_free={g.survivorship_free}, "
            f"point_in_time_fundamentals={g.point_in_time_fundamentals}. "
            f"Single-stock results on this source are DIRECTIONAL ONLY (falsification), "
            f"never position-sizing grade. Wire a sizing-grade source (e.g. Sharadar) first."
        )


# ── Empirical survivorship probe ─────────────────────────────────────────────

# US names that DELISTED (bankruptcy / fire-sale). A survivorship-free source
# must still return pre-delisting price history for these; yfinance returns
# little or nothing → the bias is made visible rather than assumed.
KNOWN_DELISTED: dict[str, str] = {
    "LEH": "Lehman Brothers — bankrupt Sep 2008",
    "WAMUQ": "Washington Mutual — bankrupt Sep 2008",
    "ENRNQ": "Enron — bankrupt Dec 2001",
    "BSC": "Bear Stearns — JPMorgan fire-sale Mar 2008",
    "GGP": "General Growth Properties — bankrupt Apr 2009",
}


@dataclass
class SurvivorshipReport:
    source: str
    grade: DataGrade
    n_probed: int
    n_returned: int           # delisted names that returned usable history
    missing: list = field(default_factory=list)  # names the source could not serve
    survivorship_biased: bool = False


def survivorship_probe(
    fetch_history: Callable[[str], "Optional[pd.Series]"],
    source: str = DEFAULT_PRICE_SOURCE,
    tickers: Optional[Iterable[str]] = None,
    min_points: int = 60,
) -> SurvivorshipReport:
    """Empirically test whether `source` can serve delisted-ticker history.

    `fetch_history(ticker)` returns a price series (or None/empty). Network lives
    in the injected fetch_fn, so this is unit-testable offline. ANY delisted name
    the source cannot serve marks it survivorship-biased.
    """
    names = list(tickers) if tickers is not None else list(KNOWN_DELISTED)
    missing: list = []
    returned = 0
    for t in names:
        try:
            s = fetch_history(t)
        except Exception:
            s = None
        if s is not None and len(s) >= min_points:
            returned += 1
        else:
            missing.append(t)
    return SurvivorshipReport(
        source=source,
        grade=data_grade(source),
        n_probed=len(names),
        n_returned=returned,
        missing=missing,
        survivorship_biased=returned < len(names),
    )


def assert_survivorship_safe(report: SurvivorshipReport) -> None:
    """Fail LOUD when a source REGISTERED sizing-grade is empirically biased —
    catches a registry lie or a broken feed before it taints a sizing backtest.

    A DIRECTIONAL source being biased is expected and consistent (no raise); the
    protection is that such a source can never reach sizing-grade in the first
    place (see `require_sizing_grade`)."""
    if report.survivorship_biased and report.grade is DataGrade.SIZING:
        raise DataIntegrityError(
            f"Source '{report.source}' is registered sizing-grade but FAILED the "
            f"survivorship probe: {report.n_returned}/{report.n_probed} delisted names "
            f"returned history; missing={report.missing}. Fix the feed or the registry."
        )
