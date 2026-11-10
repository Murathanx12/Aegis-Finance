"""One fixed-META dated assessment; offline harness only, no live sender adapter.

Pins bind bytes, not authorship. Upstream E2/E4/E5 authority is never promoted.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Callable

from backend.services import owner_decision_view as V
from backend.services import owner_decision_bridge as E4
from scripts import current_exposure_link as E5

SCHEMA = 'e6-provisional-owner-assessment/1'
MANIFEST_CAP = 65536
INPUT_CAP = 8 * 1024 * 1024
POLICY_CAP = 16384
MAX_SECONDS = 30
DESCRIPTION = 'A caller-reviewed saved report discusses Meta infrastructure plans; independent confirmation is still needed.'
DESCRIPTION_CODE = 'META_INFRASTRUCTURE_DISCUSSION_CALLER_ATTESTED'
CODE_PATHS = {
    'E2':'backend/services/provisional_event_review.py',
    'E3':'backend/services/owner_decision_view.py',
    'E4':'backend/services/owner_decision_bridge.py',
    'E5':'scripts/current_exposure_link.py',
    'E6':'backend/services/provisional_owner_notice.py',
    'RUNNER':'scripts/provisional_owner_notice.py',
    'TELEGRAM_REFERENCE_ONLY':'backend/services/telegram_bridge.py',
    'JOURNAL_PRIVACY_REFERENCE':'backend/services/owner_event_warning.py',
}
AUTHORITY = dict(E2_direct_issuer_authority=False,E3_warning_authority=False,
                 broker_origin='UNVERIFIED_SAVED_RECEIPT',event_time_holding='UNKNOWN',
                 PIT_security='UNVERIFIED',owner_decision='UNOBSERVED',forecast='NONE',
                 portfolio_action='NONE',upstream_delivery='NOT_ATTEMPTED')

class NoticeRefused(ValueError):
    """Sanitized code only; never private source contents or input paths."""


def refuse(code):
    raise NoticeRefused(code)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value if isinstance(value,bytes) else canonical(value)).hexdigest()


def exact(value,keys):
    if type(value) is not dict or set(value)!=set(keys.split()):
        refuse('INVALID_FIELDS')
    return value


def hash_value(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}',value):
        refuse('INVALID_HASH')
    return value


def clock(value):
    try:return E5.clock(value)
    except V.ViewRefused:refuse('INVALID_CLOCK')


def now():
    return datetime.now(timezone.utc)


class Bounds:
    def __init__(self,seconds=MAX_SECONDS):
        if not isinstance(seconds,(int,float)) or isinstance(seconds,bool) or not 0<seconds<=MAX_SECONDS:
            refuse('INVALID_DEADLINE')
        self.until=time.monotonic()+seconds
        self.wall_until=time.time()+seconds
        self.inputs={}
    def check(self):
        if time.monotonic()>=self.until:refuse('DEADLINE')
    def read(self,pin,cap=INPUT_CAP):
        self.check()
        try:data=E5.read(pin,cap)
        except V.ViewRefused:refuse('PIN_OR_PATH_REFUSED')
        old=self.inputs.get(str(pin.path))
        if old is not None and old!=pin.sha256:refuse('CONFLICTING_INPUT_PIN')
        self.inputs[str(pin.path)]=pin.sha256
        return data


def pin(value):
    exact(value,'path sha256')
    if type(value['path']) is not str or not Path(value['path']).is_absolute():
        refuse('INVALID_INPUT_PATH')
    return E5.Pin(Path(value['path']),hash_value(value['sha256']))


def parse(data):
    try:return E5.parse(data)
    except V.ViewRefused:refuse('INVALID_OR_DUPLICATE_JSON')


def code_pins():
    root=Path(__file__).resolve().parents[2]
    return {k:digest((root/p).read_bytes()) for k,p in CODE_PATHS.items()}


def _policy(policy,source):
    exact(policy,'schema description_code source_sha256 raw_line_sha256 rights max_source_age_seconds max_holding_age_seconds valid_from_utc valid_until_utc')
    if (policy['schema']!='e6-reviewed-message-policy/1' or policy['description_code']!=DESCRIPTION_CODE
            or policy['rights']!='METADATA_ONLY_CALLER_REVIEWED'
            or policy['source_sha256']!=source['source_sha256']
            or policy['raw_line_sha256']!=source['proof_witness_sha256']):
        refuse('POLICY_SOURCE_OR_RIGHTS')
    for name,cap in [('max_source_age_seconds',7*86400),('max_holding_age_seconds',86400)]:
        if type(policy[name]) is not int or not 1<=policy[name]<=cap:refuse('AGE_POLICY_REQUIRED')
    start,end=clock(policy['valid_from_utc']),clock(policy['valid_until_utc'])
    if not start<end or (end-start).total_seconds()>2*86400:refuse('POLICY_INTERVAL')


def _semantic_key(group,source):
    # Stable document identity distinguishes SEC sibling exhibits without
    # mistaking an accession's login CIK for the issuer CIK.
    return digest(dict(event_key=group['event_key'],source_id=source['source_id'],
                       issuer_cik='1326801',symbol='META',security_class='Class A Common Stock',venue='NASDAQ'))


def _message(a):
    c=a['clocks']
    return ('Dated provisional portfolio-review candidate - not a current holding confirmation.\n'
            'META / Class A / NASDAQ. '+DESCRIPTION+'\n'
            f"Published (publisher claim): {c['published_utc'] or 'UNKNOWN'}. First seen: {c['first_seen_utc']}.\n"
            f"Saved holding observation: {c['holding_from_utc']} to {c['holding_until_utc']}. Review: {c['review_at_utc']}.\n"
            'Relation: caller-attested subject plus inferred issuer/class/venue and same-ID nonzero saved position.\n'
            'Broker origin unverified; event-time holding UNKNOWN; PIT security UNVERIFIED. Owner decision UNOBSERVED.\n'
            'Needed: independent issuer/security binding, authenticated fresh holding and event-time continuity.\n'
            'Saved replay; upstream context caller-supplied, not a natural warning. No forecast or portfolio action. Evidence key: '+a['semantic_key'][:24]+'.')


def _build_assessment(manifest: E5.Pin | None=None,*,bounds=None):
    """Read exactly one externally pinned manifest; no writes and no discovery."""
    if type(manifest) is not E5.Pin:refuse('MANIFEST_REQUIRED')
    bounds=bounds or Bounds()
    m=parse(bounds.read(manifest,MANIFEST_CAP))
    exact(m,'schema evidence_mode event_id corpus_root receipt locator page subject mapping mapping_inputs broker policy code_pins')
    if m['schema']!='e6-saved-input-manifest/1' or m['evidence_mode']!='SAVED_REPLAY':refuse('SAVED_MANIFEST_REQUIRED')
    hash_value(m['event_id'])
    if type(m['corpus_root']) is not str or not Path(m['corpus_root']).is_absolute():refuse('INVALID_CORPUS_ROOT')
    if m['code_pins']!=code_pins():refuse('CODE_PIN_MISMATCH')
    exact(m['locator'],'source_key source_sha256 relative_corpus_path container_sha256 line_number')
    locator=E4.RowLocator(**m['locator'])
    try:container,_,_=E4._container(Path(m['corpus_root']),locator)
    except (V.ViewRefused,TypeError):refuse('LOCATOR_REFUSED')
    pins={k:pin(m[k]) for k in ('receipt','page','subject','mapping','broker','policy')}
    exact(m['mapping_inputs'],'master master_meta proxy proxy_receipt')
    maps={k:pin(v) for k,v in m['mapping_inputs'].items()}
    inputs=[manifest,*pins.values(),*maps.values(),E5.Pin(container,hash_value(locator.container_sha256))]
    # Bound the aggregate unique input set before validators may reread it.
    total=0;seen=set()
    for p in inputs:
        if str(p.path) not in seen:
            total+=len(bounds.read(p,MANIFEST_CAP if p==manifest else POLICY_CAP if p==pins['policy'] else INPUT_CAP))
            seen.add(str(p.path))
        if total>INPUT_CAP:refuse('AGGREGATE_INPUT_CAP')
    try:
        e2=V._parse_receipt(bounds.read(pins['receipt']),require_one_group=False)
        e4=E4.build_selected_event_view(receipt_path=pins['receipt'].path,receipt_sha256=pins['receipt'].sha256,
                                       selected_event_id=m['event_id'],corpus_root=Path(m['corpus_root']),locators=[locator])
        bounds.check()
        link=E5.build_link(receipt=pins['receipt'],selected_event_id=m['event_id'],corpus_root=Path(m['corpus_root']),
                           locator=locator,page=pins['page'],subject=pins['subject'],mapping=pins['mapping'],
                           mapping_inputs=maps,broker=pins['broker'])
    except V.ViewRefused:refuse('UPSTREAM_EVIDENCE_REFUSED')
    if link['status']!=E5.CANDIDATE or link['symbol']!='META' or not link['reported_nonzero']:
        refuse('FIXED_META_CANDIDATE_REQUIRED')
    if (link['E2_direct_issuer_authority'] is not False or link['E3_warning_authority'] is not False
            or link['forecast']!='NONE' or link['delivery']!='NOT_ATTEMPTED'):
        refuse('UPSTREAM_AUTHORITY')
    group=next(g for g in e2['groups'] if g['event_id']==m['event_id'])
    if len(group['sources'])!=1:refuse('ONE_SELECTED_SOURCE_REQUIRED')
    source=group['sources'][0]
    policy=parse(bounds.read(pins['policy'],POLICY_CAP));_policy(policy,source)
    current=now()
    source_at=clock(source['first_seen_utc'])
    broker=parse(bounds.read(pins['broker'],65536))
    holding_start=clock(broker['observed_from_utc']);holding_end=clock(broker['observed_until_utc'])
    if max(source_at,holding_end)>current:refuse('FUTURE_INPUT')
    reasons=[]
    if not clock(policy['valid_from_utc'])<=current<=clock(policy['valid_until_utc']):reasons.append('POLICY_EXPIRED_OR_NOT_YET_VALID')
    if (current-source_at).total_seconds()>policy['max_source_age_seconds']:reasons.append('SOURCE_TOO_OLD')
    if (current-holding_end).total_seconds()>policy['max_holding_age_seconds']:reasons.append('HOLDING_TOO_OLD')
    semantic=_semantic_key(group,source)
    # Container/report/broker refreshes do not mint a new semantic identity.
    out=dict(schema=SCHEMA,status='DATED_CALLER_ATTESTED_CANDIDATE',evidence_mode='SAVED_REPLAY',
             semantic_key=semantic,source_version_sha256=source['source_sha256'],
             input_digest=digest({str(i):p.sha256 for i,p in enumerate(inputs)}),manifest_sha256=manifest.sha256,
             policy_sha256=pins['policy'].sha256,code_pins=m['code_pins'],
             description_code=DESCRIPTION_CODE,authority=dict(AUTHORITY),
             E2_decision=group['decision'],E2_reason_codes=group['reason_codes'],
             E4_status=e4['status'],E5_status=link['status'],E2_upstream_authority=e4['upstream_digest_authority'],
             clocks=dict(published_utc=source['published_utc'],first_seen_utc=source['first_seen_utc'],
                         holding_from_utc=broker['observed_from_utc'],holding_until_utc=broker['observed_until_utc'],
                         review_at_utc=current.isoformat()),
             eligible_for_offline_injected_test=not reasons,blocked_reasons=reasons,delivery='NOT_ATTEMPTED')
    out['message']=_message(out)
    if len(out['message'])>3500:refuse('SINGLE_MESSAGE_CAP')
    out['assessment_sha256']=digest(out)
    # Check the exact same input pins after upstream validation, not just once.
    for p in inputs:bounds.read(p,MANIFEST_CAP if p==manifest else INPUT_CAP)
    bounds.check()
    return out


def build_assessment(manifest=None,*,bounds=None):
    try:return _build_assessment(manifest,bounds=bounds)
    except NoticeRefused:raise
    except (OSError,V.ViewRefused,ValueError,TypeError,KeyError,IndexError,OverflowError,RecursionError):
        refuse('ASSESSMENT_INPUT_REFUSED')


def _assessment(a):
    fields='schema status evidence_mode semantic_key source_version_sha256 input_digest manifest_sha256 policy_sha256 code_pins description_code authority E2_decision E2_reason_codes E4_status E5_status E2_upstream_authority clocks eligible_for_offline_injected_test blocked_reasons delivery message assessment_sha256'
    exact(a,fields)
    if (a['schema']!=SCHEMA or a['status']!='DATED_CALLER_ATTESTED_CANDIDATE' or a['evidence_mode']!='SAVED_REPLAY'
            or canonical(a['authority'])!=canonical(AUTHORITY) or a['description_code']!=DESCRIPTION_CODE or a['delivery']!='NOT_ATTEMPTED'
            or a['message']!=_message(a) or a['assessment_sha256']!=digest({k:v for k,v in a.items() if k!='assessment_sha256'})):
        refuse('ASSESSMENT_INTEGRITY')
    if (a['E2_decision'] not in ('REVIEW_EXPOSURE','NO_CHANGE_WITH_REASON')
            or a['E4_status']!='CANDIDATE_FOR_OWNER_REVIEW' or a['E5_status']!=E5.CANDIDATE
            or a['E2_upstream_authority']!='CALLER_SUPPLIED_NOT_TASK_ATTESTED'
            or type(a['eligible_for_offline_injected_test']) is not bool
            or type(a['blocked_reasons']) is not list
            or any(r not in ('POLICY_EXPIRED_OR_NOT_YET_VALID','SOURCE_TOO_OLD','HOLDING_TOO_OLD') for r in a['blocked_reasons'])
            or a['eligible_for_offline_injected_test']!= (not a['blocked_reasons'])):
        refuse('ASSESSMENT_INTEGRITY')
    exact(a['code_pins'],' '.join(CODE_PATHS))
    for v in a['code_pins'].values():hash_value(v)
    V.e2._safe_reason_codes(a['E2_reason_codes'])
    for k in ('semantic_key','source_version_sha256','input_digest','manifest_sha256','policy_sha256','assessment_sha256'):hash_value(a[k])
    exact(a['clocks'],'published_utc first_seen_utc holding_from_utc holding_until_utc review_at_utc')
    for k,v in a['clocks'].items():
        if v is not None:clock(v)


@dataclass(frozen=True)
class OfflineHarness:
    """TEST injection only; production adapter and production grants are absent.

    verify_suppression checks original proof contracts in the external harness;
    this module never converts a legacy/manual ACK into an E6 native ACK.
    """
    sender: Callable
    verify_suppression: Callable


def _external_dir(path):
    if not isinstance(path,Path) or not path.is_absolute() or path.drive.startswith('\\\\') or not path.is_dir():refuse('PRIVATE_EXISTING_JOURNAL_REQUIRED')
    for p in (path,*path.parents):
        info=p.lstat()
        if p.is_symlink() or getattr(info,'st_file_attributes',0)&0x400 or (p/'.git').exists():refuse('JOURNAL_PATH_REFUSED')
    # Owner-created private journal qualification is a real gate, not inferred
    # merely from a writable external folder.
    from backend.services.owner_event_warning import _journal_identity
    try:return _journal_identity(path)
    except OSError:refuse('PRIVATE_JOURNAL_REQUIRED')


def _exclusive(path,value):
    with path.open('xb') as stream:
        stream.write(canonical(value)+b'\n');stream.flush();os.fsync(stream.fileno())


def _ack(value,text,tag,recipient):
    exact(value,'state messages native_ack_sha256 tag_sha256 text_sha256 delivery_binding_sha256 native_witness')
    witness=exact(value['native_witness'],'recipient message_id chat_type')
    if (value['state']!='SENT' or type(value['messages']) is not int or value['messages']!=1
            or witness['recipient']!=recipient or witness['chat_type']!='private'
            or type(witness['message_id']) is not int or witness['message_id']<=0):refuse('ACK_BINDING')
    expected=dict(native_ack_sha256=digest(dict(schema='telegram-native-ack/1',owner=recipient,message_id=witness['message_id'])),
                  tag_sha256=digest(dict(tag=tag)),text_sha256=digest(text.encode()))
    if any(value[k]!=v for k,v in expected.items()) or value['delivery_binding_sha256']!=digest(expected):refuse('ACK_BINDING')
    # Raw recipient/message ID are transient test inputs, never persisted.
    return {k:v for k,v in value.items() if k!='native_witness'}


def _suppression(review_pin,harness,a,bounds):
    review=parse(bounds.read(review_pin,POLICY_CAP))
    exact(review,'schema reviewed_at_utc coverage proofs')
    if (review['schema']!='e6-offline-cross-lane-review/1'
            or review['coverage']!=['LEGACY_AUTO','ALL_KNOWN_MANUAL','E6_JOURNAL']
            or not now()-timedelta(minutes=5)<=clock(review['reviewed_at_utc'])<=now() or type(review['proofs']) is not list
            or not 1<=len(review['proofs'])<=64):refuse('SUPPRESSION_COVERAGE_REQUIRED')
    proof_bytes={};labels=set()
    for p in review['proofs']:
        exact(p,'label lane proof')
        if (p['lane'] not in ('LEGACY_AUTO','MANUAL') or type(p['label']) is not str
                or not re.fullmatch('[A-Z_]{1,48}',p['label']) or p['label'] in labels):refuse('SUPPRESSION_PROOF_FIELDS')
        labels.add(p['label'])
        proof_bytes[p['label']]=bounds.read(pin(p['proof']),65536)
    if 'APPLE_MANUAL' not in labels:refuse('KNOWN_MANUAL_SUPPRESSION_REQUIRED')
    # Contract-specific verification is mandatory and injected for OFFLINE tests.
    # No production proof bridge is inferred from these caller-reviewed bytes.
    try:verdict=harness.verify_suppression(review,proof_bytes,a['semantic_key'])
    except Exception:refuse('SUPPRESSION_PROOF_REFUSED')
    exact(verdict,'schema semantic_key proof_set_sha256 state')
    if (verdict['schema']!='e6-offline-suppression-verdict/1' or verdict['semantic_key']!=a['semantic_key']
            or verdict['proof_set_sha256']!=digest({k:digest(v) for k,v in proof_bytes.items()})
            or verdict['state'] not in ('CLEAR','PRIOR_ACK','UNKNOWN')):refuse('SUPPRESSION_VERDICT')
    return verdict['state']


def _grant(grant_pin,a,suppression_pin,bounds):
    grant=parse(bounds.read(grant_pin,POLICY_CAP))
    exact(grant,'schema test_only authority manifest_sha256 input_digest semantic_key code_pins policy_sha256 suppression_sha256 recipient valid_from_utc valid_until_utc')
    if (grant['schema']!='e6-offline-injection-grant/1' or grant['test_only'] is not True
            or grant['authority']!='DATED_CALLER_ATTESTED_CANDIDATE_ONLY'
            or grant['manifest_sha256']!=a['manifest_sha256'] or grant['input_digest']!=a['input_digest']
            or grant['semantic_key']!=a['semantic_key'] or grant['code_pins']!=code_pins()
            or grant['policy_sha256']!=a['policy_sha256'] or grant['suppression_sha256']!=suppression_pin.sha256):
        refuse('OFFLINE_GRANT_BINDING')
    if type(grant['recipient']) is not str or not re.fullmatch('[1-9][0-9]{0,19}',grant['recipient']):refuse('PRIVATE_RECIPIENT_REQUIRED')
    start,end=clock(grant['valid_from_utc']),clock(grant['valid_until_utc'])
    if not start<=now()<=end or not start<end or (end-start).total_seconds()>3600:refuse('GRANT_EXPIRED_OR_INVALID')
    return grant


def _journal_read(path):
    info=path.lstat()
    if path.is_symlink() or getattr(info,'st_file_attributes',0)&0x400 or info.st_size>MANIFEST_CAP:
        refuse('UNKNOWN_RECONCILE_REQUIRED')
    with path.open('rb') as stream:
        data=stream.read(MANIFEST_CAP+1)
    if len(data)>MANIFEST_CAP:refuse('UNKNOWN_RECONCILE_REQUIRED')
    return parse(V._read_pinned(path,digest(data),MANIFEST_CAP))


def _old_result(sending_path,result_path,current,recipient_sha):
    """No automatic retry after any orphan/unknown attempt. Validate old text."""
    try:
        sending=_journal_read(sending_path)
        result=_journal_read(result_path)
        exact(sending,'schema state semantic_key source_version_sha256 recipient_sha256 artifact artifact_sha256 tag_sha256 text_sha256')
        exact(result,'schema state sending_sha256 ack')
        _assessment(sending['artifact'])
        ack=exact(result['ack'],'state messages native_ack_sha256 tag_sha256 text_sha256 delivery_binding_sha256')
        ack_hashes={k:hash_value(ack[k]) for k in ('native_ack_sha256','tag_sha256','text_sha256')}
        if (sending['schema']!='e6-offline-sending/1' or sending['state']!='SENDING_INJECTED_ONLY'
                or result['schema']!='e6-offline-result/1' or result['state']!='INJECTED_ACKNOWLEDGED'
                or result['sending_sha256']!=digest(sending) or sending['artifact_sha256']!=digest(sending['artifact'])
                or ack['state']!='SENT' or type(ack['messages']) is not int or ack['messages']!=1
                or ack['tag_sha256']!=sending['tag_sha256'] or ack['text_sha256']!=sending['text_sha256']
                or ack['delivery_binding_sha256']!=digest(ack_hashes)
                or sending['text_sha256']!=digest(sending['artifact']['message'].encode())
                or sending['tag_sha256']!=digest(dict(tag='e6-offline:'+current['semantic_key']))
                or sending['semantic_key']!=current['semantic_key']
                or sending['artifact']['semantic_key']!=current['semantic_key']
                or sending['source_version_sha256']!=sending['artifact']['source_version_sha256']):refuse('UNKNOWN_RECONCILE_REQUIRED')
        if sending['recipient_sha256']!=recipient_sha:refuse('RECIPIENT_CHANGED_REVIEW_REQUIRED')
        if sending['source_version_sha256']!=current['source_version_sha256']:refuse('MATERIAL_UPDATE_REVIEW_REQUIRED')
        if sending['artifact']['policy_sha256']!=current['policy_sha256']:refuse('POLICY_CHANGED_REVIEW_REQUIRED')
    except NoticeRefused:raise
    except (OSError,V.ViewRefused,ValueError,KeyError,TypeError):refuse('UNKNOWN_RECONCILE_REQUIRED')
    return dict(state='ALREADY_SENT_INJECTED_ONLY',transport_calls=0,semantic_key=current['semantic_key'])


def _run_notice(manifest=None,*,send=False,harness=None,journal=None,grant=None,suppression=None,max_seconds=MAX_SECONDS):
    """Default is read-only preview. No production sender can be selected by CLI."""
    bounds=Bounds(max_seconds)
    a=build_assessment(manifest,bounds=bounds)
    if not send:
        return dict(state='PREVIEW' if a['eligible_for_offline_injected_test'] else 'PREVIEW_BLOCKED',
                    artifact=a,transport_calls=0,production_send_authority=False)
    if type(harness) is not OfflineHarness or type(grant) is not E5.Pin or type(suppression) is not E5.Pin:
        refuse('OFFLINE_HARNESS_AND_GRANT_REQUIRED')
    if not a['eligible_for_offline_injected_test']:refuse('STALE_OR_EXPIRED_INPUT')
    g=_grant(grant,a,suppression,bounds)
    suppression_state=_suppression(suppression,harness,a,bounds)
    if suppression_state=='UNKNOWN':refuse('CROSS_LANE_UNKNOWN_RECONCILE_REQUIRED')
    if suppression_state=='PRIOR_ACK':
        return dict(state='SUPPRESSED_BY_REVIEWED_TEST_PROOF',transport_calls=0,semantic_key=a['semantic_key'])
    source_manifest=parse(bounds.read(manifest,MANIFEST_CAP))
    policy=parse(bounds.read(pin(source_manifest['policy']),POLICY_CAP))
    expires=min(clock(g['valid_until_utc']).timestamp(),clock(policy['valid_until_utc']).timestamp(),
                (clock(a['clocks']['first_seen_utc'])+timedelta(seconds=policy['max_source_age_seconds'])).timestamp(),
                (clock(a['clocks']['holding_until_utc'])+timedelta(seconds=policy['max_holding_age_seconds'])).timestamp(),
                bounds.wall_until)
    bounds.wall_until=expires
    bounds.until=min(bounds.until,time.monotonic()+max(0,expires-time.time()))
    bounds.check()
    identity=_external_dir(journal)
    source_manifest=parse(bounds.read(manifest,MANIFEST_CAP))
    corpus=Path(source_manifest['corpus_root']).resolve()
    if (journal.resolve()==manifest.path.parent.resolve()
            or journal.resolve()==corpus or corpus in journal.resolve().parents):
        refuse('SOURCE_OUTPUT_REFUSED')
    sending_path=journal/(a['semantic_key']+'.sending.json')
    result_path=journal/(a['semantic_key']+'.result.json')
    recipient_sha=digest(dict(recipient=g['recipient']))
    if sending_path.exists() or result_path.exists():return _old_result(sending_path,result_path,a,recipient_sha)
    tag='e6-offline:'+a['semantic_key']
    record=dict(schema='e6-offline-sending/1',state='SENDING_INJECTED_ONLY',semantic_key=a['semantic_key'],
                source_version_sha256=a['source_version_sha256'],recipient_sha256=recipient_sha,
                artifact=a,artifact_sha256=digest(a),tag_sha256=digest(dict(tag=tag)),text_sha256=digest(a['message'].encode()))
    try:
        bounds.check()
        if _external_dir(journal)!=identity:refuse('JOURNAL_CHANGED')
        _exclusive(sending_path,record)
        # Rebuild source evidence and all explicit pins immediately before dispatch.
        fresh=build_assessment(manifest,bounds=bounds)
        if (fresh['input_digest']!=a['input_digest'] or fresh['semantic_key']!=a['semantic_key']
                or not fresh['eligible_for_offline_injected_test']):refuse('INPUT_CHANGED_BEFORE_DISPATCH')
        _grant(grant,a,suppression,bounds)
        if _suppression(suppression,harness,a,bounds)!='CLEAR':refuse('SUPPRESSION_CHANGED_BEFORE_DISPATCH')
        if _external_dir(journal)!=identity:refuse('JOURNAL_CHANGED')
        bounds.check()
        value=harness.sender(a['message'],tag=tag,expected_owner=g['recipient'],until=bounds.wall_until)
        bounds.check()
        _grant(grant,a,suppression,bounds)
        ack=_ack(value,a['message'],tag,g['recipient'])
        _exclusive(result_path,dict(schema='e6-offline-result/1',state='INJECTED_ACKNOWLEDGED',sending_sha256=digest(record),ack=ack))
        bounds.check()
    except Exception:
        # Includes receipt fsync, late/wrong ACK, timeout and input drift. Never
        # retry or overwrite the SENDING evidence, even when dispatch is unknown.
        refuse('UNKNOWN_RECONCILE_REQUIRED')
    return dict(state='INJECTED_ACKNOWLEDGED',transport_calls=1,semantic_key=a['semantic_key'],
                native_platform_delivery='NOT_ESTABLISHED_BY_TEST')


def run_notice(manifest=None,**kwargs):
    try:return _run_notice(manifest,**kwargs)
    except NoticeRefused:raise
    except Exception:refuse('NOTICE_INPUT_OR_PROOF_REFUSED')
