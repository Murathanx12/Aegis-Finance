"""R4 (E3) — the event families. Pins the arithmetic and the coverage story.

WHY THESE AND NOT MORE. Three things in `scripts/r4_event_families.py` can go
wrong silently and did go wrong at least once while it was being written:

  1. the multiplicity helpers (Holm / BH-FDR / DSR) can be *plausible* and
     wrong — the first DSR here used a Gumbel quantile where Bailey & Lopez de
     Prado use a Gaussian one, which inflates the null and passes rubbish;
  2. `_monthly_spread` must count DATE BLOCKS, not name-days (CANON §58) — the
     whole point of the job's t-statistics;
  3. the coverage STATEMENT must keep naming all four readings, because the
     document's first claim is that the E3 gate does not say which one it means.

Everything here is offline and takes milliseconds. Nothing loads the panel.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import r4_event_families as R

RECEIPT = R.OUT_DIR / "R4_event_families.json"


# ------------------------------------------------------------ multiplicity

def test_holm_is_monotone_and_matches_the_closed_form():
    p = {"a": 0.001, "b": 0.02, "c": 0.30}
    h = R.holm(p)
    assert h["a"] == pytest.approx(3 * 0.001)
    assert h["b"] == pytest.approx(2 * 0.02)
    assert h["c"] == pytest.approx(0.30)
    assert h["a"] <= h["b"] <= h["c"]          # Holm is monotone by construction


def test_holm_ignores_none_rather_than_counting_it():
    assert set(R.holm({"a": 0.01, "b": None})) == {"a"}


def test_bh_fdr_rejects_the_planted_and_not_the_null():
    p = {f"null_{i}": 0.5 + i / 100 for i in range(19)} | {"real": 0.0001}
    out = R.bh_fdr(p, q=0.05)
    assert out["rejected"] == ["real"]
    assert out["n"] == 20


def test_deflated_sharpe_uses_a_gaussian_quantile_not_a_gumbel_one():
    """The expected max of n iid Sharpes must match the BLdP form term for term.

    This is the bug the first version shipped: `-log(-log(1-1/n))` is the Gumbel
    quantile and is far from `Phi^-1(1-1/n)`, so the null bar came out too high
    and a real edge would have been deflated away (or, with the other sign, a
    lucky one waved through).
    """
    srs = [0.2 * i for i in range(1, 21)]      # 20 trials, wide spread
    out = R.deflated_sharpe(4.0, srs, n_periods=120)
    v = float(np.var(np.asarray(srs) / math.sqrt(12), ddof=1))
    g = 0.5772156649
    want = math.sqrt(v) * ((1 - g) * R._ppf(1 - 1 / 20) + g * R._ppf(1 - 1 / (20 * math.e)))
    # the receipt rounds to 4dp on purpose; compare at that resolution
    assert out["expected_max_sharpe_ann_under_null"] == pytest.approx(
        want * math.sqrt(12), abs=1e-4)
    assert out["n_trials_family"] == 20


def test_deflated_sharpe_refuses_rather_than_guessing():
    assert R.deflated_sharpe(1.0, [1.0], n_periods=120)["verdict"] == "CANNOT DETERMINE"
    assert R.deflated_sharpe(None, [1.0, 2.0], n_periods=120)["verdict"] == "CANNOT DETERMINE"
    assert R.deflated_sharpe(1.0, [1.0, 2.0], n_periods=4)["verdict"] == "CANNOT DETERMINE"


# ------------------------------------------------------------ date blocks

def _tape(n_months: int, n_per_month: int, effect: float, seed: int = 7):
    rng = np.random.default_rng(seed)
    rows = []
    for m in range(n_months):
        month = f"20{10 + m // 12:02d}-{m % 12 + 1:02d}"
        common = rng.normal(0, 0.05)           # the month's own market move
        for _ in range(n_per_month):
            s = rng.normal()
            rows.append({"event_month": month, "sig": s,
                         "ret": common + effect * s + rng.normal(0, 0.05),
                         "mm_beta": 1.0, "mm_alpha": 0.0})
    return pd.DataFrame(rows)


def test_monthly_spread_returns_one_number_per_event_month():
    t = _tape(24, 100, effect=0.0)
    s = R._monthly_spread(t, "sig", "ret")
    assert len(s) == 24, "n_effective must be DATE BLOCKS, never name-days"


def test_a_month_with_too_few_events_is_dropped_not_averaged():
    t = pd.concat([_tape(6, 100, 0.0),
                   _tape(1, 10, 0.0).assign(event_month="2099-01")])
    s = R._monthly_spread(t, "sig", "ret")
    assert "2099-01" not in s.index


def test_the_spread_differences_out_the_month_common_move():
    """A pure market month with no signal must not read as a spread."""
    t = _tape(36, 200, effect=0.0)
    s = R._monthly_spread(t, "sig", "ret")
    assert abs(float(s.mean())) < 0.01
    assert abs(R._t(s)) < 3.0


def test_a_planted_effect_is_recovered_with_the_right_sign():
    t = _tape(36, 200, effect=0.02)
    s = R._monthly_spread(t, "sig", "ret")
    assert float(s.mean()) > 0.05          # top vs bottom decile of a N(0,1)
    assert R._t(s) > 5


def test_mde_flags_an_underpowered_series_as_underpowered():
    rng = np.random.default_rng(3)
    tiny = pd.Series(rng.normal(0.0001, 0.05, 12))
    blk = R.mde_block(tiny)
    assert blk["n_blocks"] == 12
    assert blk["powered_for_observed_effect"] is False


def test_era_table_never_pools_and_names_all_three():
    idx = [f"{y}-{m:02d}" for y in range(1999, 2025) for m in range(1, 13)]
    s = pd.Series(np.linspace(-0.01, 0.01, len(idx)), index=idx)
    out = R.era_table(s)
    assert {"1999-2007", "2008-2015", "2016-2024"} <= set(out)
    assert out["1999-2007"]["sign"] == -1 and out["2016-2024"]["sign"] == 1
    assert out["eras_measured"] == 3


# ------------------------------------------------------- typed exits

def test_exit_attribution_separates_rank_decay_from_universe_exit():
    w = {"2020-01": {1: 0.5, 2: 0.5},
         "2020-02": {1: 0.5, 3: 0.5},
         "2020-03": {3: 1.0}}
    adm = {"2020-02": {1, 2, 3}, "2020-03": {3}}      # 2 still admissible, 1 gone
    out = R.exit_attribution(w, adm)
    assert out["exits_typed"]["RANK_DECAY"] == 1      # name 2, still admissible
    assert out["exits_typed"]["UNIVERSE_EXIT"] == 1   # name 1, left the universe


def test_exit_attribution_refuses_on_one_month():
    assert R.exit_attribution({"2020-01": {1: 1.0}}, {})["verdict"] == "CANNOT DETERMINE"


# ------------------------------------------------------- the coverage story

@pytest.mark.skipif(not RECEIPT.exists(), reason="R4 has not been run on this checkout")
def test_the_receipt_still_names_all_four_coverage_readings():
    cov = json.loads(RECEIPT.read_text(encoding="utf-8"))["STAGE_1_COVERAGE"]
    keys = cov["WHICH_READING_EVERY_NUMBER_IS_CONDITIONED_ON"]
    assert {"A_month_fraction", "B_news_universe_fraction",
            "C_event_table_permno_share", "D_panel_share_THIS_JOB"} == set(keys)


@pytest.mark.skipif(not RECEIPT.exists(), reason="R4 has not been run on this checkout")
def test_the_ibes_gate_claim_agrees_with_the_year_table():
    """X9's lesson: a headline sentence and its own table must not disagree."""
    cov = json.loads(RECEIPT.read_text(encoding="utf-8"))["STAGE_1_COVERAGE"]
    shares = [v["ibes_earnings_share_of_panel"]
              for v in cov["reading_D_by_year"].values()]
    assert min(shares) >= 0.90, "the 'MET in every year' sentence would be false"
    assert cov["reading_D_summary"]["ibes_earnings_min_share"] == pytest.approx(
        min(shares))


@pytest.mark.skipif(not RECEIPT.exists(), reason="R4 has not been run on this checkout")
def test_the_news_leg_is_refused_and_says_why():
    cov = json.loads(RECEIPT.read_text(encoding="utf-8"))["STAGE_1_COVERAGE"]
    assert cov["THE_NEWS_LEG_IS_REFUSED"]["verdict"].startswith("REFUSED")
    assert cov["price_panel_bound"]["crsp_daily_years_on_disk"][1] == 2024


def test_price_panel_bound_is_derived_from_the_files_not_asserted():
    """A gate that hard-codes its own bound cannot notice a new file landing."""
    b = R.price_panel_bound()
    years = sorted(int(p.stem.split("_")[-1])
                   for p in R.WRDS.glob("crsp_dsf_*.parquet"))
    assert b["crsp_daily_years_on_disk"] == [years[0], years[-1]]
    assert b["n_year_files"] == len(years)
