import copy,json,sys,types
from pathlib import Path
import pytest
D=Path(__file__).resolve().parent;sys.path.insert(0,str(D))
from backend.services.portfolio_intelligence import branch_population_inputs as i
from backend.services.portfolio_intelligence import branch_population as p
from backend.services.portfolio_intelligence import branch_population_operating as o

def test_source_review_never_self_admits_legacy_model_context(tmp_path):
 f=tmp_path/'review.json';f.write_text(json.dumps({'independent':True,'verdict':'PASS_POPULATION_OPERATING_SOURCES_ONLY','manifest_sha256':'x','legacy_typed_context_is_verified_fact':True,'approved_inputs':['dated_target_revision_changes','unverified_typed_sentiment_context']}))
 with pytest.raises(ValueError,match='EXACT_EXPERIMENTAL_INPUT_REVIEW'):i.read_operating_review(i.ref(f),'x')

def test_news_actual_available_clock_signed_value_and_duplicate_item_collapse(tmp_path):
 f=tmp_path/'news.jsonl'
 row={'first_seen_utc':'2026-10-15T09:00:00Z','published_utc':'2026-10-15T08:00:00Z','item_id':'fixture','url':'https://example.org/fixture','source_kind':'news','event_type':'earnings','tickers':['AAA'],'sentiment':-.7}
 rec={'cached_utc':'2026-10-15T10:00:00Z','row':row};f.write_text(json.dumps(rec)+'\n'+json.dumps(rec)+'\n')
 rows,refusals=i.news_rows(f,{'path':'review','sha256':'b'*64},observed_at='2026-10-15T12:00:00Z',market={'AAA':{'liquidity_segment':'liquid','volatility':.1}})
 assert len(rows)==1 and rows[0]['score']==-.7 and rows[0]['observed_at']=='2026-10-15T10:00:00+00:00' and not refusals
 # Incompatible classifications of the same source item do not become two
 # confirming inputs or silently last-row-win.
 other=copy.deepcopy(rec);other['row']['event_type']='m_and_a'
 f.write_text(json.dumps(rec)+'\n'+json.dumps(other)+'\n')
 rows,refusals=i.news_rows(f,{},observed_at='2026-10-15T12:00:00Z',market={'AAA':{'liquidity_segment':'liquid','volatility':.1}})
 assert not rows and refusals[0]['code']=='AMBIGUOUS_TYPED_EVENT'

def test_revision_adapter_preserves_actual_prior_receipt_and_original_pit_guard(tmp_path):
 import pandas as pd
 from backend.services import revision_flow as rf
 raw=pd.DataFrame([{'ticker':'AAA','event_date':'2026-10-14','firm':str(n),'target_action':'Raises','prior_target':100.,'current_target':110.,'pit_safe':True} for n in range(3)])
 f=tmp_path/'revision.parquet';f.write_bytes(b'fixture-source-only')
 fake=types.SimpleNamespace(read_parquet=lambda path:raw)
 receipt={'written_utc':'2026-10-14T20:33:38Z'}
 rows=i.revision_rows(f,receipt,{},observed_at='2026-10-15T12:00:00Z',rf=rf,pandas=fake,market={'AAA':{'liquidity_segment':'liquid','volatility':.1}})
 assert rows[0]['n_firms']==3 and rows[0]['net_raises']==3 and rows[0]['observed_at']=='2026-10-14T20:33:38+00:00'
 raw.loc[0,'pit_safe']=False
 with pytest.raises(ValueError,match='pit_safe=False'):i.revision_rows(f,receipt,{},observed_at='2026-10-15T12:00:00Z',rf=rf,pandas=fake,market={})

def test_shared_grader_matches_existing_actual_engine_without_global_mutation():
 import pandas as pd
 from backend.services import llm_portfolio as lp
 bars=pd.DataFrame([{'symbol':sym,'date':pd.Timestamp(day),'open':100.,'high':102.,'low':99.,'close':101.+n,'volume':1000000.} for sym in ('SPY','AAA') for n,day in enumerate(('2026-10-12','2026-10-13','2026-10-14'))])
 book=lp.freeze({'name':'SYNTHETIC','objective':'Fixture','kind':'personal','positions':[{'ticker':'AAA','weight':.5,'thesis':'fixture','falsifier':'fixture'},{'ticker':'CASH','weight':.5,'thesis':'fixture','falsifier':'fixture'}]},today='2026-10-12')
 original=lp._grouped;shared=i.SharedGrader(lp,bars)
 assert shared.grade(book,bars,today='2026-10-14')==lp.grade(book,bars,today='2026-10-14') and lp._grouped is original
 with pytest.raises(ValueError,match='EXACT_SHARED_PRICE_FRAME'):shared.grade(book,bars.copy(),today='2026-10-14')

def test_missing_prereg_review_returns_operating_wait_before_reading_financial_inputs(monkeypatch,tmp_path):
 monkeypatch.setattr(o,'EVIDENCE',tmp_path)
 monkeypatch.setattr(o,'shared_prices',lambda **kw:pytest.fail('financial input read before registry'))
 assert o.run_owned_population()=={'action':'WAIT_REGISTRY_AND_SOURCE_REVIEW','target':1000,'new_frozen_books':0}
