"""The plan reconciliation, and the gap check that feeds it.

Measured 2026-08-23: the WRDS manifest carried `completed_at`, the substrate
receipt said every consumed input was verified, `wrds_pull_catchup --dry-run`
printed `RETRYABLE: 0` — and seven planned tables had never been attempted.
None of those three could see them, for the same structural reason: each was
reading the record of what HAPPENED (files on disk, failure rows) and a table
nobody ever asked for leaves no trace in either.

They turned out to be empty on the server, so nothing was lost. That is luck,
not a check. Nothing on disk distinguishes "the table is empty" from "the
table was never pulled", which is exactly why the reconciliation has to be
derived from the PLAN rather than from the outcome.

These tests are CI-complete: they run against the committed receipt and the
committed plan/manifest JSON, never against the 46 GB bulk store or the
network.
"""

from __future__ import annotations

import json

import pytest

from backend import config as _config

WRDS = _config.OPTIMUS_LEDGER_DIR / "wrds"
RECEIPT = WRDS / "TRAINING_SUBSTRATE_V1.json"

#: Every planned table lands in exactly one of these. Two are decisions
#: (over_cap, terminal) and two are outcomes (on_disk, empty); the sum is the
#: plan, and the residual is the thing this file exists to keep at zero.
DISPOSITIONS = ("on_disk", "empty", "over_cap", "terminal")


@pytest.fixture(scope="module")
def receipt():
    if not RECEIPT.exists():
        pytest.fail(f"{RECEIPT.name} is a committed artifact — without it "
                    f"nothing certifies the training substrate")
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


class TestTheReconciliation:
    def test_the_receipt_carries_one(self, receipt):
        """A v1 receipt (no reconciliation) must not pass as a v1.1 one: it
        verified the files that EXIST, which is silent about the plan."""
        assert "plan_reconciliation" in receipt, (
            "receipt predates the plan reconciliation — it cannot distinguish "
            "a complete pull from one that skipped tables silently")
        assert receipt.get("version") == "1.1"

    def test_every_planned_table_is_accounted_for(self, receipt):
        r = receipt["plan_reconciliation"]
        assert sum(r[k] for k in DISPOSITIONS) == r["n_planned"], (
            f"dispositions {[(k, r[k]) for k in DISPOSITIONS]} do not sum to "
            f"the plan ({r['n_planned']}) — some table is double-counted or "
            f"in no bucket at all")

    def test_nothing_is_outstanding(self, receipt):
        """The one number that means 'the pull is finished'. Not
        `completed_at`, which the manifest wrote while 79% of the plan was
        missing (2026-08-20) and again with seven tables unattempted."""
        assert receipt["plan_reconciliation"]["n_outstanding"] == 0

    def test_deferred_is_not_conflated_with_missing(self, receipt):
        """235 over-cap tables are not a hole: they were MEASURED above the
        cap and deferred by the standing named-consumer rule, and they carry
        the cap they were measured against so raising it re-queues them. 240
        terminal rows are entitlement facts. A reconciliation that folded
        either into 'outstanding' would demand work that must not happen; one
        that folded 'outstanding' into either would hide work that must."""
        r = receipt["plan_reconciliation"]
        assert r["over_cap"] > 0 and r["terminal"] > 0
        assert "DECISION" in r["note"] and "ENTITLEMENT FACT" in r["note"]


class TestTheGuardCanActuallyRefuse:
    """A guard whose refusal path never executes is a comment. Canon: every
    guard ships a missing-input test."""

    def test_an_unaccounted_table_is_refused(self, monkeypatch, tmp_path):
        from scripts import training_substrate_receipt as T

        plan = {"plan": [{"schema": "zz", "table": "ghost",
                          "name": "zz.ghost"}]}
        cache = tmp_path / "plan.json"
        cache.write_text(json.dumps(plan), encoding="utf-8")
        term = tmp_path / "pull_terminal_failures.json"
        term.write_text(json.dumps({"tables": []}), encoding="utf-8")

        import scripts.wrds_pull_everything as E
        monkeypatch.setattr(E, "PLAN_CACHE", cache)
        monkeypatch.setattr(T, "WRDS", tmp_path)
        monkeypatch.setattr(T, "BULK", tmp_path / "bulk")  # empty

        with pytest.raises(SystemExit, match="unaccounted for"):
            T._reconcile_plan({"pulled": [], "over_cap": []})

    @pytest.mark.parametrize("bucket,record", [
        ("empty", {"pulled": [{"name": "zz.ghost", "rows": 0}],
                   "over_cap": []}),
        ("over_cap", {"pulled": [],
                      "over_cap": [{"name": "zz.ghost"}]}),
    ])
    def test_a_declared_disposition_is_accepted(self, monkeypatch, tmp_path,
                                                bucket, record):
        """The same absent table passes once something DECLARES why it is
        absent — which is the whole distinction the refusal draws."""
        from scripts import training_substrate_receipt as T

        cache = tmp_path / "plan.json"
        cache.write_text(json.dumps(
            {"plan": [{"schema": "zz", "table": "ghost", "name": "zz.ghost"}]}),
            encoding="utf-8")
        (tmp_path / "pull_terminal_failures.json").write_text(
            json.dumps({"tables": []}), encoding="utf-8")

        import scripts.wrds_pull_everything as E
        monkeypatch.setattr(E, "PLAN_CACHE", cache)
        monkeypatch.setattr(T, "WRDS", tmp_path)
        monkeypatch.setattr(T, "BULK", tmp_path / "bulk")

        out = T._reconcile_plan(record)
        assert out["n_outstanding"] == 0
        assert out[bucket] == 1


class TestTheCatchupSeesNeverAttempted:
    def test_the_queue_is_reconciled_against_the_plan_not_the_failures(self):
        """Source-level, because the alternative is a network pull.

        The bug was structural: the retry loop iterates the manifest's
        `failed` list, so `never attempted` had no entry to iterate. If the
        plan-driven pass is ever removed, --dry-run silently returns to
        printing RETRYABLE: 0 over a hole.
        """
        import inspect

        from scripts import wrds_pull_catchup as C

        src = inspect.getsource(C.main)
        assert "NEVER_ATTEMPTED" in src
        assert "_planned_rows()" in src, (
            "the never-attempted pass must derive from the PLAN; reading the "
            "failure list again reintroduces the bug")
