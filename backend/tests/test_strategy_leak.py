"""S3 -- the two model-free leak detectors, each against a PLANTED fault.

A detector that has never caught a planted fault is not a detector. Every test
here constructs a frame whose right answer is known BY CONSTRUCTION and asserts
the detector produces exactly it -- including which column, not merely that
something was wrong.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.strategy.leak import (CANNOT_DETERMINE, LeakAnalysisRefused,
                                   lookahead_analysis, recursive_analysis)


# --------------------------------------------------------------------------
# fixtures: one frame, three builders -- clean, planted lookahead, planted drift


def _frame(n: int = 400, seed: int = 20260908) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n)))
    vol = rng.integers(1_000_000, 5_000_000, n).astype(float)
    return pd.DataFrame({"close": close, "volume": vol}, index=idx)


def _build_clean(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["sma3"] = df["close"].rolling(3).mean()
    out["ret1"] = df["close"].pct_change()
    out["dollar_vol"] = df["close"] * df["volume"]
    return out


def _build_with_lookahead(df: pd.DataFrame) -> pd.DataFrame:
    """One planted leak (`tomorrow_ret`), one planted whole-column aggregate
    (`z_vs_full_mean`), and two honest columns."""
    out = _build_clean(df)
    out["tomorrow_ret"] = df["close"].shift(-1) / df["close"] - 1.0   # THE LEAK
    out["z_vs_full_mean"] = (df["close"] - df["close"].mean()) / df["close"].std()
    return out


def _build_slow_ewm(df: pd.DataFrame) -> pd.DataFrame:
    """A slow EWM has not converged at 20 bars and has at 999. `sma3` has."""
    out = pd.DataFrame(index=df.index)
    out["sma3"] = df["close"].rolling(3).mean()
    out["ewm_slow"] = df["close"].ewm(alpha=0.005, adjust=False).mean()
    return out


# --------------------------------------------------------------------------
# (a) LOOKAHEAD -- the planted fault


def test_lookahead_detector_names_EXACTLY_the_two_planted_columns():
    df = _frame()
    cps = list(df.index[100:300:40])
    rep = lookahead_analysis(_build_with_lookahead, df, cps)
    assert rep.verdict == "LOOKAHEAD_DETECTED"
    # KNOWN ANSWER: shift(-1) reads t+1; a full-column mean/std reads all of it.
    assert set(rep.biased_columns) == {"tomorrow_ret", "z_vs_full_mean"}
    # and the honest columns are NOT accused
    clean = {f.column for f in rep.findings if f.status == "CLEAN"}
    assert {"sma3", "ret1", "dollar_vol"} <= clean


def test_lookahead_detector_passes_a_builder_with_no_leak():
    df = _frame()
    rep = lookahead_analysis(_build_clean, df, list(df.index[100:300:40]))
    assert rep.verdict == "NO_LOOKAHEAD_FOUND"
    assert rep.biased_columns == ()


def test_lookahead_finding_carries_the_first_checkpoint_and_the_delta():
    df = _frame()
    cps = list(df.index[100:300:40])
    rep = lookahead_analysis(_build_with_lookahead, df, cps)
    f = next(x for x in rep.findings if x.column == "tomorrow_ret")
    assert f.first_checkpoint == cps[0]
    assert f.n_checkpoints_differing == len(cps)
    # NaN-vs-number at the cut edge is an infinite delta, by construction:
    # the last row of the cut frame cannot know tomorrow.
    assert f.max_abs_delta == float("inf")


def test_an_unwarmed_column_is_CANNOT_DETERMINE_not_a_leak_and_not_a_pass():
    """A 300-bar rolling mean on a 100-bar cut is all-NaN. That is a warm-up
    problem, not a leak, and it must not read as either."""
    df = _frame()

    def build(d: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({"sma300": d["close"].rolling(300).mean()}, index=d.index)

    rep = lookahead_analysis(build, df, [df.index[50], df.index[80]])
    assert rep.biased_columns == ()
    assert rep.unavailable_columns == ("sma300",)
    assert rep.verdict == CANNOT_DETERMINE
    assert CANNOT_DETERMINE in next(f for f in rep.findings).note


def test_lookahead_REFUSES_an_empty_frame_rather_than_reporting_clean():
    with pytest.raises(LeakAnalysisRefused, match="empty frame"):
        lookahead_analysis(_build_clean, pd.DataFrame())


def test_lookahead_REFUSES_when_no_checkpoint_is_in_the_index():
    df = _frame(50)
    with pytest.raises(LeakAnalysisRefused, match="no checkpoint"):
        lookahead_analysis(_build_clean, df, ["not-a-date"])


def test_lookahead_REFUSES_a_builder_that_raises_on_a_prefix():
    df = _frame(60)

    def brittle(d: pd.DataFrame) -> pd.DataFrame:
        if len(d) < 60:
            raise ValueError("needs the whole frame")
        return _build_clean(d)

    with pytest.raises(LeakAnalysisRefused, match="raised on the frame cut"):
        lookahead_analysis(brittle, df, [df.index[30]])


def test_lookahead_derives_its_own_checkpoints_when_none_are_given():
    df = _frame()
    rep = lookahead_analysis(_build_with_lookahead, df)
    assert rep.n_checkpoints > 0
    assert "tomorrow_ret" in rep.biased_columns


def test_the_report_carries_the_caveat_that_a_negative_is_not_a_proof():
    rep = lookahead_analysis(_build_clean, _frame(), None)
    assert "does not prove" in rep.as_dict()["caveat"]


# --------------------------------------------------------------------------
# (b) RECURSIVE / WARM-UP DRIFT -- the planted fault


def test_recursive_detector_names_the_unconverged_column_and_clears_the_other():
    df = _frame(1200)
    rep = recursive_analysis(_build_slow_ewm, df, declared_warmup=20)
    assert rep.verdict == "WARMUP_DRIFT_DETECTED"
    # KNOWN ANSWER: an alpha=0.005 EWM has a ~200-bar memory, so 20 bars is
    # nowhere near converged; a 3-bar rolling mean is exact at 20 bars.
    assert rep.drifting_columns == ("ewm_slow",)
    assert rep.per_column["sma3"]["status"] == "CONVERGED"
    assert rep.per_column["sma3"]["relative_deviation_at_declared_warmup"] == 0.0


def test_recursive_detector_clears_a_builder_whose_features_all_converge():
    df = _frame(1200)
    rep = recursive_analysis(_build_clean, df, declared_warmup=20)
    assert rep.verdict == "CONVERGED"
    assert rep.drifting_columns == ()


def test_an_expanding_window_is_the_growing_vs_fixed_window_case_by_construction():
    """The roadmap's own words: 'a value computed on a growing window differs
    from the same value computed on a fixed one'. An expanding mean IS that."""
    df = _frame(1200)

    def build(d: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({"expanding_mean": d["close"].expanding().mean(),
                             "rolling5": d["close"].rolling(5).mean()}, index=d.index)

    rep = recursive_analysis(build, df, declared_warmup=20)
    assert rep.drifting_columns == ("expanding_mean",)


def test_a_rung_longer_than_the_frame_is_REFUSED_BY_NAME_not_clamped():
    """A clamped rung agrees with the reference by construction and would read
    as convergence -- the exact failure a gate must not have."""
    df = _frame(120)
    rep = recursive_analysis(_build_slow_ewm, df, ladder=(20, 40, 80, 999),
                             declared_warmup=20)
    assert 999 in rep.refused_rungs
    assert CANNOT_DETERMINE in rep.refused_rungs[999]
    assert rep.reference_warmup == 80          # the longest rung that RAN


def test_recursive_REFUSES_a_one_rung_ladder():
    with pytest.raises(LeakAnalysisRefused, match="at least two rungs"):
        recursive_analysis(_build_clean, _frame(200), ladder=(50,))


def test_recursive_REFUSES_when_fewer_than_two_rungs_are_usable():
    with pytest.raises(LeakAnalysisRefused, match="usable rung"):
        recursive_analysis(_build_clean, _frame(30), ladder=(100, 200, 300))


def test_a_zero_reference_reports_the_ABSOLUTE_deviation_and_a_null_relative():
    df = _frame(1200)

    def build(d: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({"always_zero": 0.0 * d["close"]}, index=d.index)

    rep = recursive_analysis(build, df, declared_warmup=20)
    col = rep.per_column["always_zero"]
    assert col["reference_value"] == 0.0
    assert col["by_warmup"]["20"]["relative"] is None
    assert col["by_warmup"]["20"]["abs"] == 0.0
    assert col["status"] == CANNOT_DETERMINE


def test_both_reports_serialise_to_plain_json_types():
    import json

    df = _frame(1200)
    a = lookahead_analysis(_build_with_lookahead, df).as_dict()
    b = recursive_analysis(_build_slow_ewm, df, declared_warmup=20).as_dict()
    json.dumps(a, default=str)
    json.dumps(b, default=str)
    assert a["detector"] == "lookahead_analysis"
    assert b["detector"] == "recursive_analysis"
