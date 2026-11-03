"""Offline sync state-machine and transmitted read-only program checks."""
import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
import os
import subprocess

import pytest
from scripts import sync_ic_funnel_once as S

IDS = ('8105f1ef-f39d-4a82-971e-e5d02db5ac8c',
       'c36ec00c-9250-494d-ae1c-3d07c2bcf60a',
       '05e102b9-b7ee-479d-9257-a506f74730d5')


@pytest.fixture
def setup(tmp_path):
    # Derived clock, away from protection interval regardless of test run time.
    now = datetime.now(timezone.utc).replace(hour=1, minute=0, second=0, microsecond=0)
    source = tmp_path / 'source.json'
    source.write_text(json.dumps({'generated_at': (now - timedelta(hours=1)).isoformat(),
                                'candidates': [{'ticker': 'TEST', 'price': 10,
                                                'median_dollar_vol': 1000,
                                                'vol_annual': .3}]}))
    state = tmp_path / 'state'
    return source, state, now


def forbidden(*a, **k):
    pytest.fail('unexpected transport')


def invoke(setup, **kw):
    source, state, now = setup
    return S.sync(source, IDS, state, clock=lambda: now, **kw)


def test_dry_run_no_network_no_state(setup, monkeypatch):
    monkeypatch.setattr(S.subprocess, 'run', forbidden)
    assert invoke(setup, inspect=forbidden, transfer=forbidden)['status'] == 'local_dry_run'
    assert not setup[1].exists()


@pytest.mark.parametrize('delta,reason', [(0, 'equal_stamp_conflict'), (1, 'remote_newer')])
def test_conflicting_remote_never_transfers(setup, delta, reason):
    meta = S.tx.validate(setup[0].read_bytes(), now=setup[2])
    remote = dict(meta, sha256='a' * 64,
                  generated_at=(datetime.fromisoformat(meta['generated_at']) + timedelta(hours=delta)).isoformat())
    with pytest.raises(S.tx.Refused, match=reason):
        invoke(setup, apply=True, inspect=lambda ids, **kw: remote, transfer=forbidden)
    assert not list(setup[1].glob('*.HOLD'))


def test_same_hash_no_write(setup):
    meta = S.tx.validate(setup[0].read_bytes(), now=setup[2])
    assert invoke(setup, apply=True, inspect=lambda ids, **kw: meta,
                  transfer=forbidden)['status'] == 'already_present'


@pytest.mark.parametrize('absent', [False, True])
def test_newer_uses_existing_cas_and_prearmed_hold(setup, absent):
    remote = {'sha256': 'ABSENT' if absent else 'a' * 64,
              'generated_at': (setup[2] - timedelta(days=2)).isoformat()}
    def transfer(raw, **kw):
        assert {k: kw[k] for k in ('project', 'environment', 'service', 'expected', 'apply')} == dict(
            project=IDS[0], environment=IDS[1], service=IDS[2],
            expected=remote['sha256'], apply=True)
        assert kw['commit_deadline'] == S.commit_deadline(setup[2])
        assert kw['clock']() == setup[2]
        assert raw == setup[0].read_bytes()
        assert len(list(setup[1].glob('*.HOLD'))) == 1
        return {'status': 'transferred', 'wrote': True}
    assert invoke(setup, apply=True, inspect=lambda ids, **kw: remote,
                  transfer=transfer)['wrote']
    assert not list(setup[1].glob('*.HOLD'))


@pytest.mark.parametrize('phase', ['inspect', 'transfer'])
def test_ambiguity_latches_and_only_exact_hash_reconciles(setup, phase):
    def fail(*a, **kw):
        raise S.tx.Refused('transport_unconfirmed')
    with pytest.raises(S.tx.Refused):
        invoke(setup, apply=True,
               inspect=fail if phase == 'inspect' else lambda ids, **kw: {'sha256': 'ABSENT'},
               transfer=fail)
    hold = next(setup[1].glob('*.HOLD'))
    assert set(json.loads(hold.read_text())) == {'sha256', 'target'}
    reads = []
    def inspect(ids, **kw):
        reads.append(kw)
        return {'sha256': 'ABSENT'}
    with pytest.raises(S.tx.Refused, match='hold_remote_mismatch'):
        invoke(setup, apply=True, inspect=inspect, transfer=forbidden)
    assert len(reads) == 1 and reads[0]['hash_only'] is True
    assert reads[0]['commit_deadline'] == S.commit_deadline(setup[2])
    assert hold.exists()
    assert invoke(setup, inspect=forbidden)['status'] == 'hold_no_network'
    sha = S.tx.digest(setup[0].read_bytes())
    assert invoke(setup, apply=True, inspect=lambda ids, **kw: {'sha256': sha},
                  transfer=forbidden)['status'] == 'hold_reconciled'
    assert not hold.exists()


