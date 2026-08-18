"""Ground truth for what a trade costs, and the rules for retiring a declared band.

    from backend.services import taq_calibration as TC
    panel = TC.load_panel()                    # refuses on schema drift
    r     = TC.reading_for(panel, "AAPL")      # a TaqReading, or a refusal
    cost  = TC.one_way_cost(r)                 # OneWayBps(MEASURED_TAQ_QUOTED)

WHY THIS EXISTS
===============
Order 18 §1 segmented the cost model because AGK cannot resolve a megacap's
spread: its estimate sits below its own detection floor, and reading the floor
value as the cost charges roughly ten times the truth. The names AGK could not
resolve were given a DECLARED band of 1-5bp one-way, with the explicit clause
that the band **retires when a resolving instrument arrives**.

The instrument arrived. TAQ entitlement was checked on 2026-08-18 and the
millisecond NBBO tables are readable (`reference_wrds_access`). This module is
the retirement mechanism, and it retires the band ONE NAME AT A TIME — because
"we have TAQ now" is a statement about a subscription, while "this name's cost
is measured" is a statement about a name.

THE THING THIS MODULE REFUSES TO LET YOU FORGET
===============================================
The panel is a **quoted** NBBO spread, and three separate biases sit between it
and the number a strategy actually pays. Their SIGNS are known and they do not
all point the same way, so the panel is an ANCHOR, not a conservative bound:

    quoted, not effective      OVER-states  — marketable orders get price
                               improvement inside the NBBO, so the effective
                               spread is typically 0.5-0.9x quoted.
    09:45-15:45 time band      UNDER-states — the open and the close are the
                               widest parts of the session and are excluded.
    message-weighted mean      UNDER-states (usually) — quote messages cluster
                               in active, tight-spread moments, so averaging
                               over messages is not averaging over time.

Two of the three point DOWN. Anyone reporting "quoted over-states, therefore we
are being conservative" has looked at one of them. `bias_ledger()` returns all
three as DATA so a write-up cannot quietly carry only the flattering one, and
`survives_bias_sensitivity()` is how a conclusion earns the right to be stated
anyway: the megacap finding holds at 4x the measured value, which is far outside
any plausible net bias, so it does not depend on resolving the sign.

A QUANTISATION FLOOR IS NOT A VARIANCE FLOOR
============================================
The instrument-floor sweep established that a floor comes from the VARIANCE of
the null reading, not its level — a constant offset is BIAS (subtract it), a
wandering null is BLINDNESS (replace the instrument). AGK's is the second kind.

TAQ's is a THIRD kind, and it behaves differently from both. A quoted spread
cannot be narrower than one tick, so a name trading at a one-tick spread reads
one tick whatever its true willingness-to-trade cost is. That is a QUANTISATION
floor: the reading is a hard UPPER bound on the truth, the sign of the error is
known, and no amount of extra data tightens it. Unlike blindness, the reading
stays usable — an upper bound on a cost is exactly what a conservative repricing
wants. So a name at the tick floor is FLAGGED, not refused, and the flag says
which direction it errs in.
"""

from __future__ import annotations

import csv
import json
import logging
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from backend.services import cost_model as CM

logger = logging.getLogger(__name__)


class TaqRefused(RuntimeError):
    """A TAQ-measured cost was requested where the panel cannot supply one.

    Every path out of this module is either a measurement with a name attached
    or this exception. There is deliberately no "best guess" branch: the whole
    point of the Order 18 ruling is that an unmeasured name keeps its declared
    band, and a module that silently returned a panel-wide average for a name it
    never covered would defeat the ruling while appearing to implement it.
    """


PANEL_PATH = (Path(__file__).parent.parent / "data" / "optimus"
              / "taq_quoted_spreads_calibration.csv")

#: The panel's schema, declared rather than sniffed. A loader that accepts
#: whichever columns it finds will one day map a MEAN onto a MEDIAN and report
#: the difference as a market change.
REQUIRED_COLUMNS = frozenset({
    "date", "ticker", "n_quotes",
    "quoted_spread_bps_mean", "quoted_spread_bps_median", "mid_price_mean",
})

