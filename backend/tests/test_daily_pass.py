"""THE DAILY PASS (chunk 12, T1) — every step mocked, nothing real touched.

Four things are pinned here and each of them is a failure somebody has already
paid for in this repository:

* **the ORDER and the COMPLETENESS of the step list.** The runner walks the
  declared `STEPS`, not the list of things that worked, so a step that raised
  still leaves a row. A check that reads the record of what ran cannot see what
  never got called.
* **the refusal path.** A step whose precondition is absent is `refused`, the
  row NAMES the precondition, and the process still exits 0. A scheduled task
  that goes red because one source refused teaches its reader to ignore red.
* **the same-date refusal.** A second unforced pass on one date re-hits every
  source's rate limit; it is refused BEFORE any step runs, and `--force` keeps
  the earlier receipt rather than overwriting it.
* **no model server, ever.** An AST walk over the module's executable source
  (docstrings and comments removed — protocol item 10) fails if an LLM or
  model-server symbol appears in code rather than in prose.

Every test drives `tmp_path`. `daily_pass.out_dir` is the ONE seam that decides
where a receipt lands, and it is replaced in a fixture so no test can write into
`backend/data/optimus/night_factory_<today>` on a CI runner that has no such
directory and no business gaining one.
"""

from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import config as _config
from scripts import daily_pass as DP

MODULE = Path(DP.__file__).resolve()


def _seam_names() -> set[str]:
    """Every public module-level callable a `step_*` handler reaches out through.

    DERIVED from the module's own AST, never listed by hand. A hand-written
    seam list is only as good as the memory of whoever adds the next step, and
    the cost of forgetting is not a weaker test: it is the REAL function
    running against `backend/data` inside a unit test. `grade_forecasts` was
    added on 2026-09-20 and, unstubbed for one run, rewrote the live prediction
    ledger — 14,703 records graded — before the ledger was restored from git.
    """
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    module_fns = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    seams: set[str] = set()
    for node in tree.body:
        if not (isinstance(node, ast.FunctionDef) and node.name.startswith("step_")):
            continue
        for sub in ast.walk(node):
            if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                    and sub.func.id in module_fns
                    and not sub.func.id.startswith("_")):
                seams.add(sub.func.id)
    return seams


#: Sorted for a stable failure message. Captured PRISTINE at import so a test
#: can ask "is this one still the real function?" by identity.
_SEAMS = sorted(_seam_names())
_PRISTINE = {name: getattr(DP, name) for name in _SEAMS}


# --------------------------------------------------------------------------
# fixtures: the receipt directory, and a full set of step seams


@pytest.fixture(autouse=True)
def no_process_table(monkeypatch):
    """No test in the offline suite queries the real process table.

    Two reasons, and the second is the one that bites. The probe launches
    PowerShell, which is slow and does not belong in a unit test — and on the
    dev machine it would find the LIVE `scripts.daily_pass` this session was
    told not to touch, decide it is a young sibling, and refuse every test in
    this file. The kill seam is stubbed to a failure for the same reason a
    network call is: no test may reach the real one by forgetting to stub it.
    """
    monkeypatch.setattr(DP, "scan_daily_passes", lambda: [])
    monkeypatch.setattr(DP, "kill_pid", lambda pid: pytest.fail(
        f"a test killed a real process (pid {pid}); stub DP.kill_pid"))


@pytest.fixture
def out(tmp_path, monkeypatch) -> Path:
    d = tmp_path / "night_factory_test"
    d.mkdir()
    monkeypatch.setattr(DP, "out_dir", lambda: d)
    monkeypatch.setattr(DP, "git_head", lambda: "0" * 40)
    return d


