"""T3 — the first-books replay night job: the arithmetic, on synthetic panels.

No CRSP file is read here. What is pinned is the four things the job can get
wrong without failing: the cost convention, the Holm family size, the monthly
engine's look-ahead, and Book D's refusal — which must be a refusal for the
REASON registered, not because a file was missing.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from scripts import night_first_books_replay as R


# --------------------------------------------------------------------------
# the statistics


def test_newey_west_t_on_a_constant_series_is_not_a_number():
    assert R.newey_west_t([0.01] * 20) is None       # zero variance


def test_newey_west_t_needs_three_blocks():
    assert R.newey_west_t([0.01, 0.02]) is None


def test_newey_west_t_signs_with_the_mean():
    assert R.newey_west_t([0.01, 0.02, 0.03, 0.04, 0.05]) > 0
    assert R.newey_west_t([-0.01, -0.02, -0.03, -0.04, -0.05]) < 0


def test_two_sided_p_of_a_two_t_is_about_five_percent():
    assert R.two_sided_p(1.96) == pytest.approx(0.05, abs=0.002)
    assert R.two_sided_p(None) is None


# --------------------------------------------------------------------------
# Holm — the family size is DECLARED, not counted


def test_holm_corrects_against_the_declared_family_size_not_the_legs_that_ran():
    out = R.holm({"a": 0.010, "b": 0.200, "c": 0.400, "d": None})
    assert out["declared_family_size"] == 4
    assert out["legs_without"] == ["d"]
    # the smallest p is compared against 0.05/4, not 0.05/3
    assert out["per_leg"]["a"]["holm_alpha"] == pytest.approx(0.0125)
    assert out["per_leg"]["a"]["rejects_at_holm"] is True


def test_a_p_just_under_five_percent_does_not_survive_the_family():
    out = R.holm({"a": 0.044, "b": 0.25, "c": 0.75, "d": None})
    assert out["per_leg"]["a"]["rejects_at_holm"] is False


def test_holm_steps_its_alpha_down_the_ordered_p_values():
    out = R.holm({"a": 0.001, "b": 0.002, "c": 0.003, "d": 0.9})
    alphas = [out["per_leg"][k]["holm_alpha"] for k in ("a", "b", "c", "d")]
    assert alphas == sorted(alphas)


# --------------------------------------------------------------------------
# the cost convention


def test_a_full_rotation_costs_two_sides():
    c = R._cost({1, 2}, {3, 4})
    assert c == pytest.approx(2.0 * R.COST_BPS_PER_SIDE / 1e4)


def test_the_twin_rotates_exactly_as_much_as_its_book_and_no_more():
    """The cost term must cancel out of the difference.

    Before this was matched, a book that never traded beat a twin that redrew
    every month by +0.354%/month on a panel where every name earned the same
    return -- six percent a year of pure churn handed to the book, against a
    Book A MDE of 0.685%/month.
    """
    import numpy as np

    pool = pd.DataFrame({"permno": list(range(40))})
    rng = np.random.default_rng(1)
    prev_book, prev_twin = set(range(10)), set(range(20, 30))
    # the book replaces two names
    picked = list(range(2, 12))
    tw = R._turnover_matched_draw(pool, picked, prev_book, prev_twin, rng)
    assert len(tw) == len(picked)
    assert len(set(tw) - prev_twin) == len(set(picked) - prev_book) == 2


def test_a_book_that_never_trades_gets_a_twin_that_never_trades():
    import numpy as np

    pool = pd.DataFrame({"permno": list(range(40))})
    rng = np.random.default_rng(1)
    prev = set(range(10))
    tw = R._turnover_matched_draw(pool, sorted(prev), prev, set(range(20, 30)),
                                  rng)
    assert set(tw) == set(range(20, 30))


def test_holding_the_same_names_costs_nothing():
    assert R._cost({1, 2, 3}, {1, 2, 3}) == pytest.approx(0.0)


def test_the_first_period_pays_to_get_in():
    assert R._cost(set(), {1, 2}) == pytest.approx(R.COST_BPS_PER_SIDE / 1e4)


def test_the_cost_curve_is_named_as_a_placeholder():
    assert "pending_5c" in R.COST_CURVE


# --------------------------------------------------------------------------
# the monthly engine


def _panel(n_months: int = 24, n_names: int = 40, *, edge: float = 0.0):
    """A synthetic monthly panel. Names 0..9 earn `edge` extra every month."""
    rows = []
    months = pd.period_range("2020-01", periods=n_months, freq="M")
    for ym in months:
        for p in range(n_names):
            rows.append({"permno": p, "ym": ym,
                         "ret_m": 0.01 + (edge if p < 10 else 0.0),
                         "price": 50.0, "dv": 10_000_000.0,
                         "turnover_m": 0.05})
    return pd.DataFrame(rows)


def test_the_engine_finds_an_edge_that_is_there():
    res = R.run_monthly(_panel(edge=0.05), lambda pool, ym: list(range(10)),
                        k=10, seed=1, label="planted")
    # 5%/month planted on 10 of 40 names; the twin draws from the whole pool
    # and keeps whatever share of the ten it happened to draw, so the measured
    # excess is 5% minus that share and lands a little under the planted edge.
    assert 0.03 < res["mean_excess_net_monthly"] <= 0.05
    assert res["n_blocks"] == 23


def test_the_engine_finds_no_edge_when_there_is_none():
    res = R.run_monthly(_panel(edge=0.0), lambda pool, ym: list(range(10)),
                        k=10, seed=1, label="flat")
    # every name earns the same return, so book and twin differ only by cost
    assert abs(res["mean_excess_net_monthly"]) < 1e-6


def test_the_engine_never_earns_the_month_it_selected_in():
    """A selector that can only see the FUTURE earns nothing.

    The month a name is picked in is the month whose close the pick is made
    at; the return earned is the next month's. A selector handed the current
    month's realised return therefore has no advantage, which is what this
    asserts: if the engine paid out the selection month, this would win.
    """
    rows = []
    months = pd.period_range("2020-01", periods=24, freq="M")
    for i, ym in enumerate(months):
        for p in range(40):
            # exactly one name spikes each month, and it is a different one
            spike = (p == i % 40)
            rows.append({"permno": p, "ym": ym,
                         "ret_m": 1.0 if spike else 0.0, "price": 50.0,
                         "dv": 10_000_000.0, "turnover_m": 0.05})
    panel = pd.DataFrame(rows)

    def clairvoyant_about_now(pool, ym):
        return pool.sort_values("ret_m", ascending=False)["permno"].tolist()[:1]

    res = R.run_monthly(panel, clairvoyant_about_now, k=1, seed=3,
                        label="sees-only-today")
    assert res["mean_book_net_monthly"] <= 0.0      # cost, and no edge

    def clairvoyant_about_next(pool, ym):
        nxt = panel[panel["ym"] == ym + 1]
        if nxt.empty:
            return []
        return nxt.sort_values("ret_m", ascending=False)["permno"].tolist()[:1]

    leaky = R.run_monthly(panel, clairvoyant_about_next, k=1, seed=3,
                          label="sees-tomorrow")
    assert leaky["mean_book_net_monthly"] > 0.9     # the leak is visible


def test_the_engine_honours_the_dollar_volume_floor():
    panel = _panel()
    panel.loc[panel["permno"] < 10, "dv"] = 1.0     # below the floor
    seen: list = []

    def select(pool, ym):
        seen.append(set(pool["permno"]))
        return pool["permno"].tolist()[:5]

    R.run_monthly(panel, select, k=5, seed=1, label="floored")
    assert seen and all(not (s & set(range(10))) for s in seen)


def test_a_named_twin_selector_replaces_the_random_draw():
    res = R.run_monthly(_panel(edge=0.05),
                        lambda pool, ym: list(range(10)), k=10, seed=1,
                        label="conditioned", twin="unconditioned",
                        twin_select=lambda pool, ym: list(range(10, 20)))
    assert res["twin"] == "unconditioned"
    assert res["mean_excess_net_monthly"] > 0.04


def test_by_era_reports_too_few_blocks_rather_than_a_mean():
    res = {"blocks": ["2020-01", "2020-02", "2020-03"],
           "excess": [0.01, 0.02, 0.03]}
    out = R.by_era(res)
    assert out["2017-2024"]["verdict"].startswith("too few blocks")
    assert "mean_excess_net_monthly" not in out["2017-2024"]


# --------------------------------------------------------------------------
# Book D's refusal


def test_book_d_is_refused_for_the_registered_reason_not_a_missing_file():
    d = R.replay_book_d()
    assert d["ran"] is False
    why = d["refused"]
    assert "NO HISTORICAL LEG" in why
    assert "backfilled forward evidence" in why
    assert d["next_test"]


# --------------------------------------------------------------------------
# registration


def test_the_job_is_registered_in_the_night_factory():
    from scripts import night_factory_jobs as NFJ
    assert "B_first_books_replay" in NFJ.JOBS


def test_the_job_is_not_in_the_timeboxed_or_resumable_sets():
    from scripts import night_factory_jobs as NFJ
    # It runs to completion in one pass and checkpoints nothing, so claiming
    # either would be a promise the script does not keep.
    assert "B_first_books_replay" not in NFJ.TIMEBOXED
    assert "B_first_books_replay" not in NFJ.RESUMABLE


#: The four drafts this job's family covers, by name. It used to be
#: `TRIAL-DRAFT-*.md` — every draft in the directory — which was true only while
#: the four night-job books were the only drafts there. Chunk 10 added
#: `TRIAL-DRAFT-L2-typed-events-v1.md`, whose family is `E1_TYPED_EVENTS_2026_09`
#: because it shares no multiplicity budget with the books, and the glob turned
#: red for the correct behaviour. A guard that cannot tell one family from
#: another is a guard on the directory, not on the family.
BOOK_DRAFTS = (
    "TRIAL-DRAFT-A-si-low-turnover-high-v1.md",
    "TRIAL-DRAFT-B-insider-cluster-length-v1.md",
    "TRIAL-DRAFT-C-disposition-overhang-conditioner-v0.md",
    "TRIAL-DRAFT-D-abstention-book-v0.md",
)


def test_the_family_name_matches_the_pre_registrations():
    from pathlib import Path
    assert R.FAMILY == "NIGHT_JOB_BOOKS_2026_09"
    trials = Path("docs/TRIALS")
    for name in BOOK_DRAFTS:
        f = trials / name
        assert f.is_file(), f"{name} is missing — this family's own prereg"
        assert R.FAMILY in f.read_text(encoding="utf-8"), name


def test_every_draft_declares_some_family():
    """The weaker claim that IS true of every draft: a multiplicity budget has
    to be named, whichever one it is."""
    from pathlib import Path
    for f in Path("docs/TRIALS").glob("TRIAL-DRAFT-*.md"):
        text = f.read_text(encoding="utf-8")
        assert "Family" in text or "family" in text, f.name
        assert "Holm" in text, f"{f.name} names no export-time multiplicity rule"


def test_the_bhar_window_starts_after_the_filing_month_closes():
    """A BHAR window that began inside the filing month would read the
    disclosure-day move as drift."""
    idx = pd.bdate_range("2020-01-01", periods=400)
    daily = pd.DataFrame({7: 0.0}, index=idx)
    daily.loc[idx[:40], 7] = 1.0          # a huge move inside January
    block = pd.Period("2020-01", freq="M")
    out = R._bhar(daily, 7, block)
    assert out is not None
    assert math.isclose(out, 0.0, abs_tol=1e-9)
