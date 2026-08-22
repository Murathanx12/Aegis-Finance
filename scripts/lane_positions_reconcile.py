"""One-command lane reconciliation — runs the moment positions data exists.

Two ways in (first that works wins):
  1. After the branch merges:  --from-prod   GETs
     /api/pi/lane/{id}/positions for mirror + conviction.
  2. Before the merge: Murat exports the two tables however he likes and
     passes --from-file <path.json> with the same shape
     ({"lane_id":..., "positions":[{ticker,shares,cost_basis}...],
       "rebalance_events":[...]}) — the attended read shrinks to producing
     that file.

What it then does, with no further decisions:
  - schema-verifies (missing columns REFUSE);
  - reprices the positions at yesterday's close (yfinance) and compares
    against the lane's authoritative latest NAV — a mismatch beyond
    tolerance means the positions table and the NAV book disagree, which
    is itself the finding;
  - correlates the positions-book daily returns against the authoritative
    NAV series (the decision-log reconstruction found the conviction lane
    tracks balanced-ew-control at +0.60 and its own decision log at +0.19
    — this run replaces those proxies with the real book);
  - writes docs/conviction_replay/positions_reconciliation_<date>.json.

It asserts nothing about skill and never writes to prod.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

PROD = "https://aegis-finance-production.up.railway.app"
LANES = ("mirror", "conviction")
OUT_DIR = REPO / "docs" / "conviction_replay"
TOL_PCT = 2.0        # same declared tolerance as lane_autopsy_cross_arms


class ReadRefused(RuntimeError):
    pass


def load_prod(lane: str) -> dict:
    import requests
    r = requests.get(f"{PROD}/api/pi/lane/{lane}/positions", timeout=60)
    if r.status_code == 404:
        raise ReadRefused(
            f"{lane}: endpoint 404 — the branch with "
            f"/api/pi/lane/{{id}}/positions has not deployed yet; use "
            f"--from-file, or merge first")
    r.raise_for_status()
    return r.json()


def verify(payload: dict) -> dict:
    for k in ("lane_id", "positions", "rebalance_events"):
        if k not in payload:
            raise ReadRefused(f"payload missing {k!r} — refusing to "
                              f"reconcile a partial read")
    for p in payload["positions"]:
        if not {"ticker", "shares"} <= set(p):
            raise ReadRefused(f"position row missing ticker/shares: {p}")
    return payload


def reconcile(payload: dict) -> dict:
    import yfinance as yf
    lane = payload["lane_id"]
    pos = pd.DataFrame(payload["positions"])
    out: dict = {"lane": lane, "n_positions": int(len(pos)),
                 "n_rebalance_events": len(payload["rebalance_events"])}
    if pos.empty:
        out["status"] = ("EMPTY BOOK — the lane's NAV is marking nothing? "
                         "That is the finding; escalate")
        return out

    tickers = sorted(pos["ticker"].unique())
    px = yf.download(tickers, period="3mo", auto_adjust=True,
                     progress=False)["Close"]
    if isinstance(px, pd.Series):
        px = px.to_frame(tickers[0])
    missing = [t for t in tickers if t not in px.columns
               or px[t].dropna().empty]
    out["excluded_no_prices"] = missing
    live = [t for t in tickers if t not in missing]
    shares = pos.set_index("ticker")["shares"]
    equity = (px[live] * shares[live]).sum(axis=1).dropna()
    out["equity_at_last_close"] = round(float(equity.iloc[-1]), 2)

    # authoritative NAV
    import requests
    tr = requests.get(f"{PROD}/api/pi/track-record", timeout=90).json()
    nav_rows = tr["lanes"].get(lane, [])
    nav = pd.Series({r["date"]: r["value"] for r in nav_rows}, dtype=float)
    nav.index = pd.to_datetime(nav.index)
    if nav.empty:
        out["status"] = "no authoritative NAV rows for this lane"
        return out
    out["nav_latest"] = float(nav.iloc[-1])
    gap_pct = (out["equity_at_last_close"] / out["nav_latest"] - 1) * 100
    out["equity_vs_nav_gap_pct"] = round(gap_pct, 2)
    out["gap_note"] = ("gap includes CASH the positions table does not "
                       "carry — a stable small gap is cash; a LARGE or "
                       "drifting gap is the finding")

    joined = pd.concat([nav.pct_change().rename("nav"),
                        equity.pct_change().rename("book")],
                       axis=1, join="inner").dropna()
    if len(joined) > 5:
        out["daily_return_corr_lag0"] = round(
            float(joined["nav"].corr(joined["book"])), 4)
        # GAP_RESOLUTION_2026-08-19: NAV rows before the stamp-semantics flip
        # lag closes by one day (stamp=run date, price=last completed bar).
        # P-day-2026-08-19a SHIPPED 2026-08-22 (config.PI_NAV_PRICED_DATE_FROM
        # = 2026-08-23): rows from that date are stamped with the bar that
        # priced them, so the aligned comparison is lag-1 BEFORE the flip and
        # lag-0 FROM it. While the history is mostly pre-flip rows, lag1 stays
        # the headline; as post-flip rows accumulate, lag0 overtaking lag1 is
        # the fix WORKING, not drift.
        out["daily_return_corr_lag1_aligned"] = round(
            float(joined["nav"].corr(joined["book"].shift(1))), 4)
        out["nav_stamp_flip_date"] = "2026-08-23"
        out["corr_note"] = ("rows before 2026-08-23 lag closes one day "
                            "(lag1 is their aligned read, measured 0.974 "
                            "conviction / 0.78 mirror on 08-19); rows from "
                            "2026-08-23 are bar-dated (lag0 aligned) — "
                            "expect lag0 to overtake lag1 as post-flip "
                            "history accumulates")
    out["within_declared_tolerance"] = bool(abs(gap_pct) <= TOL_PCT)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lane_positions_reconcile")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-prod", action="store_true")
    src.add_argument("--from-file", type=Path)
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    results = []
    if a.from_file:
        payload = json.loads(a.from_file.read_text(encoding="utf-8"))
        payloads = payload if isinstance(payload, list) else [payload]
        for p in payloads:
            results.append(reconcile(verify(p)))
    else:
        for lane in LANES:
            results.append(reconcile(verify(load_prod(lane))))

    for r in results:
        print(json.dumps(r, indent=2))
    out = OUT_DIR / f"positions_reconciliation_{date.today().isoformat()}.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nreceipt: {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
