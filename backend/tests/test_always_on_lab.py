"""THE ALWAYS-ON LAB (chunk 14) — every loop mocked, nothing real touched.

Five things are pinned here and each of them is a failure somebody has already
paid for in this repository or is named in the spec as one that would be:

* **one instance, by PID AND by command line.** PID reuse is real on a
  long-uptime Windows box; liveness alone would report a stale lock as live the
  moment the OS handed that number to another program.
* **a refusal pauses, it does not kill.** A power plan that allows sleep pauses
  the GPU loops and says so; the news pull keeps running, and the next recheck
  can un-pause without a human restarting a scheduled task.
* **a stuck loop must not make the supervisor silent.** Each loop is issued
  from the top-level tick under a hard wall-clock box; a timeout freezes THAT
  loop's `last_tick_utc` while the heartbeat keeps advancing, which is the
  detectable divergence.
* **a loop that found nothing says so with a count.** `nothing_to_do` with an
  explicit `n`, never an omitted key — a card cannot tell an omitted key from a
  crash.
* **no order path, ever.** An AST walk over the module's executable source
  (docstrings and comments removed, per CLAUDE.md item 10) fails if a broker or
  order symbol appears in code rather than in prose.

Every test drives `tmp_path`. `config.DATA_DIR` and `always_on_lab.out_dir` are
the two seams that decide where anything lands, and both are replaced in a
fixture so no test can write into `backend/data/optimus` — on CI that directory
does not exist and has no business gaining one.

Dates are derived from `datetime.now(timezone.utc)` inside the test, never
written as a literal: a fixture that encodes a calendar moment fails the day
after it passes (CLAUDE.md rule 5).
"""

from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import config as _config
from backend.services import lab_budget
from scripts import always_on_lab as L

MODULE = Path(L.__file__).resolve()


# --------------------------------------------------------------------------
# fixtures


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """Redirect every path and stub every external probe.

    Returns the night directory, which is where the STOP file lives.
    """
    data = tmp_path / "data"
    (data / "optimus").mkdir(parents=True)
    night = data / "optimus" / "night_factory_test"
    night.mkdir()
    monkeypatch.setattr(_config, "DATA_DIR", data)
    monkeypatch.setattr(L, "out_dir", lambda: night)
    monkeypatch.setattr(L, "power_refusal", lambda: None)
    monkeypatch.setattr(L, "model_status", lambda: {
        "listening": False, "ready": False, "started_by_aegis": False,
        "foreign": False, "pid": None, "detail": "not running"})
    monkeypatch.setattr(L, "pid_alive", lambda pid: False)
    monkeypatch.setattr(L, "pid_names_lab", lambda pid: True)
    return night


@pytest.fixture
def stubbed_loops(monkeypatch):
    """Replace every loop handler with a counter, so the SCHEDULER is what is
    under test rather than any loop's own behaviour."""
    seen: dict[str, int] = {name: 0 for name, _ in L.LOOPS}

    def make(name):
        def _fn(state):
            seen[name] += 1
            return {"status": "ok", "n": 0}
        return _fn

    monkeypatch.setattr(L, "HANDLERS", {n: make(n) for n, _ in L.LOOPS})
    return seen


# --------------------------------------------------------------------------
# 1. cadence


def test_every_declared_loop_ticks_on_its_own_cadence(lab, stubbed_loops):
    """A loop advances when ITS period elapses, not on every heartbeat.

    The clock is injected rather than mocked globally: `tick(now=...)` takes the
    instant it is reasoning about, so this test needs no `freezegun` and cannot
    be broken by the suite taking a second longer than it used to.
    """
    t0 = datetime.now(timezone.utc)
    state = L.LabState()

    L.tick(state, now=t0)
    # first tick: nothing has ever run, so every loop is due exactly once
    assert all(v == 1 for v in stubbed_loops.values()), stubbed_loops

    # +5 minutes: only the 5-minute loops are due again
    L.tick(state, now=t0 + timedelta(minutes=5))
    due_at_5 = {n for n, p in L.PERIODS.items() if p <= 5}
    assert due_at_5, "the heartbeat loops must exist"
    for name, count in stubbed_loops.items():
        assert count == (2 if name in due_at_5 else 1), (name, count)

    # +15 minutes from t0: the quarter-hour loops join
    L.tick(state, now=t0 + timedelta(minutes=15))
    assert stubbed_loops["news_pull"] == 2
    assert stubbed_loops["decision_vs_reality"] == 1, "60-minute loop is not due"
    assert stubbed_loops["nn_lab"] == 1, "daily loop is not due"

    # +60 minutes: the hourly one joins, the daily ones still do not
    L.tick(state, now=t0 + timedelta(minutes=60))
    assert stubbed_loops["decision_vs_reality"] == 2
    assert stubbed_loops["nn_lab"] == 1
    assert stubbed_loops["catalyst_calendar"] == 1


