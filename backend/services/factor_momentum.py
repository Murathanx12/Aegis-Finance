"""FACTOR-MOMENTUM-1 machinery — deciding logic lives in the prereg.

Question (docs/TRIALS/PREREG_FACTOR_MOMENTUM_1.md): does monthly
reallocation toward recently-winning FACTORS beat holding all factors at
equal weight, net of declared costs, on the JKP US set (153 long-short
factors, 1926–2025)?

Everything here is mechanical: book construction, the paired contrast,
the mean-masked §64 audit, and planted rehearsal worlds. The verdict
reuses the tournament's three-way judge.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backend import config as _config
from backend.services.net_tournament import (bootstrap_block_dates,
                                             head_verdicts)
from backend.services.world_model import block_bootstrap_paired

JKP_CSV = (_config.OPTIMUS_LEDGER_DIR / "jkp" /
           "usa_all_factors_monthly_vw_cap.csv")

#: Registered primary parameters (prereg; changing any is an amendment).
FORMATION_MONTHS = 12          # t-12 .. t-2 (12-1 convention)
SKIP_MONTHS = 1
TOP_FRACTION = 1 / 3
MIN_FACTORS_PER_MONTH = 100
#: Effective one-way cost per unit of factor notional traded. A $1
#: long-short factor is two $1 stock legs; 10bp per leg one-way => 20bp.
EFFECTIVE_COST_ONE_WAY_BPS = 20.0
ECONOMIC_BAR_MONTHLY = 0.005 / 12       # 0.5%/yr, the prereg's bar


class FactorMomentumRefused(RuntimeError):
    """A required input is missing or unusable. Refused, not defaulted."""


def load_jkp() -> pd.DataFrame:
    if not JKP_CSV.exists():
        raise FactorMomentumRefused(f"{JKP_CSV} missing — download first")
    df = pd.read_csv(JKP_CSV, usecols=["name", "date", "ret"])
    df["date"] = pd.to_datetime(df["date"])
    return df.pivot_table(index="date", columns="name", values="ret",
                          aggfunc="last").sort_index()


def build_books(wide: pd.DataFrame, *,
                formation: int = FORMATION_MONTHS,
                skip: int = SKIP_MONTHS,
                top_fraction: float = TOP_FRACTION,
                cost_one_way_bps: float = EFFECTIVE_COST_ONE_WAY_BPS,
                min_factors: int = MIN_FACTORS_PER_MONTH) -> pd.DataFrame:
    """Monthly returns of the momentum book and the static book, net.

    Formation at month t uses factor returns t-formation .. t-skip-1
    inclusive — strictly before the held month t. A factor is eligible
    at t only with a complete formation history and a return at t.
    Months with < min_factors eligible are dropped AND counted.
    """
    rate = cost_one_way_bps / 1e4
    dates = wide.index
    rows = []
    prev_w_mom: pd.Series | None = None
    prev_w_stat: pd.Series | None = None
    n_thin = 0
    for i in range(formation + skip, len(dates)):
        t = dates[i]
        form = wide.iloc[i - formation - skip: i - skip]
        held = wide.iloc[i]
        elig = form.notna().all(axis=0) & held.notna()
        names = elig[elig].index
        if len(names) < min_factors:
            n_thin += 1
            continue
        score = form[names].sum(axis=0)
        k = max(1, int(round(len(names) * top_fraction)))
        top = score.sort_values(ascending=False).index[:k]

        w_mom = pd.Series(0.0, index=names)
        w_mom[top] = 1.0 / k
        w_stat = pd.Series(1.0 / len(names), index=names)

        def _net(w, prev):
            gross = float((w * held[w.index]).sum())
            if prev is None:
                turn = float(w.abs().sum())
            else:
                joint = w.index.union(prev.index)
                turn = float((w.reindex(joint, fill_value=0.0)
                              - prev.reindex(joint, fill_value=0.0))
                             .abs().sum())
            return gross - turn * rate, turn

        r_mom, turn_mom = _net(w_mom, prev_w_mom)
        r_stat, turn_stat = _net(w_stat, prev_w_stat)
        prev_w_mom, prev_w_stat = w_mom, w_stat
        rows.append((t, r_mom, r_stat, turn_mom, turn_stat, len(names)))

    out = pd.DataFrame(rows, columns=["date", "mom", "static",
                                      "turn_mom", "turn_static",
                                      "n_factors"]).set_index("date")
    out.attrs["n_thin_months_dropped"] = n_thin
    out.attrs["cost_one_way_bps"] = cost_one_way_bps
    return out


def paired_contrast(books: pd.DataFrame) -> dict:
    d = (books["mom"] - books["static"]).to_numpy(float)
    dates = books.index.to_numpy(dtype="datetime64[D]")
    block = bootstrap_block_dates(dates, 252)   # 12-month formation overlap
    out = block_bootstrap_paired(d, dates, block_days=block,
                                 seed=20260819).as_dict()
    out["block_days_derived"] = block
    out["ann_mean_diff"] = float(np.mean(d) * 12)
    return out


def masked_power_audit(books: pd.DataFrame) -> dict:
    """§64: dispersion only. The mean is never returned or printed."""
    c = paired_contrast(books)
    return {"audit": "FACTOR-MOMENTUM-PRIMARY-POWER-1 (mean-masked)",
            "n_months": int(len(books)),
            "n_thin_months_dropped": books.attrs["n_thin_months_dropped"],
            "block_days_derived": c["block_days_derived"],
            "n_effective_blocks": float(c["n_effective"]),
            "bootstrap_se_monthly": round(float(c["se"]), 6),
            "mde_80pct_power_monthly": round(
                float(c["mde_80pct_power"]), 6),
            "economic_bar_monthly": ECONOMIC_BAR_MONTHLY,
            "answerable_at_bar": bool(
                c["mde_80pct_power"] <= ECONOMIC_BAR_MONTHLY)}


def verdict(books: pd.DataFrame) -> dict:
    c = paired_contrast(books)
    v = head_verdicts({"factor_momentum": c},
                      economic_bar=ECONOMIC_BAR_MONTHLY)["factor_momentum"]
    relabel = {"COMPLEX_WINS": "MOMENTUM_WINS",
               "LINEAR_NONINFERIOR": "STATIC_NONINFERIOR",
               "NOT_ESTABLISHED": "NOT_ESTABLISHED"}
    v["verdict"] = relabel[v["verdict"]]
    v["contrast"] = c
    return v


# ── rehearsal worlds with declared answers ─────────────────────────────────
WORLDS = {
    # persistent heterogeneous factor means => momentum book must win
    "persistent": ("MOMENTUM_WINS",),
    # iid equal-mean factors => reallocation buys nothing but turnover
    "null": ("STATIC_NONINFERIOR", "NOT_ESTABLISHED"),
    # mean-reverting factors => momentum must NOT be declared a winner
    "reverting": ("STATIC_NONINFERIOR", "NOT_ESTABLISHED"),
}


def synthetic_panel(world: str, *, n_factors: int = 153,
                    n_months: int = 900, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("1950-01-31", periods=n_months, freq="ME")
    if world == "persistent":
        mu = rng.normal(0.004, 0.006, n_factors)   # stable spread in means
        r = mu + rng.normal(0, 0.02, (n_months, n_factors))
    elif world == "null":
        r = rng.normal(0.002, 0.02, (n_months, n_factors))
    elif world == "reverting":
        r = np.zeros((n_months, n_factors))
        shock = rng.normal(0, 0.02, (n_months, n_factors))
        for t in range(n_months):
            r[t] = 0.002 + shock[t] - (0.5 * shock[t - 12]
                                       if t >= 12 else 0.0)
    else:
        raise FactorMomentumRefused(f"unknown world {world!r}")
    return pd.DataFrame(r, index=dates,
                        columns=[f"f{i:03d}" for i in range(n_factors)])
