"""Make a production clone of a release tag, and print (never run) each task's repoint.

    python -m scripts.runtime_release --tag runtime-20261115 --dry-run   # the plan, nothing made
    python -m scripts.runtime_release --tag runtime-20261115             # clone + junctions + preflight

CH-05 (wrapper PR "W"). The scheduled tasks stop running from the dirty WIP checkout and run
from a fresh clone of a tag at `<AEGIS_RUNTIME_ROOT>\\<tag>`, whose `backend\\data\\optimus` is a
junction to the live data (`AEGIS_LIVE_OPTIMUS`). This script makes that clone and verifies it;
the repoint of each task is the OWNER's, so it is printed, not run.

What a real run does, in order, stopping at the first failure:
 1. `git clone --no-checkout <source> <dest>` (default source: the live checkout's object store,
    a local read; nothing in the source is modified), then `remote set-url origin <github>`.
 2. Resolves `refs/tags/<tag>` (a TAG, never a branch) and `checkout --detach` it.
 3. Deletes the clone's OWN `backend\\data\\optimus` (main's tracked copies, just written by the
    checkout; asserted to be a real directory inside the new clone, never a junction), then makes
    the junction to the live data. The order matters: a checkout with the junction already in
    place would write main's copies INTO the live data.
 4. Junctions `<clone>\\.venv` and `<clone>\\nn_lab\\.venv` to the live interpreters (both
    gitignored): main has code that resolves `REPO/.venv` (task_keeper's child python,
    alert_pass, hyp_lab, world_digest, straddle_forward) and nn_lab's cmd resolves its venv
    relative to itself.
 5. Runs `runtime_preflight` THROUGH the new clone's own wrapper, for every module a task in the
    table enters, with `--expect-commit <tag>`; PASS is required (exit 2 otherwise).
 6. Prints, per task: the `schtasks /Query /XML` backup, the `Set-ScheduledTask` repoint and the
    rollback, in the ch05 switch-plan order. Nothing touches a scheduled task.

Refusals (exit 2): a tag that is not a plain name; a destination that already exists (a
production clone is never re-checked-out, pulled, reset or cleaned -- an upgrade is a NEW clone);
running this script from inside `AEGIS_RUNTIME_ROOT` (from a production clone).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import runtime_task as RT  # noqa: E402  (stdlib-only; reads the same config)

GITHUB_URL = "https://github.com/Murathanx12/Aegis-Finance.git"
TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


class ReleaseRefused(RuntimeError):
    """The release will not proceed; always exit 2."""


@dataclass(frozen=True)
class TaskSpec:
    """One scheduled task's repoint. `wrapper` = the arguments after runtime_task.py; None
    means no action is generated and `manual` says why."""
    order: str
    name: str
    risk: str
    wrapper: Optional[tuple[str, ...]]
    acceptance: str
    note: str = ""
    manual: str = ""


def _w(*args: str) -> tuple[str, ...]:
    return tuple(args)


_OPT = r"backend\data\optimus"
#: The ch05 switch plan (ch05-runtime_REPORT.md section 6), in its order. Reporters first,
#: writers when their readers have moved, orders last and attended.
TASKS: tuple[TaskSpec, ...] = (
    TaskSpec("1", "AegisLocalRuntimeDigest", "A read-only report",
             _w("--pythonw", "-m", "scripts.local_runtime_digest"),
             "a new digest receipt today, rc 0 (fix the stale run.lock from 11-01 first)"),
    TaskSpec("2", "AegisStraddleForward", "A forward-evidence writer, no orders",
             _w("--pythonw", "-m", "scripts.straddle_forward"),
             "`--status` shows policy_hash a0f7e02d84444332; chain ok; a new observation file"),
    TaskSpec("3a", "AegisContestRehearsal", "A sheets, no orders",
             _w("--stop-file", _OPT + r"\contest\STOP", "--stop-file", _OPT + r"\contest\rehearsal\STOP",
                "--set", "AEGIS_PERSONAL_MODE=0", "--log", _OPT + r"\contest\logs\rehearsal_task.log",
                "-m", "scripts.contest_rehearsal", "daily"),
             "today's rehearsal sheet frozen",
             note="the contest ends 2026-11-13: retiring it on 11-14 (OD-b) beats moving it. "
                  "Replaces backend\\data\\optimus\\contest\\contest_rehearsal_task.cmd (same STOP files, "
                  "personal mode, log)."),
    TaskSpec("3b", "AegisContestDesk", "A sheets, no orders",
             _w("--stop-file", _OPT + r"\contest\STOP", "--set", "AEGIS_PERSONAL_MODE=0",
                "--log", _OPT + r"\contest\logs\desk_task.log", "-m", "scripts.contest_desk", "--date", "today",
                "--then", "--log", _OPT + r"\contest\logs\contest_live_task.log",
                "-m", "scripts.contest_rehearsal", "daily", "--mode", "contest"),
             "today's desk sheet and order sheet frozen",
             note="retire on 11-14 rather than move (OD-b). Replaces contest_desk_task.cmd; the exit "
                  "code is now the first failing segment's (the .cmd returned only the second's)."),
    TaskSpec("4", "AegisBrainRefresh", "B writes the Optimus brain (other repo)",
             _w("--pythonw", "-m", "scripts.task_keeper", "brain"),
             "keeper row `brain ok`; brain index mtime advances"),
    TaskSpec("5", "AegisAnalystPull", "B collector",
             _w("--pythonw", "-m", "scripts.task_keeper", "analyst"),
             "keeper row ok; a new analyst snapshot"),
    TaskSpec("6", "AegisRawSecCollection", "B collector (recovery-evidence harness)", None,
             "new raw rows; harness gone",
             manual="runs a hash-pinned recovery-evidence harness; replace with "
                    "`-m scripts.news_pull <its args>` or retire it (OD-a). No action generated."),
    TaskSpec("7", "AegisDailyPass", "B collector + decision contract (no orders)",
             _w("--log", _OPT + r"\daily_pass.log", "-m", "scripts.daily_pass"),
             "night_factory_<date>/daily_pass_<date>.json lands in the shared dir with every step's rc",
             note="OD-f: today it runs the SYSTEM python (httpx 0.27.2); this runs the venv (0.28.1). "
                  "stdin is the null device (was empty_stdin.txt)."),
    TaskSpec("8", "AegisNNLabNightly", "C learner",
             _w("--nn-lab", "--set", "AEGIS_IGNORE_DOTENV=1",
                "--log", _OPT + r"\local_pc\nn_lab\nightly.log", "-m", "nn_lab.nightly"),
             "local_pc/nn_lab/nightly.log advances; forward_grades rows added",
             note="replaces nn_lab\\run_nightly.cmd (same venv, no .env, same log). nn_lab.nightly "
                  "honours nn_lab\\STOP itself."),
    TaskSpec("9", "AegisWorldDigest", "C LLM spend",
             _w("--pythonw", "-m", "scripts.world_digest", "--hours", "24"),
             "typed rows > 0 under the envelope; spend printed",
             note="the owner wants it by market phase, not every 6 h: that is a trigger change, "
                  "separate from this repoint."),
    TaskSpec("10", "AegisHypLabNightly", "C LLM spend",
             _w("--set", "AEGIS_PERSONAL_MODE=0", "--log", _OPT + r"\hyp_lab\nightly.log",
                "-m", "scripts.hyp_lab", "nightly", "--k", "3", "--cap", "0.4"),
             "hyp_lab/ledger.jsonl rows added; not BUDGET_REFUSED",
             note="replaces backend\\data\\optimus\\hyp_lab\\run_nightly.cmd (same args, personal mode, log)."),
    TaskSpec("11", "AegisIIF1NightLauncher", "C LLM night (armed)",
             _w("--log", _OPT + r"\launcher.log", "-m", "scripts.run_night_launcher", "--scheduled"),
             "launch receipt; the night's records_written > 0",
             note="OD-f: system python today; the venv here."),
    TaskSpec("12", "AegisLocalBranchingPrivateGrade", "C grades branch populations", None,
             "a grade receipt; source-commit updated to the tag",
             manual="its arguments pin --source-commit and three file SHA-256s of a 10-15 worktree; "
                    "they must be recomputed for the tag (sha256 of scripts/local_branching_task.py, "
                    "local_branching.py, local_branching_grade_child.py in the clone) before the action "
                    "`--pythonw -m scripts.local_branching_task --source-commit <tag sha> --task-sha ... "
                    "--grade-sha ... --child-sha ...` is valid."),
    TaskSpec("13", "AegisAlerts", "D sends Telegram",
             _w("--pythonw", "-m", "scripts.alert_pass"),
             "not REFUSED on the funnel; DRY_RUN first via --dry-run --scratch, then one SENT",
             note="blocked on OD-i: the clone reads main's committed funnel (10-06) and REFUSES."),
    TaskSpec("14", "AegisOwnerEventWarning", "D owner message (recovery-evidence harness)", None,
             "rc 0 (today rc 2)",
             manual="runs a recovery-evidence PowerShell harness; its main equivalent is "
                    "`-m scripts.owner_event_warning <args>` whose arguments the harness hides (OD-a)."),
    TaskSpec("15", "AegisReaderSupervisor", "D browser (recovery-evidence harness)",
             _w("--pythonw", "-m", "scripts.task_keeper", "reader"),
             "supervisor PID alive; reader logs advance",
             note="NOT READY: task_keeper reader starts backend\\data\\optimus\\dowjones\\supervisor_run.cmd, "
                  "which lives in the DATA dir (the junction serves the LIVE copy) and does "
                  "`cd /d C:\\Users\\mrthn\\aegis-finance` -- it would run the WIP checkout's code. "
                  "Same for night_reader_supervisor's queue_run.cmd. Fix in task_keeper first (R6)."),
    TaskSpec("16", "AegisTelegramAgent", "D two-way messages",
             _w("--pythonw", "-m", "scripts.telegram_agent", "--supervise"),
             "heartbeat ok; one owner round trip",
             note="read-only mode by default (config.TELEGRAM_AGENT_MODE). Stop the old supervisor by "
                  "ITS pid (telegram_agent_lock.json) first; one poller per bot token."),
    TaskSpec("17a", "AegisDataCatalog", "D publishes", None,
             "catalog receipt; publish_commit COMMITTED only on public_receipts",
             manual="runs the PUBLICATION checkout's own code (cwd = that checkout, `-m` imports from "
                    "it) after a `git pull --ff-only` there; not a runtime-clone task. Leave its action; "
                    "after the switch only $env:AEGIS_REPO_ROOT in it may point at the clone (OD-g)."),
    TaskSpec("17b", "AegisPublicAssetsWeekly", "D publishes", None,
             "assets receipt",
             manual="task_keeper `_assets_preflight` refuses unless the code runs FROM the publication "
                    "checkout; by design not a runtime-clone task. Leave its action."),
    TaskSpec("18", "AegisCatchUp", "E dispatcher (starts other tasks)",
             _w("--pythonw", "-m", "scripts.task_keeper", "catchup"),
             "keeper rows; it only starts moved tasks",
             note="move it only after every task it starts has moved."),
    TaskSpec("19", "AegisSimOwner", "E PC-PAPER orders, new pc_policy_epoch code",
             _w("--pythonw", "-m", "scripts.task_keeper", "sim"),
             "attended, weekday, outside the US session; worst case in dollars first; first session "
             "in observe; lease in the new format; reconciliation RECONCILED",
             note="OD-e. Attended only."),
    TaskSpec("20a", "AegisFleetManagerPreclose", "E fleet --live orders",
             _w("--pythonw", "-m", "scripts.fleet_manager_run", "--pass", "preclose", "--live"),
             "attended; positions and stops reconcile; fleet_daily check green",
             note="was `pythonw scripts\\fleet_manager_run.py ...` by path; `-m` with cwd = the clone "
                  "runs the same file (it has a __main__ guard)."),
    TaskSpec("20b", "AegisFleetManagerOpen", "E fleet --live orders",
             _w("--pythonw", "-m", "scripts.fleet_manager_run", "--pass", "open", "--live"),
             "attended; positions and stops reconcile"),
)


def segment_modules(wrapper: Sequence[str]) -> list[str]:
    _opt, segs = RT.parse_argv(list(wrapper))
    return [s.module for s in segs]


def preflight_entries(tasks: Sequence[TaskSpec] = TASKS) -> list[str]:
    out: list[str] = []
    for t in tasks:
        for m in segment_modules(t.wrapper or ()) if t.wrapper else ():
            if m not in out:
                out.append(m)
    return out


# ───────────────────────────────────────────────────────────── planning

def _inside(child: Path, parent: Path) -> bool:
    try:
        Path(os.path.realpath(child)).relative_to(Path(os.path.realpath(parent)))
        return True
    except ValueError:
        return False


def _git(repo: Path, *args: str, run: Callable = subprocess.run) -> subprocess.CompletedProcess:
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    return run(["git", "-C", str(repo), *args], capture_output=True, text=True,
               encoding="utf-8", errors="replace", timeout=600, env=env)


def ps_quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def task_lines(spec: TaskSpec, *, dest: Path, cfg: Mapping[str, str], backup_dir: Path) -> dict:
    """The owner's three commands for one task (backup, repoint, rollback), as text."""
    xml = backup_dir / f"{spec.name}.xml"
    backup = (f"schtasks /Query /TN {ps_quote(spec.name)} /XML | Out-File -Encoding unicode "
              f"{ps_quote(str(xml))}")
    rollback = f"schtasks /Create /TN {ps_quote(spec.name)} /XML {ps_quote(str(xml))} /F"
    if spec.wrapper is None:
        return {"order": spec.order, "task": spec.name, "risk": spec.risk, "backup": backup,
                "set": None, "rollback": rollback, "manual": spec.manual,
                "acceptance": spec.acceptance, "note": spec.note}
    for a in spec.wrapper:
        if any(c in a for c in " \"'"):
            raise ReleaseRefused(f"{spec.name}: argument {a!r} needs quoting; keep task args plain")
    RT.parse_argv(list(spec.wrapper))            # the table itself must parse
    pyw = Path(cfg["AEGIS_VENV_DIR"]) / "Scripts" / "pythonw.exe"
    argument = f"-I \"{dest / 'scripts' / 'runtime_task.py'}\" " + " ".join(spec.wrapper)
    set_cmd = (f"Set-ScheduledTask -TaskName {ps_quote(spec.name)} -Action (New-ScheduledTaskAction "
               f"-Execute {ps_quote(str(pyw))} -Argument {ps_quote(argument)} "
               f"-WorkingDirectory {ps_quote(str(dest))})")
    return {"order": spec.order, "task": spec.name, "risk": spec.risk, "backup": backup,
            "set": set_cmd, "rollback": rollback, "execute": str(pyw), "argument": argument,
            "working_directory": str(dest), "acceptance": spec.acceptance, "note": spec.note}


