import contextlib,copy,datetime,json,sqlite3,sys
from pathlib import Path
import pytest
D=Path(__file__).resolve().parent;sys.path.insert(0,str(D))
from backend.services.portfolio_intelligence import branch_population as p
from backend.services.portfolio_intelligence import branch_population_runtime as c

def test_thousand_specs_keep_all_attempts_controls_and_unsupported_counts():
 v=p.compile_population();assert len(v['specifications'])==1000
 assert len({s['semantic_sha256'] for s in v['specifications']})==1000
 assert v['counts']['attempted_variants']==1415 and v['counts']['semantic_duplicates']==415
 assert v['counts']['research_specs_only']==4 and v['counts']['seeded']==0
 assert v==p.compile_population()
 ids={s['policy_id'] for s in v['specifications']}
 roots=p.validate_lineage(v);assert len(roots)==12
 for s in v['specifications']:
  if s['family'] in ('news_only','hybrid_news_revision'):assert s['matched_no_news_policy_id'] in ids
  if s['family']=='hybrid_news_revision':assert len(s['parent_policy_ids'])==2 and set(s['input_families'])=={'news','revision'}

def test_cash_control_clock_display_changes_do_not_inflate_economic_identity():
 v=p.compile_population();s=next(s for s in v['specifications'] if s['family']=='no_news_control');changed=dict(s,max_age_days=99,max_names=100,construction='other')
 assert p.digest(p.semantic(s))==p.digest(p.semantic(changed))

def row(family='news',ticker='AAA'):
 return dict(ticker=ticker,family=family,observed_at='2026-10-15T12:01:00Z',event_at='2026-10-15T12:00:00Z',source_ref={'path':'source','sha256':'a'*64},source_sha256='a'*64,independent_admission_ref={'path':'review','sha256':'b'*64},score=1.0 if family=='news' else None,n_firms=3 if family=='revision' else None,net_raises=2 if family=='revision' else None,event_type='earnings',liquidity_segment='liquid',volatility=.2)
def spec(family='news_only'):
 return dict(family=family,state='SOURCE_ADAPTER_REVIEW_REQUIRED',event_type='earnings',max_age_days=3,input_families=['news'] if family=='news_only' else ['news','revision'],liquidity_segment='liquid',construction='equal',join_rule='none' if family=='news_only' else 'intersection',mechanism='supported_event_delta',max_names=10)
@pytest.mark.parametrize('case',['future_observed','future_event','stale','missing_review'])
def test_time_invalid_or_unadmitted_rows_never_qualify(case):
 r=row()
 if case=='future_observed':r['observed_at']='2026-10-16T12:00:00Z'
 elif case=='future_event':r['event_at']='2026-10-16T12:00:00Z'
 elif case=='stale':r['event_at']='2026-10-01T12:00:00Z'
 else:r['independent_admission_ref']=None
 assert p.qualify_features(spec(),[r],declared_at='2026-10-15T11:00:00Z',observed_at='2026-10-15T12:02:00Z')['status']=='WAIT_INPUT'

def test_join_requires_complementary_inputs_and_changes_actual_targets():
 s=spec('hybrid_news_revision');rows=[row('news','AAA'),row('revision','BBB')]
 assert p.targets(s,rows) is None
 s['join_rule']='complementary_union';assert set(p.targets(s,rows))=={'AAA','BBB','CASH'}
 s['join_rule']='intersection';rows[1]['ticker']='AAA';assert set(p.targets(s,rows))=={'AAA','CASH'}

def test_ambiguous_issuer_feature_never_last_row_wins():
 with pytest.raises(ValueError,match='AMBIGUOUS'):p.targets(spec(),[row(),row()])

def database(monkeypatch):
 db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;db.execute('CREATE TABLE rule_experiments(id INTEGER PRIMARY KEY,param TEXT,created_at TEXT,notes TEXT)');monkeypatch.setattr(c,'committed_identity',lambda:'fixture-commit');monkeypatch.setattr(c,'source_package_hash',lambda:'fixture-package')
 def ensure(param,notes,**kw):
  existing=db.execute('SELECT id FROM rule_experiments WHERE param=?',(param,)).fetchone()
  if existing:return existing['id']
  cur=db.execute('INSERT INTO rule_experiments(param,created_at,notes)VALUES(?,?,?)',(param,datetime.datetime.now(datetime.timezone.utc).isoformat(),json.dumps(notes)));return cur.lastrowid
 return db,ensure
def test_actual_registry_counts_all_1415_attempts_not_one_family(monkeypatch):
 db,ensure=database(monkeypatch);v=p.compile_population();r=c.register_before_data(v,db_path='FIXTURE_NOT_REMOTE',ensure_trial_registered=ensure)
 assert len(r['rows'])==1436 and db.execute('SELECT COUNT(*) FROM rule_experiments').fetchone()[0]==1436
 assert c.verify_actual_registry(v,r,db)
 r['rows'].pop()
 with pytest.raises(ValueError,match='ALL_ATTEMPTS'):c.verify_actual_registry(v,r,db)

