"""TEACHER-LIBRARY-1 — the Schedule 13D/13G adapter.

The second independent source. What these tests protect is mostly the two ways
this adapter could quietly lie: by treating a passive index-fund threshold
crossing as an activist declaration, and by inventing an actor for a filing
whose filer it could not resolve.

Offline: every SEC call is monkeypatched.
"""

from __future__ import annotations

import pytest

from backend.services.teacher_library import events as E
from backend.services.teacher_library import ledger as L
from backend.services.teacher_library.adapters import ingest
from backend.services.teacher_library.adapters_13dg import (_FILER_RE,
                                                            Schedule13DGAdapter)

_HEADER = """<SEC-HEADER>
FILER:
\tCOMPANY DATA:
\t\tCOMPANY CONFORMED NAME:\t\t\tCLEVELAND CLIFFS INC
\t\tCENTRAL INDEX KEY:\t\t\t0000764065

FILED BY:

\tCOMPANY DATA:
\t\tCOMPANY CONFORMED NAME:\t\t\tVANGUARD GROUP INC
\t\tCENTRAL INDEX KEY:\t\t\t0000102909
\t\tIRS NUMBER:\t\t\t\t231945930
</SEC-HEADER>"""


def _filing(form="SC 13D", accepted="2026-08-10T09:15:00.000Z",
            filed="2026-08-10", filer="ICAHN CARL C", fcik="921669", **kw):
    row = {"form": form, "accession": f"0001-{form}-{filed}",
           "filing_date": filed, "accepted_at": accepted,
           "issuer_cik": "764065", "filer_name": filer, "filer_cik": fcik}
    row.update(kw)
    return row


def _payload(*filings, status=E.OK_DATA, ticker="CLF", reason=""):
    return {"ticker": ticker, "source": "sec_13dg", "status": status,
            "reason": reason, "filings": list(filings),
            "n_filings": len(filings), "n_unresolved_filers": 0}


# ── the filer header parser ────────────────────────────────────────────────

def test_the_filer_is_taken_from_FILED_BY_not_from_the_issuer_block():
    """The issuer appears FIRST in the header. A regex that matched the first
    company block would attribute every 13G to the company it was filed
    against — the actor and the subject swapped."""
    m = _FILER_RE.search(_HEADER)
    assert m is not None
    assert m.group("name").strip() == "VANGUARD GROUP INC"
    assert m.group("cik").lstrip("0") == "102909"


def test_a_header_with_no_filed_by_block_yields_no_filer():
    assert _FILER_RE.search("<SEC-HEADER>\nFILER:\n\tCOMPANY DATA:\n") is None


# ── 13D and 13G are not the same event ─────────────────────────────────────

def test_a_13d_is_an_activist_stake_and_a_13g_is_a_passive_one():
    """Collapsing them would average an activist's declaration of intent with an
    index fund crossing a threshold mechanically. Two different things that
    happen to share a percentage."""
    ad = Schedule13DGAdapter()
    d = ad.to_events(_payload(_filing(form="SC 13D")))[0]
    g = ad.to_events(_payload(_filing(form="SC 13G", filer="VANGUARD GROUP INC",
                                      fcik="102909")))[0]
    assert d.action_type == "ACTIVIST_STAKE"
    assert d.actor_type == E.ACTOR_ACTIVIST_INVESTOR
    assert g.action_type == "PASSIVE_STAKE"
    assert g.actor_type == E.ACTOR_FUND_MANAGER
    assert d.actor_type != g.actor_type


def test_the_actor_type_inference_is_flagged_as_an_inference():
    """It comes from the FORM, not from the filer's nature. A 13G filer can be
    an individual; the flag is what stops a later feature treating the label as
    an observation."""
    ev = Schedule13DGAdapter().to_events(_payload(_filing()))[0]
    assert "actor_type_inferred_from_form_type" in ev.data_quality_flags


# ── time ───────────────────────────────────────────────────────────────────

def test_public_at_is_the_acceptance_timestamp_not_the_filing_date():
    """Observed live: a real CLF 13G/A was accepted at 21:55 UTC — 16:55 ET,
    after the close. Treating it as same-day tradable information would hand a
    backtest most of a session it never had."""
    ev = Schedule13DGAdapter().to_events(
        _payload(_filing(accepted="2026-08-10T21:55:49.000Z",
                         filed="2026-08-10")))[0]
    assert ev.public_at.startswith("2026-08-10T21:55:49")
    assert ev.accepted_at is not None
    assert ev.filed_at == "2026-08-10"


