"""SIC 9999 is UNCLASSIFIED, never "Public Administration". Pinned forever.

Until 2026-09-03 `tracker_ibes_backtest.SIC_DIVISIONS` sent the whole 9000-9999
range to "Public Administration". CRSP's 9999 means NONCLASSIFIABLE -- and it is
98.8% of that range in this panel (3,580 of 3,625 filtered name-rows in
`crsp__stocknames.parquet`), so 22.5% of the training panel's rows carried an
industry's name when the truth was "we do not know". Three downstream files had
each grown a local workaround; the fix now lives at the source and this file is
the pin that stops the mislabel from quietly coming back in a refactor.

The tests here are cheap on purpose: a mapping table and a pure function, no
data, no network. What they buy is expensive: any future edit that folds 9999
back into an industry label -- or that renames the honest label without telling
the downstream readers that key on it -- goes red instead of silently
re-contaminating every sector-neutral construction built on the panel.
"""

from __future__ import annotations

from scripts import tracker_ibes_backtest as tib


def test_9999_is_unclassified() -> None:
    """The code that means "CRSP could not classify this" must say so."""
    assert tib.sic_division(9999) == tib.SIC_UNCLASSIFIED
    assert tib.sic_division(9999) != "Public Administration"


def test_the_whole_nonclassifiable_range_is_unclassified() -> None:
    """SIC 9900-9999 is the standard's own Nonclassifiable Establishments
    range. 9990 appears in this CRSP extract (12 name-rows); the 9995
    placeholder some vendors use does not appear but must land honestly if it
    ever does. No code in the range may read as an industry."""
    for code in range(9900, 10000):
        assert tib.sic_division(code) == tib.SIC_UNCLASSIFIED, code


def test_genuine_public_administration_keeps_its_label() -> None:
    """The fix must not overcorrect: real Division J codes (9100-9729; every
    one observed in this extract sits at 9199-9711) are a known sector and
    relabelling THEM as unknown would be the original sin mirrored."""
    for code in (9100, 9199, 9511, 9711, 9721):
        assert tib.sic_division(code) == "Public Administration", code


def test_no_division_entry_can_reach_9999_with_an_industry_name() -> None:
    """Pin the TABLE, not just the function: no (lo, hi, name) entry other
    than the unclassified one may cover 9999, so a reordering or an edit to
    `sic_division`'s scan cannot resurrect the mislabel."""
    for lo, hi, name in tib.SIC_DIVISIONS:
        if lo <= 9999 <= hi:
            assert name == tib.SIC_UNCLASSIFIED, (lo, hi, name)
        if name == "Public Administration":
            assert hi <= 9899, (lo, hi, name)


def test_missing_code_stays_unknown_and_distinct_from_unclassified() -> None:
    """"CRSP said nonclassifiable" (9999) and "no code at all" (CRSP stamps 0
    on missing; unparseable input) have different provenance. Both mean the
    sector is not known, but folding them into one label at the source would
    destroy the distinction before anyone downstream could choose to keep it."""
    for bad in (None, "not-a-code", float("nan"), 0):
        assert tib.sic_division(bad) == "_UNKNOWN", bad
    assert tib.SIC_UNCLASSIFIED != "_UNKNOWN"


def test_downstream_readers_key_on_the_source_label() -> None:
    """`scenario_bridge` and `learner_states_run` detect panel vintage by the
    presence of the post-fix label. They pin the STRING rather than importing
    this module at their own import time, so this test is the coupling: rename
    the label at the source and the readers go blind -- red here first."""
    from scripts import learner_states_run as lsr
    from scripts import scenario_bridge as sb
    assert sb.SOURCE_UNCLASSIFIED_LABEL == tib.SIC_UNCLASSIFIED
    assert lsr.SOURCE_UNCLASSIFIED_LABEL == tib.SIC_UNCLASSIFIED
