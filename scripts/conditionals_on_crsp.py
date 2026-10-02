"""Conditional (situational) questions on CRSP 1991-2024: a small pre-declared list (2026-09-30).

    python -m scripts.conditionals_on_crsp --part declare --run-id <id>   # cells + decision rule, hashed
    python -m scripts.conditionals_on_crsp --part run --declaration <id>  # every cell, once

Licence `PRODUCT_EXPERIMENT`, $0, no LLM, no network. Nothing is traded.

WHY: the mission says a global negative does not answer a conditional question
that was never asked. The library boards (2026-09-29/30) are global: one rule,
every month, every name. This asks ten situational questions where the
project has prior reason, each defined BEFORE any number was read, each read
once, with one decision rule:

  CANDIDATE iff, in VALIDATE (hold months 2009-2016), the cell's net return
  minus the market has mean > 0, t >= 2 on 3-month blocks and >= 5 of 8 years
  positive; AND in DESIGN (the source's first month .. 2008) the net-minus-market
  mean is > 0 and the gross-minus-twin mean is > 0. Otherwise CANNOT_DISTINGUISH
  when the validate net-minus-market mean is > 0, FAILED_VARIANT when it is <= 0.
  A CANDIDATE with DSR < 0.95 at the full search count is flagged
  NOT_DEFLATED_SURVIVOR: registration-eligible as a free forward shadow
  (PRODUCT_EXPERIMENT), never a claim.

THE ENGINE (the same for every cell, fixed before any read):
* monthly decision on the CRSP month-end panel; hold one month; names that
  meet the condition AND are eligible, equal weight; a month with fewer than
  MIN_NAMES names holds the MARKET (difference 0 vs the market, NaN vs twin);
* the matched twin is the cell-mean of NON-selected eligible names in the same
  size band x vol_63 tercile x 12-1 tercile cell (`matched_twins` cells),
  weighted by the selection's cell mix: the infinite-draw version of the
  21-draw twin; it is read GROSS vs GROSS (the information in the selection),
  because a twin that pays the same turnover pays the same cost;
* costs: each traded weight |w_t - w_{t-1}| pays half the name's spread, the
  spread being max(Corwin-Schultz at the decision date (cap 20%), the flat
  6/10/18/35 bps band); era-realistic and scaled by ACTUAL turnover;
* market = CRSP-era FF market + rf compounded over the hold, costless.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

JOB = "conditionals_on_crsp"
OPT = REPO / "backend" / "data" / "optimus"
OUT = OPT / "crsp_rebuild"
MIN_NAMES = 5
CS_CAP = 0.20
SPLITS = {"design": ("1991-01-01", "2008-12-31"), "validate": ("2009-01-01", "2016-12-31"),
          "holdout": ("2017-01-01", "2024-12-31"), "full": (None, None)}

#: the cells, declared before any read. `when` is the first decision date the inputs allow.
CELLS = {
    "C01_surprise_then_raises": {
        "question": "does revision flow right after a positive earnings surprise carry the drift?",
        "condition": "days_since_earn <= 45 AND ear_last in the top 30% of the month AND net_raises_30 >= 1",
        "when": "1999-09-30", "prior": "ear_flow was the best single rule of 2026-09-29 (twin t 3.9)"},
    "C02_insider_cluster_after_drawdown": {
        "question": "do 3+ distinct insiders buying within 30 days after a large drawdown predict recovery?",
        "condition": "distinct open-market insider buyers with filings usable in (d-30, d] >= 3 AND "
                     "px_vs_52w_high <= -0.40",
        "when": "2006-06-30", "prior": "Cohen-Malloy-Pomorski; TRIAL-DRAFT-B (cluster length) is a different "
                                       "definition and is not run under its name"},
    "C03_squeeze_with_rising_estimates": {
        "question": "do heavily shorted names with rising price targets squeeze?",
        "condition": "si_ratio in the top 10% of the month AND net_raises >= 1 AND mom_21 > 0",
        "when": "1999-09-30", "prior": "short-squeeze folklore; NEGATIVE_RESULTS §24 closed si_chg net of turnover"},
    "C04_concentrated_13f_initiation": {
        "question": "does a new position by a concentrated fund (3-25 names) carry information?",
        "condition": "n_conc_init >= 1 (a manager holding 3-25 names initiated the position last quarter)",
        "when": "1996-08-30", "prior": "Cohen-Polk-Silli best ideas; conviction of concentrated managers"},
    "C05_raise_in_low_coverage": {
        "question": "are target raises more informative where few analysts look?",
        "condition": "net_raises >= 1 AND n_firms <= 2 (at most two brokers active in 90 days)",
        "when": "1999-09-30", "prior": "Hong-Lim-Stein slow diffusion in low-coverage names"},
    "C06_raises_trend_on": {
        "question": "does the revision signal work when the market trend is up?",
        "condition": "net_raises in the top 20% of covered names (net_raises >= 1) AND mkt_trend_up == 1; "
                     "otherwise the market",
        "when": "1999-09-30", "prior": "regime gating; revision flow is the one consistent relative signal"},
    "C07_raises_trend_off": {
        "question": "does the revision signal work when the market trend is down?",
        "condition": "as C06 but mkt_trend_up == 0; otherwise the market",
        "when": "1999-09-30", "prior": "the complement of C06"},
    "C08_raises_high_vol": {
        "question": "does the revision signal work in a high-volatility market?",
        "condition": "as C06's selection, months where the market's 63-session realised vol at d is above its "
                     "trailing 5-year median; otherwise the market",
        "when": "1999-09-30", "prior": "information is slower to be priced when attention is scarce"},
    "C09_raises_low_vol": {
        "question": "does the revision signal work in a low-volatility market?",
        "condition": "as C08 with vol at or below its trailing 5-year median; otherwise the market",
        "when": "1999-09-30", "prior": "the complement of C08"},
    "C10_lead_raise_in_beaten_down": {
        "question": "does a raise that leads price (no run-up) in a beaten-down name predict recovery?",
        "condition": "lead_raises_90 >= 1 AND px_vs_52w_high <= -0.30",
        "when": "1999-09-30", "prior": "lead/chase was the vendor board's other ALPHA_DETECTED family"},
}
DECISION_RULE = (
    "CANDIDATE iff VALIDATE (2009-2016) net-minus-market mean > 0, t >= 2 (3-month blocks), >= 5 of 8 years "
    "positive, AND DESIGN (source start .. 2008) net-minus-market mean > 0 and gross-minus-twin mean > 0. Else "
    "CANNOT_DISTINGUISH if the validate net-minus-market mean > 0, else FAILED_VARIANT. A CANDIDATE with DSR "
    "(net-minus-market, source start .. 2016) < 0.95 at the full count is NOT_DEFLATED_SURVIVOR: registration "
    "as a free forward shadow only. 2017-2024 is read last as description.")
BREAKDOWNS = ("size band (mega/large/mid/small by 63-session median dollar volume)",
              "era (design / validate / 2017-2024)", "by hold year")


def say(*a) -> None:
    print(*a, flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ── pure engine (tested offline) ────────────────────────────────────────────

def add_cells(P: pd.DataFrame) -> pd.Series:
    """band|vol tercile|mom tercile per row, computed WITHIN each decision date over eligible names
    (`matched_twins.cell_table`); NaN for ineligible rows."""
    from backend.services import matched_twins as MT                 # noqa: PLC0415
    out = pd.Series(np.nan, index=P.index, dtype=object)
    for _d, g in P.groupby("date", sort=False):
        c = MT.cell_table(g)
        k = c["band"].astype(str) + "|" + c["vt"].astype(str) + "|" + c["mt"].astype(str)
        el = g[g["eligible"].astype(bool)]
        out.loc[el.index] = el["symbol"].map(k).to_numpy()
    return out


def twin_gross(sel: pd.Index, g: pd.DataFrame) -> float:
    """Selection's cell mix x cell-mean forward return of NON-selected eligible names.
    `g`: one decision date with columns symbol, eligible, fwd_ret, _cell."""
    e = g[g["eligible"].astype(bool) & g["fwd_ret"].notna()].drop_duplicates("symbol").set_index("symbol")
    pool = e[~e.index.isin(sel)]
    cm = pool["fwd_ret"].astype(float).groupby(pool["_cell"]).mean()
    sk = e["_cell"].reindex(sel).dropna()
    if not len(sk):
        return float("nan")
    mix = sk.value_counts(normalize=True)
    vals = cm.reindex(mix.index)
    ok = vals.notna()
    if not ok.any():
        return float("nan")
    return float((vals[ok] * mix[ok]).sum() / mix[ok].sum())


def trade_cost(prev_w: dict, w: dict, spread: dict, default: float) -> tuple[float, float]:
    """(cost, one-way turnover): each |dw| pays half its name's round-trip spread."""
    names = set(prev_w) | set(w)
    cost, to = 0.0, 0.0
    for s in names:
        dw = abs(w.get(s, 0.0) - prev_w.get(s, 0.0))
        if dw:
            sp = spread.get(s, default)
            cost += dw * (sp if np.isfinite(sp) else default) / 2.0
            to += dw
    return cost, to / 2.0