def test_a_missing_acceptance_falls_back_to_the_date_and_says_so():
    ev = Schedule13DGAdapter().to_events(
        _payload(_filing(accepted="")))[0]
    assert ev.public_at.startswith("2026-08-10")
    assert "acceptance_missing_filing_date_used" in ev.data_quality_flags


# ── identity: refused rather than invented ─────────────────────────────────

def test_an_unresolved_filer_is_identity_ambiguous_and_not_usable():
    """An activist event with no actor cannot support any actor-level question,
    and an anonymous row in a library whose subject is WHO DID WHAT is worse
    than no row."""
    ev = Schedule13DGAdapter().to_events(
        _payload(_filing(filer="", fcik="")))[0]
    assert ev.status == E.IDENTITY_AMBIGUOUS
    assert ev.reason == "filer_not_resolved"
    assert ev.identity_quality == "unresolved"
    assert not ev.usable


def test_an_unresolved_filer_still_reaches_the_ledger_and_the_coverage(tmp_path):
    """Counted, not used. A source dropping its unresolvable rows would report
    perfect identity coverage by construction."""
    p = tmp_path / "e.jsonl"
    ad = Schedule13DGAdapter(
        fetch=lambda s, **kw: _payload(_filing(filer="", fcik="")))
    ingest(ad, ["CLF"], path=p)
    assert L.events_asof("2026-08-30", path=p) == []
    cov = L.coverage(p)
    assert cov["by_status"][E.IDENTITY_AMBIGUOUS] == 1


# ── amendments ─────────────────────────────────────────────────────────────

def test_an_amendment_is_flagged_but_not_linked_to_a_parent():
    """EDGAR does not say which filing a /A amends. Setting `amends_event_id`
    on a guess would let the ledger supersede — and therefore HIDE — a filing
    the amendment may not even be amending."""
    ev = Schedule13DGAdapter().to_events(_payload(_filing(form="SC 13D/A")))[0]
    assert ev.is_amendment is True
    assert ev.amends_event_id is None
    assert "amendment_parent_unresolved" in ev.data_quality_flags


def test_an_unlinked_amendment_does_not_hide_its_probable_parent(tmp_path):
    p = tmp_path / "e.jsonl"
    ad = Schedule13DGAdapter(fetch=lambda s, **kw: _payload(
        _filing(form="SC 13D", filed="2026-08-01",
                accepted="2026-08-01T10:00:00.000Z"),
        _filing(form="SC 13D/A", filed="2026-08-10",
                accepted="2026-08-10T10:00:00.000Z")))
    ingest(ad, ["CLF"], path=p)
    got = L.events_asof("2026-08-30", path=p)
    assert len(got) == 2, "an unlinked amendment suppressed a real filing"


# ── the tri-state ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("status,reason", [
    (E.UNAVAILABLE, "submissions_fetch_failed"),
    (E.OK_EMPTY, "no_13dg_filings_in_window"),
])
def test_a_failed_and_an_empty_window_stay_distinguishable(status, reason,
                                                           tmp_path):
    p = tmp_path / "e.jsonl"
    ad = Schedule13DGAdapter(fetch=lambda s, **kw: _payload(status=status,
                                                            reason=reason))
    ingest(ad, ["CLF"], path=p)
    rows = L.all_events(p)
    assert rows[0].status == status and rows[0].reason == reason
    assert not rows[0].usable


def test_ingest_wires_13dg_to_the_ledger_beside_form4(tmp_path):
    p = tmp_path / "e.jsonl"
    # The stub must vary with the subject. An earlier version returned the
    # identical payload for both, and dedup correctly collapsed them to one —
    # the fixture was wrong, not the ledger.
    ad = Schedule13DGAdapter(fetch=lambda s, **kw: _payload(
        _filing(form="SC 13G", filer="BlackRock Inc.", fcik="1364742",
                accession=f"0001-{s}"),
        ticker=s))
    res = ingest(ad, ["CLF", "PFE"], path=p)
    assert res["written"] == 2 and res["usable_events"] == 2
    got = L.events_asof("2026-08-30", path=p)
    assert {e.source for e in got} == {"sec_13dg"}
    assert all(e.actor_id == "cik:1364742" for e in got)


def test_the_source_url_points_at_the_filing_directory():
    ev = Schedule13DGAdapter().to_events(_payload(_filing()))[0]
    assert ev.source_url.startswith("https://www.sec.gov/Archives/edgar/data/")
    assert "-" not in ev.source_url.rsplit("/", 2)[-2]   # accession de-dashed
