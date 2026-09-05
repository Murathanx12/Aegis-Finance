"""A SUPERSEDED family may not vote — in any state, tally, verdict or export.

`e6ce604` stopped a RETRACTED experiment from voting, and it did so at ONE call
site: the filter lives inside `snapshot()`. That is enough for `snapshot()` and
for nothing else. `state_of` is public and takes raw rows; `read_all` is public
and returns the whole store; the registry export written for B6 §4 is a second
consumer, and had it called `read_all()` and `state_of()` the way `snapshot()`
used to, the leaked W7 archetypes would have walked straight into
`signal_registry.yaml` with nothing going red.

So these tests pin the PROPERTY rather than the function:

    the same fixture votes without the rule and does not vote with it,

on every path that derives a state — `state_of`, `snapshot` and
`registry_rows`. The first assertion of each pair is the pre-fix behaviour, and
it is asserted, not assumed: if the fixture were too weak to reach SUPPORTED,
the second assertion would pass for the wrong reason and this file would be a
green dot proving nothing. That failure mode has a name in this repo — S47, a
test that proved a guard fires and had never made it fire.

Nothing here touches the real 65 MB store; every test builds its own.
"""
from __future__ import annotations

import json

import pytest

from learner import evidence_memory as EM


# --------------------------------------------------------------------- fixture

def _clearing_row(family: str, cell: str, utc: str, *, variant: str,
                  dsr: float, spa_p: float = 0.01, pbo: float = 0.1) -> dict:
    """One observation that WOULD be called a result on its own.

    Distinct `variant` and distinct numbers, because `evidence_key` collapses a
    deterministic job re-run into a single observation and two identical rows
    would never promote anything.
    """
    return {
        "utc": utc, "version": EM.VERSION, "family_id": family, "cell": cell,
        "job": "TEST", "run": 1, "variant": variant,
        "n_months": 240, "sharpe": None,
        "dsr": dsr, "spa_p": spa_p, "pbo": pbo,
        "verdict": "NOVEL", "powered": True,
        "years_needed_for_t2": 4.0, "years_observed": 20.0,
        "eras": {"eras_with_a_positive_mean": 3, "eras_measured": 3,
                 "holds_in_2_of_3": True, "same_sign_in_2_of_3": True,
                 "1999-2007": {"months": 48, "mean_pct": 1.0, "t": 2.4, "sign": 1},
                 "2008-2015": {"months": 96, "mean_pct": 1.1, "t": 2.6, "sign": 1},
                 "2016-2024": {"months": 96, "mean_pct": 1.2, "t": 2.2, "sign": 1}},
        "gross_beats_market": True, "net_beats_market": True,
        "screen_cleared": None, "controlled_t": None, "holm_p": None,
        "note": "test fixture",
    }


