"""ASK AEGIS: what it may read, what it may never do (roadmap O6, M3).

The assistant now reads the checkout. That is a new kind of authority — not "run
a job" but "read anything" — and the safety property is NEGATIVE: it cannot
write, cannot spawn, cannot reach a broker, cannot POST anywhere. A negative
property is only provable over a narrow file, which is why `ask` moved out of
`control.py` (that module legitimately spawns night jobs) and why this suite
walks the AST of exactly two modules.

The second half pins the ROUTER, because a deterministic router is the whole
reason an answer can be diagnosed: the same question always retrieves the same
receipts, so a wrong answer is a retrieval failure or a reading failure and
never ambiguously both.
"""

from __future__ import annotations

import ast
import json
from datetime import date
from pathlib import Path

import pytest

from backend.routers import control_ask
from backend.services import ask_tools, ledger_retrieval

MODULES = (Path(control_ask.__file__), Path(ask_tools.__file__))

#: Assembled rather than written out, so the repository's own security hook does
#: not read this list of BANNED names as a use of one of them.
BANNED_IMPORTS = ("subprocess", "alpaca", "broker", "trade_api", "tradeapi",
                  "quiet_subprocess", "os." + "system")


def _tree(p: Path) -> ast.Module:
    return ast.parse(p.read_text(encoding="utf-8"))


