"""The sticky twin's PER-DRAW turnover check (TWIN_STICKY_v2, 2026-10-07).

v1 (`matched_twins.sticky_turnover_check`) excluded a MONTH when ANY of the 21 draws redrew a
partner, so the median rule had 83% of its months excluded. v2
(`sticky_turnover_check_per_draw`) excludes the month for THAT draw only and takes the median over
draws x months. The construction is unchanged: `twin_series_sticky_draws` re-runs each draw alone
under an id whose draw-0 seed is v1's `seed_for(id, j)`, and its aggregate must equal the v1
21-draw frame.

Synthetic data only; dates derive from today; no panel parquet is read.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from backend import config as C
from backend.services import matched_twins as MT

BASE = pd.Timestamp.today().normalize() - pd.DateOffset(years=2)


def _dates(n: int) -> pd.DatetimeIndex:
    return pd.date_range(BASE, periods=n, freq="BME")


def _draw_frame(turn, twin_turn, died=None, coll=None) -> pd.DataFrame:
    n = len(turn)
    return pd.DataFrame({"n": [5] * n, "turnover": turn, "twin_turnover": twin_turn,
                         "twin_died": died or [0] * n, "twin_collision": coll or [0] * n}, index=_dates(n))


def test_a_redraw_in_draw_2_excludes_only_draw_2s_month():
    """Three draws, three months. Draw 2 (index 1) redrew in month 1 and its turnover there is off
    by 0.5. v2 drops ONLY (draw 2, month 1): 8 of 9 pairs remain and the gap is 0. v1, on the
    aggregate, drops month 1 for every draw."""
    rule = [0.10, 0.10, 0.10]
    d1 = _draw_frame(rule, [0.10, 0.10, 0.10])
    d2 = _draw_frame(rule, [0.10, 0.60, 0.10], died=[0, 1, 0])
    d3 = _draw_frame(rule, [0.10, 0.10, 0.10])
    chk = MT.sticky_turnover_check_per_draw([d1, d2, d3])
    assert chk["n_pairs_invested"] == 9
    assert chk["n_pairs_excluded_death_or_collision"] == 1
    assert chk["n_pairs"] == 8
    assert chk["median_abs_gap"] == 0.0 and chk["ok"]
    assert chk["tolerance"] == C.STICKY_TWIN_TURNOVER_TOLERANCE
    # v1 on the aggregate frame: the whole month 1 is gone (3 months -> 2)
    agg = d1[["n", "turnover"]].assign(
        twin_turnover=np.mean([d1.twin_turnover, d2.twin_turnover, d3.twin_turnover], axis=0),
        twin_died=d1.twin_died + d2.twin_died + d3.twin_died, twin_collision=0)
    v1 = MT.sticky_turnover_check(agg)
    assert v1["n_months"] == 2 and v1["n_months_excluded_death_or_collision"] == 1


def test_the_other_draws_keep_the_redraw_month_and_can_fail_it():
    """Draws 1 and 3 traded 0.2 more than the rule in month 1 with NO redraw of their own: v1
    never sees it (draw 2's redraw dropped the month), v2 counts it."""
    rule = [0.10, 0.10, 0.10]
    d1 = _draw_frame(rule, [0.10, 0.30, 0.10])
    d2 = _draw_frame(rule, [0.10, 0.60, 0.10], coll=[0, 1, 0])
    d3 = _draw_frame(rule, [0.10, 0.30, 0.10])
    chk = MT.sticky_turnover_check_per_draw([d1, d2, d3])
    assert chk["n_pairs"] == 8
    gaps = sorted([0, 0, 0, 0, 0, 0, 0.2, 0.2])
    assert chk["median_abs_gap"] == pytest.approx(float(np.median(gaps)))
    # make the off-pairs the majority: the per-draw median crosses the tolerance and refuses
    e1 = _draw_frame(rule, [0.30, 0.30, 0.10])
    e3 = _draw_frame(rule, [0.30, 0.30, 0.30])
    bad = MT.sticky_turnover_check_per_draw([e1, d2, e3])
    assert not bad["ok"] and bad["reason"].startswith("REFUSED")
    assert bad["tolerance"] == C.STICKY_TWIN_TURNOVER_TOLERANCE      # not re-tuned


def test_no_pair_left_refuses():
    f = _draw_frame([0.1, 0.1], [0.1, 0.1], died=[1, 1])
    chk = MT.sticky_turnover_check_per_draw([f])
    assert not chk["ok"] and chk["n_pairs"] == 0 and chk["reason"].startswith("REFUSED")
    with pytest.raises(MT.TwinInputMissing):
        MT.sticky_turnover_check_per_draw([])


def test_draw_ids_carry_the_v1_seeds():
    for j in range(25):
        assert MT.seed_for(MT._draw_id("qc761_x", j), 0) == MT.seed_for("qc761_x", j)


def _panel(n_months: int, n_names: int, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    lv = np.array([3e9, 3e8, 5e7, 5e6])
    rows = []
    for d in _dates(n_months):
        for i in range(n_names):
            if i % 17 == 5 and d == _dates(n_months)[n_months // 2]:
                continue                                              # a few names off the panel: deaths
            rows.append({"date": d, "symbol": f"S{i:03d}", "eligible": True,
                         "median_dollar_vol": lv[i % 4] * (1 + 0.1 * rng.random()),
                         "vol_63": rng.uniform(0.1, 0.8), "mom_252_21": rng.normal(0, 0.3),
                         "fwd_ret": rng.normal(0.005, 0.05), "_sp": 0.01})
    return pd.DataFrame(rows)


def test_the_per_draw_aggregate_is_the_v1_21_draw_frame():
    """The construction did not change: the draws re-run alone and averaged reproduce
    `twin_series_sticky` with n_draws draws exactly (drifting weights, collisions, deaths)."""
    P = _panel(9, 90)
    dts = _dates(9)
    book = {}
    for i, d in enumerate(dts):
        book[d] = [f"S{(i * 3 + k) % 60:03d}" for k in range(6)]     # rotates: entries, exits, collisions
    rule = {"id": "agg_check", "held_symbols_by_date": book}
    by_date = {pd.Timestamp(d): g for d, g in P.groupby("date")}
    K = MT.twin_series_sticky(rule, by_date=by_date, n_draws=5)
    frames, A = MT.twin_series_sticky_draws(rule, by_date=by_date, n_draws=5)
    assert len(frames) == 5
    for c in ("gross", "cost", "turnover", "twin_gross", "twin_cost", "twin_turnover", "twin_turnover_draw_sd",
              "twin_full_rt", "twin_entry", "twin_exit", "twin_died", "twin_collision", "twin_unmatched_retry",
              "twin_fallback", "twin_cash_slots"):
        assert np.array_equal(K[c].to_numpy(dtype=float), A[c].to_numpy(dtype=float), equal_nan=True), c
    assert int(K["twin_died"].sum() + K["twin_collision"].sum()) > 0   # the fixture exercises redraws


def test_the_v2_declaration_pins_the_v1_construction_and_its_own_code():
    from scripts import hyp_twin_board as TB
    d = TB.sticky_declaration_v2()
    assert d["path"].endswith("DECLARATION_TWIN_STICKY_v2.json")
    assert d["construction_sha256"] == TB.sticky_declaration()["code_sha256"]
    doc = json.loads(TB.STICKY_DECLARATION_V2.read_text(encoding="utf-8"))
    assert doc["receipt_check"]["tolerance"] == C.STICKY_TWIN_TURNOVER_TOLERANCE == 0.03


def test_a_mutated_v2_declaration_refuses(tmp_path):
    from scripts import hyp_twin_board as TB
    doc = json.loads(TB.STICKY_DECLARATION_V2.read_text(encoding="utf-8"))
    doc["receipt_check"]["tolerance"] = 0.05                          # re-tuned after the fact
    p = tmp_path / "DECLARATION_TWIN_STICKY_v2.json"
    p.write_text(json.dumps(doc, sort_keys=True, indent=1), encoding="utf-8")
    with pytest.raises(MT.TwinInputMissing, match="edited"):
        TB.sticky_declaration_v2(p)
