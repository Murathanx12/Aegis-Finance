"""Fit the price table to what the PROVIDER's balance says, and compare a run's
telemetry against a bracketing pair of balance reads.

WHY (2026-09-27)
================
A thesis-card run moved the DeepSeek balance $0.05 for 4 OpenClaw quests + 2
synth calls, while OpenClaw's own `costUsd` said ~$0.29 and our telemetry (the
table in `config.LLM_PRICE_PER_MTOK` applied to the reported tokens) said
~$0.22. Both rulers over-stated the provider 4-6x, because DeepSeek has
answered `usage.model = deepseek-flash` since 2026-09-14 and that row was
carried from the 2026-09-05 v4-flash derivation, never measured.

The 09-05 derivation (`scripts/c6b_deepseek_price_derivation.py`) solved two
legs from two balance windows of opposite in/out mix. A calibration batch run
through ONE route has ONE mix, so this module fits what one mix can identify:

* 1 window (or a singular set)   -> a SCALAR on the prior table's leg shape
                                    (`scalar_on_prior_shape`); the per-leg
                                    prices are that scalar x the prior legs.
* >= 3 windows, well conditioned -> all three legs by least squares
                                    (`three_leg_least_squares`).

THE BALANCE IS QUOTED TO THE CENT. Each window's delta is uncertain by one
granularity step (two reads, each within half a cent), so every fit carries a
bracket: the prices at delta +/- granularity. A total delta below
`LLM_PRICE_CALIBRATION_MIN_DELTA_USD` reports `TOO_COARSE` -- a point estimate
is still printed, and `adoptable` is False.

No exception class: every outcome is a status on the returned dict, because
the caller writes a receipt either way.
"""
from __future__ import annotations

import itertools
import math
from datetime import date, datetime, timezone
from typing import Any, Iterable

import numpy as np

STATUS_OK = "OK"
STATUS_TOO_COARSE = "TOO_COARSE"
STATUS_NO_WINDOW = "NO_WINDOW"
STATUS_NO_TOKENS = "NO_TOKENS"
STATUS_TOPUP_IN_WINDOW = "TOPUP_IN_WINDOW"

METHOD_SCALAR = "scalar_on_prior_shape"
METHOD_LEGS = "three_leg_least_squares"

LEGS = ("in", "cached_in", "out")


def _cfg(name: str, default: Any) -> Any:
    try:
        from backend import config as C
        return getattr(C, name, default)
    except Exception:                                              # noqa: BLE001
        return default


def _tokens(w: dict) -> np.ndarray:
    """(uncached input, cached input, output) in MILLIONS of tokens."""
    return np.array([float(w.get("tokens_in") or 0), float(w.get("cached_tokens") or 0),
                     float(w.get("tokens_out") or 0)]) / 1e6


def _target_delta(w: dict) -> float:
    """The window's balance delta less the cost of rows priced by OTHER table
    rows (e.g. a synth call ledgered as `deepseek-chat`), which are an offset,
    not part of what is being fitted."""
    return float(w["delta_usd"]) - float(w.get("offset_usd") or 0.0)


def _fit_scalar(windows: list[dict], prior: dict, deltas: list[float]) -> dict:
    p = np.array([float(prior[k]) for k in LEGS])
    table_cost = float(sum(_tokens(w) @ p for w in windows))
    k = sum(deltas) / table_cost
    return {"k": k, "table_cost_usd": table_cost,
            "prices": {leg: float(p[i] * k) for i, leg in enumerate(LEGS)}}


def _fit_legs(windows: list[dict], deltas: list[float]) -> dict:
    A = np.vstack([_tokens(w) for w in windows])
    x, *_ = np.linalg.lstsq(A, np.array(deltas), rcond=None)
    return {"prices": {leg: float(x[i]) for i, leg in enumerate(LEGS)}}


