"""Adversarial selector tests: fixtures only, no real transport or ledger."""
from datetime import datetime, time, timedelta, timezone
import json
from pathlib import Path

import pytest

from scripts import owner_event_warning as runner
from backend.tests.test_owner_event_warning_runner import manual_gate

pytest_plugins = ("backend.tests.test_owner_event_warning_runner",)


@pytest.fixture
def approved(case, monkeypatch):
    kwargs, row, source, snap = case
    snap['account_number'] = 'SYNTHETIC-PC'
    root = kwargs['ledger'] / 'pc_book'
    root.mkdir()
    day = kwargs['now'].astimezone(runner.PC_ZONE).date()
    dated = root / str(day) / 'state_latest.json'
    dated.parent.mkdir()
    dated.write_text(json.dumps(snap))
    top = root / 'state_latest.json'
    top.write_text(json.dumps(dict(snap, t=(kwargs['now'] - timedelta(minutes=1)).isoformat())))
    new = dict(kwargs, snapshot=None, newest_approved=True,
               expected_account_sha256=runner.sha(b'SYNTHETIC-PC'))
    monkeypatch.setattr(runner, 'KNOWN_MANUAL_PROOFS', {})
    # Exercise operational time gates deterministically, regardless of CI hour.
    from datetime import datetime, timezone
    class OutsideIIF(datetime):
        @classmethod
        def now(cls, tz=None):
            return kwargs['now'].replace(hour=0, minute=0).astimezone(tz or timezone.utc)
    monkeypatch.setattr(runner, 'datetime', OutsideIIF)
    return new, dated, top


def test_newest_frozen_preview_no_writes(case, approved, monkeypatch):
    kwargs, dated, top = approved
    before = {p: p.read_bytes() for p in kwargs['ledger'].rglob('*') if p.is_file()}
    # Freeze inputs then forbid all legacy path adapter calls.
    monkeypatch.setattr(runner.adapter, 'build_saved_warning', lambda **k: pytest.fail('path reopened'))
    monkeypatch.setattr(runner.adapter, 'warn_saved', lambda **k: pytest.fail('path reopened'))
    original = runner.adapter.warn_saved_bytes
    seen = []
    def deliver(**kw):
        seen.append(kw)
        return original(**kw)
    monkeypatch.setattr(runner.adapter, 'warn_saved_bytes', deliver)
    code, receipts = runner.run(**kwargs)
    assert code == 0 and receipts[0]['delivery'] == 'NOT_SENT'
    assert receipts[0]['snapshot_sha256'] == runner.sha(dated.read_bytes())
    assert seen[0]['snapshot_bytes'] == dated.read_bytes()
    assert seen[0]['source_bytes'] == case[2].read_bytes()
    assert before == {p: p.read_bytes() for p in kwargs['ledger'].rglob('*') if p.is_file()}
    assert not kwargs['journal'].exists()


def test_overnight_session_snapshot_keeps_start_day_folder(case, approved):
    kwargs, dated, top = approved
    # A session started on the prior SGT date writes after midnight there.
    overnight = datetime.combine(kwargs['now'].date(), time(18, 20), timezone.utc)
    kwargs['now'] = overnight
    prior_day = overnight.astimezone(runner.PC_ZONE).date() - timedelta(days=1)
    old_folder = dated.parent.parent / str(prior_day)
    # The fixture's current SGT date can already be the overnight session's
    # start date. Reuse that directory in this case instead of assuming the
    # test always runs before Singapore midnight.
    old_folder.mkdir(exist_ok=True)
    session_snapshot = old_folder / 'state_latest.json'
    snap = json.loads(dated.read_text())
    snap['t'] = overnight.isoformat()
    session_snapshot.write_text(json.dumps(snap))
    if dated != session_snapshot:
        dated.unlink()
    top.write_text(json.dumps(dict(snap, t=(overnight - timedelta(minutes=1)).isoformat())))
    row = case[1]
    row['first_seen_utc'] = overnight.isoformat()
    row['published_utc'] = (overnight - timedelta(hours=1)).isoformat()
    case[2].write_text(json.dumps(row) + '\n')
    code, receipts = runner.run(**kwargs)
    assert code == 0 and receipts[0]['delivery'] == 'NOT_SENT'
    assert receipts[0]['snapshot_sha256'] == runner.sha(session_snapshot.read_bytes())


