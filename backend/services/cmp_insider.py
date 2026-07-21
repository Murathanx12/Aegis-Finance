"""
CMP opportunistic-insider signal (Cohen-Malloy-Pomorski 2012) — the live scorer
behind TRIAL-CMP-INSIDER-IC, promoted from the brain module's BRAIN-003 survivor.

The signal: count of DISTINCT insiders whose trailing-12-month open-market
purchases are OPPORTUNISTIC under the CMP rule. Routine buyers (same calendar
month in each of the 3 prior years — predictable, calendar-clustered) are
dropped; insiders without a 3-year purchase history are UNCLASSIFIABLE and
dropped too (never defaulted to opportunistic). This is the classifier that
BRAIN-003 validated on CRSP 2006-2024 (large/mid +17 bps/mo vs EW, FF5+UMD
alpha +102 bps/mo t=1.89; null in microcap).

Classifying a LIVE buyer needs their multi-year history, which no live feed
provides — so the brain module ships a compact artifact
(`backend/data/cmp_routine_history.json.gz`) distilled from the SEC bulk
Insider Transactions files (2006 -> last published quarter):

  history      per-insider (CIK) purchase years + year-months, trans-date-keyed
  recent_buys  the panel's own classified opportunistic buys near panel end
  panel_end    the artifact's coverage horizon (staleness guard anchor)

A live trailing-12mo score = distinct opportunistic CIKs from the panel's
recent_buys (up to panel_end) UNION live Form-4 buys after panel_end classified
against the history. Only the post-panel gap rides on live fetches; the
artifact is refreshed quarterly from the brain module (see the trial doc).

Anti-false-zero: if panel_end falls further behind than the live lookback can
cover, the score is DEGRADED — flagged in the payload and logged, never a
silent zero (NEGATIVE_RESULTS §5 is the cautionary tale).
"""

from __future__ import annotations

import gzip
import json
import logging
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

ARTIFACT_PATH = Path(__file__).parent.parent / "data" / "cmp_routine_history.json.gz"

SCORE_LOOKBACK_DAYS = 365   # trailing window for distinct opportunistic buyers (frozen)
LIVE_FETCH_LOOKBACK_DAYS = 200  # live Form-4 window; must cover the post-panel gap
STALE_GAP_DAYS = 210        # panel older than this leaves an uncovered gap -> degraded


@lru_cache(maxsize=1)
def load_artifact(path: str | None = None) -> dict:
    """Load the routine-history artifact. Missing/corrupt file degrades to {}
    (the collector then reports every score as degraded, loudly)."""
    p = Path(path) if path else ARTIFACT_PATH
    try:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            art = json.load(f)
    except Exception as e:
        logger.warning("CMP routine-history artifact unreadable (%s): %s", p, e)
        return {}
    # Contract check at the load boundary: a renamed key or empty history would
    # otherwise make every live buyer unclassifiable — all-zero scores that LOOK
    # healthy. Malformed → {} → every score flags degraded (loud, not silent).
    if not (art.get("panel_end") and art.get("history") and "recent_buys" in art):
        logger.warning("CMP routine-history artifact malformed (%s): keys=%s — "
                       "treating as absent; scores will flag degraded",
                       p, sorted(art.keys()))
        return {}
    return art


def classify_buy(cik: str, trans_date: str, artifact: dict) -> str:
    """CMP-classify one live purchase: 'routine' | 'opportunistic' | 'unclassifiable'.

    Mirrors aegis_brain.events.insider.classify_routine_opportunistic exactly:
    trans-date-keyed, strictly-prior years only (point-in-time by construction).
    """
    cik = str(cik).strip().lstrip("0") or str(cik).strip()
    hist = (artifact.get("history") or {}).get(cik)
    if not hist or not trans_date or len(trans_date) < 7:
        return "unclassifiable"
    try:
        y, m = int(trans_date[:4]), int(trans_date[5:7])
    except ValueError:
        return "unclassifiable"
    years = set(hist.get("years") or [])
    yms = set(hist.get("year_months") or [])
    if not all((y - k) in years for k in (1, 2, 3)):
        return "unclassifiable"
    if all(f"{y - k}-{m:02d}" in yms for k in (1, 2, 3)):
        return "routine"
    return "opportunistic"


def compute_cmp_insider_score(ticker: str, live_buys: list[dict],
                              as_of: str, artifact: dict) -> tuple[float, dict]:
    """(score, payload): distinct opportunistic buyer CIKs over the trailing
    SCORE_LOOKBACK_DAYS — panel recent_buys up to panel_end, live buys after it.

    Never raises; degraded coverage is flagged in the payload, not hidden.
    """
    tk = str(ticker).strip().upper()
    asof = date.fromisoformat(as_of)
    lo = asof - timedelta(days=SCORE_LOOKBACK_DAYS)
    panel_end = None
    if artifact.get("panel_end"):
        try:
            panel_end = date.fromisoformat(artifact["panel_end"])
        except ValueError:
            pass

    opportunistic: set[str] = set()
    # Panel side: already CMP-classified opportunistic buys near panel end.
    n_panel = 0
    for b in artifact.get("recent_buys") or []:
        if b.get("ticker") != tk:
            continue
        try:
            fd = date.fromisoformat(b["filing_date"])
        except (KeyError, ValueError):
            continue
        if lo < fd <= asof:
            opportunistic.add(str(b["cik"]))
            n_panel += 1

    # Live side: Form-4 buys filed AFTER panel_end (no double count), classified here.
    n_live_opp = n_routine = n_unclass = 0
    for b in live_buys or []:
        fd_s = b.get("filing_date") or b.get("date") or ""
        try:
            fd = date.fromisoformat(fd_s[:10])
        except ValueError:
            continue
        if not (lo < fd <= asof) or (panel_end and fd <= panel_end):
            continue
        verdict = classify_buy(b.get("cik") or "", b.get("date") or fd_s, artifact)
        if verdict == "opportunistic":
            opportunistic.add(str(b.get("cik")))
            n_live_opp += 1
        elif verdict == "routine":
            n_routine += 1
        else:
            n_unclass += 1

    gap_days = (asof - panel_end).days if panel_end else None
    degraded = (not artifact) or panel_end is None or gap_days > STALE_GAP_DAYS
    if degraded:
        logger.warning("CMP insider score DEGRADED for %s: artifact panel_end=%s "
                       "(gap %s d > %s) — refresh cmp_routine_history from the brain module",
                       tk, artifact.get("panel_end"), gap_days, STALE_GAP_DAYS)
    payload = {"n_opportunistic_buyers": len(opportunistic), "n_panel_buys": n_panel,
               "n_live_opportunistic": n_live_opp, "n_live_routine": n_routine,
               "n_live_unclassifiable": n_unclass, "panel_end": artifact.get("panel_end"),
               "degraded": bool(degraded)}
    return float(len(opportunistic)), payload
