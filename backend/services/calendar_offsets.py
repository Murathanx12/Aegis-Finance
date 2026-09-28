"""The quarterly-offset triplet, and the verdict it owes every hold-3 lead.

Licence: PRODUCT_EXPERIMENT diagnostics ($0, no LLM). Lane M1 of
`docs/ROADMAP_2026-09-28_MEASURE_BEFORE_YOU_ADD.md`.

WHY. The engine starts every hold-3 rule on the panel's first selectable month
(2017-01-31), so every quarterly rule inherits ONE calendar: decisions in
Jan/Apr/Jul/Oct. `mom_12_1_q` was run at all three offsets on 2026-09-26
(`strategy_library._diagnostic_controls`) and its 2024-26 excess vs SPY was
+37.9 / -5.0 / +8.4 pp: the headline row is the best of three draws. The
adversarial review of 2026-09-28 (§1, §5.2) found that the two leads now on the
forward clock were never given the same check. This module gives it to any
hold-3 rule, through the library's own engine (`run_strategy` with
`rebalance_months`), costs on, and reads each offset against its
characteristic-matched twin (`matched_twins`), not only against SPY.

THE VERDICT RULE (declared here, in code, BEFORE the first run of 2026-09-28):

* An offset BEATS its twin when the full-window mean monthly (rule - twin21)
  is > 0 AND its t on non-overlapping REBALANCE BLOCKS is >= `BEATS_T`.
  twin21 = the mean of 21 seeded matched draws (the family pool's estimator).
  The t is blocked on the rule's own rebalance periods, because a hold-3 book
  holds the same names for three months and a monthly t would count each
  decision three times (2026-09-24 lesson: re-derive the blocking from the
  parameter being varied -- here the calendar).
* An offset LOSES to its twin when that full-window mean is <= 0.
* ROBUST_TO_CALENDAR: every offset BEATS its twin.
* CALENDAR_ARTEFACT: at least one offset BEATS its twin and at least one other
  LOSES to it -- the sign of the result depends on which month the calendar
  starts in.
* CANNOT_DISTINGUISH: anything else (e.g. every offset positive but not every
  one clears t >= 2, or none does).

The verdict is on the matched twin, not on SPY: beating SPY at every offset
can be the style (small, volatile, past winners) and nothing else.

RULE CHANGED 2026-09-28 (~07:00Z), AFTER the first verdicts were seen (receipts
T055728Z and T055923Z, both 4 x CANNOT_DISTINGUISH). Why: the rule above is
asymmetric. LOSES needs only mean <= 0, and a twin matched on the 12-1 TERCILE
keeps every momentum sort's point estimate positive (extremity inside the
tercile), so CALENDAR_ARTEFACT was almost unreachable for exactly the rules it
exists to catch (review F3, `docs/reviews/REVIEW_2026-09-28_LANE_M_MEASUREMENT.md`).
The roadmap's own rule (LANE M1, committed in b1010061) replaces it:

* ROBUST_TO_CALENDAR: ALL three offsets beat their twins at t >= 2 (mean > 0).
* CALENDAR_ARTEFACT: the BEST offset (highest t) beats its twin at t >= 2 AND at
  least one other offset does not reach t >= 1.
* CANNOT_DISTINGUISH: otherwise.
* NOT_COMPUTED: any offset without a t or with fewer than 3 blocks (review F9: a
  twin that failed to build is not a measured null).

The verdict is taken on TWO disjoint seed sets of the twin (draws 0-20 and
21-41, 21 draws each); when they disagree the verdict is CANNOT_DISTINGUISH
(review F4: one cell moved 1.0 pp/month on a single draw). The per-draw spread
of every offset's t is stored. The old rule's label is printed beside the new
one (`verdict_rule_v1`), never deciding.
"""
from __future__ import annotations

import dataclasses
import math
from typing import Optional

import numpy as np
import pandas as pd

from backend import config as _cfg
from backend.services import matched_twins as MT
from backend.services import strategy_library as SL

