"""
LPPLS bubble-structure flag — DESCRIPTIVE, never a forecaster (T1)
=================================================================

The Log-Periodic Power Law Singularity model captures the *structure* of a
speculative regime (super-exponential price growth + accelerating log-periodic
oscillations). Its predictive skill for crash *timing* was adversarially
**REFUTED twice** in the 2026-06-14 deep research
(`DEEP_RESEARCH_2026-06-14_DECISION.md` §1.1). So it ships here as a descriptive
bubble/regime flag ONLY:

  - It is measured FORWARD against a base-rate climatology baseline (TRIAL-LPPLS,
    forward Brier by horizon) before any skill is ever claimed.
  - It is HARD-WIRED to never arm a lane, never size a position, and never emit
    buy/sell language. There is no code path from this module to a trade.
  - A skill claim is permitted only if a pre-registered forward Brier ever beats
    climatology by horizon — which the literature predicts it will not.

This mirrors the crash-overlay observability template: a scheduled eval persists
an `lppls_eval` audit row each cycle, `scheduler.lppls_status()` reads the latest
and exposes a canary on `/api/health/full`, so a dark/stale flag can never run
unseen.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Surfaced with every reading so the UI/consumer can never mistake it for a call.
LPPLS_LABEL = "descriptive bubble-structure flag — NOT a crash-timing forecaster"

# Sentinel portfolio_id for the market-level (non-lane) audit rows.
MARKET_ID = "_market"

# Forward-Brier harness defaults (pre-registered in TRIAL-LPPLS).
BRIER_HORIZONS_DAYS = (30, 60, 90)
CRASH_DRAWDOWN_THRESHOLD = 0.10  # a "crash" outcome = SPY draws down >=10% within the horizon


# ─────────────────────────────────────────────────────────────────────────
# Evaluation (descriptive reading)
# ─────────────────────────────────────────────────────────────────────────


LPPLS_TRIAL_PARAM = "lppls-fragility-flag"

LPPLS_DECISION_RULE = {
    "trial": "TRIAL-LPPLS",
    "hypothesis": (
        "LPPLS bubble-structure confidence on the S&P 500 has forward skill at "
        "flagging elevated crash risk over 30/60/90-day horizons"
    ),
    "purpose": "experimental",
    "primary_metric": "forward Brier by horizon vs base-rate climatology",
    "horizons_days": list(BRIER_HORIZONS_DAYS),
    "crash_outcome": f"SPY drawdown >= {CRASH_DRAWDOWN_THRESHOLD:.0%} within horizon",
    "baseline": "climatology (predict in-sample base rate every period)",
    "adopt_threshold": "skill_score > 0 (brier_flag < brier_climatology) on a "
                       "pre-registered forward window, all horizons",
    "prior": "predictive skill REFUTED twice in deep research; expected null",
    "hard_constraint": "descriptive-only; NEVER arms a lane / no buy-sell language",
    "pre_registered": "2026-06-14",
    "canonical_doc": "docs/TRIALS/TRIAL-LPPLS-fragility.md",
}


def ensure_lppls_trial(db_path=None) -> int:
    """Idempotently pre-register TRIAL-LPPLS in the experiment registry.

    Returns the row id (existing or new). Registering it as a trial means the
    LPPLS skill test enters the cumulative trial count the DSR/PBO guards deflate
    against — the conservative direction. verdict='adopted' here means we adopt
    SHIPPING the descriptive flag; any future *signal* claim is a separate trial
    gated on the forward Brier in the decision rule.
    """
    import json as _json

    from backend.db import count_cumulative_trials, get_connection, init_db

    init_db(db_path)
    conn = get_connection(db_path)
    try:
        existing = conn.execute(
            "SELECT id FROM rule_experiments WHERE param = ? ORDER BY id LIMIT 1",
            (LPPLS_TRIAL_PARAM,),
        ).fetchone()
        if existing is not None:
            return int(existing["id"])
        cumulative = count_cumulative_trials(conn) + 1
        notes = {"hypothesis": LPPLS_DECISION_RULE["hypothesis"],
                 "purpose": "experimental",
                 "decision_rule": LPPLS_DECISION_RULE}
        cur = conn.execute(
            "INSERT INTO rule_experiments "
            "(created_at, config_version, lane_id, param, old_value, new_value, "
            " batch_trials, cumulative_trials, verdict, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), "descriptive", None, LPPLS_TRIAL_PARAM,
             None, "registered", 1, cumulative, "adopted", _json.dumps(notes)),
        )
        conn.commit()
        logger.info("Pre-registered TRIAL-LPPLS (cumulative trials now %d)", cumulative)
        return int(cur.lastrowid)
    finally:
        conn.close()


def evaluate_lppls(prices: Optional[pd.Series] = None) -> dict:
    """Compute the descriptive LPPLS reading on the S&P 500 (or a supplied series).

    Returns a dict with status ∈ {evaluated, lppls_not_installed,
    data_unavailable, eval_error} and, when evaluated, confidence/is_bubble/
    tc_date/n_valid_fits. NEVER returns an arming or sizing decision.
    """
    if prices is None:
        try:
            from backend.services.data_fetcher import DataFetcher
            data, _ = DataFetcher().fetch_market_data()
            prices = data["SP500"]
        except Exception as e:  # pragma: no cover - network/IO
            logger.warning("LPPLS: market data unavailable: %s", e)
            return {"status": "data_unavailable", "confidence": None,
                    "is_bubble": None, "label": LPPLS_LABEL}

    if prices is None or len(prices) < 120:
        return {"status": "data_unavailable", "confidence": None,
                "is_bubble": None, "label": LPPLS_LABEL}

    try:
        from backend.services.bubble_detector import get_bubble_status
        b = get_bubble_status(prices, ticker="SP500")
    except Exception as e:
        logger.warning("LPPLS eval error: %s", e)
        return {"status": "eval_error", "confidence": None,
                "is_bubble": None, "label": LPPLS_LABEL}

    if b.get("confidence") is None:
        # bubble_detector returns a reason string in `status` when lppls is absent.
        reason = b.get("status", "lppls_not_installed")
        status = "lppls_not_installed" if "not installed" in str(reason) else "eval_error"
        return {"status": status, "confidence": None, "is_bubble": None,
                "label": LPPLS_LABEL}

    return {
        "status": "evaluated",
        "confidence": b.get("confidence"),
        "is_bubble": b.get("is_bubble"),
        "tc_date": b.get("tc_date"),
        "n_valid_fits": b.get("n_valid_fits"),
        "as_of": str(prices.dropna().index[-1].date()),
        "label": LPPLS_LABEL,
        # Explicit, machine-readable guarantee echoed into every persisted row.
        "arms_lane": False,
        "descriptive_only": True,
    }


def persist_lppls_eval(reading: dict, db_path=None) -> None:
    """Append one `lppls_eval` audit row (market-level) — the forward record."""
    from backend.db import get_connection, insert_audit_log

    conn = get_connection(db_path)
    try:
        insert_audit_log(conn, datetime.now().isoformat(), MARKET_ID,
                         "lppls_eval", reading)
    finally:
        conn.close()


def run_lppls_eval(prices: Optional[pd.Series] = None, db_path=None) -> dict:
    """Evaluate + persist the descriptive LPPLS reading. Called by the scheduler.

    Loud, not silent: it always writes a status row (even on error), so a dark
    flag is visible in health rather than hidden behind a swallowed exception.
    """
    reading = evaluate_lppls(prices)
    try:
        persist_lppls_eval(reading, db_path=db_path)
    except Exception as e:  # pragma: no cover
        logger.error("LPPLS persist failed: %s", e, exc_info=True)
    return reading


# ─────────────────────────────────────────────────────────────────────────
# Forward Brier harness (the measurement — accumulates, scored later)
# ─────────────────────────────────────────────────────────────────────────


def brier_skill(forecasts, outcomes) -> dict:
    """Brier score of a probabilistic flag vs its own base-rate climatology.

    A pure, testable scorer. `forecasts` ∈ [0,1] (here: LPPLS confidence used
    as a deliberately conservative pseudo-probability), `outcomes` ∈ {0,1}.
    climatology = predicting the in-sample base rate every time. The flag has
    skill iff brier_flag < brier_climatology (skill_score > 0).

    Returns {n, base_rate, brier_flag, brier_climatology, skill_score, status}.
    """
    f = np.asarray(forecasts, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    if f.shape != y.shape or f.size == 0:
        return {"status": "no_data", "n": int(f.size)}
    base = float(y.mean())
    brier_flag = float(np.mean((f - y) ** 2))
    brier_clim = float(np.mean((base - y) ** 2))
    skill = None if brier_clim <= 1e-12 else 1.0 - brier_flag / brier_clim
    return {
        "status": "ok",
        "n": int(y.size),
        "base_rate": round(base, 4),
        "brier_flag": round(brier_flag, 4),
        "brier_climatology": round(brier_clim, 4),
        "skill_score": None if skill is None else round(skill, 4),
    }


def _realized_drawdown_within(
    prices: pd.Series, start, horizon_days: int,
    threshold: float = CRASH_DRAWDOWN_THRESHOLD,
) -> Optional[int]:
    """1 if SPY drew down >= `threshold` within `horizon_days` of `start`, 0 if
    it did not, None if the window hasn't fully matured yet."""
    start = pd.Timestamp(start)
    window_end = start + timedelta(days=horizon_days)
    if prices.index[-1] < window_end:
        return None  # not matured — cannot be scored without peeking
    window = prices.loc[(prices.index >= start) & (prices.index <= window_end)]
    if len(window) < 2:
        return None
    peak = window.iloc[0]
    trough = window.min()
    return int((trough / peak - 1.0) <= -threshold)


