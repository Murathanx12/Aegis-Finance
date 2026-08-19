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


def load_panel(years: tuple[int, int] = (2013, 2024)) -> Panel:
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

    if not PIT_PATH.exists():
        raise SimRefused(f"{PIT_PATH} missing")
    u = pd.read_parquet(PIT_PATH)
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


# ── the book engine ────────────────────────────────────────────────────────
@dataclass
class _Lot:
    shares: float
    entry: float
    exempt_until: int | None = None      # day index, inclusive


def run_book(panel: Panel, *, weighting: str, winner_handling: str,
             start: str = "2014-06-30", end: str = "2024-11-30",
             top_n: int = 50,
             cost_one_way_bps: float = COST_ONE_WAY_BPS) -> dict:
    """One simulated lane book: mom_12_1 top-N, monthly rebalance,
    daily NAV. `weighting`: 'equal'|'inverse_vol'. `winner_handling`:
    'trim' (rebalance sells winners back to weight — the live lanes'
    implicit behaviour) | 'exempt' (+40% winners keep their shares for
    60 trading days after crossing)."""
    if weighting not in ("equal", "inverse_vol"):
        raise SimRefused(f"unknown weighting {weighting!r}")
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
            sig = mom_12_1_at(panel, asof)
            sig = sig[sig.index.isin(elig)].sort_values(ascending=False)
            picks = list(sig.index[:top_n])
            if not picks:
                nav_rows.append((d, mark(d)))
                continue
            if weighting == "equal":
                w = {p: 1.0 / len(picks) for p in picks}
            else:
                iv = inv_vol_63_at(panel, asof)
                iv = iv[iv.index.isin(picks)]
                w = ({p: float(x / iv.sum()) for p, x in iv.items()}
                     if len(iv) and iv.sum() > 0
                     else {p: 1.0 / len(picks) for p in picks})

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
    return {"weighting": weighting, "winner_handling": winner_handling,
            "monthly_returns": mret, "nav": nav,
            "total_return": float(nav.iloc[-1] / nav.iloc[0] - 1.0),
            "ann_vol": float(mret.std(ddof=1) * np.sqrt(12)),
            "max_drawdown": float((nav / nav.cummax() - 1.0).min()),
            "turnover_oneway_total": float(turnover),
            "cost_paid_frac": float(cost_paid),
            "n_delist_exits": int(n_delist_exits),
            "n_winner_exemptions": int(n_exemptions),
            "label": "SIMULATION — LANE-FACTORY-SIM-1, never a track record"}
