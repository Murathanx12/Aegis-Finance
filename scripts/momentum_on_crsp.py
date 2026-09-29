"""The momentum leads rebuilt on CRSP total returns (2026-09-29).

    python -m scripts.momentum_on_crsp --part panel          # CRSP panel, era by era (local parquet)
    python -m scripts.momentum_on_crsp --part run --panel-run <id>    # the four leads + benchmark
    python -m scripts.momentum_on_crsp --part slots --panel-run <id>  # vendor vs CRSP top-20 slots
    python -m scripts.momentum_on_crsp --part emulate --panel-run <id>  # the vendor universe rule on CRSP

Licence `PRODUCT_EXPERIMENT`, $0, no LLM, no network. HINDSIGHT: every rule was
registered 2026-09-26, after every month here -- but 1991-2016 was never seen
by the library's development (the vendor panel starts 2016), so it is a
FOREIGN slice for these rules.

WHAT IT RUNS: the library's own engine, unchanged -- `night_backtest_factory.
build_panel` on a CRSP `load_wide` dict (`backend/services/crsp_rebuild.py`
explains the bridge), `strategy_library.run_strategy` at each quarterly offset,
costs on (band costs), the 21-draw matched twin on size band x vol_63 x 12-1
(two disjoint seed sets), `calendar_offsets.classify` (the declared v2 rule),
the calendar-neutral tranche average, by hold year, leave-one-hold-year-out,
MDE beside every t, share of total by date, the bet-count curve, a Fama-French
four-factor verdict, and the academic benchmark (EW decile spread and the
top decile vs the EW universe) on the same panel.

WHAT IT WRITES (all under `backend/data/optimus/crsp_rebuild/`, run id in every
name, never overwritten): `panel_<id>.parquet` + `panel_<id>.json` (local
panel, gitignored, and its receipt), `momentum_on_crsp_<id>.json` (+ the
monthly series parquet), `slots_<id>.json`. No book, ledger, bar file or past
receipt is touched.
"""
from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                              # noqa: E402
from backend.services import calendar_offsets as CO             # noqa: E402
from backend.services import crsp_rebuild as CR                 # noqa: E402
from backend.services import matched_twins as MT                # noqa: E402
from backend.services import strategy_library as SL             # noqa: E402
from scripts import night_backtest_factory as F                 # noqa: E402
from scripts.calendar_offset_triplet import peak_rss_mb, run_one  # noqa: E402
from scripts.night_checkpoint import atomic_write_json          # noqa: E402

JOB = "momentum_on_crsp"
OPT = REPO / "backend" / "data" / "optimus"
WRDS = OPT / "wrds"
OUT = OPT / "crsp_rebuild"
#: decision-year eras; each loads two warm-up years before and one after
ERAS = ((1991, 1995), (1996, 2000), (2001, 2005), (2006, 2010), (2011, 2015),
        (2016, 2020), (2021, 2024))
FIRST_YEAR, LAST_YEAR = 1990, 2024
LEADS = ("mom_12_1_q", "mom_12_1_q_trend", "qc470_mom252_quarterly_riskparity")
DISP = "disp_short_avoid"
K = 20
#: the vendor SCREEN receipt the brief reads against (2026-09-29, reader default)
VENDOR_RECEIPT = "calendar_offsets_2026-09-29T034413Z"
PANEL_COLS = ("date", "symbol", "close", "eligible", "fwd_ret", "delisted_in_period",
              "is_month_end", "median_dollar_vol", "dollar_vol_log", "vol_63", "mom_63",
              "mom_252_21", "mom_252", "mkt_trend_up", "amihud")
#: hold-month windows every read is printed on
WINDOWS = {"full": (None, None), "1991_2000": ("1991-01-01", "2000-12-31"),
           "2001_2010": ("2001-01-01", "2010-12-31"), "2011_2016": ("2011-01-01", "2016-12-31"),
           "pre_vendor_1991_2016": (None, "2016-12-31"),
           "vendor_overlap_2017_2024": ("2017-01-01", "2024-12-31"),
           "2020_2024": ("2020-01-01", "2024-12-31"), "sealed_overlap_2024": ("2024-01-01", "2024-12-31")}


def say(*a) -> None:
    print(*a, flush=True)


def market_daily() -> pd.Series:
    ff = pd.read_parquet(WRDS / "ff_factors_daily.parquet", columns=["date", "mktrf", "rf"])
    ff["date"] = pd.to_datetime(ff["date"])
    return (ff.set_index("date")["mktrf"] + ff.set_index("date")["rf"]).astype(float)


def load_years(y0: int, y1: int) -> pd.DataFrame:
    frames = []
    for y in range(max(y0, FIRST_YEAR), min(y1, LAST_YEAR) + 1):
        frames.append(pd.read_parquet(WRDS / f"crsp_dsf_{y}.parquet",
                                      columns=["permno", "date", "prc", "ret", "vol", "openprc",
                                               "cfacpr"]))
    d = pd.concat(frames, ignore_index=True)
    del frames
    for c in ("prc", "ret", "vol", "openprc", "cfacpr"):
        d[c] = pd.to_numeric(d[c], errors="coerce").astype("float64")
    return d


# ── part 1: the panel ────────────────────────────────────────────────────────

