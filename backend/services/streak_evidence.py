"""STREAK-EVIDENCE-1 machinery — deciding logic lives in the prereg.

Murat's coin parable, operationalized: after >=7 consecutive up-closes,
is the next 21 trading days' return different from what the name's
ordinary characteristics already predict? The control (§16) is a
same-date name matched on momentum and volatility WITHOUT a streak —
that subtraction is what makes the answer "beyond momentum".

Direction is measured, never assumed: persistence and reversal are the
two declared arms of one Holm family (m = 2).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backend.services.lane_factory_sim import Panel, load_panel
from backend.services.net_tournament import (bootstrap_block_dates,
                                             head_verdicts)
from backend.services.world_model import block_bootstrap_paired

#: Registered primary parameters.
STREAK_LEN = 7
FORWARD_DAYS = 21
CONTROL_MAX_STREAK = 4        # a control may not itself be mid-streak
ECONOMIC_BAR_21D = 0.0025     # ~3%/yr
MATCH_FEATURES = ("mom_12_1", "vol_63")


class StreakRefused(RuntimeError):
    """A required input is missing or unusable. Refused, not defaulted."""


def _streak_matrix(ret: pd.DataFrame) -> pd.DataFrame:
    """Running count of consecutive up days, per name (vectorized)."""
    up = (ret > 0).to_numpy()
    out = np.zeros_like(up, dtype=np.int32)
    run = np.zeros(up.shape[1], dtype=np.int32)
    for i in range(up.shape[0]):
        run = np.where(up[i], run + 1, 0)
        out[i] = run
    return pd.DataFrame(out, index=ret.index, columns=ret.columns)


def build_events(panel: Panel, *, streak_len: int = STREAK_LEN,
                 forward_days: int = FORWARD_DAYS,
                 control_max: int = CONTROL_MAX_STREAK) -> pd.DataFrame:
    """One row per (event, matched control): forward returns of both.

    Event: the FIRST day a name's up-streak reaches `streak_len` (one
    event per run, no overlap). Control: same date, PIT-eligible, streak
    <= control_max, nearest neighbour on standardized (mom_12_1, vol_63),
    drawn without replacement within the date. Events with no finite
    features, no candidate, or truncated forward windows are counted,
    never silently dropped.
    """
    ret, px = panel.ret, panel.px
    dates = ret.index
    streak = _streak_matrix(ret)
    is_event = (streak == streak_len)

    # forward 21d compounded return, shifted so row t holds t+1..t+21
    fwd = ((1.0 + ret).rolling(forward_days).apply(np.prod, raw=True)
           .shift(-forward_days) - 1.0)

    # features at t, all vectorized
    mom = px.shift(21) / px.shift(252) - 1.0
    vol = ret.rolling(63).std(ddof=1)

    rows, dropped = [], {"no_features": 0, "no_control": 0,
                         "no_forward": 0, "not_eligible": 0}
    for i, d in enumerate(dates):
        ev_names = ret.columns[is_event.iloc[i].to_numpy()]
        if len(ev_names) == 0:
            continue
        elig = panel.elig_by_month.get(d.to_period("M"), set())
        m_row, v_row = mom.iloc[i], vol.iloc[i]
        f_row = fwd.iloc[i]
        s_row = streak.iloc[i]
        pool_mask = ((s_row <= control_max) & m_row.notna()
                     & v_row.notna() & f_row.notna())
        pool = [p for p in ret.columns[pool_mask.to_numpy()] if p in elig]
        if not pool:
            dropped["no_control"] += len(ev_names)
            continue
        pm = m_row[pool].to_numpy(float)
        pv = v_row[pool].to_numpy(float)
        m_sd = pm.std() or 1.0
        v_sd = pv.std() or 1.0
        used: set = set()
        for p in ev_names:
            if p not in elig:
                dropped["not_eligible"] += 1
                continue
            if not (np.isfinite(m_row.get(p, np.nan))
                    and np.isfinite(v_row.get(p, np.nan))):
                dropped["no_features"] += 1
                continue
            if not np.isfinite(f_row.get(p, np.nan)):
                dropped["no_forward"] += 1
                continue
            dist = (((pm - m_row[p]) / m_sd) ** 2
                    + ((pv - v_row[p]) / v_sd) ** 2)
            order = np.argsort(dist)
            ctrl = None
            for j in order:
                cand = pool[j]
                if cand != p and cand not in used:
                    ctrl = cand
                    break
            if ctrl is None:
                dropped["no_control"] += 1
                continue
            used.add(ctrl)
            rows.append((d, p, ctrl, float(f_row[p]), float(f_row[ctrl])))

    ev = pd.DataFrame(rows, columns=["date", "permno", "control",
                                     "fwd_event", "fwd_control"])
    ev.attrs["dropped"] = dropped
    return ev


def verdict(events: pd.DataFrame) -> dict:
    """Two declared directions through the Holm judge (m = 2)."""
    if len(events) < 50:
        raise StreakRefused(f"only {len(events)} matched events — no")
    d = (events["fwd_event"] - events["fwd_control"]).to_numpy(float)
    dates = pd.to_datetime(events["date"]).to_numpy(dtype="datetime64[D]")
    block = bootstrap_block_dates(dates, FORWARD_DAYS)
    inf = block_bootstrap_paired(d, dates, block_days=block,
                                 seed=20260819).as_dict()
    inf["block_days_derived"] = block
    neg = {**inf, "mean": -inf["mean"], "ci_lo": -inf["ci_hi"],
           "ci_hi": -inf["ci_lo"]}
    v = head_verdicts({"persistence": inf, "reversal": neg},
                      economic_bar=ECONOMIC_BAR_21D)
    if v["persistence"]["verdict"] == "COMPLEX_WINS":
        label, direction = "STREAK_INFORMATIVE", "persistence"
    elif v["reversal"]["verdict"] == "COMPLEX_WINS":
        label, direction = "STREAK_INFORMATIVE", "reversal"
    elif (v["persistence"]["verdict"] == "LINEAR_NONINFERIOR"
          and v["reversal"]["verdict"] == "LINEAR_NONINFERIOR"):
        label, direction = "STREAK_UNINFORMATIVE", None
    else:
        label, direction = "NOT_ESTABLISHED", None
    return {"verdict": label, "direction": direction,
            "n_events": int(len(events)),
            "dropped": events.attrs.get("dropped", {}),
            "contrast": inf, "arms": v}


def masked_power_audit(events: pd.DataFrame) -> dict:
    d = (events["fwd_event"] - events["fwd_control"]).to_numpy(float)
    dates = pd.to_datetime(events["date"]).to_numpy(dtype="datetime64[D]")
    block = bootstrap_block_dates(dates, FORWARD_DAYS)
    inf = block_bootstrap_paired(d, dates, block_days=block,
                                 seed=20260819).as_dict()
    return {"audit": "STREAK-PRIMARY-POWER-1 (mean-masked)",
            "n_events": int(len(events)),
            "n_event_dates": int(pd.Series(dates).nunique()),
            "block_days_derived": block,
            "n_effective_blocks": float(inf["n_effective"]),
            "bootstrap_se": round(float(inf["se"]), 6),
            "mde_80pct_power": round(float(inf["mde_80pct_power"]), 6),
            "economic_bar_21d": ECONOMIC_BAR_21D,
            "answerable_at_bar": bool(
                inf["mde_80pct_power"] <= ECONOMIC_BAR_21D)}


# ── rehearsal worlds ───────────────────────────────────────────────────────
def synthetic_events(world: str, *, n: int = 3000,
                     seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.to_datetime("2015-01-02") + pd.to_timedelta(
        rng.integers(0, 2500, n), unit="D")
    noise = rng.normal(0, 0.06, n)
    ctrl = rng.normal(0.004, 0.06, n)
    if world == "persistence":
        ev = ctrl + 0.010 + noise * 0.1
    elif world == "reversal":
        ev = ctrl - 0.010 + noise * 0.1
    elif world == "null":
        ev = ctrl + noise * 0.1
    else:
        raise StreakRefused(f"unknown world {world!r}")
    df = pd.DataFrame({"date": dates.astype(str), "permno": range(n),
                       "control": range(n), "fwd_event": ev,
                       "fwd_control": ctrl})
    df.attrs["dropped"] = {}
    return df


WORLD_EXPECT = {
    "persistence": ("STREAK_INFORMATIVE",),
    "reversal": ("STREAK_INFORMATIVE",),
    "null": ("STREAK_UNINFORMATIVE", "NOT_ESTABLISHED"),
}
