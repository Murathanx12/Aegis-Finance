"""Temporal lineage: does a training label reach into the evaluation period?

WHY THIS EXISTS (2026-08-16, from N9)
=====================================
N9 downloaded prices to 2026, computed `fwd_20` and `fwd_60` on the full
series, and only then sliced the training frame at `TRAIN_END = 2015-12-31`.
The last twenty training rows therefore carry forward returns built from up to
twenty trading days of **2016** — the period the rules were then evaluated on.
The defect was found by reproducing N9's download window and getting exactly
582 rules where a cutoff-respecting build gets 598.

The size of that particular leak is small. The class is not, and it is
invisible at the call site: `df.loc[:TRAIN_END]` reads like a temporal split
and is one *for the features*. The label was already built.

WHAT THIS MODULE REFUSES, AND ON WHAT EVIDENCE
==============================================
A training row is admissible only when the last timestamp its LABEL depends on
falls strictly before the first timestamp the evaluation period can see:

    label_end_ts[i]  <  first_test_information_ts

Four timestamps, all explicit, none of them an integer embargo:

    feature_cutoff_ts   last bar a feature for row i may be built from
    label_start_ts      first bar the label for row i depends on
    label_end_ts        last bar the label for row i depends on
    split_cutoff_ts     first bar the evaluation period may see

**The guard derives `label_end_ts` from the index it is given.** It does not
accept a declared one, because a guard whose inputs are on the honour system is
not a guard — R13 asked authors for "independent episodes", was handed days,
and passed an unpowered design. `verify_declared` exists for the case where a
caller has its own array: it compares against the derived one and refuses on
mismatch rather than believing it.

PURGE PER HORIZON, NEVER GLOBALLY
=================================
A 20-day label and a 60-day label do not have the same admissible training set,
and a single "20-day embargo" constant applied to both leaks 40 days of the
longer one. `check_split` therefore takes a *set* of `LabelWindow`s and returns
one mask per window; there is no API that produces a single embargo for a frame
with more than one horizon.

Horizons are counted in ROWS of the supplied index, not calendar days, because
the label is built by `shift(-H)` on a trading-day series. Twenty calendar days
after a Friday in December is not twenty bars.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


class LeakageRefusal(RuntimeError):
    """A training row's label reaches into the evaluation information period."""


@dataclass(frozen=True)
class LabelWindow:
    """One label column's information geometry.

    `horizon_rows` is how many bars forward the label reads — the `H` in
    `px.shift(-H) / px - 1`. `feature_lag_rows` is how many bars BACK the
    features are read; it does not affect leakage across the split cutoff (a
    lag can only move information earlier) but it is carried so the four
    timestamps a caller can print are all derived in one place.
    """

    name: str
    horizon_rows: int
    feature_lag_rows: int = 1

    def __post_init__(self) -> None:
        if int(self.horizon_rows) < 0:
            raise ValueError(f"{self.name}: horizon_rows must be >= 0")
        if int(self.feature_lag_rows) < 0:
            raise ValueError(f"{self.name}: feature_lag_rows must be >= 0")


@dataclass(frozen=True)
class WindowReport:
    """What one label column does to one split."""

    window: LabelWindow
    n_rows_before_cutoff: int
    n_admissible: int
    n_leaking: int
    #: How far past the split the worst offending label reaches, in bars.
    max_reach_rows: int
    max_reach_ts: str | None
    first_test_information_ts: str | None
    #: Rows whose label never resolves (the window runs off the end of the
    #: series). Not a leak — but a row with a NaN label is not a training row,
    #: and counting it as one is how `n` gets inflated a second way.
    n_unresolved: int

    @property
    def clean(self) -> bool:
        return self.n_leaking == 0

    def as_dict(self) -> dict:
        return {
            "label": self.window.name,
            "horizon_rows": self.window.horizon_rows,
            "feature_lag_rows": self.window.feature_lag_rows,
            "n_rows_before_cutoff": self.n_rows_before_cutoff,
            "n_admissible": self.n_admissible,
            "n_leaking": self.n_leaking,
            "n_unresolved": self.n_unresolved,
            "max_reach_rows": self.max_reach_rows,
            "max_reach_ts": self.max_reach_ts,
            "first_test_information_ts": self.first_test_information_ts,
            "clean": self.clean,
        }


