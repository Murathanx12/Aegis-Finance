import json
from datetime import datetime
from pathlib import Path
import pandas as pd
import pytest
from backend.services import sim_session as SS, xs_ranker as XR, stitched_tickers as ST
from scripts import survivorship_cache_producer as P, survivorship_audit_bounded as B

@pytest.fixture
def environment(tmp_path,monkeypatch):
    root=tmp_path/'optimus';root.mkdir();state=root/'sim';state.mkdir()
    for name,path in {'START_LOCK':state/'start.lock','SESSION_PATH':state/'session.json','STOP_FLAG':state/'STOP'}.items():monkeypatch.setattr(SS,name,path)
    monkeypatch.setattr(P,'process_rows',lambda **k:[])
    monkeypatch.setattr(ST,'registrants',lambda *a,**k:{})
    ds=pd.bdate_range(end=datetime.now().date(),periods=300)
    rows=[dict(symbol=s,date=d,open=10.,high=10.,low=10.,close=10.+i/100,volume=1000.) for s in ('SPY','LIVE') for i,d in enumerate(ds)]
    bars=root/'bars.parquet';pd.DataFrame(rows).to_parquet(bars)
    monkeypatch.setattr(XR,'survivorship_free_paths',lambda:[bars])
    def runner(timeout,stop):return B.audit(stop_file=stop,max_seconds=min(timeout,180),memory_probe=lambda:8.)
    return root,bars,runner

def test_native_cache_and_actual_caller_reuse(environment,monkeypatch):
    root,bars,runner=environment
    old=root/'pc_book/2026-10-08/learn_survivorship_audit.json';old.parent.mkdir(parents=True);old.write_bytes(b'old historic bytes')
    result=P.produce(root=root,budget_seconds=60,audit_runner=runner)
    assert result['status']=='ok'
    cache=Path(result['cache_path']);payload=json.loads(cache.read_text())
    assert cache.parent.name==datetime.now().date().isoformat()
    assert old.read_bytes()==b'old historic bytes' and not SS.START_LOCK.exists()
    from scripts import sim_run as SIM
    monkeypatch.setattr(SIM,'_in_subprocess',lambda *a:pytest.fail('native cache caller loaded whole panel'))
    caller=SIM.u_learn(2,cache.parent)
    assert caller['skipped']=='bars unchanged since this unit last ran'
    assert caller['panel_last_session']==payload['panel_last_session']
    before=cache.read_bytes()
    reused=P.produce(root=root,budget_seconds=60,audit_runner=lambda *a:pytest.fail('unchanged full identity reloaded'))
    assert reused['status']=='nothing_to_do' and cache.read_bytes()==before

@pytest.mark.parametrize('state',['RUNNING','STARTING','STOPPING','UNCLEAN','bogus'])
def test_unsafe_writer_refuses_without_payload(environment,state):
    root,bars,runner=environment;SS.SESSION_PATH.write_text(json.dumps({'state':state}))
    assert P.produce(root=root,budget_seconds=60,audit_runner=lambda *a:pytest.fail('unsafe owner loaded'))['status']=='refused'
    assert not list(root.glob('pc_book/*/learn*'))

def test_other_lock_STOP_and_unknown_process_table_refuse(environment,monkeypatch):
    root,bars,runner=environment;SS.START_LOCK.write_bytes(b'other owner')
    assert P.produce(root=root,budget_seconds=60,audit_runner=runner)['status']=='refused'
    assert SS.START_LOCK.read_bytes()==b'other owner';SS.START_LOCK.unlink()
    SS.STOP_FLAG.touch();assert P.produce(root=root,budget_seconds=60,audit_runner=runner)['status']=='refused';SS.STOP_FLAG.unlink()
    monkeypatch.setattr(P,'process_rows',lambda **k:None)
    assert P.produce(root=root,budget_seconds=60,audit_runner=runner)['status']=='refused'

def test_drift_after_native_audit_cannot_replace_existing_cache(environment):
    root,bars,runner=environment
    good=P.produce(root=root,budget_seconds=60,audit_runner=runner);cache=Path(good['cache_path']);before=cache.read_bytes()
    bars.touch() # native fingerprint changes, immutable SHA still validates existing reuse
    def corrupt(timeout,stop):
        out=runner(timeout,stop);bars.write_bytes(bars.read_bytes()+b'x');return out
    # An input change forces recomputation rather than silently trusting old identity.
    frame=pd.read_parquet(bars);frame.loc[0,'close']+=0.2;frame.to_parquet(bars)
    assert P.produce(root=root,budget_seconds=60,audit_runner=corrupt)['status']=='refused'
    assert cache.read_bytes()==before

