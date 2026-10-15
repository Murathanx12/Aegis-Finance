"""Synthetic equivalence only: no current prices/registry/strategies read."""
import copy,types
import pandas as pd
import pytest
from backend.services import llm_portfolio as lp, revision_flow as rf
from backend.services.portfolio_intelligence import branch_population_inputs as inputs

def panel():
 return pd.DataFrame([{'symbol':s,'date':pd.Timestamp(d),'open':100.+n,'high':110.+n,'low':90.+n,'close':101.+n,'volume':1e6} for s in ('SPY','AAA','BBB') for n,d in enumerate(pd.bdate_range('2026-06-01','2026-10-14'))])

def test_five_column_union_preserves_exact_vendor_choice_values_and_liquidity():
 us=panel();global_=us[us.symbol=='AAA'].copy();global_['close']+=10
 extra=global_.tail(1).copy();extra['date']=pd.Timestamp('2026-10-15');global_=pd.concat([global_,extra])
 cols=['symbol','date','open','close','volume']
 old=lp.union_bars(us,global_);new=lp.union_bars(us[cols],global_[cols])
 pd.testing.assert_frame_equal(new,old[cols])
 assert lp.liquidity_bands(new,asof='2026-10-15')==lp.liquidity_bands(old,asof='2026-10-15')
 assert inputs.market_metadata(new,lp,observed_at='2026-10-15T13:00:00Z')==inputs.market_metadata(old,lp,observed_at='2026-10-15T13:00:00Z')

def test_revision_projection_keeps_whole_history_unsafe_refusal_before_window(tmp_path):
 raw=pd.DataFrame([{'ticker':'AAA','event_date':'2026-10-14','firm':'one','target_action':'Raises','prior_target':100.,'current_target':110.,'pit_safe':True,'unused':'do not decode'}, {'ticker':'OLD','event_date':'1999-01-01','firm':'historic','target_action':'Raises','prior_target':10.,'current_target':11.,'pit_safe':False,'unused':'do not drop'}])
 path=tmp_path/'revisions.parquet';raw.to_parquet(path,index=False)
 with pytest.raises(ValueError,match='pit_safe=False'):
  inputs.revision_rows(path,{'written_utc':'2026-10-15T12:00:00Z'},{},observed_at='2026-10-15T13:00:00Z',rf=rf,pandas=pd,market={})
 raw['pit_safe']=True;raw.to_parquet(path,index=False)
 cols=['ticker','event_date','firm','target_action','prior_target','current_target','pit_safe']
 pd.testing.assert_frame_equal(rf.compute(pd.read_parquet(path),asof='2026-10-15'),rf.compute(pd.read_parquet(path,columns=cols),asof='2026-10-15'))

def test_lazy_grader_wait_entry_does_not_build_whole_group_cache(monkeypatch):
 bars=panel()[['symbol','date','open','close','volume']]
 book=lp.freeze({'name':'fixture','objective':'fixture','kind':'personal','positions':[{'ticker':'AAA','weight':.5,'thesis':'fixture','falsifier':'fixture'},{'ticker':'CASH','weight':.5,'thesis':'fixture','falsifier':'fixture'}]},today='2026-10-15')
 expected=lp.grade(book,bars,today='2026-10-15')
 monkeypatch.setattr(lp,'_grouped',lambda _:pytest.fail('fullframe grouping before eligible entry'))
 actual=inputs.SharedGrader(lp,bars).grade(book,bars,today='2026-10-15')
 assert actual==expected and actual['status']=='PENDING'

def test_lazy_grader_eligible_full_result_equal_and_group_once(monkeypatch):
 bars=panel()[['symbol','date','open','close','volume']]
 book=lp.freeze({'name':'fixture','objective':'fixture','kind':'personal','positions':[{'ticker':'AAA','weight':.5,'thesis':'fixture','falsifier':'fixture'},{'ticker':'CASH','weight':.5,'thesis':'fixture','falsifier':'fixture'}]},today='2026-10-01')
 expected=lp.grade(book,bars,today='2026-10-14');original=lp._grouped;calls=[]
 def observed(frame):calls.append(frame);return original(frame)
 monkeypatch.setattr(lp,'_grouped',observed);shared=inputs.SharedGrader(lp,bars)
 assert shared.grade(book,bars,today='2026-10-14')==expected
 assert shared.grade(book,bars,today='2026-10-14')==expected
 assert len(calls)==1