@dataclass(frozen=True)
class LineageReport:
    """Every label window's verdict on one split, plus the joint one."""

    split_cutoff_ts: str
    n_rows: int
    windows: tuple[WindowReport, ...] = field(default_factory=tuple)

    @property
    def clean(self) -> bool:
        return all(w.clean for w in self.windows)

    @property
    def n_leaking(self) -> int:
        return sum(w.n_leaking for w in self.windows)

    def as_dict(self) -> dict:
        return {
            "split_cutoff_ts": self.split_cutoff_ts,
            "n_rows": self.n_rows,
            "clean": self.clean,
            "n_leaking_total": self.n_leaking,
            "windows": [w.as_dict() for w in self.windows],
        }

    def why(self) -> str:
        if self.clean:
            return (f"lineage clean at {self.split_cutoff_ts}: no training "
                    f"label reaches the evaluation period "
                    f"({', '.join(w.window.name for w in self.windows)})")
        bad = [w for w in self.windows if not w.clean]
        parts = [
            (f"`{w.window.name}` (H={w.window.horizon_rows}): {w.n_leaking} "
             f"training rows whose label reads up to {w.max_reach_rows} bars "
             f"past the cutoff, to {w.max_reach_ts}")
            for w in bad
        ]
        return (
            f"TEMPORAL LINEAGE REFUSED at split {self.split_cutoff_ts}. "
            + "; ".join(parts)
            + ". A label that ends at or after the first bar the evaluation "
              "period can see was built from evaluation data, whatever the "
              "feature timestamps say. Purge with `admissible_mask` — per "
              "horizon, because a 20-bar label and a 60-bar label do not have "
              "the same admissible training set."
        )


def _as_str(ts) -> str:
    """Timestamps compare and print as ISO strings, so the guard is calendar-free."""
    return str(ts)[:19] if not isinstance(ts, str) else ts


def _positions_before(index: Sequence, cutoff) -> int:
    """How many rows of `index` fall at or before `cutoff` (index must be sorted)."""
    c = _as_str(cutoff)
    n = 0
    for ts in index:
        if _as_str(ts) <= c:
            n += 1
        else:
            break
    return n


def label_timestamps(index: Sequence, window: LabelWindow) -> dict:
    """The four timestamps, DERIVED from the index rather than declared.

    Returns parallel lists of the same length as `index`. `label_end_ts[i]` is
    `None` where the window runs off the end of the series: that row's label
    does not exist, and calling it a training row is a different error from
    leaking.
    """
    idx = [_as_str(t) for t in index]
    n = len(idx)
    if any(idx[i] > idx[i + 1] for i in range(n - 1)):
        raise LeakageRefusal(
            "index is not sorted ascending; a lineage check on an unsorted "
            "index would compare the wrong bars and report clean. Sort first.")
    H = int(window.horizon_rows)
    lag = int(window.feature_lag_rows)
    feature_cutoff, label_start, label_end = [], [], []
    for i in range(n):
        feature_cutoff.append(idx[max(i - lag, 0)] if lag <= i else None)
        label_start.append(idx[i])
        j = i + H
        label_end.append(idx[j] if j < n else None)
    return {"feature_cutoff_ts": feature_cutoff,
            "label_start_ts": label_start,
            "label_end_ts": label_end}


def _first_test_ts(idx: list[str], split_cutoff, eval_start) -> str | None:
    """The first bar the EVALUATION period can see.

    Two timestamps, not one, and conflating them is its own bug: `split_cutoff`
    is the last bar training owns, `eval_start` is the first bar evaluation
    reads. An embargoed design puts a gap between them on purpose, and checking
    a label against the bar after the cutoff would score that design as if the
    embargo bought nothing. Defaults to the next bar only when there is no gap
    to declare.
    """
    if eval_start is not None:
        return _as_str(eval_start)
    n_before = _positions_before(idx, split_cutoff)
    return idx[n_before] if n_before < len(idx) else None


def admissible_mask(index: Sequence, *, split_cutoff, window: LabelWindow,
                    eval_start=None) -> list[bool]:
    """Training rows whose label ends strictly before evaluation information.

    `split_cutoff` is the last bar the TRAINING period owns; `eval_start` is
    the first bar the evaluation period reads, which defaults to the next bar
    in `index` when the design declares no embargo gap. A label ending ON
    `eval_start` is already contaminated, hence the strict inequality.

    Rows after the cutoff are False — this returns a TRAINING mask, and a
    caller that wants the evaluation rows takes the complement of
    `index <= split_cutoff`, which is a different question.
    """
    idx = [_as_str(t) for t in index]
    ts = label_timestamps(index, window)
    n_before = _positions_before(idx, split_cutoff)
    first_test = _first_test_ts(idx, split_cutoff, eval_start)
    out = []
    for i in range(len(idx)):
        if i >= n_before:
            out.append(False)
            continue
        end = ts["label_end_ts"][i]
        if end is None:                      # label never resolves
            out.append(False)
        elif first_test is None:             # nothing after the cutoff at all
            out.append(True)
        else:
            out.append(end < first_test)
    return out