def test_a_long_absence_runs_a_loop_once_not_once_per_missed_period(lab, stubbed_loops):
    """Six hours away is ONE news pull, not twenty-four.

    Catching up burns the budget on stale data for no benefit. It falls out of
    storing the last SUCCESSFUL tick rather than a schedule of missed firings,
    and this test is what stops a future edit from adding the schedule.
    """
    t0 = datetime.now(timezone.utc)
    state = L.LabState()
    L.tick(state, now=t0)
    L.tick(state, now=t0 + timedelta(hours=6))
    assert stubbed_loops["news_pull"] == 2


# --------------------------------------------------------------------------
# 2-3. the single-instance lock


def test_a_second_instance_refuses(lab, monkeypatch):
    """A live PID whose command line still names the lab holds the lock."""
    monkeypatch.setattr(L, "pid_alive", lambda pid: True)
    monkeypatch.setattr(L, "pid_names_lab", lambda pid: True)
    L.lock_path().write_text(json.dumps(
        {"pid": 4242, "started_utc": L._now(), "hostname": "other",
         "started_by": "always_on_lab"}), encoding="utf-8")

    with pytest.raises(L.AlreadyRunning) as exc:
        L.acquire_lock()
    assert "ALREADY_RUNNING" in str(exc.value)
    assert "4242" in str(exc.value)
    # the lock was NOT overwritten
    assert json.loads(L.lock_path().read_text(encoding="utf-8"))["pid"] == 4242

    assert L.main(["--ticks", "1"]) == 2


def test_a_stale_lock_is_overwritten(lab, monkeypatch):
    """A dead PID's lock is taken, and the overwrite is recorded, not silent."""
    monkeypatch.setattr(L, "pid_alive", lambda pid: False)
    L.lock_path().write_text(json.dumps(
        {"pid": 4242, "started_utc": L._now(), "started_by": "always_on_lab"}),
        encoding="utf-8")

    rec = L.acquire_lock()
    assert rec["pid"] != 4242
    assert rec["overwrote"]["pid"] == 4242
    assert "not alive" in rec["overwrote_why"]


def test_pid_reuse_is_a_stale_lock_not_a_live_one(lab, monkeypatch):
    """Alive, but the command line names something else: STALE.

    Without the command-line half, a long-uptime box that recycled PID 4242 into
    a text editor would refuse to ever start the lab again.
    """
    monkeypatch.setattr(L, "pid_alive", lambda pid: True)
    monkeypatch.setattr(L, "pid_names_lab", lambda pid: False)
    L.lock_path().write_text(json.dumps({"pid": 4242, "started_by": "always_on_lab"}),
                             encoding="utf-8")
    holder = L.lock_holder()
    assert holder["state"] == "stale"
    assert "PID reuse" in holder["why"]


def test_a_missing_probe_refuses_to_start_a_second_supervisor(lab, monkeypatch):
    """CANNOT DETERMINE on the command-line probe is treated as HELD.

    The conservative direction for a single-instance rule is to refuse, not to
    start a second copy on a maybe — two supervisors racing the same news
    cursor is the failure the lock exists for.
    """
    monkeypatch.setattr(L, "pid_alive", lambda pid: True)
    # the real probe returns True when PowerShell did not run or printed nothing
    monkeypatch.setattr(L, "pid_names_lab", lambda pid: True)
    L.lock_path().write_text(json.dumps({"pid": 4242}), encoding="utf-8")
    assert L.lock_holder()["state"] == "held"


# --------------------------------------------------------------------------
# 4. the power plan


def test_sleeping_power_plan_pauses_gpu_loops_not_the_news_pull(lab, stubbed_loops,
                                                                monkeypatch):
    """The GPU loops pause and SAY so; the network-only loops keep running.

    The task does not ask for the news pull to stop because sleep is allowed —
    only that the supervisor refuses to START a GPU job into a machine that
    might suspend mid-job.
    """
    monkeypatch.setattr(L, "power_refusal",
                        lambda: "REFUSED: the active power plan sleeps after 1800s on AC")
    state = L.LabState()
    payload = L.tick(state, now=datetime.now(timezone.utc))

    for name in L.MODEL_LOOPS:
        row = payload["loops"][name]
        assert row["status"] == "paused", (name, row)
        assert "POWER_PLAN_ALLOWS_SLEEP" in row["detail"]
        assert row["paused_since_utc"]
        assert row["last_tick_utc"] is None, "a paused loop did not tick"
        assert stubbed_loops[name] == 0, f"{name} ran into a machine that may sleep"

    assert payload["loops"]["news_pull"]["status"] == "ok"
    assert stubbed_loops["news_pull"] == 1
    assert payload["power_refusal"].startswith("REFUSED")
    assert payload["running"] is True, "a power refusal pauses; it does not kill"


