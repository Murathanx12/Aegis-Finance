"""The launcher: an IIF-1 night that starts without a person at a keyboard.

    # what it would decide right now, spends nothing, writes nothing
    python -m scripts.run_night_launcher --dry-run

    # rehearse: decide for real, write a REHEARSAL receipt, never launch
    python -m scripts.run_night_launcher --rehearse

    # the real thing (this is what the scheduled task runs)
    python -m scripts.run_night_launcher

    # is the launcher accepted yet?
    python -m scripts.run_night_launcher --acceptance

WHY A LAUNCHER IS A SCIENTIFIC OBJECT AND NOT A CONVENIENCE
===========================================================
Night 1 ran unattended once *launched*, and the launch was a person at 17:00.
That is the honour-system input the house rule forbids, applied to the calendar:
the campaign's cadence was a human's diary wearing a cron costume, and a night
missed because somebody was asleep is indistinguishable in the record from a
night the guards refused.

So the launcher's job is not "start the night". It is **to make the reason a
night did or did not run a derived, recorded fact**.

THREE PROPERTIES, EACH PAID FOR BY A PRIOR FAILURE
==================================================

1.  **Readiness is recomputed AT LAUNCH, never carried.** Every number below is
    re-derived at the moment of the decision: the session calendar, the calls
    per cell, the duration bound, the assembly allowance, the frozen
    pre-registration. A verdict computed at 09:00 and acted on at 17:00 is a
    guess about the intervening eight hours. `night_schedule_plan` already says
    this about wall-clock times; the launcher is where it becomes enforced
    rather than advised.

2.  **A REFUSING LAUNCHER AND A DEAD TASK PRODUCE IDENTICAL SILENCE.** This is
    the canon's mirror rule and it is why every outcome writes a receipt —
    `LAUNCHED`, `REFUSED` with a code and a sentence, or `REHEARSAL`. The
    morning check reads receipts. It does not read `scheduler.running`, which
    prod already proved can be true while every tick refuses. If the receipt
    cannot be written, the launcher REFUSES TO LAUNCH: an unattended run whose
    evidence of having happened may not exist is worse than a night not run.

3.  **Acceptance is receipts on three consecutive trading dates.** Not a
    dry-run flag, not a green process. Until `acceptance_report()` says
    `ACCEPTED` the attended fallback stays live, and that verdict is computed
    from the receipt files rather than asserted anywhere.

THE FINDING THIS FILE EXISTS TO ENCODE: 17:39 IS NOT A LAUNCH TIME
==================================================================
The derived stop everyone has been quoting — 17:39 local on 2026-08-18 — is
`next_open - duration_bound`. That is the latest safe START OF THE RUN, and
`assert_night_fits_before_open` is called from inside `run_night()`, which is
*after* the snapshot has been assembled. Assembly is not free: Night 1's
receipt puts it at 18.2 minutes (`decision_lag_minutes`), because it walks the
whole universe through yfinance and EDGAR.

So a launcher that fires at the derived stop starts assembling at 17:39,
reaches the guard at ~17:57, and is refused by it. The two clocks that were
named on 2026-08-17 have a third consequence nobody had drawn: **the
latest-safe-LAUNCH is the latest-safe-run-start minus the assembly allowance.**
Tonight that is 17:39 - 36.4 = **17:02**, so the standing 17:00 start has about
three minutes of margin rather than thirty-nine. It passes. It passes by much
less than the headline number suggests, and a reader who remembered "17:39"
would have launched half an hour into a window that no longer existed.

The allowance is derived, not declared, and bounded on both sides:

    assembly_allowance = min(MAX_DECISION_LAG_MINUTES,
                             worst completed night's decision_lag
                               x DECLARED_DURATION_SAFETY_FACTOR)

The cap is the point. `assert_decision_time_fresh` refuses any night whose
snapshot is older than `MAX_DECISION_LAG_MINUTES`, so an assembly longer than
that cannot produce a paid run — which makes 45 minutes the true worst case and
anything derived above it fiction. With zero completed nights there is nothing
to measure and the cap governs, which is the conservative direction.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from backend import config as _config
from backend.services import investigator_night as N
from backend.services import market_sessions as MS

logger = logging.getLogger(__name__)

TRIAL = N.TRIAL

#: Launch receipts, beside the night receipts and on the same persistent volume.
#: Separate directory deliberately: a launch receipt exists for nights that
#: never ran, and mixing them into `iif1_nights` would make every derivation
#: that globs that directory (calls/cell, duration bound) have to learn to skip
#: them. A directory whose contents mean two different things is a denominator
#: waiting to be wrong.
LAUNCH_RECEIPTS_DIR = _config.OPTIMUS_LEDGER_DIR / "iif1_launches"

RECEIPT_ENCODING = "utf-8"

#: Receipts on this many CONSECUTIVE trading dates before the launcher is
#: accepted and the attended fallback is retired (Order 15 §1).
ACCEPTANCE_CONSECUTIVE_DATES = 3

VERDICT_LAUNCHED = "LAUNCHED"
VERDICT_REFUSED = "REFUSED"
VERDICT_REHEARSAL = "REHEARSAL"

#: Refusal codes. Strings rather than an enum because they are written into
#: receipts and read back by the morning check; a code that changes value when
#: somebody reorders an enum is a receipt that stops matching its own history.
NOT_A_SESSION = "NOT_A_SESSION"
NOT_PREOPEN_WINDOW = "NOT_PREOPEN_WINDOW"
PAST_LATEST_SAFE_LAUNCH = "PAST_LATEST_SAFE_LAUNCH"
ALREADY_ATTEMPTED = "ALREADY_ATTEMPTED"
PREREG_UNREADABLE = "PREREG_UNREADABLE"
ACCRUAL_COMPLETE = "ACCRUAL_COMPLETE"
SESSION_DATE_DISAGREEMENT = "SESSION_DATE_DISAGREEMENT"


class LaunchRefused(RuntimeError):
    """The launcher cannot SEE something it is required to check.

    Distinct from a refusal *verdict*, which is a finding and gets a receipt.
    This is the other case: the launcher has been handed nothing and would have
    to answer anyway. It covers exactly two situations, and both are the same
    shape as every entry in the canon's guard list —

      * the night-receipt directory is unreadable, so "has tonight already been
        attempted?" cannot be answered, and the one-attempt rule that keeps a
        refusal from being compensated by an unregistered retry is unenforceable;
      * the launch-receipt directory cannot be written, so the run would happen
        with no evidence that it happened — and the acceptance contract, the
        morning check and the whole refusing-launcher-vs-dead-task distinction
        all rest on those files existing.

    In both cases the answer is to refuse rather than to launch and hope.
    """


def _now_utc(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now


def derive_assembly_allowance_minutes(receipts_dir: Path | None = None) -> dict:
    """Minutes to allow between LAUNCH and the first paid call, derived.

    See the module docstring. This is the quantity that turns a
    latest-safe-run-start into a latest-safe-launch, and until now nothing
    computed it — the night measured `decision_lag_minutes` on every receipt and
    no caller had ever read it back.

    Same three rules as `derive_calls_per_cell` and `derive_night_duration_bound`,
    for the same reasons: sandbox and non-`ok` nights excluded, the MAXIMUM
    rather than the mean, and the result may only ever make the launcher more
    conservative — here by being capped at `MAX_DECISION_LAG_MINUTES`, which is
    the ceiling the night's own staleness guard enforces. A derived allowance
    above that cap would be describing a night that cannot exist.
    """
    cap = float(N.MAX_DECISION_LAG_MINUTES)
    d = Path(receipts_dir or N.RECEIPTS_DIR)
    observed: list[dict] = []
    try:
        paths = sorted(d.glob("*.json")) if d.exists() else []
    except OSError as e:
        logger.warning("assembly allowance: receipts dir unreadable (%s) — the "
                       "CAP governs, and the basis says so", e)
        paths = []
    for p in paths:
        try:
            r = json.loads(p.read_text(encoding=RECEIPT_ENCODING))
        except (OSError, ValueError) as e:
            logger.warning("assembly allowance: receipt %s unreadable (%s) — "
                           "skipped", p.name, e)
            continue
        if r.get("sandbox") or str(r.get("status")) != "ok":
            continue
        lag = r.get("decision_lag_minutes")
        if isinstance(lag, (int, float)) and lag > 0:
            observed.append({"night": r.get("night") or p.stem,
                             "assembly_minutes": round(float(lag), 2)})
    if not observed:
        return {"value": cap, "basis": "CAP_NO_COMPLETED_NIGHTS", "cap": cap,
                "n_nights": 0, "observed": [],
                "safety_factor": N.DECLARED_DURATION_SAFETY_FACTOR}
    worst = max(o["assembly_minutes"] for o in observed)
    scaled = worst * N.DECLARED_DURATION_SAFETY_FACTOR
    return {
        "value": round(min(cap, scaled), 1),
        "basis": ("CAP_BINDS" if scaled >= cap else
                  "MEASURED_WORST_ASSEMBLY_X_DECLARED_FACTOR"),
        "cap": cap,
        "worst_minutes": worst,
        "scaled_minutes": round(scaled, 1),
        "n_nights": len(observed),
        "observed": observed,
        "safety_factor": N.DECLARED_DURATION_SAFETY_FACTOR,
    }


def _attempted_session_dates(receipts_dir: Path | None = None) -> set[str]:
    """Session dates that already have a NIGHT receipt of any status.

    Any status on purpose. A void night is an attempt: it selected a population,
    it may have spent, and the registration buys ONE attempt per night. Counting
    only the successes is how a refusal gets compensated by a retry nobody
    registered.

    Raises `LaunchRefused` if the directory cannot be listed — see the class.
    """
    d = Path(receipts_dir or N.RECEIPTS_DIR)
    if not d.exists():
        # Absent is a legitimate answer meaning "no night has ever run", and it
        # is the state every campaign starts in. Unreadable is not.
        return set()
    try:
        paths = sorted(d.glob("*.json"))
    except OSError as e:
        raise LaunchRefused(
            f"night receipts at {d} could not be listed ({e}), so whether "
            f"tonight has already been attempted is unknown. Launching would "
            f"risk a second paid attempt against a registration that buys one."
        ) from e
    out: set[str] = set()
    for p in paths:
        try:
            r = json.loads(p.read_text(encoding=RECEIPT_ENCODING))
        except (OSError, ValueError):
            # A torn receipt still proves an attempt was made — the filename is
            # the session date. Reading it as "no attempt" is the failure this
            # whole function exists to prevent, so the stem is trusted here even
            # though the contents are not.
            out.add(p.stem)
            continue
        if not r.get("sandbox"):
            out.add(str(r.get("night") or p.stem))
    return out


def _graded_nights_completed(receipts_dir: Path | None = None) -> int:
    """Completed, non-sandbox, `ok` nights — the campaign's accrual counter."""
    d = Path(receipts_dir or N.RECEIPTS_DIR)
    if not d.exists():
        return 0
    n = 0
    for p in sorted(d.glob("*.json")):
        try:
            r = json.loads(p.read_text(encoding=RECEIPT_ENCODING))
        except (OSError, ValueError):
            continue
        if not r.get("sandbox") and str(r.get("status")) == "ok":
            n += 1
    return n


