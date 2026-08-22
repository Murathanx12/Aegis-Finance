"""Kalshi↔Polymarket contract matching — TRIAL-PREDMARKET-2's pairing layer.

Spec: "Aegis module"/TRIALS/INSTR-PREDMARKET-MATCHING.md (V1, FED_DECISION
family only). The matcher is deliberately narrow: it pairs contracts whose
resolution semantics are MECHANICALLY identical under a declared convention,
and refuses everything else with a reason. A fuzzy text matcher would
manufacture pairs whose divergence measures wording, not mispricing.

V1 family — FED_DECISION: the target-rate action at one named FOMC meeting,
in classes {maintain, hike_25, hike_50plus, cut_25, cut_50plus} under the
declared convention that the Fed moves in 25bp multiples (so Kalshi's
">25bps" and Polymarket's "50+ bps" name the same event).

This module MEASURES same-day divergence. The trial's persistence test
(T vs T+1) and any grading happen only under the committed spec — and the
report says so on every payload.
"""

from __future__ import annotations

import json
import logging
import re

from backend import config

logger = logging.getLogger(__name__)

MATCHING_SPEC_VERSION = "INSTR-PREDMARKET-MATCHING-V1"

#: FROZEN in PREREG_PREDMARKET_2: divergence below this is not claimed as
#: money (Polymarket taker 0.04 + Kalshi ~0.07*p*(1-p) round trip + spreads).
COST_BAR = 0.05

#: Executable-edge fee model (REPORTED metric only — the trial's deciding
#: metric stays the frozen mid-divergence above). Declared approximations:
#: Kalshi general taker fee ~= 0.07 * p * (1-p) per contract at executed
#: price p (per the published schedule, ignoring per-order rounding-up to
#: the cent, which UNDERSTATES cost slightly for small orders); Polymarket
#: taker fee ~= rate * min(p, 1-p) (fee on winnings; makers pay zero). The
#: Polymarket rate comes from the row's snapshot (`fee_rate`, measured live
#: from feeSchedule) with 0.05 as the conservative fallback.
KALSHI_TAKER_COEF = 0.07
POLYMARKET_TAKER_FALLBACK = 0.05

BANNER = ("MEASUREMENT ONLY — same-day cross-venue divergence; persistence "
          "(T vs T+1) and grading run under the committed matching spec; "
          "never a signal, never an order")

_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
_MONTH_NAMES = {name.lower(): num for name, num in {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5,
    "June": 6, "July": 7, "August": 8, "September": 9, "October": 10,
    "November": 11, "December": 12}.items()}

_KALSHI_FED = re.compile(
    r"^KXFEDDECISION-(?P<yy>\d{2})(?P<mon>[A-Z]{3})-(?P<act>H0|H25|H26|C25|C26)$")

_KALSHI_CLASS = {"H0": "maintain", "H25": "hike_25", "H26": "hike_50plus",
                 "C25": "cut_25", "C26": "cut_50plus"}

_POLY_CHANGE = re.compile(
    r"will the fed (?P<dir>increase|decrease) interest rates by "
    r"(?P<bps>25|50)(?P<plus>\+)? bps after the "
    r"(?P<month>[a-z]+) (?P<year>\d{4}) meeting", re.IGNORECASE)

_POLY_NOCHANGE = re.compile(
    r"will there be no change in fed interest rates after the "
    r"(?P<month>[a-z]+) (?P<year>\d{4}) meeting", re.IGNORECASE)


def parse_kalshi(row: dict) -> tuple[str, str, str] | None:
    """(family, meeting 'YYYY-MM', class) or None if not in a V1 family."""
    m = _KALSHI_FED.match(row.get("ticker") or "")
    if not m:
        return None
    mon = _MONTHS.get(m.group("mon"))
    if mon is None:
        return None
    return ("FED_DECISION", f"20{m.group('yy')}-{mon:02d}",
            _KALSHI_CLASS[m.group("act")])


