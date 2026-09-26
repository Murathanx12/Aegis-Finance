"""The llama-server reaper: a standalone process that stops an idle model server.

    python scripts/llama_reaper.py                  # what ensure() spawns, detached
    python scripts/llama_reaper.py --once           # one tick, print the decision

WHY A SEPARATE PROCESS (G-fix, adjudication row 7, 2026-09-26)
==============================================================
Chunk G's idle watchdog was a daemon THREAD in whichever process started the
server. It died with that process, the job-object binding then killed the
server mid-batch for every other client, and the lab -- which calls `start()`
directly -- never armed a watchdog at all, so a lab-started server stayed
resident indefinitely. Idle-stop depended on which process happened to be alive.

This process depends on none of them. It reads the owner note the server's
starter wrote (`pid`, `started_utc`, `last_used_ts`/`last_used_utc`), and:

* stops the server BY PID once nothing has touched it for
  `MODEL_ROUTING_IDLE_MIN` (never by image name -- 2026-09-06);
* refuses a server Aegis did not start (`status()` only calls it ours when the
  note's PID is the PID holding the port, so a recycled PID is refused);
* exits as soon as the server is gone, so there is never a reaper without a
  server to reap. `llama_server.ensure()` spawns at most one (pid file).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import llama_server as LS  # noqa: E402


def _log_fn(path: Path):
    def log(row: dict) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, default=str) + "\n")
        except OSError:
            pass
    return log


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="one tick, print it, exit")
    ap.add_argument("--tick-s", type=float, default=None)
    ap.add_argument("--idle-s", type=float, default=None,
                    help="override MODEL_ROUTING_IDLE_MIN*60 (tests)")
    a = ap.parse_args(argv)
    if a.once:
        print(json.dumps(LS.reap_check(idle_s=a.idle_s), indent=1, default=str))
        return 0
    log = _log_fn(LS.OWNER_FILE.parent / "llama_reaper.log.jsonl")
    out = LS.reaper_loop(tick_s=a.tick_s, idle_s=a.idle_s, log=log)
    log({"t": LS._now(), "exit": out})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
