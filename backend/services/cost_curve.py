"""THE COST CURVE: what one crossing of one name on one day actually costs.

A flat basis-point rate says a $4bn-a-day megacap and a $3m-a-day microcap cost
the same to trade, which is wrong by an order of magnitude in both directions
depending on which one the book happens to hold. This module replaces that
scalar with a per-(name, date, order) rate:

    one_way_bps = half_effective_spread_bps + impact_bps(participation)

Both terms are ONE WAY and are reported SEPARATELY on every quote, because
collapsing them is how "spread" and "impact" become the same word three call
sites downstream -- the failure `cost_model.py` already had to write a
paragraph about for the quoted panel.

THE THREE BRANCHES OF THE SPREAD TERM, AND WHY THE THIRD IS NOT A NUMBER
========================================================================
MEASURED_TAQ_EFFECTIVE   the name is in `taq_effective_spreads_v1.jsonl`
                         (184 names, 23 days of 2026): the median of its daily
                         median effective full spreads, halved.
EXTRAPOLATED_REGRESSION  the name is not, but its dollar volume, price and
                         volatility are known: the log-linear fit in
                         `backend/data/optimus/cost_curve/taq_spread_regression_v1.json`,
                         which carries its own R2 and standard errors and
                         travels on the quote.
DECLARED_CONSERVATIVE    neither: a `CostBand`, not a number. An absent name is
                         NOT an average name, and `CostBand` has no `.value`
                         and no `__float__` precisely so a caller cannot treat
                         it as one by accident.

WHAT THIS CURVE IS NOT
======================
It is a FOURTH cost ruler, and the other three disagree with each other.
`NEGATIVE_RESULTS.md` S25 has Corwin-Schultz and Kyle-Obizhaeva disagreeing
3.4-9.1x on LEVEL in the same segments (Spearman 0.66 -- they agree on ORDER,
not magnitude), and this panel's 1.076bp one-way median sits BELOW even KO's
large/mid range. Nothing here adjudicates that. Every receipt names the ruler
it used and stops there.

The source panel's own `verdict_status` is **DEFERRED**: v1 has no
trade-condition, odd-lot or venue filtering. `CONVENTION_MULTIPLIER_RANGE`,
derived from the 9-name x 10-convention probe rather than asserted, is how a
downstream verdict is made to survive that -- and the probe says the direction
is NOT one-signed (excluding midpoint prints RAISES a mid-liquidity name's
effective spread up to 3x; round-lots-only LOWERS a megacap's by ~30%), which
corrects the spec's "strict conventions raise it" in the one direction a
reader could have been misled by.
"""

from __future__ import annotations

import json
import math
import os
import statistics
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Sequence

import numpy as np

from backend.services import cost_model as CM
from backend.strategy.vendor.impact import sqrt_impact


def _repo_root() -> Path:
    """The checkout, honouring `AEGIS_REPO_ROOT`.

    NOT `Path(__file__)`-rooted. Inside the packaged app `__file__` lives under
    `_internal/`, which is empty, so a path built that way reads a directory
    that does not exist and returns nothing WITHOUT failing -- defect family
    #14, five instances in one day on 2026-09-10. Here it would be worse than
    silent: the panel loader's refusal fires, so a frozen build would report
    "no TAQ panel" and a reader would conclude the data had been lost.
    `test_frozen_path_family.py` is the gate and it caught this module on its
    first full suite run.
    """
    env = os.getenv("AEGIS_REPO_ROOT")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent.parent


_DATA = _repo_root() / "backend" / "data" / "optimus"

#: The 4,224-row effective-spread panel (184 names x 23 days, 2026-07-15 to
#: 2026-08-14). Nothing in this repo consumed it before this module.
EFFECTIVE_PANEL_PATH = _DATA / "taq_effective_spreads_v1.jsonl"

#: Where `scripts/cost_curve_fit.py` writes the regression. READ here, never
#: fitted here: a cost model that re-fits itself at import is a cost model
#: whose number depends on which parquet was on disk that night.
REGRESSION_PATH = _DATA / "cost_curve" / "taq_spread_regression_v1.json"

#: The conventions probe, 9 names x 10 trade-condition conventions on one day.
CONVENTIONS_PROBE_PATH = _DATA / "effective_conventions_probe_20260814_wide.json"

