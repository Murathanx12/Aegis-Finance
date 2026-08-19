"""EXPECTATION-BACKFILL-1 v0 — the first rows G4 ever holds.

`g4_expectation` shipped as machinery with no supplier; the NET coverage
audit declares the "+expectations" family ABSENT; four daemon jobs block on
event/expectation stores. This module is the v0 supplier: historical
earnings surprises (estimate vs actual per announcement) from FMP, stored
raw with provenance, and mapped into `ExpectationRecord`s under DECLARED
conventions rather than invented precision.

WHY FMP AND WHAT THAT CAPS
==========================
The PIT hierarchy runs CRSP > SEC-EDGAR > ... > FMP > yfinance(forbidden).
FMP's earnings-surprises endpoint reports the consensus AS RECORDED AT the
announcement, at DAY precision, with no expectation_asof timestamp. So:

- `first_public_ts` = the announcement DATE (day precision, declared);
- `expectation_asof` = the PRIOR calendar day, a CONVENTION stamped on
  every record (`PRIOR_DAY_CONVENTION`) — strictly before publication by
  construction, honest about being a convention and not a measurement;
- every measured-only field this rung cannot supply carries an
  `unknown_reasons` entry, because silence and "checked, absent" must not
  look the same (the g4 contract enforces this).

The upgrade rung is IBES via WRDS (real estimate timestamps + dispersion);
this store's schema keeps `provenance` on every row so the two rungs can
coexist without laundering.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

from backend import config as _config
from backend.services.g4_expectation import ExpectationRecord

log = logging.getLogger(__name__)

STORE_DIR = _config.OPTIMUS_LEDGER_DIR / "expectations"
#: Probed 2026-08-19: /api/v3/earnings-surprises 403s for post-2025-08 keys
#: ("Legacy Endpoint") — the catalogue is not entitlement, again. The
#: /stable/earnings endpoint answers 200 and carries eps AND revenue
#: expectation/actual per announcement date.
PROVENANCE = "FMP_STABLE_EARNINGS_V0"
_FMP_BASE = "https://financialmodelingprep.com/stable"
_TIMEOUT = 15


class ExpectationStoreRefused(RuntimeError):
    """A required input is missing. Refused, not defaulted."""


@dataclass(frozen=True)
class SurpriseRow:
    ticker: str
    announced_date: str            # day precision — FMP's resolution
    eps_estimate: float
    eps_actual: float
    revenue_estimate: float | None = None
    revenue_actual: float | None = None
    provenance: str = PROVENANCE

    @property
    def surprise(self) -> float:
        return self.eps_actual - self.eps_estimate


def fetch_earnings_surprises(ticker: str) -> list[SurpriseRow] | None:
    """One budget-guarded FMP call. None = not fetched (budget/keys/error) —
    distinct from an empty list, which is FMP saying 'no rows'."""
    if not ticker or not str(ticker).strip():
        raise ExpectationStoreRefused("fetch needs a ticker; got nothing")
    from backend.config import api_keys
    if not api_keys.has("fmp"):
        return None
    from backend.services import fmp_budget
    if not fmp_budget.try_spend():
        return None
    import requests
    try:
        r = requests.get(f"{_FMP_BASE}/earnings",
                         params={"symbol": ticker, "apikey": api_keys.fmp},
                         timeout=_TIMEOUT)
        if r.status_code == 402:
            fmp_budget.mark_exhausted()
            return None
        if r.status_code in (401, 403, 429):
            return None
        r.raise_for_status()
        data = r.json()
    except Exception as e:                                     # noqa: BLE001
        log.debug("FMP stable/earnings failed for %s: %s", ticker, e)
        return None
    out = []
    for row in data if isinstance(data, list) else []:
        est, act, d = (row.get("epsEstimated"), row.get("epsActual"),
                       row.get("date"))
        if est is None or act is None or not d:
            continue    # future rows carry null actual; one side is no surprise
        out.append(SurpriseRow(
            ticker=ticker.upper(), announced_date=str(d)[:10],
            eps_estimate=float(est), eps_actual=float(act),
            revenue_estimate=(float(row["revenueEstimated"])
                              if row.get("revenueEstimated") is not None
                              else None),
            revenue_actual=(float(row["revenueActual"])
                            if row.get("revenueActual") is not None
                            else None)))
    return out


def backfill(tickers: list[str], *, store_dir: Path | None = None,
             fetch=fetch_earnings_surprises) -> dict:
    """Resumable backfill: one JSONL per ticker; already-present tickers are
    skipped and counted. Refuses an empty universe — a backfill of nothing
    reporting 'complete' is the lift-audit defect."""
    if not tickers:
        raise ExpectationStoreRefused(
            "backfill over an empty universe — refusing to report a "
            "complete store over nothing")
    d = Path(store_dir or STORE_DIR)
    d.mkdir(parents=True, exist_ok=True)
    counts = {"fetched": 0, "rows": 0, "skipped_present": 0,
              "not_fetched": []}
    for t in tickers:
        p = d / f"{t.upper()}.jsonl"
        if p.exists():
            counts["skipped_present"] += 1
            continue
        rows = fetch(t)
        if rows is None:
            counts["not_fetched"].append(t)
            continue
        p.write_text("\n".join(json.dumps(asdict(r)) for r in rows),
                     encoding="utf-8")
        counts["fetched"] += 1
        counts["rows"] += len(rows)
    counts["note"] = ("not_fetched is ACTIONABLE (budget/keys/error), "
                      "skipped_present is DELIBERATE (resumable store)")
    return counts


#: Every measured-only g4 field this rung cannot supply, with the reason —
#: stated once here instead of silently absent on ten thousand records.
_V0_UNKNOWNS = {
    "expectation_dispersion": "FMP v0 rung carries no per-analyst detail",
    "n_estimates": "FMP v0 rung carries no per-analyst detail",
    "pre_event_price_runup": "price join is the panel's job, not the store's",
    "market_reaction": "price join is the panel's job, not the store's",
    "overnight_gap": "needs intraday open/close join (panel's job)",
    "market_reaction_tradable": "needs intraday open/close join (panel's job)",
    "options_implied_move": "options PIT store not built (see handoff job 4)",
    "dollar_volume_20d": "price join is the panel's job, not the store's",
    "hl_range_20d": "price join is the panel's job, not the store's",
    "amihud_20d": "price join is the panel's job, not the store's",
}


def to_expectation_records(rows: list[SurpriseRow]) -> list[ExpectationRecord]:
    """Map raw rows into g4 records under the declared conventions."""
    if rows is None:
        raise ExpectationStoreRefused("to_expectation_records(None) — a "
                                      "missing fetch is not an empty one")
    out = []
    for r in rows:
        ann = date.fromisoformat(r.announced_date)
        out.append(ExpectationRecord(
            entity=r.ticker, entity_id_kind="ticker_dated",
            entity_id=r.ticker,
            event_type="EPS_ANNOUNCEMENT",
            event_id=f"{r.ticker}:EPS:{r.announced_date}",
            first_public_ts=f"{r.announced_date}T00:00:00Z",
            expectation_asof=f"{(ann - timedelta(days=1)).isoformat()}"
                             f"T23:59:59Z",
            observed_at=None, tradable_at=None,
            numeric_expectation=r.eps_estimate, actual=r.eps_actual,
            source_ids=[f"{PROVENANCE}:{r.ticker}:{r.announced_date}"],
            unknown_reasons={
                **_V0_UNKNOWNS,
                "observed_at": "FMP reports day precision only",
                "tradable_at": "bmo/amc flag absent on this rung",
                "_expectation_asof_basis": "PRIOR_DAY_CONVENTION — a "
                "declared convention, not a measured timestamp; the IBES "
                "rung replaces it",
            }))
    return out
