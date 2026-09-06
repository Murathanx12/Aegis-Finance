"""G7 — the forward-lane table, on planted worlds where the answer is known.

`docs/ROADMAP_2026-09-07_GROWTH_BOOK_AMENDMENT.md` §2.2 and §4. Three things
are pinned here because all three are the kind that stay true right up until
nobody is looking:

1. **BETA IS THE FIRST KEY** — of every row, on the happy path AND on the
   refusal path. A guard that only checks the successful row would pass while
   the refusals reordered themselves, which is precisely the class of guard
   this program has learned catches nothing.
2. **A SHORT SERIES REFUSES** — and the refusal names the count and the floor
   and carries no wealth numbers at all. A refusal is a finding; a refusal that
   quietly reports a beta on 8 observations is a fabrication.
3. **THE LEVERAGE-NEUTRAL CONSTRUCTION IS EXACT ON A PURE-BETA LANE** — a lane
   that is algebraically `rf + 1.5*(spy - rf)` must show beta 1.5, must win on
   RAW terminal wealth in a rising market, and must show a leverage-neutral
   excess of ZERO, because scaling by `vs/vb = 2/3` and parking the other third
   at RF reconstitutes SPY exactly:

       (2/3)·[rf + 1.5(spy − rf)] + (1/3)·rf  =  (2/3)rf + (spy − rf) + (1/3)rf
                                              =  spy

   The identity is used instead of a tolerance band on purpose: if the runner
   ever charges financing on a DE-levered book, or forgets that unused cash
   earns RF, or annualises at the wrong frequency, this goes red immediately.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import growth_g7_forward_lanes as G7
from learner import growth as G

REPO = Path(__file__).resolve().parents[2]
RECEIPT = REPO / "backend" / "data" / "optimus" / "growth_book" / "G7_forward_lanes.json"
TABLE = REPO / "backend" / "data" / "optimus" / "growth_book" / "G7_forward_lanes.md"


def _world(n: int = 120, seed: int = 20260907, beta: float = 1.5,
           alpha: float = 0.0, drift: float = 0.002, lag: int = 0):
    """A planted daily world. `lag` marks the book on YESTERDAY'S market.

    Dates are a fixed historical span, never "today + k": a fixture that
    encodes a calendar moment fails the day after that moment passes
    (CLAUDE.md, session-start protocol item 5).
    """
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-02", periods=n)
    spy = pd.Series(rng.normal(drift, 0.010, n), index=idx)
    rf = pd.Series(np.full(n, 0.00018), index=idx)
    driver = spy.shift(lag).fillna(0.0) if lag else spy
    book = rf + beta * (driver - rf) + alpha
    return book, spy, rf


def _row(**kw):
    book, spy, rf = _world(**{k: v for k, v in kw.items()
                              if k in {"n", "seed", "beta", "alpha", "drift", "lag"}})
    return G7.lane_row("planted", book, spy, rf,
                       source="planted world", cost_basis="planted, 0 bps")


# ─────────────────────────────────────────────── 1. beta is the first key

def test_beta_is_the_first_key_of_a_readable_row():
    row = _row()
    assert list(row)[0] == "beta", (
        "beta must be the FIRST key of the row dict — the amendment's rule is "
        f"enforced by ordering, and the row began with {list(row)[:3]}")
    assert row["beta"] is not None


def test_beta_is_the_first_key_of_a_REFUSAL_row_too():
    row = _row(n=10)
    assert row["verdict"] == "CANNOT DETERMINE"
    assert list(row)[0] == "beta", (
        "the refusal path must keep beta first as well; a guard that only "
        f"holds on the happy path holds nothing. Got {list(row)[:3]}")


def test_beta_is_the_first_column_of_the_markdown_table():
    assert G7._COLUMNS[0][0] == "beta"
    md = G7.to_markdown({"rows": [_row()], "counts": {}, "ruler": {},
                         "market_benchmark": {}, "rf_extension": {},
                         "discovery": {}})
    header = next(l for l in md.splitlines() if l.startswith("| beta"))
    assert header.split("|")[1].strip() == "beta"


# ────────────────────────────────────────────────── 2. the refusal path

def test_a_short_series_refuses_and_names_the_count_and_the_floor():
    row = _row(n=10)
    assert row["verdict"] == "CANNOT DETERMINE"
    assert "only 10 observations" in row["why"], row["why"]
    assert str(G7.MIN_OBS) in row["why"]
    assert "interpolated" in row["why"]


def test_a_refusal_reports_NO_wealth_numbers_at_all():
    row = _row(n=10)
    for key in ("beta", "beta_t_vs_1", "beta_dimson", "raw_excess_ann_pct",
                "raw_excess_total_pp", "lev_neutral_excess_ann_pct",
                "lev_neutral_excess_total_pp", "maxdd_lane_pct",
                "maxdd_spy_pct"):
        assert row[key] is None, (
            f"{key} must be None on a refusal — a number here is a number "
            f"invented from {row['n_obs']} observations")


def test_a_constant_lane_refuses_rather_than_reporting_a_zero_beta():
    """Zero variance is not zero beta. It is no information."""
    _, spy, rf = _world()
    flat = pd.Series(0.0, index=spy.index)
    row = G7.lane_row("flat", flat, spy, rf, source="planted",
                      cost_basis="planted")
    assert row["verdict"] == "CANNOT DETERMINE"
    assert "constant" in row["why"]


def test_the_floor_is_the_declared_constant_not_a_literal():
    row = _row(n=G7.MIN_OBS + 3)
    assert row["verdict"] == "OK", (
        "a series just above the floor must be graded, or the floor is not the "
        "floor it declares")


# ──────────────────────── 3. the leverage-neutral construction, exactly

def test_a_pure_beta_lane_shows_beta_1_5_and_ZERO_leverage_neutral_excess():
    """The whole point: a book that only borrowed beta wins raw and not neutral."""
    row = _row(beta=1.5)
    assert row["beta"] == pytest.approx(1.5, abs=1e-6), (
        "a lane planted as exactly 1.5x SPY excess must measure beta 1.5")
    # It won by arithmetic in a rising market...
    assert row["raw_excess_total_pp"] > 0
    # ...and the win evaporates the moment it is run at SPY's own volatility.
    assert row["lev_neutral_excess_total_pp"] == pytest.approx(0.0, abs=1e-6), (
        "scaling a pure-beta book to SPY's vol and parking the rest at RF "
        "reconstitutes SPY EXACTLY; a non-zero excess here means financing was "
        "charged on a de-levered book, or unused cash was not paid RF")
    assert row["lev_neutral_excess_ann_pct"] == pytest.approx(0.0, abs=1e-6)
    assert row["leverage_neutral"]["scale"] == pytest.approx(2.0 / 3.0, abs=1e-3)


def test_a_planted_intercept_wins_LEVERAGE_NEUTRAL_which_is_the_other_half():
    """"A book that wins only by borrowing beta must say so; it may still win."""
    plain = _row(beta=1.5)
    with_alpha = _row(beta=1.5, alpha=0.0004)
    assert with_alpha["lev_neutral_excess_total_pp"] > \
        plain["lev_neutral_excess_total_pp"] + 1.0
    assert with_alpha["intercept_annualised_pct"] > 5.0
    # and its beta is unchanged — the alpha did not arrive as leverage
    assert with_alpha["beta"] == pytest.approx(1.5, abs=1e-6)


