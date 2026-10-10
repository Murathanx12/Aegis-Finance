from pathlib import Path
import pandas as pd
import pytest
from scripts.beta_local_catchup import clone_grade


def row():
    return dict(prediction_id='x', specialist='investigator:test', ticker='X', observable='return_sign',
                horizon_days=1, probability=.6, made_at='2026-10-01T12:00:00Z', resolves_after='2026-10-02', evidence_population='campaign_forward')


def test_clone_is_idempotent_and_original_immutable(tmp_path):
    r=row(); frame=pd.DataFrame({'X':[10.,11.]},index=pd.to_datetime(['2026-10-01','2026-10-02']))
    result=clone_grade([r],frame,tmp_path/'clone.jsonl','2026-10-10')
    assert result['newly']==1 and result['rerun_newly']==0
    assert result['immutable_unchanged'] and 'outcome' not in r


def test_missing_bars_are_pending_not_zero(tmp_path):
    frame=pd.DataFrame({'OTHER':[10.]},index=pd.to_datetime(['2026-10-01']))
    result=clone_grade([row()],frame,tmp_path/'clone.jsonl','2026-10-10')
    assert result['newly']==0 and result['outcome_present']==0


def test_zero_price_refuses_before_clone_write(tmp_path):
    frame=pd.DataFrame({'X':[0.,11.]},index=pd.to_datetime(['2026-10-01','2026-10-02']))
    with pytest.raises(ValueError):clone_grade([row()],frame,tmp_path/'clone.jsonl','2026-10-10')
    assert not (tmp_path/'clone.jsonl').exists()


def test_direction_learning_route_packet_is_json_serializable(tmp_path):
    import json
    r=row(); r.update(observable='beats_benchmark',benchmark='SPY',horizon_days=5)
    frame=pd.DataFrame({'X':[10.,11.,12.,13.,14.,15.],'SPY':[10.]*6},
                       index=pd.bdate_range('2026-10-01',periods=6))
    result=clone_grade([r],frame,tmp_path/'clone.jsonl','2026-10-10')
    assert result['expected_return_component_rows']=={'investigator_dir':1}
    json.dumps(result)


def test_non_exchange_date_refuses_before_clone_write(tmp_path):
    r=row();r.update(made_at='2026-10-02T12:00:00Z',resolves_after='2026-10-05')
    frame=pd.DataFrame({'X':[10.,100.,9.]},index=pd.to_datetime(['2026-10-02','2026-10-03','2026-10-05']))
    from scripts.original_evidence_audit import EvidenceRefused
    with pytest.raises(EvidenceRefused,match='non-XNYS'):clone_grade([r],frame,tmp_path/'clone.jsonl','2026-10-10')
    assert not (tmp_path/'clone.jsonl').exists()
