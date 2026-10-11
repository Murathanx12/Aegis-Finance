"""Real health consumers must preserve failures, missing evidence and freshness."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.services import legibility as L
from backend.services import legibility_sanitise as LS
from backend.services import telegram_cockpit as CK
from scripts import daily_pass as DP
from backend.services import system_health as SH


@pytest.fixture(autouse=True)
def curated_fixture_services(monkeypatch):
    names = ("worker", "missing", "due_worker", "reader", "model")
    existing = {p.name for p in SH.PROBES}
    extra = [SH.Probe(name, "pc", timedelta(days=1), "synthetic source-owned ID", lambda ctx: None)
             for name in names if name not in existing]
    monkeypatch.setattr(SH, "PROBES", (*SH.PROBES, *extra))


def _receipt(base, stamp, rows):
    folder = base / 'health'
    folder.mkdir(parents=True, exist_ok=True)
    data = {'receipt':'system_health','generated_utc':stamp.isoformat(),
            'exit_code':0,'source':'pc','counts':{},'state_counts':{},'rows':rows}
    (folder / f'health_{stamp:%Y%m%dT%H%M%SZ}.json').write_text(json.dumps(data),encoding='utf-8')
    return data


def _row(now, name='worker', verdict='ALIVE'):
    return {'name':name,'probe':name,'verdict':verdict,'state':verdict,
            'evidence_utc':now.isoformat(),'age_s':0,'proof':'fixture source receipt',
            'detail':'fixture evidence'}


def test_daily_health_call_success_does_not_hide_nested_alarm(monkeypatch):
    now = datetime.now(timezone.utc)
    rows = [_row(now), _row(now,'missing','UNKNOWN')]
    monkeypatch.setattr(DP,'run_health_probes',lambda **kw:{'rows':rows,'exit_code':0,'counts':{}})
    result = DP.step_health({'rows':[]})
    assert result['status'] == 'ok'  # acquisition success; no scheduler retry-policy change
    assert result['alarm']['light'] == 'AMBER'
    assert result['alarm']['healthy'] is False
    assert any('UNKNOWN missing' in x for x in result['refusals'])


@pytest.mark.parametrize('offset', [timedelta(hours=-3),timedelta(minutes=5)])
def test_health_projection_cannot_reuse_stale_or_future_green(tmp_path,monkeypatch,offset):
    now = datetime.now(timezone.utc)
    _receipt(tmp_path,now+offset,[_row(now+offset)])
    monkeypatch.setattr(L,'base_dir',lambda:tmp_path)
    result = LS.sanitise(L.system_health_payload(now=now),LS.SPEC['system_health'])
    assert result['observation_current'] is False
    assert result['alarm']['light'] == 'AMBER'
    assert result['groups'][0]['rows'][0]['alarm']['light'] == 'AMBER'


def test_health_projection_retains_frozen_output_red_and_whitelist(tmp_path,monkeypatch):
    now = datetime.now(timezone.utc)
    frozen = _row(now,'due_worker','STALE')
    frozen['detail'] = 'same output for 30 h across 5 probes'
    frozen['same_output'] = True  # Typed producer flag; freeform text never grants progress.
    _receipt(tmp_path,now-timedelta(minutes=1),[frozen,_row(now)])
    monkeypatch.setattr(L,'base_dir',lambda:tmp_path)
    result = L.system_health_payload(now=now)
    result['alarm']['unapproved'] = 'do-not-publish'
    result['alarm']['light_counts']['unapproved'] = 999
    public = LS.sanitise(result,LS.SPEC['system_health'])
    assert public['alarm']['light'] == 'RED'
    assert public['same_output_rows'][0]['alarm']['light'] == 'RED'
    assert 'unapproved' not in public['alarm']
    assert 'unapproved' not in public['alarm']['light_counts']


def test_local_cockpit_names_unknown_and_refused_without_exception_payload(tmp_path,monkeypatch):
    now = datetime.now(timezone.utc)
    rows = [_row(now,'reader','UNKNOWN'),_row(now,'model','REFUSED')]
    rows[0]['detail'] = 'probe raised ValueError: synthetic-private-value'
    _receipt(tmp_path,now,rows)
    monkeypatch.setattr(CK,'_now',lambda:now)
    answer = CK.health_answer(root=tmp_path)
    assert 'RED BROKEN' in answer.text
    assert 'UNKNOWN reader' in answer.text and 'REFUSED model' in answer.text
    assert 'synthetic-private-value' not in answer.text


def test_local_cockpit_does_not_claim_old_all_alive_is_healthy(tmp_path,monkeypatch):
    now = datetime.now(timezone.utc)
    _receipt(tmp_path,now-timedelta(hours=3),[_row(now-timedelta(hours=3))])
    monkeypatch.setattr(CK,'_now',lambda:now)
    answer = CK.health_answer(root=tmp_path)
    assert 'AMBER ATTENTION' in answer.text
    assert 'stale; activity is unverified' in answer.text


@pytest.mark.parametrize('body_clock', [None,'malformed-clock'])
def test_filename_is_not_alarm_observation_proof(tmp_path,monkeypatch,body_clock):
    now=datetime.now(timezone.utc)
    path=tmp_path/'health'/f'health_{now:%Y%m%dT%H%M%SZ}.json'
    data=_receipt(tmp_path,now,[_row(now)])
    data['generated_utc']=body_clock
    path.write_text(json.dumps(data),encoding='utf-8')
    monkeypatch.setattr(L,'base_dir',lambda:tmp_path)
    result=LS.sanitise(L.system_health_payload(now=now),LS.SPEC['system_health'])
    assert result['generated_utc']  # preserved historical filename display
    assert result['observation_clock_source']=='UNAVAILABLE'
    assert result['observation_current'] is False
    assert result['alarm']['healthy'] is False


@pytest.mark.parametrize('offset', [timedelta(days=1),timedelta(hours=-1)])
def test_fresh_receipt_does_not_green_invalid_dynamic_evidence(tmp_path,monkeypatch,offset):
    now=datetime.now(timezone.utc)
    row=_row(now+offset)
    row.update(cadence_s=300,evidence_mode='DYNAMIC',age_s=0)
    _receipt(tmp_path,now,[row])
    monkeypatch.setattr(L,'base_dir',lambda:tmp_path)
    result=LS.sanitise(L.system_health_payload(now=now),LS.SPEC['system_health'])
    assert result['observation_current'] is True
    assert result['alarm']['healthy'] is False
    assert result['groups'][0]['rows'][0]['alarm']['light']!='GREEN'


def test_fine_state_fault_is_named_and_red_on_all_local_consumers(tmp_path,monkeypatch):
    now=datetime.now(timezone.utc)
    row=_row(now,'task:AegisDailyPass')
    row['state']='DEGRADED'
    rec=_receipt(tmp_path,now,[row])
    monkeypatch.setattr(DP,'run_health_probes',lambda **kw:rec)
    daily=DP.step_health({'rows':[]})
    assert daily['status']=='ok' and daily['alarm']['light']=='RED'
    assert any('DEGRADED task:AegisDailyPass' in x for x in daily['refusals'])
    monkeypatch.setattr(CK,'_now',lambda:now)
    assert 'RED DEGRADED task:AegisDailyPass' in CK.health_answer(root=tmp_path).text
    monkeypatch.setattr(L,'base_dir',lambda:tmp_path)
    public=LS.sanitise(L.system_health_payload(now=now),LS.SPEC['system_health'])
    owners={r['task']:r for r in public['task_owners']}
    assert owners['AegisDailyPass']['verdict']=='ALIVE'
    assert owners['AegisDailyPass']['alarm']['light']=='RED'


def test_daily_acquisition_exception_has_safe_non_green_alarm(monkeypatch):
    def fail(**kw):raise OSError('synthetic-private-value')
    monkeypatch.setattr(DP,'run_health_probes',fail)
    result=DP.step_health({'rows':[]})
    assert result['status']=='refused'
    assert result['alarm']['schema']=='health_alarm/1'
    assert result['alarm']['healthy'] is False
    assert 'OSError' in ' '.join(result['refusals'])
    assert 'synthetic-private-value' not in json.dumps(result)


def test_old_exception_receipt_is_redacted_without_rewriting_original(tmp_path,monkeypatch):
    now=datetime.now(timezone.utc)
    row=_row(now,'task:AegisDailyPass','UNKNOWN')
    row.update(detail='receipt reader raised ValueError: synthetic-private-value',
               proof='synthetic-private-value',delta=123)
    _receipt(tmp_path,now,[row])
    path=tmp_path/'health'/f'health_{now:%Y%m%dT%H%M%SZ}.json'
    original=path.read_bytes()
    monkeypatch.setattr(L,'base_dir',lambda:tmp_path)
    public=LS.sanitise(L.system_health_payload(now=now),LS.SPEC['system_health'])
    assert 'synthetic-private-value' not in json.dumps(public)
    projected=public['groups'][0]['rows'][0]
    assert projected['proof']==''
    assert projected['detail']=='service evidence unavailable; consult private receipt'
    assert path.read_bytes()==original


def test_effective_expiry_survives_public_allowlist(tmp_path,monkeypatch):
    now=datetime(2026,10,11,15,tzinfo=timezone.utc)
    row=_row(now)
    row.update(cadence_s=300,evidence_mode='DYNAMIC')
    _receipt(tmp_path,now,[row])
    monkeypatch.setattr(L,'base_dir',lambda:tmp_path)
    public=LS.sanitise(L.system_health_payload(now=now),LS.SPEC['system_health'])
    indicator=public['groups'][0]['rows'][0]['alarm']
    assert indicator['light']=='GREEN' and indicator['evidence_mode']=='DYNAMIC'
    assert datetime.fromisoformat(indicator['valid_until_utc'])==now+timedelta(seconds=375)


@pytest.mark.parametrize("verdict,state", [("UNKNOWN", "UNKNOWN"), ("DEAD", "DEAD"),
    ("STALE", "STALE"), ("REFUSED", "REFUSED"), ("ALIVE", "DEGRADED"),
    ("ALIVE", "ARBITRARY-PAYLOAD"), ("ARBITRARY-PAYLOAD", "ARBITRARY-PAYLOAD")])
def test_every_failed_consumer_withholds_all_arbitrary_payloads(tmp_path, monkeypatch, verdict, state):
    marker = "ARBITRARY-PAYLOAD"
    now = datetime.now(timezone.utc)
    value = _row(now, marker, verdict)
    value.update(state=state, detail=marker, proof=marker, delta=marker, error_type=marker,
        extra={"nested": marker}, cadence_s=300, evidence_mode="DYNAMIC", same_output=True)
    receipt = _receipt(tmp_path, now, [value])
    path = tmp_path/'health'/f'health_{now:%Y%m%dT%H%M%SZ}.json'
    original_bytes = path.read_bytes()
    original_value = json.dumps(value, sort_keys=True)
    monkeypatch.setattr(SH, "_utcnow", lambda: now)
    monkeypatch.setattr(SH, "on_railway", lambda: False)
    monkeypatch.setattr(SH, "make_ctx", lambda **kw: None)
    monkeypatch.setattr(SH, "run", lambda **kw: receipt)
    SH._API_CACHE.clear()
    try:
        assert marker not in json.dumps(SH.api_block())
        assert marker not in json.dumps(SH.api_block())
    finally:
        SH._API_CACHE.clear()
    monkeypatch.setattr(L, "base_dir", lambda: tmp_path)
    public = LS.sanitise(L.system_health_payload(now=now), LS.SPEC['system_health'])
    assert marker not in json.dumps(public)
    monkeypatch.setattr(CK, "_now", lambda: now)
    assert marker not in CK.health_answer(root=tmp_path).text
    monkeypatch.setattr(DP, "run_health_probes", lambda **kw: receipt)
    assert marker not in json.dumps(DP.step_health({'rows': []}))
    assert marker not in json.dumps(SH.fault_rows([value], now=now))
    rendered = {**receipt, 'read_me_first': 'synthetic source fixture'}
    assert marker not in SH.render_table(rendered)
    assert marker not in SH.render_md(rendered)
    assert path.read_bytes() == original_bytes and json.dumps(value, sort_keys=True) == original_value
