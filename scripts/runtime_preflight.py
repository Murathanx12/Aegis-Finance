"""Is this checkout fit to be the runtime for a scheduled task? (CH-05 acceptance receipt)

    python -m scripts.runtime_preflight --entry scripts.alert_pass \\
        --expect-commit <tag|sha> --expect-optimus C:\\path\\to\\live\\backend\\data\\optimus \\
        [--expect-funnel C:\\path\\to\\live\\backend\\data\\funnel_night10.json] \\
        [--receipt C:\\path\\receipt.json]

Run it FROM the checkout a task is about to be repointed to, with the same
environment the task will have (`AEGIS_DOTENV_PATH`, `AEGIS_IC_FUNNEL_PATH`, ...).
It reads; it writes only the receipt. Exit 0 = every check passed, 2 = at least
one FAILED (a red, non-zero exit), 1 = the preflight itself broke.

WHY (2026-11-11). For a month the scheduled tasks ran from a WIP checkout 269
commits behind main whose code imported modules that existed in no commit (an
untracked 10-15 `provider_budget.py` blocked the learning system for 24 days at
rc 0). "The runtime is a commit" has to be checkable per task, before and after
each repoint, or it is a sentence. The checks, each one a failure seen that week:

1. `commit`      HEAD is the declared tag/sha (not "whatever is checked out").
2. `code_clean`  no tracked code differs from HEAD and no untracked file sits
                 among the code (data under backend/data is excluded).
3. `imports`     every repo module the entry reaches by a static import walk is a
                 file git TRACKS at HEAD; a module that resolves to an untracked
                 file, or to nothing, fails by name.
4. `data_root`   `config.OPTIMUS_LEDGER_DIR` AND the checkout's own
                 `backend/data/optimus` both resolve to the declared live data
                 directory. 77 modules (381 sites, 2026-11-11 scan) build
                 `REPO/"backend"/"data"/...` without config, so an env var alone
                 leaves them reading and writing the checkout's tracked copy --
                 a split brain. A junction at `backend/data/optimus` passes this;
                 `AEGIS_DATA_DIR` alone does not.
5. `dotenv`      the `.env` config will load exists (its contents are never read
                 here), unless `AEGIS_IGNORE_DOTENV` is set.
6. `funnel`      with `--expect-funnel`: `config.IC_FUNNEL_PATH` is that file.
7. `tracked_data_through_junction` (WARN, never FAIL): how many files git tracks
                 under `backend/data/optimus` that differ from HEAD. While that
                 count is above zero, a checkout/reset/stash in this checkout would
                 WRITE INTO THE LIVE DATA. It reaches zero only when the growing
                 files are untracked on main; until then it is printed so nobody
                 runs git surgery here.

Added by CH-05 review 5 (2026-11-11):

8. `pi_db`       with `--expect-pi-db`: `backend.db.DB_PATH` (what the child opens) is
                 that file, it is a SQLite database whose `paper_nav` table HOLDS ROWS
                 (opened read-only), and the checkout has no stray database of its own
                 at `backend/data/aegis_pi.db`. A new empty database can never pass (B1).
9. `siblings`    every sibling path the code derives from `REPO.parent` (SIBLINGS,
                 pinned against an AST walk of the code by the tests) exists from THIS
                 checkout. A clone one level too deep made the fleet a silent rc-0 no-op
                 and three more tasks refuse (B2); now a move goes red here first.
10. `live_state` with `--live-root`: every piece of live state outside the optimus
                 junction (LIVE_STATE) is handled the way the table declares: junctions
                 resolve to the live copy; the rest is listed with its mechanism.
11. `funnel_age` (WARN) with `--live-root`: the funnel `config.IC_FUNNEL_PATH` serves
                 here, its `generated_at`, and the live one's. Not a FAIL: which funnel
                 a clone reads is an owner decision (OD-i, review 5 M2).
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

REPO = Path(__file__).resolve().parents[1]

#: Top-level packages of this repository; an import outside them is a dependency.
PACKAGES = ("backend", "scripts", "engine", "lab", "learner", "nn_lab", "ft_lab", "tools", "sdk")

#: Every directory name the code reaches as `REPO.parent / <name>` (a sibling repository or
#: checkout), and the probe that proves it is there FROM a given checkout. FAIL rows are the
#: ones whose absence turns a scheduled job into a refusal or a silent no-op. Found by walking
#: the code on 2026-11-11 (`test_runtime_preflight` re-walks it: a new sibling name fails the
#: suite until it is declared here). `users` and `if_missing` are file:line evidence.
SIBLINGS: tuple[dict, ...] = (
    {"name": "aegis-alpha-terminal", "probe": ("aegis-alpha-terminal", ".env"), "level": "FAIL",
     "users": ["scripts/fleet_manager_run.py:39", "scripts/paper_accounts_roi.py:63",
               "scripts/fleet_audit.py:59", "scripts/night_p6_bars_and_regret.py:59"],
     "if_missing": "fleet_manager_run reads no keys: every role NO_CREDENTIAL and main() returns 0 "
                   "(fleet_manager_run.py:151,441,1335); paper_accounts_roi loses broker reads"},
    {"name": "aegis-alpha-terminal", "probe": ("aegis-alpha-terminal", "state", "universe"),
     "level": "FAIL", "users": ["nn_lab/universe_filter.py:27"],
     "if_missing": "universe_filter.collect() skips it (`if tdir.exists() else []`): the nn_lab "
                   "ETF/fund exclusion list shrinks and nothing says so"},
    {"name": "aegis-alpha-terminal", "probe": ("aegis-alpha-terminal", "state", "research", "analyst_panel"),
     "level": "WARN", "users": ["backend/services/task_receipts.py:933"],
     "if_missing": "the analyst-panel health row reads UNKNOWN"},
    {"name": "optimus", "probe": ("optimus", "tools", "refresh_aegis.py"), "level": "FAIL",
     "users": ["scripts/task_keeper.py:1220"],
     "if_missing": "AegisBrainRefresh refuses ('tools/refresh_aegis.py not found'), rc 2 "
                   "(OPTIMUS_ROOT wins when set)"},
    {"name": "Aegis module", "probe": ("Aegis module", "scripts", "iif1_config.py"), "level": "FAIL",
     "users": ["backend/services/iif1_prereg.py:46"],
     "if_missing": "the IIF-1 night refuses with FrozenPreregMissing"},
    {"name": "Aegis module", "probe": ("Aegis module", "scripts", "iif1_read_gate.py"), "level": "FAIL",
     "users": ["backend/services/iif1_grader.py:729"],
     "if_missing": "the IIF-1 grader raises ImportError('no read gate')"},
    {"name": "Aegis module", "probe": ("Aegis module", "runs", "MARKET-GRAPH-1", "edge_instances.parquet"),
     "level": "WARN", "users": ["learner/features_graph.py:141"],
     "if_missing": "graph features refuse (SystemExit REFUSED); lab jobs only"},
    {"name": "aegis-finance-publication", "probe": ("aegis-finance-publication",), "level": "WARN",
     "users": ["scripts/task_keeper.py:894", "scripts/task_keeper.py:1324"],
     "if_missing": "publication tasks refuse; they run from the publication checkout, not a "
                   "clone, and the wrapper exports AEGIS_PUBLICATION_ROOT anyway"},
    {"name": "aegis-finance", "probe": None, "level": "WARN",
     "users": ["scripts/task_keeper.py:79"],
     "if_missing": "only the publication checkout derives it (`assets`); not a clone path"},
)

#: Every piece of LIVE state outside `backend/data/optimus` that scheduled code reads or
#: writes, and how a release clone handles it (review 5, B1; inventory 2026-11-11 in the
#: CH-05 review-fixes report). `junction`: the clone's path is a junction to the live path
#: (made by runtime_release, checked here). `env`: an environment variable the wrapper
#: exports points the code at the live file. `tag`: the clone's tracked copy is the right
#: one. `absent`: not carried; what that costs is stated. `decision`: an owner decision.
LIVE_STATE: tuple[dict, ...] = (
    {"path": "backend/data/optimus", "how": "junction", "required": True,
     "why": "the shared ledgers every writer uses"},
    {"path": ".venv", "how": "junction", "required": True,
     "why": "REPO/.venv in task_keeper._child_python, alert_pass, hyp_lab, world_digest, "
            "straddle_forward, night_reader_supervisor"},
    {"path": "nn_lab/.venv", "how": "junction", "required": False,
     "why": "nn_lab's autogluon venv (AegisNNLabNightly refuses without it)"},
    {"path": "ft_lab/data", "how": "junction", "required": False,
     "why": "gitignored research cells (468 MB): hyp_cells.CELLS/BULK/PREDS_2026 for the hyp_lab "
            "nightly; nn_lab size_members silently writes text_resid_7d = NaN without it"},
    {"path": "backend/data/aegis_pi.db", "how": "env", "env": "AEGIS_PI_DB_PATH",
     "why": "paper_nav (CANON section 5), written by daily_pass book_cadence; gitignored. "
            "Checked by `pi_db`; -wal/-shm follow the one path"},
    {"path": ".env", "how": "env", "env": "AEGIS_DOTENV_PATH", "why": "the keys file, pointed at"},
    {"path": "backend/data/funnel_night10.json", "how": "decision",
     "why": "OD-i (review 5 M2): config.IC_FUNNEL_PATH is BACKEND_DIR-relative, so a clone serves "
            "the TAG's committed copy; see `funnel_age`"},
    {"path": "backend/data/funnel_history", "how": "decision",
     "why": "OD-i: opportunity_funnel archives beside IC_FUNNEL_PATH; stitched_tickers and "
            "thesis_cards read it. A clone holds only the tag's tracked files"},
    {"path": "backend/data/funnel_cache", "how": "decision",
     "why": "OD-i: opportunity_funnel.CACHE_DIR (module-relative); a rebuild in a clone starts cold"},
    {"path": "docs (generated)", "how": "decision",
     "why": "review 5 m8: daily_pass writes docs/BRIDGE.md, docs/PAPER_ACCOUNTS.md and "
            "docs/assets/paper_accounts_roi_*.png into the clone's TRACKED docs/, so `code_clean` "
            "fails on the next preflight and the live checkout's copies stop updating"},
    {"path": "backend/data/public_receipts", "how": "tag",
     "why": "tracked; the live copy equals the runtime HEAD (no writer since). A writer in a clone "
            "(opportunities_build.publish_public_copy) writes the clone's copy unless "
            "AEGIS_PUBLIC_RECEIPTS_DIR is --set; DataCatalog sets it to the publication checkout"},
    {"path": "backend/data/*.yaml|*.csv|*.json.gz|news_entities|crosswalks|copy_lab|arena|swarm|leakage_probe|scrape",
     "how": "tag", "why": "tracked config and fixtures; on 2026-11-11 the live copies equal main "
                          "or main is newer (news_sources.yaml)"},
    {"path": "backend/data/terminal_mirror", "how": "absent",
     "why": "17 live-only files, last synced 2026-09-08 by hand (terminal_state_reader --sync); "
            "read by the journal API route, no scheduled writer"},
    {"path": "backend/data/apscheduler_jobs.db", "how": "absent",
     "why": "the website/desktop APScheduler store (portfolio_intelligence.scheduler); no task opens it"},
    {"path": "backend/models/*.pkl", "how": "absent",
     "why": "gitignored crash model (2026-09-27); readers are API routes, market_dashboard and "
            "portfolio_intelligence.replay: the crash overlay is dark in a clone"},
    {"path": "engine/data", "how": "absent", "why": "1.1 GB of research panels (eodhd); no scheduled reader"},
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    # GIT_OPTIONAL_LOCKS=0: `git status` must not take the index lock or rewrite the
    # stat cache of a LIVE runtime checkout while scheduled jobs are using it.
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120, env=env)


def _row(check: str, ok: Optional[bool], detail: Any, *, level: str = "FAIL") -> dict:
    status = "PASS" if ok else ("WARN" if level == "WARN" else "FAIL")
    return {"check": check, "status": status, "detail": detail}


# ----------------------------------------------------------------- 1. commit
def check_commit(repo: Path, expect: str) -> dict:
    head = _git(repo, "rev-parse", "HEAD")
    want = _git(repo, "rev-parse", "--verify", f"{expect}^{{commit}}")
    if head.returncode != 0 or want.returncode != 0:
        return _row("commit", False, {"head": head.stdout.strip() or head.stderr.strip()[:200],
                                      "expected": expect,
                                      "why": "cannot resolve HEAD or the expected commit"})
    h, w = head.stdout.strip(), want.stdout.strip()
    return _row("commit", h == w, {"head": h, "expected": expect, "expected_sha": w})


# ----------------------------------------------------------------- 2. code clean
def check_code_clean(repo: Path) -> dict:
    out = _git(repo, "status", "--porcelain=v1", "--untracked-files=all", "--",
               ".", ":(exclude)backend/data")
    if out.returncode != 0:
        return _row("code_clean", False, {"why": "git status failed", "stderr": out.stderr[:300]})
    lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
    return _row("code_clean", not lines, {"n_dirty": len(lines), "first": lines[:20]})


# ----------------------------------------------------------------- 3. imports
def _resolve(repo: Path, dotted: str) -> Optional[Path]:
    parts = dotted.split(".")
    f = repo.joinpath(*parts).with_suffix(".py")
    if f.is_file():
        return f
    init = repo.joinpath(*parts, "__init__.py")
    return init if init.is_file() else None


def _imports(path: Path, repo: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_bytes().decode("utf-8-sig", "replace"))
    except SyntaxError:
        return set()
    pkg = list(path.relative_to(repo).with_suffix("").parts[:-1])
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level:
                base = pkg[: len(pkg) - (node.level - 1)] if node.level > 1 else pkg
                mod = ".".join([*base, mod] if mod else base)
            names.add(mod)
            names.update(f"{mod}.{a.name}" for a in node.names)
    return {n for n in names if n and n.split(".")[0] in PACKAGES}


def _defines(path: Path) -> Optional[set[str]]:
    """Top-level names a module binds; None when it cannot be known statically
    (a star import or a module-level `__getattr__`)."""
    try:
        tree = ast.parse(path.read_bytes().decode("utf-8-sig", "replace"))
    except SyntaxError:
        return None
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == "__getattr__":
                return None
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                if a.name == "*":
                    return None
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        names.add(n.id)
        elif isinstance(node, (ast.If, ast.Try, ast.With)):
            return None  # conditional bindings: do not guess
    return names


def import_closure(repo: Path, entries: Iterable[str]) -> dict:
    """Static walk. `missing`: a dotted name that is neither a module nor an attribute
    of a resolvable module (an ImportError waiting to happen)."""
    seen: dict[str, Path] = {}
    missing: set[str] = set()
    stack: list[Path] = []
    for e in entries:
        f = _resolve(repo, e)
        if f is None:
            missing.add(e)
        else:
            stack.append(f)
    while stack:
        f = stack.pop()
        rel = f.relative_to(repo).as_posix()
        if rel in seen:
            continue
        seen[rel] = f
        parts = f.relative_to(repo).parts[:-1]
        for k in range(1, len(parts) + 1):
            init = repo.joinpath(*parts[:k], "__init__.py")
            if init.is_file():
                stack.append(init)
        for name in _imports(f, repo):
            g = _resolve(repo, name)
            if g is not None:
                stack.append(g)
            elif "." in name:
                parent, attr = name.rsplit(".", 1)
                pf = _resolve(repo, parent)
                if pf is None:
                    missing.add(name)
                else:
                    bound = _defines(pf)
                    if bound is not None and attr not in bound:
                        missing.add(name)   # `from pkg import x`: neither a module nor a name
    return {"modules": sorted(seen), "missing": sorted(missing)}


def tracked_files(repo: Path) -> Optional[set[str]]:
    out = _git(repo, "ls-files", "-z")
    if out.returncode != 0:
        return None
    return {p for p in out.stdout.split("\0") if p}


def check_imports(repo: Path, entries: list[str]) -> dict:
    tracked = tracked_files(repo)
    if tracked is None:
        return _row("imports", False, {"why": "git ls-files failed"})
    w = import_closure(repo, entries)
    untracked = [m for m in w["modules"] if m not in tracked]
    ok = not untracked and not w["missing"]
    return _row("imports", ok, {"entries": entries, "n_modules": len(w["modules"]),
                                "untracked_modules": untracked, "missing": w["missing"]})


# ----------------------------------------------------------------- 4-6. paths
def _same(a: Path, b: Path) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return False


def check_data_root(repo: Path, config_optimus: Path, expect: Path) -> dict:
    own = repo / "backend" / "data" / "optimus"
    detail = {"expected": str(expect), "config_optimus": str(config_optimus),
              "config_resolves_to": str(Path(config_optimus).resolve()),
              "checkout_optimus_resolves_to": str(own.resolve()),
              "expected_exists": Path(expect).is_dir()}
    cfg_ok = _same(config_optimus, expect)
    own_ok = _same(own, expect)
    if not detail["expected_exists"]:
        detail["why"] = "the declared live data directory does not exist"
    elif cfg_ok and not own_ok:
        detail["why"] = ("SPLIT_BRAIN: config points at the live data but modules that build "
                         "REPO/backend/data/optimus themselves would use the checkout's copy")
    elif own_ok and not cfg_ok:
        detail["why"] = "config.OPTIMUS_LEDGER_DIR (AEGIS_DATA_DIR?) points somewhere else"
    return _row("data_root", detail["expected_exists"] and cfg_ok and own_ok, detail)


def check_dotenv(dotenv_path: Path, environ: dict) -> dict:
    ignored = environ.get("AEGIS_IGNORE_DOTENV", "").strip().lower() in ("1", "true", "yes")
    exists = Path(dotenv_path).is_file()
    return _row("dotenv", exists or ignored,
                {"path": str(dotenv_path), "exists": exists, "ignored": ignored,
                 "declared_by": "AEGIS_DOTENV_PATH" if environ.get("AEGIS_DOTENV_PATH") else
                 "PROJECT_ROOT/.env"})


def check_funnel(funnel: Path, expect: Path) -> dict:
    return _row("funnel", _same(funnel, expect),
                {"config": str(funnel), "expected": str(expect), "exists": Path(funnel).is_file()})


SQLITE_MAGIC = b"SQLite format 3\x00"


def _paper_nav(db: Path) -> dict:
    """Read-only facts about the paper_nav table; never writes (mode=ro)."""
    import sqlite3  # noqa: PLC0415
    con = sqlite3.connect(f"{Path(db).resolve().as_uri()}?mode=ro", uri=True, timeout=10)
    try:
        n, books, last = con.execute(
            "SELECT count(*), count(DISTINCT portfolio_id), max(computed_at) FROM paper_nav").fetchone()
        return {"paper_nav_rows": int(n), "portfolios": int(books), "last_computed_at": last}
    finally:
        con.close()


def check_pi_db(repo: Path, db_path: Path, expect: Path) -> dict:
    """B1: the database the code opens is the live one, and it holds the track record."""
    own = repo / "backend" / "data" / "aegis_pi.db"
    detail: dict = {"db_path": str(db_path), "expected": str(expect),
                    "same_file": _same(db_path, expect), "exists": Path(expect).is_file()}
    try:
        with open(expect, "rb") as fh:
            detail["sqlite"] = fh.read(len(SQLITE_MAGIC)) == SQLITE_MAGIC
    except OSError:
        detail["sqlite"] = False
    if detail["sqlite"]:
        try:
            detail.update(_paper_nav(Path(expect)))
        except Exception as exc:  # noqa: BLE001  (no table, locked, corrupt: all a FAIL)
            detail["read_error"] = f"{type(exc).__name__}: {exc}"[:200]
    detail["stray_db_in_checkout"] = os.path.lexists(own) and not _same(own, expect)
    ok = (detail["same_file"] and detail["exists"] and detail["sqlite"]
          and detail.get("paper_nav_rows", 0) > 0 and not detail["stray_db_in_checkout"])
    if not ok:
        detail["why"] = ("the code would open " + str(db_path) if not detail["same_file"] else
                         "the live database is missing, not SQLite, unreadable or has no paper_nav "
                         "rows" if not detail.get("paper_nav_rows") else
                         f"{own} exists in this checkout: something opened the default path")
    return _row("pi_db", ok, detail)


def check_siblings(repo: Path, siblings: Iterable[dict] = SIBLINGS) -> dict:
    """B2: what the code finds as `REPO.parent / <sibling>` exists from THIS checkout."""
    parent = Path(repo).resolve().parent
    rows, failed, warned = [], [], []
    for s in siblings:
        if not s.get("probe"):
            continue
        p = parent.joinpath(*s["probe"])
        ok = p.exists()
        rows.append({"path": str(p), "exists": ok, "level": s["level"], "users": s["users"],
                     **({} if ok else {"if_missing": s["if_missing"]})})
        if not ok:
            (failed if s["level"] == "FAIL" else warned).append(str(p))
    status = _row("siblings", not failed, {"parent": str(parent), "missing_fail": failed,
                                           "missing_warn": warned, "probes": rows})
    if not failed and warned:
        status["status"] = "WARN"
    return status


def check_live_state(repo: Path, live_root: Path, table: Iterable[dict] = LIVE_STATE) -> dict:
    """Every declared piece of live state is handled the way LIVE_STATE says."""
    rows, failed, warned = [], [], []
    for item in table:
        row = {"path": item["path"], "how": item["how"]}
        if item["how"] == "junction":
            mine, live = repo / item["path"], Path(live_root) / item["path"]
            row.update(resolves_to=str(Path(os.path.realpath(mine))), live=str(live),
                       live_exists=live.exists(), ok=live.exists() and _same(mine, live))
            if not row["ok"]:
                (failed if item.get("required") else warned).append(item["path"])
        elif item["how"] == "env":
            row["env"] = item["env"]
            row["set"] = bool(os.environ.get(item["env"]))
        rows.append(row)
    st = _row("live_state", not failed, {"live_root": str(live_root), "failed": failed,
                                         "warned": warned, "items": rows})
    if not failed and warned:
        st["status"] = "WARN"
    return st


def _generated_at(p: Path) -> Optional[str]:
    try:
        return str(json.loads(Path(p).read_text(encoding="utf-8")).get("generated_at") or "") or None
    except (OSError, ValueError, AttributeError):
        return None


def _age_days(stamp: Optional[str], now: datetime) -> Optional[float]:
    if not stamp:
        return None
    try:
        ts = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        return None
    return round((now - ts).total_seconds() / 86400.0, 1)


def check_funnel_age(funnel: Path, live_funnel: Path, *, now: Optional[datetime] = None) -> dict:
    """WARN-only: the funnel this checkout serves vs the live one (OD-i decides which)."""
    now = now or datetime.now(timezone.utc)
    mine, live = _generated_at(funnel), _generated_at(live_funnel)
    detail = {"serves": str(funnel), "serves_generated_at": mine, "serves_age_days": _age_days(mine, now),
              "live": str(live_funnel), "live_generated_at": live, "live_age_days": _age_days(live, now),
              "same_file": _same(funnel, live_funnel),
              "decision": "OD-i: which funnel a release clone serves (review 5 M2)"}
    return _row("funnel_age", detail["same_file"] and mine is not None, detail, level="WARN")


def check_tracked_data(repo: Path) -> dict:
    out = _git(repo, "status", "--porcelain=v1", "--untracked-files=no", "--", "backend/data/optimus")
    if out.returncode != 0:
        return _row("tracked_data_through_junction", False, {"why": "git status failed"}, level="WARN")
    lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
    return _row("tracked_data_through_junction", not lines,
                {"n_tracked_differing": len(lines), "first": lines[:10],
                 "rule": "while this is above zero, never run checkout/reset/stash/clean/pull here: "
                         "git would write main's committed copies into the live data"}, level="WARN")


# ----------------------------------------------------------------- run
def run_checks(repo: Path, *, entries: list[str], expect_commit: str, expect_optimus: Path,
               expect_funnel: Optional[Path], cfg: Any, environ: dict,
               expect_pi_db: Optional[Path] = None, db_path: Optional[Path] = None,
               live_root: Optional[Path] = None, siblings: Optional[Iterable[dict]] = None) -> dict:
    rows = [check_commit(repo, expect_commit),
            check_code_clean(repo),
            check_imports(repo, entries),
            check_data_root(repo, Path(cfg.OPTIMUS_LEDGER_DIR), expect_optimus),
            # a config older than CH-05 has no DOTENV_PATH: it loads PROJECT_ROOT/.env
            check_dotenv(Path(getattr(cfg, "DOTENV_PATH", None)
                              or Path(cfg.PROJECT_ROOT) / ".env"), environ)]
    if expect_funnel is not None:
        rows.append(check_funnel(Path(cfg.IC_FUNNEL_PATH), expect_funnel))
    if expect_pi_db is not None:
        rows.append(check_pi_db(repo, Path(db_path or getattr(cfg, "PI_DB_PATH",
                                                             Path(cfg.DATA_DIR) / "aegis_pi.db")),
                                expect_pi_db))
    if siblings is not None:
        rows.append(check_siblings(repo, siblings))
    if live_root is not None:
        rows.append(check_live_state(repo, live_root))
        rows.append(check_funnel_age(Path(cfg.IC_FUNNEL_PATH),
                                     Path(live_root) / "backend" / "data" / "funnel_night10.json"))
    rows.append(check_tracked_data(repo))
    failed = [r["check"] for r in rows if r["status"] == "FAIL"]
    return {"schema": "runtime_preflight/1", "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "checkout": str(repo), "verdict": "FAIL" if failed else "PASS", "failed": failed,
            "warned": [r["check"] for r in rows if r["status"] == "WARN"], "checks": rows}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="runtime_preflight")
    ap.add_argument("--entry", action="append", required=True,
                    help="dotted entry module, e.g. scripts.alert_pass (repeatable)")
    ap.add_argument("--expect-commit", required=True, help="the tag or sha this checkout must be at")
    ap.add_argument("--expect-optimus", required=True, type=Path,
                    help="the live backend/data/optimus directory every writer must share")
    ap.add_argument("--expect-funnel", type=Path, default=None)
    ap.add_argument("--expect-pi-db", type=Path, default=None,
                    help="the live paper_nav database the checkout's backend.db must open")
    ap.add_argument("--live-root", type=Path, default=None,
                    help="the live checkout: check LIVE_STATE junctions and report the funnel age")
    ap.add_argument("--skip-siblings", action="store_true",
                    help="do not check the REPO.parent sibling paths (a context with no siblings)")
    ap.add_argument("--receipt", type=Path, default=None, help="write the receipt here as well")
    a = ap.parse_args(argv)
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from backend import config as cfg  # noqa: PLC0415  (loads the declared .env; never printed)
    db_path = None
    if a.expect_pi_db is not None:
        from backend import db as _db  # noqa: PLC0415  (what every writer imports DB_PATH from)
        db_path = Path(_db.DB_PATH)
    rep = run_checks(REPO, entries=a.entry, expect_commit=a.expect_commit,
                     expect_optimus=a.expect_optimus, expect_funnel=a.expect_funnel, cfg=cfg,
                     environ=dict(os.environ), expect_pi_db=a.expect_pi_db, db_path=db_path,
                     live_root=a.live_root, siblings=None if a.skip_siblings else SIBLINGS)
    text = json.dumps(rep, indent=1, default=str)
    if a.receipt:
        a.receipt.parent.mkdir(parents=True, exist_ok=True)
        tmp = a.receipt.with_suffix(a.receipt.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(a.receipt)
    print(text)
    for r in rep["checks"]:
        print(f"{r['status']:4}  {r['check']}", file=sys.stderr)
    print(f"RUNTIME PREFLIGHT {rep['verdict']}"
          + (f": {', '.join(rep['failed'])}" if rep["failed"] else ""), file=sys.stderr)
    return 2 if rep["failed"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"RUNTIME PREFLIGHT BROKE: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
