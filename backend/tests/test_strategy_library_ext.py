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