@pytest.fixture
def calls(monkeypatch) -> list[str]:
    """Replace every seam; record the order in which the steps reach them."""
    seen: list[str] = []

    def _news(**kw):
        seen.append("news_pull")
        return {"rows_new": 7, "sources": 3, "red": [], "refused": [],
                "resolution_rate": 0.5, "headline": "7 new rows"}

    def _analyst(**kw):
        seen.append("analyst_snapshot")
        return {"rows": 4, "by_status": {"ok": 4, "error": 0},
                "coverage_rate": 1.0, "headline": "4 rows"}

    def _e1(**kw):
        seen.append("e1_append")
        return {"rows_appended": 2, "verdict": "OK", "funnel": {"kept": 2},
                "headline": "2 rows appended"}

    def _cadences():
        return ("30m", "daily", "weekly")

    def _pass(cadence, **kw):
        seen.append(f"book_cadence:{cadence}")
        return {"books_considered": 1, "marked": ["book:1"],
                "decisions": ["book:1"], "refused": [], "bar_date": "2026-09-11"}

    def _coverage():
        seen.append("coverage")
        return {"available": True,
                "sources": [{"id": "a", "status": "OK", "rows_today": 5}],
                "regions": [{"region": "US", "rows_today": 5}],
                "totals": {"rows_today": 5}}

    monkeypatch.setattr(DP, "pull_all_news", _news)
    monkeypatch.setattr(DP, "run_analyst_snapshot", _analyst)
    monkeypatch.setattr(DP, "run_e1_append", _e1)
    monkeypatch.setattr(DP, "cadence_list", _cadences)
    monkeypatch.setattr(DP, "run_cadence_pass", _pass)
    def _contracts(**kw):
        seen.append("decision_contract")
        return [{"decision_id": "dec-aaa", "direction": "BUY", "ticker": "AAA"},
                {"decision_id": "dec-bbb", "direction": "REFUSED",
                 "ticker": "BBB"}]

    def _record(rows, day):
        return {"state": "DECIDED", "by": "daily_pass", "written": len(rows),
                "duplicate": 0, "refused": []}

    def _grade(**kw):
        seen.append("grade_forecasts")
        return {"newly_resolved": 3, "resolver_status": "ok",
                "totals": {"graded": 3, "not_yet_due": 1},
                "n_records": 4, "licence": "PRODUCT_EXPERIMENT",
                "bars": {"available": True}, "headline": "3 newly resolved"}

    monkeypatch.setattr(DP, "read_coverage", _coverage)
    # Chunk 18b. The real grader reads the LIVE prediction ledger out of
    # `backend/data` and REWRITES it — `belief_state.resolve_all` writes the
    # whole file. It was unstubbed for exactly one test run and graded 14,703
    # live records against the local bars; the ledger was restored from git and
    # `test_every_module_level_seam_is_stubbed_by_the_calls_fixture` below is
    # why the next step added here cannot repeat it.
    monkeypatch.setattr(DP, "grade_forecasts", _grade)
    # Chunk 18. BOTH seams, because the real builder reads the funnel out of
    # `backend/data` and the real ledger writes into it — neither exists in CI
    # and neither belongs in a unit test's blast radius.
    monkeypatch.setattr(DP, "build_decision_contracts", _contracts)
    monkeypatch.setattr(DP, "record_decided", _record)
    return seen


def test_the_decision_contract_step_records_what_it_decided(
        out, calls, rth_open) -> None:
    """CHUNK 18 on the UNATTENDED path. The Morning is what the operator
    clicks; this pass is what runs whether or not anybody is at the machine,
    and the chunk's gate needs the contract to exist without a click."""
    rec = DP.run_daily_pass(day=_today())
    row = next(r for r in rec["steps"] if r["step"] == "decision_contract")
    assert row["status"] == "ok"
    assert row["rows"] == 2
    assert row["count_by_direction"]["BUY"] == 1
    assert row["ledger"]["written"] == 2
    assert row["licence"] == "PRODUCT_EXPERIMENT"
    assert "decision_contract" in calls
    # SECOND, right after the corpus pull and BEFORE the analyst sweep. It was
    # fifth until 2026-09-20 and had therefore never run once: the only firing
    # that carried it wedged in the 2.5-hour snapshot four steps earlier, and
    # `backend/data/optimus/decisions/ledger.jsonl` did not exist at all.
    assert calls.index("decision_contract") < calls.index("analyst_snapshot")
    assert calls.index("decision_contract") > calls.index("news_pull")


@pytest.fixture
def rth_open(monkeypatch):
    monkeypatch.setattr(DP, "us_rth_state",
                        lambda now=None: {"inside": True, "session": True,
                                          "why": "inside US regular trading hours"})


