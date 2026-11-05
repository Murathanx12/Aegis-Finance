"""Offline shared-envelope preflight regression tests; no runtime ledger fixtures."""
import json
import socket
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import world_digest as S
from backend.services import provider_budget as REAL_PB


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        pytest.fail('network reached')
    monkeypatch.setattr(socket.socket, 'connect', no_network)
    monkeypatch.setattr(socket, 'create_connection', no_network)
    monkeypatch.setattr(S, '_ensure_streams', lambda: None)
    monkeypatch.setattr(S.WD, 'work_dir', lambda: tmp_path)
    monkeypatch.setattr(S.WD, 'stop_file', lambda: tmp_path / 'STOP')
    monkeypatch.setattr(S, '_host_budget_required', lambda: True)
    from backend.services import disk_guard as DG
    monkeypatch.setattr(DG, 'require_free', Mock())
    guards = []
    for obj, name in [(S, '_balance'), (S.WD, 'collect'), (S.WD, 'Meter'),
                      (S.WD, 'extract_items')]:
        guard = Mock(side_effect=AssertionError('downstream reached'))
        monkeypatch.setattr(obj, name, guard)
        guards.append(guard)
    snap = Mock(return_value={'cap_units': 100, 'opening_units': 0,
                              'calls': {}, 'blocked': None})
    fake_budget = SimpleNamespace(preflight_snapshot=snap, BudgetRefused=RuntimeError)
    from backend import services as service_package
    monkeypatch.setattr(service_package, 'provider_budget', fake_budget, raising=False)
    monkeypatch.setitem(sys.modules, 'backend.services.provider_budget', fake_budget)
    return tmp_path, snap, guards


@pytest.mark.parametrize('mode', ['absent', 'blocked', 'exhausted', 'overdrawn', 'invalid'])
def test_refusal_is_early_nonsecret_and_append_only(isolated, capsys, mode):
    root, snap, guards = isolated
    if mode == 'absent':
        snap.side_effect = RuntimeError('SECRET_TOKEN must never appear')
    elif mode == 'blocked':
        snap.return_value['blocked'] = 'SECRET_TOKEN'
    elif mode in ('exhausted', 'overdrawn'):
        snap.return_value['opening_units'] = 50
        snap.return_value['calls'] = {'x': {'held_units': 50 if mode == 'exhausted' else 51}}
    else:
        snap.return_value = {}
    receipts = root / 'receipts'
    receipts.mkdir()
    old = receipts / 'run_existing.json'
    old.write_bytes(b'previous receipt')
    for _ in range(2):
        assert S.main(['--no-write']) == 2
    assert snap.call_count == 2
    for guard in guards:
        guard.assert_not_called()
    assert old.read_bytes() == b'previous receipt'
    failures = list(receipts.glob('budget_refused_*.json'))
    assert len(failures) == 2
    for path in failures:
        text = path.read_text()
        data = json.loads(text)
        assert data['state'] == 'BUDGET_REFUSED'
        assert data['written'] is False
        assert data['stamp'].endswith('Z')
        assert 'SECRET_TOKEN' not in text
    assert 'SECRET_TOKEN' not in capsys.readouterr().out
    assert not (root / 'run.lock').exists()


def test_healthy_continues_once(isolated):
    _, snap, guards = isolated
    assert S.main([]) == 1  # balance sentinel proves the original path was reached
    snap.assert_called_once_with()
    guards[0].assert_called_once()
    guards[1].assert_not_called()


def test_cloud_without_host_envelope_preserves_original_path(isolated, monkeypatch):
    _, snap, guards = isolated
    monkeypatch.setattr(S, '_host_budget_required', lambda: False)
    assert S.main([]) == 1  # original balance sentinel, not budget preflight
    snap.assert_not_called()
    guards[0].assert_called_once()


def test_dry_run_does_not_require_envelope(isolated):
    _, snap, guards = isolated
    assert S.main(['--dry-run']) == 1  # collection sentinel, no balance/model
    snap.assert_not_called()
    guards[0].assert_not_called()
    guards[1].assert_called_once()


def test_stop_still_wins(isolated):
    root, snap, guards = isolated
    (root / 'STOP').touch()
    assert S.main([]) == 0
    snap.assert_not_called()
    for guard in guards:
        guard.assert_not_called()


def test_missing_budget_module_is_refused(isolated, monkeypatch):
    root, _, guards = isolated
    from backend import services as service_package
    monkeypatch.setattr(service_package, 'provider_budget', None)
    monkeypatch.setitem(sys.modules, 'backend.services.provider_budget', None)
    assert S.main([]) == 2
    assert len(list((root / 'receipts').glob('budget_refused_*.json'))) == 1
    for guard in guards:
        guard.assert_not_called()


