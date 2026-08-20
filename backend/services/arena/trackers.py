"""Universe-wide trackers: what happened today that the watchlist cannot see.

WHY THESE ARE CONTEXT AND NOT SCORES
====================================
Every feature here is short-horizon price/volume state — abnormal moves,
volume spikes, gaps, 52-week position. Two independent reasons they do NOT
enter `arena_composite`:

1. **The evidence says the obvious sign is wrong.** Two Holm-surviving
   results (2026-08-19) found short-horizon winner-chasing is an ANTI-signal
   at stock, factor and streak level (`streak_up5` −0.366%/21d; last-month
   factor chasing −2.1/−2.6%/yr). Adding `ret_5d_z` to a composite with a
   positive weight would contradict a confirmed finding in the same repo.
2. **Cheap coverage is not diverse coverage.** FEATURE-COVERAGE-AUDIT-1's
   redundancy sweep: at ρ≈0.75, which is where price-derived features sit
   relative to the momentum already in the composite, widening coverage buys
   +0.086 in latent-skill units against +0.355 at ρ=0.2. These features are
   near-copies of what is there. Piling them into the score would inflate
   `coverage_n` while adding almost no information — and the coverage-
   normalized composite would correctly refuse to reward it, so the work
   would be wasted twice.

So trackers do two things the composite cannot:

  DISCOVERY  an observation can pull a ticker INTO the candidate set that the
             static watchlist never contained. That axis is not priced by the
             coverage audit at all (it holds the universe fixed at 180), and
             it is the thing Murat has asked for repeatedly: search the
             market, do not re-rank the same list.
  CONTEXT    observations are frozen into the day state and handed to the
             daily belief review, so the LLM reasons about what happened
             rather than about a bare price level.

Everything is computed from the injected price panel, from bars at or before
the decision day. There is no lookahead here because there is no source here
other than history.
"""

from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)

#: Windows (in sessions) for the abnormal-move tracker.
MOVE_WINDOWS = (1, 5, 21, 63)

#: An observation fires when |cross-sectional z| clears this.
Z_THRESHOLD = 2.0

#: Volume spike: log(today's dollar volume / trailing median) above this.
DVOL_LOG_THRESHOLD = 1.0        # ~2.7x normal

GAP_THRESHOLD = 0.05            # 5% overnight

DRAWDOWN_THRESHOLD = -0.30      # 30% off the 52-week high

OBSERVATION_KINDS = (
    "ABNORMAL_MOVE_UP", "ABNORMAL_MOVE_DOWN", "VOLUME_SPIKE", "GAP_UP",
    "GAP_DOWN", "NEAR_52W_HIGH", "DEEP_DRAWDOWN", "VOL_REGIME_SHIFT",
)

#: The features every tracked name carries into the frozen state. Named here
#: so a reader can tell CONTEXT fields from SCORE fields without guessing:
#: nothing in this tuple may appear in `discovery.COMPOSITE_WEIGHTS`.
CONTEXT_FEATURES = (
    "ret_1", "ret_5", "ret_21", "ret_63", "dvol_log_ratio", "gap",
    "pct_off_52w_high", "vol_ratio_21_63", "dollar_volume",
)


def _ret(closes: list[float], n: int) -> float | None:
    if len(closes) < n + 1 or not closes[-(n + 1)]:
        return None
    return closes[-1] / closes[-(n + 1)] - 1.0


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2.0


def _vol(closes: list[float], n: int) -> float | None:
    if len(closes) < n + 1:
        return None
    rets = [closes[i] / closes[i - 1] - 1.0
            for i in range(len(closes) - n, len(closes)) if closes[i - 1]]
    if len(rets) < 2:
        return None
    m = sum(rets) / len(rets)
    return (sum((r - m) ** 2 for r in rets) / (len(rets) - 1)) ** 0.5


def name_features(closes: list[float], volumes: list[float],
                  open_px: float | None) -> dict:
    """Pure per-name context features from trailing bars. Missing is None —
    never 0.0, which would be a fabricated in-distribution value (the C6
    lesson from `multifactor._read_pit_scores`)."""
    out: dict = {k: None for k in CONTEXT_FEATURES}
    if not closes:
        return out
    for n in MOVE_WINDOWS:
        out[f"ret_{n}"] = _ret(closes, n)
    last = closes[-1]
    if volumes:
        dv = last * volumes[-1]
        out["dollar_volume"] = dv
        med = _median([c * v for c, v in
                       zip(closes[-len(volumes):], volumes)][-63:])
        if med and dv > 0:
            import math
            out["dvol_log_ratio"] = math.log(dv / med)
    if open_px and len(closes) >= 2 and closes[-2]:
        out["gap"] = open_px / closes[-2] - 1.0
    window = closes[-252:]
    hi = max(window) if window else None
    if hi:
        out["pct_off_52w_high"] = last / hi - 1.0
    v21, v63 = _vol(closes, 21), _vol(closes, 63)
    if v21 is not None and v63:
        out["vol_ratio_21_63"] = v21 / v63
    return out