def test_changed_local_under_hold_refuses_without_network(setup):
    def fail(*a, **kw):
        raise S.tx.Refused('inspection_unconfirmed')
    with pytest.raises(S.tx.Refused):
        invoke(setup, apply=True, inspect=fail)
    setup[0].write_text(setup[0].read_text().replace('TEST', 'OTHER'))
    with pytest.raises(S.tx.Refused, match='hold_local_or_target_changed'):
        invoke(setup, apply=True, inspect=forbidden, transfer=forbidden)


def test_stale_local_never_inspects(setup):
    source, state, now = setup
    obj = json.loads(source.read_text())
    obj['generated_at'] = (now - S.tx.MAX_AGE - timedelta(seconds=1)).isoformat()
    source.write_text(json.dumps(obj))
    with pytest.raises(S.tx.Refused, match='stale_source'):
        invoke(setup, apply=True, inspect=forbidden)
    assert not state.exists()


@pytest.mark.parametrize('hour,minute,second,blocked', [
    (16, 26, 44, False), (16, 26, 45, True), (16, 28, 54, True),
    (16, 30, 0, True), (17, 4, 0, True), (17, 5, 0, True),
    (17, 5, 1, False)])
def test_clock_budget_boundaries(setup, hour, minute, second, blocked):
    now = setup[2].astimezone(S.SGT).replace(hour=hour, minute=minute, second=second)
    deadline = S.commit_deadline(now)
    if blocked:
        with pytest.raises(S.tx.Refused, match='iif_protection_clock'):
            S.clock_guard(now, deadline, 120)
    else:
        S.clock_guard(now, deadline, 120)


def test_review_reproduction_162854_refuses_before_state_or_network(setup):
    late = setup[2].astimezone(S.SGT).replace(hour=16, minute=28, second=54)
    with pytest.raises(S.tx.Refused, match='iif_protection_clock'):
        S.sync(setup[0], IDS, setup[1], apply=True, clock=lambda: late,
               inspect=forbidden, transfer=forbidden)
    assert not setup[1].exists()


def test_clock_rechecked_before_transfer(setup):
    now = setup[2]
    later = now.astimezone(S.SGT).replace(hour=16, minute=30)
    clock = iter([now] * 7 + [later])
    with pytest.raises(S.tx.Refused, match='iif_protection_clock'):
        S.sync(setup[0], IDS, setup[1], apply=True, clock=lambda: next(clock),
               inspect=lambda ids, **kw: {'sha256': 'ABSENT'}, transfer=forbidden)
    assert not list(setup[1].glob('*.HOLD'))


def test_clock_jump_after_inspection_refuses_transfer(setup):
    now = setup[2]
    after = now.astimezone(S.SGT).replace(hour=16, minute=30)
    ticks = iter([now] * 5 + [after])
    with pytest.raises(S.tx.Refused, match='iif_protection_clock'):
        S.sync(setup[0], IDS, setup[1], apply=True, clock=lambda: next(ticks),
               inspect=lambda ids, **kw: {'sha256': 'ABSENT'}, transfer=forbidden)
    assert not list(setup[1].glob('*.HOLD'))


def test_clock_jump_inside_transfer_is_checked_again(setup):
    now = setup[2]
    after = now.astimezone(S.SGT).replace(hour=16, minute=30)
    ticks = iter([now] * 8 + [after])
    def transfer(raw, **kw):
        S.tx.guard_commit_deadline(kw['commit_deadline'], seconds=75, now=kw['clock']())
        pytest.fail('network launched')
    with pytest.raises(S.tx.Refused, match='iif_protection_clock'):
        S.sync(setup[0], IDS, setup[1], apply=True, clock=lambda: next(ticks),
               inspect=lambda ids, **kw: {'sha256': 'ABSENT'}, transfer=transfer)
    assert list(setup[1].glob('*.HOLD'))


def test_inspection_checks_clock_at_subprocess_boundary(setup, monkeypatch):
    monkeypatch.setattr(S.tx, 'resolve_railway', lambda: 'fake')
    before = setup[2].astimezone(S.SGT).replace(hour=16, minute=26)
    after = before.replace(hour=16, minute=30)
    with pytest.raises(S.tx.Refused, match='iif_protection_clock'):
        S.inspect_remote(IDS, commit_deadline=S.commit_deadline(before),
                         clock=lambda: after, run=forbidden)