def test_missing_actual_database_row_refuses_even_with_json_receipt(monkeypatch):
 db,ensure=database(monkeypatch);v=p.compile_population(5);r=c.register_before_data(v,db_path='FIXTURE',ensure_trial_registered=ensure);db.execute('DELETE FROM rule_experiments WHERE id=?',(r['rows'][0]['id'],))
 with pytest.raises(ValueError,match='ACTUAL_REGISTRY_ROW'):c.verify_actual_registry(v,r,db)

def test_shared_existing_freeze_grade_accepts_new_prospective_synthetic_book_pending():
 # Synthetic plumbing fixture only; no cache/provider/ledger or past P&L read.
 sys.path.insert(0,'C:/Users/mrthn/aegis-finance')
 from backend.services import llm_portfolio as lp
 import pandas as pd
 book={'name':'SYNTHETIC_FIXTURE_ONLY','objective':'Fixture, not financial evidence','kind':'personal','state':'READY','positions':[{'ticker':'CASH','weight':1.0,'thesis':'fixture','falsifier':'fixture'}]}
 frozen=lp.freeze(book,today='2026-10-15')
 bars=pd.DataFrame([{'symbol':'SPY','date':pd.Timestamp('2026-10-14'),'open':100.,'close':100.,'volume':1000}])
 assert lp.grade(frozen,bars,today='2026-10-15')['status']=='PENDING'

def fixture_population():
 v=p.compile_population();t=next(s for s in v['specifications'] if s['family']=='news_only' and s['event_type']=='earnings' and s['construction']=='equal' and s['liquidity_segment']=='liquid');control=next(s for s in v['specifications'] if s['policy_id']==t['matched_no_news_policy_id'])
 return {'schema':v['schema'],'root_policies':v['root_policies'],'specifications':[t,control],'attempts':[{'attempt_id':1,'policy_id':t['policy_id']},{'attempt_id':2,'policy_id':control['policy_id']}]}
class LP:
 @staticmethod
 def read_books(path):return [json.loads(x) for x in Path(path).read_text().splitlines()]
 @staticmethod
 def freeze(book,*,today):return dict(book,asof=today.isoformat(),book_id=p.digest([book['name'],book['positions'],today.isoformat()]))
 @staticmethod
 def grade(book,bars,*,today):return {'book_id':book['book_id'],'status':'PENDING'}
def prepared(monkeypatch,tmp_path):
 monkeypatch.setattr(c,'D',tmp_path);db,ensure=database(monkeypatch);v=fixture_population();reg=c.register_before_data(v,db_path='FIXTURE',ensure_trial_registered=ensure)
 base=datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(seconds=1);decl=base.isoformat();known=(base+datetime.timedelta(seconds=1)).isoformat();observed=(base+datetime.timedelta(seconds=2)).isoformat()
 source=tmp_path/'source.json';source.write_text('{}');review=tmp_path/'review.json';review.write_text('{}');ref=lambda f:{'path':str(f),'sha256':p.hashlib.sha256(f.read_bytes()).hexdigest()}
 r=row();r.update(observed_at=known,event_at=known,source_ref=ref(source),source_sha256=ref(source)['sha256'],independent_admission_ref=ref(review))
 return db,v,reg,decl,observed,r,tmp_path/'runtime/books.jsonl'
def test_consumes_atomic_same_vintage_pair_with_real_file_refs_in_private_fixture(monkeypatch,tmp_path):
 db,v,reg,decl,observed,r,path=prepared(monkeypatch,tmp_path)
 out=c.consume_batch(v,reg,db,features=[r],declared_at=decl,observed_at=observed,lp=LP,bars=None,admit_family={'news_only':lambda *a:True},private_ledger=path,writer_lock=lambda *a,**kw:contextlib.nullcontext())
 assert out['new_frozen_books']==2 and set(out['states'].values())=={'PENDING'}
 books=LP.read_books(path);assert len({b['asof'] for b in books})==1 and all(b['source']['historical_nav_inherited'] is False for b in books)
 prefix=path.read_bytes();again=c.consume_batch(v,reg,db,features=[r],declared_at=decl,observed_at=observed,lp=LP,bars=None,admit_family={'news_only':lambda *a:True},private_ledger=path,writer_lock=lambda *a,**kw:contextlib.nullcontext())
 assert again['new_frozen_books']==0 and path.read_bytes()==prefix
def test_missing_source_adapter_yields_wait_without_seeding_orphan_control(monkeypatch,tmp_path):
 db,v,reg,decl,observed,r,path=prepared(monkeypatch,tmp_path)
 out=c.consume_batch(v,reg,db,features=[r],declared_at=decl,observed_at=observed,lp=LP,bars=None,admit_family={},private_ledger=path,writer_lock=lambda *a,**kw:contextlib.nullcontext())
 assert out['new_frozen_books']==0 and not path.exists() and set(out['states'].values())=={'WAIT_INPUT_ADAPTER','WAIT_MATCHED_TREATMENT'}