def build_plan(tag: str, cfg: Mapping[str, str], *, source: Optional[Path] = None,
               repo_url: str = GITHUB_URL, backup_dir: Optional[Path] = None,
               here: Path = REPO, now: Optional[datetime] = None,
               tasks: Sequence[TaskSpec] = TASKS) -> dict:
    """Everything a release does, as data. Raises ReleaseRefused; touches nothing."""
    if not TAG_RE.match(tag or ""):
        raise ReleaseRefused(f"tag {tag!r} is not a plain name ([A-Za-z0-9._-], no slashes)")
    root = Path(cfg["AEGIS_RUNTIME_ROOT"])
    if _inside(here, root):
        raise ReleaseRefused(f"this script is running from {here}, inside the production root {root}: "
                             "never operate from or inside a production clone")
    dest = root / tag
    if dest.exists() or os.path.lexists(dest):
        raise ReleaseRefused(f"{dest} already exists: a production clone is never re-checked-out, "
                             "pulled, reset or cleaned; release a NEW tag to a new directory")
    live = Path(cfg["AEGIS_LIVE_OPTIMUS"])
    source = Path(source or cfg["AEGIS_LIVE_ROOT"])
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = Path(backup_dir or (root / "task_xml_backup" / f"{tag}_{stamp}"))
    entries = preflight_entries(tasks)
    receipt = live / "runtime_switch" / f"release_{tag}_{stamp}.json"
    py = Path(cfg["AEGIS_VENV_DIR"]) / "Scripts" / "python.exe"
    junctions = [(dest / "backend" / "data" / "optimus", live),
                 (dest / ".venv", Path(cfg["AEGIS_VENV_DIR"])),
                 (dest / "nn_lab" / ".venv", Path(cfg["AEGIS_NN_LAB_VENV_DIR"]))]
    preflight = [str(py), "-I", str(dest / "scripts" / "runtime_task.py"), "-m", "scripts.runtime_preflight",
                 *[x for e in entries for x in ("--entry", e)], "--expect-commit", tag,
                 "--expect-optimus", str(live), "--receipt", str(receipt)]
    steps = [
        {"kind": "git", "argv": ["git", "clone", "--no-checkout", str(source), str(dest)],
         "why": "clone the object store (a local read of the source; nothing there is modified)"},
        {"kind": "git", "argv": ["git", "-C", str(dest), "remote", "set-url", "origin", repo_url],
         "why": "a later fetch in the clone never reads the WIP checkout"},
        {"kind": "resolve_tag", "argv": ["git", "-C", str(dest), "rev-parse", "--verify",
                                         f"refs/tags/{tag}^{{commit}}"],
         "why": "a TAG, never a branch name"},
        {"kind": "git", "argv": ["git", "-C", str(dest), "-c", "advice.detachedHead=false",
                                 "checkout", "--detach", f"refs/tags/{tag}"],
         "why": "detached at the tag, BEFORE any junction exists"},
        {"kind": "verify_head", "argv": ["git", "-C", str(dest), "rev-parse", "HEAD"],
         "why": "HEAD is the tag's commit"},
        {"kind": "remove_tracked_optimus", "path": str(junctions[0][0]),
         "why": "main's tracked copies inside the NEW clone only; must be a real directory"},
        *[{"kind": "junction", "link": str(a), "target": str(b),
           "argv": ["cmd", "/c", "mklink", "/J", str(a), str(b)],
           "why": "shared " + ("data" if i == 0 else "interpreter")}
          for i, (a, b) in enumerate(junctions)],
        {"kind": "preflight", "argv": preflight, "cwd": str(dest),
         "why": "runtime_preflight through the clone's own wrapper; PASS required"},
    ]
    return {"schema": "runtime_release/1", "tag": tag, "dest": str(dest), "source": str(source),
            "live_optimus": str(live), "backup_dir": str(backup_dir), "receipt": str(receipt),
            "preflight_entries": entries, "steps": steps,
            "tasks": [task_lines(t, dest=dest, cfg=cfg, backup_dir=backup_dir) for t in tasks]}