def _assert_receipt_dir_writable(launch_dir: Path) -> None:
    try:
        launch_dir.mkdir(parents=True, exist_ok=True)
        probe = launch_dir / ".writable"
        probe.write_text("", encoding=RECEIPT_ENCODING)
        probe.unlink()
    except OSError as e:
        raise LaunchRefused(
            f"launch receipts at {launch_dir} are not writable ({e}). Every "
            f"outcome of this launcher is supposed to leave a receipt, because "
            f"a refusing launcher and a dead task produce identical silence. "
            f"Running without one would produce the silence AND spend money."
        ) from e


def evaluate_launch(*, now: datetime | None = None,
                    k: int | None = None,
                    n_arms: int | None = None,
                    receipts_dir: Path | None = None,
                    launch_dir: Path | None = None,
                    require_writable: bool = True) -> dict:
    """The whole decision, recomputed from scratch. Spends nothing.

    Returns a report dict with `may_launch`, `refusals` (a list of
    `{code, detail}`) and `derived` (every number the verdict rests on, so the
    receipt is auditable without re-running anything).

    Domain refusals are VERDICTS, not exceptions — they are findings and they
    get receipts. `LaunchRefused` is reserved for the launcher being unable to
    see what it must check.
    """
    now = _now_utc(now)
    launch_dir = Path(launch_dir or LAUNCH_RECEIPTS_DIR)
    if require_writable:
        _assert_receipt_dir_writable(launch_dir)

    refusals: list[dict] = []
    derived: dict = {"now_utc": now.isoformat(timespec="seconds")}

    # ── 1. the calendar ──────────────────────────────────────────────────────
    # `SessionCalendarUnavailable` is deliberately NOT caught. A launcher that
    # cannot read the exchange calendar cannot tell a holiday from a Tuesday,
    # and the previous generation of this arithmetic invented a Sunday opening
    # bell. Propagating it means the scheduled task fails loudly.
    next_open = MS.next_session_open(now)
    session_date = next_open.date()
    derived["next_open_utc"] = next_open.isoformat(timespec="minutes")
    derived["session_date"] = session_date.isoformat()
    derived["hours_until_open"] = round(
        (next_open - now).total_seconds() / 3600.0, 2)

    if not MS.is_session(session_date):
        refusals.append({"code": NOT_A_SESSION,
                         "detail": f"{session_date} is not an XNYS session"})

    if derived["hours_until_open"] > N.MAX_PREOPEN_LEAD_HOURS:
        refusals.append({
            "code": NOT_PREOPEN_WINDOW,
            "detail": (f"next open is {derived['hours_until_open']:.1f}h away, "
                       f"beyond the {N.MAX_PREOPEN_LEAD_HOURS}h pre-open lead. "
                       f"This is not a pre-open window — without this clause a "
                       f"weekend launch looks SAFER than a weekday one because "
                       f"the next real session is further off.")})

    # The night keys its snapshot and receipt by the New York decision date,
    # and the guard keys off the next XNYS open. On a pre-open run those must be
    # the same day. They disagree if the launcher fires after the bell, or on a
    # DST boundary, and the disagreement is exactly the sort of thing that
    # produces a receipt filed against the wrong session with nothing complaining.
    try:
        from backend.services import iif1_features as F
        # `now` is threaded through rather than re-read from the clock: the
        # check has to answer "what date would the night stamp IF LAUNCHED AT
        # THIS INSTANT", and a helper that consults `datetime.now()` internally
        # would make the refusal branches untestable at any hour but the real
        # one. That is the same defect as a guard reading a constant its caller
        # thinks it supplied.
        ny_date = F.resolve_decision_ts(now).date()
        derived["decision_date_ny"] = ny_date.isoformat()
        if ny_date != session_date:
            refusals.append({
                "code": SESSION_DATE_DISAGREEMENT,
                "detail": (f"the night would stamp its snapshot {ny_date} while "
                           f"the guard forecasts the {session_date} session. A "
                           f"pre-open night must be the same day on both clocks.")})
    except Exception as e:                                        # noqa: BLE001
        # A CHECK THAT DID NOT RUN IS NOT A CHECK THAT PASSED. The first draft
        # recorded this as informational and moved on, which meant an import or
        # calendar failure silently DELETED the guard — the launcher would then
        # proceed with no idea which session the night was about to stamp. It
        # refuses instead, under its own code, so the receipt says the check was
        # unavailable rather than implying it was satisfied.
        derived["decision_date_ny"] = f"UNAVAILABLE: {e}"
        refusals.append({
            "code": SESSION_DATE_DISAGREEMENT,
            "detail": (f"the date the night would stamp could not be computed "
                       f"({type(e).__name__}: {e}), so it cannot be checked "
                       f"against the {session_date} session the guard "
                       f"forecasts. Unavailable is not agreement.")})

    # ── 2. the derived stop, and the launch deadline it implies ──────────────
    k = int(k if k is not None else _frozen_k())
    arms = int(n_arms if n_arms is not None else len(N.ARMS))
    derived["k"] = k
    derived["n_arms"] = arms

    cpc = N.derive_calls_per_cell(receipts_dir)
    run_minutes, basis, modelled_serial, dur = N.decision_minutes(
        k=k, n_arms=arms, calls_per_cell=cpc["value"])
    assembly = derive_assembly_allowance_minutes(receipts_dir)

    latest_run_start = next_open - timedelta(minutes=run_minutes)
    latest_launch = latest_run_start - timedelta(minutes=assembly["value"])

    derived["calls_per_cell"] = cpc
    derived["duration_bound"] = dur
    derived["assembly_allowance"] = assembly
    derived["decision_minutes"] = round(run_minutes, 1)
    derived["decision_basis"] = basis
    derived["modelled_serial_minutes"] = round(modelled_serial, 1)
    # SECONDS, not minutes. Truncating a boundary to the minute loses up to
    # 60s in an unstated direction on each end, and these two are subtracted
    # from each other by anything checking that the assembly allowance was
    # actually applied. A receipt should carry the value the decision used, and
    # let the display round.
    derived["latest_safe_run_start_utc"] = latest_run_start.isoformat(
        timespec="seconds")
    derived["latest_safe_launch_utc"] = latest_launch.isoformat(
        timespec="seconds")
    derived["launch_margin_minutes"] = round(
        (latest_launch - now).total_seconds() / 60.0, 1)

    if now > latest_launch:
        refusals.append({
            "code": PAST_LATEST_SAFE_LAUNCH,
            "detail": (
                f"launching now leaves {derived['launch_margin_minutes']:.1f} "
                f"min of margin. The run needs {run_minutes:.0f} min ({basis}) "
                f"and assembly needs up to {assembly['value']:.0f} min "
                f"({assembly['basis']}) BEFORE the run's own guard is even "
                f"reached, so the latest safe launch is "
                f"{latest_launch.isoformat(timespec='minutes')}, not the "
                f"latest safe run start of "
                f"{latest_run_start.isoformat(timespec='minutes')}.")})

    # ── 3. one attempt per night ─────────────────────────────────────────────
    attempted = _attempted_session_dates(receipts_dir)
    derived["nights_attempted"] = len(attempted)
    if session_date.isoformat() in attempted:
        refusals.append({
            "code": ALREADY_ATTEMPTED,
            "detail": (f"a night receipt already exists for {session_date}. The "
                       f"registration buys ONE attempt per night; a launcher "
                       f"that retries after a refusal is spending error rate "
                       f"nobody reserved.")})

    # ── 4. the campaign's own end condition ──────────────────────────────────
    graded = _graded_nights_completed(receipts_dir)
    derived["graded_nights_completed"] = graded
    derived["graded_nights_required"] = N.GRADED_NIGHTS_TO_FIRST_LOOK
    if graded >= N.GRADED_NIGHTS_TO_FIRST_LOOK:
        refusals.append({
            "code": ACCRUAL_COMPLETE,
            "detail": (f"{graded} graded nights completed, and the registered "
                       f"accrual is {N.GRADED_NIGHTS_TO_FIRST_LOOK}. The "
                       f"launcher stops permanently here rather than accruing "
                       f"past a look it has not been licensed to take.")})

    # ── 5. the frozen registration ───────────────────────────────────────────
    # Verified here so the refusal is a receipt rather than a stack trace two
    # minutes into an unattended run. `run_night` verifies it again before the
    # first dollar; this is not a substitute for that, it is an early read so
    # the reason lands in the launch receipt.
    try:
        from backend.services.iif1_prereg import verify_or_refuse
        frozen = verify_or_refuse()
        derived["prereg_fields_verified"] = len(frozen)
    except Exception as e:                                        # noqa: BLE001
        derived["prereg_fields_verified"] = 0
        refusals.append({
            "code": PREREG_UNREADABLE,
            "detail": (f"{type(e).__name__}: {e}. A context that cannot read "
                       f"the registered rule must not accrue against it.")})

    return {
        "trial": TRIAL,
        "session_date": session_date.isoformat(),
        "evaluated_at_utc": now.isoformat(timespec="seconds"),
        "may_launch": not refusals,
        "refusals": refusals,
        "derived": derived,
    }


