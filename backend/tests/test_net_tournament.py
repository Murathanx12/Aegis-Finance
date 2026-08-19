"""AEGIS-NET-TOURNAMENT-1 harness — synthetic smoke only.

Nothing here touches the registered panel. The properties tested are the
gate (unsigned refuses), the arms (frozen set, unknown refuses), the scoring
(a planted linear signal is recovered; thin dates counted not averaged), and
the competing-risk frame (`neither` = censoring; the sub-30-event refusal).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import net_tournament as NT


# ── the signature gate ─────────────────────────────────────────────────────
def test_a_missing_prereg_refuses(tmp_path):
    with pytest.raises(NT.TournamentRefused, match="no pre-registration"):
        NT.assert_signed(tmp_path / "nope.md")


def test_an_unsigned_prereg_refuses(tmp_path):
    p = tmp_path / "prereg.md"
    p.write_text("# X\n\nSIGNED-BY: (unsigned)\n", encoding="utf-8")
    with pytest.raises(NT.TournamentRefused, match="UNSIGNED"):
        NT.assert_signed(p)


def test_a_prereg_without_a_signature_line_refuses(tmp_path):
    p = tmp_path / "prereg.md"
    p.write_text("# X\n\nno line at all\n", encoding="utf-8")
    with pytest.raises(NT.TournamentRefused, match="no SIGNED-BY line"):
        NT.assert_signed(p)


def test_a_signed_prereg_returns_the_signer(tmp_path):
    p = tmp_path / "prereg.md"
    p.write_text("SIGNED-BY: Murat, 2026-08-20\n", encoding="utf-8")
    assert "Murat" in NT.assert_signed(p)


def test_the_LIVE_draft_is_signed_and_names_a_human():
    """Lifecycle successor to test_the_LIVE_draft_is_currently_unsigned
    (deleted 2026-08-19 on signature, as its own docstring instructed).
    The live prereg must now name a human, and the recorded signer is
    pinned so a silent un-signing or re-signing is a test failure."""
    assert "Murat" in NT.assert_signed()


# ── arms ───────────────────────────────────────────────────────────────────
def test_an_unknown_arm_refuses():
    with pytest.raises(NT.TournamentRefused, match="frozen"):
        NT.build_arm("transformer_9000")


def test_all_declared_arms_construct():
    for a in NT.ARM_NAMES:
        assert NT.build_arm(a) is not None


# ── scoring ────────────────────────────────────────────────────────────────
def _panel(n_dates=40, n_names=20, seed=3, signal=1.0):
    """Synthetic monthly panel with a planted linear factor."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2012-01-31", periods=n_dates, freq="ME")
    rows = []
    for d in dates:
        f1 = rng.normal(size=n_names)
        f2 = rng.normal(size=n_names)
        y = signal * f1 + 0.5 * rng.normal(size=n_names)
        for i in range(n_names):
            rows.append({"date": d, "ticker": f"T{i:02d}",
                         "x1": f1[i], "x2": f2[i], "y": y[i]})
    return pd.DataFrame(rows)


def test_rank_ic_drops_and_counts_thin_dates():
    pred = np.array([1.0, 2.0, 3.0, 1.0, 2.0])
    actual = np.array([1.0, 2.0, 3.0, 2.0, 1.0])
    dates = np.array(["2020-01-01"] * 3 + ["2020-02-01"] * 2,
                     dtype="datetime64[D]")
    s = NT.rank_ic_by_date(pred, actual, dates)
    assert len(s) == 0                      # both dates below the 5-name floor
    assert s.attrs["thin_dates_dropped"] == 2


def test_run_head_recovers_a_planted_linear_signal():
    df = _panel(signal=1.0)
    out = NT.run_head(df, feature_cols=["x1", "x2"], target_col="y",
                      horizon_days=5, first_test_year=2014,
                      arms=("linear_ridge", "lightgbm"), min_train=100)
    assert out["arms"]["linear_ridge"]["ic_mean"] > 0.5, \
        "a planted linear factor must be recovered by ridge"
    assert "lightgbm" in out["loss_contrast_vs_baseline"]
    c = out["loss_contrast_vs_baseline"]["lightgbm"]
    for k in ("mean", "mde_80pct_power", "n_effective", "block_days"):
        assert k in c


def test_run_head_refuses_a_missing_column():
    df = _panel()
    with pytest.raises(NT.TournamentRefused, match="absent"):
        NT.run_head(df, feature_cols=["x1", "nope"], target_col="y",
                    horizon_days=5, first_test_year=2014, min_train=100)


def test_missing_targets_are_dropped_and_counted_never_imputed():
    df = _panel()
    df.loc[df.index[:37], "y"] = np.nan
    out = NT.run_head(df, feature_cols=["x1", "x2"], target_col="y",
                      horizon_days=5, first_test_year=2014,
                      arms=("linear_ridge",), min_train=100)
    assert out["n_rows_dropped_missing_target"] == 37


# ── competing risks (adjudication A5) ──────────────────────────────────────
def _barrier_df(n=300, seed=5, up_frac=0.3, down_frac=0.2):
    rng = np.random.default_rng(seed)
    outcome = rng.choice(["up", "down", "neither"], size=n,
                         p=[up_frac, down_frac, 1 - up_frac - down_frac])
    days = np.where(outcome == "neither", np.nan,
                    rng.integers(1, 20, size=n)).astype(float)
    return pd.DataFrame({
        "date": pd.Timestamp("2020-01-31"), "ticker": [f"T{i}" for i in range(n)],
        "f1": rng.normal(size=n), "f2": rng.normal(size=n),
        "barrier_up20_down10": outcome,
        "barrier_up20_down10_days": days,
    })


def test_neither_is_censoring_at_the_horizon_not_a_class():
    df = _barrier_df()
    cr = NT.competing_risk_frame(df, horizon_days=20)
    neither = df["barrier_up20_down10"] == "neither"
    assert (cr.loc[neither.to_numpy(), "duration"] == 20).all()
    assert (cr.loc[neither.to_numpy(), "event_up"] == 0).all()
    assert (cr.loc[neither.to_numpy(), "event_down"] == 0).all()


def test_cause_specific_fits_when_events_suffice_and_refuses_when_not():
    out = NT.fit_cause_specific(_barrier_df(n=400), ["f1", "f2"])
    assert "concordance" in out["up"] and "concordance" in out["down"]

    thin = NT.fit_cause_specific(_barrier_df(n=400, down_frac=0.02),
                                 ["f1", "f2"])
    assert "refused" in thin["down"], \
        "a sub-30-event cause must refuse, not pretend to converge"
    assert "concordance" in thin["up"]


def test_an_outcome_without_days_refuses():
    df = _barrier_df()
    hit = df["barrier_up20_down10"] == "up"
    df.loc[hit.idxmax(), "barrier_up20_down10_days"] = np.nan
    with pytest.raises(NT.TournamentRefused, match="days_to_barrier"):
        NT.competing_risk_frame(df, horizon_days=20)
