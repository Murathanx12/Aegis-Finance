import contextlib,datetime,importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
D=Path(__file__).resolve().parent;sys.path.insert(0,str(D));sys.path.insert(0,str(D.parents[1]/'services/prospective_exit_pair'))
import owned_stage as S
import test_pair_core as T
C=S.C
class StageTests(unittest.TestCase):
 def test_no_config_waits_without_price_loader(self):
  with tempfile.TemporaryDirectory() as td:
   def load(*_):raise AssertionError('financial input read before prerequisites')
   r=S.consume_owned(Path(td)/'absent.json',lp=None,ms=None,pd=None,file_lock=None,load_held_bars=load)
   self.assertEqual(r['reason'],'WAIT_PREREGISTRY_SOURCE_REVIEW_DECLARATION')
 def test_source_gate_fails_before_price_loader(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'config.json';p.write_text('{}')
   with patch.object(S,'prerequisites',side_effect=ValueError('REAL_REVIEW_MISSING')):
    with self.assertRaisesRegex(ValueError,'REAL_REVIEW_MISSING'):S.consume_owned(p,lp=None,ms=None,pd=None,file_lock=None,load_held_bars=lambda *_:self.fail('unexpected input read'))
 def test_strict_document_duplicate_nonfinite_and_size(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'bad.json'
   for value in ('{"a":1,"a":2}','{"a":NaN}'):
    p.write_text(value)
    with self.assertRaises(ValueError):S.read(p)
   p.write_text('12345')
   with self.assertRaisesRegex(ValueError,'BOUNDED'):S.read(p,cap=4)
 def test_completed_session_is_not_written_twice(self):
  # Isolated fixture files only; no actual registry/config/runtime operations.
  import pandas as pd
  d=T.declaration();index=pd.DatetimeIndex([s['date'] for s in d['sessions']]);mapping={s['date']:s for s in d['sessions']}
  class Cal:
   def sessions_window(self,entry,count):self_count=count;self_test=self_count;assert self_test==126;return index
   def session_open(self,s):return pd.Timestamp(mapping[s.date().isoformat()]['open'])
   def session_close(self,s):return pd.Timestamp(mapping[s.date().isoformat()]['close'])
  class MS:
   @staticmethod
   def _xnys():return Cal()
  class LP:
   @staticmethod
   def entry_session(_):return index[0]
  class Now(datetime.datetime):
   @classmethod
   def now(cls,tz=None):return cls(2026,11,25,23,tzinfo=datetime.timezone.utc)
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);runtime=root/'private';cfg=root/'config.json';cfg.write_text(json.dumps({'runtime_directory':str(runtime)}));source=root/'price-source';source.write_text('synthetic fixture')
   frame=pd.DataFrame([{'symbol':t,'date':pd.Timestamp('2026-11-25'),'open':100.,'close':100.,'volume':1000000.} for t in ('AAA','SPY')]);calls=[]
   def loader(*_):calls.append(True);return frame,[{'path':str(source),'sha256':S.sha(source)}]
   with patch.object(S,'RUNTIME',runtime),patch.object(S,'prerequisites',return_value=(d,root)),patch.object(S.datetime,'datetime',Now):
    a=S.consume_owned(cfg,lp=LP,ms=MS,pd=pd,file_lock=lambda *a,**k:contextlib.nullcontext(),load_held_bars=loader)
    b=S.consume_owned(cfg,lp=LP,ms=MS,pd=pd,file_lock=lambda *a,**k:contextlib.nullcontext(),load_held_bars=loader)
   self.assertEqual(a['status'],'MARKED');self.assertEqual(b['status'],'WAIT');self.assertEqual(len(calls),1);self.assertEqual(len((runtime/'pair-ledger.jsonl').read_bytes().splitlines()),1)
if __name__=='__main__':unittest.main()