def test_older_folder_is_outside_fixed_candidate_paths(case, approved, monkeypatch):
    kwargs, dated, top = approved
    older = (dated.parent.parent / str(kwargs['now'].astimezone(runner.PC_ZONE).date()
             - timedelta(days=2)))
    older.mkdir()
    (older / 'state_latest.json').write_bytes(dated.read_bytes())
    dated.unlink()
    top.unlink()
    seen = []
    original = runner.frozen_read
    def observe(path):
        seen.append(Path(path))
        return original(path)
    monkeypatch.setattr(runner, 'frozen_read', observe)
    assert runner.run(**kwargs)[0] == 2
    assert older / 'state_latest.json' not in seen


@pytest.mark.parametrize('mode', ['total_swap', 'mixed_account', 'missing_account',
    'missing_expected', 'wrong_expected', 'future', 'stale', 'folder', 'non_utc', 'equal_clock'])
def test_adversarial_refusal_before_delivery(case, approved, monkeypatch, mode):
    kwargs, dated, top = approved
    snap = json.loads(dated.read_text())
    if mode in ('total_swap', 'mixed_account'):
        snap['account_number'] = 'OTHER-PC'
        if mode == 'total_swap':
            top.write_text(json.dumps(snap))
    elif mode == 'missing_account':
        del snap['account_number']
    elif mode == 'missing_expected':
        kwargs['expected_account_sha256'] = None
    elif mode == 'wrong_expected':
        kwargs['expected_account_sha256'] = '0' * 64
    elif mode == 'future':
        snap['t'] = (kwargs['now'] + timedelta(seconds=1)).isoformat()
    elif mode == 'stale':
        snap['t'] = (kwargs['now'] - timedelta(hours=25)).isoformat()
        top.write_text(json.dumps(snap))
        dated.unlink()
    elif mode == 'folder':
        snap['t'] = (kwargs['now'] - timedelta(days=1)).isoformat()
    elif mode == 'non_utc':
        snap['t'] = kwargs['now'].astimezone(runner.PC_ZONE).isoformat()
    elif mode == 'equal_clock':
        top.write_text(json.dumps(dict(snap, tag='different bytes at same clock')))
    if mode != 'stale':
        dated.write_text(json.dumps(snap))
    monkeypatch.setattr(runner.adapter, 'warn_saved_bytes', lambda **k: pytest.fail('delivery reached'))
    assert runner.run(**kwargs)[0] == 2


def test_replacement_after_assessment_uses_exact_frozen_bytes(case, approved, monkeypatch):
    kwargs, dated, top = approved
    snapshot_bytes, source_bytes = dated.read_bytes(), case[2].read_bytes()
    build = runner.adapter.build_saved_warning_bytes
    def replace(**kw):
        artifact = build(**kw)
        dated.write_bytes(b'{"account_number":"EVIL"}')
        case[2].write_bytes(b'{"body":"EVIL"}\n')
        return artifact
    monkeypatch.setattr(runner.adapter, 'build_saved_warning_bytes', replace)
    deliver = runner.adapter.warn_saved_bytes
    def verify(**kw):
        assert kw['snapshot_bytes'] == snapshot_bytes
        assert kw['source_bytes'] == source_bytes
        return deliver(**kw)
    monkeypatch.setattr(runner.adapter, 'warn_saved_bytes', verify)
    code, receipts = runner.run(**kwargs)
    assert code == 0
    assert receipts[0]['snapshot_sha256'] == runner.sha(snapshot_bytes)
    assert receipts[0]['source_row_sha256'] == runner.sha(source_bytes)


