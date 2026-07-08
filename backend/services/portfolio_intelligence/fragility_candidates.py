"""
Fragility CANDIDATE inputs — collected, never asserted (Branch 1 item 3)
=======================================================================

Murat's three crash-thesis drivers, wired as *measured candidates* per the
TRIAL-CRASH discipline: each value is snapshotted forward into the PIT store
(``fragility_candidate:{name}``) so a forward record accrues, and each ships as
LABELED DESCRIPTIVE CONTEXT. None of them enters ``compute_fragility_index``'s
composite (the TRIAL-CRASH metric) until a pre-registered forward trial earns
it — the composite stays byte-identical to its pre-registration.

The three candidates:

- ``ipo_issuance`` — the post-IPO-glut hypothesis. Trailing-90d count of S-1
  registrations + 424B4 pricing prospectuses from EDGAR full-text search
  (free, official). More filings = hotter issuance. Raw counts; the percentile
  vs own history becomes meaningful as the PIT record accrues forward.
- ``mega_cap_concentration`` — the trillion-dollar-companies concern. Trailing
  126d total-return spread of cap-weighted SPY over equal-weighted RSP:
  positive = narrow mega-cap leadership carrying the index. Complements the
  absorption ratio (co-movement) already in the composite.
- ``crash_narrative`` — crash talk in the news. GDELT volume z-score of
  crash/recession coverage vs its own trailing baseline. Reflexive and noisy
  by construction — the label says so.

Failure isolation: one candidate failing must never break the others or the
daily check (the shared collector isolates per-name; errors are loud).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from backend.db import get_connection, get_latest_observable
from backend.services.portfolio_intelligence.pit_score_collector import collect_pit_scores

logger = logging.getLogger(__name__)

KEY_PREFIX = "fragility_candidate:"
CANDIDATE_LABEL = ("descriptive candidate — collected forward, NOT in the fragility "
                   "composite; enters only via a pre-registered trial")

_EDGAR_FTS = "https://efts.sec.gov/LATEST/search-index"
_IPO_WINDOW_DAYS = 90
_CONCENTRATION_WINDOW = 126  # trading days of relative return
_NARRATIVE_QUERY = '"stock market crash" OR "market crash" OR "recession fears"'


# ── Candidate 1: IPO issuance (EDGAR full-text search counts) ────────────────


def _edgar_form_count(form: str, start: str, end: str) -> int:
    """Count of EDGAR filings of ``form`` filed in [start, end], via the free
    full-text search API. Routed through the ONE process-wide SEC limiter +
    mandatory UA (the T9 prod-403 lesson: ALL SEC HTTP goes through _sec_get)."""
    from backend.services.insider_form4 import _sec_get
    url = f"{_EDGAR_FTS}?q=%22offering%22&forms={form}&startdt={start}&enddt={end}"
    r = _sec_get(url)
    return int(r.json().get("total", {}).get("value", 0))


def compute_ipo_issuance(as_of: str | None = None) -> tuple[float, dict]:
    """Trailing-90d S-1 + 424B4 filing count. Raw count (higher = hotter
    issuance); percentile context accrues in the PIT store forward."""
    end = date.fromisoformat(as_of) if as_of else date.today()
    start = end - timedelta(days=_IPO_WINDOW_DAYS)
    s1 = _edgar_form_count("S-1", start.isoformat(), end.isoformat())
    b4 = _edgar_form_count("424B4", start.isoformat(), end.isoformat())
    total = s1 + b4
    return float(total), {
        "s1_count": s1, "424b4_count": b4,
        "window_days": _IPO_WINDOW_DAYS,
        "source_detail": "EDGAR full-text search",
        "label": CANDIDATE_LABEL,
    }


# ── Candidate 2: mega-cap concentration (SPY vs RSP relative return) ─────────


def compute_mega_cap_concentration() -> tuple[float, dict]:
    """Trailing-126d total-return spread, cap-weighted SPY minus equal-weighted
    RSP, in return points. Positive = narrow mega-cap leadership."""
    import yfinance as yf
    px = yf.download(["SPY", "RSP"], period="9mo", progress=False,
                     auto_adjust=True)["Close"].dropna()
    if len(px) < _CONCENTRATION_WINDOW + 1 or "SPY" not in px or "RSP" not in px:
        raise ValueError(f"insufficient SPY/RSP history ({len(px)} rows)")
    win = px.iloc[-(_CONCENTRATION_WINDOW + 1):]
    spy_ret = float(win["SPY"].iloc[-1] / win["SPY"].iloc[0] - 1.0)
    rsp_ret = float(win["RSP"].iloc[-1] / win["RSP"].iloc[0] - 1.0)
    spread = spy_ret - rsp_ret
    return spread, {
        "spy_return": round(spy_ret, 4), "rsp_return": round(rsp_ret, 4),
        "window_trading_days": _CONCENTRATION_WINDOW,
        "source_detail": "SPY/RSP total-return spread (yfinance)",
        "label": CANDIDATE_LABEL,
    }


# ── Candidate 3: crash-narrative intensity (GDELT) ───────────────────────────


def compute_crash_narrative() -> tuple[float, dict]:
    """GDELT volume z-score of crash/recession coverage vs its trailing
    baseline. Reflexive/noisy by construction — descriptive only."""
    from backend.services.news_intelligence import fetch_gdelt_signals
    sig = fetch_gdelt_signals(query=_NARRATIVE_QUERY, days=30)
    if not sig.get("success"):
        raise ValueError(f"GDELT unavailable: {sig.get('reason', 'unknown')}")
    return float(sig.get("volume_zscore", 0.0)), {
        "avg_tone": sig.get("avg_tone"), "tone_trend": sig.get("tone_trend"),
        "query": _NARRATIVE_QUERY,
        "source_detail": "GDELT doc API volume z-score",
        "label": CANDIDATE_LABEL,
    }


# ── Candidates 4-12: extra FRED credit/stress series (IMPROVEMENT_BACKLOG B9) ─
#
# Fetched HERE via fredapi, deliberately NOT via config["data"]["fred_series"]:
# the crash-feature matrix iterates every configured FRED series, so adding
# these globally would silently change the model's feature contract (the
# 2026-06-10 gpr_world lesson). Candidates stay isolated until a trial admits
# them anywhere.

_B9_FRED_SERIES = {
    # name: (series_id, invert, note)   value = stress-oriented percentile [0,1]
    "bbb_oas": ("BAMLC0A4CBBB", False, "BBB corporate OAS — the IG/junk boundary"),
    "ccc_oas": ("BAMLH0A3HYC", False, "CCC & lower OAS — deepest credit tail"),
    "em_oas": ("BAMLEMCBPIOAS", False, "EM corporate OAS — external stress"),
    "yield_curve_10y2y": ("T10Y2Y", True, "10Y-2Y spread; inversion = stress (inverted)"),
    "breakeven_10y": ("T10YIE", False, "10Y breakeven — RAW percentile; both tails "
                      "matter (deflation scare vs inflation shock), no stress "
                      "orientation claimed"),
    "breakeven_5y5y": ("T5YIFR", False, "5y5y forward inflation — RAW percentile; "
                       "both tails matter, no stress orientation claimed"),
    "adj_financial_conditions": ("ANFCI", False, "Chicago Fed adjusted NFCI"),
    "stl_fin_stress": ("STLFSI4", False, "St. Louis Fed financial stress index"),
    "policy_uncertainty": ("USEPUINDXD", False, "Economic Policy Uncertainty (the "
                           "FRED-hosted GPR replacement)"),
}


def _fred_stress_percentile(series_id: str, invert: bool) -> tuple[float, dict]:
    """Percentile rank of the latest value within the series' full history,
    oriented so higher = more stress when ``invert`` (e.g. yield curve)."""
    import os
    from fredapi import Fred
    key = os.environ.get("FRED_API_KEY")
    if not key:
        raise ValueError("FRED_API_KEY not set")
    s = Fred(api_key=key).get_series(series_id).dropna()
    if len(s) < 30:
        raise ValueError(f"{series_id}: only {len(s)} observations")
    latest = float(s.iloc[-1])
    pct = float((s <= latest).mean())
    value = 1.0 - pct if invert else pct
    return value, {
        "series_id": series_id, "latest_raw": round(latest, 4),
        "percentile_raw": round(pct, 4), "inverted": invert,
        "n_obs": int(len(s)),
        "source_detail": "FRED latest-vintage (revision caveat: IMPROVEMENT_BACKLOG B14)",
        "label": CANDIDATE_LABEL,
    }


def _make_fred_candidate(series_id: str, invert: bool):
    return lambda: _fred_stress_percentile(series_id, invert)


# ── Collector + reader ────────────────────────────────────────────────────────

_CANDIDATES = {
    "ipo_issuance": lambda: compute_ipo_issuance(),
    "mega_cap_concentration": compute_mega_cap_concentration,
    "crash_narrative": compute_crash_narrative,
    **{name: _make_fred_candidate(sid, inv)
       for name, (sid, inv, _note) in _B9_FRED_SERIES.items()},
}


def collect_fragility_candidates(db_path=None, as_of: str | None = None) -> dict:
    """Snapshot all candidate readings into the PIT store (weekly-throttled,
    per-candidate failure isolation via the shared collector engine)."""
    def _score(name: str) -> tuple[float, dict]:
        return _CANDIDATES[name]()

    return collect_pit_scores(
        key_prefix=KEY_PREFIX,
        source="fragility_candidates(edgar/yfinance/gdelt)",
        score_for_ticker=_score,
        tickers=list(_CANDIDATES),
        db_path=db_path,
        as_of=as_of,
    )


def latest_candidate_readings(db_path=None) -> dict:
    """Latest PIT reading per candidate (leak-free), for the fragility surface.
    A candidate with no snapshot yet (or whose last run errored) reports
    ``status: not_collected`` — absence is shown, never papered over."""
    conn = get_connection(db_path)
    try:
        out: dict[str, dict] = {}
        for name in _CANDIDATES:
            row = get_latest_observable(conn, KEY_PREFIX + name)
            if row is None or (row.get("payload") or {}).get("error"):
                out[name] = {"status": "not_collected", "value": None,
                             "label": CANDIDATE_LABEL}
            else:
                out[name] = {"status": "collected", "value": row["value"],
                             "as_of": row["as_of"], "payload": row.get("payload"),
                             "label": CANDIDATE_LABEL}
        return out
    finally:
        conn.close()
