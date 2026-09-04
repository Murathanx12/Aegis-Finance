"""learner/benchmark.py -- THE ONE RULER.

WHY THIS FILE EXISTS
====================
On 2026-09-04 the program discovered that its most-quoted public number --
"+740% market, +250.9% strategy" -- was measured with two broken instruments at
once. `backend/services/backtest.py:95` downloaded **`^GSPC`**, the S&P 500
PRICE index, which pays no dividends and is therefore not a return anybody can
earn; and the 2026-03-30 code compounded **66 overlapping 3-month forward
windows as if they were sequential**, which multiplies the log return by ~3.12.
The overlap bug was fixed on 2026-04-15 (`726c7bf`); `BACKTEST_RESULTS.md` was
never regenerated, and nine documents copied the void figure.

The dividend-inclusive value-weighted market over the same window is **+96.7%**
(re-derived twice: `+96.67%` from the pinned Fama-French daily file). The
headline was ~7.6x too large. Nobody was lying; two defensible-looking choices
compounded, and there was no single place where "the market" was defined, so
there was nothing to test.

THIS MODULE IS THAT SINGLE PLACE. Every receipt writer imports it. Every
receipt that carries a `market` field carries this module's STAMP beside it,
and `backend/tests/test_benchmark_canonical.py` fails the suite if a receipt
written on or after 2026-09-04 has a `market` without a valid stamp.

THE SIX BENCHMARKS, AND WHY EACH ONE EXISTS
===========================================
A benchmark is not a decoration; it is the answer to *"better than what?"*
(the standing rule, [[feedback-ask-better-than-what]]). Six are canonical
because six different questions get asked:

- `vw_market_tr_pinned`   -- the CRSP value-weighted market TOTAL return from
  the hash-gated pinned Fama-French daily vintage. **The default history
  ruler.** Offline, reproducible, dividend-inclusive.
- `cash_rf_pinned`        -- the risk-free leg from the same file. The floor: a
  strategy that cannot beat T-bills has no claim at all.
- `spy_tr_yf_adjclose`    -- SPY adjusted close from yfinance. The *live*
  ruler, because the fleet's paper books are compared against what a person
  could actually have bought this morning. Requires network; REFUSES offline
  rather than silently substituting the pinned market.
- `qqq_tr_yf_adjclose`    -- same, for the tech-tilted comparison Murat asks
  for when a book is concentrated in semis.
- `ew_crsp_common_main` / `vw_crsp_common_main` -- equal- and value-weighted
  total return of *the panel's own admissible universe*. This is the honest
  comparator for a stock-selection claim: it holds the same names with no
  selection, so beating it is skill and not membership.
- `beta_matched`          -- beta x market + (1 - beta) x rf. A 1.48x-beta book
  that "beat the market" by 27%/yr may have earned exactly the equity premium
  its leverage bought (the toxic-short receipt did precisely this).
- `matched`               -- a strategy-specific control the caller constructs
  and must describe. Not a loophole: the construction string is hashed into the
  stamp, so a matched benchmark is auditable even though it is bespoke.

TWO RULES THAT ARE ENFORCED, NOT ADVISED
========================================
1. **A benchmark REFUSES rather than substitutes.** `spy_total_return()` with
   no network does not quietly hand back the pinned VW market; it raises
   `BenchmarkUnavailable` naming the missing input. A guard that cannot get its
   input must say which input, or it becomes a gate that cannot go green.
2. **Compounding is non-overlapping by construction.** `compound()` refuses a
   series whose index it was told is overlapping. If you have h-month forward
   windows sampled monthly, you must either sample every h-th window
   (`non_overlapping`) or use calendar-time cohorts -- never `.prod()` over all
   of them. That single line of arithmetic is what produced +740%.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
=========================================
It does not choose a benchmark for you. `resolve()` dispatches on an explicit
id because the choice of comparator is a research decision that belongs in the
receipt, visible, next to the number it flatters or destroys.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Iterable, Optional

import numpy as np
import pandas as pd

# --------------------------------------------------------------- constants

#: Bumped when the stamp schema changes in a way old stamps cannot satisfy.
BENCHMARK_SCHEMA: int = 1

#: The module path a stamp must name. A receipt whose stamp names something
#: else was written by a parallel implementation and is not canonical.
CANONICAL_MODULE: str = "learner.benchmark"

#: Key under which a receipt carries its stamp.
STAMP_KEY: str = "market_benchmark"

#: Receipts written on or after this date must carry a valid stamp beside any
#: `market`-like field. Earlier receipts are grandfathered: they are void or
#: superseded, not retro-fixable, and rewriting a sealed receipt is tampering.
STAMP_REQUIRED_FROM: date = date(2026, 9, 4)

#: Field names that unambiguously mean "this receipt quotes a market return".
#: Kept explicit for readability; the regex below is what actually catches the
#: long tail (`excess_vw`, `adaptive12m_..._mktpark_25bps`, `paired_t_vs_market`).
MARKET_FIELDS: tuple[str, ...] = (
    "market", "market_return", "market_total_return", "cagr_market",
    "terminal_wealth_market", "terminal_wealth_market_same_months",
    "buy_and_hold_market", "market_excess_vs", "spy", "spy_return",
    "benchmark", "primary_benchmark", "vw_market", "ew_market_cagr",
)

#: The receipt corpus carries 191 distinct market-ish key names, so an allowlist
#: cannot work. The gate is INTENTIONALLY BROAD -- a false positive costs one
#: annotation line, a false negative re-opens the hole the gate exists to close.
_MARKET_KEY_RE = __import__("re").compile(
    r"(?:^|_|\b|/|\|)(?:mkt|market|spy|qqq|bench(?:mark)?)"
    r"|excess(?:_vw|_ew|_cagr|_panel|_vs|_hac|_1m|_3m|_6m|_12m|_pp)?"
    r"|beating_(?:market|benchmark|top\d*)|mktpark"
    # `buy_hold_total_return` was MISSED by the first version of this regex and
    # slipped a receipt past the gate on 2026-09-04, minutes after the gate was
    # written. A benchmark leg does not have to contain the word "market".
    r"|buy_hold|buy_and_hold|active_passive|\bpassive\b",
    __import__("re").I)

#: ...minus the names that contain a market word but are NOT a market return:
#: sizes, regimes, row counts, feature lists, prose. Every exclusion is named
#: so a reader can see exactly what the gate chose not to look at.
_MARKET_KEY_EXCLUDE_RE = __import__("re").compile(
    r"market_cap|market_state|market_rows|market_features|market_context"
    r"|market_k_ladder|market_share_of_move|market_equal_weighted$"
    r"|by_market_state|market_states|excess_per_1sd|the_benchmark_is_the_biggest_one"
    r"|benchmark_also_stored|market_component"
    # False friends, each one checked by hand: `screen_BH_FDR` is
    # Benjamini-Hochberg, not buy-and-hold; `beats_v1` and
    # `H2_residual_arm_beats_raw_arm` compare two ARMS to each other, which is
    # an ablation, not a market comparison.
    r"|BH_FDR|beats_|beats_incumbent|beats_random|beats_v\d",
    __import__("re").I)

_PINNED_CSV = Path(__file__).resolve().parent.parent / "backend" / "data" / "ff_daily_pinned.csv.gz"
_PINNED_VINTAGE = _PINNED_CSV.with_name("ff_daily_pinned_VINTAGE.json")

#: Shumway (1997) delisting-return fills, kept here because the benchmark and
#: the panel must agree on how a dead name's last return is counted.
SHUMWAY_FILL: dict[str, float] = {"NYSE_AMEX": -0.30, "NASDAQ": -0.55}


def _endpoint(value: object) -> Optional[str]:
    """Format a series index endpoint for a stamp, whatever its dtype.

    A canonical benchmark is date-indexed, but `matched()` accepts a bespoke
    control the caller may key by month label or period. The stamp records the
    span either way rather than raising -- provenance must survive an index type
    it did not choose.
    """
    if value is None:
        return None
    d = getattr(value, "date", None)
    if callable(d):
        try:
            return str(d())
        except Exception:
            pass
    return str(value)


class BenchmarkUnavailable(RuntimeError):
    """A benchmark could not be built AND WILL NOT BE SUBSTITUTED.

    Carries `missing` so a caller (or a gate) can print which input was absent
    instead of reporting a generic failure. Silence is not evidence.
    """

    def __init__(self, benchmark_id: str, missing: str, detail: str = "") -> None:
        self.benchmark_id = benchmark_id
        self.missing = missing
        msg = f"benchmark {benchmark_id!r} unavailable: missing {missing}"
        if detail:
            msg += f" ({detail})"
        super().__init__(msg)


# ------------------------------------------------------------- the object

@dataclass(frozen=True)
class Benchmark:
    """One comparator: its identity, its return series, and its provenance.

    `returns` are SIMPLE decimal period returns (0.0123 = +1.23%), indexed by
    a `DatetimeIndex`, sorted, with no duplicate dates. `freq` is "D" or "M".
    `overlapping` records whether consecutive rows share calendar time -- the
    flag `compound()` refuses on.
    """

    benchmark_id: str
    returns: pd.Series
    freq: str
    provenance: dict = field(default_factory=dict)
    overlapping: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.returns, pd.Series):
            raise TypeError(f"{self.benchmark_id}: returns must be a Series")
        if self.freq not in ("D", "M"):
            raise ValueError(f"{self.benchmark_id}: freq must be 'D' or 'M'")

    # -- measurement -------------------------------------------------------

    def slice(self, start: Optional[str] = None, end: Optional[str] = None) -> "Benchmark":
        """Restrict to [start, end] inclusive, keeping identity and provenance."""
        r = self.returns
        if start is not None:
            r = r[r.index >= pd.Timestamp(start)]
        if end is not None:
            r = r[r.index <= pd.Timestamp(end)]
        prov = dict(self.provenance)
        prov["sliced_to"] = [
            _endpoint(r.index.min()) if len(r) else None,
            _endpoint(r.index.max()) if len(r) else None,
        ]
        return Benchmark(self.benchmark_id, r, self.freq, prov, self.overlapping)

    def total_return(self) -> float:
        """Buy-and-hold total return over the whole series. Non-overlapping only."""
        return compound(self.returns, overlapping=self.overlapping) - 1.0

    def cagr(self) -> Optional[float]:
        """Annualised geometric return, or None when the span is degenerate."""
        r = self.returns.dropna()
        if len(r) < 2:
            return None
        years = (r.index.max() - r.index.min()).days / 365.25
        if years <= 0:
            return None
        tw = compound(r, overlapping=self.overlapping)
        if tw <= 0:
            return None
        return float(tw ** (1.0 / years) - 1.0)

    def to_monthly(self) -> "Benchmark":
        """Compound daily returns into calendar months. A no-op when already M."""
        if self.freq == "M":
            return self
        m = (1.0 + self.returns.dropna()).groupby(
            pd.Grouper(freq="ME")).prod() - 1.0
        prov = dict(self.provenance)
        prov["resampled"] = "daily -> calendar month (compounded)"
        return Benchmark(self.benchmark_id, m, "M", prov, self.overlapping)

    # -- provenance --------------------------------------------------------

    def stamp(self) -> dict:
        """The block a receipt must carry beside any market number it quotes.

        `provenance_sha256` hashes the identity + provenance so that a receipt
        cannot claim this module's authority while describing a different
        construction. It is the receipt's proof of ruler, not a checksum of the
        data.
        """
        body = {
            "schema": BENCHMARK_SCHEMA,
            "module": CANONICAL_MODULE,
            "benchmark_id": self.benchmark_id,
            "freq": self.freq,
            "overlapping": bool(self.overlapping),
            "provenance": self.provenance,
        }
        blob = json.dumps(body, sort_keys=True, default=str).encode("utf-8")
        body["provenance_sha256"] = hashlib.sha256(blob).hexdigest()
        r = self.returns.dropna()
        body["span"] = [
            _endpoint(r.index.min()) if len(r) else None,
            _endpoint(r.index.max()) if len(r) else None,
        ]
        body["n_periods"] = int(len(r))
        return body


# --------------------------------------------------------- the arithmetic

def compound(returns: Iterable[float], *, overlapping: bool = False) -> float:
    """Product of (1 + r). REFUSES when the caller declares overlap.

    This is the +740% guard. There is no `force` argument on purpose: the fix
    for overlapping windows is `non_overlapping()` or calendar-time cohorts,
    never a flag that lets the wrong arithmetic through with a comment.
    """
    if overlapping:
        raise ValueError(
            "compound() refuses an overlapping series: compounding overlapping "
            "h-period forward windows as if sequential inflates the log return "
            "by ~h (measured: 3.12x on 66 overlapping 3-month windows, which is "
            "how +96.7% was published as +740%). Use non_overlapping(series, h) "
            "or calendar-time cohorts with Newey-West(h-1)."
        )
    s = pd.Series(list(returns), dtype="float64").dropna()
    if s.empty:
        return 1.0
    return float((1.0 + s).prod())


def non_overlapping(returns: pd.Series, horizon_periods: int) -> pd.Series:
    """Every `horizon_periods`-th row, so the windows tile instead of overlap.

    Keeps the FIRST row and steps forward. This throws away (h-1)/h of the
    sample -- that loss is the honest price of independent windows, and it is
    why calendar-time overlapping cohorts with a Newey-West(h-1) correction are
    preferred when the sample is short.
    """
    if horizon_periods < 1:
        raise ValueError("horizon_periods must be >= 1")
    idx = np.arange(0, len(returns), horizon_periods)
    return returns.iloc[idx]


# --------------------------------------------------------- pinned sources

def _load_pinned_ff() -> pd.DataFrame:
    """The hash-gated pinned Fama-French daily vintage, as decimals.

    Reuses `backend.services.factor_model`'s gate so there is ONE hash check in
    the program. A mismatch REFUSES: an attribution built on a tampered pin is
    worse than no attribution.
    """
    try:
        from backend.services import factor_model
    except Exception as e:  # pragma: no cover - import-environment only
        raise BenchmarkUnavailable(
            "vw_market_tr_pinned", "backend.services.factor_model", str(e))
    df, meta = factor_model._load_pinned()
    if df is None:
        raise BenchmarkUnavailable(
            "vw_market_tr_pinned", str(_PINNED_CSV),
            f"pinned vintage status={meta.get('status')}")
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    return out.sort_index()


def _pinned_provenance(extra: Optional[dict] = None) -> dict:
    try:
        meta = json.loads(_PINNED_VINTAGE.read_text(encoding="utf-8"))
    except Exception:
        meta = {}
    prov = {
        "source": "Fama-French daily research factors, PINNED vintage",
        "path": str(_PINNED_CSV.relative_to(_PINNED_CSV.parents[3]))
                if len(_PINNED_CSV.parents) > 3 else str(_PINNED_CSV),
        "vintage_date": meta.get("download_date"),
        "sha256": meta.get("sha256"),
        "dividends_included": True,
        "network": False,
    }
    if extra:
        prov.update(extra)
    return prov


def pinned_market_total_return(start: Optional[str] = None,
                               end: Optional[str] = None) -> Benchmark:
    """CRSP value-weighted market TOTAL return, daily, offline. The default.

    `Mkt-RF + RF` reconstitutes the total return of the value-weighted CRSP
    universe including dividends -- the thing `^GSPC` is not.
    """
    ff = _load_pinned_ff()
    if "Mkt-RF" not in ff.columns or "RF" not in ff.columns:
        raise BenchmarkUnavailable(
            "vw_market_tr_pinned", "Mkt-RF/RF columns",
            f"found {list(ff.columns)}")
    r = (ff["Mkt-RF"] + ff["RF"]).dropna()
    r.name = "vw_market_tr"
    bm = Benchmark("vw_market_tr_pinned", r, "D",
                   _pinned_provenance({"construction": "Mkt-RF + RF"}))
    return bm.slice(start, end)


def cash(start: Optional[str] = None, end: Optional[str] = None) -> Benchmark:
    """The risk-free leg from the same pinned file. The floor, not a rival."""
    ff = _load_pinned_ff()
    if "RF" not in ff.columns:
        raise BenchmarkUnavailable("cash_rf_pinned", "RF column")
    r = ff["RF"].dropna()
    r.name = "rf"
    bm = Benchmark("cash_rf_pinned", r, "D",
                   _pinned_provenance({"construction": "RF (daily T-bill)"}))
    return bm.slice(start, end)


# ----------------------------------------------------------- live sources

def _yf_total_return(ticker: str, benchmark_id: str,
                     start: Optional[str], end: Optional[str]) -> Benchmark:
    """Adjusted-close total return from yfinance. REFUSES offline.

    `auto_adjust=True` gives a dividend- and split-adjusted close, so the
    percentage change IS the total return an investor earned. This is the only
    network path in the module and it never falls back to the pinned market --
    a live comparison that silently became a 1926-anchored academic index is
    the same class of error this module exists to end.
    """
    try:
        import yfinance as yf
    except Exception as e:
        raise BenchmarkUnavailable(benchmark_id, "yfinance", str(e))
    try:
        px = yf.download(ticker, start=start, end=end, progress=False,
                         auto_adjust=True)
    except Exception as e:
        raise BenchmarkUnavailable(benchmark_id, f"network fetch of {ticker}", str(e))
    if px is None or len(px) == 0:
        raise BenchmarkUnavailable(benchmark_id, f"{ticker} price history",
                                   "yfinance returned no rows")
    close = px["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    r = close.astype("float64").pct_change().dropna()
    r.name = f"{ticker.lower()}_tr"
    prov = {
        "source": "yfinance",
        "ticker": ticker,
        "construction": "pct_change of auto_adjust=True Close (total return)",
        "dividends_included": True,
        "network": True,
        "fetched_utc": pd.Timestamp.utcnow().isoformat(),
    }
    return Benchmark(benchmark_id, r, "D", prov)


def spy_total_return(start: Optional[str] = None,
                     end: Optional[str] = None) -> Benchmark:
    """SPY total return -- the LIVE ruler for the paper fleet."""
    return _yf_total_return("SPY", "spy_tr_yf_adjclose", start, end)


def qqq(start: Optional[str] = None, end: Optional[str] = None) -> Benchmark:
    """QQQ total return -- for books whose concentration is the question."""
    return _yf_total_return("QQQ", "qqq_tr_yf_adjclose", start, end)


# ------------------------------------------------- the panel's own universe

def _universe_indices(px: pd.DataFrame, names: pd.DataFrame) -> pd.DataFrame:
    try:
        from learner import dataset as _ds
    except Exception as e:  # pragma: no cover
        raise BenchmarkUnavailable("ew_crsp_common_main", "learner.dataset", str(e))
    return _ds.market_indices(px, names)


def ew_universe(px: pd.DataFrame, names: pd.DataFrame) -> Benchmark:
    """Equal-weight total return of the PANEL'S OWN admissible universe.

    The honest comparator for a selection claim: same names, no selection. A
    small-cap-tilted book that beats the VW market but loses to this one did
    not select; it was small.
    """
    idx = _universe_indices(px, names).set_index("date")
    r = idx["ew_ret"].dropna()
    return Benchmark("ew_crsp_common_main", r, "D", {
        "source": "learner.dataset.market_indices",
        "construction": "equal-weight daily total return, CRSP common stock / "
                        "main exchange, membership resolved per (permno, date)",
        "dividends_included": True,
        "network": False,
    })


def vw_universe(px: pd.DataFrame, names: pd.DataFrame) -> Benchmark:
    """Value-weight total return of the panel's own universe (prev-day caps)."""
    idx = _universe_indices(px, names).set_index("date")
    r = idx["vw_ret"].dropna()
    return Benchmark("vw_crsp_common_main", r, "D", {
        "source": "learner.dataset.market_indices",
        "construction": "value-weight daily total return, weights on the "
                        "previous session's market cap",
        "dividends_included": True,
        "network": False,
    })