#: US equity minimum price increment above $1 (Reg NMS Rule 612). The quoted
#: spread cannot be narrower than this, which is what makes it a quantisation
#: floor rather than a noise floor.
TICK_USD = 0.01

#: Coverage gates. A name measured on three of twenty-two days has been sampled,
#: not measured, and its dispersion estimate is not one either.
MIN_DAYS = 15
MIN_QUOTES_PER_DAY = 5_000

#: Within this multiple of one tick, the reading IS the tick and carries no
#: information about how much narrower the truth might be.
TICK_FLOOR_TOLERANCE = 1.05

#: Provenance for a cost derived from this panel. Distinct from a hypothetical
#: `MEASURED_TAQ` effective spread, because a quoted spread and an effective
#: spread are different quantities and the name is the only thing that will
#: still be carrying that distinction three call sites downstream.
MEASURED_TAQ_QUOTED = CM.MEASURED_TAQ_QUOTED

#: The factor a headline conclusion must survive before it may be stated despite
#: the unresolved net bias sign. Declared here, before any conclusion was drawn
#: from it, per the standing rule about factors chosen after seeing what they
#: permit.
BIAS_SENSITIVITY_FACTOR = 4.0


# ── the bias ledger ────────────────────────────────────────────────────────

def bias_ledger() -> list[dict]:
    """The three known biases, with SIGNS, as data.

    Returned rather than documented so that a report which omits one has to
    omit it on purpose. `sign` is the direction the measured number is wrong
    relative to the quantity a strategy pays: `OVER` means the panel charges
    more than the truth.
    """
    return [
        {"name": "quoted_not_effective", "sign": "OVER",
         "detail": ("marketable orders execute inside the NBBO; effective "
                    "spread is typically 0.5-0.9x quoted"),
         "resolvable_by": "trade-quote join (Holden-Jacobsen), daemon work"},
        {"name": "intraday_time_band_0945_1545", "sign": "UNDER",
         "detail": ("the open and the close are the widest parts of the "
                    "session and are excluded from the panel"),
         "resolvable_by": "re-pull with the full 09:30-16:00 session"},
        {"name": "message_weighted_not_time_weighted", "sign": "UNDER",
         "detail": ("quote messages cluster in active, tight-spread moments, "
                    "so a mean over messages is not a mean over time"),
         "resolvable_by": "time-weight by quote duration in the SQL"},
    ]


def net_bias_sign() -> str:
    """`NOT_ESTABLISHED` — and that is the honest answer, not a missing one.

    Two biases point down and one points up. Their magnitudes are not measured
    here, so the net sign is unknown; a module that returned "OVER" because the
    over-stating one is the famous one would be asserting a direction it has no
    evidence for.
    """
    signs = {b["sign"] for b in bias_ledger()}
    return "NOT_ESTABLISHED" if len(signs) > 1 else next(iter(signs))


# ── the panel ──────────────────────────────────────────────────────────────

def load_panel(path: Path | str | None = None) -> list[dict]:
    """Read the calibration panel, refusing on anything it does not recognise."""
    p = Path(path) if path is not None else PANEL_PATH
    if not p.exists():
        raise TaqRefused(
            f"no TAQ panel at {p}. The declared band does NOT retire on the "
            f"strength of an entitlement — it retires on a measurement, and "
            f"there is no measurement here. Run scripts/wrds_taq_pull first.")
    with p.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise TaqRefused(
            f"TAQ panel at {p} is empty. An empty panel resolves zero names, "
            f"which downstream reads as 'no name needed retiring'.")
    have = set(rows[0].keys())
    missing = REQUIRED_COLUMNS - have
    if missing:
        raise TaqRefused(
            f"TAQ panel schema drift: missing {sorted(missing)}; got "
            f"{sorted(have)}. Refusing to map columns by guesswork — a mean "
            f"silently read as a median is a bias nobody would look for.")
    out = []
    for r in rows:
        try:
            out.append({
                "date": r["date"],
                "ticker": r["ticker"],
                "n_quotes": int(r["n_quotes"]),
                "mean_bps": float(r["quoted_spread_bps_mean"]),
                "median_bps": float(r["quoted_spread_bps_median"]),
                "mid": float(r["mid_price_mean"]),
            })
        except (TypeError, ValueError) as exc:
            raise TaqRefused(
                f"unparseable panel row {r!r}: {exc}. A row that cannot be read "
                f"is dropped silently by every tolerant parser, and the name it "
                f"belonged to then keeps its band for a reason nobody records."
            ) from exc
    return out


