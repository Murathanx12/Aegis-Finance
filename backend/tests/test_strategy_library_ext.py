"""strategy_library_ext: the discovery rows, their claimed numbers, and the loader's refusal."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import strategy_library as sl
from backend.services import strategy_library_ext as ext


def test_every_entry_has_the_required_keys():
    assert ext.EXTRA_STRATEGIES, "the extension list is empty"
    for r in ext.EXTRA_STRATEGIES:
        m = r.meta()
        for k in ext.REQUIRED_KEYS:
            assert k in m, (r.id, k)
        assert m["family"] and m["economic_reason"] and m["source"], r.id
        assert m["first_registered_utc"], r.id


def test_discovery_rows_carry_a_claimed_number():
    disc = [r for r in ext.EXTRA_STRATEGIES if r.source.startswith("discovery:")]
    assert len(disc) >= 15
    assert all(r in ext.DISCOVERY_STRATEGIES for r in disc)
    for r in disc:
        m = r.meta()
        for k in ext.DISCOVERY_KEYS:
            assert m.get(k), (r.id, k)
        assert m["first_registered_utc"] == ext.REGISTERED_DISCOVERY
        assert "http" in m["source"] or "quantpedia" in m["source"], r.id
        # the claim reaches the leaderboard row, which prints literature_reported
        assert m["claimed_number"] in m["literature_reported"]
    for row in ext.EXT_COVERED_BY + ext.EXT_NOT_REACHABLE:
        assert row["id"] and row["source"] and row["claimed_number"] and row["why"], row
    assert all(row["missing_column"] for row in ext.EXT_NOT_REACHABLE)


def test_no_discovery_row_is_filed_twice():
    ids = [r.discovery_id for r in ext.DISCOVERY_STRATEGIES]
    ids += [row["id"] for row in ext.EXT_COVERED_BY + ext.EXT_NOT_REACHABLE]
    assert len(ids) == len(set(ids))


def test_every_extension_rule_was_registered_by_the_loader():
    ours = {r.id for r in ext.EXTRA_STRATEGIES}
    assert sl.EXTRA_SOURCE.startswith("backend.services.strategy_library_ext")
    assert not (set(sl.EXTRA_REFUSED) & ours), sl.EXTRA_REFUSED
    assert ours <= {r.id for r in sl.RULES}


def test_covered_rows_point_at_real_rules():
    ids = {r.id for r in sl.RULES}
    for row in ext.EXT_COVERED_BY:
        assert row["base_rule"] in ids, row


def test_loader_refuses_a_threshold_only_duplicate_of_a_base_rule(monkeypatch):
    """EXT-QC-12 as literally built (5 lowest 252d-vol large caps) IS lowvol_252_large."""
    base = sl.rule_by_id("lowvol_252_large")
    twin = ext.DiscoveryStrategy(
        "qc310_lowvol_5_large", "low_risk", "5 lowest 252d vol, large band",
        sl.col("vol_252", -1), universe_rule="large", k=5, source="discovery:EXT-QC-12 test",
        claimed_number="5Y CAGR 9.8%", economic_reason="x")
    assert twin.signature() == base.signature()
    good = ext.DISCOVERY_STRATEGIES[0]
    base_rules = [r for r in sl.RULES if r.id not in {x.id for x in ext.EXTRA_STRATEGIES}]
    monkeypatch.setattr(sl, "RULES", list(base_rules))
    monkeypatch.setattr(sl, "EXTRA_REFUSED", {})
    monkeypatch.setattr(sl, "EXTRA_SOURCE", sl.EXTRA_SOURCE)
    monkeypatch.setattr(ext, "EXTRA_STRATEGIES", [twin, good])
    sl._load_extra()
    assert "qc310_lowvol_5_large" in sl.EXTRA_REFUSED
    assert "ThresholdVariant" in sl.EXTRA_REFUSED["qc310_lowvol_5_large"]
    assert "lowvol_252_large" in sl.EXTRA_REFUSED["qc310_lowvol_5_large"]
    ids = [r.id for r in sl.RULES]
    assert good.id in ids and "qc310_lowvol_5_large" not in ids
    assert sl.RULES[-1].control                       # controls stay last


def test_derived_columns_are_functions_of_panel_columns():
    p = pd.DataFrame({"mom_252": [0.2, 0.1], "vol_252": [0.4, 0.0],
                      "mkt_stress": [1.0, np.nan],
                      "px_vs_52w_high": [-0.02, -0.5], "px_vs_52w_low": [0.5, 0.0]})
    out = ext.derive_columns(p)
    assert out.loc[0, "sharpe_252"] == pytest.approx(0.5)
    assert np.isnan(out.loc[1, "sharpe_252"])              # zero vol is NaN, not inf
    assert out.loc[0, "mkt_not_stress"] == 0.0 and np.isnan(out.loc[1, "mkt_not_stress"])
    assert out.loc[0, "low_vs_high_252"] == pytest.approx(0.98 / 1.5 - 1.0)
    assert list(p.columns) == ["mom_252", "vol_252", "mkt_stress", "px_vs_52w_high", "px_vs_52w_low"]


def test_discovery_rules_score_on_a_panel_with_their_columns():
    rng = np.random.default_rng(7)
    n = 40
    cols = {c for r in ext.DISCOVERY_STRATEGIES for c in r.requires} - set(ext.DERIVED_COLUMNS)
    cols |= {"mom_252", "vol_252", "mkt_stress", "px_vs_52w_high", "px_vs_52w_low"}
    p = pd.DataFrame({c: rng.normal(size=n) for c in cols})
    p["vol_252"] = np.abs(p["vol_252"]) + 0.1
    p["px_vs_52w_low"] = np.abs(p["px_vs_52w_low"])
    p["px_vs_52w_high"] = -np.abs(p["px_vs_52w_high"]) / 10
    p["gsector"] = rng.integers(0, 4, size=n)
    p["date"] = pd.Timestamp("2024-01-31")
    p["symbol"] = [f"S{i}" for i in range(n)]
    p = ext.derive_columns(p)
    for r in ext.DISCOVERY_STRATEGIES:
        s = r.signal(p)
        assert len(s) == n, r.id


# ── the paper rules (2026-09-26 evening) ──────────────────────────────────────

PAPER_IDS = {"friday_ear_drift", "monday_ear_drift", "quality_momentum_gate",
             "cascade_entry_timing", "disp_short_avoid", "inst_breadth_up",
             "inst_breadth_up_21_40"}


def test_paper_rules_carry_source_claim_falsifier_and_control():
    got = {r.id: r for r in ext.PAPER_STRATEGIES}
    assert PAPER_IDS <= set(got)
    lib = {r.id for r in sl.RULES}
    for r in ext.PAPER_STRATEGIES:
        m = r.meta()
        for k in ext.REQUIRED_KEYS + ext.PAPER_KEYS:
            assert m.get(k) not in (None, "", []), (r.id, k)
        assert m["source"].startswith("literature:") and "doi.org/10." in m["source"], r.id
        assert m["claimed_number"] in m["literature_reported"]
        assert m["first_registered_utc"] == ext.REGISTERED_PAPER
        for c in m["controls"]:                       # a named control is a real rule
            assert c in lib, (r.id, c)
    # the pre-declared pair: Monday is the control, registered with Friday
    assert got["monday_ear_drift"].control and not got["friday_ear_drift"].control
    assert "monday_ear_drift" in got["friday_ear_drift"].controls
    assert got["inst_breadth_up_21_40"].control


def test_paper_rules_were_accepted_by_register():
    assert not (set(sl.EXTRA_REFUSED) & PAPER_IDS), sl.EXTRA_REFUSED
    assert PAPER_IDS <= {r.id for r in sl.RULES}
    base = [r for r in sl.RULES if r.id not in {x.id for x in ext.EXTRA_STRATEGIES}]
    lib = list(base)
    for r in ext.CHUNK_C_STRATEGIES + ext.DISCOVERY_STRATEGIES + ext.PAPER_STRATEGIES:
        sl.register(lib, r)                           # no ThresholdVariant, no id clash
    # quality_momentum_gate is NOT mom_in_high_margin relabelled: it differs by holding
    q, m = sl.rule_by_id("quality_momentum_gate"), sl.rule_by_id("mom_in_high_margin")
    assert q.shape == m.shape and q.signature() != m.signature() and q.hold_months == 3


def test_ear_filed_dow_is_derived_from_columns_dated_before_the_decision():
    d = pd.Timestamp("2024-03-29")                    # a Friday
    p = pd.DataFrame({"date": [d] * 5, "symbol": list("ABCDE"),
                      # A: filed 2024-03-22 (Fri); B: 2024-03-25 (Mon); C: NO earnings;
                      # D: age 0 = filed ON the decision date; E: an event AFTER it
                      "days_since_earn": [7.0, 4.0, np.nan, 0.0, -3.0],
                      "ear_last": [0.05, 0.04, np.nan, 0.9, 0.9]})
    out = ext.derive_columns(p)
    assert out.loc[0, "ear_filed_dow"] == 4.0 and out.loc[1, "ear_filed_dow"] == 0.0
    assert out.loc[2:, "ear_filed_dow"].isna().all()  # nothing on/after the date leaks
    fri = sl.rule_by_id("friday_ear_drift").signal(out)
    mon = sl.rule_by_id("monday_ear_drift").signal(out)
    assert fri.notna().tolist() == [True, False, False, False, False]
    assert mon.notna().tolist() == [False, True, False, False, False]


def test_cluster_age_uses_only_raises_strictly_before_the_date():
    rev = pd.DataFrame({
        "ticker": ["AAA"] * 5 + ["BBB"],
        "event_date": ["2024-01-02", "2024-01-20", "2024-02-10", "2024-02-29", "2024-03-05",
                       "2024-01-05"],
        "target_action": ["Raises", "Raises", "Raises", "Raises", "Raises", "Lowers"]})
    p = pd.DataFrame({"symbol": ["AAA", "AAA", "BBB"],
                      "date": pd.to_datetime(["2024-02-29", "2024-04-30", "2024-02-29"])})
    age = ext.cluster_age_days(p, rev)
    # 02-29: the raise ON the date is excluded; the chain 01-02 -> 01-20 -> 02-10 is active
    assert age[0] == (pd.Timestamp("2024-02-29") - pd.Timestamp("2024-01-02")).days
    # 04-30: last raise 03-05 is 56 days old -> no active cluster
    assert np.isnan(age[1])
    assert np.isnan(age[2])                            # lowers are not raises


def test_13f_quarter_is_usable_only_after_rdate_plus_45_days():
    q = [["2023-09-30", "11111111", 1.0, 10, 1.0], ["2023-12-31", "11111111", 1.0, 20, 1.0],
         ["2024-03-31", "11111111", 1.0, 30, 1.0],
         ["2023-06-30", "22222222", 1.0, 10, 1.0], ["2023-12-31", "22222222", 1.0, 40, 1.0]]
    link = {"11111111": 1, "22222222": 2}
    crsp = pd.DataFrame({"permno": [1, 1, 2, 2], "ticker": ["AAA", "AAA", "BBB", "BBB"],
                         "date": pd.to_datetime(["2020-01-31", "2024-11-29"] * 2)})
    fr = ext.inst_breadth_frame(q, link, crsp)
    assert ext.FILING_LAG_13F_DAYS == 45
    assert (fr["available"] - fr["rdate"]).dt.days.eq(45).all()
    assert set(fr["symbol"]) == {"AAA"}                # BBB skipped a quarter: no change
    on = pd.Timestamp("2023-12-31") + pd.Timedelta(days=45)
    p = pd.DataFrame({"symbol": ["AAA"] * 3,
                      "date": [on, on + pd.Timedelta(days=1), pd.Timestamp("2024-05-16")]})
    got = ext._asof_join(p, fr, ["inst_breadth_chg"], on_right="available", exact=False,
                         max_age_days=ext.MAX_13F_AGE_DAYS, age_from="rdate")["inst_breadth_chg"]
    assert np.isnan(got[0])                            # ON the deadline: not yet (strict)
    assert got[1] == pytest.approx(np.log(20 / 10))    # the day after: Q4 vs Q3
    assert got[2] == pytest.approx(np.log(30 / 20))    # Q1 2024 once 2024-05-15 has passed


def test_extraction_tag_list_carries_rd_and_sga():
    from scripts.pull_sec_fundamentals import FACTS
    assert "ResearchAndDevelopmentExpense" in FACTS["rd"]
    assert FACTS["sga"][0] == "SellingGeneralAndAdministrativeExpense"
    assert set(ext.INTANGIBLE_FACTS) == {"rd", "sga"}


def test_intangible_rules_are_in_exactly_one_place():
    paper = {r.id for r in ext.PAPER_STRATEGIES}
    waiting = {row.get("rule_id") for row in ext.EXT_NOT_REACHABLE}
    for rid in ("rd_intensity", "org_capital"):
        assert (rid in paper) != (rid in waiting), rid
        if rid in waiting:
            row = next(x for x in ext.EXT_NOT_REACHABLE if x.get("rule_id") == rid)
            assert row["missing_column"].startswith(rid)
    assert ("rd_intensity" in paper) == ext.INTANGIBLES_EXTRACTED


def test_intangibles_frame_reads_annual_first_filings_at_filed_plus_two():
    f = pd.DataFrame({
        "ticker": ["AAA"] * 6, "fact": ["rd", "rd", "sga", "assets", "sga", "assets"],
        "filed": pd.to_datetime(["2023-02-20", "2023-05-01", "2023-02-20", "2023-02-20",
                                 "2024-02-20", "2024-02-20"]),
        "end": ["2022-12-31", "2023-03-31", "2022-12-31", "2022-12-31", "2023-12-31", "2023-12-31"],
        "period_days": [364, 90, 364, np.nan, 364, np.nan],
        "val": [10.0, 3.0, 25.0, 100.0, 30.0, 120.0]})
    fr = ext.intangibles_frame(f).set_index("filed")
    y1 = fr.loc[pd.Timestamp("2023-02-20")]
    assert y1["rd_intensity"] == pytest.approx(0.10)  # the 90-day quarter is ignored
    assert y1["org_capital"] == pytest.approx(25.0 / 0.25 / 100.0)
    y2 = fr.loc[pd.Timestamp("2024-02-20")]
    assert y2["org_capital"] == pytest.approx((0.85 * 100.0 + 30.0) / 120.0)
    assert (fr["available"] - fr.index.to_series()).dt.days.eq(2).all()


def test_excluding_top_keeps_names_without_the_screen_column():
    p = pd.DataFrame({"date": pd.Timestamp("2024-01-31"), "symbol": list("ABCDEFGHIJK"),
                      "mom_252_21": np.arange(11, dtype=float),
                      "target_cv_180": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 5.0, np.nan]})
    s = sl.rule_by_id("disp_short_avoid").signal(p)
    assert np.isnan(s.iloc[9])                         # the top-decile dispersion name is out
    assert s.iloc[10] == 10.0                          # no reading: kept, not filtered away
    assert s.iloc[:9].notna().all()


# ── paper rules round 2 (2026-09-27): SSRN via OpenClaw, the VAL-01 fix ────────

ROUND2_FIVE = ("news_tone_reversal_5d", "filing_similarity_change", "distance_to_default_rising",
               "call_tone_drift", "opex_week_large_hold")


def test_round2_rules_carry_source_claim_falsifier_controls_and_twin():
    lib = {r.id for r in sl.RULES}
    for r in ext.ROUND2_STRATEGIES + ext.VALUE_UNLOCK_STRATEGIES:
        m = r.meta()
        for k in ext.REQUIRED_KEYS + ext.PAPER_KEYS:
            assert m.get(k) not in (None, "", []), (r.id, k)
        assert m["first_registered_utc"] == ext.REGISTERED_ROUND2
        assert m["claimed_number"] in m["literature_reported"]
        for c in m["controls"]:                       # a named control is a real rule
            assert c in lib, (r.id, c)
    got = {r.id: r for r in ext.ROUND2_STRATEGIES}
    for rid in ("distance_to_default_rising", "news_tone_reversal_5d"):
        twin = got[f"{rid}_21_40"]
        assert twin.control and f"{rid}_21_40" in got[rid].controls
        assert "rank_band" in twin.shape and "21-40" in twin.shape
    assert got["news_tone_reversal_5d"].forward_only and got["news_tone_reversal_5d_21_40"].forward_only
    assert not got["distance_to_default_rising"].forward_only
    assert got["distance_to_default_rising_in_stress"].regime_gate == "mkt_stress"


def test_each_of_the_five_is_in_exactly_one_place():
    registered = {r.id for r in ext.ROUND2_STRATEGIES}
    waiting = {row.get("rule_id"): row for row in ext.EXT_NOT_REACHABLE if row.get("rule_id")}
    for rid in ROUND2_FIVE:
        assert (rid in registered) != (rid in waiting), rid
        if rid in waiting:
            row = waiting[rid]
            assert row["missing_column"] and row["free_source"] and row["falsifier"], rid
            assert row["controls"], rid
    assert {"filing_similarity_change", "call_tone_drift", "opex_week_large_hold"} <= set(waiting)


def test_round2_rules_were_accepted_by_the_loader():
    ours = {r.id for r in ext.ROUND2_STRATEGIES + ext.VALUE_UNLOCK_STRATEGIES}
    assert not (set(sl.EXTRA_REFUSED) & ours), sl.EXTRA_REFUSED
    assert ours <= {r.id for r in sl.RULES}


def test_value_unlocks_leave_ext_not_reachable_only_when_the_inputs_exist():
    ids = {row["id"] for row in ext.EXT_NOT_REACHABLE}
    unl = {r.discovery_id for r in ext.VALUE_UNLOCK_STRATEGIES}
    if ext.VALUE_INPUTS_PRESENT:
        assert unl == set(ext.VALUE_UNLOCKS) and not (ids & unl)
    else:
        assert not unl and set(ext.VALUE_UNLOCKS) <= ids


def _split_world():
    """One name; a 2:1 split on 2024-07-01, AFTER the decision date 2024-05-31.

    Raw price 100 at the 2024-03-31 quarter end (10 shares -> raw mv 1,000),
    110 on the decision date (true mv 1,100). The vendor's adjusted series
    halves every close before the split: 50 and 55.
    """
    days = pd.bdate_range("2023-12-01", "2024-08-30")
    raw = np.where(days < pd.Timestamp("2024-01-15"), 90.0,
                   np.where(days < pd.Timestamp("2024-04-15"), 100.0, 110.0))
    raw = np.where(days >= pd.Timestamp("2024-07-01"), raw / 2.0, raw)
    adj = np.where(days < pd.Timestamp("2024-07-01"), raw / 2.0, raw)
    px = pd.DataFrame({"symbol": "AAA", "date": days, "close": adj})
    fundq = pd.DataFrame({"gvkey": ["1", "1", "1"],
                          "datadate": ["2024-03-31", "2024-06-30", "2023-12-31"],
                          # the June quarter is reported 2024-07-25: after the decision date
                          "rdq": ["2024-04-25", "2024-07-25", "2024-02-01"],
                          "cshoq": [10e-6, 20e-6, 10e-6], "prccq": [100.0, 55.0, 90.0]})
    sec = pd.DataFrame({"tic": ["AAA"], "gvkey": ["1"], "iid": ["01"], "excntry": ["USA"]})
    return px, fundq, sec


def _mv_at(a, px, day):
    return ext.market_value_column(pd.DataFrame({"symbol": ["AAA"], "date": [pd.Timestamp(day)]}), a, px)[0]


def test_market_value_is_split_invariant_and_point_in_time():
    px, fundq, sec = _split_world()
    a = ext.market_value_anchors(fundq, ext.compustat_ticker_map(sec))
    t = pd.Timestamp("2024-05-31")
    assert _mv_at(a, px, t) == pytest.approx(1100.0)       # raw 1,000 x adj 55 / adj 50
    naive = ext.closes_at(px, ["AAA"], [t])[0] * 10.0
    assert naive == pytest.approx(550.0)                   # the refused VAL-01 construction: halved
    # the June anchor is public at rdq + 2d = 2024-07-27; before that the March one rolls on
    assert _mv_at(a, px, "2024-07-26") == pytest.approx(1000.0 * 55.0 / 50.0)
    assert _mv_at(a, px, "2024-07-29") == pytest.approx(20.0 * 55.0)
    # an anchor available ON the decision date is not used (strictly before)
    a2 = a.copy()
    a2.loc[a2["datadate"] == pd.Timestamp("2024-03-31"), "available"] = t
    assert _mv_at(a2, px, t) == pytest.approx(10.0 * 90.0 * 55.0 / 45.0)   # the December anchor


def test_market_value_is_nan_when_the_anchor_is_stale():
    px, fundq, sec = _split_world()
    a = ext.market_value_anchors(fundq, ext.compustat_ticker_map(sec))
    late = pd.Timestamp("2024-06-30") + pd.Timedelta(days=ext.MV_STALE_DAYS + 5)
    px2 = pd.concat([px, pd.DataFrame({"symbol": ["AAA"], "date": [late], "close": [60.0]})])
    assert np.isnan(_mv_at(a, px2, late))


def test_ticker_map_drops_a_ticker_two_gvkeys_claim():
    sec = pd.DataFrame({"tic": ["AAA", "AAA", "BBB", "BBB"], "gvkey": ["1", "2", "3", "3"],
                        "iid": ["01", "01", "02", "01"], "excntry": ["USA"] * 4})
    m = ext.compustat_ticker_map(sec)
    assert "AAA" not in m and m["BBB"] == "3"


def test_round2_columns_use_only_filings_before_the_date():
    px, fundq, sec = _split_world()
    t = pd.Timestamp("2024-05-31")
    facts = pd.DataFrame({
        "ticker": ["AAA"] * 4, "fact": ["equity", "debt", "equity", "cash"],
        "filed": pd.to_datetime(["2024-05-01", "2024-05-01", "2024-05-30", "2024-05-01"]),
        "end": ["2024-03-31", "2024-03-31", "2024-04-30", "2024-03-31"],
        "period_days": [np.nan] * 4, "val": [550.0, 300.0, 9999.0, 50.0]})
    panel = pd.DataFrame({"symbol": ["AAA"], "date": [t], "is_month_end": [True],
                          "vol_252": [0.4], "mom_252": [0.1]})
    W = {"dates": px["date"].values, "symbols": np.array(["AAA"]), "close": px["close"].to_numpy()[:, None]}
    out, info = ext.attach_round2_columns(panel, W, fundq=fundq, security=sec, facts=facts)
    # equity filed 2024-05-30 is available 06-01 > t: the 05-01 filing (550) is used
    assert out.loc[0, "book_to_market"] == pytest.approx(550.0 / 1100.0)
    assert out.loc[0, "d2d"] == pytest.approx(ext.distance_to_default([1100.0], [300.0], [0.4], [0.1])[0])
    assert np.isnan(out.loc[0, "earnings_yield"])          # no annual net income filed
    assert out.loc[0, "is_opex_week"] == 0.0
    assert "news_tone_z" not in out.columns or out["news_tone_z"].isna().all()


def test_distance_to_default_is_nan_without_debt_and_falls_with_leverage():
    dd = ext.distance_to_default([100.0, 100.0, 100.0, 100.0], [0.0, np.nan, 10.0, 90.0],
                                 [0.3] * 4, [0.05] * 4)
    assert np.isnan(dd[0]) and np.isnan(dd[1])
    assert dd[2] > dd[3] > 0


def test_d2d_change_reads_only_the_previous_row_and_its_gap():
    p = pd.DataFrame({"symbol": ["A", "A", "A", "B"],
                      "date": pd.to_datetime(["2024-01-31", "2024-02-29", "2024-05-31", "2024-02-29"])})
    ch = ext.prev_panel_change(p, [1.0, 1.5, 9.0, 2.0])
    assert np.isnan(ch[0]) and ch[1] == pytest.approx(0.5)
    assert np.isnan(ch[2]) and np.isnan(ch[3])            # a 92-day gap is not a monthly change
    ch2 = ext.prev_panel_change(p, [1.0, 1.5, -50.0, 2.0])   # a later value changes no earlier row
    assert ch2[1] == pytest.approx(0.5)


def test_opex_week_flag_and_why_the_monthly_engine_cannot_hold_it():
    d = pd.to_datetime(["2024-03-11", "2024-03-15", "2024-03-17", "2024-03-18", "2024-03-08"])
    assert list(ext.is_opex_week(d)) == [1.0, 1.0, 1.0, 0.0, 0.0]
    month_ends = pd.bdate_range("2017-01-01", "2026-09-30", freq="BME")
    assert ext.is_opex_week(month_ends).sum() == 0       # the measured engine mismatch


def test_attach_news_tone_refuses_without_a_cache():
    p = pd.DataFrame({"symbol": ["A"], "date": [pd.Timestamp("2026-09-25")], "is_month_end": [True]})
    out, info = ext.attach_news_tone(p, None, tone_rows=[])
    assert "news_tone_z" not in out.columns and info["news_tone_z"].startswith("AWAITING SCORING")


# ── VAL-01 identity by the dated CCM link (review 2026-09-27 §4a) ─────────────

def _renamed_world():
    """gvkey 100 / permno 1 traded as OLD until 2020-03-01, then NEW (still NEW
    when CRSP was cut 2024-12-31). gvkey 200 / permno 2 took the ticker OLD in
    2022. Compustat's CURRENT tic for gvkey 100 is NEW."""
    lnk = pd.DataFrame({"gvkey": ["100", "200"], "linkprim": ["P", "P"], "linktype": ["LC", "LU"],
                        "lpermno": [1.0, 2.0], "linkdt": ["2010-01-01", "2021-06-01"],
                        "linkenddt": [None, None]})
    names = pd.DataFrame({"permno": [1, 1, 2, 2],
                          "namedt": ["2010-01-01", "2020-03-02", "2021-06-01", "2022-01-03"],
                          "nameenddt": ["2020-03-01", "2024-12-31", "2022-01-02", "2024-12-31"],
                          "ticker": ["OLD", "NEW", "ZZZ", "OLD"]})
    return ext.ccm_dated_link(lnk, names)


