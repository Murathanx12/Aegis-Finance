"""INTERNET-INVESTIGATOR-FWD-1 — which securities get investigated tonight.

Pre-registration: `Aegis module/TRIALS/PREREG_INTERNET_INVESTIGATOR_FWD_1.md`.
Frozen weights: `Aegis module/scripts/iif1_config.py:TRIGGER_WEIGHTS`.

WHY SPARSE TRIGGERS AT ALL
==========================
SWARM-1 asked for an opinion on every security every night. A model required to
have a view on 459 tickers will manufacture 459 views, and NIGHT-14 measured the
result: 0.49 effective distinct ideas across fourteen specialists. Forcing
opinions is how you get opinions that mean nothing.

So the expensive reasoning wakes on UNUSUAL states — abnormal move, abnormal
volume, an imminent earnings date, a fresh filing — and stays asleep otherwise.
The bet is that the LLM's real advantage, if it has one, is recognising rare
situations rather than forecasting ordinary noise.

THE PROPERTY THAT MAKES THE TRIAL PAIRED
----------------------------------------
**The same 40 names go to every arm.** The trigger score is computed once, from
numerical point-in-time data, and the resulting list is handed to all five arms
unchanged.

This is not a convenience. If each arm chose its own names, the arms would be
forecasting different cells, the paired Brier difference would no longer cancel
the "what did the market do tonight" term, and the trial would need orders of
magnitude more nights to say anything. It would also stop being a clean
comparison — an arm could look better by picking easier names.

**The trigger rule therefore contains NO model output.** If it did, the arms
would diverge the moment one of them reasoned differently, and the pairing would
be gone. This is checked at runtime and pinned by a test.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

#: Frozen in `iif1_config.py`. Duplicated here as the runtime copy; the test
#: suite asserts the two agree so a drift cannot go unnoticed.
TRIGGER_WEIGHTS: dict[str, float] = {
    "abs_resid_return_z_1d": 1.0,
    "volume_z_20d": 1.0,
    "earnings_within_5d": 1.5,
    "filing_within_2d": 1.0,
}

TRIGGERS_PER_NIGHT = 40
MIN_PRICE = 5.0
MIN_DOLLAR_VOLUME_20D = 5_000_000.0

#: A z-score is clipped before it enters the composite. One security with a
#: 40-sigma print (a bad tick, a split not yet adjusted) would otherwise take
#: every slot on the list and the night would investigate one data error.
Z_CLIP = 6.0


@dataclass
class TriggerCandidate:
    """One security's unusualness, and what it was made of."""
    ticker: str
    score: float
    components: dict[str, float] = field(default_factory=dict)
    eligible: bool = True
    reason: str = ""

    def as_row(self) -> dict:
        return {"ticker": self.ticker, "score": round(self.score, 4),
                "components": {k: round(v, 4)
                               for k, v in self.components.items()},
                "eligible": self.eligible, "reason": self.reason}


def _num(v: Any) -> float | None:
    """A number, or None. Never a zero-default.

    A missing feature silently read as 0.0 is a security that looks calm because
    we failed to measure it — the same shape as reporting a throttled news feed
    as 'quiet'. Missing components are counted and disclosed instead.
    """
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def score_candidate(ticker: str, feats: dict) -> TriggerCandidate:
    """Composite unusualness from point-in-time numerical features only.

    `feats` keys, all optional and all disclosed when absent:
        abs_resid_return_z_1d  |z| of the 1-day market-residual return
        volume_z_20d           z of today's volume against its 20-day history
        earnings_within_5d     bool
        filing_within_2d       bool
        price                  last close, for the liquidity floor
        dollar_volume_20d      20-day average dollar volume
    """
    comps: dict[str, float] = {}
    missing: list[str] = []
    for key, w in TRIGGER_WEIGHTS.items():
        raw = feats.get(key)
        if isinstance(raw, bool):
            val = 1.0 if raw else 0.0
        else:
            n = _num(raw)
            if n is None:
                missing.append(key)
                continue
            val = min(abs(n), Z_CLIP)
        comps[key] = w * val

    price = _num(feats.get("price"))
    dv = _num(feats.get("dollar_volume_20d"))
    eligible, reason = True, ""
    if price is not None and price < MIN_PRICE:
        eligible, reason = False, f"price {price:.2f} < {MIN_PRICE}"
    elif dv is not None and dv < MIN_DOLLAR_VOLUME_20D:
        eligible, reason = False, f"dollar volume {dv:,.0f} below floor"
    elif len(missing) == len(TRIGGER_WEIGHTS):
        # Every component missing is not a calm security, it is an unmeasured
        # one, and ranking it at zero would quietly park it at the bottom of
        # the list forever.
        eligible, reason = False, "no trigger features available"
    elif missing:
        reason = f"missing: {','.join(missing)}"

    return TriggerCandidate(ticker=ticker, score=sum(comps.values()),
                            components=comps, eligible=eligible, reason=reason)


def select_triggers(features_by_ticker: dict[str, dict], *,
                    k: int = TRIGGERS_PER_NIGHT,
                    as_of: date | None = None) -> dict:
    """The night's list. Same list for every arm.

    Ties are broken by ticker so the selection is deterministic: two runs of the
    same night must produce the same cells or the arms are not comparable across
    a restart.
    """
    cands = [score_candidate(t, f or {})
             for t, f in sorted(features_by_ticker.items())]
    eligible = [c for c in cands if c.eligible]
    chosen = sorted(eligible, key=lambda c: (-c.score, c.ticker))[:k]
    return {
        "as_of": str(as_of or date.today()),
        "k_requested": k,
        "n_universe": len(cands),
        "n_eligible": len(eligible),
        "n_selected": len(chosen),
        "n_excluded": len(cands) - len(eligible),
        # Short of k is DISCLOSED, never padded. Padding with the next-most-
        # ordinary names would quietly change what "triggered" means on exactly
        # the nights when nothing was unusual — and those nights are
        # informative.
        "short_of_k": len(chosen) < k,
        "tickers": [c.ticker for c in chosen],
        "selected": [c.as_row() for c in chosen],
        "excluded": [c.as_row() for c in cands if not c.eligible][:50],
        "weights": dict(TRIGGER_WEIGHTS),
    }


def assert_arms_share_cells(per_arm_tickers: dict[str, list[str]]) -> None:
    """Runtime guard: every arm must have been handed the identical cell set.

    Raises rather than warns. A divergence here does not degrade the trial, it
    invalidates it — the paired statistic silently stops being paired, and the
    resulting number would look like a result rather than like a bug.
    """
    if not per_arm_tickers:
        return
    ref_arm, ref = next(iter(per_arm_tickers.items()))
    ref_set = set(ref)
    for arm, tickers in per_arm_tickers.items():
        if set(tickers) != ref_set:
            missing = ref_set - set(tickers)
            extra = set(tickers) - ref_set
            raise ValueError(
                f"arm {arm!r} did not receive the same cells as {ref_arm!r}: "
                f"missing {sorted(missing)[:5]}, extra {sorted(extra)[:5]}. "
                f"The paired Brier statistic requires identical cells; this "
                f"night is VOID rather than reportable.")