def load_meta(path: Path | str | None = None) -> dict:
    """The panel's own account of what it measured. Absent is a refusal."""
    p = Path(path) if path is not None else PANEL_PATH
    mp = p.with_suffix(".meta.json")
    if not mp.exists():
        raise TaqRefused(
            f"no panel metadata at {mp}. The measure, the session band and the "
            f"full-vs-one-way convention live there; a panel without them is a "
            f"column of numbers whose units are folklore.")
    return json.loads(mp.read_text(encoding="utf-8"))


# ── one name ───────────────────────────────────────────────────────────────

def tick_floor_bps(mid_price: float) -> float:
    """The narrowest spread the tape can express for a name at this price."""
    if not (mid_price > 0):
        raise TaqRefused(f"mid price {mid_price} is not a price")
    return 1e4 * TICK_USD / mid_price


@dataclass(frozen=True)
class TaqReading:
    """One name's measured quoted spread, with everything needed to doubt it."""

    ticker: str
    n_days: int
    total_quotes: int
    full_bps: float                # median across days of each day's median
    full_bps_day_low: float        # min of the daily medians
    full_bps_day_high: float       # max of the daily medians
    mid_price: float
    tick_floor: float
    resolves: bool
    at_tick_floor: bool
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ticks_wide(self) -> float:
        return self.full_bps / self.tick_floor if self.tick_floor > 0 else 0.0

    @property
    def one_way_bps(self) -> float:
        """Half the full spread. The convention lives in `OneWayBps`, and this
        property exists so the halving happens once, here, with a name."""
        return self.full_bps / 2.0


def reading_for(panel: Sequence[dict], ticker: str) -> TaqReading:
    """Aggregate one name's daily rows into a reading, or refuse.

    The central estimate is the MEDIAN OF DAILY MEDIANS, not a pooled mean over
    quotes. Pooling over quotes weights a name by how chatty its tape was that
    day, and one wide, heavily-quoted afternoon would then set the number. The
    daily spread of those medians travels with the reading so that a caller can
    see whether "0.97bp" was a stable fact or one day's luck.
    """
    rows = [r for r in panel if r["ticker"] == ticker]
    if not rows:
        raise TaqRefused(
            f"{ticker} is not in the TAQ panel. Its declared band STAYS. An "
            f"absent name is not a cheap name.")

    eligible = [r for r in rows if r["n_quotes"] >= MIN_QUOTES_PER_DAY]
    daily = sorted(r["median_bps"] for r in eligible)
    notes: list[str] = []
    if len(rows) != len(eligible):
        notes.append(f"{len(rows) - len(eligible)} day(s) below "
                     f"{MIN_QUOTES_PER_DAY} quotes dropped")

    resolves = len(daily) >= MIN_DAYS
    if not daily:
        raise TaqRefused(
            f"{ticker}: every panel day fell below {MIN_QUOTES_PER_DAY} quotes. "
            f"A name this thinly quoted is exactly the segment AGK was kept "
            f"for; do not retire its band on an unusable TAQ read.")
    if not resolves:
        notes.append(f"only {len(daily)} usable day(s) < MIN_DAYS={MIN_DAYS}")

    mid = statistics.median([r["mid"] for r in eligible])
    floor = tick_floor_bps(mid)
    central = statistics.median(daily)
    at_floor = central <= floor * TICK_FLOOR_TOLERANCE
    if at_floor:
        notes.append("at the one-tick quantisation floor: this reading is an "
                     "UPPER bound on the true spread and cannot be tightened "
                     "by more data")
    if central < floor:
        # Not impossible - a sub-penny or high-price name, or a mid that moved
        # across the window - but it means the tick model does not fit here.
        notes.append(f"reading {central:.3f}bp is BELOW the one-tick floor "
                     f"{floor:.3f}bp implied by mid {mid:.2f}; the tick model "
                     f"does not describe this name")

    return TaqReading(
        ticker=ticker, n_days=len(daily),
        total_quotes=sum(r["n_quotes"] for r in eligible),
        full_bps=central, full_bps_day_low=daily[0], full_bps_day_high=daily[-1],
        mid_price=mid, tick_floor=floor, resolves=resolves,
        at_tick_floor=at_floor, notes=tuple(notes))