def forward_brier_status(db_path=None, horizons=BRIER_HORIZONS_DAYS) -> dict:
    """Forward-Brier measurement state for TRIAL-LPPLS — accumulates over time.

    Joins persisted `lppls_eval` readings with realized forward SPY drawdowns
    for readings old enough to have matured, and scores Brier vs climatology per
    horizon. Until enough matured observations exist it returns
    `insufficient_forward_data` with the count accumulated — the honest
    "still measuring" state, never a fabricated number.
    """
    import json

    from backend.db import get_connection

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT timestamp, payload FROM audit_log "
            "WHERE event_type = 'lppls_eval' ORDER BY id",
        ).fetchall()
    finally:
        conn.close()

    readings = []
    for r in rows:
        try:
            p = json.loads(r["payload"])
        except Exception:
            logger.warning("skipping malformed persisted reading row (H5): %s",
                           dict(r).get("timestamp", "?"))
            continue
        if p.get("status") == "evaluated" and p.get("confidence") is not None:
            readings.append({"date": p.get("as_of") or r["timestamp"][:10],
                             "confidence": float(p["confidence"])})

    base = {"trial": "TRIAL-LPPLS", "readings_accumulated": len(readings),
            "crash_threshold": CRASH_DRAWDOWN_THRESHOLD, "label": LPPLS_LABEL,
            "note": "descriptive flag measured forward; never arms a lane"}

    if len(readings) < 30:
        return {**base, "status": "insufficient_forward_data",
                "horizons": {str(h): {"status": "insufficient_forward_data"} for h in horizons}}

    # Realized outcomes need SPY history covering the matured windows.
    try:
        from backend.services.data_fetcher import DataFetcher
        data, _ = DataFetcher().fetch_market_data()
        spy = data["SP500"].dropna()
    except Exception:
        return {**base, "status": "data_unavailable"}

    out = {**base, "status": "ok", "horizons": {}}
    for h in horizons:
        fc, yo = [], []
        for rec in readings:
            y = _realized_drawdown_within(spy, rec["date"], h)
            if y is not None:
                fc.append(rec["confidence"])
                yo.append(y)
        out["horizons"][str(h)] = (
            brier_skill(fc, yo) if len(yo) >= 30
            else {"status": "insufficient_forward_data", "matured": len(yo)}
        )
    return out


