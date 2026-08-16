"""N4B — can the library's coverage lift be RULED OUT below the level at which
de-risking on it would pay?

    python -m scripts.n4b_coverage_equivalence

Registered at `docs/TRIALS/PREREG_N4B_COVERAGE_EQUIVALENCE.md` before this file
computed anything. Read that first; this is the run spec made executable.

THE POINT
=========
N4 measured pooled coverage lift of 0.82-1.15 against MDEs of 0.25-0.62 and
printed `NO COVERAGE`. That is a statement about the instrument. The negative
that would actually mean something has the opposite form — *we can exclude the
lifts that would have mattered* — and it needs a margin fixed from economics
before the interval is looked at.

THE MARGIN
==========
The library's only action is: when any precursor fires, cut exposure for H days.
With `q = 0.10` by construction, Bayes gives `P(tail | fire) = L * q`, so a lift
of L means the warning is right `10L`% of the time. De-risking pays when

    L*q*|mu_tail|  >  (1 - L*q)*mu_rest + cost

    =>   L_min = (mu_rest + cost) / (q * (|mu_tail| + mu_rest))

`mu_tail` and `mu_rest` are properties of the unconditional forward-return
distribution. They cannot be moved by anything this test discovers, which is
what makes the margin prospective in the only sense that matters.

THE INTERVAL
============
A moving-block bootstrap, with block starts drawn ONCE per replicate and
applied to all six securities on the shared calendar. Resampling each security
independently would treat six co-moving ETFs as six measurements — the exact
error that manufactured confidence in gamma* (SS41). Sharing the draw keeps the
cross-sectional dependence intact and produces a wider, honest interval.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend import config as _config
from backend.services.research_gym import autopsy as AU
from backend.services.research_gym import power as PW

OUT = _config.OPTIMUS_LEDGER_DIR / "research_gym" / "n4b_coverage_equivalence.json"
AUTOPSIES = _config.OPTIMUS_LEDGER_DIR / "research_gym"

UNIVERSE = ["SPY", "QQQ", "IWM", "XLF", "XLE", "XLK"]
HORIZONS = (20, 60)
TAIL_Q = 0.10
SEED = 20260816
N_BOOT = 2000
#: Round-trip cost of the exposure change, in RETURN units. Declared in the
#: prereg; the sensitivity grid is run around it and always reported.
COST = 0.0010
COST_GRID = (0.0, 0.0010, 0.0025)
BLOCK_MULTIPLIERS = (0.5, 1.0, 2.0)

#: The order the verdicts weaken in. A run reports the WEAKEST verdict it
#: produced anywhere in the sensitivity grid; reporting the headline cell would
#: be choosing the flattering assumption after seeing the answer.
_ORDER = {"AT_LEAST_MARGIN": 0, "NOT_DEMONSTRATED": 1, "RULED_OUT": 2}


def _latest_autopsies() -> Path | None:
    files = sorted(AUTOPSIES.glob("autopsies_*.jsonl"))
    return files[-1] if files else None


def _weakest(verdicts: list[str]) -> str:
    if not verdicts:
        return "UNPOWERED_IN_SCOPE"
    return min(verdicts, key=lambda v: _ORDER.get(v, -1))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default="1999-01-01")
    ap.add_argument("--end", default="2026-08-15")
    ap.add_argument("--autopsies", default=None)
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
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
    precursors = []
    for r in rows:
        au = r.get("autopsy") or {}
        spec = au.get("affected_precursor") or au.get("executable_precursor")
        if not spec:
            continue
        try:
            precursors.append(AU.compile_precursor(spec))
        except Exception as exc:                                 # noqa: BLE001
            print(f"  skipped a precursor that will not compile: {exc}")
    print(f"library: {len(rows)} mechanisms, {len(precursors)} compiled "
          f"from {path.name}\n")
    if not precursors:
        return 1

    vix = yf.download("^VIX", start=a.start, end=a.end, progress=False)["Close"]
    if isinstance(vix, pd.DataFrame):
        vix = vix.squeeze()

    per: dict[str, pd.DataFrame] = {}
    for tkr in UNIVERSE:
        px = yf.download(tkr, start=a.start, end=a.end, progress=False)["Close"]
        if isinstance(px, pd.DataFrame):
            px = px.squeeze()
        px = px.dropna()
        r = px.pct_change().dropna()
        v = vix.reindex(r.index).ffill().shift(1)
        roll_max = px.rolling(252, min_periods=20).max()
        rv20 = r.rolling(20).std() * np.sqrt(252) * 100.0
        rv60 = r.rolling(60).std() * np.sqrt(252) * 100.0
        state = pd.DataFrame({
            "vix": v,
            "drawdown_pct": ((px / roll_max - 1.0) * 100.0).shift(1),
            "ret_1m_pct": (px.pct_change(21) * 100.0).shift(1),
            "ret_3m_pct": (px.pct_change(63) * 100.0).shift(1),
            "ret_6m_pct": (px.pct_change(126) * 100.0).shift(1),
            "realised_vol_20d": rv20.shift(1),
            "vol_ratio_20_60": (rv20 / rv60).shift(1),
        }).reindex(r.index)
        state["security"] = tkr

        fired = np.zeros(len(state), dtype=bool)
        recs = state.to_dict("records")
        for fn in precursors:
            for i, rec in enumerate(recs):
                if fired[i]:
                    continue
                try:
                    if fn(rec):
                        fired[i] = True
                except Exception:                                # noqa: BLE001
                    pass
        df = pd.DataFrame({"fired": fired,
                           "has_vix": state["vix"].notna().to_numpy()},
                          index=r.index)
        for H in HORIZONS:
            df[f"fwd_{H}"] = ((px.shift(-H) / px - 1.0) * 100.0).reindex(r.index)
        per[tkr] = df
        print(f"  {tkr}: {len(df)} days, precursor fires on "
              f"{100.0 * fired.mean():.1f}%")

    common = None
    for df in per.values():
        idx = df.index[df["has_vix"].to_numpy()]
        common = idx if common is None else common.intersection(idx)
    print(f"\nshared calendar: {len(common)} days "
          f"{common[0].date()} -> {common[-1].date()}\n")

    # ── pre-extract to numpy: the bootstrap runs this 24,000 times ──────────
    arrays: dict[tuple[str, int], tuple] = {}
    for tkr in UNIVERSE:
        d = per[tkr].loc[common]
        fire = d["fired"].to_numpy()
        for H in HORIZONS:
            f = d[f"fwd_{H}"].to_numpy()
            ok = ~np.isnan(f)
            arrays[(tkr, H)] = (f[ok], fire[ok])

    rng = np.random.default_rng(SEED)

    def cell(H: int, tail: str, pos: np.ndarray | None) -> tuple | None:
        """Pooled (lift, mu_tail, mu_rest) over the securities on rows `pos`."""
        lifts, mts, mrs = [], [], []
        for tkr in UNIVERSE:
            f, fire = arrays[(tkr, H)]
            if pos is not None:
                p = pos[pos < len(f)]
                f, fire = f[p], fire[p]
            if len(f) < 200:
                return None
            cut = (np.quantile(f, TAIL_Q) if tail == "bottom"
                   else np.quantile(f, 1.0 - TAIL_Q))
            mask = f <= cut if tail == "bottom" else f >= cut
            base = float(fire.mean())
            if base <= 0 or not mask.any() or mask.all():
                return None
            lifts.append(float(fire[mask].mean()) / base)
            mts.append(float(f[mask].mean()) / 100.0)
            mrs.append(float(f[~mask].mean()) / 100.0)
        k = len(lifts)
        return (sum(lifts) / k, sum(mts) / k, sum(mrs) / k)

    def l_min(mu_tail: float, mu_rest: float, cost: float) -> float:
        mr = max(mu_rest, 0.0)
        denom = TAIL_Q * (abs(mu_tail) + mr)
        return (mr + cost) / denom if denom > 0 else float("inf")

    n = len(common)
    out_rows: list[dict] = []

    for H in HORIZONS:
        for tail in ("bottom", "top"):
            point = cell(H, tail, None)
            if point is None:
                continue
            lift_hat, mu_t, mu_r = point

            sens: list[dict] = []
            for bm in BLOCK_MULTIPLIERS:
                block = max(int(round(H * bm)), 2)
                n_blocks = max(n // block, 1)
                reps = []
                for _ in range(a.n_boot):
                    starts = rng.integers(0, max(n - block, 1), size=n_blocks)
                    pos = (starts[:, None] + np.arange(block)[None, :]).ravel()
                    got = cell(H, tail, pos)
                    if got is not None:
                        reps.append(got[0])
                if len(reps) < 50:
                    continue
                se = float(np.std(reps, ddof=1))
                for c in COST_GRID:
                    lm = l_min(mu_t, mu_r, c)
                    v = PW.can_rule_out_at_least(lift_hat, se, lm)
                    sens.append({"block": block, "cost": c, "L_min": lm,
                                 "se": se, **v})

            headline = next((s for s in sens if s["block"] == H
                             and abs(s["cost"] - COST) < 1e-12), None)
            robust = _weakest([s["verdict"] for s in sens])
            # FOUND ON THE FIRST RUN, and it would have been a false positive:
            # the margin is derived from the economics of DE-RISKING, and the
            # top tail's mu_rest is ~0 or negative, so L_min collapses to ~0.1
            # and every lift clears it. That is arithmetic, not evidence — the
            # library is a sell library and "add exposure on a danger signal"
            # is not an action it ever proposed. The top tail is reported
            # descriptively, exactly as N4 reported it, and is NOT adjudicated.
            applicable = (tail == "bottom")
            out_rows.append({
                "horizon": H, "tail": tail, "lift": lift_hat,
                "margin_applicable": applicable,
                "margin_note": (None if applicable else
                                "L_min is derived from de-risking economics; "
                                "the top tail's action is not de-risking, so "
                                "this cell is descriptive only"),
                "mu_tail_pct": mu_t * 100.0, "mu_rest_pct": mu_r * 100.0,
                "L_min_declared_cost": l_min(mu_t, mu_r, COST),
                "precision_at_lift_pct": lift_hat * TAIL_Q * 100.0,
                "headline": headline, "robust_verdict": robust,
                "sensitivity": sens, "n_days": int(n), "n_boot": a.n_boot})
            h = headline or {}
            tag = (f"-> {h.get('verdict', '?')}   [robust: {robust}]"
                   if applicable else
                   "-> DESCRIPTIVE ONLY (margin is a de-risking margin)")
            print(f"H={H:>3d}d {tail:<7s} lift {lift_hat:5.3f} "
                  f"(precision {lift_hat * TAIL_Q * 100:4.1f}%)  "
                  f"se {h.get('se', float('nan')):5.3f}  "
                  f"upper {h.get('upper_bound', float('nan')):5.3f}  "
                  f"L_min {l_min(mu_t, mu_r, COST):5.2f}  {tag}")
            print(f"          mu_tail {mu_t * 100:+6.2f}%  "
                  f"mu_rest {mu_r * 100:+6.2f}%  over {H}d")

    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"universe": UNIVERSE, "tail_quantile": TAIL_Q,
                             "seed": SEED, "cost_declared": COST,
                             "rows": out_rows}, indent=2), encoding="utf-8")
    print(f"\nwritten  {p}")
    print("The verdict that stands is the WEAKEST across the sensitivity grid, "
          "never the headline cell.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