def test_hook_reserves_existing_deadline_and_failed_refresh_never_produces(monkeypatch):
    from scripts import daily_pass as D
    seen=[]
    monkeypatch.setattr(D,'run_bars_refresh',lambda **kw:seen.append(kw['timeout_s']) or {'status':'refused','reason':'missing'})
    monkeypatch.setattr(P,'produce',lambda **k:pytest.fail('failed refresh produced audit'))
    r=D.step_bars_refresh({})
    assert r['status']=='refused' and r['survivorship_audit']['status']=='refused'
    assert seen[0] <= D._STEP_BOXES['bars_refresh']-180-60


def test_real_process_schema_competing_sim_and_missing_cmd_refuse(environment,monkeypatch):
    root,bars,runner=environment
    for command in ('python -m scripts.sim_run --session another',None):
        monkeypatch.setattr(P,'process_rows',lambda **k:[{'pid':123,'name':'python.exe','cmd':command}])
        out=P.produce(root=root,budget_seconds=60,audit_runner=lambda *a:pytest.fail('competing process entered audit'))
        assert out['status']=='refused' and not SS.START_LOCK.exists()


def test_subprocess_timeout_leaves_old_cache_and_releases_owned_lock(environment):
    import subprocess
    root,bars,runner=environment;path=root/'pc_book'/datetime.now().date().isoformat()/'learn_survivorship_audit.json';path.parent.mkdir(parents=True);path.write_bytes(b'{"old":true}')
    def expired(*a):raise subprocess.TimeoutExpired('owned native child',15)
    out=P.produce(root=root,budget_seconds=60,audit_runner=expired)
    assert out['status']=='refused' and path.read_bytes()==b'{"old":true}'
    assert not SS.START_LOCK.exists()


def test_new_native_input_appearing_and_mutation_time_STOP_refuse(environment,monkeypatch):
    root,bars,runner=environment
    def appeared(timeout,stop):
        out=runner(timeout,stop)
        new=root/'new_delisted.parquet';pd.read_parquet(bars).to_parquet(new)
        monkeypatch.setattr(XR,'survivorship_free_paths',lambda:[bars,new]);return out
    assert P.produce(root=root,budget_seconds=60,audit_runner=appeared)['status']=='refused'
    monkeypatch.setattr(XR,'survivorship_free_paths',lambda:[bars])
    from backend.services import disk_guard as DG
    append=DG.locked_append_line
    def stopped(*a,**k):
        result=append(*a,**k);SS.STOP_FLAG.touch();return result
    monkeypatch.setattr(DG,'locked_append_line',stopped)
    out=P.produce(root=root,budget_seconds=60,audit_runner=runner)
    assert out['status']=='refused' and not list(root.glob('pc_book/*/learn_survivorship_audit.json'))
    assert not SS.START_LOCK.exists()


def test_native_changed_input_recompute_backs_up_exact_old_bytes(environment):
    root,bars,runner=environment
    first=P.produce(root=root,budget_seconds=60,audit_runner=runner);cache=Path(first['cache_path']);old=cache.read_bytes()
    frame=pd.read_parquet(bars);frame.loc[0,'close']+=0.2;frame.to_parquet(bars)
    out=P.produce(root=root,budget_seconds=60,audit_runner=runner)
    assert out['status']=='ok' and Path(out['backup_path']).read_bytes()==old
    receipt=[json.loads(s) for s in Path(out['examination_path']).read_text().splitlines()]
    assert receipt[-1]['status']=='COMMITTED' and receipt[-1]['backup_path']==out['backup_path']


def test_successful_daily_hook_invokes_existing_producer_and_surfaces_refusal(monkeypatch):
    from scripts import daily_pass as D
    seen=[]
    monkeypatch.setattr(D,'run_bars_refresh',lambda **k:{'status':'ok','rc':0,'panels':{'main':{'rows_added':2}}})
    monkeypatch.setattr(P,'produce',lambda **k:seen.append(k) or {'status':'refused','reason':'active writer'})
    result=D.step_bars_refresh({})
    assert len(seen)==1 and 25<=seen[0]['budget_seconds']<=180
    assert result['status']=='refused' and result['bars_refresh_status']=='ok'
    assert result['survivorship_audit']['reason']=='active writer'


