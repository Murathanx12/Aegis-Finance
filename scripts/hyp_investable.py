"""Why the twin trails the market, and the investable versions of four "beats the twin" leads.

    python -m scripts.hyp_investable --part inputs    --tag <T>   # one input frame (~3 min)
    python -m scripts.hyp_investable --part decompose --tag <T>   # the twin drag, piece by piece
    python -m scripts.hyp_investable --part declare   --tag <T>   # hashed BEFORE any spread is read
    python -m scripts.hyp_investable --part run       --tag <T>   # design, ONE validate read, late last

Licence `PRODUCT_EXPERIMENT`. $0, no LLM, no network, no broker call. Receipts go to
`backend/data/optimus/hyp_lab/investable_*_<tag>.json`; a part REFUSES to overwrite.
Pure pieces: `backend/services/hyp_investable.py`.
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

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

JOB = "hyp_investable"
OPT = REPO / "backend" / "data" / "optimus"
WRDS = OPT / "wrds"
CR_OUT = OPT / "crsp_rebuild"
OUT = OPT / "hyp_lab"
PANEL_RUN = "2026-09-29T075640Z"
FUND_RUN = "2026-09-29T041550Z"
PIT_RUN = "PB_2026-09-29T1420Z"
EVENT_RUN = "EB_2026-09-29T1055Z"
CS_RUN = "FU_2026-09-29T0855Z"
BOARD_FLAT, BOARD_CS = "BR_FLAT_2026-09-29T1535Z", "BR_CS_2026-09-29T1545Z"
LIB_CS = "LIB_2026-09-29T0802Z"
CS_CAP = 0.20
FLOW_START = "1999-09-30"
PRIOR_SEARCH = 42_666
SPLITS = {"design": ("1991-01-01", "2008-12-31"), "validate": ("2009-01-01", "2016-12-31"),
          "late": ("2017-01-01", "2024-12-31")}
RULES = ("quality_composite", "cash_lowvol", "ope_be")
REV = "revision_trend_on_small"
OVERLAY = {"base_n": 500, "scheme": "cap", "active_share": 0.20, "cap": 0.005, "band": 0.001, "budget": 0.15}


def say(*a) -> None:
    print(*a, flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _write(p: Path, doc: dict) -> None:
    from scripts.night_checkpoint import atomic_write_json           # noqa: PLC0415
    atomic_write_json(p, doc, indent=1)


def _mem_ok() -> bool:
    from scripts.bridges_on_crsp import wait_for_memory             # noqa: PLC0415
    return wait_for_memory(3.0, 1800)


# ── inputs ───────────────────────────────────────────────────────────────────

def part_inputs(tag: str) -> int:
    fp = OUT / f"investable_inputs_{tag}.parquet"
    if fp.exists():
        say(f"REFUSED: {fp.name} exists")
        return 2
    t0 = time.time()
    P = pd.read_parquet(CR_OUT / f"library_panel_{PANEL_RUN}.parquet",
                        columns=["date", "symbol", "eligible", "fwd_ret", "median_dollar_vol", "vol_63", "vol_252",
                                 "mom_252_21", "delisted_in_period", "mkt_trend_up"])
    P["date"] = pd.to_datetime(P["date"])
    for f, cols in ((CR_OUT / f"library_fund_{FUND_RUN}.parquet", ["gp_at", "debt_at", "gsector"]),
                    (CR_OUT / f"pit_fund_{PIT_RUN}.parquet", ["ope_be", "cash_at"]),
                    (CR_OUT / f"event_bridge_{EVENT_RUN}.parquet", ["net_raises"])):
        X = pd.read_parquet(f, columns=["date", "symbol"] + cols)
        X["date"] = pd.to_datetime(X["date"])
        P = P.merge(X, on=["date", "symbol"], how="left")
        del X
        gc.collect()
    P.loc[P["date"] < pd.Timestamp(FLOW_START), "net_raises"] = np.nan
    P["gsector"] = pd.to_numeric(P["gsector"], errors="coerce").astype("float32")
    P["permno"] = pd.to_numeric(P["symbol"], errors="coerce")
    P = P.dropna(subset=["permno"])
    P["permno"] = P["permno"].astype("int64")
    m = pd.read_parquet(WRDS / "bulk" / "crsp__msf.parquet", columns=["permno", "date", "prc", "shrout"])
    m["date"] = pd.to_datetime(m["date"])
    m["permno"] = pd.to_numeric(m["permno"], errors="coerce")
    m = m.dropna(subset=["permno"])
    m["permno"] = m["permno"].astype("int64")
    m["mcap"] = (pd.to_numeric(m["prc"], errors="coerce").abs() * pd.to_numeric(m["shrout"], errors="coerce")
                 * 1e3).astype("float64")
    m["ym"] = m["date"].dt.to_period("M")
    P["ym"] = P["date"].dt.to_period("M")
    P = P.merge(m[["permno", "ym", "mcap"]].drop_duplicates(["permno", "ym"]), on=["permno", "ym"], how="left")
    del m
    D = pd.read_parquet(CR_OUT / f"followups_daily_{CS_RUN}.parquet", columns=["date", "permno", "cs_spread"])
    D["date"] = pd.to_datetime(D["date"])
    D["permno"] = pd.to_numeric(D["permno"], errors="coerce")
    D = D.dropna(subset=["permno"])
    D["permno"] = D["permno"].astype("int64")
    P = P.merge(D.drop_duplicates(["permno", "date"]), on=["permno", "date"], how="left")
    del D
    P = P.drop(columns=["ym"])
    for c in P.columns:
        if P[c].dtype == np.float64 and c not in ("fwd_ret", "median_dollar_vol", "mcap"):
            P[c] = P[c].astype("float32")
    P.to_parquet(fp, index=False)
    el = P[P["eligible"].astype(bool)]
    doc = {"schema": "hyp_lab/investable_inputs/1", "tag": tag, "written_utc": _now(), "rows": int(len(P)),
           "dates": int(P["date"].nunique()), "sources": {"panel": PANEL_RUN, "fund": FUND_RUN, "pit": PIT_RUN,
                                                           "event": EVENT_RUN, "cs": CS_RUN,
                                                           "mcap": "CRSP msf |prc| x shrout, same month"},
           "coverage_eligible": {c: float(el[c].notna().mean()) for c in
                                 ("mcap", "cs_spread", "gp_at", "ope_be", "cash_at", "debt_at", "net_raises")},
           "seconds": round(time.time() - t0, 1)}
    _write(OUT / f"investable_inputs_{tag}.json", doc)
    say(f"-> {fp.name} {len(P):,} rows; coverage {doc['coverage_eligible']} {time.time()-t0:.0f}s")
    return 0


def load(tag: str) -> pd.DataFrame:
    P = pd.read_parquet(OUT / f"investable_inputs_{tag}.parquet")
    P["date"] = pd.to_datetime(P["date"])
    P["eligible"] = P["eligible"].astype(bool)
    P["delisted_in_period"] = P["delisted_in_period"].astype(bool)
    return P


def spreads_of(P: pd.DataFrame) -> np.ndarray:
    from backend.services import xs_ranker as XR                     # noqa: PLC0415
    flat = np.array([XR.COST_BPS_BY_BAND[XR.liquidity_band(v)] / 1e4 if np.isfinite(v) else 0.0035
                     for v in P["median_dollar_vol"].to_numpy(dtype=float)])
    cs = np.minimum(P["cs_spread"].to_numpy(dtype=float), CS_CAP)
    return np.where(np.isfinite(cs), np.maximum(cs, flat), flat)


def market_and_rf(dates) -> tuple[pd.Series, pd.Series]:
    from scripts import night_backtest_factory as F                   # noqa: PLC0415
    ff = pd.read_parquet(WRDS / "ff_factors_daily.parquet", columns=["date", "mktrf", "rf"])
    ff["date"] = pd.to_datetime(ff["date"])
    ff = ff.set_index("date").astype(float)
    di = pd.DatetimeIndex(sorted(dates))
    return F._compound_onto(ff["mktrf"] + ff["rf"], di), F._compound_onto(ff["rf"], di)


def picks_library(P: pd.DataFrame, rule_id: str) -> dict:
    """{date: [symbols]} exactly as the library engine selects (`run_strategy` holdings)."""
    from backend.services import strategy_library as SL              # noqa: PLC0415
    rule = {r.id: r for r in SL.rules()}[rule_id]
    need = ["date", "symbol", "eligible", "fwd_ret", "median_dollar_vol", "delisted_in_period"] + [
        c for c in rule.requires if c in P.columns]
    hold: list = []
    SL.run_strategy(P[need], rule, k=int(rule.k), holdings=hold)
    return {pd.Timestamp(h["date"]): list(h["symbols"]) for h in hold}


def picks_revision(P: pd.DataFrame) -> tuple[dict, pd.Series]:
    """Conditional C06 restricted to the small band: top 20% net_raises (>= 1) among eligible
    names, band small, market trend up at d. Returns picks (>= 5 names) and the active flag."""
    from backend.services import matched_twins as MT                 # noqa: PLC0415
    el = P["eligible"]
    nr = P["net_raises"].where(el & P["net_raises"].notna())
    rank = nr.groupby(P["date"]).rank(pct=True)
    band = pd.Series(MT.size_band(P["median_dollar_vol"].to_numpy(dtype=float)), index=P.index)
    m = (rank >= 0.8) & (P["net_raises"] >= 1) & (band == "small") & el & P["fwd_ret"].notna()
    trend = P.groupby("date")["mkt_trend_up"].first().astype(float)
    out = {}
    for d, g in P[m].groupby("date"):
        if trend.get(d, 0.0) == 1.0 and d >= pd.Timestamp(FLOW_START) and g["symbol"].nunique() >= 5:
            out[pd.Timestamp(d)] = list(g["symbol"].unique())
    return out, trend


# ── the engine ───────────────────────────────────────────────────────────────

def run_book(P: pd.DataFrame, picks: dict, *, start: str = "1991-01-01") -> pd.DataFrame:
    """Per decision date: the long book (EW picks, costs on traded weight), the twin basket
    (gross, its own trade cost and borrow as a SHORT), the band-matched VW index, and the
    universe aggregates the decomposition needs."""
    from backend.services import hyp_investable as HI                # noqa: PLC0415
    from backend.services import matched_twins as MT                 # noqa: PLC0415
    rows = []
    prev_book, prev_twin = {}, {}
    for d, g in P.groupby("date", sort=True):
        if d < pd.Timestamp(start) or not g["fwd_ret"].notna().any():
            continue
        g = g.drop_duplicates("symbol").set_index("symbol")
        fwd = g["fwd_ret"].astype(float)
        spread = g["_sp"].to_dict()
        band = pd.Series(MT.size_band(g["median_dollar_vol"].to_numpy(dtype=float)), index=g.index)
        band_of = band.to_dict()
        ok = g["eligible"] & fwd.notna()
        sel = [s for s in picks.get(pd.Timestamp(d), []) if s in g.index]
        rec = {"date": d, "n": len(sel)}
        if sel:
            ct = MT.cell_table(g.reset_index())
            cells = ct["band"].astype(str) + "|" + ct["vt"].astype(str) + "|" + ct["mt"].astype(str)
            w = {s: 1.0 / len(sel) for s in sel}
            c, to = MT.trade_cost(prev_book, w, spread, 0.0035)
            rec.update(gross=HI.book_return(w, fwd), cost=c, turnover=to)
            tw = HI.twin_basket(sel, cells, ok)
            tc, tto = MT.trade_cost(prev_twin, tw, spread, 0.0035)
            rec.update(twin_gross=HI.book_return(tw, fwd), twin_cost=tc, twin_turnover=tto,
                       twin_full_rt=MT.twin_full_round_trip_upper_bound(tw, spread, 0.0035),
                       twin_borrow=HI.borrow_cost_monthly(tw, band_of),
                       twin_spread_mean=float(np.nanmean([spread.get(s, np.nan) for s in tw])) if tw else np.nan,
                       twin_n=len(tw))
            bi = (HI.band_index(band.reindex(sel), band, g["mcap"].astype(float), ok)
                  if "mcap" in g.columns else {})
            rec.update(bandidx_gross=HI.book_return(bi, fwd),
                       pick_adv_median=float(np.nanmedian(g.loc[sel, "median_dollar_vol"].astype(float))),
                       share_small=float((band.reindex(sel) == "small").mean()))
            prev_book, prev_twin = HI.drift(w, fwd), HI.drift(tw, fwd)
        else:
            c, to = MT.trade_cost(prev_book, {}, spread, 0.0035)
            tc, tto = MT.trade_cost(prev_twin, {}, spread, 0.0035)
            rec.update(gross=np.nan, cost=c, turnover=to, twin_gross=np.nan, twin_cost=tc, twin_turnover=tto,
                       twin_full_rt=0.0, twin_borrow=0.0,
                       bandidx_gross=np.nan)
            prev_book, prev_twin = {}, {}
        rows.append(rec)
    return pd.DataFrame(rows).set_index("date")


def universe_frame(P: pd.DataFrame) -> pd.DataFrame:
    """Eligible-universe aggregates per date: EW and VW gross, EW by band, the delisting
    rows' contribution to EW, and the mean round-trip spread of an EW universe holder."""
    from backend.services import matched_twins as MT                 # noqa: PLC0415
    rows = []
    for d, g in P[P["eligible"] & P["fwd_ret"].notna()].groupby("date", sort=True):
        g = g.drop_duplicates("symbol")
        r = g["fwd_ret"].astype(float)
        mc = g["mcap"].astype(float)
        okc = mc > 0
        band = MT.size_band(g["median_dollar_vol"].to_numpy(dtype=float))
        dl = g["delisted_in_period"].to_numpy(dtype=bool)
        rec = {"date": d, "n": len(g), "ew": float(r.mean()),
               "vw": float((r[okc] * mc[okc]).sum() / mc[okc].sum()) if okc.any() else np.nan,
               "ew_delist_contrib": float((r.where(dl, 0.0)).sum() / len(g)), "delist_share": float(dl.mean()),
               "ew_spread": float(g["_sp"].mean())}
        for b in ("mega", "large", "mid", "small"):
            m = band == b
            rec[f"ew_{b}"] = float(r[m].mean()) if m.any() else np.nan
            rec[f"share_{b}"] = float(m.mean())
        rows.append(rec)
    return pd.DataFrame(rows).set_index("date")


