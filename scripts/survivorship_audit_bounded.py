"""Private bounded equivalent of the native survivorship audit; no cache/runtime write.

Each partition contains whole symbol histories and the full SPY reference.
The existing loader performs source precedence, defect screening and stitching.
Only transformed symbol/last-date pairs survive between partitions.
"""
import argparse
from collections import Counter
from datetime import datetime,timezone
import gc
import hashlib,json,time,math,sys
from pathlib import Path

MAX_CHUNK_SYMBOLS=128
MAX_CHUNK_ROWS=250_000
MIN_FREE_GIB=2.0
RESERVE_GIB=1.0


class AuditRefused(RuntimeError):pass


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while chunk:=f.read(1<<20):h.update(chunk)
    return h.hexdigest()


def free_gib():
    if sys.platform=='win32':
        import ctypes
        class Memory(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
        m=Memory();m.length=ctypes.sizeof(m)
        return m.available/2**30 if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)) else None
    try:
        rows=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
        return int(rows['MemAvailable'].split()[0])*1024/2**30
    except (OSError,KeyError,ValueError):return None


def peak_rss_bytes():
    if sys.platform=='win32':
        import ctypes
        class Counters(ctypes.Structure):
            _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in ('peak_ws','ws','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile')]
        c=Counters();c.cb=ctypes.sizeof(c)
        return int(c.peak_ws) if ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(-1),ctypes.byref(c),c.cb) else None
    import resource
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*(1 if sys.platform=='darwin' else 1024)