def test_refreshed_apple_suppression_with_other_event_fake_sender(case, approved, monkeypatch):
    from backend.services import telegram_bridge
    kwargs, dated, top = approved
    old_kwargs, row, source, snap = case
    row['tickers'] = ['AAPL']
    snap['positions'][0]['symbol'] = 'AAPL'
    old_kwargs['snapshot'].write_text(json.dumps(snap))
    source.write_text(json.dumps(row) + '\n')
    # The existing proof fixture uses ACME; adapt its artifact-building ticker
    # solely for creating the synthetic manual Apple evidence.
    build = runner.adapter.build_saved_warning
    def apple_build(**kw):
        kw['ticker'] = 'AAPL'
        return build(**kw)
    monkeypatch.setattr(runner.adapter, 'build_saved_warning', apple_build)
    review, adoption, payload, sp, record, original = manual_gate(case, monkeypatch)
    record['ticker'] = 'AAPL'
    sp.write_text(json.dumps(record))
    ad = json.loads(adoption.read_text())
    ad['suppressions'][0]['sha256'] = runner.sha(sp.read_bytes())
    adoption.write_text(json.dumps(ad))
    payload['adoption_sha256'] = runner.sha(adoption.read_bytes())
    review.write_text(json.dumps(payload))
    monkeypatch.setattr(runner, 'KNOWN_MANUAL_PROOFS', {
        record['event_id']: (record['attempt_sha256'], record['result_sha256'], 'AAPL')})
    # A refreshed Apple-only snapshot remains suppressed without any transport.
    snap['positions'][0].update(market_value=2050, current_price=102.5)
    snap.update(long_market_value=2050, cash=7950)
    dated.write_text(json.dumps(snap))
    monkeypatch.setattr(telegram_bridge, 'owner_chat_id',
                        lambda: pytest.fail('suppressed Apple requested transport'))
    code, only_apple = runner.run(**kwargs, send=True, review=review, adoption=adoption)
    assert code == 0 and only_apple[0]['delivery'] == 'SUPPRESSED_MANUAL'
    assert only_apple[0]['provisional_decision_id'].startswith('saved-sec-decision:')
    assert not kwargs['journal'].exists()
    # Refresh exposure AND add a second event that must still be sent once.
    snap['positions'][0].update(market_value=2100, current_price=105)
    snap['positions'].append(dict(symbol='BETA', qty=10, market_value=1000, current_price=100))
    snap.update(n_positions=2, long_market_value=3100, cash=6900)
    dated.write_text(json.dumps(snap))
    beta = dict(row, tickers=['BETA'], raw_id='0000000001-26-000002:results.htm',
        url='https://www.sec.gov/Archives/edgar/data/1/000000000126000002/results.htm')
    source.write_text(json.dumps(row) + '\n' + json.dumps(beta) + '\n')
    monkeypatch.setattr(telegram_bridge, 'owner_chat_id', lambda: '123456')
    sent = []
    def fake_send(text, **kw):
        sent.append(text)
        assert 'BETA' in text and 'AAPL' not in text
        assert runner.sha(dated.read_bytes()) in text
        ack = dict(state='SENT', messages=1, native_ack_sha256='f' * 64,
            tag_sha256=runner.adapter._digest({'tag': kw['tag']}),
            text_sha256=runner.adapter._hash(text))
        ack['delivery_binding_sha256'] = runner.adapter._digest({
            k: ack[k] for k in runner.adapter._ACK_HASH_KEYS})
        return ack
    monkeypatch.setattr(telegram_bridge, 'send_owner_once', fake_send)
    kwargs['journal'].mkdir()
    inputs = {p: p.read_bytes() for p in kwargs['ledger'].rglob('*') if p.is_file()}
    code, receipts = runner.run(**kwargs, send=True, review=review, adoption=adoption)
    assert code == 0
    assert [r['delivery'] for r in receipts] == ['SUPPRESSED_MANUAL', 'SENT']
    assert receipts[0]['snapshot_sha256'] != original['snapshot_sha256']
    assert len(sent) == 1
    assert all(p.read_bytes() == raw for p, raw in inputs.items())
    assert len(list(kwargs['journal'].iterdir())) == 2  # original private ACK semantics


def test_selector_reads_only_three_approved_locations(approved, monkeypatch):
    kwargs, dated, top = approved
    paths = []
    real = runner.frozen_read
    def observe(path):
        paths.append(Path(path))
        return real(path)
    monkeypatch.setattr(runner, 'frozen_read', observe)
    runner.select_snapshot(kwargs['ledger'], now=kwargs['now'],
        expected_account_sha256=kwargs['expected_account_sha256'], check=lambda: None)
    assert len(paths) == 3
    assert all(p.name == 'state_latest.json' and 'pc_book' in p.parts for p in paths)


