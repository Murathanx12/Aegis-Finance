"""AEGIS-PANEL-1 unit tests — offline, no WRDS files opened.

The three properties that would silently corrupt the panel if lost:
the family map claims every JKP characteristic (no quiet UNMAPPED pool),
the label lead refuses month gaps (never 'next observed month'), and the
return/label columns can never re-enter the feature set.
"""

from __future__ import annotations

import pandas as pd
import pytest

from backend.services import aegis_panel as AP


class TestFamilyMap:
    def test_known_jkp_columns_all_mapped(self):
        # a representative slice of every family in the real JKP schema
        cols = ["ret_12_1", "seas_2_5an", "resff3_6_1", "prc_highprc_252d",
                "beta_60m", "ivol_capm_21d", "rmax5_rvol_21d",
                "dolvol_126d", "turnover_126d", "zero_trades_252d",
                "ami_126d", "bidaskhl_21d", "me", "market_equity",
                "assets", "be_me", "eqnpo_12m", "chcsho_6m", "div_at",
                "oaccruals_at", "cowc_gr1a", "noa_at", "at_gr1",
                "capx_gr3", "rd5_at", "saleq_su", "niq_su", "ni_inc8q",
                "gp_at", "qmj", "f_score", "o_score", "kz_index",
                "dsale_dinv", "dgp_dsale", "fi_at", "niq_saleq_std",
                "debt_at", "cash_cl", "tax_pi", "age", "eq_dur",
                "mispricing_perf"]
        fam = AP.family_map(cols)
        unmapped = [c for c, f in fam.items() if f == "UNMAPPED"]
        assert unmapped == [], f"family map lost: {unmapped}"

    def test_first_match_ordering_accruals_before_growth(self):
        fam = AP.family_map(["cowc_gr1a", "at_gr1"])
        assert fam["cowc_gr1a"] == "ACCRUALS"
        assert fam["at_gr1"] == "GROWTH_INVESTMENT"

    def test_unknown_column_is_visible_not_pooled(self):
        assert AP.family_map(["xyz_not_a_char"])["xyz_not_a_char"] \
            == "UNMAPPED"


class TestExcludeList:
    def test_every_return_column_is_excluded(self):
        for c in ("ret", "ret_local", "ret_exc", "ret_exc_lead1m",
                  "ret_lag_dif"):
            assert c in AP.JKP_EXCLUDE, f"label leak: {c} not excluded"

    def test_identity_columns_are_excluded(self):
        for c in ("permno", "gvkey", "date", "eom", "sic", "gics"):
            assert c in AP.JKP_EXCLUDE


class TestSpineLabelLead:
    def _labels(self, frame, monkeypatch, tmp_path):
        p = tmp_path / "spine.parquet"
        frame.to_parquet(p, index=False)
        monkeypatch.setattr(AP, "PIT_PATH", p)
        return AP._spine_labels()

    def test_contiguous_months_get_next_month_return(self, monkeypatch,
                                                     tmp_path):
        f = pd.DataFrame({
            "permno": [1, 1, 1],
            "date": ["2020-01-31", "2020-02-28", "2020-03-31"],
            "ret_incl_delist": [0.01, 0.02, 0.03]})
        out = self._labels(f, monkeypatch, tmp_path)
        jan = out[out["month"] == pd.Period("2020-01", "M")]
        assert float(jan["ret_1m_fwd"].iloc[0]) == pytest.approx(0.02)

    def test_month_gap_yields_nan_never_next_observed(self, monkeypatch,
                                                      tmp_path):
        f = pd.DataFrame({
            "permno": [1, 1],
            "date": ["2020-01-31", "2020-04-30"],   # Feb+Mar missing
            "ret_incl_delist": [0.01, 0.99]})
        out = self._labels(f, monkeypatch, tmp_path)
        jan = out[out["month"] == pd.Period("2020-01", "M")]
        assert jan["ret_1m_fwd"].isna().all(), \
            "a month gap must yield NaN, not a later month's return"

    def test_last_month_has_no_label(self, monkeypatch, tmp_path):
        f = pd.DataFrame({
            "permno": [1, 1],
            "date": ["2020-01-31", "2020-02-28"],
            "ret_incl_delist": [0.01, 0.02]})
        out = self._labels(f, monkeypatch, tmp_path)
        feb = out[out["month"] == pd.Period("2020-02", "M")]
        assert feb["ret_1m_fwd"].isna().all()


class TestRefusals:
    def test_missing_spine_refuses(self, monkeypatch, tmp_path):
        monkeypatch.setattr(AP, "PIT_PATH", tmp_path / "absent.parquet")
        with pytest.raises(AP.PanelRefused):
            AP._spine_labels()

    def test_missing_jkp_refuses(self, monkeypatch, tmp_path):
        monkeypatch.setattr(AP, "JKP_PATH", tmp_path / "absent.parquet")
        with pytest.raises(AP.PanelRefused):
            AP._jkp_features()
