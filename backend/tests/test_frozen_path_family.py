"""The frozen-path defect FAMILY, turned from a category into a gate.

2026-09-10 produced five instances of one bug in a single day (an empty DB in
the bundle, a dropped vendored schema, the model-server ownership note, an
`AEGIS_DATA_DIR` that doubled, `sys.executable -m`), and 2026-09-11 found a
sixth: `backend/config.py` rooted `.env` on `__file__`, so the packaged app ran
with every key absent and `load_dotenv` said nothing, because loading a missing
file is a silent no-op.

The shape is always the same. From source, `Path(__file__)` resolves correctly
and nothing fails. Inside PyInstaller `__file__` is `<dist>/_internal/...`, and
code that never mentions `__file__` starts reading a directory that has no data
in it. So: **a runtime artefact addressed from `__file__` is a defect unless it
is either allow-listed with a reason, or resolved through `AEGIS_REPO_ROOT`.**

The walk is an AST walk, not a grep (protocol item 10): three guards failed on
their first run this month by matching the docstring that EXPLAINS the banned
pattern, and the next reader deletes the explanation to make the suite green.
Docstrings and comments are invisible here by construction.

Scope and its limits, stated so nobody over-reads a green line:

* files walked: `backend/**/*.py` (tests excluded), `desktop/*.py`,
  `scripts/night_factory*.py`;
* a hit is an expression ROOTED on `Path(__file__)` -- directly, or through a
  module-level constant assigned from one -- whose joined string literals reach
  a runtime artefact (`.env`, `data`, `vendor`, `optimus`, or a `.json`,
  `.jsonl`, `.db`, `.parquet` name);
* taint does NOT cross a function boundary or a module, and a name whose
  assignment consults `AEGIS_REPO_ROOT` stops the taint, because consulting the
  override is exactly the fix this gate asks for.

This gate therefore catches the family's SHAPE. It is a tripwire, not a proof.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: a path segment naming a runtime artefact directory
_ARTEFACT_DIRS = {".env", "data", "vendor", "optimus"}
#: a file whose content is runtime state rather than code
_ARTEFACT_SUFFIXES = (".json", ".jsonl", ".db", ".parquet")

#: the env var that makes a `__file__` root harmless
_OVERRIDE = "AEGIS_REPO_ROOT"

# --------------------------------------------------------------------------
# The allow-list. Every entry is a (path, artefact literal) pair and ONE line
# saying why the bundle-relative answer is the CORRECT answer there. An entry
# without a reason is an entry nobody can review.
# --------------------------------------------------------------------------
#: `scripts/` is NEVER frozen. `desktop/AegisDesktop.spec` excludes the package
#: outright ("OUT: torch, transformers, and the `scripts`/`learner` packages"),
#: and every night job is spawned as a SUBPROCESS of the checkout's interpreter
#: by `backend.routers.control.job_python()`. `__file__` in those modules is
#: therefore already a checkout path, on both source and packaged runs.
_SCRIPTS_NEVER_FROZEN = (
    "scripts/ is excluded from the bundle and night jobs run as subprocesses of the "
    "checkout's interpreter, so __file__ is already the checkout")

#: The backend IS frozen today, and `backend/data/**` is deliberately NOT in the
#: bundle (the spec skips it by name; sweeping it in is what produced a 1.1 GB
#: onedir). So these resolve into `_internal/backend/data/...`, which does not
#: exist, and every one of them reads or writes nothing in the packaged app.
#: They are recorded here rather than left invisible. The real fix is the thin
#: launcher (handoff 2026-09-11 section 1.3): the shell runs the backend FROM
#: the checkout, at which point `__file__` is a checkout path again. Until that
#: lands, an entry removed from this list must be a path routed through a root
#: resolver, never a path that merely stopped being scanned.
_PENDING_LAUNCHER = (
    "mutable state under backend/data, which the bundle does not ship; resolved for real by the "
    "thin launcher that runs the backend from the checkout (handoff 2026-09-11 s1.3)")

#: Committed, immutable, read-only vintage data. Bundle-relative is the RIGHT
#: answer in principle -- the pinned file belongs to the code that pins it --
#: but the spec does not copy `backend/data`, so in the packaged app the file is
#: absent and the caller must degrade loudly rather than silently substitute a
#: live download.
_PINNED_VINTAGE = (
    "committed read-only pinned vintage that belongs to the code version, not to the checkout's "
    "mutable state; absent from the bundle, so the caller must degrade loudly")

ALLOW: dict[tuple[str, str], str] = {
    ("backend/services/cmp_insider.py", "data"): _PENDING_LAUNCHER,
    ("backend/services/factor_model.py", "data"): _PINNED_VINTAGE,
    ("backend/services/factor_model.py", "ff_daily_pinned_VINTAGE.json"): _PINNED_VINTAGE,
    ("backend/services/llm_telemetry.py", "llm_calls.jsonl"): _PENDING_LAUNCHER,
    ("backend/services/pm_reconcile.py", "conviction_decisions_snapshot.json"): _PENDING_LAUNCHER,
    ("backend/services/shadow_portfolios.py", "shadow_decisions.jsonl"): _PENDING_LAUNCHER,
    ("backend/services/shadow_portfolios.py", "learning_samples.jsonl"): _PENDING_LAUNCHER,
    ("backend/services/taq_calibration.py", "optimus"): _PENDING_LAUNCHER,
    ("backend/services/transaction_ensemble.py", "conviction_decisions_snapshot.json"): _PENDING_LAUNCHER,
    ("backend/strategy/adapters.py", "optimus"): _PENDING_LAUNCHER,
    ("backend/strategy/adapters.py", "G4_CHAMPION_DECLARATION.json"): _PENDING_LAUNCHER,
    ("backend/strategy/adapters.py", "G4_seal.json"): _PENDING_LAUNCHER,
    ("scripts/night_factory.py", "optimus"): _SCRIPTS_NEVER_FROZEN,
    ("scripts/night_factory.py", ".json"): _SCRIPTS_NEVER_FROZEN,
    ("scripts/night_factory_jobs.py", "optimus"): _SCRIPTS_NEVER_FROZEN,
    ("scripts/night_factory_jobs.py", "R4_earnings_events.parquet"): _SCRIPTS_NEVER_FROZEN,
    ("scripts/night_factory_jobs.py", "R4_placebo_offset40.parquet"): _SCRIPTS_NEVER_FROZEN,
    ("scripts/night_factory_jobs.py", "train_table_long.parquet"): _SCRIPTS_NEVER_FROZEN,
    ("scripts/night_factory_jobs.py", "G1_evaluations.jsonl"): _SCRIPTS_NEVER_FROZEN,
    ("scripts/night_factory_jobs.py", "G1_evolve_run01.json"): _SCRIPTS_NEVER_FROZEN,
    ("scripts/night_factory_jobs.py", "N1_configs_smoke.jsonl"): _SCRIPTS_NEVER_FROZEN,
    ("scripts/night_factory_jobs.py", ".parquet"): _SCRIPTS_NEVER_FROZEN,
    ("scripts/night_factory_jobs.py", "D1_primary_daily.parquet"): _SCRIPTS_NEVER_FROZEN,
    ("scripts/night_factory_jobs.py", ".json"): _SCRIPTS_NEVER_FROZEN,
}


def _files() -> list[Path]:
    out: list[Path] = []
    for p in sorted((REPO / "backend").rglob("*.py")):
        rel = p.relative_to(REPO).as_posix()
        if rel.startswith("backend/tests"):
            continue
        out.append(p)
    out += sorted((REPO / "desktop").glob("*.py"))
    out += sorted((REPO / "scripts").glob("night_factory*.py"))
    return out


def _is_path_file_call(node: ast.AST) -> bool:
    """`Path(__file__)` -- the root of the whole family."""
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name) and node.func.id == "Path"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Name) and node.args[0].id == "__file__")


def _root_name(node: ast.AST) -> str | None:
    """The NAME at the bottom of an attribute/call/division chain, if any.

    `REPO / "backend" / "data"` -> `REPO`; `X.parent.parent / "a"` -> `X`.
    """
    cur: ast.AST = node
    while True:
        if isinstance(cur, ast.Name):
            return cur.id
        if isinstance(cur, ast.Attribute):
            cur = cur.value
        elif isinstance(cur, ast.Call):
            cur = cur.func
        elif isinstance(cur, ast.BinOp) and isinstance(cur.op, ast.Div):
            cur = cur.left
        else:
            return None


def _rooted_on_file(node: ast.AST) -> bool:
    cur: ast.AST = node
    while True:
        if _is_path_file_call(cur):
            return True
        if isinstance(cur, ast.Attribute):
            cur = cur.value
        elif isinstance(cur, ast.Call):
            cur = cur.func
        elif isinstance(cur, ast.BinOp) and isinstance(cur.op, ast.Div):
            cur = cur.left
        else:
            return False


def _literals(node: ast.AST) -> list[str]:
    """Every string constant inside the expression (join arguments included)."""
    return [n.value for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _reaches_artefact(lits: list[str]) -> str | None:
    for lit in lits:
        for seg in str(lit).replace("\\", "/").split("/"):
            s = seg.strip().lower()
            if s in _ARTEFACT_DIRS or s.endswith(_ARTEFACT_SUFFIXES):
                return lit
    return None


def _mentions_override(node: ast.AST) -> bool:
    """Does this subtree consult `AEGIS_REPO_ROOT` (getenv or environ)?"""
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and n.value == _OVERRIDE:
            return True
        if isinstance(n, ast.Attribute) and n.attr == "environ":
            return True
    return False


def _tainted_module_names(tree: ast.Module) -> set[str]:
    """Module-level constants that ARE a `Path(__file__)` root, transitively.

    A name whose assignment consults `AEGIS_REPO_ROOT` is NOT tainted: that
    assignment is the fix, not the defect.
    """
    tainted: set[str] = set()
    assigns: list[tuple[str, ast.AST]] = []
    for stmt in tree.body:
        if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)):
            assigns.append((stmt.targets[0].id, stmt.value))
        elif (isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
                and stmt.value is not None):
            assigns.append((stmt.target.id, stmt.value))
    changed = True
    while changed:
        changed = False
        for name, value in assigns:
            if name in tainted or _mentions_override(value):
                continue
            roots = {_root_name(v) for v in ast.walk(value)
                     if isinstance(v, (ast.BinOp, ast.Attribute, ast.Call))}
            if any(_rooted_on_file(v) for v in ast.walk(value)) or (roots & tainted):
                tainted.add(name)
                changed = True
    return tainted


def _enclosing_functions(tree: ast.Module) -> dict[int, ast.AST]:
    """Line number -> the innermost function that owns it."""
    owner: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for line in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                owner[line] = node
    return owner


def scan_source(src: str, rel: str) -> list[tuple[str, int, str, str]]:
    """(relative path, line, the artefact literal, the source line)."""
    tree = ast.parse(src)
    lines = src.splitlines()
    tainted = _tainted_module_names(tree)
    owner = _enclosing_functions(tree)
    hits: list[tuple[str, int, str, str]] = []
    seen: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.BinOp, ast.Call, ast.Attribute)):
            continue
        if isinstance(node, ast.BinOp) and not isinstance(node.op, ast.Div):
            continue
        root = _root_name(node)
        if not (_rooted_on_file(node) or (root is not None and root in tainted)):
            continue
        art = _reaches_artefact(_literals(node))
        if art is None:
            continue
        line = node.lineno
        if line in seen:
            continue
        # the fix: an expression, or the function around it, that reads the override
        fn = owner.get(line)
        if _mentions_override(node) or (fn is not None and _mentions_override(fn)):
            continue
        seen.add(line)
        hits.append((rel, line, str(art), lines[line - 1].strip()[:120]))
    return hits


def scan(path: Path) -> list[tuple[str, int, str, str]]:
    # utf-8-SIG: `backend/routers/portfolio.py` carries a BOM, and `ast.parse`
    # refuses U+FEFF outright -- a walker that crashes on one file is a gate
    # that silently stops covering the rest.
    return scan_source(path.read_text(encoding="utf-8-sig"),
                       path.relative_to(REPO).as_posix())


def test_every_file_rooted_runtime_path_is_allow_listed_or_override_aware() -> None:
    offenders: list[str] = []
    for path in _files():
        for rel, line, art, text in scan(path):
            if (rel, art) in ALLOW:
                continue
            offenders.append(f"{rel}:{line}  reaches {art!r}\n        {text}")
    assert not offenders, (
        "a runtime artefact is addressed from `Path(__file__)` and is neither allow-listed nor "
        "resolved through AEGIS_REPO_ROOT -- inside the packaged app these read `_internal/`, "
        "which is empty, and they fail silently:\n  " + "\n  ".join(offenders))


def test_the_allow_list_is_reviewable() -> None:
    """Every entry names a real file and carries a reason a person can check."""
    for (rel, art), reason in ALLOW.items():
        assert (REPO / rel).exists(), f"allow-list entry for a file that no longer exists: {rel}"
        assert len(reason) > 20, f"allow-list entry {rel}:{art} has no usable reason"


def test_the_allow_list_has_no_stale_entries() -> None:
    """An entry whose hit is gone is a line nobody will ever delete otherwise.

    A list that only grows stops being a review surface. When a path is fixed —
    routed through a root resolver — its entry must go with it.
    """
    live = {(rel, art) for path in _files() for rel, _line, art, _t in scan(path)}
    stale = sorted(k for k in ALLOW if k not in live)
    assert not stale, ("these allow-list entries no longer match any hit; the path was fixed or "
                       "moved, so delete the entry: " + ", ".join(map(str, stale)))


def test_config_dotenv_is_not_allow_listed() -> None:
    """`.env` in `backend/config.py` must pass by the FIX, never by exemption."""
    assert not any(rel == "backend/config.py" for rel, _ in ALLOW)


# ------------------------------------------------------------ the gate's own gate
#
# A gate that cannot go red is not a strict gate, it is a decoration. These two
# run the walker over source it does not read from disk, so the failure mode
# "the walk silently stopped matching anything" is itself caught.

_OFFENDER = '''
from pathlib import Path
LEDGER = Path(__file__).resolve().parent / "data" / "spend.jsonl"
'''

_FIXED = '''
import os
from pathlib import Path


def _root():
    env = os.getenv("AEGIS_REPO_ROOT")
    return Path(env).resolve() if env and Path(env).is_dir() else Path(__file__).resolve().parent


def ledger():
    return _root() / "data" / "spend.jsonl"
'''


def test_the_walker_catches_the_defect_it_was_written_for() -> None:
    hits = scan_source(_OFFENDER, "synthetic/offender.py")
    assert hits, "the walker stopped recognising the family it exists to catch"
    assert hits[0][2] in ("data", "spend.jsonl")


def test_the_walker_clears_a_path_that_reads_the_override() -> None:
    assert scan_source(_FIXED, "synthetic/fixed.py") == []