def test_a_renamed_security_maps_to_its_old_ticker_for_2019_decisions():
    link = _renamed_world()
    gv, how = ext.pit_gvkeys(["OLD", "NEW", "OLD", "NEW"],
                             ["2019-06-28", "2021-06-30", "2023-06-30", "2026-06-30"], link)
    assert list(gv) == ["100", "100", "200", "100"]
    assert list(how) == ["pit", "pit", "pit", "pit"]          # 2026: the open CRSP name
    # the old current-tic map cannot place the 2019 row at all
    sec = pd.DataFrame({"tic": ["NEW", "OLD"], "gvkey": ["100", "200"], "iid": ["01", "01"],
                        "excntry": ["USA", "USA"]})
    assert ext.compustat_ticker_map(sec).get("OLD") == "200"   # ...and would give it gvkey 200


def test_one_symbol_per_series_falls_back_to_the_last_ticker():
    link = _renamed_world()
    # the price panel carries NEW back to 2016 (Alpaca's convention): no PIT
    # match in 2018, so the security's last CRSP ticker places it
    gv, how = ext.pit_gvkeys(["NEW"], ["2018-01-31"], link)
    assert gv[0] == "100" and how[0] == "last_ticker"
    # a symbol no interval and no map knows stays unplaced; the current tic
    # places a post-CRSP rename only when asked to
    gv, how = ext.pit_gvkeys(["BRANDNEW"], ["2026-01-30"], link)
    assert gv[0] is None and how[0] is None
    gv, how = ext.pit_gvkeys(["BRANDNEW"], ["2026-01-30"], link, current_map={"BRANDNEW": "100"})
    assert gv[0] == "100" and how[0] == "current_tic"