VERDICT_ROBUST = "ROBUST_TO_CALENDAR"
VERDICT_ARTEFACT = "CALENDAR_ARTEFACT"
VERDICT_CANNOT = "CANNOT_DISTINGUISH"
VERDICT_NOT_COMPUTED = "NOT_COMPUTED"
VERDICTS = (VERDICT_ROBUST, VERDICT_ARTEFACT, VERDICT_CANNOT, VERDICT_NOT_COMPUTED)
#: the t (on rebalance blocks) an offset's rule - twin21 must reach to BEAT it
BEATS_T = 2.0
#: an offset that does not reach this t makes a single-calendar beat an ARTEFACT
REACH_T = 1.0
#: draws per seed set (draw 0 + 20 extra), and the number of disjoint seed sets
DRAWS_PER_SET = 21
N_SEED_SETS = 2
MIN_BLOCKS = 3
#: the MDE multiplier the library uses everywhere (80% power at a 5% two-sided test)
MDE_Z = float(SL.MDE_Z)
#: the hindsight line's start
SL_SINCE = str(getattr(_cfg, "STRATEGY_LIB_SINCE", "2020-01-01"))
VERDICT_RULE_V1 = (
    "an offset BEATS its matched twin when the full-window mean monthly rule - twin21 > 0 "
    f"AND t >= {BEATS_T:g} on the rule's own rebalance blocks; LOSES when that mean <= 0. "
    "ROBUST_TO_CALENDAR = all three offsets beat; CALENDAR_ARTEFACT = >= 1 beats and >= 1 "
    "other loses; CANNOT_DISTINGUISH = anything else. Declared in "
    "backend/services/calendar_offsets.py before the 2026-09-28 run.")
VERDICT_RULE = (
    f"v2 (changed 2026-09-28 AFTER the first verdicts were seen; review F3/F4/F9): an offset BEATS "
    f"its matched twin when the full-window mean monthly rule - twin > 0 AND t >= {BEATS_T:g} on "
    f"its rebalance blocks. ROBUST_TO_CALENDAR = all three beat; CALENDAR_ARTEFACT = the best "
    f"offset (highest t) beats and at least one other has t < {REACH_T:g}; CANNOT_DISTINGUISH = "
    f"otherwise; NOT_COMPUTED = an offset with no t or < {MIN_BLOCKS} blocks. Read on "
    f"{N_SEED_SETS} disjoint seed sets of {DRAWS_PER_SET} twin draws; sets that disagree -> "
    "CANNOT_DISTINGUISH. Why changed: v1's LOSES needed mean <= 0, which a 12-1-tercile-matched "
    "twin almost never gives a momentum sort, so v1 could almost never say ARTEFACT.")


class OffsetInputMissing(RuntimeError):
    """A rule cannot be put through the offset triplet (not a 3-month hold,
    no monthly series, no rebalance flag): refused by name, never a silent row."""


# ── the variants ─────────────────────────────────────────────────────────────

def offset_variants(rule) -> dict:
    """{tag: the same rule rebalanced only in that tag's decision months}.

    Only a 3-month hold has three quarterly calendars; anything else refuses."""
    if int(getattr(rule, "hold_months", 0)) != 3:
        raise OffsetInputMissing(
            f"{getattr(rule, 'id', rule)}: hold_months={getattr(rule, 'hold_months', None)}; "
            "the quarterly offset triplet needs a 3-month hold")
    return {tag: dataclasses.replace(rule, id=f"{rule.id}__{tag}", rebalance_months=tuple(months))
            for tag, months in SL.QUARTER_OFFSETS.items()}


def first_rebalance_month(monthly: pd.DataFrame) -> Optional[int]:
    """The calendar month of the first rebalance (which offset a default run sits on)."""
    if monthly is None or not len(monthly):
        return None
    rb = monthly[monthly["rebalanced"].astype(bool)]
    return int(pd.Timestamp(rb["date"].iloc[0]).month) if len(rb) else None


def offset_of_month(month: Optional[int]) -> Optional[str]:
    if month is None:
        return None
    for tag, months in SL.QUARTER_OFFSETS.items():
        if int(month) in months:
            return tag
    return None


# ── statistics ───────────────────────────────────────────────────────────────

def rebalance_blocks(rebalanced) -> np.ndarray:
    """Block id per month: a new block starts at every rebalance. A series that
    does not START on a rebalance refuses (its first months belong to a book
    the series never shows being bought)."""
    rb = np.asarray(rebalanced, dtype=bool)
    if not len(rb):
        raise OffsetInputMissing("empty series: no rebalance blocks")
    if not rb[0]:
        raise OffsetInputMissing("the series does not start on a rebalance")
    return np.cumsum(rb) - 1


