"""Legacy rows-shaped view of the existing approved Arena publication only."""
from datetime import datetime,timezone,date
from pathlib import PurePosixPath
import re,math,copy
class PublicROIUnavailable(ValueError):pass
def primary(payload):
    if payload is None:return None
    if not isinstance(payload,dict) or not isinstance(payload.get('receipts'),list):raise PublicROIUnavailable('ROI_RECEIPT_SCHEMA')
    rows=[r for r in payload['receipts'] if isinstance(r,dict) and r.get('kind')=='paper_accounts_roi']
    if len(rows)!=1:raise PublicROIUnavailable('PRIMARY_ROI_SOURCE_REQUIRED')
    if rows[0].get('status') not in ('FRESH','STALE'):raise PublicROIUnavailable('PRIMARY_ROI_STATE_INVALID')
    return rows[0]
def clock(value):
    if not isinstance(value,str):raise PublicROIUnavailable('ROI_SOURCE_CLOCK_UNKNOWN')
    try:result=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:raise PublicROIUnavailable('ROI_SOURCE_CLOCK_UNKNOWN') from None
    if result.tzinfo is None or result.utcoffset() is None:raise PublicROIUnavailable('ROI_SOURCE_CLOCK_UNKNOWN')
    return result.astimezone(timezone.utc)
def validate_books(books,now):
    if not isinstance(books,list) or not books:raise PublicROIUnavailable('NO_PUBLIC_BOOK_ROWS')
    seen=set()
    for book in books:
        if not isinstance(book,dict):raise PublicROIUnavailable('PUBLIC_BOOK_SCHEMA')
        account=book.get('account')
        if not isinstance(account,str) or not account.strip() or account in seen:raise PublicROIUnavailable('PUBLIC_ACCOUNT_IDENTITY_INVALID_OR_DUPLICATE')
        seen.add(account)
        for field in ('return_pct','spy_same_window_pct','vs_spy_pp'):
            value=book.get(field)
            if value is not None and (type(value) not in (int,float) or not math.isfinite(value)):raise PublicROIUnavailable('PUBLIC_RETURN_TYPE_OR_NONFINITE')
        for field in ('n_holdings','mark_age_days'):
            value=book.get(field)
            if value is not None and (type(value) is not int or value<0):raise PublicROIUnavailable('PUBLIC_COUNT_OR_AGE_INVALID')
        for field in ('inception','last_mark'):
            value=book.get(field)
            if value is not None:
                try:
                    if type(value) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError()
                    day=date.fromisoformat(value)
                except ValueError:raise PublicROIUnavailable('PUBLIC_ROW_DATE_INVALID') from None
                if day>now.date():raise PublicROIUnavailable('PUBLIC_ROW_DATE_FUTURE')
