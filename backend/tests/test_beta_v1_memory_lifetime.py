"""Small lifetime/equivalence fixtures; never a native data/model run."""
import ast,hashlib,json,weakref
import inspect
from pathlib import Path
from datetime import datetime,timezone,timedelta

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.dataset as ds
import pytest
from backend.services import beta_v1_numerical as N

BASELINE_SHA256="4f0cbd43be855c4c58fdf30e04d8e3db9ffaba9587f996b504e4b576c5a90de0"
LEGACY_PREFIX="def _legacy_prefix(*, facts_sha256, tickers_sha256, budget=None, model_sink=None):\n    budget = budget or Budget()\n    before = code_pins()\n    if any((before[name] != expected for name, expected in FROZEN_SOURCE_PINS.items())):\n        raise NumericalRefused('frozen original model/stitch/policy source drift')\n    spec = specification()\n    registrants, metadata_audit = registrant_metadata(facts_sha256=facts_sha256, tickers_sha256=tickers_sha256, budget=budget)\n    bars, input_pins = read_prices(budget)\n    bars, audit = prepare_prices(bars, registrants=registrants)\n    budget.check('stitch/duplicates', rows=len(bars))\n    dataset_hash = hashlib.sha256(pd.util.hash_pandas_object(bars, index=False).values.tobytes()).hexdigest()\n    panel = xr.mark_eligible(xr.build_features(bars))\n    budget.check('trailing features')\n    feature_values_hash = hashlib.sha256(pd.util.hash_pandas_object(panel[['symbol', 'date', *xr.FEATURES]], index=False).values.tobytes()).hexdigest()\n    panel, target_audit = close_target(panel)\n    budget.check('exact close target')\n    return (panel, audit, metadata_audit, input_pins, dataset_hash, feature_values_hash, target_audit)"
LEGACY_PRICE_READ='def read_prices(budget):\n    """Only the two explicitly pinned ordinary price inputs, date-filtered batches."""\n    import pyarrow as pa\n    import pyarrow.dataset as ds\n\n    frames, pins, total = [], {}, 0\n    for name, expected in PRICE_SOURCES.items():\n        path = Path(name)\n        before = sha256(path)\n        if before != expected:\n            raise NumericalRefused("price source pin drift: "+path.name)\n        dataset = ds.dataset(path, format="parquet")\n        names = set(dataset.schema.names)\n        if not set(PRICE_COLUMNS[:7]) <= names:\n            raise NumericalRefused("required ordinary price columns missing")\n        date_type = dataset.schema.field("date").type\n        start = pa.scalar(pd.Timestamp(START).to_pydatetime(), type=date_type)\n        end = pa.scalar(pd.Timestamp(CUTOFF).to_pydatetime(), type=date_type)\n        scanner = dataset.scanner(columns=[c for c in PRICE_COLUMNS if c in names],\n            filter=(ds.field("date") >= start) & (ds.field("date") <= end),\n            batch_size=32768, use_threads=False, batch_readahead=1, fragment_readahead=1)\n        for batch in scanner.to_batches():\n            total += batch.num_rows\n            budget.check("price batch", rows=total)\n            frame = batch.to_pandas()\n            frame["_src"] = path.stem\n            frames.append(frame)\n        after = sha256(path)\n        if after != before:\n            raise NumericalRefused("price changed during streamed read")\n        pins[name] = {"sha256": before, "after_sha256": after, "columns": [c for c in PRICE_COLUMNS if c in names]}\n    result = pd.concat(frames, ignore_index=True)\n    budget.check("price concat", rows=len(result))\n    return result, pins'
REFERENCE_AST_SHA256='a90d514aabeff2789a60da192707c67e547c0af465dcdc6a616b2948c0ccaafe'

class StopBeforeFit(Exception):
    pass

class WeakRegistry(dict):
    pass

IO_ROOT = None

