"""Run part of `scripts.crsp_blend_followups` (experiments A and B). See that module's docstring."""
from __future__ import annotations

import dataclasses
import gc
import json
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from scripts.crsp_blend_followups import (BOARD_RUN, CS_CAP, DECISION_LINE_A, FUND_LAG_DAYS, FUND_RUN, OUT,
                                          PANEL_RUN, WINDOWS, WRDS, rank_band_mask, say, skip_fwd, verdict_a)

CAPITAL = (1e6, 1e7, 1e8)


def lagged_gross_margin(keys: pd.DataFrame) -> np.ndarray:
    """gross_margin (WRDS gpm) usable only from max(public_date, qdate + FUND_LAG_DAYS)."""
    fr = pd.read_parquet(WRDS / "bulk" / "wrdsapps__firm_ratio.parquet", columns=["permno", "qdate", "public_date", "gpm"])
    fr["public_date"] = pd.to_datetime(fr["public_date"])
    fr["qdate"] = pd.to_datetime(fr["qdate"], errors="coerce")
    fr["permno"] = pd.to_numeric(fr["permno"], errors="coerce").astype("float64")
    fr["gpm"] = pd.to_numeric(fr["gpm"], errors="coerce").astype("float32")
    fr["avail"] = fr[["public_date"]].assign(q=fr["qdate"] + pd.Timedelta(days=FUND_LAG_DAYS)).max(axis=1)
    fr = fr.dropna(subset=["permno", "avail"]).sort_values("avail")
    # among rows available by the same date keep the one on the latest fiscal period
    left = keys[["date", "symbol"]].reset_index()
    left["permno"] = pd.to_numeric(left["symbol"].astype(str), errors="coerce").astype("float64")
    left = left.dropna(subset=["permno"]).sort_values("date")
    m = pd.merge_asof(left, fr[["permno", "avail", "gpm"]], left_on="date", right_on="avail", by="permno",
                      direction="backward", tolerance=pd.Timedelta(days=70 + FUND_LAG_DAYS))
    return m.set_index("index")["gpm"].reindex(keys.index).to_numpy()


def stats_block(rn: pd.Series, tn: pd.Series, mk: pd.Series) -> dict:
    from backend.services import calendar_offsets as CO              # noqa: PLC0415
    from backend.services import crsp_rebuild as CR                  # noqa: PLC0415
    from backend.services import strategy_library as SL              # noqa: PLC0415
    diff = (rn - tn).dropna()
    vm = (rn - mk).dropna()
    out = {"vs_twin": {k: CR.window_stats(diff, *w) for k, w in WINDOWS.items()},
           "vs_market": {k: CR.window_stats(vm, *w) for k, w in WINDOWS.items()},
           "by_hold_year_vs_twin": {y: round(v["sum"], 4) for y, v in CO.by_hold_year(diff).items()},
           "by_hold_year_vs_market": {y: round(v["sum"], 4) for y, v in CO.by_hold_year(vm).items()}}
    for nm, s in (("vs_twin", diff), ("vs_market", vm)):
        for wk, (lo, hi) in (("1991-2024", (None, None)), ("2001-2024", ("2001-01-01", "2024-12-31"))):
            hold = pd.DatetimeIndex(s.index) + pd.offsets.BDay(1)
            mk_ = np.ones(len(s), dtype=bool)
            if lo:
                mk_ &= (hold >= pd.Timestamp(lo)) & (hold <= pd.Timestamp(hi))
            lw = CO.loo_worst(s[mk_])
            out.setdefault("loo_worst", {}).setdefault(nm, {})[wk] = {"worst": lw["worst"],
                                                                     "dropped_year": lw["dropped_year"]}
        out.setdefault("share_of_total_by_date", {})[nm] = CR.share_of_total_by_date(s)
    out["cagr"] = {"rule": SL._cagr(rn.dropna()), "twin21": SL._cagr(tn.dropna()), "market": SL._cagr(mk.dropna())}
    return out