def _doc_string_ids(tree: ast.Module) -> set[int]:
    """Docstring nodes, so a guard cannot fire on its own rationale.

    Three tests failed on their first run in this repo by matching the docstring
    that explained the banned pattern. A guard that flags its own explanation
    teaches the next reader to delete the explanation.
    """
    out: set[int] = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(n, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


# ------------------------------------------------------------------ negatives

@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_the_ask_path_opens_no_file_for_writing(path: Path) -> None:
    tree = _tree(path)
    banned_attrs = {"write_text", "write_bytes", "mkdir", "unlink", "rmtree", "touch"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        assert getattr(fn, "attr", None) not in banned_attrs, (
            f"{path.name} calls .{getattr(fn, 'attr', None)}()")
        if isinstance(fn, ast.Name) and fn.id == "open":
            mode = ""
            for a in list(node.args[1:]) + [k.value for k in node.keywords if k.arg == "mode"]:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    mode = a.value
            assert "w" not in mode and "a" not in mode and "+" not in mode, (
                f"{path.name} opens a file for writing")


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_the_ask_path_imports_no_subprocess_and_no_broker(path: Path) -> None:
    tree = _tree(path)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(f"{node.module or ''}.{a.name}" for a in node.names)
    joined = " ".join(sorted(names)).lower()
    for banned in BANNED_IMPORTS:
        assert banned not in joined, f"{path.name} imports {banned}"


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_the_ask_path_makes_no_outbound_post(path: Path) -> None:
    """It may read the disk. It may not send anything anywhere."""
    tree = _tree(path)
    docs = _doc_string_ids(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            attr = getattr(node.func, "attr", None)
            base = getattr(getattr(node.func, "value", None), "id", None)
            assert (base, attr) not in {("requests", "post"), ("requests", "put"),
                                        ("httpx", "post"), ("urllib", "urlopen")}, (
                f"{path.name} calls {base}.{attr}()")
            assert attr not in {"urlopen", "Request"}, f"{path.name} calls .{attr}()"
    runnable = [n.value.lower() for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and id(n) not in docs]
    assert not [s for s in runnable if s.strip() in {"post", "put", "delete"}], (
        f"{path.name} names an HTTP write verb in executable code")


def test_the_ask_path_holds_no_stop_path() -> None:
    """It may start the model. It may never stop one: closing somebody else's
    job is not something an answer is allowed to do."""
    src = Path(control_ask.__file__).read_text(encoding="utf-8")
    body = src[src.index("def ask("):]
    for banned in ("ls.stop", "stop_if_owned", "taskkill", "/IM"):
        assert banned not in body, f"the ask path must not be able to {banned}"


def test_every_declared_tool_has_a_handler_and_there_are_no_others() -> None:
    """The model does not choose its tools; a tool it cannot request is a tool
    it cannot misuse."""
    assert set(ask_tools._DISPATCH) == set(ask_tools.TOOLS)
    assert "write" not in " ".join(ask_tools.TOOLS)


# --------------------------------------------------------------------- router

@pytest.mark.parametrize("question,tool,arg", [
    ("look at scripts/night_g3_evolve_v2.py", "file", "scripts/night_g3_evolve_v2.py"),
    ("what does backend/services/belief_state.py do?", "file",
     "backend/services/belief_state.py"),
    ("what did G3_evolve_v2 find?", "receipt", "G3_evolve_v2"),
    ("summarise R2_widened_panelB", "receipt", "R2_widened_panelB"),
    ("how are the books doing?", "fleet", None),
    ("what is the fleet's excess?", "fleet", None),
    ("what should run tonight?", "night_plan", None),
    ("what do you think happens today?", "morning", None),
    ("how many names are in the universe?", "universe", None),
    ("who is Murat", "default", None),
])
def test_the_router_is_deterministic_and_most_specific_first(question, tool, arg):
    r = ask_tools.route(question)
    assert r["tool"] == tool, (question, r)
    assert r["arg"] == arg, (question, r)
    assert r["why"], "a routing decision that cannot be explained cannot be fixed"
    assert ask_tools.route(question) == r, "the same question must route the same way"


def test_a_path_beats_a_keyword_because_it_is_more_specific():
    """'what happens today in scripts/night_factory.py' is a question about a
    FILE that happens to contain the word today."""
    r = ask_tools.route("what happens today in scripts/night_factory.py")
    assert r["tool"] == "file" and r["arg"] == "scripts/night_factory.py"


def test_an_english_sentence_with_a_slash_is_not_a_path():
    r = ask_tools.route("is the long/short book up or down")
    assert r["tool"] != "file"


def test_the_file_tool_refuses_a_secret_as_text_rather_than_raising():
    """The refusal is something the model can read out. A 403 is something the
    page has to interpret."""
    text, sources = ask_tools.tool_file(".env")
    assert "REFUSED" in text and "never-served" in text
    assert sources == []


def test_the_file_tool_serves_a_real_file_with_its_commits():
    text, sources = ask_tools.tool_file("backend/services/belief_state.py")
    assert sources == ["backend/services/belief_state.py"]
    assert "PredictionRecord" in text


def test_the_sources_line_is_computed_not_asked_of_the_model():
    line = ask_tools.sources_line(["a/b.py", "c/d.json"])
    assert line.startswith("sources: ")
    assert json.loads(line[len("sources: "):]) == ["a/b.py", "c/d.json"]
    assert ask_tools.sources_line([]) == "sources: []"


# -------------------------------------------------------- the forecast answer

def test_no_morning_means_no_forecast_is_invented():
    answer = ask_tools.forecast_answer([], None)
    assert "has not written any forecast" in answer
    assert "Run the morning" in answer
    assert "I will not invent one" in answer


def test_the_forecast_answer_is_the_ledger_rows_verbatim():
    rows = [{"lane": "balanced", "benchmark": "balanced-ew-control",
             "benchmark_is_fallback": False, "probability": 0.62,
             "basis": "laplace_smoothed_paired_win_rate", "n_paired_days": 44,
             "resolves_after": "2026-09-14"}]
    answer = ask_tools.forecast_answer(rows, "backend/data/optimus/morning/x.json")
    assert "0.62" in answer and "balanced-ew-control" in answer
    assert "44 paired sessions" in answer
    assert "No model was asked" in answer
    assert "backend/data/optimus/morning/x.json" in answer


def test_a_fallback_benchmark_is_labelled_as_an_index_not_a_twin():
    rows = [{"lane": "balanced-ew-control", "benchmark": "SPY",
             "benchmark_is_fallback": True, "probability": 0.5,
             "basis": "insufficient_history", "n_paired_days": 3,
             "resolves_after": "2026-09-14"}]
    assert "an index, not a twin" in ask_tools.forecast_answer(rows, None)


# ------------------------------------------------- M3 hindsight-safe retrieval

def _rule(rule_id, resolution_date, resolved_at, outcome=1, brier=0.04, scope="AAPL"):
    return {"rule_id": rule_id, "applies_to_scope": scope,
            "resolution_date": resolution_date, "resolved_at": resolved_at,
            "outcome": outcome, "brier": brier}


def test_retrieval_excludes_rule_resolved_after_t():
    """The leak-prevention direction."""
    t = date(2026, 6, 1)
    planted = _rule("R-LEAK-1", "2026-06-15", "2026-06-16")
    got = ledger_retrieval.rules_visible_at(t, ledger=[planted], scope="AAPL")
    assert planted["rule_id"] not in {r["rule_id"] for r in got}


def test_retrieval_includes_rule_resolved_before_t():
    """Proves the filter is a DATE gate and not an accidental blanket
    exclusion -- a retriever returning [] for every query would pass the first
    test for the wrong reason."""
    t = date(2026, 6, 1)
    planted = _rule("R-OK-1", "2026-01-15", "2026-01-16")
    got = ledger_retrieval.rules_visible_at(t, ledger=[planted], scope="AAPL")
    assert planted["rule_id"] in {r["rule_id"] for r in got}


def test_retrieval_excludes_rule_due_but_not_yet_actually_resolved():
    """resolution_date < t but the resolver had not run: the 'due but not
    graded' leak, distinct from the plain future-date leak."""
    t = date(2026, 6, 1)
    planted = _rule("R-LEAK-2", "2026-05-01", None, outcome=None, brier=None)
    got = ledger_retrieval.rules_visible_at(t, ledger=[planted], scope="AAPL")
    assert planted["rule_id"] not in {r["rule_id"] for r in got}


def test_the_report_names_the_clause_that_dropped_each_candidate():
    t = date(2026, 6, 1)
    rep = ledger_retrieval.retrieval_report(t, ledger=[
        _rule("ok", "2026-01-15", "2026-01-16"),
        _rule("future", "2026-06-15", "2026-06-16"),
        _rule("ungraded", "2026-05-01", None, outcome=None, brier=None),
        _rule("late", "2026-05-01", "2026-06-20"),
    ])
    assert rep["pool"] == 4 and rep["visible"] == 1
    assert rep["dropped"]["unresolved_window"] == 1
    assert rep["dropped"]["never_graded"] == 1
    assert rep["dropped"]["graded_after_t"] == 1


def test_an_unreadable_stamp_is_never_treated_as_old_enough():
    t = date(2026, 6, 1)
    bad = _rule("R-BAD", "not-a-date", "also-not-a-date")
    assert ledger_retrieval.rules_visible_at(t, ledger=[bad]) == []


def test_an_unparseable_cutoff_refuses_rather_than_retrieving_everything():
    with pytest.raises(ValueError):
        ledger_retrieval.rules_visible_at("not-a-date", ledger=[])


def test_an_absent_rule_store_is_an_empty_retrieval_not_an_error(tmp_path):
    assert ledger_retrieval.rules_visible_at(date(2026, 6, 1),
                                             path=tmp_path / "nope.jsonl") == []