def _win_means(s: pd.Series) -> dict:
    from backend.services import hyp_investable as HI                # noqa: PLC0415
    out = {}
    for k, (lo, hi) in {"full": (None, None), **SPLITS}.items():
        st = HI.spread_stats(s, lo, hi)
        out[k] = {"mean_monthly": st["mean_monthly"], "t_blocks": st["t_blocks"], "mde_monthly": st["mde_monthly"]}
    return out


def _library_series(rule: str) -> pd.DataFrame:
    for run in (BOARD_CS, LIB_CS):
        p = CR_OUT / f"library_series_{run}" / f"{rule}.parquet"
        if p.exists():
            s = pd.read_parquet(p)
            s.attrs["run"] = run
            return s
    raise FileNotFoundError(rule)


def part_decompose(tag: str) -> int:
    rp = OUT / f"investable_decompose_{tag}.json"
    if rp.exists():
        say(f"REFUSED: {rp.name} exists")
        return 2
    t0 = time.time()
    P = load(tag)
    P["_sp"] = spreads_of(P)
    dates = sorted(P["date"].unique())
    mkt, rf = market_and_rf(dates)
    U = universe_frame(P)
    U["market"] = mkt.reindex(U.index)
    say(f"  universe frame {time.time()-t0:.0f}s")
    generic = {
        "vw_eligible_minus_market (eligibility filters + cap measure)": _win_means(U["vw"] - U["market"]),
        "ew_eligible_minus_vw_eligible (equal weighting = size tilt)": _win_means(U["ew"] - U["vw"]),
        "ew_eligible_minus_market": _win_means(U["ew"] - U["market"]),
        "ew_delisting_rows_contribution": _win_means(U["ew_delist_contrib"]),
        "ew_small_minus_market": _win_means(U["ew_small"] - U["market"]),
        "ew_mid_minus_market": _win_means(U["ew_mid"] - U["market"]),
        "ew_large_minus_market": _win_means(U["ew_large"] - U["market"]),
        "ew_mega_minus_market": _win_means(U["ew_mega"] - U["market"]),
        "ew_universe_one_full_round_trip_cost": _win_means(-U["ew_spread"]),
    }
    share = {b: {k: float(U[f"share_{b}"][(U.index.year >= int(lo[:4])) & (U.index.year <= int(hi[:4]))].mean())
                 for k, (lo, hi) in SPLITS.items()} for b in ("mega", "large", "mid", "small")}
    per_rule = {}
    S = {}
    for rid in RULES + (REV,):
        tr = time.time()
        pk = picks_revision(P)[0] if rid == REV else picks_library(P, rid)
        B = run_book(P, pk, start=FLOW_START if rid == REV else "1991-01-01")
        B["market"], B["rf"] = mkt.reindex(B.index), rf.reindex(B.index)
        B = B.join(U[["ew", "vw"]], how="left")
        S[rid] = B
        B.to_parquet(OUT / f"investable_book_{tag}_{rid}.parquet")
        inv = B["gross"].notna()
        comp = {
            "A_eligible_vw_minus_market": _win_means((B["vw"] - B["market"])[inv]),
            "B_equal_weight_minus_vw": _win_means((B["ew"] - B["vw"])[inv]),
            "C_twin_cells_minus_ew_universe": _win_means((B["twin_gross"] - B["ew"])[inv]),
            "D_twin_basket_cost_one_full_round_trip": _win_means(-B["twin_spread_mean"][inv]),
            "twin_basket_gross_minus_market (A+B+C)": _win_means((B["twin_gross"] - B["market"])[inv]),
            "rule_gross_minus_twin_basket_gross (pure selection)": _win_means((B["gross"] - B["twin_gross"])[inv]),
            "rule_net_minus_market (this engine, actual turnover x spread)": _win_means(
                (B["gross"] - B["cost"] - B["market"])[inv]),
            "rule_cost_monthly": _win_means(-B["cost"][inv]),
        }
        if rid != REV:
            L = _library_series(rid)
            lt = (L["twin21_net"] - L["market"]).dropna()
            comp["library_twin21_net_minus_market (the quoted drag, run " + L.attrs["run"] + ")"] = _win_means(lt)
            j = pd.concat([L["twin21_net"], B["twin_gross"]], axis=1, keys=["t21", "tb"]).dropna()
            comp["library_twin21_net_minus_twin_basket_gross (cost + draw noise)"] = _win_means(j["t21"] - j["tb"])
        per_rule[rid] = {"components": comp, "months_invested": int(inv.sum()),
                         "mean_turnover": float(B.loc[inv, "turnover"].mean()),
                         "mean_twin_turnover": float(B.loc[inv, "twin_turnover"].mean()),
                         "share_small_picks": float(B.loc[inv, "share_small"].mean()),
                         "seconds": round(time.time() - tr, 1)}
        say(f"  {rid}: {per_rule[rid]['months_invested']} months {time.time()-tr:.0f}s")
        gc.collect()
    doc = {"schema": "hyp_lab/investable_decompose/1", "tag": tag, "written_utc": _now(), "job": JOB,
           "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "note": ("Descriptive: no candidate is selected on these numbers; the spread declaration is written "
                    "from the construction, not from this table. All %/mo keyed on the hold month; t on 3-month "
                    "blocks. The market is FF mkt+rf, costless."),
           "splits": SPLITS, "universe": generic, "band_share_of_eligible_names": share, "per_rule": per_rule,
           "seconds": round(time.time() - t0, 1)}
    _write(rp, doc)
    say(f"-> {rp.name} {time.time()-t0:.0f}s")
    return 0