def test_corrupt_source_ref_refuses_without_ledger_write(monkeypatch,tmp_path):
 db,v,reg,decl,observed,r,path=prepared(monkeypatch,tmp_path);r['source_ref']['sha256']='0'*64
 with pytest.raises(ValueError,match='ACTUAL_FEATURE_SOURCE_HASH'):c.consume_batch(v,reg,db,features=[r],declared_at=decl,observed_at=observed,lp=LP,bars=None,admit_family={'news_only':lambda *a:True},private_ledger=path,writer_lock=lambda *a,**kw:contextlib.nullcontext())
 assert not path.exists()
def test_data_declaration_before_real_registry_timestamp_refuses(monkeypatch,tmp_path):
 db,v,reg,decl,observed,r,path=prepared(monkeypatch,tmp_path)
 with pytest.raises(ValueError,match='AFTER_REGISTRATION'):c.consume_batch(v,reg,db,features=[r],declared_at='2020-01-01T00:00:00Z',observed_at=observed,lp=LP,bars=None,admit_family={},private_ledger=path,writer_lock=lambda *a,**kw:contextlib.nullcontext())

def test_existing_dated_inputs_can_precede_declaration_without_retimestamping():
 r=row();r.update(observed_at='2026-10-15T10:00:00Z',event_at='2026-10-15T09:00:00Z')
 q=p.qualify_features(spec(),[r],declared_at='2026-10-15T11:00:00Z',observed_at='2026-10-15T12:00:00Z')
 assert q['rows']==[r] and r['observed_at']=='2026-10-15T10:00:00Z'

def test_negative_news_rejects_positive_intersection_but_declared_union_accepts():
 s=spec('hybrid_news_revision');n=row();n['score']=-.8;r=row('revision')
 assert p.targets(s,[n,r]) is None
 s['join_rule']='complementary_union';assert set(p.targets(s,[n,r]))=={'AAA','CASH'}

def test_ten_names_cap_means_half_cash_not_ninety_five_percent_gross():
 s=spec();s.update(gross_target=.95,name_cap=.05)
 out=p.targets(s,[row(ticker='X'+str(i)) for i in range(10)])
 assert sum(v for k,v in out.items() if k!='CASH')==pytest.approx(.5) and out['CASH']==pytest.approx(.5)

def test_immutable_roots_and_no_dangling_hybrid_ancestry():
 v=p.compile_population();hybrid=next(s for s in v['specifications'] if s['family']=='hybrid_news_revision')
 assert {p.validate_lineage(v)[x]['family'] for x in hybrid['parent_policy_ids']}=={'news_only','revision_flow'}
 broken=copy.deepcopy(v);broken['specifications'][0]['parent_policy_ids']=['policy:madeup']
 with pytest.raises(ValueError,match='DECLARED_PARENT'):p.validate_lineage(broken)
 broken=copy.deepcopy(v);broken['root_policies'][0]['mechanism']='changed'
 with pytest.raises(ValueError,match='IMMUTABLE_ROOT'):p.validate_lineage(broken)

def test_same_count_registration_with_substituted_variant_still_refuses(monkeypatch):
 db,ensure=database(monkeypatch);v=p.compile_population(5);reg=c.register_before_data(v,db_path='FIXTURE',ensure_trial_registered=ensure)
 reg['rows'][-1]['param']='population1000:variant:invented'
 with pytest.raises(ValueError,match='ALL_ATTEMPTS'):c.verify_actual_registry(v,reg,db)

def test_registered_parent_content_must_equal_actual_immutable_root(monkeypatch):
 db,ensure=database(monkeypatch);v=p.compile_population(5);reg=c.register_before_data(v,db_path='FIXTURE',ensure_trial_registered=ensure)
 ident=reg['rows'][0]['id'];notes=json.loads(db.execute('SELECT notes FROM rule_experiments WHERE id=?',(ident,)).fetchone()[0]);notes['root_policy']['mechanism']='forged'
 db.execute('UPDATE rule_experiments SET notes=? WHERE id=?',(json.dumps(notes),ident))
 with pytest.raises(ValueError,match='EXACT_REGISTERED_ROOT'):c.verify_actual_registry(v,reg,db)

def test_source_package_allows_only_cross_platform_line_endings(monkeypatch,tmp_path):
 source=tmp_path/'code.py';source.write_bytes(b'x = 1\n')
 binding={'files':{'code.py':p.hashlib.sha256(source.read_bytes()).hexdigest()}}
 file=tmp_path/'POPULATION_SOURCES.json';file.write_text(json.dumps(binding))
 monkeypatch.setattr(c,'D',tmp_path)
 if hasattr(c,'REPO'):monkeypatch.setattr(c,'REPO',tmp_path);monkeypatch.setattr(c,'SOURCE_BINDINGS',file)
 expected=c.source_package_hash();source.write_bytes(b'x = 1\r\n');assert c.source_package_hash()==expected
 source.write_bytes(b'x = 2\r\n')
 with pytest.raises(ValueError,match='EXACT_COMMITTED_POPULATION_SOURCE'):c.source_package_hash()