def part_panel(run_id: str) -> int:
    from backend.services import xs_ranker as XR                  # noqa: PLC0415
    OUT.mkdir(parents=True, exist_ok=True)
    pq_path, rj = OUT / f"panel_{run_id}.parquet", OUT / f"panel_{run_id}.json"
    if pq_path.exists() or rj.exists():
        say(f"REFUSED: {pq_path.name} exists; a receipt is never overwritten")
        return 2
    t0 = time.time()
    mkt = market_daily()
    dl = pd.read_parquet(WRDS / "bulk" / "crsp__dsedelist.parquet",
                         columns=["permno", "dlstdt", "dlstcd", "dlret"])
    dl["dlstdt"] = pd.to_datetime(dl["dlstdt"])
    for c in ("dlstcd", "dlret"):
        dl[c] = pd.to_numeric(dl[c], errors="coerce").astype("float64")
    parts, audits = [], []
    for a, b in ERAS:
        te = time.time()
        daily = load_years(a - 2, b + 1)
        W = CR.wide_from_crsp(daily, dl, mkt)
        n_daily = len(daily)
        del daily
        gc.collect()
        with CR.price_band_disabled(XR) as (lo, hi):
            panel = F.build_panel(W, delist_return=0.0, min_index=252)
        panel = CR.apply_actual_price(panel, W, min_price=lo, max_price=hi)
        yrs = pd.DatetimeIndex(panel["date"]).year
        panel = panel[(yrs >= a) & (yrs <= b) & panel["is_month_end"].astype(bool)]
        panel = panel[[c for c in PANEL_COLS if c in panel.columns]].reset_index(drop=True)
        au = dict(W["audit"], era=[a, b], daily_rows_loaded=int(n_daily),
                  panel_rows=int(len(panel)), decision_dates=int(panel["date"].nunique()),
                  eligible_per_date_median=float(panel.groupby("date")["eligible"].sum().median()),
                  delisted_in_period_rows=int(panel["delisted_in_period"].sum()),
                  seconds=round(time.time() - te, 1), peak_mb=peak_rss_mb())
        audits.append(au)
        say(f"  era {a}-{b}: {au['symbols']} permnos, {au['sessions']} sessions, open share "
            f"{au['open_share']:.2f}, dlret booked {au['delisting_returns_booked']} "
            f"(-30% fills {au['delisting_missing_dlret_filled']}); panel {au['panel_rows']:,} rows, "
            f"{au['decision_dates']} dates, median eligible {au['eligible_per_date_median']:.0f}; "
            f"{au['seconds']}s peak {au['peak_mb']} MB")
        parts.append(panel)
        del W, panel
        gc.collect()
    P = pd.concat(parts, ignore_index=True)
    P.to_parquet(pq_path, index=False)
    doc = {"schema": "crsp_rebuild/panel/1", "job": JOB, "run_id": run_id,
           "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "panel_parquet": str(pq_path.relative_to(REPO)).replace("\\", "/"),
           "panel_parquet_is_local": "gitignored (*.parquet); rebuild with --part panel",
           "rows": int(len(P)), "dates": int(P["date"].nunique()),
           "symbols": int(P["symbol"].nunique()),
           "first": str(pd.Timestamp(P["date"].min()).date()),
           "last": str(pd.Timestamp(P["date"].max()).date()),
           "construction": CR.__doc__.split("THE BRIDGE", 1)[1].strip(),
           "inputs": {"daily": "wrds/crsp_dsf_<y>.parquet 1990-2024 (every permno of the PIT universe "
                               "files: shrcd 10/11, exchcd 1-3; dead names included)",
                      "delisting": "wrds/bulk/crsp__dsedelist.parquet",
                      "market": "wrds/ff_factors_daily.parquet mktrf + rf (NOT SPY)"},
           "eligibility": SL.ELIGIBLE_TEXT + " -- price floor on the ACTUAL |prc|",
           "eras": audits, "seconds": round(time.time() - t0, 1), "peak_mb": peak_rss_mb()}
    atomic_write_json(rj, F._round(doc), indent=1)
    say(f"-> {pq_path.name} ({len(P):,} rows) + {rj.name}  {time.time()-t0:.0f}s")
    return 0


# ── part 2: the leads ────────────────────────────────────────────────────────

def load_panel(panel_run: str) -> pd.DataFrame:
    P = pd.read_parquet(OUT / f"panel_{panel_run}.parquet")
    P["date"] = pd.to_datetime(P["date"])
    P["eligible"] = P["eligible"].astype(bool)
    P["tiebreak"] = SL._tiebreak(P)
    return P


def spy_series(panel: pd.DataFrame) -> pd.Series:
    dates = pd.DatetimeIndex(sorted(panel["date"].unique()))
    return F._compound_onto(market_daily(), dates)


def ff_monthly() -> pd.DataFrame:
    f = pd.read_parquet(WRDS / "ff_factors_monthly.parquet", columns=["date", "mktrf", "smb", "hml",
                                                                        "rf", "umd"])
    f["month"] = pd.to_datetime(f["date"]).dt.to_period("M")
    return f.set_index("month")[["mktrf", "smb", "hml", "rf", "umd"]].astype(float)


def on_hold_months(s: pd.Series, ff: pd.DataFrame) -> pd.DataFrame:
    """FF factors aligned to a decision-date-keyed monthly series (hold month =
    decision + 1 business day)."""
    hp = SL.hold_periods(s.index)
    return ff.reindex(hp).set_index(pd.DatetimeIndex(s.index))


def factor_read(net: pd.Series, ff: pd.DataFrame, *, hold_months: int = 3) -> dict:
    from backend.services import signal_structure as SS           # noqa: PLC0415
    X = on_hold_months(net, ff)
    y = net - X["rf"]
    out = {}
    for name, cols in (("capm", ["mktrf"]), ("ff3", ["mktrf", "smb", "hml"]),
                       ("ff3_umd", ["mktrf", "smb", "hml", "umd"])):
        try:
            o = SS.ols(y, X[cols], hold_months=hold_months)
        except Exception as e:                                    # noqa: BLE001 -- named
            out[name] = {"status": f"NOT_COMPUTED: {type(e).__name__}: {e}"}
            continue
        obs = float((y - X["mktrf"]).mean())
        out[name] = {"alpha_monthly": o["alpha_monthly"],
                     "t_alpha_used": o["t_alpha_used"], "mde_alpha_80_used": o["mde_alpha_80_used"],
                     "betas": o["betas"], "r2": o["r2"], "n": o.get("n"),
                     "observed_excess_vs_market_monthly": obs,
                     "verdict": CR.factor_verdict(o["t_alpha_used"], o["mde_alpha_80_used"], obs)}
    return out


def windows_of(diff: pd.Series) -> dict:
    return {k: CR.window_stats(diff, lo, hi, mde_z=CO.MDE_Z) for k, (lo, hi) in WINDOWS.items()}