def _zscores(col: dict[str, float]) -> dict[str, float]:
    n = len(col)
    if n < 8:            # a z over a handful of names is not a z
        return {}
    m = sum(col.values()) / n
    sd = (sum((v - m) ** 2 for v in col.values()) / (n - 1)) ** 0.5
    return {t: (v - m) / sd for t, v in col.items()} if sd > 0 else {}


def observe(day: date, panel, universe: list[str]) -> dict:
    """Context features + fired observations for the whole scanned universe.

    Returns {"features": {ticker: {...}}, "observations": [...],
             "scanned_n": int, "priced_n": int}.
    """
    feats: dict[str, dict] = {}
    for t in universe:
        closes = panel.close_history(t, day, 300)
        if not closes:
            continue
        try:
            vols = panel.volume_history(t, day, 63)
        except (AttributeError, NotImplementedError):
            vols = []
        feats[t] = name_features(closes, vols, panel.open_price(t, day))

    obs: list[dict] = []
    for n in MOVE_WINDOWS:
        z = _zscores({t: f[f"ret_{n}"] for t, f in feats.items()
                      if f.get(f"ret_{n}") is not None})
        for t, v in z.items():
            feats[t][f"ret_{n}_z"] = round(v, 3)
            if abs(v) >= Z_THRESHOLD:
                obs.append({
                    "kind": ("ABNORMAL_MOVE_UP" if v > 0
                             else "ABNORMAL_MOVE_DOWN"),
                    "ticker": t, "window": n, "z": round(v, 3),
                    "value": round(feats[t][f"ret_{n}"], 5),
                    "threshold": Z_THRESHOLD})

    for t, f in feats.items():
        if (f.get("dvol_log_ratio") or 0) >= DVOL_LOG_THRESHOLD:
            obs.append({"kind": "VOLUME_SPIKE", "ticker": t,
                        "value": round(f["dvol_log_ratio"], 3),
                        "threshold": DVOL_LOG_THRESHOLD})
        g = f.get("gap")
        if g is not None and abs(g) >= GAP_THRESHOLD:
            obs.append({"kind": "GAP_UP" if g > 0 else "GAP_DOWN",
                        "ticker": t, "value": round(g, 4),
                        "threshold": GAP_THRESHOLD})
        d = f.get("pct_off_52w_high")
        if d is not None and d <= DRAWDOWN_THRESHOLD:
            obs.append({"kind": "DEEP_DRAWDOWN", "ticker": t,
                        "value": round(d, 4),
                        "threshold": DRAWDOWN_THRESHOLD})
        elif d is not None and d >= -0.02:
            obs.append({"kind": "NEAR_52W_HIGH", "ticker": t,
                        "value": round(d, 4), "threshold": -0.02})
        vr = f.get("vol_ratio_21_63")
        if vr is not None and vr >= 2.0:
            obs.append({"kind": "VOL_REGIME_SHIFT", "ticker": t,
                        "value": round(vr, 3), "threshold": 2.0})

    obs.sort(key=lambda o: (o["kind"], o["ticker"]))
    return {"features": feats, "observations": obs,
            "scanned_n": len(universe), "priced_n": len(feats),
            "by_kind": {k: sum(1 for o in obs if o["kind"] == k)
                        for k in OBSERVATION_KINDS
                        if any(o["kind"] == k for o in obs)}}


def nominations(observations: list[dict], *, core: set[str],
                max_new: int = 30) -> list[dict]:
    """Tickers a tracker says deserve a look and the core universe lacks.

    Ranked by |z|-equivalent strength so a cap truncates the weakest rather
    than an alphabetical tail, and every nomination carries the observation
    that caused it — a candidate that appears with no reason attached is a
    candidate nobody can audit later.
    """
    best: dict[str, dict] = {}
    for o in observations:
        t = o["ticker"]
        if t in core:
            continue
        strength = abs(o.get("z") if o.get("z") is not None else o["value"])
        prev = best.get(t)
        if prev is None or strength > prev["strength"]:
            best[t] = {"ticker": t, "reason": o["kind"], "observation": o,
                       "strength": round(float(strength), 4)}
    return sorted(best.values(),
                  key=lambda r: -r["strength"])[:max_new]
