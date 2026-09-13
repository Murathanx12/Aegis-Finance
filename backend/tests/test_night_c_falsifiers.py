"""C's two falsifiers, on synthetic panels where the answer is planted.

No CRSP file is read here. What is pinned is the two things this job can get
wrong without failing: a placebo that is not the book's own construction with
one sign changed, and an orthogonalisation that credits momentum for a payoff
that belonged to overhang all along.

The synthetic panels are built so the RIGHT answer is known before the run:

  * a planted overhang effect with momentum riding on it as a passenger --
    momentum must DIE once overhang is on the right-hand side, and overhang
    must survive;
  * a planted SYMMETRIC effect (both tails of the overhang distribution beat
    the unconditioned book) -- the placebo must PAY and the book must close.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import night_c_falsifiers as F
from scripts import night_first_books_replay as R


# --------------------------------------------------------------------------
# helpers: a monthly panel, an event-sign set and an overhang series


def _months(n: int):
    return pd.period_range("2000-01", periods=n, freq="M")


def _panel(rets: dict, months) -> pd.DataFrame:
    """`rets[(ym_index, permno)] -> monthly return`; every name is eligible."""
    rows = []
    for i, ym in enumerate(months):
        for p in sorted({k[1] for k in rets}):
            rows.append({"permno": p, "ym": ym,
                         "ret_m": float(rets.get((i, p), 0.0)),
                         "price": 50.0, "dv": 10_000_000.0, "turnover_m": 0.05})
    return pd.DataFrame(rows)


def _scrambled_cgo(names) -> dict:
    """Overhang that is NOT monotone in permno.

    The unconditioned comparator is `sorted(names)[:30]`, so a synthetic panel
    whose overhang rises with the permno makes the comparator and the bottom
    tercile the SAME NAMES and every difference identically zero. The first run
    of these tests did exactly that and reported "the placebo does not pay" for
    a panel built to make it pay.
    """
    n = len(names)
    return {p: ((p * 37) % n - n / 2) / (n / 2) for p in names}


def _inputs(months, *, good_names, bad_names, cgo_of) -> dict:
    """Book C's inputs, planted rather than computed from CRSP."""
    good = {(int(ym.ordinal), int(p)) for ym in months for p in good_names}
    bad = {(int(ym.ordinal), int(p)) for ym in months for p in bad_names}
    cgo_by_month = {ym: {int(p): float(v) for p, v in cgo_of.items()}
                    for ym in months}
    return {"good": good, "bad": bad, "cgo_by_month": cgo_by_month,
            "event_sign": R.EVENT_SIGN_V0}


# --------------------------------------------------------------------------
# (a) the sign-flip placebo IS the book's construction with one sign changed


def test_the_placebo_takes_the_other_tail_of_the_same_overhang_distribution():
    months = _months(6)
    good = list(range(30))
    cgo = {p: (p - 15) / 15.0 for p in good}          # -1.0 .. +0.93
    inputs = _inputs(months, good_names=good, bad_names=[], cgo_of=cgo)
    pool = pd.DataFrame({"permno": good})

    book = R.book_c_selectors(inputs)["conditioned"](pool, months[0])
    flip = F.sign_flip_selectors(inputs)["good_loss"](pool, months[0])

    assert book and flip
    assert not (set(book) & set(flip)), "the two tails must not overlap"
    # the book ranks most-POSITIVE overhang first; the placebo most-NEGATIVE
    assert cgo[book[0]] == max(cgo[p] for p in book)
    assert cgo[flip[0]] == min(cgo[p] for p in flip)
    assert len(book) == len(flip) == 10             # a tercile of 30, each end


def test_the_bad_news_leg_excludes_names_the_good_news_leg_calls_good_news():
    """A month with contradictory IBES rows puts a name in BOTH sets. A short
    leg holding names the long leg is long is not a placebo."""
    months = _months(3)
    both = 5
    inputs = _inputs(months, good_names=[both] + list(range(10, 20)),
                     bad_names=[both] + list(range(20, 30)),
                     cgo_of={p: p / 30.0 for p in range(30)})
    pool = pd.DataFrame({"permno": list(range(30))})
    bad_leg = F.sign_flip_selectors(inputs)["bad_gain"](pool, months[0])
    assert both not in bad_leg


