"""`scripts.runtime_preflight`: the per-task acceptance receipt for "the runtime is a commit".

The failures it encodes were all live on 2026-11-11: scheduled tasks imported an
untracked `provider_budget.py` (no commit held it), the checkout was 269 commits
behind main, and a clean clone pointed at the live data with `AEGIS_DATA_DIR`
alone still wrote through 77 modules' own `REPO/backend/data` paths into its
tracked copy. Every test builds a throwaway git repository under tmp_path; no
network, no real checkout is touched.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import runtime_preflight as RP


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return out.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "checkout"
    (r / "scripts").mkdir(parents=True)
    (r / "backend" / "services").mkdir(parents=True)
    (r / "backend" / "data" / "optimus").mkdir(parents=True)
    (r / "scripts" / "__init__.py").write_text("", encoding="utf-8")
    (r / "backend" / "__init__.py").write_text("", encoding="utf-8")
    (r / "backend" / "services" / "__init__.py").write_text("", encoding="utf-8")
    (r / "backend" / "services" / "budget.py").write_text("CAP = 1\n", encoding="utf-8")
    (r / "scripts" / "job.py").write_text(
        "from backend.services import budget\n"
        "def run():\n"
        "    from backend.services.budget import CAP  # an attribute, not a module\n"
        "    return CAP\n", encoding="utf-8")
    (r / "backend" / "data" / "optimus" / "ledger.jsonl").write_text("{}\n", encoding="utf-8")
    _git(r.parent, "init", "-q", str(r))
    _git(r, "add", ".")
    _git(r, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return r


def _cfg(repo: Path, **kw) -> SimpleNamespace:
    base = dict(OPTIMUS_LEDGER_DIR=repo / "backend" / "data" / "optimus",
                DOTENV_PATH=repo / ".env",
                IC_FUNNEL_PATH=repo / "backend" / "data" / "funnel_night10.json")
    base.update(kw)
    return SimpleNamespace(**base)


def _check(rep: dict, name: str) -> dict:
    return next(r for r in rep["checks"] if r["check"] == name)


def _run(repo: Path, **kw) -> dict:
    args = dict(entries=["scripts.job"], expect_commit="HEAD",
                expect_optimus=repo / "backend" / "data" / "optimus", expect_funnel=None,
                cfg=_cfg(repo), environ={"AEGIS_IGNORE_DOTENV": "1"})
    args.update(kw)
    return RP.run_checks(repo, **args)


def test_a_clean_committed_checkout_passes(repo: Path) -> None:
    rep = _run(repo)
    assert rep["verdict"] == "PASS", rep
    assert _check(rep, "imports")["detail"]["n_modules"] >= 3


def test_an_untracked_module_on_the_import_path_fails_by_name(repo: Path) -> None:
    """The 10-15 `provider_budget.py` shape: the code runs, and no commit holds it."""
    (repo / "backend" / "services" / "shadow.py").write_text("X = 2\n", encoding="utf-8")
    (repo / "scripts" / "job.py").write_text(
        "from backend.services import budget, shadow\n", encoding="utf-8")
    _git(repo, "add", "scripts/job.py")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "import shadow")
    rep = _run(repo)
    imp = _check(rep, "imports")
    assert imp["status"] == "FAIL"
    assert imp["detail"]["untracked_modules"] == ["backend/services/shadow.py"]
    assert _check(rep, "code_clean")["status"] == "FAIL"   # the untracked file is code
    assert rep["verdict"] == "FAIL"


def test_a_module_that_does_not_exist_fails_as_missing(repo: Path) -> None:
    (repo / "scripts" / "job.py").write_text("from backend.services import earnings_deadline\n"
                                             "import backend.services.gone\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "gone")
    imp = _check(_run(repo), "imports")
    assert imp["status"] == "FAIL"
    assert "backend.services.gone" in imp["detail"]["missing"]
    # `from pkg import name` where name is neither a submodule nor bound in the package
    assert "backend.services.earnings_deadline" in imp["detail"]["missing"]


def test_modified_tracked_code_fails_but_data_does_not(repo: Path) -> None:
    (repo / "backend" / "data" / "optimus" / "ledger.jsonl").write_text("{}\n{}\n", encoding="utf-8")
    (repo / "backend" / "data" / "optimus" / "new_receipt.json").write_text("{}", encoding="utf-8")
    assert _check(_run(repo), "code_clean")["status"] == "PASS"
    (repo / "backend" / "services" / "budget.py").write_text("CAP = 2\n", encoding="utf-8")
    cc = _check(_run(repo), "code_clean")
    assert cc["status"] == "FAIL" and cc["detail"]["n_dirty"] == 1


def test_the_wrong_commit_fails(repo: Path) -> None:
    first = _git(repo, "rev-parse", "HEAD")
    (repo / "scripts" / "other.py").write_text("", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "second")
    assert _check(_run(repo, expect_commit=first), "commit")["status"] == "FAIL"
    assert _check(_run(repo, expect_commit="no-such-tag"), "commit")["status"] == "FAIL"
    _git(repo, "tag", "runtime-test")
    assert _check(_run(repo, expect_commit="runtime-test"), "commit")["status"] == "PASS"


def test_an_env_var_data_root_alone_is_a_split_brain(repo: Path, tmp_path: Path) -> None:
    """`AEGIS_DATA_DIR` moves config's paths; the checkout's own backend/data/optimus
    stays where it is, and 77 modules build that path themselves."""
    live = tmp_path / "live" / "optimus"
    live.mkdir(parents=True)
    rep = _run(repo, expect_optimus=live, cfg=_cfg(repo, OPTIMUS_LEDGER_DIR=live))
    dr = _check(rep, "data_root")
    assert dr["status"] == "FAIL"
    assert "SPLIT_BRAIN" in dr["detail"]["why"]


def test_config_pointing_elsewhere_fails(repo: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    dr = _check(_run(repo, cfg=_cfg(repo, OPTIMUS_LEDGER_DIR=other)), "data_root")
    assert dr["status"] == "FAIL"


def test_a_missing_live_data_dir_fails(repo: Path, tmp_path: Path) -> None:
    dr = _check(_run(repo, expect_optimus=tmp_path / "absent"), "data_root")
    assert dr["status"] == "FAIL"
    assert dr["detail"]["expected_exists"] is False


def test_dotenv_must_exist_unless_ignored(repo: Path, tmp_path: Path) -> None:
    assert _check(_run(repo, environ={}), "dotenv")["status"] == "FAIL"
    assert _check(_run(repo), "dotenv")["status"] == "PASS"          # ignored
    keys = tmp_path / "keys.env"
    keys.write_text("A=1\n", encoding="utf-8")
    got = _check(_run(repo, environ={"AEGIS_DOTENV_PATH": str(keys)},
                      cfg=_cfg(repo, DOTENV_PATH=keys)), "dotenv")
    assert got["status"] == "PASS" and got["detail"]["declared_by"] == "AEGIS_DOTENV_PATH"
    assert "A=1" not in str(got), "the preflight must never carry .env contents"


def test_the_funnel_check_runs_only_when_declared(repo: Path, tmp_path: Path) -> None:
    rep = _run(repo)
    assert all(r["check"] != "funnel" for r in rep["checks"])
    shared = tmp_path / "funnel_night10.json"
    assert _check(_run(repo, expect_funnel=shared), "funnel")["status"] == "FAIL"
    assert _check(_run(repo, expect_funnel=shared, cfg=_cfg(repo, IC_FUNNEL_PATH=shared)),
                  "funnel")["status"] == "PASS"


def test_tracked_data_that_differs_is_a_warning_not_a_failure(repo: Path) -> None:
    (repo / "backend" / "data" / "optimus" / "ledger.jsonl").write_text("{}\n{}\n", encoding="utf-8")
    rep = _run(repo)
    td = _check(rep, "tracked_data_through_junction")
    assert td["status"] == "WARN" and td["detail"]["n_tracked_differing"] == 1
    assert rep["verdict"] == "PASS" and rep["warned"] == ["tracked_data_through_junction"]


def test_main_exits_red_on_a_failure(repo: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(RP, "REPO", repo)
    rc = RP.main(["--entry", "scripts.job", "--expect-commit", "no-such-tag",
                  "--expect-optimus", str(repo / "backend" / "data" / "optimus")])
    assert rc == 2
    assert "RUNTIME PREFLIGHT FAIL" in capsys.readouterr().err


# ───────────────────────────────────────────────────────── review 5: B1 pi_db

REPO = Path(__file__).resolve().parents[2]
WIN = sys.platform == "win32"


def _db(path: Path, rows: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE paper_nav (portfolio_id TEXT, computed_at TEXT)")
    con.executemany("INSERT INTO paper_nav VALUES (?, ?)",
                    [(f"b{i}", "2026-11-10T23:58:02+00:00") for i in range(rows)])
    con.commit()
    con.close()
    return path


def test_the_live_database_with_rows_passes(repo: Path, tmp_path: Path) -> None:
    live = _db(tmp_path / "live" / "aegis_pi.db", rows=3)
    row = RP.check_pi_db(repo, live, live)
    assert row["status"] == "PASS", row
    assert row["detail"]["paper_nav_rows"] == 3 and row["detail"]["portfolios"] == 3


@pytest.mark.parametrize("shape", ["no_rows", "zero_bytes", "absent"])
def test_a_new_empty_database_can_never_pass(repo: Path, tmp_path: Path, shape: str) -> None:
    live = tmp_path / "live" / "aegis_pi.db"
    if shape == "no_rows":
        _db(live, rows=0)                              # what init_db leaves: tables, no rows
    elif shape == "zero_bytes":
        live.parent.mkdir(parents=True)
        live.write_bytes(b"")                          # what sqlite3.connect leaves
    row = RP.check_pi_db(repo, live, live)
    assert row["status"] == "FAIL" and "why" in row["detail"]


def test_the_code_opening_another_database_fails(repo: Path, tmp_path: Path) -> None:
    live = _db(tmp_path / "live" / "aegis_pi.db", rows=1)
    other = _db(tmp_path / "clone_db" / "aegis_pi.db", rows=1)
    row = RP.check_pi_db(repo, other, live)
    assert row["status"] == "FAIL" and row["detail"]["same_file"] is False


def test_a_stray_database_in_the_checkout_fails(repo: Path, tmp_path: Path) -> None:
    live = _db(tmp_path / "live" / "aegis_pi.db", rows=1)
    _db(repo / "backend" / "data" / "aegis_pi.db", rows=0)
    row = RP.check_pi_db(repo, live, live)
    assert row["status"] == "FAIL" and row["detail"]["stray_db_in_checkout"] is True


def test_pi_db_is_part_of_the_verdict_when_declared(repo: Path, tmp_path: Path) -> None:
    live = _db(tmp_path / "live" / "aegis_pi.db", rows=0)
    rep = _run(repo, expect_pi_db=live, db_path=live)
    assert rep["verdict"] == "FAIL" and "pi_db" in rep["failed"]


def test_the_check_never_writes_the_database(repo: Path, tmp_path: Path) -> None:
    live = _db(tmp_path / "live" / "aegis_pi.db", rows=2)
    before = (live.stat().st_mtime_ns, live.read_bytes())
    RP.check_pi_db(repo, live, live)
    assert (live.stat().st_mtime_ns, live.read_bytes()) == before


# ───────────────────────────────────────────────────────── review 5: B2 siblings

def _siblings_beside(parent: Path, *, skip: tuple = ()) -> None:
    for s in RP.SIBLINGS:
        if not s["probe"] or s["probe"] in skip:
            continue
        p = parent.joinpath(*s["probe"])
        if p.suffix:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("", encoding="utf-8")
        else:
            p.mkdir(parents=True, exist_ok=True)


def test_every_sibling_present_passes(repo: Path) -> None:
    _siblings_beside(repo.parent)
    row = RP.check_siblings(repo)
    assert row["status"] == "PASS", row["detail"]["missing_fail"]


def test_a_clone_one_level_too_deep_fails(tmp_path: Path) -> None:
    """The original layout: <root>/aegis-runtime/<tag> while the siblings sit beside the live
    checkout. REPO.parent is the wrong directory, so every FAIL probe is missing."""
    _siblings_beside(tmp_path)
    deep = tmp_path / "aegis-runtime" / "runtime-x"
    deep.mkdir(parents=True)
    row = RP.check_siblings(deep)
    assert row["status"] == "FAIL"
    assert any("aegis-alpha-terminal" in p and p.endswith(".env") for p in row["detail"]["missing_fail"])


def test_a_missing_warn_sibling_is_a_warning(repo: Path) -> None:
    warn = next(s["probe"] for s in RP.SIBLINGS if s["level"] == "WARN" and s["probe"])
    _siblings_beside(repo.parent, skip=(warn,))
    assert RP.check_siblings(repo)["status"] == "WARN"


_ROOT_NAMES = {"REPO", "ROOT", "PROJECT_ROOT", "REPO_ROOT", "repo", "_REPO", "_ROOT"}


def _parent_chain_base(node: ast.AST) -> tuple:
    n = 0
    while isinstance(node, ast.Attribute) and node.attr == "parent":
        node, n = node.value, n + 1
    return node, n


def _names_root(node: ast.AST) -> bool:
    """`REPO`, `C.REPO`, `ctx.repo`, `repo_root()`, `Path(_cfg.PROJECT_ROOT)`."""
    if isinstance(node, ast.Name):
        return node.id in _ROOT_NAMES
    if isinstance(node, ast.Attribute):
        return node.attr in _ROOT_NAMES
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Name) and f.id in ("repo_root", "_repo_root"):
            return True
        if isinstance(f, ast.Name) and f.id == "Path" and node.args:
            return _names_root(node.args[0])
    return False


def _is_file_path(node: ast.AST) -> bool:
    """`Path(__file__)` or `Path(__file__).resolve()` (any `pathlib.`/alias prefix)."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "resolve":
        node = node.func.value
    return (isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "__file__")


