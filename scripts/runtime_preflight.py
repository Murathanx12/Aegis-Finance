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
               expect_funnel: Optional[Path], cfg: Any, environ: dict) -> dict:
    rows = [check_commit(repo, expect_commit),
            check_code_clean(repo),
            check_imports(repo, entries),
            check_data_root(repo, Path(cfg.OPTIMUS_LEDGER_DIR), expect_optimus),
            # a config older than CH-05 has no DOTENV_PATH: it loads PROJECT_ROOT/.env
            check_dotenv(Path(getattr(cfg, "DOTENV_PATH", None)
                              or Path(cfg.PROJECT_ROOT) / ".env"), environ)]
    if expect_funnel is not None:
        rows.append(check_funnel(Path(cfg.IC_FUNNEL_PATH), expect_funnel))
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
    ap.add_argument("--receipt", type=Path, default=None, help="write the receipt here as well")
    a = ap.parse_args(argv)
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from backend import config as cfg  # noqa: PLC0415  (loads the declared .env; never printed)
    rep = run_checks(REPO, entries=a.entry, expect_commit=a.expect_commit,
                     expect_optimus=a.expect_optimus, expect_funnel=a.expect_funnel, cfg=cfg,
                     environ=dict(os.environ))
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
