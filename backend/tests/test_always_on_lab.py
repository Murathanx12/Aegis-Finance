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
fixture so no test can write into the repository's own optimus data
directory — on CI that directory does not exist and has no business gaining one.

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
    """Redirect every path, stub every external probe, and REPLACE EVERY LOOP.

    The loop replacement is not tidiness. While this file was being written the
    fixture stubbed only the paths, and the first test that called `tick()`
    without the loop stubs ran the REAL news pull — eighteen registered sources,
    paced, against a live daily pass — inside the offline fast suite. It hung.
    A fixture that redirects where a driver writes but not what it calls is half
    a fixture: `HANDLERS` is the other half of the seam and belongs here, where
    no test can forget it.

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
    # nothing scheduled is running; individual tests override this. The real
    # probe launches PowerShell, which the offline suite must never do.
    monkeypatch.setattr(L, "running_drivers", lambda now=None: {
        "scan_ran": True, "scanned": 0,
        **{name: [] for name in L.SCHEDULED_DRIVERS}})
    monkeypatch.setattr(L, "HANDLERS",
                        {n: (lambda s: {"status": "ok", "n": 0}) for n, _ in L.LOOPS})
    # the spend ledger and the reader choice live under DATA_DIR too
    monkeypatch.delenv("AEGIS_L2_READER", raising=False)
    monkeypatch.delenv(_config.LAB_SPEND_CAP_ENV, raising=False)
    return night


class FakeSource:
    """The four registry fields the cadence check reads. Nothing else."""

    def __init__(self, sid, min_interval_s=1.0, queries=(), rate_limit="none observed"):
        self.id = sid
        self.min_interval_s = min_interval_s
        self.queries = tuple(queries)
        self.rate_limit = rate_limit


@pytest.fixture
def stubbed_loops(lab, monkeypatch):
    """Counting loop handlers, so the SCHEDULER is what is under test.

    Depends on `lab` so the counters replace the fixture's own stubs rather than
    racing them — and so no test can reach a counter without also having the
    paths redirected.
    """
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
# loop 1 — the live news pull


def test_the_news_pull_calls_pull_all_with_the_admitted_sources(lab, monkeypatch):
    seen: dict = {}

    def _pull(**kw):
        seen.update(kw)
        return {"rows_new": 12, "red": [], "refused": [], "sources": 2,
                "resolution_rate": 0.5, "headline": "12 new rows"}

    monkeypatch.setattr(L, "news_sources",
                        lambda: [FakeSource("fast"), FakeSource("also_fast")])
    monkeypatch.setattr(L, "pull_news", _pull)
    out = L.loop_news_pull(L.LabState())
    assert out["status"] == "ok"
    assert out["n"] == 12 and out["rows_new"] == 12
    assert seen["source_ids"] == ["fast", "also_fast"]


def test_a_source_whose_declared_spacing_exceeds_the_cadence_is_skipped_by_name(
        lab, monkeypatch):
    """A cadence table with an unstated exception is not a cadence table.

    Six queries at 20 s is a 120 s floor and fits a 15-minute cadence; the same
    source with 200 queries does not, and is skipped with the reason ON the row
    rather than quietly pulled less often than the registry declares.
    """
    slow = FakeSource("greedy", min_interval_s=20.0, queries=tuple(range(200)))
    row = L.cadence_admits(slow, L.PERIODS["news_pull"])
    assert row["admitted"] is False
    assert row["why"] == "rate_limit_would_be_breached_at_this_cadence"
    assert "4000s" in row["detail"] or "4,000" in row["detail"] or "s of declared" in row["detail"]

    monkeypatch.setattr(L, "news_sources", lambda: [slow, FakeSource("ok")])
    monkeypatch.setattr(L, "pull_news", lambda **kw: {
        "rows_new": 1, "red": [], "refused": [], "headline": "1"})
    out = L.loop_news_pull(L.LabState())
    assert [s["source"] for s in out["sources_skipped"]] == ["greedy"]


def test_a_budget_smaller_than_the_cadence_demands_is_skipped(lab):
    row = L.cadence_admits(FakeSource("tiny", rate_limit="10 requests per day"),
                           L.PERIODS["news_pull"])
    assert row["admitted"] is False
    assert row["declared_budget_per_day"] == 10.0


def test_an_unparseable_rate_limit_is_cannot_determine_not_a_skip(lab):
    """A refusal needs evidence just as a positive does.

    Fourteen of the eighteen registered sources say "none observed" or
    "unknown"; skipping every one of them because prose is prose would stop the
    corpus and call it caution.
    """
    row = L.cadence_admits(FakeSource("prose", rate_limit="none observed"),
                           L.PERIODS["news_pull"])
    assert row["admitted"] is True
    assert row["budget_parsed"] is False
    assert "CANNOT DETERMINE" in row["why"]


def test_the_news_pull_yields_to_a_running_daily_pass(lab, monkeypatch):
    """`daily_pass` owns 06:30 and pulls every source itself.

    Detected from the process table, never from a guessed wall-clock window: a
    daily pass running late is still running, whatever time it is.
    """
    monkeypatch.setattr(L, "running_drivers", lambda now=None: {
        "scan_ran": True, "daily_pass": [777], "night_factory": [],
        "monday_night": []})
    monkeypatch.setattr(L, "pull_news", lambda **kw: pytest.fail(
        "a second concurrent pull re-hits every source's rate limit"))
    out = L.loop_news_pull(L.LabState())
    assert out["status"] == "skipped"
    assert out["reason"] == "DAILY_PASS_RUNNING"
    assert out["pids"] == [777]


def test_an_empty_pull_is_nothing_to_do_with_a_count_not_silence(lab, monkeypatch):
    monkeypatch.setattr(L, "news_sources", lambda: [FakeSource("quiet")])
    monkeypatch.setattr(L, "pull_news", lambda **kw: {
        "rows_new": 0, "red": [], "refused": [], "headline": "0 new rows"})
    out = L.loop_news_pull(L.LabState())
    assert out["status"] == "nothing_to_do"
    assert out["n"] == 0
    assert out["sources_red"] == []


def test_red_sources_reach_the_status_file_by_name(lab, monkeypatch):
    monkeypatch.setattr(L, "news_sources", lambda: [FakeSource("dead")])
    monkeypatch.setattr(L, "pull_news", lambda **kw: {
        "rows_new": 0, "red": ["dead"], "refused": [], "headline": "0"})
    handlers = dict(L.HANDLERS)
    handlers = {n: (lambda s: {"status": "ok", "n": 0}) for n, _ in L.LOOPS}
    handlers["news_pull"] = L.loop_news_pull
    monkeypatch.setattr(L, "HANDLERS", handlers)
    payload = L.tick(L.LabState(), now=datetime.now(timezone.utc))
    assert payload["loops"]["news_pull"]["sources_red"] == ["dead"]


def test_an_unreadable_registry_refuses_by_name(lab, monkeypatch):
    monkeypatch.setattr(L, "news_sources", lambda: (_ for _ in ()).throw(
        ValueError("news_sources.yaml is malformed")))
    out = L.loop_news_pull(L.LabState())
    assert out["status"] == "refused"
    assert out["reason"] == "REGISTRY_UNREADABLE"


# --------------------------------------------------------------------------
# loop 2 — the typing loop and the model server it must never start


class SpyServer:
    """A stand-in for `llama_server` that RECORDS a start or a stop.

    The assertion is on the mock's call count, not on the module's source: a
    file-level AST check says the symbol is absent, and this says the CALL never
    happened at run time. Both, because they fail for different reasons.
    """

    def __init__(self, **status):
        self._status = status
        self.starts = 0
        self.stops = 0

    def status(self):
        return dict(self._status)

    def start(self, *a, **k):
        self.starts += 1
        raise AssertionError("the lab started the model server")

    def stop(self, *a, **k):
        self.stops += 1
        raise AssertionError("the lab stopped the model server")


def test_foreign_llama_server_is_used_not_started(lab, monkeypatch):
    """A server already running when Aegis started is not ours to stop.

    It IS ours to read from, and the typing loop does exactly that: `status()`
    once per model-touching tick, then the reader, and never a `start()`.
    """
    spy = SpyServer(listening=True, ready=True, started_by_aegis=False,
                    foreign=True, pid=9981, detail="ready as PID 9981, started OUTSIDE Aegis")
    monkeypatch.setattr(L, "model_status", spy.status)
    typed: dict = {}

    def _type(**kw):
        typed.update(kw)
        return {"status": "ok", "rows_typed": 7, "usage": {"cost_usd": 0.0},
                "corpus": {"rows_waiting": 5980, "rows_on_disk": 6020},
                "headline": "7 typed"}

    monkeypatch.setattr(L, "type_rows", _type)
    out = L.loop_l2_typing(L.LabState())
    assert out["status"] == "ok"
    assert out["n"] == 7 and out["backlog_remaining"] == 5980
    assert out["llama_server_foreign"] is True
    assert typed["backend"] == "local"
    assert spy.starts == 0 and spy.stops == 0


def test_no_server_means_pending_model_not_a_crash(lab, monkeypatch):
    spy = SpyServer(listening=False, ready=False, started_by_aegis=False,
                    foreign=False, pid=None, detail="not running")
    monkeypatch.setattr(L, "model_status", spy.status)
    monkeypatch.setattr(L, "type_rows", lambda **kw: pytest.fail(
        "the reader was called with nothing listening"))
    out = L.loop_l2_typing(L.LabState())
    assert out["status"] == "PENDING_MODEL"
    assert out["n"] == 0
    assert out["llama_server_up"] is False
    assert spy.starts == 0


def test_the_typing_loop_refuses_a_cloud_reader_that_does_not_exist(lab, monkeypatch):
    monkeypatch.setenv("AEGIS_L2_READER", "cloud")
    monkeypatch.setattr(L, "type_rows", lambda **kw: pytest.fail(
        "a refused cloud reader fell back to typing rows anyway"))
    out = L.loop_l2_typing(L.LabState())
    assert out["status"] == "refused"
    assert out["reason"] == "CLOUD_READER_NOT_IMPLEMENTED"


def test_the_typing_loop_records_a_model_call_so_the_gpu_can_be_called_idle(
        lab, monkeypatch):
    monkeypatch.setattr(L, "model_status", SpyServer(
        listening=True, ready=True, foreign=False, started_by_aegis=True).status)
    monkeypatch.setattr(L, "type_rows", lambda **kw: {
        "status": "ok", "rows_typed": 1, "corpus": {"rows_waiting": 0},
        "usage": {"cost_usd": 0.0}})
    state = L.LabState()
    now = datetime.now(timezone.utc)
    assert state.idle_minutes(now) is None, "never called is not the same as idle"
    L.loop_l2_typing(state)
    assert state.last_model_call_utc is not None
    assert state.idle_minutes(now + timedelta(minutes=30)) >= 29


def test_an_empty_backlog_is_nothing_to_do(lab, monkeypatch):
    monkeypatch.setattr(L, "model_status", SpyServer(
        listening=True, ready=True, foreign=False, started_by_aegis=True).status)
    monkeypatch.setattr(L, "type_rows", lambda **kw: {
        "status": "done", "rows_typed": 0, "corpus": {"rows_waiting": 0},
        "verdict": "NOTHING TO DO"})
    out = L.loop_l2_typing(L.LabState())
    assert out["status"] == "nothing_to_do"
    assert out["n"] == 0 and out["backlog_remaining"] == 0


def test_the_typing_loop_bounds_one_tick(lab, monkeypatch):
    """One tick must not try to type a 6,020-row backlog and block the pull."""
    monkeypatch.setattr(L, "model_status", SpyServer(
        listening=True, ready=True, foreign=False, started_by_aegis=True).status)
    seen: dict = {}
    monkeypatch.setattr(L, "type_rows", lambda **kw: seen.update(kw) or {
        "status": "ok", "rows_typed": 1, "corpus": {"rows_waiting": 10}})
    L.loop_l2_typing(L.LabState())
    assert seen["max_rows"] == _config.LAB_L2_MAX_ROWS_PER_TICK
    assert seen["max_rows"] < 6020


# --------------------------------------------------------------------------
# loop 4 — the catalyst calendar


def test_the_calendar_loop_ships_macro_even_when_the_tickers_cannot_be_read(
        lab, monkeypatch):
    """A per-ticker half that cannot load must not take the macro half down."""
    monkeypatch.setattr(L, "calendar_tickers", lambda: (_ for _ in ()).throw(
        RuntimeError("no book on disk")))
    from backend.services import macro_calendar
    today = datetime.now(timezone.utc).date()
    monkeypatch.setattr(macro_calendar, "macro_block", lambda **kw: {
        "macro": [{"kind": "CPI",
                   "event_time": (today + timedelta(days=9)).isoformat(),
                   "engine_probability": None, "probability_status": "AWAITING_L2"}],
        "legs": {"CPI": "1 date(s)"}, "refusals": [],
        "fomc_table": {"status": "FOMC_SCHEDULE_NOT_SEEDED"}})

    out = L.loop_catalyst_calendar(L.LabState())
    assert out["status"] == "ok"
    assert out["macro_events"] == 1 and out["ticker_events"] == 0
    assert "TICKERS_CANNOT_DETERMINE" in out["refusals"][0]
    assert "AWAITING_L2" in out["headline"]
    assert (lab / f"lab_catalyst_calendar_{L.run_date()}.json").exists()


def test_the_calendar_loop_names_every_refused_leg(lab, monkeypatch):
    monkeypatch.setattr(L, "calendar_tickers", lambda: [])
    from backend.services import macro_calendar
    monkeypatch.setattr(macro_calendar, "macro_block", lambda **kw: {
        "macro": [], "legs": {"CPI": "REFUSED"},
        "refusals": [{"kind": "CPI", "refusal": "FRED_KEY_ABSENT"}],
        "fomc_table": {"status": "FOMC_SCHEDULE_NOT_SEEDED"}})
    out = L.loop_catalyst_calendar(L.LabState())
    assert out["status"] == "refused"
    assert out["refusals"] == ["FRED_KEY_ABSENT"]
    assert out["n"] == 0


# --------------------------------------------------------------------------
# loop 6 — the idle-GPU queue


def _idle_state(minutes_ago: float | None = 60.0) -> L.LabState:
    state = L.LabState()
    if minutes_ago is not None:
        state.last_model_call_utc = (
            datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
        ).isoformat(timespec="seconds")
    return state


def test_idle_gpu_queue_yields_to_a_running_night_factory(lab, monkeypatch):
    """The idle queue fills the GAPS the evening run does not cover. It is not
    a second scheduler for the same jobs."""
    monkeypatch.setattr(L, "running_drivers", lambda now=None: {
        "scan_ran": True, "night_factory": [4321], "daily_pass": [],
        "monday_night": []})
    monkeypatch.setattr(L, "dispatch_job", lambda job, minutes: pytest.fail(
        f"double-dispatched {job} while the night factory was running"))
    out = L.loop_idle_gpu_queue(_idle_state())
    assert out["status"] == "skipped"
    assert out["reason"] == "NIGHT_FACTORY_ALREADY_RUNNING"
    assert out["pids"] == [4321]


def test_idle_gpu_queue_yields_to_an_attended_monday_night(lab, monkeypatch):
    monkeypatch.setattr(L, "running_drivers", lambda now=None: {
        "scan_ran": True, "night_factory": [], "daily_pass": [],
        "monday_night": [99]})
    monkeypatch.setattr(L, "dispatch_job", lambda job, minutes: pytest.fail("no"))
    out = L.loop_idle_gpu_queue(_idle_state())
    assert out["reason"] == "MONDAY_NIGHT_RUNNING"


def test_a_busy_gpu_is_a_named_skip_not_a_dispatch(lab, monkeypatch):
    monkeypatch.setattr(L, "dispatch_job", lambda job, minutes: pytest.fail("no"))
    out = L.loop_idle_gpu_queue(_idle_state(minutes_ago=2.0))
    assert out["status"] == "skipped" and out["reason"] == "GPU_BUSY"
    assert out["idle_minutes"] == pytest.approx(2.0, abs=0.2)


def test_a_foreign_server_blocks_the_idle_queue(lab, monkeypatch):
    """A server Aegis did not start may be mid-job, and is not ours to interrupt."""
    monkeypatch.setattr(L, "model_status", lambda: {
        "listening": True, "ready": True, "foreign": True, "pid": 9981,
        "started_by_aegis": False})
    monkeypatch.setattr(L, "dispatch_job", lambda job, minutes: pytest.fail("no"))
    out = L.loop_idle_gpu_queue(_idle_state())
    assert out["reason"] == "FOREIGN_SERVER_UP"
    assert "9981" in out["detail"]


def test_the_idle_queue_dispatches_in_the_declared_order_once_each_per_day(
        lab, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(L, "dispatch_job", lambda job, minutes: calls.append(job) or {
        "verdict": "OK", "headline": f"{job} done"})
    state = _idle_state()
    declared = [j for j, _ in _config.LAB_IDLE_QUEUE]

    for expected in declared:
        out = L.loop_idle_gpu_queue(state)
        assert out["status"] == "ok" and out["job"] == expected, out
        state.last_model_call_utc = (
            datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat(
                timespec="seconds")

    assert calls == declared, "the queue ran out of its declared order"
    out = L.loop_idle_gpu_queue(state)
    assert out["status"] == "nothing_to_do"
    assert out["reason"] == "EVERY_QUEUED_JOB_ALREADY_RAN_TODAY"


def test_l2_runs_first_because_it_is_the_biggest_measured_gap():
    assert _config.LAB_IDLE_QUEUE[0][0] == "L2_typed_events", (
        "every other queued job either consumes L2's output or is orthogonal "
        "to it, and the backlog is the single biggest measured gap")


def test_every_queued_job_exists_in_the_factorys_own_registry():
    from scripts.night_factory_jobs import JOBS
    for job, minutes in _config.LAB_IDLE_QUEUE:
        assert job in JOBS, f"{job} is not a registered night-factory job"
        assert minutes > 0


def test_a_failing_job_is_not_re_dispatched_every_five_minutes(lab, monkeypatch):
    """One broken job must not starve the rest of the queue."""
    def _boom(job, minutes):
        raise RuntimeError("the job died")

    monkeypatch.setattr(L, "dispatch_job", _boom)
    state = _idle_state()
    out = L.loop_idle_gpu_queue(state)
    assert out["status"] == "error"
    first = _config.LAB_IDLE_QUEUE[0][0]
    assert out["dispatched_on"][first] == L.run_date()
    assert first not in out["queue_remaining"]


# --------------------------------------------------------------------------
# the LEARNED line and the acceptance receipt


def test_the_learned_line_is_written_every_day_whatever_happened(lab, stubbed_loops):
    payload = L.tick(L.LabState(), now=datetime.now(timezone.utc))
    p = L.data_dir() / "brain" / f"LEARNED_{L.run_date()}.md"
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert text.startswith("> Always-on lab")
    assert "spend $0.00" in text
    assert "cap" in text


def test_the_learned_line_is_not_duplicated_by_a_second_tick(lab, stubbed_loops):
    t0 = datetime.now(timezone.utc)
    state = L.LabState()
    L.tick(state, now=t0)
    L.tick(state, now=t0 + timedelta(seconds=1))
    p = L.data_dir() / "brain" / f"LEARNED_{L.run_date()}.md"
    lines = [x for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(lines) == 1, lines


def test_acceptance_is_built_unaccepted_until_three_dates_carry_evidence(lab):
    report = L.acceptance_report()
    assert report["accepted"] is False
    assert report["status"] == "BUILT_UNACCEPTED"
    assert report["dates_required"] == _config.LAB_ACCEPTANCE_DATES
    assert len(report["dates_examined"]) == _config.LAB_ACCEPTANCE_DATES
    assert report["dates_with_evidence"] == []
    assert "fabricated acceptance receipt" in report["read_me_first"]


def test_acceptance_counts_dates_not_task_runs(lab):
    """ONLOGON can fire and die repeatedly in a bad state and still produce
    three "runs". The bar is three DATES with evidence on disk."""
    today = datetime.now(timezone.utc).date()
    for i in range(_config.LAB_ACCEPTANCE_DATES):
        day = (today - timedelta(days=i)).isoformat()
        folder = L.data_dir() / f"night_factory_{day}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"decision_vs_reality_{day}.json").write_text("{}", encoding="utf-8")
        (folder / f"lab_catalyst_calendar_{day}.json").write_text("{}", encoding="utf-8")
        brain = L.data_dir() / "brain"
        brain.mkdir(parents=True, exist_ok=True)
        (brain / f"LEARNED_{day}.md").write_text("> Always-on lab, x\n",
                                                 encoding="utf-8")
    report = L.acceptance_report()
    assert len(report["dates_with_evidence"]) == _config.LAB_ACCEPTANCE_DATES
    assert report["checks"]["decision_vs_reality_per_date"] is True
    assert report["checks"]["learned_line_present"] is True
    # still not ACCEPTED: two checks are honestly CANNOT DETERMINE
    assert report["accepted"] is False
    assert report["status"] == "BUILT_NOT_YET_PASSING"
    assert "CANNOT DETERMINE" in report["checks"]["news_pull_never_gapped"]


def test_every_declared_acceptance_criterion_has_a_check(lab):
    report = L.acceptance_report()
    assert set(report["checks"]) == {k for k, _ in L.ACCEPTANCE_CRITERIA}


def test_the_acceptance_receipt_is_written_into_the_night_folder(lab):
    p = L.write_acceptance()
    assert p.name == f"always_on_lab_acceptance_{L.run_date()}.json"
    assert json.loads(p.read_text(encoding="utf-8"))["receipt"] == \
        "always_on_lab_acceptance"


def test_the_schtasks_line_is_onlogon_limited_and_runs_nothing(capsys):
    assert L.main(["--schtasks"]) == 0
    out = capsys.readouterr().out
    assert '/SC ONLOGON' in out
    # 2026-09-13: the form that registers WITHOUT elevation is printed first
    assert 'Startup' in out and 'always_on_lab.cmd' in out and 'WScript.Shell' in out
    assert '/RL LIMITED' in out
    assert '/TN "AegisAlwaysOnLab"' in out
    assert "schtasks /Create" in out and "schtasks /Change" in out
    # Only the COMMAND lines are checked, not the prose around them: the printed
    # rationale explains why `< NUL` does not work, and a check over the whole
    # page would fail on the explanation — the same trap that caught the AST
    # guard in this file and three other tests in this repository.
    cmds = [ln for ln in out.splitlines() if ln.strip().startswith("schtasks ")]
    assert len(cmds) == 2
    for cmd in cmds:
        # 2026-09-13: /TR is capped at 261 characters, so the command line points
        # at the wrapper and the wrapper carries the redirects.
        assert "always_on_lab.cmd" in cmd
        assert "| tail" not in cmd, "a pipe eats the exit code, and the code is the guard"
    body = [ln for ln in out.splitlines() if "-m scripts.always_on_lab" in ln and "schtasks" not in ln]
    assert body, "the wrapper body must be printed"
    for ln in body:
        assert "< " in ln, "the stdin redirect is load-bearing"
        assert "NUL" not in ln, "it must come from a REGULAR file, not NUL"
        assert "empty_stdin.txt" in ln


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


def test_a_metered_tick_that_reports_zero_books_the_estimate_and_says_so(
        lab, monkeypatch):
    """MEASURED defect: the 17:18 DeepSeek run typed 6,007 rows and printed
    `llm_spend_usd: 0.00` while the call ledger said $2.04.

    The loop substitutes the estimate — and SAYS which of the two it booked.
    A silently substituted number is the failure the substitution exists to
    prevent, wearing the other hat.
    """
    monkeypatch.setenv("AEGIS_L2_READER", "deepseek")
    from backend.services import lab_reader
    monkeypatch.setattr(lab_reader, "provider_configured", lambda name: True)
    monkeypatch.setattr(L, "type_rows", lambda **kw: {
        "status": "ok", "rows_typed": 100, "usage": {"cost_usd": 0.0},
        "corpus": {"rows_waiting": 5900}})

    out = L.loop_l2_typing(L.LabState())
    assert out["status"] == "ok" and out["n"] == 100
    assert out["cost_source"] == "estimate_substituted"
    assert out["spend_today_usd"] == pytest.approx(
        100 * lab_reader.DEEPSEEK_USD_PER_ROW, abs=1e-6)


def test_a_metered_tick_that_reports_a_cost_books_the_receipts_number(
        lab, monkeypatch):
    monkeypatch.setenv("AEGIS_L2_READER", "deepseek")
    from backend.services import lab_reader
    monkeypatch.setattr(lab_reader, "provider_configured", lambda name: True)
    monkeypatch.setattr(L, "type_rows", lambda **kw: {
        "status": "ok", "rows_typed": 100, "usage": {"cost_usd": 0.07},
        "corpus": {"rows_waiting": 5900}})
    out = L.loop_l2_typing(L.LabState())
    assert out["cost_source"] == "receipt"
    assert out["spend_today_usd"] == pytest.approx(0.07)


def test_a_local_tick_is_booked_unmetered(lab, monkeypatch):
    monkeypatch.setattr(L, "model_status", lambda: {
        "listening": True, "ready": True, "foreign": False,
        "started_by_aegis": True, "pid": 1})
    monkeypatch.setattr(L, "type_rows", lambda **kw: {
        "status": "ok", "rows_typed": 5, "corpus": {"rows_waiting": 1}})
    out = L.loop_l2_typing(L.LabState())
    assert out["cost_source"] == "local_unmetered"
    assert out["spend_today_usd"] == 0.0