def run_rule_set(panel, spy, benches, rule_ids, *, n_spy, n_twin, tag: str) -> tuple[dict, list]:
    grid = sorted(pd.DatetimeIndex(panel.loc[panel["fwd_ret"].notna(), "date"].unique()))
    by_date = MT.panel_by_date(panel)
    cache: dict = {}
    results, series_rows = {}, []
    for rid in rule_ids:
        rule = SL.rule_by_id(rid)
        t0 = time.time()
        say(f"  [{tag}] {rid} (hold {rule.hold_months}, weight {rule.weight_rule}, "
            f"gate {rule.regime_gate or '-'})")
        entry = {"meta": {"id": rid, "k": K, "weight_rule": rule.weight_rule,
                          "regime_gate": rule.regime_gate, "universe_rule": rule.universe_rule,
                          "fingerprint": rule.fingerprint()}, "offsets": {}}
        try:
            entry["default"] = run_one(panel, spy, benches, rule, k=K, by_date=by_date, cache=cache,
                                       grid=grid, n_spy=n_spy, n_twin=n_twin, log=say,
                                       flagged=set(), refuse_defects=False)
            for otag, var in CO.offset_variants(rule).items():
                entry["offsets"][otag] = run_one(panel, spy, benches, var, k=K, by_date=by_date,
                                                 cache=cache, grid=grid, n_spy=n_spy, n_twin=n_twin,
                                                 log=say, flagged=set(), refuse_defects=False)
        except (CO.OffsetInputMissing, MT.TwinInputMissing, SL.RuleInputMissing) as e:
            results[rid] = {"refused": f"{type(e).__name__}: {e}"}
            say(f"    REFUSED {rid}: {e}")
            continue
        entry["default"].pop("_series", None)
        for r_ in [entry["default"], *entry["offsets"].values()]:
            r_.pop("bar_defect_slots", None)
        entry["classification"] = CO.classify(entry["offsets"])
        ser = {otag: r.pop("_series") for otag, r in entry["offsets"].items()}
        entry["tranche_average"] = CO.tranche_average(ser)
        for otag, df in ser.items():
            series_rows.append(df.assign(rule=rid, offset=otag, leg=tag).reset_index()
                               .rename(columns={"index": "date"}))
        common = None
        for df in ser.values():
            common = df.index if common is None else common.intersection(df.index)
        common = pd.DatetimeIndex(sorted(common))
        rn = pd.concat([df["rule_net"].reindex(common) for df in ser.values()], axis=1).mean(axis=1)
        tn = pd.concat([df["twin21_net"].reindex(common) for df in ser.values()], axis=1).mean(axis=1)
        sp = next(iter(ser.values()))["spy"].reindex(common)
        diff = rn - tn
        entry["neutral"] = {
            "rule_minus_twin21_windows": windows_of(diff),
            "rule_minus_market_windows": windows_of(rn - sp),
            "by_hold_year_rule_minus_twin21": CO.by_hold_year(diff),
            "loo_worst_rule_minus_twin21": CO.loo_worst(diff),
            "share_of_total_by_date_rule_minus_twin21": CR.share_of_total_by_date(diff),
            "cagr_net": SL._cagr(rn), "cagr_market": SL._cagr(sp.dropna()),
            "cagr_twin21": SL._cagr(tn), "max_dd_net": SL._max_dd(rn),
            "twin_verdict_full": CR.twin_verdict(windows_of(diff)["full"]),
        }
        entry["_neutral_series"] = pd.DataFrame({"rule_net": rn, "twin21_net": tn, "market": sp})
        cl = entry["classification"]
        w = entry["neutral"]["rule_minus_twin21_windows"]
        def _w(k):
            x = w.get(k) or {}
            m_, t_, e_ = x.get("mean_monthly"), x.get("t_blocks"), x.get("mde_monthly")
            return ("n/a" if m_ is None else f"{m_*100:+.2f}%/mo") +                 (f" t {t_:+.2f}" if t_ is not None else "") + (f" MDE {e_*100:.2f}" if e_ is not None else "")
        say(f"    {rid}: calendar {cl['verdict']} ({cl['why']}); neutral rule-twin full {_w('full')}; "
            f"pre-vendor {_w('pre_vendor_1991_2016')}; overlap {_w('vendor_overlap_2017_2024')}  "
            f"{time.time()-t0:.0f}s peak {peak_rss_mb()} MB")
        results[rid] = entry
    return results, series_rows


def vendor_neutral(rid: str) -> dict:
    """The vendor SCREEN tranche for the same rule, restricted to 2017-2024 hold
    months, from the receipt's own monthly parquet."""
    p = OPT / "strategy_library" / f"calendar_offsets_monthly_{VENDOR_RECEIPT.split('_', 2)[2]}.parquet"
    if not p.exists():
        return {"status": f"NOT_COMPUTED: {p.name} absent"}
    m = pd.read_parquet(p)
    m = m[m["rule"] == rid]
    if not len(m):
        return {"status": "NOT_COMPUTED: rule absent"}
    t = m.pivot_table(index="date", columns="offset", values=["rule_net", "twin21_net"]).dropna()
    rn, tn = t["rule_net"].mean(axis=1), t["twin21_net"].mean(axis=1)
    d = rn - tn
    return {"source": p.name, "full_2017_2026": CR.window_stats(d, None, None, mde_z=CO.MDE_Z),
            "overlap_2017_2024": CR.window_stats(d, "2017-01-01", "2024-12-31", mde_z=CO.MDE_Z),
            "by_hold_year": CO.by_hold_year(d)}


def benchmark(panel: pd.DataFrame, ff: pd.DataFrame, spy: pd.Series) -> tuple[dict, pd.DataFrame]:
    dec = CR.decile_returns(panel)
    dec["umd_ew"] = dec["d10"] - dec["d1"]
    dec["top_minus_ew"] = dec["d10"] - dec["ew"]
    # JT 3-month overlapping top decile, EW, gross
    p = panel[panel["eligible"] & panel["mom_252_21"].notna() & panel["fwd_ret"].notna()]
    dates = sorted(p["date"].unique())
    tops, fwd = {}, {}
    for d, g in p.groupby("date", sort=True):
        q = g["mom_252_21"].quantile(0.9)
        tops[d] = g.loc[g["mom_252_21"] >= q, "symbol"].tolist()
    for d, g in panel[panel["fwd_ret"].notna()].groupby("date", sort=True):
        fwd[d] = dict(zip(g["symbol"], g["fwd_ret"].astype(float)))
    dec["jt3_top"] = CR.jt_overlap(tops, fwd, dates, hold=3).reindex(dec.index)
    dec["jt3_top_minus_ew"] = dec["jt3_top"] - dec["ew"]
    X = on_hold_months(dec["umd_ew"], ff)
    dec["ff_umd"] = X["umd"].to_numpy()
    out = {}
    for col in ("umd_ew", "top_minus_ew", "jt3_top_minus_ew", "ff_umd"):
        s = dec[col].dropna()
        out[col] = {"windows": {k: CR.window_stats(s, lo, hi, block=1, mde_z=CO.MDE_Z)
                                for k, (lo, hi) in WINDOWS.items()},
                    "by_hold_year_sum": CO.by_hold_year(s),
                    "share_of_total_by_date": CR.share_of_total_by_date(s)}
    # the published UMD after CRSP ends (FF monthly runs past 2024)
    fu = ff["umd"]
    out["ff_umd_published"] = {
        str(k): {"mean_monthly": float(fu[(fu.index >= pd.Period(a, "M")) & (fu.index <= pd.Period(b, "M"))].mean()),
                 "n_months": int(((fu.index >= pd.Period(a, "M")) & (fu.index <= pd.Period(b, "M"))).sum())}
        for k, (a, b) in {"1927_1990": ("1927-01", "1990-12"), "1991_2000": ("1991-01", "2000-12"),
                          "2001_2010": ("2001-01", "2010-12"), "2011_2016": ("2011-01", "2016-12"),
                          "2017_2024": ("2017-01", "2024-12"), "2025_2026H1": ("2025-01", "2026-06")}.items()}
    out["note"] = ("EW deciles of 12-1 momentum over the ELIGIBLE panel names (engine floors), "
                   "monthly rebalanced, gross of costs (academic convention); the Fama-French UMD "
                   "(value-weighted, NYSE breakpoints, gross) is printed beside it. The t for a "
                   "monthly series uses 1-month blocks (non-overlapping by construction).")
    return out, dec