def require_fixture_path(path):
    candidate=Path(path).resolve()
    if IO_ROOT is None or not candidate.is_relative_to(IO_ROOT):
        raise AssertionError('analytical path outside isolated pytest fixture')
    return candidate

@pytest.fixture(autouse=True)
def fixture_access_guard(tmp_path,monkeypatch):
    global IO_ROOT
    IO_ROOT=tmp_path.resolve()
    original_sha=N.sha256;original_dataset=ds.dataset;original_parquet=pq.ParquetFile
    def fixture_sha(path):
        require_fixture_path(path)
        return original_sha(path)
    def fixture_dataset(path,*args,**kw):
        require_fixture_path(path)
        return original_dataset(path,*args,**kw)
    def fixture_parquet(path,*args,**kw):
        require_fixture_path(path)
        return original_parquet(path,*args,**kw)
    monkeypatch.setattr(N,'sha256',fixture_sha)
    monkeypatch.setattr(ds,'dataset',fixture_dataset)
    monkeypatch.setattr(pq,'ParquetFile',fixture_parquet)
    monkeypatch.setattr(N,'PRICE_SOURCES',{})
    monkeypatch.setattr(N,'FACTS_PATH',tmp_path/'unused-facts.parquet')
    monkeypatch.setattr(N,'TICKERS_PATH',tmp_path/'unused-tickers.json')
    yield
    IO_ROOT=None

def fixture_bars():
    calendar=N.xcals.get_calendar('XNYS')
    dates=calendar.sessions_in_range(N.START,N.CUTOFF).tz_localize(None)[-300:]
    rows=[]
    for symbol,base in [('AAA',10.),('BBB',20.),('SPY',100.)]:
        for i,date in enumerate(dates):
            close=base+.015*i+.2*np.sin(i/4)
            rows.append(dict(symbol=symbol,date=date,open=close*.999,high=close*1.01,low=close*.99,close=close,volume=5_000_000.,vwap=close,trades=250))
    return pd.DataFrame(rows)

def legacy(name):
    assert hashlib.sha256(ast.dump(ast.parse(LEGACY_PREFIX+'\n'+LEGACY_PRICE_READ),include_attributes=False).encode()).hexdigest()==REFERENCE_AST_SHA256
    namespace=dict(vars(N))
    # Compile only the requested reference. Compiling read_prices alongside the
    # prefix would overwrite its injected reader and escape fixture isolation.
    exec(LEGACY_PREFIX if name=='_legacy_prefix' else LEGACY_PRICE_READ,namespace)
    fn=namespace[name]
    for path in fn.__globals__['PRICE_SOURCES']:
        require_fixture_path(path)
    if name=='_legacy_prefix':
        assert fn.__globals__['read_prices'] is N.read_prices, 'frozen reference overrode injected fixture reader'
        assert fn.__globals__['registrant_metadata'] is N.registrant_metadata, 'frozen reference overrode metadata fixture'
    return fn

@pytest.mark.parametrize('reader',['hash','dataset','parquet'])
def test_native_path_rejected_before_any_analytical_io(reader):
    forbidden=Path('C:/Users/mrthn/aegis-finance/backend/data/optimus/prices_deep/bars.parquet')
    fn={'hash':N.sha256,'dataset':ds.dataset,'parquet':pq.ParquetFile}[reader]
    with pytest.raises(AssertionError,match='outside isolated pytest fixture'):
        fn(forbidden)

def test_reference_retains_injected_reader_before_execution(monkeypatch):
    class FixtureBoundary(Exception):pass
    def stop(budget):raise FixtureBoundary('isolated fixture reader invoked')
    monkeypatch.setattr(N,'code_pins',lambda:dict(N.FROZEN_SOURCE_PINS))
    monkeypatch.setattr(N,'registrant_metadata',lambda **kw:({},{}))
    monkeypatch.setattr(N,'read_prices',stop)
    fn=legacy('_legacy_prefix')
    assert fn.__globals__['read_prices'] is stop and fn.__globals__['PRICE_SOURCES']=={}
    with pytest.raises(FixtureBoundary,match='isolated fixture reader'):
        fn(facts_sha256='fixture',tickers_sha256='fixture')

