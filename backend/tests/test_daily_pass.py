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

from scripts import daily_pass as DP

MODULE = Path(DP.__file__).resolve()


# --------------------------------------------------------------------------
# fixtures: the receipt directory, and a full set of step seams


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
    monkeypatch.setattr(DP, "read_coverage", _coverage)
    return seen


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
    assert outer == ["news_pull", "analyst_snapshot", "e1_append",
                     "book_cadence", "book_cadence", "book_cadence", "coverage"]


def test_the_handler_table_covers_the_declared_steps() -> None:
    assert set(DP._HANDLERS) == {s for s, _ in DP.STEPS}


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


def test_it_never_kills_by_image_name() -> None:
    src = executable_source(MODULE)
    assert "/IM" not in src and "taskkill" not in src.lower()