def test_a_symmetric_planted_effect_makes_the_placebo_pay_and_closes_the_book():
    """Both tails beat the unconditioned book -- which is drift, not disposition.

    §5 clause 1 fires: "the sign-flip placebo ALSO pays (it is drift, i.e.
    momentum again, not disposition)".
    """
    months = _months(30)
    good = list(range(60))
    cgo = _scrambled_cgo(good)
    top = {p for p in good if cgo[p] >= np.quantile(list(cgo.values()), 2 / 3)}
    bottom = {p for p in good if cgo[p] <= np.quantile(list(cgo.values()), 1 / 3)}
    rng = np.random.default_rng(11)
    rets = {}
    for i in range(len(months)):
        for p in good:
            # noise as well as the planted edge: a series with no dispersion has
            # no sampling distribution and `newey_west_t` returns None for it,
            # which would make this test pass or fail for the wrong reason
            rets[(i, p)] = (0.04 if (p in top or p in bottom) else 0.0) \
                + float(rng.normal(0.0, 0.01))
    panel = _panel(rets, months)
    inputs = _inputs(months, good_names=good, bad_names=[], cgo_of=cgo)

    placebo = F.run_sign_flip_placebo(panel, inputs, k=20)
    assert placebo["placebo_pays"] is True
    assert placebo["vs_unconditioned"]["mean_excess_net_monthly"] > 0

    out = F.decide(placebo, {"momentum_survives": False}, {"mean_excess_net_monthly": 0.004,
                                                           "nw_lag2_t": 2.1})
    assert out["verdict"] == "FAILED_VARIANT"
    assert any("placebo" in c for c in out["clauses_fired"])


def test_an_effect_only_in_the_top_tail_leaves_the_placebo_flat():
    """The control's own control: a one-sided effect must NOT fire clause 1."""
    months = _months(30)
    good = list(range(60))
    cgo = _scrambled_cgo(good)
    cut = np.quantile(list(cgo.values()), 2 / 3)
    rng = np.random.default_rng(12)
    rets = {(i, p): (0.04 if cgo[p] >= cut else 0.0) + float(rng.normal(0.0, 0.01))
            for i in range(len(months)) for p in good}
    panel = _panel(rets, months)
    inputs = _inputs(months, good_names=good, bad_names=[], cgo_of=cgo)

    placebo = F.run_sign_flip_placebo(panel, inputs, k=20)
    assert placebo["placebo_pays"] is False
    assert placebo["vs_unconditioned"]["mean_excess_net_monthly"] <= 0


# --------------------------------------------------------------------------
# (b) the momentum orthogonalisation


def _fm_rows(n_months: int, n_names: int, *, rng, payoff: str) -> pd.DataFrame:
    """Rows where the payoff is planted on ONE of the two variables.

    `payoff="cgo"`: next month's return is driven by overhang alone, and
    momentum is a noisy COPY of overhang -- so momentum prices raw and must die
    once overhang is on the right-hand side.
    `payoff="mom"`: the mirror.
    """
    rows = []
    for m in range(n_months):
        c = rng.normal(size=n_names)
        x = 0.9 * c + 0.436 * rng.normal(size=n_names)     # corr ~0.9 with cgo
        driver = c if payoff == "cgo" else x
        y = 0.02 * driver + 0.01 * rng.normal(size=n_names)
        for i in range(n_names):
            rows.append({"ym": f"20{m // 12:02d}-{m % 12 + 1:02d}", "permno": i,
                         "mom": float(x[i]), "cgo": float(c[i]), "fwd": float(y[i])})
    return pd.DataFrame(rows)


def test_a_planted_overhang_effect_makes_momentum_die_and_overhang_survive():
    rng = np.random.default_rng(20260913)
    fm = F.fama_macbeth_orthogonalisation(_fm_rows(120, 200, rng=rng, payoff="cgo"))
    assert fm["n_blocks"] == 120
    # raw momentum LOOKS priced -- it is 0.9 correlated with the thing that pays
    assert abs(fm["raw_mom"]["nw_lag2_t"]) >= F.T_ALIVE
    v = F.read_momentum_verdict(fm)
    assert v["verdict"] == "MOMENTUM_DIES"
    assert v["momentum_survives"] is False
    assert v["overhang_survives"] is True


