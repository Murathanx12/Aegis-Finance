"""The temporal lineage guard, including the exact defect it was built from.

The first test reproduces N9's leak in miniature: build the label on the full
series, slice the features at the cutoff, and check whether anything notices.
Without the guard nothing does — which is the whole point, and is why that case
is asserted as a REFUSAL rather than as a passing check.
"""

from __future__ import annotations

import pytest

from backend.services.research_gym import lineage as LG


def _days(n: int, start: int = 1) -> list[str]:
    """A sorted daily index. Dates only — the guard compares strings."""
    out = []
    y, m, d = 2015, 1, start
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}-{d:02d}")
        d += 1
        if d > 28:
            d = 1
            m += 1
            if m > 12:
                m = 1
                y += 1
    return out


# ── the defect, reproduced ──────────────────────────────────────────────────

def test_n9s_leak_is_refused():
    """20 rows before a cutoff carry labels built from 20 rows after it."""
    idx = _days(200)
    cutoff = idx[99]
    rep = LG.check_split(idx, split_cutoff=cutoff,
                         windows=[LG.LabelWindow("fwd_20", 20)])
    assert not rep.clean
    (w,) = rep.windows
    assert w.n_rows_before_cutoff == 100
    # Rows 80..99 have label_end at 100..119, all at or past the first test bar.
    assert w.n_leaking == 20
    assert w.n_admissible == 80
    assert w.max_reach_rows == 20
    assert w.max_reach_ts == idx[119]
    with pytest.raises(LG.LeakageRefusal):
        LG.assert_clean(idx, split_cutoff=cutoff,
                        windows=[LG.LabelWindow("fwd_20", 20)])


def test_every_kept_row_resolves_before_the_evaluation_period_begins():
    """The fix has to actually fix it — not merely report a smaller number.

    Checked against the ORIGINAL split's first test bar. Re-running
    `check_split` with the last kept row as the cutoff would be a *different*
    and stricter split, and would fail for a reason that has nothing to do with
    whether the purge worked.
    """
    idx = _days(200)
    cutoff = idx[99]
    w = LG.LabelWindow("fwd_20", 20)
    mask = LG.admissible_mask(idx, split_cutoff=cutoff, window=w)
    ends = LG.label_timestamps(idx, w)["label_end_ts"]
    first_test = idx[100]
    assert sum(mask) == 80
    assert all(ends[i] is not None and ends[i] < first_test
               for i, k in enumerate(mask) if k)
    # ... and the rows it dropped are exactly the ones that did not.
    dropped = [i for i in range(100) if not mask[i]]
    assert dropped == list(range(80, 100))


# ── purge is per horizon, and that is not a stylistic preference ────────────

def test_two_horizons_do_not_share_an_admissible_set():
    idx = _days(400)
    cutoff = idx[199]
    rep = LG.check_split(
        idx, split_cutoff=cutoff,
        windows=[LG.LabelWindow("fwd_20", 20), LG.LabelWindow("fwd_60", 60)])
    a, b = rep.windows
    assert a.n_admissible == 180
    assert b.n_admissible == 140
    assert a.n_admissible != b.n_admissible


def test_a_20_day_embargo_still_leaks_the_60_day_label():
    """The mutation control for 'purge per horizon'.

    Keep the rows a 20-bar purge would keep, then ask how many of THOSE still
    have a 60-bar label reaching into the evaluation period. If one global
    embargo were adequate the answer would be zero.
    """
    idx = _days(400)
    cutoff = idx[199]
    short = LG.LabelWindow("fwd_20", 20)
    long_ = LG.LabelWindow("fwd_60", 60)
    kept = LG.admissible_mask(idx, split_cutoff=cutoff, window=short)
    ends60 = LG.label_timestamps(idx, long_)["label_end_ts"]
    first_test = idx[200]
    still_leaking = [i for i, k in enumerate(kept)
                     if k and ends60[i] >= first_test]
    # Rows 140..179 are admissible at H=20 and read to bar 200..239 at H=60.
    assert still_leaking == list(range(140, 180))
    assert len(still_leaking) == 40


# ── the cutoff and the evaluation start are two timestamps ─────────────────

def test_an_embargo_gap_is_credited_when_declared():
    """A design that leaves a gap must not be scored as if it had not."""
    idx = _days(200)
    w = LG.LabelWindow("fwd_20", 20)
    # Train owns up to bar 79; evaluation begins at bar 100. The 20 bars in
    # between are the embargo, and they are exactly enough.
    rep = LG.check_split(idx, split_cutoff=idx[79], eval_start=idx[100],
                         windows=[w])
    assert rep.clean, rep.why()
    assert rep.windows[0].n_admissible == 80


