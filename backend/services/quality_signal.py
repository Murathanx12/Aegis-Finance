"""
Quality signal — gross profitability (TRIAL-QUALITY-IC)
=======================================================

The T8 multi-factor model deferred its quality slot because the EDGAR
fundamentals path (edgartools) hangs. This is the hang-safe form: **gross
profitability = Gross Profit / Total Assets** (Novy-Marx 2013 — the single
best-documented quality measure, and one of the factors the JKP replication
confirms) computed from yfinance's annual statements.

Frozen definition discipline: the score IS GP/A, alone. A Piotroski-style
sub-score (ROA>0, CFO>0, CFO>NI accrual check, ΔGross margin>0) is computed
as payload DIAGNOSTICS only — it does not enter the score, so there are no
tunable weights to overfit. Descriptive until the forward IC says more; NOT
added to the in-flight TRIAL-MULTIFACTOR composite.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

QUALITY_LABEL = ("descriptive gross-profitability (GP/A) score — forward-IC "
                 "candidate, never a buy/sell signal")


def fetch_quality_inputs(ticker: str) -> dict:
    """Live annual statements from yfinance (hang-safe path; edgartools stays
    rejected per NEGATIVE_RESULTS)."""
    import yfinance as yf
    t = yf.Ticker(ticker)
    return {"income": t.financials, "balance": t.balance_sheet,
            "cashflow": t.cashflow}


def _row(df: Optional[pd.DataFrame], *names: str) -> Optional[pd.Series]:
    if df is None or len(df) == 0:
        return None
    for n in names:
        if n in df.index:
            s = df.loc[n].dropna()
            if len(s):
                return s
    return None


def compute_quality_score(inputs: dict) -> dict:
    """Pure scorer: GP/A from the most recent annual column; Piotroski-subset
    diagnostics in the payload. Explicit statuses on missing data."""
    income, balance = inputs.get("income"), inputs.get("balance")
    cashflow = inputs.get("cashflow")

    gp = _row(income, "Gross Profit")
    if gp is None:
        rev = _row(income, "Total Revenue", "Operating Revenue")
        cogs = _row(income, "Cost Of Revenue")
        if rev is not None and cogs is not None:
            common = rev.index.intersection(cogs.index)
            if len(common):
                gp = (rev[common] - cogs[common])
    assets = _row(balance, "Total Assets")
    if gp is None or assets is None:
        return {"quality_score": 0.0, "status": "insufficient_fundamentals",
                "label": QUALITY_LABEL}

    common = gp.index.intersection(assets.index)
    if not len(common):
        return {"quality_score": 0.0, "status": "periods_mismatch",
                "label": QUALITY_LABEL}
    latest = sorted(common)[-1]
    a = float(assets[latest])
    if a <= 0:
        return {"quality_score": 0.0, "status": "degenerate_assets",
                "label": QUALITY_LABEL}
    gpa = float(gp[latest]) / a

    # Piotroski-subset DIAGNOSTICS (payload only; never in the score).
    diag: dict = {}
    ni = _row(income, "Net Income", "Net Income Common Stockholders")
    cfo = _row(cashflow, "Operating Cash Flow",
               "Total Cash From Operating Activities")
    try:
        if ni is not None and latest in ni.index:
            diag["roa_positive"] = bool(float(ni[latest]) > 0)
        if cfo is not None and latest in cfo.index:
            diag["cfo_positive"] = bool(float(cfo[latest]) > 0)
            if ni is not None and latest in ni.index:
                diag["accruals_ok"] = bool(float(cfo[latest]) > float(ni[latest]))
        if gp is not None and len(common) >= 2:
            prev = sorted(common)[-2]
            rev = _row(income, "Total Revenue", "Operating Revenue")
            if rev is not None and latest in rev.index and prev in rev.index \
                    and float(rev[latest]) > 0 and float(rev[prev]) > 0:
                diag["gross_margin_improving"] = bool(
                    float(gp[latest]) / float(rev[latest])
                    > float(gp[prev]) / float(rev[prev]))
    except Exception as e:  # diagnostics must never sink the score
        logger.warning("quality diagnostics failed: %s", e)

    return {
        "quality_score": round(gpa, 4),
        "status": "ok",
        "fiscal_period": str(pd.Timestamp(latest).date()),
        "gross_profit": float(gp[latest]),
        "total_assets": a,
        "piotroski_subset": diag,
        "n_checks_passed": sum(1 for v in diag.values() if v is True),
        "label": QUALITY_LABEL,
    }