# ------------------------------------------------------------ derived legs

def beta_matched(market: Benchmark, beta: float,
                 rf: Optional[Benchmark] = None) -> Benchmark:
    """beta x market + (1 - beta) x rf -- what the leverage alone would earn.

    Quote this beside any book whose gross exposure is not 100%. The toxic-band
    short's "+76.6%/yr hedged gross" embedded roughly +27%/yr of equity premium
    on a 1.48x long market leg; against its beta-matched leg there was much
    less to explain.
    """
    m = market.returns.dropna()
    if rf is None:
        try:
            rf = cash()
        except BenchmarkUnavailable:
            rf = None
    if rf is not None:
        f = rf.returns.reindex(m.index).fillna(0.0)
    else:
        f = pd.Series(0.0, index=m.index)
    r = beta * m + (1.0 - beta) * f
    r.name = f"beta_{beta:g}_matched"
    return Benchmark(f"beta_matched", r, market.freq, {
        "source": "learner.benchmark.beta_matched",
        "construction": f"{beta:g} x {market.benchmark_id} + "
                        f"{1.0 - beta:g} x {'cash_rf_pinned' if rf is not None else 'zero'}",
        "beta": float(beta),
        "market_benchmark_id": market.benchmark_id,
        "rf_included": rf is not None,
        "network": bool(market.provenance.get("network")),
    })