def sibling_sites(root: Path = REPO) -> list:
    """Every `X.parent / "<name>"` where X is the repo root, every `Path(__file__)` chain that
    climbs OUT of the repo, and every `... / ".." / "<name>"`: (file, line, name). An AST walk,
    so a docstring that mentions the pattern is not an instance (CLAUDE.md protocol item 10)."""
    out = []
    for top in ("backend", "scripts", "nn_lab", "learner", "engine", "lab", "tools"):
        for f in sorted((root / top).rglob("*.py")):
            rel = f.relative_to(root).as_posix()
            if "/tests/" in f"/{rel}" or "__pycache__" in rel:
                continue
            try:
                with warnings.catch_warnings():          # another file's invalid escape is not ours
                    warnings.simplefilter("ignore", SyntaxWarning)
                    tree = ast.parse(f.read_text(encoding="utf-8-sig", errors="replace"))
            except SyntaxError:
                continue
            depth = len(f.relative_to(root).parts) - 1      # directories between the file and REPO
            for node in ast.walk(tree):
                if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
                        and isinstance(node.right, ast.Constant) and isinstance(node.right.value, str)):
                    continue
                left = node.left
                if (isinstance(left, ast.BinOp) and isinstance(left.right, ast.Constant)
                        and left.right.value == ".."):
                    out.append((rel, node.lineno, node.right.value))
                    continue
                base, ups = _parent_chain_base(left)
                if (isinstance(base, ast.Subscript) and isinstance(base.value, ast.Attribute)
                        and base.value.attr == "parents" and isinstance(base.slice, ast.Constant)):
                    ups += int(base.slice.value) + 1
                    base = base.value.value
                if ups == 0:
                    continue
                if _names_root(base):
                    out.append((rel, node.lineno, node.right.value))
                elif _is_file_path(base) and ups > depth + 1:
                    out.append((rel, node.lineno, node.right.value))
    return out


