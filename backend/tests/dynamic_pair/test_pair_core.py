import copy,datetime,importlib.util,unittest
from pathlib import Path
CORE=Path(__file__).resolve().parents[2]/'services/prospective_exit_pair/pair_core.py'
spec=importlib.util.spec_from_file_location('pair_core',CORE);C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
def declaration(rate=.001):
 # Synthetic injected calendar for mechanics only. Actual adapter separately
 # reconstructs and compares all126 XNYS sessions, including holidays/early close.
 first=[datetime.date.fromisoformat(s) for s in ['2026-11-25','2026-11-27','2026-11-30','2026-12-01','2026-12-02']]
 dates=first+[first[-1]+datetime.timedelta(days=i) for i in range(1,122)]
 schedule=[{'date':d.isoformat(),'open':d.isoformat()+'T14:30:00+00:00','close':d.isoformat()+('T18:00:00+00:00' if i==1 else 'T21:00:00+00:00')} for i,d in enumerate(dates)]
 return {'schema':'prospective_fixed_exit_pair/1','parent_book_id':'original','parent_record_sha256':'a'*64,'contract_sha256':'b'*64,'initial_nav':1000.0,'weights':{'AAA':.95,'CASH':.05},'declared_utc':'2026-11-24T22:00:00+00:00','registered_utc':'2026-11-24T21:00:00+00:00','committed_utc':'2026-11-24T20:00:00+00:00','sessions':schedule,'entry_costs':{'AAA':{'one_way_rate':rate,'known_before_utc':'2026-11-24T22:00:00+00:00'}},'exit_sessions':5,'control_exit_sessions':126,'primary_sessions':21,'cash_interest':0,'fee_budget_rule':'COMMON_PROPORTIONAL_COST_BUDGET','fee_budget_scale':1.0,'historical_nav_inherited':False,'activation':'NONE'}
def inputs(d,i,close=100.0):
 s=d['sessions'][i];observed=s['date']+'T23:00:00+00:00'
 return {'session':s['date'],'observed_utc':observed,'prices':{t:{'date':s['date'],'open':100.0,'close':close if t=='AAA' else 100.0,'available_utc':observed} for t in ('AAA','SPY')},**({'entry_costs':d['entry_costs']} if i==0 else {})}
def through(d,n,close=100.):
 st=C.initial_state(d);records=[];prev=None
 for i in range(n):
  r=C.step(d,st,inputs(d,i,close));rec=C.record(r,prev);records.append(rec);prev=rec['record_sha256'];st=r['state']
 return st,records
