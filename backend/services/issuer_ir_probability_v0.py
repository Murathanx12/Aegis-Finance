"""Frozen, zero-authority probability preview for a prospective issuer case.

The typed CURRENT row is a feature. This pure rule makes the proposed
ASML-vs-SPY H5 probability explicit before any model reply or return read.
It does not admit a source, register a trial, write a forecast, or trade.
"""
from __future__ import annotations

import math


class ProbabilityRefused(ValueError):
    pass


def preview(row: dict) -> dict:
    if (row.get("source") != "asml_ir_q3_2026"
            or row.get("event_type") not in {"earnings", "guidance"}
            or "ASML" not in row.get("tickers", [])
            or row.get("tickers_unverified")):
        raise ProbabilityRefused("source_event_or_us_symbol_not_verified")
    sentiment = row.get("sentiment")
    if (isinstance(sentiment, bool) or not isinstance(sentiment, (int, float))
            or not math.isfinite(sentiment) or not -1 <= sentiment <= 1):
        raise ProbabilityRefused("sentiment_missing_or_invalid")
    probability = 0.55 if sentiment >= 0.2 else 0.45 if sentiment <= -0.2 else 0.50
    return {"status": "PREVIEW_ONLY_NO_FORECAST_AUTHORITY",
            "mechanism": "issuer_ir_sentiment_to_asml_spy_h5_v0",
            "symbol": "ASML", "benchmark": "SPY", "horizon_sessions": 5,
            "p_symbol_beats_benchmark": probability,
            "control_probability": 0.50,
            "source_forward_claims_used": False,
            "price_or_corporate_forecast_claim": False}