def _frozen_k() -> int:
    """Triggers per night from the registration, falling back to the module."""
    try:
        from backend.services.iif1_prereg import verify_or_refuse
        return int(verify_or_refuse()["TRIGGERS_PER_NIGHT"])
    except Exception:                                             # noqa: BLE001
        from backend.services import investigator_triggers as TR
        return int(TR.TRIGGERS_PER_NIGHT)


#: How a receipt came to exist. `scheduled` is the only mode that counts toward
#: acceptance — see `acceptance_report`.
INVOCATION_SCHEDULED = "scheduled"
INVOCATION_MANUAL = "manual"


def observe_invocation(declared: str) -> dict:
    """What we BELIEVE produced this run, and one thing that can contradict it.

    The declared mode is an honour-system input: `--scheduled` is a string a
    human can type. So it is recorded alongside a DERIVED observation, exactly
    as `implementation_version` is recorded alongside `arm_implementation_
    fingerprint` — the declaration says what we think happened, the observation
    says something that actually did, and a disagreement is detectable after
    the fact instead of being an assumption.

    The observation is `sys.stdin.isatty()`. Its limits, stated rather than
    implied:

      * it catches a human in a TERMINAL claiming `--scheduled`. That is the
        realistic mistake — someone rehearsing by hand and copying the full
        registered command line.
      * it does NOT catch a human redirecting stdin, or running under CI, or
        anything else that detaches the console deliberately. Nothing stdlib
        does, and a check that claimed to would be worse than one that says so.
      * **AND IT HAS A FALSE POSITIVE, FOUND BY ITS OWN FIRST REAL RECEIPT
        (2026-08-18, `iif1_launches/2026-08-18.2.json`).** This docstring used
        to assert "a Windows scheduled task runs with no console attached, so
        its stdin is not a terminal". That is true of a task registered
        S4U / "run whether user is logged on or not", and FALSE of one
        registered `LogonType=Interactive`, which runs inside the logged-on
        session with a console. `AegisIIF1NightLauncher` is registered the
        second way, so a genuine 17:00:01 firing recorded `contradicted: true`.

    The observation is still correct as an observation — stdin really was a
    terminal — so it is not relaxed here. What it means is environment-
    dependent, which is why `acceptance_report` now names the environment as
    the fault rather than counting zero forever. An assumption about the world,
    written into a docstring, was falsified by the first receipt that tested
    it; recording the evidence is what made that visible in one day instead of
    on the morning of arming.

    Returns the pair plus `contradicted`, which `acceptance_report` treats as
    disqualifying — an ambiguous receipt is not evidence.
    """
    import sys
    try:
        interactive: bool | None = bool(sys.stdin.isatty())
    except (AttributeError, ValueError, OSError):
        # Recorded as None, never as False. "We did not look" must not read the
        # same as "we looked and it was not a terminal" — that is the git_dirty
        # lesson, and here it would launder a manual run into a scheduled one.
        interactive = None
    return {
        "invocation_mode": declared,
        "stdin_isatty": interactive,
        "contradicted": bool(declared == INVOCATION_SCHEDULED
                             and interactive is True),
    }