def bet_count(series: dict) -> dict:
    from backend.services import signal_structure as SS           # noqa: PLC0415
    df = pd.DataFrame(series).dropna()
    if df.shape[1] < 2 or len(df) < 24:
        return {"status": "NOT_COMPUTED"}
    corr = df.corr()
    return {"n_series": int(df.shape[1]), "n_months": int(len(df)), "series": list(df.columns),
            "clusters_by_rho": SS.cluster_curve(corr), **SS.pair_rho_summary(corr),
            "corr": {f"{a}|{b}": float(corr.loc[a, b]) for i, a in enumerate(corr.columns)
                     for b in corr.columns[i + 1:]}}


def attach_target_cv(panel: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    ptg = pd.read_parquet(WRDS / "bulk" / "ibes__ptgdet.parquet",
                          columns=["ticker", "estimid", "anndats", "value", "horizon", "estcur", "usfirm"])
    ptg = ptg[(ptg["usfirm"] == 1) & (ptg["horizon"] == "12") & (ptg["estcur"] == "USD")]
    ptg["anndats"] = pd.to_datetime(ptg["anndats"])
    ptg["value"] = pd.to_numeric(ptg["value"], errors="coerce")
    lk = pd.read_parquet(WRDS / "bulk" / "wrdsapps_link_crsp_ibes__ibcrsphist.parquet",
                         columns=["ticker", "permno", "sdate", "edate"])
    lk = lk.dropna(subset=["permno"])
    lk["sdate"] = pd.to_datetime(lk["sdate"])
    lk["edate"] = pd.to_datetime(lk["edate"]).fillna(pd.Timestamp("2099-12-31"))
    t = ptg.merge(lk, on="ticker", how="inner")
    t = t[(t["anndats"] >= t["sdate"]) & (t["anndats"] <= t["edate"])]
    t["permno"] = t["permno"].astype("int64")
    n_rows = int(len(t))
    dates = sorted(panel["date"].unique())
    cv = CR.target_cv(t[["permno", "estimid", "anndats", "value"]], dates)
    del t, ptg
    out = panel.merge(cv, on=["date", "symbol"], how="left")
    cov = (out[out["eligible"]].groupby(pd.DatetimeIndex(out.loc[out["eligible"], "date"]).year)
           ["target_cv_180"].apply(lambda s: float(s.notna().mean())))
    return out, {"source": "wrds/bulk/ibes__ptgdet.parquet (IBES split-adjusted 12-month USD targets, "
                           "US firms) linked by wrdsapps ibcrsphist", "linked_rows": n_rows,
                 "definition": "each broker's (estimid) latest target in [d-180d, d); std/mean across "
                               ">= 3 brokers (attach_ratings' target_cv_180)",
                 "eligible_coverage_by_year": {str(k): round(v, 3) for k, v in cov.items()}}


def part_run(panel_run: str, run_id: str) -> int:
    rp = OUT / f"momentum_on_crsp_{run_id}.json"
    if rp.exists():
        say(f"REFUSED: {rp.name} exists")
        return 2
    t0 = time.time()
    pr = json.loads((OUT / f"panel_{panel_run}.json").read_text(encoding="utf-8"))
    panel = load_panel(panel_run)
    if len(panel) != pr["rows"]:
        say(f"REFUSED: panel parquet has {len(panel)} rows, its receipt {pr['rows']}")
        return 2
    say(f"{JOB} run {run_id}: panel {panel_run} {len(panel):,} rows, {panel['date'].nunique()} dates "
        f"{pr['first']}..{pr['last']}, {panel['symbol'].nunique()} permnos; peak {peak_rss_mb()} MB")
    vr = json.loads((OPT / "strategy_library" / f"{VENDOR_RECEIPT}.json").read_text(encoding="utf-8"))
    o0 = vr["results"]["mom_12_1_q"]["offsets"]["jajo"]
    n_spy, n_twin = int(o0["dsr_vs_spy_n_trials"]), int(o0["dsr_rule_minus_twin21_n_trials"])
    spy = spy_series(panel)
    try:
        rpanel, rp_meta = F.random_panel_leg(panel)
    except Exception as e:                                        # noqa: BLE001 -- named
        rpanel, rp_meta = f"RANDOM_PANEL_SERIES_MISSING: {type(e).__name__}: {e}", {"status": "REFUSED"}
    benches = {"iwm": "IWM_SERIES_MISSING: no IWM before 2000 and none on CRSP common stock",
               "random_panel": rpanel}
    say(f"  market = FF mktrf+rf (not SPY); random panel {rp_meta.get('status')}; "
        f"{time.time()-t0:.0f}s")
    ff = ff_monthly()
    results, series_rows = run_rule_set(panel, spy, benches, LEADS, n_spy=n_spy, n_twin=n_twin,
                                        tag="full")
    # disp_short_avoid, paired with mom_12_1_q on the window its input covers
    pcv, cv_meta = attach_target_cv(panel)
    covered = [int(y) for y, v in cv_meta["eligible_coverage_by_year"].items() if v >= 0.25]
    disp = {"input": cv_meta}
    if covered:
        y0 = min(covered)
        sub = pcv[pd.DatetimeIndex(pcv["date"]).year >= y0].reset_index(drop=True)
        sub["tiebreak"] = SL._tiebreak(sub)
        spy_s = spy[spy.index >= pd.Timestamp(f"{y0}-01-01")]
        try:
            rp_s, _ = F.random_panel_leg(sub)
        except Exception as e:                                    # noqa: BLE001
            rp_s = f"RANDOM_PANEL_SERIES_MISSING: {e}"
        dres, dser = run_rule_set(sub, spy_s, {"iwm": benches["iwm"], "random_panel": rp_s},
                                  (DISP, "mom_12_1_q"), n_spy=n_spy, n_twin=n_twin, tag=f"disp_{y0}")
        series_rows += dser
        disp["window_start_year"] = y0
        disp["why_start"] = "first decision year with >= 25% of eligible names carrying a target CV"
        disp["results"] = dres
        if DISP in dres and "mom_12_1_q" in dres and "_neutral_series" in dres[DISP]:
            a, b = dres[DISP]["_neutral_series"], dres["mom_12_1_q"]["_neutral_series"]
            dd = (a["rule_net"] - b["rule_net"]).dropna()
            disp["disp_minus_mom_12_1_q_neutral"] = {"windows": windows_of(dd),
                                                     "by_hold_year": CO.by_hold_year(dd)}
    else:
        disp["status"] = "NOT_COMPUTED: no year with >= 25% target coverage"
    del pcv
    gc.collect()
    bench, dec = benchmark(panel, ff, spy)
    # the four leads' (and the benchmark's) calendar-neutral series: factor read + bet count
    neutral = {rid: e["_neutral_series"] for rid, e in results.items() if "_neutral_series" in e}
    if DISP in (disp.get("results") or {}) and "_neutral_series" in disp["results"][DISP]:
        neutral[DISP] = disp["results"][DISP]["_neutral_series"]
    factors = {rid: {"net": factor_read(df["rule_net"], ff),
                     "rule_minus_twin21": _twin_factor(df, ff)} for rid, df in neutral.items()}
    bc_net = bet_count({**{rid: df["rule_net"] for rid, df in neutral.items()},
                        "top_decile_jt3_ew": dec["jt3_top"]})
    bc_act = bet_count({**{rid: df["rule_net"] - df["twin21_net"] for rid, df in neutral.items()},
                        "top_decile_minus_ew": dec["top_minus_ew"]})
    for e in [*results.values(), *(disp.get("results") or {}).values()]:
        e.pop("_neutral_series", None)
    vendor = {rid: vendor_neutral(rid) for rid in (*LEADS, DISP)}
    monthly_path = OUT / f"momentum_on_crsp_monthly_{run_id}.parquet"
    if series_rows:
        pd.concat(series_rows, ignore_index=True).to_parquet(monthly_path, index=False)
    dec.reset_index().to_parquet(OUT / f"momentum_on_crsp_deciles_{run_id}.parquet", index=False)
    doc = {"schema": "crsp_rebuild/momentum_on_crsp/1", "job": JOB, "run_id": run_id,
           "panel_run": panel_run, "panel_receipt": f"panel_{panel_run}.json",
           "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "label": ("HINDSIGHT for 2017-2024 (the library's development window); 1991-2016 was never "
                     "seen by the library's development and is a FOREIGN slice for these rules"),
           "k": K, "market_leg": "FF daily mktrf + rf compounded over (decision, next decision] -- NOT SPY",
           "iwm": benches["iwm"], "random_panel": rp_meta,
           "verdict_rule_calendar": CO.VERDICT_RULE,
           "verdict_rule_factor": ("signal_structure.verdict: ALPHA_DETECTED |t| >= 2 on the alpha "
                                   "(HAC, lag hold-1); BETA_EXPLAINS |t| < 1 and MDE < observed excess "
                                   "vs market; else CANNOT_DISTINGUISH"),
           "verdict_rule_twin": ("FAILED_VARIANT: calendar-neutral rule - twin21 mean <= 0; "
                                 "ALPHA_DETECTED: mean > 0 at t >= 2 on 3-month blocks; else "
                                 "CANNOT_DISTINGUISH"),
           "dsr_n_trials": {"vs_spy": n_spy, "rule_minus_twin21": n_twin,
                            "source": f"{VENDOR_RECEIPT}.json (the same trial counts as the vendor read)"},
           "windows_hold_month": WINDOWS,
           "conventions": {
               "engine": "strategy_library.run_strategy with rebalance_months; band costs on (cost_scale 1.0)",
               "twin": "matched_twins: size band x vol_63 tercile x 12-1 tercile; 2 x 21 seeded draws",
               "t_blocks": "non-overlapping 3-month blocks on the calendar-neutral series",
               "mde": f"{CO.MDE_Z} x SE, %/month", "by_year": "keyed on the HOLD month"},
           "results": results, "disp_short_avoid": disp,
           "vendor_screen_same_rule": vendor,
           "factors": factors, "bet_count_curve": {"raw_net": bc_net, "vs_twin_or_ew": bc_act},
           "academic_benchmark": bench,
           "monthly_series": str(monthly_path.relative_to(REPO)).replace("\\", "/"),
           "summary": {rid: {"calendar": e.get("classification", {}).get("verdict"),
                             "twin_full": (e.get("neutral") or {}).get("twin_verdict_full"),
                             "factor_ff3_umd": ((factors.get(rid) or {}).get("net") or {})
                             .get("ff3_umd", {}).get("verdict")}
                       for rid, e in {**results, **{DISP: (disp.get("results") or {}).get(DISP, {})}}.items()},
           "elapsed_s": round(time.time() - t0, 1), "peak_working_set_mb": peak_rss_mb()}
    atomic_write_json(rp, F._round(doc), indent=1)
    say(f"-> {rp}  ({time.time()-t0:.0f}s, peak {peak_rss_mb()} MB)")
    for rid, v in doc["summary"].items():
        say(f"  {rid}: {v}")
    return 0


def _twin_factor(df: pd.DataFrame, ff: pd.DataFrame) -> dict:
    """rule - twin21 regressed on the four factors: does the twin gap load on UMD?"""
    from backend.services import signal_structure as SS           # noqa: PLC0415
    d = (df["rule_net"] - df["twin21_net"]).dropna()
    X = on_hold_months(d, ff)[["mktrf", "smb", "hml", "umd"]]
    try:
        o = SS.ols(d, X, hold_months=3)
    except Exception as e:                                        # noqa: BLE001
        return {"status": f"NOT_COMPUTED: {type(e).__name__}: {e}"}
    obs = float(d.mean())
    return {"alpha_monthly": o["alpha_monthly"], "t_alpha_used": o["t_alpha_used"],
            "mde_alpha_80_used": o["mde_alpha_80_used"], "betas": o["betas"], "r2": o["r2"],
            "observed_mean_monthly": obs,
            "verdict": CR.factor_verdict(o["t_alpha_used"], o["mde_alpha_80_used"], obs)}


# ── part 3: vendor vs CRSP top-20 slots ──────────────────────────────────────

def top_k(panel: pd.DataFrame, d, k: int = K) -> list:
    g = panel[(panel["date"] == d) & panel["eligible"].astype(bool) & panel["mom_252_21"].notna()]
    tb = SL._tiebreak(g)
    order = np.lexsort((tb, -g["mom_252_21"].to_numpy(dtype=float)))
    return g["symbol"].to_numpy()[order[:k]].tolist()


def part_slots(panel_run: str, run_id: str) -> int:
    from backend.services import xs_ranker as XR                  # noqa: PLC0415
    rp = OUT / f"slots_{run_id}.json"
    if rp.exists():
        say(f"REFUSED: {rp.name} exists")
        return 2
    t0 = time.time()
    crsp = load_panel(panel_run)
    last_seen = crsp.groupby("symbol")["date"].max()
    crsp = crsp[crsp["date"] >= pd.Timestamp("2016-12-01")][["date", "symbol", "eligible", "mom_252_21",
                                                             "median_dollar_vol", "close", "fwd_ret"]]
    paths = XR.survivorship_free_paths()
    W = F.load_wide(paths, start=_cfg.STRATEGY_LIB_START)
    vp = F.build_panel(W, delist_return=float(_cfg.STRATEGY_LIB_DELIST_RETURN))
    del W
    gc.collect()
    vp = vp[vp["is_month_end"].astype(bool)][["date", "symbol", "eligible", "mom_252_21",
                                                "median_dollar_vol", "close", "fwd_ret"]]
    say(f"  vendor panel {len(vp):,} rows; CRSP {len(crsp):,}; {time.time()-t0:.0f}s peak {peak_rss_mb()} MB")
    nm = CR.ticker_map(pd.read_parquet(WRDS / "bulk" / "crsp__stocknames.parquet"))
    p2tk = {CR.permno_symbol(p_): tk for p_, tk in nm.sort_values("namedt")[["permno", "ticker"]]
            .itertuples(index=False)}
    names = CR.names_by_ticker(nm)
    cdates = pd.DatetimeIndex(sorted(set(crsp["date"].unique())))
    vdates = pd.DatetimeIndex(sorted(set(vp["date"].unique())))
    vm = {d.to_period("M"): d for d in vdates}
    pairs = [(vm[c.to_period("M")], c) for c in cdates if c.to_period("M") in vm]
    per_date, reasons_v, reasons_c, examples, map_how = [], {}, {}, [], {}
    same_pairs: list = []
    vendor_perms_ever: set = set()
    for vd, cd in pairs:
        vtop, ctop = top_k(vp, vd), top_k(crsp, cd)
        vday = vp[vp["date"] == vd].drop_duplicates("symbol").set_index("symbol")
        cday = crsp[crsp["date"] == cd].drop_duplicates("symbol").set_index("symbol")
        # every vendor row of the day -> the permno whose history it carries
        vinfo = {s_: CR.vendor_to_permno(s_, vd, names) for s_ in vday.index}
        by_perm: dict = {}
        for s_, i in vinfo.items():
            if i.get("permno") is not None:
                by_perm.setdefault(CR.permno_symbol(i["permno"]), []).append(s_)
        vendor_perms_ever |= set(by_perm)
        vperm = {s_: (CR.permno_symbol(vinfo[s_]["permno"]) if vinfo[s_].get("permno") is not None
                      else None) for s_ in vtop}
        for s_ in vtop:
            h = vinfo[s_].get("how", "unmapped")
            map_how[h] = map_how.get(h, 0) + 1
        cset = set(ctop)
        vset_perm = {x for x in vperm.values() if x}
        same = sum(1 for s_ in vtop if vperm[s_] in cset)
        for s_ in vtop:
            if vperm[s_] in cset:
                same_pairs.append({"date": str(vd.date()), "symbol": s_, "permno": vperm[s_],
                                   "vendor_fwd": float(vday.loc[s_, "fwd_ret"]),
                                   "crsp_fwd": float(cday.loc[vperm[s_], "fwd_ret"]),
                                   "vendor_12_1": float(vday.loc[s_, "mom_252_21"]),
                                   "crsp_12_1": float(cday.loc[vperm[s_], "mom_252_21"])})
        for s_ in vtop:
            if vperm[s_] in cset:
                continue
            crow = None
            if vperm[s_] is not None and vperm[s_] in cday.index:
                r = cday.loc[vperm[s_]]
                crow = {"eligible": bool(r["eligible"]), "score": float(r["mom_252_21"]),
                        "price": float(r["close"]), "mdv": float(r["median_dollar_vol"])}
            vs = float(vday.loc[s_, "mom_252_21"])
            why = CR.classify_vendor_slot(vinfo[s_], crow, vs)
            reasons_v[why] = reasons_v.get(why, 0) + 1
            examples.append({"date": str(vd.date()), "side": "vendor_only", "symbol": s_,
                             "permno": vperm[s_], "map": vinfo[s_].get("how"), "why": why,
                             "vendor_12_1": vs, "crsp_12_1": (crow or {}).get("score"),
                             "crsp_eligible": (crow or {}).get("eligible"),
                             "crsp_price": (crow or {}).get("price"),
                             "vendor_mdv": float(vday.loc[s_, "median_dollar_vol"]),
                             "vendor_fwd": float(vday.loc[s_, "fwd_ret"])})
        for p_ in ctop:
            if p_ in vset_perm:
                continue
            vrow = None
            syms = by_perm.get(p_) or []
            if syms:
                r = vday.loc[syms[0]]
                vrow = {"eligible": bool(r["eligible"]), "score": float(r["mom_252_21"]),
                        "symbol": syms[0]}
            cs = float(cday.loc[p_, "mom_252_21"])
            why = CR.classify_crsp_slot(vrow, cs)
            reasons_c[why] = reasons_c.get(why, 0) + 1
            examples.append({"date": str(cd.date()), "side": "crsp_only", "permno": p_,
                             "vendor_symbol": (vrow or {}).get("symbol"), "why": why,
                             "crsp_12_1": cs, "vendor_12_1": (vrow or {}).get("score"),
                             "vendor_eligible": (vrow or {}).get("eligible"),
                             "crsp_mdv": float(cday.loc[p_, "median_dollar_vol"]),
                             "crsp_price": float(cday.loc[p_, "close"]),
                             "crsp_fwd": float(cday.loc[p_, "fwd_ret"])})
        per_date.append({"vendor_date": str(vd.date()), "crsp_date": str(cd.date()),
                         "same": same, "differ": K - same})
    pdf = pd.DataFrame(per_date)
    pdf["year"] = pd.to_datetime(pdf["crsp_date"]).dt.year
    by_year = {str(y): {"slots": int(len(g) * K), "differ": int(g["differ"].sum()),
                        "share_differ": float(g["differ"].sum() / (len(g) * K))}
               for y, g in pdf.groupby("year")}
    ex = pd.DataFrame(examples)
    ex["abs_gap"] = (np.log1p(ex["vendor_12_1"].clip(lower=-0.99)) -
                     np.log1p(ex["crsp_12_1"].clip(lower=-0.99))).abs()
    top_ex = ex.sort_values("abs_gap", ascending=False).head(25).to_dict("records")
    sp_ = pd.DataFrame(same_pairs)
    vo, co_ = ex[ex["side"] == "vendor_only"], ex[ex["side"] == "crsp_only"]

    def _m(x):
        x = pd.Series(x, dtype=float).dropna()
        return {"n": int(len(x)), "mean": float(x.mean()) if len(x) else None,
                "median": float(x.median()) if len(x) else None}
    c1 = co_[co_["why"] == "C1_absent_from_vendor_panel"].copy()
    c1_profile = {}
    if len(c1):
        c1["ticker_last"] = c1["permno"].map(p2tk)
        ls = pd.to_datetime(c1["permno"].map(last_seen))
        dd = pd.to_datetime(c1["date"])
        c1_profile = {
            "n_slots": int(len(c1)), "n_names": int(c1["permno"].nunique()),
            "share_names_never_in_vendor_panel": float(np.mean([p_ not in vendor_perms_ever
                                                                for p_ in c1["permno"].unique()])),
            "share_slots_whose_listing_ends_before_2024_12": float((ls < pd.Timestamp("2024-12-01")).mean()),
            "share_slots_listing_ends_within_12m": float(((ls - dd).dt.days <= 366).mean()),
            "median_price": float(c1["crsp_price"].median()),
            "share_price_below_5": float((c1["crsp_price"] < 5).mean()),
            "median_dollar_vol": float(c1["crsp_mdv"].median()),
            "share_small_band_lt_20m": float((c1["crsp_mdv"] < 2e7).mean()),
            "by_year_slots": {str(k): int(v) for k, v in pd.to_datetime(c1["date"]).dt.year
                              .value_counts().sort_index().items()},
            "fwd_if_listing_ended_within_12m": _m(c1.loc[((ls - dd).dt.days <= 366).to_numpy(), "crsp_fwd"]),
            "fwd_if_still_listed_12m_later": _m(c1.loc[((ls - dd).dt.days > 366).to_numpy(), "crsp_fwd"]),
            "examples": c1.sort_values("crsp_12_1", ascending=False).head(12)[
                ["date", "permno", "ticker_last", "crsp_12_1", "crsp_price", "crsp_mdv", "crsp_fwd"]]
            .to_dict("records")}
    fwd_read = {
        "note": ("next-month forward return of each slot on ITS OWN source (engine convention; the "
                 "last decision's return is NaN). The gap between the two top-20 books is "
                 "(vendor-only slots on vendor bars) vs (CRSP-only slots on CRSP bars), plus the "
                 "same names priced differently by the two sources."),
        "vendor_only_on_vendor": _m(vo.get("vendor_fwd")),
        "crsp_only_on_crsp": _m(co_.get("crsp_fwd")),
        "same_names_on_vendor": _m(sp_.get("vendor_fwd")),
        "same_names_on_crsp": _m(sp_.get("crsp_fwd")),
        "same_names_abs_fwd_gap_gt_2pct": int(((sp_["vendor_fwd"] - sp_["crsp_fwd"]).abs() > 0.02).sum())
        if len(sp_) else 0,
        "vendor_only_by_reason": {k: _m(g["vendor_fwd"]) for k, g in vo.groupby("why")},
        "crsp_only_by_reason": {k: _m(g["crsp_fwd"]) for k, g in co_.groupby("why")},
        "largest_vendor_only_forward_returns": vo.sort_values("vendor_fwd", ascending=False)
        .head(15)[["date", "symbol", "permno", "map", "why", "vendor_12_1", "crsp_12_1", "vendor_fwd"]]
        .to_dict("records")}
    doc = {"schema": "crsp_rebuild/slots/1", "job": JOB, "run_id": run_id, "panel_run": panel_run,
           "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "what": ("at every month-end decision both panels share (2016-12 .. 2024-12), the top-20 by "
                    "12-1 momentum among eligible names (the mom_12_1 selection every lead starts "
                    "from; the quarterly offsets are subsets of these dates), vendor (reader default: "
                    "stitch cut + defect screen) vs CRSP; vendor symbols mapped to permnos by CRSP "
                    "stocknames valid on the date"),
           "vendor_paths": [p.name for p in paths], "bar_screen": "ON (reader default)",
           "n_dates": int(len(pdf)), "slots": int(len(pdf) * K),
           "same": int(pdf["same"].sum()), "differ": int(pdf["differ"].sum()),
           "share_differ": float(pdf["differ"].sum() / (len(pdf) * K)),
           "reasons_vendor_only": dict(sorted(reasons_v.items())),
           "reasons_crsp_only": dict(sorted(reasons_c.items())),
           "vendor_top20_mapping": map_how,
           "mapping_rule": CR.vendor_to_permno.__doc__.split("So:", 1)[1].split("`names`")[0].strip(),
           "reason_key": {
               "V1_no_crsp_permno": "the vendor ticker has no CRSP name on the date (ADR/OTC/foreign/"
                                    "renamed ticker the map missed)",
               "V2_not_a_crsp_common_stock_on_nyse_amex_nasdaq": "CRSP share code not 10/11 (ADR, REIT, "
                                                                 "units, ...) or exchange outside 1-3",
               "V3_no_crsp_row_on_date": "the permno is not in the CRSP panel that month",
               "V4_ineligible_on_crsp": "price / dollar-volume / history floor fails on CRSP",
               "V6_score_differs_data": "|log(1+12-1)| differs by > 0.10 between sources",
               "V7_rank_margin_same_score": "same score within 0.10 log, ranked just outside",
               "C1_absent_from_vendor_panel": "the CRSP name's ticker is not in the vendor panel "
                                              "that month (dead / never pulled / ticker map)",
               "C2_ineligible_on_vendor": "the vendor panel has it but it fails a floor",
               "C4_score_differs_data": "|log(1+12-1)| differs by > 0.10",
               "C5_rank_margin_same_score": "same score within 0.10 log, ranked just outside"},
           "by_year": by_year, "largest_score_gaps": top_ex, "forward_return_read": fwd_read,
           "c1_profile": c1_profile,
           "elapsed_s": round(time.time() - t0, 1), "peak_working_set_mb": peak_rss_mb()}
    atomic_write_json(rp, F._round(doc), indent=1)
    say(f"-> {rp}: {doc['differ']} of {doc['slots']} slots differ; vendor-only {reasons_v}; "
        f"crsp-only {reasons_c}")
    return 0


