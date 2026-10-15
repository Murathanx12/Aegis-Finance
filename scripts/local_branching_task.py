"""Stdlib-only native owner for the private 2026-10-14 product cohort.

The heavy grade worker reads one authorization byte only after this owner has
checked STOP, source pins, IIF margin, and bound its own Windows Job.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
from pathlib import Path

_OS_KEYS = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE",
            "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "COMSPEC", "PATHEXT",
            "USERNAME", "USERDOMAIN", "PROCESSOR_ARCHITECTURE", "HOMEDRIVE",
            "HOMEPATH", "PYTHONHOME", "VIRTUAL_ENV"}
for _key in tuple(os.environ):
    if _key.upper() not in _OS_KEYS:
        os.environ.pop(_key, None)
os.environ.update(AEGIS_IGNORE_DOTENV="1", OMP_NUM_THREADS="1",
                  OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")

TASK = "AegisLocalBranchingPrivateGrade"
OUT = Path.home() / "aegis-recovery-evidence" / "oct14-continuation-20261014" / "local-branching"
COHORT = OUT / "2026-10-14"
RUNS = OUT / "automation_runs.jsonl"
STOP_FILES = (OUT / "AUTOMATION_STOP", Path.home() / "aegis-finance" / "STOP",
              Path.home() / "aegis-recovery-evidence" / "beta-through-monday" / "STOP")
LEDGER_SHA = "77c97204549fe819e52b623be6b744220c8e7fd2ffe46350ac9c7e4b9b31bdba"
RECEIPT_SHA = "0fb53e80c1d6be0a4e25519d54ddbc3e88bea0396ac46397292fdfa7df92fa96"
SGT = timezone(timedelta(hours=8))
AGGREGATE_MEMORY_LIMIT = 512 * 1024 ** 2
OWNER_RESERVE = 32 * 1024 ** 2
CHILD_WALL_SECONDS = 180
CHILD_OUTPUT_LIMIT = 64 * 1024


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def free_ram_bytes() -> int:
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_uint64), ("ullAvailPhys", ctypes.c_uint64),
                    ("ullTotalPageFile", ctypes.c_uint64), ("ullAvailPageFile", ctypes.c_uint64),
                    ("ullTotalVirtual", ctypes.c_uint64), ("ullAvailVirtual", ctypes.c_uint64),
                    ("ullAvailExtendedVirtual", ctypes.c_uint64)]
    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("GlobalMemoryStatusEx failed")
    return int(status.ullAvailPhys)


def protected_window(now_utc: datetime) -> bool:
    local = now_utc.astimezone(SGT)
    return (16, 40) <= (local.hour, local.minute) < (17, 5)


def stop_reason() -> str | None:
    return next((str(p) for p in STOP_FILES if p.exists()), None)


def preflight(now_utc: datetime, *, task_sha: str, grade_sha: str,
              child_sha: str, source_commit: str) -> dict:
    if now_utc.tzinfo is None:
        raise ValueError("preflight requires an aware UTC clock")
    stop = stop_reason()
    if stop:
        return {"action": "STOP", "reason": stop}
    if protected_window(now_utc):
        return {"action": "YIELD_IIF_WINDOW", "singapore_time": now_utc.astimezone(SGT).isoformat()}
    available = free_ram_bytes()
    scripts = Path(__file__).resolve().parent
    for file, expected in ((scripts / "local_branching_task.py", task_sha),
                           (scripts / "local_branching.py", grade_sha),
                           (scripts / "local_branching_grade_child.py", child_sha),
                           (COHORT / "books.jsonl", LEDGER_SHA),
                           (COHORT / "freeze_receipt.json", RECEIPT_SHA)):
        if digest(file) != expected:
            raise ValueError(f"reviewed source or frozen input pin differs: {file.name}")
    root = scripts.parent
    bindings_path = root / "docs/TRIALS/POPULATION-1000-SOURCES.json"
    if digest(bindings_path) != "99ded27f15e34517e1eefe29b57a5995d5a1fb3a2cc049cb7d74ec99aa3c7f64":
        raise ValueError("population source binding differs")
    population_files = json.loads(bindings_path.read_bytes())["files"]
    for relative, expected in population_files.items():
        candidate = (root / relative).resolve()
        if root.resolve() not in candidate.parents or candidate.is_symlink() or hashlib.sha256(candidate.read_bytes().replace(b'\r\n', b'\n')).hexdigest() != expected:
            raise ValueError("population source dependency differs")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
                          text=True, timeout=5, check=True).stdout.strip()
    if head != source_commit:
        raise ValueError("isolated worktree commit differs from reviewed commit")
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/local_branching_task.py",
                            "scripts/local_branching.py", "scripts/local_branching_grade_child.py",
                            "scripts/beta_v1_news_capture.py", "docs/TRIALS/POPULATION-1000-SOURCES.json", *population_files],
                           cwd=root, capture_output=True, text=True, timeout=5, check=True)
    if dirty.stdout.strip():
        raise ValueError("reviewed source files are dirty")
    return {"action": "READY", "source_commit": head, "task_sha256": task_sha,
            "grade_sha256": grade_sha, "child_sha256": child_sha,
            "ledger_sha256": LEDGER_SHA, "freeze_receipt_sha256": RECEIPT_SHA,
            "free_ram_bytes": available}


def bind_child_job(pid: int, memory_limit: int):
    """Same kernel kill-on-close pattern as llama_server.bind_lifetime."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.AssignProcessToJobObject.restype = wintypes.BOOL
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k32.SetInformationJobObject.restype = wintypes.BOOL
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    k32.QueryInformationJobObject.restype = wintypes.BOOL
    k32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID,
                                             wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    class Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
                    ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class Io(ctypes.Structure):
        _fields_ = [("ReadOperationCount", ctypes.c_uint64), ("WriteOperationCount", ctypes.c_uint64),
                    ("OtherOperationCount", ctypes.c_uint64), ("ReadTransferCount", ctypes.c_uint64),
                    ("WriteTransferCount", ctypes.c_uint64), ("OtherTransferCount", ctypes.c_uint64)]

    class Extended(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", Io),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    job = k32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(f"CreateJobObject failed: {ctypes.get_last_error()}")
    try:
        info = Extended()
        info.BasicLimitInformation.LimitFlags = 0x2000 | 0x200  # KILL_ON_JOB_CLOSE | JOB_MEMORY
        info.JobMemoryLimit = memory_limit
        if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise OSError(f"SetInformationJobObject failed: {ctypes.get_last_error()}")
        process = k32.OpenProcess(0x0100 | 0x0001, False, pid)  # SET_QUOTA | TERMINATE
        if not process:
            raise OSError(f"OpenProcess({pid}) failed: {ctypes.get_last_error()}")
        try:
            if not k32.AssignProcessToJobObject(job, process):
                raise OSError(f"AssignProcessToJobObject({pid}) failed: {ctypes.get_last_error()}")
        finally:
            k32.CloseHandle(process)
        return k32, job, Extended
    except BaseException:
        k32.CloseHandle(job)
        raise


def job_memory_cap(owner_peak: int) -> int:
    cap = AGGREGATE_MEMORY_LIMIT - owner_peak - OWNER_RESERVE
    if cap <= 0:
        raise RuntimeError("512 MiB combined owner/child budget unavailable")
    return cap


def job_peak_bytes(k32, job, info_type) -> int:
    info = info_type()
    if not k32.QueryInformationJobObject(job, 9, ctypes.byref(info),
                                         ctypes.sizeof(info), None):
        raise OSError(f"QueryInformationJobObject failed: {ctypes.get_last_error()}")
    return int(info.PeakJobMemoryUsed)


def run_child() -> dict:
    # The existing stdlib-only process meter is loaded only after main preflight.
    from scripts.beta_v1_news_capture import memory as owned_memory, owner_handle

    scripts = Path(__file__).resolve().parent
    log_path = OUT / f"child_{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.log"
    OUT.mkdir(parents=True, exist_ok=True)
    p = None
    job = None
    _, owner_peak_before = owned_memory(owner_handle())
    job_limit = job_memory_cap(owner_peak_before)
    owner_peak_seen = owner_peak_before
    child_peak_seen = 0
    job_peak_seen = 0
    try:
        with log_path.open("xb") as log:
            p = subprocess.Popen([sys.executable, "-m", "scripts.local_branching_grade_child"],
                                 cwd=scripts.parent, env=dict(os.environ), stdin=subprocess.PIPE,
                                 stdout=log, stderr=subprocess.STDOUT,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                 close_fds=True)
            k32, job, job_info_type = bind_child_job(p.pid, job_limit)
            p.stdin.write(b"G")
            p.stdin.close()
            deadline = time.monotonic() + CHILD_WALL_SECONDS
            while p.poll() is None:
                _, owner_peak = owned_memory(owner_handle())
                _, child_peak = owned_memory(p._handle)
                owner_peak_seen = max(owner_peak_seen, owner_peak)
                child_peak_seen = max(child_peak_seen, child_peak)
                job_peak_seen = max(job_peak_seen, job_peak_bytes(k32, job, job_info_type))
                if owner_peak_seen + max(child_peak_seen, job_peak_seen) >= AGGREGATE_MEMORY_LIMIT:
                    raise RuntimeError("512 MiB combined owner/child budget exceeded")
                if log_path.stat().st_size > CHILD_OUTPUT_LIMIT:
                    raise RuntimeError("owned child output limit exceeded")
                if time.monotonic() >= deadline:
                    raise TimeoutError("owned child wall limit exceeded")
                stop = stop_reason()
                if stop or protected_window(datetime.now(timezone.utc)):
                    raise RuntimeError(f"owned child interrupted by STOP/IIF: {stop or 'IIF window'}")
                time.sleep(0.25)
        raw = log_path.read_bytes()
        _, owner_peak = owned_memory(owner_handle())
        _, child_peak = owned_memory(p._handle)
        owner_peak_seen = max(owner_peak_seen, owner_peak)
        child_peak_seen = max(child_peak_seen, child_peak)
        job_peak_seen = max(job_peak_seen, job_peak_bytes(k32, job, job_info_type))
        if owner_peak_seen + max(child_peak_seen, job_peak_seen) >= AGGREGATE_MEMORY_LIMIT:
            raise RuntimeError("512 MiB combined owner/child budget exceeded")
        if len(raw) > CHILD_OUTPUT_LIMIT:
            raise RuntimeError("owned child output limit exceeded")
        if p.returncode:
            raise RuntimeError(f"owned child exited {p.returncode}: {raw[-2000:].decode(errors='replace')}")
        result = json.loads(raw.decode("utf-8"))
        if result.get("action") not in {"WAIT_ENTRY", "WAIT_SHARED_REFRESH",
                                        "WAIT_CONSTITUENT_MARKS", "ALREADY_GRADED", "GRADED"}:
            raise ValueError("owned child returned an unknown action")
        log_path.unlink()
        return {"child_pid": p.pid, **result,
                "resource_proof": {"aggregate_limit_bytes": AGGREGATE_MEMORY_LIMIT,
                                   "job_memory_limit_bytes": job_limit,
                                   "owner_peak_bytes": owner_peak_seen,
                                   "child_peak_bytes": child_peak_seen,
                                   "job_peak_memory_bytes": job_peak_seen,
                                   "aggregate_peak_upper_bound": owner_peak_seen + max(child_peak_seen, job_peak_seen),
                                   "child_reaped": p.poll() is not None}}
    except BaseException:
        if p is not None and p.poll() is None:
            p.kill()  # exact owned PID; job close also kills any descendants
            p.wait(timeout=10)
        raise
    finally:
        if job is not None:
            k32.CloseHandle(job)


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("source_commit", "task_sha", "grade_sha", "child_sha"):
        parser.add_argument("--" + name.replace("_", "-"), required=True)
    args = parser.parse_args()
    row = {"task": TASK, "utc": datetime.now(timezone.utc).isoformat()}
    try:
        row.update(preflight(datetime.now(timezone.utc), task_sha=args.task_sha,
                             grade_sha=args.grade_sha, child_sha=args.child_sha,
                             source_commit=args.source_commit))
        if row["action"] == "READY":
            row.update(run_child())
    except BaseException as exc:
        row.update(action="REFUSED", reason=f"{type(exc).__name__}: {exc}",
                   traceback=traceback.format_exc(limit=3))
    RUNS.parent.mkdir(parents=True, exist_ok=True)
    with RUNS.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, default=str) + "\n")
    return 1 if row["action"] == "REFUSED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