# ── declaration and the one read ─────────────────────────────────────────────

VARIANTS = {
    "A_long_vs_market": "rule net (EW, actual traded weight x max(CS, flat band)/2) - market (FF mkt+rf, costless)",
    "B_beta_hedged": ("(rule net - rf) - beta_t x (market - rf) - future cost 0.12%/yr; beta_t = OLS of the rule's "
                      "gross excess on the market excess over the 36 months strictly before d (min 24; before that "
                      "beta = 1)"),
    "C_short_twin_basket": ("rule net - (twin basket gross + its own traded-weight spread cost + borrow by band "
                            "0.25/0.30/0.60/1.50%/yr mega/large/mid/small); the twin basket = the selection's cell mix "
                            "x every non-selected eligible name in the cell, EW within a cell, drifted between months"),
    "D_short_band_index": ("rule net - (band-matched cap-weighted index of eligible names, the rule's band mix, "
                           "+ 0.35%/yr all-in short cost) -- long the picks, short the size index"),
    "E_overlay_top500": ("top-500-by-dollar-volume cap-weighted base + a 20% active-share tilt toward the rule's "
                         "score (cap 0.5%/name, band 0.1%, active turnover budget 15%/mo, sector-balanced), costs on "
                         "traded weight for book and base; read as book net - market"),
}
DECISION = ("A variant SURVIVES iff design (hold months 1991-2008; revision 1999-10..2008) mean > 0 AND validate "
            "(2009-2016) mean > 0 with t >= 2 on 3-month blocks AND a strict majority of the 8 validate years > 0. "
            "2017-2024 is read last, as description. A REGISTRATION candidate additionally needs 2017-2024 mean > 0. "
            "At most two registrations.")
