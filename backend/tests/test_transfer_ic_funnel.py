"""All SSH is fake; filesystem transactions are confined to pytest tmp_path."""
import ast
import contextlib
import io
import base64
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import types

import pytest
from scripts import transfer_ic_funnel as T


def payload(days=0, price=10):
    return json.dumps({'generated_at': (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(),
                       'candidates': [{'ticker': 'TEST', 'price': price,
                                       'median_dollar_vol': 1000, 'vol_annual': .3}]}).encode()


@pytest.fixture(autouse=True)
def fake_railway_path(monkeypatch):
    monkeypatch.setattr(T.shutil, 'which', lambda name: str(Path('fake tools') / name))


@pytest.fixture
def remote(tmp_path, monkeypatch):
    # Emulate Linux directory locking/fd operations on Windows, preserving real
    # file writes, fsync of staged files, os.replace and cleanup operations.
    monkeypatch.setitem(sys.modules, 'fcntl', types.SimpleNamespace(LOCK_EX=2, LOCK_NB=4, flock=lambda *a: None))
    monkeypatch.setattr(os, 'O_DIRECTORY', 0, raising=False)
    monkeypatch.setattr(os, 'O_NOFOLLOW', 0, raising=False)
    original_open, original_close, original_sync = os.open, os.close, os.fsync
    monkeypatch.setattr(os, 'open', lambda p, *a, **kw: 999999 if Path(p) == tmp_path else original_open(p, *a, **kw))
    monkeypatch.setattr(os, 'close', lambda fd: None if fd == 999999 else original_close(fd))
    monkeypatch.setattr(os, 'fsync', lambda fd: None if fd == 999999 else original_sync(fd))
    monkeypatch.setattr(os.path, 'ismount', lambda p: p == '/data')
    return tmp_path / 'funnel_night10.json'


def fake_ssh(target, before=None):
    def run(argv, **kw):
        assert argv == [T.resolve_railway(), 'ssh', '--project', '8105f1ef-f39d-4a82-971e-e5d02db5ac8c', '--environment', 'c36ec00c-9250-494d-ae1c-3d07c2bcf60a',
                        '--service', '05e102b9-b7ee-479d-9257-a506f74730d5', '--', 'python3', '-']
        assert kw['shell'] is False and kw['timeout'] == 60
        tree = ast.parse(kw['input'].decode())
        call = tree.body[-1].value
        assert call.func.id == 'remote_entry'
        encoded, expected, apply = [ast.literal_eval(arg) for arg in call.args]
        assert base64.b64decode(encoded)
        assert encoded not in ' '.join(argv)
        if before:
            before()
        # Execute exactly the transmitted program, with only its filesystem
        # destination redirected into the fixture. Never launch real Railway.
        namespace = {'__name__': 'fake_remote'}
        exec(compile(ast.Module(body=tree.body[:-1], type_ignores=[]), '<wire>', 'exec'), namespace)
        namespace['receive'].__kwdefaults__['target'] = target
        output = io.StringIO()
        rc = 0
        with contextlib.redirect_stdout(output):
            try:
                exec(compile(ast.Module(body=[tree.body[-1]], type_ignores=[]), '<wire>', 'exec'), namespace)
            except SystemExit as exc:
                rc = exc.code
        return subprocess.CompletedProcess(argv, rc, output.getvalue().encode(), b'private transport details')
    return run


def send(raw, target, expected='ABSENT', **kw):
    return T.transfer(raw, project='8105f1ef-f39d-4a82-971e-e5d02db5ac8c', environment='c36ec00c-9250-494d-ae1c-3d07c2bcf60a', service='05e102b9-b7ee-479d-9257-a506f74730d5',
                      expected=expected, apply=True, run=fake_ssh(target, **kw))


def test_default_dry_run_never_spawns_or_writes(tmp_path):
    def forbidden(*a, **k):
        pytest.fail('dry run spawned SSH')
    assert T.transfer(payload(), project=None, environment=None, service=None,
                      expected=None, run=forbidden)['status'] == 'local_dry_run'
    assert list(tmp_path.iterdir()) == []


def test_cli_defaults_dry_run(tmp_path, capsys):
    source = tmp_path / 'source.json'
    source.write_bytes(payload())
    assert T.main([str(source)]) == 0
    assert json.loads(capsys.readouterr().out)['wrote'] is False
    assert list(tmp_path.iterdir()) == [source]


def test_success_exact_bytes_and_idempotence(remote):
    raw = payload()
    assert send(raw, remote)['wrote'] is True
    assert remote.read_bytes() == raw
    assert send(raw, remote, T.digest(raw))['status'] == 'already_present'
    assert list(remote.parent.iterdir()) == [remote]


def test_remote_newer_refuses_rollback(remote):
    last = payload()
    remote.write_bytes(last)
    with pytest.raises(T.Refused):
        send(payload(days=1), remote, T.digest(last))
    assert remote.read_bytes() == last


def test_equal_stamp_different_hash_refused(remote):
    raw = payload()
    remote.write_bytes(raw)
    changed = json.loads(raw)
    changed['candidates'][0]['price'] = 20
    with pytest.raises(T.Refused):
        send(json.dumps(changed).encode(), remote, T.digest(raw))
    assert remote.read_bytes() == raw


def test_changed_remote_compare_and_swap_refused(remote):
    with pytest.raises(T.Refused):
        send(payload(), remote, before=lambda: remote.write_bytes(payload(days=1)))
    assert T.validate(remote.read_bytes())['generated_at']
    assert len(list(remote.parent.iterdir())) == 1


def test_failed_atomic_replace_keeps_last_good(remote, monkeypatch):
    old = payload(days=1)
    remote.write_bytes(old)
    def fail(*args):
        raise OSError('private failure')
    monkeypatch.setattr(os, 'replace', fail)
    with pytest.raises(T.Refused):
        send(payload(), remote, T.digest(old))
    assert remote.read_bytes() == old
    assert list(remote.parent.iterdir()) == [remote]


def test_remote_dry_run_no_write(remote):
    assert T.receive(payload(), 'ABSENT', target=remote)['wrote'] is False
    assert list(remote.parent.iterdir()) == []


def test_invalid_last_good_is_preserved(remote):
    remote.write_bytes(b'bad last good')
    with pytest.raises(T.Refused):
        send(payload(), remote, T.digest(remote.read_bytes()))
    assert remote.read_bytes() == b'bad last good'


@pytest.mark.parametrize('raw', [b'{}', b'[]', b'{"x":1,"x":2}', b'x' * (T.MAX_BYTES + 1), payload(days=11), payload(price=0)], ids=['empty-object', 'array', 'duplicate-key', 'oversized', 'stale', 'zero-price'])
def test_invalid_source_never_calls_ssh(raw):
    with pytest.raises(T.Refused):
        T.transfer(raw, project=None, environment=None, service=None, expected=None,
                   apply=True, run=lambda *a, **kw: pytest.fail('invalid source reached SSH'))


@pytest.mark.parametrize('mutation', [
    lambda o: o.update(generated_at='2026-01-01T00:00:00'),
    lambda o: o.update(generated_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat()),
    lambda o: o.update(candidates=[]),
    lambda o: o['candidates'].append(o['candidates'][0]),
    lambda o: o['candidates'][0].update(vol_annual=float('nan')),
    lambda o: o['candidates'][0].update(ticker='bad;cmd'),
])
def test_schema_failures(mutation):
    obj = json.loads(payload())
    mutation(obj)
    with pytest.raises(T.Refused):
        T.validate(json.dumps(obj).encode())


def test_timeout_sanitized():
    def timeout(*a, **kw):
        raise subprocess.TimeoutExpired('private', 60, output=b'secret')
    with pytest.raises(T.Refused, match='^transport_unconfirmed$'):
        T.transfer(payload(), project='8105f1ef-f39d-4a82-971e-e5d02db5ac8c', environment='c36ec00c-9250-494d-ae1c-3d07c2bcf60a', service='05e102b9-b7ee-479d-9257-a506f74730d5',
                   expected='ABSENT', apply=True, run=timeout)


def test_config_path_remains_policy_pinned_with_cloud_data_dir(tmp_path):
    # Evaluate the real config in a fresh process with dotenv disabled: no local
    # .env or module reload can contaminate the result. The Docker image binds
    # this path to the Railway volume without changing the frozen Python source.
    root = Path(__file__).resolve().parents[2]
    code = ('import runpy,sys,types; sys.modules["dotenv"]=types.SimpleNamespace(load_dotenv=lambda *a,**k:None); '
            'c=runpy.run_path("backend/config.py"); '
            'assert c["IC_FUNNEL_PATH"] == c["BACKEND_DIR"] / "data/funnel_night10.json"; '
            'print(c["IC_FUNNEL_PATH"])')
    env = os.environ.copy()
    env.pop('AEGIS_REPO_ROOT', None)
    env.pop('AEGIS_DATA_DIR', None)
    local = subprocess.run([sys.executable, '-c', code], cwd=root, env=env, capture_output=True, text=True)
    assert local.returncode == 0, local.stderr
    assert Path(local.stdout.strip()) == root / 'backend/data/funnel_night10.json'
    env['AEGIS_DATA_DIR'] = str(tmp_path)
    cloud = subprocess.run([sys.executable, '-c', code], cwd=root, env=env, capture_output=True, text=True)
    assert cloud.returncode == 0, cloud.stderr
    assert Path(cloud.stdout.strip()) == root / 'backend/data/funnel_night10.json'


def test_mount_missing_never_writes(remote, monkeypatch):
    monkeypatch.setattr(os.path, 'ismount', lambda p: False)
    with pytest.raises(T.Refused):
        send(payload(), remote)
    assert list(remote.parent.iterdir()) == []


def test_failed_stage_fsync_keeps_last_good(remote, monkeypatch):
    last = payload(days=1)
    remote.write_bytes(last)
    def fail(fd):
        raise OSError('secret detail')
    monkeypatch.setattr(os, 'fsync', fail)
    with pytest.raises(T.Refused):
        send(payload(), remote, T.digest(last))
    assert remote.read_bytes() == last
    assert list(remote.parent.iterdir()) == [remote]


def test_missing_expected_refuses_before_ssh():
    with pytest.raises(T.Refused, match='expected_remote_required'):
        T.transfer(payload(), project='8105f1ef-f39d-4a82-971e-e5d02db5ac8c', environment='c36ec00c-9250-494d-ae1c-3d07c2bcf60a', service='05e102b9-b7ee-479d-9257-a506f74730d5',
                   expected=None, apply=True, run=lambda *a, **kw: pytest.fail('spawned'))


def test_cli_failure_receipt_is_sanitized(tmp_path, capsys):
    source = tmp_path / 'private-name.json'
    source.write_bytes(b'private invalid payload')
    assert T.main([str(source)]) == 2
    receipt = json.loads(capsys.readouterr().out)
    assert receipt == {'status': 'refused_or_unconfirmed', 'reason': 'invalid_schema'}


def test_missing_volume_ic_reports_degraded(tmp_path, monkeypatch):
    from backend import config
    from backend.services import investment_committee as IC
    monkeypatch.setattr(config, 'IC_FUNNEL_PATH', tmp_path / 'funnel_night10.json')
    health = IC.ic_health()
    assert health['status'] == 'DEGRADED'
    assert health['funnel_available'] is False


def test_busy_remote_lock_no_write(remote, monkeypatch):
    def busy(*args):
        raise BlockingIOError('busy')
    monkeypatch.setattr(sys.modules['fcntl'], 'flock', busy)
    with pytest.raises(T.Refused):
        send(payload(), remote)
    assert list(remote.parent.iterdir()) == []


def test_mismatched_remote_receipt_is_refused():
    def bad_receipt(argv, **kw):
        return subprocess.CompletedProcess(argv, 0, b'{"status":"transferred","sha256":"bad"}', b'')
    with pytest.raises(T.Refused):
        T.transfer(payload(), project='8105f1ef-f39d-4a82-971e-e5d02db5ac8c', environment='c36ec00c-9250-494d-ae1c-3d07c2bcf60a', service='05e102b9-b7ee-479d-9257-a506f74730d5',
                   expected='ABSENT', apply=True, run=bad_receipt)


def test_transport_failure_does_not_leak_output():
    def failure(argv, **kw):
        return subprocess.CompletedProcess(argv, 2, b'private payload', b'private credential')
    with pytest.raises(T.Refused, match='^remote_refused_or_unconfirmed$'):
        T.transfer(payload(), project='8105f1ef-f39d-4a82-971e-e5d02db5ac8c', environment='c36ec00c-9250-494d-ae1c-3d07c2bcf60a', service='05e102b9-b7ee-479d-9257-a506f74730d5',
                   expected='ABSENT', apply=True, run=failure)


@pytest.mark.parametrize('platform,names,available', [
    ('win32', ['railway.exe', 'railway.cmd'], 'railway.cmd'),
    ('win32', ['railway.exe'], 'railway.exe'),
    ('linux', ['railway'], 'railway'),
])
def test_explicit_executable_resolution(platform, names, available, tmp_path, monkeypatch):
    executable = tmp_path / 'tools with spaces' / available
    executable.parent.mkdir()
    executable.write_text('fake executable')
    searched = []
    def which(name):
        searched.append(name)
        return str(executable) if name == available else None
    monkeypatch.setattr(T.sys, 'platform', platform)
    monkeypatch.setattr(T.shutil, 'which', which)
    assert T.resolve_railway() == str(executable.resolve())
    assert searched == names


def test_windows_cmd_only_transport_uses_resolved_path(remote, tmp_path, monkeypatch):
    shim = tmp_path / 'npm tools with spaces' / 'railway.cmd'
    shim.parent.mkdir()
    shim.write_text('@echo off')
    monkeypatch.setattr(T.sys, 'platform', 'win32')
    monkeypatch.setattr(T.shutil, 'which', lambda name: str(shim) if name == 'railway.cmd' else None)
    fake = fake_ssh(remote)
    def run(argv, **kwargs):
        assert argv[0] == str(shim.resolve())
        assert kwargs['shell'] is False
        return fake(argv, **kwargs)
    assert T.transfer(payload(), project='8105f1ef-f39d-4a82-971e-e5d02db5ac8c', environment='c36ec00c-9250-494d-ae1c-3d07c2bcf60a', service='05e102b9-b7ee-479d-9257-a506f74730d5',
                      expected='ABSENT', apply=True, run=run)['wrote'] is True


def test_missing_executable_refuses_without_spawn(monkeypatch):
    monkeypatch.setattr(T.shutil, 'which', lambda name: None)
    with pytest.raises(T.Refused, match='^railway_executable_missing$'):
        T.transfer(payload(), project='8105f1ef-f39d-4a82-971e-e5d02db5ac8c', environment='c36ec00c-9250-494d-ae1c-3d07c2bcf60a', service='05e102b9-b7ee-479d-9257-a506f74730d5',
                   expected='ABSENT', apply=True, run=lambda *a, **kw: pytest.fail('spawned'))


def test_dry_run_does_not_resolve_executable(monkeypatch):
    def forbidden(name):
        pytest.fail('dry run tried executable resolution')
    monkeypatch.setattr(T.shutil, 'which', forbidden)
    assert T.transfer(payload(), project=None, environment=None, service=None,
                      expected=None)['status'] == 'local_dry_run'


def test_cli_parses_native_target_ids_without_ssh(tmp_path, monkeypatch, capsys):
    source = tmp_path / 'source.json'
    raw = payload()
    source.write_bytes(raw)
    def transfer(data, **kwargs):
        assert data == raw
        assert kwargs == dict(project='8105f1ef-f39d-4a82-971e-e5d02db5ac8c',
                              environment='c36ec00c-9250-494d-ae1c-3d07c2bcf60a',
                              service='05e102b9-b7ee-479d-9257-a506f74730d5',
                              expected='ABSENT', apply=True)
        return {'status': 'fake_transport_only', 'wrote': False}
    monkeypatch.setattr(T, 'transfer', transfer)
    assert T.main([str(source), '--apply',
                   '--project', '8105f1ef-f39d-4a82-971e-e5d02db5ac8c',
                   '--environment', 'c36ec00c-9250-494d-ae1c-3d07c2bcf60a',
                   '--service', '05e102b9-b7ee-479d-9257-a506f74730d5',
                   '--expected-remote-sha256', 'ABSENT']) == 0
    assert json.loads(capsys.readouterr().out)['wrote'] is False


def test_cli_rejects_project_name(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        T.main([str(tmp_path / 'unused.json'), '--project', 'selfless-courage'])
    assert exc.value.code == 2
    assert 'UUID required' in capsys.readouterr().err


@pytest.mark.parametrize('mutation,reader_error', [
    (lambda obj: obj.update(evidence_basis='bad-shape'), AttributeError),
    (lambda obj: obj['candidates'][0].update(why=1), TypeError),
    (lambda obj: obj.update(evidence_basis={'ranked_by': [1]}), TypeError),
])
def test_incompatible_actual_shortlist_contract_refused(mutation, reader_error, remote):
    from backend.services import investment_committee as IC
    obj = json.loads(payload())
    mutation(obj)
    raw = json.dumps(obj).encode()
    source = remote.parent / 'malformed-source.json'
    source.write_bytes(raw)
    # Reproduce the real reader failure rather than mirroring its implementation.
    with pytest.raises(reader_error):
        IC.shortlist(funnel_path=source)
    with pytest.raises(T.Refused):
        T.transfer(raw, project=None, environment=None, service=None, expected=None,
                   apply=True, run=lambda *a, **kw: pytest.fail('invalid shape reached SSH'))
    # A bypassed local validator must still be rejected remotely, before staging.
    with pytest.raises(T.Refused):
        T.receive(raw, 'ABSENT', target=remote, apply=True)
    assert not remote.exists()
    assert list(remote.parent.iterdir()) == [source]


@pytest.mark.parametrize('mutation', [
    lambda obj: obj.update(evidence_basis=[]),
    lambda obj: obj.update(universe='bad-shape'),
    lambda obj: obj.update(evidence_basis={'ranked_by': 'profitability_small'}),
    lambda obj: obj['candidates'][0].update(why='text-is-not-a-reason-list'),
    lambda obj: obj['candidates'][0].update(why=[1]),
    lambda obj: obj['candidates'][0].update(blocked_by=1),
    lambda obj: obj['candidates'][0].update(score=True),
    lambda obj: obj['candidates'][0].update(score='1'),
    lambda obj: obj['candidates'][0].update(score=10 ** 400),
])
def test_additional_consumer_shapes_refused(mutation):
    obj = json.loads(payload())
    mutation(obj)
    with pytest.raises(T.Refused):
        T.validate(json.dumps(obj).encode())


@pytest.mark.parametrize('optional_nulls', [False, True])
def test_optional_consumer_defaults_still_readable(tmp_path, optional_nulls):
    from backend.services import investment_committee as IC
    obj = json.loads(payload())
    if optional_nulls:
        obj.update(evidence_basis=None, universe=None)
        obj['candidates'][0].update(why=None, blocked_by=None, score=None)
    raw = json.dumps(obj).encode()
    assert T.validate(raw)['candidates'] == 1
    path = tmp_path / 'valid.json'
    path.write_bytes(raw)
    rows = IC.shortlist(funnel_path=path)
    assert rows[0]['ticker'] == 'TEST'
    assert rows[0]['reasons'] == []


def test_real_producer_artifact_validates_and_actual_shortlist_reads():
    from backend.services import investment_committee as IC
    path = Path(__file__).resolve().parents[1] / 'data/funnel_night10.json'
    raw = path.read_bytes()
    obj = json.loads(raw)
    stamp = datetime.fromisoformat(obj['generated_at'].replace('Z', '+00:00'))
    # Historical compatibility check at its own stamp, never a current-freshness
    # claim and never rewriting the real artifact or its embedded provenance.
    meta = T.validate(raw, now=stamp)
    rows = IC.shortlist(asof=stamp, funnel_path=path)
    assert meta['sha256'] == T.digest(raw)
    assert meta['candidates'] == len(obj['candidates'])
    assert rows
    assert {row['ticker'] for row in rows} <= {c['ticker'] for c in obj['candidates']}
    by_ticker = {c['ticker']: c for c in obj['candidates']}
    for row in rows:
        assert row['reasons'] == by_ticker[row['ticker']]['why']
        assert row['score'] == by_ticker[row['ticker']]['score']
    assert path.read_bytes() == raw


@pytest.mark.parametrize('field,value,reader_error', [
    ('quality', 10 ** 400, OverflowError),
    ('market_cap', 10 ** 400, OverflowError),
    ('vol_annual', 1e308, OverflowError),
])
def test_numeric_reader_crashes_are_refused_before_transfer(field, value, reader_error, tmp_path):
    from backend.services import investment_committee as IC
    # Start with a real, ordinary 25-candidate producer artifact so variance
    # has another candidate, exactly as the independent reviewer reproduced it.
    source = Path(__file__).resolve().parents[1] / 'data/funnel_night10.json'
    obj = json.loads(source.read_bytes())
    assert len(obj['candidates']) > 1
    obj['candidates'][0][field] = value
    raw = json.dumps(obj).encode()
    path = tmp_path / 'bad-reader-shape.json'
    path.write_bytes(raw)
    with pytest.raises(reader_error):
        IC._compute_funnel_state(path)
    with pytest.raises(T.Refused):
        T.validate(raw, fresh=False)
    with pytest.raises(T.Refused):
        T.transfer(raw, project=None, environment=None, service=None,
                   expected=None, apply=True,
                   run=lambda *a, **kw: pytest.fail('unsafe number reached SSH'))


@pytest.mark.parametrize('field,value', [
    ('quality', 10 ** 400), ('market_cap', 10 ** 400),
    ('vol_annual', 1e308), ('vol_annual', 1e-101),
    ('insider_score', 10 ** 400), ('analyst_upside', 1e308),
    ('median_dollar_vol', 10 ** 400), ('price', 10 ** 400),
])
def test_numeric_consumer_bound_rejects_all_routes(field, value):
    obj = json.loads(payload())
    obj['candidates'][0][field] = value
    with pytest.raises(T.Refused):
        T.validate(json.dumps(obj).encode())


def test_oct26_pc_artifact_validates_and_real_state_reader_is_noncrashing():
    from backend.services import investment_committee as IC
    # Read-only integration fixture: preserve the dirty runtime checkout.
    source = Path('C:/Users/mrthn/aegis-finance/backend/data/funnel_night10.json')
    if not source.exists():
        pytest.skip('PC runtime artifact is unavailable on this machine')
    raw = source.read_bytes()
    stamp = datetime.fromisoformat(json.loads(raw)['generated_at'].replace('Z', '+00:00'))
    meta = T.validate(raw, now=stamp)
    assert meta['candidates'] > 1
    state = IC._compute_funnel_state(source)
    assert state['gate']['status'] == 'CLEAN'
    assert len(state['recs']) == meta['candidates']
    assert state['funnel_generated_at'] == json.loads(raw)['generated_at']
    assert source.read_bytes() == raw
