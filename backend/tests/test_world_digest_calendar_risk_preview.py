"""Offline calendar sidecar integration; synthetic private inputs only."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import world_digest as S
from scripts import pre_event_owner_warning_discover as discovery
pytest_plugins = ["backend.tests.test_pre_event_owner_warning_discover"]


@pytest.fixture
def guarded(tmp_path, monkeypatch):
    monkeypatch.setattr(S.WD, 'stop_file', lambda: tmp_path / 'STOP')
    monkeypatch.setattr(S.WD, 'work_dir', lambda: tmp_path / 'digest')
    monkeypatch.setattr(S, '_host_budget_required', lambda: True)
    monkeypatch.setattr(S, '_shared_budget_refusal', lambda: 'SHARED_ENVELOPE_BLOCKED')
    guards = []
    for obj, name in [(S, '_balance'), (S.WD, 'collect'), (S.WD, 'Meter'),
                      (S.WD, 'extract_items')]:
        guard = Mock(side_effect=AssertionError('digest/provider reached'))
        monkeypatch.setattr(obj, name, guard)
        guards.append(guard)
    return guards


def args(kwargs):
    return SimpleNamespace(
        dry_run=False, calendar_risk_preview=True,
        calendar_risk_receipt_dir=kwargs['receipt_dir'],
        calendar_risk_journal_dir=kwargs['journal_dir'],
        calendar_risk_ledger_dir=kwargs['ledger_dir'],
        calendar_risk_account_sha256=kwargs['expected_account_sha256'])


def test_default_off_unchanged(guarded, monkeypatch, capsys):
    preview = Mock(side_effect=AssertionError('sidecar reached'))
    monkeypatch.setattr(S, '_calendar_risk_preview', preview)
    assert S.run(SimpleNamespace(dry_run=False)) == 2
    preview.assert_not_called()
    assert 'CALENDAR_RISK_PREVIEW' not in capsys.readouterr().out


def test_budget_refusal_keeps_real_preview_and_ids(case, guarded, capsys):
    kwargs, save = case
    save()
    before = {p: p.read_bytes() for root in ('receipt_dir', 'journal_dir', 'ledger_dir')
              for p in kwargs[root].rglob('*') if p.is_file()}
    assert S.run(args(kwargs)) == 2
    lines = capsys.readouterr().out.splitlines()
    result = json.loads(lines[0].removeprefix('CALENDAR_RISK_PREVIEW '))
    assert result['delivery'] == 'PREVIEW'
    for key in ('event_id', 'receipt_id', 'decision_id'):
        assert result[key]
    assert 'shared budget preflight' in lines[1]
    assert all(p.read_bytes() == data for p, data in before.items())
    assert not list(kwargs['journal_dir'].iterdir())
    for guard in guarded:
        guard.assert_not_called()


@pytest.mark.parametrize('bad', ['missing', 'relative', 'pin', 'nonexistent'])
def test_private_inputs_refuse_before_discovery(case, guarded, monkeypatch, capsys, bad):
    kwargs, _ = case
    a = args(kwargs)
    if bad == 'missing':
        a.calendar_risk_receipt_dir = None
    elif bad == 'relative':
        a.calendar_risk_receipt_dir = type(kwargs['receipt_dir'])('relative')
    elif bad == 'pin':
        a.calendar_risk_account_sha256 = 'invalid'
    else:
        a.calendar_risk_ledger_dir = kwargs['ledger_dir'] / 'absent'
    discover = Mock(side_effect=AssertionError('discovery reached'))
    monkeypatch.setattr(discovery, 'run', discover)
    assert S.run(a) == 2
    discover.assert_not_called()
    assert 'PRIVATE_INPUTS_REQUIRED' in capsys.readouterr().out
    for guard in guarded:
        guard.assert_not_called()


def test_no_candidate_is_refusal(case, guarded, capsys):
    kwargs, _ = case
    assert S.run(args(kwargs)) == 2
    result = json.loads(capsys.readouterr().out.splitlines()[0].split(' ', 1)[1])
    assert result['status'] == 'REFUSED'
    assert result['reason'] == 'NO_SAVED_RECEIPT'
    for guard in guarded:
        guard.assert_not_called()


def test_send_authority_cannot_be_forwarded(case, guarded, monkeypatch):
    kwargs, _ = case
    a = args(kwargs)
    a.send = True
    a.review = 'untrusted'
    run = Mock(return_value=(0, {'status': 'PROVISIONAL', 'delivery': 'PREVIEW'}))
    monkeypatch.setattr(discovery, 'run', run)
    assert S.run(a) == 2
    assert run.call_args.kwargs['send'] is False
    assert 'review' not in run.call_args.kwargs


def test_unexpected_error_is_nonsecret_refusal(case, guarded, monkeypatch, capsys):
    kwargs, _ = case
    monkeypatch.setattr(discovery, 'run', Mock(side_effect=RuntimeError('PRIVATE_PATH')))
    assert S.run(args(kwargs)) == 2
    output = capsys.readouterr().out
    assert 'CALENDAR_RISK_PREVIEW_FAILED' in output and 'PRIVATE_PATH' not in output


def test_cli_opt_in_and_private_inputs(case, guarded, monkeypatch):
    kwargs, _ = case
    monkeypatch.setattr(S, '_ensure_streams', lambda: None)
    run = Mock(return_value=0)
    monkeypatch.setattr(S, 'run', run)
    options = ['--calendar-risk-preview']
    for name in ('receipt-dir', 'journal-dir', 'ledger-dir'):
        options.extend(['--calendar-risk-' + name, str(kwargs[name.replace('-', '_')])])
    options.extend(['--calendar-risk-account-sha256', kwargs['expected_account_sha256']])
    assert S.main(options) == 0
    parsed = run.call_args.args[0]
    assert parsed.calendar_risk_preview is True
    assert parsed.calendar_risk_receipt_dir == kwargs['receipt_dir']
    assert parsed.calendar_risk_account_sha256 == kwargs['expected_account_sha256']