def test_preprocessing_values_hashes_and_dead_reference_lifetimes(monkeypatch):
    refs={}; snapshots={}; original_features=N.xr.build_features; original_eligible=N.xr.mark_eligible
    raw=fixture_bars()
    monkeypatch.setattr(N,'PRICE_SOURCES',{})  # unexpected native reader has no authorized paths
    def registrants(**kw):
        reg=WeakRegistry(by_ticker={s:{'cik':i+1,'first_filed':pd.Timestamp(N.START)-pd.Timedelta(days=365),'source':'fixture'} for i,s in enumerate(['AAA','BBB','SPY'])},cik_first=pd.Series(dtype='datetime64[ns]'),sources=['fixture'])
        refs['registry']=weakref.ref(reg)
        return reg,{'source_pins':{},'scope':'fixture'}
    prepare=N.prepare_prices
    def prepared(bars,**kw):
        result,audit=prepare(bars,**kw)
        refs['prepared_bars']=weakref.ref(result)
        return result,audit
    def features(bars):
        snapshots['at_features_registry_alive']=refs['registry']() is not None
        result=original_features(bars);refs['features']=weakref.ref(result);return result
    def eligible(frame):
        snapshots['at_eligibility_bars_alive']=refs['prepared_bars']() is not None
        return original_eligible(frame)
    monkeypatch.setattr(N,'registrant_metadata',registrants)
    monkeypatch.setattr(N,'read_prices',lambda budget:(raw.assign(_src='fixture'),{'fixture':{'sha256':'fixture'}}))
    monkeypatch.setattr(N,'prepare_prices',prepared)
    monkeypatch.setattr(N.xr,'build_features',features);monkeypatch.setattr(N.xr,'mark_eligible',eligible)
    monkeypatch.setattr(N,'code_pins',lambda:dict(N.FROZEN_SOURCE_PINS))
    expected=legacy('_legacy_prefix')(facts_sha256='fixture',tickers_sha256='fixture')
    assert snapshots['at_features_registry_alive'] and snapshots['at_eligibility_bars_alive']
    captured={};events=[]
    def stop(panel,budget):
        caller=inspect.currentframe().f_back.f_locals
        for key in ['audit','metadata_audit','input_pins','dataset_hash','feature_values_hash','target_audit']:
            captured[key]=caller[key]
        captured['panel']=panel
        assert refs['registry']() is None and refs['prepared_bars']() is None and refs['features']() is None
        raise StopBeforeFit()
    monkeypatch.setattr(N,'fit_oos',stop)
    with pytest.raises(StopBeforeFit):N.run(facts_sha256='fixture',tickers_sha256='fixture',budget=N.Budget(progress_callback=events.append))
    assert not snapshots['at_features_registry_alive'] and not snapshots['at_eligibility_bars_alive']
    pd.testing.assert_frame_equal(expected[0],captured['panel'],check_exact=True,check_dtype=True)
    for value,key in zip(expected[1:],['audit','metadata_audit','input_pins','dataset_hash','feature_values_hash','target_audit']):assert value==captured[key]
    assert [(e['stage'],e['phase']) for e in events]==[(s,p) for s in ['registrants','price_read','prepare_prices','dataset_hash','features','eligibility','feature_hash','close_target'] for p in ['enter','complete']]
    assert N.specification()['parameters']==N.xr.LGB_PARAMS and N.specification()['folds']==4

