"""Integration functions for the EXISTING trial registry and virtual grader.

Not a scheduler or broker. Root must independently review and wire these into
the existing owned bounded task; importing this module never accrues data.
"""
import datetime,hashlib,json,os,subprocess
from pathlib import Path
from backend.services.portfolio_intelligence.branch_population import clock,digest,qualify_features,targets,validate_lineage
REPO=Path(__file__).resolve().parents[3]
D=Path('C:/Users/mrthn/aegis-recovery-evidence/oct15-clean-recovery-20261015/branching-population-1000-r1')
SOURCE_BINDINGS=REPO/'docs/TRIALS/POPULATION-1000-SOURCES.json'

def source_package_hash():
 binding=json.loads(SOURCE_BINDINGS.read_bytes())
 for relative,expected in binding['files'].items():
  path=REPO/relative
  if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected:raise ValueError('EXACT_COMMITTED_POPULATION_SOURCE_REQUIRED')
 return digest(binding)
def committed_identity():
 source_package_hash()
 if (REPO/'.git').exists():
  result=subprocess.run(['git','rev-parse','HEAD'],cwd=REPO,capture_output=True,text=True,check=True,timeout=5)
  files=list(json.loads(SOURCE_BINDINGS.read_bytes())['files'])+['docs/TRIALS/POPULATION-1000-SOURCES.json','scripts/local_branching_task.py']
  dirty=subprocess.run(['git','status','--porcelain','--',*files],cwd=REPO,capture_output=True,text=True,check=True,timeout=5)
  if dirty.stdout:raise ValueError('FROZEN_POPULATION_SOURCE_DIRTY')
  return result.stdout.strip()
 value=os.environ.get('RAILWAY_GIT_COMMIT_SHA','')
 if len(value)!=40 or any(c not in '0123456789abcdef' for c in value.lower()):raise ValueError('ACTUAL_PLATFORM_DEPLOYMENT_COMMIT_REQUIRED')
 return value.lower()

def register_before_data(specs,*,db_path,ensure_trial_registered):
 """Explicit reviewed operation only; use existing idempotent DB function.

Caller chooses the authoritative actual DB. A fixture/local DB must not be
reported as remote registry integration. No observations are read here.
"""
 validate_lineage(specs);commit=committed_identity();package=source_package_hash();manifest=digest(specs);rows=[];registered_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
 for root in specs.get('root_policies',[]):
  param='population1000:root:'+root['policy_id'];notes={'kind':'declared_root_policy','manifest_sha256':manifest,'commit':commit,'source_package_sha256':package,'license':'PRODUCT_EXPERIMENT','activation':'NONE','root_policy':root,'registered_at_utc':registered_at}
  rows.append({'param':param,'id':ensure_trial_registered(param,notes,db_path=db_path,config_version='descriptive')})
 for family in sorted({s['family'] for s in specs['specifications']}):
  param='population1000:family:'+manifest[:16]+':'+family
  notes={'kind':'family_declaration','manifest_sha256':manifest,'commit':commit,'source_package_sha256':package,'license':'PRODUCT_EXPERIMENT','activation':'NONE','inferential_claim':'BLOCKED_UNPOWERED','family':family,'registered_at_utc':registered_at}
  rows.append({'param':param,'id':ensure_trial_registered(param,notes,db_path=db_path,config_version='descriptive')})
 for attempt in specs['attempts']:
  param='population1000:variant:'+manifest[:16]+':'+str(attempt['attempt_id'])
  notes={'kind':'attempted_variant','manifest_sha256':manifest,'commit':commit,'source_package_sha256':package,'license':'PRODUCT_EXPERIMENT','activation':'NONE','variant':attempt,'family_count_is_not_search_count':True,'registered_at_utc':registered_at}
  rows.append({'param':param,'id':ensure_trial_registered(param,notes,db_path=db_path,config_version='descriptive')})
 return {'schema':'existing_registry_population_insertion/1','manifest_sha256':manifest,'commit':commit,'source_package_sha256':package,'db_path':str(db_path),'rows':rows,'remote_registry_verified':False,'activation':'NONE'}