def block_stats(diff: pd.Series, blocks) -> dict:
    """Mean monthly difference, and its t / SE / MDE on non-overlapping blocks.

    Each block's value is the SUM of its monthly differences; the monthly SE is
    the block SE divided by the mean block length, so the MDE is in %/month
    and comparable with the library's other MDEs."""
    d = pd.Series(np.asarray(diff, dtype=float))
    b = np.asarray(blocks)
    ok = np.isfinite(d.to_numpy())
    d, b = d[ok], b[ok]
    n = int(len(d))
    out = {"n_months": n, "mean_monthly": float(d.mean()) if n else None,
           "n_blocks": 0, "t_blocks": None, "se_monthly": None, "mde_monthly": None,
           "t_monthly_naive": None}
    if n > 1:
        sd = float(d.std(ddof=1))
        out["t_monthly_naive"] = (float(d.mean() / (sd / math.sqrt(n))) if sd > 0 else None)
    if not n:
        return out
    sums = d.groupby(b).sum()
    lens = d.groupby(b).size()
    nb = int(len(sums))
    out["n_blocks"] = nb
    if nb > 2:
        sb = float(sums.std(ddof=1))
        if sb > 0:
            se_b = sb / math.sqrt(nb)
            out["t_blocks"] = float(sums.mean() / se_b)
            se_m = se_b / float(lens.mean())
            out["se_monthly"] = se_m
            out["mde_monthly"] = MDE_Z * se_m
    return out


def cagr_without_best(r, n: int = 5) -> Optional[float]:
    """CAGR after deleting the `n` best months (the library's own formula)."""
    lr = np.log1p(np.asarray(pd.Series(r).dropna(), dtype=float))
    if len(lr) <= n:
        return None
    rest = np.sort(lr)[:-n]
    return float(np.exp(rest.sum() * 12.0 / len(rest)) - 1.0)


def by_hold_year(diff: pd.Series) -> dict:
    """{hold year: sum of monthly differences}, keyed on the month HELD."""
    s = pd.Series(np.asarray(diff, dtype=float), index=pd.DatetimeIndex(diff.index))
    yrs = SL.hold_years(s.index)
    out = {}
    for y in sorted(set(yrs.tolist())):
        v = s[yrs == y].dropna()
        out[str(int(y))] = {"sum": float(v.sum()), "n_months": int(len(v))}
    return out


def loo_worst(diff: pd.Series) -> dict:
    """Leave-one-HOLD-year-out mean monthly difference: the worst year to lose."""
    s = pd.Series(np.asarray(diff, dtype=float), index=pd.DatetimeIndex(diff.index))
    loo = SL.leave_one_year_out(s.to_numpy(), SL.hold_years(s.index))
    if not loo:
        return {"worst": None, "dropped_year": None, "all": {}}
    k = min(loo, key=loo.get)
    return {"worst": loo[k], "dropped_year": k, "all": loo}


# ── the matched twin ─────────────────────────────────────────────────────────

def twin_record(rule_id: str, k: int, holdings: list, monthly: pd.DataFrame) -> dict:
    """run_strategy's holdings + monthly frame -> the record `twin_series` reads,
    through the factory's own sidecar format (so writer and reader agree)."""
    H = MT.holdings_frame([(rule_id, int(k), holdings)])
    M = MT.monthly_frame([(rule_id, int(k), monthly)])
    recs = MT.cell_records(H, M)
    rec = recs.get((str(rule_id), int(k)))
    if rec is None or not rec.get("monthly_return_series"):
        raise OffsetInputMissing(f"{rule_id}@k{k}: no holdings / monthly series for the twin")
    return rec