def matched(returns: pd.Series, label: str, construction: str,
            freq: str = "M", **extra) -> Benchmark:
    """A bespoke strategy-matched control. The construction string is MANDATORY.

    Bespoke is allowed; undocumented is not. `construction` is hashed into the
    stamp, so a reader six months later can tell whether the "matched control"
    matched on sector, on size, on the admissible set, or on nothing.
    """
    if not construction or not construction.strip():
        raise ValueError("matched() requires a non-empty construction string")
    prov = {
        "source": "learner.benchmark.matched",
        "construction": construction,
        "label": label,
        "network": False,
    }
    prov.update(extra)
    return Benchmark(f"matched:{label}", returns.dropna(), freq, prov)


# ---------------------------------------------------------------- registry

#: Every canonical id and the callable that builds it. `resolve()` dispatches
#: here so a receipt's `benchmark_id` is a closed vocabulary, not free text.
REGISTRY: dict[str, Callable[..., Benchmark]] = {
    "vw_market_tr_pinned": pinned_market_total_return,
    "cash_rf_pinned": cash,
    "spy_tr_yf_adjclose": spy_total_return,
    "qqq_tr_yf_adjclose": qqq,
    "ew_crsp_common_main": ew_universe,
    "vw_crsp_common_main": vw_universe,
    "beta_matched": beta_matched,
    "matched": matched,
}