# ── part 4: the vendor universe rule, emulated on CRSP ────────────────────────

def part_emulate(panel_run: str, run_id: str) -> int:
    """Does the vendor's membership rule (living names floored on END-of-sample
    liquidity, dead names added back) manufacture the vendor's twin gap on CRSP?"""
    rp = OUT / f"emulate_vendor_universe_{run_id}.json"
    if rp.exists():
        say(f"REFUSED: {rp.name} exists")
        return 2
    t0 = time.time()
    panel = load_panel(panel_run)
    vr = json.loads((OPT / "strategy_library" / f"{VENDOR_RECEIPT}.json").read_text(encoding="utf-8"))
    o0 = vr["results"]["mom_12_1_q"]["offsets"]["jajo"]
    n_spy, n_twin = int(o0["dsr_vs_spy_n_trials"]), int(o0["dsr_rule_minus_twin21_n_trials"])
    floor = float(json.loads((OPT / "prices_deep" / "pull_receipt.json").read_text(encoding="utf-8"))
                  ["universe"]["floor_median_dollar_volume"])
    asof = panel["date"].max()
    U = CR.end_screen_universe(panel, asof=asof, min_median_dollar_vol=floor)
    spy_all = spy_series(panel)
    legs = {"A_crsp_all_2017": (panel["date"] >= pd.Timestamp("2016-12-01"), None),
            "B_crsp_end_screened_2017": (panel["date"] >= pd.Timestamp("2016-12-01"), U["keep"]),
            "C_crsp_end_screened_1991": (panel["date"] >= panel["date"].min(), U["keep"])}
    out, series_rows = {}, []
    for leg, (mask, keep) in legs.items():
        sub = panel[mask]
        if keep is not None:
            sub = sub[sub["symbol"].isin(keep)]
        sub = sub.reset_index(drop=True)
        spy_l = spy_all[spy_all.index >= sub["date"].min()]
        try:
            rp_l, _ = F.random_panel_leg(sub)
        except Exception as e:                                    # noqa: BLE001
            rp_l = f"RANDOM_PANEL_SERIES_MISSING: {e}"
        res, ser = run_rule_set(sub, spy_l, {"iwm": "IWM_SERIES_MISSING", "random_panel": rp_l},
                                LEADS, n_spy=n_spy, n_twin=n_twin, tag=leg)
        for e in res.values():
            e.pop("_neutral_series", None)
        series_rows += ser
        el = sub[sub["eligible"]].groupby("date").size()
        out[leg] = {"rows": int(len(sub)), "symbols": int(sub["symbol"].nunique()),
                    "eligible_per_date_median": float(el.median()),
                    "summary": {rid: {"calendar": e.get("classification", {}).get("verdict"),
                                      "neutral_full": e.get("neutral", {}).get(
                                          "rule_minus_twin21_windows", {}).get("full"),
                                      "neutral_overlap_2017_2024": e.get("neutral", {}).get(
                                          "rule_minus_twin21_windows", {}).get("vendor_overlap_2017_2024"),
                                      "neutral_pre_vendor": e.get("neutral", {}).get(
                                          "rule_minus_twin21_windows", {}).get("pre_vendor_1991_2016"),
                                      "by_hold_year": e.get("neutral", {}).get("by_hold_year_rule_minus_twin21"),
                                      "offset_t": (e.get("classification", {}).get("set_a") or {}).get("t_blocks")}
                                for rid, e in res.items()}}
    if series_rows:
        pd.concat(series_rows, ignore_index=True).to_parquet(
            OUT / f"emulate_vendor_universe_monthly_{run_id}.parquet", index=False)
    doc = {"schema": "crsp_rebuild/emulate_vendor_universe/1", "job": JOB, "run_id": run_id,
           "panel_run": panel_run, "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "rule": CR.end_screen_universe.__doc__.strip(),
           "vendor_rule_source": "backend/data/optimus/prices_deep/pull_receipt.json (universe_asof "
                                 "2026-09-01, floor_median_dollar_volume) + delisted_receipt.json",
           "asof": str(pd.Timestamp(asof).date()), "floor_median_dollar_volume": floor,
           "universe": {"dead": len(U["dead"]), "alive_liquid": len(U["alive_liquid"]),
                        "alive_shrunk_dropped": len(U["alive_shrunk"])},
           "vendor_same_rules": {rid: vendor_neutral(rid) for rid in LEADS},
           "legs": out, "k": K, "elapsed_s": round(time.time() - t0, 1),
           "peak_working_set_mb": peak_rss_mb()}
    atomic_write_json(rp, F._round(doc), indent=1)
    say(f"-> {rp} ({time.time()-t0:.0f}s)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=("panel", "run", "slots", "emulate"), required=True)
    ap.add_argument("--panel-run", default=None)
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    run_id = F.new_run_id()
    if a.part == "panel":
        return part_panel(run_id)
    if not a.panel_run:
        say("REFUSED: --panel-run is required")
        return 2
    if a.part == "emulate":
        return part_emulate(a.panel_run, run_id)
    return part_run(a.panel_run, run_id) if a.part == "run" else part_slots(a.panel_run, run_id)


if __name__ == "__main__":
    raise SystemExit(main())
