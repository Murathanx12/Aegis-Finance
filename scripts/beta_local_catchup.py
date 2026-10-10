"""Grade only reviewed admissible original copies, using local prices; no live commit option."""
import argparse
from datetime import datetime, date, timezone
import hashlib
import json
from pathlib import Path
import numpy as np

from scripts.beta_catchup_inventory import classify, calendar
from scripts.beta_output_coverage import RESOLUTION, digest
from scripts.original_evidence_audit import Sources, EvidenceRefused


def immutable(r):
    return digest({k:v for k,v in r.items() if k not in RESOLUTION})


def validate_frame(prices):
    import pandas as pd
    if not isinstance(prices.index,pd.DatetimeIndex) or prices.index.tz is not None or prices.index.hasnans or prices.index.has_duplicates or not prices.index.is_monotonic_increasing or prices.columns.has_duplicates:
        raise EvidenceRefused('unique sorted timezone-naive session/date and symbol axes required')
    if any(t!=t.normalize() for t in prices.index):raise EvidenceRefused('daily session labels required')
    if not prices.index.isin(calendar().sessions).all():raise EvidenceRefused('non-XNYS price dates refused')
    values=prices.to_numpy(dtype=float)
    if np.any(np.isfinite(values)&(values<=0)) or np.any(np.isinf(values)):
        raise ValueError('non-positive/nonfinite local prices refused, never zero-filled')


def frame_hash(prices):
    import pandas as pd
    return digest({'columns':list(prices.columns),'dtypes':[str(x) for x in prices.dtypes],
        'rows_sha256':hashlib.sha256(pd.util.hash_pandas_object(prices,index=True).values.tobytes()).hexdigest()})


def window_ready(row,prices,now):
    import pandas as pd
    if classify(row,now)!='MATURE_TARGET_VALID_PRICE_UNVERIFIED':return False
    cal=calendar();i=int(cal.sessions.searchsorted(pd.Timestamp(row['made_at'][:10])))
    required=cal.sessions[i:i+row['horizon_days']+1]
    if len(required)!=row['horizon_days']+1:return False
    for sym in (row['ticker'],row.get('benchmark') if row['observable']=='beats_benchmark' else None):
        if sym is None:continue
        if sym not in prices or not required.isin(prices.index).all():return False
        v=prices.loc[required,sym].to_numpy(dtype=float)
        if not np.isfinite(v).all() or not (v>0).all():return False
    return True


