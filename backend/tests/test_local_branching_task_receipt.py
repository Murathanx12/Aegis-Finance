"""Native-owner journal fixtures; no task, grade, registry or private ledger runs."""
import json
from datetime import datetime,timedelta,timezone
import pytest
from backend.services import task_receipts as TR,system_health as SH

NAME='AegisLocalBranchingPrivateGrade'

def setup(tmp_path,action='WAIT_ENTRY'):
    now=datetime.now(timezone.utc);p=tmp_path/'automation_runs.jsonl'
    ctx=SH.ProbeCtx(optimus_dir=tmp_path/'optimus',now=now,repo=tmp_path,
                    paths={'local_branching_runs':p})
    row={'task':NAME,'utc':now.isoformat(),'action':action,'resource_proof':{
        'child_reaped':True,'aggregate_limit_bytes':512*1024**2,'aggregate_peak_upper_bound':64*1024**2}}
    return ctx,p,row

def judge(ctx,path,row):
    path.write_text(json.dumps(row)+'\n',encoding='utf8')
    return TR.judge(ctx,NAME,{'TaskName':NAME,'Scheduled Task State':'Enabled','Last Result':'0'})

@pytest.mark.parametrize('action,expected',[
    ('WAIT_ENTRY','ALIVE_IDLE_EXPECTED'),('WAIT_SHARED_REFRESH','ALIVE_IDLE_EXPECTED'),
    ('WAIT_CONSTITUENT_MARKS','ALIVE_IDLE_EXPECTED'),('ALREADY_GRADED','ALIVE_IDLE_EXPECTED'),
    ('YIELD_IIF_WINDOW','ALIVE_IDLE_EXPECTED'),('STOP','STOPPED_BY_OPERATOR'),
    ('REFUSED','REFUSED'),('UNRECOGNIZED','DEGRADED')])
def test_actual_owner_actions_do_not_invent_progress(tmp_path,action,expected):
    ctx,p,row=setup(tmp_path,action);assert judge(ctx,p,row).state==expected

def test_original_grade_requires_real_owner_result_and_cleanup(tmp_path):
    ctx,p,row=setup(tmp_path,'GRADED');assert judge(ctx,p,row).state=='DEGRADED'
    row.update(n_books=247,n_twins=0,grade_receipt='existing-grade.json')
    assert judge(ctx,p,row).state=='ALIVE_PROGRESSING'
    row['resource_proof']['child_reaped']=False
    assert judge(ctx,p,row).state=='DEGRADED'

@pytest.mark.parametrize('proof',[None,{},'invalid',{'child_reaped':True,'aggregate_limit_bytes':512*1024**2,'aggregate_peak_upper_bound':512*1024**2}])
def test_wait_requires_owned_child_cleanup_resource_proof(tmp_path,proof):
    ctx,p,row=setup(tmp_path);row['resource_proof']=proof
    assert judge(ctx,p,row).state=='DEGRADED'

@pytest.mark.parametrize('nested,expected',[
    ({'action':'WAIT_REGISTRY_AND_SOURCE_REVIEW'},'ALIVE_IDLE_EXPECTED'),
    ({'action':'REFUSED','reason':'source pin changed'},'REFUSED'),
    ({'action':'FAILED'},'DEGRADED'),
    ({'action':'POPULATION_OPERATED','activation':'NONE','new_frozen_books':0,'marked':0,'pending_entry':10},'ALIVE_IDLE_EXPECTED'),
    ({'action':'POPULATION_OPERATED','activation':'LIVE','new_frozen_books':1,'marked':0,'pending_entry':0},'DEGRADED')])
def test_population_wait_or_failure_is_not_hidden_by_original_grade(tmp_path,nested,expected):
    ctx,p,row=setup(tmp_path,'GRADED');row.update(n_books=247,n_twins=0,grade_receipt='existing-grade.json',population1000=nested)
    assert judge(ctx,p,row).state==expected

@pytest.mark.parametrize('field',['error','errors','traceback'])
def test_population_operated_counts_never_hide_error_fields(tmp_path,field):
    ctx,p,row=setup(tmp_path,'GRADED');row.update(n_books=247,n_twins=0,grade_receipt='existing-grade.json',
        population1000={'action':'POPULATION_OPERATED','activation':'NONE','new_frozen_books':1,'marked':1,'pending_entry':0,field:'actual producer failure'})
    assert judge(ctx,p,row).state=='DEGRADED'

def test_newest_malformed_row_does_not_reuse_prior_healthy_result(tmp_path):
    ctx,p,row=setup(tmp_path,'GRADED');row.update(n_books=247,n_twins=0,grade_receipt='existing-grade.json')
    assert judge(ctx,p,row).state=='ALIVE_PROGRESSING'
    with p.open('a') as f:f.write('{malformed latest write\n')
    assert TR.judge(ctx,NAME,{'Scheduled Task State':'Enabled'}).state not in TR.ALIVE_STATES

def test_owner_identity_clock_and_real_two_hour_cadence(tmp_path):
    ctx,p,row=setup(tmp_path);row['task']='OtherOwner'
    assert judge(ctx,p,row).state=='DEGRADED'
    row['task']=NAME;row['utc']=(ctx.now+timedelta(minutes=2)).isoformat()
    assert judge(ctx,p,row).state=='DEGRADED'
    row['utc']=(ctx.now-timedelta(hours=3)).isoformat()
    assert judge(ctx,p,row).state=='STALE'

def test_private_cadence_override_preserves_other_task_config_fallback(tmp_path,monkeypatch):
    ctx,_,_=setup(tmp_path)
    monkeypatch.setattr(TR._config,'HEALTH_TASK_CADENCE_H',{NAME:99.0,'OtherOwnedTask':6.0})
    private=TR.TASK_RECEIPT[NAME]
    assert private.cadence_h==2.0
    assert TR.allowed_age_s(NAME,private,None,ctx.now)==2*3600*(1+SH.GRACE)
    ordinary=TR.TaskSpec(reader=lambda *_:TR.Reading(),receipt='fixture')
    assert ordinary.cadence_h is None
    assert TR.allowed_age_s('OtherOwnedTask',ordinary,None,ctx.now)==6*3600*(1+SH.GRACE)
    assert TR.allowed_age_s('UndeclaredCadence',ordinary,None,ctx.now)==24*3600*(1+SH.GRACE)