@pytest.mark.parametrize('failure',['STOP','active','timeout'])
def test_actual_daily_hook_exposes_native_producer_guards(environment,monkeypatch,failure):
    import subprocess
    from scripts import daily_pass as D
    root,bars,runner=environment
    monkeypatch.setattr(D,'run_bars_refresh',lambda **k:{'status':'ok','rc':0,'panels':{'main':{'rows_added':2}}})
    native=P.produce
    if failure=='STOP':SS.STOP_FLAG.touch()
    elif failure=='active':SS.SESSION_PATH.write_text(json.dumps({'state':'RUNNING'}))
    else:
        def runner(*a):raise subprocess.TimeoutExpired('owned native child',30)
    monkeypatch.setattr(P,'produce',lambda **kw:native(root=root,audit_runner=runner,**kw))
    result=D.step_bars_refresh({})
    assert result['status']=='refused' and result['survivorship_audit']['status']=='refused'
    assert not list(root.glob('pc_book/*/learn_survivorship_audit.json'))


def test_local_startup_day_rollover_refuses_before_cache_mutation(environment,monkeypatch):
    from datetime import timedelta
    root,bars,runner=environment;next_day=False
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):
            value=datetime.now(tz)
            return value+timedelta(days=1) if next_day else value
    monkeypatch.setattr(P,'datetime',Clock)
    def rollover(timeout,stop):
        nonlocal next_day
        result=runner(timeout,stop);next_day=True;return result
    out=P.produce(root=root,budget_seconds=60,audit_runner=rollover)
    assert out['status']=='refused' and 'day changed' in out['reason']
    assert not list(root.glob('pc_book/*/learn_survivorship_audit.json'))


def test_lost_start_lock_ownership_never_removes_another_owner(environment):
    root,bars,runner=environment
    def lost(timeout,stop):
        out=runner(timeout,stop);SS.START_LOCK.write_bytes(b'new foreign owner');return out
    assert P.produce(root=root,budget_seconds=60,audit_runner=lost)['status']=='refused'
    assert SS.START_LOCK.read_bytes()==b'new foreign owner'
    assert not list(root.glob('pc_book/*/learn_survivorship_audit.json'))


@pytest.mark.parametrize('mutation',['fingerprint','missing_count','invalid_fraction','native_status'])
def test_warm_native_schema_and_fingerprint_corruption_refuses(environment,mutation):
    root,bars,runner=environment
    first=P.produce(root=root,budget_seconds=60,audit_runner=runner);cache=Path(first['cache_path'])
    payload=json.loads(cache.read_text())
    if mutation=='fingerprint':payload['bars_fingerprint']='unusable by native caller'
    elif mutation=='missing_count':del payload['stopped_90d_before_end']
    elif mutation=='invalid_fraction':payload['fraction_dead_90d']=float('nan')
    else:payload['skipped']='unexpected marker changes native health semantics'
    cache.write_text(json.dumps(payload));old=cache.read_bytes()
    out=P.produce(root=root,budget_seconds=60,audit_runner=lambda *a:pytest.fail('corrupt warm cache silently rebuilt'))
    assert out['status']=='refused' and cache.read_bytes()==old


def test_warm_cache_byte_drift_after_last_identity_check_refuses(environment,monkeypatch):
    root,bars,runner=environment;cache=Path(P.produce(root=root,budget_seconds=60,audit_runner=runner)['cache_path'])
    native=P.identity;calls=0
    def changing():
        nonlocal calls
        result=native();calls+=1
        if calls==2:cache.write_bytes(b'changed after last source identity check')
        return result
    monkeypatch.setattr(P,'identity',changing)
    assert P.produce(root=root,budget_seconds=60,audit_runner=lambda *a:pytest.fail('warm path audited'))['status']=='refused'


def test_hardlinked_examination_never_poisons_price_input(environment):
    import os
    root,bars,runner=environment;day=root/'pc_book'/datetime.now().date().isoformat();day.mkdir(parents=True)
    os.link(bars,day/'survivorship_audit_examinations.jsonl');old=bars.read_bytes()
    out=P.produce(root=root,budget_seconds=60,audit_runner=lambda *a:pytest.fail('aliased destination loaded audit'))
    assert out['status']=='refused' and bars.read_bytes()==old
    assert not list(day.glob('*.bin')) and not (day/'learn_survivorship_audit.json').exists()