def run_cell(P: pd.DataFrame, mask: pd.Series, market: pd.Series, spreads: pd.Series,
             active: Optional[pd.Series] = None, start: Optional[str] = None) -> pd.DataFrame:
    """Monthly series of one conditional cell.

    `mask`: boolean over P's rows (the condition; eligibility applied here).
    `active`: optional boolean by date (a regime gate); inactive -> market.
    `spreads`: round-trip spread per P row (max(CS, flat band)).
    Returns date-indexed: gross, cost, net, twin_gross, market, n, turnover, invested.
    """
    P = P.assign(_m=mask.to_numpy(dtype=bool) & P["eligible"].astype(bool).to_numpy(),
                 _sp=spreads.to_numpy(dtype=float))
    rows, prev_w = [], {}
    for d, g in P.groupby("date", sort=True):
        if start and d < pd.Timestamp(start):
            continue
        if not g["fwd_ret"].notna().any():
            continue
        mk = float(market.get(d, np.nan))
        on = True if active is None else bool(active.get(d, False))
        sel = g[g["_m"] & g["fwd_ret"].notna()].drop_duplicates("symbol")
        if (not on) or len(sel) < MIN_NAMES:
            spread_prev = dict(zip(g["symbol"], g["_sp"]))
            c, to = trade_cost(prev_w, {}, spread_prev, 0.0035)
            prev_w = {}
            rows.append((d, mk - c, c, mk - c, np.nan, mk, 0, to, False))
            continue
        w = {s: 1.0 / len(sel) for s in sel["symbol"]}
        spread = dict(zip(g["symbol"], g["_sp"]))
        c, to = trade_cost(prev_w, w, spread, 0.0035)
        gross = float(sel["fwd_ret"].astype(float).mean())
        tg = twin_gross(pd.Index(sel["symbol"]), g)
        rows.append((d, gross, c, gross - c, tg, mk, len(sel), to, True))
        prev_w = w
    return pd.DataFrame(rows, columns=["date", "gross", "cost", "net", "twin_gross", "market", "n", "turnover",
                                       "invested"]).set_index("date")


