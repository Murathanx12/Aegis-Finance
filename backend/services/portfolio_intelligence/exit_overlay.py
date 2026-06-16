"""
TRIAL-EXIT — ATR trailing-stop exit overlay (decision core).

The reusable mechanism the `conservative-atr` lane will apply: given a lane's
current positions and each name's price history since entry, decide which
positions the ATR Chandelier trailing stop has stopped out (→ sell to cash) and
which to hold (let the winner run). Pure wrapper over `exit_engine` — no I/O, no
lane state — so it unit-tests deterministically and the live lane can call it at
each daily check.

This is checklist item 1 of `docs/TRIALS/TRIAL-EXIT-atr-trailing-stops.md`. Items
2–4 (separate-hash lane config, attended new-inception seeding, registry) remain
the attended step — this overlay arms NOTHING on its own.
"""

from __future__ import annotations

import pandas as pd

from backend.services.exit_engine import simulate_trailing_exit, volatility_target_weight


def evaluate_exit_overlay(positions: dict, prices: dict, *, atr_period=None,
                          atr_multiple=None) -> dict:
    """Per-position exit decision under the ATR Chandelier trailing stop.

    ``positions``: {ticker: {"entry_date": iso_str|None, ...}}.
    ``prices``: {ticker: pd.Series of closes} (DatetimeIndex enables entry_date
    alignment; otherwise entry is bar 0).

    Returns {ticker: {action: "exit"|"hold", reason, bars_held, return_pct,
    max_favorable_pct, stop_level}}. A position is "exit" iff the trailing stop
    fired at/before the latest bar; otherwise "hold" (the winner runs).
    """
    out: dict = {}
    for ticker, pos in positions.items():
        s = prices.get(ticker)
        if s is None:
            out[ticker] = {"action": "hold", "reason": "no_prices"}
            continue
        s = pd.Series(s).dropna()
        if len(s) < 2:
            out[ticker] = {"action": "hold", "reason": "insufficient_data"}
            continue

        entry_index = 0
        entry_date = (pos or {}).get("entry_date")
        if entry_date is not None and isinstance(s.index, pd.DatetimeIndex):
            entry_index = int(s.index.searchsorted(pd.to_datetime(entry_date)))
            entry_index = min(max(entry_index, 0), len(s) - 1)

        res = simulate_trailing_exit(s, entry_index=entry_index,
                                     atr_period=atr_period, atr_multiple=atr_multiple)
        stopped = res.reason == "trailing_stop"
        out[ticker] = {
            "action": "exit" if stopped else "hold",
            "reason": res.reason,
            "bars_held": res.bars_held,
            "return_pct": round(res.return_pct, 4),
            "max_favorable_pct": round(res.max_favorable_pct, 4),
            "stop_level": round(res.stop_path[-1], 4) if res.stop_path else None,
        }
    return out


def vol_capped_weights(base_weights: dict, returns: dict, *, target_vol=None,
                       max_weight=None) -> dict:
    """Apply the volatility-target cap to base allocation weights, then
    renormalise to sum to the original total. A violent name is trimmed; the
    freed weight is redistributed pro-rata across the rest. (The sizing half of
    the overlay; the exit half is ``evaluate_exit_overlay``.)"""
    total = sum(base_weights.values())
    if total <= 0:
        return dict(base_weights)
    capped: dict = {}
    for t, w in base_weights.items():
        r = returns.get(t)
        if r is None:
            capped[t] = w
            continue
        cap = volatility_target_weight(pd.Series(r), target_vol=target_vol,
                                       max_weight=max_weight)
        capped[t] = min(w, cap) if cap > 0 else 0.0
    cap_total = sum(capped.values())
    if cap_total <= 0:
        return {t: 0.0 for t in base_weights}
    scale = total / cap_total
    return {t: round(w * scale, 6) for t, w in capped.items()}
