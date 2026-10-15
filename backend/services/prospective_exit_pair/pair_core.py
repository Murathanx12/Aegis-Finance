"""One prospectively declared fixed-basket exit pair; pure event accounting.

Not LP.grade: that grader has no sale event. Reuse its future-entry calendar
and prior-liquidity cost inputs in the owned adapter; retain every trade here.
All inputs are observations, never providers, forecasts, or learned policies.
"""
import copy, datetime, hashlib, json, math

def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def clock(s):
 t=datetime.datetime.fromisoformat(s.replace('Z','+00:00'))
 if t.tzinfo is None:raise ValueError('AWARE_ACTUAL_CLOCK_REQUIRED')
 return t.astimezone(datetime.timezone.utc)
def number(v):
 if type(v) not in (int,float) or not math.isfinite(v):raise ValueError('FINITE_NUMBER_REQUIRED')
 return v
def fee_scale(weights,costs):
 names=set(weights)-{'CASH'}
 if set(costs)!=names:raise ValueError('EXACT_DECLARED_COST_NAMES_REQUIRED')
 gross=sum(weights[t] for t in names);budget=sum(weights[t]*number(costs[t]['one_way_rate']) for t in names)
 if any(not 0<=costs[t]['one_way_rate']<.01 for t in names):raise ValueError('BOUNDED_ONE_WAY_RATE_REQUIRED')
 return min(1.0,1.0/(gross+budget)) if gross+budget else 1.0
def validate_declaration(d):
 if d.get('schema')!='prospective_fixed_exit_pair/1' or d.get('exit_sessions')!=5 or d.get('control_exit_sessions')!=126 or d.get('primary_sessions')!=21 or d.get('cash_interest')!=0:raise ValueError('FROZEN_PAIR_POLICY_REQUIRED')
 if d.get('historical_nav_inherited') is not False or d.get('activation')!='NONE':raise ValueError('NO_INHERITED_NAV_OR_ACTIVATION')
 if not 0<number(d['initial_nav'])<=1000000:raise ValueError('VIRTUAL_NOTIONAL_BOUND')
 if not d['weights'] or len(d['weights'])>40 or 'CASH' not in d['weights'] or any(number(w)<0 for w in d['weights'].values()) or abs(sum(d['weights'].values())-1)>1e-12:raise ValueError('EXACT_UNSCALED_PARENT_WEIGHTS')
 if d.get('fee_budget_rule')!='COMMON_PROPORTIONAL_COST_BUDGET' or abs(number(d['fee_budget_scale'])-fee_scale(d['weights'],d['entry_costs']))>1e-14:raise ValueError('EXACT_PREDECLARED_COMMON_FEE_BUDGET')
 if len(d['sessions'])!=126:raise ValueError('EXACT_XNYS_SCHEDULE_REQUIRED')
 prev=None
 for s in d['sessions']:
  day=datetime.date.fromisoformat(s['date']);op,cl=clock(s['open']),clock(s['close'])
  if op>=cl or op.date()!=day or cl.date()!=day or prev and day<=prev:raise ValueError('STRICT_SESSION_SCHEDULE_REQUIRED')
  prev=day
 if datetime.date.fromisoformat(d['sessions'][0]['date'])<=clock(d['declared_utc']).date():raise ValueError('FUTURE_ENTRY_AFTER_DECLARATION_DATE')
 if clock(d['registered_utc'])>clock(d['declared_utc']) or clock(d['committed_utc'])>clock(d['registered_utc']):raise ValueError('COMMIT_REGISTER_DECLARE_ORDER_REQUIRED')
 if not d['parent_book_id'] or not d['parent_record_sha256'] or not d['contract_sha256']:raise ValueError('ACTUAL_FROZEN_LINEAGE_REQUIRED')
 return d
def initial_state(d):
 validate_declaration(d)
 return {'declaration_sha256':digest(d),'next_index':0,'benchmark_entry_open':None,'arms':{role:{'cash':d['initial_nav'],'shares':{},'entry_rates':{},'cost_usd':0.0,'traded_usd':0.0,'nav_sum':0.0,'n_marks':0,'last_nav':None} for role in ('exit5','fixed_hold')}}