def test_an_embargo_one_bar_short_still_leaks_exactly_one_row():
    idx = _days(200)
    w = LG.LabelWindow("fwd_20", 20)
    rep = LG.check_split(idx, split_cutoff=idx[80], eval_start=idx[100],
                         windows=[w])
    assert not rep.clean
    assert rep.windows[0].n_leaking == 1
    assert rep.windows[0].max_reach_rows == 1


def test_reach_is_measured_from_the_evaluation_start_not_the_cutoff():
    """The bug this parameter fixed: scoring the gap as if it were zero.

    Without `eval_start` the guard treats the bar after the cutoff as the first
    evaluation bar, so an embargoed design reports its full horizon as leaking.
    """
    idx = _days(200)
    w = LG.LabelWindow("fwd_20", 20)
    naive = LG.check_split(idx, split_cutoff=idx[79], windows=[w])
    honest = LG.check_split(idx, split_cutoff=idx[79], eval_start=idx[100],
                            windows=[w])
    assert naive.windows[0].n_leaking == 20      # the embargo bought nothing
    assert honest.windows[0].n_leaking == 0      # ... except it did


# ── the timestamps are derived, not believed ───────────────────────────────

def test_declared_lineage_that_disagrees_with_the_index_is_refused():
    idx = _days(50)
    w = LG.LabelWindow("fwd_5", 5)
    derived = LG.label_timestamps(idx, w)["label_end_ts"]
    LG.verify_declared(idx, w, derived)          # agreement is silent
    lying = list(derived)
    lying[10] = idx[10]                          # "the label ends where it starts"
    with pytest.raises(LG.LeakageRefusal, match="refused, not trusted"):
        LG.verify_declared(idx, w, lying)


def test_a_wrong_length_declaration_is_refused():
    idx = _days(50)
    w = LG.LabelWindow("fwd_5", 5)
    with pytest.raises(LG.LeakageRefusal, match="different frames"):
        LG.verify_declared(idx, w, ["2015-01-01"] * 10)


def test_an_unsorted_index_is_refused_rather_than_reported_clean():
    idx = _days(50)
    idx[10], idx[11] = idx[11], idx[10]
    with pytest.raises(LG.LeakageRefusal, match="not sorted"):
        LG.check_split(idx, split_cutoff=idx[20],
                       windows=[LG.LabelWindow("fwd_5", 5)])


def test_horizons_are_counted_in_bars_not_calendar_days():
    """A gap in the index must not move the label end by calendar arithmetic."""
    idx = ["2015-01-01", "2015-01-02", "2015-06-01", "2015-06-02", "2015-06-03"]
    ts = LG.label_timestamps(idx, LG.LabelWindow("fwd_2", 2))
    assert ts["label_end_ts"][0] == "2015-06-01"
    assert ts["label_end_ts"][3] is None          # runs off the end


# ── the ways a check can pass for the wrong reason ─────────────────────────

def test_unresolved_labels_are_counted_separately_from_leaks():
    idx = _days(30)
    rep = LG.check_split(idx, split_cutoff=idx[29],
                         windows=[LG.LabelWindow("fwd_10", 10)])
    (w,) = rep.windows
    assert w.n_leaking == 0                      # nothing after the cutoff
    assert w.n_unresolved == 10                  # but ten labels do not exist
    assert w.n_admissible == 20


def test_a_zero_horizon_label_never_leaks():
    idx = _days(50)
    rep = LG.check_split(idx, split_cutoff=idx[24],
                         windows=[LG.LabelWindow("contemporaneous", 0)])
    assert rep.clean
    assert rep.windows[0].n_admissible == 25


def test_no_declared_window_is_a_refusal_not_a_pass():
    with pytest.raises(ValueError, match="at least one LabelWindow"):
        LG.check_split(_days(10), split_cutoff="2015-01-05", windows=[])


def test_negative_horizon_is_rejected_at_construction():
    with pytest.raises(ValueError):
        LG.LabelWindow("backwards", -1)


def test_the_refusal_message_names_the_column_and_the_reach():
    idx = _days(200)
    rep = LG.check_split(idx, split_cutoff=idx[99],
                         windows=[LG.LabelWindow("fwd_20", 20)])
    why = rep.why()
    assert "fwd_20" in why and "20 bars past the cutoff" in why
    assert idx[119] in why