def test_momentum_that_was_never_alive_cannot_be_subsumed_and_says_so():
    """Run 1 (2026-09-13) read raw momentum at t 0.15 on the book's rows, so
    'momentum dies' was vacuous. The verdict names it: not a pass of the
    subsumption test, but the costume clause does not fire either, because a
    payoff momentum does not earn cannot be momentum's."""
    fm = {"n_blocks": 348,
          "raw_mom": {"nw_lag2_t": 0.1525}, "resid_mom": {"nw_lag2_t": 0.1174},
          "raw_cgo": {"nw_lag2_t": 0.6498}, "resid_cgo": {"nw_lag2_t": 0.8595}}
    v = F.read_momentum_verdict(fm)
    assert v["verdict"] == "MOMENTUM_NOT_ALIVE"
    assert v["subsumption_testable"] is False
    assert v["momentum_survives"] is False
    assert "NOT a pass" in v["why"]
    out = F.decide({"placebo_pays": False}, v, {"mean_excess_net_monthly": 0.002438,
                                                "nw_lag2_t": 1.3809,
                                                "declared_effect_size": 0.01})
    assert out["verdict"] == "CONDITIONAL"
    assert "untestable, not passed" in out["reading"]
    assert "both falsifiers PASSED" not in out["reading"]


def test_a_live_raw_momentum_marks_the_subsumption_test_as_testable():
    rng = np.random.default_rng(20260913)
    fm = F.fama_macbeth_orthogonalisation(_fm_rows(120, 200, rng=rng, payoff="cgo"))
    assert F.read_momentum_verdict(fm)["subsumption_testable"] is True


def test_a_planted_momentum_effect_makes_momentum_survive_and_closes_the_book():
    rng = np.random.default_rng(20260913)
    fm = F.fama_macbeth_orthogonalisation(_fm_rows(120, 200, rng=rng, payoff="mom"))
    v = F.read_momentum_verdict(fm)
    assert v["verdict"] == "MOMENTUM_SURVIVES"
    out = F.decide({"placebo_pays": False}, v, {"mean_excess_net_monthly": 0.004,
                                                "nw_lag2_t": 2.1})
    assert out["verdict"] == "FAILED_VARIANT"
    assert any("momentum" in c for c in out["clauses_fired"])


def test_the_bivariate_and_residual_legs_agree_on_sign_and_on_the_line():
    """Frisch-Waugh, as far as it actually goes.

    The bivariate slope is the residual slope divided by sqrt(1 - rho^2), and
    rho is re-estimated every month, so the two SERIES differ by a varying
    factor and their Newey-West t's are close but not equal. What must hold —
    and what a sign error would break — is that they agree on the sign and on
    which side of the |t| >= 2 line they land.
    """
    rng = np.random.default_rng(7)
    fm = F.fama_macbeth_orthogonalisation(_fm_rows(60, 150, rng=rng, payoff="cgo"))
    for a, b in (("resid_mom", "bivariate_mom"), ("resid_cgo", "bivariate_cgo")):
        assert np.sign(fm[a]["mean_monthly_slope"]) == np.sign(fm[b]["mean_monthly_slope"])
        assert (abs(fm[a]["nw_lag2_t"]) >= F.T_ALIVE) == (abs(fm[b]["nw_lag2_t"]) >= F.T_ALIVE)
        assert fm[a]["nw_lag2_t"] == pytest.approx(fm[b]["nw_lag2_t"], rel=0.25)


def test_a_month_with_too_few_names_is_skipped_and_counted():
    rng = np.random.default_rng(1)
    rows = _fm_rows(4, 200, rng=rng, payoff="cgo")
    thin = rows[rows["ym"] == "2000-01"].head(5)
    rows = pd.concat([rows[rows["ym"] != "2000-01"], thin], ignore_index=True)
    fm = F.fama_macbeth_orthogonalisation(rows)
    assert fm["skipped_months"]["too_few_names"] == 1
    assert fm["n_blocks"] == 3


def test_an_empty_frame_refuses_rather_than_returning_a_zero():
    fm = F.fama_macbeth_orthogonalisation(pd.DataFrame(
        columns=["ym", "permno", "mom", "cgo", "fwd"]))
    assert fm["n_blocks"] == 0 and "refused" in fm
    v = F.read_momentum_verdict(fm)
    assert v["verdict"] == "CANNOT_DETERMINE" and v["momentum_survives"] is None


