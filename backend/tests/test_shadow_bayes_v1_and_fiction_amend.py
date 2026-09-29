"""2026-09-29 amendments: the shadow rule's successor (v1) and the AMNESIA-2 Opus re-reading.

REVIEW_2026-09-29_SHADOW_BOOK_AND_TRUST_WEIGHTS F2-F5 and REVIEW_2026-09-29_FICTION_BACKTEST
findings 1 and 4. Synthetic data, no network, no model call.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from scripts import fiction_backtest as FB
from scripts import shadow_bayes_rule as SB


# ───────────────────────────── shadow v1 ─────────────────────────────

def test_v1_has_no_declared_t_and_gives_llm_direction_its_prior_for_the_right_reason():
    assert SB.EVIDENCE_V1["ranker_lgbm"]["obs"] == []
    llm = SB.EVIDENCE_V1["llm_direction"]
    assert llm["obs"] == [] and SB.posterior_v1(llm["obs"])["post_mean"] == 0.0
    assert "no evidence FOR a weight" in llm["receipt"] and "44.6" not in llm["receipt"]
    # the momentum edge is the twin21 reading, smaller than v0's draw-0 reading
    assert SB.posterior_v1(SB.EVIDENCE_V1["momentum_12_1"]["obs"])["post_mean"] < \
        SB.posterior(SB.EVIDENCE["momentum_12_1"]["obs"])["post_mean"]


def _cells(n: int = 300, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    f = pd.DataFrame({"mdv63": rng.choice([5e6, 5e7, 5e8, 5e9], n), "vol_63": rng.uniform(0.01, 0.05, n),
                      "mom_12_1": rng.normal(0, 0.3, n)}, index=[f"N{i:03d}" for i in range(n)])
    f["band"] = f.mdv63.map(SB.band_of)
    f["vol_t"] = pd.qcut(f.vol_63.rank(method="first"), 3, labels=False)
    f["mom_t"] = pd.qcut(f.mom_12_1.rank(method="first"), 3, labels=False)
    return f


def test_the_matched_twin_stays_in_band_vol_and_momentum_cells_and_is_reproducible():
    f = _cells()
    held = {"N000": 0.02, "N001": 0.01}
    tw, meta = SB.matched_twin21(held, f, seed=11, exclude=set(held))
    tw2, _ = SB.matched_twin21(held, f, seed=11, exclude=set(held))
    assert tw == tw2 and meta["seed"] == 11 and meta["draws"] == 21
    assert sum(tw.values()) == pytest.approx(sum(held.values()))
    assert not set(tw) & set(held)
    cells = {tuple(f.loc[t, ["band", "vol_t", "mom_t"]]) for t in held}
    if meta["fallbacks"]["cell"] == 2 * 21:
        assert all(tuple(f.loc[t, ["band", "vol_t", "mom_t"]]) in cells for t in tw)


def test_the_kill_rule_states_its_power():
    held = {"A": 0.01, "B": 0.01}
    k = SB.kill_rule_power(held, {"A": 0.001, "B": 0.001}, {"A": 0.08, "B": 0.08})
    sd = math.sqrt(2 * 0.25 * 0.08 ** 2 * 3 * (1 + 1 / 21))
    assert k["sd_D"] == pytest.approx(sd, rel=1e-3)
    assert k["P_kill_if_rule_worthless"] == pytest.approx(0.05, abs=1e-3)
    assert k["P_kill_if_posterior_true"] < k["P_kill_if_rule_worthless"]
    assert k["mde80_one_sided_5pct"] == pytest.approx((1.645 + 0.8416) * sd, rel=1e-3)


# ───────────────────────────── AMNESIA-2 amendments ─────────────────────────────

def test_the_leak_rule_is_evaluated_for_an_arm_that_answered_only_the_canaries():
    can = {"file:opus|famous|A3_SYNTHETIC": {"n": 30, "identified_company": 7, "identified_rate": 7 / 30},
           "deepseek|famous|A3_SYNTHETIC": {"n": 30, "identified_company": 0, "identified_rate": 0.0}}
    F = pd.DataFrame([{"arm": "deepseek", "part": "famous", "level": "A3_SYNTHETIC",
                       "p_beat_median_5d": 0.6, "beat5": 1}] * 10)
    t = FB.leak_table(F, can)
    assert t["file:opus"]["fiction_leaks"] is True
    assert t["file:opus"]["clauses"]["famous_A3_hit_ge_0.70"] is None          # never answered: not evaluated
    assert t["deepseek"]["clauses_evaluated"] == ["identified_rate_gt_10pct", "famous_A3_hit_ge_0.70"]
    assert t["deepseek"]["fiction_leaks"] is True                               # hit 1.0 >= 0.70 here


def test_an_abstaining_model_reads_cannot_distinguish_beside_the_formal_verdict():
    rng = np.random.default_rng(5)
    p = np.clip(0.49 + rng.normal(0, 0.01, 120), 0.44, 0.53)
    p[:37] = 0.5
    y = (rng.random(120) < 0.54).astype(int)
    a = FB.abstention(p, y)
    assert a["abstained"] and a["share_p_exactly_half"] == pytest.approx(37 / 120)
    assert a["n_took_a_side"] == 83
    cell = {"dir5": {"n": 120, "wilson95": (0.36, 0.539), "week_block": {"t": 0.2},
                     "momentum_hit_same_rows": 0.525, "hit": 0.446, "sd_p": float(np.std(p, ddof=1)), **a}}
    v = FB.verdicts(cell)
    assert v["direction"] == "FAILED_VARIANT"
    assert v["direction_reading"].startswith("CANNOT_DISTINGUISH (model abstained")


def test_auc_is_a_rank_statistic():
    y = np.array([0, 0, 1, 1])
    assert FB.auc(np.array([0.1, 0.2, 0.8, 0.9]), y) == 1.0
    assert FB.auc(np.array([0.9, 0.8, 0.2, 0.1]), y) == 0.0
    assert FB.auc(np.full(4, 0.5), y) == 0.5