def test_every_sibling_the_code_derives_is_declared() -> None:
    """A new `REPO.parent / "<repo>"` in the code fails here until SIBLINGS declares it, so a
    future move of the clone goes red in the preflight instead of exiting 0."""
    declared = {s["name"] for s in RP.SIBLINGS}
    sites = sibling_sites()
    files = {f for f, _l, _n in sites}
    for must in ("scripts/fleet_manager_run.py", "scripts/task_keeper.py",
                 "backend/services/iif1_prereg.py", "nn_lab/universe_filter.py"):
        assert must in files, f"the walker missed {must}"         # proof that it walks at all
    undeclared = [s for s in sites if s[2] not in declared]
    assert not undeclared, f"undeclared sibling path(s): {undeclared}"


def test_every_declared_sibling_user_really_builds_that_path() -> None:
    """Each SIBLINGS `users` file holds an AST site for that sibling name. The line numbers
    are evidence for a reader and are NOT pinned: an edit above them must not turn this red."""
    sites = {(f, n) for f, _l, n in sibling_sites()}
    for s in RP.SIBLINGS:
        for u in s["users"]:
            f = u.rsplit(":", 1)[0]
            assert (f, s["name"]) in sites, (u, s["name"])


# ───────────────────────────────────────────────────────── review 5: live_state, funnel_age

