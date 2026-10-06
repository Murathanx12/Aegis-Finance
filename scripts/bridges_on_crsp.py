"""The last library rules on CRSP: short interest, 13F, 8-K, analyst timing/skill, Compustat (2026-09-30).

    python -m scripts.bridges_on_crsp --part si       --run-id <id>   # short interest
    python -m scripts.bridges_on_crsp --part f13      --run-id <id>   # 13F breadth + initiations
    python -m scripts.bridges_on_crsp --part eightk   --run-id <id>   # 8-K item counts
    python -m scripts.bridges_on_crsp --part analyst2 --run-id <id>   # lead/chase, first mover, skill
    python -m scripts.bridges_on_crsp --part fund     --run-id <id>   # Compustat -> SEC-facts columns
    python -m scripts.bridges_on_crsp --part declare  --run-id <id>   # the decision line, BEFORE any rule
    python -m scripts.bridges_on_crsp --part run  --declaration <id> --run-id <id> [--cs]
    python -m scripts.bridges_on_crsp --part turnover --declaration <id> --run-id <id>
    python -m scripts.bridges_on_crsp --part board --declaration <id> --flat-run <id> --cs-run <id> --turnover-run <id>

Licence `PRODUCT_EXPERIMENT`, $0, no LLM, no network. Nothing is traded; no
book, ledger row or earlier receipt is touched. Every output carries its run id
and is refused if it already exists.

WHY: after the IBES/Form-4 bridge (2026-09-29) 96 library rules were still not
run on CRSP because their inputs had no point-in-time bridge. The timing rule of
each source is in `backend/services/crsp_pit_bridges.py`. The rules run through
`library_on_crsp.part_run` UNCHANGED (costs on, the 21-draw matched twin, two
seed sets), at flat costs and with the per-name Corwin-Schultz spread, as the
2026-09-29 event run did; the board then scales the spread by each rule's
MEASURED turnover (the reviewer's lesson) and reads everything against the
market as well as the twin.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
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

JOB = "bridges_on_crsp"
OPT = REPO / "backend" / "data" / "optimus"
WRDS = OPT / "wrds"
BULK = WRDS / "bulk"
OUT = OPT / "crsp_rebuild"
PANEL_RUN = "2026-09-29T075640Z"
FUND_RUN = "2026-09-29T041550Z"
EVENT_BRIDGE_RUN = "EB_2026-09-29T1055Z"
CS_DAILY_RUN = "FU_2026-09-29T0855Z"
CS_CAP = 0.20
LIB_RUN = "LIB_2026-09-29T0802Z"
EVT_RUNS = ("EVT_FLAT_2026-09-29T1105Z", "EVT_CS_2026-09-29T1110Z")
#: the whole search before tonight, as the brief states it: the reviewer's 42,216 + 10 follow-ups +
#: 152 event cells + 19 revision-tilt cells + 19 mid-cap revision-tilt cells = 42,416
PRIOR_SEARCH = 42_416
SPLITS = {"design": ("1991-01-01", "2008-12-31"), "validate": ("2009-01-01", "2016-12-31"),
          "holdout": ("2017-01-01", "2024-12-31"), "design_validate": ("1991-01-01", "2016-12-31"),
          "full": (None, None)}
#: the event bridge's declared starts (2026-09-29), reused unchanged
EVENT_SOURCE_START = {"flow": "1999-09-30", "rating": "1994-11-30", "target_cv": "1999-09-30",
                      "insider": "2006-06-30"}


def say(*a) -> None:
    print(*a, flush=True)


def _mem_gb() -> float:
    """Available physical memory in GB (psutil if present, else the Windows API)."""
    try:
        import psutil                                                # noqa: PLC0415
        return psutil.virtual_memory().available / 1e9
    except Exception:                                                # noqa: BLE001
        pass
    try:
        import ctypes                                                # noqa: PLC0415

        class _MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = _MS()
        m.dwLength = ctypes.sizeof(_MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullAvailPhys / 1e9
    except Exception:                                                # noqa: BLE001
        return 99.0


def wait_for_memory(floor_gb: float = 3.0, max_wait_s: int = 1800) -> bool:
    """Shared machine: wait (not fail) while free memory is under the floor."""
    t0 = time.time()
    while _mem_gb() < floor_gb:
        if time.time() - t0 > max_wait_s:
            return False
        say(f"  waiting: {_mem_gb():.1f} GB free < {floor_gb} GB")
        time.sleep(30)
    return True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _keys() -> pd.DataFrame:
    k = pd.read_parquet(OUT / f"library_panel_{PANEL_RUN}.parquet", columns=["date", "symbol"])
    k["date"] = pd.to_datetime(k["date"])
    k["permno"] = pd.to_numeric(k["symbol"], errors="coerce").astype("float64")
    return k


def _refuse_if_exists(*paths: Path) -> bool:
    for p in paths:
        if p.exists():
            say(f"REFUSED: {p.name} exists; a receipt is never overwritten")
            return True
    return False


def _write_bridge(name: str, run_id: str, keys: pd.DataFrame, cols: dict, meta: dict) -> int:
    from backend.services import crsp_pit_bridges as PB              # noqa: PLC0415
    from scripts.night_checkpoint import atomic_write_json           # noqa: PLC0415
    fp, fj = OUT / f"pit_{name}_{run_id}.parquet", OUT / f"pit_{name}_{run_id}.json"
    out = keys[["date", "symbol"]].copy()
    for c, v in cols.items():
        out[c] = np.asarray(v, dtype="float64").astype(np.float32)
    fr = out.assign(permno=keys["permno"])
    meta["names_per_month_by_year"] = {c: PB.coverage_by_year(fr, c) for c in cols}
    meta["rows"], meta["columns"] = int(len(out)), list(cols)
    out.to_parquet(fp, index=False)
    doc = {"schema": f"crsp_rebuild/pit_{name}/1", "job": JOB, "run_id": run_id, "licence": "PRODUCT_EXPERIMENT",
           "llm_spend_usd": 0.0, "written_utc": _now(), "panel_run": PANEL_RUN, **meta}
    atomic_write_json(fj, doc, indent=1)
    say(f"-> {fp.name}")
    return 0


# ── bridges ─────────────────────────────────────────────────────────────────

def part_si(run_id: str) -> int:
    from backend.services import crsp_pit_bridges as PB              # noqa: PLC0415
    if _refuse_if_exists(OUT / f"pit_si_{run_id}.parquet"):
        return 2
    t0 = time.time()
    d = OPT / "short_interest" / "comp_sec_shortint"
    frames = [pd.read_parquet(p, columns=["permno", "datadate", "shortint", "shortintadj", "shares_outstanding",
                                          "turnover_21d"]) for p in sorted(d.glob("*.parquet"))]
    si = pd.concat(frames, ignore_index=True)
    del frames
    pr = PB.si_prints(si)
    keys = _keys()
    got = PB.si_panel(keys, pr)
    meta = {"source": "short_interest/comp_sec_shortint (Compustat sec_shortint + legacy, CCM-linked to permno)",
            "timing": f"datadate (settlement) + {PB.SI_LAG_DAYS} calendar days; stale after {PB.SI_STALE_DAYS} "
                      f"days; si_chg_3m vs the print known {PB.SI_PREV_DAYS} days earlier",
            "dtc_definition": "shortint / (21-session share volume / 21), both on the datadate share basis",
            "n_prints": int(len(pr)), "prints_first": str(pr["datadate"].min().date()),
            "prints_last": str(pr["datadate"].max().date()),
            "caveat": "Nasdaq volume double-counting (Anderson-Dyl) is not adjusted: dtc is not comparable "
                      "across venues before 2001", "seconds": round(time.time() - t0, 1)}
    return _write_bridge("si", run_id, keys, {c: got[c] for c in PB.SI_COLS}, meta)


def _dsenames() -> pd.DataFrame:
    n = pd.read_parquet(BULK / "crsp__dsenames.parquet", columns=["permno", "namedt", "nameendt", "ncusip", "ticker"])
    n["namedt"] = pd.to_datetime(n["namedt"], errors="coerce")
    n["nameendt"] = pd.to_datetime(n["nameendt"], errors="coerce")
    return n


def part_f13(run_id: str) -> int:
    from backend.services import crsp_pit_bridges as PB              # noqa: PLC0415
    if _refuse_if_exists(OUT / f"pit_f13_{run_id}.parquet"):
        return 2
    t0 = time.time()
    files = sorted(WRDS.glob("tr13f_s34_*.parquet"))
    prev, stats = None, []
    for f in files:
        rows = PB.f13_fresh(pd.read_parquet(f, columns=["fdate", "rdate", "mgrno", "cusip", "shares"]))
        for q in sorted(rows["rdate"].unique()):
            cur = rows[rows["rdate"] == q]
            pv = prev if (prev is not None and 80 <= (pd.Timestamp(q) - prev["rdate"].iloc[0]).days <= 100) else None
            stats.append(PB.f13_quarter_stats(cur, pv))
            prev = cur
        say(f"  {f.name}: {len(rows):,} fresh rows {time.time()-t0:.0f}s")
        del rows
        gc.collect()
    q = pd.concat(stats, ignore_index=True)
    names = _dsenames().dropna(subset=["ncusip"]).rename(columns={"ncusip": "cusip"})
    q, link_meta = PB.dated_link(q, names, key="cusip", day_col="rdate", lo="namedt", hi="nameendt")
    b = PB.f13_breadth(q)
    keys = _keys()
    got = PB.asof_panel(keys, b, ["inst_breadth_chg", "n_inst", "n_conc_init", "n_init"], on="available",
                        age_from="rdate", max_age_days=PB.F13_MAX_AGE_DAYS)
    meta = {"source": "wrds/tr13f_s34_<year>.parquet (Thomson s34; pulled on the CRSP-screened CUSIP universe)",
            "timing": (f"holdings of quarter rdate usable from rdate + {PB.F13_LAG_DAYS} days + 1 business day "
                       f"(the filing deadline: the earliest a full quarter is public); only rows whose vintage "
                       f"fdate == rdate; stale after {PB.F13_MAX_AGE_DAYS} days from rdate"),
            "concentrated_manager": f"{PB.F13_CONC_MIN_HOLDINGS}-{PB.F13_CONC_MAX_HOLDINGS} names held that quarter",
            "initiation": "held this quarter, not held last quarter, by a manager that reported last quarter",
            "cusip_link": link_meta, "quarters": [str(q["rdate"].min().date()), str(q["rdate"].max().date())],
            "caveat": ("late filers (after the 45-day deadline) are counted from the deadline: a small "
                       "optimistic leak; the s34 pull universe was the CRSP-screened CUSIP set (not every "
                       "13F security)"), "seconds": round(time.time() - t0, 1)}
    return _write_bridge("f13", run_id, keys, {c: got[c] for c in PB.F13_COLS}, meta)


def part_eightk(run_id: str) -> int:
    from backend.services import crsp_pit_bridges as PB              # noqa: PLC0415
    if _refuse_if_exists(OUT / f"pit_eightk_{run_id}.parquet"):
        return 2
    t0 = time.time()
    ek = pd.read_parquet(OPT / "edgar_8k" / "eightk_items.parquet",
                         columns=["ticker", "permno", "acceptance_datetime", "filing_date", "items_joined"])
    ek["day0"] = pd.to_datetime(ek["filing_date"], errors="coerce")
    has = ek["permno"].notna()
    names = _dsenames().dropna(subset=["ticker"])
    lk, link_meta = PB.dated_link(ek[~has].drop(columns=["permno"]).dropna(subset=["day0", "ticker"]), names,
                                  key="ticker", day_col="day0", lo="namedt", hi="nameendt")
    ek = pd.concat([ek[has], lk], ignore_index=True)
    ev = PB.eightk_events(ek)
    keys = _keys()
    dates = sorted(keys["date"].unique())
    pan = PB.eightk_panel(ev, dates)
    pan["permno"] = pan["permno"].astype("float64")
    m = keys.merge(pan, on=["date", "permno"], how="left")
    meta = {"source": "edgar_8k/eightk_items.parquet (EDGAR submissions API, 2013-01 .. 2026-09)",
            "timing": "acceptance time in New York; usable from the next business day",
            "link": {"rows_with_permno_in_file": int(has.sum()), "ticker_dated_link": link_meta},
            "n_filings": int(len(ev)), "first": str(ev["day"].min().date()), "last": str(ev["day"].max().date()),
            "SURVIVORSHIP_WARNING": ("the 8-K pull covered 2,594 CIKs chosen from TODAY's ticker list and starts "
                                     "2013: dead issuers are absent and there is no design window (1991-2008). "
                                     "8-K rules are run as DESCRIPTION only and cannot meet the decision line."),
            "seconds": round(time.time() - t0, 1)}
    return _write_bridge("eightk", run_id, keys, {c: m[c].to_numpy() for c in PB.EIGHTK_COLS}, meta)


def _ibes_targets() -> tuple[pd.DataFrame, dict]:
    from backend.services import crsp_event_bridge as B               # noqa: PLC0415
    link = pd.read_parquet(BULK / "wrdsapps_link_crsp_ibes__ibcrsphist.parquet")
    link["score"] = pd.to_numeric(link["score"], errors="coerce").fillna(9)
    ptg = pd.read_parquet(BULK / "ibes__ptgdet.parquet", columns=["ticker", "estimid", "value", "anndats", "actdats",
                                                                  "horizon", "curr", "usfirm"],
                          filters=[("usfirm", "=", 1)])
    ptg = ptg[(ptg["horizon"].astype(str) == "12") & (ptg["curr"].astype(str) == "USD")]
    ptg["day"] = B.event_day(ptg["anndats"], ptg["actdats"]).to_numpy()
    ptg = ptg.dropna(subset=["day", "value"])[["ticker", "estimid", "value", "day"]]
    ptg, meta = B.link_permno(ptg, link)
    ptg = ptg.rename(columns={"estimid": "broker"})
    ptg["value"] = ptg["value"].astype(float)
    ptg = B.target_signs(ptg)
    ptg["usable"] = B.usable_date(ptg["day"]).to_numpy()
    return ptg[["permno", "broker", "day", "usable", "sign", "value"]].reset_index(drop=True), meta


def part_analyst2(run_id: str) -> int:
    from backend.services import crsp_pit_bridges as PB              # noqa: PLC0415
    from backend.services import pit_features as PF                  # noqa: PLC0415
    from scripts import momentum_on_crsp as M                         # noqa: PLC0415
    if _refuse_if_exists(OUT / f"pit_analyst2_{run_id}.parquet"):
        return 2
    t0 = time.time()
    ev, link_meta = _ibes_targets()
    say(f"  targets {len(ev):,} {time.time()-t0:.0f}s")
    mkt = M.market_daily()
    parts = []
    for y in range(1999, 2025):
        sub = ev[pd.DatetimeIndex(ev["day"]).year == y]
        if not len(sub):
            continue
        wait_for_memory()
        fr = []
        if y > 1990:
            fr.append(pd.read_parquet(WRDS / f"crsp_dsf_{y-1}.parquet", columns=["permno", "date", "ret"],
                                      filters=[("date", ">=", pd.Timestamp(f"{y-1}-08-01"))]))
        fr.append(pd.read_parquet(WRDS / f"crsp_dsf_{y}.parquet", columns=["permno", "date", "ret"]))
        if y < 2024:
            fr.append(pd.read_parquet(WRDS / f"crsp_dsf_{y+1}.parquet", columns=["permno", "date", "ret"],
                                      filters=[("date", "<=", pd.Timestamp(f"{y+1}-05-15"))]))
        dly = pd.concat(fr, ignore_index=True)
        dly["date"] = pd.to_datetime(dly["date"])
        dly["permno"] = pd.to_numeric(dly["permno"], errors="coerce").astype("int64")
        dly = dly[dly["permno"].isin(set(sub["permno"]))]
        parts.append(PB.price_context(sub, dly, mkt))
        say(f"  {y}: {len(sub):,} events priced {time.time()-t0:.0f}s")
        del dly, fr
        gc.collect()
    ev = pd.concat(parts, ignore_index=True)
    del parts
    ev["first_mover"] = False
    rz = ev["sign"] > 0
    ev.loc[rz, "first_mover"] = PB.first_movers(ev.loc[rz, ["permno", "day"]])
    keys = _keys()
    dates = sorted(keys["date"].unique())
    pan = PB.analyst2_panel(ev, dates)
    diag = pan.groupby("date")[["_n_skilled", "_n_active", "_n_active_skilled"]].first()
    pan = pan.drop(columns=["_n_skilled", "_n_active", "_n_active_skilled"])
    pan["permno"] = pan["permno"].astype("float64")
    m = keys.merge(pan, on=["date", "permno"], how="left")
    say(f"  lead/chase/skill panel {time.time()-t0:.0f}s")
    cols = {c: m[c].to_numpy() for c in PB.ANALYST2_COLS}
    raises = ev[ev["sign"] > 0]
    cols["cluster_age_days"] = PB.cluster_age_panel(raises, keys)
    # analyst_skill_weight (pit_features.skill_features) with walk-forward IBES reliability
    rev = ev[ev["sign"] != 0].sort_values("usable", kind="mergesort")
    prep = pd.DataFrame({"ticker": rev["permno"].to_numpy(), "t": rev["usable"].to_numpy(),
                         "sign": rev["sign"].to_numpy(), "estimid": rev["broker"].to_numpy(),
                         "firm": rev["broker"].to_numpy()})
    claims = PB.reliability_claims(ev)
    dts = pd.DatetimeIndex(dates)
    sk = PF.skill_features(prep, claims, dts)
    say(f"  analyst_skill_weight {time.time()-t0:.0f}s")
    clus = PF.revision_clusters(prep.sort_values("t", kind="mergesort").reset_index(drop=True))
    fm = PF.first_mover_features(clus, dts)
    say(f"  first_mover_rank {time.time()-t0:.0f}s")
    for fr_, c in ((sk, "analyst_skill_weight"), (fm, "first_mover_rank")):
        x = fr_[["ticker", "date", c]].rename(columns={"ticker": "permno"})
        x["permno"] = x["permno"].astype("float64")
        x["date"] = pd.to_datetime(x["date"])
        cols[c] = keys.merge(x, on=["date", "permno"], how="left")[c].to_numpy()
    raised = ev[ev["sign"] > 0]
    meta = {"source": "wrds/bulk/ibes__ptgdet.parquet (12m USD targets, usfirm=1) + crsp_dsf daily returns",
            "ibes_link": link_meta, "n_targets": int(len(ev)),
            "timing": ("event day = max(anndats, actdats); usable = day + 1 BDay <= d. ret10 ends the session "
                       "BEFORE the event day; exc63 runs from the event session's close 63 sessions on and a raise "
                       "enters a broker's skill record only once that 63rd session is <= d. first mover: no raise "
                       "by any broker on the name in [day-30, day). analyst_skill_weight: pit_features."
                       "skill_features with IBES revisions as claims (outcome = sign x exc63 > 0), counted only "
                       "after resolution; first_mover_rank: pit_features.revision_clusters / "
                       "first_mover_features on usable dates"),
            "lead_share_of_raises": round(float((raised["ret10"] <= 0).mean()), 4),
            "chase_share_of_raises": round(float((raised["ret10"] > raised["sig10"]).mean()), 4),
            "first_mover_share_of_raises": round(float(raised["first_mover"].mean()), 4),
            "priced_share": round(float(ev["ret10"].notna().mean()), 4),
            "resolved_share": round(float(ev["res_day"].notna().mean()), 4),
            "skilled_brokers_by_year": {str(y): int(g["_n_skilled"].median()) for y, g in
                                        diag.groupby(pd.DatetimeIndex(diag.index).year)},
            "active_skilled_share_by_year": {str(y): round(float((g["_n_active_skilled"] / g["_n_active"]).median()), 3)
                                             for y, g in diag.groupby(pd.DatetimeIndex(diag.index).year)},
            "analyst_skill_1": ("NOT re-run and not reused as weights: its broker skills were estimated on "
                                "2013-2018, a look-ahead for any decision before 2019. Verdict "
                                "docs/ANALYST_SKILL_1_VERDICT_2026-09-26.md (ADOPT at ~1/12 of the declared effect)."),
            "seconds": round(time.time() - t0, 1)}
    ev_sample = ev[ev["sign"] > 0].sample(n=min(40, int(rz.sum())), random_state=7)[
        ["permno", "broker", "day", "usable", "ret10", "sig10", "exc63", "res_day", "first_mover"]]
    meta["row_by_row_timing_sample"] = json.loads(ev_sample.to_json(orient="records", date_format="iso"))
    return _write_bridge("analyst2", run_id, keys, cols, meta)


def _msf_mv() -> pd.DataFrame:
    m = pd.read_parquet(BULK / "crsp__msf.parquet", columns=["permno", "date", "prc", "shrout"])
    m["date"] = pd.to_datetime(m["date"])
    m["mv"] = pd.to_numeric(m["prc"], errors="coerce").abs() * pd.to_numeric(m["shrout"], errors="coerce") * 1000.0
    m["permno"] = pd.to_numeric(m["permno"], errors="coerce").astype("int64")
    return m.dropna(subset=["mv"])[["permno", "date", "mv"]]


def part_fund(run_id: str) -> int:
    from backend.services import crsp_pit_bridges as PB              # noqa: PLC0415
    from backend.services import pit_features as PF                  # noqa: PLC0415
    from backend.services import strategy_library_ext as EXT         # noqa: PLC0415
    if _refuse_if_exists(OUT / f"pit_fund_{run_id}.parquet"):
        return 2
    t0 = time.time()
    wait_for_memory()
    cols = ["gvkey", "datadate", "fqtr", "rdq", "saleq", "cogsq", "oiadpq", "niq", "atq", "cheq", "dlttq", "dlcq",
            "ceqq", "xrdq", "xsgaq", "curcdq"]
    q = pd.read_parquet(BULK / "comp__fundq.parquet", columns=cols,
                        filters=[("indfmt", "=", "INDL"), ("datafmt", "=", "STD"), ("consol", "=", "C"),
                                 ("popsrc", "=", "D"), ("datadate", ">=", pd.Timestamp("1985-01-01").date())])
    q["datadate"] = pd.to_datetime(q["datadate"])
    n_raw = len(q)
    q = q.drop_duplicates(["gvkey", "datadate"], keep="last")
    link = pd.read_parquet(WRDS / "link_ccm.parquet")
    link = link[link["linktype"].isin(["LC", "LU"]) & link["linkprim"].isin(["P", "C"])].copy()
    link["_rank"] = PB.ccm_rank(link)
    q, link_meta = PB.dated_link(q, link, key="gvkey", day_col="datadate", rank_col="_rank")
    say(f"  fundq {n_raw:,} rows, linked {link_meta} {time.time()-t0:.0f}s")
    f = PB.fund_features(q)
    del q
    gc.collect()
    say(f"  features {time.time()-t0:.0f}s")
    keys = _keys()
    got = PB.asof_panel(keys, f, PB.FUND_COLS + PB.FUND_LEVEL_COLS, on="available",
                        age_from="available", max_age_days=PB.FUND_STALE_DAYS)
    out = {c: got[c].to_numpy() for c in PB.FUND_COLS}
    # market value at the decision month end (CRSP msf |prc| x shrout), value ratios, distance to default
    mv = PB.asof_panel(keys, _msf_mv().rename(columns={"date": "mdate"}), ["mv"], on="mdate", age_from="mdate",
                       max_age_days=40)["mv"].to_numpy()
    out.update(PB.value_columns(mv, got["_ni_ttm"], got["_oi_ttm"], got["_debt"], got["_cash"], got["_ceq"]))
    P = pd.read_parquet(OUT / f"library_panel_{PANEL_RUN}.parquet", columns=["vol_252", "mom_252"])
    dd = EXT.distance_to_default(mv, got["_debt"].to_numpy(dtype=float) * 1e6, P["vol_252"].to_numpy(dtype=float),
                                 P["mom_252"].to_numpy(dtype=float))
    out["d2d"] = dd
    out["d2d_chg"] = EXT.prev_panel_change(keys, dd)
    del P
    # pricing power under cost pressure: fiscal-Q4 TTM gross-margin change x the in-house cost-pressure proxy
    ff_ = f.sort_values(["gvkey", "datadate"])
    # COGS growth of the TTM year vs the TTM year four quarters earlier (from the level columns)
    margins = pd.DataFrame({"filed": ff_["available"] - pd.Timedelta(days=PF.FUND_LAG_DAYS),
                            "cogs_growth": np.nan})
    gm = ff_["gross_margin_q"].to_numpy(dtype=float)
    rg = ff_["rev_gr"].to_numpy(dtype=float)
    gmc = ff_["gm_chg"].to_numpy(dtype=float)
    # cogs_t / cogs_{t-4} - 1 = (1+rev_gr)*(1-gm_t)/(1-gm_{t-4}) - 1, with gm_{t-4} = gm_t - gm_chg
    with np.errstate(divide="ignore", invalid="ignore"):
        cg = (1.0 + rg) * (1.0 - gm) / (1.0 - (gm - gmc)) - 1.0
    margins["cogs_growth"] = np.where(np.isfinite(cg), cg, np.nan)
    cpd = PF.cost_pressure_proxy(margins, pd.DatetimeIndex(sorted(keys["date"].unique())))
    cp = keys[["date"]].merge(cpd[["date", "cost_pressure"]], on="date", how="left")["cost_pressure"].to_numpy()
    out["pricing_power_cost_pressure"] = np.where(cp > 0, got["gm_chg"].to_numpy(dtype=float) * cp, np.nan)
    meta = {"source": "wrds/bulk/comp__fundq.parquet (INDL/STD/C/D) + wrds/link_ccm.parquet + crsp__msf",
            "timing": (f"usable from max(rdq, datadate + {PB.FUND_DEADLINE_Q} days (fqtr 1-3) or "
                       f"{PB.FUND_DEADLINE_Q4} days (fqtr 4)) + {PB.FUND_EXTRA_DAYS} days; stale after "
                       f"{PB.FUND_STALE_DAYS} days; gvkey -> permno by the CCM row active on datadate"),
            "definitions": ("TTM flows (four consecutive quarters); one year earlier = four quarters back; "
                            "operating income = oiadpq; debt = dlttq + dlcq; mkt value = CRSP msf |prc| x shrout "
                            "at the latest month end <= d; earnings_yield/ebit_ev/ebit_ic/d2d as "
                            "strategy_library_ext; org_capital = perpetual inventory on TTM SG&A at fiscal Q4 "
                            "(15% depreciation); pricing_power_cost_pressure = gm_chg x the in-house cost-pressure "
                            "proxy (pit_features.cost_pressure_proxy on Compustat COGS growth)"),
            "ccm_link": link_meta, "fundq_rows": int(n_raw),
            "caveat": ("Compustat stores the CURRENT vintage of each value, not the as-first-reported one "
                       "(restatements leak); the deadline rule is conservative for accelerated filers"),
            "seconds": round(time.time() - t0, 1)}
    return _write_bridge("fund", run_id, keys, out, meta)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", required=True,
                    choices=["si", "f13", "eightk", "analyst2", "fund", "declare", "run", "turnover", "board"])
    ap.add_argument("--run-id")
    ap.add_argument("--declaration")
    ap.add_argument("--cs", action="store_true")
    ap.add_argument("--flat-run")
    ap.add_argument("--cs-run")
    ap.add_argument("--turnover-run")
    ap.add_argument("--fair-run", help="board: the fair-twin board run (scripts.hyp_twin_board) with each "
                                       "twin's own measured turnover; required")
    a = ap.parse_args(argv)
    if a.part != "board" and not wait_for_memory():     # the board reads small series only
        say("REFUSED: under 3 GB free memory for 30 minutes")
        return 3
    rid = a.run_id or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    fn = {"si": part_si, "f13": part_f13, "eightk": part_eightk, "analyst2": part_analyst2, "fund": part_fund}
    if a.part in fn:
        return fn[a.part](rid)
    from scripts import bridges_on_crsp_run as R                    # noqa: PLC0415
    if a.part == "declare":
        return R.part_declare(rid)
    if a.part == "run":
        return R.part_run(a.declaration, rid, a.cs)
    if a.part == "turnover":
        return R.part_turnover(a.declaration, rid)
    return R.part_board(a.declaration, a.flat_run, a.cs_run, a.turnover_run, a.fair_run)


if __name__ == "__main__":
    raise SystemExit(main())
