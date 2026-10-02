"""The alert pass: freeze INFO alerts from SEC events, then deliver (or hold) them.

    python -m scripts.alert_pass              # one pass, in the configured mode
    python -m scripts.alert_pass --dry-run    # render + freeze, status DRY_RUN, send nothing
    python -m scripts.alert_pass --dry-run --scratch DIR
                                              # the same on a COPY of the ledger in DIR:
                                              # the real ledger is not touched, so a
                                              # rehearsal does not close today's alerts
    python -m scripts.alert_pass --schtasks   # print the AegisAlerts registration; runs nothing
    python -m scripts.alert_pass --status     # the ledger's counts; runs nothing

Run every 30 minutes by the `AegisAlerts` Windows scheduled task under the venv's
`pythonw.exe` (windowless: stdout/stderr are None there, so this script writes
its own log, `alerts/alert_pass.log`, and the evidence is the receipt
`alerts/receipts/alert_pass_<run id>.json`, not the log).

STOP: create `backend/data/optimus/alerts/STOP` and every later pass exits at
once with a STOPPED receipt. Delete the file to resume.

MODE: `backend/config.py::ALERTS_SEND_ENABLED`. False: each alert is frozen
and closed HELD_NOT_ENABLED and the Telegram sender is never called. The owner
confirmed sending on 2026-09-28; the lane A review held it while the message
template was fixed (see the config comment for the current state). No LLM call
is made anywhere on this path.

FAILURE: a refused pass (stale candidate set, a second pass holding the lock, a
full disk) and a crashed pass both write `receipts/alert_pass_<run>.json` with
`state: REFUSED: ...` / `CRASHED: ...`: under pythonw nothing else shows it.

Every line printed goes through `telegram_bridge.redact`; the bot token and the
owner chat id are never read by this script.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                                   # noqa: E402
from backend.services import alerts as AL                            # noqa: E402

TASK_NAME = "AegisAlerts"
EVERY_MIN = 30


def _ensure_streams() -> None:
    """pythonw gives None for stdout/stderr; print() would then raise."""
    if sys.stdout is None or sys.stderr is None:
        log = AL.default_root() / "alert_pass.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        fh = open(log, "a", encoding="utf-8")                        # noqa: SIM115
        if sys.stdout is None:
            sys.stdout = fh
        if sys.stderr is None:
            sys.stderr = fh
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")          # type: ignore[union-attr]
        except Exception:                                            # noqa: BLE001
            pass


def _print(text: str) -> None:
    from backend.services.telegram_bridge import redact
    print(redact(text), flush=True)


def print_schtasks() -> int:
    """Print (never run) the registration. PowerShell, because `schtasks /Create`
    cannot set the Start-in directory `-m scripts.alert_pass` needs, and a
    `cmd /c cd ...` wrapper would flash a console window every 30 minutes."""
    py = REPO / ".venv" / "Scripts" / "pythonw.exe"
    _print("Register (PowerShell):")
    _print(f"  $a = New-ScheduledTaskAction -Execute '{py}' -Argument '-m scripts.alert_pass' "
           f"-WorkingDirectory '{REPO}'")
    _print(f"  $t = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) "
           f"-RepetitionInterval (New-TimeSpan -Minutes {EVERY_MIN})")
    _print("  $s = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew "
           "-ExecutionTimeLimit (New-TimeSpan -Minutes 20)")
    _print(f"  Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $a -Trigger $t -Settings $s")
    _print(f'Remove:  schtasks /Delete /TN "{TASK_NAME}" /F')
    _print(f"Pause without removing: create {AL.stop_file()}")
    return 0


def status() -> int:
    rows = AL.read_ledger()
    st = AL.send_state(rows)
    _print(json.dumps({"frozen": len(AL.frozen_alerts(rows)),
                       "followups": sum(r.get("kind") == "FOLLOWUP" for r in rows),
                       "latest_status": dict(Counter(s["status"] for s in st.values())),
                       "send_enabled": bool(_cfg.ALERTS_SEND_ENABLED),
                       "stop_file": AL.stop_file().exists()}, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    _ensure_streams()
    ap = argparse.ArgumentParser(prog="alert_pass")
    ap.add_argument("--dry-run", action="store_true",
                    help="render and freeze with status DRY_RUN; never send")
    ap.add_argument("--schtasks", action="store_true", help="print the task registration")
    ap.add_argument("--status", action="store_true", help="ledger counts only")
    ap.add_argument("--scratch", default=None,
                    help="with --dry-run: copy the ledger into this directory and run there")
    a = ap.parse_args(argv)
    if a.schtasks:
        return print_schtasks()
    if a.status:
        return status()
    root = None
    if a.scratch:
        if not a.dry_run:
            _print("REFUSED: --scratch is a rehearsal and needs --dry-run")
            return 2
        import shutil
        root = Path(a.scratch).resolve()
        if root == AL.default_root().resolve():
            _print("REFUSED: --scratch must not be the real alerts directory")
            return 2
        root.mkdir(parents=True, exist_ok=True)
        if AL.ledger_path().exists():
            shutil.copyfile(AL.ledger_path(), AL.ledger_path(root))
    from backend.services import disk_guard as DG
    try:
        DG.require_free(_cfg.DISK_FREE_DEAD_GB + 1, "alert_pass", path=_cfg.OPTIMUS_LEDGER_DIR)
    except DG.DiskTooFull as exc:
        _print(f"REFUSED: {exc}")
        AL.write_failure_receipt(str(exc), root=root)
        return 2
    try:
        r = AL.run_pass(dry_run=a.dry_run, root=root)
    except AL.AlertRefused as exc:
        _print(f"REFUSED: {exc}")
        AL.write_failure_receipt(str(exc), root=root)
        return 2
    except Exception as exc:                                         # noqa: BLE001
        import traceback
        tb = traceback.format_exc()
        _print(tb)
        AL.write_failure_receipt(f"{type(exc).__name__}: {exc} | {tb[-1500:]}", root=root,
                                 state="CRASHED")
        return 1
    if str(r.get("state", "")).startswith("STOPPED"):
        _print(r["state"])
        return 0
    u = r["universe"]
    if (r.get("bars_health") or {}).get("state") == "DEGRADED":
        _print("!! " + r["bars_health"]["line"])
    _print(f"alert pass {r['run_id']}  mode {r['mode']}  llm spend ${r['llm_spend_usd']:.2f}")
    _print(f"universe: {u['n']} tickers ({u['n_funnel']} funnel + {u['n_book_tickers']} book "
           f"names over {u['n_books']} books); funnel age {u['funnel_age_days']} d "
           f"(limit {u['funnel_stale_limit_days']} d), generated {u['funnel_generated_at']}")
    for k, s in (r.get("sources") or {}).items():
        _print(f"source {k}: {json.dumps(s, default=str)}")
    _print(f"events {r['n_events']}  freeze {json.dumps(r['freeze'])}")
    _print(f"n_alert_dates_graded {r['n_alert_dates_graded']}  distance to "
           f"{_cfg.ALERT_MIN_GRADED_DATES}: {r['distance_to_100']}  "
           f"(grading: {r['grading'].get('state')})")
    _print(f"kill rule: {r['kill_rule']['mode']} -- {r['kill_rule']['why']}")
    _print(f"delivery: {json.dumps(r['delivery'])}")
    _print(f"state: {r.get('state')}")
    for m in r.get("messages", [])[: (None if root else 1)]:
        _print("---- rendered message ----\n" + m)
    _print(f"receipt -> {r.get('receipt_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