# --------------------------------------------------------------------------
# momentum is built from the month BEFORE the formation close


def test_momentum_never_contains_the_month_it_is_formed_at_or_the_one_it_earns():
    months = _months(30)
    names = list(range(5))
    # One name spikes in exactly one month. Momentum at the formation month is
    # the eleven months ENDING ONE MONTH EARLIER, so the spike must be absent
    # at the spike month itself, present the month after, and gone again twelve
    # months later.
    spike_i, spike_p = 12, 3
    rets = {(i, p): (0.5 if (i == spike_i and p == spike_p) else 0.0)
            for i in range(len(months)) for p in names}
    panel = _panel(rets, months)
    cgo_by_month = {ym: {p: 0.1 * p for p in names} for ym in months}
    rows = F.momentum_overhang_rows(panel, cgo_by_month)
    got = {(r.ym, r.permno): r.mom for r in rows.itertuples()}
    assert got[(str(months[spike_i]), spike_p)] == pytest.approx(0.0)
    assert got[(str(months[spike_i + 1]), spike_p)] == pytest.approx(0.5)
    assert got[(str(months[spike_i + 12]), spike_p)] == pytest.approx(0.0)
    # the first eleven months cannot carry a momentum at all, and are absent
    assert (str(months[3]), spike_p) not in got


def test_the_regression_universe_is_the_books_own_eligible_corner():
    months = _months(20)
    names = list(range(10))
    rets = {(i, p): 0.01 for i in range(len(months)) for p in names}
    panel = _panel(rets, months)
    panel.loc[panel["permno"] < 4, "dv"] = 1.0          # below the $3M floor
    cgo_by_month = {ym: {p: 0.1 * p for p in names} for ym in months}
    rows = F.momentum_overhang_rows(panel, cgo_by_month)
    assert not rows.empty
    assert set(rows["permno"]) == set(range(4, 10))


# --------------------------------------------------------------------------
# the verdict, and what it may not do


def test_a_falsifier_that_passes_is_not_evidence_for_the_book():
    out = F.decide({"placebo_pays": False},
                   {"momentum_survives": False, "overhang_survives": True},
                   {"mean_excess_net_monthly": 0.003978, "nw_lag2_t": 2.1283,
                    "declared_effect_size": 0.01})
    assert out["verdict"] == "CONDITIONAL"
    assert "not evidence FOR the book" in out["reading"]


def test_a_primary_on_the_wrong_side_of_zero_closes_the_book_by_amendment_1():
    """TRIAL-DRAFT-C §5 Amendment 1 (2026-09-13) carries the clause A §5 always
    had: a net block-mean <= 0 over the registered slice is FAILED_VARIANT
    whatever the falsifiers did. The amendment was written before the
    registered read; the builder's first version of this job NAMED the gap
    instead of filling it, and the amendment is the signed answer."""
    out = F.decide({"placebo_pays": False},
                   {"momentum_survives": False, "overhang_survives": True},
                   {"mean_excess_net_monthly": -0.004003, "nw_lag2_t": -1.12,
                    "declared_effect_size": 0.01})
    assert out["verdict"] == "FAILED_VARIANT"
    assert out["primary_is_below_zero"] is True
    assert len(out["clauses_fired"]) == 1
    assert "Amendment 1" in out["clauses_fired"][0]
    assert "WRONG SIDE OF ZERO" in out["reading"]


def test_a_positive_primary_below_the_declared_effect_does_not_claim_a_gap():
    out = F.decide({"placebo_pays": False},
                   {"momentum_survives": False, "overhang_survives": True},
                   {"mean_excess_net_monthly": 0.003978, "nw_lag2_t": 2.1283,
                    "declared_effect_size": 0.01})
    assert out["primary_is_below_zero"] is False
    assert "WRONG SIDE OF ZERO" not in out["reading"]


def test_both_clauses_can_fire_at_once_and_both_are_named():
    out = F.decide({"placebo_pays": True}, {"momentum_survives": True}, None)
    assert out["verdict"] == "FAILED_VARIANT"
    assert len(out["clauses_fired"]) == 2