def project(payload,*,now,stale_hours):
    ref=primary(payload)
    if ref is None:raise PublicROIUnavailable('NO_APPROVED_ROI_RECEIPT')
    stamp=clock(ref.get('stamp_utc'));age=(now-stamp).total_seconds()/3600
    if age<0 or age>stale_hours:raise PublicROIUnavailable('PRIMARY_ROI_SOURCE_STALE_OR_FUTURE')
    if ref.get('status')=='MISSING':raise PublicROIUnavailable('PRIMARY_ROI_SOURCE_MISSING')
    books=payload.get('books')
    validate_books(books,now)
    rows=[]
    for book in books:
        if not isinstance(book,dict):raise PublicROIUnavailable('PUBLIC_BOOK_SCHEMA')
        row={key:book.get(key) for key in ('account','family','inception','last_mark','status','source','note','spy_base','mark_status','mark_age_days','spy_same_window_pct','vs_spy_pp')}
        missing=dict(book.get('missing_because') or {})
        for field in ('return_pct','spy_same_window_pct','vs_spy_pp','n_holdings','last_mark','mark_age_days'):
            if book.get(field) is None:missing.setdefault(field,'SOURCE_VALUE_UNAVAILABLE_NO_ZERO_FILL')
        row.update(roi_pct=book.get('return_pct'),n_positions=book.get('n_holdings'),equity=None,start_capital=None,
            missing_because={**missing,'equity':'NOT_IN_APPROVED_PUBLIC_ARENA_VIEW','start_capital':'NOT_IN_APPROVED_PUBLIC_ARENA_VIEW'},
            return_source='EXISTING_ARENA_BOOK_RETURN_NOT_RECOMPUTED')
        rows.append(row)
    file=PurePosixPath(str(ref.get('file') or '').replace('\\','/')).name
    match=re.fullmatch(r'roi_(\d{4}-\d{2}-\d{2}T\d{6}Z)(?:\.nobroker)?\.json',file)
    numbers=payload.get('numbers') or {}
    aggregate={key:numbers.get(key) for key in ('n_ahead_raw','n_ahead_twins','n_ahead_controls','n_ahead_strategy','n_holdings_clusters_ahead','effective_bets_exante','effective_bets_exante_spy_residual','exante_window','exante_n_books','collapse_factor_twins_controls','collapse_factor_holdings_overlap','collapse_factor_exante','n_ahead_dense','status_counts')}
    aggregate.update(all_priced=None,priced_excluding_control_twins=None,by_family=payload.get('by_family'),
        missing_because={'dollar_totals':'NOT_IN_APPROVED_PUBLIC_ARENA_VIEW','raw_account_counts':'OWNER_PERSONAL_BOOKS_EXCLUDED_BY_EXISTING_ARENA_VIEW'})
    return {'schema':'paper_accounts_roi/1','receipt':'paper_accounts_roi','public_view':'arena_allowlist_compatibility/1',
        'licence':(payload.get('top') or {}).get('licence'),'generated_utc':ref['stamp_utc'],'run_id':match.group(1) if match else None,
        'rows':rows,'aggregate':aggregate,'broker_read':payload.get('broker_read'),'mark_status_counts':numbers.get('mark_status_counts'),
        'sources':payload['receipts'],'scope':{'public_view':'EXISTING_ARENA_PERSONAL_BOOK_EXCLUSIONS'},
        'lane_nav_series':None,'market_benchmark':None,'chart':None,'read_me_first':(payload.get('top') or {}).get('read_me_first'),
        'receipt_file':file,'source_dir':'approved_public_arena_view','freshness':{'primary_roi_stamp_utc':ref['stamp_utc'],'primary_roi_age_hours':age,'primary_roi_status':'FRESH',
            'mark_basis':'EACH_ROW_LAST_MARK_AND_EXISTING_MARK_STATUS;NO_SESSION_OR_MARK_PROMOTION'},
        'missing_because':{'dollar_fields':'NOT_PUBLICLY_APPROVED','lane_nav_series':'NOT_IN_APPROVED_PUBLIC_VIEW','market_benchmark':'USE_EACH_ROW_OWN_WINDOW_BENCHMARK','chart':'NOT_IN_APPROVED_PUBLIC_VIEW'}}
def read_public_paper_accounts():
    from backend.services import legibility as L,legibility_sanitise as S,publish_receipts as PR
    now=L._now();live=L.arena_payload(now=now);pub=PR.load_published('arena')
    # Primary ROI stamp only: a later book_dna/wrapper cannot hide an older ROI.
    candidates=[]
    for is_pub,payload in ((False,live),(True,pub)):
        ref=primary(payload)
        if ref is not None:candidates.append((clock(ref.get('stamp_utc')),not is_pub,is_pub,payload))
    if not candidates:raise PublicROIUnavailable('NO_APPROVED_ROI_RECEIPT')
    _,_,is_pub,payload=max(candidates,key=lambda row:row[:2])
    # Same unchanged policy exactly once for either selected storage location.
    # Validate before it can coerce bool/noninteger ages or overwrite state.
    validate_books(payload.get('books'),now)
    payload=copy.deepcopy(payload)
    PR._reage_arena(payload,now)
    approved=S.sanitise(payload,S.SPEC['arena'])
    return project(approved,now=now,stale_hours=L.stale_limit_h('paper_accounts_roi'))