# ─────────────────────────────────────────────────────────────────────────
# Fragility composite (descriptive index) + TRIAL-CRASH
# ─────────────────────────────────────────────────────────────────────────

# Equal-weighted by design: we do NOT fit weights, because fitting them to past
# crashes is exactly the hindsight overfitting this project refuses. Each input
# is normalized to a documented [0,1] fragility scale (1 = most fragile).
FRAGILITY_LABEL = (
    "descriptive structural-fragility index — NOT a crash forecast or timing call"
)
CRASH_TRIAL_DRAWDOWN = 0.20  # TRIAL-CRASH outcome: SPY drawdown >=20% within horizon
CRASH_TRIAL_PARAM = "fragility-composite"

# Candidate inputs the research flagged but NOT yet wired as active inputs. They
# are logged here (not asserted) so the composite is honest about what it omits.
FRAGILITY_CANDIDATE_INPUTS = [
    {"name": "vix_term_structure", "reason": "backwardation = near-term stress; "
     "needs the VIX futures curve (flaky/extra fetch)"},
    {"name": "options_put_skew", "reason": "put/call IV skew = hedging demand; "
     "yfinance options chain (network-flaky)"},
    {"name": "ipo_issuance", "reason": "Murat's post-IPO-glut hypothesis feature — "
     "COLLECTING forward since 2026-07-08 (EDGAR S-1/424B4 counts via the "
     "candidate collector); still not in the composite"},
    {"name": "mega_cap_concentration", "reason": "trillion-dollar-club narrowness — "
     "COLLECTING forward since 2026-07-08 (SPY/RSP relative-return spread); "
     "complements absorption ratio; not in the composite"},
    {"name": "crash_narrative", "reason": "crash talk in the news (GDELT volume "
     "z-score) — COLLECTING forward since 2026-07-08; reflexive/noisy by "
     "construction; not in the composite"},
]