#: Ids that require network. A test asserts the fast suite never resolves one.
NETWORK_IDS: frozenset[str] = frozenset({"spy_tr_yf_adjclose", "qqq_tr_yf_adjclose"})


def resolve(benchmark_id: str, **kwargs) -> Benchmark:
    """Build a canonical benchmark by id. Unknown ids REFUSE with the vocabulary."""
    fn = REGISTRY.get(benchmark_id)
    if fn is None:
        raise BenchmarkUnavailable(
            benchmark_id, "a registered benchmark id",
            "known ids: " + ", ".join(sorted(REGISTRY)))
    return fn(**kwargs)


# ------------------------------------------------------------- validation

def declare(benchmark_id: str, *, construction: str,
            span: Optional[list] = None, n_periods: Optional[int] = None,
            **extra) -> dict:
    """Stamp a canonical benchmark a caller measured WITHOUT holding the series.

    Why this exists: `backend/services/backtest.py` downloads SPY adjusted close
    itself (it needs the price PATH to compute the signal, not just the return),
    so it has no `Benchmark` object to call `.stamp()` on. Without this function
    it would hand-roll a stamp, `validate_stamp` would reject it for naming the
    wrong module, and the tempting fix would be to widen the validator to accept
    several modules -- which is how a gate stops gating.

    So: ONE producer, ONE validator, and the fact that no series was passed is
    RECORDED (`declared_only: True`) rather than hidden. The id must still be in
    the registry, so nobody can declare `^GSPC` to be the market.
    """
    if benchmark_id not in REGISTRY and not benchmark_id.startswith("matched:"):
        raise BenchmarkUnavailable(
            benchmark_id, "a registered benchmark id",
            "known ids: " + ", ".join(sorted(REGISTRY)))
    if not construction or not construction.strip():
        raise ValueError("declare() requires a non-empty construction string")
    prov = {"construction": construction, "declared_only": True}
    prov.update(extra)
    body = {
        "schema": BENCHMARK_SCHEMA,
        "module": CANONICAL_MODULE,
        "benchmark_id": benchmark_id,
        "freq": prov.get("freq", "D"),
        "overlapping": False,
        "provenance": prov,
    }
    blob = json.dumps(body, sort_keys=True, default=str).encode("utf-8")
    body["provenance_sha256"] = hashlib.sha256(blob).hexdigest()
    body["span"] = span
    body["n_periods"] = n_periods
    return body


