"""Every ledger-writing service must resolve storage through
`config.OPTIMUS_LEDGER_DIR`, and nothing may resolve it from an environment
variable that the deployment does not set.

WHAT THIS COST, 2026-08-25
==========================
`options_pit_store._root()` read `os.environ["OPTIMUS_LEDGER_DIR"]` — a
variable set nowhere — and fell through to `backend/data/optimus/options_pit`,
a path INSIDE THE CONTAINER IMAGE. Railway sets `AEGIS_DATA_DIR=/data` and
mounts the volume there; `config.OPTIMUS_LEDGER_DIR` honours that and every
other ledger service imports it.

So the option-state store was ephemeral. The gate read
`options_pit accruing: ok rows=179 days=1` before a deploy and
`ABSENT rows=0 days=0` after it, and `days_held` had never once exceeded 1 —
the same fact from the other side. `monday_gate_check` states the cost in its
own words: *option chains have NO history; a missed day is gone.*

It also hid itself from the suite: the rest of the tests override storage by
monkeypatching `config.OPTIMUS_LEDGER_DIR`, which this module ignored. Its
tests exercised a resolution path production never used.

This guard exists because an actual failure showed it was necessary, which is
the standing bar for adding one.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SERVICES = Path(__file__).resolve().parents[1] / "services"

#: Reading the env var is allowed only as a first-priority override with a
#: config-backed fallback. This pattern catches the shape that bit us: an env
#: read whose `else` branch reconstructs a path from `__file__`.
_FROM_FILE = re.compile(r"Path\(__file__\)\.resolve\(\)\.parents\[\d+\]\s*/\s*[\"']data[\"']")


def _service_files() -> list[Path]:
    return sorted(p for p in SERVICES.rglob("*.py")
                  if "__pycache__" not in p.parts)


#: A function may rebuild the old image path when its whole job is to migrate
#: OFF it. Rows there cannot be recreated, so the path has to stay reachable.
_LEGACY_OK = ("legacy",)


def _functions_matching(src: str, pattern) -> list[str]:
    """Names of the functions whose source contains `pattern`.

    AST rather than a whole-file scan, because the file-level answer cannot
    distinguish the live root resolution from a named legacy path kept for
    migration — and on 2026-08-25 the whole-file version failed the very
    module that had just been fixed.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    lines = src.splitlines()
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = "\n".join(lines[node.lineno - 1:(node.end_lineno or node.lineno)])
        if pattern.search(body):
            out.append(node.name)
    return out


def test_the_active_root_resolution_never_comes_from_dunder_file():
    """THE REGRESSION. A ledger path rebuilt from `__file__` points into the
    deployed image, which on Railway is wiped by every deploy.

    Scoped to the function that resolves the ACTIVE root: `_legacy_root()` is
    allowed to name the old path precisely so `migrate_legacy()` can rescue
    what is stranded there."""
    offenders = []
    for p in _service_files():
        src = p.read_text(encoding="utf-8", errors="replace")
        if "OPTIMUS_LEDGER_DIR" not in src:
            continue
        for fn in _functions_matching(src, _FROM_FILE):
            if any(tok in fn.lower() for tok in _LEGACY_OK):
                continue
            offenders.append(f"{p.relative_to(SERVICES).as_posix()}::{fn}")
    assert not offenders, (
        f"these resolve a ledger path from __file__ instead of "
        f"config.OPTIMUS_LEDGER_DIR, so they write inside the container image "
        f"and every deploy destroys them: {offenders}")


def test_the_guard_still_catches_the_original_defect():
    """A guard narrowed to fix a false positive must still fail the true one."""
    buggy = (
        "OPTIMUS_LEDGER_DIR\n"
        "def _root():\n"
        "    env = os.environ.get('OPTIMUS_LEDGER_DIR')\n"
        "    base = Path(env) if env else "
        "Path(__file__).resolve().parents[1] / 'data' / 'optimus'\n"
        "    return base / 'options_pit'\n")
    assert _functions_matching(buggy, _FROM_FILE) == ["_root"]

    allowed = buggy.replace("def _root():", "def _legacy_root():")
    names = _functions_matching(allowed, _FROM_FILE)
    assert names == ["_legacy_root"]
    assert all(any(t in n.lower() for t in _LEGACY_OK) for n in names)


def test_env_read_of_ledger_dir_always_has_a_config_fallback():
    """Reading the env var is fine. Reading it WITHOUT falling back to config
    is what made options_pit ephemeral."""
    offenders = []
    for p in _service_files():
        src = p.read_text(encoding="utf-8", errors="replace")
        if 'environ.get("OPTIMUS_LEDGER_DIR")' not in src and \
           "environ.get('OPTIMUS_LEDGER_DIR')" not in src:
            continue
        if "OPTIMUS_LEDGER_DIR" not in src.replace("environ", ""):
            offenders.append(p.relative_to(SERVICES).as_posix())
            continue
        if "config" not in src:
            offenders.append(p.relative_to(SERVICES).as_posix())
    assert not offenders, (
        f"these read OPTIMUS_LEDGER_DIR from the environment with no "
        f"config-backed fallback: {offenders}")