# Temporal classification of each input relative to a drawdown. Research-graded
# where the 2026-06-14 deep research spoke (turbulence COINCIDENT, absorption
# LEADING, LPPL refuted — docs/FRAGILITY_RESEARCH_2026-06-14.md); by-construction
# reasoning otherwise. This is a TRANSPARENCY label only — it does NOT re-weight
# the composite (equal-weight stays, per the no-fit-weights canon). It does drive
# a secondary, equal-weighted `leading_composite` view for forward reads.
FRAGILITY_LEAD_LAG = {
    "lppls_confidence": ("leading", "bubble structure precedes — but LPPL predictive "
                         "skill is refuted twice; descriptive only"),
    "sos": ("lagging", "recession confirmation; coincident-to-lagging by construction"),
    "sahm": ("lagging", "recession-onset rule; triggers after the downturn begins"),
    "turbulence": ("coincident", "research-graded: peaks DURING crises, not before "
                   "(Salisu 2022; ORCA 2026) — use persistence, not as a leading trigger"),
    "absorption_ratio": ("leading", "research-graded: rises before major drawdowns; "
                         "'strongest classical baseline' (Kritzman 2011)"),
    "net_liquidity": ("leading", "financial-conditions input; liquidity drains ahead of stress"),
    "hy_oas": ("coincident", "high-yield credit spread; widens as risk reprices"),
    "ig_oas": ("coincident", "investment-grade credit spread; widens as risk reprices"),
}


def _clip01(x: float) -> float:
    return float(min(max(x, 0.0), 1.0))


def _pct_rank(series: pd.Series, value: float) -> Optional[float]:
    """Percentile rank of `value` within `series` history, in [0,1]."""
    s = series.dropna()
    if len(s) < 30:
        return None
    return float((s <= value).mean())