def test_receipt_storage_failure_stays_red_and_nonsecret(isolated, monkeypatch, capsys):
    _, snap, guards = isolated
    snap.side_effect = RuntimeError('SECRET_TOKEN')
    monkeypatch.setattr(S, '_budget_failure_receipt',
                        Mock(side_effect=OSError('SECRET_STORAGE_PATH')))
    assert S.main([]) == 2
    output = capsys.readouterr().out
    assert 'could not be persisted' in output
    assert 'SECRET' not in output
    for guard in guards:
        guard.assert_not_called()


@pytest.mark.parametrize('refused', [False, True])
def test_completed_run_preserves_partial_work_and_reports_budget_status(isolated, monkeypatch, refused):
    from collections import Counter
    from backend.services import belief_state as B
    from backend.services import world_state as WS

    root, snap, _ = isolated
    meter = SimpleNamespace(spent=0.001, models={'fake'}, statuses=Counter())
    meter.summary = lambda: {'spent_usd': meter.spent, 'budget_usd': .9,
                            'calls': 2, 'failed': int(refused),
                            'served_models': {'fake': 1}, 'statuses': dict(meter.statuses)}
    monkeypatch.setattr(S, '_balance', Mock(return_value={}))
    monkeypatch.setattr(S.WD, 'collect', Mock(return_value={
        'items': ['cached-source'], 'counts': {}, 'since': 'start', 'until': 'end'}))
    monkeypatch.setattr(S.WD, 'Meter', Mock(return_value=meter))
    monkeypatch.setattr(S.WD, 'read_cache', lambda: {})
    monkeypatch.setattr(S.WD, 'extract_items', Mock(return_value={
        'rows': [{'topic': 'valid fact'}], 'cache_hits': 1}))
    monkeypatch.setattr(S.WD, 'load_closes', lambda: SimpleNamespace(columns=['TEST']))
    monkeypatch.setattr(S.WD, 'stitched_symbols', lambda: set())
    monkeypatch.setattr(S, 'previous_titles', lambda: [])
    monkeypatch.setattr(S.WD, 'find_themes', Mock(return_value=[{'title': 'useful'}]))
    monkeypatch.setattr(S.WD, 'merge_near_duplicate_themes', lambda themes: (themes, []))
    monkeypatch.setattr(S.WD, 'implications_for', lambda *args, **kwargs: {
        'title': 'useful', 'implications': [{}], 'unknowns': []})
    record = SimpleNamespace(prediction_id='valid-row', observable='direction')
    monkeypatch.setattr(S.WD, 'implication_records', lambda *args, **kwargs: ([record], 'valid'))
    monkeypatch.setattr(B, 'read_predictions', lambda: [])
    append = Mock()
    monkeypatch.setattr(B, 'append', append)
    monkeypatch.setattr(S.WD, 'freeze_contract', Mock(side_effect=RuntimeError('offline shadow')))

    def cycle(*args, **kwargs):
        # Refusal AFTER valid rows were already appended must still turn the run red.
        if refused:
            meter.statuses['BUDGET_REFUSED'] += 1
        return {'state': 'DETERMINISTIC_ARTIFACT_PRESERVED'}

    monkeypatch.setattr(WS, 'run_cycle', cycle)
    monkeypatch.setattr(WS, 'render_lines', lambda value: ['deterministic artifact'])
    monkeypatch.setattr(S.WD, 'previous_digest', lambda stamp: None)
    monkeypatch.setattr(S.WD, 'what_changed', lambda *args: {})
    monkeypatch.setattr(S.WD, 'out_dir', lambda: root / 'digest')
    monkeypatch.setattr(S.WD, 'render', lambda digest: 'useful full render')
    monkeypatch.setattr(S.WD, 'render_short', lambda digest: 'useful short render')

    assert S.main(['--no-sections']) == (2 if refused else 0)
    snap.assert_called_once_with()
    append.assert_called_once_with([record])
    paths = list((root / 'digest').glob('*.json'))
    assert len(paths) == 1
    digest = json.loads(paths[0].read_text())
    assert digest['writes']['prediction_ids'] == ['valid-row']
    assert digest['writes']['written'] is True
    assert digest['n_rows'] == 1
    assert digest['world_state']['state'] == 'DETERMINISTIC_ARTIFACT_PRESERVED'
    assert paths[0].with_suffix('.md').read_text().startswith('useful full render')
    assert paths[0].with_suffix('.short.txt').read_text() == 'useful short render'
    if refused:
        assert digest['status'] == 'DEGRADED_MODEL_BUDGET'
    else:
        assert 'status' not in digest  # preserve the healthy output contract
    assert not (root / 'run.lock').exists()