def write_launch_receipt(report: dict, *, verdict: str,
                         launch_dir: Path | None = None,
                         invocation: str = INVOCATION_MANUAL,
                         extra: dict | None = None) -> Path:
    """One receipt per session date, per verdict. Never overwritten silently.

    A second receipt for the same date lands beside the first with a suffix
    rather than replacing it: two launch attempts on one date is itself the
    finding, and a writer that overwrites destroys the evidence of the thing it
    is supposed to make visible.
    """
    launch_dir = Path(launch_dir or LAUNCH_RECEIPTS_DIR)
    launch_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(report)
    payload["verdict"] = verdict
    payload["written_at_utc"] = datetime.now(timezone.utc).isoformat(
        timespec="seconds")
    payload.update(N.git_provenance())
    payload.update(observe_invocation(invocation))
    # ON EVERY RECEIPT, including refusals. A manifest attached only to
    # launches would leave the rehearsal — the one receipt whose whole purpose
    # is to pin a later launch — as the one with nothing to compare against.
    payload["launch_manifest"] = launch_manifest()
    payload["implementation_version"] = N.IMPLEMENTATION_VERSION
    payload["arm_implementation_fingerprint"] = N.arm_implementation_fingerprint()
    if extra:
        payload.update(extra)

    stem = str(report.get("session_date") or date.today().isoformat())
    path = launch_dir / f"{stem}.json"
    n = 1
    while path.exists():
        path = launch_dir / f"{stem}.{n}.json"
        n += 1
    path.write_text(json.dumps(payload, indent=2, default=str),
                    encoding=RECEIPT_ENCODING)
    return path