HONESTY = ("These four leads were chosen AFTER their validation windows were partly read: the board already printed "
           "rule-twin and rule-market for 2009-2016 and 2017-2024, and the revision cell's small-band trend-on split "
           "was seen on the full 1999-2024 sample. Variants A and C are therefore implementation reads of numbers "
           "whose sign is known; B, D and E are constructions never computed before. No read here is a clean "
           "out-of-sample test; nothing from it can be a RESEARCH_CLAIM.")


def declaration() -> dict:
    n_cells = 4 * len(RULES) + 4 + len(RULES)   # A-D for all four, E for the three library rules
    return {"schema": "hyp_lab/investable_declaration/1", "job": JOB, "licence": "PRODUCT_EXPERIMENT",
            "written_before_any_spread_was_read": True, "candidates": list(RULES) + [REV],
            "revision_definition": ("conditional C06 restricted to the small band: net_raises top 20% of eligible "
                                    "covered names and >= 1, band small (median $ volume < $20M), market close above "
                                    "its 200-day MA at d; months with < 5 names or trend off hold nothing (spread 0)"),
            "variants": VARIANTS, "overlay": OVERLAY, "decision": DECISION, "honesty": HONESTY, "splits": SPLITS,
            "costs": "long legs: traded weight x max(Corwin-Schultz capped 20%, flat band 6/10/18/35 bps)/2",
            "borrow_annual": __import__("backend.services.hyp_investable", fromlist=["x"]).BORROW_ANNUAL,
            "search_count": {"prior": PRIOR_SEARCH, "cells_this_run": n_cells, "after": PRIOR_SEARCH + n_cells}}


