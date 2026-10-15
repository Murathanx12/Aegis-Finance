"""Finite stage for an EXISTING reviewed owned launcher; never self-schedules.

No default activation/config. Actual canonical commitment, two-site registry,
independent source review and a fresh declaration are mandatory first. Root
must separately bind this stage into an existing native custody/Job/STOP guard.
"""
import datetime,hashlib,json,os,sqlite3,subprocess,sys,types
from pathlib import Path
# Existing native launcher must hold/pin both files before bootstrap. Compile
# the held core's source directly: -B alone does not prevent reading a .pyc.
_core_path=Path(__file__).resolve().with_name('pair_core.py')
C=types.ModuleType('pair_core')
exec(compile(_core_path.read_bytes(),str(_core_path),'exec'),C.__dict__)

E=Path('C:/Users/mrthn/aegis-recovery-evidence/oct15-clean-recovery-20261015')
RUNTIME=E/'branching-dynamic-pair-r1/runtime'
LOCAL_DB=Path('C:/Users/mrthn/aegis-finance/backend/data/aegis_pi.db')
PROPOSAL=E/'branching-outcome-review-r1/ROOT_ACTUAL_CYCLE/prospective-child-proposal.json'
PROPOSAL_SHA='11d26b0fedfa935b67af06c04d7bb436faa0bf3c7936723223dbee2aaa95769c'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for chunk in iter(lambda:f.read(65536),b''):h.update(chunk)
 return h.hexdigest()
def parse_json(raw):
 def unique(pairs):
  d={}
  for k,v in pairs:
   if k in d:raise ValueError('DUPLICATE_JSON_FIELD')
   d[k]=v
  return d
 return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('NONFINITE_JSON')))
def read(p,cap=4*1024*1024):
 p=Path(p)
 if p.is_symlink() or p.stat().st_nlink!=1 or p.stat().st_size>cap:raise ValueError('BOUNDED_SINGLE_LINK_DOCUMENT_REQUIRED')
 return parse_json(p.read_bytes())
def pinned(ref):
 if set(ref)!={'path','sha256'} or sha(ref['path'])!=ref['sha256']:raise ValueError('EXACT_PRIVATE_EVIDENCE_REF_REQUIRED')
 return read(ref['path'])
