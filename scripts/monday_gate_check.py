"""The Monday operational gate, as ONE command instead of a prose checklist.

    python -m scripts.monday_gate_check

WHY THIS EXISTS. The gate is seven checks spread across `HANDOFF §4`, and it has
to be run at 05:45 Hong Kong time — which is the worst possible moment to be
re-deriving a checklist from prose. Every check below is mechanical; the only
judgement left is what to do about a FAIL.

IT COMPUTES THE CLOCK ITSELF, AND THAT IS THE POINT. The scheduler runs on
US/Eastern and this machine is UTC+8. A Hong Kong Monday EVENING is Eastern
Monday PRE-DAWN, so the jobs fire on the local TUESDAY:

    pi_options_pit   15:30 ET        = 03:30 HKT Tue   (INSIDE the session,
                                                      30 min before the close,
                                                      one shot, no retry)
    pi_why_moved     17:15-19:15 ET  = 05:15-07:15 HKT Tue  (after the close)
    pi_arena_daily   17:45-19:45 ET  = 05:45-07:45 HKT Tue  (after the close)

The 18:xx and 19:xx firings are idempotent catch-up retries, so the honest
deadline for "still ABSENT means a fault" is after the LAST one.

A session already got this wrong once, and the handoff's warning did not stop it
being got wrong again. So a check whose job has not had a chance to run yet
reports **PENDING**, never FAIL — reading "ABSENT" as a failure before 15:30 ET
is the same error in the other direction, and it would send somebody debugging a
collector that is working perfectly.

EXIT CODE: 0 if nothing FAILED (pending is fine), 1 if anything FAILED.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

BASE = "https://aegis-finance-production.up.railway.app"
ET = ZoneInfo("US/Eastern")
HK = ZoneInfo("Asia/Hong_Kong")

#: When each job's checks become meaningful, in ET, read off the CronTriggers in
#: `portfolio_intelligence/scheduler.py` rather than remembered.
#:
#: TWO THINGS THE FIRST VERSION GOT WRONG, both by quoting only the first fire:
#:
#: 1. `pi_why_moved` and `pi_arena_daily` are `hour="17-19"`, so each has two
#:    CATCH-UP RETRIES (18:15/19:15 and 18:45/19:45). They exist because this
#:    process restarted four times in 71 minutes on 2026-08-21, and they are
#:    idempotent no-ops once the first pass succeeds. So the honest "still
#:    ABSENT means a fault" deadline is after the LAST retry, not the first —
#:    07:45 HKT Tuesday, not 05:45. Calling a fault an hour and a half early is
#:    how somebody ends up debugging a job that was about to run.
#:
#: 2. `pi_options_pit` is a single 15:30 fire with NO retry, and 15:30 ET is
#:    INSIDE the session — half an hour before the close, not after it. That is
#:    deliberate: the row has to precede the after-close announcement it will
#:    later be joined to, and the chain is perishable. One shot per day.
#:
#: (first_h, first_m, last_h, last_m)
FIRES = {"pi_options_pit": (15, 30, 15, 30),
         "pi_why_moved": (17, 15, 19, 15),
         "pi_arena_daily": (17, 45, 19, 45)}

PASS, FAIL, PEND, INFO = "PASS", "FAIL", "PENDING", "INFO"
_ICON = {PASS: "[ok]  ", FAIL: "[FAIL]", PEND: "[wait]", INFO: "[--]  "}


def _get(path: str, attempts: int = 4) -> dict:
    """Fetch with retries, because a dropped connection is not a finding.

    Railway resets the connection on the large health payload often enough that
    a single attempt turned this gate red twice while nothing was wrong. A
    transient blip reading as FAIL is precisely the false alarm the script
    exists to prevent — it would send somebody to debug a healthy deploy at
    05:00.
    """
    last = None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(BASE + path, timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:                               # noqa: BLE001
            last = e
            if i < attempts - 1:
                time.sleep(5 * (i + 1))
    raise RuntimeError(f"{type(last).__name__}: {last} (after {attempts} tries)")


def _last_chance(job: str, now_et: datetime) -> datetime:
    """TODAY's last scheduled firing, retries included."""
    _, _, h, m = FIRES[job]
    return now_et.replace(hour=h, minute=m, second=0, microsecond=0)


