"""Exact reviewed campaign catch-up executor. Default is plan; no provider/network calls.

Legacy canonical writes atomically replace the file; stream-only append requires
a separately approved migration. This tool never migrates or opens trial outcomes.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path

from scripts.beta_local_catchup import immutable, validate_frame, window_ready, frame_hash
from scripts.beta_output_coverage import digest
from scripts.original_evidence_audit import EvidenceRefused

REQUIRED_PINS = ('scripts/beta_catchup_commit.py','scripts/beta_catchup_inventory.py',
    'scripts/beta_local_catchup.py','scripts/beta_output_coverage.py',
    'scripts/original_evidence_audit.py','backend/services/belief_state.py',
    'backend/services/forecast_ledger.py','backend/services/evidence_population.py',
    'backend/services/ledger_resolver.py','backend/services/forecast_grader.py')


def execute(authority_path, authority_sha256, *, commit=False):
    from backend.services import forecast_ledger as FL, belief_state as B
    from backend.services import evidence_population as EP, ledger_resolver as LR
    import pandas as pd
    ap=Path(authority_path).resolve()
    if FL.sha256_file(ap)!=authority_sha256:raise EvidenceRefused('authority hash mismatch')
    a=json.loads(ap.read_text(encoding='utf-8'))
    ledger=Path(a['ledger']).resolve(); receipt=Path(a['examination_ledger']).resolve()
    repo=Path(__file__).resolve().parents[1]
    if receipt==ledger or receipt.is_relative_to(repo):raise EvidenceRefused('separate examination ledger required')
    now=datetime.fromisoformat(a['as_of_utc'].replace('Z','+00:00'))
    if now.tzinfo is None:raise EvidenceRefused('aware closed-session cutoff required')
    allow=a['exact_allowlist']
    if len(allow)!=22 or len({x['prediction_id'] for x in allow})!=22:
        raise EvidenceRefused('exact distinct 22 authority required')
    if a['population']!='campaign_forward':raise EvidenceRefused('campaign authority only')
    def check_owner():
        owner=a.get('writer_owner_coordination',{})
        if a.get('commit_approval')!='REVIEWED_RUNTIME_COMMIT_APPROVED' or not owner.get('owner') or owner.get('exclusive_scheduler_coordination') is not True or owner.get('ledger')!=str(ledger) or datetime.fromisoformat(owner['valid_until_utc'].replace('Z','+00:00'))<=datetime.now(now.tzinfo):
            raise EvidenceRefused('explicit current owner coordination and review approval required')
    if commit:check_owner()
    provider=Path(a['provider_receipt']).resolve(); price=provider.parent/'adjusted_closes.parquet'
    backup=Path(a['original_byte_backup']).resolve()
    def check_separation():
        inputs=[ledger,ap,provider,price,ledger.parent/FL.LOCK_NAME,ledger.parent/FL.LOCK_HOLDER_NAME]
        inputs.extend((repo/rel).resolve() for rel in a['source_pins'])
        def aliases(left,right):
            return left==right or (left.exists() and right.exists() and left.samefile(right))
        if aliases(receipt,backup) or any(aliases(out,p) for out in (receipt,backup) for p in inputs):
            raise EvidenceRefused('output aliases pinned input or original backup')
    check_separation()
    def pin_inputs():
        if FL.sha256_file(ap)!=authority_sha256:raise EvidenceRefused('authority drift')
        if set(REQUIRED_PINS)-set(a['source_pins']):raise EvidenceRefused('incomplete source pins')
        for rel,h in a['source_pins'].items():
            p=(repo/rel).resolve()
            if not p.is_relative_to(repo) or FL.sha256_file(p)!=h:raise EvidenceRefused('source/backend drift')
        if FL.marker_path(ledger).exists():raise EvidenceRefused('stream migration requires separate authority')
        if FL.sha256_file(provider)!=a['provider_receipt_sha256'] or FL.sha256_file(price)!=a['price_sha256']:raise EvidenceRefused('price evidence drift')
    pin_inputs()
    p=json.loads(provider.read_text(encoding='utf-8'))
    if p.get('auto_adjust') is not True or p.get('parquet_sha256')!=a['price_sha256'] or p.get('closed_session_cutoff')!=a['closed_session_cutoff']:raise EvidenceRefused('provider contract mismatch')
    prices=pd.read_parquet(price); validate_frame(prices); frozen_frame=frame_hash(prices); pin_inputs()
    from scripts.beta_catchup_inventory import calendar
    closed=calendar().sessions[calendar().sessions<=pd.Timestamp(a['closed_session_cutoff'])][-1]
    if calendar().session_close(closed).to_pydatetime()>now or prices.index.max()>closed:raise EvidenceRefused('unclosed/future price frame')
    # The canonical lock is reentrant; record_terminal re-enters THIS lock.
    with FL.ledger_lock(ledger.parent,purpose='reviewed_beta_catchup'):
        pin_inputs()
        if frame_hash(prices)!=frozen_frame:raise EvidenceRefused('in-memory price frame drift')
        EP.assert_write_allowed('campaign_forward',ledger)
        LR.assert_single_population(ledger,'campaign_forward')
        before_sha=FL.sha256_file(ledger); before_size=ledger.stat().st_size
        if before_size>256<<20:raise EvidenceRefused('ledger byte bound')
        prior=[]
        if receipt.exists():
            prior=[json.loads(line) for line in receipt.read_text(encoding='utf-8').splitlines() if line]
        resumed=any(x.get('authority_sha256')==authority_sha256 and x.get('after_sha256')==before_sha and x.get('after_bytes')==before_size for x in prior)
        if not resumed and (before_sha!=a['ledger_sha256'] or before_size!=a['ledger_bytes']):raise EvidenceRefused('entire ledger drift')
        rows=FL.read_rows(ledger,strict=True); byid={r['prediction_id']:r for r in rows}
        if len(byid)!=len(rows):raise EvidenceRefused('duplicate immutable identity')
        if backup.is_relative_to(ledger.parent) or backup.is_relative_to(repo):raise EvidenceRefused('private original byte backup required')
        if resumed:
            if backup.stat().st_size!=a['ledger_bytes'] or FL.sha256_file(backup)!=a['ledger_sha256']:raise EvidenceRefused('original backup drift')
            terminals={x['prediction_id']:x['expected_terminal_row_sha256'] for x in allow}
            seen=set()
            with backup.open(encoding='utf-8') as f:
                for line in f:
                    original=json.loads(line); key=original['prediction_id']
                    if key in seen or key not in byid or digest(byid[key])!=terminals.get(key,digest(original)):raise EvidenceRefused('rerun original/skipped row drift')
                    seen.add(key)
            if seen!=set(byid):raise EvidenceRefused('rerun identity drift')
        pairs=[]
        for expected in allow:
            r=byid.get(expected['prediction_id'])
            if r is None or immutable(r)!=expected['immutable_sha256']:raise EvidenceRefused('original identity drift')
            if digest(r)==expected['expected_terminal_row_sha256']:
                if not resumed:raise EvidenceRefused('terminal drift without examination receipt')
                continue
            if resumed or EP.record_hash(r)!=expected['population_record_hash'] or digest(r)!=expected['original_row_sha256'] or not window_ready(r,prices,now):raise EvidenceRefused('protected/ineligible/original row drift')
            out=B.resolve_one(dict(r),prices,today=now.date())
            if out is None or immutable(out)!=immutable(r) or digest(out)!=expected['expected_terminal_row_sha256']:raise EvidenceRefused('approved terminal mismatch')
            pairs.append((r,out))
        pin_inputs()
        if frame_hash(prices)!=frozen_frame:raise EvidenceRefused('in-memory price frame drift')
        if FL.sha256_file(ledger)!=before_sha or ledger.stat().st_size!=before_size:raise EvidenceRefused('ledger changed under lock')
        result={'planned':len(pairs),'written':0,'runtime_commit':commit,'canonical_backend':'legacy_atomic_replacement','immutable_unchanged':True}
        if not commit:return result
        if a.get('write_contract')!='canonical_legacy_atomic_replacement':raise EvidenceRefused('legacy is not append-only; explicit contract required')
        if not resumed:
            backup.parent.mkdir(parents=True,exist_ok=True)
            if not backup.exists():
                with ledger.open('rb') as src, backup.open('xb') as dst:
                    while chunk:=src.read(1<<20):dst.write(chunk)
                    dst.flush();os.fsync(dst.fileno())
            if backup.stat().st_size!=a['ledger_bytes'] or FL.sha256_file(backup)!=a['ledger_sha256']:raise EvidenceRefused('original backup drift')
        receipt.parent.mkdir(parents=True,exist_ok=True)
        # Verify receipt destination before entering the terminal mutation.
        with receipt.open('a',encoding='utf-8'):pass
        # Owner lease and path identity must survive the entire preflight.
        check_separation();check_owner();pin_inputs()
        if frame_hash(prices)!=frozen_frame:raise EvidenceRefused('in-memory price frame drift')
        if FL.sha256_file(ledger)!=before_sha or ledger.stat().st_size!=before_size:raise EvidenceRefused('ledger changed under lock')
        recorded=FL.record_terminal(ledger,pairs,kind='resolve',writer='beta_catchup_commit.reviewed_exact22')
        if recorded.get('refused') or recorded['written']!=len(pairs):raise EvidenceRefused('canonical terminal accounting mismatch')
        after=FL.read_rows(ledger,strict=True); aftermap={r['prediction_id']:r for r in after}
        wanted={old['prediction_id']:new for old,new in pairs}
        if len(after)!=len(rows) or set(aftermap)!=set(byid) or any(immutable(r)!=immutable(aftermap[k]) or aftermap[k]!=wanted.get(k,r) for k,r in byid.items()):raise EvidenceRefused('postwrite immutable/skipped audit failed')
        pin_inputs()
        if frame_hash(prices)!=frozen_frame:raise EvidenceRefused('in-memory price frame drift')
        result.update(written=recorded['written'],authority_sha256=authority_sha256,before_sha256=before_sha,before_bytes=before_size,after_sha256=FL.sha256_file(ledger),after_bytes=ledger.stat().st_size,examined_at_utc=datetime.now(now.tzinfo).isoformat(),schema='beta_catchup_examination/1',population='campaign_forward')
        with receipt.open('a',encoding='utf-8') as f:
            f.write(json.dumps(result,sort_keys=True)+'\n'); f.flush(); os.fsync(f.fileno())
        return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--authority',required=True);ap.add_argument('--authority-sha256',required=True)
    ap.add_argument('--commit',action='store_true')
    a=ap.parse_args();print(json.dumps(execute(a.authority,a.authority_sha256,commit=a.commit)))


if __name__=='__main__':main()
