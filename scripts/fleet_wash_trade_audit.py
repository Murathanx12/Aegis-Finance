"""C27 measurement: every broker 403 "potential wash trade" rejection since 2026-10-01,
and what the rejections cost or saved. Read-only: run receipts + the bars panel.

    python -m scripts.fleet_wash_trade_audit                 # since 2026-10-01
    python -m scripts.fleet_wash_trade_audit --since 2026-10-01

Writes `paper_accounts/fleet_manager/wash_trade_audit_<run_id>.json` (a run id in
the name: a second run never overwrites the first).

WHAT IT MEASURES, per rejected buy (from the run receipt that sent it):
  account, symbol, intended qty and limit, the resting stop at that moment (from
  the same receipt's stop table), and the P&L the frozen contract would have
  earned on that top-up: filled at the intended limit on the session it was
  sent (the limit is ask x 1.001, marketable), protected by ONE stop at
  max(the resting stop, the contract's stop level), held to the newest close in
  the bars panel or stopped out on the first later session whose open or low
  reached the stop (exit at the open on a gap below the stop, else at the stop).
  The session of the attempt is not path-checked intraday (the fill was ~10:45
  ET; the bar does not say whether its low came before or after). Costs: the
  contract's `assumed_bps_per_side` on BOTH sides (entry and exit/mark), as
  `grade_row` charges turnover.

THE DOUBLE-COUNT: a rejected top-up is re-planned at the next open pass with
the same shortfall, so the same missing shares are rejected again. The sum over
every rejection counts one shortfall several times; the honest number is the
FIRST rejection per (account, symbol), which is the headline. Both are printed.

It also counts the names held WITHOUT a full resting stop in the newest
receipt of each pass type, net of a stop the same pass placed for them.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                          # noqa: E402
from backend.services import fleet_manager as FM             # noqa: E402

PANEL = Path(_cfg.OPTIMUS_LEDGER_DIR) / "prices_2025_26" / "bars.parquet"
_EXISTING = re.compile(r"existing_order_id'?\"?:\s*'?\"?([0-9a-f-]{36})")


def rejected_rows(receipts: list[tuple[str, dict]]) -> tuple[list[dict], dict]:
    """[(path, receipt)] -> every LIVE buy the broker rejected, with the resting stop then."""
    rows: list[dict] = []
    tot = {"live_buys_sent": 0, "by_reason": {FM.REJ_WASH: 0, FM.REJ_422: 0, FM.REJ_OTHER: 0},
           "by_pass": {}}
    for path, r in receipts:
        for acc in r.get("accounts") or []:
            if not isinstance(acc, dict):
                continue
            st = {x["symbol"]: x for x in acc.get("stop_table") or []}
            pos = {x["symbol"]: x for x in acc.get("positions") or []}
            day = (acc.get("clock") or {}).get("session_day_et")
            for a in acc.get("actions") or []:
                if a.get("side") != "buy" or a.get("kind") != "buy" or a.get("mode") != "LIVE":
                    continue
                oc = str(a.get("outcome") or "")
                if not oc or oc.startswith("STOP file") or oc.startswith("ALREADY SUBMITTED"):
                    continue
                tot["live_buys_sent"] += 1
                k = FM.classify_rejection(oc)
                key = f"{day} {r.get('pass')}"
                bp = tot["by_pass"].setdefault(key, {"sent": 0, "rejected": 0})
                bp["sent"] += 1
                if not k:
                    continue
                tot["by_reason"][k] += 1
                bp["rejected"] += 1
                row = st.get(a["symbol"]) or {}
                m = _EXISTING.search(oc)
                rows.append({"receipt": Path(path).name, "run_id": r.get("run_id"), "pass": r.get("pass"),
                             "session": day, "role": acc.get("role"), "symbol": a["symbol"], "qty": int(a["qty"]),
                             "limit": a.get("limit"), "reason": k, "coid": a.get("coid"),
                             "existing_order_id": m.group(1) if m else None,
                             "held_qty": (pos.get(a["symbol"]) or {}).get("qty"),
                             "price": row.get("price") or (pos.get(a["symbol"]) or {}).get("price"),
                             "target_stop_frac": row.get("target_stop_frac"),
                             "resting_stop": [{"stop_price": float(x["stop_price"]), "qty": float(x["qty"]),
                                               "client_order_id": x.get("client_order_id"),
                                               "expires_at": x.get("expires_at")}
                                              for x in row.get("resting") or []],
                             "outcome": oc[:200]})
    return rows, tot


def path_return(entry_day: str, entry_px: float, stop: Optional[float], bars: list[dict],
                cost_bps_side: float) -> dict:
    """Bars are [{date, open, low, close}] ascending. Fill at `entry_px` on
    `entry_day`; from the NEXT session on, exit at the open when it gaps below
    the stop, else at the stop when the low reaches it; otherwise mark at the
    newest close. Net of `cost_bps_side` on both sides."""
    after = [b for b in bars if b["date"] > entry_day]
    same = [b for b in bars if b["date"] == entry_day]
    exit_px, exit_day, how = None, None, "mark"
    for b in after:
        if stop is not None and b["open"] <= stop:
            exit_px, exit_day, how = b["open"], b["date"], "gap below stop: exit at the open"
            break
        if stop is not None and b["low"] <= stop:
            exit_px, exit_day, how = stop, b["date"], "stopped at the stop"
            break
    if exit_px is None:
        last = (after or same or [None])[-1]
        if last is None:
            return {"gross": None, "net": None, "how": "no bar on or after the entry session"}
        exit_px, exit_day = last["close"], last["date"]
    gross = exit_px / entry_px - 1.0
    net = gross - 2 * cost_bps_side / 1e4
    return {"exit_px": round(exit_px, 4), "exit_day": exit_day, "how": how,
            "gross": round(gross, 6), "net": round(net, 6)}


def load_bars(symbols: list[str], since: str) -> tuple[dict[str, list[dict]], Optional[str]]:
    import pandas as pd
    df = pd.read_parquet(PANEL, columns=["symbol", "date", "open", "low", "close"],
                         filters=[("symbol", "in", sorted(set(symbols)))])
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df[df["date"] >= since].sort_values(["symbol", "date"])
    out = {s: g[["date", "open", "low", "close"]].to_dict("records") for s, g in df.groupby("symbol")}
    return out, (df["date"].max() if len(df) else None)


def unprotected_now(receipts: list[tuple[str, dict]]) -> list[dict]:
    """Newest receipt of each pass type: held long names whose resting stops do not
    cover the quantity, net of a stop that same pass placed (LIVE, submitted)."""
    out = []
    for which in ("open", "preclose"):
        cand = [(p, r) for p, r in receipts if r.get("pass") == which]
        if not cand:
            continue
        p, r = cand[-1]
        for acc in r.get("accounts") or []:
            if not isinstance(acc, dict):
                continue
            placed = {}
            for a in (acc.get("actions") or []) + (acc.get("entry_protection") or []):
                if a.get("type") == "stop" and a.get("mode") == "LIVE" and "submitted" in str(a.get("outcome")):
                    placed[a["symbol"]] = placed.get(a["symbol"], 0) + int(a.get("qty") or 0)
            for x in acc.get("stop_table") or []:
                cov = sum(float(y["qty"]) for y in x.get("resting") or [])
                gap = float(x["qty"]) - cov - placed.get(x["symbol"], 0)
                if gap > 1e-9:
                    out.append({"receipt": Path(p).name, "pass": which, "role": acc.get("role"),
                                "symbol": x["symbol"], "qty": x["qty"], "covered_resting": cov,
                                "placed_this_pass": placed.get(x["symbol"], 0), "uncovered": gap})
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-10-01")
    a = ap.parse_args(argv)
    runs = FM.root() / "runs"
    ymd = a.since.replace("-", "")
    paths = sorted(p for p in glob.glob(str(runs / "run_*.json")) if Path(p).name[4:12] >= ymd)
    receipts = [(p, json.loads(Path(p).read_text(encoding="utf-8"))) for p in paths]
    rows, tot = rejected_rows(receipts)
    cost = float(FM.costs_block()["assumed_bps_per_side"])
    bars, newest = load_bars([r["symbol"] for r in rows], a.since) if rows else ({}, None)
    for r in rows:
        old = max([x["stop_price"] for x in r["resting_stop"]] or [0.0]) or None
        cl = FM.stop_price_for(float(r["price"]), float(r["target_stop_frac"])) \
            if r.get("price") and r.get("target_stop_frac") else None
        sp = max(x for x in (old, cl) if x is not None) if (old or cl) else None
        r["combined_stop"] = sp
        pr = path_return(r["session"], float(r["limit"]), sp, bars.get(r["symbol"]) or [], cost)
        r.update(pr)
        r["intended_notional"] = round(r["qty"] * float(r["limit"]), 2)
        r["pnl_usd_net"] = round(r["intended_notional"] * pr["net"], 2) if pr.get("net") is not None else None
    first: dict[tuple, dict] = {}
    for r in rows:
        first.setdefault((r["role"], r["symbol"]), r)
    dedup = list(first.values())

    def agg(rs: list[dict]) -> dict:
        ok = [x for x in rs if x.get("pnl_usd_net") is not None]
        by_role: dict[str, dict] = {}
        for x in ok:
            d = by_role.setdefault(x["role"], {"n": 0, "notional": 0.0, "pnl_usd_net": 0.0})
            d["n"] += 1
            d["notional"] = round(d["notional"] + x["intended_notional"], 2)
            d["pnl_usd_net"] = round(d["pnl_usd_net"] + x["pnl_usd_net"], 2)
        n_ = sum(x["intended_notional"] for x in ok)
        p_ = sum(x["pnl_usd_net"] for x in ok)
        return {"n": len(rs), "n_priced": len(ok), "notional_usd": round(n_, 2), "pnl_usd_net": round(p_, 2),
                "return_on_notional_net": round(p_ / n_, 6) if n_ else None,
                "n_stopped": sum(1 for x in ok if x.get("how") != "mark"), "by_role": by_role}

    unp = unprotected_now(receipts)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-{hashlib.sha256(json.dumps(paths).encode()).hexdigest()[:6]}"
    n_rej = sum(tot["by_reason"].values())
    out: dict[str, Any] = {
        "schema": "fleet_wash_trade_audit/1", "run_id": run_id, "written_utc": FM._now_iso(),
        "licence": FM.LICENCE, "places_orders": False, "since": a.since,
        "receipts": [Path(p).name for p in paths],
        "broker_rule": {"url": FM.WASH_RULE_URL, "quote": FM.WASH_RULE_QUOTE},
        "live_buys_sent": tot["live_buys_sent"], "rejected": n_rej, "by_reason": tot["by_reason"],
        "by_pass": tot["by_pass"],
        "every_rejection_is_a_topup_with_a_resting_stop": all(r["resting_stop"] for r in rows),
        "pnl_method": ("fill at the intended limit on the attempt session; ONE stop at max(resting stop, contract "
                       "level at the reference price); from the next session, exit at the open on a gap below the "
                       "stop, else at the stop when the low reaches it, else mark at the newest panel close; "
                       f"{cost:g} bps per side on both sides (the contract's costs_block)"),
        "panel": str(PANEL.relative_to(REPO)) if PANEL.is_relative_to(REPO) else str(PANEL),
        "panel_newest_close": newest,
        "headline_first_rejection_per_name": agg(dedup),
        "every_rejection_double_counts": agg(rows),
        "unprotected_now": {"n": len(unp), "rows": unp,
                            "note": "held long names whose resting stops do not cover the quantity in the newest "
                                    "receipt of each pass, net of a stop that same pass placed"},
        "rows": rows,
    }
    p = FM.root() / f"wash_trade_audit_{run_id}.json"
    FM.atomic_write_json(p, out)
    h = out["headline_first_rejection_per_name"]
    e = out["every_rejection_double_counts"]
    print(f"LIVE buys sent since {a.since}: {tot['live_buys_sent']}; rejected {n_rejected_line(tot)}")
    print(f"first rejection per (account, symbol): {h['n']} names, notional ${h['notional_usd']:,.0f}, "
          f"net P&L had they filled ${h['pnl_usd_net']:,.2f} ({(h['return_on_notional_net'] or 0):+.2%} on "
          f"notional, {h['n_stopped']} stopped) to the close of {newest}")
    print(f"every rejection (double-counts the same shortfall): {e['n']}, ${e['pnl_usd_net']:,.2f}")
    for role, d in sorted(h["by_role"].items()):
        print(f"  {role}: {d['n']} names, notional ${d['notional']:,.0f}, net ${d['pnl_usd_net']:,.2f}")
    print(f"held without a full resting stop (newest receipts, net of stops placed): {len(unp)} "
          f"{[(u['role'], u['symbol'], u['uncovered']) for u in unp]}")
    print(f"receipt: {p}")
    return 0


def n_rejected_line(tot: dict) -> str:
    b = tot["by_reason"]
    return (f"{sum(b.values())} ({b[FM.REJ_WASH]} wash-trade 403, {b[FM.REJ_422]} 422, {b[FM.REJ_OTHER]} other); "
            f"by pass {tot['by_pass']}")


if __name__ == "__main__":
    sys.exit(main())