def twin21(rec: dict, panel: pd.DataFrame, *, cell_id: str, by_date: Optional[dict] = None,
           cache: Optional[dict] = None, grid=None, n_extra: int = MT.N_EXTRA_DRAWS,
           n_second_set: int = 0) -> dict:
    """Draw 0 + `n_extra` seeded matched twins (set A); return the rule's net,
    draw 0's net and the mean of set A's net (twin net = twin gross - the RULE's
    cost). With `n_second_set` > 0, a DISJOINT set B of that many further draws
    (seeds `seed_for(cell, j)` for j after set A) is drawn and its mean returned
    as `twinB_net`; every draw's net is kept in `draw_nets` (A then B)."""
    by_date = by_date if by_date is not None else MT.panel_by_date(panel)
    cache = cache if cache is not None else {}
    rec = dict(rec, id=cell_id)
    ts = MT.twin_series(rec, panel, seed=MT.seed_for(cell_id), by_date=by_date, cache=cache,
                        grid=grid)
    cost = ts["cost"].astype(float)
    nets = [ts["twin_gross"] - cost]
    for j in range(1, int(n_extra) + 1):
        tj = MT.twin_series(rec, panel, seed=MT.seed_for(cell_id, j), by_date=by_date,
                            cache=cache, grid=grid)
        nets.append(tj["twin_gross"] - cost)
    n_a = len(nets)
    for j in range(n_a, n_a + int(n_second_set)):
        tj = MT.twin_series(rec, panel, seed=MT.seed_for(cell_id, j), by_date=by_date,
                            cache=cache, grid=grid)
        nets.append(tj["twin_gross"] - cost)
    fb: dict = {}
    for f in ts["fallbacks"]:
        for k_, v_ in (f or {}).items():
            fb[k_] = fb.get(k_, 0) + v_
    recon = (ts["rule_gross_recon"] - ts["stored_gross"].astype(float)).abs()
    return {"rule_net": ts["stored_net"].astype(float), "twin0_net": nets[0],
            "twin21_net": pd.concat(nets[:n_a], axis=1).mean(axis=1), "n_draws": n_a,
            "twinB_net": (pd.concat(nets[n_a:], axis=1).mean(axis=1) if len(nets) > n_a else None),
            "n_draws_setB": len(nets) - n_a, "draw_nets": nets,
            "fallbacks": fb, "recon_max_abs_gap_gross": float(recon.max()) if len(recon) else None}


# ── one offset, every number ─────────────────────────────────────────────────

