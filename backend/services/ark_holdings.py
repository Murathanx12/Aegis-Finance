"""
ARK daily ETF holdings — fetch + parse + flow score.
=====================================================

TRIAL-ARK-IC (see docs/TRIALS/TRIAL-ARK-IC.md). Descriptive only.

ARK publishes each fund's FULL holdings as a public CSV every trading day —
the only free, official, daily stream of a real active manager's decisions.
Share-count diffs between consecutive published days are attributable trades.

Fail-loud contract: HTTP errors raise; an empty CSV raises; a header rename
raises (contract drift must never read as a quiet day). One fund failing does
NOT sink the others — the collector isolates per fund but reports failures
loudly in its summary.
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_BASE = "https://assets.ark-funds.com/fund-documents/funds-etf-csv"
_TIMEOUT = 30
_UA = {"User-Agent": "Mozilla/5.0 (AegisFinance research; educational)"}

# Frozen fund set (TRIAL-ARK-IC) — filenames verified live 2026-07-11.
FUND_FILES: dict[str, str] = {
    "ARKK": "ARK_INNOVATION_ETF_ARKK_HOLDINGS.csv",
    "ARKW": "ARK_NEXT_GENERATION_INTERNET_ETF_ARKW_HOLDINGS.csv",
    "ARKG": "ARK_GENOMIC_REVOLUTION_ETF_ARKG_HOLDINGS.csv",
    "ARKQ": "ARK_AUTONOMOUS_TECH._&_ROBOTICS_ETF_ARKQ_HOLDINGS.csv",
    "ARKF": "ARK_FINTECH_INNOVATION_ETF_ARKF_HOLDINGS.csv",
    "ARKX": "ARK_SPACE_EXPLORATION_&_INNOVATION_ETF_ARKX_HOLDINGS.csv",
}

_REQUIRED_COLS = {"date", "fund", "ticker", "shares"}

SCORE_WINDOW_SESSIONS = 21  # frozen
SCORE_CLIP = 1.0            # per-fund relative change clipped to [-1, +1]


def _parse_shares(raw: str) -> Optional[float]:
    s = (raw or "").replace(",", "").replace('"', "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _parse_date(raw: str) -> Optional[str]:
    """ARK dates are MM/DD/YYYY → ISO, or None if unparseable."""
    parts = (raw or "").strip().split("/")
    if len(parts) != 3:
        return None
    try:
        m, d, y = int(parts[0]), int(parts[1]), int(parts[2])
        return f"{y:04d}-{m:02d}-{d:02d}"
    except ValueError:
        return None


def fetch_fund_holdings(fund: str) -> list[dict]:
    """One fund's current holdings: [{fund, date(iso), ticker, shares, weight_pct}].

    Raises on HTTP failure, empty payload, or header drift. Non-equity rows
    (no ticker — cash/receivables) are excluded.
    """
    fname = FUND_FILES.get(fund)
    if fname is None:
        raise ValueError(f"unknown ARK fund {fund!r}")
    resp = requests.get(f"{_BASE}/{fname}", headers=_UA, timeout=_TIMEOUT)
    resp.raise_for_status()

    reader = csv.DictReader(io.StringIO(resp.text))
    if reader.fieldnames is None or not _REQUIRED_COLS.issubset(
            {c.strip().lower() for c in reader.fieldnames}):
        raise ValueError(
            f"ARK {fund} CSV header drift: {reader.fieldnames!r}")

    rows: list[dict] = []
    for r in reader:
        r = {(k or "").strip().lower(): (v or "") for k, v in r.items()}
        ticker = r.get("ticker", "").strip().upper()
        date_iso = _parse_date(r.get("date", ""))
        shares = _parse_shares(r.get("shares", ""))
        if not ticker or date_iso is None or shares is None:
            continue  # cash / footer rows
        weight = r.get("weight (%)", "").replace("%", "").strip()
        try:
            weight_pct = float(weight)
        except ValueError:
            weight_pct = None
        rows.append({"fund": fund, "date": date_iso, "ticker": ticker,
                     "shares": shares, "weight_pct": weight_pct})

    if not rows:
        raise ValueError(f"ARK {fund} CSV parsed to zero holdings — "
                         "contract drift or empty publication")
    return rows


def compute_ark_scores(
    current: dict[str, dict[str, float]],
    baseline: dict[str, dict[str, float]],
) -> dict[str, tuple[float, dict]]:
    """Frozen TRIAL-ARK-IC score from two {fund: {ticker: shares}} maps:

        score(ticker) = Σ_funds clip((now − then) / then, ±1)

    A position absent at baseline but present now is a new buy (+1 for that
    fund); present then but gone now is a full exit (−1)."""
    tickers: set[str] = set()
    for m in (*current.values(), *baseline.values()):
        tickers.update(m)

    out: dict[str, tuple[float, dict]] = {}
    for t in tickers:
        total = 0.0
        n_funds = 0
        for fund in FUND_FILES:
            now = current.get(fund, {}).get(t)
            then = baseline.get(fund, {}).get(t)
            if now is None and then is None:
                continue
            n_funds += 1
            if then is None or then <= 0:
                change = SCORE_CLIP           # new position
            elif now is None or now <= 0:
                change = -SCORE_CLIP          # full exit
            else:
                change = max(-SCORE_CLIP,
                             min(SCORE_CLIP, (now - then) / then))
            total += change
        if n_funds:
            out[t] = (round(total, 6), {"n_funds": n_funds})
    return out