def part_declare(tag: str) -> int:
    p = OUT / f"investable_DECLARATION_{tag}.json"
    if p.exists():
        say(f"REFUSED: {p.name} exists")
        return 2
    body = declaration()
    body["sha16"] = _sha(body)
    body["written_utc"] = _now()
    _write(p, body)
    say(f"-> {p.name} sha {body['sha16']}")
    return 0


def overlay_series(P: pd.DataFrame, rid: str) -> pd.DataFrame:
    from backend.services import strategy_library as SL              # noqa: PLC0415
    from scripts import revision_tilt_on_crsp as RTS                 # noqa: PLC0415
    rule = {r.id: r for r in SL.rules()}[rid]
    need = ["date", "symbol", "eligible", "fwd_ret", "median_dollar_vol", "delisted_in_period"] + list(rule.requires)
    sc = SL.selection_scores(P[need], rule)
    Q = P[["date", "symbol", "permno", "eligible", "fwd_ret", "median_dollar_vol", "mcap", "cs_spread",
           "gsector"]].copy()
    Q["net_raises"] = sc.to_numpy(dtype=float)       # the tilt engine reads its score from this column
    Q["n_firms"], Q["ear_last"] = np.nan, np.nan
    o = RTS.simulate(Q, signal="net_raises", active_share=OVERLAY["active_share"], band=OVERLAY["band"],
                     scheme=OVERLAY["scheme"], cap=OVERLAY["cap"], budget=OVERLAY["budget"], n=OVERLAY["base_n"])
    return o["series"]