@pytest.fixture
def rth_shut(monkeypatch):
    monkeypatch.setattr(DP, "us_rth_state",
                        lambda now=None: {"inside": False, "session": False,
                                          "why": "not an XNYS session"})


def _today() -> str:
    """Derived from the clock, never a literal: a fixture that encodes a
    calendar moment fails the day after it passes (CLAUDE.md protocol 5)."""
    return datetime.now(timezone.utc).date().isoformat()


# --------------------------------------------------------------------------
# the order, and the completeness


def test_every_declared_step_runs_in_order(out, calls, rth_open) -> None:
    rec = DP.run_daily_pass(day=_today())
    assert [r["step"] for r in rec["steps"]] == [s for s, _ in DP.STEPS]
    # the cadence step fans out inside itself; the OUTER order is the declared one
    outer = [c.split(":")[0] for c in calls]
    assert outer == ["news_pull", "decision_contract", "analyst_snapshot",
                     "e1_append", "book_cadence", "book_cadence", "book_cadence",
                     "grade_forecasts", "coverage"]


def test_the_handler_table_covers_the_declared_steps() -> None:
    assert set(DP._HANDLERS) == {s for s, _ in DP.STEPS}


def test_every_module_level_seam_is_stubbed_before_a_pass_runs(
        out, calls, rth_open) -> None:
    """MEASURED 2026-09-20, at this repository's expense.

    `grade_forecasts` was added to `STEPS` and the `calls` fixture was not
    taught about it. One `pytest backend/tests/test_daily_pass.py` later, the
    real grader had run against the LIVE prediction ledger and written outcomes
    onto 14,703 records — the ledger was restored from git, and this test is
    the reason the next step added here cannot do it again.

    The seam list is derived from the module's AST, so a new seam is covered
    the moment it exists rather than the moment somebody remembers it.
    """
    assert _SEAMS, "the AST walk found no seams at all — it has stopped working"
    live = [name for name in _SEAMS if getattr(DP, name) is _PRISTINE[name]]
    assert not live, (
        f"{live} reach outside and are NOT stubbed by the fixtures, so a unit "
        f"test would run them for real against backend/data")


def test_a_step_that_raises_still_leaves_a_row(out, calls, rth_open,
                                               monkeypatch) -> None:
    def _boom(**kw):
        raise RuntimeError("the corpus directory is gone")

    monkeypatch.setattr(DP, "pull_all_news", _boom)
    rec = DP.run_daily_pass(day=_today())
    row = next(r for r in rec["steps"] if r["step"] == "news_pull")
    assert row["status"] == "error"
    assert "the corpus directory is gone" in row["refusals"][0]
    # and the steps AFTER it still ran
    assert [r["step"] for r in rec["steps"]] == [s for s, _ in DP.STEPS]
    assert next(r for r in rec["steps"] if r["step"] == "coverage")["status"] == "ok"


# --------------------------------------------------------------------------
# the refusal path


def test_a_refusing_step_names_its_precondition_and_the_pass_exits_zero(
        out, calls, rth_open, monkeypatch) -> None:
    monkeypatch.setattr(DP, "run_e1_append", lambda **kw: {
        "rows_appended": 0, "verdict": "REFUSED",
        "headline": "REFUSED: no bars parquet — nothing can be labelled"})
    rec = DP.run_daily_pass(day=_today())
    row = next(r for r in rec["steps"] if r["step"] == "e1_append")
    assert row["status"] == "refused"
    assert "no bars parquet" in row["refusals"][0]
    assert rec["steps_that_did_not_run"] == ["e1_append"]
    # ...and the PROCESS exits 0 on the same refusal. `--force` only because
    # the call above already wrote today's receipt; the exit code under test is
    # the one a refusing step produces, not the one the date guard produces.
    assert DP.main(["--date", _today(), "--force"]) == 0


def test_nothing_to_do_is_not_an_ok_with_zeros(out, calls, rth_open,
                                               monkeypatch) -> None:
    monkeypatch.setattr(DP, "pull_all_news", lambda **kw: {
        "rows_new": 0, "sources": 3, "red": [], "refused": []})
    rec = DP.run_daily_pass(day=_today())
    row = next(r for r in rec["steps"] if r["step"] == "news_pull")
    assert row["status"] == "nothing_to_do"
    assert row["rows"] == 0