def compute_fragility_index(data=None, fred_data=None, as_of_ts=None) -> dict:
    """Equal-weighted descriptive structural-fragility index in [0,1].

    Aggregates already-fetched structural signals, each normalized to a [0,1]
    fragility scale (1 = most fragile), and returns their equal-weighted mean
    over the inputs that are available this cycle. DESCRIPTIVE ONLY — no code
    path from here arms a lane, sizes a position, or emits buy/sell language.

    ``as_of_ts`` (optional): slice every input series to ``<= as_of_ts`` so all
    values and percentile ranks use only data knowable at that date — correct-by-
    construction and leak-proof when backtested. ``None`` (live) is a no-op.

    Returns {status, composite, level, n_inputs, dispersion, components,
    candidate_inputs, label, as_of}. `composite` is None if no input resolved.
    """
    components: dict = {}

    def _add(name: str, normalized: Optional[float], raw=None):
        # B1 guard: a NaN/inf normalization is an unresolved signal, not a value.
        # Without this, _clip01(NaN)=NaN counts as "available" and poisons the
        # composite mean (root cause of FINDINGS F1/F7).
        if normalized is not None and not np.isfinite(normalized):
            normalized = None
        cls, note = FRAGILITY_LEAD_LAG.get(name, ("unclassified", ""))
        components[name] = {
            "raw": raw,
            "normalized": None if normalized is None else round(_clip01(normalized), 4),
            "available": normalized is not None,
            "lead_lag": cls,
            "lead_lag_note": note,
        }

    # Fetch the shared inputs once.
    if data is None or fred_data is None:
        try:
            from backend.services.data_fetcher import DataFetcher
            f = DataFetcher()
            if data is None:
                data, _ = f.fetch_market_data()
            if fred_data is None:
                fred_data = f.fetch_fred_data()
        except Exception as e:  # pragma: no cover - network/IO
            logger.warning("fragility composite: data unavailable: %s", e)
            return {"status": "data_unavailable", "composite": None,
                    "label": FRAGILITY_LABEL, "candidate_inputs": FRAGILITY_CANDIDATE_INPUTS}

    # As-of bound: slice every input series to <= as_of_ts so EVERY downstream
    # value and percentile rank uses only data knowable at as_of — correct-by-
    # construction, leak-proof even when backtested. At the live edge
    # (as_of_ts=None) this is a no-op, so live behavior is unchanged.
    # (net_liquidity below fetches its own live series and is not as-of bound —
    # it is network-gated and absent in offline backtests; noted in the docstring.)
    if as_of_ts is not None:
        cutoff = pd.Timestamp(as_of_ts)
        try:
            data = data.loc[data.index <= cutoff]
        except Exception as e:
            # H5: proceeding UNSLICED would silently leak the future into a
            # backtested composite (defeats B5). A missing reading is honest;
            # a leaked one is not.
            logger.warning("fragility composite: as-of slice failed (%s) — "
                           "refusing to compute unsliced at as_of=%s", e, as_of_ts)
            return {"status": "asof_slice_failed", "composite": None,
                    "label": FRAGILITY_LABEL,
                    "candidate_inputs": FRAGILITY_CANDIDATE_INPUTS}
        fred_data = {
            k: (v.loc[v.index <= cutoff] if hasattr(v, "loc") else v)
            for k, v in (fred_data or {}).items()
        }

    as_of = None
    try:
        as_of = str(data["SP500"].dropna().index[-1].date())
    except Exception:
        pass

    # 1. LPPLS confidence (already [0,1]).
    try:
        lp = evaluate_lppls(data["SP500"])
        _add("lppls_confidence",
             lp.get("confidence") if lp.get("status") == "evaluated" else None,
             raw=lp.get("confidence"))
    except Exception:
        _add("lppls_confidence", None)

    # 2/3. SOS + Sahm (recession-confirmation; normalized vs their triggers).
    try:
        from backend.services.macro_indicators import recession_indicators
        ri = recession_indicators(fred_data)
        sos = ri["sos"]
        _add("sos", sos["value"] / 0.5 if sos.get("status") == "ok" and sos.get("value") is not None else None,
             raw=sos.get("value"))
        sahm = ri["sahm"]
        _add("sahm", sahm["value"] / 1.0 if sahm.get("status") == "ok" and sahm.get("value") is not None else None,
             raw=sahm.get("value"))
    except Exception:
        _add("sos", None); _add("sahm", None)

    # 4/5. Systemic risk: turbulence percentile + absorption ratio.
    try:
        from backend.services.systemic_risk import compute_systemic_risk
        sr = compute_systemic_risk(data)
        tp = sr.get("turbulence_percentile")
        _add("turbulence", tp / 100.0 if tp is not None else None, raw=tp)
        ar = sr.get("absorption_ratio_current")
        _add("absorption_ratio", ar if ar is not None else None, raw=ar)
    except Exception:
        _add("turbulence", None); _add("absorption_ratio", None)

    # 6. Net liquidity: draining vs its own 52wk history = higher fragility.
    try:
        from backend.services.net_liquidity import get_net_liquidity
        nl = get_net_liquidity()
        hist = nl.get("history") or []
        if len(hist) >= 8:
            vals = pd.Series([h["net_liquidity"] for h in hist])
            chg4 = vals.diff(4).dropna()  # 4-week changes
            latest_chg = float(chg4.iloc[-1])
            rank = _pct_rank(chg4, latest_chg)  # low rank = draining fast
            _add("net_liquidity", None if rank is None else (1.0 - rank),
                 raw=round(latest_chg, 4))
        else:
            _add("net_liquidity", None)
    except Exception:
        _add("net_liquidity", None)

    # 7/8. Credit spreads: HY + IG OAS percentile vs own history (widening = stress).
    for key in ("hy_oas", "ig_oas"):
        try:
            s = fred_data.get(key)
            if s is not None and len(s.dropna()) >= 30:
                cur = float(s.dropna().iloc[-1])
                _add(key, _pct_rank(s, cur), raw=round(cur, 3))
            else:
                _add(key, None)
        except Exception:
            _add(key, None)

    norms = [c["normalized"] for c in components.values() if c["available"]]
    if not norms:
        return {"status": "no_inputs", "composite": None, "components": components,
                "label": FRAGILITY_LABEL, "candidate_inputs": FRAGILITY_CANDIDATE_INPUTS}

    composite = float(np.mean(norms))
    dispersion = float(np.std(norms))  # signals' disagreement = honest uncertainty
    # Neutral descriptive bands — deliberately NOT "crash imminent" language.
    level = ("low" if composite < 0.30 else "moderate" if composite < 0.55
             else "elevated" if composite < 0.75 else "high")
    # Secondary view: equal-weighted mean over only the LEADING inputs. Not a
    # re-weighting of the composite (which stays the TRIAL-CRASH metric) — a
    # separate descriptive read for "where is fragility heading", since coincident
    # inputs (turbulence, OAS) peak DURING stress and lagging ones (Sahm/SOS)
    # confirm after onset. Same equal-weight discipline, just a subset.
    leading_norms = [
        c["normalized"] for c in components.values()
        if c["available"] and c["lead_lag"] == "leading"
    ]
    leading_composite = (
        round(float(np.mean(leading_norms)), 4) if leading_norms else None
    )
    return {
        "status": "ok",
        "composite": round(composite, 4),
        "level": f"{level} structural fragility (descriptive)",
        "n_inputs": len(norms),
        "dispersion": round(dispersion, 4),
        "leading_composite": leading_composite,
        "leading_inputs": len(leading_norms),
        "lead_lag_note": (
            "composite is equal-weighted over ALL available inputs (unchanged, "
            "the TRIAL-CRASH metric). leading_composite is the equal-weighted "
            "subset of leading inputs — coincident inputs (turbulence, OAS) peak "
            "during stress, lagging inputs (Sahm/SOS) confirm after onset."
        ),
        "components": components,
        "candidate_inputs": FRAGILITY_CANDIDATE_INPUTS,
        "as_of": as_of,
        "label": FRAGILITY_LABEL,
        "arms_lane": False,
        "descriptive_only": True,
    }


