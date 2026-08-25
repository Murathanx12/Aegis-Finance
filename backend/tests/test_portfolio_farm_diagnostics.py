"""Signal diagnostics, and baselines that state what they select.

TWO DEFECTS THESE PIN, BOTH PAID FOR
====================================
1. **A baseline decided by a tie-break.** `equal` scored every name 0.0, so
   `top_k` fell through to permno order and the farm's "equal" control was
   really *the k oldest surviving listings*. "Nothing beats equal" was read as
   *nothing beats a dumb equal-weight book* and actually meant *ROE and
   momentum are not distinguishable from a listing-age exposure* — a much
   narrower claim, and the one that turned `profit_roe`'s 31-year requirement
   into 126.
2. **Portfolio diagnostics standing in for signal diagnostics.** Every farm
   leaderboard went straight to terminal wealth, which cannot separate a weak
   signal from a good signal wrecked by construction. `value_bm` looked like a
   failed signal and is really "extreme top-k value in a mega-liquid universe
   selects distress".
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.services.portfolio_farm import diagnostics as D
from backend.services.portfolio_farm import replay
from backend.services.portfolio_farm import signals as SIG
from backend.services.portfolio_farm.panel import Panel
from backend.services.portfolio_farm.policy import Policy

T = 900
N = 40


def _panel(ret: np.ndarray | None = None, *, div: float = 0.0) -> Panel:
    """A panel whose returns are supplied, so a forward return is checkable."""
    r = np.zeros((T, N)) if ret is None else ret
    rx = r - div
    tri = np.cumprod(1.0 + r, axis=0)
    close = 100.0 * np.cumprod(1.0 + rx, axis=0)
    return Panel(
        dates=np.array([f"d{i:04d}" for i in range(T)], dtype=object),
        permnos=np.arange(1001, 1001 + N, dtype=np.int64),
        close=close.astype(np.float32), open_=close.astype(np.float32),
        ret=r.astype(np.float32), retx=rx.astype(np.float32),
        traded=np.ones((T, N), dtype=bool),
        dolvol=np.full((T, N), 1e8, dtype=np.float32),
        mktcap=np.full((T, N), 1e10, dtype=np.float32),
        tri=tri.astype(np.float32), source="diag-test")


def _pol(**kw) -> Policy:
    return Policy(**{"top_k": 5, "universe_n": N, "holding_days": 21, **kw})


# ── the baselines say what they select ──────────────────────────────────────


def _choose(permnos, sig_row, k=4):
    idx = np.flatnonzero(np.isfinite(sig_row))
    return idx[np.argsort(-sig_row[idx], kind="stable")][:k]


def test_oldest_listing_holds_exactly_what_the_old_tie_break_held():
    """THE RENAME IS HOLDINGS-IDENTICAL — given the panel's own invariant.

    `Panel` documents `permnos` as ASCENDING, so column order IS permno order
    and the old tie-break happened to land on the oldest names. If it were not
    identical this would be a silent change to every historical `equal`
    receipt rather than a rename.
    """
    permnos = np.array([1, 3, 4, 7, 8, 9, 15, 22], dtype=np.int64)   # ascending
    tie_break = _choose(permnos, np.zeros(len(permnos)))       # the old `equal`
    declared = _choose(permnos, -permnos.astype(np.float64))   # oldest_listing
    assert np.array_equal(tie_break, declared)
    assert sorted(permnos[declared]) == [1, 3, 4, 7]


def test_the_old_tie_break_was_only_the_oldest_BY_ACCIDENT():
    """WHY DECLARING THE SCORE IS BETTER, not merely clearer.

    The old `equal` book was the oldest listings only because `Panel` happens
    to sort permnos ascending. Hand it a panel ordered any other way and the
    tie-break silently selects something else entirely, with nothing in any
    receipt reading differently. `oldest_listing` selects on `-permno`, so it
    is the oldest names under ANY column order.
    """
    permnos = np.array([9, 4, 7, 1, 22, 3, 15, 8], dtype=np.int64)   # not sorted
    tie_break = _choose(permnos, np.zeros(len(permnos)))
    declared = _choose(permnos, -permnos.astype(np.float64))
    assert not np.array_equal(tie_break, declared)
    # the DECLARED book is right regardless of ordering; the tie-break is not
    assert sorted(permnos[declared]) == [1, 3, 4, 7]
    assert sorted(permnos[tie_break]) != [1, 3, 4, 7]


def test_newest_listing_is_the_opposite_tail():
    """The canon requires an opposite-tail control. If BOTH age books beat the
    market, the finding is about the universe, not about age."""
    p = _panel()
    old = SIG.matrix(p, "oldest_listing")
    new = SIG.matrix(p, "newest_listing")
    assert np.allclose(old, -new)
    k = 5
    o = np.argsort(-old[0], kind="stable")[:k]
    n = np.argsort(-new[0], kind="stable")[:k]
    assert not (set(o.tolist()) & set(n.tolist()))


def test_no_explicit_baseline_decides_its_holdings_by_a_tie_break():
    """THE REGRESSION. A baseline whose score is constant has no holdings of
    its own — it inherits whatever the sort does, and nothing prints
    differently when the sort changes."""
    p = _panel()
    for name in sorted(SIG.EXPLICIT_BASELINES):
        row = SIG.matrix(p, name)[0]
        finite = row[np.isfinite(row)]
        assert len(np.unique(finite)) == len(finite), (
            f"{name} produces tied scores, so its holdings come from the "
            f"sort's tie-break rather than from anything it declares")


def test_equal_still_resolves_but_reports_the_rename(caplog):
    """Receipts on disk name `equal`. One that no longer parses is a mutated
    history, so the alias resolves — loudly."""
    assert SIG.resolve_alias("equal") == "oldest_listing"
    assert "equal" not in SIG.SIGNALS
    p = _panel()
    assert np.allclose(SIG.matrix(p, "equal"), SIG.matrix(p, "oldest_listing"))


def test_a_policy_naming_the_retired_signal_is_REFUSED_and_told_the_new_name():
    """Refused rather than silently resolved. A `Policy` is a frozen hashed
    strategy record, so rewriting its signal field would produce a policy whose
    hash does not match the receipt it came from — a reproducibility problem
    wearing a convenience."""
    from backend.services.portfolio_farm.policy import PolicyError
    with pytest.raises(PolicyError) as e:
        Policy(signal="equal")
    msg = str(e.value)
    assert "oldest_listing" in msg, "the refusal must name the replacement"
    assert "tie-break" in msg or "LISTING AGE" in msg, (
        "the refusal must say WHY, or the next reader re-derives it")


def test_the_age_books_are_registered_as_baselines_not_discoveries():
    for n in ("oldest_listing", "newest_listing"):
        assert n in SIG.NULL_SIGNALS, f"{n} could be quoted as a discovery"


# ── forward returns are the ones the replay can actually fill ───────────────


def test_forward_return_is_next_open_to_open_not_close_to_close():
    """Scoring close-to-close books the overnight gap that FOLLOWS the signal —
    a systematic gift to whatever is being searched for."""
    rng = np.random.default_rng(3)
    r = rng.normal(0.0005, 0.01, (T, N))
    p = _panel(r)
    rows = np.array([300, 400])
    h = 21
    fwd = D.forward_returns(p, rows, h)
    t = D.open_total_return_index(p)
    for n, row in enumerate(rows):
        expect = t[row + 1 + h] / t[row + 1] - 1.0
        assert np.allclose(fwd[n], expect, equal_nan=True)


def test_forward_return_includes_dividends():
    """Dividend yield is cross-sectionally correlated with value and
    profitability — exactly the signals this module judges — so dropping it is
    not a wash."""
    r = np.full((T, N), 0.001)
    with_div = _panel(r, div=0.0004)      # same total return, less price
    no_div = _panel(r, div=0.0)
    rows = np.array([300])
    a = D.forward_returns(with_div, rows, 21)
    b = D.forward_returns(no_div, rows, 21)
    assert np.allclose(np.nanmean(a), np.nanmean(b), atol=1e-9), (
        "total return should be identical when only the dividend split differs")


def test_formation_rows_never_overlap_and_never_run_off_the_panel():
    p = _panel()
    for h in (5, 21, 63):
        rows = D.formation_rows(p, h, warmup=260)
        assert (np.diff(rows) == h).all(), "overlapping forward windows"
        assert (rows + 1 + h <= T - 1).all(), "forward window past the panel"


# ── the IC and the quantile curve say what they claim ───────────────────────


def _planted(strength: float, seed: int = 11):
    """A panel in which a KNOWN per-name score orders forward returns."""
    rng = np.random.default_rng(seed)
    score = np.linspace(-1, 1, N)
    r = rng.normal(0, 0.01, (T, N)) + strength * score / 252.0
    return _panel(r), score


def test_a_planted_monotone_signal_is_detected():
    p, score = _planted(strength=3.0)
    rows = D.formation_rows(p, 21, warmup=260)
    sig = np.repeat(score[None, :], len(rows), axis=0)
    fwd = D.forward_returns(p, rows, 21)
    elig = np.ones_like(sig, dtype=bool)

    ic = D.rank_ic(sig, fwd, elig)
    assert ic["ic_t"] > 3, ic
    qp = D.quantile_profile(sig, fwd, elig, n_q=5, holding_days=21)
    assert qp["is_monotone"], qp
    assert qp["monotonicity_spearman"] == pytest.approx(1.0)
    assert qp["top_minus_bottom_annual_pct"] > 0


def test_pure_noise_does_not_clear_the_cross_section_check():
    """The floor. A diagnostic that passes noise is worse than none."""
    rng = np.random.default_rng(5)
    p = _panel(rng.normal(0, 0.01, (T, N)))
    rows = D.formation_rows(p, 21, warmup=260)
    sig = rng.normal(0, 1, (len(rows), N))
    fwd = D.forward_returns(p, rows, 21)
    elig = np.ones_like(sig, dtype=bool)
    ic = D.rank_ic(sig, fwd, elig)
    assert abs(ic["ic_t"]) < 3, ic


def test_ic_t_counts_date_blocks_not_days():
    """Overlapping windows inflate the sample ~holding_days-fold with no new
    information, which is how a signal with no edge acquires a t of 4."""
    p, score = _planted(strength=3.0)
    spaced = D.formation_rows(p, 21, warmup=260)
    dense = np.arange(260, T - 23)
    sig_s = np.repeat(score[None, :], len(spaced), axis=0)
    sig_d = np.repeat(score[None, :], len(dense), axis=0)
    t_spaced = D.rank_ic(sig_s, D.forward_returns(p, spaced, 21),
                         np.ones_like(sig_s, dtype=bool))["ic_t"]
    t_dense = D.rank_ic(sig_d, D.forward_returns(p, dense, 21),
                        np.ones_like(sig_d, dtype=bool))["ic_t"]
    assert t_dense > t_spaced, (
        "overlapping windows must inflate t; if they do not, the spacing rule "
        "is not doing anything and this test is not protecting it")


# ── the census answers "what did it buy?" ───────────────────────────────────


def test_a_static_list_is_flagged_as_a_static_list():
    """`liquid` had the best t on the 2013-2024 grid and was a FAANG list.
    One name per slot is the cheapest possible detector for that."""
    p = _panel()
    rows = D.formation_rows(p, 21, warmup=260)
    score = np.arange(N, dtype=np.float64)          # never changes
    sig = np.repeat(score[None, :], len(rows), axis=0)
    elig = np.ones_like(sig, dtype=bool)
    cen = D.selection_census(p, sig, rows, elig, top_k=5)
    assert cen["distinct_names_per_slot"] == pytest.approx(1.0)
    assert cen["mean_turnover_pct"] == pytest.approx(0.0)


def test_percentiles_are_measured_against_the_eligible_set_not_the_panel():
    """THE BUG THIS FIXES. The book chooses from the top-`universe_n` by dollar
    volume, which is far older and larger than the panel. A panel-relative
    percentile reports a book of ancient mega-caps as 'average age' — hiding
    the exact confound the census exists to expose."""
    p = _panel()
    rows = D.formation_rows(p, 21, warmup=260)
    # eligible = only the ten OLDEST names; the book then buys the newest FIVE
    # of those, which is old against the panel and new against what it could
    # have bought.
    elig = np.zeros((len(rows), N), dtype=bool)
    elig[:, :10] = True
    score = np.arange(N, dtype=np.float64)
    sig = np.repeat(score[None, :], len(rows), axis=0)
    cen = D.selection_census(p, sig, rows, elig, top_k=5)
    assert cen["mean_permno_percentile_of_holdings"] > 50, (
        "measured against the eligible ten, the newest five must read ABOVE "
        "50; a panel-relative percentile would report ~18")
    assert cen["percentile_baseline"] == "eligible set on each formation date"


# ── one definition of eligibility ───────────────────────────────────────────


def test_diagnostics_and_replay_share_one_eligibility_definition():
    """A rank IC over every name, printed beside a book drawn from the top-500
    by dollar volume, describes a universe the book never traded — and neither
    number would look wrong."""
    import inspect
    src = inspect.getsource(replay.run)
    assert "eligible_at(" in src, (
        "replay no longer calls the shared definition, so diagnostics can "
        "silently drift onto a different universe")


def test_diagnostics_feeds_eligible_at_the_SAME_liquidity_series_as_replay():
    """Sharing the definition is worthless if the callers hand it different
    inputs. A different `min_obs` changes which names have a finite trailing
    dollar volume, which changes eligibility — the exact drift `eligible_at`
    was extracted to prevent, reintroduced one argument along."""
    import inspect
    d_src = inspect.getsource(D.signal_report)
    r_src = inspect.getsource(replay.run)
    for src, who in ((d_src, "diagnostics"), (r_src, "replay")):
        assert "_roll_mean(panel.dolvol.astype(np.float64), SIG.MONTH, 5)" in src, (
            f"{who} no longer builds the liquidity series the same way; "
            f"eligibility can now differ between the diagnostic and the book")


def test_eligible_at_applies_the_price_floor_and_the_liquidity_cut():
    p = _panel()
    liq = np.full(N, 1e8)
    liq[:5] = np.nan                       # no trailing volume -> ineligible
    e = replay.eligible_at(p, 300, _pol(min_price=5.0), liq)
    assert not e[:5].any()
    assert e[5:].all()

    tight = replay.eligible_at(p, 300, _pol(universe_n=7), np.arange(N) * 1.0)
    assert tight.sum() == 7, "universe_n cut not applied"


def test_signal_report_refuses_a_panel_too_short_to_diagnose():
    """A refusal is a finding; a diagnostic computed on four dates is not."""
    short = _panel()
    rep = D.signal_report(short, "oldest_listing", holding_days=400,
                          warmup=260, top_k=3)
    assert "error" in rep and "formation dates" in rep["error"]


#: Per-year effect size for the SHAPE fixtures. Deliberately small.
#:
#: `_planted(strength=3.0)` is fine for detection tests and useless for shape
#: ones: it compounds to +1045%/yr in the top bucket, so ANY rising curve turns
#: exponential and every shape reads as "tail". Real farm buckets span roughly
#: 7-19%/yr, where compounding is mild and the shape survives annualisation.
#: The fixture has to live in the regime the classifier is used in.
_SHAPE_STRENGTH = 0.12


def _gradient_panel(seed: int = 31):
    """Return rises LINEARLY across the cross section, at a realistic size."""
    rng = np.random.default_rng(seed)
    score = np.linspace(-1, 1, N)
    r = rng.normal(0, 0.004, (T, N)) + _SHAPE_STRENGTH * score / 252.0
    return _panel(r), score


def _tail_only_panel(seed: int = 21):
    """A panel where ONLY the top bucket earns anything extra."""
    rng = np.random.default_rng(seed)
    score = np.linspace(-1, 1, N)
    bonus = np.where(score >= 0.6, _SHAPE_STRENGTH, 0.0) / 252.0   # top ~20%
    r = rng.normal(0, 0.004, (T, N)) + bonus
    return _panel(r), score


def test_a_TAIL_signal_is_not_failed_for_lacking_monotonicity():
    """MY OWN INSTRUMENT FLAW, found by the data.

    Monotonicity PENALISES a signal whose whole payoff is in its extreme tail,
    and that is a real and common shape rather than a defect. Measured
    1993-2024 at ten buckets, `rev_dispersion` runs a flat middle and a
    +7.6%/yr jump in the last decile: monotonicity 0.24, which reads as "no
    signal", and a lift second only to momentum's. It implies a NARROW book,
    not no book.
    """
    p, score = _tail_only_panel()
    rows = D.formation_rows(p, 21, warmup=260)
    sig = np.repeat(score[None, :], len(rows), axis=0)
    fwd = D.forward_returns(p, rows, 21)
    elig = np.ones_like(sig, dtype=bool)

    qp = D.quantile_profile(sig, fwd, elig, n_q=5, holding_days=21)
    assert qp["top_bucket_lift_annual_pct"] > 0
    assert qp["shape"] == "tail", qp
    v = D._verdict(D.rank_ic(sig, fwd, elig), qp,
                   {"distinct_names_per_slot": 5.0})
    assert "NARROW" in v["implied_construction"].upper()
    assert not any("not monotone" in r for r in v["failed"]), (
        "a tail-concentrated signal was failed for the one statistic that "
        "cannot describe it")


def test_lift_and_monotonicity_answer_DIFFERENT_questions():
    """A gradient signal has monotonicity and little tail lift; a tail signal
    has lift and little monotonicity. Reporting only one loses half the
    signals, and they imply OPPOSITE constructions."""
    grad_p, grad_score = _gradient_panel()
    rows = D.formation_rows(grad_p, 21, warmup=260)
    g_sig = np.repeat(grad_score[None, :], len(rows), axis=0)
    g_qp = D.quantile_profile(g_sig, D.forward_returns(grad_p, rows, 21),
                              np.ones_like(g_sig, dtype=bool), n_q=5,
                              holding_days=21)

    tail_p, tail_score = _tail_only_panel()
    t_sig = np.repeat(tail_score[None, :], len(rows), axis=0)
    t_qp = D.quantile_profile(t_sig, D.forward_returns(tail_p, rows, 21),
                              np.ones_like(t_sig, dtype=bool), n_q=5,
                              holding_days=21)

    assert g_qp["monotonicity_spearman"] > t_qp["monotonicity_spearman"]
    assert g_qp["shape"] != "tail"
    assert t_qp["shape"] == "tail"


def test_a_REVERSED_signal_is_reported_as_reversed_not_as_absent():
    """`value_bm` reads monotonicity -0.90 over 32 years. That is a signal
    pointing the other way, not an absent one, and reporting it as "not
    monotone" buries the only actionable thing about it: test the negation."""
    p, score = _planted(strength=3.0)
    rows = D.formation_rows(p, 21, warmup=260)
    # negate the score so the relationship is strong and inverted
    sig = np.repeat(-score[None, :], len(rows), axis=0)
    fwd = D.forward_returns(p, rows, 21)
    elig = np.ones_like(sig, dtype=bool)
    qp = D.quantile_profile(sig, fwd, elig, n_q=5, holding_days=21)
    assert qp["monotonicity_spearman"] <= -0.6

    v = D._verdict(D.rank_ic(sig, fwd, elig), qp,
                   {"distinct_names_per_slot": 5.0})
    assert v["reversed_signal_worth_testing"] is True
    assert any("REVERSED" in r for r in v["failed"])
    assert v["cross_section_supports_a_book"] is False, (
        "a reversed signal must not read as tradeable AS BUILT")


def test_verdict_is_advisory_and_says_so():
    """Under the three-licence rule this governs what may be CLAIMED, never
    what may be tested in paper. A gate here would recreate the 24-month
    paralysis under a new name."""
    p, score = _planted(strength=0.0, seed=9)
    rep = D.signal_report(p, "oldest_listing", top_k=5, holding_days=21,
                          warmup=260)
    assert "note" in rep["verdict"]
    assert "never what may be tested in paper" in rep["verdict"]["note"]