def _link(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if WIN:
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True,
                       capture_output=True)
    else:
        os.symlink(target, link, target_is_directory=True)


def _unlink(link: Path) -> None:
    """Remove the LINK only, never what it points at."""
    if WIN:
        os.rmdir(link)
    else:
        os.unlink(link)


def test_live_state_junctions_must_resolve_to_the_live_copy(repo: Path, tmp_path: Path) -> None:
    live = tmp_path / "live"
    junctions = [i["path"] for i in RP.LIVE_STATE if i["how"] == "junction"]
    for rel in junctions:
        (live / rel).mkdir(parents=True, exist_ok=True)
    (live / "backend" / "data" / "optimus" / "canary.txt").write_text("live", encoding="utf-8")
    # the fixture has a REAL backend/data/optimus (no junction): a required FAIL
    row = RP.check_live_state(repo, live)
    assert row["status"] == "FAIL" and "backend/data/optimus" in row["detail"]["failed"]
    shutil.rmtree(repo / "backend" / "data" / "optimus")
    try:
        for rel in junctions:
            _link(repo / rel, live / rel)
        row = RP.check_live_state(repo, live)
        assert row["status"] == "PASS", row["detail"]
    finally:
        for rel in junctions:
            if os.path.lexists(repo / rel):
                _unlink(repo / rel)
    assert (live / "backend" / "data" / "optimus" / "canary.txt").exists()