def test_secure_read_rejects_directory_and_oversize(tmp_path):
    with pytest.raises((OSError, runner.Refused)):
        runner.frozen_read(tmp_path)
    large = tmp_path / 'large.json'
    with large.open('wb') as f:
        f.truncate(runner.SELECTOR_MAX_BYTES + 1)
    with pytest.raises(runner.Refused):
        runner.frozen_read(large)


def test_budget_refuses_before_delivery(approved, monkeypatch):
    kwargs, _, _ = approved
    calls = iter([0, 6])
    monkeypatch.setattr(runner.time, 'monotonic', lambda: next(calls))
    assert runner.run(**kwargs)[0] == 2


def test_secure_read_rejects_redirected_parent(tmp_path):
    import os
    import subprocess
    target = tmp_path / 'target'
    target.mkdir()
    (target / 'state.json').write_text('{}')
    link = tmp_path / 'link'
    if os.name == 'nt':
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)],
                                capture_output=True)
        assert result.returncode == 0
    else:
        link.symlink_to(target, target_is_directory=True)
    with pytest.raises((OSError, runner.Refused)):
        runner.frozen_read(link / 'state.json')


def test_windows_read_handle_prevents_replacement(tmp_path, monkeypatch):
    import os
    if os.name != 'nt':
        pytest.skip('Windows handle sharing contract')
    source = tmp_path / 'state.json'
    source.write_bytes(b'{"frozen":true}')
    other = tmp_path / 'other.json'
    other.write_bytes(b'{"frozen":false}')
    real = os.fdopen
    def attempt_replace(*a, **kw):
        with pytest.raises(PermissionError):
            other.replace(source)
        with pytest.raises(PermissionError):
            source.write_bytes(b'EVIL')
        return real(*a, **kw)
    monkeypatch.setattr(os, 'fdopen', attempt_replace)
    assert runner.frozen_read(source) == b'{"frozen":true}'


def test_iif_protected_window_refuses(approved, monkeypatch):
    from datetime import datetime, timezone
    kwargs, _, _ = approved
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return kwargs['now'].replace(hour=8, minute=45).astimezone(tz or timezone.utc)
    monkeypatch.setattr(runner, 'datetime', Clock)
    assert runner.run(**kwargs)[0] == 2


def test_frozen_bytes_reach_fake_sender_after_file_replacement(case, approved, monkeypatch):
    from backend.services import telegram_bridge
    from backend.tests.test_owner_event_warning_runner import gates
    kwargs, dated, _ = approved
    frozen_snapshot, frozen_source = dated.read_bytes(), case[2].read_bytes()
    review, adoption, _ = gates(kwargs['ledger'])
    kwargs['journal'].mkdir()
    monkeypatch.setattr(runner.adapter, '_journal_identity', lambda p: (1, 1))
    monkeypatch.setattr(telegram_bridge, 'owner_chat_id', lambda: '123456')
    build = runner.adapter.build_saved_warning_bytes
    def replace(**kw):
        artifact = build(**kw)
        dated.write_bytes(b'REPLACED')
        case[2].write_bytes(b'REPLACED')
        return artifact
    monkeypatch.setattr(runner.adapter, 'build_saved_warning_bytes', replace)
    sent = []
    def sender(text, **kw):
        sent.append(text)
        assert runner.sha(frozen_snapshot) in text
        assert runner.sha(frozen_source) in text
        assert 'REPLACED' not in text
        ack = dict(state='SENT', messages=1, native_ack_sha256='e' * 64,
            tag_sha256=runner.adapter._digest({'tag': kw['tag']}),
            text_sha256=runner.adapter._hash(text))
        ack['delivery_binding_sha256'] = runner.adapter._digest({
            k: ack[k] for k in runner.adapter._ACK_HASH_KEYS})
        return ack
    monkeypatch.setattr(telegram_bridge, 'send_owner_once', sender)
    code, receipts = runner.run(**kwargs, send=True, review=review, adoption=adoption)
    assert code == 0 and receipts[0]['delivery'] == 'SENT' and len(sent) == 1
    saved = json.loads(next(p for p in kwargs['journal'].iterdir()
                           if not p.name.endswith('.result.json')).read_text())
    assert saved['artifact']['snapshot_sha256'] == runner.sha(frozen_snapshot)
    assert saved['artifact']['source_row_sha256'] == runner.sha(frozen_source)
    from backend.services.saved_sec_event_path import build_saved_sec_event_path
    expected = build_saved_sec_event_path(event_bytes=frozen_source,
        snapshot_bytes=frozen_snapshot, ticker='ACME',
        cutoff_utc=kwargs['now'].isoformat(), decision_utc=kwargs['now'].isoformat())
    assert saved['artifact']['forecast_input_id'] == expected['forecast_input_id']
    assert saved['artifact']['provisional_decision_id'] == expected['decision_id']
    assert expected['decision_id'] in sent[0]



