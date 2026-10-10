from pathlib import Path
import pandas as pd
import pytest
from backend.services import xs_ranker as XR, stitched_tickers as ST
from scripts import survivorship_audit_bounded as B


@pytest.fixture
def panels(tmp_path,monkeypatch):
    dates=pd.bdate_range('2025-01-02',periods=240)
    def rows(symbol,ds,close=10.,volume=1000):
        return [dict(symbol=symbol,date=d,open=close,high=close,low=close,close=close,volume=volume) for d in ds]
    living=rows('SPY',dates,100.)+rows('LIVE',dates)+rows('REUSED',dates[-40:],100.)
    living+=rows('DARK',dates[:195])+rows('DARK',dates[195:],volume=0)
    dead=rows('DEAD',dates[:50])+rows('REUSED',dates[:40],1.)
    # Source precedence must retain the living observation over this duplicate.
    dead+=rows('LIVE',dates[:1],999.)
    paths=[tmp_path/'bars.parquet',tmp_path/'bars_delisted.parquet']
    for p,rs in zip(paths,(living,dead)):pd.DataFrame(rs).to_parquet(p)
    monkeypatch.setattr(ST,'registrants',lambda *a,**kw:{})
    return paths


def test_native_whole_loader_equivalence_including_stitched_dead_and_duplicates(panels):
    whole=XR.load_bars(panels)
    assert any(str(s).startswith('REUSED#') for s in whole['symbol'])
    expected=XR.survivorship_audit(whole)
    for size in (1,2,3):
        result=B.audit(panels,chunk_symbols=size,memory_probe=lambda:8.)
        assert result['audit']==expected
        assert result['audit']['n_symbols']==whole['symbol'].nunique()
        assert result['transformed_non_SPY_rows']==int((whole['symbol']!='SPY').sum())
        assert result['input_raw_rows']==sum(pd.read_parquet(p).shape[0] for p in panels)


def test_resource_or_STOP_refuses_before_loader(panels,tmp_path,monkeypatch):
    def forbidden(*a,**kw):pytest.fail('native payload loader entered after refusal')
    monkeypatch.setattr(XR,'load_bars',forbidden)
    with pytest.raises(B.AuditRefused,match='memory'):B.audit(panels,memory_probe=lambda:1.)
    stop=tmp_path/'STOP';stop.touch()
    with pytest.raises(B.AuditRefused,match='STOP'):B.audit(panels,stop_file=stop,memory_probe=lambda:8.)


def test_missing_panel_or_missing_SPY_never_returns_empty(tmp_path):
    with pytest.raises(B.AuditRefused):B.audit([tmp_path/'absent.parquet'],memory_probe=lambda:8.)
    p=tmp_path/'no_spy.parquet';pd.DataFrame([dict(symbol='X',date=pd.Timestamp('2026-10-09'),open=1.,high=1.,low=1.,close=1.,volume=1.)]).to_parquet(p)
    with pytest.raises(B.AuditRefused,match='SPY'):B.audit([p],memory_probe=lambda:8.)


def test_current_input_drift_during_chunk_refuses(panels,monkeypatch):
    native=XR.load_bars;calls=0
    def change(*a,**kw):
        nonlocal calls
        out=native(*a,**kw);calls+=1
        if calls==1:panels[0].write_bytes(panels[0].read_bytes()+b'changed')
        return out
    monkeypatch.setattr(XR,'load_bars',change)
    with pytest.raises(B.AuditRefused,match='drift'):B.audit(panels,chunk_symbols=1,memory_probe=lambda:8.)


def test_adaptive_row_bound_never_loads_oversized_symbol(panels,monkeypatch):
    with pytest.raises(B.AuditRefused,match='row bound'):B.audit(panels,max_chunk_rows=10,memory_probe=lambda:8.)


def test_native_transform_failure_remains_refused(panels,monkeypatch):
    monkeypatch.setattr(XR,'load_bars',lambda *a,**kw:pd.DataFrame())
    with pytest.raises(B.AuditRefused,match='empty'):B.audit(panels,memory_probe=lambda:8.)


def test_memory_measurement_unknown_never_bypasses_guard(panels):
    for value in (None,float('nan')):
        with pytest.raises(B.AuditRefused,match='memory'):B.audit(panels,memory_probe=lambda:value)


def test_default_input_selection_changes_refuse_even_when_original_bytes_unchanged(panels,monkeypatch):
    original=XR.load_bars
    selected=list(panels)
    monkeypatch.setattr(XR,'survivorship_free_paths',lambda:list(selected))
    def change(*args,**kwargs):
        frame=original(*args,**kwargs)
        selected.reverse()  # Same files/hashes, different canonical precedence.
        return frame
    monkeypatch.setattr(XR,'load_bars',change)
    with pytest.raises(B.AuditRefused,match='selection drift'):
        B.audit(chunk_symbols=1,memory_probe=lambda:8.)


def test_explicit_slice_does_not_consult_native_default_selection(panels,monkeypatch):
    expected=XR.survivorship_audit(XR.load_bars(panels))
    def forbidden():pytest.fail('explicit slice consulted native default selection')
    monkeypatch.setattr(XR,'survivorship_free_paths',forbidden)
    out=B.audit(panels,chunk_symbols=1,memory_probe=lambda:8.)
    assert out['audit']==expected
    assert out['native_input_selection_bound'] is False