def test_an_unanswerable_orthogonalisation_is_not_a_pass():
    out = F.decide({"placebo_pays": False}, {"momentum_survives": None}, None)
    assert out["verdict"] == "CANNOT_DETERMINE"
    assert "did not run is not a check that passed" in out["reading"]


def test_a_missing_primary_receipt_cannot_be_read_as_conditional():
    out = F.decide({"placebo_pays": False},
                   {"momentum_survives": False, "overhang_survives": True}, None)
    assert out["verdict"] == "CANNOT_DETERMINE"


# --------------------------------------------------------------------------
# the REGISTERED construction: a full 60-month window, and a 1995 start


def test_a_name_with_thirty_months_of_history_is_in_at_24_and_out_at_60():
    """Run 1 computed an overhang from 24 months while passing a 60-month
    lookback, so its first 36 overhangs per name came off a TRUNCATED
    reference-price window. The registered construction is a full window."""
    months = _months(31)
    names = list(range(3))
    rows = []
    for i, ym in enumerate(months):
        for p in names:
            rows.append({"permno": p, "ym": ym, "ret_m": 0.0,
                         "price": 50.0 + i, "dv": 10_000_000.0,
                         "turnover_m": 0.05})
    panel = pd.DataFrame(rows)

    at24 = R.book_c_overhang(panel, min_history=24, lookback=60)
    at60 = R.book_c_overhang(panel, min_history=60, lookback=60)
    # 31 months on the tape: the last seven carry a 24-month-history overhang
    assert sum(len(d) for d in at24.values()) == 7 * len(names)
    # and NOT ONE month carries one when a full 60-month window is required
    assert sum(len(d) for d in at60.values()) == 0


def test_the_replay_default_is_still_run01s_so_run01_stays_reproducible():
    """A silent change here would rewrite a published receipt's meaning."""
    import inspect
    sig = inspect.signature(R.book_c_inputs)
    assert sig.parameters["min_history"].default == R.CGO_MIN_HISTORY_RUN01 == 24
    assert sig.parameters["lookback"].default == R.CGO_LOOKBACK_MONTHS == 60
    assert F.REGISTERED_MIN_HISTORY == 60


def test_the_read_starts_at_the_later_of_the_registration_and_the_first_full_window():
    months = _months(36)
    panel = _panel({(i, p): 0.0 for i in range(36) for p in range(3)}, months)
    have = {ym: ({1: 0.2} if i >= 20 else {}) for i, ym in enumerate(months)}
    inputs = {"cgo_by_month": have}
    read, start, first = F.registered_read_panel(panel, inputs, read_start="1995-01")
    assert first == str(months[20])
    assert start == str(months[20]), "the registration's own start is EARLIER here"
    assert read["ym"].min() == months[20]

    late = F.registered_read_panel(panel, inputs, read_start=str(months[30]))
    assert late[1] == str(months[30]), "a later registered start wins"


def test_the_january_split_is_labelled_an_unregistered_diagnostic():
    res = {"blocks": [str(m) for m in _months(48)],
           "excess": [0.05 if i % 12 == 0 else 0.0 for i in range(48)]}
    out = F.january_split(res)
    assert out["status"] == "UNREGISTERED_DIAGNOSTIC"
    assert out["january"]["n_blocks"] == 4
    assert out["february_to_december"]["n_blocks"] == 44
    assert out["january_minus_rest"] == pytest.approx(0.05)
    assert "no decision rule" in out["why"].lower()


def test_the_january_split_refuses_a_result_with_no_block_series():
    assert F.january_split({})["status"] == "no block series"


# --------------------------------------------------------------------------
# registration and provenance


def test_the_job_is_registered_in_the_night_factory():
    from scripts import night_factory_jobs as NFJ
    assert "C_falsifiers" in NFJ.JOBS
    assert "C_falsifiers" not in NFJ.TIMEBOXED
    assert "C_falsifiers" not in NFJ.RESUMABLE


def test_the_falsifiers_are_the_ones_the_first_read_named():
    """The `next_test` on run 1's Book C receipt IS this job's brief."""
    import json
    from pathlib import Path

    p = Path("backend/data/optimus/first_books/replay/"
             "disposition_overhang_conditioner_v0_2026-09-12T215811Z.json")
    assert p.is_file(), "the first read's Book C receipt"
    nxt = json.loads(p.read_text(encoding="utf-8"))["next_test"]
    assert "sign-flip placebo" in nxt and "momentum orthogonalisation" in nxt