def test_every_live_state_row_says_how_and_why() -> None:
    for item in RP.LIVE_STATE:
        assert item["how"] in ("junction", "env", "tag", "absent", "decision"), item
        assert item["why"].strip(), item
    paths = {i["path"] for i in RP.LIVE_STATE}
    for must in ("backend/data/aegis_pi.db", "backend/data/funnel_night10.json",
                 "backend/data/funnel_history", "ft_lab/data", "docs (generated)"):
        assert must in paths


def test_funnel_age_warns_and_prints_both_stamps(tmp_path: Path) -> None:
    mine = tmp_path / "clone" / "funnel_night10.json"
    live = tmp_path / "live" / "funnel_night10.json"
    mine.parent.mkdir()
    live.parent.mkdir()
    mine.write_text(json.dumps({"generated_at": "2026-10-06T15:51:08+00:00"}), encoding="utf-8")
    live.write_text(json.dumps({"generated_at": "2026-11-05T19:18:48+00:00"}), encoding="utf-8")
    now = datetime(2026, 11, 11, tzinfo=timezone.utc)      # a fixed clock: no calendar moment
    row = RP.check_funnel_age(mine, live, now=now)
    assert row["status"] == "WARN"
    assert row["detail"]["serves_age_days"] == pytest.approx(35.3, abs=0.1)
    assert row["detail"]["live_age_days"] == pytest.approx(5.2, abs=0.1)
    assert RP.check_funnel_age(live, live, now=now)["status"] == "PASS"