def offset_row(*, monthly: pd.DataFrame, ev: dict, spy: pd.Series, random_panel,
               twin: dict, n_trials_spy: int, n_trials_twin: int) -> dict:
    """Assemble the per-offset line from `SL.evaluate`'s cell (`ev`), the run's
    monthly frame, and the twin draws. Every field named in the brief; a field
    that cannot be computed is None with a `_why`, never omitted."""
    from learner.inference import deflated_sharpe
    m = monthly.set_index("date").sort_index()
    net = m["net"].astype(float)
    sp = spy.reindex(net.index).astype(float)
    blocks = rebalance_blocks(m["rebalanced"].to_numpy())
    act = net - sp
    win = SL.split_windows(net.index)
    row: dict = {"first_rebalance": str(m.index[m["rebalanced"].astype(bool)][0].date()),
                 "n_months": int(len(net)), "span": ev.get("span")}
    tw = float(np.prod(1.0 + net.to_numpy()) - 1.0)
    sp_ok = sp.dropna()
    row["cum_net_full"] = tw
    row["cagr_net_full"] = SL._cagr(net)
    row["spy_cagr_full"] = SL._cagr(sp_ok)
    row["active_cagr_vs_spy_full"] = (row["cagr_net_full"] - row["spy_cagr_full"]
                                      if None not in (row["cagr_net_full"], row["spy_cagr_full"])
                                      else None)
    h20 = ev.get("hindsight_since_2020") or {}
    row["cum_net_since_2020"] = h20.get("cum_net")
    row["cum_spy_since_2020"] = h20.get("cum_spy")
    row["cagr_net_since_2020"] = h20.get("cagr_net")
    for w in ("dev", "sealed"):
        row[f"{w}_vs_spy"] = ev.get(f"{w}_vs_spy")
        row[f"{w}_vs_random_panel"] = ev.get(f"{w}_vs_random_panel")
        row[f"{w}_vs_iwm"] = ev.get(f"{w}_vs_iwm")
    # vs the panel's random portfolio over the FULL window (same months)
    if isinstance(random_panel, pd.Series):
        rp = random_panel.reindex(net.index)
        if rp.isna().any():
            row["active_cagr_vs_random_panel_full"] = None
            row["active_cagr_vs_random_panel_full_why"] = (
                f"RANDOM_PANEL_SERIES_MISSING: {int(rp.isna().sum())} months")
        else:
            row["active_cagr_vs_random_panel_full"] = SL._cagr(net) - SL._cagr(rp)
    else:
        row["active_cagr_vs_random_panel_full"] = None
        row["active_cagr_vs_random_panel_full_why"] = str(random_panel)
    # vs SPY: which part of the sample
    row["by_year_hold_excess_vs_spy"] = {y: v.get("excess") for y, v in
                                         (ev.get("by_year_hold") or {}).items()}
    row["by_year_signs"] = ev.get("by_year_signs")
    row["loo_worst_mean_active_vs_spy"] = ev.get("loo_worst_mean_active")
    row["loo_worst_dropped_year_vs_spy"] = ev.get("loo_worst_dropped_year")
    row["cagr_without_best_5_months"] = ev.get("cagr_without_best_5_months")
    row["spy_cagr_without_best_5_months"] = cagr_without_best(sp_ok, 5)
    row["top5_months_share_of_log_return"] = ev.get("top5_months_share_of_log_return")
    row["top5_months_hold"] = ev.get("top5_months_hold")
    sa = block_stats(act, blocks)
    row["active_vs_spy_stats"] = sa
    d = deflated_sharpe([float(x) for x in act.dropna()], n_trials=int(n_trials_spy))
    row["dsr_vs_spy"] = d.get("dsr")
    row["dsr_vs_spy_n_trials"] = int(n_trials_spy)
    # vs the matched twin (twin21 = mean of 21 draws)
    diff = (twin["rule_net"] - twin["twin21_net"]).reindex(net.index)
    diff0 = (twin["rule_net"] - twin["twin0_net"]).reindex(net.index)
    tw_full = block_stats(diff, blocks)
    row["twin"] = {
        "n_draws": twin.get("n_draws"), "fallbacks": twin.get("fallbacks"),
        "recon_max_abs_gap_gross": twin.get("recon_max_abs_gap_gross"),
        "full": tw_full,
        "draw0_mean_monthly": float(diff0.mean()) if diff0.notna().any() else None,
        "cagr_rule_minus_twin21_full": (
            SL._cagr(twin["rule_net"]) - SL._cagr(twin["twin21_net"])),
    }
    for w in ("dev", "sealed"):
        mk = win[w]
        row["twin"][w] = block_stats(diff[mk], blocks[mk])
        rn, tn = twin["rule_net"][mk], twin["twin21_net"][mk]
        row["twin"][w]["cagr_rule_minus_twin21"] = (
            (SL._cagr(rn) - SL._cagr(tn)) if len(rn) else None)
    # set B (disjoint seeds) and the per-draw spread (review F4)
    if twin.get("twinB_net") is not None:
        diffB = (twin["rule_net"] - twin["twinB_net"]).reindex(net.index)
        row["twin"]["setB"] = {"n_draws": twin.get("n_draws_setB"), "full": block_stats(diffB, blocks)}
        for w in ("dev", "sealed"):
            mk = win[w]
            row["twin"]["setB"][w] = block_stats(diffB[mk], blocks[mk])
    if twin.get("draw_nets"):
        ts_, ms_ = [], []
        for dn in twin["draw_nets"]:
            st = block_stats((twin["rule_net"] - dn).reindex(net.index), blocks)
            ts_.append(st.get("t_blocks"))
            ms_.append(st.get("mean_monthly"))
        row["twin"]["per_draw"] = {"n": len(ts_), "t_blocks": ts_, "mean_monthly": ms_,
                                   "summary": draw_spread(ts_, ms_)}
    row["twin"]["by_year_hold_sum"] = by_hold_year(diff)
    row["twin"]["loo_worst"] = loo_worst(diff)
    dd = deflated_sharpe([float(x) for x in diff.dropna()], n_trials=int(n_trials_twin))
    row["dsr_rule_minus_twin21"] = dd.get("dsr")
    row["dsr_rule_minus_twin21_n_trials"] = int(n_trials_twin)
    row["beats_twin"] = beats_twin(tw_full)
    row["loses_to_twin"] = loses_to_twin(tw_full)
    return row


def beats_twin(stats: dict) -> bool:
    m, t = stats.get("mean_monthly"), stats.get("t_blocks")
    return bool(m is not None and m > 0 and t is not None and t >= BEATS_T)


def loses_to_twin(stats: dict) -> bool:
    m = stats.get("mean_monthly")
    return bool(m is not None and m <= 0)


def draw_spread(ts: list, ms: list) -> dict:
    """min / median / max of the per-draw t and mean, and the share of draws
    whose single-draw comparison would clear t >= BEATS_T / fail t >= REACH_T."""
    t = np.array([x for x in ts if x is not None], dtype=float)
    m = np.array([x for x in ms if x is not None], dtype=float)
    if not len(t):
        return {"n": 0}
    return {"n": int(len(t)), "t_min": float(t.min()), "t_median": float(np.median(t)),
            "t_max": float(t.max()), "t_sd": float(t.std(ddof=1)) if len(t) > 1 else None,
            "mean_min": float(m.min()) if len(m) else None,
            "mean_max": float(m.max()) if len(m) else None,
            "share_draws_t_ge_beats": float((t >= BEATS_T).mean()),
            "share_draws_t_lt_reach": float((t < REACH_T).mean())}


