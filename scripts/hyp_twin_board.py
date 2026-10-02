"""Re-score every CRSP library rule against a FAIR twin (2026-09-30).

    python -m scripts.hyp_twin_board --run-id <R>        # ~1 h, resumable (jsonl), $0

The board's matched twin (21 random redraws a month) is charged a full spread round trip every
month; a rule turning over 10-50% a month is charged its own turnover. Tonight's decomposition
(`hyp_investable --part decompose`) found that asymmetry IS the twin drag: the twin basket's
GROSS return is within 0.1-0.2%/mo of the market, and its 100%-turnover cost is 0.6-0.8%/mo.

For every rule the library ran on CRSP (LIB, EVT, BR runs), this prints, beside the board's own
rule - twin21 t (flat run):
- pure selection: rule gross - twin basket gross (no costs either side);
- fair twin: rule net (actual traded weight x max(CS, flat)/2) - (twin basket gross - its own
  actual trade cost) -- the twin held as a portfolio, not redrawn;
- rule net - market (FF mkt+rf, costless).
A transformation of already-run rules: no new rule, no new search count. Descriptive; it
changes what "beats its twin" is allowed to mean, not any verdict against the market.
"""
from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.hyp_investable import (CR_OUT, CS_RUN, OUT, SPLITS, _mem_ok, _now, _write, market_and_rf,  # noqa: E402
                                    run_book, say, spreads_of)

RUNS = {"LIB_2026-09-29T0802Z": "LIB_2026-09-29T0802Z", "EVT_FLAT_2026-09-29T1105Z": "EVT_FLAT_2026-09-29T1105Z",
        "BR_FLAT_2026-09-29T1535Z": "BR_FLAT_2026-09-29T1535Z"}