def test_the_placebo_uses_the_books_own_tercile_function_not_a_second_one():
    """A placebo that cuts its tercile with a second implementation of the
    book's quantile is not a placebo."""
    import ast
    from pathlib import Path

    src = Path("scripts/night_c_falsifiers.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "overhang_conditioned_ranks" in called
    assert "quantile" not in called, (
        "the falsifier computes its own tercile cut instead of the book's")


def test_the_cost_ruler_is_named_as_a_placeholder_on_the_job():
    assert F.COST_CURVE == "flat_25bps_pending_5c"
    assert F.COST_BPS_PER_SIDE == 25.0


# --------------------------------------------------------------------------
# THE $10M FLOOR (chunk 12, T2) — C's own registered `next_test`
#
# The floor is the one parameter in this job that can move the answer without
# moving a line of the construction, so it is pinned three ways: the DEFAULT is
# the registered primary (so an unqualified call still runs the registered
# read), the floor reaches the ORTHOGONALISATION's universe and not only the
# book's, and the pair is read under "both floors or neither".


def _mixed_dv_panel(months, *, big, small):
    """A panel whose names sit on two sides of the $10M line."""
    rows = []
    for ym in months:
        for p in big:
            rows.append({"permno": p, "ym": ym, "ret_m": 0.01, "price": 50.0,
                         "dv": 50_000_000.0, "turnover_m": 0.05})
        for p in small:
            rows.append({"permno": p, "ym": ym, "ret_m": 0.01, "price": 50.0,
                         "dv": 4_000_000.0, "turnover_m": 0.05})
    return pd.DataFrame(rows)


def test_the_default_floor_is_the_registered_primary_one():
    """An unqualified call must still run the REGISTERED read: the second floor
    is a deviation and has to be asked for by name."""
    import inspect

    assert F.PRIMARY_FLOOR_USD is None, (
        "None means `run_monthly`'s own FLOOR_USD; a second copy of 3e6 here "
        "would be a second place for the registered floor to drift")
    assert F.SECONDARY_FLOOR_USD == 10_000_000.0
    for fn in (F.C_falsifiers, F.run_sign_flip_placebo, F.momentum_overhang_rows):
        assert (inspect.signature(fn).parameters["floor_usd"].default
                is F.PRIMARY_FLOOR_USD), fn.__name__


def test_the_floor_moves_the_orthogonalisations_universe_too():
    """A regression run on the $3M universe while the book traded the $10M one
    answers a question about a different market."""
    months = _months(20)
    big, small = [1, 2, 3], [4, 5, 6]
    panel = _mixed_dv_panel(months, big=big, small=small)
    cgo = {ym: {p: 0.1 * p for p in big + small} for ym in months}

    wide = F.momentum_overhang_rows(panel, cgo)
    assert set(wide["permno"]) == set(big + small), "the $3M floor keeps both tiers"

    tight = F.momentum_overhang_rows(panel, cgo, floor_usd=F.SECONDARY_FLOOR_USD)
    assert set(tight["permno"]) == set(big), "the $10M floor drops the small tier"


def test_the_floor_moves_the_book_and_its_twin_together():
    """TRIAL-H5's lesson: a corner-dependent control is re-measured at every
    corner. Raising the floor for the book alone would compare a $10M book with
    a $3M control."""
    months = _months(8)
    big, small = [1, 2, 3, 4], [5, 6, 7, 8]
    panel = _mixed_dv_panel(months, big=big, small=small)
    seen: list[set] = []

    def _select(pool, ym):
        seen.append(set(int(p) for p in pool["permno"]))
        return sorted(int(p) for p in pool["permno"])[:2]

    R.run_monthly(panel, _select, k=2, seed=1, label="t",
                  floor_usd=F.SECONDARY_FLOOR_USD)
    assert seen and all(s == set(big) for s in seen), (
        "the twin is drawn from the SAME eligible frame the selector saw")


# --- the pair, read under "both floors or neither" -------------------------


def _cell(mean, t, *, ran=True, eras=None, refused=None, floor=3_000_000.0):
    return {
        "ran": ran, "floor_usd": floor, "refused": refused,
        "primary_registered_construction": {
            "result": {"mean_excess_net_monthly": mean, "nw_lag2_t": t,
                       "p_two_sided": 0.5, "n_blocks": 359,
                       "median_names_selected": 30},
            "by_era": {k: {"mean_excess_net_monthly": v}
                       for k, v in (eras or {}).items()},
        },
        "verdict_block": {"verdict": "CONDITIONAL"},
        "sign_flip_placebo": {"placebo_pays": False},
        "momentum_orthogonalisation": {"verdict": "MOMENTUM_NOT_ALIVE"},
    }


def test_a_cell_that_did_not_run_means_neither_floor_is_quoted():
    """Both floors are printed or neither is. Quoting the floor that flatters
    the book is quoting a chosen corner."""
    pair = F.read_floor_pair(_cell(0.004, 2.4),
                             _cell(None, None, ran=False,
                                   refused="the IBES panel is absent"))
    assert pair["verdict"] == "CANNOT DETERMINE"
    assert pair["both_floors_read"] is False
    assert "IBES panel" in pair["reading"]


def test_a_secondary_floor_below_zero_closes_the_cell_not_the_primary():
    pair = F.read_floor_pair(_cell(0.004, 2.4), _cell(-0.001, -0.3,
                                                      floor=1e7))
    assert pair["verdict"] == "FAILED_VARIANT_AT_THE_SECONDARY_FLOOR"
    assert "SECONDARY floor" in pair["reading"]
    assert "$3M primary" in pair["reading"]


def test_a_secondary_floor_that_clears_cannot_promote_a_primary_that_did_not():
    """§5's ladder is read off the PRIMARY. A flattering corner is not a pass."""
    pair = F.read_floor_pair(_cell(0.002, 1.2), _cell(0.02, 3.0, floor=1e7))
    assert pair["verdict"] == "SECONDARY_FLOOR_CLEARS"
    assert "cannot promote" in pair["reading"]


def test_the_floor_clause_cannot_fire_on_a_primary_that_never_cleared():
    pair = F.read_floor_pair(_cell(0.0024, 1.38), _cell(0.0007, 0.45, floor=1e7))
    assert pair["verdict"] == "SECONDARY_FLOOR_DOES_NOT_CLEAR"
    assert "has not cleared" in pair["reading"]
    assert pair["delta_mean_secondary_minus_primary"] == pytest.approx(-0.0017)


def test_era_stability_is_counted_with_its_denominator_and_names_the_losers():
    st = F.era_stability({"by_era": {
        "1990-1999": {"mean_excess_net_monthly": -0.0028},
        "2000-2009": {"mean_excess_net_monthly": 0.0034},
        "2010-2016": {"mean_excess_net_monthly": -0.0018},
        "2017-2024": {"mean_excess_net_monthly": 0.0018}}})
    assert st["n_eras_read"] == 4 and st["n_positive"] == 2
    assert st["negative_eras"] == ["1990-1999", "2010-2016"]
    assert st["all_positive"] is False


def test_the_pair_reports_when_era_stability_does_not_survive_the_floor():
    """The $3M read's one property its t did not have was 'positive in every
    era'. Whether that survives the floor is the thing to print."""
    pair = F.read_floor_pair(
        _cell(0.0024, 1.38, eras={"a": 0.0002, "b": 0.0039,
                                  "c": 0.0030, "d": 0.0016}),
        _cell(0.0007, 0.45, floor=1e7,
              eras={"a": -0.0028, "b": 0.0034, "c": -0.0018, "d": 0.0018}))
    era = pair["era_stability"]
    assert era["primary_floor"]["n_positive"] == 4
    assert era["secondary_floor"]["n_positive"] == 2
    assert "does not survive the floor" in era["reading"]


def test_c_floor10m_is_registered_and_dispatchable():
    """A job the queue cannot dispatch is a job that silently never runs."""
    import inspect

    from scripts import night_factory_jobs as J

    assert "C_floor10m" in J.JOBS
    assert J.JOB_STAGES.get("C_floor10m") == "pnl", (
        "it prices books (net monthly excess), like C_falsifiers and A_corner")
    src = inspect.getsource(J.main)
    assert '"C_floor10m"' in src, (
        "the dispatcher must pass smoke= to it, or the queue crashes on arrival")
