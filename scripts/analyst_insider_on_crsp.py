"""Analyst, insider and earnings-event rules of the strategy library on CRSP (2026-09-29).

    python -m scripts.analyst_insider_on_crsp --part bridge [--run-id <id>]      # PIT event columns
    python -m scripts.analyst_insider_on_crsp --part run --bridge-run <id> --run-id <id> [--cs]
    python -m scripts.analyst_insider_on_crsp --part board --flat-run <id> --cs-run <id>

Licence `PRODUCT_EXPERIMENT`, $0, no LLM, no network. Nothing is traded, no book,
ledger row or earlier receipt is touched.

WHY: 172 of the library's 312 rules could not run on CRSP because their inputs
had no point-in-time bridge to 1991-2024. `backend/services/crsp_event_bridge`
builds the analyst (IBES target + recommendation detail), insider (SEC Form 4,
FILING date) and earnings-event (IBES actuals, announcement date) columns keyed
to CRSP permno, every event lagged one trading day. Then every rule those
columns unlock runs through `library_on_crsp.part_run` UNCHANGED (costs on, the
21-draw matched twin, two seed sets), once on the flat band cost schedule and
once with a per-name Corwin-Schultz spread charged on top
(`followups_daily_FU_2026-09-29T0855Z`, the same estimator as the co03 follow-up).

THE SPLIT, DECLARED BEFORE ANY RULE WAS RUN (hold month):
  DESIGN   1991-2008 (analyst targets exist from 1999, Form 4 from 2006: each
           rule's design window is the part of 1991-2008 its inputs cover)
  VALIDATE 2009-2016, read once
  HOLDOUT  2017-2024, read once, at the end, and nothing is chosen on it.
DECISION LINE (declared before the run; the reviewer's lessons, 2026-09-29):
  a rule SURVIVES only if, net of the Corwin-Schultz spread variant, rule - twin
  AND rule - market are both > 0 in DESIGN and in VALIDATE, rule - twin has t >= 2
  over DESIGN+VALIDATE, and its deflated Sharpe (rule - twin, 1991-2016) is
  >= 0.95 at the FULL count of everything looked at today. Only a survivor's
  holdout is read as a decision; the holdout of every other rule is printed
  as description, never used to choose.
"""
from __future__ import annotations

import argparse
import gc
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

JOB = "analyst_insider_on_crsp"
OPT = REPO / "backend" / "data" / "optimus"
WRDS = OPT / "wrds"
BULK = WRDS / "bulk"
OUT = OPT / "crsp_rebuild"
PANEL_RUN = "2026-09-29T075640Z"
FUND_RUN = "2026-09-29T041550Z"
CS_DAILY_RUN = "FU_2026-09-29T0855Z"
CS_CAP = 0.20
#: first decision date on which each source has enough history for its windows (declared
#: after reading only the bridge's coverage receipt, before any rule ran): IBES targets are
#: first usable 1999-02-22 (a 180-day window is complete from 1999-09); IBES recommendations
#: from 1993-11 (every broker's first record reads as an "init", so a year of history is
#: required); Form 4 from 2006-01 (180-day window complete from 2006-07). Before these dates
#: the columns are NaN, never 0 (a 0 would let a tiebreak masquerade as a signal).
SOURCE_START = {"flow": "1999-09-30", "rating": "1994-11-30", "target_cv": "1999-09-30", "insider": "2006-06-30"}
SPLITS = {"design": ("1991-01-01", "2008-12-31"), "validate": ("2009-01-01", "2016-12-31"),
          "holdout": ("2017-01-01", "2024-12-31"), "design_validate": ("1991-01-01", "2016-12-31"),
          "full": (None, None)}