def read_launch_receipts(launch_dir: Path | None = None) -> list[dict]:
    d = Path(launch_dir or LAUNCH_RECEIPTS_DIR)
    if not d.exists():
        return []
    out: list[dict] = []
    for p in sorted(d.glob("*.json")):
        try:
            r = json.loads(p.read_text(encoding=RECEIPT_ENCODING))
        except (OSError, ValueError) as e:
            logger.warning("launch receipt %s unreadable (%s)", p.name, e)
            continue
        r["_path"] = str(p)
        out.append(r)
    return out


def acceptance_report(*, launch_dir: Path | None = None,
                      now: datetime | None = None,
                      n_required: int = ACCEPTANCE_CONSECUTIVE_DATES) -> dict:
    """Is the launcher accepted? Receipts on N consecutive TRADING dates.

    Not `scheduler.running`, not "the task is registered", not a dry run. Prod
    has already demonstrated that all seven jobs can be registered and running
    while every tick refuses — receipts prove a job ran, and their absence is
    what proves it did not.

    CONSECUTIVE means consecutive **XNYS sessions**, not consecutive calendar
    days: a launcher that produced receipts on Thursday and Friday and none on
    Saturday has not skipped anything. Rehearsal receipts count — the thing
    being accepted is that the launcher WAKES UP AND DECIDES, and a refusal
    decided on time is exactly as much evidence of that as a launch.

    ONLY `scheduled` RECEIPTS COUNT, and that is the load-bearing clause. A
    receipt written by a human running the command is proof of the code path
    and no proof at all of the thing under test, which is that **nobody had to
    be there**. Counting hand-run rehearsals would make acceptance satisfiable
    by three afternoons at a keyboard — the honour system this launcher exists
    to remove, re-entering through its own acceptance test. Receipts that
    declare `scheduled` while `observe_invocation` contradicts them are
    excluded too, and both exclusions are reported rather than silently
    dropped: a count that shrank for a reason nobody can see is the denominator
    failure in a new costume.
    """
    now = _now_utc(now)
    receipts = read_launch_receipts(launch_dir)
    counted, excluded = [], []
    for r in receipts:
        if not r.get("session_date"):
            continue
        if r.get("invocation_mode") != INVOCATION_SCHEDULED:
            excluded.append({"session_date": r["session_date"],
                             "why": f"invocation_mode="
                                    f"{r.get('invocation_mode') or 'undeclared'}"})
        elif r.get("contradicted"):
            excluded.append({"session_date": r["session_date"],
                             "why": "declared scheduled but stdin was a terminal"})
        else:
            counted.append(r)
    have = {str(r["session_date"]) for r in counted}

    # Walk backwards through real sessions from the most recent one on or
    # before today, so a missing Monday breaks a Friday-Tuesday streak.
    sessions: list[date] = []
    cursor = now.date()
    guard = 0
    while len(sessions) < n_required + 10 and guard < 60:
        guard += 1
        if MS.is_session(cursor):
            sessions.append(cursor)
        cursor -= timedelta(days=1)

    streak: list[str] = []
    for d in sessions:
        if d.isoformat() in have:
            streak.append(d.isoformat())
        else:
            break

    accepted = len(streak) >= n_required

    # A CRITERION THAT CANNOT BE MET LOOKS EXACTLY LIKE ONE THAT HAS NOT BEEN
    # MET YET. Both print `n_consecutive: 0` and both wait. That is the refusing
    # guard / dead job shape: identical silence, opposite remedies — one needs
    # another day, the other needs a change, and nobody finds out which until
    # the day arming was supposed to happen.
    #
    # So: if unattended firings HAVE left receipts and every one of them was
    # disqualified, say that. It is a different verdict from "not yet", and it
    # is the one that carries a remedy. Note this is still computed from
    # receipt FILES — the evidence that something fired is the receipt it
    # wrote, never a liveness flag consulted from here.
    contradicted = [e for e in excluded
                    if e["why"].startswith("declared scheduled")]
    n_scheduled = len(counted) + len(contradicted)
    unsatisfiable = bool(n_scheduled > 0 and not counted)
    diagnosis = None
    if unsatisfiable:
        diagnosis = (
            f"{n_scheduled} unattended firing(s) left receipts and EVERY one "
            f"was disqualified, so this criterion cannot currently be satisfied "
            f"by waiting. The known cause on Windows is a task registered with "
            f"LogonType=Interactive: it runs inside the logged-on session with "
            f"a console attached, so stdin IS a terminal and "
            f"`observe_invocation` reads a genuinely scheduled firing as "
            f"contradicted. The docstring there asserts the opposite ('a "
            f"Windows scheduled task runs with no console attached') and that "
            f"assertion is false for this registration. Remedies, both "
            f"attended: redirect the task action's stdin (`cmd /c ... < NUL`), "
            f"or re-register with LogonType=S4U / 'run whether user is logged "
            f"on or not'. Do NOT relax the contradiction test — it is reading "
            f"its input correctly; its input is confounded.")

    verdict = ("ACCEPTED" if accepted
               else "UNSATISFIABLE_IN_THIS_ENVIRONMENT" if unsatisfiable
               else "NOT_ACCEPTED")
    return {
        "accepted": accepted,
        "verdict": verdict,
        "unsatisfiable": unsatisfiable,
        "diagnosis": diagnosis,
        "n_scheduled_receipts": n_scheduled,
        "n_scheduled_contradicted": len(contradicted),
        "n_required": n_required,
        "consecutive_session_dates": list(reversed(streak)),
        "n_consecutive": len(streak),
        "n_receipts_total": len(receipts),
        "n_receipts_counted": len(counted),
        "excluded": excluded,
        "recent_sessions_checked": [d.isoformat() for d in sessions[:n_required + 3]],
        "note": ("Until ACCEPTED the attended fallback stays live. This verdict "
                 "is computed from receipt files written by SCHEDULED firings; "
                 "it is not a flag anything sets, and a hand-run rehearsal "
                 "does not count toward it."),
    }


