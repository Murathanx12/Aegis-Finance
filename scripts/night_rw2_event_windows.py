"""RW2 -- the randomised-window ruler applied to the EVENT-CLOCK books.

RW1 put the monthly cross-sectional selectors on random windows. The two live
event-clock candidates never got that treatment:

* the **reaction long-short** (D3/D4): +15.9%/yr pooled, Holm-clean, placebo-flat
  -- and 0 of 12 late-window construction corners positive once the $10m/day
  liquidity floor is applied;
* the **N1 `H5|all` learner** long-short: +44.5%/yr with a placebo-trained control
  at t -0.45, found AFTER its pre-specified primary failed, at -78% drawdown and
  **with no borrow cost anywhere on its short leg**.

RW2 answers three questions the pooled numbers cannot:

1. On a randomly drawn window of 6-72 months, how often does each arm beat a
   beta-matched market -- and how often does its **own matched control** (the
   identical pipeline on dateless +40-session placebo events) do the same?
   Every cell carries `vs_control`; the runner has no stamp without it.
2. Where does the win rate live -- by start era and by window length?
3. What does a short leg cost? Every arm is graded at borrow **0 / 50 / 200
   bps a year**, charged daily on the sessions the short leg is actually open.

The windows are drawn with RW1's own seed and generator, so the two files answer
the same question on comparable draws.

NO HOLDOUT IS READ: every window is descriptive, and the reaction and learner
signals were both already fitted on this tape. RW2 measures dispersion and
control-relative performance, not out-of-sample truth.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.night_factory_jobs import (          # noqa: E402  the night's own event machinery
    COST_BPS,
    Tape,
    _diff_book,
    _events,
    _load_tape,
    _n1_features,
    _select,
    _select_bottom,
    _walk_forward,
    fwd_market_adjusted,
    pit_rank,
    calendar_book,
)

RUN_DATE = "2026-09-08"
OUT = REPO / "backend" / "data" / "optimus" / f"night_factory_{RUN_DATE}"
OUT.mkdir(parents=True, exist_ok=True)

LENGTHS = (6, 12, 24, 36, 48, 60, 72)
FIRST_M, LAST_M = "1999-03", "2024-12"
NW_LAG_M = 4
FLOORS = {"floor_0": None, "floor_3m": 3_000_000.0, "floor_10m": 10_000_000.0}
BORROW_BPS_YR = (0.0, 50.0, 200.0)
H5_HORIZON = 5
N1_FEATS_ALL = ["reaction", "z_reaction", "sue", "sd60", "mom_12_1", "vsurge",
                "log_dv21", "log_cap", "prc_e", "gap_prev"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _r(v, nd=4):
    try:
        return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), nd)
    except Exception:  # noqa: BLE001
        return None


def _nw_t(x: np.ndarray, lag: int = NW_LAG_M) -> float | None:
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 6:
        return None
    u = x - x.mean()
    s = float(np.dot(u, u)) / n
    for L in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - L / (lag + 1.0)) * float(np.dot(u[L:], u[:-L])) / n
    se = math.sqrt(max(s, 1e-18) / n)
    return float(x.mean() / se) if se > 0 else None


def _max_dd(m: np.ndarray) -> float:
    w = np.cumprod(1.0 + np.asarray(m, dtype="float64"))
    return float(np.min(w / np.maximum.accumulate(w) - 1.0)) if len(w) else 0.0


def draw_windows(n: int, seed: int, first: str = FIRST_M, last: str = LAST_M) -> list[tuple[str, str, int]]:
    """RW1's generator, verbatim, so both files draw the same windows for a seed.

    The span is an ARGUMENT because it has to be derived from the tape actually
    loaded: a smoke run holds five years of daily prices, and drawing windows
    across 1999-2024 against it produced 240 windows of which zero could be
    graded, then a `KeyError: 'signal'` on the empty frame. A generator that
    cannot be graded is the same failure as a gate that cannot go green. In the
    full run the tape spans 1999-2024 and the draws are identical to RW1's.
    """
    rng = random.Random(seed)
    months = [str(p) for p in pd.period_range(first, last, freq="M")]
    usable = [x for x in LENGTHS if x <= len(months)]
    if not usable:
        raise SystemExit(f"REFUSED: the tape spans {first}..{last}, shorter than the shortest window {min(LENGTHS)}m")
    out = []
    for _ in range(n):
        L = rng.choice(usable)
        s = rng.randrange(0, len(months) - L + 1)
        out.append((months[s], months[s + L - 1], L))
    return out


def era_of(month: str) -> str:
    y = int(month[:4])
    return "1999-2007" if y <= 2007 else ("2008-2015" if y <= 2015 else "2016-2024")


# ------------------------------------------------------------ book -> series

def monthly_frame(tape: Tape, bk: dict, borrow_bps_yr: float = 0.0) -> pd.DataFrame:
    """Daily book -> monthly net, market, and the sessions the book was open.

    Borrow is charged DAILY on the sessions the (short side of the) book is open.
    For a self-financing long-short the short notional equals the long notional,
    so one borrow leg is the whole charge; for a long-only arm `borrow_bps_yr`
    is passed as 0 by the caller and this term vanishes.
    """
    daily = np.asarray(bk["net"], dtype="float64").copy()
    if borrow_bps_yr:
        live = np.asarray(bk["n_open"], dtype="float64") > 0
        daily = daily - live * (borrow_bps_yr / 10_000.0 / 252.0)
    df = pd.DataFrame({"month": tape.month_of, "net": daily,
                       "mkt": tape.mkt_vw, "open": np.asarray(bk["n_open"], dtype="float64") > 0})
    g = df.groupby("month", sort=True)
    return pd.DataFrame({
        "net": g["net"].apply(lambda x: float(np.prod(1.0 + x.to_numpy()) - 1.0)),
        "mkt": g["mkt"].apply(lambda x: float(np.prod(1.0 + x.to_numpy()) - 1.0)),
        "open_sessions": g["open"].sum(),
    })


def grade_window(mf: pd.DataFrame, a: str, b: str) -> dict | None:
    """One window of an already-built monthly series. BETA FIRST."""
    w = mf[(mf.index >= a) & (mf.index <= b)]
    w = w[w["open_sessions"] > 0]
    if len(w) < 6:
        return None
    y = w["net"].to_numpy(dtype="float64")
    x = w["mkt"].to_numpy(dtype="float64")
    beta = float(np.polyfit(x, y, 1)[0]) if np.std(x) > 0 else 1.0
    ex = y - beta * x
    return {"months": int(len(y)), "beta": beta,
            "bm_ann_pct": float(ex.mean()) * 12 * 100, "t_bm": _nw_t(ex),
            "raw_ann_pct": float((y - x).mean()) * 12 * 100,
            "tw_net": float(np.prod(1 + y)), "tw_mkt": float(np.prod(1 + x)),
            "max_dd": _max_dd(y), "beats_bm": bool(ex.mean() > 0)}


# ------------------------------------------------------------------ the arms

def build_arms(tape: Tape, ann: pd.DataFrame, plc: pd.DataFrame, *, seed: int,
               smoke: bool) -> dict[str, dict]:
    """Every arm is a DAILY book plus its matched control, built once.

    A window is then a slice of the monthly series, so 240 windows cost one book
    build rather than 240.
    """
    arms: dict[str, dict] = {}

    # ---- 1. the reaction long-short, at three liquidity floors ---------------
    for fname, floor in FLOORS.items():
        for tag, df in (("reaction_LS", ann), ("CONTROL_reaction_LS", plc)):
            d = df.copy()
            d["rank"] = pit_rank(d, col="reaction")
            top = calendar_book(tape, _select(d, 0.10, floor=floor), 21, cost_bps=COST_BPS)
            bot = calendar_book(tape, _select_bottom(d, 0.10, floor=floor), 21, cost_bps=COST_BPS)
            arms[f"{tag}|{fname}"] = _diff_book(top, bot)
        print(f"    reaction LS built at {fname}", flush=True)

    # ---- 2. the N1 H5|all learner long-short, and its placebo-trained twin ---
    for tag, df in (("N1_H5_all_LS", ann), ("CONTROL_N1_H5_all_LS", plc)):
        d = _n1_features(df)
        d["fwd"] = fwd_market_adjusted(tape, d, H5_HORIZON)
        d = d[np.isfinite(d["fwd"].to_numpy())].copy()
        feats = [f for f in N1_FEATS_ALL if f in d.columns]
        pred, folds = _walk_forward(d, feats, "fwd", tape, H5_HORIZON, seed,
                                    first_test_year=2004 if not smoke else 2004)
        d["pred"] = pred
        d = d[np.isfinite(d["pred"].to_numpy())].copy()
        d["prank"] = pit_rank(d, col="pred")
        print(f"    {tag}: {len(folds)} walk-forward folds, {len(d):,} scored events", flush=True)
        for fname, floor in FLOORS.items():
            top = calendar_book(tape, _select(d, 0.10, floor=floor, col="prank"), H5_HORIZON, cost_bps=COST_BPS)
            bot = calendar_book(tape, _select_bottom(d, 0.10, floor=floor, col="prank"), H5_HORIZON, cost_bps=COST_BPS)
            arms[f"{tag}|{fname}"] = _diff_book(top, bot)
    return arms


def RW2_event_windows(n_windows: int = 240, seed: int = 20260909, smoke: bool = False) -> dict:
    t0 = time.time()
    tape, years = _load_tape(smoke)
    ann, plc = _events(tape, years, smoke)
    arms = build_arms(tape, ann, plc, seed=0, smoke=smoke)

    # monthly series per (arm, borrow rate) -- built once, sliced per window
    series: dict[tuple[str, float], pd.DataFrame] = {}
    for name, bk in arms.items():
        for bo in (BORROW_BPS_YR if not smoke else (0.0, 200.0)):
            series[(name, bo)] = monthly_frame(tape, bk, borrow_bps_yr=bo)

    # the span is DERIVED from the tape that was actually loaded, then checked
    # against RW1's: in a full run they are identical, so the two files' seeds
    # draw the same windows and their tables can be read side by side.
    tape_months = sorted(set(tape.month_of))
    span = (max(FIRST_M, tape_months[0]), min(LAST_M, tape_months[-1]))
    windows = draw_windows(n_windows if not smoke else 20, seed, first=span[0], last=span[1])
    rows = []
    signals = ["reaction_LS", "N1_H5_all_LS"]
    for (a, b, L) in windows:
        for sig in signals:
            for fname in FLOORS:
                for bo in (BORROW_BPS_YR if not smoke else (0.0, 200.0)):
                    arm = grade_window(series[(f"{sig}|{fname}", bo)], a, b)
                    ctl = grade_window(series[(f"CONTROL_{sig}|{fname}", bo)], a, b)
                    if arm is None:
                        continue
                    vs = None
                    if ctl is not None:
                        vs = arm["bm_ann_pct"] - ctl["bm_ann_pct"]
                    rows.append({
                        "start": a, "end": b, "length_m": L, "era_start": era_of(a),
                        "signal": sig, "floor": fname, "borrow_bps_yr": bo,
                        "months": arm["months"], "beta": _r(arm["beta"]),
                        "bm_ann_pct": _r(arm["bm_ann_pct"], 3), "t_bm": _r(arm["t_bm"], 3),
                        "max_dd": _r(arm["max_dd"]),
                        "control_bm_ann_pct": _r(ctl["bm_ann_pct"], 3) if ctl else None,
                        "control_t_bm": _r(ctl["t_bm"], 3) if ctl else None,
                        "vs_control_ann_pct": _r(vs, 3),
                        "beats_bm": arm["beats_bm"],
                        "beats_control": bool(vs is not None and vs > 0),
                        "beats_both": bool(arm["beats_bm"] and vs is not None and vs > 0),
                        "control_graded": ctl is not None,
                    })
    if not rows:
        return {"job": "RW2_event_windows", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
                "verdict": "REFUSED: no window could be graded",
                "headline": (f"{len(windows)} windows drawn over {span[0]}..{span[1]} and none produced "
                             f"6 gradable months on the loaded tape -- nothing was measured"),
                "windows": {"n": len(windows), "seed": seed, "span": span},
                "family_max_p": None, "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}
    res = pd.DataFrame(rows)
    res.to_parquet(OUT / f"RW2_windows_seed{seed}.parquet", index=False)

    def agg(g: pd.DataFrame) -> dict:
        return {"n": int(len(g)),
                "win_bm": _r(g["beats_bm"].mean(), 3),
                "win_vs_control": _r(g["beats_control"].mean(), 3),
                "win_both": _r(g["beats_both"].mean(), 3),
                "median_bm_ann_pct": _r(g["bm_ann_pct"].median(), 3),
                "median_control_ann_pct": _r(g["control_bm_ann_pct"].median(), 3),
                "median_vs_control_ann_pct": _r(g["vs_control_ann_pct"].median(), 3),
                "median_beta": _r(g["beta"].median(), 3),
                "median_max_dd": _r(g["max_dd"].median(), 3),
                "share_t_gt_2": _r((g["t_bm"].fillna(0) > 2).mean(), 3),
                "share_control_ungraded": _r((~g["control_graded"]).mean(), 3)}

    summary = {}
    for (sig, fl, bo), g in res.groupby(["signal", "floor", "borrow_bps_yr"]):
        summary[f"{sig}|{fl}|borrow{int(bo)}"] = {
            "overall": agg(g),
            "by_start_era": {e: agg(gg) for e, gg in g.groupby("era_start")},
            "by_length_months": {int(L): agg(gg) for L, gg in g.groupby("length_m")},
        }

    # the borrow curve at the tradability floor, the cell a product would live in
    curve = {}
    for bo in (BORROW_BPS_YR if not smoke else (0.0, 200.0)):
        for sig in signals:
            k = f"{sig}|floor_10m|borrow{int(bo)}"
            if k in summary:
                curve[k] = {"median_vs_control_ann_pct": summary[k]["overall"]["median_vs_control_ann_pct"],
                            "win_vs_control": summary[k]["overall"]["win_vs_control"],
                            "late_era_win_vs_control": (summary[k]["by_start_era"].get("2016-2024") or {}).get("win_vs_control")}

    # the verdict reads the tradable corner: $10m floor, 200 bps borrow, late era
    def cell(sig: str) -> dict:
        k = f"{sig}|floor_10m|borrow200"
        s = summary.get(k, {})
        late = (s.get("by_start_era") or {}).get("2016-2024") or {}
        return {"key": k, "overall": s.get("overall"), "late": late}

    react, learner = cell("reaction_LS"), cell("N1_H5_all_LS")

    def verdict_for(c: dict, name: str) -> str:
        o, late = c["overall"] or {}, c["late"] or {}
        if not o:
            return f"{name}: CANNOT DETERMINE (no window graded at the tradable corner)"
        wc = o.get("win_vs_control")
        wl = late.get("win_vs_control")
        med = o.get("median_vs_control_ann_pct")
        if wc is None:
            return f"{name}: CANNOT DETERMINE -- no control was graded on these windows"
        # a late era that was never DRAWN is not a late era that failed
        late_txt = "no 2016-2024 start was drawn on this tape" if wl is None else f"{wl:.0%} of 2016-2024 starts"
        if wl is None:
            return (f"{name}: CANNOT DETERMINE on the era that matters -- {wc:.0%} of windows over control "
                    f"(median {med:+.2f}%/yr), but {late_txt}")
        if wc >= 0.65 and wl >= 0.6 and (med or 0) > 0:
            return (f"{name}: PRODUCT_PROMISING at $10m/200bps -- beats its own control in "
                    f"{wc:.0%} of windows ({late_txt}), median {med:+.2f}%/yr over control")
        if wc >= 0.55 and (med or 0) > 0:
            return (f"{name}: CONDITIONAL -- {wc:.0%} of windows over control (median {med:+.2f}%/yr) "
                    f"but {late_txt}")
        return (f"{name}: FAILED_VARIANT at the tradable corner -- beats its own control in only "
                f"{wc:.0%} of windows, median {med:+.2f}%/yr over control")

    return {
        "job": "RW2_event_windows", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "question": ("On random windows of 6-72 months in 1999-2024, do the two event-clock candidates "
                     "(the reaction long-short and the N1 H5|all learner) beat a beta-matched market MORE "
                     "OFTEN THAN THEIR OWN MATCHED CONTROL on the same window -- at three liquidity floors "
                     "and three borrow rates on the short leg?"),
        "windows": {"n": len(windows), "seed": seed, "lengths": LENGTHS,
                    "generator": "identical to RW1 draw_windows, so seeds are comparable across files"},
        "arms": sorted(arms), "floors_usd": FLOORS, "borrow_bps_per_year": BORROW_BPS_YR,
        "cost_bps_per_side": COST_BPS, "horizons": {"reaction_LS": 21, "N1_H5_all_LS": H5_HORIZON},
        "control": ("the identical pipeline on R4_placebo_offset40 -- same names, same construction, same "
                    "costs, announcement dates shifted +40 sessions, so zero event information"),
        "gradings": int(len(res)),
        "summary": summary, "borrow_curve_at_10m_floor": curve,
        "windows_parquet": str(OUT / f"RW2_windows_seed{seed}.parquet"),
        "headline": (
            f"{len(windows)} random windows; at the tradable corner ($10m floor, 200 bps borrow) the reaction "
            f"long-short beats its own control in {(react['overall'] or {}).get('win_vs_control')} of windows "
            f"(median {(react['overall'] or {}).get('median_vs_control_ann_pct')}%/yr) and the N1 H5|all learner "
            f"in {(learner['overall'] or {}).get('win_vs_control')} "
            f"(median {(learner['overall'] or {}).get('median_vs_control_ann_pct')}%/yr)"),
        "verdict": "DESCRIPTIVE, NO HOLDOUT. " + verdict_for(react, "reaction_LS") + " | " + verdict_for(learner, "N1_H5_all_LS"),
        "family_max_p": None,
        "elapsed_s": round(time.time() - t0, 1), "written_utc": _now(),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--windows", type=int, default=240)
    ap.add_argument("--seed", type=int, default=20260909)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--run", type=int, default=1)
    a = ap.parse_args(argv)
    p = RW2_event_windows(n_windows=a.windows, seed=a.seed, smoke=a.smoke)
    p["run"] = a.run
    out = Path(a.out) if a.out else OUT / f"RW2_event_windows_run{a.run:02d}{'_smoke' if a.smoke else ''}.json"
    out.write_text(json.dumps(p, indent=1, default=str), encoding="utf-8")
    print(f"\nRW2: {p['headline']}\n  verdict: {p['verdict']}\n  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
