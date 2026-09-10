"""N1H5_prereg_read -- the ONE historical read TRIAL-H5 registers.

`docs/TRIALS/TRIAL-H5-event-learner-five-session.md` (registered 2026-09-09,
commit 9bc271b, annotated da14d39) permits exactly one computation on the
2004-2024 purged walk-forward, by a job with this name, after that commit. This
file is that job. It runs the FROZEN configuration and nothing else:

    hold 5 sessions; entry at the close of session +1; feature set `all`;
    LightGBM 400 trees with N1's hyper-parameters; purged walk-forward by year
    with an embargo of 5 sessions from first test year 2004; PIT rank window 63
    sessions, pool >= 200; top and bottom deciles; 25 bps a side;
    borrow 100 bps/yr on the short leg; floors $3m (report) and $10m (DECIDE);
    seeds 0-12, reported as the seed-median.

The primary metric -- the only deciding one -- is `learner_minus_control`: the
learner's long-short minus the long-short of the IDENTICAL pipeline trained and
traded on the +40-session placebo tape, beta-matched, on monthly date blocks,
at the $10m floor with borrow charged.

No metric substitution. The +44.5%/yr pooled raw line the search printed is a
SECONDARY number here and is reported as such. This job places nothing, seals
nothing, and registers no successor.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.night_factory_jobs import (          # noqa: E402  the frozen N1 machinery, unchanged
    COST_BPS,
    Tape,
    _diff_book,
    _events,
    _load_tape,
    _n1_features,
    _select,
    _select_bottom,
    _walk_forward,
    calendar_book,
    fwd_market_adjusted,
    pit_rank,
)

RUN_DATE = "2026-09-08"
OUT = REPO / "backend" / "data" / "optimus" / f"night_factory_{RUN_DATE}"
OUT.mkdir(parents=True, exist_ok=True)
TRIAL = "TRIAL-H5-event-learner-five-session"

HOLD = 5
FIRST_TEST_YEAR = 2004
SEEDS = tuple(range(13))
BORROW_BPS_YR = 100.0
FLOOR_DECIDE = 10_000_000.0
FLOOR_REPORT = 3_000_000.0
NW_LAG = 4
ERAS = {"2004-2007": (2004, 2007), "2008-2015": (2008, 2015), "2016-2024": (2016, 2024)}
FEATS_ALL = ["reaction", "z_reaction", "sue", "sd60", "mom_12_1", "vsurge",
             "log_dv21", "log_cap", "prc_e", "gap_prev"]

ADOPT = {"seed_median_ann_pct": 31.0, "t_nw": 2.8, "max_drawdown": -0.45}
REJECT = {"seed_median_ann_pct": 4.0, "t_nw": 1.5, "control_seed_median_ann_pct": 4.0,
          "floor_removes_more_than": 0.5}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _r(v, nd=4):
    try:
        return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), nd)
    except Exception:  # noqa: BLE001
        return None


def _nw_t(x: np.ndarray, lag: int = NW_LAG) -> float | None:
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 12:
        return None
    u = x - x.mean()
    s = float(np.dot(u, u)) / n
    for L in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - L / (lag + 1.0)) * float(np.dot(u[L:], u[:-L])) / n
    se = math.sqrt(max(s, 1e-18) / n)
    return float(x.mean() / se) if se > 0 else None


def _max_dd(m: np.ndarray) -> float:
    eq = np.cumprod(1.0 + np.asarray(m, dtype="float64"))
    return float((eq / np.maximum.accumulate(eq) - 1.0).min()) if len(eq) else 0.0


def monthly(tape: Tape, bk: dict, borrow_bps_yr: float) -> pd.DataFrame:
    """Daily long-short -> monthly, with borrow charged on the sessions the book
    is open. A self-financing long-short posts short notional equal to its long,
    so one borrow leg is the whole charge."""
    daily = np.asarray(bk["net"], dtype="float64").copy()
    live = np.asarray(bk["n_open"], dtype="float64") > 0
    daily = daily - live * (borrow_bps_yr / 10_000.0 / 252.0)
    f = pd.DataFrame({"month": tape.month_of, "net": daily, "mkt": tape.mkt_vw, "live": live})
    f = f[f["month"] >= f.loc[live, "month"].min()] if live.any() else f
    g = f.groupby("month", sort=True)
    out = pd.DataFrame({"net": g["net"].apply(lambda x: float(np.prod(1 + x.to_numpy()) - 1.0)),
                        "mkt": g["mkt"].apply(lambda x: float(np.prod(1 + x.to_numpy()) - 1.0)),
                        "live": g["live"].sum()})
    return out[out["live"] > 0]


def beta_matched(m: pd.DataFrame) -> tuple[np.ndarray, float]:
    y, x = m["net"].to_numpy(dtype="float64"), m["mkt"].to_numpy(dtype="float64")
    beta = float(np.polyfit(x, y, 1)[0]) if np.std(x) > 0 else 1.0
    return y - beta * x, beta


def cell(m: pd.DataFrame, label: str) -> dict:
    ex, beta = beta_matched(m)
    y = m["net"].to_numpy(dtype="float64")
    eras = {}
    for name, (a, b) in ERAS.items():
        mask = np.array([a <= int(mm[:4]) <= b for mm in m.index])
        if mask.sum() >= 12:
            eras[name] = {"months": int(mask.sum()), "ann_pct": _r(float(ex[mask].mean()) * 12 * 100, 3),
                          "t": _r(_nw_t(ex[mask]), 3), "sign": int(np.sign(ex[mask].mean()))}
    return {"label": label, "months": int(len(m)), "beta": _r(beta),
            "beta_matched_ann_pct": _r(float(ex.mean()) * 12 * 100, 3), "t_nw": _r(_nw_t(ex), 3),
            "max_drawdown": _r(_max_dd(y)), "ann_vol_pct": _r(float(np.std(y, ddof=1)) * math.sqrt(12) * 100, 2),
            "terminal_wealth_net": _r(float(np.prod(1 + y))), "eras": eras,
            "_ex": ex, "_idx": [str(v) for v in m.index]}


def diff_series(a: dict, b: dict) -> tuple[np.ndarray, list[str]]:
    """learner MINUS control on the months both were live."""
    da = dict(zip(a["_idx"], a["_ex"]))
    db = dict(zip(b["_idx"], b["_ex"]))
    idx = [m for m in a["_idx"] if m in db]
    return np.array([da[m] - db[m] for m in idx]), idx


def N1H5_prereg_read(seeds=SEEDS, smoke: bool = False) -> dict:
    t0 = time.time()
    tape, years = _load_tape(smoke)
    ann, plc = _events(tape, years, smoke)
    seeds = tuple(seeds) if not smoke else (0,)

    per_seed: dict[str, dict] = {}
    for tag, src in (("learner", ann), ("control", plc)):
        d = _n1_features(src)
        d["fwd"] = fwd_market_adjusted(tape, d, HOLD)
        d = d[np.isfinite(d["fwd"].to_numpy())].copy()
        feats = [f for f in FEATS_ALL if f in d.columns]
        for s in seeds:
            pred, folds = _walk_forward(d, feats, "fwd", tape, HOLD, s, first_test_year=FIRST_TEST_YEAR)
            e = d.assign(pred=pred)
            e = e[np.isfinite(e["pred"].to_numpy())].copy()
            e["prank"] = pit_rank(e, col="pred")
            for fname, floor in (("floor_10m", FLOOR_DECIDE), ("floor_3m", FLOOR_REPORT)):
                top = calendar_book(tape, _select(e, 0.10, floor=floor, col="prank"), HOLD, cost_bps=COST_BPS)
                bot = calendar_book(tape, _select_bottom(e, 0.10, floor=floor, col="prank"), HOLD, cost_bps=COST_BPS)
                ls = _diff_book(top, bot)
                per_seed[f"{tag}|{fname}|s{s}"] = cell(monthly(tape, ls, BORROW_BPS_YR), f"{tag}|{fname}|s{s}")
            print(f"    {tag} seed {s}: {len(folds)} folds, $10m "
                  f"{per_seed[f'{tag}|floor_10m|s{s}']['beta_matched_ann_pct']}%/yr "
                  f"t {per_seed[f'{tag}|floor_10m|s{s}']['t_nw']}  [{time.time() - t0:.0f}s]", flush=True)

    result: dict[str, dict] = {}
    for fname in ("floor_10m", "floor_3m"):
        rows, series = [], []
        for s in seeds:
            a, b = per_seed[f"learner|{fname}|s{s}"], per_seed[f"control|{fname}|s{s}"]
            d, idx = diff_series(a, b)
            rows.append({"seed": s, "learner_ann_pct": a["beta_matched_ann_pct"],
                         "control_ann_pct": b["beta_matched_ann_pct"],
                         "diff_ann_pct": _r(float(d.mean()) * 12 * 100, 3), "diff_t": _r(_nw_t(d), 3),
                         "months": len(idx), "learner_max_dd": a["max_drawdown"]})
            series.append(pd.Series(d, index=idx))
        # the seed-median monthly series: one number per month, so the t is
        # computed on the same object the median summarises
        S = pd.concat(series, axis=1).dropna()
        med = S.median(axis=1).to_numpy()
        med_idx = [str(v) for v in S.index]
        eras = {}
        for name, (a2, b2) in ERAS.items():
            mask = np.array([a2 <= int(mm[:4]) <= b2 for mm in med_idx])
            if mask.sum() >= 12:
                eras[name] = {"months": int(mask.sum()), "ann_pct": _r(float(med[mask].mean()) * 12 * 100, 3),
                              "t": _r(_nw_t(med[mask]), 3), "sign": int(np.sign(med[mask].mean()))}
        result[fname] = {
            "per_seed": rows,
            "seed_median_of_per_seed_ann_pct": _r(float(np.median([r["diff_ann_pct"] for r in rows])), 3),
            "seed_median_series_ann_pct": _r(float(med.mean()) * 12 * 100, 3),
            "seed_median_series_t_nw": _r(_nw_t(med), 3),
            "months": len(med_idx), "eras": eras,
            "learner_seed_median_ann_pct": _r(float(np.median([r["learner_ann_pct"] for r in rows])), 3),
            "control_seed_median_ann_pct": _r(float(np.median([r["control_ann_pct"] for r in rows])), 3),
            "learner_seed_median_max_dd": _r(float(np.median([r["learner_max_dd"] for r in rows])), 4),
        }

    p, rep = result["floor_10m"], result["floor_3m"]
    primary = p["seed_median_series_ann_pct"]
    t = p["seed_median_series_t_nw"]
    dd = p["learner_seed_median_max_dd"]
    ctl = p["control_seed_median_ann_pct"]
    signs = [v["sign"] for v in p["eras"].values()]
    # "the $10m floor removes more than half of the $3m-floor excess" is a
    # RATIO, and a ratio with a non-positive denominator is not a fraction of
    # anything: a negative $3m excess with a positive $10m one gives a negative
    # ratio, which would trip the reject clause for the opposite reason it
    # exists. The clause is evaluated only where it is defined, and reported as
    # undefined otherwise -- a check that could not run is not a check that failed.
    base = rep["seed_median_series_ann_pct"]
    floor_kept = (primary / base) if (base is not None and base > 0 and primary is not None) else None

    checks = {
        "adopt_effect_ge_31": bool((primary or -99) >= ADOPT["seed_median_ann_pct"]),
        "adopt_t_ge_2.8": bool((t or -99) >= ADOPT["t_nw"]),
        "adopt_same_sign_in_every_era": bool(signs and all(x > 0 for x in signs)),
        "adopt_max_dd_ge_-0.45": bool((dd or -9) >= ADOPT["max_drawdown"]),
        "adopt_RW2_excess_ge_0.15_in_every_era": False,
        "reject_effect_lt_4": bool((primary or -99) < REJECT["seed_median_ann_pct"]),
        "reject_t_lt_1.5": bool((t or -99) < REJECT["t_nw"]),
        "reject_control_gt_4": bool((ctl or -99) > REJECT["control_seed_median_ann_pct"]),
        "reject_10m_floor_removes_over_half": bool(floor_kept is not None and floor_kept < REJECT["floor_removes_more_than"]),
    }
    rejected = [k for k, v in checks.items() if k.startswith("reject_") and v]
    adopt_failed = [k for k, v in checks.items() if k.startswith("adopt_") and not v]

    if rejected:
        verdict = (f"REJECTED: {', '.join(rejected)}. Primary (learner minus control, $10m floor, "
                   f"{BORROW_BPS_YR:.0f} bps borrow, seed-median): {primary}%/yr t {t}. "
                   f"The trial closes and H5|all goes to NEGATIVE_RESULTS.md; the same instrument is not re-run.")
    elif not adopt_failed:
        verdict = f"ADOPT (historical screen passed): {primary}%/yr t {t}; the forward leg may start"
    else:
        verdict = (f"CONDITIONAL, NOT ADOPTED: primary {primary}%/yr t {t}; the adopt clauses that fail are "
                   f"{adopt_failed}. Reported and sent to the forward leg unadopted, per the registration.")

    return {
        "job": "N1H5_prereg_read", "trial": TRIAL, "licence": "RESEARCH_CLAIM candidate",
        "llm_spend_usd": 0.0, "READ_ONCE": True,
        "registered_by": "docs/TRIALS/TRIAL-H5-event-learner-five-session.md (commit 9bc271b, annotated da14d39)",
        "frozen_configuration": {
            "hold_sessions": HOLD, "entry": "close of session +1", "featureset": "all", "features": FEATS_ALL,
            "model": "LightGBM 400 trees, N1 hyper-parameters", "walk_forward": "purged by year, embargo = 5 sessions",
            "first_test_year": FIRST_TEST_YEAR, "pit_rank_window": 63, "min_pool": 200,
            "deciles": "top and bottom 10% of the PIT-ranked prediction",
            "cost_bps_per_side": COST_BPS, "borrow_bps_per_year": BORROW_BPS_YR,
            "floor_decide_usd": FLOOR_DECIDE, "floor_report_usd": FLOOR_REPORT, "seeds": list(seeds)},
        "PRIMARY_learner_minus_control_at_10m_floor": {
            "seed_median_series_ann_pct": primary, "t_nw": t, "months": p["months"],
            "eras": p["eras"], "learner": p["learner_seed_median_ann_pct"], "control": ctl,
            "learner_max_drawdown": dd,
            "seed_median_of_per_seed_estimates_ann_pct": p["seed_median_of_per_seed_ann_pct"]},
        "SECONDARY_at_3m_floor": rep,
        "share_of_3m_excess_kept_at_10m": _r(floor_kept, 3),
        "share_of_3m_excess_kept_at_10m_note": (
            None if floor_kept is not None else
            f"undefined: the $3m-floor excess is {base}%/yr, so 'kept a share of it' has no meaning; "
            "the reject clause that reads this ratio is recorded as not evaluated, not as passed"),
        "decision_checks": checks,
        "RW2_clause": ("evaluated OUTSIDE this job from RW2_event_windows_run01.json: the excess win rate over "
                       "the control is 0.44 in 1999-2007 and 0.46 in 2016-2024 at the $10m floor, so the "
                       "registered clause 'RW2 excess >= +0.15 in every start era' already fails"),
        "headline": (f"TRIAL-H5 single registered read: learner minus control at the $10m floor with "
                     f"{BORROW_BPS_YR:.0f} bps borrow, seed-median over {len(seeds)} seeds = {primary}%/yr "
                     f"t {t} on {p['months']} monthly blocks (learner {p['learner_seed_median_ann_pct']}, "
                     f"control {ctl}, max DD {dd}); at the $3m floor {rep['seed_median_series_ann_pct']}%/yr "
                     f"t {rep['seed_median_series_t_nw']}"),
        "verdict": verdict, "family_max_p": None,
        "elapsed_s": round(time.time() - t0, 1), "written_utc": _now(),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--run", type=int, default=1)
    a = ap.parse_args(argv)
    p = N1H5_prereg_read(smoke=a.smoke)
    p["run"] = a.run
    out = Path(a.out) if a.out else OUT / f"N1H5_prereg_read_run{a.run:02d}{'_smoke' if a.smoke else ''}.json"
    out.write_text(json.dumps(p, indent=1, default=str), encoding="utf-8")
    print(f"\nN1H5_prereg_read: {p['headline']}\n  verdict: {p['verdict']}\n  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
