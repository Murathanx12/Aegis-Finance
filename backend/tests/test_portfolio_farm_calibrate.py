"""The calibration battery: reproduce known facts before trusting novel ones.

WHAT IT ALREADY PAID FOR
========================
On its FIRST run (2026-08-25) it failed `rev_breadth` — I had bounded breadth
at |1| from the formula, reasoning that `numup + numdown` cannot exceed
`numest`. The data disagreed: those are a FLOW and a STOCK respectively, and
the bound had been silently dropping 16,024 rows — 1.52%, and precisely the
most heavily-revised names, which are the most informative observations the
signal has.

That is the whole argument for the battery. The signal still "worked"; its
leaderboard row looked entirely ordinary; nothing else in the system could have
noticed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import portfolio_farm_calibrate as CAL


def test_a_failing_check_is_reported_as_failing():
    """A battery that cannot go red is not a battery — the standing rule from
    `monday_gate_check`, which reported a permanent FAIL no state could clear."""
    ok = CAL._check("x", True, "fine")
    bad = CAL._check("y", False, "broken")
    assert ok["pass"] is True and bad["pass"] is False


def test_the_industry_tails_are_fama_frenchs_taxonomy_not_an_invented_one():
    """`ffi12` ships inside `finratio`, so the expected tails are FF's own
    classification rather than a list chosen to make the check pass."""
    assert "MONEY" in CAL.VALUE_INDUSTRIES
    assert "BUSEQ" in CAL.GROWTH_INDUSTRIES and "HLTH" in CAL.GROWTH_INDUSTRIES
    assert not (CAL.VALUE_INDUSTRIES & CAL.GROWTH_INDUSTRIES), (
        "an industry in both tails would make the check unfalsifiable")


def test_an_inverted_bm_would_be_caught(tmp_path):
    """THE FAILURE MODE THE VALUE CHECKS EXIST FOR. If `bm` were stored or
    joined inverted, every value result would flip sign and nothing else in the
    system would notice."""
    n = 5000
    rng = np.random.default_rng(4)
    bm = rng.lognormal(mean=-0.7, sigma=0.8, size=n)
    # correct world: cheap (high bm) is SMALL
    cap = 5000.0 / np.maximum(bm, 0.05)
    good = pd.DataFrame({"permno": np.arange(n), "public_date": "2020-01-31",
                         "bm": bm, "roe": rng.normal(0.06, 0.1, n),
                         "mktcap": cap,
                         "ffi12_desc": rng.choice(["MONEY", "BUSEQ"], n)})
    (tmp_path / "finratio_monthly.parquet").write_bytes(b"")
    good.to_parquet(tmp_path / "finratio_monthly.parquet", index=False)
    rows = CAL.calibrate_characteristics(dir_=tmp_path)
    by = {r["check"]: r["pass"] for r in rows}
    assert by["value skews SMALLER than growth"] is True

    # inverted world: cheap is LARGE — must be caught
    bad = good.copy()
    bad["mktcap"] = 5000.0 * np.maximum(bm, 0.05)
    bad.to_parquet(tmp_path / "finratio_monthly.parquet", index=False)
    rows = CAL.calibrate_characteristics(dir_=tmp_path)
    by = {r["check"]: r["pass"] for r in rows}
    assert by["value skews SMALLER than growth"] is False, (
        "an inverted book-to-market passed the calibration battery")


def test_missing_source_is_reported_rather_than_silently_skipped():
    """A check that did not run is not a check that passed."""
    from pathlib import Path
    rows = CAL.calibrate_characteristics(dir_=Path("no-such-dir"))
    assert rows and rows[0]["pass"] is False
    assert "absent" in rows[0]["detail"]


def test_breadth_bound_is_not_asserted_from_the_formula():
    """The regression. `numup`/`numdown` are a FLOW of revisions filed in the
    period; `numest` is the STOCK standing now, so the ratio legitimately
    exceeds 1. Bounding at |1| dropped the 1.52% most-revised rows."""
    from backend.services.portfolio_farm import revisions as RV
    lo, hi = RV.PLAUSIBLE["rev_breadth"]
    assert hi >= 5.0 and lo <= -5.0, (
        "the breadth bound has been tightened back toward the formula's |1|, "
        "which silently removes the most informative observations")


@pytest.mark.slow
def test_the_real_battery_passes_end_to_end():
    """Reads ~5.7M rows off disk, so it is `slow` and not part of the fast
    gate. Run it before trusting any new characteristic result."""
    rows = CAL.calibrate_characteristics() + CAL.calibrate_revisions()
    failed = [r for r in rows if not r["pass"]]
    assert not failed, f"calibration failures: {failed}"