def check_split(index: Sequence, *, split_cutoff,
                windows: Sequence[LabelWindow],
                eval_start=None) -> LineageReport:
    """Does any training label reach the evaluation period, per window?

    Reports rather than raises, so a caller can print the chain; `assert_clean`
    raises on the same condition so a caller cannot ignore it (canon: the exit
    code IS the guard).
    """
    if not windows:
        raise ValueError("check_split needs at least one LabelWindow; a frame "
                         "with no declared label has no lineage to check, and "
                         "silently passing it is the failure this module is for")
    idx = [_as_str(t) for t in index]
    n_before = _positions_before(idx, split_cutoff)
    first_test = _first_test_ts(idx, split_cutoff, eval_start)
    #: Position of the first evaluation bar, so "how far past" is measured from
    #: the boundary the design actually declared rather than from the cutoff.
    first_test_pos = (_positions_before(idx, first_test) - 1
                      if first_test is not None else len(idx))

    reports = []
    for w in windows:
        ts = label_timestamps(index, w)
        leaking = 0
        unresolved = 0
        worst_rows, worst_ts = 0, None
        for i in range(n_before):
            end = ts["label_end_ts"][i]
            if end is None:
                unresolved += 1
                continue
            if first_test is not None and end >= first_test:
                leaking += 1
                reach = (i + w.horizon_rows) - first_test_pos + 1
                if reach > worst_rows:
                    worst_rows, worst_ts = reach, end
        reports.append(WindowReport(
            window=w,
            n_rows_before_cutoff=n_before,
            n_admissible=sum(admissible_mask(idx, split_cutoff=split_cutoff,
                                             window=w, eval_start=eval_start)),
            n_leaking=leaking,
            max_reach_rows=worst_rows,
            max_reach_ts=worst_ts,
            first_test_information_ts=first_test,
            n_unresolved=unresolved,
        ))
    return LineageReport(split_cutoff_ts=_as_str(split_cutoff),
                         n_rows=len(idx), windows=tuple(reports))


def assert_clean(index: Sequence, *, split_cutoff,
                 windows: Sequence[LabelWindow],
                 eval_start=None) -> LineageReport:
    """`check_split`, but a leak stops the run."""
    rep = check_split(index, split_cutoff=split_cutoff, windows=windows,
                      eval_start=eval_start)
    if not rep.clean:
        raise LeakageRefusal(rep.why())
    return rep


def verify_declared(index: Sequence, window: LabelWindow,
                    declared_label_end_ts: Sequence) -> None:
    """Refuse a caller-supplied `label_end_ts` that disagrees with the index.

    The point of the module is that the guard computes what it checks. This is
    the escape hatch for a caller whose labels are built somewhere else — and
    it is an escape hatch that CANNOT be used to declare a cleaner lineage than
    the data supports, because disagreement is a refusal rather than a warning.
    """
    derived = label_timestamps(index, window)["label_end_ts"]
    dec = [None if d is None else _as_str(d) for d in declared_label_end_ts]
    if len(dec) != len(derived):
        raise LeakageRefusal(
            f"{window.name}: declared label_end_ts has {len(dec)} entries for "
            f"{len(derived)} index rows — the two describe different frames")
    for i, (a, b) in enumerate(zip(derived, dec)):
        if a != b:
            raise LeakageRefusal(
                f"{window.name}: declared label_end_ts[{i}] = {b!r} but the "
                f"index says the {window.horizon_rows}-bar window ends at "
                f"{a!r}. A declared lineage that disagrees with the data is "
                f"refused, not trusted.")


def purge_report_line(rep: LineageReport) -> str:
    """One line per window, for a script that must print what it purged."""
    return " | ".join(
        f"{w.window.name}: {w.n_admissible}/{w.n_rows_before_cutoff} admissible"
        f" (-{w.n_rows_before_cutoff - w.n_admissible})"
        for w in rep.windows)