def clone_grade(rows, prices, clone, asof):
    from backend.services import belief_state as B, forecast_ledger as FL
    validate_frame(prices)
    frozen_frame=frame_hash(prices)
    from backend.services.evidence_population import record_hash
    now=datetime.fromisoformat(asof).replace(tzinfo=timezone.utc)
    skips={record_hash(r) for r in rows if not window_ready(r,prices,now)}
    clone=Path(clone)
    if clone.exists():
        raise EvidenceRefused('fresh unique clone path required')
    before={r['prediction_id']:immutable(r) for r in rows}
    if len(before)!=len(rows):
        raise EvidenceRefused('duplicate original IDs')
    clone.parent.mkdir(parents=True,exist_ok=True)
    clone.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
    first=B.resolve_all(prices,clone,today=date.fromisoformat(asof),skip_hashes=skips)
    if frame_hash(prices)!=frozen_frame:raise EvidenceRefused('price frame mutated during grading')
    grades=FL.read_rows(clone,strict=True)
    after={r['prediction_id']:immutable(r) for r in grades}
    if before!=after:
        raise EvidenceRefused('canonical grade changed immutable original evidence')
    first_hash=FL.sha256_file(clone)
    second=B.resolve_all(prices,clone,today=date.fromisoformat(asof),skip_hashes=skips)
    if frame_hash(prices)!=frozen_frame:raise EvidenceRefused('price frame mutated during rerun')
    if FL.sha256_file(clone)!=first_hash or second['newly_resolved']:
        raise EvidenceRefused('canonical clone rerun is not byte-idempotent')
    from backend.services import forecast_reputation as FR, expected_return as ER
    frame=FR.graded_frame_from_rows(grades)
    components=ER._forecast_long(frame)
    return {'newly':first['newly_resolved'],'rerun_newly':second['newly_resolved'],
        'outcome_present':sum(r.get('outcome') is not None for r in grades),
        'immutable_unchanged':True,'clone_sha256':first_hash,'incomplete_or_ineligible_skipped':len(skips),
        'reputation_accepted_rows':len(frame),
        'expected_return_component_rows':{str(k):int(v) for k,v in components['component'].value_counts().items()} if len(components) else {},
        'actual_sizing_changed':False,'runtime_commit':False}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',required=True); ap.add_argument('--now',required=True)
    ap.add_argument('--private-dir',required=True)
    ap.add_argument('--private-price-evidence',help='Existing reviewed private provider-receipt.json; full single-basis frame replaces local panel for clone only')
    a=ap.parse_args()
    from backend.services import forecast_ledger as FL
    import pyarrow.parquet as pq
    import pandas as pd
    root=Path(a.root).resolve(); private=Path(a.private_dir).resolve()
    if private.is_relative_to(root) or private.exists():
        raise EvidenceRefused('fresh private directory outside runtime required')
    now=datetime.fromisoformat(a.now.replace('Z','+00:00'))
    if now.tzinfo is None:raise EvidenceRefused('timezone-aware cutoff required')
    ledger=root/FL.LEGACY_NAME
    if FL.marker_path(ledger).exists() or ledger.stat().st_size>256<<20:
        raise EvidenceRefused('split/oversized ledger refused by this bounded clone path')
    src=Sources(root); rows=[]
    for r in src.jsonl(FL.LEGACY_NAME):
        if classify(r,now)=='MATURE_TARGET_VALID_PRICE_UNVERIFIED':rows.append(r)
    if FL.marker_path(ledger).exists():raise EvidenceRefused('backend changed')
    if len(rows)>100:raise EvidenceRefused('candidate bound100 exceeded')
    syms=sorted({r['ticker'] for r in rows}|{r['benchmark'] for r in rows if r.get('benchmark')})
    start=min(r['made_at'][:10] for r in rows)
    cal=calendar(); closed=[s for s in cal.sessions if cal.session_close(s).to_pydatetime()<=now]
    cutoff=str(closed[-1].date())
    frames=[]; panels=[]
    for rel in ('prices_2025_26/bars.parquet','prices_2025_26/bars_forecast_only.parquet'):
        p=root/rel
        if not p.exists():
            panels.append({'path':rel,'status':'missing; not empty'});continue
        h=FL.sha256_file(p)
        table=pq.read_table(p,columns=['symbol','date','close'],filters=[('symbol','in',syms)])
        f=table.to_pandas(); f['date']=pd.to_datetime(f['date']).dt.tz_localize(None)
        f=f.loc[(f['date']>=start)&(f['date']<=cutoff)]
        if len(f)>200000:raise EvidenceRefused('filtered price bound exceeded')
        if FL.sha256_file(p)!=h:raise EvidenceRefused('price source changed')
        frames.append(f);panels.append({'path':rel,'sha256':h,'filtered_rows':len(f)})
    if not frames:raise EvidenceRefused('no approved existing local price panel')
    long=pd.concat(frames)
    collisions=long.loc[long.duplicated(['symbol','date'],keep=False)]
    if len(collisions) and collisions.groupby(['symbol','date'])['close'].nunique(dropna=False).max()>1:
        raise EvidenceRefused('conflicting symbol/date price collision')
    long=long.drop_duplicates(['symbol','date'],keep='first')
    wide=long.pivot(index='date',columns='symbol',values='close').sort_index()
    provider=None
    evidence_pins=[]
    if a.private_price_evidence:
        receipt_path=Path(a.private_price_evidence).resolve()
        if receipt_path.is_relative_to(root):raise EvidenceRefused('private evidence must be outside runtime')
        receipt_hash=FL.sha256_file(receipt_path)
        provider=json.loads(receipt_path.read_text(encoding='utf-8'))
        supplied=receipt_path.parent/'adjusted_closes.parquet'
        if provider.get('auto_adjust') is not True or provider.get('closed_session_cutoff')!=cutoff:
            raise EvidenceRefused('provider adjustment/cutoff contract mismatch')
        if FL.sha256_file(supplied)!=provider.get('parquet_sha256'):
            raise EvidenceRefused('provider evidence hash mismatch')
        try:wide=pd.read_parquet(supplied)
        except (OSError,ValueError) as exc:raise EvidenceRefused('provider read failed') from exc
        if FL.sha256_file(supplied)!=provider['parquet_sha256'] or FL.sha256_file(receipt_path)!=receipt_hash:
            raise EvidenceRefused('provider frame/receipt changed during read')
        evidence_pins=[(receipt_path,receipt_hash),(supplied,provider['parquet_sha256'])]
        wide.index=pd.to_datetime(wide.index).tz_localize(None)
        if len(wide)>200000 or (len(wide) and str(wide.index.max().date())>cutoff):
            raise EvidenceRefused('provider size/future-close bound violated')
        if not set(wide.columns).issubset(set(provider['requested_symbols'])):
            raise EvidenceRefused('foreign provider symbol')
        panels.append({'provider_evidence':str(receipt_path),'parquet_sha256':provider['parquet_sha256'],
                       'basis':'entire adjusted provider frame; never spliced with stale local prices'})
    def verify_inputs():
        if FL.marker_path(ledger).exists():raise EvidenceRefused('backend changed during provider/grading read')
        for p,h in evidence_pins:
            if FL.sha256_file(p)!=h:raise EvidenceRefused('provider evidence changed')
        for p in panels:
            if 'path' in p and 'sha256' in p and FL.sha256_file(root/p['path'])!=p['sha256']:
                raise EvidenceRefused('local frame changed')
        pin=src.records[FL.LEGACY_NAME]
        if ledger.stat().st_size!=pin['complete_prefix_bytes'] or FL.sha256_file(ledger)!=pin['sha256']:
            raise EvidenceRefused('entire original ledger changed')
    verify_inputs()
    validate_frame(wide)
    private.mkdir(parents=True)
    result=clone_grade(rows,wide,private/'admissible_originals.jsonl',now.date().isoformat())
    result.update(schema='beta_local_catchup/1',as_of_utc=now.isoformat(),closed_session_cutoff=cutoff,
        admissible_originals=len(rows),sources=src.records,local_price_sources=panels,
        original_identity_union_sha256=digest(sorted(immutable(r) for r in rows)),
        local_live_population='unavailable: local live/campaign paths coincide; no separate production source established',
        price_convention='existing canonical local grader close panel; main wins same-symbol/date collision',
        approval_required='isolated proof only; no runtime commit or consumer refit',
        provider_contract=provider,
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    # Verify that the exact complete original prefix remains untouched.
    if FL._prefix_sha256(ledger,src.records[FL.LEGACY_NAME]['complete_prefix_bytes'])!=src.records[FL.LEGACY_NAME]['sha256']:
        raise EvidenceRefused('original source prefix changed')
    verify_inputs()
    (private/'review-packet.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'private_packet':str(private/'review-packet.json'),**{k:result[k] for k in ('admissible_originals','newly','rerun_newly','reputation_accepted_rows','expected_return_component_rows','runtime_commit')}}))


if __name__=='__main__':main()