def test_the_coverage_card_refuses_rather_than_reporting_an_empty_card(
        out, calls, rth_open, monkeypatch) -> None:
    monkeypatch.setattr(DP, "read_coverage", lambda: {
        "available": False, "error": "ImportError: news_registry"})
    row = next(r for r in DP.run_daily_pass(day=_today())["steps"]
               if r["step"] == "coverage")
    assert row["status"] == "refused"
    assert "news_registry" in row["refusals"][0]


# --------------------------------------------------------------------------
# 30m books only inside RTH


def test_the_intraday_bucket_is_skipped_outside_rth_and_says_so(
        out, calls, rth_shut) -> None:
    rec = DP.run_daily_pass(day=_today())
    row = next(r for r in rec["steps"] if r["step"] == "book_cadence")
    intraday = [p for p in row["per_cadence"] if p["cadence"] == "30m"]
    assert len(intraday) == 1, "the bucket is SKIPPED, never omitted"
    assert intraday[0]["status"] == "skipped"
    assert "outside US RTH" in intraday[0]["reason"]
    assert "book_cadence:30m" not in calls
    assert "book_cadence:daily" in calls


def test_the_intraday_bucket_runs_inside_rth(out, calls, rth_open) -> None:
    DP.run_daily_pass(day=_today())
    assert "book_cadence:30m" in calls


def test_us_rth_state_says_cannot_determine_when_the_calendar_is_unreadable(
        monkeypatch) -> None:
    import backend.services.market_sessions as MS

    def _boom(day):
        raise RuntimeError("exchange_calendars is not installed")

    monkeypatch.setattr(MS, "is_session", _boom)
    state = DP.us_rth_state(datetime.now(timezone.utc))
    assert state["inside"] is False
    assert state["basis"] == "CANNOT DETERMINE"
    assert state["session"] is None


def test_us_rth_state_is_false_out_of_hours_on_a_real_session(monkeypatch) -> None:
    import backend.services.market_sessions as MS

    monkeypatch.setattr(MS, "is_session", lambda day: True)
    # 02:00 UTC is 21:00/22:00 ET the previous day — never inside RTH,
    # whichever side of a DST change today happens to fall on.
    when = datetime.now(timezone.utc).replace(hour=2, minute=0, second=0,
                                              microsecond=0)
    assert DP.us_rth_state(when)["inside"] is False


# --------------------------------------------------------------------------
# the same-date refusal


def test_a_second_pass_on_the_same_date_is_refused_before_any_step_runs(
        out, calls, rth_open) -> None:
    day = _today()
    DP.run_daily_pass(day=day)
    calls.clear()
    with pytest.raises(DP.SamePassAlreadyRan) as exc:
        DP.run_daily_pass(day=day)
    assert day in str(exc.value)
    assert calls == [], "the refusal must come BEFORE the first step"
    assert DP.main(["--date", day]) == 2


def test_force_keeps_the_earlier_receipt_and_numbers_the_second(
        out, calls, rth_open) -> None:
    day = _today()
    first = DP.run_daily_pass(day=day)
    second = DP.run_daily_pass(day=day, force=True)
    assert first["run"] == 1 and second["run"] == 2
    assert Path(first["path"]).exists(), "the first receipt is never overwritten"
    assert Path(second["path"]).name == f"daily_pass_{day}_run02.json"
    assert second["forced"] is True
    assert second["prior_receipts"] == [Path(first["path"]).name]


def test_a_different_date_is_not_blocked_by_yesterdays_receipt(
        out, calls, rth_open) -> None:
    today = datetime.now(timezone.utc).date()
    DP.run_daily_pass(day=str(today - timedelta(days=1)))
    rec = DP.run_daily_pass(day=str(today))
    assert rec["run"] == 1


# --------------------------------------------------------------------------
# the receipt shape


