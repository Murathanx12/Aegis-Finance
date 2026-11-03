"""Focused runner checks; no real transport, accounts or runtime corpus."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from scripts import owner_event_warning as runner


@pytest.fixture
def case(tmp_path):
    now = datetime.now(timezone.utc)
    base = tmp_path / 'news_corpus' / 'sec_edgar_8k_ex99_body'
    base.mkdir(parents=True)
    row = dict(source='sec_edgar_8k_ex99_body', first_seen_utc=now.isoformat(),
        published_utc=(now - timedelta(hours=1)).isoformat(),
        url='https://www.sec.gov/Archives/edgar/data/1/000000000126000001/results.htm',
        body='Financial results PRIVATE_OWNER',
        title='8-K - Acme (0000000001) (Filer) — EX-99.1',
        tickers=['ACME'], raw_id='0000000001-26-000001:results.htm')
    source = base / f'{now.date()}.jsonl'
    source.write_text(json.dumps(row) + '\n', encoding='utf-8')
    snapshot = tmp_path / 'pc.json'
    snap = dict(t=now.isoformat(), equity=10000, cash=8000,
        long_market_value=2000, short_market_value=0, n_positions=1,
        positions=[dict(symbol='ACME', qty=20, market_value=2000, current_price=100)])
    snapshot.write_text(json.dumps(snap))
    kwargs = dict(ledger=tmp_path, snapshot=snapshot, journal=tmp_path / 'missing', now=now)
    return kwargs, row, source, snap


def test_preview_no_writes_or_transport(case, monkeypatch):
    kwargs, _, _, _ = case
    def forbidden(*a, **k):
        pytest.fail('transport or journal mutation')
    monkeypatch.setattr(runner.adapter, '_deliver', lambda artifact, **kw:
        {'artifact': artifact, 'delivery': 'NOT_SENT'} if kw['sender'] is None else forbidden())
    before = {p: p.read_bytes() for p in kwargs['ledger'].rglob('*') if p.is_file()}
    code, receipts = runner.run(**kwargs)
    assert code == 0 and receipts[0]['delivery'] == 'NOT_SENT'
    assert 'PRIVATE_OWNER' not in json.dumps(receipts)
    assert before == {p: p.read_bytes() for p in kwargs['ledger'].rglob('*') if p.is_file()}


@pytest.mark.parametrize('mode', ['ambiguous', 'malformed', 'duplicate_hold',
                                  'bad_exposure', 'multi_ticker', 'future'])
def test_refusal_before_delivery(case, monkeypatch, mode):
    kwargs, row, source, snap = case
    if mode == 'future':
        row['first_seen_utc'] = (kwargs['now'] + timedelta(hours=1)).isoformat()
    if mode == 'multi_ticker':
        row['tickers'].append('OTHER')
    source.write_text(json.dumps(row) + '\n')
    if mode == 'ambiguous':
        previous = source.parent / f'{kwargs["now"].date() - timedelta(days=1)}.jsonl'
        previous.write_text(json.dumps(dict(row, body='Other financial results')) + '\n')
    if mode == 'malformed':
        source.write_text('{PRIVATE_OWNER')
    if mode == 'duplicate_hold':
        snap['positions'] *= 2
    if mode == 'bad_exposure':
        snap['cash'] = -1
    kwargs['snapshot'].write_text(json.dumps(snap))
    monkeypatch.setattr(runner.adapter, 'warn_saved_bytes', lambda **k: pytest.fail('delivery reached'))
    code, receipts = runner.run(**kwargs)
    assert code == 2
    assert 'PRIVATE_OWNER' not in json.dumps(receipts)


def test_expired_source_is_dated_and_skipped_without_delivery(case, monkeypatch):
    kwargs, row, source, _ = case
    row['published_utc'] = (kwargs['now'] - timedelta(hours=25)).isoformat()
    source.write_text(json.dumps(row) + '\n')
    monkeypatch.setattr(runner.adapter, 'warn_saved_bytes',
                        lambda **kw: pytest.fail('expired source reached delivery'))
    code, receipts = runner.run(**kwargs)
    assert code == 0
    assert receipts[0]['reason'] == 'SOURCE_STALE'
    assert receipts[0]['delivery'] == 'EXPIRED_SOURCE_SKIPPED'


def test_fresh_held_event_survives_expired_row_in_same_file(case):
    kwargs, row, source, _ = case
    old = dict(row, published_utc=(kwargs['now'] - timedelta(hours=25)).isoformat())
    fresh = dict(row, raw_id='0000000001-26-000002:results.htm',
                 url='https://www.sec.gov/Archives/edgar/data/1/000000000126000002/results.htm',
                 body='New financial results')
    source.write_text(json.dumps(old) + '\n' + json.dumps(fresh) + '\n')
    code, receipts = runner.run(**kwargs)
    assert code == 0
    assert [(x['reason'], x['delivery']) for x in receipts] == [
        ('SOURCE_STALE', 'EXPIRED_SOURCE_SKIPPED'),
        ('SAVED_EVIDENCE_ONLY', 'NOT_SENT')]


def test_fresh_other_holding_survives_expired_apple_like_row(case):
    kwargs, row, source, snap = case
    old = dict(row, published_utc=(kwargs['now'] - timedelta(hours=25)).isoformat())
    fresh = dict(row, tickers=['BETA'], raw_id='0000000001-26-000002:results.htm',
                 url='https://www.sec.gov/Archives/edgar/data/1/000000000126000002/results.htm',
                 body='Beta financial results')
    snap['positions'].append(dict(symbol='BETA', qty=20, market_value=2000, current_price=100))
    snap['n_positions'] = 2
    snap['long_market_value'] = 4000
    snap['cash'] = 6000
    kwargs['snapshot'].write_text(json.dumps(snap))
    source.write_text(json.dumps(old) + '\n' + json.dumps(fresh) + '\n')
    code, receipts = runner.run(**kwargs)
    assert code == 0
    assert [(x['reason'], x['delivery']) for x in receipts] == [
        ('SOURCE_STALE', 'EXPIRED_SOURCE_SKIPPED'),
        ('SAVED_EVIDENCE_ONLY', 'NOT_SENT')]


def test_expired_row_with_bad_sec_identity_still_refuses(case):
    kwargs, row, source, _ = case
    row['published_utc'] = (kwargs['now'] - timedelta(hours=25)).isoformat()
    row['url'] = 'https://example.com/results.htm'
    source.write_text(json.dumps(row) + '\n')
    assert runner.run(**kwargs)[0] == 2


def test_only_two_dates_and_only_held(case):
    kwargs, row, source, _ = case
    (source.parent / f'{kwargs["now"].date() - timedelta(days=2)}.jsonl').write_text('invalid')
    source.write_text(json.dumps(dict(row, tickers=['OTHER'])) + '\n')
    assert runner.run(**kwargs) == (0, [])


def test_missing_gates_block_opt_in(case, monkeypatch):
    kwargs, _, _, _ = case
    monkeypatch.setattr(runner.adapter, 'warn_saved_bytes', lambda **k: pytest.fail('delivery reached'))
    assert runner.run(**kwargs, send=True)[0] == 2


def gates(tmp_path):
    adoption = tmp_path / 'adoption.json'
    adoption.write_text(json.dumps(dict(schema='owner-warning-adoption/3',
        all_manual_deliveries_covered=True, suppressions=[])))
    review = tmp_path / 'review.json'
    payload = dict(schema='owner-warning-review/1', independent_exact_source_review=True,
        reviewer='independent human', adoption_sha256=runner.sha(adoption.read_bytes()),
        sha256={p: runner.sha(runner.read(runner.ROOT / p)) for p in runner.SOURCE_PATHS})
    review.write_text(json.dumps(payload))
    return review, adoption, payload


def test_review_exact_hashes_and_manual_adoption(case, monkeypatch):
    kwargs, _, _, _ = case
    review, adoption, payload = gates(kwargs['ledger'])
    monkeypatch.setattr(runner.adapter, '_journal_identity', lambda p: (1, 1))
    runner.qualify_send(review, adoption, kwargs['journal'], now=kwargs['now'])
    for path in runner.SOURCE_PATHS:
        damaged = dict(payload, sha256={**payload['sha256'], path: '0' * 64})
        review.write_text(json.dumps(damaged))
        with pytest.raises(runner.Refused):
            runner.qualify_send(review, adoption, kwargs['journal'], now=kwargs['now'])
    review.write_text(json.dumps(payload))
    adoption.write_text('{}')
    with pytest.raises(runner.Refused):
        runner.qualify_send(review, adoption, kwargs['journal'], now=kwargs['now'])


@pytest.mark.parametrize('delivery', ['UNKNOWN_RECONCILE_REQUIRED',
                                     'DUPLICATE_RECONCILE_REQUIRED',
                                     'REFUSED_JOURNAL_UNQUALIFIED'])
def test_pending_unknown_no_retry(case, monkeypatch, delivery):
    kwargs, _, _, _ = case
    calls = []
    original = runner.adapter.warn_saved_bytes
    def stub(**kw):
        calls.append(kw)
        result = original(**kw)
        result['delivery'] = delivery
        return result
    monkeypatch.setattr(runner.adapter, 'warn_saved_bytes', stub)
    assert runner.run(**kwargs)[0] == 2
    assert len(calls) == 1


def test_changed_input_refuses(case, monkeypatch):
    kwargs, _, _, _ = case
    original = runner.read
    calls = 0
    def changing(path):
        nonlocal calls
        data = original(path)
        if path == kwargs['snapshot']:
            calls += 1
            if calls > 1:
                return data + b' '
        return data
    monkeypatch.setattr(runner, 'read', changing)
    assert runner.run(**kwargs)[0] == 2


def test_opt_in_binds_owner_deadline_and_single_attempt(case, monkeypatch):
    from backend.services import telegram_bridge
    kwargs, _, _, _ = case
    review, adoption, _ = gates(kwargs['ledger'])
    monkeypatch.setattr(runner.adapter, '_journal_identity', lambda p: (1, 1))
    monkeypatch.setattr(telegram_bridge, 'owner_chat_id', lambda: '123456')
    sent = []
    def fake_transport(text, **kw):
        sent.append(kw)
        assert kw['expected_owner'] == '123456'
        assert kw['until'] > runner.time.time()
        return {'state': 'UNKNOWN'}
    monkeypatch.setattr(telegram_bridge, 'send_owner_once', fake_transport)
    def fake_adapter(**kw):
        # Exercise injected callback, with no journal mutation or actual network.
        kw['sender']('synthetic', tag='owner-event-warning:test')
        return {'artifact': {'status': 'PROVISIONAL'},
                'delivery': 'UNKNOWN_RECONCILE_REQUIRED'}
    monkeypatch.setattr(runner.adapter, 'warn_saved_bytes', fake_adapter)
    assert runner.run(**kwargs, send=True, review=review, adoption=adoption)[0] == 2
    assert len(sent) == 1


def test_private_journal_gate_failure(case, monkeypatch):
    kwargs, _, _, _ = case
    review, adoption, _ = gates(kwargs['ledger'])
    def fail(path):
        raise OSError('PRIVATE_OWNER')
    monkeypatch.setattr(runner.adapter, '_journal_identity', fail)
    monkeypatch.setattr(runner.adapter, 'warn_saved_bytes', lambda **kw: pytest.fail('send reached'))
    code, receipts = runner.run(**kwargs, send=True, review=review, adoption=adoption)
    assert code == 2 and 'PRIVATE_OWNER' not in json.dumps(receipts)


@pytest.mark.parametrize('previous_exists', [False, True])
def test_missing_current_corpus_never_no_candidate_success(case, previous_exists):
    kwargs, row, source, _ = case
    source.unlink()
    if previous_exists:
        previous = source.parent / f'{kwargs["now"].date() - timedelta(days=1)}.jsonl'
        previous.write_text(json.dumps(dict(row, tickers=['OTHER'])) + '\n')
    assert runner.run(**kwargs)[0] == 2



@pytest.fixture(autouse=True)
def isolate_known_manual_proofs(monkeypatch):
    # Old runner tests concern transport qualification without real manual files.
    monkeypatch.setattr(runner, 'KNOWN_MANUAL_PROOFS', {})


def manual_gate(case, monkeypatch):
    kwargs, row, source, _ = case
    review, adoption, payload = gates(kwargs['ledger'])
    artifact = runner.adapter.build_saved_warning(source_jsonl_path=source,
        pc_paper_snapshot_path=kwargs['snapshot'], ticker='ACME', now=kwargs['now'])
    attempt = dict(schema='owner-warning-manual-fallback/1', event_id='fake-manual-event',
        created_utc=kwargs['now'].isoformat(), source_url=row['url'],
        source_first_seen_utc=row['first_seen_utc'], source_row_sha256='e' * 64,
        snapshot_clock=artifact['snapshot_as_of'], snapshot_sha256=artifact['snapshot_sha256'],
        message_sha256='d' * 64, delivery='SENDING', no_automatic_retry=True,
        basis='manual pre-open fallback, not AEGIS auto forecast')
    ack = dict(state='SENT', messages=1, native_ack_sha256='f' * 64,
        tag_sha256=runner.adapter._digest({'tag': 'fake-manual-event'}), text_sha256='d' * 64)
    ack['delivery_binding_sha256'] = runner.adapter._digest({k: ack[k] for k in runner.adapter._ACK_HASH_KEYS})
    result = dict(status='PLATFORM_ACKNOWLEDGED', ack=ack, owner_read='UNVERIFIED',
                  observed_utc=kwargs['now'].isoformat())
    ap = kwargs['ledger'] / 'manual.attempt.json'
    rp = kwargs['ledger'] / 'manual.result.json'
    ap.write_text(json.dumps(attempt))
    rp.write_text(json.dumps(result))
    record = dict(schema='owner-warning-manual-suppression/1', event_id=attempt['event_id'],
        ticker='ACME', accession=row['raw_id'].split(':')[0], event_key=artifact['event_key'],
        source_url=row['url'], source_first_seen_utc=row['first_seen_utc'],
        snapshot_clock=attempt['snapshot_clock'], snapshot_sha256=artifact['snapshot_sha256'],
        manual_source_row_sha256=attempt['source_row_sha256'],
        corpus_line_sha256=artifact['source_row_sha256'], source_hashes_differ=True,
        tag_sha256=ack['tag_sha256'], attempt_path=str(ap), attempt_sha256=runner.sha(ap.read_bytes()),
        result_path=str(rp), result_sha256=runner.sha(rp.read_bytes()))
    sp = kwargs['ledger'] / 'suppression.json'
    sp.write_text(json.dumps(record))
    adoption.write_text(json.dumps(dict(schema='owner-warning-adoption/3',
        all_manual_deliveries_covered=True,
        suppressions=[dict(path=str(sp), sha256=runner.sha(sp.read_bytes()))])))
    payload['adoption_sha256'] = runner.sha(adoption.read_bytes())
    review.write_text(json.dumps(payload))
    monkeypatch.setattr(runner, 'KNOWN_MANUAL_PROOFS', {
        attempt['event_id']: (record['attempt_sha256'], record['result_sha256'], 'ACME')})
    monkeypatch.setattr(runner, 'private_read', runner.read)
    monkeypatch.setattr(runner.adapter, '_journal_identity', lambda p: (1, 1))
    return review, adoption, payload, sp, record, artifact


def test_manual_schema_success_suppresses_without_adapter_or_transport(case, monkeypatch):
    kwargs, _, _, _ = case
    review, adoption, _, _, _, _ = manual_gate(case, monkeypatch)
    monkeypatch.setattr(runner.adapter, 'warn_saved_bytes', lambda **kw: pytest.fail('adapter send reached'))
    code, receipts = runner.run(**kwargs, send=True, review=review, adoption=adoption)
    assert code == 0 and receipts[0]['delivery'] == 'SUPPRESSED_MANUAL'
    assert not kwargs['journal'].exists()


def test_manual_suppression_survives_a_later_paper_snapshot(case, monkeypatch):
    kwargs, _, _, snap = case
    review, adoption, _, _, _, original = manual_gate(case, monkeypatch)
    snap['positions'][0]['market_value'] = 2100
    snap['positions'][0]['current_price'] = 105
    snap['long_market_value'] = 2100
    snap['cash'] = 7900
    kwargs['snapshot'].write_text(json.dumps(snap))
    refreshed = runner.adapter.build_saved_warning(
        source_jsonl_path=case[2], pc_paper_snapshot_path=kwargs['snapshot'],
        ticker='ACME', now=kwargs['now'])
    assert refreshed['snapshot_sha256'] != original['snapshot_sha256']
    monkeypatch.setattr(runner.adapter, 'warn_saved_bytes',
                        lambda **kw: pytest.fail('duplicate adapter send reached'))
    code, receipts = runner.run(**kwargs, send=True, review=review, adoption=adoption)
    assert code == 0 and receipts[0]['delivery'] == 'SUPPRESSED_MANUAL'


@pytest.mark.parametrize('field,value', [
    ('manual_source_row_sha256', '0' * 64), ('snapshot_sha256', '0' * 64),
    ('corpus_line_sha256', '0' * 64), ('source_hashes_differ', False),
    ('accession', '0000000001-26-000002'), ('source_url', 'https://example.com/results.htm'),
    ('event_key', '0' * 64), ('event_id', 'different-event'),
    ('tag_sha256', '0' * 64), ('attempt_sha256', '0' * 64), ('result_sha256', '0' * 64),
    ('source_first_seen_utc', '2000-01-01T00:00:00Z'),
])
def test_manual_record_mismatch_fails_even_rehashed(case, monkeypatch, field, value):
    kwargs, _, _, _ = case
    review, adoption, payload, sp, record, _ = manual_gate(case, monkeypatch)
    record[field] = value
    sp.write_text(json.dumps(record))
    ad = json.loads(adoption.read_text())
    ad['suppressions'][0]['sha256'] = runner.sha(sp.read_bytes())
    adoption.write_text(json.dumps(ad))
    payload['adoption_sha256'] = runner.sha(adoption.read_bytes())
    review.write_text(json.dumps(payload))
    assert runner.run(**kwargs, send=True, review=review, adoption=adoption)[0] == 2


@pytest.mark.parametrize('missing', ['record', 'attempt', 'result', 'reference'])
def test_manual_missing_proofs_fail_closed(case, monkeypatch, missing):
    kwargs, _, _, _ = case
    review, adoption, payload, sp, record, _ = manual_gate(case, monkeypatch)
    if missing == 'reference':
        ad = json.loads(adoption.read_text())
        ad['suppressions'] = []
        adoption.write_text(json.dumps(ad))
        payload['adoption_sha256'] = runner.sha(adoption.read_bytes())
        review.write_text(json.dumps(payload))
    else:
        from pathlib import Path
        (sp if missing == 'record' else Path(record[missing + '_path'])).unlink()
    assert runner.run(**kwargs, send=True, review=review, adoption=adoption)[0] == 2


def test_suppression_hash_not_silently_adopted(case, monkeypatch):
    kwargs, _, _, _ = case
    review, adoption, _, sp, _, _ = manual_gate(case, monkeypatch)
    sp.write_text(sp.read_text() + ' ')
    assert runner.run(**kwargs, send=True, review=review, adoption=adoption)[0] == 2


def test_native_ack_binding_checked_with_unpinned_additional_manual(case, monkeypatch):
    kwargs, _, _, _ = case
    review, adoption, payload, sp, record, _ = manual_gate(case, monkeypatch)
    from pathlib import Path
    rp = Path(record['result_path'])
    result = json.loads(rp.read_text())
    result['ack']['text_sha256'] = 'b' * 64
    rp.write_text(json.dumps(result))
    record['result_sha256'] = runner.sha(rp.read_bytes())
    sp.write_text(json.dumps(record))
    ad = json.loads(adoption.read_text())
    ad['suppressions'][0]['sha256'] = runner.sha(sp.read_bytes())
    adoption.write_text(json.dumps(ad))
    payload['adoption_sha256'] = runner.sha(adoption.read_bytes())
    review.write_text(json.dumps(payload))
    monkeypatch.setattr(runner, 'KNOWN_MANUAL_PROOFS', {})
    assert runner.run(**kwargs, send=True, review=review, adoption=adoption)[0] == 2



def test_private_suppression_acl_failure_refuses(case, monkeypatch):
    kwargs, _, _, _ = case
    review, adoption, _, _, _, _ = manual_gate(case, monkeypatch)
    def private_failure(path):
        raise OSError('private ACL not qualified')
    monkeypatch.setattr(runner, 'private_read', private_failure)
    assert runner.run(**kwargs, send=True, review=review, adoption=adoption)[0] == 2


def test_no_equal_manual_and_corpus_hash_claim(case, monkeypatch):
    kwargs, _, _, _ = case
    review, adoption, payload, sp, record, _ = manual_gate(case, monkeypatch)
    record['corpus_line_sha256'] = record['manual_source_row_sha256']
    sp.write_text(json.dumps(record))
    ad = json.loads(adoption.read_text())
    ad['suppressions'][0]['sha256'] = runner.sha(sp.read_bytes())
    adoption.write_text(json.dumps(ad))
    payload['adoption_sha256'] = runner.sha(adoption.read_bytes())
    review.write_text(json.dumps(payload))
    assert runner.run(**kwargs, send=True, review=review, adoption=adoption)[0] == 2