#: Chunk 5b's D2 deliverable: every paper fill vs the IEX quote and the SIP
#: NBBO. ABSENT as of 2026-09-12, which is why `retail_paper` refuses.
FILL_QUALITY_DIR = _DATA / "fill_quality"

#: The declared regimes. A book names ONE at construction.
KNOWN_CURVES = ("flat", "taq_empirical", "retail_paper")

#: Coverage gates, mirroring `taq_calibration.MIN_DAYS` / `MIN_QUOTES_PER_DAY`.
#: On v1 the thinnest name-day carries 9,597 trades, so the per-day gate drops
#: ZERO rows here -- stated rather than discovered, because a gate whose reach
#: is invisible is a gate nobody re-checks when the next pull is wider.
MIN_DAYS = 15
MIN_TRADES_PER_DAY = 5_000

#: THE ONE DERIVED NUMBER IN THIS MODULE. Solved in
#: `scripts/cost_curve_fit.py` so that
#:
#:     1e4 * eta * volatility_ann * sqrt(0.01) + half_spread_bps = 40bp
#:
#: at the fitted panel's median annualised volatility and median half spread --
#: the midpoint of the 30-50bp one-way cost at 1% of ADV that Frazzini, Israel
#: and Moskowitz (2018), "Trading Costs" (AQR) report on live institutional
#: trades, as cited by `spec_cost_model.md` S1.4 (the spec is the proximate
#: source; the paper was not re-checked in the session that froze this).
#:
#: THE UNIT. This eta multiplies an ANNUALISED volatility. The vendored
#: `sqrt_impact` documents a DAILY one, so this value is NOT comparable to the
#: vendor's 0.3-0.8 default: the comparable figure is
#: `eta * sqrt(252) = 1.91`, which is well ABOVE Almgren et al. (2005)'s
#: calibrated range. That is the finding, not a bug: FIM's blended live-trade
#: cost implies roughly 2.5x the impact the classic square-root calibration
#: does, and this curve is the more expensive of the two.
#:
#: Pinned by `test_cost_curve.py`; a re-calibration is a deliberate edit to a
#: named test, never a silent drift.
ETA_SQRT_IMPACT = 0.120620

#: The measured multiplier range the effective spread moves over when the
#: trade-condition convention changes, DERIVED from the probe by
#: `convention_multiplier_range()` rather than asserted. Cells with zero
#: surviving prints are excluded: a convention that keeps no trades measures
#: nothing, and folding its 0.0 in would make every verdict "sensitive".
_CONVENTION_MIN_PRINTS = 1


class CurveError(ValueError):
    """A curve was asked for something it does not implement."""


# ── the quote ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CostQuote:
    """One name, one day, one order: the rate and everything needed to doubt it.

    Deliberately NOT a float either. The two terms are carried apart, and the
    provenance rides with them, so a receipt can print "80% measured, 20%
    regression" instead of one averaged number whose mix nobody recorded.
    """

    spread_bps: float
    impact_bps: float
    provenance: str
    basis: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)
    meta: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        for v, n in ((self.spread_bps, "spread"), (self.impact_bps, "impact")):
            if not (float(v) >= 0.0):
                raise CM.CostRefused(
                    f"a {n} of {v} is not a cost: a negative or NaN rate pays "
                    f"the book to trade, which no downstream check would flag "
                    f"as anything but a good result.")
        if self.provenance not in CM._PROVENANCES:
            raise CM.CostRefused(f"unknown provenance {self.provenance!r}")

    @property
    def one_way_bps(self) -> float:
        return float(self.spread_bps) + float(self.impact_bps)

    @property
    def round_trip_bps(self) -> float:
        return 2.0 * self.one_way_bps

    def as_one_way(self) -> CM.OneWayBps:
        return CM.OneWayBps(self.one_way_bps, self.provenance, self.basis)

    def as_row(self) -> dict:
        return {"one_way_bps": round(self.one_way_bps, 4),
                "spread_bps": round(float(self.spread_bps), 4),
                "impact_bps": round(float(self.impact_bps), 4),
                "provenance": self.provenance,
                "basis": self.basis,
                "notes": list(self.notes),
                **{k: v for k, v in self.meta}}