@pytest.mark.parametrize("mode,expected", [
    ("missing", "MISSING"),
    ("json", "MALFORMED"),
    ("schema", "MALFORMED"),
    ("encoding", "MALFORMED"),
    ("unreadable", "LOCK_UNREADABLE"),
    ("lock", "LOCK_UNREADABLE"),
    ("import", "IMPORT_FAILED"),
    ("unexpected", "UNAVAILABLE"),
])
def test_real_preflight_reasons_are_read_only_and_fail_closed(
        isolated, monkeypatch, capsys, mode, expected):
    from pathlib import Path
    from backend import services
    from backend.services import belief_state as B, disk_guard as DG

    root, _, downstream = isolated
    p = root / "private-envelope.json"
    monkeypatch.setenv("AEGIS_DEEPSEEK_BUDGET_PATH", str(p))
    monkeypatch.setattr(services, "provider_budget", REAL_PB)
    monkeypatch.setitem(sys.modules, "backend.services.provider_budget", REAL_PB)
    if mode == "json":
        p.write_text("SECRET_TOKEN invalid json", encoding="utf-8")
    elif mode == "schema":
        p.write_text('{"schema": "SECRET_TOKEN"}', encoding="utf-8")
    elif mode == "encoding":
        p.write_bytes(b"\xff")
    elif mode in ("unreadable", "lock", "unexpected"):
        error = {"unreadable": PermissionError, "lock": DG.FileLockTimeout,
                 "unexpected": RuntimeError}[mode]
        monkeypatch.setattr(Path, "read_text", Mock(side_effect=error("SECRET_TOKEN")))
    elif mode == "import":
        monkeypatch.delattr(services, "provider_budget")
        monkeypatch.setitem(sys.modules, "backend.services.provider_budget", None)
    before = {f.name: f.read_bytes() for f in root.iterdir() if f.is_file()}
    guards = []
    for obj, name in [(REAL_PB, "_lock"), (REAL_PB, "reserve"),
                      (REAL_PB, "settle"), (REAL_PB, "initialize"),
                      (REAL_PB, "attempt"), (DG, "atomic_write_json"), (B, "append")]:
        guard = Mock(side_effect=AssertionError("write/provider reached"))
        monkeypatch.setattr(obj, name, guard)
        guards.append(guard)
    reason = "SHARED_ENVELOPE_" + expected
    # The preflight itself has no writes, including lock/directory creation.
    assert S._shared_budget_refusal() == reason
    assert {f.name: f.read_bytes() for f in root.iterdir() if f.is_file()} == before
    assert sorted(f.name for f in root.iterdir()) == sorted(before)
    # Run directly: production main's run lock and diagnostic receipt are outside
    # the read-only preflight. Mock only that explicitly allowed receipt here.
    receipt = Mock()
    monkeypatch.setattr(S, "_budget_failure_receipt", receipt)
    # This probe isolates the original budget diagnostic without the new
    # independently tested, default-on local sidecar.
    assert S.run(SimpleNamespace(dry_run=False, no_provisional_review=True)) == 2
    receipt.assert_called_once_with(reason)
    assert capsys.readouterr().out == f"REFUSED: shared budget preflight: {reason}\n"
    for guard in guards + downstream:
        guard.assert_not_called()
    assert {f.name: f.read_bytes() for f in root.iterdir() if f.is_file()} == before


def test_real_healthy_preflight_needs_no_lock_or_write(tmp_path, monkeypatch):
    from backend import services
    p = tmp_path / "envelope.json"
    p.write_text(json.dumps({"schema": REAL_PB.SCHEMA, "session_id": "fixture",
        "cap_units": 100, "opening_units": 0, "opening_evidence": "fixture",
        "calls": {}, "daily": {}, "blocked": None}), encoding="utf-8")
    before = p.read_bytes()
    monkeypatch.setenv("AEGIS_DEEPSEEK_BUDGET_PATH", str(p))
    monkeypatch.setattr(services, "provider_budget", REAL_PB)
    lock = Mock(side_effect=AssertionError("lock reached"))
    monkeypatch.setattr(REAL_PB, "_lock", lock)
    assert S._shared_budget_refusal() is None
    lock.assert_not_called()
    assert p.read_bytes() == before
    assert list(tmp_path.iterdir()) == [p]
