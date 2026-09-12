"""The read-only surface an agent talks to, checked by READING ITS AST.

A grep for `open(...)` finds the word in a docstring and misses
`Path.write_text`. The tests below parse the module and walk it, which is the
discipline CLAUDE.md item 10 demands after three guards failed on their own
explanations.

What is asserted: no write of any kind, no shell, no broker, no network; every
read bounded; no path outside the data root; and a missing input that answers
CANNOT DETERMINE rather than an empty success.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from backend.services import brain_queries as BQ

MODULE = Path(BQ.__file__)
TREE = ast.parse(MODULE.read_text(encoding="utf-8"))


# ------------------------------------------------------- the AST no-write test

#: Names that can only ever be a write or a shell-out. A local variable is
#: never called `write_text`, so these are banned whatever the receiver is.
ALWAYS_FORBIDDEN = {"write_text", "write_bytes", "writelines", "mkdir",
                    "unlink", "rmdir", "rename", "to_parquet", "to_csv",
                    "to_json", "touch", "system", "popen", "check_output",
                    "dump"}

#: Names that are a write when a MODULE does them and ordinary Python when a
#: local list or dict does. `rows.append(...)` is not a write to the world and
#: `evidence_memory.append(...)` is; a guard that cannot tell them apart is the
#: broken guard of CLAUDE.md item 10, so the RECEIVER is checked.
MUTATORS = {"append", "observe", "supersede", "save", "set", "update",
            "delete", "write", "run", "call", "extend", "insert"}

#: Top-level modules that reach the world, plus the fully-qualified project
#: modules that hold a write path.
FORBIDDEN_ROOTS = {"subprocess", "socket", "requests", "httpx", "urllib",
                   "alpaca", "alpaca_trade_api", "ccxt", "shutil"}
FORBIDDEN_MODULES = {"backend.services.execution_ledger",
                     "backend.services.paper_broker_targets",
                     "backend.services.belief_state"}


def _imported_aliases(tree) -> set[str]:
    """Every name in this module that refers to an imported MODULE."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                out.add(a.asname or a.name)
    return out


def _calls(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute):
                receiver = fn.value.id if isinstance(fn.value, ast.Name) else None
                yield fn.attr, receiver, node
            elif isinstance(fn, ast.Name):
                yield fn.id, None, node


def test_the_module_never_calls_anything_that_writes_or_shells_out():
    """The structural half of read-only: not a flag that can be off, a write
    path that does not exist."""
    aliases = _imported_aliases(TREE)
    offenders = []
    for name, receiver, node in _calls(TREE):
        if name in ALWAYS_FORBIDDEN:
            offenders.append((name, receiver, node.lineno))
        elif name in MUTATORS and receiver in aliases:
            offenders.append((name, receiver, node.lineno))
    assert not offenders, (
        f"brain_queries calls write-shaped functions at {offenders}. A "
        f"read-only surface with a write path is a read-only surface until "
        f"somebody calls the other function.")


def test_the_module_imports_nothing_that_reaches_the_world():
    bad = []
    for node in ast.walk(TREE):
        if isinstance(node, ast.Import):
            bad += [a.name for a in node.names
                    if a.name.split(".")[0] in FORBIDDEN_ROOTS
                    or a.name in FORBIDDEN_MODULES]
        elif isinstance(node, ast.ImportFrom) and node.module:
            full = [f"{node.module}.{a.name}" for a in node.names]
            if node.module.split(".")[0] in FORBIDDEN_ROOTS:
                bad.append(node.module)
            bad += [f for f in full if f in FORBIDDEN_MODULES]
    assert not bad, f"brain_queries imports {bad}"


def test_the_guard_can_actually_fail():
    """S47's lesson: a test that proves a guard fires and has never made it
    fire is proving nothing. The same walker, pointed at code that DOES write,
    must flag it -- and must NOT flag a local list, which is the distinction
    the first version of this guard got wrong on its own module."""
    writes = ast.parse("\n".join([
        "from pathlib import Path",
        "def f(p):",
        "    Path(p).write_text('x')"]))
    assert [n for n, _, _ in _calls(writes) if n in ALWAYS_FORBIDDEN]

    module_write = ast.parse("\n".join([
        "from learner import evidence_memory as EM",
        "def f(r):",
        "    EM.append(r)"]))
    aliases = _imported_aliases(module_write)
    assert [(n, rec) for n, rec, _ in _calls(module_write)
            if n in MUTATORS and rec in aliases]

    local_list = ast.parse("\n".join([
        "def f():",
        "    out = []",
        "    out.append(1)",
        "    return out"]))
    assert not [(n, rec) for n, rec, _ in _calls(local_list)
                if n in MUTATORS and rec in _imported_aliases(local_list)]

    bad_import = ast.parse("import subprocess")
    names = [a.name for node in ast.walk(bad_import)
             if isinstance(node, ast.Import) for a in node.names]
    assert "subprocess" in names


def test_the_declared_surface_matches_what_the_module_defines():
    """The doc, the MCP registration and this module cannot fall out of step
    if the list is data and the list is asserted."""
    defined = {n.name for n in TREE.body if isinstance(n, ast.FunctionDef)
               and not n.name.startswith("_")}
    assert set(BQ.SURFACE) <= defined, set(BQ.SURFACE) - defined
    assert set(BQ.SURFACE) == {"panel_query", "farm_query", "receipt",
                               "leaderboard", "books"}
    for name in BQ.SURFACE:
        assert callable(getattr(BQ, name))


