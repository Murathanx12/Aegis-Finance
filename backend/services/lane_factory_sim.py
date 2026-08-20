"""LANE-FACTORY-SIM-1 — simulated lane books on the CRSP PIT substrate.

SIMULATION, clearly and everywhere: nothing here reads or writes the live
lane tables, the NAV write path, or any production surface. Books run
over the pulled `crsp_dsf_*.parquet` daily panel (2013–2024, delistings
included) with costs charged both ways, so rule variants can be tried by
the thousand where sprawl is free and the referee charges for every
attempt (design: docs/research/LANE_FACTORY_SIM_1.md).

PIT discipline: formation at a rebalance date uses only prices/returns
through that date; eligibility comes from the monthly PIT universe's own
flag for that calendar month. Delisting: when a name's daily series ends
while held, the position exits at its last daily price with the CRSP
delisting return applied — a delisting is an OUTCOME, never a silent
disappearance.

Known v1 approximations, declared:
- flat one-way cost (COST_ONE_WAY_BPS); per-name measured TAQ is the
  documented upgrade and a NEW sweep when it lands;
- when a winner-exempt lot's target weight cannot be traded, its weight
  share of investable capital stays in cash rather than being
  redistributed (conservative for the exempt arm);
- monthly dlret applied at exit day (daily dlret not in the pull).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from backend import config as _config

WRDS_DIR = _config.OPTIMUS_LEDGER_DIR / "wrds"
PIT_PATH = (_config.OPTIMUS_LEDGER_DIR / "crsp_pit" /
            "crsp_pit_monthly_v1.parquet")

#: Declared v1 cost basis; changing it mid-sweep is a new sweep.
COST_ONE_WAY_BPS = 3.0

#: The convexity trial's cell, transported.
WINNER_THRESHOLD = 0.40
WINNER_EXEMPT_DAYS = 60

#: permno x formation-date table of PREDICTED variance, installed by a
#: caller that has out-of-sample predictions (RISK-SIZING-VALUE-1). Left
#: None so `weighting='model_vol'` REFUSES rather than quietly degrading
#: to trailing vol — a silent fallback would make the challenger
#: identical to the incumbent and report the null as a result.
MODEL_PRED_VAR = None


class SimRefused(RuntimeError):
    """A required input is missing or unusable. Refused, not defaulted."""


@dataclass
class Panel:
    """Price/return matrices (dates × permnos) + PIT eligibility."""

    px: pd.DataFrame
    ret: pd.DataFrame
    elig_by_month: dict          # Period('M') -> set of permnos
    dlret: pd.Series             # permno -> last delisting return
    last_day: pd.Series          # permno -> last trading date


def load_panel(years: tuple[int, int] = (2013, 2024),
               univ_path=None) -> Panel:
    """`univ_path` overrides the PIT universe file — the early-era
    confirmation slice passes `crsp_pit_monthly_early.parquet`."""
    parts = []
    for yr in range(years[0], years[1] + 1):
        p = WRDS_DIR / f"crsp_dsf_{yr}.parquet"
        if not p.exists():
            raise SimRefused(f"{p.name} missing — pull before simulating")
        parts.append(pd.read_parquet(
            p, columns=["permno", "date", "prc", "ret"]))
    df = pd.concat(parts, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df["permno"] = df["permno"].astype(int)
    df["prc"] = df["prc"].abs()          # negative = bid/ask midpoint
    px = df.pivot_table(index="date", columns="permno", values="prc",
                        aggfunc="last").sort_index()
    ret = df.pivot_table(index="date", columns="permno", values="ret",
                         aggfunc="last").sort_index()

    upath = Path(univ_path) if univ_path else PIT_PATH
    if not upath.exists():
        raise SimRefused(f"{upath} missing")
    u = pd.read_parquet(upath)
    u["date"] = pd.to_datetime(u["date"])
    u["permno"] = u["permno"].astype(int)
    elig = {per: set(g.loc[g["eligible"], "permno"])
            for per, g in u.groupby(u["date"].dt.to_period("M"))}
    dl = (u.dropna(subset=["dlret"]).groupby("permno")["dlret"].last())
    last_day = df.groupby("permno")["date"].max()
    return Panel(px=px, ret=ret, elig_by_month=elig, dlret=dl,
                 last_day=last_day)


# ── signals: vectorized over the whole cross-section at a date ─────────────
def mom_12_1_at(panel: Panel, asof: pd.Timestamp) -> pd.Series:
    hist = panel.px.loc[:asof]
    if len(hist) < 252:
        return pd.Series(dtype=float)
    return (hist.iloc[-21] / hist.iloc[-252] - 1.0).dropna()


def inv_vol_63_at(panel: Panel, asof: pd.Timestamp) -> pd.Series:
    hist = panel.ret.loc[:asof].iloc[-63:]
    sd = hist.std(ddof=1)
    n = hist.notna().sum()
    sd = sd[(n >= 40) & (sd > 0)]
    return 1.0 / sd


#: trailing window for the min-variance covariance estimate
MIN_VAR_LOOKBACK = 252


def _min_var_weights(panel: Panel, asof: pd.Timestamp,
                     picks: list) -> dict:
    """Long-only minimum-variance weights over `picks`.

    Uses the programme's own denoised covariance (Marchenko-Pastur) —
    with ~50 names and 252 observations the sample covariance is badly
    conditioned and its inverse would be dominated by noise eigenvalues,
    which is exactly the failure the denoiser exists to prevent.

    Long-only is imposed by clipping the analytic solution and
    renormalising rather than by a QP. That is an approximation and is
    declared as one: it is enough to answer "does covariance awareness
    change the book", which is the question, and it is not a claim to
    have found the optimal long-only portfolio.
    """
    hist = panel.ret.loc[:asof].iloc[-MIN_VAR_LOOKBACK:]
    cols = [p for p in picks if p in hist.columns]
    sub = hist[cols].dropna(axis=1, thresh=int(0.8 * len(hist)))
    sub = sub.dropna(axis=0, how="any")
    if sub.shape[1] < 5 or sub.shape[0] < 60:
        return {p: 1.0 / len(picks) for p in picks}
    try:
        from backend.services.covariance import estimate_covariance
        cov = estimate_covariance(sub, method="denoised").to_numpy(float)
    except Exception:                                          # noqa: BLE001
        cov = sub.cov().to_numpy(float)
    n = cov.shape[0]
    cov = cov + np.eye(n) * 1e-10
    try:
        inv1 = np.linalg.solve(cov, np.ones(n))
    except np.linalg.LinAlgError:
        return {p: 1.0 / len(picks) for p in picks}
    w = np.clip(inv1, 0.0, None)
    if w.sum() <= 0:
        return {p: 1.0 / len(picks) for p in picks}
    w = w / w.sum()
    out = {p: float(x) for p, x in zip(sub.columns, w)}
    # names dropped for insufficient history keep an equal-weight share
    miss = [p for p in picks if p not in out]
    if miss:
        share = len(miss) / len(picks)
        out = {p: v * (1 - share) for p, v in out.items()}
        out.update({p: share / len(miss) for p in miss})
    return out


def prepare_extras(panel: Panel, finratio_path=None) -> dict:
    """One-time precomputation for the MEGA-SWEEP signal set.

    finratio pivots are indexed by PUBLIC_DATE (the WRDS availability
    stamp), so an as-of lookup can never read a ratio before the world
    could; the streak matrix reuses STREAK-EVIDENCE-1's run-length
    definition verbatim.
    """
    from backend.services.streak_evidence import _streak_matrix
    fr = pd.read_parquet(finratio_path or
                         WRDS_DIR / "finratio_monthly.parquet",
                         columns=["permno", "public_date", "bm", "roe"])
    fr["public_date"] = pd.to_datetime(fr["public_date"])
    piv = {c: fr.pivot_table(index="public_date", columns="permno",
                             values=c, aggfunc="last").sort_index()
           for c in ("bm", "roe")}
    return {"finratio": piv, "streak": _streak_matrix(panel.ret)}


def _finratio_at(extras: dict, col: str, asof: pd.Timestamp) -> pd.Series:
    piv = extras["finratio"][col].loc[:asof]
    if not len(piv):
        return pd.Series(dtype=float)
    return piv.iloc[-1].dropna()


#: MEGA-SWEEP-1 signal registry (declaration doc is the authority).
#: Every signal returns "higher = better" scores at the as-of date.
SIGNALS = {
    "mom_12_1": lambda pn, t, ex: mom_12_1_at(pn, t),
    "mom_63": lambda pn, t, ex: (
        pn.px.loc[:t].iloc[-1] / pn.px.loc[:t].iloc[-63] - 1.0).dropna()
        if len(pn.px.loc[:t]) >= 63 else pd.Series(dtype=float),
    "rev_21": lambda pn, t, ex: (
        -(pn.px.loc[:t].iloc[-1] / pn.px.loc[:t].iloc[-21] - 1.0)).dropna()
        if len(pn.px.loc[:t]) >= 21 else pd.Series(dtype=float),
    "low_vol": lambda pn, t, ex: inv_vol_63_at(pn, t),
    "value_bm": lambda pn, t, ex: _finratio_at(ex, "bm", t),
    "quality_roe": lambda pn, t, ex: _finratio_at(ex, "roe", t),
    "streak_7_avoid": lambda pn, t, ex: (
        mom_12_1_at(pn, t)
        .drop(labels=[c for c in ex["streak"].columns
                      if ex["streak"].loc[:t].iloc[-1].get(c, 0) >= 7],
              errors="ignore")),
}


# ── the book engine ────────────────────────────────────────────────────────
@dataclass
class _Lot:
    shares: float
    entry: float
    exempt_until: int | None = None      # day index, inclusive


def run_book(panel: Panel, *, weighting: str, winner_handling: str,
             start: str = "2014-06-30", end: str = "2024-11-30",
             top_n: int | None = 50, signal: str = "mom_12_1",
             extras: dict | None = None, avoid_streak: int | None = None,
             weight_cap: float | None = None,
             cost_one_way_bps: float = COST_ONE_WAY_BPS) -> dict:
    """One simulated lane book: `signal` top-N, monthly rebalance, daily
    NAV. `weighting`: 'equal'|'inverse_vol'|'rank'. `winner_handling`:
    'trim' (rebalance sells winners back to weight — the live lanes'
    implicit behaviour) | 'exempt' (+40% winners keep their shares for
    60 trading days after crossing). `signal='none'` with top_n=None is
    the baseline book: equal-weight everything eligible."""
    if signal != "none" and signal not in SIGNALS:
        raise SimRefused(f"unknown signal {signal!r}; declared set is "
                         f"{sorted(SIGNALS)} + 'none'")
    if signal in ("value_bm", "quality_roe", "streak_7_avoid") \
            and extras is None:
        raise SimRefused(f"{signal} needs prepared extras (finratio/"
                         "streak) — refusing to run without its inputs")
    if avoid_streak is not None and (extras is None
                                     or "streak" not in extras):
        raise SimRefused("avoid_streak needs the prepared streak matrix "
                         "— refusing to run without its input")
    if weighting not in ("equal", "inverse_vol", "rank", "model_vol",
                         "min_var"):
        raise SimRefused(f"unknown weighting {weighting!r}")
    if weighting == "model_vol" and MODEL_PRED_VAR is None:
        raise SimRefused(
            "weighting='model_vol' needs MODEL_PRED_VAR — a permno x "
            "formation-date table of PREDICTED variance. Refusing rather "
            "than silently falling back to trailing vol, which would make "
            "the challenger and the incumbent the same book and report a "
            "null difference as a finding.")
    if winner_handling not in ("trim", "exempt"):
        raise SimRefused(f"unknown winner_handling {winner_handling!r}")
    rate = cost_one_way_bps / 1e4
    px = panel.px
    dates = px.index
    sched = iter(pd.date_range(start, end, freq="BME"))
    next_rb = next(sched, None)

    cash, lots = 1.0, {}
    nav_rows: list[tuple] = []
    turnover, cost_paid, n_delist_exits, n_exemptions = 0.0, 0.0, 0, 0
    n_filter_blocked = 0
    row_of = {d: i for i, d in enumerate(dates)}

    def mark(d) -> float:
        v = cash
        for p, lot in lots.items():
            price = px.at[d, p]
            if np.isfinite(price):
                v += lot.shares * price
        return float(v)

    for d in dates:
        if d < pd.Timestamp(start):
            continue
        if d > pd.Timestamp(end):
            break
        di = row_of[d]

        # delisting exits
        for p in [p for p in list(lots) if panel.last_day.get(p, d) < d]:
            lot = lots.pop(p)
            series = px[p].loc[:d].dropna()
            last_px = float(series.iloc[-1]) if len(series) else 0.0
            dl = float(panel.dlret.get(p, 0.0))
            cash += lot.shares * last_px * (1.0 + dl) * (1 - rate)
            n_delist_exits += 1

        if next_rb is not None and d >= next_rb:
            while next_rb is not None and d >= next_rb:
                next_rb = next(sched, None)
            asof = d
            elig = panel.elig_by_month.get(asof.to_period("M"), set())
            if signal == "none":
                have = panel.px.loc[:asof].iloc[-1].dropna().index
                picks = [p for p in have if p in elig]
            else:
                sig = SIGNALS[signal](panel, asof, extras)
                sig = sig[np.isfinite(sig)]
                sig = sig[sig.index.isin(elig)].sort_values(
                    ascending=False)
                picks = list(sig.index[:top_n] if top_n else sig.index)
            if avoid_streak is not None and picks:
                srow = extras["streak"].loc[:asof].iloc[-1]
                blocked = [p for p in picks
                           if p not in lots
                           and srow.get(p, 0) >= avoid_streak]
                n_filter_blocked += len(blocked)
                picks = [p for p in picks if p not in blocked]
            if not picks:
                nav_rows.append((d, mark(d)))
                continue
            if weighting == "min_var":
                # Covariance-AWARE sizing. Inverse-vol weighting of any
                # flavour optimises each name's MARGINAL variance and is
                # blind to how the names co-move, so it can concentrate a
                # book into one correlated cluster while every individual
                # forecast is good. This arm is the control for that:
                # long-only minimum variance on a denoised covariance of
                # the picks' trailing daily returns.
                w = _min_var_weights(panel, asof, picks)
            elif weighting == "model_vol":
                # inverse PREDICTED vol, as-of: only predictions stamped
                # on or before the rebalance date are visible
                hist = MODEL_PRED_VAR.loc[:asof]
                pv = (hist.iloc[-1] if len(hist)
                      else pd.Series(dtype=float))
                pv = pv[pv.index.isin(picks)].dropna()
                pv = pv[pv > 0]
                if len(pv):
                    iv = 1.0 / np.sqrt(pv)
                    w = {p: float(x / iv.sum()) for p, x in iv.items()}
                    # names the model has no view on keep equal weight
                    miss = [p for p in picks if p not in w]
                    if miss:
                        share = len(miss) / len(picks)
                        w = {p: v * (1 - share) for p, v in w.items()}
                        w.update({p: share / len(miss) for p in miss})
                else:
                    w = {p: 1.0 / len(picks) for p in picks}
            elif weighting == "equal":
                w = {p: 1.0 / len(picks) for p in picks}
            elif weighting == "rank":
                ranks = np.arange(len(picks), 0, -1, dtype=float)
                ranks /= ranks.sum()
                w = {p: float(r) for p, r in zip(picks, ranks)}
            else:
                iv = inv_vol_63_at(panel, asof)
                iv = iv[iv.index.isin(picks)]
                w = ({p: float(x / iv.sum()) for p, x in iv.items()}
                     if len(iv) and iv.sum() > 0
                     else {p: 1.0 / len(picks) for p in picks})

            # Optional concentration cap, applied to ANY weighting so the
            # cap and the estimator can be varied independently. Inverse-
            # volatility sizing is unbounded by construction: a name the
            # estimator thinks is very quiet attracts arbitrarily large
            # weight, and a MODEL can output a far smaller variance than
            # a 63-day trailing window ever will. Excess is redistributed
            # pro-rata over the uncapped names, iterating to a fixed
            # point so redistribution cannot push a name back over.
            if weight_cap is not None and w:
                cap = float(weight_cap) / len(w)
                for _ in range(50):
                    over = {p: v for p, v in w.items() if v > cap}
                    if not over:
                        break
                    excess = sum(v - cap for v in over.values())
                    rest = {p: v for p, v in w.items() if v <= cap}
                    if not rest or sum(rest.values()) <= 0:
                        w = {p: 1.0 / len(w) for p in w}
                        break
                    tot = sum(rest.values())
                    w = {**{p: cap for p in over},
                         **{p: v + excess * v / tot
                            for p, v in rest.items()}}

            nav = mark(d)
            frozen = {}
            if winner_handling == "exempt":
                for p, lot in lots.items():
                    price = px.at[d, p]
                    if not np.isfinite(price):
                        continue
                    if (lot.exempt_until is None
                            and price / lot.entry - 1.0 >= WINNER_THRESHOLD):
                        lot.exempt_until = di + WINNER_EXEMPT_DAYS
                        n_exemptions += 1
                    if lot.exempt_until is not None and di <= lot.exempt_until:
                        frozen[p] = lot
            investable = nav - sum(l.shares * px.at[d, p]
                                   for p, l in frozen.items())
            investable = max(investable, 0.0)

            new_lots, traded = dict(frozen), 0.0
            for p in set(w) | (set(lots) - set(frozen)):
                price = px.at[d, p] if p in px.columns else np.nan
                if not np.isfinite(price) or price <= 0:
                    continue
                if p in frozen:
                    continue                      # weight share stays cash
                tgt_val = w.get(p, 0.0) * investable
                old = lots.get(p)
                old_val = old.shares * price if old else 0.0
                traded += abs(tgt_val - old_val)
                if tgt_val > 0:
                    new_lots[p] = _Lot(shares=tgt_val / price,
                                       entry=old.entry if old else price,
                                       exempt_until=old.exempt_until
                                       if old else None)
            cost = traded * rate
            held = sum(l.shares * px.at[d, p] for p, l in new_lots.items()
                       if np.isfinite(px.at[d, p]))
            cash = nav - held - cost
            cost_paid += cost
            turnover += traded / max(nav, 1e-9)
            lots = new_lots

        nav_rows.append((d, mark(d)))

    nav = pd.Series(dict(nav_rows)).sort_index()
    mret = nav.resample("ME").last().pct_change().dropna()
    return {"signal": signal, "top_n": top_n,
            "weighting": weighting, "winner_handling": winner_handling,
            "monthly_returns": mret, "nav": nav,
            "total_return": float(nav.iloc[-1] / nav.iloc[0] - 1.0),
            "ann_vol": float(mret.std(ddof=1) * np.sqrt(12)),
            "max_drawdown": float((nav / nav.cummax() - 1.0).min()),
            "turnover_oneway_total": float(turnover),
            "cost_paid_frac": float(cost_paid),
            "n_delist_exits": int(n_delist_exits),
            "n_winner_exemptions": int(n_exemptions),
            "n_filter_blocked_buys": int(n_filter_blocked),
            "label": "SIMULATION — LANE-FACTORY-SIM-1, never a track record"}