class Mechanics(unittest.TestCase):
 def test_entry_is_explicit_same_units_cost_and_cash_for_both(self):
  d=declaration();r=C.step(d,C.initial_state(d),inputs(d,0))
  self.assertEqual(len(r['events']),2)
  for a in r['state']['arms'].values():self.assertAlmostEqual(a['shares']['AAA'],9.5);self.assertAlmostEqual(a['cash'],49.05);self.assertAlmostEqual(a['last_nav'],999.05)
 def test_full_stock_target_gets_common_proportional_fee_reserve(self):
  d=declaration();d['weights']={'AAA':1.0,'CASH':0.0};d['fee_budget_scale']=C.fee_scale(d['weights'],d['entry_costs']);r=C.step(d,C.initial_state(d),inputs(d,0))
  self.assertAlmostEqual(d['fee_budget_scale'],1/1.001)
  a,b=r['state']['arms'].values();self.assertEqual(a,b);self.assertGreaterEqual(a['cash'],0);self.assertAlmostEqual(a['shares']['AAA'],10/1.001)
  m=r['marks']['exit5'];self.assertEqual(m['target_initial_stock_gross'],1.0);self.assertLess(m['actual_initial_stock_gross'],1)
 def test_fifth_real_session_exit_cost_uses_sale_notional(self):
  d=declaration();s,recs=through(d,5,110)
  a=s['arms']['exit5'];self.assertFalse(a['shares']);self.assertAlmostEqual(a['cash'],1093.005)
  sell=[e for e in recs[-1]['result']['events'] if e['side']=='SELL'];self.assertEqual(len(sell),1);self.assertAlmostEqual(sell[0]['traded_usd'],1045);self.assertAlmostEqual(sell[0]['cost_usd'],1.045)
  self.assertEqual(recs[-1]['result']['session'],'2026-12-02')
 def test_cash_has_no_post_exit_price_exposure_or_interest(self):
  d=declaration();s,_=through(d,5,110);before=s['arms']['exit5']['cash'];r=C.step(d,s,inputs(d,5,150))
  self.assertEqual(r['marks']['exit5']['nav_usd'],before);self.assertEqual(r['marks']['exit5']['equity_exposure_usd'],0);self.assertGreater(r['marks']['fixed_hold']['nav_usd'],before)
 def test_control_sells_only_on126_and_both_cost_sides_exist(self):
  d=declaration();s,records=through(d,126)
  self.assertEqual(sum(e['side']=='SELL' and e['role']=='fixed_hold' for r in records for e in r['result']['events']),1)
  self.assertEqual(records[-1]['result']['session_number'],126)
  for a in s['arms'].values():self.assertFalse(a['shares']);self.assertAlmostEqual(a['cost_usd'],1.9)
 def test_zero_cost_replays_hold_gross_before_exit(self):
  d=declaration(0);_,recs=through(d,4,120)
  for r in recs:
   for m in r['result']['marks'].values():self.assertAlmostEqual(m['nav_usd'],.05*1000+.95*1000*1.2)
 def test_missing_price_waits_with_no_events_or_state_mutation(self):
  d=declaration();st=C.initial_state(d);pin=C.digest(st);i=inputs(d,0);i['prices'].pop('AAA');r=C.step(d,st,i)
  self.assertEqual(r['status'],'WAIT');self.assertNotIn('marks',r);self.assertEqual(pin,C.digest(st))
 def test_missing_exit_close_cannot_silently_keep_old_nav(self):
  d=declaration();st,_=through(d,4);i=inputs(d,4);i['prices']['AAA']['close']=None;r=C.step(d,st,i)
  self.assertEqual(r['status'],'WAIT');self.assertTrue(st['arms']['exit5']['shares'])
 def test_future_and_premature_price_availability_refuse(self):
  d=declaration();st=C.initial_state(d)
  for stamp in ('2026-11-26T23:00:00+00:00','2026-11-25T20:00:00+00:00'):
   i=inputs(d,0);i['prices']['AAA']['available_utc']=stamp;self.assertEqual(C.step(d,st,i)['status'],'WAIT')
 def test_no_skipped_session(self):
  d=declaration();st=C.initial_state(d)
  with self.assertRaisesRegex(ValueError,'NO_SKIPPED'):C.step(d,st,inputs(d,1))
 def test_cost_override_cannot_avoid_declared_rate(self):
  d=declaration();i=inputs(d,0);i['entry_costs']=copy.deepcopy(i['entry_costs']);i['entry_costs']['AAA']['one_way_rate']=0
  with self.assertRaisesRegex(ValueError,'EXACT_DECLARED_COSTS'):C.step(d,C.initial_state(d),i)
 def test_after_open_liquidity_is_not_pit_cost(self):
  d=declaration();d['entry_costs']['AAA']['known_before_utc']=d['sessions'][0]['close']
  self.assertEqual(C.step(d,C.initial_state(d),inputs(d,0))['status'],'WAIT')
 def test_no_historical_inception_or_profit_carry(self):
  d=declaration();d['declared_utc']='2026-11-25T13:00:00+00:00'
  with self.assertRaisesRegex(ValueError,'FUTURE_ENTRY'):C.initial_state(d)
  d=declaration();d['historical_nav_inherited']=True
  with self.assertRaisesRegex(ValueError,'INHERITED'):C.initial_state(d)
 def test_replay_rejects_semantic_corruption_even_after_rehash(self):
  d=declaration();_,rs=through(d,1);rs[0]['result']['marks']['exit5']['nav_usd']+=1;body={k:v for k,v in rs[0].items() if k!='record_sha256'};rs[0]['record_sha256']=C.digest(body)
  with self.assertRaisesRegex(ValueError,'REPLAY_REFUSED'):C.replay(d,rs)
 def test_replay_preserves_exact_trade_positions_and_no_duplicate_exit(self):
  d=declaration();st,rs=through(d,6,110);replayed,_=C.replay(d,rs);self.assertEqual(st,replayed)
  self.assertEqual(sum(e['side']=='SELL' for r in rs for e in r['result']['events']),1)
 def test_primary_is21_not_peeking_h5_decision(self):
  d=declaration();_,rs=through(d,21);self.assertFalse(rs[4]['result']['primary_window_complete']);self.assertTrue(rs[20]['result']['primary_window_complete'])
if __name__=='__main__':unittest.main()
