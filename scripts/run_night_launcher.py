"""The scheduled entry point. Decides, records, and only then maybe launches.

    python -m scripts.run_night_launcher --dry-run     # decide, write nothing
    python -m scripts.run_night_launcher --rehearse    # decide, REHEARSAL receipt
    python -m scripts.run_night_launcher --acceptance  # are we accepted yet?
    python -m scripts.run_night_launcher --schtasks    # print the registration
    python -m scripts.run_night_launcher               # the real firing

WHAT THIS FILE IS AND IS NOT
============================
It is the thing a Windows scheduled task runs at 17:00 local. It is NOT where
the decision lives — that is `backend.services.night_launcher.evaluate_launch`,
which is importable and testable and recomputes everything from scratch. This
file's whole job is: evaluate, WRITE THE RECEIPT, and then hand off.

The order matters and is the point. The receipt is written BEFORE the night is
launched, not after it returns, because a night that crashes the machine still
has to leave evidence that the launcher woke up and decided to run it. A receipt
written only on success reports exactly the cases that did not need reporting.

EXACTLY ONE NIGHT-LEVEL ATTEMPT
===============================
There is no retry, no backoff and no "it refused, try again in an hour". A
refusal is a finding and the night is over. Compensating for a refusal with an
unregistered second attempt is how a campaign quietly buys nights nobody
reserved, and it would be invisible in the record because both attempts look
like one night.

ARMING IS ATTENDED
==================
A real launch requires `AEGIS_IIF1_LAUNCHER_ARMED=1` in the environment. The
session that writes this file cannot arm it; Murat can. `--rehearse` and
`--dry-run` never consult it, which is what makes a rehearsal a safe thing to
run at any hour.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from backend.services import night_launcher as L

logger = logging.getLogger(__name__)


def _utf8() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                          # noqa: BLE001
            pass


def _local(dt_utc: datetime) -> str:
    off = datetime.now().astimezone().utcoffset() or timedelta(0)
    return (dt_utc + off).strftime("%H:%M")


def print_report(rep: dict) -> None:
    d = rep["derived"]
    print("=" * 74)
    print(f"NIGHT LAUNCHER — {rep['trial']}")
    print("=" * 74)
    print(f"  evaluated     {rep['evaluated_at_utc']}  "
          f"(local {_local(datetime.fromisoformat(rep['evaluated_at_utc']))})")
    print(f"  session       {rep['session_date']}   open "
          f"{d['next_open_utc']}  ({d['hours_until_open']:.1f}h away)")
    print()
    print(f"  run needs     {d['decision_minutes']:.0f} min   "
          f"[{d['decision_basis']}]")
    a = d["assembly_allowance"]
    print(f"  assembly      {a['value']:.0f} min   [{a['basis']}"
          + (f", worst measured {a['worst_minutes']:.1f} min over "
             f"{a['n_nights']} night(s), cap {a['cap']:.0f}]"
             if a.get("worst_minutes") is not None else f", cap {a['cap']:.0f}]"))
    print()
    lrs = datetime.fromisoformat(d["latest_safe_run_start_utc"])
    lsl = datetime.fromisoformat(d["latest_safe_launch_utc"])
    print(f"  latest safe RUN START   {d['latest_safe_run_start_utc']}  "
          f"local {_local(lrs)}")
    print(f"  latest safe LAUNCH      {d['latest_safe_launch_utc']}  "
          f"local {_local(lsl)}   <- THE ONE THAT BINDS A LAUNCHER")
    print(f"  margin now              {d['launch_margin_minutes']:+.1f} min")
    print("  (the two differ by the assembly allowance: the run's own guard is")
    print("   reached only AFTER the snapshot is built, so a launcher that")
    print("   fires at the run-start boundary is refused by the time it gets")
    print("   there. Do not quote a remembered clock time for either.)")
    print()
    print(f"  attempts on record      {d['nights_attempted']} night(s)")
    print(f"  accrual                 {d['graded_nights_completed']}"
          f"/{d['graded_nights_required']} graded nights")
    print(f"  frozen prereg           {d['prereg_fields_verified']} fields verified")
    print()
    if rep["may_launch"]:
        print("  VERDICT       READY TO LAUNCH")
    else:
        print(f"  VERDICT       REFUSED ({len(rep['refusals'])} reason(s))")
        for r in rep["refusals"]:
            print(f"    [{r['code']}]")
            for line in _wrap(r["detail"], 66):
                print(f"        {line}")


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def print_acceptance(acc: dict) -> None:
    print("=" * 74)
    print("LAUNCHER ACCEPTANCE — receipts, never `scheduler.running`")
    print("=" * 74)
    print(f"  verdict       {acc['verdict']}")
    print(f"  consecutive   {acc['n_consecutive']}/{acc['n_required']} trading "
          f"dates  {acc['consecutive_session_dates'] or '(none)'}")
    print(f"  receipts      {acc['n_receipts_counted']} counted "
          f"/ {acc['n_receipts_total']} total")
    # Exclusions are printed, never silently subtracted. A count that shrank
    # for a reason nobody can see is the denominator failure in a new costume.
    for e in acc["excluded"]:
        print(f"    excluded  {e['session_date']}  ({e['why']})")
    print(f"  sessions checked (most recent first): "
          f"{', '.join(acc['recent_sessions_checked'])}")
    print(f"\n  {acc['note']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="run_night_launcher")
    ap.add_argument("--dry-run", action="store_true",
                    help="decide and print; write no receipt, launch nothing")
    ap.add_argument("--rehearse", action="store_true",
                    help="decide for real and write a REHEARSAL receipt; never "
                         "launches, never consults the arming flag")
    ap.add_argument("--acceptance", action="store_true",
                    help="report whether the launcher is accepted yet")
    ap.add_argument("--schtasks", action="store_true",
                    help="print the Windows registration command; runs nothing")
    ap.add_argument("--at", default=None,
                    help="evaluate as if it were this UTC time (ISO), for "
                         "rehearsing the refusal branches")
    ap.add_argument("--require-rehearsal", action="store_true",
                    help="refuse to launch unless a prior REHEARSAL receipt "
                         "pins this exact invocation (Order 16 §1). The "
                         "comparison runs and is recorded either way; this "
                         "makes it binding. Night 3+ should set it.")
    ap.add_argument("--manifest", action="store_true",
                    help="print the launch manifest and exit")
    ap.add_argument("--scheduled", action="store_true",
                    help="declare that the scheduled task invoked this. ONLY "
                         "receipts carrying it count toward acceptance — a "
                         "hand-run rehearsal proves the code path, never that "
                         "nobody had to be there. The registered command line "
                         "passes it; do not pass it by hand.")
    a = ap.parse_args(argv)
    invocation = (L.INVOCATION_SCHEDULED if a.scheduled else L.INVOCATION_MANUAL)

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    _utf8()

    if a.acceptance:
        print_acceptance(L.acceptance_report())
        return 0

    if a.manifest:
        man = L.launch_manifest()
        print(json.dumps(man, indent=2, default=str))
        prior = L.latest_rehearsal_manifest()
        if prior is None:
            print("\nno prior REHEARSAL manifest to compare against")
            return 0
        diffs = L.manifest_differences(prior, man)
        print("\nvs the last rehearsal: "
              + ("IDENTICAL invocation" if not diffs
                 else "DRIFTED —\n  " + "\n  ".join(diffs)))
        return 0 if not diffs else 1

    if a.schtasks:
        return _print_schtasks()

    now = (datetime.fromisoformat(a.at).replace(tzinfo=timezone.utc)
           if a.at else None)

    # A `LaunchRefused` here is NOT caught. It means the launcher cannot see
    # something it must check — and the one thing it must never do in that
    # state is proceed. A nonzero exit from a scheduled task is visible; a
    # swallowed exception is the silence this whole design is built against.
    rep = L.evaluate_launch(now=now, require_writable=not a.dry_run)
    print_report(rep)

    if a.dry_run:
        print("\n--dry-run: nothing written, nothing launched.")
        return 0 if rep["may_launch"] else 1

    if a.rehearse:
        path = L.write_launch_receipt(
            rep, verdict=L.VERDICT_REHEARSAL, invocation=invocation,
            extra={"rehearsal": True,
                   "note": "the launcher woke, recomputed readiness and "
                           "recorded its verdict; it did not launch"})
        print(f"\nREHEARSAL receipt -> {path}")
        print("The decision above is the real one. Only the launch was skipped.")
        return 0

    if not rep["may_launch"]:
        path = L.write_launch_receipt(rep, verdict=L.VERDICT_REFUSED,
                                      invocation=invocation)
        print(f"\nREFUSED receipt -> {path}")
        print("This night is over. There is no retry: compensating for a "
              "refusal\nwith a second attempt spends error rate nobody reserved.")
        return 0                    # a refusal is a FINDING, not a task failure

    if not L.is_armed():
        rep = dict(rep)
        rep["refusals"] = [{"code": "NOT_ARMED",
                            "detail": "AEGIS_IIF1_LAUNCHER_ARMED is not 1. "
                                      "Every derived check passed; arming an "
                                      "unattended paid run is attended."}]
        rep["may_launch"] = False
        path = L.write_launch_receipt(rep, verdict=L.VERDICT_REFUSED,
                                      invocation=invocation)
        print("\nNOT ARMED — every check passed but the launcher is not armed.")
        print(f"receipt -> {path}")
        print("Arm with:  set AEGIS_IIF1_LAUNCHER_ARMED=1")
        return 0

    # ── equivalence: is this the invocation that was rehearsed? ─────────────
    # Order 16 §1. An unattended night is licensed by a rehearsal, and that
    # licence is only worth anything if the two run the same experiment — on a
    # repository where main changes all day, that is a claim about the last few
    # hours rather than a property of the code. `--require-rehearsal` makes it
    # binding; without it the comparison is still made and REPORTED, so the
    # difference is visible in the receipt either way.
    equivalence: dict = {"checked": False,
                         "why": "no prior REHEARSAL receipt carrying a manifest"}
    prior = L.latest_rehearsal_manifest()
    if prior is not None:
        try:
            equivalence = L.assert_invocation_equivalent(prior,
                                                         L.launch_manifest())
            print("\nequivalence   the live invocation matches the rehearsed one")
        except L.LaunchRefused as e:
            equivalence = {"checked": True, "equivalent": False,
                           "detail": str(e)}
            print(f"\n*** INVOCATION DRIFT since the rehearsal:\n{e}")
            if a.require_rehearsal:
                rep = dict(rep)
                rep["refusals"] = [{"code": "INVOCATION_DRIFT",
                                    "detail": str(e)}]
                rep["may_launch"] = False
                p = L.write_launch_receipt(rep, verdict=L.VERDICT_REFUSED,
                                           invocation=invocation,
                                           extra={"equivalence": equivalence})
                print(f"receipt -> {p}")
                return 0
    elif a.require_rehearsal:
        rep = dict(rep)
        rep["refusals"] = [{"code": "NO_REHEARSAL",
                            "detail": "--require-rehearsal was set and no "
                                      "REHEARSAL receipt carrying a launch "
                                      "manifest exists to pin this invocation "
                                      "against."}]
        rep["may_launch"] = False
        p = L.write_launch_receipt(rep, verdict=L.VERDICT_REFUSED,
                                   invocation=invocation,
                                   extra={"equivalence": equivalence})
        print(f"\nNO REHEARSAL to pin against.  receipt -> {p}")
        return 0

    # ── the receipt goes down BEFORE the night starts ────────────────────────
    path = L.write_launch_receipt(
        rep, verdict=L.VERDICT_LAUNCHED, invocation=invocation,
        extra={"equivalence": equivalence,
               "note": "written before the night began, so a night that dies "
                       "mid-run still proves the launcher decided to run it"})
    print(f"\nLAUNCHED receipt -> {path}")
    print("Handing off to the night. One attempt.\n")

    cmd = [sys.executable, "-m", "backend.services.iif1_run"]
    print("  " + " ".join(cmd) + "\n")
    # No pipe. `timeout N cmd | tail` reports tail's exit code while the thing
    # being checked was killed — the exit code IS the guard, and a pipeline
    # discards it.
    proc = subprocess.run(cmd, check=False)
    print(f"\nnight exited {proc.returncode}")
    return proc.returncode


def _print_schtasks() -> int:
    """Print the registration. Deliberately does not run it."""
    import os
    root = os.getcwd()
    print("=" * 74)
    print("REGISTER THE LAUNCHER — not run; registering it is a decision")
    print("=" * 74)
    print("""
