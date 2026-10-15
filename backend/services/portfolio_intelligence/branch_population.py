"""Bounded prospective policy compiler; no provider, LLM, broker or old-ledger writer.

Specifications are not active books. Every attempted variant is retained even
when duplicate, unsupported or refused. Runtime adapters must supply qualified
time-valid features; raw headlines or retrospective target levels never qualify.
"""
from __future__ import annotations
import hashlib,itertools,json,math,random
from collections import Counter
from datetime import datetime,timezone

SEED=20261015
EVENTS=('earnings','guidance','analyst_action','m_and_a','product','regulation_legal','supply_chain','capital_markets')
FAMILIES=('news_only','revision_flow','net_raises','hybrid_news_revision','recommendation','recovery_quality','supply_chain','insider_public')
SUPPORTED=frozenset(FAMILIES[:4])
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def validate_lineage(specs):
 roots={}
 for root in specs.get('root_policies',[]):
  body={k:v for k,v in root.items() if k not in ('policy_id','content_sha256')};key=digest(body)
  if root['policy_id']!='root:'+key[:24] or root['content_sha256']!=key or root['policy_id'] in roots or root['historical_nav_inherited'] is not False:raise ValueError('IMMUTABLE_ROOT_POLICY_REQUIRED')
  roots[root['policy_id']]=root
 for spec in specs['specifications']:
  parents=spec['parent_policy_ids']
  if not parents or len(parents)!=len(set(parents)) or any(p not in roots for p in parents):raise ValueError('DECLARED_PARENT_POLICY_REQUIRED')
  if spec['family']=='hybrid_news_revision' and {roots[p]['family'] for p in parents}!={'news_only','revision_flow'}:raise ValueError('ACTUAL_COMPLEMENTARY_PARENTS_REQUIRED')
 return roots
def clock(v):
 t=datetime.fromisoformat(v.replace('Z','+00:00'))
 if t.tzinfo is None:raise ValueError('AWARE_INPUT_CLOCK_REQUIRED')
 return t.astimezone(timezone.utc)
def semantic(spec):
 # Names, ancestry, evidence handles and same-vintage display IDs cannot create
 # a new policy. Actual mechanism/input/clock/construction differences can.
 if spec['family']=='no_news_control':return {k:spec[k] for k in ('family','mechanism','horizon_sessions','control_role')}
 return {k:spec[k] for k in ('family','mechanism','event_type','horizon_sessions','max_age_days','liquidity_segment','construction','max_names','join_rule','input_families','control_role','gross_target','name_cap')}