@pytest.mark.parametrize('optional',[True,False])
def test_streamed_concat_equivalence_and_release_before_checkpoint(tmp_path,monkeypatch,optional):
    frame=fixture_bars().iloc[:80].copy();paths=[]
    for i in range(2):
        part=frame.iloc[i*40:(i+1)*40].copy()
        if i==1 and not optional:part=part.drop(columns=['vwap','trades'])
        path=tmp_path/f'price{i}.parquet';pq.write_table(pa.Table.from_pandas(part,preserve_index=False),path);paths.append(path)
    monkeypatch.setattr(N,'PRICE_SOURCES',{str(p):N.sha256(p) for p in paths})
    original_concat=N.pd.concat;refs=[];live=[]
    def concat(frames,**kw):
        refs[:]=[weakref.ref(f) for f in frames]
        return original_concat(frames,**kw)
    class Checkpoint:
        def check(self,stage,**kw):
            if stage=='price concat':live.append(sum(r() is not None for r in refs))
    monkeypatch.setattr(N.pd,'concat',concat)
    old,pins=legacy('read_prices')(Checkpoint())
    assert live[-1]==2
    new,newpins=N.read_prices(Checkpoint())
    assert live[-1]==0
    pd.testing.assert_frame_equal(new,old,check_exact=True,check_dtype=True)
    assert pins==newpins
    assert pd.util.hash_pandas_object(new,index=False).equals(pd.util.hash_pandas_object(old,index=False))

@pytest.mark.parametrize('mutate', ['pin','required_column'])
def test_stream_source_refusals_match_reference(tmp_path,monkeypatch,mutate):
    frame=fixture_bars().iloc[:10].copy()
    if mutate=='required_column':frame=frame.drop(columns='open')
    path=tmp_path/'refused.parquet';pq.write_table(pa.Table.from_pandas(frame,preserve_index=False),path)
    monkeypatch.setattr(N,'PRICE_SOURCES',{str(path):'0'*64 if mutate=='pin' else N.sha256(path)})
    for fn in [legacy('read_prices'),N.read_prices]:
        with pytest.raises(N.NumericalRefused,match='pin drift|required ordinary price columns'):fn(N.Budget())

def test_scalar_trace_bounds_and_whitelist(monkeypatch):
    monkeypatch.setattr(N,'rss_bytes',lambda *a,**kw:123)
    events=[];budget=N.Budget(progress_callback=events.append)
    for _ in range(64):budget.check('features',rows=10,phase='enter')
    assert len(events)==64 and budget.progress_bytes<=64*1024
    with pytest.raises(N.NumericalRefused,match='metadata cap'):budget.check('features',phase='complete')
    assert len(events)==64
    assert set(events[0])=={'schema','stage','phase','utc','pid','elapsed_seconds','rows','rss_bytes','peak_rss_bytes'}
    assert datetime.fromisoformat(events[0]['utc']).utcoffset() is not None
    assert events[0]['rss_bytes']==events[0]['peak_rss_bytes']==123
    assert not any('symbol' in e or 'values' in e for e in events)
    with pytest.raises(N.NumericalRefused,match='unsupported'):N.Budget(progress_callback=events.append).check('private numeric panel',phase='enter')
    budget=N.Budget(progress_callback=events.append);budget.progress_bytes=65535
    with pytest.raises(N.NumericalRefused,match='metadata cap'):budget.check('features',phase='enter')
    assert len(events)==64

def test_callback_failure_and_time_cost_refuse(monkeypatch):
    monkeypatch.setattr(N,'rss_bytes',lambda *a,**kw:123)
    def failure(e):raise OSError('private detail must not leak')
    with pytest.raises(N.NumericalRefused,match='callback failed: OSError') as exc:N.Budget(progress_callback=failure).check('features',phase='enter')
    assert 'private detail' not in str(exc.value)
    clock=[0.];monkeypatch.setattr(N.time,'monotonic',lambda:clock[0])
    def slow(e):clock[0]=466
    with pytest.raises(N.NumericalRefused,match='during scalar progress'):N.Budget(started=0,progress_callback=slow).check('features',phase='enter')