def test_the_power_plan_is_rechecked_on_a_cadence_not_only_at_boot(lab, monkeypatch):
    """A plan that was 'never sleep' at 09:00 can change by 15:00."""
    calls = {"n": 0}

    def _probe():
        calls["n"] += 1
        return None if calls["n"] == 1 else "REFUSED: sleeps after 900s"

    monkeypatch.setattr(L, "power_refusal", _probe)
    monkeypatch.setattr(L, "HANDLERS", {n: (lambda s: {"status": "ok", "n": 0})
                                        for n, _ in L.LOOPS})
    t0 = datetime.now(timezone.utc)
    state = L.LabState()
    L.tick(state, now=t0)
    assert calls["n"] == 1 and state.power_refusal is None

    L.tick(state, now=t0 + timedelta(minutes=5))
    assert calls["n"] == 1, "rechecked before its own period elapsed"

    L.tick(state, now=t0 + timedelta(minutes=L.POWER_RECHECK_MINUTES + 1))
    assert calls["n"] == 2
    assert state.power_refusal.startswith("REFUSED")


def test_a_raising_power_probe_is_cannot_determine_not_a_crash(lab, monkeypatch):
    monkeypatch.setattr(L, "power_refusal",
                        lambda: (_ for _ in ()).throw(OSError("powercfg is gone")))
    monkeypatch.setattr(L, "HANDLERS", {n: (lambda s: {"status": "ok", "n": 0})
                                        for n, _ in L.LOOPS})
    state = L.LabState()
    payload = L.tick(state, now=datetime.now(timezone.utc))
    assert state.power_refusal is None
    assert payload["loops"]["l2_typing"]["status"] == "ok"


# --------------------------------------------------------------------------
# the STOP file and the stuck-loop watchdog


def test_the_stop_file_ends_the_loop_and_says_who_stopped_it(lab, stubbed_loops):
    (lab / "STOP").write_text("stop", encoding="utf-8")
    payload = L.run_forever(max_ticks=5, sleeper=lambda s: None)
    assert payload["running"] is False
    assert payload["stopped_by"] == "STOP_file"
    assert all(v == 0 for v in stubbed_loops.values()), "a loop ran after STOP"
    assert json.loads(L.status_path().read_text(encoding="utf-8"))["stopped_by"] \
        == "STOP_file"


def test_a_stuck_loop_freezes_its_own_stamp_and_not_the_heartbeat(lab, monkeypatch):
    """The supervisor's `utc` advances; the stuck loop's `last_tick_utc` does not.

    That divergence is the whole signal. A supervisor that awaited the stuck
    call would go silent instead, and silence is never success.
    """
    import threading as _t
    gate = _t.Event()

    def _wedged(state):
        gate.wait(30)
        return {"status": "ok"}

    handlers = {n: (lambda s: {"status": "ok", "n": 0}) for n, _ in L.LOOPS}
    handlers["news_pull"] = _wedged
    monkeypatch.setattr(L, "HANDLERS", handlers)
    monkeypatch.setitem(L.TIMEOUTS, "news_pull", 0.2)

    t0 = datetime.now(timezone.utc)
    state = L.LabState()
    try:
        payload = L.tick(state, now=t0)
        row = payload["loops"]["news_pull"]
        assert row["status"] == "timeout"
        assert row["detail"].startswith("timeout_after_")
        assert row["last_tick_utc"] is None
        assert payload["loops"]["status"]["last_tick_utc"] is not None, \
            "the heartbeat kept advancing"

        # the wedged loop is NOT re-issued while it is still out there
        payload = L.tick(state, now=t0 + timedelta(minutes=20))
        assert payload["loops"]["news_pull"]["status"] == "timeout"
        assert "not re-issued" in payload["loops"]["news_pull"]["detail"]
    finally:
        gate.set()


def test_a_raising_loop_is_an_error_row_not_a_dead_supervisor(lab, monkeypatch):
    handlers = {n: (lambda s: {"status": "ok", "n": 0}) for n, _ in L.LOOPS}
    handlers["l2_typing"] = lambda s: (_ for _ in ()).throw(ValueError("boom"))
    monkeypatch.setattr(L, "HANDLERS", handlers)
    payload = L.tick(L.LabState(), now=datetime.now(timezone.utc))
    assert payload["loops"]["l2_typing"]["status"] == "error"
    assert "ValueError: boom" in payload["loops"]["l2_typing"]["detail"]
    assert payload["loops"]["news_pull"]["status"] == "ok", "one loop did not stop the rest"


# --------------------------------------------------------------------------
# 13. silence is never success


