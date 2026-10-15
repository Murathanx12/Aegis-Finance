"""Finite population stage called by the existing owned branching child.

No task registration, providers, models, orders or paper_nav writes. Before
any financial input is read, require actual local registry rows and the
independently reviewed actual server readback. Missing prerequisites WAIT.
"""
import collections,datetime,json,sqlite3,uuid
from pathlib import Path
from backend.services.portfolio_intelligence.branch_population import digest,clock,validate_lineage
from backend.services.portfolio_intelligence.branch_population_runtime import consume_batch,verify_actual_registry,committed_identity
from backend.services.portfolio_intelligence.branch_population_inputs import ExistingInputAdapters,SharedGrader,read_operating_review,sha
ROOT=Path('C:/Users/mrthn/aegis-finance')
EVIDENCE=Path('C:/Users/mrthn/aegis-recovery-evidence/oct15-clean-recovery-20261015/branching-population-1000-r1')
LOCAL_DB=ROOT/'backend/data/aegis_pi.db'

def bounded_json(path,cap=1024*1024):
 p=Path(path)
 if p.is_symlink() or p.stat().st_nlink!=1 or p.stat().st_size>cap:raise ValueError('BOUNDED_ACTUAL_POPULATION_DOCUMENT')
 return json.loads(p.read_bytes())

def prerequisites(specs,registration,review_ref,remote_ref,connection):
 registered=verify_actual_registry(specs,registration,connection)
 review=read_operating_review(review_ref,digest(specs))
 if review.get('commit')!=committed_identity() or review.get('remote_readback_ref')!=remote_ref:raise ValueError('REVIEWED_ACTUAL_GLOBAL_REGISTRATION_REQUIRED')
 if sha(remote_ref['path'])!=remote_ref['sha256']:raise ValueError('ACTUAL_REMOTE_REGISTRY_PIN')
 remote=bounded_json(remote_ref['path']);params=sorted(r['param'] for r in registration['rows'])
 if remote.get('schema')!='actual_population_registry_readback/1' or remote.get('site')!='railway_actual' or remote.get('manifest_sha256')!=digest(specs) or remote.get('source_package_sha256')!=registration['source_package_sha256'] or remote.get('population_row_count')!=len(params) or remote.get('population_params_sha256')!=digest(params):raise ValueError('ALL_REMOTE_ATTEMPTS_REQUIRED')
 all_params=remote['all_params']
 if len(all_params)!=len(set(all_params)) or remote.get('all_params_sha256')!=digest(sorted(all_params)) or remote.get('count')!=len(all_params) or remote.get('max_cumulative',0)<len(all_params) or not set(params)<=set(all_params):raise ValueError('GLOBAL_CUMULATIVE_SEARCH_COUNT_REQUIRED')
 # Reconciliation must include every historical natural parameter from both
 # sites. The independent review binds the exact initial union, not a label.
 peer_union=review.get('historical_union_params')
 if not isinstance(peer_union,list) or not peer_union or not set(peer_union)<=set(all_params):raise ValueError('REMOTE_HISTORICAL_UNION_REQUIRED')
 local={r[0] for r in connection.execute('SELECT param FROM rule_experiments')}
 if not set(peer_union)<=local:raise ValueError('LOCAL_HISTORICAL_UNION_REQUIRED')
 return max(registered,clock(remote['registered_at']),clock(remote['observed_at']))

def shared_prices(*,observed_at,lp,pandas):
 from backend.services import market_sessions as MS
 now=clock(observed_at);cal=MS._xnys()
 sessions=cal.sessions_in_range((now.date()-datetime.timedelta(days=14)).isoformat(),now.date().isoformat())
 closed=[s for s in sessions if cal.session_close(s).to_pydatetime()<=now]
 if not closed:raise ValueError('WAIT_SHARED_CLOSED_SESSION')
 session=closed[-1].date();start=session-datetime.timedelta(days=400)
 paths=(ROOT/'backend/data/optimus/prices_2025_26/bars.parquet',ROOT/'backend/data/optimus/llm_portfolio/global_bars.parquet')
 before=[(p.stat().st_size,p.stat().st_mtime_ns) for p in paths];frames=[]
 # Original union/grade/market metadata read only these five columns. Keep
 # the exact400day filter and complete-symbol vendor selection unchanged.
 columns=['symbol','date','open','close','volume']
 for path in paths:
  frames.append(pandas.read_parquet(path,columns=columns,filters=[('date','>=',pandas.Timestamp(start)),('date','<=',pandas.Timestamp(session))]))
  if sum(len(f) for f in frames)>3000000:raise ValueError('BOUNDED_SHARED_PRICE_PANEL')
 bars=lp.union_bars(*frames)
 del frames  # Do not retain both decoded inputs while hashing/snapshotting.
 if bars.empty or bars['date'].max().date()!=session:raise ValueError('WAIT_SHARED_PRICE_REFRESH')
 pins=[{'path':str(p),'sha256':sha(p)} for p in paths]
 if before!=[(p.stat().st_size,p.stat().st_mtime_ns) for p in paths]:raise ValueError('WAIT_SHARED_PRICE_REFRESH')
 return bars,pins,session.isoformat()