def wait(state,reason):return {'status':'WAIT','reason':reason,'state_unchanged_sha256':digest(state)}
def step(d,state,inputs):
 """Consume exactly the next real session, atomically across both arms.

Modeled trades carry scheduled economic time AND actual observation time.
No live fills, retroactive declaration, forward-filled mark or missing zero.
"""
 validate_declaration(d)
 if state['declaration_sha256']!=digest(d):raise ValueError('EXACT_DECLARATION_REQUIRED')
 i=state['next_index']
 if i>=126:return {'status':'COMPLETE','state_unchanged_sha256':digest(state)}
 s=d['sessions'][i];now=clock(inputs['observed_utc'])
 if inputs['session']!=s['date']:raise ValueError('NO_SKIPPED_OR_REORDERED_SESSION')
 if now<clock(s['close']):return wait(state,'SESSION_NOT_CLOSED')
 names=set(d['weights'])-{'CASH'};prices=inputs['prices']
 for t in names|{'SPY'}:
  row=prices.get(t)
  if not row or row.get('date')!=s['date']:return wait(state,'MISSING_EXACT_SESSION_PRICE')
  if not clock(s['close'])<=clock(row['available_utc'])<=now:return wait(state,'PRICE_NOT_KNOWN_AT_OBSERVATION')
  try:
   if number(row['close'])<=0 or i==0 and number(row['open'])<=0:return wait(state,'INVALID_EXACT_SESSION_PRICE')
  except (KeyError,ValueError):return wait(state,'INVALID_EXACT_SESSION_PRICE')
 if i==0:
  costs=inputs.get('entry_costs',{})
  if costs!=d['entry_costs']:raise ValueError('EXACT_DECLARED_COSTS_REQUIRED')
  if set(costs)!=names:return wait(state,'MISSING_PRIOR_LIQUIDITY_COST')
  for t,c in costs.items():
   if not 0<=number(c['one_way_rate'])<.01 or clock(c['known_before_utc'])>=clock(s['open']):return wait(state,'INVALID_PRIOR_LIQUIDITY_COST')
 out=copy.deepcopy(state);events=[];marks={};N=d['initial_nav']
 if i==0:out['benchmark_entry_open']=prices['SPY']['open']
 for role,a in out['arms'].items():
  if i==0:
   for t in sorted(names):
    usd=N*d['weights'][t]*d['fee_budget_scale'];px=prices[t]['open'];sh=usd/px;rate=inputs['entry_costs'][t]['one_way_rate'];cost=usd*rate
    a['shares'][t]=sh;a['entry_rates'][t]=rate;a['cash']-=usd+cost;a['cost_usd']+=cost;a['traded_usd']+=usd
    events.append({'role':role,'side':'BUY','ticker':t,'shares':sh,'price':px,'traded_usd':usd,'cost_usd':cost,'rate':rate,'economic_utc':s['open'],'observed_utc':inputs['observed_utc'],'execution':'MODELED_PRECOMMITTED_ENTRY_OPEN_NOT_BROKER_FILL'})
   if a['cash'] < -1e-8:raise ValueError('CASH_CANNOT_FINANCE_ENTRY_COST')
   if abs(a['cash'])<1e-8:a['cash']=0.0  # floating roundoff only, never missing data
  due=(role=='exit5' and i==4) or (role=='fixed_hold' and i==125)
  if due:
   for t,sh in sorted(a['shares'].items()):
    px=prices[t]['close'];usd=sh*px;rate=a['entry_rates'][t];cost=usd*rate
    a['cash']+=usd-cost;a['cost_usd']+=cost;a['traded_usd']+=usd
    events.append({'role':role,'side':'SELL','ticker':t,'shares':sh,'price':px,'traded_usd':usd,'cost_usd':cost,'rate':rate,'economic_utc':s['close'],'observed_utc':inputs['observed_utc'],'execution':'MODELED_PRECOMMITTED_CLOSE_EXIT_NOT_BROKER_FILL'})
   a['shares']={}
  exposure=sum(sh*prices[t]['close'] for t,sh in a['shares'].items());nav=a['cash']+exposure
  a['nav_sum']+=nav;a['n_marks']+=1;a['last_nav']=nav;avg=a['nav_sum']/a['n_marks']
  days=(datetime.date.fromisoformat(s['date'])-datetime.date.fromisoformat(d['sessions'][0]['date'])).days
  marks[role]={'nav_usd':nav,'return_fraction':nav/N-1,'equity_exposure_usd':exposure,'equity_exposure_fraction_nav':exposure/nav,'cash_usd':a['cash'],'cumulative_cost_usd':a['cost_usd'],'cumulative_traded_usd':a['traded_usd'],'cost_bps_traded':10000*a['cost_usd']/a['traded_usd'] if a['traded_usd'] else None,'annualized_cost_fraction_average_nav':a['cost_usd']/avg*365.25/days if days else None,'cost_model':'LP_XR_PRIOR_ENTRY_BAND_HALF_ROUNDTRIP_PER_ACTUAL_TRADED_NOTIONAL; no impact/spread/participation/delay model','exit_executed':not bool(a['shares'])}
 out['next_index']=i+1
 for m in marks.values():m.update(entry_fee_budget_scale=d['fee_budget_scale'],target_initial_stock_gross=1-d['weights']['CASH'],actual_initial_stock_gross=(1-d['weights']['CASH'])*d['fee_budget_scale'])
 b=prices['SPY']['close']/out['benchmark_entry_open']-1
 for m in marks.values():m['benchmark_return_fraction']=b;m['excess_return_fraction']=m['return_fraction']-b
 return {'status':'MARKED','session':s['date'],'session_number':i+1,'observed_utc':inputs['observed_utc'],'inputs':copy.deepcopy(inputs),'events':events,'marks':marks,'net_pair_difference_fraction':marks['exit5']['return_fraction']-marks['fixed_hold']['return_fraction'],'primary_window_complete':i+1>=21,'no_independent_trial_or_skill_claim':True,'state':out}
def replay(d,records):
 state=initial_state(d);prev=None
 for r in records:
  body={k:v for k,v in r.items() if k!='record_sha256'}
  if r.get('previous_sha256')!=prev or r.get('record_sha256')!=digest(body):raise ValueError('PAIR_LEDGER_HASH_CHAIN_REFUSED')
  expected=step(d,state,r['result']['inputs'])
  if expected['status']!='MARKED' or expected!=r['result']:raise ValueError('PAIR_LEDGER_REPLAY_REFUSED')
  state=expected['state'];prev=r['record_sha256']
 return state,prev
def record(result,previous_sha256):
 if result['status']!='MARKED':raise ValueError('WAIT_NEVER_BECOMES_ZERO_NAV')
 body={'schema':'fixed_exit_pair_session/1','previous_sha256':previous_sha256,'result':result}
 return dict(body,record_sha256=digest(body))