# ── the measured panel ─────────────────────────────────────────────────────

def load_effective_panel(path: Path | str | None = None) -> list[dict]:
    """Read the effective-spread panel, refusing on anything unrecognised."""
    p = Path(path) if path is not None else EFFECTIVE_PANEL_PATH
    if not p.exists():
        raise CM.CostRefused(
            f"no effective-spread panel at {p}. `curve='taq_empirical'` does "
            f"not fall back to a flat rate -- a measured curve with no "
            f"measurement is a flat rate wearing a better name.")
    rows: list[dict] = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            missing = {"date", "ticker", "n_trades",
                       "effective_full_bps_median"} - set(r)
            if missing:
                raise CM.CostRefused(
                    f"effective panel schema drift: row missing "
                    f"{sorted(missing)}. Refusing to map columns by guesswork "
                    f"-- a dollar-weighted mean read as a median is a bias "
                    f"nobody would look for.")
            rows.append({"date": str(r["date"]), "ticker": str(r["ticker"]),
                         "n_trades": int(r["n_trades"]),
                         "full_bps": float(r["effective_full_bps_median"]),
                         "basis": str(r.get("basis", ""))})
    if not rows:
        raise CM.CostRefused(f"effective panel at {p} is empty")
    return rows


@lru_cache(maxsize=4)
def _panel_cached(path: str) -> tuple[dict, ...]:
    return tuple(load_effective_panel(Path(path)))


def panel() -> list[dict]:
    """The default panel, read once per process."""
    return list(_panel_cached(str(EFFECTIVE_PANEL_PATH)))


@dataclass(frozen=True)
class EffectiveReading:
    """One name's measured effective spread, with everything needed to doubt it."""

    ticker: str
    n_days: int
    n_trades: int
    full_bps: float          # median across days of each day's median
    day_low: float
    day_high: float
    resolves: bool
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def half_bps(self) -> float:
        """Half the full spread. The halving happens once, here, with a name --
        `turn = sum(|dw|)` counts both legs, so the rate charged against it is
        the HALF spread while the panel stores the FULL one."""
        return self.full_bps / 2.0


def reading_for(rows: Sequence[dict], ticker: str) -> EffectiveReading:
    """Aggregate one name's daily rows, or refuse.

    MEDIAN OF DAILY MEDIANS, not a pooled mean over trades: pooling weights a
    name by how chatty its tape was that day, and one wide, heavily-printed
    afternoon would set the number.
    """
    mine = [r for r in rows if r["ticker"] == ticker]
    if not mine:
        raise CM.CostRefused(
            f"{ticker} is not in the effective-spread panel. Its declared "
            f"band STAYS. An absent name is not a cheap name.")
    eligible = [r for r in mine if r["n_trades"] >= MIN_TRADES_PER_DAY]
    notes: list[str] = []
    if len(eligible) != len(mine):
        notes.append(f"{len(mine) - len(eligible)} day(s) below "
                     f"{MIN_TRADES_PER_DAY} trades dropped")
    if not eligible:
        raise CM.CostRefused(
            f"{ticker}: every panel day fell below {MIN_TRADES_PER_DAY} "
            f"trades. A name this thinly printed has been sampled, not "
            f"measured.")
    daily = sorted(r["full_bps"] for r in eligible)
    resolves = len(daily) >= MIN_DAYS
    if not resolves:
        notes.append(f"only {len(daily)} usable day(s) < MIN_DAYS={MIN_DAYS}")
    notes.append("panel v1: NO trade-condition/odd-lot/venue filtering "
                 "(verdict_status DEFERRED)")
    return EffectiveReading(
        ticker=ticker, n_days=len(daily),
        n_trades=sum(r["n_trades"] for r in eligible),
        full_bps=statistics.median(daily), day_low=daily[0],
        day_high=daily[-1], resolves=resolves, notes=tuple(notes))


# ── the regression, for names the panel never saw ──────────────────────────

