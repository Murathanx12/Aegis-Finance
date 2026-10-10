import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
import pytest
from scripts.beta_catchup_commit import execute, REQUIRED_PINS
from scripts.beta_local_catchup import immutable
from scripts.beta_output_coverage import digest
from scripts.original_evidence_audit import EvidenceRefused
from backend.services import forecast_ledger as FL, evidence_population as EP, belief_state as B


@pytest.fixture
def authority(tmp_path,monkeypatch):
    ledger=tmp_path/'runtime'/'predictions.jsonl';ledger.parent.mkdir()
    rows=[dict(prediction_id=str(i),specialist='review:v0',ticker='X',observable='return_sign',
        horizon_days=1,probability=.6,made_at='2026-10-01T12:00:00Z',resolves_after='2026-10-02',evidence_population='campaign_forward',cost_usd=.01,schema_version='1.4.0') for i in range(22)]
    rows.append(dict(rows[0],prediction_id='excluded',specialist='investigator:A_holdout'))
    ledger.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    provider=tmp_path/'private'/'provider-receipt.json';provider.parent.mkdir()
    frame=pd.DataFrame({'X':[10.,11.]},index=pd.to_datetime(['2026-10-01','2026-10-02']))
    price=provider.parent/'adjusted_closes.parquet';frame.to_parquet(price)
    provider.write_text(json.dumps(dict(auto_adjust=True,parquet_sha256=FL.sha256_file(price),closed_session_cutoff='2026-10-09')))
    repo=Path(__file__).resolve().parents[2]
    a=dict(ledger=str(ledger),examination_ledger=str(provider.parent/'examinations.jsonl'),
        original_byte_backup=str(provider.parent/'original.jsonl'),ledger_sha256=FL.sha256_file(ledger),ledger_bytes=ledger.stat().st_size,
        population='campaign_forward',as_of_utc='2026-10-10T12:10:30Z',closed_session_cutoff='2026-10-09',
        provider_receipt=str(provider),provider_receipt_sha256=FL.sha256_file(provider),price_sha256=FL.sha256_file(price),
        source_pins={p:FL.sha256_file(repo/p) for p in REQUIRED_PINS},
        write_contract='canonical_legacy_atomic_replacement',commit_approval='REVIEWED_RUNTIME_COMMIT_APPROVED',
        writer_owner_coordination=dict(owner='private_test_owner',ledger=str(ledger),exclusive_scheduler_coordination=True,valid_until_utc=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()),
        exact_allowlist=[dict(prediction_id=r['prediction_id'],immutable_sha256=immutable(r),population_record_hash=EP.record_hash(r),original_row_sha256=digest(r),expected_terminal_row_sha256=digest(B.resolve_one(r,frame,today=datetime(2026,10,10).date()))) for r in rows[:22]])
    # The real population write-path guard stays active, configured to this test ledger.
    monkeypatch.setattr(EP,'ledger_path',lambda pop:ledger)
    path=provider.parent/'authority.json'
    def save():path.write_text(json.dumps(a));return FL.sha256_file(path)
    return a,path,save,ledger,rows


def test_success_exact22_rerun0_and_immutable_skipped_backup(authority):
    a,path,save,ledger,rows=authority;h=save();original=ledger.read_bytes()
    assert execute(path,h)['planned']==22 and ledger.read_bytes()==original
    assert execute(path,h,commit=True)['written']==22
    first=ledger.read_bytes()
    assert execute(path,h,commit=True)['written']==0 and ledger.read_bytes()==first
    assert Path(a['original_byte_backup']).read_bytes()==original
    after=FL.read_rows(ledger,strict=True)
    assert all(immutable(r)==immutable(s) for r,s in zip(rows,after)) and after[-1]==rows[-1]
    receipts=[json.loads(x) for x in Path(a['examination_ledger']).read_text().splitlines()]
    assert [r['written'] for r in receipts]==[22,0]


@pytest.mark.parametrize('mutation',['terminal','ledger','source','owner','appendonly','population','price','allowlist'])
def test_refuse_before_terminal_write(authority,mutation):
    a,path,save,ledger,rows=authority
    if mutation=='terminal':a['exact_allowlist'][0]['expected_terminal_row_sha256']='0'*64
    elif mutation=='ledger':ledger.write_text(ledger.read_text()+'\n')
    elif mutation=='source':a['source_pins'][REQUIRED_PINS[0]]='0'*64
    elif mutation=='owner':a['writer_owner_coordination']['exclusive_scheduler_coordination']=False
    elif mutation=='appendonly':a['write_contract']='append_only_required'
    elif mutation=='population':a['population']='live_forward'
    elif mutation=='price':a['price_sha256']='0'*64
    elif mutation=='allowlist':a['exact_allowlist'][0]['prediction_id']='excluded'
    original=ledger.read_bytes();h=save()
    with pytest.raises(EvidenceRefused):execute(path,h,commit=True)
    assert ledger.read_bytes()==original and not Path(a['examination_ledger']).exists()


def test_forged_rerun_receipt_cannot_authorize_other_row_drift(authority):
    a,path,save,ledger,rows=authority;h=save();execute(path,h,commit=True)
    after=FL.read_rows(ledger,strict=True);after[-1]['probability']=.9
    ledger.write_text(''.join(json.dumps(r)+'\n' for r in after))
    receipt=Path(a['examination_ledger'])
    r=json.loads(receipt.read_text().splitlines()[0]);r['after_sha256']=FL.sha256_file(ledger);r['after_bytes']=ledger.stat().st_size
    receipt.write_text(json.dumps(r)+'\n')
    original=ledger.read_bytes()
    with pytest.raises(EvidenceRefused,match='rerun original'):execute(path,h,commit=True)
    assert ledger.read_bytes()==original


@pytest.mark.parametrize('destination',['examination_ledger','original_byte_backup'])
def test_hardlink_output_alias_to_price_refuses_without_mutation(authority,destination):
    import os
    a,path,save,ledger,rows=authority
    price=Path(a['provider_receipt']).parent/'adjusted_closes.parquet'
    alias=price.parent/'hardlink.parquet';os.link(price,alias)
    a[destination]=str(alias);h=save()
    original=ledger.read_bytes();evidence=price.read_bytes()
    with pytest.raises(EvidenceRefused,match='aliases'):execute(path,h,commit=True)
    assert ledger.read_bytes()==original and price.read_bytes()==evidence
