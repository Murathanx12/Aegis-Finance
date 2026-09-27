"""Score the three FINRA short-sale-volume rules (+ their controls) once, on real data.

    python -m scripts.finra_short_volume_rules            # bars-built SPY/IWM legs, no network

PRODUCT_EXPERIMENT. Runs the rules through the SAME machinery as the nightly
factory (`night_backtest_factory.build_panel` -> `strategy_library.run_strategy`
with band costs ON -> `strategy_library.evaluate`), restricted to the rules of
family `short_sale_flow` plus three reference rows (mom_12_1, short_covering,
random_1). No network at all: the SPY and IWM legs are built from the
survivorship-free bars (`spy_leg(network=False)`), the stamp says so.

The receipt `finra_short_volume_rules_<run id>.json` (under
`<OPTIMUS>/strategy_library/finra/`) carries, per rule at its primary k:
by-year (keyed on the HOLD month), leave-one-year-out, the cost rate paid,
coverage (names/dates with a non-null column), SE and MDE beside every mean,
the SPY + (IWM-SPY) regression, and ONE verdict from
{ALPHA_DETECTED, CANNOT_DISTINGUISH, BETA_EXPLAINS}.

VERDICT RULE (written before the first score, 2026-09-27):
  months = decision months in which the rule held names (FINRA-covered months)
  active = net - SPY;  SE = sd/sqrt(n) (monthly, non-overlapping: hold = 1 month)
  MDE    = 2.8 x SE  (80% power, two-sided 5%)
  alpha  = intercept of net - SPY on [SPY, IWM - SPY] (HAC-free OLS; n small)
  ALPHA_DETECTED  alpha t >= 2 AND leave-one-year-out worst mean active > 0
                  AND mean net minus the random panel > 0
  BETA_EXPLAINS   |active t| >= 2 but |alpha t| < 2 (the exposure carries it)
  CANNOT_DISTINGUISH  everything else (incl. n < 24 months)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                                  # noqa: E402
from backend.services import strategy_library as SL                 # noqa: E402,I001
from backend.services import strategy_library_ext as EXT            # noqa: E402
from backend.services import finra_short_volume as FSV              # noqa: E402
from scripts import night_backtest_factory as NF                    # noqa: E402
from scripts.night_checkpoint import atomic_write_json              # noqa: E402

REFERENCE_RULES = ("mom_12_1", "short_covering", "random_1")
MIN_MONTHS = 24
MDE_MULT = 2.8


def _stats(x: pd.Series) -> dict:
    x = x.dropna()
    n = int(len(x))
    if n < 2:
        return {"n": n, "mean": float(x.mean()) if n else None, "se": None, "t": None, "mde": None}
    m, sd = float(x.mean()), float(x.std(ddof=1))
    se = sd / math.sqrt(n)
    return {"n": n, "mean": m, "se": se, "t": (m / se) if se > 0 else None, "mde": MDE_MULT * se}


def _ols_alpha(y: pd.Series, X: pd.DataFrame) -> dict:
    d = pd.concat([y.rename("y"), X], axis=1).dropna()
    n = len(d)
    if n < 12:
        return {"n": n, "status": "TOO_FEW_MONTHS"}
    A = np.column_stack([np.ones(n), d[X.columns].to_numpy(float)])
    yy = d["y"].to_numpy(float)
    beta, *_ = np.linalg.lstsq(A, yy, rcond=None)
    resid = yy - A @ beta
    dof = n - A.shape[1]
    s2 = float(resid @ resid) / dof
    cov = s2 * np.linalg.inv(A.T @ A)
    se = np.sqrt(np.diag(cov))
    names = ["alpha", *X.columns]
    return {"n": n, "coef": {k: float(b) for k, b in zip(names, beta)},
            "se": {k: float(s) for k, s in zip(names, se)},
            "t": {k: float(b / s) if s > 0 else None for k, b, s in zip(names, beta, se)},
            "alpha_mde": MDE_MULT * float(se[0])}


def _hold_year(d: pd.Series) -> pd.Series:
    # decision at month-end t, money held over the NEXT month
    return (pd.to_datetime(d) + pd.Timedelta(days=1)).dt.year


def score_rule(rule, m: pd.DataFrame, spy: pd.Series, iwm, rp, keep=None) -> dict:
    """Score one primary cell. `keep`: the decision dates to score. A FINRA rule is
    scored ONLY on the months it REBALANCED (hold = 1 month, so every month with
    >= k scored names): `run_strategy` carries the old book through a month with
    fewer than k candidates, and a book carried through a FINRA coverage gap is
    a stale book, not the rule."""
    f = m.set_index("date").sort_index()
    held = f[f["n_held"].fillna(0) > 0]
    if keep is not None:
        held = held[held.index.isin(keep)]
    net = held["net"].astype(float)
    spy_ = spy.reindex(net.index)
    act = (net - spy_).dropna()
    out: dict = {"id": rule.id, "control": bool(rule.control), "k": int(rule.k),
                 "n_months_held": int(len(held)),
                 "first_month": str(held.index.min().date()) if len(held) else None,
                 "last_month": str(held.index.max().date()) if len(held) else None,
                 "net": _stats(net), "active_vs_spy": _stats(act),
                 "mean_cost_per_month": _stats(held["cost"].astype(float)),
                 "mean_names_held": float(held["n_held"].mean()) if len(held) else None}
    if isinstance(rp, pd.Series):
        out["active_vs_random_panel"] = _stats((net - rp.reindex(net.index)).dropna())
    else:
        out["active_vs_random_panel"] = {"status": str(rp)}
    yrs = _hold_year(pd.Series(act.index, index=act.index))
    out["by_year_hold"] = {int(y): _stats(act[yrs == y]) for y in sorted(set(yrs))}
    loo = {}
    for y in sorted(set(yrs)):
        loo[int(y)] = _stats(act[yrs != y])["mean"]
    out["leave_one_year_out_mean_active"] = loo
    if loo:
        wy = min(loo, key=lambda k: loo[k] if loo[k] is not None else 9e9)
        out["loo_worst"] = {"dropped_year": wy, "mean_active": loo[wy]}
    if isinstance(iwm, pd.Series):
        X = pd.DataFrame({"spy": spy_, "iwm_minus_spy": iwm.reindex(net.index) - spy_})
        out["regression_net_minus_spy_on_spy_iwm"] = _ols_alpha(net - spy_, X)
    else:
        out["regression_net_minus_spy_on_spy_iwm"] = {"status": str(iwm)}
    out["verdict"], out["verdict_why"] = verdict(out)
    return out


def verdict(r: dict) -> tuple[str, str]:
    a = r["active_vs_spy"]
    if a["n"] < MIN_MONTHS or a["t"] is None:
        return "CANNOT_DISTINGUISH", f"only {a['n']} months (< {MIN_MONTHS})"
    reg = r.get("regression_net_minus_spy_on_spy_iwm") or {}
    at = (reg.get("t") or {}).get("alpha")
    loo = (r.get("loo_worst") or {}).get("mean_active")
    rpm = (r.get("active_vs_random_panel") or {}).get("mean")
    if at is not None and at >= 2 and loo is not None and loo > 0 and rpm is not None and rpm > 0:
        return "ALPHA_DETECTED", f"alpha t {at:.2f}, LOO worst {loo:+.4f}, vs random panel {rpm:+.4f}"
    if abs(a["t"]) >= 2 and (at is None or abs(at) < 2):
        return "BETA_EXPLAINS", f"active t {a['t']:.2f} but alpha t {at if at is None else round(at, 2)}"
    return "CANNOT_DISTINGUISH", (f"active mean {a['mean']:+.4f} (SE {a['se']:.4f}, MDE {a['mde']:.4f}, "
                                  f"t {a['t']:.2f}); alpha t {None if at is None else round(at, 2)}")


def coverage(panel: pd.DataFrame) -> dict:
    me = panel["is_month_end"].fillna(False).astype(bool)
    el = me & panel["eligible"].fillna(False).astype(bool) if "eligible" in panel.columns else me
    out = {}
    for c in ("short_vol_ratio_21", "short_vol_ratio_z", "short_vol_ratio_chg_21"):
        ok = el & panel[c].notna()
        d = pd.to_datetime(panel.loc[ok, "date"])
        out[c] = {"eligible_month_end_rows_non_null": int(ok.sum()),
                  "eligible_month_end_rows": int(el.sum()),
                  "names_non_null": int(panel.loc[ok, "symbol"].nunique()),
                  "dates_non_null": int(d.nunique()),
                  "first": str(d.min().date()) if len(d) else None,
                  "last": str(d.max().date()) if len(d) else None,
                  "median_names_per_date": float(ok.groupby(panel["date"]).sum()[lambda s: s > 0].median())
                  if ok.any() else 0.0}
    return out


def main(argv=None) -> int:
    from backend.services import xs_ranker as XR
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2017-06-01",
                    help="bars from here (12-1 momentum needs ~1y before FINRA's 2018-08 start)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-symbols", type=int, default=0, help="smoke only")
    a = ap.parse_args(argv)
    t0 = time.time()
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    out = Path(a.out) if a.out else Path(_cfg.OPTIMUS_LEDGER_DIR) / _cfg.STRATEGY_LIB_SUBDIR / "finra"
    out.mkdir(parents=True, exist_ok=True)
    man = json.loads((FSV.default_root() / "manifest.json").read_text(encoding="utf-8"))
    paths = XR.survivorship_free_paths()
    W = NF.load_wide(paths, start=a.start, max_symbols=a.max_symbols)
    print(f"wide {W['close'].shape} in {time.time()-t0:.0f}s", flush=True)
    panel = NF.build_panel(W, delist_return=float(_cfg.STRATEGY_LIB_DELIST_RETURN))
    for c_ in ("high", "low", "volume"):
        W.pop(c_, None)
    print(f"panel {len(panel):,} rows in {time.time()-t0:.0f}s", flush=True)
    panel, sv_info = EXT.attach_short_volume(panel, W)
    print(f"short volume attached: {sv_info.get('non_nan')} ({time.time()-t0:.0f}s)", flush=True)
    try:
        panel, si_info = NF.attach_short_interest(panel)
    except Exception as e:                                     # noqa: BLE001 -- named
        si_info = {"status": "REFUSED", "why": f"{type(e).__name__}: {e}"}
    panel["tiebreak"] = SL._tiebreak(panel)
    spy, spy_meta = NF.spy_leg(panel, W, network=False)
    try:
        iwm, iwm_meta = NF.iwm_leg(panel, W, network=False)
    except SL.BenchmarkMissing as e:
        iwm, iwm_meta = str(e), {"status": f"REFUSED: {e}"}
    try:
        rp, rp_meta = NF.random_panel_leg(panel)
    except Exception as e:                                     # noqa: BLE001 -- named
        rp, rp_meta = f"RANDOM_PANEL_MISSING: {type(e).__name__}: {e}", {"status": "REFUSED"}
    rules = [r for r in EXT.FINRA_STRATEGIES] + [SL.rule_by_id(x) for x in REFERENCE_RULES]
    results, evals, frames = {}, {}, {}
    for rule in rules:
        sink: list = []
        ev = NF.evaluate_rule(panel, spy, rule, since=_cfg.STRATEGY_LIB_SINCE,
                              benches={"iwm": iwm, "random_panel": rp}, sink=sink)
        prim = [s for s in sink if s[1] == int(rule.k)]
        if ev.get("status") != "OK" or not prim:
            results[rule.id] = {"id": rule.id, "status": "REFUSED", "why": ev.get("why")}
            continue
        frames[rule.id] = prim[0][3]
        c = ev["cells"].get(str(rule.k)) or {}
        evals[rule.id] = {k: c.get(k) for k in ("turnover_annual", "cost_bps_paid",
                                                 "mean_cost_bps_per_month", "by_year_hold",
                                                 "loo_worst_mean_active_hold", "dsr",
                                                 "t_active_horizon_blocks", "n_blocks_horizon",
                                                 "max_dd", "n_delisting_fills")}
        print(f"  ran {rule.id} ({time.time()-t0:.0f}s)", flush=True)
    # every row is scored on the SAME months: a FINRA rule on the months it
    # rebalanced; a reference row on the union of those months (like for like)
    finra_ids = {r.id for r in EXT.FINRA_STRATEGIES}
    reb = {rid: set(pd.to_datetime(f.loc[f["rebalanced"].astype(bool) & (f["n_held"] > 0), "date"]))
           for rid, f in frames.items() if rid in finra_ids}
    union = set().union(*reb.values()) if reb else set()
    for rule in rules:
        if rule.id not in frames:
            continue
        keep = reb.get(rule.id) if rule.id in finra_ids else union
        results[rule.id] = score_rule(rule, frames[rule.id], spy, iwm, rp, keep=keep)
        r = results[rule.id]
        a_ = r["active_vs_spy"]
        print(f"  {rule.id:32s} {r['verdict']:18s} n={a_['n']} active={a_['mean']} "
              f"se={a_['se']} t={a_['t']}", flush=True)
    scored = sorted(union)
    finra_months = {"n_months_union": len(scored),
                    "first": str(scored[0].date()) if scored else None,
                    "last": str(scored[-1].date()) if scored else None,
                    "per_rule_n_rebalanced": {k: len(v) for k, v in reb.items()},
                    "gaps_note": ("months with fewer than k scored names are EXCLUDED, not "
                                  "carried: see score_rule")}
    rec = {"schema": "finra_short_volume_rules/1", "run_id": run_id, "licence": "PRODUCT_EXPERIMENT",
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "registered_utc": EXT.REGISTERED_FINRA, "llm_spend_usd": 0.0, "network": "none",
           "pit_rule": FSV.PIT_RULE,
           "finra_manifest": {k: man.get(k) for k in ("rows", "dates", "first", "last",
                                                       "not_published_weekdays", "written_utc")},
           "coverage": coverage(panel), "attach_info": sv_info, "short_interest": si_info,
           "cost_model": {"round_trip_bps_by_band": SL._band_costs(),
                          "applied": "band round trip on the weight actually traded, every rebalance"},
           "benchmarks": {"spy": {k: v for k, v in spy_meta.items() if k != "market_benchmark"},
                          "iwm": iwm_meta, "random_panel": rp_meta},
           "verdict_rule": __doc__.split("VERDICT RULE", 1)[1].strip(),
           "panel": {"rows": int(len(panel)), "symbols": int(panel["symbol"].nunique()),
                     "first": str(panel["date"].min().date()), "last": str(panel["date"].max().date()),
                     "fingerprint": NF.panel_fingerprint(panel)},
           "scored_window_start": finra_months,
           "results": results, "factory_evaluate_primary_cell": evals,
           "elapsed_s": round(time.time() - t0, 1)}
    p = out / f"finra_short_volume_rules_{run_id}.json"
    atomic_write_json(p, NF._round(rec), indent=1)
    print(f"-> {p}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