Two properties before this is pasted:

  * The task time is WALL CLOCK and the opening bell is not. From
    2026-11-01 the same 17:00 fires an hour later relative to the bell.
    The launcher RE-DERIVES its window at every firing and will refuse
    rather than run into the open, so the failure mode is a lost night
    and a receipt saying why — not a contaminated one. Re-check the
    margin after each DST change anyway.

  * The task runs the LAUNCHER, which decides. It does not run a night.
    Whether a night happens is `evaluate_launch`'s verdict plus the
    arming flag, both recomputed at 17:00.

  * THE STDIN REDIRECT IS LOAD-BEARING — DO NOT DROP IT, AND DO NOT
    REDIRECT FROM `NUL`. A task registered with LogonType=Interactive
    runs inside the logged-on session WITH a console, so
    `sys.stdin.isatty()` is True and `observe_invocation` marks every
    genuine firing `contradicted`. Those receipts count for nothing and
    acceptance can never reach 3/3. The first real firing,
    2026-08-18 17:00:01, was disqualified exactly this way.

    `< NUL` WAS TRIED AND DOES NOT WORK ON WINDOWS. It was registered on
    2026-08-18 and the 2026-08-19 17:00:01 firing recorded
    `stdin_isatty: true, contradicted: true` all the same — a second
    wasted receipt. The reason is the Windows CRT: `_isatty()` returns
    true for ANY CHARACTER DEVICE, and `NUL` is a character device. So
    the redirect happens and changes nothing observable. Measured
    directly, same shell, same interpreter:

        python -c "...isatty()"                  -> True
        python -c "...isatty()" < NUL            -> True   (the trap)
        python -c "...isatty()" < empty_stdin.txt -> False

    Redirect from an EMPTY REGULAR FILE (`backend/data/optimus/
    empty_stdin.txt`, tracked and zero-length). A disk file is not a
    character device, so isatty is False and the check can do the job it
    was built for — catching a human in a terminal who typed
    `--scheduled`. Verified 2026-08-19 through `observe_invocation`
    itself, not through a proxy: `contradicted: false`.

    A pipe (`echo. | python ...`) also yields False and is NOT used: it
    would read the launcher's exit code through a pipeline, and the exit
    code IS the guard.

    RESIDUAL WEAKNESS, STATED RATHER THAN IMPLIED: a human who copies
    this registered command line verbatim now redirects stdin too, and
    so evades the check. That hole is inherent to putting the redirect in
    the registered line and was equally true of the `< NUL` intent; the
    check catches the careless terminal `--scheduled`, not a determined
    copy-paste.