def verdict_v2(stats: dict) -> dict:
    """{tag: {mean_monthly, t_blocks, n_blocks}} -> the v2 verdict (module doc)."""
    bad = sorted(tg for tg, st in stats.items()
                 if (st or {}).get("t_blocks") is None or (st or {}).get("mean_monthly") is None
                 or ((st or {}).get("n_blocks") is not None and st["n_blocks"] < MIN_BLOCKS))
    if bad:
        return {"verdict": VERDICT_NOT_COMPUTED, "why": f"no t / < {MIN_BLOCKS} blocks at {bad}"}
    beats = sorted(tg for tg, st in stats.items() if beats_twin(st))
    best = max(stats, key=lambda tg: stats[tg]["t_blocks"])
    short = sorted(tg for tg, st in stats.items() if tg != best and st["t_blocks"] < REACH_T)
    if len(beats) == len(stats):
        v = VERDICT_ROBUST
    elif best in beats and short:
        v = VERDICT_ARTEFACT
    else:
        v = VERDICT_CANNOT
    return {"verdict": v, "beats_twin": beats, "best_offset": best,
            "others_below_reach_t": short,
            "t_blocks": {tg: st["t_blocks"] for tg, st in stats.items()}}


def _verdict_v1(offsets: dict) -> str:
    beats = [t for t, r in offsets.items() if r.get("beats_twin")]
    loses = [t for t, r in offsets.items() if r.get("loses_to_twin")]
    if len(beats) == len(offsets):
        return VERDICT_ROBUST
    return VERDICT_ARTEFACT if (beats and loses) else VERDICT_CANNOT


def classify(offsets: dict) -> dict:
    """{tag: offset row} -> the rule's calendar verdict (v2), with the reasons."""
    if set(offsets) != set(SL.QUARTER_OFFSETS):
        missing = sorted(set(SL.QUARTER_OFFSETS) - set(offsets))
        return {"verdict": VERDICT_NOT_COMPUTED, "why": f"offsets missing: {missing}",
                "rule": VERDICT_RULE}
    beats = sorted(t for t, r in offsets.items() if r.get("beats_twin"))
    loses = sorted(t for t, r in offsets.items() if r.get("loses_to_twin"))
    set_a = verdict_v2({t: (r.get("twin") or {}).get("full") or {} for t, r in offsets.items()})
    set_b = None
    if all(((r.get("twin") or {}).get("setB") or {}).get("full") for r in offsets.values()):
        set_b = verdict_v2({t: r["twin"]["setB"]["full"] for t, r in offsets.items()})
    v = set_a["verdict"]
    why = "seed set A only (draws 0-20)"
    if set_b is not None:
        if set_b["verdict"] == set_a["verdict"]:
            why = "seed sets A and B agree"
        elif VERDICT_NOT_COMPUTED in (set_a["verdict"], set_b["verdict"]):
            v, why = VERDICT_NOT_COMPUTED, "a seed set could not be computed"
        else:
            v, why = VERDICT_CANNOT, (f"seed sets disagree (A {set_a['verdict']}, "
                                      f"B {set_b['verdict']}): the label moves with the twin's seed")
    # the per-draw verdict: the same rule on ONE draw at every offset
    per_draw: dict = {}
    pds = [((r.get("twin") or {}).get("per_draw") or {}) for r in offsets.values()]
    if pds and all(x.get("n") for x in pds) and len({x["n"] for x in pds}) == 1:
        for j in range(pds[0]["n"]):
            st = {tg: {"t_blocks": r["twin"]["per_draw"]["t_blocks"][j],
                       "mean_monthly": r["twin"]["per_draw"]["mean_monthly"][j]}
                  for tg, r in offsets.items()}
            vj = verdict_v2(st)["verdict"]
            per_draw[vj] = per_draw.get(vj, 0) + 1
    means = {t: (r.get("twin") or {}).get("full", {}).get("mean_monthly") for t, r in offsets.items()}
    sealed = {t: r.get("sealed_vs_spy") for t, r in offsets.items()}
    cum20 = {t: r.get("cum_net_since_2020") for t, r in offsets.items()}
    fin = [x for x in means.values() if x is not None]
    return {"verdict": v, "why": why, "rule": VERDICT_RULE,
            "set_a": set_a, "set_b": set_b, "per_draw_verdicts": per_draw,
            "verdict_rule_v1": _verdict_v1(offsets), "rule_v1": VERDICT_RULE_V1,
            "beats_twin": beats, "loses_to_twin": loses,
            "mean_monthly_rule_minus_twin21": means,
            "spread_mean_monthly_rule_minus_twin21": (max(fin) - min(fin)) if fin else None,
            "sealed_vs_spy": sealed,
            "spread_sealed_vs_spy": _spread(sealed),
            "cum_net_since_2020": cum20,
            "spread_cum_net_since_2020": _spread(cum20)}