def test_a_beta_one_lane_is_leverage_neutral_unchanged():
    """Scale 1.0 must charge nothing and pay nothing. The no-op case."""
    row = _row(beta=1.0)
    assert row["leverage_neutral"]["scale"] == pytest.approx(1.0, abs=1e-6)
    assert row["lev_neutral_excess_total_pp"] == pytest.approx(0.0, abs=1e-6)


def test_the_daily_financing_argument_charges_the_ANNUAL_rate_not_a_monthly_one():
    """`lever` divides by 12; a daily series needs the argument pre-scaled.

    Without this the runner would charge one MONTH of spread every DAY — a 21x
    overcharge that would look like a plausible drag rather than like a bug.
    """
    arg = G7.financing_bps_periodic(100.0, 252)
    per_period = arg / 10_000.0 / 12.0
    assert per_period == pytest.approx(100.0 / 10_000.0 / 252.0, rel=1e-12)
    # and the levered leg actually pays it: 2x for one period costs
    # (L-1) * (rf + spread).
    idx = pd.bdate_range("2024-01-02", periods=1)
    b = pd.Series([0.0], index=idx)
    rf = pd.Series([0.0], index=idx)
    assert float(G.lever(b, rf, 2.0, financing_bps=arg).iloc[0]) == \
        pytest.approx(-100.0 / 10_000.0 / 252.0, rel=1e-9)