def validate_stamp(stamp: object) -> tuple[bool, str]:
    """Is this a stamp this module could have produced? Returns (ok, reason)."""
    if not isinstance(stamp, dict):
        return False, "stamp is not an object"
    if stamp.get("module") != CANONICAL_MODULE:
        return False, f"module is {stamp.get('module')!r}, not {CANONICAL_MODULE!r}"
    if int(stamp.get("schema", -1)) != BENCHMARK_SCHEMA:
        return False, f"schema {stamp.get('schema')!r} != {BENCHMARK_SCHEMA}"
    bid = stamp.get("benchmark_id")
    if bid not in REGISTRY and not str(bid).startswith("matched:"):
        return False, f"benchmark_id {bid!r} is not in the registry"
    if not stamp.get("provenance_sha256"):
        return False, "no provenance_sha256"
    prov = stamp.get("provenance")
    if not isinstance(prov, dict) or not prov.get("construction"):
        return False, "provenance carries no construction string"
    return True, "ok"


def is_market_key(key: str) -> bool:
    """Does this receipt key name a market-relative RETURN (not a cap or a regime)?"""
    if key in MARKET_FIELDS:
        return True
    if _MARKET_KEY_EXCLUDE_RE.search(key):
        return False
    return bool(_MARKET_KEY_RE.search(key))


