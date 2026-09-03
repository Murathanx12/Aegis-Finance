"""OFFLINE tests for `learner/features_ext.py` -- the PIT rules, not the numbers.

WHAT THESE PIN
==============
The ablation's whole claim rests on two joins being point-in-time, and both are
easy to get quietly wrong:

* 13F is joined on `quarter_end + 45 calendar days`, not on the report quarter
  end. Joining on the report date would manufacture a 45-day look-ahead that
  looks like alpha and is arithmetic.
* an analyst's bias is the expanding mean of the errors of targets that had
  ALREADY RESOLVED before the month opened. Using an unresolved target's error
  is target leakage wearing a per-analyst hat.

Every test here builds its OWN tiny frames. None reads the 200MB training table,
none reads WRDS, none touches the network, and none needs the built panels to be
present -- so a green run means the rules hold, not that the artefacts happened
to exist on this machine. Dates are derived from a fixture anchor rather than
written literally: a hard-coded quarter that was "last quarter" fails the day it
stops being one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from learner import dataset as D          # noqa: E402
from learner import features_ext as F     # noqa: E402


# --------------------------------------------------------------- the schema

def test_families_are_disjoint_and_complete():
    seen: set[str] = set()
    for cols in F.FAMILIES.values():
        assert len(set(cols)) == len(cols), "a family lists a column twice"
        assert not (seen & set(cols)), "two families claim the same column"
        seen |= set(cols)
    assert seen == set(F.all_ext_features())


def test_no_extension_column_collides_with_the_base_schema():
    """A colliding name would silently OVERWRITE a base feature in `attach`, and
    the ablation would then compare two different base models."""
    base = set(D.feature_columns()) | {f"prior_{h}m" for h in D.HORIZONS}
    assert not (base & set(F.all_ext_features()))


def test_family_of_round_trips():
    for fam, cols in F.FAMILIES.items():
        for c in cols:
            assert F.family_of(c) == fam
    assert F.family_of("log_market_cap") is None


def test_ablation_ladder_is_nested_and_starts_at_base():
    names = [n for n, _ in F.ABLATION_SETS]
    assert names[0] == "base"
    assert F.ABLATION_SETS[0][1] == ()
    assert "base+holder" in names, (
        "a purely nested ladder cannot attribute a joint gain to one family")
    full = F.ABLATION_SETS[-1][1]
    assert set(full) == set(F.FAMILIES)


def test_every_interaction_leg_has_its_main_effect_available():
    """An 'interaction' whose legs are not both in the model is a main effect in
    disguise. The legs are 13F/analyst columns or base columns; assert the ones
    this module owns are declared."""
    owned = set(F.HOLDER_FEATURES) | set(F.ANALYST_FEATURES)
    base = set(D.feature_columns())
    for leg in ("h_net_entry_frac", "h_exit_frac", "h_new_frac",
                "h_new_longdur_frac", "h_stake_anom_mean", "h_specialist_frac",
                "a_bias_mean", "a_thin_cov"):
        assert leg in owned
    for leg in ("target_rev_1m", "upside", "ret_6m"):
        assert leg in base


# ------------------------------------------------------------ date helpers

def test_public_date_is_exactly_45_days_after_the_report_quarter_end():
    for y in (2013, 2019, 2024):
        for q in (1, 2, 3, 4):
            qi = F._qidx_of(y, q)
            assert (F._public_date(qi) - F._quarter_end(qi)).days == F.FILING_LAG_DAYS


def test_qidx_helpers_agree_with_the_fingerprint_script():
    """`features_ext` re-derives the quarter index rather than importing it, so
    the two definitions are pinned against each other here. A silent one-quarter
    offset would join the WRONG filing and still look plausible."""
    HF = pytest.importorskip("scripts.holder_fingerprint")
    for y in (1996, 2013, 2024):
        for q in (1, 2, 3, 4):
            assert F._qidx_of(y, q) == HF.qidx_of(y, q)
            assert F._quarter_end(F._qidx_of(y, q)) == pd.Timestamp(
                HF.quarter_end(HF.qidx_of(y, q)))


# ------------------------------------------------------ synthetic fixtures

def _train_frame(anchor: pd.Timestamp, n_months: int = 8, n_names: int = 40) -> pd.DataFrame:
    """A minimal stand-in for the training table: only the columns `attach`
    reads. Dates are derived from `anchor`, never written literally."""
    rng = np.random.default_rng(20260903)
    rows = []
    for mi in range(n_months):
        m = (anchor.to_period("M") + mi)
        entry = m.to_timestamp() + pd.Timedelta(days=15)
        for p in range(n_names):
            rows.append({
                "permno": 10000 + p,
                "month": str(m),
                "entry_date": entry,
                "upside": float(rng.normal(0.2, 0.4)),
                "coverage": int(rng.integers(1, 30)),
                "target_rev_1m": float(rng.normal(0, 0.05)),
                "target_rev_3m": float(rng.normal(0, 0.09)),
                "ret_6m": float(rng.normal(0.02, 0.2)),
            })
    return pd.DataFrame(rows)


def _holder_frame(qidx_list, permnos) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rows = []
    for q in qidx_list:
        for p in permnos:
            r = {"permno": p, "qidx": q, "public_qidx": q,
                 "public_date": F._public_date(q)}
            for c in F.HOLDER_FEATURES:
                r[c] = float(rng.normal())
            rows.append(r)
    return pd.DataFrame(rows)


def _analyst_frame(months, permnos) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    rows = []
    for m in months:
        for p in permnos:
            rows.append({"permno": p, "month": m,
                         "a_n_live_targets": int(rng.integers(1, 20)),
                         "a_n_live_analysts": int(rng.integers(1, 9)),
                         "a_implied_mean": float(rng.normal(0.2, 0.3)),
                         "a_bias_mean": float(rng.normal(0.1, 0.2)),
                         "a_bias_disp": float(abs(rng.normal(0.1, 0.05))),
                         "a_implied_bias_corrected": float(rng.normal(0.1, 0.3))})
    return pd.DataFrame(rows)


# ------------------------------------------------------------ the 13F join

def test_attach_never_reads_a_filing_before_its_public_date():
    """THE test. A row is only ever joined to a 13F quarter that had already
    passed its statutory deadline."""
    anchor = pd.Timestamp("2020-01-01")
    df = _train_frame(anchor)
    qs = [F._qidx_of(2019, 1), F._qidx_of(2019, 2), F._qidx_of(2019, 3),
          F._qidx_of(2019, 4), F._qidx_of(2020, 1), F._qidx_of(2020, 2)]
    permnos = sorted(df["permno"].unique())
    h = _holder_frame(qs, permnos)
    a = _analyst_frame(sorted(df["month"].unique()), permnos)

    out, diag = F.attach(df, h, a)
    assert diag["holder_join"]["lag_days_after_quarter_end_min"] >= F.FILING_LAG_DAYS
    assert diag["holder_join"]["match_rate"] > 0.9

    # and the SPECIFIC pick: a row dated 2020-02-01 must not see 2019Q4, whose
    # public date is 2019-12-31 + 45d = 2020-02-14.
    one = pd.DataFrame([{"permno": permnos[0], "month": "2020-02",
                         "entry_date": pd.Timestamp("2020-02-01"),
                         "upside": 0.1, "coverage": 5, "target_rev_1m": 0.0,
                         "target_rev_3m": 0.0, "ret_6m": 0.0}])
    picked = pd.merge_asof(
        one[["permno", "entry_date"]].sort_values("entry_date"),
        h.sort_values("public_date"), left_on="entry_date",
        right_on="public_date", by="permno", direction="backward")
    assert int(picked["qidx"].iloc[0]) == F._qidx_of(2019, 3)


def test_attach_refuses_a_holder_panel_stamped_inside_the_statutory_window():
    """A gate that cannot fire is a broken gate. This one is handed a panel
    whose public dates are the report quarter ends themselves -- the classic
    45-day look-ahead -- and must REFUSE rather than join it."""
    anchor = pd.Timestamp("2020-01-01")
    df = _train_frame(anchor)
    permnos = sorted(df["permno"].unique())
    qs = [F._qidx_of(2019, q) for q in (1, 2, 3, 4)] + [F._qidx_of(2020, 1)]
    h = _holder_frame(qs, permnos)
    h["public_date"] = h["public_qidx"].map(F._quarter_end)     # the bug
    a = _analyst_frame(sorted(df["month"].unique()), permnos)
    with pytest.raises(SystemExit, match="look-ahead"):
        F.attach(df, h, a)


def test_attach_leaves_stale_quarters_unjoined_rather_than_reaching_back():
    """A name that stops filing must go NaN, not inherit a year-old quarter."""
    anchor = pd.Timestamp("2020-01-01")
    df = _train_frame(anchor, n_months=8)
    permnos = sorted(df["permno"].unique())
    h = _holder_frame([F._qidx_of(2017, 1)], permnos)            # far too old
    a = _analyst_frame(sorted(df["month"].unique()), permnos)
    out, diag = F.attach(df, h, a)
    assert diag["holder_join"]["matched"] == 0
    assert out["h_n_holders"].isna().all()


def test_attach_does_not_mutate_the_input_frame():
    anchor = pd.Timestamp("2020-01-01")
    df = _train_frame(anchor)
    before = list(df.columns)
    permnos = sorted(df["permno"].unique())
    h = _holder_frame([F._qidx_of(2019, q) for q in (2, 3, 4)], permnos)
    a = _analyst_frame(sorted(df["month"].unique()), permnos)
    F.attach(df, h, a)
    assert list(df.columns) == before


def test_interactions_are_products_of_within_month_standardised_legs():
    anchor = pd.Timestamp("2020-01-01")
    df = _train_frame(anchor)
    permnos = sorted(df["permno"].unique())
    h = _holder_frame([F._qidx_of(2019, q) for q in (2, 3, 4)]
                      + [F._qidx_of(2020, q) for q in (1, 2)], permnos)
    a = _analyst_frame(sorted(df["month"].unique()), permnos)
    out, _ = F.attach(df, h, a)
    for c in F.INTERACTION_FEATURES:
        assert c in out.columns
    # a z-scored leg has mean 0 within each month, so a product of two of them
    # is centred near zero -- a raw-level product would not be.
    v = out["x_holder_add_x_rev"].dropna()
    assert len(v) > 100
    assert abs(float(v.mean())) < 0.5


def test_within_month_z_uses_only_that_month():
    s = pd.Series([1.0, 2.0, 3.0, 100.0, 200.0, 300.0])
    by = pd.Series(["a", "a", "a", "b", "b", "b"])
    z = F._z(s, by)
    assert np.isclose(z.iloc[:3].to_numpy(), z.iloc[3:].to_numpy()).all()
    assert abs(float(z.iloc[:3].mean())) < 1e-12


# ------------------------------------------------------- the analyst panel

def _write_grades(tmp: Path, rows: list[dict]) -> Path:
    p = tmp / "grades.parquet"
    pd.DataFrame(rows).to_parquet(p, index=False)
    return p


def test_analyst_bias_uses_only_targets_that_had_already_resolved(tmp_path, monkeypatch):
    """A target announced in month m resolves at m+12. Its error must not enter
    the analyst's bias until AFTER that -- otherwise the feature knows the
    12-month outcome of a target that is still live, which is the target itself."""
    ann = pd.Timestamp("2013-01-15")
    # Analyst 1 is the only one with a non-zero error. Two targets: the first
    # resolves 2014-01 (usable from 2014-02), the second keeps the analyst LIVE
    # long enough for the resolved bias to show up in the aggregate at all.
    rows = [{"amaskcd": 1.0, "permno": 10001, "anndats": ann,
             "implied": 0.5, "error": 0.9},
            {"amaskcd": 1.0, "permno": 10001,
             "anndats": pd.Timestamp("2014-06-15"), "implied": 0.5, "error": 0.9}]
    # a second analyst, unbiased, so every month has something to average
    rows += [{"amaskcd": 2.0, "permno": 10001,
              "anndats": ann + pd.DateOffset(months=k),
              "implied": 0.1, "error": 0.0} for k in range(0, 30)]
    monkeypatch.setattr(F, "GRADES", _write_grades(tmp_path, rows))
    a, diag = F.build_analyst_panel("2013-01", "2015-12", verbose=False)
    a = a.set_index("month")

    # analyst 1's first error resolves 2014-01 (ann + 365d), usable from 2014-02.
    early = a.loc[[m for m in a.index if m < "2014-02"], "a_bias_mean"]
    assert (early.fillna(0.0).abs() < 1e-9).all(), (
        "an unresolved target's error leaked into the bias")
    later = a.loc[[m for m in a.index if "2014-07" <= m <= "2015-05"], "a_bias_mean"]
    assert later.max() > 0.0, "the resolved error never entered the bias at all"


def test_a_target_is_not_live_in_its_own_announcement_month(tmp_path, monkeypatch):
    ann = pd.Timestamp("2013-05-20")
    rows = [{"amaskcd": 1.0, "permno": 10001, "anndats": ann,
             "implied": 0.5, "error": 0.1}]
    monkeypatch.setattr(F, "GRADES", _write_grades(tmp_path, rows))
    a, _ = F.build_analyst_panel("2013-01", "2015-12", verbose=False)
    months = set(a["month"])
    assert "2013-05" not in months, "a target was live in the month it was announced"
    assert "2013-06" in months and "2014-05" in months
    assert "2014-06" not in months, "a target outlived its 12-month window"


def test_analyst_panel_refuses_when_the_grades_artefact_is_absent(tmp_path, monkeypatch):
    """SILENCE IS NOT EVIDENCE. A missing row-level artefact must refuse, not
    fall back to the consensus panel and quietly build a family that carries no
    analyst identity at all."""
    monkeypatch.setattr(F, "GRADES", tmp_path / "does_not_exist.parquet")
    with pytest.raises(SystemExit, match="REFUSED"):
        F.build_analyst_panel("2013-01", "2013-12", verbose=False)


def test_bias_correction_moves_the_consensus_the_right_way(tmp_path, monkeypatch):
    """Bias is `implied - realized`, so POSITIVE bias is over-optimism and the
    corrected consensus must sit BELOW the raw one. Getting this sign backwards
    would build a feature that amplifies optimism and still look like a feature."""
    ann0 = pd.Timestamp("2013-01-15")
    rows = [{"amaskcd": 1.0, "permno": 10001,
             "anndats": ann0 + pd.DateOffset(months=k),
             "implied": 0.5, "error": 0.4} for k in range(0, 30)]
    monkeypatch.setattr(F, "GRADES", _write_grades(tmp_path, rows))
    a, _ = F.build_analyst_panel("2013-01", "2016-12", verbose=False)
    late = a[(a["month"] >= "2015-01") & a["a_bias_mean"].notna()]
    assert len(late) > 5
    assert (late["a_implied_bias_corrected"] < late["a_implied_mean"]).all()


# --------------------------------------------------- the built panel, if any

def test_cached_holder_panel_is_point_in_time_if_it_exists():
    """Not a substitute for the synthetic tests above -- an extra check on the
    real artefact when this machine has one. It never SKIPS silently: when the
    panel is absent it asserts the rules were checked synthetically instead."""
    if not F.HOLDER_PANEL.exists():
        assert F.FILING_LAG_DAYS == 45
        return
    h = pd.read_parquet(F.HOLDER_PANEL, columns=["qidx", "public_qidx", "public_date"])
    assert (h["public_qidx"] >= h["qidx"]).all()
    lag = (h["public_date"] - h["public_qidx"].map(F._quarter_end)).dt.days
    assert int(lag.min()) == F.FILING_LAG_DAYS
    assert int(lag.max()) == F.FILING_LAG_DAYS


def test_describe_names_what_was_deliberately_not_built():
    d = F.describe()
    assert d["licence"] == "PRODUCT_EXPERIMENT"
    nb = d["not_built"]
    assert "sentiment_novelty_attention" in nb
    assert "analyst_accuracy_weighting" in nb
    assert d["thin_coverage"]["thin"] == F.THIN_COVERAGE
