"""
Macro recession-confirmation indicators
=======================================

Honest, descriptive recession flags. These are **coincident-to-lagging**, not
leading — they confirm a downturn that has (probably) already begun. We display
them by *lag-to-onset*, never as foresight, and attach no prediction claim.

Currently:
  - Sahm rule (SAHMREALTIME, already fetched) — triggers ~3.4 months after NBER
    onset; has had false positives (2003, 2024).
  - SOS (Richmond Fed, EB 25-07) — 26-week MA of the insured unemployment rate
    rising >= 0.2pp above its prior-52-week minimum. In the Richmond Fed study
    it caught all 7 recessions since 1971 with zero false positives and signals
    ~2.3 months after onset (earlier than Sahm) — but that record is historical
    and 2024-vintage; immigration-driven 2024 labor dynamics may not generalize,
    so it must be **measured forward**, not asserted as skill.

Reference: Richmond Fed Economic Brief 25-07,
https://www.richmondfed.org/publications/research/economic_brief/2025/eb_25-07
(verified 2026-06-14, DEEP_RESEARCH_2026-06-14_DECISION.md §1.2).
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

# SOS parameters (Richmond Fed EB 25-07).
SOS_MA_WEEKS = 26          # moving-average window on the insured unemployment rate
SOS_LOOKBACK_WEEKS = 52    # prior window for the trough comparison
SOS_THRESHOLD_PP = 0.20    # trigger when the MA rises >= 0.2pp above the prior trough

# Honest framing shown with every recession indicator. Deliberately contains NO
# leading-indicator language — these confirm, they do not predict.
RECESSION_FRAMING = (
    "Recession-CONFIRMATION indicators (coincident-to-lagging, shown by "
    "lag-to-onset, NOT as foresight). SOS triggers earlier than Sahm relative "
    "to NBER onset but still after a recession has begun. Zero-false-positive "
    "records are historical/in-sample and must be measured forward; this is "
    "descriptive context, not a prediction or a skill claim."
)


def compute_sos_signal(insured_unemployment_rate: Optional[pd.Series]) -> dict:
    """Richmond Fed SOS recession-confirmation flag from the insured unemployment rate.

    SOS = (26-week MA of the insured unemployment rate) minus (the minimum of
    that 26-week MA over the *prior* 52 weeks). The flag triggers when that gap
    is >= 0.2 percentage points.

    Args:
        insured_unemployment_rate: weekly IURSA series (percent). May be None.

    Returns:
        dict with status ∈ {ok, insufficient_history, no_data} and, when ok:
        value (pp above prior trough), triggered (bool), ma_26w, prior_52w_min,
        threshold_pp, last_date. NEVER a probability or a prediction.
    """
    if insured_unemployment_rate is None or len(insured_unemployment_rate) == 0:
        return {"status": "no_data", "value": None, "triggered": None}

    s = insured_unemployment_rate.dropna()
    # Need the full MA window plus the prior lookback window of MA values.
    min_obs = SOS_MA_WEEKS + SOS_LOOKBACK_WEEKS
    if len(s) < min_obs:
        return {"status": "insufficient_history", "value": None,
                "triggered": None, "n_obs": int(len(s)), "min_obs": min_obs}

    ma = s.rolling(SOS_MA_WEEKS).mean()
    # Prior-52-week minimum of the MA, EXCLUDING the current week (shift(1)).
    prior_min = ma.shift(1).rolling(SOS_LOOKBACK_WEEKS).min()

    ma_now = float(ma.iloc[-1])
    prior_min_now = float(prior_min.iloc[-1])
    value = ma_now - prior_min_now
    return {
        "status": "ok",
        "value": round(value, 4),
        "triggered": bool(value >= SOS_THRESHOLD_PP),
        "ma_26w": round(ma_now, 4),
        "prior_52w_min": round(prior_min_now, 4),
        "threshold_pp": SOS_THRESHOLD_PP,
        "last_date": str(s.index[-1].date()),
    }


def _sahm_from_fred(fred_data: dict) -> dict:
    """Latest Sahm-rule value as a descriptive flag (triggers at +0.50pp)."""
    series = fred_data.get("sahm_rule")
    if series is None or len(series) == 0:
        return {"status": "no_data", "value": None, "triggered": None}
    s = series.dropna()
    if len(s) == 0:
        return {"status": "no_data", "value": None, "triggered": None}
    val = float(s.iloc[-1])
    return {
        "status": "ok",
        "value": round(val, 4),
        "triggered": bool(val >= 0.50),
        "threshold_pp": 0.50,
        "last_date": str(s.index[-1].date()),
    }


def recession_indicators(fred_data: dict) -> dict:
    """Both recession-confirmation flags (Sahm + SOS) with honest framing.

    Args:
        fred_data: output of DataFetcher.fetch_fred_data() (keyed by friendly name).

    Returns:
        {"sahm": {...}, "sos": {...}, "framing": RECESSION_FRAMING}.
    """
    return {
        "sahm": _sahm_from_fred(fred_data),
        "sos": compute_sos_signal(fred_data.get("insured_unemployment_rate")),
        "framing": RECESSION_FRAMING,
    }
