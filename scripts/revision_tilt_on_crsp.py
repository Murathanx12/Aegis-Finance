"""Revision flow as a TILT on a top-500 market-like base, on CRSP (2026-09-29).

    python -m scripts.revision_tilt_on_crsp --part inputs  --tag <T>     # build the input frame (~2 min)
    python -m scripts.revision_tilt_on_crsp --part declare --tag <T>     # write the declaration BEFORE any run
    python -m scripts.revision_tilt_on_crsp --part design  --tag <T>     # 18 variants, DESIGN dates only
    python -m scripts.revision_tilt_on_crsp --part validate --tag <T>    # the ONE chosen config, full run

Licence `PRODUCT_EXPERIMENT`. $0, no LLM, no network, no broker call. Nothing is
traded; no book, ledger row or earlier receipt is touched. Every receipt is new
and named by run tag; a part REFUSES to overwrite.

The construction lives in `backend/services/revision_tilt.py`. The split, the
variant grid, the selection rule and the decision rule are written to
`revision_tilt_DECLARATION_<tag>.json` (hashed) before the design run, and the
design run only ever simulates decision dates whose hold month ends by 2008-12.
The validate part refuses unless the declaration hash and the selection receipt
agree.
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

JOB = "revision_tilt_on_crsp"
OPT = REPO / "backend" / "data" / "optimus"
WRDS = OPT / "wrds"
OUT = OPT / "crsp_rebuild"
PANEL_RUN = "2026-09-29T075640Z"
FUND_RUN = "2026-09-29T041550Z"
BRIDGE_RUN = "EB_2026-09-29T1055Z"
CS_DAILY_RUN = "FU_2026-09-29T0855Z"
CS_CAP = 0.20
FLOW_START = "1999-09-30"          # the bridge's declared first decision date for revision flow
PRIOR_LOOKS = 42_378               # the running count before this experiment
SPLITS = {"design": ("1999-10-01", "2008-12-31"), "validate": ("2009-01-01", "2016-12-31"),
          "late_2017_2024": ("2017-01-01", "2024-12-31")}
GRID = {"signal": ["net_raises", "breadth", "ear_flow"], "active_share": [0.10, 0.20, 0.30],
        "band": [0.0005, 0.0010]}
FIXED = {"base_n": 500, "base_rank": "trailing median daily dollar volume (panel median_dollar_vol), eligible names",
         "base_scheme": "cap", "base_scheme_sensitivity": "equal", "cap_per_name": 0.005,
         "turnover_budget_active_monthly": 0.15, "sector_neutral": "PIT gsector (WRDS ratios), unknown sector = own group",
         "long_only": True, "rebalance": "monthly at the panel's month-end decision dates"}
COSTS = {"primary": ("per name per month: max(Corwin-Schultz round-trip spread capped at 20%, the engine's flat band "
                     "schedule 6/10/18/35 bps); flat band where CS is missing; charged as |trade| x spread / 2 on "
                     "ACTUAL traded weight, book and base alike; the market leg (FF mktrf + rf) is costless"),
         "sensitivity": "flat band schedule only, same turnover scaling"}
SELECTION_RULE = ("Among the 18 variants, choose the one with the highest t (3-month blocks, hold month) of "
                  "(book net - base net, primary costs) over the DESIGN window; ties -> smaller active share. "
                  "Nothing else is read before the choice.")
DECISION_RULE = ("CANDIDATE iff, for the ONE chosen config over VALIDATE 2009-2016 (hold month), book net - market "
                 "(primary costs) has mean > 0 AND t (3-month blocks) >= 2 AND is positive in >= 5 of the 8 hold years. "
                 "Else CANNOT_DISTINGUISH if the mean is > 0, FAILED_VARIANT if <= 0. 2017-2024 is read last and is "
                 "labelled NOT a clean holdout (the library's rules were written on the 2016-2026 vendor calendar). "
                 "If CANDIDATE: register ONE forward shadow (tilt on the current top-500 base, bar-defect screen on) "
                 "plus the untilted base as its matched comparison, kill line sized from the active return's sd. "
                 "Otherwise register nothing.")

# ── profiles (2026-09-29 evening) ───────────────────────────────────────────
# "top500" is the original experiment, byte-for-byte: its declaration() is the
# dict above and its hash reproduces 0f0939b893b2754e (pinned by test). A new
# profile changes the declared constants, so it has its own hash and its own tag.
PROFILES = {
    "top500": {"fixed": FIXED, "prior": PRIOR_LOOKS, "decision": DECISION_RULE, "rank_lo": 0,
               "inputs_tag": None, "extra": None},
    "mid501_1500": {
        "fixed": {**FIXED, "base_n": 1000, "base_rank_lo": 500,
                  "base_rank": ("ranks 501-1500 by trailing median daily dollar volume (panel median_dollar_vol), "
                                "eligible names"),
                  "base_scheme": "equal", "base_scheme_sensitivity": "cap", "cap_per_name": 0.01},
        "prior": 42_397,           # 42,378 + the top-500 experiment's 18 design cells + 1 validation
        "decision": DECISION_RULE.replace("tilt on the current top-500 base",
                                          "tilt on the current rank 501-1500 equal-weight base"),
        "rank_lo": 500,
        "inputs_tag": "RT_2026-09-29T1110Z",
        "extra": {"profile": "mid501_1500",
                  "why": ("revision_tilt_2026-09-29.md HIGHEST-EV: move the base, not the tilt; the names where "
                          "net_raises found its twin gap; equal-weight base because no cap-weighted index tracks there"),
                  "inputs_reused_from": ("revision_tilt_inputs_RT_2026-09-29T1110Z.parquet (same panel/fund/bridge/"
                                         "cs runs; it holds every eligible name, not only the top 500)"),
                  "primary_scheme": "equal (the verdict reads the equal-weight base)"},
    },
}
ACTIVE = {"profile": "top500"}


def _p() -> dict:
    return PROFILES[ACTIVE["profile"]]


def _primary_scheme() -> str:
    return _p()["fixed"]["base_scheme"]


def say(*a) -> None:
    print(*a, flush=True)


def _mem_ok(floor_gb: float = 2.0) -> bool:
    try:
        import psutil                                                # noqa: PLC0415
        return psutil.virtual_memory().available / 1e9 >= floor_gb
    except Exception:                                                # noqa: BLE001
        return True


def _sha(doc: dict) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _write(path: Path, doc: dict) -> None:
    from scripts.night_checkpoint import atomic_write_json           # noqa: PLC0415
    if path.exists():
        raise FileExistsError(f"REFUSED: {path.name} exists")
    atomic_write_json(path, doc, indent=1)


def variants() -> list[dict]:
    out = []
    for s in GRID["signal"]:
        for a in GRID["active_share"]:
            for b in GRID["band"]:
                out.append({"id": f"{s}_as{int(a*100)}_b{int(b*1e4)}", "signal": s, "active_share": a, "band": b})
    return out


# ── inputs ──────────────────────────────────────────────────────────────────

def part_inputs(tag: str) -> int:
    fp = OUT / f"revision_tilt_inputs_{tag}.parquet"
    if fp.exists():
        say(f"REFUSED: {fp.name} exists")
        return 2
    t0 = time.time()
    P = pd.read_parquet(OUT / f"library_panel_{PANEL_RUN}.parquet",
                        columns=["date", "symbol", "eligible", "fwd_ret", "median_dollar_vol", "delisted_in_period"],
                        filters=[("date", ">=", pd.Timestamp(FLOW_START))])
    P["date"] = pd.to_datetime(P["date"])
    E = pd.read_parquet(OUT / f"event_bridge_{BRIDGE_RUN}.parquet",
                        columns=["date", "symbol", "net_raises", "n_firms", "ear_last"],
                        filters=[("date", ">=", pd.Timestamp(FLOW_START))])
    E["date"] = pd.to_datetime(E["date"])
    P = P.merge(E, on=["date", "symbol"], how="left")
    del E
    F = pd.read_parquet(OUT / f"library_fund_{FUND_RUN}.parquet", columns=["date", "symbol", "gsector"],
                        filters=[("date", ">=", pd.Timestamp(FLOW_START))])
    F["date"] = pd.to_datetime(F["date"])
    F["gsector"] = pd.to_numeric(F["gsector"], errors="coerce").astype("float32")
    P = P.merge(F, on=["date", "symbol"], how="left")
    del F
    P["permno"] = pd.to_numeric(P["symbol"], errors="coerce")
    P = P.dropna(subset=["permno"])
    P["permno"] = P["permno"].astype("int64")
    dates = set(P["date"].unique())
    caps = []
    for y in range(1999, 2025):
        d = pd.read_parquet(WRDS / f"crsp_dsf_{y}.parquet", columns=["permno", "date", "prc", "shrout"])
        d["date"] = pd.to_datetime(d["date"])
        d = d[d["date"].isin(dates)]
        d["permno"] = pd.to_numeric(d["permno"], errors="coerce")
        d = d.dropna(subset=["permno"])
        d["permno"] = d["permno"].astype("int64")
        d["mcap"] = (pd.to_numeric(d["prc"], errors="coerce").abs()
                     * pd.to_numeric(d["shrout"], errors="coerce") * 1e3).astype("float64")
        caps.append(d[["permno", "date", "mcap"]])
        del d
        gc.collect()
    C = pd.concat(caps, ignore_index=True).drop_duplicates(["permno", "date"])
    P = P.merge(C, on=["permno", "date"], how="left")
    del C
    D = pd.read_parquet(OUT / f"followups_daily_{CS_DAILY_RUN}.parquet", columns=["date", "permno", "cs_spread"],
                        filters=[("date", ">=", pd.Timestamp(FLOW_START))])
    D["date"] = pd.to_datetime(D["date"])
    D["permno"] = pd.to_numeric(D["permno"], errors="coerce")
    D = D.dropna(subset=["permno"])
    D["permno"] = D["permno"].astype("int64")
    P = P.merge(D.drop_duplicates(["permno", "date"]), on=["permno", "date"], how="left")
    del D
    for c in ("net_raises", "n_firms", "ear_last", "mcap", "cs_spread"):
        P[c] = P[c].astype("float32") if c not in ("mcap",) else P[c]
    P.to_parquet(fp, index=False)
    el = P[P["eligible"].astype(bool)]
    say(f"-> {fp.name}: {len(P):,} rows, {P['date'].nunique()} dates, mcap coverage (eligible) "
        f"{el['mcap'].notna().mean():.3f}, cs coverage {el['cs_spread'].notna().mean():.3f}, "
        f"gsector {el['gsector'].notna().mean():.3f} {time.time()-t0:.0f}s")
    return 0


def load_inputs(tag: str) -> pd.DataFrame:
    P = pd.read_parquet(OUT / f"revision_tilt_inputs_{_p()['inputs_tag'] or tag}.parquet")
    P["date"] = pd.to_datetime(P["date"])
    P["eligible"] = P["eligible"].astype(bool)
    return P


# ── simulation ──────────────────────────────────────────────────────────────

def cost_rates(g: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    from backend.services import xs_ranker as XR                     # noqa: PLC0415
    flat = np.array([XR.COST_BPS_BY_BAND[XR.liquidity_band(v)] / 1e4
                     for v in g["median_dollar_vol"].to_numpy(dtype=float)])
    cs = np.minimum(g["cs_spread"].to_numpy(dtype=float), CS_CAP)
    prim = np.where(np.isfinite(cs), np.maximum(cs, flat), flat)
    return prim, flat


def simulate(P: pd.DataFrame, *, signal: str, active_share: float, band: float, scheme: str = "cap",
             cap: float = 0.005, budget: float = 0.15, n: int = 500, last_hold: str | None = None,
             keep_trades: bool = False, rank_lo: int = 0) -> dict:
    """Monthly simulation. Returns a per-decision-date frame (book/base gross and net under
    both cost schemes, turnover) and trade-level participation for capacity."""
    from backend.services import revision_tilt as RT                 # noqa: PLC0415
    dates = sorted(P["date"].unique())
    if last_hold:
        dates = [d for d in dates if pd.Timestamp(d) + pd.offsets.BDay(1) <= pd.Timestamp(last_hold)]
    groups = {d: g for d, g in P.groupby("date", sort=True)}
    held_book: dict = {}
    held_base: dict = {}
    rows, trades = [], []
    for d in dates:
        g = groups[d]
        el = g["eligible"].to_numpy(dtype=bool)
        dv = g["median_dollar_vol"].to_numpy(dtype=float)
        mc = g["mcap"].to_numpy(dtype=float)
        b_all = RT.base_weights(dv, el, mc, n=n, scheme=scheme, rank_lo=rank_lo)
        perm = g["permno"].to_numpy()
        idx_pos = {p: i for i, p in enumerate(perm)}
        keep = b_all > 0
        for p in list(held_book) + list(held_base):
            if p in idx_pos:
                keep[idx_pos[p]] = True
        h = g[keep]
        b = b_all[keep]
        pm = h["permno"].to_numpy()
        wb_prev = np.array([held_book.get(p, 0.0) for p in pm])
        bb_prev = np.array([held_base.get(p, 0.0) for p in pm])
        lost_book = max(0.0, sum(held_book.values()) - wb_prev.sum())
        lost_base = max(0.0, sum(held_base.values()) - bb_prev.sum())
        first = not held_book
        if first:
            wb_prev, bb_prev = b.copy(), b.copy()
        score = RT.signal_score(h, signal)
        sec = h["gsector"].to_numpy(dtype=float)
        a_t = RT.target_active(score, b, active_share=active_share, cap=cap, sector=sec)
        a_new, act_turn = RT.step_active(wb_prev - b, a_t, b, cap=cap, band=band, budget=budget)
        w = b + a_new
        dw, db = w - wb_prev, b - bb_prev
        prim, flat = cost_rates(h)
        r = h["fwd_ret"].to_numpy(dtype=float)
        n_nan = int((~np.isfinite(r) & (w > 0)).sum())
        rr = np.where(np.isfinite(r), r, 0.0)
        book_g, base_g = float(w @ rr), float(b @ rr)
        c_book_p, c_book_f = float(np.abs(dw) @ prim / 2), float(np.abs(dw) @ flat / 2)
        c_base_p, c_base_f = float(np.abs(db) @ prim / 2), float(np.abs(db) @ flat / 2)
        rows.append({"date": d, "book_gross": book_g, "base_gross": base_g,
                     "book_net": book_g - c_book_p, "base_net": base_g - c_base_p,
                     "book_net_flat": book_g - c_book_f, "base_net_flat": base_g - c_base_f,
                     "cost_book_bps": c_book_p * 1e4, "cost_base_bps": c_base_p * 1e4,
                     "turnover_book": 0.5 * (np.abs(dw).sum() + lost_book),
                     "turnover_base": 0.5 * (np.abs(db).sum() + lost_base),
                     "turnover_active": act_turn, "active_share": 0.5 * float(np.abs(a_new).sum()),
                     "active_share_target_reached": 0.5 * float(np.abs(a_t).sum()),
                     "max_abs_active": float(np.abs(a_new).max()) if len(a_new) else 0.0,
                     "n_base": int((b > 0).sum()), "n_over": int((a_new > 1e-9).sum()),
                     "n_under": int((a_new < -1e-9).sum()), "n_nan_ret_held": n_nan,
                     "signal_coverage_in_base": float(np.isfinite(score[b > 0]).mean()) if (b > 0).any() else 0.0,
                     "first": first})
        if keep_trades:
            m = np.abs(dw) > 1e-7
            trades.append(pd.DataFrame({"date": d, "abs_dw": np.abs(dw[m]), "adv": dv[keep][m],
                                        "abs_da": np.abs(dw[m] - db[m])}))
        wd, bd = RT.drift(w, r), RT.drift(b, r)
        held_book = {p: x for p, x in zip(pm, wd) if x > 0}
        held_base = {p: x for p, x in zip(pm, bd) if x > 0}
    S = pd.DataFrame(rows).set_index("date")
    return {"series": S, "trades": pd.concat(trades, ignore_index=True) if trades else None}


def market_series(P: pd.DataFrame) -> pd.Series:
    from scripts import momentum_on_crsp as M                         # noqa: PLC0415
    return M.spy_series(P[["date"]].drop_duplicates())


def stats_block(s: pd.Series) -> dict:
    from backend.services import calendar_offsets as CO              # noqa: PLC0415
    from backend.services import crsp_rebuild as CR                  # noqa: PLC0415
    from backend.services import revision_tilt as RT                 # noqa: PLC0415
    s = s.dropna()
    out = {}
    for k, (lo, hi) in SPLITS.items():
        w = CR.window_stats(s, lo, hi)
        hold = pd.DatetimeIndex(s.index) + pd.offsets.BDay(1)
        sub = s[(hold >= pd.Timestamp(lo)) & (hold <= pd.Timestamp(hi))]
        sd = float(sub.std()) if len(sub) > 2 else None
        w["sd_monthly"] = sd
        w["ir_annual"] = (float(sub.mean()) / sd * np.sqrt(12)) if sd else None
        w["tracking_error_annual"] = sd * np.sqrt(12) if sd else None
        w["max_drawdown"] = RT.max_drawdown(sub)
        by = CO.by_hold_year(sub)
        w["by_hold_year_sum"] = {y: round(v["sum"], 5) for y, v in by.items()}
        w["years_positive"] = f"{sum(1 for v in by.values() if v['sum'] > 0)} of {len(by)}"
        lw = CO.loo_worst(sub)
        w["loo_worst"] = {"mean_monthly": lw["worst"], "dropped_year": lw["dropped_year"]}
        out[k] = w
    return out


# ── declare / design / validate ─────────────────────────────────────────────

def declaration() -> dict:
    p = _p()
    FIXED, PRIOR_LOOKS, DECISION_RULE = p["fixed"], p["prior"], p["decision"]      # noqa: N806
    doc = {"schema": "crsp_rebuild/revision_tilt_declaration/1", "job": JOB, "licence": "PRODUCT_EXPERIMENT",
            "inputs": {"panel": PANEL_RUN, "fund": FUND_RUN, "bridge": BRIDGE_RUN, "cs_daily": CS_DAILY_RUN,
                       "flow_start_decision_date": FLOW_START},
            "splits_hold_month": SPLITS, "variant_grid": GRID, "n_variants": len(variants()),
            "fixed": FIXED, "costs": COSTS, "selection_rule": SELECTION_RULE, "decision_rule": DECISION_RULE,
            "search_count": {"prior": PRIOR_LOOKS, "this_experiment_design_cells": len(variants()),
                             "validation_cells": 1, "total_for_deflation": PRIOR_LOOKS + len(variants()) + 1},
            "market": "FF daily mktrf + rf compounded over (decision date, next decision date] (momentum_on_crsp.spy_series)",
            "statistics": "3-month blocks keyed on the hold month (crsp_rebuild.window_stats); MDE = 2.8 x SE"}
    if p["extra"]:
        doc.update(p["extra"])
    return doc


def part_declare(tag: str) -> int:
    doc = declaration()
    doc["declaration_hash"] = _sha(declaration())
    doc["written_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _write(OUT / f"revision_tilt_DECLARATION_{tag}.json", doc)
    say(f"declaration {doc['declaration_hash']} written")
    return 0


def _check_declaration(tag: str) -> str:
    d = json.loads((OUT / f"revision_tilt_DECLARATION_{tag}.json").read_text(encoding="utf-8"))
    h = _sha(declaration())
    if d.get("declaration_hash") != h:
        raise RuntimeError(f"REFUSED: declaration hash {d.get('declaration_hash')} != code {h}")
    return h


def part_design(tag: str) -> int:
    from backend.services import crsp_rebuild as CR                  # noqa: PLC0415
    h = _check_declaration(tag)
    P = load_inputs(tag)
    lo, hi = SPLITS["design"]
    res = {}
    t0 = time.time()
    for v in variants():
        fx = _p()["fixed"]
        S = simulate(P, signal=v["signal"], active_share=v["active_share"], band=v["band"], budget=fx[
            "turnover_budget_active_monthly"], cap=fx["cap_per_name"], last_hold=hi, scheme=fx["base_scheme"],
            n=fx["base_n"], rank_lo=_p()["rank_lo"])["series"]
        act = S["book_net"] - S["base_net"]
        w = CR.window_stats(act, lo, hi)
        res[v["id"]] = {**v, "design_active_vs_base": w,
                        "mean_turnover_active": float(S["turnover_active"].mean()),
                        "mean_turnover_book": float(S["turnover_book"].mean()),
                        "mean_active_share": float(S["active_share"].mean()),
                        "last_decision": str(S.index.max().date())}
        say(f"  {v['id']:28s} active vs base {w['mean_monthly']*100:+.3f}%/mo t {w['t_blocks']:+.2f} "
            f"turn_act {res[v['id']]['mean_turnover_active']:.3f} AS {res[v['id']]['mean_active_share']:.3f} "
            f"{time.time()-t0:.0f}s")
    best = max(res.values(), key=lambda r: ((r["design_active_vs_base"]["t_blocks"] or -99), -r["active_share"]))
    doc = {"schema": "crsp_rebuild/revision_tilt_design/1", "job": JOB, "tag": tag, "declaration_hash": h,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "design_window_hold": SPLITS["design"], "variants": res, "chosen": best["id"],
           "chosen_config": {k: best[k] for k in ("signal", "active_share", "band")}}
    doc["selection_hash"] = _sha({"declaration_hash": h, "chosen_config": doc["chosen_config"]})
    _write(OUT / f"revision_tilt_DESIGN_{tag}.json", doc)
    say(f"CHOSEN {best['id']} selection {doc['selection_hash']}")
    return 0


def part_validate(tag: str) -> int:
    from learner.inference import deflated_sharpe                    # noqa: PLC0415
    from backend.services import revision_tilt as RT                 # noqa: PLC0415
    h = _check_declaration(tag)
    D = json.loads((OUT / f"revision_tilt_DESIGN_{tag}.json").read_text(encoding="utf-8"))
    if D["declaration_hash"] != h:
        raise RuntimeError("REFUSED: design receipt was made under another declaration")
    cfg = D["chosen_config"]
    P = load_inputs(tag)
    mk = market_series(P)
    out = {"schema": "crsp_rebuild/revision_tilt_validate/1", "job": JOB, "tag": tag, "declaration_hash": h,
           "selection_hash": D["selection_hash"], "chosen": D["chosen"], "chosen_config": cfg,
           "written_utc": None}
    runs = {}
    fx = _p()["fixed"]
    for scheme in (fx["base_scheme"], fx["base_scheme_sensitivity"]):
        r = simulate(P, signal=cfg["signal"], active_share=cfg["active_share"], band=cfg["band"], scheme=scheme,
                     cap=fx["cap_per_name"], budget=fx["turnover_budget_active_monthly"], keep_trades=True,
                     n=fx["base_n"], rank_lo=_p()["rank_lo"])
        S = r["series"].join(mk.rename("market"), how="left")
        runs[scheme] = (S, r["trades"])
        S.to_parquet(OUT / f"revision_tilt_series_{tag}_{scheme}.parquet")
        blk = {
            "book_net_minus_market": stats_block(S["book_net"] - S["market"]),
            "book_net_minus_base_net": stats_block(S["book_net"] - S["base_net"]),
            "base_net_minus_market": stats_block(S["base_net"] - S["market"]),
            "base_gross_minus_market": stats_block(S["base_gross"] - S["market"]),
            "book_gross_minus_base_gross": stats_block(S["book_gross"] - S["base_gross"]),
            "flat_costs": {"book_net_minus_market": stats_block(S["book_net_flat"] - S["market"]),
                           "book_net_minus_base_net": stats_block(S["book_net_flat"] - S["base_net_flat"])},
            "turnover": {k: {"book": float(S.loc[_win(S, *w), "turnover_book"].mean()),
                             "base": float(S.loc[_win(S, *w), "turnover_base"].mean()),
                             "active": float(S.loc[_win(S, *w), "turnover_active"].mean()),
                             "active_share": float(S.loc[_win(S, *w), "active_share"].mean()),
                             "cost_book_bps_mo": float(S.loc[_win(S, *w), "cost_book_bps"].mean()),
                             "cost_base_bps_mo": float(S.loc[_win(S, *w), "cost_base_bps"].mean()),
                             "signal_coverage_in_base": float(S.loc[_win(S, *w), "signal_coverage_in_base"].mean()),
                             "max_abs_active": float(S.loc[_win(S, *w), "max_abs_active"].max())}
                         for k, w in SPLITS.items()},
            "n_nan_ret_held_total": int(S["n_nan_ret_held"].sum()),
            "year_2009": {c: float((S[a] - S[b]).loc[_win(S, "2009-01-01", "2009-12-31")].sum())
                          for c, a, b in (("book_minus_market", "book_net", "market"),
                                          ("book_minus_base", "book_net", "base_net"),
                                          ("base_minus_market", "base_net", "market"))},
        }
        tr = r["trades"]
        tr["hold"] = pd.DatetimeIndex(tr["date"]) + pd.offsets.BDay(1)
        cap_ = {}
        for aum in (1e6, 1e8):
            part = tr["abs_dw"] * aum / tr["adv"].where(tr["adv"] > 0)
            m = tr["hold"] >= pd.Timestamp("2009-01-01")
            cap_[f"aum_{int(aum):,}"] = {
                "participation_median_2009_2024": float(part[m].median()),
                "participation_p99_2009_2024": float(part[m].quantile(0.99)),
                "participation_max_2009_2024": float(part[m].max()),
                "share_trades_over_1pct_adv": float((part[m] > 0.01).mean()),
                "share_trades_over_5pct_adv": float((part[m] > 0.05).mean())}
        blk["capacity"] = cap_
        out[f"base_{scheme}"] = blk
    S = runs[_primary_scheme()][0]
    out["primary_scheme"] = _primary_scheme()
    hold = pd.DatetimeIndex(S.index) + pd.offsets.BDay(1)
    vmask = (hold >= pd.Timestamp(SPLITS["validate"][0])) & (hold <= pd.Timestamp(SPLITS["validate"][1]))
    n_total = _p()["prior"] + len(variants()) + 1
    for nm, s in (("book_net_minus_market", S["book_net"] - S["market"]),
                  ("book_net_minus_base_net", S["book_net"] - S["base_net"])):
        out.setdefault("dsr_validate", {})[nm] = {
            "n_trials": n_total, **{k: v for k, v in deflated_sharpe(s[vmask].dropna().tolist(),
                                                                       n_trials=n_total).items()
                                    if k in ("dsr", "z", "sr", "sr_star", "n")}}
    v = out[f"base_{_primary_scheme()}"]["book_net_minus_market"]["validate"]
    npos = int(v["years_positive"].split(" of ")[0])
    mean_, t_ = v["mean_monthly"] or 0.0, v["t_blocks"] or 0.0
    if mean_ > 0 and t_ >= 2 and npos >= 5:
        verdict = "CANDIDATE"
    elif mean_ > 0:
        verdict = "CANNOT_DISTINGUISH"
    else:
        verdict = "FAILED_VARIANT"
    out["verdict"] = verdict
    out["verdict_inputs"] = {"mean_monthly": mean_, "t_blocks": t_, "years_positive": v["years_positive"]}
    act = (S["book_net"] - S["base_net"])[vmask]
    out["kill_line_if_registered_126_sessions"] = RT.kill_line(float(act.std()), 6.0)
    out["written_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _write(OUT / f"revision_tilt_VALIDATE_{tag}.json", out)
    say(json.dumps({"verdict": verdict, **out["verdict_inputs"]}))
    return 0


def _win(S: pd.DataFrame, lo: str, hi: str) -> np.ndarray:
    hold = pd.DatetimeIndex(S.index) + pd.offsets.BDay(1)
    return np.asarray((hold >= pd.Timestamp(lo)) & (hold <= pd.Timestamp(hi)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", required=True, choices=["inputs", "declare", "design", "validate"])
    ap.add_argument("--tag", required=True)
    ap.add_argument("--profile", default="top500", choices=sorted(PROFILES),
                    help="top500 = the original experiment (default, unchanged); mid501_1500 = ranks 501-1500")
    a = ap.parse_args(argv)
    ACTIVE["profile"] = a.profile
    if not _mem_ok():
        say("REFUSED: under 2 GB free memory")
        return 3
    return {"inputs": part_inputs, "declare": part_declare, "design": part_design,
            "validate": part_validate}[a.part](a.tag)


if __name__ == "__main__":
    raise SystemExit(main())
