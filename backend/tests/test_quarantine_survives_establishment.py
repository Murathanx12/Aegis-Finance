"""The quarantine must survive the population becoming established.

THE DEFECT THIS PINS (found 2026-08-17, reproduced before it was fixed)
======================================================================
`live_forward_is_established` answers "has the deployed product accrued anything
the campaign did not already write?" via `established = shared < len(live)`.
That is the right answer to that question.

`ledger_resolver.resolve_due` then used it as the gate on whether to GRADE the
live volume — and `resolve_all` rewrites the whole file. So the condition
protecting 112 quarantined campaign copies was released by the arrival of ONE
unrelated record: the first genuine forecast the product ever writes flips
`established` to True, and the next 16:30 ET tick grades all 112 copies into the
live product's forward record, unattended.

Measured on the real prod topology before the fix: 112 copies + 1 genuine record
⇒ established True, 112 records due, 112 of them copies.

An outcome written onto a record is the thing that makes it evidence, and it
cannot be un-written. So these tests pin the property the boolean could not
carry: the copies are ungradeable BY CONTENT, whatever else the file holds.
"""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from backend import config as _config
from backend.services import evidence_population as EP
from backend.services.ledger_resolver import resolve_due


@pytest.fixture
def split(tmp_path, monkeypatch):
    """Production topology: campaign in the image, live on the volume."""
    repo = tmp_path / "image" / "optimus"
    vol = tmp_path / "volume" / "optimus"
    repo.mkdir(parents=True)
    vol.mkdir(parents=True)
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_LEGACY_DIR", repo)
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", vol)
    return repo, vol


def _copy_record(i: int) -> dict:
    """A campaign swarm row of the kind that reached the volume pre-guard.

    Untagged, exactly like the real 112: their population is inferred from the
    file they sit in, which is why the same bytes read LIVE on the volume and
    CAMPAIGN in the image.
    """
    return {"prediction_id": f"camp-{i}", "ticker": "AAA",
            "specialist": "swarm", "observable": "return_sign",
            "horizon_days": 20, "probability": 0.6,
            "made_at": "2025-02-03T00:00:00",
            "resolves_after": "2025-03-05T00:00:00",
            "outcome": None, "model": "m", "model_version": "v"}


def _genuine_record() -> dict:
    """The product's own forward forecast — nothing the campaign ever wrote."""
    return {"prediction_id": "live-genuine-001", "ticker": "AAA",
            "specialist": "pi_daily_check", "observable": "return_sign",
            "horizon_days": 20, "probability": 0.55,
            "made_at": "2025-02-03T00:00:00",
            "resolves_after": "2025-03-05T00:00:00",
            "outcome": None, "model": "m", "model_version": "v",
            "evidence_population": "live_forward"}


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n",
                    encoding="utf-8")


def _prices(n=400, drift=0.002):
    idx = pd.bdate_range("2025-01-01", periods=n)
    rng = np.random.default_rng(0)
    up = 100 * np.cumprod(1 + drift + rng.normal(0, 0.005, n))
    return pd.DataFrame({"AAA": up, "SPY": np.linspace(100, 110, n)}, index=idx)