def market_keys(obj: object, _path: str = "") -> list[str]:
    """Every market-return key in a nested receipt, as dotted paths.

    Returned rather than counted so a failing gate can print WHICH field it
    objected to -- a gate that says only "invalid" teaches the reader to skim.
    """
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == STAMP_KEY:
                continue
            here = f"{_path}.{k}" if _path else str(k)
            if is_market_key(str(k)) and not isinstance(v, (dict, list)) and v is not None:
                found.append(here)
            found.extend(market_keys(v, here))
    elif isinstance(obj, list):
        for i, x in enumerate(obj):
            found.extend(market_keys(x, f"{_path}[{i}]"))
    return found


def receipt_quotes_market(obj: object) -> bool:
    """Does this receipt (nested dicts/lists) quote a market number anywhere?"""
    return bool(market_keys(obj))


def find_stamp(obj: object) -> Optional[dict]:
    """The first `market_benchmark` stamp anywhere in a nested receipt."""
    if isinstance(obj, dict):
        s = obj.get(STAMP_KEY)
        if isinstance(s, dict):
            return s
        for v in obj.values():
            found = find_stamp(v)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for x in obj:
            found = find_stamp(x)
            if found is not None:
                return found
    return None


__all__ = [
    "Benchmark", "BenchmarkUnavailable", "BENCHMARK_SCHEMA", "CANONICAL_MODULE",
    "STAMP_KEY", "STAMP_REQUIRED_FROM", "MARKET_FIELDS", "REGISTRY",
    "NETWORK_IDS", "SHUMWAY_FILL",
    "compound", "non_overlapping", "is_market_key", "market_keys",
    "pinned_market_total_return", "cash", "spy_total_return", "qqq",
    "ew_universe", "vw_universe", "beta_matched", "matched",
    "resolve", "declare", "validate_stamp", "receipt_quotes_market", "find_stamp",
]
