"""CH-57: three guards that refuse BEFORE damage, each with a named reason and a non-zero exit.

(a) DATABASE  `backend.config` refuses to let a process that runs from a release clone
              (`aegis-runtime-<tag>`) without the wrapper CREATE a database file there.
(b) TESTS     `backend/tests/conftest.py` aborts the session when the checkout is a release
              clone or a data directory resolves, through a junction, outside the checkout.
(c) MEMORY    `scripts/runtime_task.py --min-free-gb N` refuses with `LOW_MEMORY` below the
              task's declared floor; with no floor declared nothing changes.

Everything is synthetic and under `tmp_path`: simulated clones, a real junction between two
temp folders, an injected free-memory figure. Nothing touches the live data or a real clone.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from backend import config as C
from backend.tests import conftest as CT
from backend.tests import ledger_guard
from backend.tests.test_runtime_task import CLEAN_ENV, FakeChild, _plan, _rows, make_clone
from scripts import runtime_task as RT

REPO = Path(__file__).resolve().parents[2]
WIN = sys.platform == "win32"


def _sim_checkout(tmp_path: Path, name: str) -> Path:
    """A folder shaped like a checkout (`<name>/backend/data`), holding no database."""
    root = tmp_path / name
    (root / "backend" / "data").mkdir(parents=True)
    return root


def _junction(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if WIN:
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                       check=True, capture_output=True)
    else:
        os.symlink(target, link, target_is_directory=True)


def test_the_constants_have_one_value_each():
    assert C.RUNTIME_CLONE_PREFIX == RT.CLONE_PREFIX
    assert C.RUNTIME_LOW_MEMORY_RC == RT.LOW_MEMORY_RC
    codes = {RT.REFUSED_RC, C.RELEASE_CLONE_DB_REFUSED_RC, C.TEST_ISOLATION_ABORT_RC,
             RT.LOW_MEMORY_RC}
    assert len(codes) == 4 and 0 not in codes


# ───────────────────────────────────────────────────────────── (a) the database guard

def test_a_new_database_in_an_unwrapped_release_clone_is_refused(tmp_path):
    clone = _sim_checkout(tmp_path, "aegis-runtime-20991231a")
    db = clone / "backend" / "data" / "aegis_pi.db"
    why = C.new_database_refusal(str(db), clone, environ={})
    assert why and "RELEASE_CLONE_DATABASE" in why and "scripts/runtime_task.py" in why
    assert str(db) in why
    # the same refusal for bytes, a PathLike and a read-write URI
    assert C.new_database_refusal(os.fsencode(str(db)), clone, environ={})
    assert C.new_database_refusal(db, clone, environ={})
    assert C.new_database_refusal(db.as_uri(), clone, environ={})
    # a mark that names ANOTHER folder is not this clone's wrapper
    other = {C.RUNTIME_WRAPPER_MARK_ENV: str(tmp_path / "aegis-runtime-other")}
    assert C.new_database_refusal(str(db), clone, environ=other)


def test_what_the_database_guard_leaves_alone(tmp_path):
    clone = _sim_checkout(tmp_path, "aegis-runtime-20991231a")
    db = clone / "backend" / "data" / "aegis_pi.db"
    marked = {C.RUNTIME_WRAPPER_MARK_ENV: str(clone)}
    assert C.new_database_refusal(str(db), clone, environ=marked) is None      # the wrapper's child
    assert C.new_database_refusal(":memory:", clone, environ={}) is None
    assert C.new_database_refusal("", clone, environ={}) is None
    assert C.new_database_refusal(db.as_uri() + "?mode=ro", clone, environ={}) is None
    assert C.new_database_refusal(str(tmp_path / "elsewhere.db"), clone, environ={}) is None
    sqlite3.connect(db).close()                                                 # it exists now
    assert C.new_database_refusal(str(db), clone, environ={}) is None          # not a creation
    # an ordinary checkout: any name that is not a release clone's
    for name in ("aegis-finance", "ch57-isolation", "aegis-runtime-"):
        plain = _sim_checkout(tmp_path, name)
        assert not C.is_release_clone(plain)
        assert C.new_database_refusal(str(plain / "backend" / "data" / "aegis_pi.db"),
                                      plain, environ={}) is None


def test_this_checkout_is_not_guarded_and_the_path_resolution_is_unchanged(monkeypatch):
    assert C.RELEASE_CLONE_DB_GUARD_ROOTS == ()          # no audit hook in a dev checkout or CI
    monkeypatch.delenv("AEGIS_PI_DB_PATH", raising=False)
    assert C._pi_db_path() == C.DATA_DIR / "aegis_pi.db"


_OPEN_DB = (
    "from backend import config as C\n"
    "from backend import db as D\n"
    "print('ROOTS=%d' % len(C.RELEASE_CLONE_DB_GUARD_ROOTS))\n"
    "print('DB_PATH=' + str(D.DB_PATH))\n"
    "try:\n"
    "    D.init_db()\n"
    "    print('INIT_OK')\n"
    "except Exception as exc:\n"          # what backend.main does: 'non-fatal', carry on
    "    print('SWALLOWED ' + type(exc).__name__)\n"
    "print('STILL_RUNNING')\n")


def _run_in(root: Path, **extra: str) -> subprocess.CompletedProcess:
    """Import this branch's code as if it ran from `root` (config follows AEGIS_REPO_ROOT),
    then open the paper_nav database the way the app's startup does."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("AEGIS_PI_DB_PATH", "AEGIS_RUNTIME_CLONE", "AEGIS_DATA_DIR",
                        "AEGIS_DOTENV_PATH", "PYTHONPATH")}
    env.update({"AEGIS_REPO_ROOT": str(root), "AEGIS_IGNORE_DOTENV": "1", **extra})
    return subprocess.run([sys.executable, "-c", _OPEN_DB], cwd=str(REPO), env=env,
                          capture_output=True, text=True, timeout=300,
                          creationflags=RT.CREATE_NO_WINDOW if WIN else 0)