def parse_polymarket(row: dict) -> tuple[str, str, str] | None:
    title = row.get("title") or ""
    m = _POLY_NOCHANGE.search(title)
    if m:
        klass = "maintain"
    else:
        m = _POLY_CHANGE.search(title)
        if not m:
            return None
        bps, plus = m.group("bps"), bool(m.group("plus"))
        if bps == "25" and not plus:
            klass = ("hike_25" if m.group("dir").lower() == "increase"
                     else "cut_25")
        elif bps == "50" and plus:
            klass = ("hike_50plus" if m.group("dir").lower() == "increase"
                     else "cut_50plus")
        else:
            # "50 bps" exact or "25+ bps" have no Kalshi twin in V1 —
            # refusing beats inventing an equivalence.
            return None
    mon = _MONTH_NAMES.get(m.group("month").lower())
    if mon is None:
        return None
    return ("FED_DECISION", f"{m.group('year')}-{mon:02d}", klass)


def _load_rows(day: str, source: str) -> list[dict]:
    p = (config.PREDICTION_MARKET_DIR / "snapshots"
         / f"{day}.{source}.jsonl")
    if not p.exists():
        return []
    out = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def _index(rows: list[dict], parse) -> tuple[dict, list[dict]]:
    """key -> row, plus refusals for ambiguous keys (2+ contracts, 1 key).

    An ambiguous key is REFUSED entirely — picking one of two contracts that
    both claim the same event would let listing quirks choose the price.
    """
    grouped: dict = {}
    for r in rows:
        key = parse(r)
        if key is not None:
            grouped.setdefault(key, []).append(r)
    by_key, refusals = {}, []
    for key, rs in grouped.items():
        if len(rs) == 1:
            by_key[key] = rs[0]
        else:
            refusals.append({
                "key": list(key),
                "reason": "ambiguous — multiple contracts share this key",
                "tickers": [r.get("ticker") for r in rs]})
    return by_key, refusals


def _days_locked(day: str, *close_times: str | None) -> int | None:
    """Calendar days from the snapshot day to the LATEST leg close (capital
    stays committed until the last leg resolves). None if no close is known."""
    from datetime import date, datetime

    latest = None
    for ct in close_times:
        if not ct:
            continue
        try:
            d = datetime.fromisoformat(str(ct).replace("Z", "+00:00")).date()
        except ValueError:
            continue
        latest = d if latest is None or d > latest else latest
    if latest is None:
        return None
    try:
        held = (latest - date.fromisoformat(day)).days
    except ValueError:
        return None
    return max(held, 1)


def _kalshi_fee(p: float) -> float:
    return KALSHI_TAKER_COEF * p * (1.0 - p)


def _poly_fee(p: float, rate: float | None) -> float:
    r = rate if rate is not None else POLYMARKET_TAKER_FALLBACK
    return r * min(p, 1.0 - p)


def executable_edge(kr: dict, pr: dict, day: str) -> dict:
    """Locked-profit arithmetic for one matched pair, TOP-OF-BOOK ONLY.

    GPT-review correction adopted (ADJUDICATION 2026-08-22): |mid−mid| is
    price disagreement, not arbitrage. The executable quantity is: buy YES at
    the cheap venue's ask + buy NO at the expensive venue (= 1 − its bid),
    pocket $1 at resolution. Gross locked edge = bid_high − ask_low; net
    subtracts both venues' declared taker fees; ROIC annualizes over the
    capital-lock period. Reported, never deciding; depth is NOT captured, so
    fillability beyond one top-of-book contract is UNKNOWN — this measures
    whether edge exists, not capacity.
    """
    kb, ka = kr.get("yes_bid"), kr.get("yes_ask")
    pb, pa = pr.get("yes_bid"), pr.get("yes_ask")
    if None in (kb, ka, pb, pa):
        return {"verdict": "REFUSED_NO_BOOK",
                "reason": "need two-sided books on BOTH venues"}
    # Direction 1: YES on Kalshi at ka, NO on Polymarket at (1 − pb).
    # Direction 2: YES on Polymarket at pa, NO on Kalshi at (1 − kb).
    candidates = []
    rate = pr.get("fee_rate")
    d1_gross = pb - ka
    candidates.append({
        "direction": "yes_kalshi/no_polymarket", "gross": d1_gross,
        "capital": ka + (1.0 - pb),
        "fees": _kalshi_fee(ka) + _poly_fee(1.0 - pb, rate)})
    d2_gross = kb - pa
    candidates.append({
        "direction": "yes_polymarket/no_kalshi", "gross": d2_gross,
        "capital": pa + (1.0 - kb),
        "fees": _kalshi_fee(1.0 - kb) + _poly_fee(pa, rate)})
    best = max(candidates, key=lambda c: c["gross"] - c["fees"])
    net = best["gross"] - best["fees"]
    out = {
        "verdict": "MEASURED",
        "direction": best["direction"],
        "gross_locked": round(best["gross"], 4),
        "fees": round(best["fees"], 4),
        "net_locked": round(net, 4),
        "capital_per_dollar_payout": round(best["capital"], 4),
        "note": "top-of-book only — no depth, fillability unknown",
    }
    days = _days_locked(day, kr.get("close_time"), pr.get("close_time"))
    if days is not None:
        out["days_locked"] = days
        if net > 0 and best["capital"] > 0:
            out["annualized_roic"] = round(
                (net / best["capital"]) * (365.0 / days), 4)
    return out


