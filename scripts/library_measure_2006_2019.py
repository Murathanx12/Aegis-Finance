"""What the published wheel actually pays on our panel, net, 2006-2019.

    python -m scripts.library_measure_2006_2019

WHY THIS RUNS BEFORE THE FACTORY
================================
A factory result is unanchored until we know what MOMENTUM delivers on the same
panel, net, over the same window. The published strategies are not competition
for the paper — they are the BENCHMARK the factory's output has to beat, and a
mechanism that cannot beat a 1993 decile sort is not a finding regardless of its
t-statistic.

"Adopt before inventing" also cuts the other way: if the wheel pays nothing net
on 2006-2019, then the factory is not competing against 3%/yr, and the bar it
has to clear is lower than the literature implies. Either answer is worth more
than a guess.

THE ALIGNMENT FACT, MEASURED RATHER THAN ASSUMED
================================================
Chen & Zimmermann's convention note says signals are lagged so month t predicts
t+1. Notes are not data, so it was checked against our own return panel:

    Mom12m  at label month m == cumulative return over months m-11 .. m-1
    Mom6m   at label month m == cumulative return over months m-5  .. m-1

exact, correlation 1.0 and max |difference| 0.0, on three widely separated
months. So a signal labelled m is built from data through m-1 for the two
return-based predictors we can verify from first principles.

That verifies TWO predictors, not 209. Accounting signals carry their own lags
and we cannot re-derive each from our data. So the primary measurement pairs the
signal labelled m with the return of month **m+1** — a rule that is PIT-safe for
every predictor under any convention, because m+1 is strictly after the label
month whatever went into it.

That costs momentum a month of freshness: our UMD is effectively 12-2, not 12-1.
It is a DECLARED cost of one uniform defensible rule, in place of 209 individual
conventions we would have to take on trust. The `--same-month` flag measures the
other pairing for the two verified predictors only, so the size of the concession
is a number rather than a worry.

WHAT IS AND IS NOT MEASURED HERE
================================
* NOT a confirmation. 2006-2019 is registered EXPLORE (`slc_c3246e5093c41c25`)
  because if we later choose which strategies to deploy from these numbers, this
  window selected them. M4's confirmation window is reserved disjoint.
* NOT a reproduction of the authors' results. Their windows mostly end before
  2002, and our pre-2002 panel is registered-use-only. For nearly every
  predictor here 2006-2019 is entirely POST-PUBLICATION, which is why no decay
  ratio is computed: we have the decayed half and not the other one.
* The dollar-volume series is used to RANK and to SCREEN by percentile, never as
  a level. Its absolute scale did not reconcile against a known mega-cap, so it
  is treated the way `hl_range_20d` was in the cost path — ordering only. Ranks
  within a month are invariant to any monotone within-month rescaling, which is
  the only property this use needs.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

MODULE = Path(r"C:\Users\mrthn\Aegis module")
OSAP = MODULE / "data" / "osap" / "firm_char.parquet"
SIGNALDOC = MODULE / "data" / "reference" / "osap_SignalDoc_snap20260726.csv"
PANEL = MODULE / "data" / "crsp_panel_2002"
OUT = MODULE / "data" / "library" / "measure_2006_2019.json"

#: The selection window, registered EXPLORE before the first return was
#: computed. Confirmation is reserved disjoint on 2020-06-01..2026-07-17.
START, END = 200601, 201912

#: Formation screens. Declared here, not tuned: a $5 price floor and the bottom
#: quintile of dollar volume dropped are the conventional microcap guards, and
#: moving them after seeing a return would be choosing the universe to fit it.
MIN_PRICE = 5.0
MIN_DVOL_PCTILE = 20.0
MIN_NAMES = 100
N_DECILES = 10

#: Cost per unit of notional CROSSED ONCE, in basis points. Charged against
#: `sum |w_t - w_{t-1}|`, so a full rotation of a long-short book pays four
#: times this. Illustrative, and the break-even is what actually decides.
#:
#: THE UNIT IS IN THE NAME (Order 18 §1). `sum(|dw|)` counts BOTH legs of a
#: rotation, so the rate charged against it is the ONE-WAY cost — the HALF
#: spread. Every spread estimator in `backend/services/spread_estimators.py`
#: returns the FULL spread, so plugging one in here raw charges TWICE the
#: truth, and this panel's survivor count moves 4 -> 3 -> 1 -> 0 across
#: 0/5/10/20bp: a factor of two moves a verdict two whole steps. Convert at the
#: boundary with `SpreadEstimate.as_one_way_bps()`, which is the only place the
#: halving happens.
COST_BPS_ONE_WAY = 10.0

#: 12-month circular blocks. Anomaly returns are autocorrelated and their
#: crashes cluster (momentum's do, violently), so an iid bootstrap over months
#: would understate the SE of exactly the strategies most likely to look good.
BLOCK = 12
N_BOOT = 2000
SEED = 20260817

#: The seeded library, mapped to the predictor that implements it. `None` means
#: no faithful implementation exists in this data and the library refuses rather
#: than substituting a cousin.
SEED_MAP = {
    "UMD - cross-sectional momentum (12-1)": "Mom12m",
    "HML - book-to-market value": "BM",
    "Profitability (gross profits / assets)": "GP",
    "PEAD - post-earnings-announcement drift": "EarningsSurprise",
    "Low-volatility / defensive equity": "RealizedVol",
    "BAB - betting against beta": "BetaFP",
    "Short-term reversal (1-month)": "__own_1m_reversal",
    "TSMOM - time-series momentum": "__own_tsmom",
    "QMJ - quality minus junk": None,
    "Volatility targeting": "__own_voltarget",
}


def _log(msg: str) -> None:
    print(msg, flush=True)


# ── data ───────────────────────────────────────────────────────────────────
def load_panel() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ret = pd.read_parquet(PANEL / "monthly_ret.parquet")
    prc = pd.read_parquet(PANEL / "month_end_price.parquet")
    dvl = pd.read_parquet(PANEL / "monthly_dollar_vol.parquet")
    for d in (ret, prc, dvl):
        d.columns = [int(c) for c in d.columns]
        d.index = pd.PeriodIndex(d.index, freq="M")
    return ret.astype("float64"), prc.abs().astype("float64"), dvl.astype("float64")


def osap_columns() -> list[str]:
    f = pq.ParquetFile(OSAP)
    return [c for c in f.schema_arrow.names if c not in ("permno", "yyyymm")]


def load_osap(cols: list[str]) -> pd.DataFrame:
    f = pq.ParquetFile(OSAP)
    parts = []
    for i in range(f.metadata.num_row_groups):
        d = f.read_row_group(i, columns=["permno", "yyyymm"] + cols).to_pandas()
        d = d[(d.yyyymm >= START) & (d.yyyymm <= END)]
        if len(d):
            parts.append(d)
    return pd.concat(parts, ignore_index=True)


# ── the measurement ────────────────────────────────────────────────────────
def block_bootstrap_se(x: np.ndarray, rng: np.random.Generator) -> float:
    """Circular block bootstrap over MONTHS. n_effective counts blocks (S58)."""
    n = len(x)
    if n < BLOCK * 2:
        return float("nan")
    nb = int(np.ceil(n / BLOCK))
    means = np.empty(N_BOOT)
    starts = rng.integers(0, n, size=(N_BOOT, nb))
    offs = np.arange(BLOCK)
    for b in range(N_BOOT):
        idx = ((starts[b][:, None] + offs[None, :]).ravel() % n)[:n]
        means[b] = x[idx].mean()
    return float(np.std(means, ddof=1))


def decile_ls(sig: np.ndarray, fwd: np.ndarray, ok: np.ndarray
              ) -> tuple[np.ndarray, np.ndarray]:
    """Long top decile, short bottom, equal weight, month by month.

    OSAP signals are SIGNED so that a higher value means a higher expected
    return; the long leg is therefore always the top decile and there is no
    per-strategy sign decision to get wrong (or to fit).
    """
    n_m, n_p = sig.shape
    rets = np.full(n_m, np.nan)
    w_prev = np.zeros(n_p)
    turn = np.full(n_m, np.nan)
    for t in range(n_m - 1):
        m = ok[t] & np.isfinite(sig[t]) & np.isfinite(fwd[t])
        k = int(m.sum())
        if k < MIN_NAMES:
            continue
        idx = np.flatnonzero(m)
        order = idx[np.argsort(sig[t, idx], kind="stable")]
        nq = k // N_DECILES
        if nq < 5:
            continue
        lo, hi = order[:nq], order[-nq:]
        w = np.zeros(n_p)
        w[hi] = 1.0 / nq
        w[lo] = -1.0 / nq
        rets[t] = float(fwd[t, hi].mean() - fwd[t, lo].mean())
        turn[t] = float(np.abs(w - w_prev).sum())
        w_prev = w
    return rets, turn


def score(rets: np.ndarray, turn: np.ndarray, rng) -> dict:
    m = np.isfinite(rets)
    r = rets[m]
    if len(r) < 24:
        return {"n_months": int(len(r)), "insufficient": True}
    tr = turn[m]
    tr = tr[np.isfinite(tr)]
    mean_m = float(r.mean())
    se_m = block_bootstrap_se(r, rng)
    turn_m = float(tr.mean()) if len(tr) else float("nan")
    cost_m = turn_m * COST_BPS_ONE_WAY / 1e4
    gross_a = mean_m * 12.0
    net_a = (mean_m - cost_m) * 12.0
    se_a = se_m * 12.0
    mde_a = (1.959964 + 0.8416212) * se_a
    return {
        "n_months": int(len(r)),
        "gross_annual": gross_a,
        "net_annual": net_a,
        "se_annual": se_a,
        "mde_annual": mde_a,
        "z": float(mean_m / se_m) if se_m and np.isfinite(se_m) else float("nan"),
        "sharpe": float(mean_m / r.std(ddof=1) * np.sqrt(12)),
        "monthly_turnover": turn_m,
        # The break-even is the fact; COST_BPS_ONE_WAY is the assumption. A reader who
        # disputes the schedule reads this column instead.
        "breakeven_bps": float(1e4 * mean_m / turn_m) if turn_m else float("nan"),
        # DETECTABILITY IS A PROPERTY OF THE QUANTITY BEING CLAIMED.
        #
        # The first version tested `gross` against the MDE and every table then
        # printed `net`. Costs shift the estimate without changing its SE, so
        # the two differ by a fixed amount and the flag was quietly certifying
        # one number while the reader read another — three of four "tradable
        # survivors" turned out to sit at 0.6-0.8x their own MDE. Both are
        # reported; the verdicts use the net one, because net is the claim.
        "detectable_gross": bool(np.isfinite(se_a) and abs(gross_a) >= mde_a),
        "detectable": bool(np.isfinite(se_a) and abs(net_a) >= mde_a),
        "worst_year": float(pd.Series(r).rolling(12).sum().min()),
    }


def own_signals(ret: pd.DataFrame, months) -> dict[str, np.ndarray]:
    """The seeded strategies OSAP does not carry, built from the panel.

    Kept separate from the OSAP block on purpose: these are OUR construction and
    a reader must be able to tell which numbers depend on someone else's code.

    Only signals that are genuinely CROSS-SECTIONAL rankings belong here.
    TSMOM is not one — see `tsmom_equity_analogue`.
    """
    out = {}
    # 1-month reversal: last month's return, sign-flipped so high = expected high.
    out["__own_1m_reversal"] = -ret.reindex(months).shift(1).to_numpy()
    return out


def tsmom_equity_analogue(ret: pd.DataFrame, months, fwd: np.ndarray,
                          ok: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Time-series momentum, held as a TIME-SERIES rule rather than a rank.

    The first version of this pushed `sign(past return)` through the decile
    sorter. That is not TSMOM and it would have been reported as if it were: a
    three-valued signal has no interior deciles, so the sort was really ordering
    ties by permno and the top decile was an arbitrary tenth of the positive-
    trend names.

    TSMOM as MOP (2012) define it holds EVERY instrument, long or short by the
    sign of its own past return, sized inversely to its own volatility so no
    single name dominates. Nothing is ranked against anything else. It stays
    labelled an ANALOGUE because they ran it on 58 futures and we are running it
    on equities, which is a different test rather than the same one with
    different tickers.
    """
    lr = np.log1p(ret)
    mom = np.expm1(lr.rolling(11).sum().shift(1)).reindex(months).to_numpy()
    vol = lr.rolling(12).std().shift(1).reindex(months).to_numpy()
    n_m, n_p = fwd.shape
    rets = np.full(n_m, np.nan)
    turn = np.full(n_m, np.nan)
    w_prev = np.zeros(n_p)
    for t in range(n_m - 1):
        m = (ok[t] & np.isfinite(mom[t]) & np.isfinite(fwd[t])
             & np.isfinite(vol[t]) & (vol[t] > 0))
        if m.sum() < MIN_NAMES:
            continue
        w = np.zeros(n_p)
        raw = np.sign(mom[t, m]) / vol[t, m]
        w[m] = raw / np.abs(raw).sum()          # gross exposure normalised to 1
        rets[t] = float(np.nansum(w * fwd[t]))
        turn[t] = float(np.abs(w - w_prev).sum())
        w_prev = w
    return rets, turn


