"""Order 4: the nightly resolver must not grade campaign rows as live evidence.

THE DATED HAZARD THIS CLOSES
============================
Adjudicated 2026-08-15: every record on the LIVE_FORWARD volume is
content-identical to a CAMPAIGN_FORWARD record — a partial copy of campaign
history that reached the volume before the migration guard existed. Their
`resolves_after` dates begin **2026-08-16**, with 25 due that month.

So `pi_ledger_resolve` — nightly, unattended, correctly pinned to
`live_forward` — was four days from writing outcomes onto campaign swarm rows
and thereby manufacturing "the deployed product's forward record" out of
history. An outcome written onto a record is the thing that makes it evidence;
there is no later correction that unmakes it.

AND WHY THE RECEIPT MATTERS
===========================
When nothing is due, a healthy run mutates nothing. So "the ledger is
unchanged" is the EXPECTED result and cannot distinguish a run that had nothing
to do from a job that never fired. The receipt makes `nothing_was_due` a
written result rather than an inference from silence.
"""

from __future__ import annotations

import json

from backend.services import evidence_population as EP
from backend.services import ledger_resolver as LR


def _rec(pid, resolves_after="2026-08-16", pop="live_forward"):
    return {"prediction_id": pid, "ticker": "AAA", "specialist": "skeptic",
            "made_at": "2026-08-12T09:00:00+00:00", "observable": "return_sign",
            "horizon_days": 5, "probability": 0.5, "outcome": None,
            "model": "deepseek-chat", "model_version": "deepseek-v4-flash",
            "resolves_after": resolves_after, "evidence_population": pop}


def test_resolution_is_refused_when_every_live_record_is_a_campaign_copy(
        monkeypatch, tmp_path):
    live = tmp_path / "live.jsonl"
    live.write_text("".join(json.dumps(_rec(f"p{i}")) + "\n" for i in range(3)),
                    encoding="utf-8")

    monkeypatch.setattr(EP, "ledger_path", lambda pop: live)
    monkeypatch.setattr(EP, "live_forward_is_established", lambda **kw: {
        "established": False, "n_records": 3, "n_shared_with_campaign": 3,
        "reason": "every one of 3 LIVE_FORWARD record(s) is content-identical "
                  "to a CAMPAIGN_FORWARD record ... UNESTABLISHED"})
    monkeypatch.setattr(LR, "assert_single_population", lambda *a, **k: None)
    monkeypatch.setattr(EP, "lineage", lambda *a, **k: {})

    import datetime as dt
    out = LR.resolve_due(population="live_forward",
                         today=dt.date(2026, 8, 16))   # the day 25 fall due

    assert out["status"] == "REFUSED"
    assert out["newly_resolved"] == 0
    assert out["due"] == 0
    assert out["health"]["status"] == "DEGRADED"
    assert "UNESTABLISHED" in out["reason"]
    # Untouched on disk: a refusal must not half-resolve.
    rows = [json.loads(l) for l in live.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    assert all(r["outcome"] is None for r in rows)


def test_an_established_population_is_resolved_normally(monkeypatch, tmp_path):
    live = tmp_path / "live.jsonl"
    live.write_text(json.dumps(_rec("p1", resolves_after="2099-01-01")) + "\n",
                    encoding="utf-8")

    monkeypatch.setattr(EP, "ledger_path", lambda pop: live)
    monkeypatch.setattr(EP, "live_forward_is_established", lambda **kw: {
        "established": True, "n_records": 1, "n_shared_with_campaign": 0,
        "reason": ""})
    monkeypatch.setattr(LR, "assert_single_population", lambda *a, **k: None)
    monkeypatch.setattr(EP, "lineage", lambda *a, **k: {})

    import datetime as dt
    out = LR.resolve_due(population="live_forward", today=dt.date(2026, 8, 16))

    # The guard is narrow on purpose: it blocks a population that owns nothing,
    # not resolution in general.
    assert out.get("status") != "REFUSED"
    assert out["due"] == 0          # nothing matured; that is a clean report


def test_an_empty_live_ledger_is_not_refused(monkeypatch, tmp_path):
    live = tmp_path / "live.jsonl"
    live.write_text("", encoding="utf-8")

    monkeypatch.setattr(EP, "ledger_path", lambda pop: live)
    monkeypatch.setattr(EP, "live_forward_is_established", lambda **kw: {
        "established": False, "n_records": 0, "n_shared_with_campaign": 0,
        "reason": "LIVE_FORWARD is empty"})
    monkeypatch.setattr(LR, "assert_single_population", lambda *a, **k: None)
    monkeypatch.setattr(EP, "lineage", lambda *a, **k: {})

    import datetime as dt
    out = LR.resolve_due(population="live_forward", today=dt.date(2026, 8, 16))

    # An empty ledger has nothing to grade and needs no refusal. Refusing here
    # would make an ordinary quiet night look like an incident.
    assert out.get("status") != "REFUSED"


# ── the receipt ─────────────────────────────────────────────────────────────

def test_a_run_with_nothing_due_still_leaves_a_receipt(monkeypatch, tmp_path):
    from backend import config as _config
    from backend.services.portfolio_intelligence import scheduler as S
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", tmp_path)

    S._write_resolver_receipt({"due": 0, "newly_resolved": 0, "pending": 106,
                               "overdue": 0, "health": {"status": "ok"}})

    files = list((tmp_path / "resolver_receipts").glob("*.json"))
    assert len(files) == 1
    body = json.loads(files[0].read_text(encoding="utf-8"))
    # `nothing_was_due` is a RESULT, written down — not an inference from an
    # unchanged ledger, which is exactly what a job that never ran also leaves.
    assert body["nothing_was_due"] is True
    assert body["job"] == "pi_ledger_resolve"
    assert body["population"] == "live_forward"
    assert body["ran_at"]


def test_a_refusal_is_recorded_on_the_receipt(monkeypatch, tmp_path):
    from backend import config as _config
    from backend.services.portfolio_intelligence import scheduler as S
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", tmp_path)

    S._write_resolver_receipt({"status": "REFUSED", "reason": "unestablished",
                               "due": 0, "newly_resolved": 0})

    body = json.loads(next((tmp_path / "resolver_receipts")
                           .glob("*.json")).read_text(encoding="utf-8"))
    assert body["status"] == "REFUSED"
    assert body["reason"] == "unestablished"


def test_a_receipt_failure_never_takes_down_the_resolution(monkeypatch):
    from backend import config as _config
    from backend.services.portfolio_intelligence import scheduler as S
    # An unwritable destination must not propagate: instrumentation may degrade
    # to a log line, the run it describes may not.
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR",
                        __import__("pathlib").Path("\0invalid"))
    S._write_resolver_receipt({"due": 0})