# ── the defect, stated as the property it violated ──────────────────────────
def test_one_genuine_record_does_not_release_the_copies(split):
    """The whole finding. 112 copies + 1 genuine ⇒ grade the 1, never the 112."""
    repo, vol = split
    copies = [_copy_record(i) for i in range(112)]
    _write(EP.ledger_path(EP.EvidencePopulation.CAMPAIGN_FORWARD), copies)
    _write(EP.ledger_path(EP.EvidencePopulation.LIVE_FORWARD),
           copies + [_genuine_record()])

    est = EP.live_forward_is_established()
    assert est["established"] is True, (
        "one genuine record does make the population established — that part "
        "was never wrong, and this test is not about changing it")
    assert est["n_genuine"] == 1
    assert len(est["quarantined_hashes"]) == 112

    rep = resolve_due(price_fetch=lambda t, s, e: _prices(),
                      today=date(2025, 6, 2), population="live_forward")

    assert rep["newly_resolved"] == 1, (
        "exactly the product's own record should have been graded; "
        f"got {rep['newly_resolved']}")
    assert rep["quarantine"]["n_quarantined"] == 112
    assert rep["due"] == 1, (
        "the 112 copies must not even enter the due set — they drive the price "
        "panel and would otherwise be fetched nightly forever")

    graded = [r for r in EP._read_jsonl(
        EP.ledger_path(EP.EvidencePopulation.LIVE_FORWARD))
        if r.get("outcome") is not None]
    assert len(graded) == 1
    assert graded[0]["prediction_id"] == "live-genuine-001", (
        "a campaign copy was graded onto the live volume — the outcome that "
        "makes a record evidence cannot be un-written")


def test_copies_are_written_back_verbatim_not_merely_ungraded(split):
    """Skipped ≠ mangled. The bytes of a quarantined record must not move."""
    repo, vol = split
    copies = [_copy_record(i) for i in range(3)]
    _write(EP.ledger_path(EP.EvidencePopulation.CAMPAIGN_FORWARD), copies)
    live = EP.ledger_path(EP.EvidencePopulation.LIVE_FORWARD)
    _write(live, copies + [_genuine_record()])

    before = {EP.record_hash(r) for r in EP._read_jsonl(live)
              if r["prediction_id"].startswith("camp-")}
    resolve_due(price_fetch=lambda t, s, e: _prices(),
                today=date(2025, 6, 2), population="live_forward")
    after = {EP.record_hash(r) for r in EP._read_jsonl(live)
             if r["prediction_id"].startswith("camp-")}
    assert before == after, "quarantined records were rewritten"


def test_an_all_copies_ledger_is_still_refused_outright(split):
    """The original refusal keeps working — this fix adds to it, not replaces."""
    repo, vol = split
    copies = [_copy_record(i) for i in range(112)]
    _write(EP.ledger_path(EP.EvidencePopulation.CAMPAIGN_FORWARD), copies)
    _write(EP.ledger_path(EP.EvidencePopulation.LIVE_FORWARD), copies)

    rep = resolve_due(price_fetch=lambda t, s, e: _prices(),
                      today=date(2025, 6, 2), population="live_forward")
    assert rep["status"] == "REFUSED"
    assert rep["newly_resolved"] == 0


def test_quarantined_overdue_is_reported_separately_from_unpriceable(split):
    """The two reasons a record sits overdue have OPPOSITE remedies.

    A price gap is a bug to fix; a quarantined copy is supposed to sit there
    until Murat disposes of it. One conflated number is how prod's "25 overdue"
    read to two reviewers as a dead resolver.
    """
    repo, vol = split
    copies = [_copy_record(i) for i in range(5)]
    _write(EP.ledger_path(EP.EvidencePopulation.CAMPAIGN_FORWARD), copies)
    _write(EP.ledger_path(EP.EvidencePopulation.LIVE_FORWARD),
           copies + [_genuine_record()])

    rep = resolve_due(price_fetch=lambda t, s, e: _prices(),
                      today=date(2025, 6, 2), population="live_forward")
    assert rep["quarantine"]["n_quarantined_overdue"] == 5
    assert rep["unpriceable"] == [], (
        "quarantined records must not masquerade as a pricing failure")


