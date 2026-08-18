"""The one command to run before `git push`. Exit 1 means do not push.

    python -m scripts.verify_before_push

WHY THIS EXISTS (2026-08-16, review §15)
========================================
Three avoidable failures in one session, all of the same shape:

* **Two red CI pushes** against a gate that blocks Railway deploys. `ci_env_sim`
  existed and was used as a debugging tool *after* the red, not as a step
  *before* the push.
* **Source edited twice while a suite was running.** The suite then reports on
  a tree that no longer exists — green on code nobody has, or red on code
  nobody wrote. It happened twice in one session, which makes it a process
  defect rather than a slip.
* **An 83-minute test run** caused by a network-heavy research job competing
  with the suite for the same machine.

None of these are interesting problems and all of them cost deploys. The fix is
not more discipline; it is one command that is easier to run than to skip.

WHAT IT CHECKS, AND WHY EACH ONE IS HERE
========================================
1. **Every changed Python file compiles.** Catches the syntax error that turns
   a whole CI job red for a reason no test name will tell you.
2. **The tree is stable across the run.** Every tracked file is hashed before
   and after the suite; if anything moved, the result is DISCARDED rather than
   reported. This is the guard for the repeated failure, and it fails *loudly*
   rather than silently reporting a stale pass.
3. **The suite runs in CI's world, not this machine's** — sibling repo hidden,
   CI's env exported, secrets blanked (`backend/tests/ci_env_sim`). The
   dev-machine world is not the world that gates production.
4. **The sibling module's own tests run when the sibling has changed.** Two
   repos, one programme; a change over there can only be verified over there.
5. **Competing heavy jobs are reported, not blocked.** A second python process
   running a research script is usually the reason a four-minute suite takes
   eighty-three minutes. Naming it is enough; refusing would be wrong, since a
   long-running collector is often exactly what should be running.

It does not replace checking CI after the push. Nothing replaces checking CI.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIBLING = ROOT.parent / "Aegis module"

#: Tracked paths the suite is ALLOWED to rewrite. Kept as an explicit suffix
#: list, not a glob: every entry here is a place where a test writes into the
#: repository, which is worth seeing in one list rather than discovering later.
SUITE_MAY_WRITE: tuple[str, ...] = ()


def _run(cmd: list[str], cwd: Path, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), text=True, encoding="utf-8",
                          errors="replace", **kw)


def _tracked_files(repo: Path) -> list[str]:
    p = _run(["git", "ls-files"], repo, capture_output=True)
    if p.returncode != 0:
        return []
    return [ln for ln in p.stdout.splitlines() if ln.strip()]


def _tree_hash(repo: Path) -> dict[str, str]:
    """Per-file hashes of the working tree as it is ON DISK.

    `git status` would not notice an edit that was made and reverted, and
    `git stash list` says nothing at all. Hashing the bytes is the only way to
    answer "is this the same tree the suite just ran against".

    Per FILE rather than one digest, because the first version printed "the
    tree changed" and nothing else — and a guard that reports a problem it
    cannot localise is a guard that gets switched off. It fired on its own
    first real run and I could not act on it until it named the file.
    """
    out: dict[str, str] = {}
    for rel in _tracked_files(repo):
        p = repo / rel
        try:
            out[rel] = hashlib.sha256(
                p.read_bytes() if p.is_file() else b"<absent>").hexdigest()
        except OSError:
            out[rel] = "<unreadable>"
    return out


def _tree_diff(before: dict[str, str], after: dict[str, str]) -> list[str]:
    keys = set(before) | set(after)
    return sorted(k for k in keys if before.get(k) != after.get(k))


def _changed_python(repo: Path) -> list[Path]:
    """Python files differing from HEAD, staged or not, plus untracked ones."""
    out: set[str] = set()
    for args in (["git", "diff", "--name-only", "HEAD"],
                 ["git", "ls-files", "--others", "--exclude-standard"]):
        p = _run(args, repo, capture_output=True)
        if p.returncode == 0:
            out |= {ln for ln in p.stdout.splitlines() if ln.endswith(".py")}
    return [repo / f for f in sorted(out) if (repo / f).is_file()]


def _competing_python() -> list[str] | None:
    """Other python processes, so an 83-minute suite has a named cause.

    RETURNS `None` WHEN IT COULD NOT LOOK, never an empty list. This check ran
    for weeks printing "competing python processes: 0" on a machine with no
    `psutil` installed — so it printed the all-clear without ever looking, which
    is the one output a diagnostic must never fake. Found 2026-08-18 while an
    IIF-1 night run and four MCP servers were demonstrably alive and the gate
    still said 0.

    Same rule as `observe_invocation`'s `stdin_isatty`: "we did not look" must
    not read the same as "we looked and there was nothing".
    """
    me = str(__import__("os").getpid())
    try:
        import psutil                                          # type: ignore
    except ImportError:
        return _competing_python_fallback(me)
    out = []
    for pr in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if "python" not in (pr.info["name"] or "").lower():
                continue
            if str(pr.info["pid"]) == me:
                continue
            cmd = " ".join(pr.info["cmdline"] or [])[:110]
            if cmd:
                out.append(f"pid {pr.info['pid']}: {cmd}")
        except Exception:                                      # noqa: BLE001
            continue
    return out


def _competing_python_fallback(me: str) -> list[str] | None:
    """No psutil: ask Windows directly rather than reporting a clean machine."""
    if sys.platform != "win32":
        return None
    try:
        p = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    out = []
    for line in p.stdout.splitlines():
        pid, _, cmd = line.partition("\t")
        pid = pid.strip()
        if not pid.isdigit() or pid == me:
            continue
        out.append(f"pid {pid}: {cmd.strip()[:110]}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fast", action="store_true",
                    help="skip the sibling repo's suite")
    ap.add_argument("-k", default=None,
                    help="pytest -k expression, for a targeted pre-check "
                         "(a targeted run is NOT a green light to push)")
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    fail: list[str] = []
    print("=" * 72)
    print("VERIFY BEFORE PUSH")
    print("=" * 72)

    # ── 1. every changed python file compiles ───────────────────────────────
    changed = _changed_python(ROOT)
    if SIBLING.exists():
        changed += _changed_python(SIBLING)
    print(f"\n[1/5] compiling {len(changed)} changed Python file(s)")
    import py_compile
    for p in changed:
        try:
            py_compile.compile(str(p), doraise=True, quiet=1)
        except py_compile.PyCompileError as exc:
            fail.append(f"syntax: {p}")
            print(f"  FAIL {p}\n       {exc}")
    if not fail:
        print("  ok")

    # ── 2. name the competition before blaming the machine ──────────────────
    others = _competing_python()
    if others is None:
        print("\n[2/5] competing python processes: UNKNOWN — could not look "
              "(no psutil, and the platform query failed)")
        print("  (this used to print '0' here, which is what a clean machine "
              "looks like. It is not a refusal, but do not read it as clear.)")
    else:
        print(f"\n[2/5] competing python processes: {len(others)}")
        for o in others[:6]:
            print(f"  {o}")
        if others:
            print("  (not a refusal — but if this run takes an hour, that is why)")

    # ── 3. the suite, in CI's world, with the tree pinned ───────────────────
    before = _tree_hash(ROOT)
    before_sib = _tree_hash(SIBLING) if SIBLING.exists() else {}
    cmd = [sys.executable, "-m", "pytest", "backend/tests/", "-q",
           "-m", "not slow", "-p", "backend.tests.ci_env_sim"]
    if a.k:
        cmd += ["-k", a.k]
    print(f"\n[3/5] pytest in the CI-simulated world"
          f"{' (-k ' + a.k + ')' if a.k else ''}")
    t0 = time.time()
    p = _run(cmd, ROOT)
    mins = (time.time() - t0) / 60.0
    print(f"  exit {p.returncode} in {mins:.1f} min")
    if p.returncode != 0:
        fail.append("backend suite (CI-simulated world)")

    # ── 4. THE REPEAT: was the tree edited underneath the run? ──────────────
    print("\n[4/5] tree stability across the run")
    after = _tree_hash(ROOT)
    after_sib = _tree_hash(SIBLING) if SIBLING.exists() else {}
    moved = ([f"aegis-finance/{x}" for x in _tree_diff(before, after)]
             + [f"Aegis module/{x}" for x in _tree_diff(before_sib, after_sib)])
    # A test that legitimately WRITES a tracked artefact would trip this on
    # every run, and a guard that cries wolf every run is off within a week.
    # Those paths are excluded by name, and the exclusion is narrow and
    # visible rather than a wildcard.
    moved = [m for m in moved if not m.endswith(SUITE_MAY_WRITE)]
    if moved:
        fail.append("TREE CHANGED DURING THE RUN — result discarded")
        print("  FAIL the working tree changed while the suite was running.\n"
              "       Whatever it just printed describes a tree that no longer\n"
              "       exists. Re-run without editing. (This happened twice on\n"
              "       2026-08-15 and is why this check is here.)")
        for m in moved[:20]:
            print(f"         changed: {m}")
    else:
        print("  ok — same tree before and after")

    # ── 5. the sibling's own suite, if it changed ───────────────────────────
    print("\n[5/5] sibling module")
    if a.fast:
        print("  skipped (--fast)")
    elif not SIBLING.exists():
        print("  absent — nothing to run")
    elif not _changed_python(SIBLING):
        print("  unchanged — nothing to run")
    else:
        ps = _run([sys.executable, "-m", "pytest", "tests/", "-q"], SIBLING)
        print(f"  exit {ps.returncode}")
        if ps.returncode != 0:
            fail.append("Aegis module suite")

    print("\n" + "=" * 72)
    if fail:
        print("DO NOT PUSH — " + "; ".join(fail))
        print("=" * 72)
        return 1
    print("OK to push. Then CHECK CI — this simulates that world, it is not "
          "that world.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
