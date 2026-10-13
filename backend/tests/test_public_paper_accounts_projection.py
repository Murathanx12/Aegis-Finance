import ast,asyncio,copy,importlib.util,json,sys,time,types,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];D=ROOT
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
M=load('candidate_public_roi',ROOT/'backend/services/public_paper_accounts.py')
S=load('actual_sanitiser',ROOT/'backend/services/legibility_sanitise.py')
prtree=ast.parse((ROOT/'backend/services/publish_receipts.py').read_bytes())
reage=next(n for n in prtree.body if isinstance(n,ast.FunctionDef) and n.name=='_reage_arena')
prscope={'datetime':datetime,'L':types.SimpleNamespace(parse_utc=lambda value:M.clock(value) if value else None),'_config':types.SimpleNamespace(PAPER_ACCOUNT_MARK_STALE_DAYS=4),'_ARENA_ROW_LISTS':('books','winners','short_lived','losers')}
exec(compile(ast.Module(body=[reage],type_ignores=[]),'exact-main-reage','exec'),prscope)
NOW=datetime(2026,10,13,tzinfo=timezone.utc)
def payload(days=0):
    stamp=(NOW-timedelta(days=days)).isoformat()
    return {'schema':'legibility/2','page':'arena','receipts':[{'kind':'paper_accounts_roi','file':'paper_accounts/roi_2026-10-12T235436Z.json','stamp_utc':stamp,'status':'FRESH'}],
      'books':[{'account':'baseline-public','family':'reference','return_pct':0,'spy_same_window_pct':None,'last_mark':'2026-10-09','mark_status':'LIVE','mark_age_days':3,'equity':999,'start_capital':100,'secret_key':'PRIVATE_SENTINEL'}],
      'top':{'licence':'PRODUCT_EXPERIMENT'},'numbers':{'n_ahead_raw':0,'mark_status_counts':{'LIVE':1}},'broker_read':{'performed':True}}
def invoke(live,pub):
    L=types.SimpleNamespace(_now=lambda:NOW,arena_payload=lambda now:live,stale_limit_h=lambda kind:48)
    PR=types.SimpleNamespace(load_published=lambda kind:pub,_reage_arena=prscope['_reage_arena'])
    services=types.ModuleType('backend.services');services.legibility=L;services.legibility_sanitise=S;services.publish_receipts=PR
    backend=types.ModuleType('backend');backend.services=services
    with patch.dict(sys.modules,{'backend':backend,'backend.services':services}):return M.read_public_paper_accounts()