def one_way_cost(reading: TaqReading) -> CM.OneWayBps:
    """A `OneWayBps` for a name TAQ resolved, or a refusal naming why not."""
    if not reading.resolves:
        raise TaqRefused(
            f"{reading.ticker}: TAQ covers only {reading.n_days} usable day(s) "
            f"(need {MIN_DAYS}). The band does not retire on partial coverage — "
            f"a thin read is how a measurement and a guess become the same "
            f"number. Notes: {'; '.join(reading.notes) or 'none'}")
    return CM.OneWayBps(
        reading.one_way_bps, MEASURED_TAQ_QUOTED,
        basis=(f"TAQ NBBO quoted full spread {reading.full_bps:.3f}bp "
               f"(median of {reading.n_days} daily medians, range "
               f"{reading.full_bps_day_low:.3f}-{reading.full_bps_day_high:.3f}), "
               f"halved to one-way; {reading.ticks_wide:.2f} ticks at mid "
               f"{reading.mid_price:.2f}"))


def cost_for(panel: Sequence[dict], ticker: str) -> dict:
    """The retirement decision for one name, as a dict that states its branch.

    Either the band retires and `cost` is a measurement, or the band stays and
    `band` is the Order 18 declared range with the reason recorded. The reason
    is the point: "TAQ did not cover it" and "TAQ covered it and it was cheap"
    must not be the same row in a summary table.
    """
    out: dict = {"ticker": ticker}
    try:
        reading = reading_for(panel, ticker)
    except TaqRefused as exc:
        out.update(branch=CM.DECLARED_CONSERVATIVE, band_retired=False,
                   band=CM.declared_liquid_band(reason=str(exc)),
                   reason=str(exc))
        return out
    out["reading"] = reading
    try:
        out["cost"] = one_way_cost(reading)
    except TaqRefused as exc:
        out.update(branch=CM.DECLARED_CONSERVATIVE, band_retired=False,
                   band=CM.declared_liquid_band(reason=str(exc)),
                   reason=str(exc))
        return out
    out.update(branch=MEASURED_TAQ_QUOTED, band_retired=True,
               at_tick_floor=reading.at_tick_floor, notes=reading.notes)
    return out


# ── the calibration, and the scope it may not leave ────────────────────────