# ── the launch manifest and equivalence pinning (Order 16 §1) ──────────────
#: The modules whose BYTES define what a night does. Order 16 supersedes Order
#: 15 §1 here: a rehearsal only pins a real launch if the two demonstrably ran
#: the same code, and "the same commit" is not that claim — an uncommitted edit
#: changes behaviour without moving the SHA, which is precisely why
#: `arm_implementation_fingerprint` exists alongside `git_commit` already.
NIGHT_MODULES = (
    "backend.services.investigator_night",
    "backend.services.investigator_agent",
    "backend.services.investigator_tools",
    "backend.services.investigator_triggers",
    "backend.services.iif1_features",
    "backend.services.iif1_run",
    "backend.services.iif1_prereg",
)

#: Manifest fields whose disagreement means the rehearsal did NOT pin the
#: launch. Deliberately excludes `git_commit`: a docs-only commit between the
#: rehearsal and the launch changes the SHA and changes nothing that runs, and
#: refusing on it would train the operator to re-rehearse for no reason — which
#: is how a guard gets routed around. The module hashes carry the real claim.
EQUIVALENCE_FIELDS = ("prereg_hash", "module_hashes", "implementation_version",
                      "arm_implementation_fingerprint", "frozen_surface")


def _sha256_file(path: Path) -> str:
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def launch_manifest() -> dict:
    """Everything needed to say WHICH EXPERIMENT this launch is about to run.

    Order 16 §1, adopted verbatim from the GPT plan: prereg hash, module
    hashes, version + fingerprint, SHA and dirty state. The point is not
    provenance for its own sake — it is that a rehearsal can only pin a real
    launch if the two are demonstrably the same invocation, and until this
    existed "we rehearsed it" was a statement about the operator's memory.

    Unreadable inputs are recorded as `UNAVAILABLE: <reason>`, never omitted
    and never defaulted. An absent hash that compares equal to another absent
    hash would make two different worlds look identical, which is the exact
    failure this manifest is built to catch.
    """
    import sys

    m: dict = {"manifest_version": 1,
               "built_at_utc": datetime.now(timezone.utc).isoformat(
                   timespec="seconds"),
               "python": sys.version.split()[0]}

    try:
        from backend.services import iif1_prereg as P
        m["prereg_path"] = str(P.CONFIG_PATH)
        m["prereg_hash"] = _sha256_file(P.CONFIG_PATH)
    except Exception as e:                                        # noqa: BLE001
        m["prereg_path"] = "UNAVAILABLE"
        m["prereg_hash"] = f"UNAVAILABLE: {type(e).__name__}: {e}"

    # The FROZEN SURFACE ITSELF, not only a hash of the file that holds it.
    # A hash says "something changed"; the surface says what the night is
    # actually about to run, and the two answer different questions on the
    # morning somebody has to decide whether a rehearsal still counts.
    try:
        from backend.services.iif1_prereg import verify_or_refuse
        frozen = verify_or_refuse()
        m["frozen_surface"] = {k: (list(v) if isinstance(v, (list, tuple)) else v)
                               for k, v in sorted(frozen.items())}
    except Exception as e:                                        # noqa: BLE001
        m["frozen_surface"] = f"UNAVAILABLE: {type(e).__name__}: {e}"

    hashes: dict[str, str] = {}
    for name in NIGHT_MODULES:
        try:
            import importlib
            mod = importlib.import_module(name)
            hashes[name] = _sha256_file(Path(mod.__file__))
        except Exception as e:                                    # noqa: BLE001
            hashes[name] = f"UNAVAILABLE: {type(e).__name__}: {e}"
    m["module_hashes"] = hashes

    m["implementation_version"] = N.IMPLEMENTATION_VERSION
    m["arm_implementation_fingerprint"] = N.arm_implementation_fingerprint()
    m.update(N.git_provenance())
    return m