def prerequisites(config):
 d=pinned(config['declaration_ref']);C.validate_declaration(d)
 review=pinned(config['independent_source_review_ref']);remote=pinned(config['remote_registry_export_ref']);manifest=pinned(config['source_manifest_ref'])
 contract=pinned(config['policy_contract_ref'])
 doc=Path(config['prereg_doc_ref']['path']);lint=pinned(config['corpse_lint_ref'])
 if sha(doc)!=config['prereg_doc_ref']['sha256'] or review.get('prereg_doc_ref')!=config['prereg_doc_ref'] or review.get('corpse_lint_ref')!=config['corpse_lint_ref']:raise ValueError('EXACT_PREDECLARED_TRIAL_AND_LINT_REQUIRED')
 lint_doc=Path(lint['file'])
 if lint_doc.stat().st_size>65536 or hashlib.sha256(lint_doc.read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=hashlib.sha256(doc.read_bytes().replace(b'\r\n',b'\n')).hexdigest():raise ValueError('LINT_MUST_BIND_THIS_PREDECLARATION')
 if lint.get('blocking') or lint.get('duplicates') or lint.get('resurrections') or lint.get('verdict') not in ('PASS','UNPOWERED_AT_REGISTRATION'):raise ValueError('UNRESOLVED_CORPSE_OR_REGISTRATION_REFUSAL')
 if lint['verdict']=='UNPOWERED_AT_REGISTRATION' and review.get('operating_license')!='DESCRIPTIVE_UNPOWERED_PAPER_EXPERIMENT_ONLY':raise ValueError('NO_INFERENTIAL_PASS_FROM_UNPOWERED_LINT')
 if sha(PROPOSAL)!=PROPOSAL_SHA or contract['actual_proposal_ref']!={'path':str(PROPOSAL),'sha256':PROPOSAL_SHA} or C.digest(contract)!=d['contract_sha256']:raise ValueError('EXACT_ACTUAL_PROPOSAL_CONTRACT_REQUIRED')
 for key in ('parent_book_id','parent_record_sha256','weights','exit_sessions','control_exit_sessions','primary_sessions','cash_interest','fee_budget_rule'):
  if d.get(key)!=contract.get(key):raise ValueError('EXACT_REGISTERED_POLICY_DEFINITION_REQUIRED')
 if review.get('independent') is not True or review.get('verdict')!='PASS_DYNAMIC_PAIR_EXPERIMENTAL_ACCOUNTING_ONLY' or review.get('contract_sha256')!=d['contract_sha256'] or review.get('source_manifest_sha256')!=config['source_manifest_ref']['sha256'] or review.get('remote_registry_export_ref')!=config['remote_registry_export_ref']:raise ValueError('ACTUAL_INDEPENDENT_PAIR_SOURCE_REVIEW_REQUIRED')
 if review.get('declaration_ref')!=config['declaration_ref'] or not C.clock(d['declared_utc'])<=C.clock(review['reviewed_utc'])<C.clock(d['sessions'][0]['open']) or C.clock(review['reviewed_utc'])>datetime.datetime.now(datetime.timezone.utc):raise ValueError('ACTUAL_DECLARATION_REVIEW_BEFORE_ENTRY_REQUIRED')
 repo=Path(config['canonical_repo_root']).resolve()
 if not (repo/'.git').exists():raise ValueError('ACTUAL_CANONICAL_COMMIT_REQUIRED')
 head=subprocess.run(['git','rev-parse','HEAD'],cwd=repo,capture_output=True,text=True,timeout=5,check=True).stdout.strip()
 committed=subprocess.run(['git','show','-s','--format=%cI',head],cwd=repo,capture_output=True,text=True,timeout=5,check=True).stdout.strip()
 if head!=d['source_commit'] or C.clock(committed)!=C.clock(d['committed_utc']):raise ValueError('EXACT_ACTUAL_COMMIT_CLOCK_REQUIRED')
 canonical=manifest.get('canonical_files',{})
 if len(canonical)<3 or not any(p.startswith('docs/TRIALS/') and p.endswith('.md') for p in canonical):raise ValueError('CANONICAL_PREREG_AND_CODE_REQUIRED')
 for rel,expected_sha in canonical.items():
  p=(repo/rel).resolve()
  if repo not in p.parents or hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected_sha:raise ValueError('EXACT_CANONICAL_COMMITTED_FILE_REQUIRED')
 subprocess.run(['git','ls-files','--error-unmatch','--',*canonical],cwd=repo,capture_output=True,timeout=5,check=True)
 if subprocess.run(['git','status','--porcelain','--',*canonical],cwd=repo,capture_output=True,text=True,timeout=5,check=True).stdout:raise ValueError('CANONICAL_PAIR_SOURCE_DIRTY')
 for r in manifest['source_refs']:
  if sha(r['path'])!=r['sha256']:raise ValueError('EXACT_COMMITTED_PAIR_SOURCE_REQUIRED')
 if remote.get('schema')!='actual_registry_peer_export/1' or remote.get('site')!='railway_actual':raise ValueError('ACTUAL_REMOTE_REGISTRY_EXPORT_REQUIRED')
 if remote.get('count')!=len(remote['rows']) or remote.get('rows_sha256')!=C.digest(remote['rows']) or len({r['param'] for r in remote['rows']})!=len(remote['rows']):raise ValueError('FULL_ACTUAL_REMOTE_REGISTRY_EXPORT_REQUIRED')
 if C.clock(remote['observed_at'])>C.clock(d['registered_utc']):raise ValueError('DECLARATION_AFTER_ACTUAL_REGISTRY_READBACK_REQUIRED')
 expected={row['param']:row for row in d['registry_rows']}
 if len(expected)!=2 or {row['arm'] for row in expected.values()}!={'exit5','fixed_hold'}:raise ValueError('BOTH_PAIR_ATTEMPTS_REQUIRED')
 if any(param!='dynamic-exit5:'+d['contract_sha256']+':'+row['arm'] for param,row in expected.items()):raise ValueError('EXACT_NATURAL_PAIR_TRIAL_IDENTITIES_REQUIRED')
 with sqlite3.connect(LOCAL_DB.as_uri()+'?mode=ro',uri=True) as conn:
  conn.row_factory=sqlite3.Row
  local=[dict(r) for p in expected for r in conn.execute('SELECT * FROM rule_experiments WHERE param=?',(p,))]
 for rows in (local,remote['rows']):
  selected=[r for r in rows if r['param'] in expected]
  if len(selected)!=2 or len({r['param'] for r in selected})!=2:raise ValueError('EXACT_BOTH_REGISTRY_ROWS_REQUIRED')
  for r in selected:
   n=json.loads(r['notes']);want=expected[r['param']]
   if any(n.get(k)!=v for k,v in {'kind':'prospective_dynamic_pair','contract_sha256':d['contract_sha256'],'source_commit':head,'source_manifest_sha256':config['source_manifest_ref']['sha256'],'arm':want['arm'],'parent_book_id':d['parent_book_id'],'historical_nav_inherited':False,'activation':'NONE'}.items()):raise ValueError('EXACT_REGISTERED_PAIR_CONTENT_REQUIRED')
   if C.clock(n['registered_at_utc'])>C.clock(d['registered_utc']):raise ValueError('DECLARATION_AFTER_EVERY_REGISTRATION_REQUIRED')
 # Full source custody/owner identity/resource/STOP is supplied by the existing
 # reviewed native launcher. No self-labelled JSON value can establish it here.
 return d,repo

def prepare_declaration(parent,*,registered_utc,committed_utc,source_commit,contract_sha256,registry_rows,lp,ms,pd,prior_bars,prior_input_refs):
 """Root-only after prereg/registry/review. Returns data; writes nothing.

Freeze entry liquidity at this actual declaration from known CLOSED history;
never infer pre-open local availability from a file first captured after entry.
"""
 now=datetime.datetime.now(datetime.timezone.utc);entry=lp.entry_session(now.date());cal=ms._xnys()
 if not prior_input_refs:raise ValueError('ACTUAL_DECLARATION_HISTORY_SOURCE_REQUIRED')
 for r in prior_input_refs:
  if sha(r['path'])!=r['sha256']:raise ValueError('ACTUAL_DECLARATION_HISTORY_CHANGED')
 sessions=cal.sessions_window(entry,126)
 if len(sessions)!=126:raise ValueError('EXACT_FUTURE_XNYS_SCHEDULE_REQUIRED')
 schedule=[{'date':s.date().isoformat(),'open':cal.session_open(s).isoformat(),'close':cal.session_close(s).isoformat()} for s in sessions]
 weights={p['ticker']:p['weight'] for p in parent['positions']}
 if len(weights)!=len(parent['positions']):raise ValueError('EXACT_UNIQUE_PARENT_POSITIONS_REQUIRED')
 grouped=lp._grouped(prior_bars);costs={}
 from backend.services import xs_ranker as XR
 for t in set(weights)-{'CASH'}:
  g=grouped.get(t)
  if g is None:raise ValueError('WAIT_PRIOR_LIQUIDITY_HISTORY')
  g=g[["date","open","close","volume"]].copy()
  closed=[x for x in g['date'] if cal.is_session(x) and cal.session_close(x).to_pydatetime()<=now]
  g=g[g['date'].isin(closed)].sort_values('date').reset_index(drop=True)
  if g['date'].map(lambda x:pd.Timestamp(x).date()).duplicated().any():raise ValueError('WAIT_DUPLICATE_PRIOR_LIQUIDITY_SESSION')
  if len(g)<5:raise ValueError('WAIT_CLOSED_PRIOR_LIQUIDITY_HISTORY')
  # Validate exactly the existing LP cost window before its NaN-skipping
  # median. Never fill, collapse duplicates, or extend beyond63 observations.
  try:
   for row in g.iloc[-63:].itertuples():
    close=C.number(float(row.close));volume=C.number(float(row.volume))
    if close<=0 or volume<=0 or C.number(close*volume)<=0:raise ValueError('INVALID_LIQUIDITY_OBSERVATION')
  except (ValueError,TypeError,OverflowError):raise ValueError('WAIT_VALID_PRIOR_LIQUIDITY_HISTORY') from None
  mdv=lp._entry_mdv(g,len(g))
  if mdv is None or not 0<C.number(mdv):raise ValueError('WAIT_PRIOR_LIQUIDITY_HISTORY')
  costs[t]={'one_way_rate':XR.round_trip_bps(mdv)/20000,'median_dollar_volume':mdv,'basis':'LP_PRIOR63_CLOSED_SESSIONS_AT_ACTUAL_DECLARATION_FROZEN_FOR_BOTH_SIDES'}
 for r in prior_input_refs:
  if sha(r['path'])!=r['sha256']:raise ValueError('ACTUAL_DECLARATION_HISTORY_CHANGED')
 completed=datetime.datetime.now(datetime.timezone.utc)
 if completed.date()!=now.date():raise ValueError('DECLARATION_CROSSED_UTC_DATE_REQUIRES_NEW_PREPARATION')
 declared_utc=completed.isoformat()
 for c in costs.values():c['known_before_utc']=declared_utc
 d={'schema':'prospective_fixed_exit_pair/1','parent_book_id':parent['book_id'],'parent_record_sha256':C.digest(parent),'weights':weights,'initial_nav':lp.START_CAPITAL,'declared_utc':declared_utc,'registered_utc':registered_utc,'committed_utc':committed_utc,'source_commit':source_commit,'contract_sha256':contract_sha256,'registry_rows':registry_rows,'sessions':schedule,'entry_costs':costs,'exit_sessions':5,'control_exit_sessions':126,'primary_sessions':21,'cash_interest':0,'historical_nav_inherited':False,'activation':'NONE'}
 d['declaration_history_refs']=prior_input_refs;d['history_read_started_utc']=now.isoformat()
 d['fee_budget_rule']='COMMON_PROPORTIONAL_COST_BUDGET';d['fee_budget_scale']=C.fee_scale(weights,costs)
 C.validate_declaration(d);return d

def consume_owned(config_path,*,lp,ms,pd,file_lock,load_held_bars):
 """One next-session atomic ledger append, under existing outer native guard.

Caller supplies the held shared frame/actual input refs and existing disk_guard
lock. No providers/models/strategy construction or main/population mutations.
"""
 if not Path(config_path).is_file():return {'status':'WAIT','reason':'WAIT_PREREGISTRY_SOURCE_REVIEW_DECLARATION','activation':'NONE'}
 config=read(config_path);d,repo=prerequisites(config)
 if Path(config['runtime_directory']).resolve()!=RUNTIME.resolve():raise ValueError('NEW_PRIVATE_PAIR_LEDGER_ONLY')
 # Independently recheck XNYS rather than trusting edited declaration dates.
 cal=ms._xnys();entry=lp.entry_session(C.clock(d['declared_utc']).date());schedule=cal.sessions_window(entry,126)
 actual=[{'date':s.date().isoformat(),'open':cal.session_open(s).isoformat(),'close':cal.session_close(s).isoformat()} for s in schedule]
 if actual!=d['sessions']:raise ValueError('EXACT_ACTUAL_XNYS_CALENDAR_REQUIRED')
 RUNTIME.mkdir(parents=True,exist_ok=True)
 with file_lock(RUNTIME/'pair-ledger.lock',timeout_s=0):
  path=RUNTIME/'pair-ledger.jsonl';records=[]
  if path.exists():
   if path.is_symlink() or path.stat().st_nlink!=1 or path.stat().st_size>4*1024*1024:raise ValueError('STRICT_PRIVATE_PAIR_LEDGER_REQUIRED')
   raw=path.read_bytes()
   if raw and not raw.endswith(b'\n'):raise ValueError('STRICT_PRIVATE_PAIR_LEDGER_REQUIRED')
   records=[parse_json(line) for line in raw.splitlines()]
  state,previous=C.replay(d,records);i=state['next_index'];now=datetime.datetime.now(datetime.timezone.utc)
  if i==126:return {'status':'COMPLETE','sessions':126,'activation':'NONE'}
  s=d['sessions'][i]
  if now<C.clock(s['close'])+datetime.timedelta(minutes=90):return {'status':'WAIT','reason':'WAIT_CLOSED_SESSION_PLUS90MIN','activation':'NONE'}
  bars,price_input_refs=load_held_bars(d,s)
  if not price_input_refs or len(bars)>20000:raise ValueError('BOUNDED_HELD_SHARED_PRICE_INPUT_REQUIRED')
  for r in price_input_refs:
   if sha(r['path'])!=r['sha256']:raise ValueError('HELD_SHARED_PRICE_INPUT_CHANGED')
  names=(set(d['weights'])-{'CASH'})|{'SPY'};prices={}
  if records:
   old_entry=records[0]['result']['inputs']['prices']
   for t in names:
    original=bars[(bars['symbol']==t)&(pd.to_datetime(bars['date']).dt.date==datetime.date.fromisoformat(d['sessions'][0]['date']))]
    if len(original)!=1:return {'status':'WAIT','reason':'WAIT_EXACT_ORIGINAL_ENTRY_BASIS','activation':'NONE'}
    if float(original.iloc[0]['open'])!=old_entry[t]['open']:raise ValueError('REFUSED_PRICE_ENTRY_BASIS_REVISION')
    if t!='SPY':
     g=bars[bars['symbol']==t].sort_values('date').reset_index(drop=True);days=pd.to_datetime(g['date']);j=int(days.searchsorted(pd.Timestamp(d['sessions'][0]['date'])));k=int(days.searchsorted(pd.Timestamp(s['date']),side='right'))-1
     if lp._suspect_splits(t,g,j,k):raise ValueError('REFUSED_CORPORATE_ACTION_REVIEW_REQUIRED')
  for t in names:
   rows=bars[(bars['symbol']==t)&(pd.to_datetime(bars['date']).dt.date==datetime.date.fromisoformat(s['date']))]
   if len(rows)!=1:return {'status':'WAIT','reason':'MISSING_OR_DUPLICATE_EXACT_SESSION_MARK','activation':'NONE'}
   row=rows.iloc[0];prices[t]={'date':s['date'],'open':float(row['open']),'close':float(row['close']),'available_utc':now.isoformat()}
  inputs={'session':s['date'],'observed_utc':now.isoformat(),'prices':prices,'price_input_refs':price_input_refs}
  if i==0:inputs['entry_costs']=d['entry_costs']
  result=C.step(d,state,inputs)
  if result['status']!='MARKED':return result
  for r in price_input_refs:
   if sha(r['path'])!=r['sha256']:raise ValueError('HELD_SHARED_PRICE_INPUT_CHANGED')
  r=C.record(result,previous);raw=(json.dumps(r,sort_keys=True,allow_nan=False)+'\n').encode()
  with path.open('ab') as f:f.write(raw);f.flush();os.fsync(f.fileno())
  return {'status':'MARKED','session':s['date'],'session_number':i+1,'ledger_record_sha256':r['record_sha256'],'marks':result['marks'],'modelled_trade_events':len(result['events']),'real_fills':0,'activation':'NONE'}

def load_existing_shared_prices(d,s,*,lp,pd):
 """Exact existing two-panel union projected to this pair, no network."""
 root=Path('C:/Users/mrthn/aegis-finance/backend/data/optimus')
 paths=(root/'prices_2025_26/bars.parquet',root/'llm_portfolio/global_bars.parquet')
 names=sorted((set(d['weights'])-{'CASH'})|{'SPY'});start=datetime.date.fromisoformat(d['sessions'][0]['date'])-datetime.timedelta(days=400)
 pins=[{'path':str(p),'sha256':sha(p)} for p in paths];frames=[]
 for p in paths:
  frame=pd.read_parquet(p,columns=['symbol','date','open','close','volume'],filters=[('symbol','in',names),('date','>=',pd.Timestamp(start)),('date','<=',pd.Timestamp(s['date']))])
  frames.append(frame)
  if sum(len(f) for f in frames)>20000:raise ValueError('BOUNDED_PAIR_PRICE_PANEL_REQUIRED')
 bars=lp.union_bars(*frames);del frames
 if any(sha(r['path'])!=r['sha256'] for r in pins):raise ValueError('SHARED_PRICE_INPUT_CHANGED_DURING_READ')
 return bars,pins

def run_owned(config_path):
 """Root invokes only through independently approved existing native carrier."""
 if not Path(config_path).is_file():return {'status':'WAIT','reason':'WAIT_PREREGISTRY_SOURCE_REVIEW_DECLARATION','activation':'NONE'}
 if os.environ.get('AEGIS_IGNORE_DOTENV')!='1' or 'backend' in sys.modules:raise ValueError('FRESH_SANITIZED_CANONICAL_CHILD_REQUIRED')
 config=read(config_path);d,repo=prerequisites(config)  # before cache imports/read
 sys.path.insert(0,str(repo))
 from backend.services import llm_portfolio as lp,market_sessions as ms,disk_guard
 import pandas as pd
 return consume_owned(config_path,lp=lp,ms=ms,pd=pd,file_lock=disk_guard.file_lock,load_held_bars=lambda d,s:load_existing_shared_prices(d,s,lp=lp,pd=pd))

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);args=parser.parse_args()
 print(json.dumps(run_owned(args.config),sort_keys=True,allow_nan=False))