def fit_prices(windows: list[dict], prior: dict, *, granularity: float | None = None,
               min_delta: float | None = None, max_condition: float = 30.0) -> dict:
    """Fit $/1M tokens for one model from balance windows.

    Each window: {"delta_usd", "tokens_in" (uncached), "cached_tokens",
    "tokens_out", optional "offset_usd", "n_calls"}. `prior` is the table row
    {"in", "cached_in", "out"} whose SHAPE the scalar fit keeps.
    """
    g = float(granularity if granularity is not None
              else _cfg("DEEPSEEK_BALANCE_GRANULARITY_USD", 0.01))
    lo_ok = float(min_delta if min_delta is not None
                  else _cfg("LLM_PRICE_CALIBRATION_MIN_DELTA_USD", 0.05))
    out: dict[str, Any] = {"n_windows": len(windows), "granularity_usd": g,
                           "min_delta_usd": lo_ok, "prior": dict(prior)}
    if not windows:
        return {**out, "status": STATUS_NO_WINDOW, "adoptable": False,
                "why": "no balance window"}
    if any(float(w["delta_usd"]) < 0 for w in windows):
        return {**out, "status": STATUS_TOPUP_IN_WINDOW, "adoptable": False,
                "why": "a window's balance went UP: a top-up landed inside it"}
    if any(not _tokens(w).any() for w in windows):
        return {**out, "status": STATUS_NO_TOKENS, "adoptable": False,
                "why": "a window charged money and the ledger saw no tokens"}
    deltas = [_target_delta(w) for w in windows]
    total = float(sum(float(w["delta_usd"]) for w in windows))
    A = np.vstack([_tokens(w) for w in windows])
    # Column-scaled: cached counts run 30x the others, and an unscaled
    # condition number would call a perfectly identified system singular.
    if len(windows) >= 3:
        norms = np.linalg.norm(A, axis=0)
        cond = (float(np.linalg.cond(A / np.where(norms > 0, norms, 1.0)))
                if (norms > 0).all() else math.inf)
    else:
        cond = math.inf
    method = METHOD_LEGS if (len(windows) >= 3 and cond <= max_condition) else METHOD_SCALAR
    fit = _fit_legs(windows, deltas) if method == METHOD_LEGS else _fit_scalar(windows, prior, deltas)
    # Bracket: every corner of delta +/- g per window (<= 2^6 corners).
    corners = []
    for signs in itertools.product((-1.0, 1.0), repeat=min(len(windows), 6)):
        d = [x + s * g for x, s in zip(deltas, signs)] + deltas[len(signs):]
        d = [max(0.0, x) for x in d]
        f = (_fit_legs(windows, d) if method == METHOD_LEGS
             else _fit_scalar(windows, prior, d))
        corners.append(f["prices"])
    bracket = {leg: [round(min(c[leg] for c in corners), 8),
                     round(max(c[leg] for c in corners), 8)] for leg in LEGS}
    status = STATUS_OK if total >= lo_ok else STATUS_TOO_COARSE
    res = {**out, "status": status, "method": method,
           "condition_number": None if math.isinf(cond) else round(cond, 4),
           "delta_total_usd": round(total, 6),
           "fitted_usd_per_mtok": {k: round(v, 8) for k, v in fit["prices"].items()},
           "bracket_usd_per_mtok": bracket,
           "relative_uncertainty": round(g * len(windows) / total, 4) if total > 0 else None,
           "adoptable": status == STATUS_OK and all(v > 0 for v in fit["prices"].values())}
    if method == METHOD_SCALAR:
        res["k_vs_prior"] = round(fit["k"], 6)
        res["k_bracket"] = [round(min(c["out"] for c in corners) / float(prior["out"]), 6),
                            round(max(c["out"] for c in corners) / float(prior["out"]), 6)]
        res["prior_table_cost_usd"] = round(fit["table_cost_usd"], 6)
        res["identified"] = ("ONE equation: the level on this route's mix. The per-leg "
                             "split is the prior table's shape, NOT measured.")
    if status == STATUS_TOO_COARSE:
        res["why"] = (f"total delta ${total:.2f} < ${lo_ok:.2f}: at ${g:.2f} balance "
                      f"granularity the estimate is too coarse -- widen the batch")
    return res


# ─────────────────────── windows from snapshots + ledger ─────────────────────