def test_an_unwrapped_process_in_a_release_clone_exits_before_creating_the_database(tmp_path):
    clone = _sim_checkout(tmp_path, "aegis-runtime-20991231a")
    r = _run_in(clone)
    assert r.returncode == C.RELEASE_CLONE_DB_REFUSED_RC, (r.stdout, r.stderr)
    assert "ROOTS=1" in r.stdout                         # importing config is still allowed
    assert "REFUSED RELEASE_CLONE_DATABASE" in r.stderr and "scripts/runtime_task.py" in r.stderr
    # the refusal is not swallowed by `except Exception`, and nothing ran after it
    assert "SWALLOWED" not in r.stdout and "STILL_RUNNING" not in r.stdout
    assert not list(clone.rglob("*.db*")), "a database file was created in the clone"


def test_the_wrappers_child_in_a_release_clone_opens_the_live_database(tmp_path):
    clone = _sim_checkout(tmp_path, "aegis-runtime-20991231a")
    live = tmp_path / "live" / "aegis_pi.db"
    live.parent.mkdir()
    sqlite3.connect(live).close()
    r = _run_in(clone, AEGIS_RUNTIME_CLONE=str(clone), AEGIS_PI_DB_PATH=str(live))
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "ROOTS=0" in r.stdout and "INIT_OK" in r.stdout and "STILL_RUNNING" in r.stdout
    assert f"DB_PATH={live.resolve()}" in r.stdout
    assert not list(clone.rglob("*.db*"))


def test_an_ordinary_checkout_still_creates_its_own_database(tmp_path):
    plain = _sim_checkout(tmp_path, "some-dev-checkout")
    r = _run_in(plain)
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "ROOTS=0" in r.stdout and "INIT_OK" in r.stdout
    assert (plain / "backend" / "data" / "aegis_pi.db").is_file()       # unchanged behaviour


# ───────────────────────────────────────────────────────────── (b) the test-session guard

def test_a_data_dir_that_resolves_outside_the_checkout_aborts_the_session(tmp_path, monkeypatch):
    checkout = _sim_checkout(tmp_path, "some-dev-checkout")
    live = tmp_path / "live-data" / "optimus"
    live.mkdir(parents=True)
    link = checkout / "backend" / "data" / "optimus"
    _junction(link, live)
    dirs = CT.suite_data_dirs(checkout)
    assert link in dirs                                   # found by listing, not by name alone
    why = CT.data_isolation_refusal(checkout, dirs, C.RUNTIME_CLONE_PREFIX)
    assert why and "DATA_OUTSIDE_CHECKOUT" in why and str(link) in why

    # and the hook itself ends the session with the distinct code, before the ledger
    # fingerprint (the first thing it would otherwise read)
    monkeypatch.setattr(ledger_guard, "REPO", checkout)
    monkeypatch.setattr(CT, "suite_data_dirs", lambda repo=None: dirs)
    monkeypatch.setattr(ledger_guard, "fingerprint",
                        lambda *a, **k: pytest.fail("the session went on past the guard"))
    with pytest.raises(pytest.exit.Exception) as exc:
        CT.pytest_sessionstart(None)
    assert exc.value.returncode == C.TEST_ISOLATION_ABORT_RC
    assert "DATA_OUTSIDE_CHECKOUT" in str(exc.value.msg)
    assert not any(live.iterdir())                        # nothing was written through the link


def test_a_release_clone_aborts_the_session_even_with_plain_data_dirs(tmp_path):
    clone = _sim_checkout(tmp_path, "aegis-runtime-20991231a")
    (clone / "backend" / "data" / "optimus").mkdir()
    why = CT.data_isolation_refusal(clone, CT.suite_data_dirs(clone), C.RUNTIME_CLONE_PREFIX)
    assert why and "RELEASE_CLONE" in why and str(clone) in why


def test_an_ordinary_checkout_and_this_one_start_normally(tmp_path):
    plain = _sim_checkout(tmp_path, "some-dev-checkout")
    (plain / "backend" / "data" / "optimus" / "learner").mkdir(parents=True)
    assert CT.data_isolation_refusal(plain, CT.suite_data_dirs(plain), C.RUNTIME_CLONE_PREFIX) is None
    # a junction that stays INSIDE the checkout is not a refusal
    _junction(plain / "backend" / "data" / "alias", plain / "backend" / "data" / "optimus")
    assert CT.data_isolation_refusal(plain, CT.suite_data_dirs(plain), C.RUNTIME_CLONE_PREFIX) is None
    # the real session this test runs in (a dev checkout, a worktree, CI)
    assert CT.data_isolation_refusal(ledger_guard.REPO, CT.suite_data_dirs(),
                                     C.RUNTIME_CLONE_PREFIX) is None


