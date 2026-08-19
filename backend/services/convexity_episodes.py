"""CONVEXITY-EPISODES-1 — the episode library CONVEXITY-PRESERVATION-1 will run on.

Order 17 §spec / Order 19 §3.2 / Order 20 §2.2. This module CONSTRUCTS the
dataset: threshold-crossing episodes (+20/+40/+75/+100), per-episode
management-arm outcomes, and a matched non-winner control per episode (§16 —
the informative unit is winner vs matched non-winner, never a gallery of
survivors). It deliberately computes NO aggregate comparison: "does trimming
destroy right-tail wealth" is the registered trial's question
(CONVEXITY-PRESERVATION-1, submitted to the daemon, unrun), and answering it
during dataset construction would be evaluation before registration.

EPISODE DEFINITION
==================
Entry dates are month-end trading days (the same grid as AEGIS-NET-PANEL-1).
An episode exists when the cumulative return from entry first touches a
threshold within MAX_CROSSING_DAYS trading days. One entry can spawn one
episode per threshold; the crossing DATE anchors everything downstream —
features are PIT at the crossing, arms trade from the crossing, the outcome
window is the H days after it.

THE TRAILING STOP IS AN ARM (§15's correct home)
================================================
Canon §15 killed the trailing stop as an EVALUATION (conditioning on the
path being evaluated). Here it is a MANAGEMENT ARM applied from a crossing
chosen by a rule that does not look at the post-crossing path, evaluated on
the same fixed forward window as every other arm — the trap is the control
design, not the candidate.

PER-DOLLAR ACCOUNTING
=====================
Every arm starts with $1 in the position at the crossing close. Proceeds of
any sale sit in cash at zero return (a deliberate, stated simplification —
the reinvestment question is a different experiment). Costs are one-way bps
on the traded fraction, charged when the trade happens.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from backend import config as _config
from backend.services import net_panel as NP

log = logging.getLogger(__name__)

LIBRARY = "CONVEXITY-EPISODES-1"
OUT_DIR = _config.OPTIMUS_LEDGER_DIR / "convexity"

THRESHOLDS = (0.20, 0.40, 0.75, 1.00)
#: A crossing must arrive within this many trading days of entry, or the
#: entry produced no episode at that threshold. Unbounded search would make
#: every 2013 entry "cross +100%" eventually, which studies the index, not
#: the management decision.
MAX_CROSSING_DAYS = 252
#: The management window after the crossing. Arms are scored at its end.
OUTCOME_DAYS = 60

#: Matching: exact calendar month of the crossing, nearest neighbour within
#: a caliper on standardized PIT characteristics (subset of
#: `winner_loser_factory.MATCH_DIMENSIONS` — the ones this panel can
#: compute; the full-covariate version is the CRSP extension).
MATCH_FEATURES = ("mom_252", "vol_63", "drawdown_252")
CALIPER_SD = 0.5

ARMS = ("hold", "trim_25", "trim_50", "exit_full",
        "trail_stop_20", "stop_vol_1_5")


class EpisodeRefused(RuntimeError):
    """An input the library needs is missing or unusable."""


# ── arms, per-dollar ───────────────────────────────────────────────────────
def arm_outcome(path: np.ndarray, arm: str, *, cost_one_way_bps: float,
                ann_vol_at_crossing: float) -> dict:
    """Terminal wealth of $1 managed by `arm` over the post-crossing path.

    `path` is prices from the crossing close (inclusive) to crossing+H;
    path[0] is the price the arm trades at. Returns terminal wealth and the
    day the arm's rule fired (None if it never did).
    """
    if len(path) < 2:
        raise EpisodeRefused("an outcome window needs at least two prices")
    rel = path / path[0]
    rate = cost_one_way_bps / 1e4
    fired: int | None = None

    if arm == "hold":
        invested, cash = 1.0, 0.0
    elif arm == "trim_25":
        invested, cash = 0.75, 0.25 * (1 - rate)
        fired = 0
    elif arm == "trim_50":
        invested, cash = 0.50, 0.50 * (1 - rate)
        fired = 0
    elif arm == "exit_full":
        return {"terminal_wealth": 1.0 * (1 - rate), "fired_day": 0}
    elif arm in ("trail_stop_20", "stop_vol_1_5"):
        if arm == "trail_stop_20":
            stop = 0.20
        else:
            # 1.5x the crossing-date annualized vol, scaled to a 21-day
            # move — a stop that adapts to the name instead of importing 20%
            # into a 60-vol biotech and a 15-vol staple alike.
            stop = float(np.clip(1.5 * ann_vol_at_crossing *
                                 np.sqrt(21 / 252), 0.05, 0.60))
        peak = rel[0]
        invested, cash = 1.0, 0.0
        for i in range(1, len(rel)):
            peak = max(peak, rel[i - 1])
            if rel[i] <= peak * (1.0 - stop):
                cash = rel[i] * (1 - rate)
                invested = 0.0
                fired = i
                break
        if invested > 0.0:
            return {"terminal_wealth": float(rel[-1]), "fired_day": None,
                    "stop_frac": stop}
        return {"terminal_wealth": float(cash), "fired_day": fired,
                "stop_frac": stop}
    else:
        raise EpisodeRefused(f"unknown arm {arm!r}; arms are {ARMS}")

    return {"terminal_wealth": float(invested * rel[-1] + cash),
            "fired_day": fired}


# ── detection ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Episode:
    ticker: str
    entry_date: str
    crossing_date: str
    threshold: float
    days_to_crossing: int
    gain_at_crossing: float


def detect_episodes(px: pd.DataFrame,
                    entry_dates: list[pd.Timestamp]) -> list[Episode]:
    """First-touch crossings per (name, entry, threshold), bounded in time."""
    positions = {d: i for i, d in enumerate(px.index)}
    out: list[Episode] = []
    values = {c: px[c].to_numpy(dtype=float) for c in px.columns}
    for d in entry_dates:
        e = positions[d]
        for name, v in values.items():
            p0 = v[e]
            if not np.isfinite(p0):
                continue
            end = min(e + MAX_CROSSING_DAYS, len(v) - 1)
            if end <= e:
                continue
            window = v[e + 1:end + 1] / p0 - 1.0
            for thr in THRESHOLDS:
                hit = np.flatnonzero(window >= thr)
                if hit.size == 0:
                    continue
                k = int(hit[0]) + 1
                out.append(Episode(
                    ticker=name, entry_date=str(d.date()),
                    crossing_date=str(px.index[e + k].date()),
                    threshold=thr, days_to_crossing=k,
                    gain_at_crossing=float(v[e + k] / p0 - 1.0)))
    return out


# ── matched non-winners (§16) ──────────────────────────────────────────────
def grid_features(px: pd.DataFrame,
                  grid: list[pd.Timestamp]) -> dict[str, pd.DataFrame]:
    """MATCH_FEATURES per name, PIT at each grid date, keyed by 'YYYY-MM'.

    Matching characteristics are measured on a COMMON grid (the last
    month-end at or before the crossing) for episode and candidates alike —
    comparing a crossing-day feature against month-end features would build
    the distance out of two different clocks.
    """
    out: dict[str, pd.DataFrame] = {}
    for d in grid:
        t = px.index.get_loc(d)
        feats = {}
        for name in px.columns:
            s = px[name].iloc[:t + 1].dropna()
            if len(s) < NP.MIN_HISTORY or pd.isna(px[name].iloc[t]):
                continue
            f = NP.price_features(s)
            feats[name] = {k: f[k] for k in MATCH_FEATURES}
        if feats:
            out[str(d.date())[:7]] = pd.DataFrame(feats).T
    return out


def match_control(episode: Episode, feats_by_month: dict[str, pd.DataFrame],
                  crossers_by_month: dict[str, set[str]]) -> dict:
    """The nearest non-crossing name, matched in the crossing's month.

    Candidates: names with grid features in the month that did NOT cross any
    threshold that month. Distance: standardized Euclidean over
    MATCH_FEATURES. Refuses (with the reason) rather than matching across
    the caliper — a bad match silently accepted poisons the pair, and the
    pair is the unit (§16).
    """
    month = episode.crossing_date[:7]
    # Features come from the month-end BEFORE the crossing's month — the
    # crossing month's own month-end postdates an early-month crossing, and
    # a matching distance built on future prices is a leak wearing a caliper.
    prev = (pd.Period(month, freq="M") - 1).strftime("%Y-%m")
    frame = feats_by_month.get(prev)
    if frame is None:
        return {"control": None,
                "reason": "no grid features for the pre-crossing month"}
    excluded = crossers_by_month.get(month, set()) | {episode.ticker}
    cands = frame.drop(index=[n for n in excluded if n in frame.index])
    if episode.ticker not in frame.index:
        return {"control": None,
                "reason": "episode name has no grid features in the month"}
    if cands.empty:
        return {"control": None, "reason": "no eligible non-crossing name "
                                           "alive in the crossing month"}
    mu, sd = frame.mean(), frame.std(ddof=1).replace(0.0, 1.0)
    z = (cands - mu) / sd
    z_ep = (frame.loc[episode.ticker] - mu) / sd
    dist = np.sqrt(((z - z_ep) ** 2).sum(axis=1))
    best = dist.idxmin()
    if float(dist[best]) > CALIPER_SD * np.sqrt(len(MATCH_FEATURES)):
        return {"control": None,
                "reason": "nearest candidate exceeds the caliper"}
    return {"control": best, "z_distance": float(dist[best])}


# ── materialization ────────────────────────────────────────────────────────
def materialize(px: pd.DataFrame, *, cost_lookup=None) -> dict:
    """Episodes + per-episode arm outcomes + matched control. No aggregates.

    `cost_lookup(ticker) -> one-way bps` defaults to the declared band
    midpoint (3.0bp one-way) — v1 charges every name alike and SAYS so; the
    per-name TAQ join is the registered trial's refinement.
    """
    cost = cost_lookup or (lambda _t: 3.0)
    entries = NP.decision_dates(px)
    episodes = detect_episodes(px, entries)

    # Names that crossed ANY threshold in a month, for control exclusion.
    crossers: dict[str, set[str]] = {}
    for ep in episodes:
        crossers.setdefault(ep.crossing_date[:7], set()).add(ep.ticker)

    feats_by_month = grid_features(px, entries)

    rows = []
    skipped = {"outcome_window_truncated": 0, "insufficient_history": 0}
    controls_missing: dict[str, int] = {}
    for ep in episodes:
        t = px.index.get_loc(pd.Timestamp(ep.crossing_date))
        if t + OUTCOME_DAYS >= len(px):
            skipped["outcome_window_truncated"] += 1
            continue
        s = px[ep.ticker].iloc[:t + 1].dropna()
        if len(s) < NP.MIN_HISTORY:
            skipped["insufficient_history"] += 1
            continue
        f = NP.price_features(s)
        path = px[ep.ticker].iloc[t:t + OUTCOME_DAYS + 1].to_numpy(float)
        row = {"ticker": ep.ticker, "entry_date": ep.entry_date,
               "crossing_date": ep.crossing_date,
               "threshold": ep.threshold,
               "days_to_crossing": ep.days_to_crossing,
               "gain_at_crossing": ep.gain_at_crossing,
               **{f"pit_{k}": v for k, v in f.items()}}
        for arm in ARMS:
            o = arm_outcome(path, arm, cost_one_way_bps=cost(ep.ticker),
                            ann_vol_at_crossing=f["vol_63"])
            row[f"tw_{arm}"] = o["terminal_wealth"]
            row[f"fired_{arm}"] = o["fired_day"]
        m = match_control(ep, feats_by_month, crossers)
        row["control"] = m.get("control")
        row["control_z_distance"] = m.get("z_distance")
        if m.get("control") is None:
            controls_missing[m["reason"]] = (
                controls_missing.get(m["reason"], 0) + 1)
        else:
            cpath = px[m["control"]].iloc[t:t + OUTCOME_DAYS + 1].to_numpy(
                float)
            row["control_tw_hold"] = float(cpath[-1] / cpath[0])
        rows.append(row)

    df = pd.DataFrame(rows)
    meta = {
        "library": LIBRARY,
        "thresholds": list(THRESHOLDS),
        "max_crossing_days": MAX_CROSSING_DAYS,
        "outcome_days": OUTCOME_DAYS,
        "arms": list(ARMS),
        "match_features": list(MATCH_FEATURES),
        "caliper_sd": CALIPER_SD,
        "cost_basis": "flat 3.0bp one-way unless a lookup was supplied; "
                      "the per-name TAQ join is the trial's refinement",
        "universe_note": "182 large-caps (the in-repo panel). A large-cap "
                         "universe UNDER-samples +75/+100 crossings by "
                         "construction; the CRSP extension is the registered "
                         "trial's substrate, and headline counts here must "
                         "not be quoted as base rates for the market.",
        "skipped": skipped,
        "controls_missing": controls_missing,
        "n_episodes": len(df),
        "episodes_by_threshold": ({f"{int(t*100)}pct": int(
            (df["threshold"] == t).sum()) for t in THRESHOLDS}
            if len(df) else {}),
        "no_aggregates_note": "per-episode outcomes only. The trim-vs-hold "
                              "comparison is CONVEXITY-PRESERVATION-1's "
                              "question and runs under its registration.",
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
    }
    return {"rows": df, "meta": meta}


def write(result: dict, out_dir: Path | str | None = None,
          version: str = "v1") -> dict[str, Path]:
    import json
    d = Path(out_dir or OUT_DIR)
    d.mkdir(parents=True, exist_ok=True)
    paths = {"parquet": d / f"episodes_{version}.parquet",
             "meta": d / f"episodes_{version}.meta.json"}
    result["rows"].to_parquet(paths["parquet"], index=False)
    paths["meta"].write_text(json.dumps(result["meta"], indent=2,
                                        default=str), encoding="utf-8")
    return paths