def test_current_day_junction_cannot_rewrite_old_history(environment):
    import os,subprocess
    root,bars,runner=environment;historic=root/'pc_book/2000-01-01';historic.mkdir(parents=True)
    old=historic/'learn_survivorship_audit.json';old.write_bytes(b'{"history":true}')
    today=root/'pc_book'/datetime.now().date().isoformat()
    assert historic.resolve().is_relative_to(root.resolve()) and today.parent.resolve().is_relative_to(root.resolve())
    try:today.symlink_to(historic,target_is_directory=True)
    except OSError:
        if os.name!='nt':raise
        made=subprocess.run(['cmd','/d','/c','mklink','/J',str(today),str(historic)],capture_output=True)
        assert made.returncode==0, 'private Windows junction fixture unavailable'
    out=P.produce(root=root,budget_seconds=60,audit_runner=lambda *a:pytest.fail('historical alias entered audit'))
    assert out['status']=='refused' and old.read_bytes()==b'{"history":true}'


def test_partial_lock_write_and_temp_cleanup_failure_release_owned_inode(environment,monkeypatch):
    root,bars,runner=environment;fdopen=P.os.fdopen
    class Broken:
        def __init__(self,fd,mode):self.f=fdopen(fd,mode)
        def __enter__(self):return self
        def __exit__(self,*args):self.f.close()
        def write(self,data):self.f.write(data[:3]);self.f.flush();raise OSError('partial write')
    with monkeypatch.context() as scoped:
        scoped.setattr(P.os,'fdopen',Broken)
        assert P.produce(root=root,budget_seconds=60,audit_runner=lambda *a:pytest.fail('partial acquired lock loaded audit'))['status']=='refused'
        assert not SS.START_LOCK.exists()
    from backend.services import disk_guard as DG
    append=DG.locked_append_line;unlink=Path.unlink
    def stopped(*a,**k):
        result=append(*a,**k);SS.STOP_FLAG.touch();return result
    def broken_unlink(p,*a,**k):
        if p.name.startswith('.survivorship_audit_'):raise OSError('temporary cleanup failure')
        return unlink(p,*a,**k)
    monkeypatch.setattr(DG,'locked_append_line',stopped);monkeypatch.setattr(Path,'unlink',broken_unlink)
    with pytest.raises(OSError,match='temporary cleanup'):P.produce(root=root,budget_seconds=60,audit_runner=runner)
    assert not SS.START_LOCK.exists()


def test_self_consistent_changed_audit_counts_require_exact_committed_output(environment):
    root,bars,runner=environment
    first=P.produce(root=root,budget_seconds=60,audit_runner=runner);cache=Path(first['cache_path'])
    data=json.loads(cache.read_text());data['n_symbols']+=100
    cache.write_text(json.dumps(data));changed=cache.read_bytes()
    out=P.produce(root=root,budget_seconds=60,audit_runner=lambda *a:pytest.fail('altered produced output silently recomputed'))
    assert out['status']=='refused' and 'committed' in out['reason']
    assert cache.read_bytes()==changed


@pytest.mark.parametrize('appearing',['default_bars','auxiliary','present_auxiliary_replace'])
def test_native_inventory_appearing_inside_final_hash_snapshot_refuses(environment,monkeypatch,appearing):
    import shutil
    root,bars,runner=environment;selected=[bars];aux=root/'company_tickers.json'
    monkeypatch.setattr(XR,'survivorship_free_paths',lambda:list(selected))
    monkeypatch.setattr(ST,'COMPANY_TICKERS_PATH',aux)
    if appearing=='present_auxiliary_replace':aux.write_text('{}')
    first=P.produce(root=root,budget_seconds=60,audit_runner=runner);cache=Path(first['cache_path']);old=cache.read_bytes()
    original=P.sha;calls=0
    def hashing(path):
        nonlocal calls
        result=original(path)
        if Path(path)==bars:
            calls+=1
            if calls==2:
                if appearing=='default_bars':
                    new=root/'new_delisted.parquet';shutil.copyfile(bars,new);selected.append(new)
                elif appearing=='auxiliary':aux.write_text('{}')
                else:
                    replacement=root/'replacement_company_tickers.json';replacement.write_text('{}')
                    monkeypatch.setattr(ST,'COMPANY_TICKERS_PATH',replacement)
        return result
    monkeypatch.setattr(P,'sha',hashing)
    out=P.produce(root=root,budget_seconds=60,audit_runner=lambda *a:pytest.fail('warm prior audited changed inventory'))
    assert out['status']=='refused' and cache.read_bytes()==old
