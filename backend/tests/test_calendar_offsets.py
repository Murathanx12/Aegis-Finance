"""Lane M1: the quarterly-offset triplet (`backend/services/calendar_offsets.py`).

Synthetic data only; dates derived from today; no network.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from backend.services import calendar_offsets as CO
from backend.services import matched_twins as MT
from backend.services import strategy_library as SL


def _month_ends(n: int) -> pd.DatetimeIndex:
    end = pd.Timestamp(date.today()).normalize() - pd.offsets.MonthEnd(1)
    return pd.date_range(end=end, periods=n, freq="BME")


def _panel(n_months: int = 72, n_sym: int = 90, alpha: float = 0.0, seed: int = 3) -> pd.DataFrame:
    """A month-end panel with a per-symbol `alpha` column that predicts fwd_ret
    with strength `alpha` and is independent of band, vol and 12-1 momentum."""
    rng = np.random.default_rng(seed)
    dates = _month_ends(n_months)
    syms = [f"S{i:03d}" for i in range(n_sym)]
    rows = []
    for j, d in enumerate(dates):
        a = rng.normal(size=n_sym)
        mom = rng.normal(0.1, 0.3, size=n_sym)
        vol = rng.uniform(0.15, 0.8, size=n_sym)
        mdv = np.exp(rng.uniform(np.log(5e6), np.log(3e9), size=n_sym))
        fwd = 0.01 + alpha * a + rng.normal(0, 0.08, size=n_sym)
        if j == n_months - 1:
            fwd = np.full(n_sym, np.nan)
        for i, s in enumerate(syms):
            rows.append({"date": d, "symbol": s, "eligible": True, "median_dollar_vol": mdv[i],
                         "vol_63": vol[i], "mom_252_21": mom[i], "alpha": a[i], "fwd_ret": fwd[i],
                         "delisted_in_period": False, "is_month_end": True})
    return pd.DataFrame(rows)


def _spy(panel: pd.DataFrame) -> pd.Series:
    d = sorted(panel["date"].unique())
    rng = np.random.default_rng(11)
    return pd.Series(rng.normal(0.008, 0.04, size=len(d)), index=pd.DatetimeIndex(d))


def _rule(signal_col: str = "alpha", k: int = 10, hold: int = 3):
    return SL.Strategy(f"syn_{signal_col}_q", "momentum", "synthetic quarterly rule",
                       SL.col(signal_col), k=k, hold_months=hold)


def _run_offsets(panel: pd.DataFrame, rule, n_extra: int = 4) -> dict:
    spy = _spy(panel)
    rp = spy * 0.9
    by_date = MT.panel_by_date(panel)
    grid = sorted(pd.DatetimeIndex(panel.loc[panel["fwd_ret"].notna(), "date"].unique()))
    out = {}
    for tag, var in CO.offset_variants(rule).items():
        hold: list = []
        m = SL.run_strategy(panel, var, holdings=hold)
        ev = SL.evaluate(m, spy, hold_months=3, iwm="IWM_SERIES_MISSING: test", random_panel=rp)
        rec = CO.twin_record(var.id, var.k, hold, m)
        tw = CO.twin21(rec, panel, cell_id=f"{var.id}@k{var.k}", by_date=by_date, grid=grid,
                       n_extra=n_extra)
        row = CO.offset_row(monthly=m, ev=ev, spy=spy, random_panel=rp, twin=tw,
                            n_trials_spy=100, n_trials_twin=50)
        row["first_offset"] = CO.offset_of_month(CO.first_rebalance_month(m))
        out[tag] = row
    return out


def test_offset_variants_refuse_a_monthly_rule_by_name():
    with pytest.raises(CO.OffsetInputMissing, match="3-month hold"):
        CO.offset_variants(_rule(hold=1))


def test_offset_variants_cover_the_three_calendars():
    v = CO.offset_variants(_rule())
    assert set(v) == set(SL.QUARTER_OFFSETS)
    months = sorted(m for x in v.values() for m in x.rebalance_months)
    assert months == list(range(1, 13))
    assert len({x.id for x in v.values()}) == 3


def test_rebalance_blocks_refuse_a_series_that_does_not_start_on_a_rebalance():
    with pytest.raises(CO.OffsetInputMissing):
        CO.rebalance_blocks([False, True, False])
    assert list(CO.rebalance_blocks([True, False, False, True, False])) == [0, 0, 0, 1, 1]


def test_block_stats_sum_blocks_and_scale_the_mde_to_a_month():
    diff = pd.Series([0.01, 0.01, 0.01, 0.03, 0.03, 0.03, 0.00, 0.00, 0.00, 0.02, 0.02, 0.02])
    blocks = CO.rebalance_blocks([True, False, False] * 4)
    s = CO.block_stats(diff, blocks)
    assert s["n_blocks"] == 4 and s["n_months"] == 12
    sums = np.array([0.03, 0.09, 0.0, 0.06])
    se_b = sums.std(ddof=1) / np.sqrt(4)
    assert s["t_blocks"] == pytest.approx(sums.mean() / se_b)
    assert s["se_monthly"] == pytest.approx(se_b / 3)
    assert s["mde_monthly"] == pytest.approx(CO.MDE_Z * se_b / 3)


def _row(mean, t, n_blocks=30):
    st = {"mean_monthly": mean, "t_blocks": t, "n_blocks": n_blocks}
    return {"twin": {"full": st}, "beats_twin": CO.beats_twin(st), "loses_to_twin": CO.loses_to_twin(st),
            "sealed_vs_spy": mean, "cum_net_since_2020": mean}


def test_classify_robust_artefact_and_cannot_distinguish():
    r = CO.classify({"jajo": _row(0.02, 2.5), "fman": _row(0.01, 2.1), "mjsd": _row(0.015, 3.0)})
    assert r["verdict"] == CO.VERDICT_ROBUST
    a = CO.classify({"jajo": _row(0.02, 2.5), "fman": _row(-0.001, -0.2), "mjsd": _row(0.004, 0.8)})
    assert a["verdict"] == CO.VERDICT_ARTEFACT and a["loses_to_twin"] == ["fman"]
    # v2 (2026-09-28): positive-but-weak other calendars ARE an artefact -- the
    # v1 rule filed this CANNOT_DISTINGUISH because nothing "lost"
    c = CO.classify({"jajo": _row(0.02, 2.5), "fman": _row(0.003, 0.9), "mjsd": _row(0.004, 0.8)})
    assert c["verdict"] == CO.VERDICT_ARTEFACT and c["verdict_rule_v1"] == CO.VERDICT_CANNOT
    # every other calendar reaches t >= 1 without clearing 2: cannot distinguish
    c2 = CO.classify({"jajo": _row(0.02, 2.5), "fman": _row(0.01, 1.5), "mjsd": _row(0.01, 1.2)})
    assert c2["verdict"] == CO.VERDICT_CANNOT
    # the best offset does not clear 2: never an artefact, whatever the others do
    c3 = CO.classify({"jajo": _row(0.02, 1.9), "fman": _row(0.0, 0.1), "mjsd": _row(0.0, 0.2)})
    assert c3["verdict"] == CO.VERDICT_CANNOT
    n = CO.classify({"jajo": _row(0.02, 2.5)})
    assert n["verdict"] == CO.VERDICT_NOT_COMPUTED and "missing" in n["why"]
    assert r["spread_mean_monthly_rule_minus_twin21"] == pytest.approx(0.01)


def test_each_offset_rebalances_only_in_its_own_months():
    rows = _run_offsets(_panel(n_months=40, alpha=0.0), _rule(), n_extra=1)
    for tag, row in rows.items():
        assert row["first_offset"] == tag
        assert int(row["first_rebalance"][5:7]) in SL.QUARTER_OFFSETS[tag]


def test_a_planted_selection_signal_beats_its_twin_at_every_calendar():
    rows = _run_offsets(_panel(alpha=0.03), _rule())
    v = CO.classify(rows)
    assert v["verdict"] == CO.VERDICT_ROBUST, v
    for row in rows.values():
        assert row["twin"]["full"]["mean_monthly"] > 0
        assert row["twin"]["recon_max_abs_gap_gross"] < 1e-9


def test_no_signal_is_not_called_robust_and_every_field_is_present():
    rows = _run_offsets(_panel(alpha=0.0, seed=5), _rule())
    assert CO.classify(rows)["verdict"] != CO.VERDICT_ROBUST
    need = ("cum_net_full", "cagr_net_full", "active_cagr_vs_spy_full", "cum_net_since_2020",
            "sealed_vs_spy", "active_cagr_vs_random_panel_full", "by_year_hold_excess_vs_spy",
            "loo_worst_mean_active_vs_spy", "cagr_without_best_5_months",
            "spy_cagr_without_best_5_months", "active_vs_spy_stats", "dsr_vs_spy",
            "dsr_rule_minus_twin21", "twin", "beats_twin", "loses_to_twin")
    for row in rows.values():
        for f in need:
            assert f in row, f
        assert row["sealed_vs_iwm"] is None          # the IWM refusal is carried, not invented
        assert set(row["twin"]) >= {"full", "dev", "sealed", "by_year_hold_sum", "loo_worst"}


def test_tranche_average_is_the_mean_of_the_three_offsets_on_common_months():
    idx = _month_ends(12)
    mk = lambda r, t: pd.DataFrame({"rule_net": r, "twin21_net": t, "spy": 0.01}, index=idx)  # noqa: E731
    ser = {"jajo": mk(0.03, 0.01), "fman": mk(0.00, 0.01), "mjsd": mk(0.03, 0.01)}
    ta = CO.tranche_average(ser)
    assert ta["n_months"] == 12
    assert ta["rule_minus_twin21"]["mean_monthly"] == pytest.approx(0.01)
    assert ta["rule_minus_twin21"]["n_blocks"] == 4
    assert CO.tranche_average({})["status"] == "REFUSED"


def test_shrink_check_refuses_a_smaller_panel_or_revision_table():
    from scripts import calendar_offset_triplet as T
    p = _panel(n_months=14, n_sym=20)
    ref = {"run_id": "ref", "panel": {"symbols": 20, "dates": 14,
                                      "first": str(p["date"].min().date())},
           "chunk_d_inputs": {"ratings": {"n_events": 1000}}}
    ok = T.shrink_check(ref, p, {"status": "OK", "n_events": 1000})
    assert ok["refuse"] == []
    small = p[p["symbol"] != "S000"]
    bad = T.shrink_check(ref, small, {"status": "OK", "n_events": 500})
    assert any("symbols" in x for x in bad["refuse"])
    assert any("revision events" in x for x in bad["refuse"])
    refused = T.shrink_check(ref, p, {"status": "REFUSED", "why": "no parquet"})
    assert any("ratings attach" in x for x in refused["refuse"])



# ── v2 (2026-09-28, review F3 / F4 / F9) ─────────────────────────────────────

def test_disp_short_avoid_shape_is_a_calendar_artefact_under_v2():
    """The receipt's numbers for disp_short_avoid: +1.61 t 2.32 / +0.52 t 0.96 /
    +0.21 t 0.46. v1 said CANNOT_DISTINGUISH (nothing had mean <= 0)."""
    v = CO.classify({"jajo": _row(0.0161, 2.32), "fman": _row(0.0052, 0.96),
                     "mjsd": _row(0.0021, 0.46)})
    assert v["verdict"] == CO.VERDICT_ARTEFACT and v["verdict_rule_v1"] == CO.VERDICT_CANNOT
    assert v["set_a"]["best_offset"] == "jajo"


def test_an_empty_twin_is_not_computed_not_a_measured_null():
    v = CO.classify({"jajo": _row(0.02, 2.5), "fman": _row(None, None, 0), "mjsd": _row(0.01, 1.2)})
    assert v["verdict"] == CO.VERDICT_NOT_COMPUTED
    v2 = CO.classify({"jajo": _row(0.02, 2.5), "fman": _row(0.01, 1.5, 2), "mjsd": _row(0.01, 1.2)})
    assert v2["verdict"] == CO.VERDICT_NOT_COMPUTED


def _row_ab(a, b):
    r = _row(*a)
    r["twin"]["setB"] = {"full": {"mean_monthly": b[0], "t_blocks": b[1], "n_blocks": 30}}
    return r


def test_two_seed_sets_that_disagree_cannot_decide_the_label():
    same = CO.classify({"jajo": _row_ab((0.02, 2.5), (0.02, 2.4)), "fman": _row_ab((0.01, 2.1), (0.01, 2.2)),
                        "mjsd": _row_ab((0.01, 2.3), (0.01, 2.2))})
    assert same["verdict"] == CO.VERDICT_ROBUST and "agree" in same["why"]
    split = CO.classify({"jajo": _row_ab((0.02, 2.5), (0.02, 2.4)), "fman": _row_ab((0.01, 2.04), (0.01, 1.9)),
                         "mjsd": _row_ab((0.01, 2.3), (0.01, 2.2))})
    assert split["set_a"]["verdict"] == CO.VERDICT_ROBUST
    assert split["set_b"]["verdict"] == CO.VERDICT_CANNOT
    assert split["verdict"] == CO.VERDICT_CANNOT and "disagree" in split["why"]


def test_draw_spread_and_two_disjoint_seed_sets_are_stored():
    rows = _run_offsets(_panel(n_months=40, alpha=0.0), _rule(), n_extra=2)
    for row in rows.values():
        pdw = row["twin"]["per_draw"]
        assert pdw["n"] == 3 and len(pdw["t_blocks"]) == 3
        assert pdw["summary"]["t_min"] <= pdw["summary"]["t_median"] <= pdw["summary"]["t_max"]
    # a second seed set is drawn from seeds disjoint from the first
    panel = _panel(n_months=40, alpha=0.0)
    var = next(iter(CO.offset_variants(_rule()).values()))
    hold: list = []
    m = SL.run_strategy(panel, var, holdings=hold)
    rec = CO.twin_record(var.id, var.k, hold, m)
    grid = sorted(pd.DatetimeIndex(panel.loc[panel["fwd_ret"].notna(), "date"].unique()))
    tw = CO.twin21(rec, panel, cell_id="c@k10", grid=grid, n_extra=2, n_second_set=3)
    assert tw["n_draws"] == 3 and tw["n_draws_setB"] == 3 and len(tw["draw_nets"]) == 6
    assert not tw["twinB_net"].equals(tw["twin21_net"])


# ── review F5 (2026-09-28): the calendar-neutral figure is the headline ──────

def _entry():
    return {"classification": {"verdict": CO.VERDICT_CANNOT,
                               "cum_net_since_2020": {"jajo": 13.23, "fman": 4.24, "mjsd": 4.33}},
            "tranche_average": {"cum_net_since_2020": 6.61, "cum_spy_since_2020": 1.62,
                                "rule_minus_twin21": {"mean_monthly": 0.012, "t_blocks": 2.49},
                                "sealed_rule_minus_twin21": {"mean_monthly": 0.010, "t_blocks": 1.18}}}


def test_calendar_context_leads_with_the_calendar_neutral_book():
    txt = SL.calendar_context({"id": "r", "hold_months": 3}, _entry())
    assert txt.startswith("CALENDAR-NEUTRAL") and "+661%" in txt
    assert txt.index("+661%") < txt.index("+1323%")
    assert "ONE calendar of three" in txt
    no_tr = dict(_entry(), tranche_average={})
    assert "CALENDAR-NEUTRAL NOT COMPUTED" in SL.calendar_context({"id": "r", "hold_months": 3}, no_tr)


def test_the_leaderboard_cum_cell_prints_neutral_first_and_one_calendar_after():
    from scripts import night_backtest_factory as F
    row = {"id": "r", "hold_months": 3, "hindsight_cum_since_2020": 13.23,
           "calendar_neutral": SL.calendar_neutral(_entry())}
    cell = F._cum_cell(row)
    assert cell.index("+661%") < cell.index("+1323%") and "one calendar of three" in cell
    assert "NOT COMPUTED" in F._cum_cell({"id": "q", "hold_months": 3, "hindsight_cum_since_2020": 1.0})
    assert F._cum_cell({"id": "m", "hold_months": 1, "hindsight_cum_since_2020": 1.0}) == "+100%"


def test_leads_that_move_together_are_printed_as_one_bet():
    idx = _month_ends(36)
    rng = np.random.default_rng(1)
    base = rng.normal(0, 0.05, len(idx))
    rows = []
    for rule, noise in (("a", 0.005), ("b", 0.005), ("c", 0.01)):
        for off in SL.QUARTER_OFFSETS:
            r = base + rng.normal(0, noise, len(idx))
            rows.append(pd.DataFrame({"date": idx, "rule_net": r, "rule": rule, "offset": off}))
    corr = CO.cross_rule_correlation(pd.concat(rows, ignore_index=True))
    assert corr["status"] == "OK" and corr["min"] > 0.8
    txt = SL.one_bet_text(corr)
    assert txt.startswith("ONE BET") and "3 independent" in txt
    assert SL.one_bet_text({"status": "NOT_COMPUTED"}) is None
    assert CO.cross_rule_correlation(pd.DataFrame())["status"] == "NOT_COMPUTED"