def cell_verdict(s: pd.DataFrame, when: str) -> dict:
    from backend.services import calendar_offsets as CO              # noqa: PLC0415
    from backend.services import crsp_rebuild as CR                  # noqa: PLC0415
    vm = (s["net"] - s["market"]).dropna()
    vt = (s["gross"] - s["twin_gross"]).where(s["invested"]).dropna()
    out = {"vs_market_net": {k: CR.window_stats(vm, *w) for k, w in SPLITS.items()},
           "vs_twin_gross": {k: CR.window_stats(vt, *w) for k, w in SPLITS.items()}}
    hm = pd.DatetimeIndex(vm.index) + pd.offsets.BDay(1)
    val = vm[(hm >= pd.Timestamp("2009-01-01")) & (hm <= pd.Timestamp("2016-12-31"))]
    byv = CO.by_hold_year(val) if len(val) else {}
    out["validate_years_positive"] = int(sum(1 for v in byv.values() if v["sum"] > 0))
    out["validate_years"] = int(len(byv))
    out["by_hold_year_vs_market"] = {y: round(v["sum"], 4) for y, v in CO.by_hold_year(vm).items()}
    out["by_hold_year_vs_twin"] = {y: round(v["sum"], 4) for y, v in CO.by_hold_year(vt).items()}
    out["loo_worst_vs_market"] = {k: v for k, v in CO.loo_worst(vm).items() if k != "all"}
    v, d = out["vs_market_net"]["validate"], out["vs_market_net"]["design"]
    dt = out["vs_twin_gross"]["design"]
    cand = ((v.get("mean_monthly") or 0) > 0 and (v.get("t_blocks") or 0) >= 2
            and out["validate_years_positive"] >= 5 and (d.get("mean_monthly") or 0) > 0
            and (dt.get("mean_monthly") or 0) > 0)
    out["verdict"] = "CANDIDATE" if cand else ("CANNOT_DISTINGUISH" if (v.get("mean_monthly") or 0) > 0
                                                else "FAILED_VARIANT")
    out["months_invested"] = int(s["invested"].sum())
    out["mean_names_when_invested"] = float(s.loc[s["invested"], "n"].mean()) if s["invested"].any() else 0.0
    out["mean_turnover_when_invested"] = float(s.loc[s["invested"], "turnover"].mean()) if s["invested"].any() else None
    out["mean_cost_bps_when_invested"] = (float(s.loc[s["invested"], "cost"].mean() * 1e4)
                                          if s["invested"].any() else None)
    return out


