"""
Congressional (STOCK Act) trading disclosures — fetch + score.
================================================================

TRIAL-CONGRESS-IC (see docs/TRIALS/TRIAL-CONGRESS-IC.md). Descriptive only.

Source: FMP `senate-latest` + `house-latest` (official API, free tier —
verified live 2026-07-11; the free GitHub stock-watcher dumps are dead since
2021 and were rejected). PIT discipline: the knowledge time is
``disclosureDate`` — when the public could know — never ``transactionDate``
(trades disclose up to 45 days late).

Fail-loud contract: HTTP errors and malformed payloads RAISE. An empty page
deep in pagination is legal (end of data), but page 0 empty for BOTH chambers
raises — Congress always has recent disclosures, so "no data" means the source
broke, and a silent zero would poison the IC clock with false-neutral
snapshots (the house failure mode).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

import requests

from backend.config import api_keys

logger = logging.getLogger(__name__)

_BASE = "https://financialmodelingprep.com/stable"
_TIMEOUT = 30

WINDOW_DAYS = 90
UNIVERSE_CAP = 150  # frozen: most-active tickers by trade count
_CHAMBER_ENDPOINTS = {"senate": "senate-latest", "house": "house-latest"}


def _fmp_get(endpoint: str, page: int, limit: int) -> list[dict]:
    """One FMP page. Raises on HTTP error or non-list payload (FMP signals
    errors — bad key, rate limit — as a JSON object, not a list)."""
    if not api_keys.has("fmp"):
        raise RuntimeError("FMP_API_KEY not set — congress trades unavailable")
    # Priority draw (2026-07-17): this pre-registered collector may spend the
    # reserved slice that fmp_budget holds back from fallback/ESG traffic.
    from backend.services import fmp_budget
    if not fmp_budget.try_spend(priority=True):
        raise RuntimeError(
            f"FMP {endpoint} skipped — daily FMP budget exhausted (ledger); "
            "congress source unavailable this run (retries next slot)"
        )
    resp = requests.get(
        f"{_BASE}/{endpoint}",
        params={"page": page, "limit": limit, "apikey": api_keys.fmp},
        timeout=_TIMEOUT,
    )
    if resp.status_code == 402:
        # FMP signals an exhausted free-tier daily quota as 402 on otherwise
        # free endpoints (senate-latest verified free 2026-07-11 AND
        # 2026-07-17 — the 2026-07-16 AND 2026-07-17 prod 402s were the
        # day's shared quota, burned by fallback-provider traffic — at the
        # 07:30 ET slot the quota was ALREADY gone, which is why the
        # fmp_budget ledger now meters every caller).
        fmp_budget.mark_exhausted()
        raise RuntimeError(
            f"FMP {endpoint} returned 402 — daily FMP quota exhausted; "
            "congress source unavailable this run (retries next slot)"
        )
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        # requests embeds the full URL (incl. apikey) in the message — redact
        # before the scheduler's error handler can put it in a log line.
        raise requests.HTTPError(api_keys.redact(str(e)), response=resp) from None
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError(f"FMP {endpoint} returned non-list payload: {str(data)[:200]}")
    return data


def fetch_congress_trades(
    window_days: int = WINDOW_DAYS,
    as_of: Optional[str] = None,
    max_pages: int = 8,
    page_size: int = 250,
) -> list[dict]:
    """All disclosures from both chambers with disclosureDate inside
    ``(as_of − window_days, as_of]``, normalized. Paginates until a page is
    empty, older than the window, or max_pages."""
    aso = date.fromisoformat(as_of) if as_of else date.today()
    cutoff = aso - timedelta(days=window_days)

    trades: list[dict] = []
    for chamber, endpoint in _CHAMBER_ENDPOINTS.items():
        for page in range(max_pages):
            rows = _fmp_get(endpoint, page, page_size)
            if not rows:
                if page == 0:
                    raise ValueError(
                        f"FMP {endpoint} page 0 empty — source broken, refusing "
                        "to emit false-neutral scores"
                    )
                break
            page_exhausted = False
            for r in rows:
                disc = (r.get("disclosureDate") or "")[:10]
                try:
                    disc_d = date.fromisoformat(disc)
                except ValueError:
                    continue  # undated rows are unusable for PIT
                if disc_d <= cutoff:
                    page_exhausted = True
                    continue
                if disc_d > aso:
                    continue  # future-dated rows never enter (leak-safe)
                symbol = (r.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                trades.append({
                    "chamber": chamber,
                    "member_id": r.get("senateID") or
                    f"{r.get('firstName', '')} {r.get('lastName', '')}".strip(),
                    "symbol": symbol,
                    "asset_type": (r.get("assetType") or "").strip(),
                    "type": (r.get("type") or "").strip(),
                    "amount": r.get("amount") or "",
                    "transaction_date": (r.get("transactionDate") or "")[:10],
                    "disclosure_date": disc,
                })
            if page_exhausted:
                break

    # Contract-drift guard: Congress ALWAYS has disclosures in a 90d window
    # (both chambers, thousands per quarter). Pages came back non-empty but
    # nothing parsed → a field rename (disclosureDate/symbol) is silently
    # dropping every row, and that must be loud, not a quiet-week lookalike.
    if not trades:
        raise ValueError(
            "FMP congress pages returned rows but zero parsed into the "
            f"{window_days}d window — payload contract drift?"
        )

    logger.info("congress trades: %d disclosures in window (%s -> %s)",
                len(trades), cutoff.isoformat(), aso.isoformat())
    return trades


def _is_common_stock(asset_type: str) -> bool:
    at = asset_type.lower()
    return at.startswith("stock") and "option" not in at


def compute_congress_scores(
    trades: list[dict],
    as_of: Optional[str] = None,
    window_days: int = WINDOW_DAYS,
) -> dict[str, tuple[float, dict]]:
    """Per-ticker ``congress_score = n_buy_members − n_sell_members`` over
    common-stock disclosures in the window (frozen — TRIAL-CONGRESS-IC).
    Distinct members, not trade counts: cluster buying is the documented
    effect and one member splitting an order must not look like conviction."""
    aso = date.fromisoformat(as_of) if as_of else date.today()
    cutoff = aso - timedelta(days=window_days)

    agg: dict[str, dict] = {}
    for t in trades:
        try:
            disc_d = date.fromisoformat(t["disclosure_date"])
        except (KeyError, ValueError):
            continue
        if not (cutoff < disc_d <= aso):
            continue
        sym = t["symbol"]
        a = agg.setdefault(sym, {"buyers": set(), "sellers": set(),
                                 "n_trades": 0, "n_nonstock": 0,
                                 "chambers": set()})
        if not _is_common_stock(t.get("asset_type", "")):
            a["n_nonstock"] += 1
            continue
        a["n_trades"] += 1
        a["chambers"].add(t["chamber"])
        ttype = t.get("type", "").lower()
        if "purchase" in ttype:
            a["buyers"].add(t["member_id"])
        elif "sale" in ttype:
            a["sellers"].add(t["member_id"])

    out: dict[str, tuple[float, dict]] = {}
    for sym, a in agg.items():
        if a["n_trades"] == 0:
            continue  # only non-stock instruments — no headline score
        score = float(len(a["buyers"]) - len(a["sellers"]))
        out[sym] = (score, {
            "n_buy_members": len(a["buyers"]),
            "n_sell_members": len(a["sellers"]),
            "n_trades": a["n_trades"],
            "n_nonstock": a["n_nonstock"],
            "chambers": sorted(a["chambers"]),
        })
    return out


def active_universe(scores: dict[str, tuple[float, dict]],
                    cap: int = UNIVERSE_CAP) -> list[str]:
    """The most-active tickers by in-window trade count, capped (frozen).
    Deterministic tiebreak by symbol so reruns snapshot the same set."""
    ranked = sorted(scores.items(),
                    key=lambda kv: (-kv[1][1]["n_trades"], kv[0]))
    return [sym for sym, _ in ranked[:cap]]