def part_run(tag: str) -> int:
    from backend.services import hyp_investable as HI                # noqa: PLC0415
    from learner.inference import deflated_sharpe                    # noqa: PLC0415
    dp = OUT / f"investable_DECLARATION_{tag}.json"
    d = json.loads(dp.read_text(encoding="utf-8"))
    if _sha({k: v for k, v in d.items() if k not in ("sha16", "written_utc")}) != d["sha16"]:
        say("REFUSED: declaration hash mismatch")
        return 2
    rp = OUT / f"investable_RESULTS_{tag}.json"
    if rp.exists():
        say(f"REFUSED: {rp.name} exists (read once)")
        return 2
    t0 = time.time()
    n_trials = int(d["search_count"]["after"])
    P = None
    res = {}
    for rid in d["candidates"]:
        B = pd.read_parquet(OUT / f"investable_book_{tag}_{rid}.parquet")
        inv = B["gross"].notna()
        net = B["gross"] - B["cost"]
        mk, rf = B["market"], B["rf"]
        # months with no book: the long leg holds nothing -> every spread is 0 (cash vs cash)
        beta = HI.pit_beta((B["gross"] - rf).where(inv), (mk - rf).where(inv)).fillna(1.0)
        sp = {
            "A_long_vs_market": (net - mk).where(inv, 0.0),
            "B_beta_hedged": ((net - rf) - beta * (mk - rf) - HI.FUTURE_ANNUAL / 12).where(inv, 0.0),
            "C_short_twin_basket": (net - (B["twin_gross"] + B["twin_cost"] + B["twin_borrow"])).where(inv, 0.0),
            "D_short_band_index": (net - (B["bandidx_gross"] + HI.INDEX_SHORT_ANNUAL / 12)).where(inv, 0.0),
        }
        if rid != REV:
            if P is None:
                P = load(tag)
            O = overlay_series(P, rid)
            O.to_parquet(OUT / f"investable_overlay_{tag}_{rid}.parquet")
            sp["E_overlay_top500"] = (O["book_net"] - mk.reindex(O.index)).dropna()
            sp["E_overlay_minus_base"] = (O["book_net"] - O["base_net"]).dropna()
        lo0 = FLOW_START if rid == REV else None
        out = {}
        for v, s in sp.items():
            s = s.dropna()
            if lo0:
                s = s[s.index >= pd.Timestamp(lo0)]
            st = {k: HI.spread_stats(s, lo, hi) for k, (lo, hi) in SPLITS.items()}
            if rid == REV:
                st["design"] = HI.spread_stats(s, "1999-10-01", "2008-12-31")
            ok, fails = HI.survives(st["design"], st["validate"])
            dv = HI.window(s, None, "2016-12-31")
            ds = deflated_sharpe(dv.tolist(), n_trials=n_trials) if len(dv) > 8 else {}
            reg = ok and (st["late"].get("mean_monthly") or 0) > 0 and v != "E_overlay_minus_base"
            out[v] = {**st, "full": HI.spread_stats(s), "survives": ok, "fails": fails,
                      "dsr_to_2016": ds.get("dsr"), "registration_candidate": bool(reg)}
            say(f"  {rid:22s} {v:22s} D {st['design']['mean_monthly']:+.4f} V {st['validate']['mean_monthly']:+.4f} "
                f"t {st['validate']['t_blocks']} yrs {st['validate']['years_positive']} L "
                f"{st['late']['mean_monthly']:+.4f} {'SURVIVES' if ok else ''}")
        capacity = {}
        adv = B.loc[inv, "pick_adv_median"]
        k = B.loc[inv, "n"].median()
        for cap_usd in (1e6, 1e7, 1e8):
            capacity[f"${int(cap_usd/1e6)}M"] = {"per_name_usd": cap_usd / k,
                                                 "pct_of_median_pick_adv_by_era": {
                                                     str(e): float(np.nanmedian(cap_usd / k / adv[(adv.index.year // 10 * 10) == e]) * 100)
                                                     for e in sorted(set(adv.index.year // 10 * 10))}}
        res[rid] = {"variants": out, "beta_mean_validate": float(beta[(beta.index.year >= 2009) &
                                                                      (beta.index.year <= 2016)].mean()),
                    "turnover_mean": float(B.loc[inv, "turnover"].mean()),
                    "cost_bps_per_month_mean": float(B.loc[inv, "cost"].mean() * 1e4),
                    "twin_turnover_mean": float(B.loc[inv, "twin_turnover"].mean()),
                    "twin_cost_bps_mean": float(B.loc[inv, "twin_cost"].mean() * 1e4),
                    "twin_borrow_bps_mean": float(B.loc[inv, "twin_borrow"].mean() * 1e4),
                    "median_names": float(k), "months_invested": int(inv.sum()), "capacity": capacity}
    doc = {"schema": "hyp_lab/investable_results/1", "tag": tag, "declaration_sha16": d["sha16"],
           "written_utc": _now(), "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0, "decision": DECISION,
           "honesty": HONESTY, "n_trials_for_dsr": n_trials, "results": res,
           "n_survivors": sum(v["survives"] for r in res.values() for v in r["variants"].values()),
           "n_registration_candidates": sum(v["registration_candidate"] for r in res.values()
                                            for v in r["variants"].values()),
           "seconds": round(time.time() - t0, 1)}
    _write(rp, doc)
    say(f"-> {rp.name} survivors {doc['n_survivors']} candidates {doc['n_registration_candidates']} "
        f"{time.time()-t0:.0f}s")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", required=True, choices=["inputs", "decompose", "declare", "run"])
    ap.add_argument("--tag", required=True)
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    if a.part != "declare" and not _mem_ok():
        say("REFUSED: under 3 GB free for 30 minutes")
        return 3
    return {"inputs": part_inputs, "decompose": part_decompose, "declare": part_declare,
            "run": part_run}[a.part](a.tag)


if __name__ == "__main__":
    raise SystemExit(main())