def test_a_row_two_gvkeys_claim_is_dropped():
    lnk = pd.DataFrame({"gvkey": ["1", "2"], "linkprim": ["P", "P"], "linktype": ["LC", "LC"],
                        "lpermno": [1.0, 2.0], "linkdt": ["2010-01-01"] * 2, "linkenddt": [None] * 2})
    names = pd.DataFrame({"permno": [1, 2], "namedt": ["2010-01-01"] * 2,
                          "nameenddt": ["2024-12-31"] * 2, "ticker": ["DUP", "DUP"]})
    gv, how = ext.pit_gvkeys(["DUP"], ["2020-01-31"], ext.ccm_dated_link(lnk, names))
    assert gv[0] is None and how[0] == "ambiguous"


def test_linked_market_value_rolls_the_rows_own_series_across_a_rename():
    link = _renamed_world()
    fundq = pd.DataFrame({"gvkey": ["100"], "datadate": ["2019-03-31"], "rdq": ["2019-04-25"],
                          "cshoq": [10.0], "prccq": [50.0]})
    px = pd.DataFrame({"symbol": ["OLD", "OLD"], "date": pd.to_datetime(["2019-03-29", "2019-06-28"]),
                       "close": [25.0, 30.0]})           # adjusted: a later 2:1 split halves both
    panel = pd.DataFrame({"symbol": ["OLD"], "date": pd.to_datetime(["2019-06-28"])})
    gv, _ = ext.pit_gvkeys(panel["symbol"], panel["date"], link)
    mv = ext.market_value_column_linked(panel, ext.market_value_anchors_by_gvkey(fundq), px, gv)
    assert mv[0] == pytest.approx(10.0 * 50.0 * 1e6 * 30.0 / 25.0)