def test_every_declared_loop_has_a_block_every_tick(lab, stubbed_loops):
    payload = L.tick(L.LabState(), now=datetime.now(timezone.utc))
    for name, what in L.LOOPS:
        row = payload["loops"][name]
        assert row["what"] == what
        assert "status" in row and "last_tick_utc" in row
    assert set(payload["loops"]) == {n for n, _ in L.LOOPS}


def test_the_status_file_carries_spend_and_the_cap_every_tick(lab):
    payload = L.tick(L.LabState(), now=datetime.now(timezone.utc))
    assert payload["spend_today_usd"] == 0.0
    assert payload["spend_cap_usd"] == lab_budget.cap_usd()
    assert payload["spend_cap_reached"] is False


def test_the_status_file_is_written_atomically(lab, stubbed_loops):
    L.tick(L.LabState(), now=datetime.now(timezone.utc))
    assert L.status_path().exists()
    assert not L.status_path().with_suffix(".json.tmp").exists()


def test_state_is_carried_across_a_restart(lab, stubbed_loops):
    t0 = datetime.now(timezone.utc)
    state = L.LabState()
    L.tick(state, now=t0)
    revived = L.LabState.load()
    assert revived.loops["news_pull"]["last_tick_utc"] is not None
    assert not revived.due("news_pull", t0 + timedelta(minutes=1))
    assert revived.due("news_pull", t0 + timedelta(minutes=16))


# --------------------------------------------------------------------------
# the declared surface, and the things it must never do


def test_declared_loops_periods_handlers_and_boxes_agree():
    names = {n for n, _ in L.LOOPS}
    assert set(L.PERIODS) == names
    assert set(L.TIMEOUTS) == names
    assert set(L.HANDLERS) == names
    assert L.MODEL_LOOPS <= names


def executable_source(path: Path) -> str:
    """The module's code with every docstring removed.

    Three tests in this repository failed on their first run by matching the
    prose that EXPLAINS a banned pattern. A grep-shaped guard that cannot tell
    an explanation from an instance is a broken guard (CLAUDE.md item 10).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def _dotted(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def call_targets(path: Path) -> set[str]:
    """Every dotted name this module CALLS. What it does, not what it says."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {_dotted(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)} - {""}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module)
    return out


def call_string_args(path: Path) -> list[str]:
    """String constants passed to a call — EXCEPT to `print`.

    The exception is the whole point. `_print_schtasks` prints the rule "never
    `taskkill /F /IM python.exe`" to a human, and a guard that cannot tell that
    sentence from an invocation would force the next reader to delete the
    rationale to make the suite green (CLAUDE.md item 10, third instance).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call) or _dotted(n.func) == "print":
            continue
        for arg in list(n.args) + [k.value for k in n.keywords]:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    out.append(sub.value)
    return out


@pytest.mark.parametrize("banned", [
    "submit_order", "place_order", "TradingClient",
    "llama_server.start", "llama_server.stop", "start", "stop",
])
def test_the_supervisor_calls_no_order_path_and_starts_no_model_server(banned):
    """What the module CALLS, read from the AST — never a grep over its prose."""
    offenders = {t for t in call_targets(MODULE)
                 if t == banned or t.endswith("." + banned)}
    # the supervisor's own thread lifecycle is allowed to call `start`; a MODEL
    # server's is not, and the two are told apart by the receiver, not the verb.
    offenders -= {"t.start", "threading.Thread.start"}
    assert not offenders, (
        f"{sorted(offenders)} — the lab places no order and is never the "
        f"process that starts or stops the model server.")


def test_the_supervisor_imports_no_broker_module():
    bad = [m for m in imported_modules(MODULE)
           if any(w in m.lower() for w in ("alpaca", "broker", "trading_client"))]
    assert not bad, bad


def test_no_kill_by_image_name_is_ever_invoked():
    """CLAUDE.md rule 6. The PRINTED warning is allowed; a call is not."""
    for s in call_string_args(MODULE):
        low = s.lower()
        assert "taskkill" not in low, s
        assert "/im " not in low, s


def test_the_supervisor_imports_the_sleep_guard_rather_than_copying_it():
    src = MODULE.read_text(encoding="utf-8")
    assert "from scripts.night_factory import refuse_if_the_machine_may_sleep" in src
    assert "powercfg" not in executable_source(MODULE), \
        "a second powercfg parser would drift from night_factory's"


def test_no_test_in_this_file_encodes_a_calendar_moment():
    """CLAUDE.md rule 5, applied to this file itself.

    A literal `2026-09-13` in a fixture passes today and fails tomorrow. The
    check is on the DIGITS, so it also catches a date written into a path.
    """
    import re
    src = Path(__file__).read_text(encoding="utf-8")
    body = executable_source(Path(__file__))
    for match in re.findall(r"20\d\d-\d\d-\d\d", body):
        raise AssertionError(f"literal date {match!r} in executable test source")
    assert "datetime.now" in src