def manifest_differences(rehearsal: dict, live: dict) -> list[str]:
    """Human-readable list of equivalence-significant disagreements."""
    out: list[str] = []
    for f in EQUIVALENCE_FIELDS:
        a, b = rehearsal.get(f), live.get(f)
        if f == "module_hashes" and isinstance(a, dict) and isinstance(b, dict):
            for name in sorted(set(a) | set(b)):
                if a.get(name) != b.get(name):
                    out.append(f"{f}[{name}]: rehearsed {a.get(name)!r} -> "
                               f"live {b.get(name)!r}")
            continue
        if a != b:
            out.append(f"{f}: rehearsed {a!r} -> live {b!r}")
    return out


def assert_invocation_equivalent(rehearsal: dict, live: dict) -> dict:
    """Refuse a launch whose effective invocation differs from its rehearsal.

    THE CLAIM A REHEARSAL MAKES, made checkable. "We rehearsed the launcher"
    only licenses an unattended night if the launcher then runs the same
    experiment — and on a repository where main changes all day, that is a
    claim about the last few hours, not a property of the code.

    An `UNAVAILABLE` value on EITHER side refuses even when the two strings
    match, because two unreadable hashes comparing equal is exactly how a
    missing input passes for agreement.
    """
    for side, man in (("rehearsal", rehearsal), ("live", live)):
        for f in EQUIVALENCE_FIELDS:
            v = man.get(f)
            if isinstance(v, str) and v.startswith("UNAVAILABLE"):
                raise LaunchRefused(
                    f"{side} manifest field {f!r} is {v}. Two unreadable "
                    f"values comparing equal is not equivalence — it is a "
                    f"missing input passing for agreement.")
            if f == "module_hashes" and isinstance(v, dict):
                bad = sorted(k for k, h in v.items()
                             if str(h).startswith("UNAVAILABLE"))
                if bad:
                    raise LaunchRefused(
                        f"{side} manifest could not hash {bad}. A module whose "
                        f"bytes cannot be read cannot be shown to be the same "
                        f"bytes the rehearsal ran.")
    diffs = manifest_differences(rehearsal, live)
    if diffs:
        raise LaunchRefused(
            "the live invocation is NOT the one that was rehearsed:\n  "
            + "\n  ".join(diffs)
            + "\n\nA rehearsal pins a launch only if the two run the same "
              "experiment. Re-rehearse, or launch from the frozen worktree so "
              "main can change without changing the night.")
    return {"equivalent": True, "fields_compared": list(EQUIVALENCE_FIELDS),
            "note": ("git_commit is deliberately NOT compared: a docs-only "
                     "commit moves the SHA and changes nothing that runs, and "
                     "refusing on it would train the operator to re-rehearse "
                     "for no reason. The module hashes carry the real claim.")}


def latest_rehearsal_manifest(launch_dir: Path | None = None) -> dict | None:
    """The manifest from the most recent REHEARSAL receipt, if there is one."""
    best = None
    for r in read_launch_receipts(launch_dir):
        if r.get("verdict") != VERDICT_REHEARSAL:
            continue
        man = r.get("launch_manifest")
        if isinstance(man, dict):
            if best is None or str(r.get("written_at_utc", "")) >= str(
                    best[0]):
                best = (r.get("written_at_utc", ""), man)
    return best[1] if best else None


def is_armed() -> bool:
    """Whether a real launch may proceed, read from the environment.

    The launcher is env-gated for the same reason lane seeding is: arming an
    unattended paid run is Murat's decision, and a session that could arm it by
    editing a constant is a session that can spend his money by refactoring.
    `--rehearse` and `--dry-run` never consult this.
    """
    return os.environ.get("AEGIS_IIF1_LAUNCHER_ARMED", "").strip() == "1"