def test_val01_counts_the_renamed_dead_population():
    sec = pd.DataFrame({"tic": ["AXTC.1", "LIVE", "GONE"], "gvkey": ["100", "300", "400"],
                        "iid": ["01", "01", "01"], "excntry": ["USA"] * 3,
                        "secstat": ["I", "A", "I"], "dldtei": ["2018-05-01", None, "2019-01-01"]})
    lnk = pd.DataFrame({"gvkey": ["100"], "linkprim": ["P"], "linktype": ["LC"], "lpermno": [1.0],
                        "linkdt": ["2010-01-01"], "linkenddt": ["2018-05-01"]})
    names = pd.DataFrame({"permno": [1], "namedt": ["2010-01-01"], "nameenddt": ["2018-05-01"],
                          "ticker": ["AXTC"]})
    c = ext.val01_mapping_counts(sec, ext.ccm_dated_link(lnk, names, data_end="2024-12-31"),
                                 panel_symbols={"AXTC"})
    assert c["inactive_since"] == 2 and c["renamed_suffixed_tic"] == 1
    assert c["now_map"] == 1 and c["now_map_unsuffixed_ticker"] == 1 and c["in_panel"] == 1


def _value_panel():
    d1, d2 = pd.Timestamp("2026-02-27"), pd.Timestamp("2026-04-30")
    rows = []
    for d, bm in ((d1, [0.9, 0.5, 0.2]), (d2, [np.nan, np.nan, np.nan])):
        for s, v in zip(["A", "B", "C"], bm):
            rows.append({"date": d, "symbol": s, "book_to_market": v, "eligible": True,
                         "median_dollar_vol": 5e7, "fwd_ret": 0.01, "is_month_end": True})
    return pd.DataFrame(rows)


def test_a_date_with_zero_eligible_names_refuses():
    rule = sl.Strategy("t_bm", "value", "b/m", sl.col("book_to_market"), k=2)
    p = _value_panel()
    el = ext.eligible_names_by_date(p, rule)
    assert el["by_date"] == {"2026-02-27": 3, "2026-04-30": 0}
    assert el["refused_dates"] == ["2026-04-30"]
    # the engine alone keeps the February book and prints an April return ...
    raw = sl.run_strategy(p, rule, k=2)
    assert pd.Timestamp("2026-04-30") in set(raw["date"])
    # ... the value runner refuses that period instead
    m = ext.run_value_rule(p, rule)
    assert pd.Timestamp("2026-04-30") not in set(m["date"])
    assert m.attrs["eligibility"]["n_periods_refused"] == 1
    rec = ext.value_rule_receipts(p, [rule])
    assert rec["t_bm"]["n_refused"] == 1
