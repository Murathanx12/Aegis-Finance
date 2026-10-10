import json
from pathlib import Path

from scripts.beta_output_coverage import census


def put(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')


def test_archive_overlap_status_and_idempotency(tmp_path):
    old = dict(prediction_id='one', made_at='2026-09-01', resolves_after='2026-09-03',
               specialist='source:x', observable='direction', horizon_days=2, probability=.6)
    put(tmp_path / 'predictions.jsonl', [dict(old, outcome=1),
        dict(old, prediction_id='two', resolves_after='2026-12-01')])
    put(tmp_path / 'archive/predictions_2026-09.jsonl', [old])
    first = census({'runtime': tmp_path}, as_of='2026-10-10')
    assert first == census({'runtime': tmp_path}, as_of='2026-10-10')
    group = first['row_families']['runtime:forecast:source:x|direction|2']
    assert group['raw'] == 3 and group['unique'] == 2 and group['duplicates'] == 1
    assert group['states'] == {'graded': 1, 'pending': 1}
    assert len(first['sources']) == 2


def test_malformed_and_unknown_due_are_explicit(tmp_path):
    (tmp_path / 'predictions.jsonl').write_text('{broken}\n' + json.dumps(
        {'prediction_id': 'one', 'made_at': '2026-09-01', 'probability': .5}) + '\n')
    result = census({'runtime': tmp_path}, as_of='2026-10-10')
    assert result['errors'][0]['reason'].startswith('malformed')
    assert next(iter(result['row_families'].values()))['states'] == {'unknown_due': 1}
    assert result['complete'] is False


def test_sealed_outputs_are_not_opened(tmp_path, monkeypatch):
    path = tmp_path / 'sealed_holdout/results.jsonl'
    put(path, [{'outcome': 1}])
    original = Path.open
    def refuse(self, *args, **kwargs):
        if self == path:
            raise AssertionError('protected contents opened')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', refuse)
    result = census({'runtime': tmp_path}, as_of='2026-10-10')
    assert result['sources'][0]['coverage'] == 'protected_metadata_only'
    assert result['row_families'] == {}


def test_missing_root_is_not_empty(tmp_path):
    result = census({'cloud': tmp_path / 'missing'}, as_of='2026-10-10')
    assert result['roots']['cloud']['status'] == 'inaccessible'
    assert result['complete'] is False


def test_conflicting_original_probability_is_not_deduplicated(tmp_path):
    row = dict(prediction_id='one', made_at='2026-09-01', resolves_after='2026-09-03', probability=.6)
    put(tmp_path / 'predictions.jsonl', [row, dict(row, probability=.7)])
    result = census({'runtime': tmp_path}, as_of='2026-10-10')
    assert any(e['reason'] == 'conflicting_original_identity' for e in result['errors'])
    assert result['complete'] is False


def test_lossless_monthly_archive_and_active_are_one_union(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    rows = [dict(call_id='first', timestamp='2026-09-02', cost_usd=.04),
            dict(call_id='second', timestamp='2026-09-03', cost_usd=.08)]
    put(tmp_path / 'llm_calls_2026-09.jsonl', rows)
    archive = tmp_path / 'ledger_archive/llm_calls_2026-09.parquet'
    archive.parent.mkdir()
    pq.write_table(pa.table({'line': [json.dumps(r).encode() for r in rows]}), archive)
    result = census({'runtime': tmp_path}, as_of='2026-10-10')
    group = result['row_families']['runtime:llm_calls|unspecified|unspecified']
    assert (group['raw'], group['unique'], group['duplicates']) == (4, 2, 2)
    assert group['first_date'] == '2026-09-02'
    assert group['last_date'] == '2026-09-03'


def test_memory_bound_is_explicit(tmp_path):
    put(tmp_path / 'events.jsonl', [dict(event_id=str(i), date='2026-09-03') for i in range(4)])
    result = census({'runtime': tmp_path}, as_of='2026-10-10', max_unique_records=2)
    assert result['totals']['unique_records'] == 2
    assert any(e['reason'] == 'unique_record_memory_limit' for e in result['errors'])
    assert result['complete'] is False


def test_reused_decision_id_is_not_an_event_identity(tmp_path):
    put(tmp_path / 'alternatives.jsonl', [dict(decision_id='d', action='hold'),
        dict(decision_id='d', action='buy')])
    result = census({'runtime': tmp_path}, as_of='2026-10-10')
    assert result['totals']['unique_records'] == 2
    assert result['errors'] == []


def test_protected_gold_is_inventory_only(tmp_path, monkeypatch):
    path = tmp_path / 'nested/gold/outcomes.jsonl'
    put(path, [{'outcome': 1}])
    original = Path.open
    def refuse(self, *args, **kwargs):
        if self == path:
            raise AssertionError('gold outcome contents opened')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', refuse)
    result = census({'runtime': tmp_path}, as_of='2026-10-10')
    assert result['sources'][0]['coverage'] == 'protected_metadata_only'


def test_backup_overlap_is_reported_without_pooling(tmp_path):
    row = dict(prediction_id='one', made_at='2026-09-01', probability=.6)
    put(tmp_path / 'local/predictions.jsonl', [row])
    put(tmp_path / 'backup/predictions_prefix.jsonl', [row])
    result = census({'runtime': tmp_path / 'local', 'cloud_backup': tmp_path / 'backup'}, as_of='2026-10-10')
    assert result['totals']['unique_records'] == 2
    overlap, = result['forecast_population_overlaps']
    assert overlap['identical_immutable_originals'] == 1