def _has_fired(job: str, now_et: datetime) -> bool:
    """Has this job had every chance TODAY, retries included?

    Deliberately today-only, with no walk-back to the previous weekday. A first
    attempt walked back so that a 06:00 HKT Tuesday run (= 18:00 ET Monday)
    would not read Monday's completed pass as pending — and it made `fired`
    return True off LAST FRIDAY's slot, which reports a job as having had its
    chance hours before it does. That over-claims, and over-claiming here means
    calling a working collector broken.

    The residual cost of today-only is the opposite and cheaper error: run this
    at 02:00 ET Tuesday and Monday evening's completed pass reads PENDING rather
    than PASS. It UNDER-claims, the underlying checks still show their real
    values, and the summary line says which slot to wait for.
    """
    if now_et.weekday() >= 5:
        return False
    return now_et >= _last_chance(job, now_et)


def main() -> None:
    now_et = datetime.now(ET)
    now_hk = now_et.astimezone(HK)
    print(f"ET  {now_et:%a %Y-%m-%d %H:%M}      "
          f"HKT {now_hk:%a %Y-%m-%d %H:%M}")
    for job, (h, m, lh, lm) in FIRES.items():
        tgt = now_et.replace(hour=h, minute=m, second=0, microsecond=0)
        window = (f"{h:02d}:{m:02d}" if (h, m) == (lh, lm)
                  else f"{h:02d}:{m:02d}-{lh:02d}:{lm:02d}")
        if _has_fired(job, now_et):
            state = "every firing done"
        elif now_et.weekday() >= 5:
            state = "weekend - does not run"
        else:
            state = f"first firing in {(tgt - now_et).total_seconds() / 3600:.1f}h"
        print(f"  {job:17s} {window:>11s} ET  {state}")
    print()

    try:
        health = _get("/api/health/full")
        arena = _get("/api/arena/status")
    except Exception as e:                                   # noqa: BLE001
        print(f"{_ICON[FAIL]} could not reach production: "
              f"{type(e).__name__}: {e}")
        sys.exit(1)

    rows: list[tuple[str, str, str]] = []

    def add(status: str, name: str, detail: str = "") -> None:
        rows.append((status, name, detail))

    # ── 0. the deploy itself ────────────────────────────────────────────────
    add(INFO, "deploy", f"{health['deploy']['commit'][:12]} "
                        f"up {health['deploy']['uptime_seconds']}s")

    # ── 1. the one-way door: seeds migrate to per-book identity ─────────────
    books = arena.get("books", {})
    stamped = [b for b, v in books.items()
               if v.get("fingerprint_scheme") == "book-v1"]
    # DERIVE OR REFUSE. If not one book carries the key, the endpoint is not
    # serving it and this check has no input — which is "cannot determine",
    # never FAIL. Reported 0/9 as a hard failure until 2026-08-25 while the
    # seeds' actual state was simply invisible, and a red line that no state
    # of the system can clear teaches a reader to skim red lines.
    served = any("fingerprint_scheme" in v for v in books.values())
    if books and not served:
        add(INFO, "seed migration -> book-v1",
            "CANNOT DETERMINE - /api/arena/status does not serve "
            "fingerprint_scheme (deploy the identity fields, then re-check)")
    elif _has_fired("pi_arena_daily", now_et):
        add(PASS if len(stamped) == len(books) else FAIL,
            "seed migration -> book-v1",
            f"{len(stamped)}/{len(books)} stamped")
    else:
        add(PEND if not stamped else FAIL,
            "seed migration -> book-v1",
            f"{len(stamped)}/{len(books)} stamped "
            f"({'correct - the pass has not run' if not stamped else 'STAMPED EARLY, investigate'})")

    # ── 2. nine books, not ten ──────────────────────────────────────────────
    add(PASS if len(books) == 9 else FAIL, "book count",
        f"{len(books)} (expect 9 - PROFIT_ALLOCATOR_v1 retired)")

    # ── 3. NAV advanced ─────────────────────────────────────────────────────
    navs = sorted({v.get("nav_rows") for v in books.values()})
    if _has_fired("pi_arena_daily", now_et):
        add(PASS if navs and min(navs) >= 2 else FAIL, "nav rows advanced",
            f"rows={navs}")
    else:
        add(PEND, "nav rows advanced", f"rows={navs}")

    # ── 4. options_pit leaves ABSENT — LOST EVIDENCE if it does not ─────────
    op = health.get("options_pit", {})
    if _has_fired("pi_options_pit", now_et):
        add(PASS if op.get("status") != "ABSENT" else FAIL,
            "options_pit accruing",
            f"{op.get('status')} rows={op.get('rows')} "
            f"days={op.get('days_held')}"
            + ("  <- option chains have NO history; a missed day is gone"
               if op.get("status") == "ABSENT" else ""))
    else:
        add(PEND, "options_pit accruing", f"{op.get('status')} (expected)")

    # ── 5. event_store ──────────────────────────────────────────────────────
    es = health.get("event_store", {})
    if _has_fired("pi_arena_daily", now_et):
        add(PASS if es.get("status") != "ABSENT" else FAIL,
            "event_store accruing", str(es.get("status")))
    else:
        add(PEND, "event_store accruing", f"{es.get('status')} (expected)")

    # ── 6. the broker must NOT have traded ──────────────────────────────────
    #
    # trades > 0 is the FINDING, not the success: the arena Alpaca account is
    # empty and `sync` deliberately will not open the first position. Only the
    # attended seed does that.
    el = health.get("execution_ledger", {})
    n_targets = el.get("n_targets", 0)
    if el.get("status") == "ABSENT":
        add(PASS if not _has_fired("pi_arena_daily", now_et) else INFO,
            "arena broker did NOT trade",
            "execution_ledger ABSENT - nothing submitted, which is correct "
            "until the attended seed")
    else:
        add(INFO, "arena broker", f"execution_ledger {el.get('status')} "
                                  f"targets={n_targets} - REVIEW: any arena "
                                  f"order before the attended seed is the "
                                  f"finding")

    # ── 7. why_moved / live_forward ─────────────────────────────────────────
    pops = health.get("forecast_populations", {}).get("populations", {})
    lf = pops.get("live_forward", {})
    quiet = lf.get("days_quiet")
    if _has_fired("pi_why_moved", now_et):
        add(PASS if (quiet is not None and quiet <= 1) else FAIL,
            "live_forward writing",
            f"days_quiet={quiet} (P0 if still quiet after the job)")
    else:
        add(PEND, "live_forward writing", f"days_quiet={quiet}")

    # ── 8. today's additions ────────────────────────────────────────────────
    si = health.get("selector_identity", {})
    if si.get("status") == "ok":
        comp = si["selectors"]["arena_composite"]
        ok = all(comp["at_seed_baseline"].values())
        add(PASS if ok else FAIL, "selector identity at seed baseline",
            json.dumps(comp["at_seed_baseline"]))
    else:
        add(FAIL, "selector identity", str(si.get("status")))

    bus = health.get("information_bus", {})
    add(PASS if bus.get("status") == "ok" else FAIL, "information bus",
        f"{bus.get('status')} composite={bus.get('composite_fingerprint')}")

    llm = health.get("llm", {})
    prov = llm.get("providers", {})
    add(PASS if prov.get("matches_declaration") else FAIL, "llm provider",
        f"active={prov.get('active')} refusals={llm.get('language_refusals')}")

    # ── report ──────────────────────────────────────────────────────────────
    for status, name, detail in rows:
        print(f"{_ICON[status]} {name:34s} {detail}")

    n_fail = sum(1 for s, _, _ in rows if s == FAIL)
    n_pend = sum(1 for s, _, _ in rows if s == PEND)
    print()
    if n_fail:
        print(f"{n_fail} FAILED, {n_pend} pending - read the FAIL lines above.")
    elif n_pend:
        print(f"nothing failed; {n_pend} check(s) still waiting on a job that "
              f"has not fired yet. Re-run after 19:45 ET - the LAST "
              f"catch-up retry - which is 07:45 HKT Tuesday.")
    else:
        print("gate clear.")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