def test_the_receipt_shape(out, calls, rth_open) -> None:
    day = _today()
    rec = DP.run_daily_pass(day=day)
    for key in ("receipt", "licence", "date", "run", "git_head", "started_utc",
                "finished_utc", "elapsed_s", "declared_steps", "steps",
                "step_status_counts", "steps_that_did_not_run", "headline",
                "read_me_first", "llm_spend_usd"):
        assert key in rec, key
    assert rec["receipt"] == "daily_pass"
    assert rec["licence"] == "PRODUCT_EXPERIMENT"
    assert rec["llm_spend_usd"] == 0.0
    assert rec["declared_steps"] == [s for s, _ in DP.STEPS]
    assert set(rec["step_status_counts"]) == set(DP.STATUSES)
    for row in rec["steps"]:
        assert row["status"] in DP.STATUSES
        assert isinstance(row["refusals"], list)
        assert "seconds" in row and "rows" in row and "what" in row
    on_disk = json.loads(Path(rec["path"]).read_text(encoding="utf-8"))
    assert on_disk["date"] == day
    assert [r["step"] for r in on_disk["steps"]] == [s for s, _ in DP.STEPS]


def test_the_receipt_carries_a_stage_and_it_is_the_last_one_it_reaches(
        out, calls, rth_open) -> None:
    """The receipt lands in the night folder, and every json in there must carry
    a stage (`test_stage_contract_no_forward_read`). A driver is not one stage:
    it is stamped at the LAST stage it reaches, which is the conservative
    direction -- `pnl` may read anything and nothing may read it, so the stamp
    can never license a forward read."""
    from scripts.night_factory_jobs import STAGE_ORDER

    rec = DP.run_daily_pass(day=_today())
    assert rec["stage"] == "pnl"
    assert rec["stage"] in STAGE_ORDER
    assert set(rec["step_stages"]) == {s for s, _ in DP.STEPS}, (
        "a step without a declared stage would be stamped by the roll-up alone")
    assert set(rec["step_stages"].values()) <= set(STAGE_ORDER)
    assert max(STAGE_ORDER.index(v) for v in rec["step_stages"].values()) ==         STAGE_ORDER.index(rec["stage"])


def test_the_receipt_lands_in_the_nights_own_folder(out, calls, rth_open) -> None:
    rec = DP.run_daily_pass(day=_today())
    assert Path(rec["path"]).parent == out


def test_dry_run_writes_nothing_and_calls_nothing(out, calls, rth_shut) -> None:
    plan = DP.plan(_today())
    assert plan["dry_run"] is True
    assert [s["step"] for s in plan["steps"]] == [s for s, _ in DP.STEPS]
    assert calls == []
    assert list(out.glob("*.json")) == []


def test_the_status_vocabulary_is_closed() -> None:
    with pytest.raises(ValueError):
        DP._row("news_pull", "fine")


# --------------------------------------------------------------------------
# no model server, no LLM, no order path


def executable_source(path: Path) -> str:
    """The module's source with comments AND docstrings removed.

    Copied from `test_desktop_control_surface.py` for the same reason it exists
    there: three guards failed on their first run this month by matching the
    docstring that EXPLAINS the banned pattern, and the next reader deletes the
    explanation to make the suite green.
    """
    src = path.read_text(encoding="utf-8")
    drop: set[int] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", None)
            first = body[0] if body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                drop.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return "\n".join(line for i, line in enumerate(src.splitlines(), 1)
                     if i not in drop and not line.strip().startswith("#"))


@pytest.mark.parametrize("banned", [
    "llama_server", "llm_analyzer", "llm_client", "deepseek", "anthropic",
    "openai", "_call_llm", "model_server",
])
def test_the_daily_pass_never_reaches_the_model_server(banned: str) -> None:
    assert banned not in executable_source(MODULE).lower(), (
        f"{banned!r} appears in daily_pass.py's executable source. The daily "
        f"pass accumulates data and costs $0 of LLM; a step that asks a model "
        f"for a number belongs in a night job with its own receipt.")


@pytest.mark.parametrize("banned", ["submit_order", "place_order", "TradingClient",
                                    "alpaca_trade_api"])
def test_the_daily_pass_has_no_order_path(banned: str) -> None:
    assert banned not in executable_source(MODULE)


# --------------------------------------------------------------------------
# THE BOXES AND THE STALE SIBLING (chunk 16a, 2026-09-18)
#
# MEASURED: the 09-14 06:30 pass wedged inside its analyst snapshot after 1,500
# of 2,362 symbols and stayed alive for four days. Every later firing reported
# Windows 0x80070420 and no pass ran on 09-15..09-18.


