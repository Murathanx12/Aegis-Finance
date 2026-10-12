"""Arena grading faults must not hide inside a successful decision pass."""
import asyncio
from datetime import date
from types import SimpleNamespace
import pytest
from backend.services.arena import engine
from backend.services.portfolio_intelligence import scheduler

def isolated_pass(monkeypatch,grading):
    day=date(2026,10,9);calls=[]
    monkeypatch.setattr(engine.spec_mod,'active_specs',lambda:{'synthetic':SimpleNamespace(scan_universe_n=0)})
    monkeypatch.setattr(engine.store,'is_seeded',lambda *a:True)
    monkeypatch.setattr(engine.store,'read_positions',lambda *a:{'positions':{}})
    monkeypatch.setattr(engine.discovery,'candidate_universe',lambda **k:['SYNTHETIC'])
    monkeypatch.setattr(engine.fundamentals,'refresh',lambda *a,**k:{'status':'ok'})
    monkeypatch.setattr(engine.fundamentals,'coverage',lambda *a,**k:{'status':'ok'})
    monkeypatch.setattr(engine.trackers,'observe',lambda *a,**k:{'observations':[]})
    monkeypatch.setattr(engine.trackers,'nominations',lambda *a,**k:[])
    monkeypatch.setattr(engine.discovery,'freeze_day_state',lambda *a,**k:{'state':{},'information_state_hash':'inert'})
    def book(*a,**k):calls.append('book_completed');return {'book_id':'synthetic','status':'ok'}
    monkeypatch.setattr(engine,'run_book',book)
    monkeypatch.setattr(engine.experience,'mature_outcomes',lambda *a,**k:{'resolved':0})
    def grader(*a,**k):
        calls.append('grader')
        if isinstance(grading,Exception):raise grading
        return grading
    monkeypatch.setattr(engine.experience,'resolve_perceptions',grader)
    def reliability(*a,**k):calls.append('reliability_completed');return {'status':'ok'}
    monkeypatch.setattr(engine.reliability,'snapshot',reliability)
    return engine.run_daily(day,panel=SimpleNamespace(sessions=lambda:[day])),calls

@pytest.mark.parametrize('grading,expected',[(RuntimeError('synthetic grading failure'),'FAILED'),
    ({'status':'no_price_frame','total':4,'newly_resolved':0},'UNAVAILABLE')])
def test_grading_failure_is_visible_without_losing_successful_book_work(grading,expected,monkeypatch):
    result,calls=isolated_pass(monkeypatch,grading)
    assert result['grading_status']==expected and result['status']=='DEGRADED'
    assert result['receipts']==[{'book_id':'synthetic','status':'ok'}]
    assert calls==['book_completed','grader','reliability_completed']
    assert result['reliability']['status']=='ok'

@pytest.mark.parametrize('grading,expected',[({'status':'ok','total':4,'newly_resolved':0,'OVERDUE_AND_UNRESOLVED':0,'refused_by_ledger':0,'health':'ok'},'OK'),
    ({'status':'no_records','total':0,'newly_resolved':0},'IDLE_NO_RECORDS')])
def test_completed_or_empty_grading_is_distinct_from_no_prices(grading,expected,monkeypatch):
    result,_=isolated_pass(monkeypatch,grading)
    assert result['grading_status']==expected and result['status']=='ok'

@pytest.mark.parametrize('grading,expected',[(None,'UNAVAILABLE'),({'status':'error'},'FAILED'),
    ({'status':'unexpected'},'UNAVAILABLE')])
def test_unknown_grading_cannot_be_healthy(grading,expected,monkeypatch):
    result,_=isolated_pass(monkeypatch,grading)
    assert result['grading_status']==expected and result['status']=='DEGRADED'

@pytest.mark.parametrize('grading,expected',[({'status':'error'},'FAILED'),
    ({'status':'no_price_frame'},'UNAVAILABLE'),('invalid','UNAVAILABLE')])
def test_scheduler_warns_and_receipts_grading_without_cancelling_completed_decision(grading,expected,monkeypatch,caplog):
    notes=[]
    monkeypatch.setattr(engine,'run_daily',lambda:{'status':'ok','session':'2026-10-09','receipts':[{'status':'ok'}],'perception_grading':grading})
    monkeypatch.setattr(scheduler,'note',lambda **kw:notes.append(kw))
    assert asyncio.run(scheduler._arena_daily_pass()) is True
    assert any(r.levelname=='WARNING' and expected in r.getMessage() for r in caplog.records)
    assert notes[-1]['arena_grading_status']==expected
    assert notes[-1]['arena_decision_completed'] is True


_EMPTY = {"status": "no_records", "total": 0, "newly_resolved": 0}


@pytest.mark.parametrize("changed", [
    {"newly_resolved": 1}, {"newly_resolved": True}, {"newly_resolved": None},
    {"newly_resolved": "0"}, {"total": True}, {"OVERDUE_AND_UNRESOLVED": 1},
    {"OVERDUE_AND_UNRESOLVED": False}, {"refused_by_ledger": 1},
    {"health": "FAILED"}, {"error": "synthetic"}, {"errors": ["synthetic"]},
    {"overdue_ids": ["synthetic"]}, {"resolved": 1}, {"pending_not_yet_due": 1},
])
def test_contradictory_empty_report_propagates_engine_to_receipt_to_health(changed,monkeypatch,tmp_path,caplog):
    from datetime import datetime, timezone
    from backend.services import job_receipts as JR, forecast_populations as FP, belief_state as B
    report=dict(_EMPTY,**changed)
    result,_=isolated_pass(monkeypatch,report)
    assert result["grading_status"]=="UNAVAILABLE" and result["status"]=="DEGRADED"
    monkeypatch.setattr(engine,"run_daily",lambda:result)
    monkeypatch.setattr(JR,"_root",lambda:tmp_path/"job_receipts")
    @JR.receipted("arena_daily")
    async def complete_decision():
        return await scheduler._arena_daily_pass()
    assert asyncio.run(complete_decision()) is True
    assert any(r.levelname=="WARNING" and "UNAVAILABLE" in r.getMessage() for r in caplog.records)
    ledger=tmp_path/"arena"/"predictions.jsonl";ledger.parent.mkdir();ledger.write_text("")
    monkeypatch.setattr(B,"ledger_health",lambda *a,**k:{"status":"ok","n_overdue":0,"problems":[]})
    row=FP.health("arena_forward",root=tmp_path,now=datetime.now(timezone.utc))
    assert row["grading_receipt"]["status"]=="UNAVAILABLE"
    assert row["ledger_status"]=="ok" and row["status"]=="DEGRADED"
    assert row["problems"]==["arena grading observation UNAVAILABLE"]


def test_empty_native_shape_requires_newly_counter_and_accepts_noncontradictory_metadata():
    assert engine._grading_status(_EMPTY)=="IDLE_NO_RECORDS"
    assert engine._grading_status({"status":"no_records","total":0})=="UNAVAILABLE"
    assert engine._grading_status(dict(_EMPTY,health="ok",OVERDUE_AND_UNRESOLVED=0,refused_by_ledger=0))=="IDLE_NO_RECORDS"
