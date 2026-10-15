"""Synthetic mechanics using ACTUAL existing LP/calendar/cost functions."""
import datetime,importlib.util,os,sys,unittest,tempfile
from pathlib import Path
os.environ['AEGIS_IGNORE_DOTENV']='1';sys.dont_write_bytecode=True
REPO=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(REPO))
from backend.services import llm_portfolio as LP,market_sessions as MS,xs_ranker as XR
import pandas as pd
CORE=REPO/'backend/services/prospective_exit_pair/pair_core.py'
spec=importlib.util.spec_from_file_location('pair_core',CORE);C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
class ExistingAccounting(unittest.TestCase):
 def test_actual_xnys_holiday_early_close_and_inclusive_count(self):
  entry=LP.entry_session(datetime.date(2026,11,25));self.assertEqual(entry.date(),datetime.date(2026,11,27))
  cal=MS._xnys();sessions=cal.sessions_window(entry,126);self.assertEqual(len(sessions),126)
  self.assertEqual(cal.session_close(entry).isoformat(),'2026-11-27T18:00:00+00:00')
 def test_actual_lp_net_agrees_before_exit_including_entry_cost(self):
  cal=MS._xnys();entry=LP.entry_session(datetime.date(2026,11,24));sessions=cal.sessions_window(entry,126);prior=cal.sessions_window(cal.previous_session(entry),-70)
  rows=[]
  for t in ('AAA','SPY'):
   for s in prior:rows.append(dict(symbol=t,date=s,open=100.,close=100.,volume=2000000.))
   for s in sessions[:4]:rows.append(dict(symbol=t,date=s,open=100.,close=110. if t=='AAA' else 100.,volume=2000000.))
  bars=pd.DataFrame(rows);g=bars[bars.symbol=='AAA'].sort_values('date').reset_index(drop=True);mdv=LP._entry_mdv(g,len(prior));rate=XR.round_trip_bps(mdv)/20000
  schedule=[dict(date=s.date().isoformat(),open=cal.session_open(s).isoformat(),close=cal.session_close(s).isoformat()) for s in sessions]
  d=dict(schema='prospective_fixed_exit_pair/1',parent_book_id='synthetic',parent_record_sha256='a'*64,contract_sha256='b'*64,weights={'AAA':.95,'CASH':.05},initial_nav=LP.START_CAPITAL,declared_utc='2026-11-24T22:00:00+00:00',registered_utc='2026-11-24T21:00:00+00:00',committed_utc='2026-11-24T20:00:00+00:00',sessions=schedule,entry_costs={'AAA':{'one_way_rate':rate,'known_before_utc':'2026-11-24T22:00:00+00:00'}},fee_budget_rule='COMMON_PROPORTIONAL_COST_BUDGET',fee_budget_scale=1.,exit_sessions=5,control_exit_sessions=126,primary_sessions=21,cash_interest=0,historical_nav_inherited=False,activation='NONE')
  state=C.initial_state(d)
  for i,s in enumerate(schedule[:4]):
   now=s['date']+'T23:00:00+00:00';inp=dict(session=s['date'],observed_utc=now,prices={t:dict(date=s['date'],open=100.,close=110. if t=='AAA' else 100.,available_utc=now) for t in ('AAA','SPY')})
   if i==0:inp['entry_costs']=d['entry_costs']
   actual=C.step(d,state,inp);state=actual['state']
  book=dict(book_id='synthetic',name='synthetic_fixture',kind='personal',benchmark='SPY',asof='2026-11-24',objective='synthetic accounting equivalence',positions=[dict(ticker=t,weight=w) for t,w in d['weights'].items()],n_positions=2,horizon_days=[1,5,21,126])
  expected=LP.grade(book,bars,today=sessions[3])
  self.assertEqual(expected['status'],'OK')
  for m in actual['marks'].values():self.assertAlmostEqual(m['return_fraction'],expected['to_date']['net'],places=12);self.assertAlmostEqual(m['benchmark_return_fraction'],expected['to_date']['benchmark_return'],places=12)
class DeclarationClock(unittest.TestCase):
 def test_current_day_liquidity_is_used_only_after_actual_close(self):
  from unittest.mock import patch
  sys.path.insert(0,str(CORE.parent));import owned_stage as S
  cal=MS._xnys();dates=cal.sessions_window(pd.Timestamp('2026-11-24'),-70)
  bars=pd.DataFrame([dict(symbol='AAA',date=s,open=100.,close=100.,volume=2000000.) for s in dates]);seen=[]
  class L:
   START_CAPITAL=LP.START_CAPITAL;entry_session=staticmethod(LP.entry_session);_grouped=staticmethod(LP._grouped)
   @staticmethod
   def _entry_mdv(g,j):seen.append(g['date'].max().date());return LP._entry_mdv(g,j)
  class DT(datetime.datetime):
   hour=22
   @classmethod
   def now(cls,tz=None):return cls(2026,11,24,cls.hour,tzinfo=datetime.timezone.utc)
  parent={'book_id':'fixture','positions':[dict(ticker='AAA',weight=.95),dict(ticker='CASH',weight=.05)]}
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'synthetic-prior';p.write_text('fixture only');refs=[{'path':str(p),'sha256':S.sha(p)}]
   with patch.object(S.datetime,'datetime',DT):
    for hour in (20,22):
     DT.hour=hour
     d=S.prepare_declaration(parent,registered_utc='2026-11-24T19:00:00+00:00',committed_utc='2026-11-24T18:00:00+00:00',source_commit='f'*40,contract_sha256='b'*64,registry_rows=[],lp=L,ms=MS,pd=pd,prior_bars=bars,prior_input_refs=refs)
     self.assertEqual(d['sessions'][0]['date'],'2026-11-25')
  self.assertEqual(seen,[datetime.date(2026,11,23),datetime.date(2026,11,24)])
if __name__=='__main__':unittest.main()