def compile_population(target=1000):
 if type(target) is not int or not 1<=target<=1000:raise ValueError('BOUNDED_POPULATION_TARGET')
 rng=random.Random(SEED);attempts=[];canonical={};unique=[];family_attempts=Counter()
 # Stratify across distinct mechanisms first. The fixed candidate permutation
 # samples niches instead of expanding every cheap cross-product to fit a count.
 candidates=[]
 mechanisms={'news_only':('typed_sentiment_context_experiment',),'revision_flow':('net_times_breadth','action_firm_normalized','freshness_weighted'),'net_raises':('positive_net_raises',),'hybrid_news_revision':('revision_plus_typed_context_experiment',),'recommendation':('fresh_upgrades','falling_sell_share','recommendation_acceleration'),'recovery_quality':('cash_stability_after_drawdown',),'supply_chain':('dated_customer_exposure',),'insider_public':('qualified_public_purchase',)}
 roots=[];root_ids={}
 for family,values in mechanisms.items():
  for mechanism in values:
   root={'schema':'immutable_declared_root_policy/1','version':1,'family':family,'mechanism':mechanism,'baseline_params':{'horizon_sessions':126,'max_age_days':3,'liquidity_segment':'liquid','construction':'equal','max_names':20,'gross_target':.95,'name_cap':.05},'source_contract':'docs/TRIALS/TRIAL-POPULATION-1000-20261015.md','state':'DECLARED_ROOT_UNSEEDED','historical_nav_inherited':False,'activation':'NONE'}
   rid='root:'+digest(root)[:24];root_ids[(family,mechanism)]=rid;roots.append(dict(root,policy_id=rid,content_sha256=digest(root)))
 for family in FAMILIES:
  if family not in SUPPORTED:
   candidates.append((family,iter([(mechanisms[family][0],None,126,5,'liquid','equal',20,'none')])));continue
  events=EVENTS if family in ('news_only','hybrid_news_revision') else (None,)
  joins=('intersection','complementary_union') if family=='hybrid_news_revision' else ('none',)
  rows=list(itertools.product(mechanisms[family],events,(21,63,126),(1,3,5),('liquid','broad'),('equal','volatility_aware'),(10,20,40),joins));rng.shuffle(rows)
  candidates.append((family,iter(rows)))
 active=list(candidates)
 while active and len(unique)<target:
  following=[]
  for family,rows in active:
   try:mechanism,event,horizon,age,liquidity,construction,names,join=next(rows)
   except StopIteration:continue
   following.append((family,rows))
   inputs=['news','revision'] if family=='hybrid_news_revision' else ['news'] if family=='news_only' else ['revision'] if family in ('revision_flow','net_raises') else [family]
   spec=dict(family=family,mechanism=mechanism,event_type=event,horizon_sessions=horizon,max_age_days=age,liquidity_segment=liquidity,construction=construction,max_names=names,join_rule=join,input_families=inputs,control_role='treatment',gross_target=.95,name_cap=.05)
   parent_ids=[root_ids[('news_only','typed_sentiment_context_experiment')],root_ids[('revision_flow','net_times_breadth')]] if family=='hybrid_news_revision' else [root_ids[(family,mechanism)]]
   spec.update(parent_policy_ids=parent_ids,delta={'mechanism':mechanism,'clock_max_age_days':age,'construction':construction,'join_rule':join},license='PRODUCT_EXPERIMENT',activation='NONE',record_start='ACTUAL_DECLARATION_THEN_NEXT_ELIGIBLE_SESSION',state='SOURCE_ADAPTER_REVIEW_REQUIRED' if family in SUPPORTED else 'RESEARCH_SPEC_ONLY')
   variants=[spec]
   if family in ('news_only','hybrid_news_revision'):
    # One economic no-news twin is reused where removing news makes several
    # event-specific variants identical. These duplicate attempts stay visible.
    twin=dict(spec);twin.update(family='revision_flow' if family=='hybrid_news_revision' else 'no_news_control',mechanism='net_times_breadth' if family=='hybrid_news_revision' else 'declared_cash_baseline',event_type=None,input_families=['revision'] if family=='hybrid_news_revision' else [],join_rule='none',control_role='no_news',parent_policy_ids=parent_ids,delta={'remove_input':'news'},state='SOURCE_ADAPTER_REVIEW_REQUIRED');variants.append(twin)
   ids=[]
   for row in variants:
    key=digest(semantic(row));policy_id=key[:24];duplicate=key in canonical
    attempt_id=len(attempts)+1;family_attempts[family]+=1
    attempts.append(dict(attempt_id=attempt_id,attempt_family=family,policy_id=policy_id,semantic_sha256=key,status='SEMANTIC_DUPLICATE' if duplicate else 'UNIQUE_SPEC',canonical_attempt=canonical.get(key,attempt_id)))
    ids.append(policy_id)
    if not duplicate:
     canonical[key]=attempt_id;unique.append(dict(row,policy_id=policy_id,semantic_sha256=key))
    if len(unique)>=target:break
   if len(ids)==2:
    for row in unique[-2:]:
     if row['policy_id']==ids[0]:row['matched_no_news_policy_id']=ids[1]
   if len(unique)>=target:break
  active=following
 # A treatment at the final budget edge may lack a twin. It stays unqualified.
 for row in unique:
  if row['family'] in ('news_only','hybrid_news_revision') and 'matched_no_news_policy_id' not in row:row['state']='WAIT_MATCHED_CONTROL'
 return dict(schema='prospective_population_specs/1',seed=SEED,target_operating_policies=target,root_policies=roots,specifications=unique,attempts=attempts,counts=dict(attempted_variants=len(attempts),semantic_duplicates=len(attempts)-len(unique),unique_specs=len(unique),declared_unseeded_roots=len(roots),by_family=dict(Counter(s['family'] for s in unique)),by_control_role=dict(Counter(s['control_role'] for s in unique)),by_attempt_family=dict(family_attempts),research_specs_only=sum(s['state']=='RESEARCH_SPEC_ONLY' for s in unique),data_qualified=0,pending_entry=0,seeded=0,marked=0,outcome_bearing=0),activation='NONE')

def collapse_news(rows):
 groups={};out=[]
 for row in rows:
  if row['family']!='news':out.append(row);continue
  groups.setdefault((row['ticker'],row['event_type']),[]).append(row)
 for key,items in sorted(groups.items()):
  by_id={}
  for row in items:
   item=row['source_item_id']
   if not isinstance(item,str) or not item:raise ValueError('ACTUAL_NEWS_ITEM_ID_REQUIRED')
   if item in by_id and digest(by_id[item])!=digest(row):raise ValueError('AMBIGUOUS_NEWS_SOURCE_ITEM')
   by_id[item]=row
  components=[by_id[item] for item in sorted(by_id)]
  if len({digest([r['source_ref'],r['independent_admission_ref'],r['volatility'],r['liquidity_segment']]) for r in components})!=1:raise ValueError('ONE_REVIEWED_NEWS_SNAPSHOT_REQUIRED')
  aggregate=dict(components[0]);aggregate.update(source_item_id=None,score=sum(r['score'] for r in components)/len(components),event_at=min(components,key=lambda r:clock(r['event_at']))['event_at'],observed_at=max(components,key=lambda r:clock(r['observed_at']))['observed_at'],_component_rows=components)
  out.append(aggregate)
 return out