def test_malformed_numeric_holdings_are_sanitized(approved):
    kwargs, dated, _ = approved
    snap = json.loads(dated.read_text())
    snap['positions'][0]['qty'] = 'PRIVATE_INVALID_NUMBER'
    dated.write_text(json.dumps(snap))
    code, receipts = runner.run(**kwargs)
    assert code == 2 and receipts[-1]['status'] == 'REFUSED'
    assert 'PRIVATE_INVALID_NUMBER' not in json.dumps(receipts)


def test_corpus_has_no_following_exists_probe(case, approved, monkeypatch):
    kwargs, _, _ = approved
    exists = Path.exists
    def forbid_probe(path):
        if path == case[2]:
            pytest.fail('following corpus probe')
        return exists(path)
    monkeypatch.setattr(Path, 'exists', forbid_probe)
    assert runner.run(**kwargs)[0] == 0


def test_manual_proofs_cooperate_between_each_read(case, monkeypatch):
    kwargs, _, _, _ = case
    _, _, _, sp, record, _ = manual_gate(case, monkeypatch)
    reads = []
    def read(path):
        reads.append(path)
        return runner.read(path)
    def check():
        if len(reads) >= 2:
            raise runner.Refused('BUDGET_TEST')
    monkeypatch.setattr(runner, 'private_read', read)
    with pytest.raises(runner.Refused, match='BUDGET_TEST'):
        runner.suppression_record(dict(path=str(sp), sha256=runner.sha(sp.read_bytes())),
                                  now=kwargs['now'], check=check)
    assert reads == [str(sp), record['attempt_path']]


def test_manual_proof_count_is_bounded(case, monkeypatch):
    from backend.tests.test_owner_event_warning_runner import gates
    kwargs, _, _, _ = case
    review, adoption, payload = gates(kwargs['ledger'])
    ad = json.loads(adoption.read_text())
    ad['suppressions'] = [{}] * 65
    adoption.write_text(json.dumps(ad))
    payload['adoption_sha256'] = runner.sha(adoption.read_bytes())
    review.write_text(json.dumps(payload))
    monkeypatch.setattr(runner, 'private_read', lambda p: pytest.fail('excessive proof read'))
    with pytest.raises(runner.Refused, match='MANUAL_PROOF_COUNT_EXCEEDED'):
        runner.qualify_send(review, adoption, kwargs['journal'], now=kwargs['now'], check=lambda: None)


def test_legacy_cli_freezes_bytes_despite_replacement_after_recheck(case, monkeypatch):
    kwargs, _, source, _ = case
    snapshot = kwargs['snapshot']
    raw_snapshot, raw_source = snapshot.read_bytes(), source.read_bytes()
    read = runner.read
    calls = 0
    def replace_after_recheck(path):
        nonlocal calls
        raw = read(path)
        if path == snapshot:
            calls += 1
            if calls == 2:
                snapshot.write_bytes(b'REPLACED_AFTER_CHECK')
        return raw
    monkeypatch.setattr(runner, 'read', replace_after_recheck)
    warn = runner.adapter.warn_saved_bytes
    seen = []
    def verify(**kw):
        assert kw['snapshot_bytes'] == raw_snapshot
        assert kw['source_bytes'] == raw_source
        seen.append(kw)
        return warn(**kw)
    monkeypatch.setattr(runner.adapter, 'warn_saved_bytes', verify)
    code, receipts = runner.run(**kwargs)
    assert code == 0 and calls == 2 and len(seen) == 1
    assert receipts[0]['snapshot_sha256'] == runner.sha(raw_snapshot)
