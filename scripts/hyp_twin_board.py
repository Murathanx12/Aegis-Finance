"""The FAIR-TWIN board: every CRSP library rule against its matched twin under ONE cost
convention (2026-09-30; shared-code fix 2026-10-06, CHUNK C1 of ROADMAP_2026-10-06_V1_BETA).

    python -m scripts.hyp_twin_board --run-id <R>        # ~30 min, resumable (jsonl), $0

The 09-29/09-30 bridges board charged the matched twin a full Corwin-Schultz round trip
every month while the rule paid only its own measured turnover; that asymmetry WAS the twin
drag. This board is the one implementation of `matched_twins.twin_cost_convention()`:

- the rule: its library picks (`strategy_library.run_strategy` holdings, carried for the
  hold), equal weight, charged `matched_twins.trade_cost` on its own traded weight at the
  per-name round trip max(Corwin-Schultz at the decision date (cap 20%), flat band);
- the twin: the matched twin BASKET (selection's size x vol x 12-1 cell mix over every
  non-selected eligible name in those cells -- the infinite-draw twin), HELD as a portfolio,
  charged the SAME `trade_cost` on its OWN traded weight;
- market: FF mkt + rf compounded over the hold, costless. A gated-off month after the rule's
  first position holds cash (earns 0) and is read against the market as such.

Every row prints the four `matched_twins.FOUR_COLUMNS` side by side (pure selection, fair
twin, net minus market, and the full-round-trip twin as a labelled UPPER BOUND no verdict
reads), each on full / design / validate / late / 1991-2016 windows with t on 3-month blocks
and the MDE, plus by hold year and leave-one-year-out for the fair twin and the market line.
The board's own flat-run rule - twin21 is kept beside as `board_rule_minus_twin21_flat`.

A transformation of already-run rules: no new rule, no new search count. Receipts carry the
run id in their name and are never overwritten: `hyp_lab/twin_board_<R>.jsonl`,
`hyp_lab/fair_twin_series_<R>/<rule>.parquet`, `hyp_lab/twin_board_SUMMARY_<R>.json`.
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


#: windows every column is read on (hold month); 1991-2016 is the bridges board's t window
WINDOWS = {"full": (None, None), **SPLITS, "design_validate": ("1991-01-01", "2016-12-31")}
SCHEMA = "hyp_lab/twin_board/2"


def fair_series(B: pd.DataFrame, market: pd.Series) -> pd.DataFrame:
    """`run_book` frame -> the monthly frame every board row reads: the inputs and the four
    `MT.FOUR_COLUMNS`. Months before the rule's first position are dropped; after it, a
    month with no position holds cash (gross 0, the exit trade still charged)."""
    from backend.services import matched_twins as MT                 # noqa: PLC0415
    inv = B["gross"].notna()
    if not inv.any():
        raise MT.TwinInputMissing("the rule never held a position on this panel")
    B = B.loc[B.index >= B.index[inv.to_numpy()][0]].copy()
    inv = B["gross"].notna()
    for c in ("cost", "twin_cost", "twin_turnover", "twin_full_rt"):
        if c not in B.columns or B[c].isna().any():
            raise MT.TwinInputMissing(f"run_book frame lacks a complete {c!r} column")
    mk = market.reindex(B.index)
    rg = B["gross"].where(inv, 0.0)
    tg = B["twin_gross"].where(inv)
    F = MT.four_columns(rg, B["cost"], tg, B["twin_cost"], B["twin_full_rt"], mk)
    for c in (MT.FOUR_COLUMNS[0], MT.FOUR_COLUMNS[1], MT.FOUR_COLUMNS[3]):
        F[c] = F[c].where(inv)                       # twin legs exist only while the rule holds
    out = pd.concat([B[["gross", "cost", "turnover", "twin_gross", "twin_cost", "twin_turnover", "twin_full_rt"]],
                     mk.rename("market"), inv.rename("invested"), F], axis=1)
    out.attrs["cost_convention"] = MT.TWIN_COST_CONVENTION
    return out


def column_stats(s: pd.Series, *, by_year: bool) -> dict:
    """Window stats of one column; by hold year and leave-one-year-out when asked (always
    for the fair twin and the market line, so a positive cell carries them)."""
    from backend.services import calendar_offsets as CO              # noqa: PLC0415
    from backend.services import crsp_rebuild as CR                  # noqa: PLC0415
    s = s.dropna()
    out = {k: CR.window_stats(s, lo, hi) for k, (lo, hi) in WINDOWS.items()}
    if by_year and len(s):
        out["by_hold_year"] = {y: round(v["sum"], 5) for y, v in CO.by_hold_year(s).items()}
        lw = CO.loo_worst(s)
        out["loo_worst"] = {"worst": lw["worst"], "dropped_year": lw["dropped_year"]}
    return out


def fair_row(S: pd.DataFrame, board: pd.Series | None = None) -> dict:
    """One board row: all four columns side by side (+ the old flat board line)."""
    from backend.services import matched_twins as MT                 # noqa: PLC0415
    inv = S["invested"].astype(bool)
    row = {"cost_convention": MT.TWIN_COST_CONVENTION, "four_columns": list(MT.FOUR_COLUMNS),
           "upper_bound_column_never_in_verdicts": MT.UPPER_BOUND_COLUMN}
    for c in MT.FOUR_COLUMNS:
        row[c] = column_stats(S[c], by_year=c in ("fair_twin_net", "net_minus_market"))
    if board is not None:
        row["board_rule_minus_twin21_flat"] = column_stats(board, by_year=False)
    row.update(turnover=float(S.loc[inv, "turnover"].mean()), twin_turnover=float(S.loc[inv, "twin_turnover"].mean()),
               rule_cost_bps=float(S.loc[inv, "cost"].mean() * 1e4),
               twin_cost_bps=float(S.loc[inv, "twin_cost"].mean() * 1e4),
               twin_full_rt_bps_UPPER_BOUND=float(S.loc[inv, "twin_full_rt"].mean() * 1e4),
               months=int(inv.sum()), first_month=str(S.index.min().date()))
    return row


def t_of(r: dict, k: str, w: str = "full") -> float:
    return ((r.get(k) or {}).get(w) or {}).get("t_blocks") or 0.0


def m_of(r: dict, k: str, w: str = "full") -> float:
    return ((r.get(k) or {}).get(w) or {}).get("mean_monthly") or 0.0


def summarise(ok: list) -> dict:
    """Counts the reissue reads. `beats_fair_twin_and_market_validate` is the headline."""
    return {"n_ok": len(ok),
            "pure_selection_t_ge_2": sum(t_of(r, "pure_selection") >= 2 for r in ok),
            "fair_twin_t_ge_2": sum(t_of(r, "fair_twin_net") >= 2 for r in ok),
            "upper_bound_twin_t_ge_2": sum(t_of(r, "twin_full_round_trip_UPPER_BOUND") >= 2 for r in ok),
            "board_flat_rule_minus_twin21_t_ge_2": sum(t_of(r, "board_rule_minus_twin21_flat") >= 2 for r in ok),
            "net_minus_market_validate_t_ge_2": sum(t_of(r, "net_minus_market", "validate") >= 2 for r in ok),
            "beats_fair_twin_and_market_validate": sorted(
                r["rule"] for r in ok if t_of(r, "fair_twin_net") >= 2
                and t_of(r, "net_minus_market", "validate") >= 2),
            "fair_twin_and_pure_selection_t_ge_2": sorted(
                r["rule"] for r in ok if t_of(r, "fair_twin_net") >= 2 and t_of(r, "pure_selection") >= 2),
            "beats_fair_twin_and_selection_and_market_validate": sorted(
                r["rule"] for r in ok if t_of(r, "fair_twin_net") >= 2 and t_of(r, "pure_selection") >= 2
                and t_of(r, "net_minus_market", "validate") >= 2),
            "median_twin_turnover_minus_rule_turnover": float(np.nanmedian(
                [(r.get("twin_turnover") or np.nan) - (r.get("turnover") or np.nan) for r in ok])) if ok else None,
            "beats_fair_twin_1991_2016_and_market_validate": sorted(
                r["rule"] for r in ok if t_of(r, "fair_twin_net", "design_validate") >= 2
                and t_of(r, "net_minus_market", "validate") >= 2),
            "median_upper_bound_minus_fair_mean_monthly": float(np.nanmedian(
                [m_of(r, "twin_full_round_trip_UPPER_BOUND") - m_of(r, "fair_twin_net") for r in ok])) if ok else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--only", default="")
    a = ap.parse_args(argv)
    from backend.services import matched_twins as MT                 # noqa: PLC0415
    from backend.services import strategy_library as SL              # noqa: PLC0415
    jl = OUT / f"twin_board_{a.run_id}.jsonl"
    summ_p = OUT / f"twin_board_SUMMARY_{a.run_id}.json"
    if summ_p.exists():
        say(f"REFUSED: {summ_p.name} exists (a run id is written once)")
        return 2
    if not _mem_ok():
        say("REFUSED: under 3 GB free for 30 minutes; nothing was scored")
        return 3
    from scripts import bridges_on_crsp_run as BR                    # noqa: PLC0415
    sdir = OUT / f"fair_twin_series_{a.run_id}"
    sdir.mkdir(parents=True, exist_ok=True)
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
    say(f"{len(todo)} rules to score, {len(done)} done; convention {MT.TWIN_COST_CONVENTION}")
    t0 = time.time()
    if todo:
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
            S = fair_series(run_book(Q, pk), mkt)
            S.to_parquet(sdir / f"{rid}.parquet")
            L = pd.read_parquet(CR_OUT / f"library_series_{run}" / f"{rid}.parquet")
            rec.update(family=rule.family, **fair_row(S, (L["rule_net"] - L["twin21_net"]).dropna()), status="OK")
        except Exception as e:                                       # noqa: BLE001 -- named per rule
            rec.update(status=f"REFUSED: {type(e).__name__}: {e}")
        rec["seconds"] = round(time.time() - tr, 1)
        with open(jl, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
        say(f"  {rid:42s} sel t {_r(t_of(rec, 'pure_selection'))} fair t {_r(t_of(rec, 'fair_twin_net'))} "
            f"UB t {_r(t_of(rec, 'twin_full_round_trip_UPPER_BOUND'))} mktV t "
            f"{_r(t_of(rec, 'net_minus_market', 'validate'))} {rec['status'][:40]} {rec['seconds']}s")
        gc.collect()
    rows = [json.loads(ln) for ln in jl.read_text(encoding="utf-8").splitlines() if ln.strip()]
    ok = [r for r in rows if r.get("status") == "OK"]
    refused = [r["rule"] for r in rows if r.get("status") != "OK"]
    summ = {"n_rules": len(rows), "n_refused": len(refused), "refused": refused, **summarise(ok)}
    _write(summ_p, {"schema": SCHEMA, "run_id": a.run_id, "written_utc": _now(), "licence": "PRODUCT_EXPERIMENT",
                    "status": "OK" if not refused else f"PARTIAL: {len(refused)} rules refused (named)",
                    "cost_convention": MT.TWIN_COST_CONVENTION, "cost_convention_doc": MT.twin_cost_convention.__doc__,
                    "four_columns": list(MT.FOUR_COLUMNS), "windows": WINDOWS, "llm_spend_usd": 0.0,
                    "supersedes_for_twin_reads": "twin_board_SUMMARY_TB_2026-09-30_1.json (schema 1)",
                    "summary": summ, "seconds": round(time.time() - t0, 1)})
    say(f"-> summary {summ}")
    return 0


def _r(x) -> str:
    return f"{x:+.2f}"


if __name__ == "__main__":
    raise SystemExit(main())