#: everything looked at today before this run (the reviewer's count): 1,296 library cells +
#: 2 blends + the 4-of-33 blend space (40,920) = 42,216; + 10 follow-up cells (co03 x6, rank bands x4)
PRIOR_LOOKS_TODAY = 42_216 + 10
DECISION_LINE = (
    "SURVIVES iff, on the Corwin-Schultz variant: rule-twin > 0 and rule-market > 0 in DESIGN (1991-2008) "
    "and in VALIDATE (2009-2016); rule-twin t >= 2 over 1991-2016; DSR(rule-twin, 1991-2016) >= 0.95 at the "
    "full count. Only then is the 2017-2024 holdout read as a decision.")


def say(*a) -> None:
    print(*a, flush=True)


def _mem_ok(floor_gb: float = 2.0) -> bool:
    try:
        import psutil                                                # noqa: PLC0415
        return psutil.virtual_memory().available / 1e9 >= floor_gb
    except Exception:                                                # noqa: BLE001
        return True


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


# ── part 1: the bridge ──────────────────────────────────────────────────────

def _load_link() -> pd.DataFrame:
    L = pd.read_parquet(BULK / "wrdsapps_link_crsp_ibes__ibcrsphist.parquet")
    L["score"] = pd.to_numeric(L["score"], errors="coerce").fillna(9)
    return L


def _ibes(path: Path, cols: list, filters=None) -> pd.DataFrame:
    return pd.read_parquet(path, columns=cols, filters=filters)


