"""Synthetic regressions for the declared unique, valid prior63 cost basis."""
import datetime,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ['AEGIS_IGNORE_DOTENV']='1'
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'backend/services/prospective_exit_pair'))
from backend.services import llm_portfolio as LP,market_sessions as MS
import pandas as pd
import owned_stage as S

class FixedClock(datetime.datetime):
 @classmethod
 def now(cls,tz=None):return cls(2026,11,24,22,tzinfo=datetime.timezone.utc)

class LiquidityValidity(unittest.TestCase):
 def bars(self,n=5):
  dates=MS._xnys().sessions_window(pd.Timestamp('2026-11-24'),-n)
  return pd.DataFrame([dict(symbol='AAA',date=s,open=100.,close=100.,volume=2e6) for s in dates])
 def declare(self,bars):
  parent={'book_id':'synthetic-only','positions':[{'ticker':'AAA','weight':.95},{'ticker':'CASH','weight':.05}]}
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'synthetic-history';p.write_text('synthetic fixture only')
   with patch.object(S.datetime,'datetime',FixedClock):
    return S.prepare_declaration(parent,registered_utc='2026-11-24T19:00:00+00:00',committed_utc='2026-11-24T18:00:00+00:00',source_commit='f'*40,contract_sha256='b'*64,registry_rows=[],lp=LP,ms=MS,pd=pd,prior_bars=bars,prior_input_refs=[{'path':str(p),'sha256':S.sha(p)}])
 def test_one_valid_four_nan_cannot_supply_five_observations(self):
  bars=self.bars();bars.loc[1:,'volume']=float('nan')
  with self.assertRaisesRegex(ValueError,'WAIT_VALID_PRIOR_LIQUIDITY_HISTORY'):self.declare(bars)
 def test_five_duplicate_rows_cannot_supply_five_sessions(self):
  bars=self.bars();bars['date']=bars.date.iloc[-1]
  with self.assertRaisesRegex(ValueError,'WAIT_DUPLICATE_PRIOR_LIQUIDITY_SESSION'):self.declare(bars)
 def test_fewer_than_five_valid_unique_closed_sessions_waits(self):
  with self.assertRaisesRegex(ValueError,'WAIT_CLOSED_PRIOR_LIQUIDITY_HISTORY'):self.declare(self.bars(4))
 def test_invalid_window_rows_do_not_reach_lp_nan_skipping_median(self):
  for column,value in [('close',float('nan')),('close',0.),('volume',-1.),('volume',float('inf'))]:
   with self.subTest(column=column,value=value):
    bars=self.bars();bars.loc[2,column]=value
    with patch.object(LP,'_entry_mdv',side_effect=AssertionError('invalid data reached median')):
     with self.assertRaisesRegex(ValueError,'WAIT_VALID_PRIOR_LIQUIDITY_HISTORY'):self.declare(bars)
 def test_finite_inputs_with_overflowing_dollar_volume_wait(self):
  bars=self.bars();bars.loc[2,['close','volume']]=[1e308,1e308]
  with self.assertRaisesRegex(ValueError,'WAIT_VALID_PRIOR_LIQUIDITY_HISTORY'):self.declare(bars)
 def test_exact_five_valid_sessions_preserve_original_cost(self):
  bars=self.bars();d=self.declare(bars)
  self.assertEqual(d['entry_costs']['AAA']['median_dollar_volume'],LP._entry_mdv(bars,len(bars)))
  self.assertEqual(d['entry_costs']['AAA']['one_way_rate'],.0005)
 def test_no_extension_past63_to_replace_invalid_recent_observation(self):
  bars=self.bars(70);bars.loc[len(bars)-1,'volume']=float('nan')
  with self.assertRaisesRegex(ValueError,'WAIT_VALID_PRIOR_LIQUIDITY_HISTORY'):self.declare(bars)
 def test_old_invalid_rows_outside_unchanged63_do_not_affect_cost(self):
  bars=self.bars(70);bars.loc[:6,'volume']=float('nan');d=self.declare(bars)
  self.assertEqual(d['entry_costs']['AAA']['median_dollar_volume'],LP._entry_mdv(bars,len(bars)))
 def test_future_row_does_not_rescue_insufficient_closed_history(self):
  bars=self.bars(4);future=bars.iloc[[-1]].copy();future['date']=pd.Timestamp('2026-11-25')
  with self.assertRaisesRegex(ValueError,'WAIT_CLOSED_PRIOR_LIQUIDITY_HISTORY'):self.declare(pd.concat([bars,future],ignore_index=True))

if __name__=='__main__':unittest.main()