# ── the canon-mandated refusal test: hand the guard a MISSING input ─────────
def test_the_guard_refuses_when_it_cannot_see_the_campaign_ledger(split):
    """A guard whose comparison set is missing must refuse, not pass.

    If the campaign ledger is absent, `shared` is 0, `established` is True and
    every copy looks genuine — the guard would clear the whole quarantine
    because it could not see the thing it compares against. Absence of the
    comparison set is not evidence the records are the product's own.
    """
    repo, vol = split
    copies = [_copy_record(i) for i in range(112)]
    # campaign ledger deliberately NOT written
    _write(EP.ledger_path(EP.EvidencePopulation.LIVE_FORWARD), copies)
    assert not EP.ledger_path(EP.EvidencePopulation.CAMPAIGN_FORWARD).exists()

    with pytest.raises(EP.PopulationRequired, match="campaign"):
        EP.quarantined_hashes()

    # And the describing call reports the same gap WITHOUT raising, because a
    # missing repo artifact must not take a health page down.
    est = EP.live_forward_is_established()
    assert est["comparison_available"] is False
    assert est["established"] is False, (
        "an unjudgeable population must not read as established — that is the "
        "silent-clear this guard exists to stop")


def test_a_due_record_is_refused_when_the_quarantine_is_uncomputable(split):
    """No comparison set + something due ⇒ refuse. The copies are unidentifiable."""
    repo, vol = split
    _write(EP.ledger_path(EP.EvidencePopulation.LIVE_FORWARD),
           [_copy_record(i) for i in range(3)])
    rep = resolve_due(price_fetch=lambda t, s, e: _prices(),
                      today=date(2025, 6, 2), population="live_forward")
    assert rep["status"] == "REFUSED"
    assert rep["newly_resolved"] == 0
    assert "comparison set" in rep["reason"]


def test_health_names_the_refusal_instead_of_a_bare_overdue_count(split):
    """The reporting half, and the reason two reviews misdiagnosed prod.

    `ledger_health` reported "25 forecast(s) past due and unresolved" for records
    the resolver was deliberately refusing to grade. A guard that refuses and a
    job that never ran produce identical silence, so the row must say which. Both
    reviewers read that count as a dead scheduler and proposed rebuilding a
    scheduler that had all seven jobs registered and was running fine.
    """
    from backend.services.belief_state import ledger_health

    repo, vol = split
    copies = [_copy_record(i) for i in range(5)]
    _write(EP.ledger_path(EP.EvidencePopulation.CAMPAIGN_FORWARD), copies)
    live = EP.ledger_path(EP.EvidencePopulation.LIVE_FORWARD)
    _write(live, copies + [_genuine_record()])

    blind = ledger_health(live, today=date(2025, 6, 2))
    assert blind["n_overdue"] == 6
    assert not any("QUARANTINED" in p for p in blind["problems"]), (
        "without the quarantine set the row cannot split the count — that is "
        "the state that misled the reviews, pinned here so the split is not "
        "silently lost again")

    split_row = ledger_health(live, today=date(2025, 6, 2),
                              quarantined_hashes=EP.quarantined_hashes())
    assert split_row["n_overdue_quarantined"] == 5
    assert split_row["n_overdue_actionable"] == 1
    assert any("QUARANTINED" in p and "on purpose" in p
               for p in split_row["problems"]), (
        "the row must say the refusal is deliberate, in words, not leave it to "
        "be inferred from a number")
    assert split_row["n_overdue"] == 6, "the total must still be reported"


def test_a_clean_live_ledger_with_nothing_due_is_not_refused(split):
    """The narrowing that keeps the guard honest.

    A live ledger with no matured records is in no danger, whatever the campaign
    artifact's state — nothing would be graded. Refusing here would strand a
    clean ledger on any machine without the campaign history, which is a guard
    inventing work rather than preventing harm.
    """
    repo, vol = split
    _write(EP.ledger_path(EP.EvidencePopulation.LIVE_FORWARD),
           [dict(_genuine_record(), resolves_after="2099-01-01T00:00:00")])
    rep = resolve_due(price_fetch=lambda t, s, e: _prices(),
                      today=date(2025, 6, 2), population="live_forward")
    assert rep.get("status") != "REFUSED"
    assert rep["due"] == 0
    assert rep["pending"] == 1
    assert rep["lineage"]["evidence_population"] == "live_forward"