def part_bridge(run_id: str) -> int:
    from backend.services import crsp_event_bridge as B               # noqa: PLC0415
    from scripts.night_checkpoint import atomic_write_json           # noqa: PLC0415
    fp, fj = OUT / f"event_bridge_{run_id}.parquet", OUT / f"event_bridge_{run_id}.json"
    if fp.exists() or fj.exists():
        say(f"REFUSED: {fp.name} exists")
        return 2
    t0 = time.time()
    keys = pd.read_parquet(OUT / f"library_panel_{PANEL_RUN}.parquet", columns=["date", "symbol"])
    keys["date"] = pd.to_datetime(keys["date"])
    dates = sorted(keys["date"].unique())
    nxt = B.next_decision(dates)
    link = _load_link()
    meta: dict = {"panel_run": PANEL_RUN, "decision_dates": len(dates)}

    # analyst: price targets
    ptg = _ibes(BULK / "ibes__ptgdet.parquet", ["ticker", "estimid", "value", "anndats", "actdats", "horizon",
                                                  "curr", "usfirm"], filters=[("usfirm", "=", 1)])
    ptg = ptg[(ptg["horizon"].astype(str) == "12") & (ptg["curr"].astype(str) == "USD")]
    ptg["day"] = B.event_day(ptg["anndats"], ptg["actdats"]).to_numpy()
    ptg = ptg.dropna(subset=["day", "value"])[["ticker", "estimid", "value", "day"]]
    ptg, meta["ptg_link"] = B.link_permno(ptg, link)
    ptg = ptg.rename(columns={"estimid": "broker"})
    ptg["value"] = ptg["value"].astype(float)
    ptg = B.target_signs(ptg)
    ptg["usable"] = B.usable_date(ptg["day"]).to_numpy()
    say(f"  ptg: {meta['ptg_link']} {time.time()-t0:.0f}s")
    # analyst: recommendations
    rec = _ibes(BULK / "ibes__recddet.parquet", ["ticker", "estimid", "ireccd", "anndats", "actdats", "usfirm"],
                filters=[("usfirm", "=", 1)])
    rec["day"] = B.event_day(rec["anndats"], rec["actdats"]).to_numpy()
    rec = rec.dropna(subset=["day"])[["ticker", "estimid", "ireccd", "day"]]
    rec, meta["rec_link"] = B.link_permno(rec, link)
    rec = rec.rename(columns={"estimid": "broker", "ireccd": "code"})
    rec = B.rec_actions(rec)
    rec["usable"] = B.usable_date(rec["day"]).to_numpy()
    say(f"  rec: {meta['rec_link']} {time.time()-t0:.0f}s")
    # flow events: every target (signed) + every rating action (sign 0) -- the vendor's
    # revision parquet carries both (yfinance upgrades_downgrades), n_firms counts any action
    ev = pd.concat([ptg[["permno", "usable", "broker", "sign", "chg"]],
                    rec[["permno", "usable", "broker"]].assign(sign=0, chg=np.nan)], ignore_index=True)
    flow = B.flow_panel(ev, dates)
    del ev
    gc.collect()
    rat = B.rating_panel(rec[["permno", "usable", "broker", "action"]], ptg[["permno", "usable", "broker", "value"]],
                         dates)
    meta["n_targets"], meta["n_recs"] = int(len(ptg)), int(len(rec))
    meta["target_first_usable"] = str(ptg["usable"].min().date())
    meta["rec_first_usable"] = str(rec["usable"].min().date())
    meta["target_sign_shares"] = {str(k): round(float(v), 4) for k, v in ptg["sign"].value_counts(normalize=True).items()}
    meta["rec_action_shares"] = {str(k): round(float(v), 4) for k, v in rec["action"].value_counts(normalize=True).items()}
    del ptg, rec
    gc.collect()
    say(f"  flow {len(flow):,} rows, ratings {len(rat):,} rows {time.time()-t0:.0f}s")

    # insider (Form 4, filing date)
    ins = pd.read_parquet(OPT / "sec_insider" / "insider_events_v1.parquet",
                          columns=["permno", "event_type", "observed_at_utc", "insider_cik", "insider_is_officer",
                                   "insider_dollar_value"])
    ins = ins.dropna(subset=["permno", "observed_at_utc"])
    ins["permno"] = pd.to_numeric(ins["permno"], errors="coerce").astype("int64")
    obs = pd.to_datetime(ins["observed_at_utc"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    ins["usable"] = B.usable_date(obs.dt.normalize()).to_numpy()
    meta["insider_events_linked"] = int(len(ins))
    meta["insider_first_usable"] = str(ins["usable"].min().date())
    insf = B.insider_panel(ins, dates)
    del ins
    gc.collect()
    say(f"  insider {len(insf):,} rows {time.time()-t0:.0f}s")

    # earnings (IBES actuals: quarterly EPS, first announcement per period)
    act = _ibes(BULK / "ibes__act_epsus.parquet", ["ticker", "measure", "pdicity", "pends", "anndats", "anntims",
                                                     "usfirm"], filters=[("usfirm", "=", 1)])
    act = act[(act["measure"] == "EPS") & (act["pdicity"] == "QTR")]
    act["day"] = pd.to_datetime(act["anndats"]).dt.normalize()
    act, meta["act_link"] = B.link_permno(act, link)
    er = B.earnings_events(act)
    del act
    mkt = __import__("scripts.momentum_on_crsp", fromlist=["x"]).market_daily()
    parts = []
    for y in range(1990, 2025):
        sub = er[er["reaction_day"].dt.year == y]
        if not len(sub):
            continue
        frames = [pd.read_parquet(WRDS / f"crsp_dsf_{y}.parquet", columns=["permno", "date", "ret"])]
        if y > 1990:
            frames.insert(0, pd.read_parquet(WRDS / f"crsp_dsf_{y-1}.parquet", columns=["permno", "date", "ret"],
                                             filters=[("date", ">=", pd.Timestamp(f"{y-1}-12-01"))]))
        if y < 2024:
            frames.append(pd.read_parquet(WRDS / f"crsp_dsf_{y+1}.parquet", columns=["permno", "date", "ret"],
                                          filters=[("date", "<=", pd.Timestamp(f"{y+1}-01-20"))]))
        dly = pd.concat(frames, ignore_index=True)
        dly["date"] = pd.to_datetime(dly["date"])
        dly["permno"] = pd.to_numeric(dly["permno"], errors="coerce").astype("int64")
        dly = dly[dly["permno"].isin(set(sub["permno"]))]
        parts.append(B.three_day_car(dly, mkt, sub))
        del dly, frames
        gc.collect()
    er = pd.concat(parts, ignore_index=True)
    meta["earnings_events"] = int(len(er))
    meta["earnings_priced"] = int(er["ear"].notna().sum())
    earn = B.earnings_panel(er[["permno", "anndats", "ear", "known"]], dates, nxt)
    del er
    gc.collect()
    say(f"  earnings {len(earn):,} rows {time.time()-t0:.0f}s")

    # merge onto the panel keys
    keys["permno"] = pd.to_numeric(keys["symbol"], errors="coerce").astype("float64")
    out = keys
    for f in (flow, rat, insf, earn):
        f["permno"] = pd.to_numeric(f["permno"], errors="coerce").astype("float64")
        f = f.dropna(subset=["permno"])
        f["date"] = pd.to_datetime(f["date"])
        out = out.merge(f, on=["date", "permno"], how="left")
    cols = [c for c in out.columns if c not in ("date", "symbol", "permno")]
    for c in cols:
        if out[c].dtype == np.float64:
            out[c] = out[c].astype(np.float32)
    out.drop(columns=["permno"]).to_parquet(fp, index=False)
    cov = {}
    for c in ("net_raises", "rating_net_90", "target_cv_180", "ins_buyers_90", "ear_last", "earn_next"):
        f = out[out[c].notna()]
        per = f.groupby("date")["permno"].nunique()
        cov[c] = {str(y): int(round(v)) for y, v in per.groupby(pd.DatetimeIndex(per.index).year).mean().items()}
    meta["names_per_month_by_year"] = cov
    meta["eligible_share_covered"] = None
    doc = {"schema": "crsp_rebuild/event_bridge/1", "job": JOB, "run_id": run_id, "licence": "PRODUCT_EXPERIMENT",
           "llm_spend_usd": 0.0, "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "timestamp_rule": ("IBES: max(anndats, actdats); Form 4: filing date (observed_at_utc, ET day); "
                              "usable = that day + 1 business day; counted at decision date d iff usable <= d. "
                              "Earnings announcement return [e-1, e+1] usable from the business day after e+1. "
                              "IBES ticker -> permno through the ibcrsphist row active on the EVENT date "
                              "(lowest score)."),
           "sources": {"targets": "wrds/bulk/ibes__ptgdet.parquet (12m horizon, USD, usfirm=1)",
                       "recs": "wrds/bulk/ibes__recddet.parquet (usfirm=1; ireccd 1=strong buy..5=sell)",
                       "actuals": "wrds/bulk/ibes__act_epsus.parquet (EPS, QTR; first announcement per period "
                                  "within 120 days of period end)",
                       "insider": "sec_insider/insider_events_v1.parquet (2006-2024 linked to permno)",
                       "link": "wrds/bulk/wrdsapps_link_crsp_ibes__ibcrsphist.parquet"},
           "differences_from_vendor": [
               "vendor revision flow = yfinance upgrades_downgrades rows; here = IBES target changes (sign from "
               "the same broker's previous 12m target <= 365 days old) + IBES recommendation actions (sign 0)",
               "vendor 'firm' = broker name; here = IBES estimid",
               "lead/chase, skill and first-mover columns are NOT built here (not in scope tonight)",
               "earnings: vendor uses 8-K item 2.02; here IBES actual announcement dates",
               "ins_* columns: the same file and event types as the vendor; only 2006+ exists"],
           "rows": int(len(out)), "columns": cols, **meta, "seconds": round(time.time() - t0, 1)}
    atomic_write_json(fj, doc, indent=1)
    say(f"-> {fp.name} {time.time()-t0:.0f}s")
    return 0


# ── part 2: run the unlocked rules through library_on_crsp.part_run ─────────

def unlocked_rules(bridge_cols: list) -> list:
    """NOT_RUN rules of the CRSP library run whose MISSING inputs (as that run named them)
    are all produced by the bridge."""
    import ast                                                        # noqa: PLC0415
    import re                                                         # noqa: PLC0415
    rows = [json.loads(ln) for ln in (OUT / "library_rules_LIB_2026-09-29T0802Z.jsonl").read_text(
        encoding="utf-8").splitlines() if ln.strip()]
    have = set(bridge_cols)
    out = []
    for r in rows:
        if r.get("status") != "NOT_RUN":
            continue
        m = re.search(r"\[(.*)\]", r.get("why", ""))
        miss = ast.literal_eval("[" + m.group(1) + "]") if m else ["?"]
        if set(miss) <= have:
            out.append(r["rule"])
    return out


def part_run(bridge_run: str, run_id: str, cs: bool) -> int:
    from backend.services import crsp_event_bridge as B               # noqa: PLC0415
    from backend.services import xs_ranker as XR                     # noqa: PLC0415
    from scripts import library_on_crsp as LOC                        # noqa: PLC0415
    bp = OUT / f"event_bridge_{bridge_run}.parquet"
    bcols = [c for c in pd.read_parquet(bp).columns if c not in ("date", "symbol")] if bp.exists() else []
    rules = unlocked_rules(bcols + ["ins_buy_value_dv_90"])
    say(f"{JOB} run {run_id}: {len(rules)} rules unlocked by bridge {bridge_run}; cs={cs}")
    orig = LOC.load_full_panel

    def patched(panel_run, fund_run=None):
        P, meta = orig(panel_run, fund_run)
        E = pd.read_parquet(bp)
        E["date"] = pd.to_datetime(E["date"])
        P = P.merge(E, on=["date", "symbol"], how="left")
        del E
        P["ins_buy_value_dv_90"] = P["ins_buy_value_90"] / P["median_dollar_vol"]
        gates = {"flow": B.FLOW_COLS, "rating": ["rating_net_90", "rating_downgrades_90", "initiations_90"],
                 "target_cv": ["target_cv_180"], "insider": B.INSIDER_COLS + ["ins_buy_value_dv_90"]}
        for src, cols_ in gates.items():
            early = P["date"] < pd.Timestamp(SOURCE_START[src])
            for c_ in cols_:
                if c_ in P.columns:
                    P.loc[early, c_] = np.nan
        if cs:
            D = pd.read_parquet(OUT / f"followups_daily_{CS_DAILY_RUN}.parquet", columns=["date", "permno", "cs_spread"])
            D["symbol"] = D["permno"].map(lambda p: f"{int(p):06d}")
            D["date"] = pd.to_datetime(D["date"])
            j = P[["date", "symbol"]].merge(D[["date", "symbol", "cs_spread"]], on=["date", "symbol"], how="left")
            cs_ = np.minimum(j["cs_spread"].to_numpy(dtype=float), CS_CAP)
            flat = np.array([XR.COST_BPS_BY_BAND[XR.liquidity_band(v)] / 1e4 if np.isfinite(v) else 0.0035
                             for v in P["median_dollar_vol"].to_numpy(dtype=float)])
            P["fwd_ret"] = P["fwd_ret"].to_numpy(dtype=float) - np.where(np.isfinite(cs_), cs_, flat)
            meta["cs"] = {"coverage": float(np.isfinite(cs_).mean())}
        meta["event_bridge"] = bp.name
        return P, meta

    LOC.load_full_panel = patched
    try:
        rc = LOC.part_run(PANEL_RUN, run_id, only=rules, fund_run=FUND_RUN)
    finally:
        LOC.load_full_panel = orig
    return rc


# ── part 3: the board ───────────────────────────────────────────────────────

def split_stats(s: pd.Series) -> dict:
    from backend.services import crsp_rebuild as CR                  # noqa: PLC0415
    return {k: CR.window_stats(s, *w) for k, w in SPLITS.items()}


def survives(twin: dict, mkt: dict, dsr: Optional[float]) -> tuple[bool, list]:
    fails = []
    for sp in ("design", "validate"):
        if not ((twin[sp].get("mean_monthly") or 0) > 0):
            fails.append(f"rule-twin <= 0 in {sp}")
        if not ((mkt[sp].get("mean_monthly") or 0) > 0):
            fails.append(f"rule-market <= 0 in {sp}")
    if not ((twin["design_validate"].get("t_blocks") or 0) >= 2):
        fails.append("rule-twin t < 2 over 1991-2016")
    if not ((dsr or 0) >= 0.95):
        fails.append("DSR < 0.95 at the full count")
    return (not fails), fails


def part_board(flat_run: str, cs_run: str) -> int:
    from backend.services import calendar_offsets as CO              # noqa: PLC0415
    from learner.inference import deflated_sharpe                    # noqa: PLC0415
    from scripts.night_checkpoint import atomic_write_json           # noqa: PLC0415
    bid = _run_id()
    bj = OUT / f"event_board_{flat_run}__{bid}.json"
    rows = {}
    for tag, rid in (("flat", flat_run), ("cs", cs_run)):
        jl = OUT / f"library_rules_{rid}.jsonl"
        if not jl.exists():
            continue
        for ln in jl.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except Exception:                                        # noqa: BLE001
                continue
            rows.setdefault(r["rule"], {})[tag] = r
    series = {}
    for rule in rows:
        for tag, rid in (("flat", flat_run), ("cs", cs_run)):
            p = OUT / f"library_series_{rid}" / f"{rule}.parquet"
            if p.exists():
                series.setdefault(rule, {})[tag] = pd.read_parquet(p)
    n_cells = sum(len(v) for v in series.values())
    n_total = PRIOR_LOOKS_TODAY + n_cells
    out_rows = []
    for rule, sv in series.items():
        rec = {"rule": rule, "family": (rows[rule].get("flat") or rows[rule].get("cs") or {}).get("family"),
               "requires": (rows[rule].get("flat") or {}).get("requires")}
        for tag, df in sv.items():
            dt = (df["rule_net"] - df["twin21_net"]).dropna()
            dm = (df["rule_net"] - df["market"]).dropna()
            hold = pd.DatetimeIndex(dt.index) + pd.offsets.BDay(1)
            dv = dt[hold <= pd.Timestamp("2016-12-31")]
            d_ = deflated_sharpe(dv.tolist(), n_trials=n_total) if len(dv) > 8 else {}
            rec[tag] = {"vs_twin": split_stats(dt), "vs_market": split_stats(dm),
                        "by_hold_year_vs_twin": {y: round(v["sum"], 4) for y, v in CO.by_hold_year(dt).items()},
                        "loo_worst_vs_twin": {k: v for k, v in CO.loo_worst(dt).items() if k != "all"},
                        "first_month": str(dt.index.min().date()) if len(dt) else None,
                        "dsr_rule_minus_twin_1991_2016": d_.get("dsr"), "dsr_z": d_.get("z"),
                        "sd_monthly_gap": float(dt.std()) if len(dt) > 2 else None,
                        "mean_cost_bps_per_month": (rows[rule].get(tag) or {}).get("mean_cost_bps_per_month")}
        if "cs" in rec:
            ok, why = survives(rec["cs"]["vs_twin"], rec["cs"]["vs_market"], rec["cs"]["dsr_rule_minus_twin_1991_2016"])
            rec["survives"], rec["fails"] = ok, why
        out_rows.append(rec)
    out_rows.sort(key=lambda r: -((r.get("cs") or r.get("flat") or {}).get("vs_twin", {}).get("design_validate", {})
                                  .get("t_blocks") or -9))
    doc = {"schema": "crsp_rebuild/event_board/1", "job": JOB, "board_id": bid, "flat_run": flat_run,
           "cs_run": cs_run, "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "splits": SPLITS, "decision_line": DECISION_LINE,
           "deflation_count": {"prior_looks_today": PRIOR_LOOKS_TODAY, "cells_this_run": n_cells,
                               "n_trials_used": n_total,
                               "note": "the reviewer's 60,000 random 4-of-133 draws are a null, not a search; "
                                       "at the 4-of-133 space (12.4M) no DSR here could exceed its value at n_trials_used"},
           "n_rules": len(out_rows), "n_survivors": sum(1 for r in out_rows if r.get("survives")),
           "rows": out_rows}
    atomic_write_json(bj, doc, indent=1)
    say(f"-> {bj.name}: {len(out_rows)} rules, survivors {doc['n_survivors']}, n_trials {n_total}")
    return 0


# ── part 4: turnover and capacity of named rules (the board's leaders) ──────

def part_profile(bridge_run: str, rules_csv: str, tag: str) -> int:
    from backend.services import strategy_library as SL              # noqa: PLC0415
    from scripts import library_on_crsp as LOC                        # noqa: PLC0415
    from scripts.crsp_blend_followups_run import book_profile        # noqa: PLC0415
    from scripts.night_checkpoint import atomic_write_json           # noqa: PLC0415
    rj = OUT / f"event_profile_{tag}.json"
    if rj.exists():
        say(f"REFUSED: {rj.name} exists")
        return 2
    bp = OUT / f"event_bridge_{bridge_run}.parquet"
    P, _ = LOC.load_full_panel(PANEL_RUN, FUND_RUN)
    E = pd.read_parquet(bp)
    E["date"] = pd.to_datetime(E["date"])
    P = P.merge(E, on=["date", "symbol"], how="left").reset_index(drop=True)
    del E
    from backend.services import crsp_event_bridge as B               # noqa: PLC0415
    P["ins_buy_value_dv_90"] = P["ins_buy_value_90"] / P["median_dollar_vol"]
    gates = {"flow": B.FLOW_COLS, "rating": ["rating_net_90", "rating_downgrades_90", "initiations_90"],
             "target_cv": ["target_cv_180"], "insider": B.INSIDER_COLS + ["ins_buy_value_dv_90"]}
    for src, cols_ in gates.items():
        early = P["date"] < pd.Timestamp(SOURCE_START[src])
        for c_ in cols_:
            P.loc[early, c_] = np.nan
    rules = {r.id: r for r in SL.rules()}
    out = {}
    for rid in rules_csv.split(","):
        try:
            out[rid] = book_profile(P, rules[rid], int(rules[rid].k))
            say(f"  {rid}: turnover {out[rid]['turnover_per_month']:.2f} median pick ADV $M "
                f"{out[rid]['median_pick_adv_musd_by_decade']}")
        except Exception as e:                                       # noqa: BLE001
            out[rid] = {"status": f"REFUSED: {type(e).__name__}: {e}"}
    atomic_write_json(rj, {"schema": "crsp_rebuild/event_profile/1", "bridge_run": bridge_run,
                           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           "profiles": out}, indent=1)
    say(f"-> {rj.name}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", required=True, choices=["bridge", "run", "board", "profile"])
    ap.add_argument("--run-id")
    ap.add_argument("--bridge-run")
    ap.add_argument("--cs", action="store_true")
    ap.add_argument("--flat-run")
    ap.add_argument("--cs-run")
    ap.add_argument("--rules")
    ap.add_argument("--tag")
    a = ap.parse_args(argv)
    if not _mem_ok():
        say("REFUSED: under 2 GB free memory")
        return 3
    if a.part == "bridge":
        return part_bridge(a.run_id or _run_id())
    if a.part == "run":
        return part_run(a.bridge_run, a.run_id or f"EVT_{_run_id()}", a.cs)
    if a.part == "profile":
        return part_profile(a.bridge_run, a.rules, a.tag or _run_id())
    return part_board(a.flat_run, a.cs_run)


if __name__ == "__main__":
    raise SystemExit(main())
