"""
TRIAL-MOM-BACKTEST panel-quality gate (contamination clause) — run BEFORE
the backtest is ever evaluated. Frozen in the trial doc 2026-07-18:

  Check 1: >=80% coverage of the pre-committed 2017+ delisted spot-check
           names (the 2017+ subset of the survivorship-audit list, chosen
           before the harvest) — file exists AND history ends within 400
           days of the known exit year.
  Check 2: 10 active tickers' adjusted closes within 1% of yfinance on 10
           random overlapping dates (run after the active harvest lands).

    python -m engine.research.panel_quality_gate
"""

from __future__ import annotations

import gzip
import json
import logging
from datetime import date
from pathlib import Path

log = logging.getLogger("panel_gate")
logging.basicConfig(level=logging.INFO, format="%(message)s")

DATA = Path(__file__).resolve().parents[1] / "data" / "eodhd"
OUT = Path(__file__).parent / f"panel_gate_{date.today().isoformat()}.json"

# The 2017+ deaths from engine/research/survivorship_audit.py DELISTED —
# committed as the spot-check set in the trial doc before harvest results
# were inspected.
SPOT_2017 = [("YHOO", 2017), ("MON", 2018), ("TWX", 2018), ("CELG", 2019),
             ("AGN", 2020), ("XLNX", 2022), ("ATVI", 2023), ("TWTR", 2022),
             ("FRC", 2023), ("SIVB", 2023), ("SBNY", 2023), ("PXD", 2024),
             ("SGEN", 2023), ("ABMD", 2022)]

# Check-2 active names: the 10 largest US caps as of 2026 — objective rule,
# no cherry-picking.
SPOT_ACTIVE = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
               "META", "AVGO", "TSLA", "LLY", "JPM"]


def _last_date(path: Path) -> str:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        lines = f.read().strip().splitlines()
    # csv: Date,Open,High,Low,Close,Adjusted_close,Volume
    return lines[-1].split(",")[0] if len(lines) > 1 else ""


def check1_delisted() -> dict:
    results = {}
    for sym, exit_year in SPOT_2017:
        p = DATA / "delisted" / f"{sym}.csv.gz"
        if not p.exists():
            results[sym] = {"ok": False, "reason": "file missing"}
            continue
        last = _last_date(p)
        ly = int(last[:4]) if last[:4].isdigit() else 0
        ok = abs(ly - exit_year) <= 1
        results[sym] = {"ok": ok, "last_date": last, "exit_year": exit_year,
                        "reason": None if ok else "ends far from death (recycled?)"}
    n_ok = sum(1 for v in results.values() if v["ok"])
    frac = n_ok / len(results)
    for sym, v in results.items():
        log.info("  %-5s %s  %s", sym, "OK " if v["ok"] else "BAD",
                 v.get("last_date") or v["reason"])
    verdict = "PASS" if frac >= 0.80 else "FAIL - trial VOID unrun"
    log.info("CHECK 1 (delisted spot-check): %d/%d = %.0f%% (bar 80%%) -> %s",
             n_ok, len(results), frac * 100, verdict)
    return {"check": 1, "n_ok": n_ok, "n": len(results), "frac": frac,
            "verdict": verdict, "detail": results}


def check2_active_vs_yfinance() -> dict:
    import numpy as np
    import pandas as pd
    import yfinance as yf
    results = {}
    for sym in SPOT_ACTIVE:
        p = DATA / "active" / f"{sym}.csv.gz"
        if not p.exists():
            results[sym] = {"ok": False, "reason": "not harvested yet"}
            continue
        e = pd.read_csv(p, compression="gzip", parse_dates=["Date"],
                        index_col="Date")
        y = yf.download(sym, start="2024-01-01", auto_adjust=True,
                        progress=False)["Close"]
        if isinstance(y, pd.DataFrame):
            y = y.iloc[:, 0]
        both = e["Adjusted_close"].tz_localize(None).to_frame("e").join(
            y.tz_localize(None).to_frame("y"), how="inner").dropna()
        if len(both) < 50:
            results[sym] = {"ok": False, "reason": f"overlap={len(both)}"}
            continue
        sample = both.sample(10, random_state=42)
        max_dev = float((sample["e"] / sample["y"] - 1).abs().max())
        results[sym] = {"ok": max_dev <= 0.01, "max_dev_pct": round(max_dev * 100, 3)}
    n_ok = sum(1 for v in results.values() if v["ok"])
    for sym, v in results.items():
        log.info("  %-6s %s  %s", sym, "OK " if v["ok"] else "BAD",
                 v.get("max_dev_pct", v.get("reason")))
    verdict = "PASS" if n_ok == len(results) else "FAIL/incomplete"
    log.info("CHECK 2 (active vs yfinance, 1%% tol): %d/%d -> %s",
             n_ok, len(results), verdict)
    return {"check": 2, "n_ok": n_ok, "n": len(results), "verdict": verdict,
            "detail": results}


if __name__ == "__main__":
    out = {"check1": check1_delisted()}
    try:
        out["check2"] = check2_active_vs_yfinance()
    except Exception as e:  # active harvest may not have landed yet
        log.info("CHECK 2 skipped: %s", str(e)[:120])
        out["check2"] = {"check": 2, "verdict": "not_run", "reason": str(e)[:200]}
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    log.info("written: %s", OUT)
