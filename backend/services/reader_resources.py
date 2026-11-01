"""Read-only Windows resource samples and pure admission/throughput projections.

No process control, browser, model or settings write. Pagefile fields retain
their Windows reported meaning; reserves are protective heuristics, not measured
renderer costs or a target to consume all physical memory.
"""
import math
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

GIB = 1024**3

def _native_memory_cpu():
    if sys.platform != 'win32':
        raise OSError('WINDOWS_RESOURCE_PROBE_REQUIRED')
    import ctypes
    class Memory(ctypes.Structure):
        _fields_=[('length',ctypes.c_uint32),('load',ctypes.c_uint32),
                  *[(n,ctypes.c_uint64) for n in ('total_phys','avail_phys','total_pagefile',
                       'avail_pagefile','total_virtual','avail_virtual','avail_extended')]]
    class FileTime(ctypes.Structure):
        _fields_=[('low',ctypes.c_uint32),('high',ctypes.c_uint32)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    memory=Memory();memory.length=ctypes.sizeof(memory)
    memory_call=kernel.GlobalMemoryStatusEx
    memory_call.argtypes=[ctypes.POINTER(Memory)];memory_call.restype=ctypes.c_int
    cpu_call=kernel.GetSystemTimes
    cpu_call.argtypes=[ctypes.POINTER(FileTime)]*3;cpu_call.restype=ctypes.c_int
    idle,kern,user=FileTime(),FileTime(),FileTime()
    if not memory_call(ctypes.byref(memory)) or not cpu_call(ctypes.byref(idle),ctypes.byref(kern),ctypes.byref(user)):
        raise OSError('RESOURCE_SAMPLE_UNAVAILABLE')
    ticks=lambda t:(t.high<<32)|t.low
    return {'physical_total_bytes':int(memory.total_phys),'physical_available_bytes':int(memory.avail_phys),
            'pagefile_total_bytes':int(memory.total_pagefile),'pagefile_available_bytes':int(memory.avail_pagefile),
            'idle_ticks':ticks(idle),'kernel_ticks':ticks(kern),'user_ticks':ticks(user)}

class ResourceSampler:
    def __init__(self, *, read_fn=None, clock=time.monotonic, period_s=2.0):
        self.read=read_fn or _native_memory_cpu;self.clock=clock;self.period=period_s
        self.previous=None;self.last=None;self.sequence=0;self.lock=threading.RLock()

    def sample(self):
        with self.lock:
            now=self.clock()
            if self.last and 0 <= now-self.last['observed_monotonic'] < self.period:
                return dict(self.last)
            self.sequence+=1
            base={'sequence':self.sequence,'observed_monotonic':now}
            try:
                row=self.read();cpu=None
                if self.previous:
                    idle=row['idle_ticks']-self.previous['idle_ticks']
                    total=row['kernel_ticks']-self.previous['kernel_ticks']+row['user_ticks']-self.previous['user_ticks']
                    if total>0 and 0 <= idle <= total:cpu=100.0*(1.0-idle/total)
                self.previous=row
                self.last={**base,**{k:row[k] for k in ('physical_total_bytes','physical_available_bytes',
                    'pagefile_total_bytes','pagefile_available_bytes')},'cpu_busy_percent':cpu,
                    'status':'OK' if cpu is not None else 'CPU_WARMUP_UNKNOWN'}
            except (OSError,ValueError,KeyError,TypeError):
                self.previous=None;self.last={**base,'status':'RESOURCE_UNKNOWN','cpu_busy_percent':None}
            return dict(self.last)

def resource_verdict(row, *, now, in_flight=0, actually_open=0, recent_admissions=0, estimated_tab_gib=0.5,
                     min_commit_gib=1.0, commit_fraction=0.05,
                     min_physical_gib=0.5, physical_fraction=0.01,
                     grow_cpu=75.0, hold_cpu=90.0):
    denied={'ok':False,'can_grow':False,'reason':'RESOURCE_UNKNOWN'}
    try:
        fields=('physical_total_bytes','physical_available_bytes','pagefile_total_bytes','pagefile_available_bytes')
        if row.get('status')!='OK' or any(type(row.get(k)) is not int for k in fields):return denied
        cpu=row['cpu_busy_percent'];age=now-row['observed_monotonic']
        if type(cpu) not in (int,float) or not math.isfinite(cpu) or not 0<=cpu<=100 or not 0<=age<=10:return denied
        physical,free,limit,available=(row[k] for k in fields)
        if not (physical>0 and limit>0 and 0<=free<=physical and 0<=available<=limit):return denied
        if any(type(n) is not int or n<0 for n in (in_flight,actually_open,recent_admissions)):return denied
        if not (0<estimated_tab_gib<=4 and 0<commit_fraction<0.5 and 0<physical_fraction<0.5
                and min_commit_gib>0 and min_physical_gib>0 and 0<grow_cpu<hold_cpu<100):return denied
        commit_reserve=max(min_commit_gib*GIB,limit*commit_fraction)
        physical_reserve=max(min_physical_gib*GIB,physical*physical_fraction)
        # Opened since a cached sample may not yet appear in its headroom.
        pending=max(0,in_flight-actually_open,recent_admissions)+1
        needed=commit_reserve+pending*estimated_tab_gib*GIB
        reason=('CPU_PRESSURE' if cpu>=hold_cpu else 'PHYSICAL_HEADROOM' if free<=physical_reserve
                else 'COMMIT_HEADROOM' if available<=needed else 'READY')
        return {'ok':reason=='READY','can_grow':reason=='READY' and cpu<=grow_cpu,'reason':reason,
                'commit_reserve_bytes':int(commit_reserve),'physical_reserve_bytes':int(physical_reserve),
                'next_admission_commit_requirement_bytes':int(needed),
                'pending_slot_estimate':pending,'cost_basis':'PROTECTIVE_ESTIMATE_NOT_MEASURED_RENDERER_COST'}
    except (KeyError,TypeError,ValueError):return denied

def throughput_window(timings, *, now, started, window_s=300):
    """Actual completed events in an observed window, never a speedup forecast."""
    lower=max(started,now-timedelta(seconds=window_s));seconds=max(0.0,(now-lower).total_seconds())
    rows=[];invalid=0
    for row in timings:
        try:
            stamp=datetime.fromisoformat(row['at'])
            if stamp.tzinfo is None or stamp>now:raise ValueError('CLOCK')
            if stamp>=lower:rows.append(row)
        except (ValueError,TypeError,KeyError):invalid+=1
    outcomes={}
    for row in rows:
        kind=str(row.get('outcome','UNKNOWN'))
        kind=kind if re.fullmatch('[A-Z_]{1,64}',kind) else 'OTHER'
        outcomes[kind]=outcomes.get(kind,0)+1
    def percentile(field, fraction):
        values=sorted(float(r[field]) for r in rows if type(r.get(field)) in (int,float)
                      and math.isfinite(r[field]) and r[field]>=0)
        return values[max(0,math.ceil(len(values)*fraction)-1)] if values else None
    ok=outcomes.get('OK',0)
    return {'observed_start_utc':lower.isoformat(),'observed_end_utc':now.isoformat(),
            'observed_seconds':seconds,'completed_pages':len(rows),'successful_pages':ok,
            'retained_timing_rows':len(timings),
            'history_at_retention_limit':len(timings)>=2000,
            'outcome_counts':outcomes,'invalid_or_future_clock_rows':invalid,
            'normalized_successful_per_hour':ok*3600/seconds if seconds else None,
            'p50_work_s':percentile('work_s',0.5),'p95_work_s':percentile('work_s',0.95),
            'p95_open_s':percentile('open_s',0.95),'p95_wait_s':percentile('wait_s',0.95),
            'qualification':'RETAINED_ACTUAL_TIMING_EVENTS; NORMALIZED_OBSERVED_RATE_NOT_SUSTAINED_SPEEDUP'}