class Tests(unittest.TestCase):
 def test_published_primary_beats_stale_live_without_raw_forward(self):
    out=invoke(payload(6),payload())
    self.assertEqual(out['schema'],'paper_accounts_roi/1');self.assertEqual(len(out['rows']),1)
    self.assertEqual(out['rows'][0]['roi_pct'],0);self.assertIsNone(out['rows'][0]['equity']);self.assertIsNone(out['rows'][0]['start_capital'])
    self.assertNotIn('PRIVATE_SENTINEL',json.dumps(out));self.assertEqual(out['generated_utc'],NOW.isoformat())
 def test_new_dna_and_wrapper_do_not_mask_old_primary(self):
    older=payload(6);older['served_utc']=NOW.isoformat();older['receipts'].append({'kind':'book_dna','stamp_utc':NOW.isoformat()})
    with self.assertRaisesRegex(M.PublicROIUnavailable,'STALE'):invoke(None,older)
 def test_primary_order_not_max_other_receipt(self):
    live=payload();pub=payload(1);pub['receipts'].append({'kind':'book_dna','stamp_utc':(NOW+timedelta(days=1)).isoformat()})
    self.assertEqual(invoke(live,pub)['generated_utc'],NOW.isoformat())
 def test_unknown_naive_future_primary_refused(self):
    for stamp in (None,'bad','2026-10-12T23:54:36',(NOW+timedelta(seconds=1)).isoformat()):
        p=payload();p['receipts'][0]['stamp_utc']=stamp
        with self.assertRaises(M.PublicROIUnavailable):invoke(None,p)
 def test_absent_duplicate_empty_are_unavailable(self):
    for p in (None,dict(payload(),books=[]),dict(payload(),receipts=[]),dict(payload(),receipts=payload()['receipts']*2)):
        with self.assertRaises(M.PublicROIUnavailable):invoke(None,p)
 def test_weekend_mark_not_rewritten_or_promoted(self):
    out=invoke(None,payload());row=out['rows'][0]
    self.assertEqual(row['last_mark'],'2026-10-09');self.assertEqual(row['mark_age_days'],3)
    self.assertIn('NO_SESSION_OR_MARK_PROMOTION',out['freshness']['mark_basis'])
 def test_stale_row_kept_explicit_not_empty_green(self):
    p=payload();p['books'][0].update(mark_status='STALE',mark_age_days=9);p['numbers']['mark_status_counts']={'STALE':1}
    out=invoke(None,p);self.assertEqual(out['rows'][0]['mark_status'],'STALE');self.assertEqual(out['mark_status_counts'],{'STALE':1})
 def test_absent_values_never_zero_filled(self):
    p=payload();p['books'][0]['return_pct']=None
    out=invoke(None,p);self.assertIsNone(out['rows'][0]['roi_pct']);self.assertIsNone(out['aggregate']['all_priced']);self.assertIsNone(out['lane_nav_series'])
 def test_mixed_contract_compatibility_fields_and_source_date(self):
    out=invoke(None,payload());self.assertEqual(out['run_id'],'2026-10-12T235436Z');self.assertEqual(out['receipt_file'],'roi_2026-10-12T235436Z.json')
    for key in ('schema','receipt','generated_utc','sources','scope','broker_read','rows','aggregate','lane_nav_series','market_benchmark','chart','receipt_file','source_dir'):self.assertIn(key,out)
 def test_actual_candidate_route_stale_503_and_redacted_500(self):
    source=(ROOT/'backend/routers/portfolio_intelligence.py').read_text()
    fn=next(n for n in ast.parse(source).body if isinstance(n,ast.AsyncFunctionDef) and n.name=='get_paper_accounts');fn.decorator_list=[]
    class HTTPError(Exception):
        def __init__(self,status_code,detail):self.status_code=status_code;self.detail=detail
    helper=types.ModuleType('backend.services.public_paper_accounts');helper.PublicROIUnavailable=M.PublicROIUnavailable
    scope={'HTTPException':HTTPError,'logger':types.SimpleNamespace(error=lambda *args:None)}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'candidate-route','exec'),scope)
    for exception,expected in ((M.PublicROIUnavailable('PRIMARY_ROI_SOURCE_STALE_OR_FUTURE'),503),(RuntimeError('PRIVATE_SENTINEL'),500)):
        def fail():raise exception
        helper.read_public_paper_accounts=fail
        with patch.dict(sys.modules,{'backend.services.public_paper_accounts':helper}),self.assertRaises(HTTPError) as caught:asyncio.run(scope['get_paper_accounts']())
        self.assertEqual(caught.exception.status_code,expected);self.assertNotIn('PRIVATE_SENTINEL',str(caught.exception.detail))
 def test_missing_empty_duplicate_accounts_refused(self):
    for account in (None,'',True,123):
        p=payload();p['books'][0]['account']=account
        with self.assertRaises(M.PublicROIUnavailable):invoke(None,p)
    p=payload();p['books']*=2
    with self.assertRaises(M.PublicROIUnavailable):invoke(None,p)
 def test_nullable_finite_returns_bool_string_nonfinite_refused(self):
    for field in ('return_pct','spy_same_window_pct','vs_spy_pp'):
        for value in (True,'1',float('nan'),float('inf'),-float('inf')):
            p=payload();p['books'][0][field]=value
            with self.assertRaises(M.PublicROIUnavailable):invoke(None,p)
 def test_invalid_holdings_and_mark_ages_refused_before_coercion(self):
    for field in ('n_holdings','mark_age_days'):
        for value in (-1,True,'2',1.5,2.0):
            p=payload();p['books'][0][field]=value
            with self.assertRaises(M.PublicROIUnavailable):invoke(None,p)
 def test_bad_future_row_dates_refused(self):
    for field in ('inception','last_mark'):
        for value in (True,12,'bad','2026-02-30','2026-10-14'):
            p=payload();p['books'][0][field]=value
            with self.assertRaises(M.PublicROIUnavailable):invoke(None,p)
 def test_invalid_primary_state_not_rewritten(self):
    for status in ('INVALID','MISSING','UNKNOWN',None):
        p=payload();p['receipts'][0]['status']=status
        with self.assertRaises(M.PublicROIUnavailable):invoke(None,p)
 def test_real_reage_local_published_parity_and_no_double_age(self):
    p=payload(1);p['books'][0].update(mark_status='LIVE',mark_age_days=4,last_mark='2026-10-08')
    local=invoke(copy.deepcopy(p),None);published=invoke(None,copy.deepcopy(p));tie=invoke(copy.deepcopy(p),copy.deepcopy(p))
    self.assertEqual(local['rows'],published['rows']);self.assertEqual(local['rows'],tie['rows'])
    self.assertEqual(local['rows'][0]['mark_status'],'STALE');self.assertEqual(local['rows'][0]['mark_age_days'],5)
    self.assertEqual(p['books'][0]['mark_age_days'],4)
 def test_losses_zero_and_missing_kept_with_reason(self):
    for value in (-12.75,0,None):
        p=payload();p['books'][0].update(return_pct=value,n_holdings=0,last_mark=None,mark_age_days=None)
        out=invoke(None,p);self.assertEqual(out['rows'][0]['roi_pct'],value);self.assertEqual(out['rows'][0]['n_positions'],0)
        self.assertIn('last_mark',out['rows'][0]['missing_because'])
 def test_exact_candidate_opportunities_cap_keeps_original_count_and_order(self):
    tree=ast.parse((ROOT/'backend/services/publish_receipts.py').read_bytes())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_opportunities')
    rows=[{'ticker':'T'+str(i),'news':list(range(10))} for i in range(300)]
    original={'receipt_file':'opportunities_fixture.json','generated_utc':NOW.isoformat(),'lists':[{'list_id':'global','rows':rows},{'list_id':'other','rows':rows[:50]}]}
    ops=types.ModuleType('backend.services.opportunities');ops.load_latest=lambda:copy.deepcopy(original);ops.opportunities_dir=lambda:Path('fixture')
    backend=types.ModuleType('backend');services=types.ModuleType('backend.services');backend.services=services;services.opportunities=ops
    scope={'Optional':__import__('typing').Optional,'L':types.SimpleNamespace(PERSONAL_ACCOUNT_PREFIXES=('murat_',),rel=lambda p:str(p),sha256_of=lambda p:'0'*64),'OPP_MAX_ROWS_PER_LIST':100,'OPP_CAPS':{'news':3,'catalysts':5,'why_picked':5},'OPP_RECENT_CAP':3}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'actual-candidate-opportunity-builder','exec'),scope)
    with patch.dict(sys.modules,{'backend':backend,'backend.services':services,'backend.services.opportunities':ops}):out=scope['_opportunities']()
    self.assertEqual(len(out['lists']),2);self.assertEqual(len(out['lists'][0]['rows']),100);self.assertEqual(len(out['lists'][1]['rows']),50)
    self.assertEqual(out['lists'][0]['n_rows_in_receipt'],300);self.assertIn('first 100 rows of 300',out['lists'][0]['rows_trimmed_note'])
    self.assertEqual([r['ticker'] for r in out['lists'][0]['rows']],[r['ticker'] for r in rows[:100]])
    self.assertEqual(len(rows),300);self.assertEqual(len(rows[0]['news']),10)