def test_every_declared_step_has_a_box() -> None:
    assert set(DP._STEP_BOXES) == {s for s, _ in DP.STEPS}
    assert all(DP.step_box_s(s) > 0 for s, _ in DP.STEPS)
    assert "timeout" in DP.STATUSES


def test_the_stale_bound_is_above_the_sum_of_every_box() -> None:
    """A sibling old enough to kill must be one that outlived every box it has.

    A guard DERIVES its inputs or refuses. If a future edit raises the analyst
    box past the stale bound, a HEALTHY three-hour pass becomes a victim of the
    rule meant to protect it — so the inequality is pinned here rather than
    trusted to whoever edits the config next.
    """
    total = sum(DP._STEP_BOXES.values())
    assert total <= float(_config.DAILY_PASS_STALE_SIBLING_H) * 3600, (
        f"the boxes sum to {total:.0f}s but a sibling is killed after "
        f"{_config.DAILY_PASS_STALE_SIBLING_H} h")


def test_a_step_that_outlives_its_box_is_a_timeout_row_and_the_pass_goes_on(
        out, calls, rth_open, monkeypatch) -> None:
    """The whole of the 09-14 fix, in one assertion: the wedged step yields a
    `timeout` row and the NEXT step still runs."""
    import time as _time

    monkeypatch.setitem(DP._STEP_BOXES, "analyst_snapshot", 0.2)

    def _wedged(**kw):
        calls.append("analyst_snapshot")
        _time.sleep(30)                        # the daemon thread is abandoned
        return {"rows": 0}

    monkeypatch.setattr(DP, "run_analyst_snapshot", _wedged)
    rec = DP.run_daily_pass(day=_today())
    rows = {r["step"]: r for r in rec["steps"]}
    assert rows["analyst_snapshot"]["status"] == "timeout"
    assert rows["analyst_snapshot"]["box_s"] == 0.2
    assert rows["analyst_snapshot"]["refusals"] == ["timeout_after_0.2s"]
    # the pass CONTINUED: every declared step still has a row, and the ones
    # after the wedged one actually ran.
    assert [r["step"] for r in rec["steps"]] == [s for s, _ in DP.STEPS]
    assert rows["e1_append"]["status"] == "ok"
    assert rows["coverage"]["status"] in ("ok", "nothing_to_do")
    assert rec["step_status_counts"]["timeout"] == 1
    assert "analyst_snapshot" in rec["steps_that_did_not_run"]


def test_a_boxed_out_pass_still_writes_its_receipt_and_exits_zero(
        out, calls, rth_open, monkeypatch) -> None:
    """Four dates had NO receipt because one process would not die. A pass that
    times out everywhere still leaves the evidence behind."""
    import time as _time

    for step, _ in DP.STEPS:
        monkeypatch.setitem(DP._STEP_BOXES, step, 0.05)
    # DERIVED, not listed. A seam left off a hand-written list is not a weaker
    # test — it is the REAL function running against `backend/data` inside a
    # unit test, which is how `grade_forecasts` rewrote the live prediction
    # ledger the first time it was added.
    for seam in _SEAMS:
        monkeypatch.setattr(DP, seam, lambda *a, **k: _time.sleep(30))
    rc = DP.main(["--date", _today()])
    assert rc == 0, "a boxed-out pass must not go red; the receipt is the evidence"
    written = json.loads(DP.receipt_path(_today(), 1).read_text(encoding="utf-8"))
    assert written["step_status_counts"]["timeout"] == len(DP.STEPS)


def test_the_sibling_scan_excludes_this_process_and_its_launcher_parent():
    """2026-09-18: the venv's python.exe is a redirector that spawns the real
    interpreter; both carry `-m scripts.daily_pass`. The first pass on the boxed
    code refused ITSELF ("running as pid(s) [24924]", its own launcher)."""
    table = "\n".join([
        "100	2026-09-18T05:45:31Z	python.exe -u -m scripts.daily_pass --force",   # my launcher
        "101	2026-09-18T05:45:31Z	python.exe -u -m scripts.daily_pass --force",   # me
        "102	2026-09-14T22:30:00Z	python.exe -m scripts.daily_pass --scheduled",  # a real sibling
        "103	2026-09-18T04:00:00Z	python.exe -m scripts.always_on_lab",           # not a pass
        "garbage line",
    ])
    rows = DP.parse_process_table(table, me=101, parent=100)
    assert [r["pid"] for r in rows] == [102]
    assert rows[0]["created_utc"] == "2026-09-14T22:30:00Z"