def verify_actual_registry(specs,registration,connection):
 """Actual readback; an edited JSON file or owner-labelled PASS is insufficient."""
 validate_lineage(specs);manifest=digest(specs)
 if registration['manifest_sha256']!=manifest or registration['commit']!=committed_identity() or registration['source_package_sha256']!=source_package_hash():raise ValueError('ACTUAL_COMMIT_MANIFEST_REGISTRY_REQUIRED')
 expected_content={}
 for root in specs.get('root_policies',[]):expected_content['population1000:root:'+root['policy_id']]={'kind':'declared_root_policy','root_policy':root}
 for family in {s['family'] for s in specs['specifications']}:expected_content['population1000:family:'+manifest[:16]+':'+family]={'kind':'family_declaration','family':family}
 for attempt in specs['attempts']:expected_content['population1000:variant:'+manifest[:16]+':'+str(attempt['attempt_id'])]={'kind':'attempted_variant','variant':attempt}
 expected=len(expected_content)
 if len(registration['rows'])!=expected or {r['param'] for r in registration['rows']}!=set(expected_content):raise ValueError('ALL_ATTEMPTS_MUST_BE_COUNTED')
 times=[]
 for ref in registration['rows']:
  row=connection.execute('SELECT id,param,created_at,notes FROM rule_experiments WHERE id=?',(ref['id'],)).fetchone()
  if row is None or row['param']!=ref['param']:raise ValueError('ACTUAL_REGISTRY_ROW_REQUIRED')
  notes=json.loads(row['notes'])
  if notes.get('manifest_sha256')!=manifest or notes.get('commit')!=registration['commit'] or notes.get('source_package_sha256')!=registration['source_package_sha256'] or notes.get('activation')!='NONE':raise ValueError('ACTUAL_REGISTRY_CONTENT_REQUIRED')
  if any(notes.get(k)!=v for k,v in expected_content[ref['param']].items()):raise ValueError('EXACT_REGISTERED_ROOT_FAMILY_VARIANT_REQUIRED')
  times.append(clock(notes['registered_at_utc']))
 return max(times)
def verify_refs(row):
 """Source and independent admission documents must be actual bounded files.

This does not replace family-specific semantic validation by the reviewed
adapter; the consumer below requires that adapter, never admits labels itself.
"""
 for key in ('source_ref','independent_admission_ref'):
  ref=row[key]
  if not isinstance(ref,dict) or set(ref)!={'path','sha256'}:raise ValueError('ACTUAL_FEATURE_SOURCE_REF_REQUIRED')
  p=Path(ref['path'])
  if not p.is_file() or p.is_symlink() or p.stat().st_nlink!=1 or p.stat().st_size>64*1024**2:raise ValueError('ACTUAL_FEATURE_SOURCE_HASH_REQUIRED')
  h=hashlib.sha256()
  with p.open('rb') as f:
   for part in iter(lambda:f.read(65536),b''):h.update(part)
  if h.hexdigest()!=ref['sha256']:raise ValueError('ACTUAL_FEATURE_SOURCE_HASH_REQUIRED')
 if row['source_sha256']!=row['source_ref']['sha256']:raise ValueError('FEATURE_SOURCE_PIN_JOIN_REQUIRED')
