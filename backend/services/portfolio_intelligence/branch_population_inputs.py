"""Concrete existing-cache adapters, zero providers/model calls.

Typed sentiment is an explicitly unverified model-context experimental input,
never a factual admission, market probability or H21 expected-return mapping.
Revision features reuse revision_flow.compute on its existing pit_safe events.
"""
import datetime,hashlib,json,math,shutil,types
from pathlib import Path
from backend.services.portfolio_intelligence.branch_population import clock,digest,collapse_news
ROOT=Path('C:/Users/mrthn/aegis-finance');DATA=ROOT/'backend/data/optimus'
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for part in iter(lambda:f.read(65536),b''):h.update(part)
 return h.hexdigest()
def ref(path):return {'path':str(path),'sha256':sha(path)}
def snapshot(path,directory):
 path=Path(path);before=(path.stat().st_size,path.stat().st_mtime_ns)
 if before[0]>64*1024**2:raise ValueError('SHARED_INPUT_SNAPSHOT_CAP')
 target=Path(directory)/path.name
 with path.open('rb') as source,target.open('xb') as dest:shutil.copyfileobj(source,dest,65536)
 if before!=(path.stat().st_size,path.stat().st_mtime_ns) or sha(path)!=sha(target):raise ValueError('WAIT_SHARED_INPUT_REFRESH')
 return target
def read_operating_review(reference,manifest_sha):
 path=Path(reference['path'])
 if sha(path)!=reference['sha256']:raise ValueError('INPUT_REVIEW_PIN')
 value=json.loads(path.read_bytes())
 if value.get('independent') is not True or value.get('verdict')!='PASS_POPULATION_OPERATING_SOURCES_ONLY' or value.get('manifest_sha256')!=manifest_sha or value.get('legacy_typed_context_is_verified_fact') is not False or set(value.get('approved_inputs',[]))!={'dated_target_revision_changes','unverified_typed_sentiment_context'}:raise ValueError('EXACT_EXPERIMENTAL_INPUT_REVIEW_REQUIRED')
 return value
def revision_rows(path,receipt,review_ref,*,observed_at,rf,pandas,market):
 available=clock(receipt['written_utc']);now=clock(observed_at)
 if available>now:raise ValueError('FUTURE_REVISION_AVAILABILITY')
 # STRICT prior-date event cutoff is the original implementation's contract.
 frame=rf.compute(pandas.read_parquet(path),asof=now.date())
 source=ref(path);rows=[]
 for ticker,v in frame.iterrows():
  if ticker not in market:continue
  event=datetime.datetime.combine(now.date(),datetime.time(),tzinfo=datetime.timezone.utc)-datetime.timedelta(days=float(v['days_since_last']))
  if event>available:continue
  rows.append(dict(ticker=str(ticker),family='revision',observed_at=available.isoformat(),event_at=event.isoformat(),source_ref=source,source_sha256=source['sha256'],independent_admission_ref=review_ref,score=None,n_firms=float(v['n_firms']),net_raises=float(v['net_raises']),event_type=None,liquidity_segment=market[ticker]['liquidity_segment'],volatility=market[ticker]['volatility'],source_item_id=None))
 return rows
def news_rows(path,review_ref,*,observed_at,market):
 now=clock(observed_at);latest={};refusals=[]
 with Path(path).open('r',encoding='utf8') as f:
  for line in f:
   if len(line)>1024*1024:raise ValueError('NEWS_CACHE_ROW_CAP')
   rec=json.loads(line);row=rec.get('row')
   if not isinstance(row,dict) or not rec.get('cached_utc'):continue
   known=clock(rec['cached_utc'])
   if known>now:continue
   if not row.get('item_id') or not row.get('url') or row.get('source_kind')!='news' or row.get('injection_lines_removed') not in (None,0):continue
   first=clock(row['first_seen_utc']);published=clock(row['published_utc']) if row.get('published_utc') else first
   if first>known or published>known or (now-published).total_seconds()>5*86400:continue
   score=row.get('sentiment')
   if type(score) not in (int,float) or not math.isfinite(score) or not -1<=score<=1:continue
   key=row['item_id']
   if key in latest and latest[key] is None:continue
   if key in latest and latest[key][1].get('event_type')!=row.get('event_type'):
    refusals.append({'item_id':key,'code':'AMBIGUOUS_TYPED_EVENT'});latest[key]=None;continue
   if key not in latest or latest[key][0]<known:latest[key]=(known,row,published)
 source=ref(path);rows=[]
 for value in latest.values():
  if value is None:continue
  known,row,published=value
  for ticker in row.get('tickers',[]):
   if ticker in market:
    # Keep each actual story clock. Policy-age filtering must precede averaging;
    # a fresh story can never refresh a stale story's signed context.
    rows.append(dict(ticker=ticker,family='news',observed_at=known.isoformat(),event_at=published.isoformat(),source_ref=source,source_sha256=source['sha256'],independent_admission_ref=review_ref,score=float(row['sentiment']),n_firms=None,net_raises=None,event_type=row.get('event_type'),liquidity_segment=market[ticker]['liquidity_segment'],volatility=market[ticker]['volatility'],source_item_id=row['item_id']))
 return rows,refusals