def test_a_seven_hour_old_sibling_is_killed_by_pid_and_named_in_the_receipt(
        out, calls, rth_open, monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    old = (now - timedelta(hours=7)).isoformat()
    monkeypatch.setattr(DP, "scan_daily_passes", lambda: [
        {"pid": 4242, "created_utc": old,
         "cmdline": "python -m scripts.daily_pass"}])
    killed: list[int] = []
    monkeypatch.setattr(DP, "kill_pid", lambda pid: killed.append(pid) or
                        {"killed": True, "pid": pid, "detail": "SUCCESS"})
    rec = DP.run_daily_pass(day=_today())
    assert killed == [4242], "the stale sibling was not killed"
    assert rec["stale_sibling_killed"] == [
        {"pid": 4242, "age_h": pytest.approx(7.0, abs=0.1), "killed": True,
         "detail": "SUCCESS", "cmdline": "python -m scripts.daily_pass"}]
    assert rec["step_status_counts"]["ok"] >= 1, "the pass did not take the day"


def test_a_two_hour_old_sibling_is_refused_by_name_and_never_killed(
        out, calls, rth_open, monkeypatch) -> None:
    """Two passes minutes apart is a human being deliberate. A driver that
    killed its own operator's run would be worse than the stall it fixes."""
    now = datetime.now(timezone.utc)
    young = (now - timedelta(hours=2)).isoformat()
    monkeypatch.setattr(DP, "scan_daily_passes", lambda: [
        {"pid": 99, "created_utc": young, "cmdline": "python -m scripts.daily_pass"}])
    with pytest.raises(DP.SiblingPassRunning) as exc:
        DP.run_daily_pass(day=_today())
    assert "99" in str(exc.value)
    assert calls == [], "a refused pass ran a step"


def test_an_unreadable_creation_time_kills_nothing(monkeypatch) -> None:
    """CANNOT DETERMINE is not 'old enough'. A sibling whose age could not be
    read is left alone and reported."""
    monkeypatch.setattr(DP, "scan_daily_passes", lambda: [
        {"pid": 7, "created_utc": "not a date", "cmdline": "x"}])
    found = DP.stale_siblings()
    assert found["stale"] == []
    assert found["young"][0]["age_h"] is None


def test_the_refusal_is_about_the_invocation_so_the_exit_code_is_two(
        out, calls, monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(DP, "scan_daily_passes", lambda: [
        {"pid": 99, "created_utc": (now - timedelta(minutes=5)).isoformat(),
         "cmdline": "python -m scripts.daily_pass"}])
    assert DP.main(["--date", _today()]) == 2


def test_it_never_kills_by_image_name() -> None:
    """The pass became a killer on 2026-09-18. It kills BY PID, only.

    `taskkill` is no longer absent — the stale-sibling rule needs it, because a
    pass wedged for four days cost 09-15 through 09-18. What must stay absent is
    the IMAGE-NAME form: on 2026-09-06 one `taskkill /F /IM python.exe` took
    down two other agents' jobs, a running test suite, ~1,676 already-billed LLM
    extractions and the Optimus MCP server (CLAUDE.md rule 6).

    Read from the AST, so the paragraph above — which names the banned flag —
    cannot itself fail the guard the way three tests in this repo did on their
    first run.
    """
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    invocations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for arg in node.args:
            if not isinstance(arg, ast.List):
                continue
            parts = [e.value for e in arg.elts
                     if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            if parts and "taskkill" in parts[0].lower():
                invocations.append(parts)
    assert invocations, "the stale-sibling kill disappeared; it is load-bearing"
    for parts in invocations:
        upper = [p.upper() for p in parts]
        assert "/IM" not in upper, f"kill by image name: {parts}"
        assert "/PID" in upper, f"a taskkill with no /PID: {parts}"