def test_busy_lock_refuses(setup):
    state = setup[1]
    state.mkdir()
    key = S.tx.digest('|'.join(IDS).encode())
    (state / (key + '.lock')).touch()
    with pytest.raises(S.tx.Refused, match='state_busy_or_interrupted'):
        invoke(setup, apply=True, inspect=forbidden)


def test_bad_uuid_refuses_before_network(setup):
    with pytest.raises(S.tx.Refused, match='explicit_target_uuid_required'):
        S.sync(setup[0], ('project-name', *IDS[1:]), setup[1], apply=True,
               inspect=forbidden)


def test_state_directory_permissions_are_private(setup):
    state = setup[1]
    S.private_directory(state)
    if os.name != 'nt':
        assert state.stat().st_mode & 0o777 == 0o700
        return
    script = '''$ErrorActionPreference = 'Stop'
$p = [Console]::In.ReadToEnd() | ConvertFrom-Json
$acl = (New-Object System.IO.DirectoryInfo($p)).GetAccessControl()
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$rules = @($acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
if (!$acl.AreAccessRulesProtected -or $rules.Count -ne 1 -or $rules[0].IdentityReference.Value -ne $sid -or $rules[0].AccessControlType -ne 'Allow') { exit 2 }
'''
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                            input=json.dumps(str(state)).encode(), capture_output=True, timeout=10)
    assert result.returncode == 0


def test_local_validator_reused(setup):
    setup[0].write_bytes(b'{"generated_at": "invalid"}')
    with pytest.raises(S.tx.Refused, match='invalid_schema'):
        invoke(setup, apply=True, inspect=forbidden)


def test_stale_held_source_can_only_reconcile(setup):
    def fail(*a, **kw):
        raise S.tx.Refused('inspection_unconfirmed')
    with pytest.raises(S.tx.Refused):
        invoke(setup, apply=True, inspect=fail)
    sha = S.tx.digest(setup[0].read_bytes())
    def read(ids, **kw):
        assert kw['hash_only'] is True
        assert kw['commit_deadline'] == S.commit_deadline(setup[2] + timedelta(days=11))
        return {'sha256': sha}
    assert S.sync(setup[0], IDS, setup[1], apply=True,
                  clock=lambda: setup[2] + timedelta(days=11),
                  inspect=read, transfer=forbidden)['status'] == 'hold_reconciled'


def test_corrupt_hold_remains_and_refuses(setup):
    def fail(*a, **kw):
        raise S.tx.Refused('inspection_unconfirmed')
    with pytest.raises(S.tx.Refused):
        invoke(setup, apply=True, inspect=fail)
    hold = next(setup[1].glob('*.HOLD'))
    hold.write_text('broken')
    with pytest.raises(ValueError):
        invoke(setup, apply=True, inspect=forbidden, transfer=forbidden)
    assert hold.read_text() == 'broken'


@pytest.mark.parametrize('hash_only', [False, True])
def test_inspection_wire_executes_read_only(setup, monkeypatch, hash_only):
    monkeypatch.setattr(S.tx, 'resolve_railway', lambda: 'fake-railway')
    before = setup[0].read_bytes()
    def run(argv, **kw):
        assert argv == ['fake-railway', 'ssh', '--project', IDS[0], '--environment',
                        IDS[1], '--service', IDS[2], '--', 'python3', '-']
        assert kw['timeout'] == 60 and kw['shell'] is False
        assert before not in kw['input']
        ns = {'__name__': 'fake_remote'}
        # Redirect only fixed target and mount check; execute the real wire body.
        source, body = kw['input'].decode().split('\nif not os.path.ismount', 1)
        exec(source, ns)
        ns['TARGET'] = setup[0]
        monkeypatch.setattr(ns['os'].path, 'ismount', lambda p: True)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            exec('if not os.path.ismount' + body, ns)
        return subprocess.CompletedProcess(argv, 0, out.getvalue().encode(), b'private')
    result = S.inspect_remote(IDS, hash_only=hash_only, run=run)
    assert result['sha256'] == S.tx.digest(before)
    assert ('generated_at' in result) != hash_only
    assert setup[0].read_bytes() == before


@pytest.mark.parametrize('failure', ['timeout', 'exit', 'json', 'oversize'])
def test_inspection_errors_sanitized(monkeypatch, failure):
    monkeypatch.setattr(S.tx, 'resolve_railway', lambda: 'fake')
    def run(argv, **kw):
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(argv, 60, output=b'PRIVATE')
        return subprocess.CompletedProcess(argv, 1 if failure == 'exit' else 0,
                                           b'PRIVATE' * (1000 if failure == 'oversize' else 1), b'PRIVATE')
    with pytest.raises(S.tx.Refused, match='^inspection_unconfirmed$'):
        S.inspect_remote(IDS, run=run)