def run_owned_population():
 # Source module import stays stdlib-only. Finite config/registry gates precede
 # pandas/cache imports, even while the original247 cohort is WAIT_ENTRY.
 runtime=EVIDENCE/'runtime';config_path=EVIDENCE/'OPERATING_CONFIG.json'
 if not config_path.is_file():return {'action':'WAIT_REGISTRY_AND_SOURCE_REVIEW','target':1000,'new_frozen_books':0}
 config=bounded_json(config_path)
 specs=bounded_json(config['specifications_path'],4*1024*1024);validate_lineage(specs)
 if digest(specs)!=config['manifest_sha256']:raise ValueError('EXACT_FROZEN_POPULATION_MANIFEST')
 registration=bounded_json(config['local_registration_path'])['registration']
 with sqlite3.connect(LOCAL_DB.as_uri()+'?mode=ro',uri=True) as connection:
  connection.row_factory=sqlite3.Row
  after=prerequisites(specs,registration,config['input_review_ref'],config['remote_readback_ref'],connection)
  from backend.services import disk_guard, llm_portfolio as lp, revision_flow as rf
  import pandas as pd
  runtime.mkdir(parents=True,exist_ok=True)
  with disk_guard.file_lock(runtime/'population-operation.lock',timeout_s=0):
   declared_path=runtime/'declaration.json';now=datetime.datetime.now(datetime.timezone.utc);observed=now.isoformat()
   if declared_path.exists():declaration=bounded_json(declared_path)
   else:
    if now<after:raise ValueError('ACTUAL_DECLARATION_AFTER_REGISTRY')
    declaration={'schema':'actual_prospective_population_declaration/1','declared_at':observed,'manifest_sha256':digest(specs),'commit':committed_identity(),'inherited_nav':False}
    # Exclusive first declaration; never replace it with an earlier timestamp.
    with declared_path.open('x',encoding='utf8') as f:json.dump(declaration,f,sort_keys=True)
   if declaration['manifest_sha256']!=digest(specs) or declaration['commit']!=committed_identity() or clock(declaration['declared_at'])<after:raise ValueError('PROSPECTIVE_DECLARATION_REQUIRED')
   bars,price_refs,session=shared_prices(observed_at=observed,lp=lp,pandas=pd)
   generation=runtime/'input-snapshots'/uuid.uuid4().hex
   adapters=ExistingInputAdapters(specs,config['input_review_ref'],generation,observed_at=observed,lp=lp,rf=rf,pandas=pd,bars=bars)
   price_snapshot=generation/'shared-prices.parquet';bars.to_parquet(price_snapshot,index=False)
   if price_snapshot.stat().st_size>128*1024**2:raise ValueError('BOUNDED_SHARED_PRICE_SNAPSHOT')
   # Verify price files again before any ledger append. The fixed frame itself
   # remains held in this one Job; subsequent refreshes cannot alter its values.
   if any(sha(r['path'])!=r['sha256'] for r in price_refs):raise ValueError('WAIT_SHARED_PRICE_REFRESH')
   result=consume_batch(specs,registration,connection,features=adapters.features,declared_at=declaration['declared_at'],observed_at=observed,lp=SharedGrader(lp,bars),bars=bars,admit_family=adapters.callbacks(),private_ledger=runtime/'books.jsonl',writer_lock=disk_guard.file_lock)
   result.update(price_refs=price_refs,shared_price_snapshot={'path':str(price_snapshot),'sha256':sha(price_snapshot)},closed_session=session,source_input_refusals=adapters.refusals,declared_root_count=len(specs['root_policies']),attempted_variants_cumulative=len(specs['attempts']))
   receipt=runtime/('operation_'+now.strftime('%Y%m%dT%H%M%S%fZ')+'.json')
   disk_guard.atomic_write_json(receipt,result)
   statuses=collections.Counter(result['states'].values());actual_marked=sum(g.get('status')=='OK' for g in result['grades'])
   return {'action':'POPULATION_OPERATED','receipt':str(receipt),'new_frozen_books':result['new_frozen_books'],'pending_entry':statuses.get('PENDING',0),'marked':actual_marked,'operating_states':dict(statuses),'attempted_variants_cumulative':len(specs['attempts']),'registry_population_rows':len(registration['rows']),'activation':'NONE'}