# ─────────────────────────────────────────────────────────────────────────
# Continuous exposure multiplier (descriptive bridge — NOT armed)
# ─────────────────────────────────────────────────────────────────────────

# The research's specific ask: a crisis engine must output a CONTINUOUS exposure
# multiplier, NEVER a binary "risk-off" call — there are only ~2 endogenous
# modern US crashes (2000, 2008; 2020 exogenous), far too few to validate a
# trigger. This maps the descriptive fragility composite to the exposure a future
# PRE-REGISTERED defensive lane COULD apply. It is NOT wired to any live lane
# here (canon: no strategy change to an in-flight tracked lane) — it mirrors how
# `exit_overlay.evaluate_exit_overlay` was built before the conservative-atr lane
# was seeded. A real defensive lane would consume this on a NEW inception.
EXPOSURE_FLOOR = 0.50      # never de-risk below 50% on a descriptive signal
FRAGILITY_NEUTRAL = 0.30   # at/below this composite, full exposure (1.0)
FRAGILITY_HIGH = 0.90      # at/above this composite, the exposure floor

EXPOSURE_LABEL = (
    "descriptive exposure multiplier — NOT armed; continuous (never a binary "
    "risk-off call); for a future pre-registered defensive lane only"
)


def exposure_multiplier(
    composite: Optional[float],
    *,
    floor: float = EXPOSURE_FLOOR,
    neutral: float = FRAGILITY_NEUTRAL,
    high: float = FRAGILITY_HIGH,
) -> dict:
    """Map a descriptive fragility composite in [0,1] to a CONTINUOUS exposure
    multiplier in [floor, 1.0]: 1.0 at/below ``neutral``, linearly down to
    ``floor`` at/above ``high``. Monotonic non-increasing in fragility.

    DESCRIPTIVE ONLY — returns the multiplier a future pre-registered defensive
    lane COULD apply; no code path from here arms or scales a live lane.
    """
    if composite is None or (isinstance(composite, float) and np.isnan(composite)):
        # A NaN composite (e.g. an upstream input that normalized to NaN) is
        # treated like "no reading" — never a NaN multiplier reported as ok.
        return {"status": "unavailable", "multiplier": None,
                "label": EXPOSURE_LABEL, "arms_lane": False}
    c = _clip01(composite)
    if c <= neutral:
        mult = 1.0
    elif c >= high:
        mult = floor
    else:
        frac = (c - neutral) / (high - neutral)
        mult = 1.0 - frac * (1.0 - floor)
    return {
        "status": "ok",
        "multiplier": round(float(mult), 4),
        "composite": round(c, 4),
        "floor": floor,
        "neutral": neutral,
        "high": high,
        "label": EXPOSURE_LABEL,
        "arms_lane": False,
        "descriptive_only": True,
    }


