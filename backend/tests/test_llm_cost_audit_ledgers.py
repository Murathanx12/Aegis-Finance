"""llm_cost_audit reads every ledger file the WRITER produces (2026-09-29).

It read only the legacy monolith `llm_calls.jsonl`, retired by the 2026-09-12
monthly rotation, so its telemetry half was $0.00 on every run while the
provider's balance moved. The file list now comes from the writer's own rule
(`llm_telemetry.ledger_files`), and a provider/telemetry gap beyond a stated
tolerance is printed as DISAGREE by name.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.services import llm_telemetry as LT
from scripts import llm_cost_audit as A


def _write_via_writer(base: Path) -> None:
    LT.append([LT.build_call(provider="deepseek", model="deepseek-chat",
                             purpose="p_test", tokens_in=1_000_000, tokens_out=0)],
              path=base)


def test_the_audit_reads_the_month_files_the_writer_writes(monkeypatch, tmp_path):
    base = tmp_path / "llm_calls.jsonl"
    monkeypatch.setenv(LT.LLM_TELEMETRY_PATH_ENV, str(base))
    _write_via_writer(base)
    assert not base.exists()                       # the writer never writes the base
    files = A.find_ledgers()
    written = LT.ledger_files(base)
    assert written and all(f in files for f in written)
    tot = sum(A.ledger_totals(f, None)["usd"] for f in written)
    assert tot > 0


def test_main_prints_telemetry_beside_the_provider_and_says_disagree(monkeypatch, tmp_path, capsys):
    base = tmp_path / "llm_calls.jsonl"
    monkeypatch.setenv(LT.LLM_TELEMETRY_PATH_ENV, str(base))
    monkeypatch.setattr(A, "ledger_bases", lambda: [base])
    _write_via_writer(base)
    tel_usd = sum(A.ledger_totals(f, None)["usd"] for f in LT.ledger_files(base))
    monkeypatch.setattr(A.bal, "snapshots", lambda: [])
    monkeypatch.setattr(A.bal, "read_balance", lambda: {"total_usd": 10.0})
    # provider moved tel_usd + $1.47: telemetry cannot explain it
    A.main(["--since", "2000-01-01", "--balance-then", str(10.0 + tel_usd + 1.47), "--json"])
    rep = json.loads(capsys.readouterr().out)
    assert rep["telemetry_total_usd"] > 0
    assert rep["agreement"] == "DISAGREE"
    A.main(["--since", "2000-01-01", "--balance-then", str(10.0 + tel_usd)])
    out = capsys.readouterr().out
    assert "provider vs telemetry: AGREE" in out and "telemetry says" in out


def test_agreement_states_its_tolerance():
    assert A.agreement(None, 1.0)["verdict"] == "NOT COMPUTABLE"
    a = A.agreement(1.47, 0.0)
    assert a["verdict"] == "DISAGREE" and a["tolerance_usd"] >= A.DISAGREE_TOLERANCE_USD
    assert A.agreement(1.00, 0.99)["verdict"] == "AGREE"


def test_importing_the_audit_does_not_silence_telemetry_warnings():
    """The unpriced-model quieting is scoped to the recompute call. It was a
    module-level setLevel(ERROR), so importing this script silenced every
    telemetry warning for the whole process (2026-09-29)."""
    import logging
    lg = logging.getLogger("backend.services.llm_telemetry")
    assert lg.level != logging.ERROR
    before = lg.level
    with A._quiet_telemetry():
        assert lg.level == logging.ERROR
    assert lg.level == before
