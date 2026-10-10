"""Read-only eligibility metadata. Never imports/calls a resolving writer or prices an outcome."""
import argparse
from collections import Counter
from datetime import date, datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re

from scripts.original_evidence_audit import Sources, EvidenceRefused
from scripts.beta_output_coverage import RESOLUTION, digest, dimension


@lru_cache(maxsize=1)
def calendar():
    import exchange_calendars as xc
    return xc.get_calendar('XNYS')


def classify(row, now):
    if row.get('outcome') is not None or any(row.get(k) for k in ('void_reason','voided_at','voided_by','voided')) or str(row.get('resolution_state','')).upper() in ('VOID','VOIDED'):
        return 'ALREADY_TERMINAL'
    if any(row.get(k) for k in ('quarantined','quarantine_reason','quarantined_at')) or str(row.get('resolution_state','')).upper()=='QUARANTINED':
        return 'QUARANTINED_FLAG'
    if row.get('evidence_population') != 'campaign_forward' or not isinstance(row.get('evidence_population'),str):
        return 'NON_CAMPAIGN_OR_UNVERIFIED_POPULATION'
    if isinstance(row.get('evidence'),str) and row['evidence'].upper() in ('REPLAY','SANDBOX'):
        return 'REPLAY_OR_SANDBOX_EXCLUDED'
    if any(row.get(k) is not None and (not isinstance(row[k],str) or re.search(r'iif|trial|sealed|holdout|gold|investigator:[ABCD]_',row[k],re.I)) for k in ('specialist','mechanism_id')):
        return 'GATED_METADATA_ONLY'
    from backend.services.forecast_grader import refusal_for
    if refusal_for(row) != 'NO_BAR_FOR_RESOLUTION_DATE':
        return 'INVALID_OR_UNSUPPORTED_TARGET'
    try:
        p=row.get('probability')
        if isinstance(p,bool) or not isinstance(p,(int,float)) or not math.isfinite(p) or not 0<=p<=1:
            return 'INVALID_PROBABILITY'
        if row.get('observable') in ('abs_move_exceeds','drawdown_exceeds'):
            t=row.get('threshold')
            if isinstance(t,bool) or not isinstance(t,(int,float)) or not math.isfinite(t) or t<0 or (row['observable']=='drawdown_exceeds' and t>1):
                return 'INVALID_THRESHOLD'
        h = row['horizon_days']
        if not isinstance(h, int) or isinstance(h, bool) or h <= 0:
            return 'INVALID_TARGET_OR_HORIZON'
        due = date.fromisoformat(str(row['resolves_after'])[:10])
        made = datetime.fromisoformat(str(row['made_at']).replace('Z', '+00:00'))
        if due > now.date():
            return 'NOT_CALENDAR_DUE'
        cal = calendar()
        import pandas as pd
        index = int(cal.sessions.searchsorted(pd.Timestamp(made.date())))
        first = cal.sessions[index]
        endpoint = cal.sessions[index + h]
        close = cal.session_close(endpoint).to_pydatetime()
        if close > now:
            return 'CALENDAR_DUE_WINDOW_NOT_CLOSED'
        if made.tzinfo is None:
            return 'MATURE_TIMESTAMP_ZONE_UNVERIFIED'
        if made > cal.session_close(first).to_pydatetime():
            return 'ENTRY_CLOSE_PRECEDES_FORECAST_REVIEW_REQUIRED'
        return 'MATURE_TARGET_VALID_PRICE_UNVERIFIED'
    except (KeyError, ValueError, TypeError, IndexError):
        return 'INVALID_TARGET_OR_HORIZON'


def inventory(root, now):
    from backend.services import forecast_ledger as FL
    root = Path(root).resolve()
    path = root / FL.LEGACY_NAME
    marker = FL.marker_path(path)
    if marker.exists():
        raise EvidenceRefused('bounded catch-up inventory currently refuses split backend; use reviewed split census')
    if path.stat().st_size > 256 << 20:
        raise EvidenceRefused('legacy ledger exceeds 256 MiB bound')
    src = Sources(root)
    groups = {}
    seen = {}
    conflicts = 0
    for row in src.jsonl(FL.LEGACY_NAME):
        group = dimension(row.get('mechanism_id') or row.get('specialist'), 'UNATTRIBUTED') + '|' + dimension(row.get('observable'), 'unknown') + '|' + dimension(row.get('horizon_days'), 'unknown')
        g = groups.setdefault(group, {'raw': 0, 'unique': 0, 'states': Counter(),
            'owner': 'attended campaign owner; production scheduler owns genuine live population',
            'grader': 'ledger_resolver.resolve_due / belief_state.resolve_one; target compatibility checked without grading',
            'consumer': 'forecast reputation; E[r] only for approved investigator/thesis_card prefixes',
            'learning_route': 'regularized calibration only after licensed original grades; no LLM outcome lessons',
            'commit_authorized': False})
        g['raw'] += 1
        h = digest({k:v for k,v in row.items() if k not in RESOLUTION})
        identity = row.get('prediction_id')
        if identity in seen:
            if seen[identity] != h:
                conflicts += 1
                g['states']['IMMUTABLE_IDENTITY_CONFLICT'] += 1
            continue
        seen[identity] = h
        g['unique'] += 1
        g['states'][classify(row, now)] += 1
    if marker.exists():
        raise EvidenceRefused('migration marker appeared during inventory')
    for g in groups.values():
        g['states'] = dict(g['states'])
    return {'schema':'beta_catchup_inventory/1', 'as_of_utc':now.isoformat(),
            'source':src.records, 'root':str(root), 'families':groups,
            'immutable_conflicts':conflicts, 'ready_for_commit':False,
            'limits':{'ledger_bytes':256 << 20},
            'limitations':['XNYS session-close maturity is an eligibility screen, not actual per-ticker bar availability.',
                'No official live quarantine comparison was executed; cloud snapshot is never a grading target.',
                'Existing resolver date-based entry may precede an after-close forecast; such rows require review.',
                'Regret route requires same-basis actual ticker and benchmark windows at 5/21/63 sessions; outcomes not read or priced.'],
            'states':dict(sum((Counter(g['states']) for g in groups.values()), Counter()))}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',required=True)
    ap.add_argument('--now',required=True)
    ap.add_argument('--out',required=True)
    a=ap.parse_args()
    now=datetime.fromisoformat(a.now.replace('Z','+00:00'))
    if now.tzinfo is None:
        ap.error('--now must contain a timezone')
    out=Path(a.out).resolve()
    if out.is_relative_to(Path(a.root).resolve()):
        ap.error('private output must stay outside runtime root')
    result=inventory(a.root,now.astimezone(timezone.utc))
    result['generator_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'packet':str(out),'states':result['states'],'ready_for_commit':False}))


if __name__=='__main__':
    main()