def persist_fragility_eval(result: dict, db_path=None) -> None:
    """Append one market-level `fragility_eval` audit row (the forward record)."""
    from backend.db import get_connection, insert_audit_log

    # Store a compact row (score + per-input normalized) — enough to score forward.
    row = {"status": result.get("status"), "composite": result.get("composite"),
           "level": result.get("level"), "n_inputs": result.get("n_inputs"),
           "as_of": result.get("as_of"), "arms_lane": False,
           "components": {k: v.get("normalized") for k, v in
                          (result.get("components") or {}).items()}}
    conn = get_connection(db_path)
    try:
        insert_audit_log(conn, datetime.now().isoformat(), MARKET_ID,
                         "fragility_eval", row)
    finally:
        conn.close()


def latest_persisted_composite(db_path=None) -> dict:
    """The most recent persisted `fragility_eval` row (fast, no network) —
    what the daily check last computed, with its timestamp. For read surfaces
    that must not trigger a live recompute."""
    import json as _json

    from backend.db import get_connection

    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT timestamp, payload FROM audit_log "
            "WHERE event_type = 'fragility_eval' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return {"status": "no_reading", "label": FRAGILITY_LABEL}
    try:
        p = _json.loads(row["payload"]) or {}
    except Exception:
        logger.warning("skipping malformed latest fragility_eval row (H5)")
        return {"status": "no_reading", "label": FRAGILITY_LABEL}
    p["evaluated_at"] = row["timestamp"]
    p["label"] = FRAGILITY_LABEL
    return p


def run_fragility_eval(data=None, fred_data=None, db_path=None) -> dict:
    """Compute + persist the descriptive fragility composite (scheduler hook)."""
    result = compute_fragility_index(data=data, fred_data=fred_data)
    try:
        persist_fragility_eval(result, db_path=db_path)
    except Exception as e:  # pragma: no cover
        logger.error("Fragility persist failed: %s", e, exc_info=True)
    return result


CRASH_DECISION_RULE = {
    "trial": "TRIAL-CRASH",
    "hypothesis": (
        "An equal-weighted descriptive structural-fragility composite has forward "
        "skill at flagging large S&P 500 drawdowns over 30/60/90-day horizons"
    ),
    "purpose": "experimental",
    "primary_metric": "forward Brier + calibration curve by horizon vs climatology",
    "horizons_days": list(BRIER_HORIZONS_DAYS),
    "crash_outcome": f"SPY drawdown >= {CRASH_TRIAL_DRAWDOWN:.0%} within horizon",
    "baseline": "climatology (predict the in-sample base rate every period)",
    "adopt_threshold": "skill_score > 0 on a pre-registered forward window, all horizons",
    "rarity_caveat": (
        f"a >= {CRASH_TRIAL_DRAWDOWN:.0%} drawdown within 90d is rare, so the "
        "base rate is low and a meaningful forward Brier needs a long window; "
        "calibration at this rarity is weak — reported honestly, not glossed"
    ),
    "candidate_inputs": [c["name"] for c in FRAGILITY_CANDIDATE_INPUTS],
    "hard_constraint": "descriptive-only; NEVER arms a lane / no buy-sell language / "
                       "no 'crash imminent' framing",
    "pre_registered": "2026-06-14",
    "canonical_doc": "docs/TRIALS/TRIAL-CRASH-fragility-composite.md",
}