def audit(paths=None,*,chunk_symbols=64,max_chunk_rows=MAX_CHUNK_ROWS,
          stop_file=None,max_seconds=180,memory_probe=free_gib):
    from backend.services import xs_ranker as XR,stitched_tickers as ST,bar_defects as BD
    from backend import config
    import pandas as pd
    import pyarrow.parquet as pq
    if not 1<=chunk_symbols<=MAX_CHUNK_SYMBOLS or not 1<=max_chunk_rows<=MAX_CHUNK_ROWS or not 0<max_seconds<=180:
        raise AuditRefused('chunk/time bounds invalid')
    start=time.monotonic();minimum=None;peak=0
    def guard(rows=0):
        nonlocal minimum,peak
        if stop_file and Path(stop_file).exists():raise AuditRefused('owner STOP')
        if time.monotonic()-start>=max_seconds:raise AuditRefused('bounded audit deadline')
        memory=memory_probe()
        if memory is None or not math.isfinite(memory) or memory<max(MIN_FREE_GIB,RESERVE_GIB+rows*448/2**30):raise AuditRefused('memory/headroom insufficient')
        minimum=memory if minimum is None else min(minimum,memory)
        measured=peak_rss_bytes()
        if measured is None:raise AuditRefused('peak memory measurement inaccessible')
        peak=max(peak,measured)
    guard()
    native_selection=paths is None
    paths=[Path(p).resolve() for p in (XR.survivorship_free_paths() if native_selection else paths)]
    if not paths or len(set(paths))!=len(paths):raise AuditRefused('missing/duplicate input paths')
    if any(not p.is_file() for p in paths):raise AuditRefused('missing bars input; never empty')
    dependencies=[Path(XR.__file__),Path(ST.__file__),Path(BD.__file__),Path(config.__file__),Path(__file__)]
    auxiliary=[ST.SEC_FACTS_PATH,ST.COMPANY_TICKERS_PATH]
    files=list(dict.fromkeys(paths+dependencies+[Path(p).resolve() for p in auxiliary if Path(p).exists()]))
    frozen={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in files}
    absent=[str(Path(p).resolve()) for p in auxiliary if not Path(p).exists()]
    def verify_selection():
        # New deep/delisted inputs can change native source precedence without
        # changing ANY already selected byte. Explicit test slices stay explicit.
        if native_selection and [Path(p).resolve() for p in XR.survivorship_free_paths()]!=paths:
            raise AuditRefused('native input selection drift')
    def verify():
        verify_selection()
        for p,pin in frozen.items():
            path=Path(p)
            if not path.is_file() or path.stat().st_size!=pin['bytes'] or sha(path)!=pin['sha256']:raise AuditRefused('input/source drift')
        if any(Path(p).exists() for p in absent):raise AuditRefused('auxiliary source appeared during audit')
        verify_selection()
    counts=Counter()
    for p in paths:
        guard();parquet=pq.ParquetFile(p)
        if not XR._BAR_COLUMNS<=set(parquet.schema.names):raise AuditRefused('malformed bars schema')
        for batch in parquet.iter_batches(batch_size=4096,columns=['symbol']):
            guard()
            for symbol in batch.column(0).to_pylist():
                if not isinstance(symbol,str) or not symbol:raise AuditRefused('malformed universe symbol')
                counts[symbol]+=1
    if not counts:raise AuditRefused('empty input universe')
    if 'SPY' not in counts:raise AuditRefused('missing SPY global reference calendar')
    # Native global transforms depend on the reference calendar. Preflight it
    # through the SAME loader, not a raw dates shortcut; later chunks include it.
    guard(counts['SPY'])
    if counts['SPY']>max_chunk_rows:raise AuditRefused('SPY reference row bound')
    reference=XR.load_bars(paths,symbols=['SPY'])
    if reference.empty or 'SPY' not in set(reference['symbol']):raise AuditRefused('empty screened SPY reference')
    spy_dates=tuple(reference.loc[reference['symbol']=='SPY','date']);reference_symbols=set(reference['symbol']);del reference;gc.collect();verify()
    groups=[];current=[];n=counts['SPY']
    for symbol in sorted(set(counts)-{'SPY'}):
        if counts[symbol]+counts['SPY']>max_chunk_rows:raise AuditRefused('single symbol exceeds row bound')
        if current and (len(current)>=chunk_symbols or n+counts[symbol]>max_chunk_rows):
            groups.append(current);current=[];n=counts['SPY']
        current.append(symbol);n+=counts[symbol]
    if current:groups.append(current)
    if not groups:groups=[[]]
    last={};seen_bases=set();transformed_rows=0
    for group in groups:
        raw_rows=sum(counts[s] for s in group)+counts['SPY'];guard(raw_rows)
        bars=XR.load_bars(paths,symbols=group+['SPY'])
        if bars.empty:raise AuditRefused('empty native transformed partition')
        if tuple(bars.loc[bars['symbol']=='SPY','date'])!=spy_dates:raise AuditRefused('SPY calendar differs across native partitions')
        allowed=set(group)|{'SPY'}
        if any(not any(s==base or str(s).startswith(base+'#') for base in allowed) for s in bars['symbol'].unique()):raise AuditRefused('unexpected transformed symbol identity')
        maxima=bars.groupby('symbol')['date'].max()
        for symbol,date in maxima.items():
            last[symbol]=max(last.get(symbol,date),date)
        transformed_rows+=int((~bars['symbol'].isin(reference_symbols)).sum());seen_bases.update(group)
        del bars,maxima;gc.collect();guard()
        # Cheap per-partition size/presence guard; complete hashes below pin all
        # bytes without re-reading200MB on every symbol chunk.
        for p,pin in frozen.items():
            if not Path(p).is_file() or Path(p).stat().st_size!=pin['bytes']:raise AuditRefused('input/source drift')
        verify_selection()
    if seen_bases!=set(counts)-{'SPY'}:raise AuditRefused('incomplete universe partition')
    compact=pd.DataFrame({'symbol':list(last),'date':list(last.values())})
    result=XR.survivorship_audit(compact);guard();verify();guard()
    return {'schema':'survivorship_audit_bounded/1','audit':result,'ran_utc':datetime.now(timezone.utc).isoformat(),
        'canonical_input_paths':[str(p) for p in paths],'native_input_selection_bound':native_selection,'input_raw_rows':sum(counts.values()),
        'input_base_symbols':len(counts),'partitions':len(groups),'chunk_symbols_bound':chunk_symbols,
        'chunk_rows_bound':max_chunk_rows,'transformed_non_SPY_rows':transformed_rows,
        'source_and_input_pins':frozen,'auxiliary_missing_named':absent,'native_default_transforms':True,
        'SPY_calendar_sessions':len(spy_dates),'SPY_counted_once':True,'elapsed_seconds':round(time.monotonic()-start,3),
        'minimum_available_gib':round(minimum,3),'process_peak_rss_gib':round(peak/2**30,3),'runtime_writes':0}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--private-result',required=True)
    ap.add_argument('--stop-file',required=True);a=ap.parse_args()
    from backend import config
    output=Path(a.private_result).resolve()
    if output.exists() or output.is_relative_to(Path(config.OPTIMUS_LEDGER_DIR).resolve()) or output.is_relative_to(Path(__file__).resolve().parents[1]):raise AuditRefused('fresh private output outside runtime/source required')
    result=audit(stop_file=a.stop_file)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8',newline='\n') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({'private_result':str(output),'panel_last_session':result['audit']['panel_last_session'],'partitions':result['partitions'],'peak_rss_gib':result['process_peak_rss_gib'],'runtime_writes':0}))


if __name__=='__main__':main()
