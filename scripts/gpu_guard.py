"""ONE GPU guard, used by every job that wants the card. Not one per script.

THE MEASUREMENT THIS EXISTS FOR. N3 embedded 162,548 texts in **129.7s** on
2026-09-10 with the card free (1,252.9 texts/s) and 163,284 texts in
**40,059.4s** on 2026-09-11 (4.1 texts/s) because `llama-server` was resident
for the whole run. Same script, same encoder, same corpus to within 736 texts,
a 309x difference in wall clock, and nothing in the code noticed. Both numbers
are in those two receipts; neither run was wrong, only one was affordable.

So: a job that is about to spend GPU seconds asks first, and REFUSES rather
than running 11 hours for a 2-minute job. The refusal names the process that
holds the card, because "the GPU is busy" is not actionable and "PID 24140,
llama-server.exe, 5,861 MiB" is.

THE RULE, and its two deliberate limits:

1. The check runs ONCE, before the work starts. It is NOT a polling loop: a
   job that begins on a free card and is later joined by a contender should
   finish, not abort mid-checkpoint. Checkpointing already covers the crash
   case; aborting a half-done encode covers nothing.
2. The threshold is on OTHER processes' usage, not on the card's total. An
   encoder's own ~1-2 GB fp16 footprint must not lock out the next chunk of
   its own run, and the desktop's compositor (~300-400 MiB here) is not
   contention.

`nvidia-smi` is parsed in exactly one place for the per-process view, and the
card totals come from `backend.services.llama_server.vram()` rather than a
second text parse of the same tool -- the same "one guard, every caller uses
it" rule that the language pin follows.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: MiB another process may hold before a GPU job refuses to start. Chosen to
#: clear the encoder's own fp16 footprint plus the desktop, and to catch
#: `llama-server`, which is multi-GB at every quant this repo runs.
CONTENTION_MIB = 3072


def _compute_apps() -> list[dict]:
    """Per-process GPU memory, or [] when the query is unavailable.

    Windows reports `[Insufficient Permissions]` for processes owned by another
    user and `[N/A]` for used_memory under WDDM. Both are kept, with the memory
    as None, because "a process is on the card and we cannot size it" is a
    different fact from "no process is on the card" and the caller must be able
    to tell them apart.
    """
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        out = subprocess.run(
            [exe, "--query-compute-apps=pid,used_memory,process_name",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        try:
            mib = int(parts[1])
        except ValueError:
            mib = None
        rows.append({"pid": pid, "used_mib": mib, "name": parts[2]})
    return rows


def gpu_state(self_pid: int | None = None) -> dict:
    """What is on the card right now, and who holds it.

    Returns `available: False` when there is no NVIDIA GPU to ask -- which is
    CI, and is not contention. A caller must not read a missing GPU as a busy
    one, so the two are separate keys.
    """
    from backend.services import llama_server

    self_pid = int(self_pid if self_pid is not None else os.getpid())
    card = llama_server.vram()
    apps = _compute_apps()
    others = [a for a in apps if a["pid"] != self_pid]
    sized = [a for a in others if a["used_mib"] is not None]
    others_mib = sum(int(a["used_mib"]) for a in sized)
    unsized = [a for a in others if a["used_mib"] is None]

    llama_pid = llama_server.pid_on_port()
    for a in others:
        if llama_pid and a["pid"] == llama_pid:
            a["is_llama_server"] = True

    return {
        "available": card is not None,
        "card": card,
        "self_pid": self_pid,
        "processes_other_than_self": others,
        "other_process_mib_measured": others_mib,
        "other_processes_unmeasurable": len(unsized),
        "llama_server_pid_on_port": llama_pid,
        "threshold_mib": CONTENTION_MIB,
    }


def contention(self_pid: int | None = None, threshold_mib: int = CONTENTION_MIB) -> dict:
    """`{"contended": bool, "reason": str, "state": {...}}` -- never raises.

    Contended when another process' MEASURED usage clears the threshold, or --
    the case that matters on this machine -- when per-process sizes are hidden
    and the CARD's own used total clears it, since an unattributable 5.8 GB is
    still 5.8 GB we do not have. A card we cannot see at all is not contended:
    refusing on a machine with no GPU would make this guard un-greenable, which
    is the broken-gate failure mode.
    """
    st = gpu_state(self_pid)
    if not st["available"]:
        return {"contended": False, "reason": "no NVIDIA GPU visible to nvidia-smi", "state": st}

    measured = int(st["other_process_mib_measured"])
    if measured > threshold_mib:
        who = ", ".join(f"PID {a['pid']} {a['name']} {a['used_mib']} MiB"
                        for a in st["processes_other_than_self"] if a["used_mib"] is not None)
        return {"contended": True,
                "reason": f"{measured} MiB held by other processes (> {threshold_mib}): {who}",
                "state": st}

    used = int((st["card"] or {}).get("used_mib") or 0)
    if st["other_processes_unmeasurable"] and used - measured > threshold_mib:
        who = ", ".join(f"PID {a['pid']} {a['name']}"
                        for a in st["processes_other_than_self"] if a["used_mib"] is None)
        return {"contended": True,
                "reason": (f"the card reports {used} MiB used and {st['other_processes_unmeasurable']} "
                           f"process(es) hide their size ({who}); "
                           f"{used - measured} MiB is unaccounted for (> {threshold_mib})"),
                "state": st}

    return {"contended": False,
            "reason": (f"{measured} MiB held by other processes, card at {used} MiB "
                       f"(threshold {threshold_mib})"),
            "state": st}


def refuse_if_contended(job: str, self_pid: int | None = None,
                        threshold_mib: int = CONTENTION_MIB) -> dict:
    """The block a refusing receipt carries. Returns the same dict either way.

    The caller writes `status: "REFUSED_GPU_CONTENTION"` and exits non-zero on
    `contended`; the block is written on the green path too, so a receipt always
    says what the card looked like when the run started rather than only when it
    did not.
    """
    c = contention(self_pid=self_pid, threshold_mib=threshold_mib)
    return {
        "job": job,
        "checked_once_at_start": True,
        "not_a_polling_loop": ("a job that starts on a free card and is later joined by a "
                               "contender finishes; aborting mid-encode saves nothing"),
        "contended": bool(c["contended"]),
        "reason": c["reason"],
        "gpu": c["state"],
        "evidence": ("N3 2026-09-10: 162,548 texts in 129.7s with the card free; "
                     "N3 2026-09-11: 163,284 texts in 40,059.4s contending with llama-server"),
    }


def main(argv=None) -> int:
    c = contention()
    print(c["reason"])
    print("CONTENDED" if c["contended"] else "FREE")
    return 3 if c["contended"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