def consume_batch(specs,registration,connection,*,features,declared_at,observed_at,lp,bars,admit_family,private_ledger,writer_lock):
 """Bounded shared-input batch, reusable with original LP.freeze/grade.

admit_family is the existing separately reviewed source adapter; no generic
admission PASS is created. Missing adapters/inputs yield operating WAIT_INPUT.
"""
 registered_at=verify_actual_registry(specs,registration,connection)
 now=clock(observed_at);declared=clock(declared_at)
 if now<declared or declared<registered_at:raise ValueError('PROSPECTIVE_CLOCK_AFTER_REGISTRATION_REQUIRED')
 destination=Path(private_ledger).resolve();runtime=(D/'runtime').resolve()
 if runtime not in destination.parents or destination.name!='books.jsonl':raise ValueError('NEW_PRIVATE_LEDGER_ONLY')
 if len(specs['specifications'])>1000 or len(features)>10000:raise ValueError('BOUNDED_SHARED_POPULATION_INPUT')
 states={};new=[];grades=[];manifest=digest(specs);verified_sources={}
 family_rows={}
 for row in features:family_rows.setdefault(row['family'],[]).append(row)
 with writer_lock(destination.with_suffix('.lock'),timeout_s=0):
  if destination.exists():
   raw=destination.read_bytes()
   if len(raw)>16*1024**2 or raw and not raw.endswith(b'\n'):raise ValueError('PRIVATE_LEDGER_TORN_OR_OVERSIZE')
   strict=[json.loads(line) for line in raw.splitlines()]
   ids=[r['book_id'] for r in strict]
   if len(ids)!=len(set(ids)):raise ValueError('PRIVATE_LEDGER_DUPLICATE_IDS')
  existing=lp.read_books(destination) if destination.exists() else []
  if destination.exists() and len(existing)!=len(strict):raise ValueError('SHARED_READER_DROPPED_PRIVATE_RECORDS')
  by_policy={b.get('source',{}).get('policy_id'):b for b in existing if isinstance(b.get('source'),dict)}
  if len(by_policy)!=len(existing) or None in by_policy:raise ValueError('PRIVATE_POPULATION_SOURCE_ID_REQUIRED')
  specifications={s['policy_id']:s for s in specs['specifications']}
  if set(by_policy)-set(specifications):raise ValueError('UNDECLARED_PRIVATE_POLICY_RECORD')
  def prepare(spec):
   if spec['family'] not in admit_family and spec['family']!='no_news_control':return 'WAIT_INPUT_ADAPTER',None
   rows=[r for family in spec['input_families'] for r in family_rows.get(family,[])]
   q=qualify_features(spec,rows,declared_at=declared_at,observed_at=observed_at)
   if not q['status'].startswith('INPUT_ROWS_PRESENT'):return q['status'],None
   for row in q['rows']:
    key=digest([row['source_ref'],row['independent_admission_ref']])
    if key not in verified_sources:verify_refs(row);verified_sources[key]=row
   if spec['family']!='no_news_control' and admit_family[spec['family']](spec,q['rows'],observed_at) is not True:return 'REFUSED_INPUT_ADMISSION',None
   weights=targets(spec,q['rows'],asof=observed_at)
   return ('READY',weights) if weights is not None else ('WAIT_NO_ELIGIBLE_NAMES',None)
  def freeze_spec(spec,weights):
   pid=spec['policy_id']
   book={'name':'population1000_'+pid,'objective':'Descriptive net virtual outcome versus SPY and declared matched control; no adoption','kind':'personal','state':'READY','model':'existing_deterministic_shared_engine','strategy':spec['mechanism'],'benchmark':'SPY','horizon_days':[spec['horizon_sessions']],'source':{'type':'prospective_population1000','policy_id':pid,'multiple_parent_policy_ids':spec['parent_policy_ids'],'matched_no_news_policy_id':spec.get('matched_no_news_policy_id'),'declared_at':declared_at,'manifest_sha256':manifest,'registry_commit':registration['commit'],'historical_nav_inherited':False,'input_quality':'UNVERIFIED_TYPED_MODEL_CONTEXT_EXPERIMENT' if 'news' in spec['input_families'] else 'DATED_REVISION_CHANGE_EXPERIMENT','actual_gross':sum(w for t,w in weights.items() if t!='CASH')},'positions':[{'ticker':t,'weight':w,'thesis':'Frozen descriptive policy '+pid,'falsifier':'Input qualification or original frozen mechanism fails'} for t,w in weights.items()]}
   return lp.freeze(book,today=now.date())
  for spec in specs['specifications']:
   pid=spec['policy_id']
   if pid in by_policy:continue
   if spec['control_role']=='no_news':states[pid]='WAIT_MATCHED_TREATMENT';continue
   status,weights=prepare(spec)
   if status!='READY':states[pid]=status;continue
   pair=[];twin_id=spec.get('matched_no_news_policy_id')
   if twin_id:
    if twin_id not in specifications:states[pid]='WAIT_MATCHED_CONTROL';continue
    if twin_id in by_policy:
     if by_policy[twin_id]['asof']!=now.date().isoformat():states[pid]='WAIT_MATCHED_CONTROL_VINTAGE';continue
    else:
     twin_status,twin_weights=prepare(specifications[twin_id])
     if twin_status!='READY':states[pid]='WAIT_MATCHED_CONTROL_INPUT';continue
     pair.append(freeze_spec(specifications[twin_id],twin_weights))
   pair.append(freeze_spec(spec,weights))
   for record in pair:new.append(record);by_policy[record['source']['policy_id']]=record
  if new:
   for row in verified_sources.values():verify_refs(row)
   destination.parent.mkdir(parents=True,exist_ok=True)
   with destination.open('a',encoding='utf8',newline='\n') as f:
    for row in new:f.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n')
    f.flush();os.fsync(f.fileno())
  for pid,book in by_policy.items():
   grade=lp.grade(book,bars,today=now.date());grades.append(grade)
   # Preserve the grader's true statuses; no absent/failed mark becomes zero.
   states[pid]=str(grade.get('status','UNCLASSIFIED_GRADE_REFUSED'))
 return {'schema':'shared_virtual_population_consumer/1','observed_at':observed_at,'new_frozen_books':len(new),'ledger':str(destination),'states':states,'grades':grades,'activation':'NONE','broker_mutations':0,'registry_remote_verification':'SEPARATE_REQUIRED','target_operating_policies':1000}
