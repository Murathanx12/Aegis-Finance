"""
EODHD acceptance test — the pre-committed gate on the $50/mo data decision.

Frozen bar (docs/research/DATA_SOURCES_AND_BASELINES_2026-07-16.md):
EODHD is bought only if >=16/20 of the survivorship-audit delisted names
(the exact list that failed yfinance at 1/20) come back usable.

Two phases so the FREE plan answers most of the question before paying:

  Phase 1 (FREE API key, no card):
      python -m engine.research.eodhd_acceptance --phase 1
    Checks the delisted symbol list (exchange-symbol-list/US?delisted=1)
    for all 20 audit names. If fewer than 16 are even LISTED, stop — do
    not subscribe.

  Phase 2 (paid All World key):
      python -m engine.research.eodhd_acceptance --phase 2
    Fetches EOD history for each name and applies the SAME usability
    criteria as survivorship_audit.py (>=250 rows, history ends within 400
    days of the known exit year — i.e., it is the real dead company, not a
    recycled symbol). Reports N/20 against the >=16 bar.

Set EODHD_API_TOKEN in the environment. Results print + write JSON next to
this file. This script is research tooling — it never touches the backend.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine.research.survivorship_audit import DELISTED  # noqa: E402

log = logging.getLogger("eodhd_acceptance")
logging.basicConfig(level=logging.INFO, format="%(message)s")

BASE = "https://eodhd.com/api"
PASS_BAR = 16  # frozen in the research doc BEFORE any EODHD data was seen
OUT = Path(__file__).parent / f"eodhd_acceptance_{date.today().isoformat()}.json"


def _token() -> str:
    tok = os.getenv("EODHD_API_TOKEN", "").strip()
    if not tok:
        sys.exit("Set EODHD_API_TOKEN (free plan key works for phase 1). "
                 "Sign up: https://eodhd.com/register")
    return tok


def phase1(tok: str) -> dict:
    """Free-plan check: are the 20 dead companies in the delisted list at all?"""
    r = requests.get(f"{BASE}/exchange-symbol-list/US",
                     params={"api_token": tok, "fmt": "json", "delisted": "1"},
                     timeout=120)
    r.raise_for_status()
    listed = {row.get("Code", "").upper() for row in r.json()}
    log.info("Delisted US symbol list: %d tickers", len(listed))

    results = {}
    for t, note, exit_year in DELISTED:
        results[t] = t.upper() in listed
        log.info("  %-6s %s  (%s, %d)", t, "LISTED" if results[t] else "MISSING",
                 note, exit_year)
    n = sum(results.values())
    verdict = "PROCEED to phase 2 (subscribe)" if n >= PASS_BAR else \
              "STOP — do not subscribe (fewer than 16/20 even listed)"
    log.info("PHASE 1: %d/%d present — %s", n, len(DELISTED), verdict)
    return {"phase": 1, "present": results, "n": n, "bar": PASS_BAR,
            "verdict": verdict}


def phase2(tok: str) -> dict:
    """Paid check: usable history for each name (same criteria as the audit)."""
    results = {}
    for t, note, exit_year in DELISTED:
        try:
            r = requests.get(f"{BASE}/eod/{t}.US",
                             params={"api_token": tok, "fmt": "json"},
                             timeout=120)
            rows = r.json() if r.status_code == 200 else []
            if not isinstance(rows, list) or len(rows) < 250:
                results[t] = {"usable": False, "reason": f"rows={len(rows) if isinstance(rows, list) else 'n/a'}"}
            else:
                last = rows[-1].get("date", "")
                last_year = int(last[:4]) if last[:4].isdigit() else 0
                # real dead company: history ENDS near the known exit year —
                # a recycled symbol keeps trading past it
                ends_at_death = abs(last_year - exit_year) <= 1
                results[t] = {"usable": ends_at_death, "rows": len(rows),
                              "last_date": last, "exit_year": exit_year,
                              "reason": None if ends_at_death else
                              f"history ends {last} but company died {exit_year} (recycled symbol?)"}
        except Exception as e:
            results[t] = {"usable": False, "reason": str(e)[:120]}
        st = results[t]
        log.info("  %-6s %s  %s", t,
                 "USABLE " if st["usable"] else "UNUSABLE",
                 st.get("reason") or f"{st.get('rows')} rows to {st.get('last_date')}")
    n = sum(1 for v in results.values() if v["usable"])
    verdict = ("PASS — keep the subscription; build the loader"
               if n >= PASS_BAR else
               "FAIL — cancel EODHD; get a Sharadar SEP quote instead")
    log.info("PHASE 2: %d/%d usable (bar %d) — %s", n, len(DELISTED), PASS_BAR, verdict)
    return {"phase": 2, "results": results, "n": n, "bar": PASS_BAR,
            "verdict": verdict}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", type=int, choices=[1, 2], required=True)
    args = ap.parse_args()
    tok = _token()
    out = phase1(tok) if args.phase == 1 else phase2(tok)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    log.info("Report written: %s", OUT)
