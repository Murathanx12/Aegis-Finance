"""E3 -- adaptive conformal intervals on a real head, graded per volatility regime.

TWO PARTS, AND THE FIRST ONE DECIDES WHETHER THE SECOND MEANS ANYTHING.

1. A SYNTHETIC series with a PLANTED regime shift. Plain split conformal's
   realised coverage must fall measurably below nominal after the shift; ACI's
   must come back; and the recovery speed `k` is SWEPT and reported rather than
   hardcoded and hoped for. A method that cannot be shown to break where it is
   known to break, and to recover where it is claimed to recover, is not
   evidence about anything.

2. A REAL head's forecast stream, from E1's own daily file: `pred_*` is the
   head's predicted decile-spread for that session and `gross_*` is what the
   spread actually did -- a forecast and its realisation on one scale, from one
   walk-forward, with no second model invented to produce a point estimate.

WHICH HEAD GETS THE INTERVAL (spec section 3.3). Whichever E1/E2 arm has a
POSITIVE control-adjusted IC. If none does -- which is the standing state after
N3's two FAILED_VARIANTs and E1's and E2's -- the machinery is exercised on the
GBM CONTROL arm and the receipt says so in those words. Refusing to report an
interval because nothing beat shuffle would be a gate that cannot go green: the
interval question ("does the coverage hold up when vol triples") is worth
answering about a control, and is answered the same way about a signal the day
one exists.

THE HEADLINE IS THE COVERAGE TABLE, not a point estimate with coverage in a
footnote. Three methods x three vol terciles, plus ALL.

Licence: PRODUCT_EXPERIMENT. No order, no claim of alpha.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import conformal                           # noqa: E402
from scripts import night_n3_frozen_embedding_head as n3         # noqa: E402
from scripts.night_checkpoint import atomic_write_json           # noqa: E402

JOB = "E3_adaptive_conformal"
LICENCE = "PRODUCT_EXPERIMENT"
SEED = n3.SEED
ALPHA = 0.10
GAMMA = conformal.DEFAULT_GAMMA
RHO = 0.95
OUT_DIR = n3.OUT_DIR
BARS = n3.BARS


# ---------------------------------------------------------------------------
# 1. the known-answer synthetic
# ---------------------------------------------------------------------------
def synthetic_shift(n: int = 1000, shift_at: int = 500, vol_mult: float = 3.0,
                    phi: float = 0.4, seed: int = SEED):
    """AR(1) around a predictable mean, whose innovation variance triples at t.

    The point forecast is the AR(1) conditional mean, which stays CORRECT after
    the shift -- only its error distribution changes. That is the distribution
    shift conformal is supposed to notice, isolated from a forecasting failure.
    """
    rng = np.random.default_rng(seed)
    sd = np.where(np.arange(n) >= shift_at, 0.01 * vol_mult, 0.01)
    y = np.zeros(n)
    pred = np.zeros(n)
    for t in range(1, n):
        pred[t] = phi * y[t - 1]
        y[t] = pred[t] + rng.normal(0.0, sd[t])
    return pred, y, sd


def _window_coverage(run: conformal.ConformalRun, lo: int, hi: int) -> float:
    cov = np.asarray(run.covered)
    sl = cov[lo:hi]
    sl = sl[sl >= 0]
    return float(sl.mean()) if len(sl) else float("nan")


def known_answer(alpha: float = ALPHA, gamma: float = GAMMA, rho: float = RHO) -> dict:
    """Does the naive method break where it is known to, and does ACI recover?"""
    pred, y, _sd = synthetic_shift()
    shift_at, n = 500, 1000
    runs = {
        "NAIVE": conformal.run_stream(pred, y, alpha=alpha, adaptive=False, rho=1.0),
        "ACI": conformal.run_stream(pred, y, alpha=alpha, gamma=gamma, adaptive=True, rho=1.0),
        "ACI_WEIGHTED": conformal.run_stream(pred, y, alpha=alpha, gamma=gamma,
                                             adaptive=True, rho=rho),
    }
    nominal = 1.0 - alpha
    post = {k: _window_coverage(v, shift_at, shift_at + 120) for k, v in runs.items()}

    # the smallest k after which coverage is back within 5 points of nominal,
    # SWEPT rather than assumed
    def recovery_k(run, tol=0.05, width=150):
        for k in range(10, 400, 10):
            c = _window_coverage(run, shift_at + k, min(n, shift_at + k + width))
            if np.isfinite(c) and abs(c - nominal) <= tol:
                return k
        return None

    ks = {k: recovery_k(v) for k, v in runs.items()}
    naive_broke = np.isfinite(post["NAIVE"]) and post["NAIVE"] < nominal - 0.15
    aci_recovers = ks["ACI"] is not None
    weighted_at_least_as_fast = (
        ks["ACI_WEIGHTED"] is not None and ks["ACI"] is not None
        and ks["ACI_WEIGHTED"] <= ks["ACI"])
    return {
        "design": {"n": n, "shift_at": shift_at, "vol_multiplier": 3.0, "ar1_phi": 0.4,
                   "alpha": alpha, "nominal_coverage": nominal, "gamma": gamma, "rho": rho,
                   "note": ("the point forecast stays correct after the shift; only the error "
                            "SCALE changes, so this isolates distribution shift from a "
                            "forecasting failure")},
        "post_shift_coverage_120_steps": {k: round(v, 4) for k, v in post.items()},
        "smallest_k_back_within_5_points": ks,
        "naive_coverage_collapses": bool(naive_broke),
        "aci_recovers": bool(aci_recovers),
        "weighted_recovers_at_least_as_fast": bool(weighted_at_least_as_fast),
        "weighted_vs_plain_note": ("reported, not assumed -- a weighting that helped on a "
                                   "different series is not evidence about this one"),
    }


# ---------------------------------------------------------------------------
# 2. the real head's stream
# ---------------------------------------------------------------------------
def spy_vol(dates: np.ndarray, window: int = 21) -> np.ndarray:
    """Trailing 21-session SPY volatility, via the repo's own helper.

    `learner.growth_lab._trailing_vol` annualises with sqrt(12), which is a
    MONTHLY convention applied to a daily series. That constant factor is wrong
    as a level and irrelevant as an ordering, and only the ordering is used --
    terciles are invariant to a positive constant. The helper is reused rather
    than reimplemented so a change to the repo's vol definition reaches here;
    the receipt carries this caveat.
    """
    from learner.growth_lab import _trailing_vol

    b = pd.read_parquet(BARS, columns=["symbol", "date", "open", "close"])
    b = b[b["symbol"] == "SPY"].copy()
    b["date"] = pd.to_datetime(b["date"]).dt.normalize()
    b = b.sort_values("date")
    r = pd.Series((b["close"] / b["open"] - 1.0).to_numpy(), index=b["date"].to_numpy())
    v = _trailing_vol(r, int(window))
    return v.reindex(pd.to_datetime(dates)).to_numpy(dtype=float)


def _pick_arm(daily: pd.DataFrame, receipts: list[dict]) -> dict:
    """Spec section 3.3: a positive control-adjusted IC, else the GBM control."""
    for r in receipts:
        vs = ((r.get("results") or {}).get("eras") or {}).get("ALL", {}).get("vs_controls", {})
        for key, cell in vs.items():
            if not key.endswith("_minus_SHUFFLE"):
                continue
            mean = (cell.get("ic") or {}).get("mean")
            if mean is not None and mean > 0:
                model = key.split(":")[0] if ":" in key else "GBM"
                arm = "EVENT" if "EVENT" in key else "EMBED"
                col = f"pred_{model}_{arm}"
                if col in daily.columns:
                    return {"column": f"{model}_{arm}", "reason":
                            f"{key} has a POSITIVE control-adjusted IC ({mean:+.4f})"}
    for cand in ("GBM_NOTEXT", "GBM_EVENT"):
        if f"pred_{cand}" in daily.columns:
            return {"column": cand, "reason":
                    ("no E1/E2 arm has a positive control-adjusted IC, so the machinery is "
                     "exercised on the GBM CONTROL arm. This is NOT a claim that the control "
                     "carries signal; it is the interval question answered about the only "
                     "forecast stream that exists.")}
    raise SystemExit("REFUSED: E1's daily file has no `pred_*` column to build a stream from")


def real_stream(daily_csv: Path, receipts: list[dict], alpha: float = ALPHA,
                gamma: float = GAMMA, rho: float = RHO) -> dict:
    daily = pd.read_csv(daily_csv, parse_dates=["date"])
    pick = _pick_arm(daily, receipts)
    key = pick["column"]
    d = daily[["date", f"pred_{key}", f"gross_{key}"]].dropna().sort_values("date")
    if len(d) < 60:
        return {"status": "CANNOT DETERMINE -- fewer than 60 graded date blocks", **pick}
    pred = d[f"pred_{key}"].to_numpy(dtype=float)
    truth = d[f"gross_{key}"].to_numpy(dtype=float)
    vol = spy_vol(d["date"].to_numpy())
    regime = conformal.terciles(vol)

    runs = {
        "NAIVE": conformal.run_stream(pred, truth, alpha=alpha, adaptive=False, rho=1.0),
        "ACI": conformal.run_stream(pred, truth, alpha=alpha, gamma=gamma, adaptive=True, rho=1.0),
        "ACI_WEIGHTED": conformal.run_stream(pred, truth, alpha=alpha, gamma=gamma,
                                             adaptive=True, rho=rho),
    }
    table = conformal.coverage_table(runs, regime)
    return {
        "status": "done",
        "arm": key,
        "arm_choice_reason": pick["reason"],
        "daily_csv": str(daily_csv),
        "n_date_blocks": int(len(d)),
        "dates": [str(d["date"].min().date()), str(d["date"].max().date())],
        "forecast": (f"pred_{key} -- the head's predicted decile spread for that session; the "
                     f"outcome is gross_{key}, the spread's realised GROSS return (costs are "
                     f"charged in E1's net column and are not part of the forecast)"),
        "vol_regime": {"source": "trailing 21-session SPY open-to-close vol via "
                                 "learner.growth_lab._trailing_vol",
                       "caveat": "the helper annualises with sqrt(12); terciles are invariant "
                                 "to that constant and only the ordering is used",
                       "n_ungradable_regime": int((regime < 0).sum())},
        "coverage_table": table,
    }


# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="E3 adaptive conformal intervals")
    ap.add_argument("--out", default=None)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--daily", default=None, help="E1's *_daily.csv (default: the newest in OUT_DIR)")
    ap.add_argument("--stage", default="signal")
    args = ap.parse_args(argv)

    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else (OUT_DIR / f"{JOB}_run{args.run:02d}.json")

    receipt = {
        "job": JOB, "licence": LICENCE, "run": args.run, "smoke": bool(args.smoke),
        "stage": args.stage, "llm_spend_usd": 0.0,
        "question": ("Does adaptive conformal (ACI, plus recency-weighted non-exchangeable "
                     "quantiles) hold its nominal coverage across volatility regimes where "
                     "plain split conformal does not?"),
        "method": conformal.declaration(),
        "design": {"alpha": ALPHA, "nominal_coverage": 1 - ALPHA, "gamma": GAMMA, "rho": RHO,
                   "naive_control": "fixed alpha, rho = 1.0 -- the exchangeable case, no "
                                    "separate code path",
                   "seed": SEED},
        "inputs": [],          # filled once the real stream's source is resolved
        "status": "running", "written_utc": n3._now(),
    }
    atomic_write_json(out, receipt, indent=1)

    print("[e3] known-answer: a planted regime shift", flush=True)
    ka = known_answer()
    receipt["known_answer"] = ka
    atomic_write_json(out, receipt, indent=1)

    daily = Path(args.daily) if args.daily else None
    if daily is None:
        hits = sorted(OUT_DIR.glob("E1_event_head_*_daily.csv"))
        daily = hits[-1] if hits else None
    receipts = []
    for p in sorted(OUT_DIR.glob("E1_event_head_*.json")) + sorted(OUT_DIR.glob("E2_*.json")):
        try:
            receipts.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue

    if daily is None or not daily.is_file():
        receipt["real_stream"] = {"status": "CANNOT DETERMINE -- no E1 daily file on this "
                                            "checkout, so no real forecast stream exists yet"}
    else:
        print(f"[e3] real stream from {daily.name}", flush=True)
        receipt["real_stream"] = real_stream(daily, receipts)
        # E3 reads a SIGNAL-stage artefact and is itself signal-stage. That edge
        # is legal and is the one the contract's test actually walks.
        receipt["inputs"] = [daily.name, n3.BARS.name]

    rs = receipt["real_stream"]
    if rs.get("status") == "done":
        t = rs["coverage_table"]

        def cov(method, cell):
            c = t[method]["by_vol_tercile"].get(cell, {})
            return c.get("realised_coverage")

        head = (f"nominal {1 - ALPHA:.0%} on {rs['n_date_blocks']} date blocks, arm {rs['arm']}: "
                f"HIGH-vol realised coverage NAIVE {cov('NAIVE', 'HIGH')} / "
                f"ACI {cov('ACI', 'HIGH')} / ACI_WEIGHTED {cov('ACI_WEIGHTED', 'HIGH')}; "
                f"LOW-vol NAIVE {cov('NAIVE', 'LOW')} / ACI {cov('ACI', 'LOW')}")
    else:
        head = f"interval mechanics validated on the synthetic only -- {rs.get('status')}"

    v = ("interval mechanics validated" if ka["aci_recovers"] else
         "CANNOT DETERMINE -- ACI did not recover on the planted shift")
    if "control" in (rs.get("arm_choice_reason") or ""):
        v += ("; no head has a signal worth intervalizing yet, so this ran on the GBM control "
              "arm and says so")
    receipt["headline"] = head
    receipt["verdict"] = v
    receipt["next_test"] = ("re-run against whichever head first shows a positive "
                            "control-adjusted IC, and against E4's ADWIN-gated refit, whose "
                            "stale-model dates should show up here as a coverage cost")
    receipt["status"] = "done"
    receipt["elapsed_s"] = round(time.time() - t0, 1)
    receipt["written_utc"] = n3._now()
    atomic_write_json(out, receipt, indent=1)
    print("\n" + head)
    print(v)
    print(f"receipt: {out}")
    return 0


def E3_adaptive_conformal(smoke: bool = False, run: int = 1) -> dict:
    out = OUT_DIR / f"{JOB}_run{run:02d}{'_smoke' if smoke else ''}.json"
    argv = ["--run", str(run), "--out", str(out)] + (["--smoke"] if smoke else [])
    rc = main(argv)
    payload = json.loads(out.read_text(encoding="utf-8"))
    if rc != 0:
        payload.setdefault("status", "REFUSED")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