# ───────────────────────────────────────────────────────────── (c) the memory floor

def _never(*_a, **_k):
    pytest.fail("must not launch")


def test_a_floor_above_free_memory_refuses_low_memory_with_the_figure(tmp_path):
    plan, _ = _plan(tmp_path, ["--min-free-gb", "6", "-m", "heavy.job", "--night"])
    assert plan["min_free_gb"] == 6.0
    made = []
    rc = RT.run_plan(plan, popen=_never, job_factory=lambda m: made.append(m),
                     free_memory=lambda: int(2.5 * RT.GIB))
    assert rc == RT.LOW_MEMORY_RC == 93 and rc != RT.REFUSED_RC
    assert made == []                                     # refused before the job object too
    rows = _rows(plan)
    assert len(rows) == 1
    row = rows[0]
    assert (row["event"], row["reason"]) == ("refused", "LOW_MEMORY")
    assert row["why"].startswith("LOW_MEMORY:")
    assert row["free_gb"] == 2.5 and row["min_free_gb"] == 6.0 and row["rc"] == 93
    assert row["free_bytes"] == int(2.5 * RT.GIB)
    assert row["argv"] == [["-m", "heavy.job", "--night"]]


def test_no_floor_declared_measures_nothing_and_runs(tmp_path):
    plan, _ = _plan(tmp_path, ["-m", "a"])
    assert plan["min_free_gb"] is None
    rc = RT.run_plan(plan, popen=lambda argv, **kw: FakeChild(0),
                     free_memory=lambda: pytest.fail("no floor declared: must not measure"))
    assert rc == 0
    assert [r["event"] for r in _rows(plan)] == ["start", "end"]          # the rows as before


def test_a_floor_that_is_met_runs_and_an_unreadable_figure_does_not_refuse(tmp_path):
    plan, _ = _plan(tmp_path, ["--min-free-gb", "2.5", "-m", "a"])
    assert RT.run_plan(plan, popen=lambda argv, **kw: FakeChild(0),
                       free_memory=lambda: int(2.5 * RT.GIB)) == 0        # at the floor = met
    assert [r["event"] for r in _rows(plan)] == ["start", "end"]
    assert RT.run_plan(plan, popen=lambda argv, **kw: FakeChild(4), free_memory=lambda: None) == 4
    rows = _rows(plan)[2:]
    assert [r["event"] for r in rows] == ["memory_floor", "start", "end"]
    assert rows[0]["verdict"] == "CANNOT DETERMINE"


def test_a_stop_file_still_wins_and_a_bad_floor_is_a_wrapper_refusal(tmp_path):
    plan, _ = _plan(tmp_path, ["--min-free-gb", "64", "--stop-file", "STOP", "-m", "a"])
    Path(plan["clone"], "STOP").write_text("", encoding="utf-8")
    assert RT.run_plan(plan, popen=_never, free_memory=lambda: 0) == 0
    for bad in ("0", "-1", "lots", "nan", "inf"):
        with pytest.raises(RT.Refused, match="min-free-gb"):
            RT.parse_argv(["--min-free-gb", bad, "-m", "a"])
    with pytest.raises(RT.Refused, match="needs a value"):
        RT.parse_argv(["--min-free-gb"])


def test_free_memory_is_measured_without_a_new_dependency():
    free = RT.free_physical_bytes()
    if WIN or Path("/proc/meminfo").is_file():
        assert isinstance(free, int) and 0 < free < 2 ** 50
    else:
        assert free is None                               # CANNOT DETERMINE, never a guess


@pytest.mark.skipif(not WIN, reason="the wrapper runs scheduled tasks on Windows")
def test_a_real_wrapper_process_exits_93_below_its_floor(tmp_path):
    clone, conf, cfg = make_clone(tmp_path)
    env = {**CLEAN_ENV}
    py = Path(cfg["AEGIS_VENV_DIR"]) / "Scripts" / "python.exe"
    argv = [str(py), "-I", str(clone / "scripts" / "runtime_task.py"),
            "--min-free-gb", "1000000", "-m", "json.tool", "--help"]
    r = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=120,
                       creationflags=RT.CREATE_NO_WINDOW)
    assert r.returncode == RT.LOW_MEMORY_RC, (r.stdout, r.stderr)
    assert "LOW_MEMORY" in r.stderr and r.stdout == ""
    log = Path(cfg["AEGIS_LIVE_OPTIMUS"]) / RT.RUN_LOG_REL
    rows = _rows({"run_log": str(log)})
    assert [(x["event"], x["reason"]) for x in rows] == [("refused", "LOW_MEMORY")]
    assert rows[0]["free_gb"] > 0 and rows[0]["min_free_gb"] == 1000000.0