# ── declare / run ───────────────────────────────────────────────────────────

def part_declare(run_id: str, prior_count: int, library_cells_tonight: int) -> int:
    from scripts.night_checkpoint import atomic_write_json           # noqa: PLC0415
    p = OUT / f"conditionals_DECLARATION_{run_id}.json"
    if p.exists():
        say(f"REFUSED: {p.name} exists")
        return 2
    n_looks = len(CELLS) * (1 + 4 + 3)             # each cell + 4 size bands + 3 eras
    body = {"schema": "crsp_rebuild/conditionals_declaration/1", "job": JOB, "run_id": run_id,
            "licence": "PRODUCT_EXPERIMENT", "written_utc": _now(), "written_before_any_cell_ran": True,
            "cells": CELLS, "decision_rule": DECISION_RULE, "engine": __doc__.split("THE ENGINE")[1].strip(),
            "splits_hold_month": SPLITS, "min_names": MIN_NAMES, "breakdowns": BREAKDOWNS,
            "search_count": {"before_tonight": prior_count, "library_cells_tonight": library_cells_tonight,
                             "conditional_looks": n_looks,
                             "n_trials_for_dsr": prior_count + library_cells_tonight + n_looks},
            "honesty_note": ("the revision-flow family was chosen knowing 2026-09-29's validation numbers for "
                             "net_raises/ear_flow as stand-alone books; the conditions, thresholds and regimes "
                             "were not tuned on any window")}
    body["sha16"] = _sha({k: v for k, v in body.items() if k != "written_utc"})
    atomic_write_json(p, body, indent=1)
    say(f"-> {p.name} sha {body['sha16']}")
    return 0