def tranche_average(series: dict) -> dict:
    """The calendar-NEUTRAL book: one third in each offset's book (the
    'rebalance timing luck' remedy). `series`: {tag: DataFrame(rule_net,
    twin21_net, spy) indexed by decision date}. Read beside the verdict, never
    an input to it (the verdict rule was declared first). The t is on
    non-overlapping 3-month blocks from the first common month."""
    if not series:
        return {"status": "REFUSED", "why": "no offset series"}
    common = None
    for df in series.values():
        common = df.index if common is None else common.intersection(df.index)
    common = pd.DatetimeIndex(sorted(common))
    rn = pd.concat([df["rule_net"].reindex(common) for df in series.values()], axis=1).mean(axis=1)
    tn = pd.concat([df["twin21_net"].reindex(common) for df in series.values()], axis=1).mean(axis=1)
    sp = next(iter(series.values()))["spy"].reindex(common).astype(float)
    blocks = np.arange(len(common)) // 3
    s20 = common >= pd.Timestamp(SL_SINCE)
    out = {"n_months": int(len(common)),
           "span": [str(common.min().date()), str(common.max().date())] if len(common) else None,
           "cagr_net": SL._cagr(rn), "spy_cagr": SL._cagr(sp.dropna()),
           "cum_net_since_2020": float(np.prod(1.0 + rn[s20].to_numpy()) - 1.0) if s20.any() else None,
           "cum_spy_since_2020": (float(np.prod(1.0 + sp[s20].dropna().to_numpy()) - 1.0)
                                  if s20.any() else None),
           "rule_minus_twin21": block_stats(rn - tn, blocks),
           "active_vs_spy": block_stats(rn - sp, blocks)}
    win = SL.split_windows(common)
    for w in ("dev", "sealed"):
        mk = win[w]
        out[f"{w}_rule_minus_twin21"] = block_stats((rn - tn)[mk], blocks[mk])
        out[f"{w}_vs_spy_cagr"] = ((SL._cagr(rn[mk]) - SL._cagr(sp[mk].dropna()))
                                   if mk.any() else None)
    return out


def _spread(d: dict) -> Optional[float]:
    xs = [x for x in d.values() if x is not None]
    return (max(xs) - min(xs)) if xs else None


def cross_rule_correlation(monthly: pd.DataFrame) -> dict:
    """Pairwise correlation of the rules' CALENDAR-NEUTRAL monthly net returns
    (mean over the three offsets per decision month), from the receipt's
    `calendar_offsets_monthly_<run>.parquet`. Several leads whose returns move
    together at 0.8-1.0 are ONE bet wearing several names (review 2026-09-28)."""
    if monthly is None or not len(monthly) or not {"date", "rule", "rule_net"} <= set(monthly.columns):
        return {"status": "NOT_COMPUTED", "why": "no monthly series"}
    t = monthly.groupby(["date", "rule"])["rule_net"].mean().unstack().dropna()
    rules = list(t.columns)
    if len(rules) < 2 or len(t) < 12:
        return {"status": "NOT_COMPUTED", "why": f"{len(rules)} rules / {len(t)} common months"}
    c = t.corr()
    pairs = {f"{a}|{b}": float(c.loc[a, b]) for i, a in enumerate(rules) for b in rules[i + 1:]}
    return {"status": "OK", "rules": rules, "n_months": int(len(t)), "pairs": pairs,
            "min": float(min(pairs.values())), "max": float(max(pairs.values())),
            "basis": "calendar-neutral (1/3 each quarterly calendar) monthly net returns"}