def ensure_crash_trial(db_path=None) -> int:
    """Idempotently pre-register TRIAL-CRASH (the composite skill test).

    Non-lane trial: it increments the RAW cumulative trial count (the DSR
    strictness floor) but carries no return stream, so the effective-N (N_eff)
    computation — which runs over REFERENCE_LANES only — is unaffected. verdict
    'adopted' = we adopt SHIPPING the descriptive composite; any future *signal*
    claim is a separate trial gated on the forward Brier.
    """
    import json as _json

    from backend.db import count_cumulative_trials, get_connection, init_db

    init_db(db_path)
    conn = get_connection(db_path)
    try:
        existing = conn.execute(
            "SELECT id FROM rule_experiments WHERE param = ? ORDER BY id LIMIT 1",
            (CRASH_TRIAL_PARAM,),
        ).fetchone()
        if existing is not None:
            return int(existing["id"])
        cumulative = count_cumulative_trials(conn) + 1
        notes = {"hypothesis": CRASH_DECISION_RULE["hypothesis"],
                 "purpose": "experimental", "decision_rule": CRASH_DECISION_RULE}
        cur = conn.execute(
            "INSERT INTO rule_experiments "
            "(created_at, config_version, lane_id, param, old_value, new_value, "
            " batch_trials, cumulative_trials, verdict, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), "descriptive", None, CRASH_TRIAL_PARAM,
             None, "registered", 1, cumulative, "adopted", _json.dumps(notes)),
        )
        conn.commit()
        logger.info("Pre-registered TRIAL-CRASH (cumulative trials now %d)", cumulative)
        return int(cur.lastrowid)
    finally:
        conn.close()


def forward_brier_status_composite(db_path=None, horizons=BRIER_HORIZONS_DAYS) -> dict:
    """Forward-Brier state for TRIAL-CRASH (composite vs 20% drawdown climatology).

    Joins persisted `fragility_eval` readings with realized forward SPY 20%
    drawdowns for matured readings; reports `insufficient_forward_data` (with the
    count accumulated) until enough matured observations exist per horizon.
    """
    import json

    from backend.db import get_connection

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT timestamp, payload FROM audit_log "
            "WHERE event_type = 'fragility_eval' ORDER BY id",
        ).fetchall()
    finally:
        conn.close()

    readings = []
    for r in rows:
        try:
            p = json.loads(r["payload"])
        except Exception:
            logger.warning("skipping malformed persisted reading row (H5): %s",
                           dict(r).get("timestamp", "?"))
            continue
        if p.get("status") == "ok" and p.get("composite") is not None:
            readings.append({"date": p.get("as_of") or r["timestamp"][:10],
                             "composite": float(p["composite"])})

    base = {"trial": "TRIAL-CRASH", "readings_accumulated": len(readings),
            "crash_threshold": CRASH_TRIAL_DRAWDOWN, "label": FRAGILITY_LABEL,
            "note": "descriptive composite measured forward; never arms a lane"}

    if len(readings) < 30:
        return {**base, "status": "insufficient_forward_data",
                "horizons": {str(h): {"status": "insufficient_forward_data"} for h in horizons}}

    try:
        from backend.services.data_fetcher import DataFetcher
        data, _ = DataFetcher().fetch_market_data()
        spy = data["SP500"].dropna()
    except Exception:
        return {**base, "status": "data_unavailable"}

    out = {**base, "status": "ok", "horizons": {}}
    for h in horizons:
        fc, yo = [], []
        for rec in readings:
            y = _realized_drawdown_within(spy, rec["date"], h, threshold=CRASH_TRIAL_DRAWDOWN)
            if y is not None:
                fc.append(rec["composite"])
                yo.append(y)
        out["horizons"][str(h)] = (
            brier_skill(fc, yo) if len(yo) >= 30
            else {"status": "insufficient_forward_data", "matured": len(yo)}
        )
    return out