def test_the_rescale_is_capped_by_the_gross_cap():
    """A very low-vol lane cannot be levered past the declared ceiling."""
    _, spy, rf = _world()
    tiny = rf + 0.05 * (spy - rf)          # ~1/20th of SPY's vol
    row = G7.lane_row("tiny", tiny, spy, rf, source="planted",
                      cost_basis="planted")
    assert row["leverage_neutral"]["capped_by_gross"] is True
    assert row["leverage_neutral"]["scale"] == pytest.approx(G7.GROSS_CAP)


# ───────────────────────────── the stale-mark diagnostic, both directions

def test_a_book_marked_a_day_late_is_FLAGGED_and_its_ols_beta_understates():
    """The finding that made this diagnostic non-optional, planted."""
    row = _row(beta=1.0, lag=1)
    assert row["stale_marks_suspected"] is True
    assert abs(row["beta"]) < 0.3, (
        "a one-session-late mark must collapse the contemporaneous beta — "
        "that is the bias the diagnostic exists to expose")
    assert row["beta_dimson"] == pytest.approx(1.0, abs=0.15), (
        "the Dimson sum must recover the exposure the OLS beta hid")
    assert "STALE MARKS" in row["headline"]


def test_a_synchronously_marked_book_is_NOT_flagged():
    """A diagnostic that fires on everything is not a diagnostic."""
    row = _row(beta=1.0, lag=0)
    assert row["stale_marks_suspected"] is False
    assert "STALE MARKS" not in row["headline"]


# ───────────────────────────────────────────── the phrase rule, in code

def test_beats_SPY_never_appears_without_beta_maxDD_and_the_cost_basis():
    row = _row(beta=1.5)
    head = row["headline"]
    assert "beats SPY" in head, "a 1.5x book in a rising market beats SPY raw"
    for token in ("beta", "maxDD", "cost basis"):
        assert token in head, (
            f"the amendment §4 forbids 'beats SPY' without {token!r} beside it")


@pytest.mark.skipif(not TABLE.is_file(), reason="G7 table not generated")
def test_the_written_table_obeys_the_phrase_rule_line_by_line():
    for line in TABLE.read_text(encoding="utf-8").splitlines():
        if "beats SPY" in line:
            assert "beta" in line and "maxDD" in line and "cost basis" in line, \
                f"line says 'beats SPY' without its escorts: {line[:160]}"


# ──────────────────────────────────────────────── the artefact on disk

@pytest.mark.skipif(not RECEIPT.is_file(), reason="G7 receipt not generated")
def test_the_receipt_is_provenance_clean_and_covers_every_declared_book():
    from backend.services.receipt_provenance import check_receipt, hard_failures

    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    assert hard_failures(check_receipt(receipt)) == []
    lanes = {r["lane"] for r in receipt["rows"]}
    missing = (set(G7.WEBSITE_LANES) | set(G7.HACK_ACCOUNTS)) - lanes
    assert not missing, (
        f"every declared book gets a row, readable or not; missing {missing}. "
        "A book dropped from the table reads as 'not a book'.")
    for row in receipt["rows"]:
        assert list(row)[0] == "beta"
        assert row["verdict"] in {"OK", "CANNOT DETERMINE"}
        if row["verdict"] == "CANNOT DETERMINE":
            assert row["why"]


@pytest.mark.skipif(not RECEIPT.is_file(), reason="G7 receipt not generated")
def test_the_receipt_records_how_much_of_the_window_the_rf_carry_covered():
    """The RF vintage ends before the lane windows do, and that is stated."""
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    rf = receipt["rf_extension"]
    assert rf["days_carried_forward"] >= 0
    assert rf["last_observed"]
    assert "never interpolated" in rf["construction"]