def qualify_features(spec,rows,*,declared_at,observed_at):
 if spec['state'] in ('RESEARCH_SPEC_ONLY','WAIT_MATCHED_CONTROL') or spec['family'] not in SUPPORTED|{'no_news_control'}:return {'status':'WAIT_INPUT_ADAPTER','rows':[]}
 start=clock(declared_at);now=clock(observed_at)
 if now<start:raise ValueError('NO_PREDECLARATION_DATA')
 good=[];refused=[]
 for row in rows:
  required={'ticker','family','observed_at','event_at','source_ref','source_sha256','independent_admission_ref','score','n_firms','net_raises','event_type','liquidity_segment','volatility','source_item_id'}
  if not isinstance(row,dict) or set(row)!=required:raise ValueError('EXACT_TIME_VALID_FEATURE_SCHEMA')
  known=clock(row['observed_at']);event=clock(row['event_at'])
  if known>now or event>known or (now-event).total_seconds()>spec['max_age_days']*86400:refused.append({'ticker':row['ticker'],'code':'TIME_OR_FRESHNESS_REFUSED'});continue
  if not row['source_ref'] or not row['independent_admission_ref'] or not isinstance(row['source_sha256'],str) or len(row['source_sha256'])!=64:refused.append({'ticker':row['ticker'],'code':'SOURCE_ADMISSION_ABSENT'});continue
  numbers=(row['score'],) if row['family']=='news' else (row['n_firms'],row['net_raises'])
  if spec['construction']=='volatility_aware':numbers=(*numbers,row['volatility'])
  if any(type(x) not in (int,float) or not math.isfinite(x) for x in numbers):raise ValueError('FINITE_ACTUAL_FEATURES_REQUIRED')
  if row['family'] not in spec['input_families'] or (spec['event_type'] is not None and row['family']=='news' and row['event_type']!=spec['event_type']):continue
  if spec['liquidity_segment']=='liquid' and row['liquidity_segment']!='liquid':continue
  good.append(row)
 present={r['family'] for r in good}
 if any(f not in present for f in spec['input_families']):return {'status':'WAIT_INPUT','rows':[],'refusals':refused}
 return {'status':'INPUT_ROWS_PRESENT_NOT_PRICE_OR_SOURCE_CONTENT_QUALIFICATION','rows':collapse_news(good),'refusals':refused}

def targets(spec,rows,*,asof=None):
 if spec['family']=='no_news_control':return {'CASH':1.0}
 grouped={}
 for r in rows:
  by_family=grouped.setdefault(r['ticker'],{})
  if r['family'] in by_family:raise ValueError('AMBIGUOUS_SAME_ISSUER_FEATURE_ROWS')
  by_family[r['family']]=r
 scores={}
 for ticker,features in grouped.items():
  if spec['join_rule']=='intersection' and not {'news','revision'}<=features.keys():continue
  total=0.0;input_scores={}
  for family,r in features.items():
   score=r['score']
   if family=='revision':
    if r['n_firms']<3:input_scores[family]=0;continue
    score=r['net_raises']*r['n_firms']
    if spec['mechanism']=='action_firm_normalized':score=r['net_raises']/r['n_firms']
    elif spec['mechanism']=='positive_net_raises':score=r['net_raises']
    elif spec['mechanism']=='freshness_weighted':
     if asof is None:raise ValueError('ACTUAL_SCORE_CLOCK_REQUIRED')
     age=(clock(asof)-clock(r['event_at'])).total_seconds()/86400
     if age<0:raise ValueError('FUTURE_EVENT_REFUSED')
     score*=2**(-age/spec['max_age_days'])
   input_scores[family]=score
   if score>0:total+=score
  if spec['join_rule']=='intersection' and any(input_scores.get(f,0)<=0 for f in ('news','revision')):continue
  if total>0:scores[ticker]=total
 names=sorted(scores,key=lambda t:(-scores[t],t))[:spec['max_names']]
 if not names:return None
 raw={t:1.0 for t in names}
 if spec['construction']=='volatility_aware':
  for t in names:
   vol={r['volatility'] for r in grouped[t].values()}
   if len(vol)!=1 or any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in vol):raise ValueError('QUALIFIED_SAME_PRICE_VOLATILITY_REQUIRED')
   raw[t]=1/next(iter(vol))
 total=sum(raw.values());weights={t:min(spec.get('name_cap',.05),spec.get('gross_target',.95)*v/total) for t,v in raw.items()}
 return {**weights,'CASH':1-sum(weights.values())}

def describe_counts(specs,states):
 counts=Counter(states.get(s['policy_id'],'UNCONSUMED') for s in specs['specifications'])
 return {'attempted_variants_cumulative':len(specs['attempts']),'unique_specs':len(specs['specifications']),'operating_states':dict(counts),'actual_seeded':sum(v for k,v in counts.items() if k in ('SEEDED','MARKED','OUTCOME_BEARING')),'active_claim_requires_actual_consumer':True}
