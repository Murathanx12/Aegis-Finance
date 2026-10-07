"""Every reader of the forecast ledger goes through `forecast_ledger`, or says why not.

After the attended split (`scripts.ledger_split --apply`), `predictions.jsonl` is a
FROZEN file: every new forecast and every new grade lands in the monthly streams.
A reader that opens the legacy path directly keeps working -- and silently reads a
ledger that stopped growing on the day of the migration. Nothing would be red.

So this is an enrolment gate, the same shape as the guard contract and the
reachability audit: every place in code (not in a docstring; protocol item 10) that
names the ledger file, and every direct read of a ledger-path constant, is either
routed through `backend.services.forecast_ledger` or listed below with the reason it
may touch the file itself. A new one fails until somebody decides which.
"""

from __future__ import annotations

import ast
import functools
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOTS = ("backend", "scripts", "nn_lab", "learner", "desktop", "engine", "lab")
LITERAL = "predictions.jsonl"
#: Names that hold the ledger's path in this codebase.
PATH_NAMES = {"PREDICTIONS", "PREDICTIONS_PATH", "FORECAST_LEDGER"}
#: Calls that read or write the bytes of a path (not `.exists()` / `.stat()`).
BYTE_CALLS = {"open", "read_text", "read_bytes", "write_text", "write_bytes"}
#: Module-level copies of a path's bytes: `shutil.copy2(PREDICTIONS, ...)` is a
#: read of the frozen file just as surely as `open(PREDICTIONS)` is.
COPY_CALLS = {"copy", "copy2", "copyfile", "move"}

#: file -> why it may NAME the ledger file. "via the layer" means its reads were
#: checked to go through forecast_ledger (read_rows / logical_lines / tail_lines /
#: exists / fingerprint) or through belief_state, which does.
NAMES_THE_FILE: dict[str, str] = {
    "backend/services/forecast_ledger.py": "the layer itself (LEGACY_NAME)",
    "backend/services/belief_state.py": "defines PREDICTIONS; read/append/resolve go through the layer",
    "backend/services/evidence_population.py": "LEDGER_FILE names the logical ledger; reads via the layer",
    "backend/services/forecast_populations.py": "declares where each population lives; reads via belief_state",
    "backend/services/arena/store.py": "the ARENA's own ledger, a separate logical ledger (legacy by design)",
    "backend/services/ledger_archive.py": "NEVER-archive list",
    "backend/services/accrual_canary.py": "via the layer (forecast_accrual)",
    "backend/services/daily_review.py": "via the layer (_tail_rows -> tail_lines)",
    "backend/services/expected_return.py": "via the layer (forecast_reputation.load_ledger)",
    "backend/services/fast_mover_forensics.py": "via the layer (logical_lines)",
    "backend/services/forecast_reputation.py": "via the layer (load_ledger -> read_rows)",
    "backend/services/legibility.py": "via the layer (read_rows, fingerprint)",
    "backend/services/query_planner.py": "via the layer (logical_lines, fingerprint)",
    "backend/services/system_health.py": "via the layer (logical_lines; accrual canary)",
    "nn_lab/config.py": "FORECAST_LEDGER, read by nn_lab.table.ledger via the layer",
    "scripts/bridge_report.py": "via the layer (magnitude_rows -> logical_lines)",
    "scripts/daily_learning_report.py": "via the layer (read_rows; accrual canary)",
    "scripts/decision_autopsy.py": "via the layer (load_predictions -> logical_lines)",
    "scripts/iif1_grade.py": "default --ledger path, read by iif1_grader.load_records via the layer",
    "scripts/night_error_dataset.py": "via the layer (build -> read_rows)",
    "scripts/night_specialist_scoreboard.py": "via the layer (load -> read_rows)",
    "scripts/stock_lists_v3_build.py": ("a dated 2026-09-27 one-off document builder that reads rows "
                                        "made 2026-09-26; the frozen legacy file still holds them"),
    "scripts/verify_live_forward_disarm.py": "writes a scratch ledger in a temp dir for its own check",
}

#: file -> why it may OPEN a ledger-path constant's bytes directly.
OPENS_THE_FILE: dict[str, str] = {
    "backend/services/forecast_ledger.py": "the layer itself",
}


