"""Synthetic inputs and fake callbacks only; never imports the Telegram bridge."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.services import owner_event_warning as warning


@pytest.fixture
def inputs():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    stamp = (now - timedelta(hours=1)).isoformat()
    row = dict(ticker='ACME', form='8-K', exhibit='EX-99.1', item='2.02',
               event_type='earnings_results', accession='0000000001-26-000001',
               url='https://www.sec.gov/Archives/edgar/data/1/000000000126000001/results.htm',
               published_at=stamp, captured_at=stamp, body='Quarterly financial results.')
    snap = dict(lane='PC-PAPER', as_of=stamp, equity_usd=10000,
                positions=[dict(ticker='ACME', market_value_usd=2000, instrument='equity', leverage=1)])
    return now, row, snap


def ack(text, *, tag):
    value = dict(state='SENT', messages=1, native_ack_sha256='a' * 64,
                 tag_sha256=warning._digest({'tag': tag}), text_sha256=warning._hash(text))
    value['delivery_binding_sha256'] = warning._digest({k: value[k] for k in
        ('native_ack_sha256', 'tag_sha256', 'text_sha256')})
    return value


def run(inputs, tmp_path, sender=ack):
    now, row, snap = inputs
    if sender is not None:
        tmp_path.mkdir(exist_ok=True)
    return warning.warn(json.dumps(row), json.dumps(snap), now=now,
                        journal_dir=tmp_path, sender=sender)


def test_success_durable_before_send_and_duplicate(inputs, tmp_path):
    calls = []
    def send(text, **kwargs):
        records = list(tmp_path.glob('*.json'))
        assert len(records) == 1
        saved = json.loads(records[0].read_text())
        assert saved['state'] == 'SENDING'
        calls.append(text)
        return ack(text, **kwargs)
    result = run(inputs, tmp_path, send)
    assert result['delivery'] == 'SENT'
    artifact = result['artifact']
    assert artifact['exposure_weight'] == '0.2'
    assert artifact['conditional_loss_usd'] == {'5_percent_decline': '100.00', '10_percent_decline': '200.00'}
    assert artifact['forecast_status'] == 'NO_CALIBRATED_EVENT_FORECAST'
    assert artifact['source_row_sha256'] == warning._hash(json.dumps(inputs[1]))
    assert artifact['snapshot_sha256'] == warning._hash(json.dumps(inputs[2]))
    assert artifact['paper_decision'] == ['HOLD_EXISTING', 'NO_NEW_BET', 'REVIEW_NEW_EVIDENCE']
    # A newer snapshot/capture must not resend the same event.
    inputs[2]['as_of'] = inputs[0].isoformat()
    inputs[1]['captured_at'] = inputs[0].isoformat()
    assert run(inputs, tmp_path, send)['delivery'] == 'ALREADY_SENT'
    assert len(calls) == 1


@pytest.mark.parametrize('target,key,value,reason', [
    ('row', 'form', '10-K', 'SOURCE_AMBIGUOUS'),
    ('row', 'body', 'Unrelated corporate announcement', 'SOURCE_AMBIGUOUS'),
    ('row', 'event_type', 'unknown', 'SOURCE_AMBIGUOUS'),
    ('row', 'url', 'https://127.0.0.1/results.htm', 'SOURCE_AMBIGUOUS'),
    ('row', 'url', 'https://www.sec.gov/Archives/edgar/data/1/000000000126000001/results.htm?owner=123', 'SOURCE_AMBIGUOUS'),
    ('snap', 'equity_usd', 0, 'BAD_EQUITY_OR_EXPOSURE'),
    ('snap', 'equity_usd', 'NaN', 'BAD_EQUITY_OR_EXPOSURE'),
    ('snap', 'equity_usd', True, 'BAD_EQUITY_OR_EXPOSURE'),
    ('snap', 'equity_usd', -100, 'BAD_EQUITY_OR_EXPOSURE'),
    ('snap', 'equity_usd', 100, 'BAD_EQUITY_OR_EXPOSURE'),
    ('snap', 'positions', [], 'NOT_HELD'),
    ('snap', 'lane', 'LIVE', 'BAD_EQUITY_OR_EXPOSURE'),
])
def test_refusals(inputs, tmp_path, target, key, value, reason):
    inputs[1 if target == 'row' else 2][key] = value
    def never(*args, **kwargs):
        pytest.fail('refusal sent')
    result = run(inputs, tmp_path, never)
    assert result['artifact']['status'] == 'REFUSED'
    assert result['artifact']['reason'] == reason
    assert result['delivery'] == 'NOT_SENT'
    assert not list(tmp_path.iterdir())
    assert 'conditional_loss_usd' not in result['artifact']


@pytest.mark.parametrize('key,hours,reason', [
    ('published_at', -25, 'SOURCE_STALE'),
    ('published_at', 1, 'SOURCE_CLOCK_INVALID'),
    ('captured_at', 1, 'SOURCE_CLOCK_INVALID'),
    ('captured_at', -2, 'SOURCE_CLOCK_INVALID'),
    ('as_of', -25, 'SNAPSHOT_STALE'),
    ('as_of', 1, 'SNAPSHOT_CLOCK_INVALID'),
])
def test_clocks(inputs, tmp_path, key, hours, reason):
    inputs[2 if key == 'as_of' else 1][key] = (inputs[0] + timedelta(hours=hours)).isoformat()
    result = run(inputs, tmp_path, lambda *a, **k: pytest.fail('sent'))
    assert result['artifact']['reason'] == reason


@pytest.mark.parametrize('key,value', [('market_value_usd', -1), ('leverage', 2), ('instrument', 'option')])
def test_unsupported_exposure(inputs, tmp_path, key, value):
    inputs[2]['positions'][0][key] = value
    assert run(inputs, tmp_path)['artifact']['status'] == 'REFUSED'


@pytest.mark.parametrize('field,value', [('state', 'UNKNOWN'), ('messages', True),
    ('native_ack_sha256', ''), ('tag_sha256', 'b'*64), ('text_sha256', 'b'*64),
    ('delivery_binding_sha256', 'b'*64)])
def test_bad_ack_blocks_retry(inputs, tmp_path, field, value):
    def send(text, **kwargs):
        result = ack(text, **kwargs)
        result[field] = value
        return result
    assert run(inputs, tmp_path, send)['delivery'] == 'UNKNOWN_RECONCILE_REQUIRED'
    assert run(inputs, tmp_path)['delivery'] == 'DUPLICATE_RECONCILE_REQUIRED'


def test_private_data_hygiene(inputs, tmp_path):
    private = 'PRIVATE_OWNER_987654321'
    inputs[1]['owner_id'] = private
    inputs[1]['body'] += ' ' + private
    inputs[2]['owner_id'] = private
    def send(text, **kwargs):
        assert private not in text
        raise RuntimeError(private)
    result = run(inputs, tmp_path, send)
    assert result['delivery'] == 'UNKNOWN_RECONCILE_REQUIRED'
    assert private not in json.dumps(result)
    assert all(private not in p.read_text() for p in tmp_path.iterdir())


@pytest.mark.parametrize('raw', ['[]', '{}', '{"ticker":"ACME","ticker":"OTHER"}', 'invalid', 'NaN'])
def test_malformed_json(inputs, tmp_path, raw):
    result = warning.warn(raw, json.dumps(inputs[2]), now=inputs[0], journal_dir=tmp_path,
                          sender=lambda *a, **k: pytest.fail('sent'))
    assert result['artifact']['status'] == 'REFUSED'


def test_no_sender_preview(inputs, tmp_path):
    assert run(inputs, tmp_path, None)['delivery'] == 'NOT_SENT'
    assert not list(tmp_path.iterdir())


def test_existing_sending_or_corrupt_journal_blocks(inputs, tmp_path):
    artifact = warning.build_warning(json.dumps(inputs[1]), json.dumps(inputs[2]), now=inputs[0])
    (tmp_path / (artifact['event_key'] + '.json')).write_text('incomplete')
    assert run(inputs, tmp_path, lambda *a, **k: pytest.fail('sent'))['delivery'] == 'DUPLICATE_RECONCILE_REQUIRED'

@pytest.mark.parametrize('key', ['published_at', 'captured_at', 'as_of'])
def test_naive_timestamp_refused(inputs, tmp_path, key):
    inputs[2 if key == 'as_of' else 1][key] = inputs[0].replace(tzinfo=None).isoformat()
    assert run(inputs, tmp_path)['artifact']['status'] == 'REFUSED'


def test_exact_freshness_boundary(inputs, tmp_path):
    boundary = (inputs[0] - timedelta(hours=24)).isoformat()
    inputs[1]['published_at'] = boundary
    inputs[1]['captured_at'] = boundary
    inputs[2]['as_of'] = boundary
    assert run(inputs, tmp_path)['delivery'] == 'SENT'


def test_duplicate_positions_refused(inputs, tmp_path):
    inputs[2]['positions'] *= 2
    assert run(inputs, tmp_path)['artifact']['status'] == 'REFUSED'


def test_pre_send_persistence_failure_never_sends(inputs, tmp_path, monkeypatch):
    def fail(_):
        raise OSError('disk failure')
    monkeypatch.setattr(warning.os, 'fsync', fail)
    assert run(inputs, tmp_path, lambda *a, **k: pytest.fail('sent'))['delivery'] == 'UNKNOWN_RECONCILE_REQUIRED'
    assert run(inputs, tmp_path)['delivery'] == 'DUPLICATE_RECONCILE_REQUIRED'


def test_concurrent_attempt_sees_sending(inputs, tmp_path):
    def send(text, **kwargs):
        assert run(inputs, tmp_path, lambda *a, **k: pytest.fail('second send'))['delivery'] == 'DUPLICATE_RECONCILE_REQUIRED'
        return ack(text, **kwargs)
    assert run(inputs, tmp_path, send)['delivery'] == 'SENT'


def test_ack_extra_private_fields_not_persisted(inputs, tmp_path):
    def send(text, **kwargs):
        return {**ack(text, **kwargs), 'owner': 'PRIVATE_123456789'}
    result = run(inputs, tmp_path, send)
    assert result['delivery'] == 'SENT'
    assert all('PRIVATE_123456789' not in p.read_text() for p in tmp_path.iterdir())

@pytest.fixture
def saved(inputs, tmp_path):
    now, row, snap = inputs
    native = dict(source='sec_edgar_8k_ex99_body', first_seen_utc=row['captured_at'],
                  published_utc=row['published_at'], url=row['url'], body=row['body'],
                  title='8-K - Acme Inc. (0000000001) (Filer) — EX-99.1',
                  tickers=['ACME'], raw_id=row['accession'] + ':results.htm', private='PRIVATE_ACCOUNT')
    pc = dict(t=snap['as_of'], equity=10000, cash=8000, long_market_value=2000,
              short_market_value=0, n_positions=1, account_number='PRIVATE_ACCOUNT',
              positions=[dict(symbol='ACME', qty=20, current_price=100, market_value=2000)])
    return now, native, pc, tmp_path / 'source.jsonl', tmp_path / 'pc.json'


def saved_run(saved, sender=None):
    now, row, pc, source, snapshot = saved
    source.write_bytes((json.dumps(row) + '\r\n').encode())
    snapshot.write_bytes(json.dumps(pc).encode())
    if sender is not None:
        (source.parent / 'journal').mkdir(exist_ok=True)
    return warning.warn_saved(source_jsonl_path=source, pc_paper_snapshot_path=snapshot,
        ticker='ACME', now=now, journal_dir=source.parent / 'journal', sender=sender)


def test_saved_success_no_item_and_original_hashes(saved):
    result = saved_run(saved)
    artifact = result['artifact']
    assert artifact['status'] == 'PROVISIONAL'
    assert result['delivery'] == 'NOT_SENT'
    assert artifact['source_row_sha256'] == warning.hashlib.sha256(saved[3].read_bytes()).hexdigest()
    assert artifact['snapshot_sha256'] == warning.hashlib.sha256(saved[4].read_bytes()).hexdigest()
    assert 'Item 2.02 UNKNOWN' in artifact['source_proof']
    assert 'PRIVATE_ACCOUNT' not in json.dumps(result)
    assert not (saved[3].parent / 'journal').exists()


@pytest.mark.parametrize('key,value', [
    ('source', 'other'), ('raw_id', '0000000001-26-000002:results.htm'),
    ('raw_id', '0000000001-26-000001:other.htm'), ('title', '8-K - Acme EX-99.1'),
    ('title', '8-K - Acme (0000000002) (Filer) — EX-99.1'),
    ('title', '8-K - Acme (0000000001) (Filer) — EX-99.2'),
    ('body', 'Appointment of director'), ('tickers', ['ACME', 'OTHER']),
    ('url', 'https://example.com/Archives/edgar/data/1/000000000126000001/results.htm'),
])
def test_saved_event_refusal(saved, key, value):
    saved[1][key] = value
    assert saved_run(saved, lambda *a, **k: pytest.fail('sent'))['artifact']['status'] == 'REFUSED'


@pytest.mark.parametrize('key', ['published_utc', 'first_seen_utc', 't'])
@pytest.mark.parametrize('mode', ['future', 'stale', 'naive'])
def test_saved_clocks(saved, key, mode):
    now = saved[0]
    stamp = (now + timedelta(hours=1) if mode == 'future' else now - timedelta(hours=26))
    if mode == 'naive':
        stamp = now.replace(tzinfo=None)
    saved[2 if key == 't' else 1][key] = stamp.isoformat()
    if key == 'first_seen_utc' and mode == 'stale':
        saved[1]['published_utc'] = (now - timedelta(hours=27)).isoformat()
    assert saved_run(saved)['artifact']['status'] == 'REFUSED'


@pytest.mark.parametrize('key,value', [('qty', -1), ('market_value', -1), ('leverage', 2), ('side', 'short'), ('asset_class', 'option')])
def test_saved_exposure_refusal(saved, key, value):
    saved[2]['positions'][0][key] = value
    assert saved_run(saved)['artifact']['status'] == 'REFUSED'


def test_saved_ambiguous_rows_and_io_hygiene(saved):
    saved_run(saved)
    source = saved[3]
    row = dict(saved[1], body='Another financial results release')
    with source.open('a') as f:
        f.write(json.dumps(row) + '\n')
    artifact = warning.build_saved_warning(source_jsonl_path=source,
        pc_paper_snapshot_path=saved[4], ticker='ACME', now=saved[0])
    assert artifact['reason'] == 'SOURCE_SELECTION_AMBIGUOUS'
    artifact = warning.build_saved_warning(source_jsonl_path=source.parent / 'PRIVATE_ACCOUNT',
        pc_paper_snapshot_path=saved[4], ticker='ACME', now=saved[0])
    assert artifact['status'] == 'REFUSED'
    assert 'PRIVATE_ACCOUNT' not in json.dumps(artifact)


def test_saved_ack_and_duplicate(saved):
    assert saved_run(saved, ack)['delivery'] == 'SENT'
    assert saved_run(saved, lambda *a, **k: pytest.fail('resent'))['delivery'] == 'ALREADY_SENT'


@pytest.mark.parametrize('change', [
    lambda pc: pc.update(n_positions=2),
    lambda pc: pc.update(cash=8001),
    lambda pc: pc.update(long_market_value=2050),
    lambda pc: pc.update(short_market_value=1),
    lambda pc: pc['positions'][0].update(current_price=99),
])
def test_saved_reconciliation_extremes_refuse(saved, change):
    change(saved[2])
    assert saved_run(saved)['artifact']['status'] == 'REFUSED'


def test_saved_small_position_sum_residual_is_labeled(saved):
    saved[2]['long_market_value'] = 2000.50
    saved[2]['cash'] = 7999.50
    artifact = saved_run(saved)['artifact']
    assert artifact['status'] == 'PROVISIONAL'
    assert artifact['reconciliation']['reported_long_minus_positions_usd'] == '0.5'
    assert '0.5' in artifact['reconciliation_note']


def test_delivery_requires_existing_private_directory(inputs, tmp_path):
    missing = tmp_path / 'absent'
    result = warning.warn(json.dumps(inputs[1]), json.dumps(inputs[2]),
                          now=inputs[0], journal_dir=missing,
                          sender=lambda *a, **k: pytest.fail('sent'))
    assert result['delivery'] == 'REFUSED_JOURNAL_UNQUALIFIED'
    assert not missing.exists()


def test_existing_result_file_blocks_send(inputs, tmp_path):
    artifact = warning.build_warning(json.dumps(inputs[1]), json.dumps(inputs[2]), now=inputs[0])
    (tmp_path / (artifact['event_key'] + '.result.json')).write_text('prior result')
    assert run(inputs, tmp_path, lambda *a, **k: pytest.fail('sent'))['delivery'] == 'DUPLICATE_RECONCILE_REQUIRED'


@pytest.mark.parametrize('failure', ['create', 'write', 'fsync'])
def test_post_send_result_failure_is_unknown_and_never_retried(inputs, tmp_path, monkeypatch, failure):
    artifact = warning.build_warning(json.dumps(inputs[1]), json.dumps(inputs[2]), now=inputs[0])
    result_path = tmp_path / (artifact['event_key'] + '.result.pending.json')
    calls = []
    if failure == 'create':
        original_open = type(result_path).open
        def failed_open(self, *args, **kwargs):
            if self == result_path:
                raise OSError('PRIVATE_OWNER_SECRET')
            return original_open(self, *args, **kwargs)
        monkeypatch.setattr(type(result_path), 'open', failed_open)
    elif failure == 'write':
        original_dump = warning.json.dump
        def failed_dump(value, file, *args, **kwargs):
            if file.name == str(result_path):
                raise OSError('PRIVATE_OWNER_SECRET')
            return original_dump(value, file, *args, **kwargs)
        monkeypatch.setattr(warning.json, 'dump', failed_dump)
    else:
        original_fsync = warning.os.fsync
        def failed_fsync(fd):
            if warning.os.path.exists(result_path):
                raise OSError('PRIVATE_OWNER_SECRET')
            return original_fsync(fd)
        monkeypatch.setattr(warning.os, 'fsync', failed_fsync)
    def sender(text, **kwargs):
        calls.append(text)
        return ack(text, **kwargs)
    result = run(inputs, tmp_path, sender)
    assert result['delivery'] == 'UNKNOWN_RECONCILE_REQUIRED'
    assert len(calls) == 1
    assert 'PRIVATE_OWNER_SECRET' not in json.dumps(result)
    assert (tmp_path / (artifact['event_key'] + '.json')).exists()
    assert run(inputs, tmp_path, sender)['delivery'] == 'DUPLICATE_RECONCILE_REQUIRED'
    assert len(calls) == 1


def test_broad_acl_refuses_before_send(inputs, tmp_path, monkeypatch):
    if warning.os.name != 'nt':
        pytest.skip('Windows ACL test')
    import subprocess
    grant = subprocess.run(['icacls', str(tmp_path), '/grant', '*S-1-5-32-545:(RX)'],
                           capture_output=True, text=True)
    if grant.returncode:
        pytest.skip('cannot provision test ACL')
    try:
        result = run(inputs, tmp_path, lambda *a, **k: pytest.fail('sent'))
        assert result['delivery'] == 'REFUSED_JOURNAL_UNQUALIFIED'
    finally:
        subprocess.run(['icacls', str(tmp_path), '/remove:g', '*S-1-5-32-545'],
                       capture_output=True, text=True, check=True)


def test_symlink_journal_refuses(inputs, tmp_path):
    linked = tmp_path / 'link'
    try:
        linked.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip('directory symlinks unavailable')
    result = warning.warn(json.dumps(inputs[1]), json.dumps(inputs[2]), now=inputs[0],
                          journal_dir=linked, sender=lambda *a, **k: pytest.fail('sent'))
    assert result['delivery'] == 'REFUSED_JOURNAL_UNQUALIFIED'


def test_redirected_parent_refuses_before_send(inputs, tmp_path, monkeypatch):
    from types import SimpleNamespace
    journal = tmp_path / 'private'
    journal.mkdir()
    original = type(journal).lstat
    parent = tmp_path.absolute()
    def redirected(self, *args, **kwargs):
        info = original(self, *args, **kwargs)
        if self == parent:
            return SimpleNamespace(st_mode=info.st_mode,
                                   st_file_attributes=getattr(info, 'st_file_attributes', 0) | 0x400)
        return info
    monkeypatch.setattr(type(journal), 'lstat', redirected)
    result = warning.warn(json.dumps(inputs[1]), json.dumps(inputs[2]), now=inputs[0],
                          journal_dir=journal, sender=lambda *a, **k: pytest.fail('sent'))
    assert result['delivery'] == 'REFUSED_JOURNAL_UNQUALIFIED'


def test_confirmed_replay_persists_only_native_ack_hashes(inputs, tmp_path):
    sent = run(inputs, tmp_path, lambda text, **kw: {**ack(text, **kw),
                                                     'owner': 'PRIVATE_OWNER_123',
                                                     'message_id': 98765})
    assert sent['delivery'] == 'SENT'
    key = sent['artifact']['event_key']
    sending = json.loads((tmp_path / (key + '.json')).read_text())
    result = json.loads((tmp_path / (key + '.result.json')).read_text())
    assert set(result) == {'state', 'at', 'ack'}
    assert set(result['ack']) == {'state', 'messages', 'native_ack_sha256',
                                  'tag_sha256', 'text_sha256', 'delivery_binding_sha256'}
    assert result['ack']['native_ack_sha256'] == 'a' * 64
    assert result['ack']['tag_sha256'] == sending['tag_sha256']
    assert result['ack']['text_sha256'] == sending['text_sha256']
    assert result['ack']['delivery_binding_sha256'] == warning._digest({
        k: result['ack'][k] for k in warning._ACK_HASH_KEYS})
    assert 'PRIVATE_OWNER_123' not in json.dumps(result)
    assert 'message_id' not in json.dumps(result)
    assert run(inputs, tmp_path, None)['delivery'] == 'ALREADY_SENT'


@pytest.mark.parametrize('target,field,value', [
    ('sending', 'text_sha256', '0' * 64),
    ('sending', 'tag_sha256', '0' * 64),
    ('sending', 'artifact_sha256', '0' * 64),
    ('result', 'state', 'UNKNOWN_RECONCILE_REQUIRED'),
    ('ack', 'native_ack_sha256', '0' * 64),
    ('ack', 'tag_sha256', '0' * 64),
    ('ack', 'text_sha256', '0' * 64),
    ('ack', 'delivery_binding_sha256', '0' * 64),
])
def test_replay_mismatch_blocks_without_sender(inputs, tmp_path, target, field, value):
    sent = run(inputs, tmp_path)
    key = sent['artifact']['event_key']
    file = tmp_path / (key + ('.json' if target == 'sending' else '.result.json'))
    data = json.loads(file.read_text())
    (data['ack'] if target == 'ack' else data)[field] = value
    file.write_text(json.dumps(data))
    assert run(inputs, tmp_path, None)['delivery'] == 'DUPLICATE_RECONCILE_REQUIRED'
    assert run(inputs, tmp_path, lambda *a, **k: pytest.fail('resent'))['delivery'] == 'DUPLICATE_RECONCILE_REQUIRED'


def test_replay_pending_or_incomplete_blocks(inputs, tmp_path):
    sent = run(inputs, tmp_path)
    key = sent['artifact']['event_key']
    pending = tmp_path / (key + '.result.pending.json')
    pending.write_text('incomplete')
    assert run(inputs, tmp_path, None)['delivery'] == 'DUPLICATE_RECONCILE_REQUIRED'
    pending.unlink()
    result = tmp_path / (key + '.result.json')
    result.write_text('{')
    assert run(inputs, tmp_path, None)['delivery'] == 'DUPLICATE_RECONCILE_REQUIRED'


def test_result_link_failure_never_confirms(inputs, tmp_path, monkeypatch):
    def fail_link(*args):
        raise OSError('PRIVATE_NATIVE_ERROR')
    monkeypatch.setattr(warning.os, 'link', fail_link)
    sent = run(inputs, tmp_path)
    assert sent['delivery'] == 'UNKNOWN_RECONCILE_REQUIRED'
    assert 'PRIVATE_NATIVE_ERROR' not in json.dumps(sent)
    assert run(inputs, tmp_path, None)['delivery'] == 'DUPLICATE_RECONCILE_REQUIRED'