""")
    print(f'  schtasks /Create /TN "AegisIIF1NightLauncher" /SC WEEKLY '
          f'/D MON,TUE,WED,THU,FRI /ST 17:00 /TR '
          f'"cmd /c cd /d {root} && '
          f'python -m scripts.run_night_launcher --scheduled < '
          f'{root}\\backend\\data\\optimus\\empty_stdin.txt >> '
          f'{root}\\backend\\data\\optimus\\launcher.log 2>&1"')
    print("\n  Already registered? Change it in place rather than "
          "re-registering:\n")
    print(f'  schtasks /Change /TN "AegisIIF1NightLauncher" /TR '
          f'"cmd /c cd /d {root} && '
          f'python -m scripts.run_night_launcher --scheduled < '
          f'{root}\\backend\\data\\optimus\\empty_stdin.txt >> '
          f'{root}\\backend\\data\\optimus\\launcher.log 2>&1"')
    print("""
  WEEKLY/MON-FRI rather than DAILY is a coarse pre-filter only. It is not
  the calendar: the launcher reads XNYS and refuses holidays itself. A
  weekday rule would happily fire on Thanksgiving; this one merely avoids
  waking the machine on Saturdays.

  The log redirect is deliberate. It is a convenience, NOT the evidence —
  the evidence is the receipt in iif1_launches/, which is written whether
  or not anything is watching stdout.
""")
    acc = L.acceptance_report()
    print(f"  current acceptance: {acc['verdict']} "
          f"({acc['n_consecutive']}/{acc['n_required']} consecutive)")
    # The diagnosis is the whole reason the third verdict exists. Computing it
    # and then printing only the count would leave the one field that says
    # WHAT TO DO unread — the write-only-telemetry shape, in the one place a
    # human is standing at the keyboard about to paste a registration.
    if acc.get("diagnosis"):
        print(f"\n  !! {acc['diagnosis']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