def _insider_buyers_30(keys: pd.DataFrame) -> np.ndarray:
    """Distinct open-market insider buyers with a Form 4 usable in (d-30, d] (filing day + 1 BDay)."""
    ins = pd.read_parquet(OPT / "sec_insider" / "insider_events_v1.parquet",
                          columns=["permno", "event_type", "observed_at_utc", "insider_cik"],
                          filters=[("event_type", "=", "insider_open_market_buy")])
    ins = ins.dropna(subset=["permno", "observed_at_utc"])
    ins["permno"] = pd.to_numeric(ins["permno"], errors="coerce").astype("int64")
    obs = pd.to_datetime(ins["observed_at_utc"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    ins["usable"] = obs.dt.normalize() + pd.offsets.BDay(1)
    ins = ins.sort_values("usable")
    tt = ins["usable"].to_numpy(dtype="datetime64[ns]")
    rows = []
    for d in sorted(keys["date"].unique()):
        d = pd.Timestamp(d)
        lo = int(np.searchsorted(tt, np.datetime64(d - pd.Timedelta(days=30)), "right"))
        hi = int(np.searchsorted(tt, np.datetime64(d), "right"))
        w = ins.iloc[lo:hi]
        if len(w):
            n = w.drop_duplicates(["permno", "insider_cik"]).groupby("permno").size()
            rows.append(pd.DataFrame({"date": d, "permno": n.index.astype(float), "b30": n.to_numpy(float)}))
    f = pd.concat(rows, ignore_index=True)
    return keys[["date", "permno"]].merge(f, on=["date", "permno"], how="left")["b30"].to_numpy()


def _market_vol_regime(dates) -> pd.Series:
    """1 when the market's 63-session realised vol at d exceeds its trailing 5-year median (daily FF)."""
    from scripts import momentum_on_crsp as M                         # noqa: PLC0415
    m = M.market_daily().sort_index()
    v = m.rolling(63, min_periods=50).std()
    med = v.rolling(1260, min_periods=750).median()
    out = {}
    for d in dates:
        d = pd.Timestamp(d)
        x, y = v[:d], med[:d]
        out[d] = (float(x.iloc[-1]) > float(y.iloc[-1])) if len(x) and len(y) and np.isfinite(y.iloc[-1]) else None
    return pd.Series(out)


def part_run(dec_id: str) -> int:
    from backend.services import xs_ranker as XR                     # noqa: PLC0415
    from learner.inference import deflated_sharpe                    # noqa: PLC0415
    from scripts import bridges_on_crsp_run as BR                    # noqa: PLC0415
    from scripts import momentum_on_crsp as M                         # noqa: PLC0415
    from scripts.night_checkpoint import atomic_write_json           # noqa: PLC0415
    from backend.services import matched_twins as MT                 # noqa: PLC0415
    decl = json.loads((OUT / f"conditionals_DECLARATION_{dec_id}.json").read_text(encoding="utf-8"))
    if _sha({k: v for k, v in decl.items() if k not in ("written_utc", "sha16")}) != decl["sha16"]:
        say("REFUSED: declaration hash mismatch")
        return 2
    rp = OUT / f"conditionals_RESULTS_{dec_id}.json"
    if rp.exists():
        say(f"REFUSED: {rp.name} exists (each cell is read once)")
        return 2
    t0 = time.time()
    P, _ = BR.load_merged(False)
    keep = ["date", "symbol", "eligible", "fwd_ret", "median_dollar_vol", "vol_63", "mom_252_21", "mom_21",
            "px_vs_52w_high", "mkt_trend_up", "days_since_earn", "ear_last", "net_raises", "net_raises_30",
            "n_firms", "si_ratio", "n_conc_init", "lead_raises_90"]
    P = P[keep].copy()
    gc.collect()
    P["permno"] = pd.to_numeric(P["symbol"], errors="coerce").astype("float64")
    P["_cell"] = add_cells(P)
    say(f"  panel {len(P):,} rows {time.time()-t0:.0f}s")
    D = pd.read_parquet(OUT / "followups_daily_FU_2026-09-29T0855Z.parquet", columns=["date", "permno", "cs_spread"])
    D["date"] = pd.to_datetime(D["date"])
    D["permno"] = D["permno"].astype("float64")
    cs = P[["date", "permno"]].merge(D, on=["date", "permno"], how="left")["cs_spread"].to_numpy(dtype=float)
    flat = np.array([XR.COST_BPS_BY_BAND[XR.liquidity_band(v)] / 1e4 if np.isfinite(v) else 0.0035
                     for v in P["median_dollar_vol"].to_numpy(dtype=float)])
    spreads = pd.Series(np.fmax(np.minimum(cs, CS_CAP), flat), index=P.index)
    del D
    mkt = M.spy_series(P)
    P["b30"] = _insider_buyers_30(P)
    say(f"  inputs {time.time()-t0:.0f}s")
    # cross-sectional cut points per month, computed within the month (no look-ahead)
    el = P["eligible"].astype(bool)
    P["ear_rank"] = P["ear_last"].where(el & P["days_since_earn"].le(45)).groupby(P["date"]).rank(pct=True)
    P["si_rank"] = P["si_ratio"].where(el).groupby(P["date"]).rank(pct=True)
    nr = P["net_raises"].where(el & P["net_raises"].notna())
    P["nr_rank"] = nr.groupby(P["date"]).rank(pct=True)
    top_raises = (P["nr_rank"] >= 0.8) & (P["net_raises"] >= 1)
    dates = sorted(P["date"].unique())
    trend = P.groupby("date")["mkt_trend_up"].first().astype(float)
    volr = _market_vol_regime(dates)
    masks: dict[str, tuple[pd.Series, Optional[pd.Series]]] = {
        "C01_surprise_then_raises": ((P["ear_rank"] >= 0.7) & (P["net_raises_30"] >= 1), None),
        "C02_insider_cluster_after_drawdown": ((P["b30"] >= 3) & (P["px_vs_52w_high"] <= -0.40), None),
        "C03_squeeze_with_rising_estimates": ((P["si_rank"] >= 0.9) & (P["net_raises"] >= 1) & (P["mom_21"] > 0), None),
        "C04_concentrated_13f_initiation": ((P["n_conc_init"] >= 1), None),
        "C05_raise_in_low_coverage": ((P["net_raises"] >= 1) & (P["n_firms"] <= 2), None),
        "C06_raises_trend_on": (top_raises, trend == 1.0),
        "C07_raises_trend_off": (top_raises, trend == 0.0),
        "C08_raises_high_vol": (top_raises, volr == True),              # noqa: E712
        "C09_raises_low_vol": (top_raises, volr == False),              # noqa: E712
        "C10_lead_raise_in_beaten_down": ((P["lead_raises_90"] >= 1) & (P["px_vs_52w_high"] <= -0.30), None),
    }
    band = pd.Series(MT.size_band(P["median_dollar_vol"].to_numpy(dtype=float)), index=P.index)
    n_trials = int(decl["search_count"]["n_trials_for_dsr"])
    results = {}
    sdir = OUT / f"conditionals_series_{dec_id}"
    sdir.mkdir(parents=True, exist_ok=True)
    for cid, (mask, active) in masks.items():
        tc = time.time()
        when = CELLS[cid]["when"]
        s = run_cell(P, mask.fillna(False), mkt, spreads, active=active, start=when)
        s.to_parquet(sdir / f"{cid}.parquet")
        r = cell_verdict(s, when)
        vm = (s["net"] - s["market"]).dropna()
        hm = pd.DatetimeIndex(vm.index) + pd.offsets.BDay(1)
        dv = vm[hm <= pd.Timestamp("2016-12-31")]
        ds = deflated_sharpe(dv.tolist(), n_trials=n_trials) if len(dv) > 8 else {}
        r["dsr_vs_market_to_2016"] = ds.get("dsr")
        if r["verdict"] == "CANDIDATE" and (ds.get("dsr") or 0) < 0.95:
            r["verdict_flag"] = "NOT_DEFLATED_SURVIVOR"
        r["sd_monthly_net_minus_market"] = float(vm.std()) if len(vm) > 2 else None
        where = {}
        for b in ("mega", "large", "mid", "small"):
            sb = run_cell(P, mask.fillna(False) & (band == b), mkt, spreads, active=active, start=when)
            vb = (sb["net"] - sb["market"]).dropna()
            tb = (sb["gross"] - sb["twin_gross"]).where(sb["invested"]).dropna()
            from backend.services import crsp_rebuild as CR          # noqa: PLC0415
            where[b] = {"months_invested": int(sb["invested"].sum()),
                        "mean_names": float(sb.loc[sb["invested"], "n"].mean()) if sb["invested"].any() else 0.0,
                        "vs_market_net_validate": CR.window_stats(vb, *SPLITS["validate"]),
                        "vs_market_net_full": CR.window_stats(vb),
                        "vs_twin_gross_full": CR.window_stats(tb)}
        r["by_size_band"] = where
        results[cid] = r
        v = r["vs_market_net"]["validate"]
        say(f"  {cid}: {r['verdict']} validate net-mkt {v.get('mean_monthly')} t {v.get('t_blocks')} "
            f"yrs+ {r['validate_years_positive']}/{r['validate_years']} names {r['mean_names_when_invested']:.0f} "
            f"{time.time()-tc:.0f}s")
    doc = {"schema": "crsp_rebuild/conditionals_results/1", "job": JOB, "declaration": dec_id,
           "declaration_sha16": decl["sha16"], "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "written_utc": _now(), "decision_rule": DECISION_RULE, "n_trials_for_dsr": n_trials,
           "cells": results, "seconds": round(time.time() - t0, 1)}
    atomic_write_json(rp, doc, indent=1)
    say(f"-> {rp.name} {time.time()-t0:.0f}s")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", required=True, choices=["declare", "run"])
    ap.add_argument("--run-id")
    ap.add_argument("--declaration")
    ap.add_argument("--prior-count", type=int, default=42_416)
    ap.add_argument("--library-cells", type=int, default=0)
    a = ap.parse_args(argv)
    from scripts.bridges_on_crsp import wait_for_memory             # noqa: PLC0415
    if not wait_for_memory():
        say("REFUSED: under 3 GB free memory for 30 minutes")
        return 3
    if a.part == "declare":
        return part_declare(a.run_id or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ"), a.prior_count,
                            a.library_cells)
    return part_run(a.declaration)


if __name__ == "__main__":
    raise SystemExit(main())
