"""Offline calendar sidecar integration; synthetic private inputs only."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import world_digest as S
from scripts import pre_event_owner_warning_discover as discovery
from backend.tests.test_pre_event_owner_warning_discover import case as calendar_case


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
    output = kwargs['receipt_dir'].parent / 'private-preview'
    output.mkdir(exist_ok=True)
    return SimpleNamespace(
        dry_run=False, calendar_risk_preview=True,
        calendar_risk_output_dir=output,
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


def test_budget_refusal_keeps_real_preview_and_ids(calendar_case, guarded, capsys, monkeypatch):
    kwargs, save = calendar_case
    save()
    original = discovery.run
    monkeypatch.setattr(discovery, 'run', lambda **options: original(**options, now=kwargs['now']))
    original_once = discovery.once.run
    monkeypatch.setattr(discovery.once, 'run', lambda **options: original_once(
        **options, wall_clock=lambda: kwargs['now'], epoch_clock=lambda: kwargs['now'].timestamp()))
    before = {p: p.read_bytes() for root in ('receipt_dir', 'journal_dir', 'ledger_dir')
              for p in kwargs[root].rglob('*') if p.is_file()}
    assert S.run(args(kwargs)) == 2
    lines = capsys.readouterr().out.splitlines()
    result = json.loads(lines[0].removeprefix('CALENDAR_RISK_PREVIEW '))
    assert set(result) == {'status', 'receipt_id'}
    assert result['status'] == 'PREVIEW'
    saved = json.loads((args(kwargs).calendar_risk_output_dir / (result['receipt_id'] + '.json')).read_text())
    result = saved['result']
    assert result['delivery'] == 'PREVIEW'
    for key in ('event_id', 'receipt_id', 'decision_id'):
        assert result[key]
    assert 'shared budget preflight' in lines[1]
    assert all(p.read_bytes() == data for p, data in before.items())
    assert not list(kwargs['journal_dir'].iterdir())
    for guard in guarded:
        guard.assert_not_called()


@pytest.mark.parametrize('bad', ['missing', 'relative', 'pin', 'nonexistent'])
def test_private_inputs_refuse_before_discovery(calendar_case, guarded, monkeypatch, capsys, bad):
    kwargs, _ = calendar_case
    a = args(kwargs)
    if bad == 'missing':
        a.calendar_risk_receipt_dir = None
    elif bad == 'relative':
        a.calendar_risk_receipt_dir = type(kwargs['receipt_dir'])('relative')
    elif bad == 'pin':
        a.calendar_risk_account_sha256 = 'invalid'
    else:
        a.calendar_risk_ledger_dir = kwargs['ledger_dir'] / 'absent'
    discover = Mock(return_value=(2, {'status': 'REFUSED', 'delivery': 'NOT_SENT'}))
    monkeypatch.setattr(discovery, 'run', discover)
    assert S.run(a) == 2
    if bad != 'flush':
        discover.assert_not_called()
    lines = capsys.readouterr().out.splitlines()
    safe = json.loads(lines[0].split(' ', 1)[1])
    saved = json.loads((a.calendar_risk_output_dir / (safe['receipt_id'] + '.json')).read_text())
    assert saved['result']['reason'] == 'PRIVATE_INPUTS_REQUIRED'
    assert 'shared budget preflight' in lines[1]
    for guard in guarded:
        guard.assert_not_called()


def test_no_candidate_is_refusal(calendar_case, guarded, capsys):
    kwargs, _ = calendar_case
    assert S.run(args(kwargs)) == 2
    result = json.loads(capsys.readouterr().out.splitlines()[0].split(' ', 1)[1])
    assert result['status'] == 'REFUSED'
    saved = json.loads((args(kwargs).calendar_risk_output_dir / (result['receipt_id'] + '.json')).read_text())
    assert saved['result']['reason'] == 'NO_SAVED_RECEIPT'
    for guard in guarded:
        guard.assert_not_called()


def test_send_authority_cannot_be_forwarded(calendar_case, guarded, monkeypatch):
    kwargs, _ = calendar_case
    a = args(kwargs)
    a.send = True
    a.review = 'untrusted'
    run = Mock(return_value=(0, {'status': 'PROVISIONAL', 'delivery': 'PREVIEW'}))
    monkeypatch.setattr(discovery, 'run', run)
    assert S.run(a) == 2
    assert run.call_args.kwargs['send'] is False
    assert 'review' not in run.call_args.kwargs


def test_unexpected_error_is_nonsecret_refusal(calendar_case, guarded, monkeypatch, capsys):
    kwargs, _ = calendar_case
    monkeypatch.setattr(discovery, 'run', Mock(side_effect=RuntimeError('PRIVATE_PATH')))
    assert S.run(args(kwargs)) == 2
    output = capsys.readouterr().out
    assert 'PRIVATE_PATH' not in output
    safe = json.loads(output.splitlines()[0].split(' ', 1)[1])
    saved = json.loads((args(kwargs).calendar_risk_output_dir / (safe['receipt_id'] + '.json')).read_text())
    assert saved['result']['reason'] == 'CALENDAR_RISK_PREVIEW_FAILED'
    assert 'shared budget preflight' in output


def test_cli_opt_in_and_private_inputs(calendar_case, guarded, monkeypatch):
    kwargs, _ = calendar_case
    monkeypatch.setattr(S, '_ensure_streams', lambda: None)
    run = Mock(return_value=0)
    monkeypatch.setattr(S, 'run', run)
    options = ['--calendar-risk-preview', '--calendar-risk-output-dir',
               str(args(kwargs).calendar_risk_output_dir)]
    for name in ('receipt-dir', 'journal-dir', 'ledger-dir'):
        options.extend(['--calendar-risk-' + name, str(kwargs[name.replace('-', '_')])])
    options.extend(['--calendar-risk-account-sha256', kwargs['expected_account_sha256']])
    assert S.main(options) == 0
    parsed = run.call_args.args[0]
    assert parsed.calendar_risk_preview is True
    assert parsed.calendar_risk_receipt_dir == kwargs['receipt_dir']
    assert parsed.calendar_risk_account_sha256 == kwargs['expected_account_sha256']


def test_stop_precedes_preview(calendar_case, guarded, monkeypatch, capsys):
    kwargs, _ = calendar_case
    S.WD.stop_file().touch()
    preview = Mock(side_effect=AssertionError('preview reached'))
    budget = Mock(side_effect=AssertionError('budget reached'))
    monkeypatch.setattr(S, '_calendar_risk_preview', preview)
    monkeypatch.setattr(S, '_shared_budget_refusal', budget)
    a = args(kwargs)
    assert S.run(a) == 0
    preview.assert_not_called()
    budget.assert_not_called()
    assert capsys.readouterr().out.strip() == 'STOPPED: STOP file present'
    receipts = list((S.WD.work_dir() / 'receipts').glob('run_*.json'))
    assert len(receipts) == 1
    assert json.loads(receipts[0].read_text())['state'] == 'STOPPED: STOP file present'
    assert not list(a.calendar_risk_output_dir.iterdir())


@pytest.mark.parametrize('bad', ['missing', 'relative', 'file', 'validation', 'write', 'flush'])
def test_output_failure_safe_and_digest_continues(calendar_case, guarded, monkeypatch, capsys, bad):
    kwargs, _ = calendar_case
    a = args(kwargs)
    if bad == 'missing':
        a.calendar_risk_output_dir = None
    elif bad == 'relative':
        a.calendar_risk_output_dir = type(kwargs['receipt_dir'])('relative')
    elif bad == 'file':
        a.calendar_risk_output_dir = kwargs['ledger_dir'] / 'secret-file'
        a.calendar_risk_output_dir.touch()
    elif bad == 'validation':
        monkeypatch.setattr(discovery.once.capture, '_private_identity',
                            Mock(side_effect=ValueError('PRIVATE_PATH')))
    elif bad == 'flush':
        monkeypatch.setattr(S.os, 'fsync', Mock(side_effect=OSError('PRIVATE_PATH')))
    else:
        original = type(kwargs['receipt_dir']).open
        def fail_preview(path, *options, **kw):
            if path.parent == a.calendar_risk_output_dir:
                raise OSError('PRIVATE_PATH')
            return original(path, *options, **kw)
        monkeypatch.setattr(type(kwargs['receipt_dir']), 'open', fail_preview)
    discover = Mock(return_value=(2, {'status': 'REFUSED', 'delivery': 'NOT_SENT'}))
    monkeypatch.setattr(discovery, 'run', discover)
    assert S.run(a) == 2
    if bad != 'flush':
        discover.assert_not_called()
    lines = capsys.readouterr().out.splitlines()
    assert json.loads(lines[0].split(' ', 1)[1]) == {
        'status': 'REFUSED_OUTPUT_UNAVAILABLE', 'receipt_id': None}
    assert 'shared budget preflight' in lines[1]
    assert 'PRIVATE_PATH' not in '\n'.join(lines)
    if a.calendar_risk_output_dir is not None and a.calendar_risk_output_dir.is_dir():
        assert not list(a.calendar_risk_output_dir.iterdir())


def test_preview_receipts_are_exclusive_and_logs_are_safe(calendar_case, guarded, monkeypatch, capsys):
    kwargs, _ = calendar_case
    output = {'status': 'PROVISIONAL', 'delivery': 'PREVIEW',
              'equity': 1234567, 'path': 'PRIVATE_PATH', 'event_id': 'PRIVATE_EVENT'}
    monkeypatch.setattr(discovery, 'run', Mock(return_value=(0, output)))
    a = args(kwargs)
    assert S.run(a) == 2
    assert S.run(a) == 2
    receipts = list(a.calendar_risk_output_dir.glob('calendar-risk-preview-*.json'))
    assert len(receipts) == 2
    for path in receipts:
        saved = json.loads(path.read_text())
        assert saved['result'] == output
        assert path.stem == saved['receipt_id']
        assert saved['stamp'] in path.name
    log = capsys.readouterr().out
    for secret in ('1234567', 'PRIVATE_PATH', 'PRIVATE_EVENT', str(a.calendar_risk_output_dir)):
        assert secret not in log


@pytest.mark.parametrize('name', ['receipt_dir', 'journal_dir', 'ledger_dir'])
@pytest.mark.parametrize('kind', ['same', 'child', 'parent', 'alias', 'symlink'])
def test_output_cannot_overlap_inputs(calendar_case, guarded, monkeypatch, capsys, name, kind):
    kwargs, _ = calendar_case
    a = args(kwargs)
    root = kwargs[name]
    if kind == 'same':
        output = root
    elif kind == 'child':
        output = root / 'preview'
        output.mkdir()
    elif kind == 'parent':
        output = root.parent
    elif kind == 'alias':
        output = root / '..' / root.name
    else:
        output = root.parent / 'alias-output'
        try:
            output.symlink_to(root, target_is_directory=True)
        except OSError:
            pytest.skip('directory symlinks unavailable')
    a.calendar_risk_output_dir = output
    before = set(root.parent.rglob('*'))
    discover = Mock(side_effect=AssertionError('discovery reached'))
    monkeypatch.setattr(discovery, 'run', discover)
    assert S.run(a) == 2
    discover.assert_not_called()
    assert set(root.parent.rglob('*')) - before <= {
        S.WD.work_dir(), *S.WD.work_dir().rglob('*')}
    safe = json.loads(capsys.readouterr().out.splitlines()[0].split(' ', 1)[1])
    assert safe == {'status': 'REFUSED_OUTPUT_UNAVAILABLE', 'receipt_id': None}


@pytest.mark.parametrize('failure', ['partial', 'fsync', 'root', 'publish'])
def test_failed_persistence_never_publishes(calendar_case, guarded, monkeypatch, capsys, failure):
    kwargs, _ = calendar_case
    a = args(kwargs)
    monkeypatch.setattr(discovery, 'run', Mock(return_value=(0, {
        'status': 'PROVISIONAL', 'delivery': 'PREVIEW'})))
    if failure == 'partial':
        original = S.json.dump
        def partial(value, stream, **options):
            if str(stream.name).endswith('.pending'):
                stream.write('{"partial":')
                raise OSError('PRIVATE_PATH')
            return original(value, stream, **options)
        monkeypatch.setattr(S.json, 'dump', partial)
    elif failure == 'fsync':
        monkeypatch.setattr(S.os, 'fsync', Mock(side_effect=OSError('PRIVATE_PATH')))
    elif failure == 'root':
        original = discovery.once.capture._private_identity
        calls = 0
        def changed(path):
            nonlocal calls
            result = original(path)
            if path == a.calendar_risk_output_dir:
                calls += 1
                if calls >= 3:
                    return (-1, -1)
            return result
        monkeypatch.setattr(discovery.once.capture, '_private_identity', changed)
    else:
        monkeypatch.setattr(S.os, 'link', Mock(side_effect=OSError('PRIVATE_PATH')))
    assert S.run(a) == 2
    assert not list(a.calendar_risk_output_dir.iterdir())
    log = capsys.readouterr().out
    assert 'PRIVATE_PATH' not in log
    assert 'REFUSED_OUTPUT_UNAVAILABLE' in log
    assert 'shared budget preflight' in log


def test_uuid_collision_preserves_existing_receipt(calendar_case, guarded, monkeypatch, capsys):
    import uuid
    kwargs, _ = calendar_case
    a = args(kwargs)
    monkeypatch.setattr(uuid, 'uuid4', lambda: SimpleNamespace(hex='fixed'))
    monkeypatch.setattr(discovery, 'run', Mock(return_value=(0, {
        'status': 'PROVISIONAL', 'delivery': 'PREVIEW'})))
    # Freeze the receipt timestamp as well as the UUID.
    real_datetime = S.datetime
    frozen = real_datetime.now(S.timezone.utc)
    monkeypatch.setattr(S, 'datetime', SimpleNamespace(now=lambda tz: frozen))
    assert S.run(a) == 2
    receipt, = a.calendar_risk_output_dir.iterdir()
    original = receipt.read_bytes()
    assert S.run(a) == 2
    assert receipt.read_bytes() == original
    assert list(a.calendar_risk_output_dir.iterdir()) == [receipt]
    assert 'REFUSED_OUTPUT_UNAVAILABLE' in capsys.readouterr().out


def test_replaced_root_after_fsync_has_no_final_receipt(calendar_case, guarded, monkeypatch, capsys):
    kwargs, _ = calendar_case
    a = args(kwargs)
    moved = a.calendar_risk_output_dir.with_name('moved-preview')
    original = S.os.fsync
    def replace_root(fd):
        original(fd)
        a.calendar_risk_output_dir.rename(moved)
        a.calendar_risk_output_dir.mkdir()
    monkeypatch.setattr(S.os, 'fsync', replace_root)
    monkeypatch.setattr(discovery, 'run', Mock(return_value=(0, {
        'status': 'PROVISIONAL', 'delivery': 'PREVIEW'})))
    assert S.run(a) == 2
    assert not list(a.calendar_risk_output_dir.iterdir())
    assert not list(moved.glob('*.json'))
    assert 'REFUSED_OUTPUT_UNAVAILABLE' in capsys.readouterr().out


def test_output_failure_reaches_normal_digest_collection(calendar_case, guarded, monkeypatch):
    from backend.services import disk_guard
    kwargs, _ = calendar_case
    a = args(kwargs)
    a.calendar_risk_output_dir = kwargs['receipt_dir']
    a.dry_run = True
    a.hours = 24
    monkeypatch.setattr(disk_guard, 'require_free', Mock())
    class CollectionReached(Exception):
        pass
    collect = Mock(side_effect=CollectionReached)
    monkeypatch.setattr(S.WD, 'collect', collect)
    with pytest.raises(CollectionReached):
        S.run(a)
    collect.assert_called_once()