def market_metadata(bars,lp,*,observed_at):
 import pandas as pd
 asof=pd.Timestamp(clock(observed_at).date());prior=bars[bars['date']<=asof]
 bands=lp.liquidity_bands(prior,asof=asof);out={}
 for ticker,g in prior.groupby('symbol'):
  close=g.sort_values('date')['close'].astype(float)
  if not close.map(math.isfinite).all() or (close<=0).any():continue
  returns=close.pct_change(fill_method=None).dropna().tail(63)
  if len(returns)<20 or g['date'].max()<asof-pd.Timedelta(days=5):continue
  vol=float(returns.std())
  if not math.isfinite(vol) or vol<=0:continue
  # Existing liquidity bands, no surrogate source of total analyst coverage.
  out[str(ticker)]={'liquidity_segment':'liquid' if bands.get(ticker) in ('large','mid','mega') else 'broad','volatility':vol}
 return out
class ExistingInputAdapters:
 quality='UNVERIFIED_TYPED_MODEL_CONTEXT_AND_DATED_REVISION_EXPERIMENT'
 def __init__(self,specs,review_ref,directory,*,observed_at,lp,rf,pandas,bars):
  read_operating_review(review_ref,digest(specs));directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
  self.features=[];self.refusals=[];self.known_rows=set()
  market=market_metadata(bars,lp,observed_at=observed_at)
  revision=snapshot(DATA/'analyst/target_revisions.parquet',directory)
  receipts=sorted((DATA/'analyst').glob('analyst_pull_*.json'))
  if not receipts:raise ValueError('ACTUAL_REVISION_PULL_RECEIPT_REQUIRED')
  receipt_path=snapshot(receipts[-1],directory);receipt=json.loads(receipt_path.read_bytes())
  self.features+=revision_rows(revision,receipt,review_ref,observed_at=observed_at,rf=rf,pandas=pandas,market=market)
  news=snapshot(DATA/'news_corpus/_digest_cache/extract_wd_v1.jsonl',directory)
  news_features,self.refusals=news_rows(news,review_ref,observed_at=observed_at,market=market);self.features+=news_features
  if len(self.features)>10000:raise ValueError('SHARED_FEATURE_CAP')
  self.known_rows={digest(row) for row in self.features}
 def admit(self,spec,rows,observed_at):
  for row in rows:
   components=row.get('_component_rows')
   if components is None:
    if digest(row) not in self.known_rows:return False
   elif any(digest(component) not in self.known_rows for component in components) or collapse_news(components)!=[row]:return False
  return bool(rows)
 def callbacks(self):return {name:self.admit for name in ('news_only','hybrid_news_revision','revision_flow','net_raises')}

class SharedGrader:
 """Original grade code/rules, one private grouping cache for one fixed frame."""
 def __init__(self,lp,bars):
  self.read_books=lp.read_books;grouped=lp._grouped(bars)
  def priced_freeze(book,**kwargs):return lp.freeze(book,universe=set(grouped),**kwargs)
  self.freeze=priced_freeze
  def same_frame(actual):
   if actual is not bars:raise ValueError('EXACT_SHARED_PRICE_FRAME_REQUIRED')
   return grouped
  self.grade=types.FunctionType(lp.grade.__code__,dict(lp.grade.__globals__,_grouped=same_frame),lp.grade.__name__,lp.grade.__defaults__,lp.grade.__closure__)
  self.grade.__kwdefaults__=dict(lp.grade.__kwdefaults__ or {})