def calibrate_against_agk(panel: Sequence[dict],
                          agk_one_way_bps: dict[str, float]) -> dict:
    """Compare AGK to TAQ on the overlap, and record where the answer applies.

    The overlap is not a random sample of the market. AGK only produces a
    reading above its own floor for names whose spreads are WIDE, so every pair
    in this comparison comes from the illiquid end. A ratio measured there is a
    statement about that end, and §60's lesson — holding out securities is not
    holding out data when they co-move — is the same shape as the mistake of
    carrying it to megacaps. So the returned dict names its own range and
    `apply_calibration` refuses outside it, rather than leaving that to whoever
    reads the number next.
    """
    pairs = []
    for ticker, agk in agk_one_way_bps.items():
        try:
            reading = reading_for(panel, ticker)
        except TaqRefused:
            continue
        if not reading.resolves:
            continue
        taq = reading.one_way_bps
        if taq <= 0:
            continue
        pairs.append({"ticker": ticker, "agk_one_way_bps": agk,
                      "taq_one_way_bps": taq, "ratio": agk / taq,
                      "at_tick_floor": reading.at_tick_floor})
    if not pairs:
        raise TaqRefused(
            "no name has both a resolving AGK estimate and a resolving TAQ "
            "reading, so there is no overlap to calibrate on. This is a "
            "finding, not an error: it says the two instruments see disjoint "
            "segments, which is precisely why the ruling was segmented.")
    ratios = sorted(p["ratio"] for p in pairs)
    taqs = sorted(p["taq_one_way_bps"] for p in pairs)
    return {
        "n_pairs": len(pairs),
        "pairs": pairs,
        "ratio_median": statistics.median(ratios),
        "ratio_min": ratios[0],
        "ratio_max": ratios[-1],
        "valid_taq_one_way_range_bps": [taqs[0], taqs[-1]],
        "scope": ("measured only on names where AGK resolves, i.e. the wide "
                  "end; not applicable to names AGK could not read, which is "
                  "the entire segment the band was declared for"),
    }


def apply_calibration(calibration: dict, agk_one_way_bps: float) -> float:
    """Deflate an AGK estimate by the measured ratio — inside the range only."""
    lo, hi = calibration["valid_taq_one_way_range_bps"]
    implied = agk_one_way_bps / calibration["ratio_median"]
    if not (lo <= implied <= hi):
        raise TaqRefused(
            f"an AGK estimate of {agk_one_way_bps}bp one-way implies "
            f"{implied:.3f}bp after calibration, outside the range the ratio "
            f"was measured on ({lo:.3f}-{hi:.3f}bp). Extrapolating a "
            f"liquidity-segment correction past its own segment is how the "
            f"floor value became a cost in the first place.")
    return implied


# ── the sensitivity that lets a conclusion be stated anyway ────────────────

def survives_bias_sensitivity(measured_one_way_bps: float,
                              threshold_one_way_bps: float,
                              *, factor: float = BIAS_SENSITIVITY_FACTOR) -> dict:
    """Does a comparison survive the measured value being `factor` times wrong?

    The net bias sign is `NOT_ESTABLISHED`, so a conclusion drawn from the point
    estimate is drawn from a number of unknown direction. A conclusion that
    holds when the measurement is inflated by the declared factor does not
    depend on resolving it.
    """
    if factor < 1.0:
        raise TaqRefused(f"a sensitivity factor of {factor} shrinks the "
                         f"measurement, which tests nothing")
    inflated = measured_one_way_bps * factor
    breaks_at = (threshold_one_way_bps / measured_one_way_bps
                 if measured_one_way_bps > 0 else float("inf"))
    return {
        "measured_one_way_bps": measured_one_way_bps,
        "inflated_one_way_bps": inflated,
        "threshold_one_way_bps": threshold_one_way_bps,
        "factor": factor,
        "survives": bool(inflated < threshold_one_way_bps),
        "breaks_at_factor": breaks_at,
        "net_bias_sign": net_bias_sign(),
    }


def summarise_retirement(results: Iterable[dict]) -> dict:
    """How much of the declared band actually retired. The split is the fact."""
    rows = list(results)
    if not rows:
        raise TaqRefused("no names to summarise; an empty retirement summary "
                         "reads as 'nothing needed retiring'")
    retired = [r for r in rows if r.get("band_retired")]
    at_floor = [r for r in retired if r.get("at_tick_floor")]
    return {
        "n_names": len(rows),
        "n_band_retired": len(retired),
        "n_band_stays": len(rows) - len(retired),
        "fraction_retired": round(len(retired) / len(rows), 4),
        "n_at_tick_floor": len(at_floor),
        "provenance": MEASURED_TAQ_QUOTED,
        "net_bias_sign": net_bias_sign(),
        "note": ("names whose band did NOT retire carry no measured cost; "
                 "their verdicts are still reported across the declared band"),
    }