def test_options_pit_root_follows_the_configured_ledger_dir(monkeypatch, tmp_path):
    """The specific module, and the specific override the suite relies on.

    Monkeypatching `config.OPTIMUS_LEDGER_DIR` must move the store. It did not
    before the fix, because the module never consulted config at all."""
    from backend import config as _config
    from backend.services import options_pit_store as ops

    monkeypatch.delenv("OPTIMUS_LEDGER_DIR", raising=False)
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", tmp_path)
    root = ops._root()
    assert root == tmp_path / "options_pit", root


def test_options_pit_env_var_still_wins_when_set(monkeypatch, tmp_path):
    from backend.services import options_pit_store as ops

    monkeypatch.setenv("OPTIMUS_LEDGER_DIR", str(tmp_path))
    assert ops._root() == tmp_path / "options_pit"


def test_root_is_read_at_call_time_not_bound_at_import(monkeypatch, tmp_path):
    """Binding the config value at import would silently ignore every
    monkeypatch in the suite — the same class of bug one level along."""
    from backend import config as _config
    from backend.services import options_pit_store as ops

    monkeypatch.delenv("OPTIMUS_LEDGER_DIR", raising=False)
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", tmp_path / "a")
    first = ops._root()
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", tmp_path / "b")
    assert ops._root() != first


@pytest.mark.parametrize("mod,attr", [
    ("backend.services.event_store", None),
    ("backend.services.arena.store", "ROOT"),
])
def test_neighbouring_stores_already_resolve_through_config(mod, attr):
    """Sanity anchor: the modules that survived the deploy do it the right way,
    which is why arena seeds and event_store persisted while options_pit did
    not. If this ever fails, the comparison in the docstring above is stale."""
    import importlib

    m = importlib.import_module(mod)
    src = Path(m.__file__).read_text(encoding="utf-8", errors="replace")
    assert "OPTIMUS_LEDGER_DIR" in src
    assert not _functions_matching(src, _FROM_FILE)


def test_guard_scans_a_plausible_number_of_services():
    """A registry guard that silently matches nothing passes forever."""
    scanned = [p for p in _service_files()
               if "OPTIMUS_LEDGER_DIR" in p.read_text(encoding="utf-8",
                                                      errors="replace")]
    assert len(scanned) >= 15, (
        f"only {len(scanned)} services mention OPTIMUS_LEDGER_DIR; the guard "
        f"is probably looking in the wrong place")


def test_every_scanned_service_parses():
    """The regex scan is cheap but blind; make sure it is reading real Python
    rather than silently skipping files that fail to parse."""
    for p in _service_files():
        src = p.read_text(encoding="utf-8", errors="replace")
        if "OPTIMUS_LEDGER_DIR" not in src:
            continue
        try:
            ast.parse(src)
        except SyntaxError as e:                     # pragma: no cover
            pytest.fail(f"{p.name} does not parse: {e}")


# --------------------------------------------------------------------------
# Moving a store is only half the job. Rows left at the OLD path have to be
# rescued, because an option chain taken before its event cannot be recreated.
# --------------------------------------------------------------------------
def test_migrate_legacy_is_a_noop_when_paths_coincide(monkeypatch, tmp_path):
    """Locally AEGIS_DATA_DIR is unset, so root == legacy_root. Copying a file
    onto itself must not happen."""
    from backend.services import options_pit_store as ops

    monkeypatch.delenv("OPTIMUS_LEDGER_DIR", raising=False)
    monkeypatch.setattr(ops, "_legacy_root", lambda: tmp_path / "same")
    out = ops.migrate_legacy(root=tmp_path / "same")
    assert out["status"] == "nothing to do"
    assert out["rows_migrated"] == 0


def test_migrate_legacy_rescues_rows_onto_the_volume(monkeypatch, tmp_path):
    import json as _json
    from dataclasses import asdict

    from backend.services import options_pit_store as ops

    legacy, dest = tmp_path / "image", tmp_path / "volume"
    legacy.mkdir()
    fields = {f: 0.0 for f in ops.OptionState.__dataclass_fields__}
    fields.update(ticker="AAPL", as_of="2026-08-24")
    state = ops.OptionState(**{k: v for k, v in fields.items()})
    (legacy / "option_state_2026-08.jsonl").write_text(
        _json.dumps(asdict(state), default=str) + "\n", encoding="utf-8")

    monkeypatch.setattr(ops, "_legacy_root", lambda: legacy)
    out = ops.migrate_legacy(root=dest)
    assert out["rows_migrated"] == 1, out
    assert (dest / "option_state_2026-08.jsonl").exists()

    # WRITE-ONCE: a second run rescues nothing and replaces nothing
    again = ops.migrate_legacy(root=dest)
    assert again["rows_migrated"] == 0
    assert again["skipped"] == 1


def test_health_names_the_directory_it_looked_in(tmp_path):
    """ABSENT without a path is what made this take an hour to diagnose."""
    from backend.services import options_pit_store as ops

    h = ops.health(root=tmp_path / "nothing-here")
    assert h["status"] == "ABSENT"
    assert "root" in h and str(tmp_path) in h["root"]
    assert "legacy_root" in h and "legacy_files" in h


def test_capture_job_rescues_before_it_captures():
    """The migration has to run somewhere that actually executes in prod."""
    from pathlib import Path as _P

    src = _P("backend/services/portfolio_intelligence/scheduler.py").read_text(
        encoding="utf-8")
    i = src.index("async def _options_pit_capture")
    body = src[i:i + 2000]
    assert "migrate_legacy" in body
    assert body.index("migrate_legacy") < body.index("ops.capture")