def test_the_doc_names_the_same_five_functions():
    doc = (MODULE.parent.parent.parent / "docs" / "OPTIMUS_MCP_SURFACE.md")
    assert doc.is_file(), "the optimus repo needs a contract to wrap"
    text = doc.read_text(encoding="utf-8")
    for name in BQ.SURFACE:
        assert f"{name}(" in text, name
    assert str(BQ.MAX_LIMIT) in text


# ------------------------------------------------------------- the bounds

@pytest.mark.parametrize("bad", [0, -1, BQ.MAX_LIMIT + 1, "many", None])
def test_an_unbounded_or_unreadable_limit_is_REFUSED(bad):
    with pytest.raises(BQ.QueryRefused):
        BQ._check_limit(bad)


def test_every_surface_function_that_takes_a_limit_enforces_the_cap():
    for fn in (BQ.panel_query, BQ.farm_query, BQ.leaderboard, BQ.books):
        with pytest.raises(BQ.QueryRefused):
            fn(limit=BQ.MAX_LIMIT + 1)


# -------------------------------------------------------------- the sandbox

def test_a_path_outside_the_data_root_is_refused_by_name(tmp_path):
    with pytest.raises(BQ.QueryRefused, match="resolves outside"):
        BQ._sandboxed(tmp_path / "elsewhere.json")
    with pytest.raises(BQ.QueryRefused, match="resolves outside"):
        BQ._sandboxed(BQ.DATA() / ".." / ".." / ".." / "somewhere.json")


@pytest.mark.parametrize("bad", ["../../secrets", "a/b", "a\\b", ""])
def test_a_job_name_carrying_a_path_is_refused(bad):
    with pytest.raises(BQ.QueryRefused):
        BQ.receipt(bad)


# ------------------------------------------------------------- the filters

def test_a_query_STRING_is_not_accepted_anywhere():
    """There is no code path that evaluates an expression, so there is nothing
    to inject and nothing to write through."""
    with pytest.raises(BQ.QueryRefused, match="query STRING"):
        BQ._matches({"a": 1}, {"a": "1 OR 1=1"})
    with pytest.raises(BQ.QueryRefused, match="unknown op"):
        BQ._matches({"a": 1}, {"a": {"op": "evaluate", "value": "anything"}})


def test_a_missing_field_never_matches():
    """A filter that quietly passed rows lacking the field it filters on would
    return a superset the caller cannot see."""
    assert BQ._matches({"a": 1}, {"a": {"op": "eq", "value": 1}}) is True
    assert BQ._matches({}, {"a": {"op": "eq", "value": 1}}) is False
    assert BQ._matches({"a": None}, {"a": {"op": "eq", "value": 1}}) is False


@pytest.mark.parametrize("op,value,target,expected", [
    ("eq", "AA", "AA", True), ("ne", "AA", "BB", True),
    ("in", "AA", ["AA", "BB"], True), ("not_in", "CC", ["AA"], True),
    ("gte", 5, 5, True), ("lte", 5, 4, False), ("gt", 5, 5, False),
    ("lt", 4, 5, True), ("between", 5, [1, 10], True),
    ("contains", "hello world", "WORLD", True),
])
def test_each_declared_op_does_what_it_says(op, value, target, expected):
    assert BQ._matches({"f": value},
                       {"f": {"op": op, "value": target}}) is expected


# ------------------------------------------------------- the refusals answer

def test_a_missing_receipt_says_CANNOT_DETERMINE_and_does_not_raise():
    """A caller cannot tell an empty answer from an absent one unless the
    answer says which it is."""
    out = BQ.receipt("no_such_job_at_all")
    assert out["available"] is False
    assert "CANNOT DETERMINE" in out["why"]


def test_a_receipt_that_exists_comes_back_whole():
    out = BQ.receipt("E5_stopping_rules")
    if not out["available"]:                                  # pragma: no cover
        pytest.skip("no E5 receipt on this checkout")
    assert out["receipt"]["job"] == "E5_stopping_rules"
    assert Path(out["path"]).is_file()


def test_every_reply_is_JSON_serialisable():
    """An MCP reply that cannot be serialised is an error on the far side, and
    a `PaperBook` carries a whole nested `Strategy` dataclass."""
    for payload in (BQ.books(limit=2), BQ.farm_query(limit=2),
                    BQ.leaderboard(limit=2),
                    BQ.receipt("no_such_job_at_all")):
        json.dumps(payload)


def test_a_nested_dataclass_is_walked_into_and_not_stringified():
    import dataclasses

    @dataclasses.dataclass
    class Inner:
        x: int = 1

    @dataclasses.dataclass
    class Outer:
        name: str = "o"
        inner: Inner = dataclasses.field(default_factory=Inner)

    out = BQ._jsonable(Outer())
    assert out == {"name": "o", "inner": {"x": 1}}


def test_the_panel_reply_names_what_its_as_of_excluded():
    """On this checkout only a few hundred of 340k panel rows carry a
    `first_seen_utc`, so an `as_of` query returns almost nothing -- and a
    caller who saw only the empty result would read it as 'no news before that
    date' rather than 'the anchor is thin'."""
    out = BQ.panel_query(limit=2, as_of="2026-09-11T12:20:00Z")
    if not out["available"]:                                  # pragma: no cover
        pytest.skip("no news panel on this checkout")
    assert out["as_of_anchor"] == "first_seen_utc"
    assert out["n_dropped_no_readable_anchor"] is not None
    assert "EXCLUDED" in out["pit_note"]
    plain = BQ.panel_query(limit=2)
    assert plain["n_dropped_no_readable_anchor"] is None


def test_an_unparseable_as_of_is_a_refusal_not_a_query_with_no_cutoff():
    with pytest.raises(BQ.QueryRefused, match="cut-off"):
        BQ.panel_query(limit=2, as_of="whenever")