def book_profile(P: pd.DataFrame, rule, k: int) -> dict:
    """Turnover and capacity from the rule's own holdings."""
    from backend.services import strategy_library as SL              # noqa: PLC0415
    hold: list = []
    SL.run_strategy(P, rule, k=k, holdings=hold)
    mdv = P.set_index(["date", "symbol"])["median_dollar_vol"]
    to, med, p10, yrs = [], [], [], []
    prev = None
    for h in hold:
        s = set(h["symbols"])
        if prev is not None:
            to.append(1.0 - len(s & prev) / max(1, len(s)))
        prev = s
        v = mdv.reindex([(pd.Timestamp(h["date"]), x) for x in h["symbols"]]).to_numpy(dtype=float)
        med.append(np.nanmedian(v))
        p10.append(np.nanpercentile(v, 10))
        yrs.append(pd.Timestamp(h["date"]).year)
    df = pd.DataFrame({"year": yrs, "med": med, "p10": p10})
    cap = {}
    for c in CAPITAL:
        per = c / k
        cap[f"${int(c/1e6)}M"] = {"per_name_usd": per,
                                   "pct_of_median_pick_adv": float(np.nanmedian(per / df["med"]) * 100),
                                   "pct_of_p10_pick_adv": float(np.nanmedian(per / df["p10"]) * 100)}
    return {"turnover_per_month": float(np.mean(to)) if to else None,
            "median_pick_adv_musd_by_decade": {str(d): float(g["med"].median() / 1e6)
                                               for d, g in df.groupby(df["year"] // 10 * 10)},
            "p10_pick_adv_musd_by_decade": {str(d): float(g["p10"].median() / 1e6)
                                            for d, g in df.groupby(df["year"] // 10 * 10)},
            "capacity": cap, "n_rebalances": len(hold)}


def part_run(run_id: str, daily_run: str) -> int:
    from backend.services import matched_twins as MT                 # noqa: PLC0415
    from backend.services import strategy_library as SL              # noqa: PLC0415
    from backend.services import xs_ranker as XR                     # noqa: PLC0415
    from scripts import library_on_crsp as LOC                        # noqa: PLC0415
    from scripts import momentum_on_crsp as M                         # noqa: PLC0415
    from scripts import night_backtest_factory as F                   # noqa: PLC0415
    from scripts.calendar_offset_triplet import run_one              # noqa: PLC0415
    from scripts.night_checkpoint import atomic_write_json           # noqa: PLC0415
    rj = OUT / f"followups_{run_id}.json"
    if rj.exists():
        say(f"REFUSED: {rj.name} exists")
        return 2
    t0 = time.time()
    say(f"decision line A (stated before running): {DECISION_LINE_A}")
    P, meta = LOC.load_full_panel(PANEL_RUN, FUND_RUN)
    P = P.reset_index(drop=True)
    spy = M.spy_series(P)
    try:
        rpanel, _ = F.random_panel_leg(P)
    except Exception as e:                                           # noqa: BLE001
        rpanel = f"RANDOM_PANEL_SERIES_MISSING: {type(e).__name__}: {e}"
    benches = {"iwm": "IWM_SERIES_MISSING", "random_panel": rpanel}
    rules = {r.id: r for r in SL.rules()}

    # inputs for A
    D = pd.read_parquet(OUT / f"followups_daily_{daily_run}.parquet")
    D["symbol"] = D["permno"].map(lambda p: f"{int(p):06d}")
    D["date"] = pd.to_datetime(D["date"])
    D = D.sort_values(["symbol", "date"])
    D["g_next"] = D.groupby("symbol")["g_skip"].shift(-1)
    j = P[["date", "symbol"]].merge(D[["date", "symbol", "g_skip", "g_next", "cs_spread"]],
                                    on=["date", "symbol"], how="left")
    g_now, g_next = j["g_skip"].to_numpy(), j["g_next"].to_numpy()
    cs = np.minimum(j["cs_spread"].to_numpy(dtype=float), CS_CAP)
    flat_rt = np.array([XR.COST_BPS_BY_BAND[XR.liquidity_band(v)] / 1e4 if np.isfinite(v) else 0.0035
                        for v in P["median_dollar_vol"].to_numpy(dtype=float)])
    cs_filled = np.where(np.isfinite(cs), cs, flat_rt)
    fwd0 = P["fwd_ret"].to_numpy(dtype=float)
    fwd_skip = np.where(np.isfinite(fwd0), skip_fwd(fwd0, g_now, g_next), np.nan)
    gm_lag = lagged_gross_margin(P)
    gm0 = P["gross_margin"].to_numpy()
    el = P["eligible"].to_numpy(dtype=bool)
    inp = {"g_skip_coverage_eligible": float(np.isfinite(g_now[el]).mean()),
           "cs_coverage_eligible": float(np.isfinite(cs[el]).mean()),
           "cs_median_eligible_by_decade": {str(d): float(np.nanmedian(cs[el & (P["date"].dt.year.to_numpy() // 10 * 10 == d)]))
                                            for d in (1990, 2000, 2010, 2020)},
           "flat_rt_median_eligible": float(np.median(flat_rt[el])),
           "gross_margin_coverage_eligible": {"as_run": float(np.isfinite(gm0[el].astype(float)).mean()),
                                              "lagged": float(np.isfinite(gm_lag[el].astype(float)).mean())},
           "mean_abs_skip_minus_base": float(np.nanmean(np.abs(fwd_skip[el] - fwd0[el])))}
    say(f"inputs: {json.dumps(inp)}")

    def one(Pv, rule, tag):
        grid = sorted(pd.DatetimeIndex(Pv.loc[Pv["fwd_ret"].notna(), "date"].unique()))
        row = run_one(Pv, spy, benches, rule, k=int(rule.k), by_date=MT.panel_by_date(Pv), cache={}, grid=grid,
                      n_spy=LOC.VENDOR_CELLS_LOOKED_AT, n_twin=LOC.VENDOR_CELLS_LOOKED_AT, log=lambda *a: None,
                      flagged=set(), refuse_defects=False)
        s = row.pop("_series")
        s.to_parquet(OUT / f"followups_series_{run_id}__{tag}.parquet")
        st = stats_block(s["rule_net"], s["twin21_net"], s["spy"])
        st["mean_cost_bps_per_month"] = row.get("mean_cost_bps_per_month")
        st["n_delisting_fills"] = row.get("n_delisting_fills")
        w = st["vs_twin"]
        say(f"  {tag:34s} " + " | ".join(f"{k} {100*(w[k]['mean_monthly'] or 0):+.2f} t {w[k]['t_blocks'] or 0:+.2f}"
                                          for k in WINDOWS) +
            f" || mkt 01-24 {100*(st['vs_market']['2001-2024']['mean_monthly'] or 0):+.2f} "
            f"t {st['vs_market']['2001-2024']['t_blocks'] or 0:+.2f}  {time.time()-t0:.0f}s")
        return st

    res = {"A": {}, "B": {}}
    co = rules["co03_reversal_in_high_margin"]
    co_inst = dataclasses.replace(co, cost_scale=0.0, zero_cost_diagnostic=True)
    variants = [
        ("A0_as_run", fwd0, gm0, co),
        ("A1_skip", fwd_skip, gm0, co),
        ("A2_lag4m", fwd0, gm_lag, co),
        ("A3_cs_on_top", fwd0 - cs_filled, gm0, co),
        ("A4_all_three_cs_on_top_of_flat", fwd_skip - cs_filled, gm_lag, co),
        ("A5_all_three_cs_instead_of_flat", fwd_skip - cs_filled, gm_lag, co_inst),
    ]
    for tag, fwd, gm, rule in variants:
        Pv = P.copy()
        Pv["fwd_ret"] = fwd
        Pv["gross_margin"] = gm
        try:
            st = one(Pv, rule, tag)
            if tag.startswith("A4") or tag.startswith("A0"):
                st["book"] = book_profile(Pv, rule, int(rule.k))
            res["A"][tag] = st
        except Exception as e:                                       # noqa: BLE001
            res["A"][tag] = {"status": f"REFUSED: {type(e).__name__}: {e}"}
            say(f"  {tag} REFUSED {type(e).__name__}: {e}")
        del Pv
        gc.collect()
    a4 = (res["A"].get("A4_all_three_cs_on_top_of_flat") or {}).get("vs_twin", {}).get("2001-2024", {})
    res["A_verdict"] = {"decision_line": DECISION_LINE_A, "read": a4, "verdict": verdict_a(a4)}
    say(f"A verdict: {res['A_verdict']['verdict']}")

    for n in (300, 500):
        Pv = P.copy()
        Pv["eligible"] = rank_band_mask(Pv, n)
        for rid in ("px_vs_ma200", "mom_12_1"):
            tag = f"B_{rid}_top{n}"
            try:
                st = one(Pv, rules[rid], tag)
                st["book"] = book_profile(Pv, rules[rid], int(rules[rid].k))
                res["B"][tag] = st
            except Exception as e:                                   # noqa: BLE001
                res["B"][tag] = {"status": f"REFUSED: {type(e).__name__}: {e}"}
                say(f"  {tag} REFUSED {type(e).__name__}: {e}")
        del Pv
        gc.collect()
    # the board's own nominal-$100M versions, same statistics, from its series
    for rid in ("px_vs_ma200_large", "mom_12_1_large", "co03_reversal_in_high_margin"):
        s = pd.read_parquet(OUT / f"library_series_{BOARD_RUN}" / f"{rid}.parquet")
        res["B" if "large" in rid else "A"][f"board_{rid}"] = stats_block(s["rule_net"], s["twin21_net"], s["market"])

    doc = {"schema": "crsp_rebuild/followups/1", "run_id": run_id, "daily_run": daily_run,
           "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "inputs_panel": PANEL_RUN, "inputs_fund": FUND_RUN, "board_run": BOARD_RUN,
           "construction": {
               "engine": "calendar_offset_triplet.run_one unchanged (21-draw matched twin, set B beside); "
                         "the twin pays the RULE's flat band cost, so the flat schedule cancels in rule - twin",
               "skip": "open of t+2 (close of t+1 when no open) to the same one session after the next decision",
               "cs": f"Corwin-Schultz 2012, overnight-adjusted, negatives -> 0, 20-pair mean ending at the decision, "
                     f"capped {CS_CAP:.0%}, missing -> the flat band round trip; charged as a FULL round trip "
                     "per month on every held name of book and twin (book turnover < 100% => slight over-charge "
                     "of the book)",
               "fund_lag": f"WRDS ratio row usable from max(public_date, qdate + {FUND_LAG_DAYS} days)",
               "rank_band": "eligible cut to the top N by 63-session median dollar volume on each decision date; "
                            "px_vs_ma200 / mom_12_1 with no band filter inside it; the twin draws from the same cut"},
           "inputs_check": inp, "results": res, "seconds": round(time.time() - t0, 1)}
    atomic_write_json(rj, F._round(doc), indent=1)
    say(f"-> {rj.name} {time.time()-t0:.0f}s")
    return 0