def carried_picks(hold: list, dates, rule, gate: pd.Series | None) -> dict:
    """{date: symbols} for every decision date: the last rebalance's names carried for at most
    `hold_months` dates; a gated-off date holds nothing."""
    reb = {pd.Timestamp(h["date"]): list(h["symbols"]) for h in hold}
    out, cur, age = {}, None, 0
    hm = max(1, int(rule.hold_months or 1))
    for d in sorted(pd.DatetimeIndex(dates)):
        if d in reb:
            cur, age = reb[d], 0
        elif cur is not None:
            age += 1
            if age >= hm and not rule.rebalance_months:
                cur = None
        if gate is not None and not (gate.get(d, 1.0) > 0):
            continue
        if cur:
            out[d] = cur
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--only", default="")
    a = ap.parse_args(argv)
    if not _mem_ok():
        say("REFUSED: under 3 GB free for 30 minutes")
        return 3
    from backend.services import hyp_investable as HI                # noqa: PLC0415
    from backend.services import strategy_library as SL              # noqa: PLC0415
    from scripts import bridges_on_crsp_run as BR                    # noqa: PLC0415
    jl = OUT / f"twin_board_{a.run_id}.jsonl"
    done = set()
    if jl.exists():
        for ln in jl.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(ln)["rule"])
            except Exception:                                        # noqa: BLE001 -- torn tail
                pass
    todo = []
    for run in RUNS:
        for ln in (CR_OUT / f"library_rules_{run}.jsonl").read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            if r.get("status") == "RUN" and r["rule"] not in done and r["rule"] not in [t[0] for t in todo]:
                todo.append((r["rule"], run))
    if a.only:
        todo = [t for t in todo if t[0] in a.only.split(",")]
    say(f"{len(todo)} rules to score, {len(done)} done")
    t0 = time.time()
    P, _ = BR.load_merged(False)
    P = P.reset_index(drop=True)
    D = pd.read_parquet(CR_OUT / f"followups_daily_{CS_RUN}.parquet", columns=["date", "permno", "cs_spread"])
    D["date"] = pd.to_datetime(D["date"])
    D["symbol"] = D["permno"].map(lambda p: f"{int(p):06d}")
    P = P.merge(D[["date", "symbol", "cs_spread"]].drop_duplicates(["date", "symbol"]), on=["date", "symbol"],
                how="left")
    del D
    P["_sp"] = spreads_of(P)
    P["eligible"] = P["eligible"].astype(bool)
    dates = sorted(P["date"].unique())
    mkt, _rf = market_and_rf(dates)
    rules = {r.id: r for r in SL.rules()}
    say(f"  panel {len(P):,} x {P.shape[1]} {time.time()-t0:.0f}s")
    base = ["date", "symbol", "eligible", "fwd_ret", "median_dollar_vol", "delisted_in_period", "vol_63",
            "mom_252_21", "_sp", "tiebreak"]
    for rid, run in todo:
        tr = time.time()
        rule = rules.get(rid)
        rec = {"rule": rid, "run": run}
        try:
            need = list(dict.fromkeys(base + [c for c in rule.requires if c in P.columns]
                                      + ([rule.regime_gate] if rule.regime_gate else [])))
            Q = P[need]
            hold: list = []
            SL.run_strategy(Q, rule, k=int(rule.k), holdings=hold)
            gate = Q.groupby("date")[rule.regime_gate].first() if rule.regime_gate else None
            pk = carried_picks(hold, dates, rule, gate)
            B = run_book(Q, pk)
            inv = B["gross"].notna()
            B["market"] = mkt.reindex(B.index)
            s_sel = (B["gross"] - B["twin_gross"])[inv]
            s_fair = ((B["gross"] - B["cost"]) - (B["twin_gross"] - B["twin_cost"]))[inv]
            s_mkt = (B["gross"] - B["cost"] - B["market"]).where(inv, 0.0)
            L = pd.read_parquet(CR_OUT / f"library_series_{run}" / f"{rid}.parquet")
            s_board = (L["rule_net"] - L["twin21_net"]).dropna()
            for tag, s in (("board_rule_minus_twin21", s_board), ("pure_selection", s_sel), ("fair_twin", s_fair),
                           ("net_minus_market", s_mkt)):
                rec[tag] = {k: {kk: HI.spread_stats(s, lo, hi)[kk] for kk in ("mean_monthly", "t_blocks", "mde_monthly")}
                            for k, (lo, hi) in {"full": (None, None), **SPLITS}.items()}
            rec.update(family=rule.family, turnover=float(B.loc[inv, "turnover"].mean()),
                       twin_turnover=float(B.loc[inv, "twin_turnover"].mean()),
                       rule_cost_bps=float(B.loc[inv, "cost"].mean() * 1e4),
                       twin_cost_bps=float(B.loc[inv, "twin_cost"].mean() * 1e4), months=int(inv.sum()),
                       status="OK")
        except Exception as e:                                       # noqa: BLE001 -- named per rule
            rec.update(status=f"REFUSED: {type(e).__name__}: {e}")
        rec["seconds"] = round(time.time() - tr, 1)
        with open(jl, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
        f = rec.get("fair_twin", {}).get("full", {})
        b = rec.get("board_rule_minus_twin21", {}).get("full", {})
        say(f"  {rid:42s} board t {b.get('t_blocks')} fair t {f.get('t_blocks')} {rec['status'][:40]} "
            f"{rec['seconds']}s")
        gc.collect()
    rows = [json.loads(ln) for ln in jl.read_text(encoding="utf-8").splitlines() if ln.strip()]
    ok = [r for r in rows if r.get("status") == "OK"]

    def t_of(r, k, w="full"):
        return ((r.get(k) or {}).get(w) or {}).get("t_blocks") or 0.0

    summ = {"n_rules": len(rows), "n_ok": len(ok),
            "board_t_ge_2": sum(t_of(r, "board_rule_minus_twin21") >= 2 for r in ok),
            "fair_t_ge_2": sum(t_of(r, "fair_twin") >= 2 for r in ok),
            "pure_selection_t_ge_2": sum(t_of(r, "pure_selection") >= 2 for r in ok),
            "board_t_ge_2_and_fair_t_ge_2": sum(t_of(r, "board_rule_minus_twin21") >= 2 and t_of(r, "fair_twin") >= 2
                                                for r in ok),
            "net_minus_market_validate_t_ge_2": sum(t_of(r, "net_minus_market", "validate") >= 2 for r in ok),
            "median_board_minus_fair_mean_monthly": float(np.nanmedian(
                [((r["board_rule_minus_twin21"]["full"]["mean_monthly"] or np.nan)
                  - (r["fair_twin"]["full"]["mean_monthly"] or np.nan)) for r in ok])) if ok else None}
    _write(OUT / f"twin_board_SUMMARY_{a.run_id}.json", {"schema": "hyp_lab/twin_board/1", "run_id": a.run_id,
                                                          "written_utc": _now(), "licence": "PRODUCT_EXPERIMENT",
                                                          "llm_spend_usd": 0.0, "summary": summ,
                                                          "seconds": round(time.time() - t0, 1)})
    say(f"-> summary {summ}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