def match_day(day: str) -> dict:
    """Pair the two venues' snapshots for one day. Reads disk only."""
    kalshi = _load_rows(day, "kalshi")
    poly = _load_rows(day, "polymarket")
    if not kalshi or not poly:
        return {"status": "OK_EMPTY", "day": day, "banner": BANNER,
                "spec": MATCHING_SPEC_VERSION,
                "reason": (f"snapshots present: kalshi={bool(kalshi)} "
                           f"polymarket={bool(poly)} — a pair needs both")}

    k_idx, k_ref = _index(kalshi, parse_kalshi)
    p_idx, p_ref = _index(poly, parse_polymarket)

    pairs, unpaired = [], []
    for key in sorted(set(k_idx) & set(p_idx)):
        kr, pr = k_idx[key], p_idx[key]
        mid_k, mid_p = kr.get("mid"), pr.get("mid")
        row = {"family": key[0], "meeting": key[1], "action_class": key[2],
               "kalshi_ticker": kr.get("ticker"),
               "polymarket_ticker": pr.get("ticker"),
               "mid_kalshi": mid_k, "mid_polymarket": mid_p}
        if mid_k is None or mid_p is None:
            row["verdict"] = "REFUSED_NO_MID"
            row["reason"] = "one venue has a one-sided book — no mid to compare"
        else:
            d = round(abs(mid_k - mid_p), 4)
            row["abs_divergence"] = d
            row["above_cost_bar"] = d > COST_BAR
            row["verdict"] = "MEASURED"
        # Reported beside the frozen trial metric, never deciding it.
        row["executable"] = executable_edge(kr, pr, day)
        pairs.append(row)
    for key in sorted(set(k_idx) ^ set(p_idx)):
        unpaired.append({"key": list(key),
                         "only_on": "kalshi" if key in k_idx else "polymarket"})

    measured = [p for p in pairs if p["verdict"] == "MEASURED"]
    return {
        "status": "ok",
        "day": day,
        "banner": BANNER,
        "spec": MATCHING_SPEC_VERSION,
        "cost_bar": COST_BAR,
        "n_pairs": len(pairs),
        "n_measured": len(measured),
        "n_above_cost_bar": sum(p["above_cost_bar"] for p in measured),
        "n_executable_net_positive": sum(
            1 for p in pairs
            if p.get("executable", {}).get("verdict") == "MEASURED"
            and p["executable"]["net_locked"] > 0),
        "note": ("same-day divergence only — the trial's deciding metric "
                 "additionally requires persistence to the NEXT daily "
                 "snapshot, not assessed here"),
        "pairs": pairs,
        "refused": k_ref + p_ref,
        "n_unpaired_keys": len(unpaired),
        "unpaired": unpaired[:20],
    }


def latest_divergence() -> dict:
    """The newest day both venues have a snapshot for."""
    d = config.PREDICTION_MARKET_DIR / "snapshots"
    if not d.exists():
        return {"status": "OK_EMPTY", "banner": BANNER,
                "spec": MATCHING_SPEC_VERSION,
                "reason": "no snapshots yet"}
    days_k = {f.stem.split(".")[0] for f in d.glob("*.kalshi.jsonl")}
    days_p = {f.stem.split(".")[0] for f in d.glob("*.polymarket.jsonl")}
    both = sorted(days_k & days_p)
    if not both:
        return {"status": "OK_EMPTY", "banner": BANNER,
                "spec": MATCHING_SPEC_VERSION,
                "reason": "no day has snapshots from BOTH venues yet"}
    return match_day(both[-1])
