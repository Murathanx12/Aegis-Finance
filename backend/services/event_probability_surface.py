"""EVENT_PROBABILITY_SURFACE v0 — model-free coherence checks on the daily
prediction-market snapshots.

Adopted from the 2026-08-22 adjudication (ORDER 27 P5): a set of contracts
over one underlying event is one probability distribution, not a bag of
unrelated binaries. For a mutually-exclusive-and-exhaustive outcome set the
mids must sum to ~1; a deviation is either venue microstructure (spread,
stale quotes) or structural mispricing — v0 only MEASURES it.

Scope v0 = the FED_DECISION family only, reusing the frozen V1 matching
parsers, because that is the one family whose resolution semantics we have
committed to understanding mechanically. Threshold/calendar monotonicity
checks arrive with the families that need them (CPI, index levels) — a check
we cannot ground in committed contract semantics would measure wording.

Statistical-unit rule (the G1 horizon lesson, applied here BEFORE the
mistake): one FOMC meeting = ONE unit. Anything downstream that grades
forecasts against these surfaces scores the meeting's multinomial, never
five correlated binaries as five results.

Descriptive context only. Never a signal, never an order path.
"""

from __future__ import annotations

import logging

from backend.services.prediction_market_matching import (
    MATCHING_SPEC_VERSION, _load_rows, parse_kalshi, parse_polymarket,
)

logger = logging.getLogger(__name__)

BANNER = ("MEASUREMENT ONLY — coherence of market-implied event "
          "distributions; one meeting is one statistical unit; "
          "never a signal, never an order")

#: The V1 convention declares {maintain, hike_25, hike_50plus, cut_25,
#: cut_50plus} mutually exclusive and exhaustive (Fed moves in 25bp
#: multiples). A basket missing classes is reported PARTIAL, not summed
#: against 1 as if complete.
FULL_CLASS_SET = frozenset(
    {"maintain", "hike_25", "hike_50plus", "cut_25", "cut_50plus"})

#: |sum(mids) − 1| above this is flagged. Half the round-trip cost bar:
#: below it, the "violation" is inside quoted spreads and means nothing.
BASKET_TOLERANCE = 0.025


def _meeting_baskets(rows: list[dict], parse) -> dict:
    """meeting -> {action_class: row}, refusing duplicate (meeting, class)."""
    out: dict = {}
    for r in rows:
        key = parse(r)
        if key is None:
            continue
        _family, meeting, action_class = key
        out.setdefault(meeting, {}).setdefault(action_class, []).append(r)
    baskets = {}
    for meeting, classes in out.items():
        basket = {}
        for cls, rs in classes.items():
            if len(rs) == 1:
                basket[cls] = rs[0]
            # duplicates were already refused by the matcher; here they
            # simply void the class — a basket must not guess between them
        baskets[meeting] = basket
    return baskets


def _basket_report(meeting: str, basket: dict) -> dict:
    rep: dict = {"meeting": meeting,
                 "classes_present": sorted(basket)}
    sanity = []
    for cls, r in basket.items():
        bid, ask, mid = r.get("yes_bid"), r.get("yes_ask"), r.get("mid")
        if bid is not None and ask is not None and bid > ask:
            sanity.append(f"{cls}: crossed book (bid {bid} > ask {ask})")
        if mid is not None and not (0.0 <= mid <= 1.0):
            sanity.append(f"{cls}: mid {mid} outside [0, 1]")
    rep["sanity_violations"] = sanity

    mids = {cls: r.get("mid") for cls, r in basket.items()}
    if any(m is None for m in mids.values()) or not mids:
        rep["verdict"] = "REFUSED_NO_MID"
        rep["reason"] = "one-sided book somewhere in the basket"
        return rep
    total = round(sum(mids.values()), 4)
    rep["implied_distribution"] = {c: round(m, 4) for c, m in mids.items()}
    rep["mid_sum"] = total
    if set(basket) != FULL_CLASS_SET:
        # An incomplete basket's sum tells us nothing about coherence — the
        # missing class's probability is simply not quoted on this venue.
        rep["verdict"] = "PARTIAL_BASKET"
        rep["missing_classes"] = sorted(FULL_CLASS_SET - set(basket))
        return rep
    dev = round(abs(total - 1.0), 4)
    rep["deviation_from_one"] = dev
    rep["verdict"] = ("BASKET_INCOHERENT" if dev > BASKET_TOLERANCE
                      else "COHERENT")
    return rep


def surface_day(day: str) -> dict:
    """Coherence report for one snapshot day, both venues. Reads disk only."""
    per_venue = {}
    for source, parse in (("kalshi", parse_kalshi),
                          ("polymarket", parse_polymarket)):
        rows = _load_rows(day, source)
        if not rows:
            per_venue[source] = {"status": "NO_SNAPSHOT"}
            continue
        reports = [_basket_report(m, b)
                   for m, b in sorted(_meeting_baskets(rows, parse).items())]
        per_venue[source] = {
            "status": "ok",
            "n_meetings": len(reports),
            "n_coherent": sum(r["verdict"] == "COHERENT" for r in reports),
            "n_incoherent": sum(
                r["verdict"] == "BASKET_INCOHERENT" for r in reports),
            "meetings": reports,
        }
    return {
        "status": "ok",
        "day": day,
        "banner": BANNER,
        "spec": MATCHING_SPEC_VERSION,
        "family": "FED_DECISION",
        "basket_tolerance": BASKET_TOLERANCE,
        "statistical_unit": "one FOMC meeting = one multinomial distribution",
        "venues": per_venue,
    }


def latest_surface() -> dict:
    """The newest day with a snapshot from either venue."""
    from backend import config

    d = config.PREDICTION_MARKET_DIR / "snapshots"
    if not d.exists():
        return {"status": "OK_EMPTY", "banner": BANNER,
                "reason": "no snapshots yet"}
    days = sorted({f.stem.split(".")[0] for f in d.glob("*.jsonl")})
    if not days:
        return {"status": "OK_EMPTY", "banner": BANNER,
                "reason": "no snapshots yet"}
    return surface_day(days[-1])
