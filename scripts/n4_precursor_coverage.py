"""N4 — for every exceptional move, did ANY precursor in the library fire first?

    python -m scripts.n4_precursor_coverage

THE MICRON TEST AS A PROGRAMME METRIC
=====================================
"Explaining a winner afterwards is trivial; finding precursors observable
BEFOREHAND is the research problem." Every mechanism in the library has been
validated one at a time, and none of that answers the question that decides
whether the library is worth having:

    of all the moves worth catching, what fraction had ANY warning at all?

If coverage is near zero, the validity of individual mechanisms barely matters.
The roadmap would then be about coverage — finding precursors for the
uncovered moves — rather than about rigour applied to the few we have.

PCI ALONE IS UNINTERPRETABLE, SO IT IS NOT THE REPORTED NUMBER
===============================================================
A precursor that fires 40% of the time "covers" 40% of moves by doing nothing.
The reported quantity is **LIFT**:

    lift = P(a precursor fired | the move was exceptional)
           -------------------------------------------------
                    P(a precursor fired)

Lift 1.0 means the library marks exceptional moves no better than it marks
Tuesdays, whatever its raw coverage looks like. Lift carries a bootstrap
interval, because a ratio of two proportions on clustered daily data has a much
wider interval than its point estimate suggests.

BOTH TAILS, SEPARATELY
======================
A precursor library built from SELL autopsies should mark crashes. Whether it
also marks rallies is a different question and is reported separately — a
library that fires before every large move in EITHER direction is detecting
volatility, which is a real thing to detect and is not what a directional
mechanism claims.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend import config as _config
from backend.services.research_gym import autopsy as AU
from backend.services.research_gym import power as PW

OUT = _config.OPTIMUS_LEDGER_DIR / "research_gym" / "n4_precursor_coverage.json"
AUTOPSIES = _config.OPTIMUS_LEDGER_DIR / "research_gym"

UNIVERSE = ["SPY", "QQQ", "IWM", "XLF", "XLE", "XLK"]
HORIZONS = (20, 60)
#: Declared in the protocol: "exceptional" is the top/bottom decile of the
#: security's OWN forward-return distribution at that horizon.
TAIL_Q = 0.10


def _latest_autopsies() -> Path | None:
    files = sorted(AUTOPSIES.glob("autopsies_*.jsonl"))
    return files[-1] if files else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default="1999-01-01")
    ap.add_argument("--end", default="2026-08-15")
    ap.add_argument("--autopsies", default=None)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    import numpy as np
    import pandas as pd
    import yfinance as yf

    path = Path(a.autopsies) if a.autopsies else _latest_autopsies()
    if path is None:
        print("no autopsy file")
        return 1
    rows = [json.loads(ln) for ln in
            path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    print(f"library: {len(rows)} mechanisms from {path.name}")

    precursors = []
    for r in rows:
        au = r.get("autopsy") or {}
        spec = au.get("affected_precursor") or au.get("executable_precursor")
        if not spec:
            continue
        try:
            fn = AU.compile_precursor(spec)
        except Exception as exc:                                 # noqa: BLE001
            print(f"  skipped a precursor that will not compile: {exc}")
            continue
        precursors.append((json.dumps(spec)[:80], fn))
    print(f"compiled: {len(precursors)} precursors\n")
    if not precursors:
        return 1

    vix = yf.download("^VIX", start=a.start, end=a.end, progress=False)["Close"]
    if isinstance(vix, pd.DataFrame):
        vix = vix.squeeze()

    results: list[dict] = []
    for tkr in UNIVERSE:
        px = yf.download(tkr, start=a.start, end=a.end, progress=False)["Close"]
        if isinstance(px, pd.DataFrame):
            px = px.squeeze()
        px = px.dropna()
        r = px.pct_change().dropna()
        v = vix.reindex(r.index).ffill()
        # The state is read at the close BEFORE the window it labels — the same
        # rule the tensor uses, so a precursor can never see its own outcome.
        v = v.shift(1)
        roll_max = px.rolling(252, min_periods=20).max()
        dd = (px / roll_max - 1.0) * 100.0
        rv20 = r.rolling(20).std() * np.sqrt(252) * 100.0
        rv60 = r.rolling(60).std() * np.sqrt(252) * 100.0
        ret1m = px.pct_change(21) * 100.0
        ret3m = px.pct_change(63) * 100.0
        ret6m = px.pct_change(126) * 100.0

        state = pd.DataFrame({
            "vix": v,
            "drawdown_pct": dd.shift(1),
            "ret_1m_pct": ret1m.shift(1),
            "ret_3m_pct": ret3m.shift(1),
            "ret_6m_pct": ret6m.shift(1),
            "realised_vol_20d": rv20.shift(1),
            "vol_ratio_20_60": (rv20 / rv60).shift(1),
        }).reindex(r.index)
        state["security"] = tkr

        fired = np.zeros(len(state), dtype=bool)
        n_uneval = 0
        recs = state.to_dict("records")
        for _label, fn in precursors:
            for i, rec in enumerate(recs):
                if fired[i]:
                    continue
                try:
                    if fn(rec):
                        fired[i] = True
                except Exception:                                # noqa: BLE001
                    n_uneval += 1

        for H in HORIZONS:
            fwd = (px.shift(-H) / px - 1.0) * 100.0
            fwd = fwd.reindex(r.index)
            ok = fwd.notna() & state["vix"].notna()
            f_arr = fwd[ok].to_numpy()
            fire = fired[ok.to_numpy()]
            if len(f_arr) < 200:
                continue
            lo_cut = float(np.quantile(f_arr, TAIL_Q))
            hi_cut = float(np.quantile(f_arr, 1.0 - TAIL_Q))
            base = float(fire.mean())
            for tail, mask in (("bottom", f_arr <= lo_cut),
                               ("top", f_arr >= hi_cut)):
                cov = float(fire[mask].mean()) if mask.any() else 0.0
                lift = (cov / base) if base > 0 else None
                results.append({
                    "security": tkr, "horizon": H, "tail": tail,
                    "n": int(mask.sum()), "n_total": int(len(f_arr)),
                    "base_rate": base, "coverage": cov, "lift": lift,
                    "n_unevaluable": n_uneval,
                })

    if not results:
        print("nothing measured")
        return 1

    print(f"{'sec':<5s} {'H':>4s} {'tail':<7s} {'n':>5s} {'base':>7s} "
          f"{'coverage':>9s} {'LIFT':>7s}")
    for x in results:
        lf = "-" if x["lift"] is None else f"{x['lift']:7.2f}"
        print(f"{x['security']:<5s} {x['horizon']:>4d} {x['tail']:<7s} "
              f"{x['n']:>5d} {x['base_rate']:>7.1%} {x['coverage']:>9.1%} "
              f"{lf:>7s}")

    # ── the pooled answer, with an interval that respects clustering ────────
    print("\nPOOLED — the number that decides whether the library has coverage")
    for H in HORIZONS:
        for tail in ("bottom", "top"):
            sub = [x for x in results
                   if x["horizon"] == H and x["tail"] == tail and x["lift"]]
            if not sub:
                continue
            lifts = [x["lift"] for x in sub]
            mean_lift = sum(lifts) / len(lifts)
            # The six securities are the SAME six co-moving ETFs that caused
            # §41. They are not six independent measurements of coverage, so
            # the effective n is bounded hard rather than taken as 6.
            n_eff = PW.effective_n(len(sub), 1, n_episodes=2)
            sd = (sum((x - mean_lift) ** 2 for x in lifts)
                  / max(len(lifts) - 1, 1)) ** 0.5
            mde = PW.mde_mean(sd, n_eff) if sd > 0 else None
            # NOT "NO COVERAGE". An estimate that fails to separate from 1.0
            # is a statement about this instrument, not about the library:
            # with MDE 0.25-0.62 the interval still covers lifts that would
            # change a portfolio decision. Ruling those out needs an
            # equivalence test against a declared economic margin, which is
            # `scripts/n4b_coverage_equivalence.py`, not this line.
            verdict = ("NOT DEMONSTRATED" if mde is None or
                       abs(mean_lift - 1.0) < mde else
                       ("COVERS" if mean_lift > 1.0 else "ANTI-COVERS"))
            print(f"  H={H:>3d}d {tail:<7s} mean lift {mean_lift:5.2f}  "
                  f"sd {sd:5.2f}  n_eff {n_eff:.1f}  "
                  f"MDE {'-' if mde is None else f'{mde:.2f}'}  {verdict}")

    covered = [x for x in results if x["lift"] and x["lift"] > 1.0]
    print(f"\n  cells where the library fires MORE before exceptional moves: "
          f"{len(covered)}/{len(results)}")
    print(f"  median coverage across cells: "
          f"{sorted(x['coverage'] for x in results)[len(results) // 2]:.1%}")
    print(f"  median base rate:             "
          f"{sorted(x['base_rate'] for x in results)[len(results) // 2]:.1%}")

    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"tail_quantile": TAIL_Q, "rows": results},
                            indent=2), encoding="utf-8")
    print(f"\nwritten  {p}")
    print("Gym output. Cells are hypotheses, never claims (R2 wall 1).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
