"""Machine-safety checks for an unattended GPU job on a shared laptop.

* refuse to start if free RAM < MIN_FREE_RAM_GB or another process holds > 20% of VRAM
* cap this process at VRAM_FRACTION of the card
* a time box counted in AWAKE seconds (monotonic clock minus detected gaps > 60 s, so a
  Modern-Standby freeze does not silently eat the box and then let the job run on)
* a STOP file (ft_lab/runs/STOP) ends a run at the next step, after a checkpoint
"""
from __future__ import annotations

import ctypes
import subprocess
import time

from ft_lab import config as C

STOP_FILE = C.RUNS / "STOP"


def free_ram_gb() -> float:
    class MEMSTAT(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MEMSTAT()
    m.dwLength = ctypes.sizeof(MEMSTAT)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 1024 ** 3


def own_ram_gb() -> float:
    """This process's working set (GB), so a log can tell our share from the machine's."""
    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    c = PMC()
    c.cb = ctypes.sizeof(PMC)
    k32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.WorkingSetSize / 1024 ** 3


def gpu_state() -> dict:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total,temperature.gpu,utilization.gpu",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=20).stdout
        used, total, temp, util = [float(x) for x in out.strip().split(",")]
        return {"used_mib": used, "total_mib": total, "temp_c": temp, "util_pct": util}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def trim_working_set() -> None:
    """Hand this process's idle pages back to Windows (EmptyWorkingSet semantics)."""
    import gc
    gc.collect()
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    k32.SetProcessWorkingSetSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t]
    k32.SetProcessWorkingSetSize(k32.GetCurrentProcess(), ctypes.c_size_t(-1), ctypes.c_size_t(-1))


def wait_for_ram(label: str, max_wait_s: float = 900, clock: "AwakeClock | None" = None,
                 floor: float | None = None) -> float:
    """Pause (not abort) while free RAM is under the floor: other agents share the machine and
    their test runs come and go. Refuse after `max_wait_s`. The pause is not counted as awake
    training time."""
    floor = C.MIN_FREE_RAM_GB if floor is None else floor
    t0 = time.monotonic()
    ram = free_ram_gb()
    if ram < floor:
        trim_working_set()
        ram = free_ram_gb()
    while ram < floor:
        if time.monotonic() - t0 > max_wait_s:
            raise SystemExit(f"REFUSED {label}: free RAM {ram:.1f} GB < {floor} for {max_wait_s:.0f}s")
        print(f"[safety] {label}: free RAM {ram:.1f} GB < {floor} (this process {own_ram_gb():.1f} GB); "
              "pausing 20 s", flush=True)
        time.sleep(20)
        trim_working_set()
        ram = free_ram_gb()
    if clock is not None:
        clock.last = time.monotonic()
    return ram


def preflight(label: str) -> dict:
    ram = wait_for_ram(label)
    g = gpu_state()
    if "used_mib" in g and g["used_mib"] > 0.2 * g["total_mib"]:
        raise SystemExit(f"REFUSED {label}: another process holds {g['used_mib']:.0f} MiB of VRAM")
    if STOP_FILE.exists():
        raise SystemExit(f"REFUSED {label}: {STOP_FILE} exists")
    return {"free_ram_gb": round(ram, 2), "gpu": g}


class AwakeClock:
    """Seconds of awake time since start: a gap > 60 s between ticks is counted as sleep."""

    def __init__(self):
        self.last = time.monotonic()
        self.awake = 0.0
        self.sleep_gaps = 0

    def tick(self) -> float:
        now = time.monotonic()
        dt = now - self.last
        self.last = now
        if dt > 60:
            self.sleep_gaps += 1
        else:
            self.awake += dt
        return self.awake