@lru_cache(maxsize=4)
def load_regression(path: str | None = None) -> dict:
    """The fitted coefficients. Refuses when absent -- see module docstring."""
    p = Path(path) if path else REGRESSION_PATH
    if not p.exists():
        raise CM.CostRefused(
            f"no spread regression at {p}. Run `python -m "
            f"scripts.cost_curve_fit`. The curve does NOT fit itself at "
            f"import: a coefficient that changes with whichever parquet was "
            f"on disk makes every receipt that quoted it unreproducible.")
    blob = json.loads(p.read_text(encoding="utf-8"))
    need = {"intercept", "log_dollar_volume_usd", "log_price_usd",
            "volatility_ann"}
    have = set(blob.get("coefficients", {}))
    if need - have:
        raise CM.CostRefused(
            f"regression receipt at {p} is missing {sorted(need - have)}")
    return blob


def regression_coefficients(fit: dict | None = None) -> tuple[float, float, float, float]:
    f = fit if fit is not None else load_regression()
    c = f["coefficients"]
    return (float(c["intercept"]["estimate"]),
            float(c["log_dollar_volume_usd"]["estimate"]),
            float(c["log_price_usd"]["estimate"]),
            float(c["volatility_ann"]["estimate"]))


def regression_half_spread_bps(dollar_volume_usd: float, price_usd: float,
                               volatility_ann: float,
                               fit: dict | None = None) -> float:
    """`exp(b0 + b1 log(dolvol) + b2 log(px) + b3 vol)`, one name.

    The MEDIAN of a lognormal, not its mean: no `exp(sigma^2/2)` correction is
    applied, because the left-hand side was fitted in logs and the quantity a
    cost model wants is the typical name's cost, not the expectation over a
    fat right tail it would then charge every name.
    """
    b0, b1, b2, b3 = regression_coefficients(fit)
    for v, n in ((dollar_volume_usd, "dollar_volume_usd"),
                 (price_usd, "price_usd")):
        if not (float(v) > 0):
            raise CM.CostRefused(f"{n}={v} is not positive; the regression is "
                                 f"in logs and has no answer here")
    if not (float(volatility_ann) >= 0):
        raise CM.CostRefused(f"volatility_ann={volatility_ann} is not a "
                             f"volatility")
    return float(math.exp(b0 + b1 * math.log(float(dollar_volume_usd))
                          + b2 * math.log(float(price_usd))
                          + b3 * float(volatility_ann)))