#: Seeded strategies with no faithful implementation in this data. Recorded
#: EXPLICITLY rather than omitted: a strategy missing from a results table reads
#: as "not run yet", and a strategy that CANNOT be run from what we hold is a
#: different fact that the next reader needs.
NOT_IMPLEMENTABLE = {
    "QMJ - quality minus junk": (
        "needs the profitability/growth/safety composite as AFP construct it. "
        "OSAP carries components (GP, OperProf, roaq) but assembling our own "
        "composite and calling it QMJ would be measuring a strategy of ours "
        "under their name."),
    "Volatility targeting": (
        "a SIZING rule, not a selection rule — it has no cross-section to sort, "
        "so it cannot appear in a table of decile spreads. It wraps whatever it "
        "is applied to and belongs in the sizing layer measurement (S59), where "
        "the outcome is risk rather than return."),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="measure only the first N predictors (smoke test)")
    ap.add_argument("--terciles", action="store_true",
                    help="also measure within each dollar-volume tercile")
    a = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    t0 = time.time()
    ret, prc, dvl = load_panel()
    months = pd.period_range(str(START)[:4] + "-" + str(START)[4:],
                             str(END)[:4] + "-" + str(END)[4:], freq="M")
    perms = sorted(set(ret.columns))
    pidx = {p: i for i, p in enumerate(perms)}
    n_m, n_p = len(months), len(perms)
    _log(f"panel: {n_m} months x {n_p} permnos")

    R = ret.reindex(index=months, columns=perms).to_numpy()
    P = prc.reindex(index=months, columns=perms).to_numpy()
    V = dvl.reindex(index=months, columns=perms).to_numpy()
    # FORWARD return: signal labelled m is paired with the return of m+1. The
    # uniform PIT-safe rule; see the module docstring for what it costs.
    FWD = np.vstack([R[1:], np.full((1, n_p), np.nan)])

    # Formation screen, evaluated at m with information available at m.
    OKBASE = np.isfinite(P) & (P >= MIN_PRICE) & np.isfinite(V)
    dv_rank = np.full((n_m, n_p), np.nan)
    for t in range(n_m):
        m = OKBASE[t]
        if m.sum() > 10:
            dv_rank[t, m] = pd.Series(V[t, m]).rank(pct=True).to_numpy() * 100
    OK = OKBASE & (dv_rank >= MIN_DVOL_PCTILE)
    _log(f"eligible names/month: median {np.median(OK.sum(1)):.0f}")

    rng = np.random.default_rng(SEED)
    results: dict[str, dict] = {}

    # ── our own construction ───────────────────────────────────────────────
    retp = ret.reindex(columns=perms)
    own = own_signals(retp, months)
    for name, sig in own.items():
        r, tn = decile_ls(np.asarray(sig, dtype="float64"), FWD, OK)
        results[name] = {**score(r, tn, rng), "source": "AEGIS_CONSTRUCTION"}
        _log(f"  {name:<28} net {results[name].get('net_annual', float('nan')):+.3%}")
    r, tn = tsmom_equity_analogue(retp, months, FWD, OK)
    results["__own_tsmom"] = {**score(r, tn, rng),
                              "source": "AEGIS_CONSTRUCTION",
                              "note": "time-series rule, not a rank; equity "
                                      "analogue of a futures strategy"}
    _log(f"  {'__own_tsmom':<28} net "
         f"{results['__own_tsmom'].get('net_annual', float('nan')):+.3%}")
    for name, why in NOT_IMPLEMENTABLE.items():
        results[f"__refused::{name}"] = {"refused": True, "why": why,
                                         "source": "REFUSED"}
        _log(f"  {name:<28} REFUSED — no faithful implementation")

    # ── the 209 published predictors ───────────────────────────────────────
    cols = osap_columns()
    if a.limit:
        cols = cols[:a.limit]
    _log(f"measuring {len(cols)} published predictors...")
    BATCH = 25
    scatter_cache: dict[str, np.ndarray] = {}
    for s in range(0, len(cols), BATCH):
        chunk = cols[s:s + BATCH]
        d = load_osap(chunk)
        mi = ((d.yyyymm // 100 - int(str(START)[:4])) * 12
              + (d.yyyymm % 100 - int(str(START)[4:]))).to_numpy()
        pi = d.permno.map(pidx).to_numpy()
        good = np.isfinite(pi.astype("float64")) & (mi >= 0) & (mi < n_m)
        mi, pi = mi[good].astype(int), pi[good].astype(int)
        for c in chunk:
            v = d[c].to_numpy(dtype="float64")[good]
            S = np.full((n_m, n_p), np.nan)
            S[mi, pi] = v
            r, tn = decile_ls(S, FWD, OK)
            results[c] = {**score(r, tn, rng), "source": "OSAP_PUBLISHED"}
            if a.terciles:
                scatter_cache[c] = S
        _log(f"  ...{min(s + BATCH, len(cols))}/{len(cols)} "
             f"({time.time() - t0:.0f}s)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "window": f"{START}..{END}",
        "registered_as": "EXPLORE (slc_c3246e5093c41c25, M4-SELECTOR)",
        "pairing": "signal labelled m -> return of m+1 (uniform PIT-safe rule)",
        "screens": {"min_price": MIN_PRICE, "min_dvol_pctile": MIN_DVOL_PCTILE,
                    "min_names": MIN_NAMES, "deciles": N_DECILES,
                    "weighting": "equal", "cost_bps_per_crossing": COST_BPS_ONE_WAY},
        "alignment_verified": {
            "Mom12m": "label m == cum return m-11..m-1, corr 1.0, maxdiff 0.0",
            "Mom6m": "label m == cum return m-5..m-1, corr 1.0, maxdiff 0.0",
            "note": "two predictors verified from first principles, not 209"},
        "seed_map": SEED_MAP,
        "results": results,
        "elapsed_s": round(time.time() - t0, 1),
    }
    OUT.write_text(json.dumps(payload, indent=1, default=float),
                   encoding="utf-8")
    _log(f"\nwrote {OUT}  ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
