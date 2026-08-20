"""Pure policy layer: frozen day-state in, target weights + decision rows out.

No IO, no clocks, no randomness. Every exclusion carries a reason, every
selection carries its rank and score, and rejected near-misses are returned
alongside the chosen so the experience loop can label opportunity cost.

Rule provenance:
  * inverse_trailing_vol — Order 24: trailing 63d vol beat the risk model on
    all five spend routes; the cheap estimator IS the finding.
  * winner_exemption — CONVEXITY-PRESERVATION-1 (Holm-surviving): +40%
    positions exempt from trims for 60 trading days.
  * streak_up_5 / top_decile_ret21 — the two Holm-surviving anti-chase
    results (streak_up5 −0.366%/21d; last-month factor/winner chasing
    negative at stock, factor and streak level).
LLM tilts arrive here as a plain dict {ticker: factor}; producing them —
budget, ledger, grading — is perception.py's job. This layer only applies
bounded numbers deterministically. The LLM never sizes.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Selection:
    chosen: list[dict] = field(default_factory=list)     # {ticker, score, rank}
    rejected: list[dict] = field(default_factory=list)   # near-misses, with reason
    excluded: list[dict] = field(default_factory=list)   # screened/ineligible


def _eligible(names: dict, min_price: float,
              signal: str) -> tuple[dict, list[dict]]:
    ok, excluded = {}, []
    for t, row in names.items():
        if row.get("status") != "ok":
            excluded.append({"ticker": t, "reason": "no_price"})
        elif row.get("close", 0) < min_price:
            excluded.append({"ticker": t, "reason": f"price<{min_price}"})
        elif row.get("scores", {}).get(signal) is None:
            excluded.append({"ticker": t, "reason": f"no_{signal}"})
        else:
            ok[t] = row
    return ok, excluded


def _apply_screens(names: dict, screens: tuple[str, ...]) -> tuple[dict, list[dict]]:
    if not screens:
        return names, []
    out, screened = dict(names), []
    if "streak_up_5" in screens:
        for t in list(out):
            if (out[t].get("streak_up") or 0) >= 5:
                screened.append({"ticker": t, "reason": "streak_up_5",
                                 "streak": out[t].get("streak_up")})
                del out[t]
    if "top_decile_ret21" in screens:
        with_ret = [(t, r.get("ret21")) for t, r in out.items()
                    if r.get("ret21") is not None]
        if len(with_ret) >= 10:
            cutoff_i = max(1, len(with_ret) // 10)
            hot = {t for t, _ in
                   sorted(with_ret, key=lambda x: x[1], reverse=True)[:cutoff_i]}
            for t in hot:
                screened.append({"ticker": t, "reason": "top_decile_ret21",
                                 "ret21": out[t].get("ret21")})
                del out[t]
    return out, screened


def select(day_state: dict, *, top_k: int, min_price: float,
           screens: tuple[str, ...] = (), n_rejected: int = 3,
           signal: str = "arena_composite") -> Selection:
    """Rank by the declared composite; keep top_k; keep the near-misses too."""
    names = day_state.get("names", {})
    eligible, excluded = _eligible(names, min_price, signal)
    screened_pool, screened = _apply_screens(eligible, screens)
    excluded.extend(screened)
    ranked = sorted(screened_pool.items(),
                    key=lambda kv: kv[1]["scores"][signal],
                    reverse=True)
    sel = Selection(excluded=excluded)
    for i, (t, row) in enumerate(ranked[:top_k], 1):
        sel.chosen.append({"ticker": t, "rank": i,
                           "score": row["scores"][signal]})
    for i, (t, row) in enumerate(ranked[top_k:top_k + n_rejected],
                                 top_k + 1):
        sel.rejected.append({"ticker": t, "rank": i,
                             "score": row["scores"][signal],
                             "reason": "below_rank_cutoff"})
    return sel


def size(chosen: list[dict], day_state: dict, *, sizing: str,
         max_single_name: float) -> dict[str, float]:
    """Weights for the chosen set. Missing vol under inverse-vol sizing makes
    a name ineligible for that book (missing is missing, never 'average')."""
    names = day_state.get("names", {})
    weights: dict[str, float] = {}
    if sizing == "inverse_trailing_vol":
        inv = {}
        for c in chosen:
            v = names.get(c["ticker"], {}).get("vol63")
            if v and v > 0:
                inv[c["ticker"]] = 1.0 / v
        total = sum(inv.values())
        if total > 0:
            weights = {t: w / total for t, w in inv.items()}
    if not weights:  # equal_weight, or inverse-vol with nothing usable
        n = len(chosen)
        weights = {c["ticker"]: 1.0 / n for c in chosen} if n else {}
    return _cap_and_renorm(weights, max_single_name)


def _cap_and_renorm(weights: dict[str, float], cap: float) -> dict[str, float]:
    if not weights:
        return {}
    w = dict(weights)
    for _ in range(10):
        over = {t: v for t, v in w.items() if v > cap + 1e-9}
        if not over:
            break
        spare = sum(v - cap for v in over.values())
        under = {t: v for t, v in w.items() if v <= cap + 1e-9}
        for t in over:
            w[t] = cap
        s_under = sum(under.values())
        if s_under <= 0:
            break
        for t in under:
            w[t] += spare * under[t] / s_under
    total = sum(w.values())
    return {t: v / total for t, v in w.items()} if total else {}


def apply_llm_tilts(weights: dict[str, float], tilts: dict[str, float],
                    *, tilt_cap: float, max_single_name: float) -> dict[str, float]:
    """Deterministic mapper: multiply each weight by clip(factor) and
    renormalize. `tilts` values are multiplicative factors around 1.0."""
    if not tilts:
        return weights
    lo, hi = 1.0 - tilt_cap, 1.0 + tilt_cap
    w = {t: v * min(max(tilts.get(t, 1.0), lo), hi)
         for t, v in weights.items()}
    return _cap_and_renorm(w, max_single_name)


def apply_winner_exemption(target: dict[str, float], positions: dict,
                           day_state: dict, session_index: int, *,
                           gain_threshold_pct: float,
                           exempt_trading_days: int) -> tuple[dict[str, float], list[dict]]:
    """A position up >= threshold since entry keeps at least its CURRENT weight
    for `exempt_trading_days` sessions after first crossing — the rebalance may
    not trim or evict it. Returns (adjusted weights, exemption receipts)."""
    names = day_state.get("names", {})
    nav_weights = _current_weights(positions, names)
    receipts: list[dict] = []
    out = dict(target)
    for t, pos in (positions.get("positions") or {}).items():
        row = names.get(t, {})
        px = row.get("close")
        basis = pos.get("cost_basis")
        if not px or not basis:
            continue
        gain_pct = (px / basis - 1.0) * 100.0
        crossed = pos.get("exempt_since_session")
        if gain_pct >= gain_threshold_pct and crossed is None:
            crossed = session_index  # first crossing observed today
        active = (crossed is not None
                  and session_index - crossed < exempt_trading_days)
        if not active:
            continue
        cur = nav_weights.get(t, 0.0)
        if out.get(t, 0.0) < cur:
            receipts.append({"ticker": t, "rule": "winner_exemption",
                             "gain_pct": round(gain_pct, 2),
                             "kept_weight": round(cur, 4),
                             "target_was": round(out.get(t, 0.0), 4),
                             "exempt_since_session": crossed})
            out[t] = cur
    total = sum(out.values())
    if total > 0:
        out = {t: v / total for t, v in out.items()}
    return out, receipts


def _current_weights(positions: dict, names: dict) -> dict[str, float]:
    vals = {}
    for t, pos in (positions.get("positions") or {}).items():
        px = names.get(t, {}).get("close")
        if px:
            vals[t] = pos.get("shares", 0.0) * px
    total = sum(vals.values()) + (positions.get("cash") or 0.0)
    return {t: v / total for t, v in vals.items()} if total > 0 else {}


def substitution_check(positions: dict, sel: Selection, day_state: dict, *,
                       margin_z: float, round_trip_cost: float = 0.0,
                       signal: str = "arena_composite") -> dict | None:
    """Daily capital substitution: is the best non-held candidate better than
    the weakest holding by a clear score margin?

    Scores are composite z-scores, so `margin_z` is in score units. The cost
    of the round trip is paid at the fill and reported there; it is NOT
    netted against a z-score here — the two are not in the same units, and
    pretending otherwise would be arithmetic against the wrong world.
    """
    held = set((positions.get("positions") or {}).keys())
    names = day_state.get("names", {})
    held_scored = [(t, names.get(t, {}).get("scores", {}).get(signal))
                   for t in held]
    held_scored = [(t, s) for t, s in held_scored if s is not None]
    candidates = [c for c in sel.chosen if c["ticker"] not in held]
    if not held_scored or not candidates:
        return None
    weakest_t, weakest_s = min(held_scored, key=lambda x: x[1])
    best = max(candidates, key=lambda c: c["score"])
    if best["score"] - weakest_s >= margin_z:
        return {"sell": weakest_t, "buy": best["ticker"],
                "score_gap": round(best["score"] - weakest_s, 4),
                "margin_z": margin_z}
    return None


# ── orders ──────────────────────────────────────────────────────────────────
def orders_from_targets(positions: dict, target: dict[str, float],
                        day_state: dict, *, cost_bps: float,
                        slippage_bps: float, min_trade_usd: float = 200.0
                        ) -> list[dict]:
    """Diff current book against target weights at today's closes.

    Orders are QUEUED for the next session's open — nothing fills at the price
    that produced the decision. Tiny rebalance dust below `min_trade_usd` is
    skipped so costs are not paid to move nothing.
    """
    names = day_state.get("names", {})
    cash = positions.get("cash") or 0.0
    held = positions.get("positions") or {}
    nav = cash + sum(p.get("shares", 0.0) * (names.get(t, {}).get("close") or 0)
                     for t, p in held.items())
    if nav <= 0:
        return []
    orders = []
    # Buys are scaled down by the cost rate so paying the fill's cost cannot
    # push cash below zero — a paper book quietly on margin is a wrong world.
    buffer = 1.0 - (cost_bps + slippage_bps) / 10_000.0
    tickers = set(held) | set(target)
    for t in sorted(tickers):
        px = names.get(t, {}).get("close")
        if not px:
            continue  # unpriceable today; the position is carried, not traded
        cur_usd = held.get(t, {}).get("shares", 0.0) * px
        tgt_usd = target.get(t, 0.0) * nav * buffer
        delta = tgt_usd - cur_usd
        if abs(delta) < min_trade_usd:
            continue
        orders.append({"ticker": t, "side": "buy" if delta > 0 else "sell",
                       "usd": round(abs(delta), 2),
                       "decision_close": px,
                       "cost_bps": cost_bps, "slippage_bps": slippage_bps,
                       "status": "queued"})
    return orders