def test_progress_optional_and_original_caps_unchanged(monkeypatch):
    monkeypatch.setattr(N,'rss_bytes',lambda *a,**kw:123)
    budget=N.Budget();budget.check('original legacy checkpoint')
    assert budget.progress_events==budget.progress_bytes==0
    assert (budget.max_rss,budget.max_rows,budget.max_seconds,budget.max_output)==(3*1024**3,2_500_000,465,32*1024**2)
    with pytest.raises(N.NumericalRefused,match='resource cap'):budget.check('rows',rows=budget.max_rows+1)


# Exact function-only f62 reference; no private artifact/path import at test time.
FOLD_REFERENCE_ORIGIN_SHA256 = 'f62ec9d20cf17cbc7bc54b4a4726acb5fe4005bb031a6536bc3ef35ac3d5489f'
FOLD_REFERENCE_SOURCE_SHA256 = '88de592bcb74f12fd719c8f27feb08209a4a6b7b4f1bbac8a2c11369bc58ecec'
FOLD_REFERENCE_AST_SHA256 = 'd36c4059792a15a02cb5de8ee1ece4e5142cdea7653d8a2e4bae27de7a57cab7'


def fold_reference_tree():
    assert FOLD_REFERENCE_ORIGIN_SHA256 == 'f62ec9d20cf17cbc7bc54b4a4726acb5fe4005bb031a6536bc3ef35ac3d5489f'
    assert hashlib.sha256(FOLD_REFERENCE_SOURCE.encode()).hexdigest() == FOLD_REFERENCE_SOURCE_SHA256
    tree = ast.parse(FOLD_REFERENCE_SOURCE)
    assert len(tree.body) == 1 and isinstance(tree.body[0], ast.FunctionDef)
    assert tree.body[0].name == 'fit_oos'
    assert hashlib.sha256(ast.dump(tree.body[0], include_attributes=False).encode()).hexdigest() == FOLD_REFERENCE_AST_SHA256
    return tree


def fold_fixture_panel(registry):
    calendar = N.xcals.get_calendar('XNYS')
    sessions = calendar.sessions_in_range('2024-01-02', '2025-12-31')[:300]
    values = []
    for index, session in enumerate(sessions[:240]):
        for symbol in ('AAA', 'BBB'):
            record = {name: (index+1)/1000 + position/100 for position, name in enumerate(N.xr.FEATURES)}
            record.update(symbol=symbol, date=session.tz_localize(None), eligible=True,
                y=.001+index/100000, fwd_rel=.001+index/100000, fwd_ret=.01,
                bench_fwd_ret=.009, median_dollar_vol=30_000_000., close=10.,
                formation_at=calendar.session_close(session).isoformat(),
                label_start_at=calendar.session_close(sessions[index+1]).isoformat(),
                label_end_at=calendar.session_close(sessions[index+22]).isoformat())
            values.append(record)

    class TrackWholeRows(pd.DataFrame):
        @property
        def _constructor(self):
            parent = weakref.ref(self)
            def construct(*args, **kwargs):
                result = pd.DataFrame(*args, **kwargs)
                if parent() is panel and 'whole_rows' not in registry:
                    registry['whole_rows'] = weakref.ref(result)
                return result
            return construct
    panel = TrackWholeRows(values)
    return panel