# ───────────────────────────────────────────────────────────── executing

def _is_link_or_junction(p: Path) -> bool:
    if os.path.islink(p):
        return True
    is_junction = getattr(p, "is_junction", None)          # Python 3.12+
    return bool(is_junction and is_junction())


def remove_tracked_optimus(path: Path, dest: Path) -> None:
    """Delete the NEW clone's real `backend/data/optimus`, never anything else."""
    path, dest = Path(path), Path(dest)
    if _is_link_or_junction(path):
        raise ReleaseRefused(f"{path} is already a link/junction; refusing to delete through it")
    if not _inside(path, dest) or Path(os.path.realpath(path)) == Path(os.path.realpath(dest)):
        raise ReleaseRefused(f"{path} is not inside the new clone {dest}")
    if not path.is_dir():
        raise ReleaseRefused(f"{path} is not a directory after checkout")
    for p in path.rglob("*"):                               # git never writes links here
        if _is_link_or_junction(p):
            raise ReleaseRefused(f"{p} is a link inside the tracked copy; refusing")
    shutil.rmtree(path)


def execute(plan: dict, *, run: Callable = subprocess.run, out=print) -> int:
    dest = Path(plan["dest"])
    tag_sha = None
    for st in plan["steps"]:
        out(f"-- {st['kind']}: {st['why']}")
        if st["kind"] == "remove_tracked_optimus":
            remove_tracked_optimus(Path(st["path"]), dest)
            continue
        if st["kind"] == "junction":
            link, target = Path(st["link"]), Path(st["target"])
            if not target.is_dir():
                if link.name == ".venv" and link.parent.name == "nn_lab":
                    out(f"   WARN: {target} absent; nn_lab tasks will refuse until it exists")
                    continue
                raise ReleaseRefused(f"junction target {target} is not a directory")
            link.parent.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
        r = run(st["argv"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=3600, cwd=st.get("cwd"), env=env)
        if r.returncode != 0:
            out((r.stdout or "")[-2000:])
            out((r.stderr or "")[-2000:])
            raise ReleaseRefused(f"step {st['kind']} failed rc {r.returncode}: {' '.join(st['argv'][:6])} ...")
        if st["kind"] == "resolve_tag":
            tag_sha = r.stdout.strip()
        elif st["kind"] == "verify_head" and r.stdout.strip() != tag_sha:
            raise ReleaseRefused(f"HEAD {r.stdout.strip()} is not the tag's commit {tag_sha}")
        elif st["kind"] == "junction":
            if os.path.realpath(st["link"]) != os.path.realpath(st["target"]):
                raise ReleaseRefused(f"junction {st['link']} does not resolve to {st['target']}")
        elif st["kind"] == "preflight":
            out((r.stderr or "")[-1500:])
    out(f"RELEASE READY: {dest} at {plan['tag']} ({tag_sha}); preflight receipt {plan['receipt']}")
    return 0


# ───────────────────────────────────────────────────────────── printing

def render(plan: dict, *, dry_run: bool) -> str:
    L = [f"# runtime release {plan['tag']} -> {plan['dest']}"
         + ("   (DRY RUN: nothing was created)" if dry_run else ""),
         f"# source object store: {plan['source']}   live data: {plan['live_optimus']}", ""]
    if dry_run:
        L.append("# steps a real run takes")
        for st in plan["steps"]:
            what = " ".join(st["argv"]) if "argv" in st else f"delete real dir {st['path']}"
            L.append(f"#   [{st['kind']}] {what}")
        L.append("")
    L += ["# ---- task repoints: run by the OWNER, one at a time, in this order. Before each: the task",
          "# has no running instance (Get-ScheduledTask State != Running, no PID in its lock file).",
          "# After each: runtime_preflight PASS, one supervised firing whose OWN receipt advances.",
          f"New-Item -ItemType Directory -Force {ps_quote(plan['backup_dir'])} | Out-Null", ""]
    for t in plan["tasks"]:
        L.append(f"# [{t['order']}] {t['task']}  ({t['risk']})")
        L.append(f"#   accept: {t['acceptance']}")
        if t.get("note"):
            L.append(f"#   note: {t['note']}")
        L.append(t["backup"])
        if t["set"]:
            L.append(t["set"])
        else:
            L.append(f"#   NO ACTION GENERATED: {t['manual']}")
        L.append(f"#   rollback: {t['rollback']}")
        L.append("")
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="runtime_release", description=__doc__.split("\n\n")[0])
    ap.add_argument("--tag", required=True)
    ap.add_argument("--dry-run", action="store_true", help="print the plan; create nothing")
    ap.add_argument("--source", type=Path, default=None,
                    help="where to clone from (default AEGIS_LIVE_ROOT's object store)")
    ap.add_argument("--repo-url", default=GITHUB_URL)
    ap.add_argument("--backup-dir", type=Path, default=None)
    ap.add_argument("--json", action="store_true", help="print the plan as JSON")
    a = ap.parse_args(argv)
    try:
        cfg = RT.read_config()
        plan = build_plan(a.tag, cfg, source=a.source, repo_url=a.repo_url, backup_dir=a.backup_dir)
        if a.dry_run:
            r = _git(Path(plan["source"]), "rev-parse", "--verify", f"refs/tags/{a.tag}^{{commit}}")
            plan["tag_sha_in_source"] = r.stdout.strip() if r.returncode == 0 else None
            print(json.dumps(plan, indent=1) if a.json else render(plan, dry_run=True))
            if plan["tag_sha_in_source"] is None:
                print(f"# WARN: refs/tags/{a.tag} is not in {plan['source']} yet "
                      "(tag on main, then `git fetch origin --tags` there)", file=sys.stderr)
            return 0
        execute(plan)
        print(json.dumps(plan, indent=1) if a.json else render(plan, dry_run=False))
        return 0
    except (ReleaseRefused, RT.Refused) as exc:
        print(f"RUNTIME RELEASE REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
