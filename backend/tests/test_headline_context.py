"""Lane M2 (2026-09-28): a leaderboard never shows a big number alone.

Every row that prints a return carries, beside it: the matched-twin verdict, the
family verdict, DSR, the CAGR without the best 5 months, and for a quarterly
rule the spread across its calendar offsets. A field not computed prints
NOT COMPUTED, never a blank. Synthetic rows only; no network.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from backend.services import strategy_library as SL
from scripts import night_backtest_factory as F


def _row(rid="rule_q", k=20, hold=3, family="momentum", dsr=0.2, wo=0.12, spy_wo=0.09):
    return {"id": rid, "family": family, "k": k, "hold_months": hold, "dsr": dsr,
            "dsr_n_trials": 868, "cagr_without_best_5_months": wo,
            "spy_cagr_without_best_5_months": spy_wo, "spy_cagr_same_window": 0.15,
            "worst_cell": {"k": 10, "cagr_since_2020": 0.1}, "by_year_signs": "+-+",
            "hindsight_cagr_since_2020": 0.5, "hindsight_spy_cagr_since_2020": 0.157,
            "hindsight_cum_since_2020": 13.2, "sealed_vs_spy": 0.38}


def _sources():
    twin = {"cell": "rule_q@k20",
            "dev": {"t_monthly_rule_minus_twin21": 2.4, "mean_monthly_rule_minus_twin21": 0.015},
            "sealed": {"t_monthly_rule_minus_twin21": 1.1, "mean_monthly_rule_minus_twin21": 0.01}}
    fam = {"family": "momentum", "rule_minus_twin": {"verdict": "CANNOT_DISTINGUISH"},
           "vs_spy": {"verdict": "CANNOT_DISTINGUISH", "alpha_sign": "+"}}
    off = {"rule_q": {"classification": {"verdict": "CANNOT_DISTINGUISH",
                                         "cum_net_since_2020": {"jajo": 13.2, "fman": 4.2, "mjsd": 4.3}}}}
    return {"twins": {"run": "R1", "by_key": {"rule_q@k20": twin}},
            "families": {"run": "R1", "by_key": {"momentum": fam}, "too_small": []},
            "offsets": {"run": "R2", "by_key": off}}


def test_no_source_prints_not_computed_never_blank():
    ctx = SL.headline_context(_row())
    assert set(ctx) == set(SL.HEADLINE_CONTEXT_FIELDS)
    for f in ("matched_twin", "family", "calendar_offsets"):
        assert ctx[f] == SL.NOT_COMPUTED
    txt = SL.headline_context_text(ctx)
    for name in ("twin:", "family:", "DSR:", "w/o best 5:", "calendar:"):
        assert name in txt
    assert "::" not in txt and ": ;" not in txt and not txt.endswith(": ")


def test_missing_dsr_and_without_best_5_print_not_computed():
    ctx = SL.headline_context(_row(dsr=None, wo=None))
    assert ctx["dsr"] == SL.NOT_COMPUTED and ctx["without_best_5"] == SL.NOT_COMPUTED


def test_sources_fill_every_field_and_name_a_foreign_run():
    s = _sources()
    ctx = SL.headline_context(_row(), twins=s["twins"], families=s["families"], offsets=s["offsets"],
                              board_run="R1")
    assert ctx["matched_twin"].startswith("CANNOT_DISTINGUISH")       # t >= 2 in dev only
    assert "monthly t on a 3-month hold overstates" in ctx["matched_twin"]
    assert "momentum: vs twin CANNOT_DISTINGUISH" in ctx["family"]
    assert "jajo +1320%" in ctx["calendar_offsets"] and "fman +420%" in ctx["calendar_offsets"]
    assert "[offsets R2]" in ctx["calendar_offsets"]                  # another run is labelled
    assert "[twins" not in ctx["matched_twin"]                        # the board's own run is not
    assert "SPY without its best 5 +9.0%" in ctx["without_best_5"]


def test_twin_alpha_needs_both_windows_with_one_sign():
    s = _sources()
    s["twins"]["by_key"]["rule_q@k20"]["sealed"]["t_monthly_rule_minus_twin21"] = 2.2
    ctx = SL.headline_context(_row(), twins=s["twins"])
    assert ctx["matched_twin"].startswith("ALPHA_DETECTED +")


def test_a_monthly_rule_has_no_calendar_spread_and_says_so():
    ctx = SL.headline_context(_row(hold=1))
    assert ctx["calendar_offsets"].startswith("n/a (hold 1 month")


def test_a_small_family_is_named_not_blank():
    s = _sources()
    s["families"]["too_small"] = ["momentum"]
    ctx = SL.headline_context(_row(), families=s["families"])
    assert ctx["family"].startswith(SL.NOT_COMPUTED) and "too few" in ctx["family"]


def test_every_rendered_table_row_carries_the_beside_column():
    rows = [_row(), _row(rid="m1", hold=1, family="trend")]
    board = {"run_id": "R1", "top_by_dsr": rows}
    F.annotate_headline_context(board, _sources())
    for lines in (F._table(board["top_by_dsr"]), F._sealed_table(board["top_by_dsr"])):
        assert "BESIDE THE HEADLINE" in lines[0]
        n_cols = lines[0].count("|")
        for ln in lines[2:]:
            assert ln.count("|") == n_cols
            assert "twin:" in ln and "family:" in ln and "DSR:" in ln and "calendar:" in ln
    # the monthly rule without a twin row: NOT COMPUTED, not blank
    ln = F._table([rows[1]])[2]
    assert "twin: NOT COMPUTED" in ln


def test_an_unannotated_row_still_renders_every_field():
    ln = F._table([_row()])[2]
    assert "twin: NOT COMPUTED" in ln and "calendar: NOT COMPUTED" in ln and "DSR: 0.200" in ln


def test_headline_sources_prefer_the_run_and_refuse_by_name(tmp_path):
    lib, ss = tmp_path / "lib", tmp_path / "ss"
    lib.mkdir()
    ss.mkdir()
    (ss / "matched_twins_2026-01-01T000000Z.json").write_text(json.dumps(
        {"run_id": "2026-01-01T000000Z", "rows": [{"cell": "a@k20"}]}), encoding="utf-8")
    (ss / "matched_twins_2026-02-01T000000Z.json").write_text(json.dumps(
        {"run_id": "2026-02-01T000000Z", "rows": [{"cell": "b@k20"}]}), encoding="utf-8")
    src = F.headline_sources("2026-01-01T000000Z", lib=lib, ss=ss)
    assert src["twins"]["run"] == "2026-01-01T000000Z"
    src2 = F.headline_sources("none", lib=lib, ss=ss)
    assert src2["twins"]["run"] == "2026-02-01T000000Z"          # newest when the run has none
    assert src2["families"] is None and "family_pool" in src2["why"]["families"]
    board = F.annotate_headline_context({"run_id": "x", "all_rows": [_row()]}, src2)
    assert board["headline_context_sources"]["offsets"].startswith(SL.NOT_COMPUTED)


def test_evaluate_prints_spy_without_its_own_best_5_months():
    idx = pd.date_range(end=pd.Timestamp.today().normalize() - pd.offsets.MonthEnd(1),
                        periods=30, freq="BME")
    rng = np.random.default_rng(1)
    spy = pd.Series(rng.normal(0.01, 0.04, 30), index=idx)
    m = pd.DataFrame({"date": idx, "gross": spy.values + 0.001, "cost": 0.0, "net": spy.values + 0.001,
                      "turnover": 0.0, "n_held": 20, "n_delisted": 0, "rebalanced": True})
    ev = SL.evaluate(m, spy)
    lr = np.sort(np.log1p(spy.values))[:-5]
    assert ev["spy_cagr_without_best_5_months"] == np.float64(np.exp(lr.sum() * 12 / 25) - 1)
    assert ev["spy_cagr_without_best_5_months"] < ev["spy_cagr_same_window"]