def run_fold_fixture(monkeypatch, *, frozen, refused=(), enforce_lifetime=False):
    """Real split/calendar/features/params; tiny gate/model doubles, no fitting.

    Synthetic MIN_TRAIN_ROWS=2 only exercises both branches in a small panel.
    specification() still checks unchanged production 40000/350/24/four-fold
    constants. The fake model retains no DataFrame and runs no native model code.
    """
    from types import FunctionType, SimpleNamespace
    import sys
    registry = {'split_refs': [], 'model_refs': []}
    panel = fold_fixture_panel(registry)
    snapshot = pd.DataFrame(panel).copy(deep=True)
    events, fitted_parameters = [], []
    fold_number = [0]

    class Booster:
        def __init__(self):
            self.text = ''
        def model_to_string(self):
            return self.text

    class SyntheticModel:
        def __init__(self, **kwargs):
            assert kwargs == {**N.xr.LGB_PARAMS, 'n_jobs': 2}
            assert kwargs['n_estimators'] == 350 and len(N.xr.FEATURES) == 24
            self.booster_ = Booster()
            registry['model_refs'].append(weakref.ref(self))
            fitted_parameters.append(kwargs.copy())
        def fit(self, features, target):
            assert list(features.columns) == list(N.xr.FEATURES)
            self.center = float(target.mean())
            self.booster_.text = json.dumps({'rows': len(features), 'center': self.center,
                                            'columns': list(features.columns)}, sort_keys=True)
        def predict(self, features):
            return features.sum(axis=1).to_numpy()*0.001 + self.center

    monkeypatch.setitem(sys.modules, 'lightgbm', SimpleNamespace(LGBMRegressor=SyntheticModel))

    def split(input_panel, train_end, start, end):
        train, test, receipt = N.fold_rows(input_panel, train_end, start, end)
        number = fold_number[0]
        fold_number[0] += 1
        if number in refused:
            train = train.iloc[:1].copy()
            receipt = {**receipt, 'n_train': len(train),
                       'latest_train_label_end': max(train['label_end_at']) if len(train) else None}
        registry['split_refs'].append((weakref.ref(train), weakref.ref(test)))
        return train, test, receipt

    class FixtureBudget:
        def check(self, stage, **kwargs):
            events.append((stage, kwargs.copy()))
            if enforce_lifetime and stage == 'fold_split' and kwargs.get('phase') == 'enter':
                assert registry['whole_rows']() is None, 'whole eligible rows survived into fold split'
                assert all(ref() is None for pair in registry['split_refs'] for ref in pair), 'previous train/test survived'
                assert all(ref() is None for ref in registry['model_refs']), 'previous model survived'

    proxy = SimpleNamespace(FEATURES=N.xr.FEATURES, LGB_PARAMS=dict(N.xr.LGB_PARAMS),
                            MIN_TRAIN_ROWS=2, make_folds=N.xr.make_folds)
    namespace = {**vars(N), 'xr': proxy, 'fold_rows': split}
    assert namespace['read_prices'] is N.read_prices and namespace['PRICE_SOURCES'] == {}
    assert namespace['registrant_metadata'] is N.registrant_metadata
    if frozen:
        exec(compile(fold_reference_tree(), 'frozen_f62_fit_oos_only', 'exec'), namespace)
        function = namespace['fit_oos']
    else:
        # Execute exactly the current function bytecode with isolated fixture
        # globals; never replace current module functions or compile a producer.
        function = FunctionType(N.fit_oos.__code__, namespace, N.fit_oos.__name__, N.fit_oos.__defaults__)
    assert function.__globals__['fold_rows'] is split
    assert function.__globals__['read_prices'] is N.read_prices
    assert function.__globals__['PRICE_SOURCES'] == {}
    try:
        oos, ledger = function(panel, FixtureBudget())
    except N.NumericalRefused as exc:
        assert str(exc) == 'all four chronological folds refused'
        oos, ledger = None, exc.evidence['folds']
    pd.testing.assert_frame_equal(pd.DataFrame(panel), snapshot, check_exact=True)
    return oos, ledger, events, fitted_parameters, registry


@pytest.mark.parametrize('refused', [(), (1,), (0, 1, 2, 3)])
def test_fold_lifetime_exact_frozen_oos_ledger_and_budget_event_equivalence(monkeypatch, refused):
    original_functions = (N.fit_oos, N.fold_rows, N.read_prices, N.registrant_metadata)
    old = run_fold_fixture(monkeypatch, frozen=True, refused=refused)
    new = run_fold_fixture(monkeypatch, frozen=False, refused=refused)
    if old[0] is None:
        assert new[0] is None
    else:
        pd.testing.assert_frame_equal(old[0], new[0], check_exact=True, check_dtype=True, check_like=False)
    assert old[1:4] == new[1:4]
    assert original_functions == (N.fit_oos, N.fold_rows, N.read_prices, N.registrant_metadata)