FAMILY = "test-family-leaked"
CELL = "arm|10bps"
ROWS = [
    _clearing_row(FAMILY, CELL, "2026-09-01T00:00:00+00:00", variant="a", dsr=0.99),
    _clearing_row(FAMILY, CELL, "2026-09-01T01:00:00+00:00", variant="b", dsr=0.98),
]
RULE = {"utc": "2026-09-02T00:00:00+00:00", "family_id": FAMILY,
        "before_utc": "2026-09-02T00:00:00+00:00", "cell_prefix": None,
        "why": "the control pool leaked; this instrument could not have seen it"}


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """A private store, so no test can read or write the real 65 MB memory."""
    monkeypatch.setattr(EM, "STORE_DIR", tmp_path)
    monkeypatch.setattr(EM, "STORE", tmp_path / "evidence_memory.jsonl")
    monkeypatch.setattr(EM, "SUPERSESSIONS", tmp_path / "supersessions.jsonl")
    monkeypatch.setattr(EM, "STATE_SNAPSHOT", tmp_path / "state.json")
    (tmp_path / "evidence_memory.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in ROWS), encoding="utf-8")
    return tmp_path


def _write_rule(store_dir, rule=RULE):
    (store_dir / "supersessions.jsonl").write_text(
        json.dumps(rule) + "\n", encoding="utf-8")


# ------------------------------------------------- 1. the state, both directions

def test_the_fixture_can_actually_vote():
    """THE RED PROOF. Without the rule these two observations reach SUPPORTED.

    This is the pre-fix behaviour, stated as an assertion. Every "cannot vote"
    test below is only meaningful because this one passes: a fixture that could
    not promote itself would make them all vacuous.
    """
    st = EM.state_of(list(ROWS))
    assert st["state"] == "SUPPORTED", st
    assert st["passes_clearing_the_bar"] == 2, st


def test_state_of_refuses_a_superseded_observation():
    """The same rows, with the rule, do not vote at all."""
    st = EM.state_of(list(ROWS), rules=[RULE])
    assert st["state"] == "IDEA", st
    assert st["why"] == "never observed", st
    assert st["passes_clearing_the_bar"] == 0, st


def test_snapshot_excludes_the_superseded_family(store):
    """`snapshot()` — the path e6ce604 fixed — still holds, and says how much
    it declined and why."""
    before = EM.snapshot()
    assert before["state_counts"].get("SUPPORTED") == 1, before["state_counts"]
    assert FAMILY in before["families"]

    _write_rule(store)
    after = EM.snapshot()
    assert after["state_counts"].get("SUPPORTED") is None, after["state_counts"]
    assert after["cells"] == 0
    assert FAMILY not in after["families"]
    assert after["observations"] == 0
    assert after["observations_on_file"] == 2
    assert sum(after["observations_superseded"].values()) == 2
    assert FAMILY in after["superseded_families_barred_from_export"]


def test_the_registry_export_excludes_the_superseded_family(store):
    """THE PATH THAT DID NOT EXIST WHEN THE FILTER WAS WRITTEN.

    The export is the second consumer, and the whole point of `live_rows` is
    that it inherits the filter rather than re-implementing or forgetting it.
    """
    rows, meta = EM.registry_rows()
    assert [r["family"] for r in rows if r["era"] == "ALL"] == [FAMILY]
    assert meta["families_excluded"] == {}

    _write_rule(store)
    rows, meta = EM.registry_rows()
    assert rows == [], rows
    assert FAMILY in meta["families_excluded"]
    assert meta["families_excluded"][FAMILY]["reason"] == "SUPERSEDED"
    # Withheld, and SAID SO. Silently dropping a retracted family is the same
    # error as letting it vote, pointed the other way. Here the rule's boundary
    # postdates every row, so there is no SURVIVING cell to withhold and the
    # honest number is the row count the boundary already removed.
    assert meta["families_excluded"][FAMILY]["cells_withheld_by_state"] == {}
    assert meta["families_excluded"][FAMILY]["observations_row_superseded"] == 2


def test_a_family_whose_corrected_rows_survive_is_still_excluded_and_counted(store):
    """THE CASE THE REAL STORE IS IN, and the reason both numbers are reported.

    `weekend-W7-matched-loser` carries 6,199 observations and the leak rule
    removes 101 of them, so NINE of the memory's twelve SUPPORTED cells are
    corrected re-runs that survive the boundary and still sit inside a family we
    have had to retract once. The export declines to speak for them and names
    the count, so B9 re-admits a known quantity instead of rediscovering it.
    """
    late = [_clearing_row(FAMILY, CELL, "2026-09-03T00:00:00+00:00",
                          variant="c", dsr=0.97),
            _clearing_row(FAMILY, CELL, "2026-09-03T01:00:00+00:00",
                          variant="d", dsr=0.96)]
    (store / "evidence_memory.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in ROWS + late), encoding="utf-8")
    _write_rule(store)
    rows, meta = EM.registry_rows()
    assert rows == []
    node = meta["families_excluded"][FAMILY]
    assert node["cells_withheld_by_state"] == {"SUPPORTED": 1}
    assert node["observations_row_superseded"] == 2


def test_a_retracted_verdict_is_excluded_even_with_no_rule(store):
    """A family whose own recorded verdict says RETRACT does not reach the
    registry either. The rule file is one channel; the verdict is another."""
    rows = [dict(r, verdict="RETRACTED -- the control pool leaked") for r in ROWS]
    (store / "evidence_memory.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    exported, meta = EM.registry_rows()
    assert exported == []
    assert meta["families_excluded"][FAMILY]["reason"] == "RETRACTED"


# ------------------------------------------ 2. the rule file cannot fail quietly

def test_an_unparseable_supersession_raises_rather_than_being_skipped(store):
    """THE ASYMMETRY. `read_all` skips a bad observation and loses one data
    point; skipping a bad SUPERSESSION puts a retracted experiment back into
    every tally, silently, in the direction of claiming more than we know."""
    (store / "supersessions.jsonl").write_text(
        json.dumps(RULE) + "\n{not json}\n", encoding="utf-8")
    with pytest.raises(EM.EvidenceMemoryError, match="does not parse"):
        EM.read_supersessions()


def test_a_boundary_that_cannot_match_is_refused():
    """`before_utc: "2026-09-05"` excludes NOTHING — the comparison is
    lexicographic, and every full timestamp on that day sorts AFTER the bare
    date. A rule that reads as a retraction and retracts nothing is a broken
    guard, so it is refused at the point of writing."""
    with pytest.raises(EM.EvidenceMemoryError, match="shorter than a full timestamp"):
        EM._check_before_utc("2026-09-05")
    with pytest.raises(EM.EvidenceMemoryError, match="not an ISO timestamp"):
        EM._check_before_utc("last tuesday")
    # And the shape that DOES work, plus the whole-family form.
    EM._check_before_utc("2026-09-05T05:40:00+00:00")
    EM._check_before_utc(None)


def test_supersede_refuses_an_unreasoned_or_unfamilied_rule(store):
    with pytest.raises(EM.EvidenceMemoryError, match="family_id"):
        EM.supersede("", "2026-09-05T05:40:00+00:00", "why")
    with pytest.raises(EM.EvidenceMemoryError, match="reason"):
        EM.supersede(FAMILY, "2026-09-05T05:40:00+00:00", "")


def test_a_whole_family_retraction_needs_no_boundary(store):
    """`before_utc=None` supersedes the family for all time — a retraction with
    no surviving correction. Written through the real entry point."""
    EM.supersede(FAMILY, None, "the whole family is withdrawn")
    rules = EM.read_supersessions()
    assert len(rules) == 1
    kept, dropped, effect = EM.live_rows()
    assert kept == []
    assert sum(dropped.values()) == 2


def test_a_rule_that_excludes_nothing_says_so_loudly(store):
    """SILENCE IS NOT EVIDENCE. A rule aimed at a family that is not in the
    store excludes zero rows, and must never read as 'applied, no effect'."""
    _write_rule(store, dict(RULE, family_id="a-family-that-does-not-exist"))
    kept, dropped, effect = EM.live_rows()
    assert len(kept) == 2 and dropped == {}
    (only,) = effect.values()
    assert only["observations_excluded"] == 0
    assert "broken guard" in only["WARNING"]

    _write_rule(store)
    _, _, effect = EM.live_rows()
    (only,) = effect.values()
    assert only["observations_excluded"] == 2
    assert only["WARNING"] is None