#: Modules a "via the layer" reader may reach the layer THROUGH; each of them is
#: itself checked to reference forecast_ledger.
INTERMEDIARIES = ("forecast_ledger", "belief_state", "forecast_reputation", "accrual_canary",
                  "iif1_grader")


def _py_files(repo: Path):
    for root in ROOTS:
        base = repo / root
        if not base.exists():
            continue
        for f in sorted(base.rglob("*.py")):
            rel = f.relative_to(repo).as_posix()
            if "/tests/" in rel or f.name.startswith("test_") or "node_modules" in rel:
                continue
            yield rel, f


def _docstring_ids(tree: ast.AST) -> set[int]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                out.add(id(body[0].value))
    return out


@functools.lru_cache(maxsize=4)
def _scan(repo: Path = REPO):
    names, opens = {}, {}
    for rel, f in _py_files(repo):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        docs = _docstring_ids(tree)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in docs
                    and (node.value == LITERAL or node.value.endswith("/" + LITERAL))):
                names.setdefault(rel, []).append(node.lineno)
            if isinstance(node, ast.Call):
                target = None
                if isinstance(node.func, ast.Name) and node.func.id == "open" and node.args:
                    target = node.args[0]
                elif (isinstance(node.func, ast.Attribute) and node.func.attr in COPY_CALLS
                      and isinstance(node.func.value, ast.Name) and node.func.value.id == "shutil"
                      and node.args):
                    target = node.args[0]
                elif isinstance(node.func, ast.Attribute) and node.func.attr in BYTE_CALLS:
                    target = node.func.value
                tname = (target.id if isinstance(target, ast.Name) else
                         target.attr if isinstance(target, ast.Attribute) else None)
                if tname in PATH_NAMES:
                    opens.setdefault(rel, []).append(node.lineno)
    return names, opens


def test_every_file_naming_the_ledger_is_classified():
    names, _ = _scan()
    unclassified = sorted(set(names) - set(NAMES_THE_FILE))
    assert not unclassified, (
        f"these files name {LITERAL} in code and are not classified: "
        f"{ {k: names[k] for k in unclassified} }. Route their reads through "
        f"backend.services.forecast_ledger (read_rows / logical_lines / tail_lines / exists), "
        f"then add them to NAMES_THE_FILE with how they read; after the split, a direct "
        f"read sees a frozen file.")


def test_the_classification_has_no_stale_entries():
    names, _ = _scan()
    stale = sorted(set(NAMES_THE_FILE) - set(names))
    assert not stale, f"no longer name the ledger, remove from NAMES_THE_FILE: {stale}"


def test_nothing_opens_a_ledger_path_constant_directly():
    _, opens = _scan()
    direct = {k: v for k, v in opens.items() if k not in OPENS_THE_FILE}
    assert not direct, (
        f"direct byte access to a ledger-path constant ({sorted(PATH_NAMES)}): {direct}. "
        f"Use backend.services.forecast_ledger instead.")


def test_the_layer_is_what_the_via_the_layer_files_import():
    for mod in INTERMEDIARIES[1:]:
        src = (REPO / "backend" / "services" / f"{mod}.py").read_text(encoding="utf-8")
        assert "forecast_ledger" in src, f"{mod} no longer routes through forecast_ledger"
    for rel, why in NAMES_THE_FILE.items():
        if not why.startswith("via the layer"):
            continue
        src = (REPO / rel).read_text(encoding="utf-8")
        assert any(m in src for m in INTERMEDIARIES), rel


def test_the_scanner_sees_a_bypass_when_there_is_one(tmp_path):
    """The gate on the gate: a planted direct reader is found."""
    pkg = tmp_path / "scripts"
    pkg.mkdir()
    (pkg / "bypass.py").write_text(
        '"""mentions predictions.jsonl in a docstring, which is fine"""\n'
        "from pathlib import Path\n"
        "PREDICTIONS = Path('x') / 'predictions.jsonl'\n"
        "rows = PREDICTIONS.read_text()\n"
        "import shutil\n"
        "shutil.copy2(PREDICTIONS, 'elsewhere.jsonl')\n", encoding="utf-8")
    names, opens = _scan(tmp_path)
    assert names == {"scripts/bypass.py": [3]}
    assert opens == {"scripts/bypass.py": [4, 6]}