@pytest.mark.parametrize('refused', [(), (1,), (0, 1, 2, 3)])
def test_dead_fold_inputs_models_and_refused_frames_released_before_next_split(monkeypatch, refused):
    result = run_fold_fixture(monkeypatch, frozen=False, refused=refused, enforce_lifetime=True)
    registry = result[4]
    assert registry['whole_rows']() is None
    assert all(ref() is None for pair in registry['split_refs'] for ref in pair)
    assert all(ref() is None for ref in registry['model_refs'])


def test_fold_lifetime_source_changes_only_dead_deletes_and_eager_fold_binding():
    from copy import deepcopy
    current = ast.parse(inspect.getsource(N.fit_oos)).body[0]
    normalized = deepcopy(current)
    fold_binding = next(node for node in normalized.body if isinstance(node, ast.Assign)
                        and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'folds')
    loop = next(node for node in normalized.body if isinstance(node, ast.For))
    assert isinstance(loop.iter, ast.Name) and loop.iter.id == 'folds'
    loop.iter = fold_binding.value
    deletes = [[target.id for target in node.targets] for node in ast.walk(normalized) if isinstance(node, ast.Delete)]
    assert sorted(deletes) == sorted([['rows'], ['train', 'test'], ['train', 'test', 'model']])
    class StripLifetimeOnly(ast.NodeTransformer):
        def visit_Delete(self, node):
            return None
    normalized = StripLifetimeOnly().visit(normalized)
    normalized.body.remove(fold_binding)
    assert ast.dump(normalized, include_attributes=False) == ast.dump(fold_reference_tree().body[0], include_attributes=False)
FOLD_REFERENCE_SOURCE = 'def fit_oos(panel, budget):\n    import lightgbm as lgb\n\n    specification()\n    rows = panel.loc[panel["eligible"] & panel["y"].notna()]\n    predictions, ledger = [], []\n    for train_end, start, end in xr.make_folds(rows["date"].values, n_folds=4, min_train_frac=.45):\n        budget.check("before fold")\n        budget.check("fold_split", phase="enter")\n        train, test, receipt = fold_rows(panel, train_end, start, end)\n        budget.check("fold_split", rows=len(train)+len(test), phase="complete")\n        if len(train) < xr.MIN_TRAIN_ROWS or test.empty:\n            ledger.append({**receipt, "status": "REFUSED", "reason": "unchanged minimum train rows or empty test"})\n            continue\n        model = lgb.LGBMRegressor(**xr.LGB_PARAMS, n_jobs=2)\n        budget.check("fold_fit", rows=len(train), phase="enter")\n        model.fit(train[list(xr.FEATURES)], train["y"])\n        budget.check("fold_fit", rows=len(train), phase="complete")\n        budget.check("after fold fit")\n        prediction = test[["symbol", "date", "y", "fwd_rel", "fwd_ret", "bench_fwd_ret", "median_dollar_vol",\n            "close", "formation_at", "label_start_at", "label_end_at"]].copy()\n        budget.check("fold_predict", rows=len(test), phase="enter")\n        prediction["score"] = model.predict(test[list(xr.FEATURES)])\n        budget.check("fold_predict", rows=len(test), phase="complete")\n        prediction["fold_train_end"] = train_end\n        predictions.append(prediction)\n        ledger.append({**receipt, "status": "FITTED", "model_serialized_sha256": model_hash(model)})\n    if not predictions:\n        raise NumericalRefused("all four chronological folds refused", evidence={"folds": ledger})\n    oos = pd.concat(predictions, ignore_index=True)\n    oos["score_pct"] = oos.groupby("date")["score"].rank(pct=True, method="average")\n    oos["decile"] = np.clip((oos["score_pct"]*10).astype(int), 0, 9)\n    return oos, ledger'
