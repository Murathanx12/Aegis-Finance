"""The first run, in order, one GPU job at a time. Launch with Start-Process and a log:

  Start-Process ft_lab\\.venv\\Scripts\\python.exe -ArgumentList "-m","ft_lab.run_first" ...

Each stage is a subprocess; a failed stage is logged and the next independent stage still
runs (inference on the student is skipped if its adapter is missing). Create
ft_lab/runs/STOP to end at the next training step.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone

from ft_lab import config as C

PY = sys.executable
STAGES = [
    ("train_size", ["-m", "ft_lab.train_size", "--minutes", "35", "--max-train", "52000"]),
    ("train_extract", ["-m", "ft_lab.train_extract", "--minutes", "45"]),
    ("base_events", ["-m", "ft_lab.infer", "--model", "base", "--task", "events", "--set", "events_test", "--n", "1500"]),
    ("student_events", ["-m", "ft_lab.infer", "--model", "student", "--task", "events", "--set", "events_test", "--n", "1500"]),
    ("base_psych", ["-m", "ft_lab.infer", "--model", "base", "--task", "psych", "--set", "psych_test", "--n", "0"]),
    ("student_psych", ["-m", "ft_lab.infer", "--model", "student", "--task", "psych", "--set", "psych_test", "--n", "0"]),
    ("student_psych_val", ["-m", "ft_lab.infer", "--model", "student", "--task", "psych", "--set", "psych_val", "--n", "3000"]),
    ("student_psych_testall", ["-m", "ft_lab.infer", "--model", "student", "--task", "psych", "--set", "psych_testall", "--n", "6000"]),
]


def main() -> int:
    C.RUNS.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])
    status = []
    for name, args in STAGES:
        if only and name not in only:
            continue
        if (C.RUNS / "STOP").exists():
            status.append({"stage": name, "rc": None, "skipped": "STOP file"})
            break
        t0 = time.time()
        print(f"=== {name} {datetime.now(timezone.utc).isoformat(timespec='seconds')}", flush=True)
        with open(C.RUNS / f"{name}.log", "w", encoding="utf-8") as fh:
            p = subprocess.Popen([PY] + args, cwd=str(C.REPO), stdout=fh, stderr=subprocess.STDOUT)
            (C.RUNS / f"{name}.pid").write_text(str(p.pid))
            rc = p.wait()
        status.append({"stage": name, "rc": rc, "minutes": round((time.time() - t0) / 60, 1)})
        print(json.dumps(status[-1]), flush=True)
    (C.RUNS / "run_first_status.json").write_text(json.dumps(status, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