def regression_half_spread_bps_array(dollar_volume_usd, price_usd,
                                     volatility_ann,
                                     fit: dict | None = None) -> np.ndarray:
    """Vectorised twin, for the replay loop. NaN where an input is unusable --
    the caller decides what an unpriceable name costs, because silently
    substituting a population mean here is exactly the "an absent name is an
    average name" error the scalar path refuses."""
    b0, b1, b2, b3 = regression_coefficients(fit)
    dv = np.asarray(dollar_volume_usd, dtype=float)
    px = np.asarray(price_usd, dtype=float)
    vl = np.asarray(volatility_ann, dtype=float)
    ok = np.isfinite(dv) & (dv > 0) & np.isfinite(px) & (px > 0) & np.isfinite(vl)
    out = np.full(np.broadcast(dv, px, vl).shape, np.nan, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        vals = np.exp(b0 + b1 * np.log(np.where(ok, dv, 1.0))
                      + b2 * np.log(np.where(ok, px, 1.0))
                      + b3 * np.where(ok, vl, 0.0))
    return np.where(ok, vals, out)


# ── the impact term ────────────────────────────────────────────────────────

def impact_bps(volatility_ann: float, participation: float,
               eta: float = ETA_SQRT_IMPACT) -> float:
    """`1e4 * eta * sigma_ann * sqrt(participation)`, via the VENDORED function.

    The formula is not re-derived here. `sqrt_impact` is byte-pinned MIT vendor
    code (`test_strategy_execution.py`); calling it with `price=1, direction=+1,
    adv=1` collapses it to its bare impact fraction, which is then expressed in
    basis points. Forking the formula to save one multiplication is how a
    vendored file and its caller drift apart.
    """
    p = float(participation)
    if not (p >= 0.0) or not math.isfinite(p):
        raise CM.CostRefused(f"participation={participation} is not a rate")
    if p == 0.0:
        return 0.0
    fill = sqrt_impact(1.0, 1, p, 1.0, float(volatility_ann), eta=float(eta))
    return 1e4 * (float(fill) - 1.0)


# ── the conventions sensitivity ────────────────────────────────────────────

@lru_cache(maxsize=2)
def convention_multiplier_range(path: str | None = None) -> tuple[float, float]:
    """How far the measured effective spread moves when the convention does.

    DERIVED from the probe, not asserted. The spec said strict Holden-Jacobsen
    conventions RAISE the ratio; the probe says the sign depends on the name --
    `no_midpoint` raises WEC 2.98x while `round_lots_only` lowers MSFT to
    0.47x. A one-signed caveat would have been wrong in both directions.
    """
    p = Path(path) if path else CONVENTIONS_PROBE_PATH
    if not p.exists():
        raise CM.CostRefused(
            f"no conventions probe at {p}; the panel's verdict_status is "
            f"DEFERRED and there is nothing to bound the sensitivity with.")
    blob = json.loads(p.read_text(encoding="utf-8"))
    mults: list[float] = []
    for _name, block in blob.get("names", {}).items():
        grid = {g["convention"]: g for g in block.get("grid", [])}
        base = grid.get("v1_all", {}).get("med_eff_bps")
        if not base:
            continue
        for g in grid.values():
            if int(g.get("n_prints", 0)) < _CONVENTION_MIN_PRINTS:
                continue
            m = float(g["med_eff_bps"]) / float(base)
            if m > 0:
                mults.append(m)
    if not mults:
        raise CM.CostRefused(f"conventions probe at {p} yielded no multipliers")
    return (round(min(mults), 3), round(max(mults), 3))


def survives_convention_sensitivity(verdict_fn, measured_one_way_bps: float,
                                    path: str | None = None) -> dict:
    """Evaluate a verdict at BOTH ends of the conventions range.

    Mirrors `taq_calibration.survives_bias_sensitivity` and
    `cost_model.verdict_across_band`: a verdict that only holds at v1's
    unfiltered convention is `COST_MODEL_SENSITIVE`, not a pass.
    """
    lo, hi = convention_multiplier_range(path)
    at_lo = verdict_fn(measured_one_way_bps * lo)
    at_hi = verdict_fn(measured_one_way_bps * hi)
    agree = at_lo == at_hi
    return {"multiplier_low": lo, "multiplier_high": hi,
            "one_way_bps_low": round(measured_one_way_bps * lo, 4),
            "one_way_bps_high": round(measured_one_way_bps * hi, 4),
            "verdict_low": at_lo, "verdict_high": at_hi,
            "survives": agree,
            "verdict": at_lo if agree else CM.COST_MODEL_SENSITIVE,
            "basis": ("effective_conventions_probe_20260814_wide: 9 names x 10 "
                      "conventions, one day; v1 panel verdict_status DEFERRED")}


# ── the institutional curve ────────────────────────────────────────────────

def taq_empirical_one_way(ticker: str | None = None, *,
                          participation: float = 0.0,
                          volatility_ann: float | None = None,
                          dollar_volume_usd: float | None = None,
                          price_usd: float | None = None,
                          rows: Sequence[dict] | None = None,
                          fit: dict | None = None) -> CostQuote | CM.CostBand:
    """The institutional one-way cost for one name-day-order.

    Returns a `CostQuote` when the spread term is measured or extrapolable, and
    a `CostBand` -- which has no `.value` and no `__float__` -- when it is
    neither. The type IS the refusal: a caller that could `float()` the result
    of a name nobody measured has already defeated it.
    """
    notes: list[str] = []
    spread: float | None = None
    provenance = ""
    basis = ""

    if ticker:
        try:
            reading = reading_for(rows if rows is not None else panel(), ticker)
        except CM.CostRefused as exc:
            notes.append(str(exc).split(".")[0])
        else:
            if reading.resolves:
                spread = reading.half_bps
                provenance = CM.MEASURED_TAQ_EFFECTIVE
                basis = (f"TAQ effective full spread {reading.full_bps:.3f}bp "
                         f"(median of {reading.n_days} daily medians, range "
                         f"{reading.day_low:.3f}-{reading.day_high:.3f}), "
                         f"halved to one-way; conventions=v1_unfiltered")
                notes.extend(reading.notes)
            else:
                notes.append(f"{ticker}: {reading.n_days} usable day(s) < "
                             f"MIN_DAYS={MIN_DAYS}; not a measurement")

    if spread is None:
        if (dollar_volume_usd is not None and price_usd is not None
                and volatility_ann is not None):
            f = fit if fit is not None else load_regression()
            spread = regression_half_spread_bps(dollar_volume_usd, price_usd,
                                                volatility_ann, f)
            provenance = CM.EXTRAPOLATED_REGRESSION
            basis = (f"log-linear fit on {f['n']} TAQ-covered names, "
                     f"R2={f['r2']}, LOO R2={f.get('loo_r2')}, residual sigma "
                     f"{f.get('residual_sigma_log')} in logs")
            notes.append("extrapolated, not measured: this name is outside the "
                         "184-name TAQ panel")
        else:
            missing = [n for n, v in (("dollar_volume_usd", dollar_volume_usd),
                                      ("price_usd", price_usd),
                                      ("volatility_ann", volatility_ann))
                       if v is None]
            return CM.declared_liquid_band(
                reason=(f"{ticker or 'name'}: no TAQ row and the regression is "
                        f"missing {missing}. An absent name is NOT an average "
                        f"name, so this is a DECLARED band and not the "
                        f"population mean."))

    imp = impact_bps(float(volatility_ann), participation) if (
        volatility_ann is not None and participation) else 0.0
    if participation and volatility_ann is None:
        raise CM.CostRefused(
            "a participation rate was given with no volatility: the impact "
            "term is eta * sigma * sqrt(POV) and has no value without sigma. "
            "Charging zero impact instead would understate every large order "
            "silently.")
    meta: list[tuple[str, float]] = [("participation", float(participation))]
    if provenance == CM.EXTRAPOLATED_REGRESSION:
        f = fit if fit is not None else load_regression()
        meta.append(("regression_r2", float(f["r2"])))
        meta.append(("regression_loo_r2", float(f.get("loo_r2", float("nan")))))
        meta.append(("regression_residual_sigma_log",
                     float(f.get("residual_sigma_log", float("nan")))))
    return CostQuote(spread_bps=spread, impact_bps=imp, provenance=provenance,
                     basis=basis, notes=tuple(notes), meta=tuple(meta))


# ── the retail curve: a STUB that refuses, and says why ────────────────────

#: The ceiling of the declared retail band: the flat rate every night receipt
#: currently charges (`scripts/night_*.py`, `COST_BPS = 25.0`).
RETAIL_CEILING_ONE_WAY_BPS = 25.0

#: The floor: Alpaca cannot beat the NBBO, so retail cannot be cheaper than the
#: institutional effective half spread the tape recorded.
RETAIL_FLOOR_ONE_WAY_BPS = 1.076


def fill_quality_receipts(directory: Path | str | None = None) -> list[Path]:
    d = Path(directory) if directory is not None else FILL_QUALITY_DIR
    return sorted(d.glob("*.jsonl")) if d.exists() else []


def retail_paper_status(directory: Path | str | None = None) -> dict:
    """What the retail curve can and cannot do, as a payload a receipt prints."""
    receipts = fill_quality_receipts(directory)
    return {
        "curve": "retail_paper",
        "available": bool(receipts),
        "state": "MEASURED" if receipts else "STUB_REFUSES",
        "n_fill_quality_receipts": len(receipts),
        "blocked_on": None if receipts else (
            "chunk 5b / lane D item D2: every paper fill vs the IEX quote and "
            "vs the SIP NBBO. No receipt on disk at "
            f"{Path(directory) if directory else FILL_QUALITY_DIR}."),
        "declared_band_one_way_bps": [RETAIL_FLOOR_ONE_WAY_BPS,
                                      RETAIL_CEILING_ONE_WAY_BPS],
        "why_not_the_institutional_curve": (
            "Alpaca paper quotes IEX (~2.5% of consolidated volume) and its "
            "fills have documented quirks (partial fills ~10% of the time at "
            "random size; tif=opg 13/15 EXPIRED UNFILLED on 2026-09-02). "
            "Falling back to the TAQ curve would understate retail cost BY "
            "CONSTRUCTION, because the SIP-wide tape is a strictly better book "
            "than the one these fills see."),
    }


def retail_paper_band(directory: Path | str | None = None) -> CM.CostBand:
    """The declared band standing in until D2 lands. Not a point estimate."""
    return CM.CostBand(
        low=CM.OneWayBps(RETAIL_FLOOR_ONE_WAY_BPS, CM.DECLARED_CONSERVATIVE,
                         "TAQ effective one-way median: Alpaca cannot beat the NBBO"),
        high=CM.OneWayBps(RETAIL_CEILING_ONE_WAY_BPS, CM.DECLARED_CONSERVATIVE,
                          "the flat 25bp every night receipt charges today"),
        reason=retail_paper_status(directory)["blocked_on"]
        or "fill-quality receipts exist; this band is superseded")


def retail_paper_one_way(*_a, directory: Path | str | None = None,
                         **_kw) -> CostQuote:
    """REFUSES until chunk 5b's D2 fill-quality receipt exists."""
    st = retail_paper_status(directory)
    if not st["available"]:
        raise CM.CostRefused(
            "no fill-quality receipt; a retail book may not claim "
            "curve='retail_paper' as a measured rate until one exists. "
            f"{st['blocked_on']} Use `retail_paper_band()` for the DECLARED "
            f"band {st['declared_band_one_way_bps']} one-way, and state that "
            f"it is declared.")
    raise NotImplementedError(
        "fill-quality receipts are on disk but the retail curve's reader is "
        "chunk 5c's addendum, not 5c itself. Refusing rather than guessing at "
        "a schema this session never saw.")


# ── what a Policy needs to know before it can refuse zero cost ─────────────

def curve_floor_one_way_bps(curve: str) -> float:
    """The cheapest one-way rate this curve can EVER charge.

    `Policy`'s zero-cost refusal is about a book that pays nothing. Under a
    curve, `transaction_cost_bps` is unused, so the refusal has to ask the
    curve itself -- and a curve whose every rate happened to floor at exactly
    zero (a regression gone wrong, a panel of zeros) is the true bug that
    refusal exists to catch.
    """
    if curve not in KNOWN_CURVES:
        raise CurveError(f"unknown cost curve {curve!r}; declared: "
                         f"{list(KNOWN_CURVES)}")
    if curve == "flat":
        raise CurveError(
            "'flat' has no curve floor: its rate is the policy's own declared "
            "transaction_cost_bps + slippage_bps. Asking the curve instead "
            "would silently replace a declared number with a measured one.")
    if curve == "retail_paper":
        return RETAIL_FLOOR_ONE_WAY_BPS
    rows = panel()
    halves = [r["full_bps"] / 2.0 for r in rows
              if r["n_trades"] >= MIN_TRADES_PER_DAY and r["full_bps"] > 0]
    if not halves:
        return 0.0
    return float(min(halves))


def curve_provenance_mix(quotes: Sequence[CostQuote | CM.CostBand]) -> dict:
    """THE SPLIT IS THE REPORTABLE FACT -- `cost_model.summarise_segmentation`'s
    rule, applied to a book's own charged rates. A book that is 80% measured
    and 20% extrapolated prints both counts, never one blended label."""
    counts: dict[str, int] = {}
    for q in quotes:
        counts[q.provenance] = counts.get(q.provenance, 0) + 1
    total = sum(counts.values())
    return {"n": total, "counts": dict(sorted(counts.items())),
            "mix": {k: round(v / total, 4) for k, v in sorted(counts.items())}
            if total else {}}


__all__ = [
    "CONVENTIONS_PROBE_PATH", "EFFECTIVE_PANEL_PATH", "ETA_SQRT_IMPACT",
    "FILL_QUALITY_DIR", "KNOWN_CURVES", "MIN_DAYS", "MIN_TRADES_PER_DAY",
    "REGRESSION_PATH", "RETAIL_CEILING_ONE_WAY_BPS",
    "RETAIL_FLOOR_ONE_WAY_BPS", "CostQuote", "CurveError", "EffectiveReading",
    "convention_multiplier_range", "curve_floor_one_way_bps",
    "curve_provenance_mix", "fill_quality_receipts", "impact_bps",
    "load_effective_panel", "load_regression", "panel", "reading_for",
    "regression_coefficients", "regression_half_spread_bps",
    "regression_half_spread_bps_array", "retail_paper_band",
    "retail_paper_one_way", "retail_paper_status",
    "survives_convention_sensitivity", "taq_empirical_one_way",
]
