"""A's corner: the floor must move the universe AND the control with it.

No CRSP file is read here. What is pinned is the thing TRIAL-H5 paid for: a
corner-dependent control that stays at the old corner compares a $10M book
against a $3M null and calls the difference selection.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import night_a_corner as A
from scripts import night_first_books_replay as R


def _months(n: int):
    return pd.period_range("2011-01", periods=n, freq="M")


def _panel(months, *, n_names: int = 60, big: int = 20) -> pd.DataFrame:
    """`big` names clear the $10M floor; the rest clear only the $3M floor."""
    rng = np.random.default_rng(5)
    rows = []
    for ym in months:
        for p in range(n_names):
            rows.append({"permno": p, "ym": ym,
                         "ret_m": float(rng.normal(0.01, 0.02)),
                         "price": 50.0,
                         "dv": 2.0e7 if p < big else 5.0e6,
                         "turnover_m": 0.05})
    return pd.DataFrame(rows)


def _si(months, permnos) -> pd.DataFrame:
    rng = np.random.default_rng(9)
    rows = []
    for ym in months:
        asof = ym.to_timestamp(how="end")
        for p in permnos:
            rows.append({"permno": p, "observed_at": asof,
                         "si_ratio": float(rng.uniform(0.01, 0.2)),
                         "turnover_21d_w": float(rng.uniform(0.01, 0.2))})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# the floor moves the universe, and the twin is drawn from the moved universe


def test_the_floor_changes_the_eligible_universe():
    months = _months(6)
    panel = _panel(months)
    at3 = A._median_pool(panel, A.PRIMARY_FLOOR)
    at10 = A._median_pool(panel, A.SECONDARY_FLOOR)
    assert at3 == 60 and at10 == 20


def test_the_twin_is_redrawn_at_the_floor_and_the_seed_is_recorded():
    """The $10M twin must be drawn from the $10M band.

    A twin left at the $3M band would make the comparison a $10M book against
    a $3M null, which is TRIAL-H5's own lesson going unlearned.
    """
    months = _months(30)
    panel = _panel(months)
    seen: dict = {"3m": [], "10m": []}

    def spy(tag):
        def select(pool, ym):
            seen[tag].append(sorted(int(p) for p in pool["permno"]))
            return sorted(int(p) for p in pool["permno"])[:5]
        return select

    a = R.run_monthly(panel, spy("3m"), k=5, seed=R.BOOK_A_SEED, label="3m",
                      floor_usd=A.PRIMARY_FLOOR)
    b = R.run_monthly(panel, spy("10m"), k=5, seed=R.BOOK_A_SEED, label="10m",
                      floor_usd=A.SECONDARY_FLOOR)
    assert a["floor_usd"] == A.PRIMARY_FLOOR
    assert b["floor_usd"] == A.SECONDARY_FLOOR
    assert a["seed"] == b["seed"] == R.BOOK_A_SEED
    assert all(len(s) == 60 for s in seen["3m"])
    assert all(len(s) == 20 for s in seen["10m"])
    # and the twin the engine drew at $10M can only contain $10M names
    assert b["n_blocks"] > 3


def test_the_default_floor_is_unchanged_so_run01_stays_reproducible():
    months = _months(6)
    panel = _panel(months)
    default = R.eligible(panel[panel["ym"] == months[0]])
    explicit = R.eligible(panel[panel["ym"] == months[0]],
                          floor_usd=R.FLOOR_USD)
    assert len(default) == len(explicit) == 60


# --------------------------------------------------------------------------
# the confirm slice is not an era


def test_the_confirm_slice_is_cut_from_the_same_block_series_as_the_eras():
    res = {"blocks": [str(m) for m in pd.period_range("2008-01", periods=60, freq="M")],
           "excess": [0.01] * 36 + [-0.01] * 24}
    out = A.slice_stats(res, 2011, 2024)
    assert out["slice"] == "2011-2024"
    assert out["n_blocks"] == 24            # 2011-01 .. 2012-12
    assert out["mean_excess_net_monthly"] == pytest.approx(-0.01)


def test_a_slice_with_fewer_than_three_blocks_says_so_rather_than_averaging():
    res = {"blocks": ["2011-01", "2011-02"], "excess": [0.01, 0.02]}
    out = A.slice_stats(res, 2011, 2024)
    assert out["verdict"].startswith("too few blocks")
    assert "mean_excess_net_monthly" not in out


# --------------------------------------------------------------------------
# the contamination clause, BEFORE the number


def test_the_join_rate_is_measured_on_the_cells_own_universe():
    """It is a different number at $10M than at $3M, and both belong on the
    receipt: the panel covers larger names better."""
    months = _months(12)
    panel = _panel(months)
    si = _si(months, list(range(20)))            # only the big names have prints
    at3 = A.join_rate_by_year(panel, si, floor_usd=A.PRIMARY_FLOOR)
    at10 = A.join_rate_by_year(panel, si, floor_usd=A.SECONDARY_FLOOR)
    assert at3[2011] == pytest.approx(20 / 60, abs=1e-4)   # rounded to 4 dp
    assert at10[2011] == pytest.approx(1.0)


def test_a_year_below_the_join_rate_floor_is_excluded_and_named():
    rates = {2010: 0.10, 2011: 0.40, 2012: 0.80, 2013: 0.49}
    out = A.excluded_years(rates, lo=2011, hi=2024)
    assert out == [2011, 2013], "2010 is outside the confirm slice"


def test_an_excluded_year_drops_the_month_from_the_book_and_the_twin_together():
    months = _months(36)
    panel = _panel(months)
    si = _si(months, list(range(60)))
    select = R.book_a_selector(si, skip_years={2012})
    pool = R.eligible(panel[panel["ym"] == months[0]])
    assert select(pool, months[0])                       # 2011 is fine
    assert select(pool, pd.Period("2012-06", freq="M")) == []


# --------------------------------------------------------------------------
# the decision rule


def _cell(mean, t, n=168):
    return {"confirm_slice": {"slice": "2011-2024", "n_blocks": n,
                              "mean_excess_net_monthly": mean, "nw_lag2_t": t}}


def test_a_negative_primary_cell_closes_the_book_whatever_the_corner_did():
    out = A.decide(_cell(-0.005407, -2.2603), _cell(0.02, 3.0))
    assert out["verdict"] == "FAILED_VARIANT"
    assert "clause 1" in out["clause"]
    assert "already below zero" in out["why"]


def test_the_corner_clause_fires_only_when_the_primary_cell_passed():
    out = A.decide(_cell(0.012, 2.6), _cell(0.001, 0.4))
    assert out["verdict"] == "FAILED_VARIANT"
    assert "tradability killed it" in out["clause"]


def test_both_floors_clearing_is_the_only_route_to_promising():
    assert A.decide(_cell(0.012, 2.6), _cell(0.011, 2.4))["verdict"] == "PRODUCT_PROMISING"
    # one floor short of the declared effect is CONDITIONAL, not a pass
    assert A.decide(_cell(0.008, 2.6), _cell(0.011, 2.4))["verdict"] == "CONDITIONAL"
    # a t inside [1.0, 2.0) is CONDITIONAL
    assert A.decide(_cell(0.012, 1.4), _cell(0.011, 2.4))["verdict"] == "CONDITIONAL"


def test_one_floor_may_not_be_quoted_without_the_other():
    """§8: both are printed or neither is."""
    out = A.decide(_cell(0.012, 2.6), {"confirm_slice": {"n_blocks": 0}})
    assert out["verdict"] == "CANNOT_DETERMINE"
    assert "both are printed or neither is" in out["why"]


def test_cell_passes_refuses_rather_than_guessing_on_a_missing_series():
    assert A.cell_passes({"confirm_slice": {"n_blocks": 0}}) is None


# --------------------------------------------------------------------------
# registration and the registered constants


def test_the_job_is_registered_in_the_night_factory():
    from scripts import night_factory_jobs as NFJ
    assert "A_corner" in NFJ.JOBS
    assert NFJ.JOB_STAGES["A_corner"] == "pnl"
    assert "A_corner" not in NFJ.TIMEBOXED and "A_corner" not in NFJ.RESUMABLE


def test_the_frozen_parameters_are_the_drafts_own():
    """§6 freezes k = 50, the $3M primary and $10M secondary floors, and the
    2011-2024 confirm slice; §4 computes the MDE at 0.685%/month."""
    assert A.PRIMARY_FLOOR == 3_000_000.0 and A.SECONDARY_FLOOR == 10_000_000.0
    assert A.CONFIRM_SLICE == (2011, 2024)
    assert R.BOOK_A_K == 50 and R.BOOK_A_MIN_NAMES == 20
    assert A.DECLARED_MDE_MONTHLY == 0.00685
    assert A.DECLARED_EFFECT_SIZE == 0.01
    assert A.MIN_JOIN_RATE == 0.50

    from pathlib import Path
    text = Path("docs/TRIALS/TRIAL-DRAFT-A-si-low-turnover-high-v1.md").read_text(
        encoding="utf-8")
    assert "$3M primary and $10M secondary floors" in text
    assert "0.685%/month" in text