def _instant(v: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def deepseek_rows_between(rows: Iterable[dict], start: Any, end: Any) -> list[dict]:
    a, b = _instant(start), _instant(end)
    out = []
    for r in rows:
        if str(r.get("provider") or "") != "deepseek":
            continue
        t = _instant(r.get("ts"))
        if t is not None and a is not None and b is not None and a <= t <= b:
            out.append(r)
    return out


def window_from_rows(rows: list[dict], *, delta_usd: float, model: str) -> dict:
    """Aggregate a window's DeepSeek rows: tokens of `model` are fitted, every
    other DeepSeek row is priced at its own table row and becomes the offset."""
    from backend.services import llm_telemetry as LT
    w = {"delta_usd": float(delta_usd), "tokens_in": 0, "cached_tokens": 0,
         "tokens_out": 0, "offset_usd": 0.0, "n_calls": 0, "n_offset_calls": 0,
         "n_unpriced_calls": 0, "offset_models": {}}
    for r in rows:
        if str(r.get("model") or "") == model:
            w["n_calls"] += 1
            w["tokens_in"] += int(r.get("tokens_in") or 0)
            w["cached_tokens"] += int(r.get("cached_tokens") or 0)
            w["tokens_out"] += int(r.get("tokens_out") or 0)
            if not (r.get("tokens_in") or r.get("tokens_out")):
                w["n_unpriced_calls"] += 1     # a call whose tokens never came back
        else:
            c = LT.row_cost(r)
            w["n_offset_calls"] += 1
            w["offset_usd"] += float(c or 0.0)
            m = str(r.get("model"))
            w["offset_models"][m] = w["offset_models"].get(m, 0) + 1
    w["offset_usd"] = round(w["offset_usd"], 8)
    return w


# ───────────────────── the provider line on a run receipt ────────────────────

def calibration_age_days(today: Any = None) -> int | None:
    cal = _cfg("LLM_PRICE_CALIBRATION", {}) or {}
    on = cal.get("calibrated_on")
    if not on:
        return None
    t = today or datetime.now(timezone.utc).date()
    if isinstance(t, datetime):
        t = t.date()
    return (t - date.fromisoformat(str(on)[:10])).days


def bracketing_pair(snaps: list[dict], start: Any, end: Any) -> tuple[dict, dict] | None:
    """The last read at or before `start` and the first at or after `end`."""
    a, b = _instant(start), _instant(end)
    if a is None or b is None:
        return None
    before = [s for s in snaps if (_instant(s.get("read_at")) or b) <= a]
    after = [s for s in snaps if (_instant(s.get("read_at")) or a) >= b]
    if not before or not after:
        return None
    return (max(before, key=lambda s: str(s["read_at"])),
            min(after, key=lambda s: str(s["read_at"])))


def provider_delta_line(start: Any, end: Any, *, snaps: list[dict] | None = None,
                        rows: list[dict] | None = None, today: Any = None,
                        warn_at: float | None = None) -> dict:
    """The receipt's THIRD spend line: the provider's own balance delta over a
    snapshot pair that brackets [start, end], against ALL DeepSeek telemetry in
    that same pair's window (the balance is account-wide, so the comparison
    must be too). A disagreement above `warn_at` is a WARNING carrying the
    calibration's age -- never a refusal: the balance moves in whole cents."""
    warn_at = float(warn_at if warn_at is not None
                    else _cfg("LLM_PROVIDER_DISAGREE_WARN", 0.25))
    if snaps is None:
        from backend.services import deepseek_balance as DB
        snaps = DB.snapshots()
    pair = bracketing_pair(snaps, start, end)
    age = calibration_age_days(today)
    if pair is None:
        return {"status": "NO_BRACKETING_PAIR", "warning": None,
                "calibration_age_days": age,
                "why": "no balance snapshot at/before the run start AND at/after its end"}
    s0, s1 = pair
    prov = round(float(s0["total_usd"]) - float(s1["total_usd"]), 6)
    if rows is None:
        from backend.services import llm_telemetry as LT
        rows = LT.read_calls()
    from backend.services import llm_telemetry as LT
    win = deepseek_rows_between(rows, s0["read_at"], s1["read_at"])
    costs = [LT.row_cost(r) for r in win]
    tel = round(sum(c for c in costs if c is not None), 6)
    n_unpriced = sum(1 for c in costs if c is None)
    out = {"status": "OK", "read_before": s0["read_at"], "read_after": s1["read_at"],
           "balance_before_usd": s0["total_usd"], "balance_after_usd": s1["total_usd"],
           "provider_delta_usd": prov, "telemetry_deepseek_usd": tel,
           "n_deepseek_rows": len(win), "n_unpriced_rows": n_unpriced,
           "calibration_age_days": age, "warn_at": warn_at, "warning": None}
    if prov < 0:
        out["status"] = STATUS_TOPUP_IN_WINDOW
        out["warning"] = "the balance went UP inside the window (a top-up); no comparison"
        return out
    hi = max(abs(prov), abs(tel))
    dis = 0.0 if hi == 0 else round(abs(prov - tel) / hi, 4)
    out["provider_disagreement"] = dis
    if dis > warn_at:
        out["warning"] = (f"WARNING provider balance moved ${prov:.2f} vs telemetry "
                          f"${tel:.4f} ({dis:.0%} > {warn_at:.0%}); the price table's "
                          f"calibration is {age if age is not None else 'UNKNOWN'} days "
                          f"old -- re-run scripts/llm_price_calibrate.py")
    return out
