"""Make a production clone of a release tag, and print (never run) each task's repoint.

    python -m scripts.runtime_release --tag runtime-20261115 --dry-run   # the plan, nothing made
    python -m scripts.runtime_release --tag runtime-20261115             # clone + junctions + preflight
    python -m scripts.runtime_release --retire runtime-20261115 --dry-run   # what a retire removes
    python -m scripts.runtime_release --retire runtime-20261115             # the ONLY safe delete
    python -m scripts.runtime_release --repoint-plan 20261115a --out <dir>  # READ-ONLY plan + 2 scripts

`--repoint-plan <tag>` (S70 P4, engineer D7) reads the scheduler (read-only `Get-ScheduledTask`,
no window, bounded; a failed read REFUSES, never an empty plan) and plans every task whose
action names a release clone: ON_TARGET, ATTENDED (config RUNTIME_REPOINT_ATTENDED_*: can reach
an order path), SKIP_RUNNING, REFUSED_MODULE_MISSING, REFUSED_CONFIG_DRIFT (a running population's
declaration.json differs from the target's own `config_snapshot()`), or REPOINT. The whole plan
refuses unless the target clone exists and its newest `runtime_switch/release_<tag>_*.json`
preflight is PASS for that clone. With `--out` it writes `repoint_<tag>.ps1` (REPOINT rows only:
re-checks Running and the action, exports the XML, `Set-ScheduledTask -Action` only) and
`rollback_<tag>.ps1` (re-registers each from that XML). The tool runs neither. Exit 0; 3 when a
task was refused; 2 when the plan was.

CH-05 (wrapper PR "W", fixed after review 5). The scheduled tasks stop running from the dirty
WIP checkout and run from a fresh clone of a tag at `<parent of AEGIS_LIVE_ROOT>\\aegis-runtime-<tag>`
-- BESIDE the live checkout, so every `REPO.parent / <sibling repo>` path the code builds
resolves exactly as it does today (review 5 B2) -- whose `backend\\data\\optimus` is a junction
to the live data (`AEGIS_LIVE_OPTIMUS`). This script makes that clone and verifies it; the
repoint of each task is the OWNER's, so it is printed, not run.

What a real run does, in order, stopping at the first failure:
 0. Checks in the SOURCE (a read) that the tag's commit is an ancestor of `origin/main`: a
    pushed tag on another branch is not a release (review 5 m7).
 1. `git clone --no-checkout <source> <dest>` (default source: the live checkout's object store,
    a local read; nothing in the source is modified), then `remote set-url origin <github>`.
 2. Resolves `refs/tags/<tag>` (a TAG, never a branch) and `checkout --detach` it.
 3. Deletes the clone's OWN `backend\\data\\optimus` (main's tracked copies, just written by the
    checkout; asserted to be a real directory inside the new clone, never a junction), then makes
    the junction to the live data. The order matters: a checkout with the junction already in
    place would write main's copies INTO the live data.
 4. Junctions `<clone>\\.venv`, `<clone>\\nn_lab\\.venv` and `<clone>\\ft_lab\\data` to the live
    copies (all gitignored). `runtime_preflight.LIVE_STATE` is the full inventory of live state
    outside the optimus junction and how each piece is handled. The paper_nav database is NOT
    junctioned or linked: the wrapper exports AEGIS_PI_DB_PATH to the live file (B1).
 5. Runs `runtime_preflight` THROUGH the new clone's own wrapper, for every module a task in the
    table enters, with `--expect-commit <tag> --expect-pi-db <live db> --live-root <live>`;
    PASS is required (exit 2 otherwise). It also checks every sibling path (B2).
 6. Prints, per task: the `schtasks /Query /XML` backup, the `Set-ScheduledTask` repoint and the
    rollback, in the ch05 switch-plan order. Nothing touches a scheduled task. Task XML backups
    go under `<AEGIS_LIVE_OPTIMUS>\\runtime_switch\\task_xml_backup`, never inside a clone.
 7. Prints the desktop app step (CH-22b). The owner's one `Aegis.lnk` starts the app FROM a
    release clone, and a new clone has neither `node_modules` nor a frontend export, so each
    release needs `npm ci`, the export, and the shortcut repointed. Printed, never run.

`--retire <tag>` (review 5 M4) is the only supported way to delete a clone. Every clone holds
junctions to LIVE state (the ~82 GB data dir among them), and a recursive delete that follows a
junction deletes the live target. Retire refuses unless the clone is a real directory named
`aegis-runtime-<tag>` beside the live checkout, no scheduled task action names it (read-only
`schtasks /Query /XML`), no running process names it in its command line, and no shortcut or
script on the Desktop, in the Start Menu or in Startup names it (a retired clone would leave a
double-click that does nothing, and the app is the reader's only control). It then removes
every junction/symlink in the clone with a call that removes the LINK (`os.rmdir`/`os.unlink`
on the verified reparse point itself), re-walks the tree to prove no reparse point remains, and
only then deletes the tree. Never `Remove-Item -Recurse`, `rmdir /s` or Explorer on a clone.

Refusals (exit 2): a tag that is not a plain name; a destination that already exists (a
production clone is never re-checked-out, pulled, reset or cleaned -- an upgrade is a NEW clone);
running this script from inside a production clone.
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
from scripts import runtime_preflight as RP  # noqa: E402  (stdlib at import; LIVE_STATE)

GITHUB_URL = "https://github.com/Murathanx12/Aegis-Finance.git"
TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
#: Printed with RELEASE READY and with every refusal once a junction may exist (M4).
DELETE_RULE = ("never delete a release clone with Remove-Item -Recurse, rmdir /s or Explorer: it "
               "holds junctions to LIVE data; use `python -m scripts.runtime_release --retire <tag>`")
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
#: Live state that is junctioned but may legitimately be absent (a WARN, the task refuses).
OPTIONAL_JUNCTIONS = frozenset({"nn_lab/.venv", "ft_lab/data"})
#: The owner's one desktop entry point and what it runs through the wrapper (CH-22b).
DESKTOP_SHORTCUT = "Aegis.lnk"
DESKTOP_WRAPPER = ("--allow-breakaway", "--pythonw", "-m", "desktop.aegis_desktop")
#: Where a double-click or a logon starts something: (User Shell Folders value, walk subfolders).
#: The Desktop is listed flat: under OneDrive a recursive walk can stall on cloud-only folders.
SHELL_FOLDERS = (("Desktop", False), ("Programs", True), ("Startup", True))
LAUNCHER_SUFFIXES = frozenset({".lnk", ".url", ".vbs", ".cmd", ".bat", ".ps1"})


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
    #: Non-empty: the repoint is printed COMMENTED OUT behind this reason (an owner decision
    #: the task depends on), so copy-pasting the whole plan cannot repoint it.
    blocked: str = ""


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
             "night_factory_<date>/daily_pass_<date>.json lands in the shared dir with every step's rc; "
             "paper_nav max(computed_at) advances in the LIVE aegis_pi.db",
             note="OD-f: today it runs the SYSTEM python (httpx 0.27.2); this runs the venv (0.28.1). "
                  "stdin is the null device (was empty_stdin.txt). The decision-contract step reads "
                  "config.IC_FUNNEL_PATH, which in a clone is the TAG's committed funnel (review 5 M2); "
                  "it also writes docs/BRIDGE.md, docs/PAPER_ACCOUNTS.md and docs/assets/*.png into "
                  "the clone's tracked docs (m8).",
             blocked="OD-i (which funnel a clone serves) and m8 (generated docs)"),
    TaskSpec("8", "AegisNNLabNightly", "C learner",
             _w("--nn-lab", "--set", "AEGIS_IGNORE_DOTENV=1",
                "--log", _OPT + r"\local_pc\nn_lab\nightly.log", "-m", "nn_lab.nightly"),
             "local_pc/nn_lab/nightly.log advances; forward_grades rows added",
             note="replaces nn_lab\\run_nightly.cmd (same venv, no .env, same log). nn_lab.nightly "
                  "honours nn_lab\\STOP itself."),
    TaskSpec("9", "AegisWorldDigest", "C LLM spend",
             _w("--pythonw", "-m", "scripts.world_digest", "--phase-auto"),
             "typed rows > 0 under the envelope; spend printed; schedule/decisions.jsonl has one "
             "RUN or a declared SKIP per tick",
             note="--phase-auto (review 5 M3): the 0.60 monthly share and the market-phase slots are "
                  "enforced only in this mode; `--hours 24` every 6 h projected ~$16/month against "
                  "the $15 cap. The TRIGGER must change too, by the owner, in the same step: every "
                  "30 minutes, MultipleInstancesPolicy IgnoreNew, ExecutionTimeLimit PT60M. This "
                  "Set-ScheduledTask line changes the action only."),
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
             note="the clone reads the tag's committed funnel (main: 2026-10-06) and REFUSES on its age.",
             blocked="OD-i (which funnel a clone serves)"),
    TaskSpec("14", "AegisOwnerEventWarning", "D owner message (recovery-evidence harness)", None,
             "rc 0 (today rc 2)",
             manual="runs a recovery-evidence PowerShell harness; its main equivalent is "
                    "`-m scripts.owner_event_warning <args>` whose arguments the harness hides (OD-a)."),
    TaskSpec("15", "AegisReaderSupervisor", "D browser (recovery-evidence harness)",
             _w("--allow-breakaway", "--pythonw", "-m", "scripts.task_keeper", "reader"),
             "supervisor PID alive AFTER the task ends; reader logs advance",
             note="--allow-breakaway: the supervisor this task starts must outlive it; in the default "
                  "tree mode the wrapper's kill-on-close job would kill it when the task returned. "
                  "Needs a tag that includes PR #105 (merged 2026-11-11): before it, task_keeper reader "
                  "started the data-dir supervisor_run.cmd, whose `cd /d C:\\Users\\mrthn\\aegis-finance` "
                  "ran the WIP checkout's code; #105 launches the supervisor from THIS checkout."),
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
             _w("--allow-breakaway", "--pythonw", "-m", "scripts.task_keeper", "sim"),
             "attended, weekday, outside the US session; worst case in dollars first; first session "
             "in observe; lease in the new format; reconciliation RECONCILED",
             note="OD-e. Attended only. --allow-breakaway: sim_session.start launches the session "
                  "DETACHED (sim_session._spawn) and it must outlive this task. sim_run reads "
                  "config.IC_FUNNEL_PATH (the tag's funnel in a clone).",
             blocked="OD-e (attended PC-epoch switch) and OD-i (funnel)"),
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
    c = os.path.normcase(os.path.realpath(child))
    p = os.path.normcase(os.path.realpath(parent))
    return c == p or c.startswith(p.rstrip("\\/") + os.sep)


def clone_parent(cfg: Mapping[str, str]) -> Path:
    """Release clones live BESIDE the live checkout (B2): `REPO.parent` is then the same
    directory for both, and every sibling path the code derives from it still resolves."""
    return Path(cfg["AEGIS_LIVE_ROOT"]).parent


def clone_dest(tag: str, cfg: Mapping[str, str]) -> Path:
    if not TAG_RE.match(tag or ""):
        raise ReleaseRefused(f"tag {tag!r} is not a plain name ([A-Za-z0-9._-], no slashes)")
    return clone_parent(cfg) / f"{RT.CLONE_PREFIX}{tag}"


def production_clone_of(here: Path, cfg: Mapping[str, str]) -> Optional[Path]:
    """The release clone `here` is inside (any `<parent>\\aegis-runtime-*`), else None."""
    parent = Path(os.path.realpath(clone_parent(cfg)))
    h = Path(os.path.realpath(here))
    try:
        first = h.relative_to(parent).parts[:1]
    except ValueError:
        return None
    if first and first[0].lower().startswith(RT.CLONE_PREFIX):
        return parent / first[0]
    return None


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
            "working_directory": str(dest), "acceptance": spec.acceptance, "note": spec.note,
            "blocked": spec.blocked}


def desktop_lines(tag: str, *, dest: Path, cfg: Mapping[str, str], backup_dir: Path) -> dict:
    """The owner's desktop app step for one release (CH-22b), as text. The app is served FROM
    the clone, so every new clone needs its own frontend export and the shortcut repointed."""
    RT.parse_argv(list(DESKTOP_WRAPPER))
    scripts = Path(cfg["AEGIS_VENV_DIR"]) / "Scripts"
    argument = f"-I \"{dest / 'scripts' / 'runtime_task.py'}\" " + " ".join(DESKTOP_WRAPPER)
    lnk = f"(Join-Path ([Environment]::GetFolderPath('Desktop')) {ps_quote(DESKTOP_SHORTCUT)})"
    saved = ps_quote(str(backup_dir / DESKTOP_SHORTCUT))
    props = {"TargetPath": str(scripts / "pythonw.exe"), "Arguments": argument,
             "WorkingDirectory": str(dest),
             "IconLocation": f"{dest / 'desktop' / 'assets' / 'aegis.ico'},0",
             "Description": f"Aegis - local research desktop (release {tag})"}
    return {
        "export": [f"Push-Location {ps_quote(str(dest / 'frontend'))}; npm ci; Pop-Location",
                   f"Push-Location {ps_quote(str(dest))}; & {ps_quote(str(scripts / 'python.exe'))} "
                   "-m scripts.frontend_check --skip site; Pop-Location"],
        "backup": f"Copy-Item {lnk} {saved}",
        "set": (f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({lnk}); "
                + "; ".join(f"$s.{k} = {ps_quote(v)}" for k, v in props.items()) + "; $s.Save()"),
        "rollback": f"Copy-Item {saved} {lnk} -Force",
        "argument": argument, "working_directory": str(dest),
        "acceptance": (f"{dest / 'frontend' / 'out' / 'desktop' / 'reader' / 'index.html'} exists; close "
                       "the app and open it from the shortcut: aegis_desktop_report.json in the live data "
                       f"dir shows health_ok true and repo_root {dest}"),
    }


def build_plan(tag: str, cfg: Mapping[str, str], *, source: Optional[Path] = None,
               repo_url: str = GITHUB_URL, backup_dir: Optional[Path] = None,
               here: Path = REPO, now: Optional[datetime] = None,
               tasks: Sequence[TaskSpec] = TASKS) -> dict:
    """Everything a release does, as data. Raises ReleaseRefused; touches nothing."""
    dest = clone_dest(tag, cfg)
    inside = production_clone_of(here, cfg)
    if inside is not None:
        raise ReleaseRefused(f"this script is running from {here}, inside the production clone "
                             f"{inside}: never operate from or inside a production clone")
    if dest.exists() or os.path.lexists(dest):
        raise ReleaseRefused(f"{dest} already exists: a production clone is never re-checked-out, "
                             "pulled, reset or cleaned; release a NEW tag to a new directory")
    live_root = Path(cfg["AEGIS_LIVE_ROOT"])
    live = Path(cfg["AEGIS_LIVE_OPTIMUS"])
    source = Path(source or live_root)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    # in the LIVE data dir, never inside a clone: a retire can never delete the rollbacks
    backup_dir = Path(backup_dir or (live / "runtime_switch" / "task_xml_backup" / f"{tag}_{stamp}"))
    if _inside(backup_dir, dest):
        raise ReleaseRefused(f"backup dir {backup_dir} is inside the clone; keep rollbacks outside it")
    entries = preflight_entries(tasks)
    receipt = live / "runtime_switch" / f"release_{tag}_{stamp}.json"
    py = Path(cfg["AEGIS_VENV_DIR"]) / "Scripts" / "python.exe"
    # every LIVE_STATE junction, in table order; optimus first (it replaces a checked-out dir)
    targets = {"backend/data/optimus": live, ".venv": Path(cfg["AEGIS_VENV_DIR"]),
               "nn_lab/.venv": Path(cfg["AEGIS_NN_LAB_VENV_DIR"])}
    junctions = [(item["path"], dest.joinpath(*item["path"].split("/")),
                  targets.get(item["path"], live_root.joinpath(*item["path"].split("/"))))
                 for item in RP.LIVE_STATE if item["how"] == "junction"]
    preflight = [str(py), "-I", str(dest / "scripts" / "runtime_task.py"), "-m", "scripts.runtime_preflight",
                 *[x for e in entries for x in ("--entry", e)], "--expect-commit", tag,
                 "--expect-optimus", str(live), "--expect-pi-db", cfg["AEGIS_LIVE_PI_DB"],
                 "--live-root", str(live_root), "--receipt", str(receipt)]
    steps = [
        {"kind": "ancestry", "argv": ["git", "-C", str(source), "merge-base", "--is-ancestor",
                                      f"refs/tags/{tag}^{{commit}}", "refs/remotes/origin/main"],
         "why": "the tag's commit is on origin/main (a read in the source)"},
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
        {"kind": "remove_tracked_optimus", "path": str(junctions[0][1]),
         "why": "main's tracked copies inside the NEW clone only; must be a real directory"},
        *[{"kind": "junction", "rel": rel, "link": str(a), "target": str(b),
           "optional": rel in OPTIONAL_JUNCTIONS,
           "argv": ["cmd", "/c", "mklink", "/J", str(a), str(b)],
           "why": f"live {rel} (runtime_preflight.LIVE_STATE)"}
          for rel, a, b in junctions],
        {"kind": "preflight", "argv": preflight, "cwd": str(dest),
         "why": "runtime_preflight through the clone's own wrapper; PASS required"},
    ]
    return {"schema": "runtime_release/2", "tag": tag, "dest": str(dest), "source": str(source),
            "live_optimus": str(live), "live_pi_db": cfg["AEGIS_LIVE_PI_DB"],
            "backup_dir": str(backup_dir), "receipt": str(receipt),
            "preflight_entries": entries, "steps": steps,
            "live_state": [dict(i) for i in RP.LIVE_STATE],
            "tasks": [task_lines(t, dest=dest, cfg=cfg, backup_dir=backup_dir) for t in tasks],
            "desktop": desktop_lines(tag, dest=dest, cfg=cfg, backup_dir=backup_dir)}


# ───────────────────────────────────────────────────────────── executing

def _is_link_or_junction(p: Path) -> bool:
    if os.path.islink(p):
        return True
    is_junction = getattr(p, "is_junction", None)          # Python 3.12+
    return bool(is_junction and is_junction())


def remove_tracked_optimus(path: Path, dest: Path) -> None:
    """Delete the NEW clone's real `backend/data/optimus`, never anything else. Absent is
    fine (main may track nothing there once growing data has left git, OD-c)."""
    path, dest = Path(path), Path(dest)
    if _is_link_or_junction(path):
        raise ReleaseRefused(f"{path} is already a link/junction; refusing to delete through it")
    if not _inside(path, dest) or _inside(dest, path):
        raise ReleaseRefused(f"{path} is not inside the new clone {dest}")
    if not os.path.lexists(path):
        return
    if not path.is_dir():
        raise ReleaseRefused(f"{path} is not a directory after checkout")
    for p in path.rglob("*"):                               # git never writes links here
        if _is_link_or_junction(p):
            raise ReleaseRefused(f"{p} is a link inside the tracked copy; refusing")
    shutil.rmtree(path)


def execute(plan: dict, *, run: Callable = subprocess.run, out=print) -> int:
    dest = Path(plan["dest"])
    tag_sha = None
    linked = False                       # once a junction may exist, every refusal says how to delete
    try:
        for st in plan["steps"]:
            out(f"-- {st['kind']}: {st['why']}")
            if st["kind"] == "remove_tracked_optimus":
                remove_tracked_optimus(Path(st["path"]), dest)
                continue
            if st["kind"] == "junction":
                link, target = Path(st["link"]), Path(st["target"])
                if not target.is_dir():
                    if st.get("optional"):
                        out(f"   WARN: {target} absent; the tasks that read {st['rel']} will refuse "
                            "or degrade until it exists (runtime_preflight live_state)")
                        continue
                    raise ReleaseRefused(f"junction target {target} is not a directory")
                if os.path.lexists(link):
                    raise ReleaseRefused(f"{link} already exists in the new clone (tracked by the tag?); "
                                         "refusing to junction over it")
                link.parent.mkdir(parents=True, exist_ok=True)
                linked = True
            env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
            r = run(st["argv"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=3600, cwd=st.get("cwd"), env=env)
            if r.returncode != 0:
                out((r.stdout or "")[-2000:])
                out((r.stderr or "")[-2000:])
                if st["kind"] == "ancestry":
                    raise ReleaseRefused(f"the tag {plan['tag']} is not on origin/main in {plan['source']} "
                                         f"(merge-base --is-ancestor rc {r.returncode}); fetch, or tag main")
                raise ReleaseRefused(f"step {st['kind']} failed rc {r.returncode}: {' '.join(st['argv'][:6])} ...")
            if st["kind"] == "resolve_tag":
                tag_sha = r.stdout.strip()
            elif st["kind"] == "verify_head" and r.stdout.strip() != tag_sha:
                raise ReleaseRefused(f"HEAD {r.stdout.strip()} is not the tag's commit {tag_sha}")
            elif st["kind"] == "junction":
                if os.path.normcase(os.path.realpath(st["link"])) != os.path.normcase(os.path.realpath(st["target"])):
                    raise ReleaseRefused(f"junction {st['link']} does not resolve to {st['target']}")
            elif st["kind"] == "preflight":
                out((r.stderr or "")[-1500:])
    except ReleaseRefused as exc:
        if linked:
            raise ReleaseRefused(f"{exc}. The half-built clone {dest} holds junctions: {DELETE_RULE}") from None
        raise
    out(f"RELEASE READY: {dest} at {plan['tag']} ({tag_sha}); preflight receipt {plan['receipt']}. "
        f"To remove it later: {DELETE_RULE}")
    return 0


# ───────────────────────────────────────────────────────────── retire (M4)

def _is_reparse_point(p: Path) -> bool:
    """Any NTFS reparse point (junction, symlink, other), read WITHOUT following it."""
    try:
        st = os.lstat(p)
    except OSError:
        return False
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT) or os.path.islink(p)


def reparse_points(root: Path) -> list[dict]:
    """Every reparse point under `root`, found without descending into any of them."""
    found: list[dict] = []
    stack = [Path(root)]
    while stack:
        d = stack.pop()
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        for e in entries:
            p = Path(e.path)
            if _is_reparse_point(p):
                try:
                    target = os.readlink(p)
                except OSError:
                    target = None
                attrs = getattr(os.lstat(p), "st_file_attributes", 0)
                found.append({"path": str(p),
                              # the LINK's own attribute: a junction or a `mklink /D` symlink is a
                              # directory entry (removed with rmdir), a file symlink is not
                              "dir": bool(attrs & 0x10) or e.is_dir(follow_symlinks=False),
                              "junction": bool(getattr(p, "is_junction", lambda: False)()),
                              "symlink": os.path.islink(p), "target": target})
            elif e.is_dir(follow_symlinks=False):
                stack.append(p)
    return sorted(found, key=lambda r: r["path"])


def query_task_xml() -> str:
    """Read-only: every scheduled task's XML (`schtasks /Query /XML`)."""
    r = subprocess.run(["schtasks", "/Query", "/XML"], capture_output=True, text=True,
                       errors="replace", timeout=120)
    if r.returncode != 0:
        raise ReleaseRefused(f"schtasks /Query /XML failed rc {r.returncode}: cannot prove no task "
                             "still runs from the clone")
    return r.stdout


def _norm(s: str) -> str:
    return os.path.normcase(str(s).replace("/", os.sep).replace("\\", os.sep))


def _names_path(text: str, dest: Path) -> bool:
    """`text` mentions `dest` itself or a path under it (any case, either slash), and not a
    longer sibling name (`aegis-runtime-x` must not match `aegis-runtime-x2`)."""
    return re.search(re.escape(_norm(str(dest))) + r"(?![A-Za-z0-9._-])", _norm(text)) is not None


def tasks_naming(dest: Path, xml_text: str) -> list[str]:
    """Task names whose XML (`<!-- \\Name -->` precedes each task) mentions `dest`."""
    names, current = set(), None
    for line in xml_text.splitlines():
        s = line.strip()
        if s.startswith("<!--") and s.endswith("-->"):
            current = s[4:-3].strip()
            continue
        if _names_path(s, dest):
            names.add(current or "<unknown task>")
    return sorted(names)


def query_process_cmdlines() -> list[str]:
    """Read-only: the command line of every running process."""
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        "Get-CimInstance Win32_Process | ForEach-Object { [string]$_.ProcessId + ' ' + "
                        "[string]$_.CommandLine }"],
                       capture_output=True, text=True, errors="replace", timeout=120)
    if r.returncode != 0:
        raise ReleaseRefused(f"process listing failed rc {r.returncode}: cannot prove nothing runs "
                             "from the clone")
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def shell_folders() -> list[tuple[Path, bool]]:
    """Read-only: the user's Desktop, Start Menu and Startup folders, from the registry (OneDrive
    redirects the Desktop, so `~/Desktop` is not the authority). Empty off Windows."""
    if sys.platform != "win32":
        return []
    import winreg  # noqa: PLC0415
    found: list[tuple[Path, bool]] = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
            for name, deep in SHELL_FOLDERS:
                try:
                    raw, _ = winreg.QueryValueEx(key, name)
                except FileNotFoundError:
                    continue
                found.append((Path(os.path.expandvars(raw)), deep))
    except OSError as exc:
        raise ReleaseRefused(f"cannot read User Shell Folders ({exc}): cannot prove no shortcut "
                             "still starts the clone") from exc
    if not found:
        raise ReleaseRefused("User Shell Folders names no Desktop, Programs or Startup folder: cannot "
                             "prove no shortcut still starts the clone")
    return found


def launcher_text(raw: bytes) -> str:
    """Every reading of a launcher's bytes a path can hide in. A .lnk stores its target in the
    ANSI code page and usually again as UTF-16 at an arbitrary offset: latin-1, the same with
    NULs dropped (UTF-16 ASCII at either alignment), and both UTF-16 alignments."""
    return "\n".join([raw.decode("latin-1"), raw.replace(b"\x00", b"").decode("latin-1"),
                      raw.decode("utf-16-le", errors="replace"),
                      raw[1:].decode("utf-16-le", errors="replace")])


def query_launchers(folders: Optional[Sequence[tuple[Path, bool]]] = None) -> list[tuple[str, str]]:
    """Read-only: (path, text) for every shortcut or script in the shell folders."""
    seen: dict[str, tuple[str, str]] = {}
    for root, deep in (shell_folders() if folders is None else folders):
        stack = [Path(root)]
        while stack:
            d = stack.pop()
            try:
                entries = list(os.scandir(d))
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise ReleaseRefused(f"cannot list {d} ({exc}): cannot prove no shortcut still "
                                     "starts the clone") from exc
            for e in entries:
                if e.is_dir(follow_symlinks=False):
                    if deep:
                        stack.append(Path(e.path))
                elif Path(e.name).suffix.lower() in LAUNCHER_SUFFIXES and _norm(e.path) not in seen:
                    try:
                        seen[_norm(e.path)] = (e.path, launcher_text(Path(e.path).read_bytes()))
                    except OSError as exc:
                        raise ReleaseRefused(f"cannot read {e.path} ({exc}): cannot prove it does "
                                             "not start the clone") from exc
    return sorted(seen.values())


def plan_retire(tag: str, cfg: Mapping[str, str], *, here: Path = REPO,
                task_xml: Optional[Callable[[], str]] = None,
                processes: Optional[Callable[[], list[str]]] = None,
                launchers: Optional[Callable[[], list[tuple[str, str]]]] = None) -> dict:
    """What a retire would remove, as data. Reads only; raises ReleaseRefused."""
    dest = clone_dest(tag, cfg)
    live_root = Path(cfg["AEGIS_LIVE_ROOT"])
    if not os.path.lexists(dest):
        raise ReleaseRefused(f"{dest} does not exist")
    if _is_reparse_point(dest) or not dest.is_dir():
        raise ReleaseRefused(f"{dest} is a link or not a directory; refusing (remove a link with "
                             "`cmd /c rmdir <path>` after checking what it points at)")
    for protected in (live_root, Path(cfg["AEGIS_LIVE_OPTIMUS"]), clone_parent(cfg)):
        if _inside(protected, dest):
            raise ReleaseRefused(f"{dest} contains {protected}; refusing")
    if _inside(here, dest):
        raise ReleaseRefused(f"this script runs from inside {dest}; run it from a main worktree")
    points = reparse_points(dest)
    bad = [p for p in points if not (p["junction"] or p["symlink"])]
    if bad:
        raise ReleaseRefused(f"{len(bad)} reparse point(s) in {dest} are neither junctions nor symlinks "
                             f"(first: {bad[0]['path']}); refusing to guess how to remove them")
    tasks = tasks_naming(dest, (task_xml or query_task_xml)())
    procs = [ln for ln in (processes or query_process_cmdlines)() if _names_path(ln, dest)]
    shortcuts = [path for path, text in (launchers or query_launchers)() if _names_path(text, dest)]
    return {"schema": "runtime_retire/2", "tag": tag, "dest": str(dest), "links": points,
            "tasks_naming_clone": tasks, "processes_naming_clone": procs,
            "shortcuts_naming_clone": shortcuts, "refused": bool(tasks or procs or shortcuts)}


def _rm_readonly(func, path, _exc) -> None:
    """git writes its objects read-only on Windows; clear the bit and retry once."""
    import stat  # noqa: PLC0415
    os.chmod(path, stat.S_IWRITE)
    func(path)


def execute_retire(plan: dict, *, out=print) -> int:
    dest = Path(plan["dest"])
    if plan["tasks_naming_clone"]:
        raise ReleaseRefused(f"scheduled task(s) still name {dest}: {', '.join(plan['tasks_naming_clone'])}; "
                             "roll them back first (the printed `schtasks /Create ... /XML` lines)")
    if plan["processes_naming_clone"]:
        raise ReleaseRefused(f"{len(plan['processes_naming_clone'])} running process(es) name {dest} "
                             f"(first: {plan['processes_naming_clone'][0][:160]}); wait for them")
    if plan["shortcuts_naming_clone"]:
        raise ReleaseRefused(f"shortcut(s) still start {dest}: {', '.join(plan['shortcuts_naming_clone'])}; "
                             "repoint them at the current release first (the desktop step a release prints)")
    for lk in plan["links"]:
        p = Path(lk["path"])
        if not _is_reparse_point(p):                       # re-verify at the moment of removal
            raise ReleaseRefused(f"{p} is no longer a reparse point; refusing to remove it")
        if lk["dir"]:
            os.rmdir(p)                 # RemoveDirectoryW on the reparse point: the LINK only
        else:
            os.unlink(p)
        out(f"   removed link {p} (-> {lk['target']})")
    left = reparse_points(dest)
    if left:
        raise ReleaseRefused(f"{len(left)} reparse point(s) remain in {dest} (first: {left[0]['path']}); "
                             "nothing was deleted beyond the links listed above")
    if sys.version_info >= (3, 12):
        shutil.rmtree(dest, onexc=_rm_readonly)
    else:                                                   # pragma: no cover
        shutil.rmtree(dest, onerror=_rm_readonly)
    out(f"RETIRED: {dest} ({len(plan['links'])} link(s) removed first, then the tree)")
    return 0


def render_retire(plan: dict, *, dry_run: bool) -> str:
    L = [f"# runtime retire {plan['tag']} -> {plan['dest']}" + ("   (DRY RUN: nothing was removed)" if dry_run else ""),
         f"# links, removed FIRST with os.rmdir/os.unlink on the link itself ({len(plan['links'])}):"]
    L += [f"#   {lk['path']} -> {lk['target']}" for lk in plan["links"]] or ["#   (none)"]
    L.append(f"# scheduled tasks naming the clone: {plan['tasks_naming_clone'] or 'none'}")
    L.append(f"# running processes naming the clone: {len(plan['processes_naming_clone'])}")
    L.append("# desktop, start menu and startup launchers naming the clone: "
             f"{plan['shortcuts_naming_clone'] or 'none'}")
    L.append("# verdict: " + ("REFUSED (see above)" if plan["refused"] else
                              "would remove the links, re-walk for reparse points, then delete the tree"))
    return "\n".join(L)


# ───────────────────────────────────────────────────── repoint plan (S70 P4, D7)
#
# WHY. On 2026-11-15 sixteen scheduled tasks ran from SEVEN release clones, because each
# release printed per-task lines that a human ran one at a time, so a fix reached only the
# tasks somebody remembered. `--repoint-plan <tag>` READS the scheduler, decides per task, and
# WRITES two PowerShell scripts (repoint + rollback) that the brain session runs. The tool
# itself never changes a task.

#: Every status a planned task can take, in precedence order (the first that applies wins).
REPOINT_STATUSES = ("REFUSED", "ON_TARGET", "ATTENDED", "SKIP_RUNNING", "REFUSED_MODULE_MISSING",
                    "REFUSED_CONFIG_DRIFT", "REPOINT")
#: The statuses that are a guard refusal: the plan still prints, the exit code is 3.
REPOINT_REFUSALS = frozenset({"REFUSED", "REFUSED_MODULE_MISSING", "REFUSED_CONFIG_DRIFT"})
CLONE_TOKEN_RE = re.compile(re.escape(RT.CLONE_PREFIX) + r"([A-Za-z0-9][A-Za-z0-9._-]{0,99})", re.I)
RECEIPT_STAMP_RE = r"\d{8}T\d{6}Z"
EXEC_ACTION = "MSFT_TaskExecAction"

#: Read-only. Every task (the total proves the scheduler answered), and the actions of the
#: ones whose action names a release clone.
_ENUM_PS = r"""
$ErrorActionPreference = 'Stop'
$all = @(Get-ScheduledTask)
$rows = @(foreach ($t in $all) {
  $acts = @($t.Actions | ForEach-Object { [pscustomobject]@{ kind = "$($_.CimClass.CimClassName)";
    execute = $_.Execute; arguments = $_.Arguments; working_directory = $_.WorkingDirectory } })
  $txt = ($acts | ForEach-Object { "$($_.execute) $($_.arguments) $($_.working_directory)" }) -join ' '
  if ($txt -match '__PREFIX__') {
    [pscustomobject]@{ name = $t.TaskName; path = $t.TaskPath; state = "$($t.State)"; actions = $acts } }
})
[pscustomobject]@{ total = $all.Count; tasks = $rows } | ConvertTo-Json -Depth 6 -Compress
"""


def _repoint_cfg() -> dict:
    """The declared attended lists and declarations (backend/config.py, one block)."""
    from backend import config as C  # noqa: PLC0415  (lazy: --tag / --retire stay stdlib-only)
    return {"tasks": tuple(C.RUNTIME_REPOINT_ATTENDED_TASKS), "flags": tuple(C.RUNTIME_REPOINT_ATTENDED_FLAGS),
            "modules": tuple(C.RUNTIME_REPOINT_ATTENDED_MODULES),
            "declarations": dict(C.RUNTIME_REPOINT_DECLARATIONS),
            "enum_timeout_s": float(C.RUNTIME_REPOINT_ENUM_TIMEOUT_S),
            "snapshot_timeout_s": float(C.RUNTIME_REPOINT_SNAPSHOT_TIMEOUT_S)}


def parse_enumeration(stdout: str) -> dict:
    """The enumeration's JSON, validated. A malformed answer is a refusal, never 'no tasks'."""
    try:
        js = json.loads(stdout or "")
    except ValueError as exc:
        raise ReleaseRefused(f"scheduler enumeration returned no JSON ({exc}): no plan from a failed read") from None
    if not isinstance(js, dict) or not isinstance(js.get("total"), int) or js["total"] <= 0:
        raise ReleaseRefused("scheduler enumeration reported no tasks at all: a scheduler always holds "
                             "some, so this is a failed read; no plan")
    rows = js.get("tasks")
    rows = [] if rows is None else (rows if isinstance(rows, list) else [rows])
    out = []
    for r in rows:
        if not isinstance(r, dict) or not r.get("name"):
            raise ReleaseRefused(f"scheduler enumeration row without a name: {str(r)[:120]}")
        acts = r.get("actions")
        acts = [] if acts is None else (acts if isinstance(acts, list) else [acts])
        out.append({"name": str(r["name"]), "path": str(r.get("path") or "\\"), "state": str(r.get("state")),
                    "actions": [{"kind": str(a.get("kind") or ""), "execute": a.get("execute") or "",
                                 "arguments": a.get("arguments") or "",
                                 "working_directory": a.get("working_directory") or ""} for a in acts]})
    return {"total": js["total"], "tasks": out}


def query_clone_tasks(timeout_s: float = 120.0) -> dict:
    """Read-only `Get-ScheduledTask`, no console window, bounded. Raises ReleaseRefused."""
    ps = _ENUM_PS.replace("__PREFIX__", RT.CLONE_PREFIX)
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout_s, creationflags=RT.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleaseRefused(f"scheduler enumeration failed ({type(exc).__name__}: {exc}): no plan") from None
    if r.returncode != 0:
        raise ReleaseRefused(f"scheduler enumeration rc {r.returncode}: {(r.stderr or '')[-300:]}; no plan")
    return parse_enumeration(r.stdout)


def split_args(s: str) -> list[str]:
    """Windows command-line tokens: whitespace separates, double quotes group (no escapes:
    every argument in these tasks is a plain path or word)."""
    out, cur, quoted, have = [], [], False, False
    for ch in s or "":
        if ch == '"':
            quoted, have = not quoted, True
        elif ch.isspace() and not quoted:
            if have:
                out.append("".join(cur))
            cur, have = [], False
        else:
            cur.append(ch)
            have = True
    if have:
        out.append("".join(cur))
    return out


def task_segments(arguments: str) -> Optional[list]:
    """The wrapper segments a task runs (`-I <clone>\\scripts\\runtime_task.py <wrapper args>`),
    or bare `-m module args` segments for a task that does not use the wrapper. None when the
    module cannot be determined."""
    toks = split_args(arguments)
    for i, tok in enumerate(toks):
        if tok.replace("/", "\\").lower().endswith("\\scripts\\runtime_task.py"):
            try:
                _opt, segs = RT.parse_argv(toks[i + 1:])
            except RT.Refused:
                return None
            return segs
    segs = [RT.Segment(module=toks[i + 1], args=toks[i + 2:]) for i, t in enumerate(toks)
            if t == "-m" and i + 1 < len(toks)]
    return segs[:1] or None


def module_in(clone: Path, module: str) -> bool:
    base = Path(clone).joinpath(*module.split("."))
    return (base.with_suffix(".py").is_file() or (base / "__init__.py").is_file()
            or (base / "__main__.py").is_file())


def _seg_value(seg, flag: str) -> Optional[str]:
    a = list(seg.args)
    for i, t in enumerate(a):
        if t == flag and i + 1 < len(a):
            return a[i + 1]
        if t.startswith(flag + "="):
            return t.split("=", 1)[1]
    return None


def attended_reasons(name: str, arguments: str, segs: Optional[list], rc: Mapping) -> list[str]:
    why = []
    if name in rc["tasks"]:
        why.append("declared attended task name")
    for tok in split_args(arguments):
        for f in rc["flags"]:
            if tok == f or tok.startswith(f + "="):
                why.append(f"argument {tok} (an order/execute flag)")
    for s in segs or ():
        for m in rc["modules"]:
            mod, _, sub = m.partition(" ")
            if s.module == mod and (not sub or (s.args[:1] == [sub])):
                why.append(f"runs {m}")
    return why


def _path_re(p: Path) -> re.Pattern:
    """`p` itself (either slash, any case), not a longer sibling name, and not the tail of a
    longer path. A ROOTED path keeps its leading separator(s) in the match: `/tmp/x` and
    `\\\\server\\share` start with an empty part, and dropping it made the match begin one
    character late, so a rewrite doubled the root (`//tmp/...`; CI on Linux, PR #156)."""
    parts = [re.escape(x) for x in re.split(r"[\\/]+", str(p).rstrip("\\/"))]
    return re.compile(r"(?<![A-Za-z0-9._-])" + r"[\\/]+".join(parts) + r"(?![A-Za-z0-9._-])", re.I)


def rewrite_clone_path(text: str, src: Path, dest: Path) -> str:
    """Replace the clone path `src` (and paths under it) with `dest`; nothing else changes."""
    return _path_re(src).sub(lambda _m: str(dest), text or "")


def clones_named(texts: Sequence[str], parent: Path) -> tuple[list[str], list[str]]:
    """(tags of clones under `parent` the texts name, clone-like names NOT under `parent`)."""
    tags, stray = [], []
    for text in texts:
        for m in CLONE_TOKEN_RE.finditer(text or ""):
            tag = m.group(1)
            if _path_re(parent / f"{RT.CLONE_PREFIX}{tag}").search(text):
                if tag.lower() not in [t.lower() for t in tags]:
                    tags.append(tag)
            elif m.group(0) not in stray:
                stray.append(m.group(0))
    return tags, stray


def find_preflight(tag: str, data_root: Path, dest: Path) -> dict:
    """The newest `runtime_switch/release_<tag>_<stamp>.json`; refuses unless it is PASS for `dest`."""
    d = Path(data_root) / "runtime_switch"
    pat = re.compile(rf"^release_{re.escape(tag)}_{RECEIPT_STAMP_RE}\.json$")
    found = sorted(p for p in (d.iterdir() if d.is_dir() else ()) if pat.match(p.name))
    if not found:
        raise ReleaseRefused(f"no preflight receipt {d}\\release_{tag}_<stamp>.json: the target clone was "
                             "never verified; release it with --tag first")
    newest = found[-1]
    try:
        rec = json.loads(newest.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ReleaseRefused(f"preflight receipt {newest} unreadable ({type(exc).__name__})") from None
    if rec.get("verdict") != "PASS":
        raise ReleaseRefused(f"preflight receipt {newest.name} verdict {rec.get('verdict')!r}, not PASS "
                             f"(failed: {rec.get('failed')})")
    if _norm(rec.get("checkout") or "") != _norm(str(dest)):
        raise ReleaseRefused(f"preflight receipt {newest.name} is for {rec.get('checkout')!r}, not {dest}")
    return {"path": str(newest), "utc": rec.get("utc"), "verdict": rec["verdict"],
            "warned": rec.get("warned") or []}


_SNAPSHOT_CODE = (
    "import json, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from backend.services.portfolio_intelligence import branch_population_rolling as R\n"
    "print('SNAPSHOT_FILE=' + R.__file__)\n"
    "print('SNAPSHOT=' + json.dumps(R.config_snapshot(), sort_keys=True))\n")


def target_config_snapshot(dest: Path, cfg: Mapping[str, str], timeout_s: float = 180.0) -> dict:
    """The TARGET clone's own `branch_population_rolling.config_snapshot()`, computed by the
    clone's code in a child (a read: it imports config and hashes the contract file)."""
    py = Path(cfg["AEGIS_VENV_DIR"]) / "Scripts" / "python.exe"
    env = {k: v for k, v in os.environ.items() if k not in RT.CLEARED}
    env["AEGIS_IGNORE_DOTENV"] = "1"
    try:
        r = subprocess.run([str(py), "-I", "-c", _SNAPSHOT_CODE, str(dest)], cwd=str(dest), env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_s,
                           creationflags=RT.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleaseRefused(f"config snapshot in {dest} failed ({type(exc).__name__})") from None
    lines = (r.stdout or "").splitlines()
    src = next((ln.split("=", 1)[1] for ln in lines if ln.startswith("SNAPSHOT_FILE=")), "")
    snap = next((ln.split("=", 1)[1] for ln in lines if ln.startswith("SNAPSHOT=")), None)
    if r.returncode != 0 or snap is None:
        raise ReleaseRefused(f"config snapshot in {dest} rc {r.returncode}: {(r.stderr or '')[-300:]}")
    if not _inside(Path(src), dest):
        raise ReleaseRefused(f"config snapshot imported {src}, not the target clone's own module")
    return json.loads(snap)


def declaration_drift(declared: Mapping, snap: Mapping) -> list[str]:
    """The keys whose value differs (the comparison `Store.declare` refuses on)."""
    return sorted(k for k in set(declared) | set(snap) if declared.get(k) != snap.get(k))


def plan_repoint(tag: str, cfg: Mapping[str, str], *, data_root: Optional[Path] = None,
                 backup_dir: Optional[Path] = None, now: Optional[datetime] = None,
                 enumerate_tasks: Optional[Callable[[], dict]] = None,
                 snapshot: Optional[Callable[[Path], dict]] = None,
                 repoint_cfg: Optional[Mapping] = None) -> dict:
    """Every task that names a release clone, and what a repoint to `tag` would do with it.
    Reads only. Raises ReleaseRefused for the WHOLE plan (target missing or not PASS, a failed
    enumeration); a per-task refusal is a row."""
    rc = dict(repoint_cfg or _repoint_cfg())
    dest = clone_dest(tag, cfg)
    parent = clone_parent(cfg)
    data_root = Path(data_root or cfg["AEGIS_LIVE_OPTIMUS"])
    if not dest.is_dir() or _is_reparse_point(dest):
        raise ReleaseRefused(f"target clone {dest} is not a directory: release {tag} first")
    if not (dest / "scripts" / "runtime_task.py").is_file():
        raise ReleaseRefused(f"target clone {dest} has no scripts\\runtime_task.py")
    preflight = find_preflight(tag, data_root, dest)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = Path(backup_dir or (data_root / "runtime_switch" / "task_xml_backup" / f"repoint_{tag}_{stamp}"))
    if production_clone_of(backup_dir, cfg) is not None:
        raise ReleaseRefused(f"backup dir {backup_dir} is inside a release clone; a retire would delete it")
    enum = (enumerate_tasks or (lambda: query_clone_tasks(rc["enum_timeout_s"])))()
    if not isinstance(enum, dict) or not isinstance(enum.get("total"), int) or enum["total"] <= 0:
        raise ReleaseRefused("scheduler enumeration failed or empty: no plan from a failed read")
    snap_cache: dict = {}

    def target_snapshot() -> dict:
        if "v" not in snap_cache:
            snap_cache["v"] = (snapshot or (lambda d: target_config_snapshot(d, cfg, rc["snapshot_timeout_s"])))(dest)
        return snap_cache["v"]

    rows = []
    for t in sorted(enum["tasks"], key=lambda r: (r["path"], r["name"])):
        acts = t["actions"]
        texts = [x for a in acts for x in (a["execute"], a["arguments"], a["working_directory"])]
        tags, stray = clones_named(texts, parent)
        row = {"task": t["name"], "path": t["path"], "state": t["state"], "from": tags[0] if len(tags) == 1 else tags,
               "to": tag, "reasons": [], "modules": [], "notes": []}
        found: list[str] = []
        if len(acts) != 1 or acts[0]["kind"] != EXEC_ACTION:
            found.append("REFUSED")
            row["reasons"].append(f"{len(acts)} action(s) of kind {[a['kind'] for a in acts]}; exactly one exec "
                                  "action is planned")
        if stray:
            found.append("REFUSED")
            row["reasons"].append(f"names a clone outside {parent}: {stray}")
        if len(tags) != 1:
            found.append("REFUSED")
            row["reasons"].append(f"names {len(tags)} release clones {tags}; exactly one is planned")
        a = acts[0] if acts else {"execute": "", "arguments": "", "working_directory": ""}
        segs = task_segments(a["arguments"])
        row["modules"] = [s.module for s in segs or ()]
        if len(tags) == 1 and tags[0].lower() == tag.lower():
            found.append("ON_TARGET")
        why = attended_reasons(t["name"], a["arguments"], segs, rc)
        if why:
            found.append("ATTENDED")
            row["reasons"] += why
        if t["state"] == "Running":
            found.append("SKIP_RUNNING")
            row["reasons"].append("Running now: never repoint a running task; plan again after it ends")
        if segs is None:
            found.append("REFUSED")
            row["reasons"].append("cannot determine the module this task runs")
        else:
            missing = [s.module for s in segs if not module_in(dest, s.module)]
            if missing:
                found.append("REFUSED_MODULE_MISSING")
                row["reasons"].append(f"module(s) {missing} not in {dest}")
            for s in segs:
                sub = rc["declarations"].get(s.module)
                if not sub:
                    continue
                out = _seg_value(s, "--out")
                droot = _seg_value(s, "--data-root") or str(data_root)
                decl_p = Path(out) / "declaration.json" if out else Path(droot) / sub / "declaration.json"
                row["declaration"] = str(decl_p)
                if not decl_p.is_file():
                    row["notes"].append(f"no {decl_p} yet: nothing is bound")
                    continue
                try:
                    declared = json.loads(decl_p.read_bytes()).get("config")
                    if not isinstance(declared, dict):
                        raise ValueError("no config object")
                    diff = declaration_drift(declared, target_snapshot())
                except (ReleaseRefused, OSError, ValueError) as exc:
                    found.append("REFUSED_CONFIG_DRIFT")
                    row["reasons"].append(f"cannot compare {decl_p} with the target's config ({exc})")
                    continue
                if diff:
                    found.append("REFUSED_CONFIG_DRIFT")
                    row["reasons"].append(f"target config differs from {decl_p.name} on {diff}: a born "
                                          "population would refuse every tick")
                else:
                    row["notes"].append(f"target config_snapshot() matches {decl_p}")
        found.append("REPOINT")
        row["status"] = next(s for s in REPOINT_STATUSES if s in found)
        if row["status"] == "REPOINT":
            src = parent / f"{RT.CLONE_PREFIX}{tags[0]}"
            row["current"] = dict(a)
            row["new"] = {k: rewrite_clone_path(a[k], src, dest) for k in ("execute", "arguments", "working_directory")}
        rows.append(row)
    # which clones would be left with no task (candidates for --retire; nothing is retired)
    still = {}
    for r in rows:
        for x in ([r["from"]] if isinstance(r["from"], str) else r["from"]):
            keep = r["status"] != "REPOINT"
            still[x.lower()] = still.get(x.lower(), False) or keep
    on_disk = sorted(p.name[len(RT.CLONE_PREFIX):] for p in parent.glob(f"{RT.CLONE_PREFIX}*") if p.is_dir())
    empty_after = [x for x in on_disk if x.lower() != tag.lower() and not still.get(x.lower(), False)]
    return {"schema": "runtime_repoint_plan/1", "tag": tag, "dest": str(dest), "generated_utc": stamp,
            "data_root": str(data_root), "preflight": preflight, "backup_dir": str(backup_dir),
            "scheduler_total_tasks": enum["total"], "tasks": rows,
            "attended_declared": {"tasks": list(rc["tasks"]), "flags": list(rc["flags"]),
                                  "modules": list(rc["modules"])},
            "clones_on_disk": on_disk,
            "clones_empty_after_plan": empty_after,
            "clones_with_no_task_now": [x for x in on_disk if x.lower() not in still and x.lower() != tag.lower()],
            "counts": {s: sum(1 for r in rows if r["status"] == s) for s in REPOINT_STATUSES}}


def repoint_script(plan: dict) -> str:
    """PowerShell: per REPOINT row, re-check (not Running, action unchanged since the plan, no
    backup already there), export the XML, set the new action ONLY, verify. Never run here."""
    q = ps_quote
    L = [f"# repoint_{plan['tag']}.ps1 -- generated {plan['generated_utc']} by "
         f"`python -m scripts.runtime_release --repoint-plan {plan['tag']}`; NOT run by the tool.",
         f"# Target clone {plan['dest']} (preflight {plan['preflight']['verdict']}: {plan['preflight']['path']}).",
         "# Only REPOINT rows are here: ATTENDED, Running, ON_TARGET and REFUSED tasks are not in this file.",
         "# Set-ScheduledTask -Action changes the action only: triggers, settings and principal stay.",
         f"# Undo: rollback_{plan['tag']}.ps1 (restores each task from the XML this script exports).",
         "$ErrorActionPreference = 'Stop'",
         f"$Backup = {q(plan['backup_dir'])}",
         "New-Item -ItemType Directory -Force -Path $Backup | Out-Null",
         "function Repoint-One([string]$Name, [string]$TaskPath, [string]$FromExe, [string]$FromArgs,",
         "                     [string]$FromWd, [string]$ToExe, [string]$ToArgs, [string]$ToWd) {",
         "  try {",
         "    $t = Get-ScheduledTask -TaskName $Name -TaskPath $TaskPath",
         "    if (\"$($t.State)\" -eq 'Running') { return \"SKIP $Name : Running now; never repoint a running task\" }",
         "    $acts = @($t.Actions)",
         "    if ($acts.Count -ne 1) { return \"SKIP $Name : $($acts.Count) actions; the plan saw one\" }",
         "    $a = $acts[0]",
         "    if (\"$($a.Execute)\" -cne $FromExe -or \"$($a.Arguments)\" -cne $FromArgs -or \"$($a.WorkingDirectory)\" -cne $FromWd) {",
         "      return \"SKIP $Name : its action changed since the plan; plan again\" }",
         "    $xmlPath = Join-Path $Backup ($Name + '.xml')",
         "    if (Test-Path -LiteralPath $xmlPath) { return \"SKIP $Name : $xmlPath exists (already run?); a backup is never overwritten\" }",
         "    $xml = Export-ScheduledTask -TaskName $Name -TaskPath $TaskPath",
         "    [IO.File]::WriteAllText($xmlPath, $xml, [Text.Encoding]::Unicode)",
         "    $new = New-ScheduledTaskAction -Execute $ToExe -Argument $ToArgs -WorkingDirectory $ToWd",
         "    Set-ScheduledTask -TaskName $Name -TaskPath $TaskPath -Action $new | Out-Null",
         "    $b = @((Get-ScheduledTask -TaskName $Name -TaskPath $TaskPath).Actions)[0]",
         "    if (\"$($b.Execute)\" -ceq $ToExe -and \"$($b.Arguments)\" -ceq $ToArgs -and \"$($b.WorkingDirectory)\" -ceq $ToWd) {",
         "      return \"OK $Name -> $ToWd (backup $xmlPath)\" }",
         "    return \"FAILED $Name : the action read back differs from the plan; run the rollback for it\"",
         "  } catch { return \"FAILED $Name : $($_.Exception.Message)\" }",
         "}",
         "$results = @()"]
    for r in plan["tasks"]:
        if r["status"] != "REPOINT":
            continue
        c, n = r["current"], r["new"]
        if not n["working_directory"]:
            raise ReleaseRefused(f"{r['task']}: an empty working directory is not planned")
        L.append(f"# {r['task']}: {r['from']} -> {r['to']}  ({', '.join(r['modules'])})")
        L.append("$results += Repoint-One " + " ".join(q(x) for x in (
            r["task"], r["path"], c["execute"], c["arguments"], c["working_directory"],
            n["execute"], n["arguments"], n["working_directory"])))
    L += ["$results | ForEach-Object { Write-Output $_ }",
          "if (@($results | Where-Object { $_ -like 'FAILED*' }).Count -gt 0) { exit 1 }",
          "exit 0", ""]
    return "\r\n".join(L)


def rollback_script(plan: dict) -> str:
    """PowerShell: per REPOINT row, re-register the task from the XML the repoint exported."""
    q = ps_quote
    L = [f"# rollback_{plan['tag']}.ps1 -- generated {plan['generated_utc']}; NOT run by the tool.",
         f"# Restores each task repoint_{plan['tag']}.ps1 changed, from the exact XML it exported.",
         "# A task with no backup was not changed and is left alone; a Running task is skipped.",
         "$ErrorActionPreference = 'Stop'",
         f"$Backup = {q(plan['backup_dir'])}",
         "function Restore-One([string]$Name, [string]$TaskPath) {",
         "  try {",
         "    $xmlPath = Join-Path $Backup ($Name + '.xml')",
         "    if (-not (Test-Path -LiteralPath $xmlPath)) { return \"SKIP $Name : no backup; the repoint did not change it\" }",
         "    $t = Get-ScheduledTask -TaskName $Name -TaskPath $TaskPath",
         "    if (\"$($t.State)\" -eq 'Running') { return \"SKIP $Name : Running now; run this again when it ends\" }",
         "    $xml = [IO.File]::ReadAllText($xmlPath)",
         "    Register-ScheduledTask -TaskName $Name -TaskPath $TaskPath -Xml $xml -Force | Out-Null",
         "    return \"RESTORED $Name from $xmlPath\"",
         "  } catch { return \"FAILED $Name : $($_.Exception.Message)\" }",
         "}",
         "$results = @()"]
    for r in plan["tasks"]:
        if r["status"] == "REPOINT":
            L.append(f"$results += Restore-One {q(r['task'])} {q(r['path'])}")
    L += ["$results | ForEach-Object { Write-Output $_ }",
          "if (@($results | Where-Object { $_ -like 'FAILED*' }).Count -gt 0) { exit 1 }",
          "exit 0", ""]
    return "\r\n".join(L)


def write_repoint(plan: dict, out: Path) -> dict:
    """Write the plan JSON and both scripts into `out`; never over an earlier plan's scripts
    (their rollback would lose its backup folder)."""
    out = Path(out)
    files = {"repoint": out / f"repoint_{plan['tag']}.ps1", "rollback": out / f"rollback_{plan['tag']}.ps1",
             "plan": out / f"repoint_plan_{plan['tag']}_{plan['generated_utc']}.json"}
    clash = [str(p) for p in files.values() if p.exists()]
    if clash:
        raise ReleaseRefused(f"{clash} already exist: a regenerated rollback would lose the earlier backup "
                             "folder; use a new --out")
    texts = {"repoint": repoint_script(plan), "rollback": rollback_script(plan)}
    out.mkdir(parents=True, exist_ok=True)
    for k in ("repoint", "rollback"):
        # UTF-8 with BOM: Windows PowerShell 5.1 reads a BOM-less file in the ANSI code page
        files[k].write_text(texts[k], encoding="utf-8-sig", newline="")
    plan = {**plan, "files": {k: str(v) for k, v in files.items()}}
    files["plan"].write_text(json.dumps(plan, indent=1, default=str), encoding="utf-8")
    return plan


def render_repoint(plan: dict) -> str:
    L = [f"# repoint plan -> {plan['tag']} ({plan['dest']}); READ-ONLY: no task was changed",
         f"# preflight {plan['preflight']['verdict']}: {plan['preflight']['path']}",
         f"# scheduler answered: {plan['scheduler_total_tasks']} tasks in all, {len(plan['tasks'])} name a release clone",
         f"# {'task':<26} {'state':<8} {'from':<11} {'status':<22} reason"]
    for r in plan["tasks"]:
        frm = r["from"] if isinstance(r["from"], str) else ",".join(r["from"]) or "-"
        why = "; ".join(r["reasons"] or r["notes"]) or ("-> " + r["to"] if r["status"] == "REPOINT" else "")
        L.append(f"  {r['task']:<26} {r['state']:<8} {frm:<11} {r['status']:<22} {why}")
    L.append("# counts: " + ", ".join(f"{k} {v}" for k, v in plan["counts"].items() if v))
    L.append(f"# attended (never scripted): {[r['task'] for r in plan['tasks'] if r['status'] == 'ATTENDED']}")
    L.append(f"# clones with no task after this plan (candidates for --retire; NOTHING retired; --retire "
             f"still checks processes and shortcuts): {plan['clones_empty_after_plan']}")
    L.append(f"#   of which already have no task today: {plan['clones_with_no_task_now']}")
    if plan.get("files"):
        L.append(f"# wrote {plan['files']['repoint']} and {plan['files']['rollback']} (not run), plan {plan['files']['plan']}")
    else:
        L.append("# no --out: nothing written")
    return "\n".join(L)


# ───────────────────────────────────────────────────────────── printing

def render(plan: dict, *, dry_run: bool) -> str:
    L = [f"# runtime release {plan['tag']} -> {plan['dest']}"
         + ("   (DRY RUN: nothing was created)" if dry_run else ""),
         f"# source object store: {plan['source']}   live data: {plan['live_optimus']}",
         f"# paper_nav database (exported as AEGIS_PI_DB_PATH, never linked): {plan['live_pi_db']}",
         f"# {DELETE_RULE}", ""]
    if dry_run:
        L.append("# steps a real run takes")
        for st in plan["steps"]:
            what = " ".join(st["argv"]) if "argv" in st else f"delete real dir {st['path']}"
            L.append(f"#   [{st['kind']}]{' (optional)' if st.get('optional') else ''} {what}")
        L.append("")
        L.append("# live state outside the optimus junction (runtime_preflight.LIVE_STATE)")
        for item in plan.get("live_state", []):
            L.append(f"#   {item['how']:8} {item['path']}: {item['why']}")
        L.append("")
    L += ["# ---- task repoints: run by the OWNER, one at a time, in this order. Before each: the task",
          "# has no running instance (Get-ScheduledTask State != Running, no PID in its lock file).",
          "# After each: runtime_preflight PASS, one supervised firing whose OWN receipt advances.",
          "# A row marked BLOCKED is printed commented out: decide its reason first.",
          f"New-Item -ItemType Directory -Force {ps_quote(plan['backup_dir'])} | Out-Null", ""]
    for t in plan["tasks"]:
        L.append(f"# [{t['order']}] {t['task']}  ({t['risk']})")
        L.append(f"#   accept: {t['acceptance']}")
        if t.get("note"):
            L.append(f"#   note: {t['note']}")
        L.append(t["backup"])
        if t["set"] and t.get("blocked"):
            L.append(f"# BLOCKED ({t['blocked']}): {t['set']}")
        elif t["set"]:
            L.append(t["set"])
        else:
            L.append(f"#   NO ACTION GENERATED: {t['manual']}")
        L.append(f"#   rollback: {t['rollback']}")
        L.append("")
    d = plan["desktop"]
    L += [f"# ---- desktop app (CH-22b): {DESKTOP_SHORTCUT} starts the app FROM a release clone, and this",
          "# clone has no node_modules and no frontend export yet. Close the app first. Until the",
          "# shortcut is repointed, --retire refuses for the clone it still names.",
          f"#   accept: {d['acceptance']}",
          *d["export"], d["backup"], d["set"], f"#   rollback: {d['rollback']}", ""]
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="runtime_release", description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--tag", help="release this tag to a new clone")
    g.add_argument("--retire", metavar="TAG", help="safely delete the clone of this tag")
    g.add_argument("--repoint-plan", metavar="TAG",
                   help="READ-ONLY: plan moving every task that names a release clone to this tag's clone; "
                        "with --out, write repoint_<tag>.ps1 + rollback_<tag>.ps1 (never run)")
    ap.add_argument("--out", type=Path, default=None, help="--repoint-plan: where the scripts and plan go")
    ap.add_argument("--data-root", type=Path, default=None,
                    help="--repoint-plan: the live data dir (default AEGIS_LIVE_OPTIMUS)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan; create/remove nothing")
    ap.add_argument("--source", type=Path, default=None,
                    help="where to clone from (default AEGIS_LIVE_ROOT's object store)")
    ap.add_argument("--repo-url", default=GITHUB_URL)
    ap.add_argument("--backup-dir", type=Path, default=None)
    ap.add_argument("--json", action="store_true", help="print the plan as JSON")
    a = ap.parse_args(argv)
    try:
        cfg = RT.read_config()
        if a.repoint_plan:
            plan = plan_repoint(a.repoint_plan, cfg, data_root=a.data_root, backup_dir=a.backup_dir)
            if a.out is not None:
                plan = write_repoint(plan, a.out)
            print(json.dumps(plan, indent=1, default=str) if a.json else render_repoint(plan))
            return 3 if any(r["status"] in REPOINT_REFUSALS for r in plan["tasks"]) else 0
        if a.retire:
            rp = plan_retire(a.retire, cfg)
            print(json.dumps(rp, indent=1) if a.json else render_retire(rp, dry_run=a.dry_run))
            if a.dry_run:
                return 2 if rp["refused"] else 0
            return execute_retire(rp)
        plan = build_plan(a.tag, cfg, source=a.source, repo_url=a.repo_url, backup_dir=a.backup_dir)
        if a.dry_run:
            r = _git(Path(plan["source"]), "rev-parse", "--verify", f"refs/tags/{a.tag}^{{commit}}")
            plan["tag_sha_in_source"] = r.stdout.strip() if r.returncode == 0 else None
            anc = _git(Path(plan["source"]), "merge-base", "--is-ancestor",
                       f"refs/tags/{a.tag}^{{commit}}", "refs/remotes/origin/main")
            plan["tag_on_origin_main"] = (anc.returncode == 0) if plan["tag_sha_in_source"] else None
            print(json.dumps(plan, indent=1) if a.json else render(plan, dry_run=True))
            if plan["tag_sha_in_source"] is None:
                print(f"# WARN: refs/tags/{a.tag} is not in {plan['source']} yet "
                      "(tag on main, then `git fetch origin --tags` there)", file=sys.stderr)
            elif not plan["tag_on_origin_main"]:
                print(f"# WARN: refs/tags/{a.tag} is not an ancestor of origin/main in {plan['source']}: "
                      "a real run refuses", file=sys.stderr)
            return 0
        execute(plan)
        print(json.dumps(plan, indent=1) if a.json else render(plan, dry_run=False))
        return 0
    except (ReleaseRefused, RT.Refused) as exc:
        print(f"RUNTIME RELEASE REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
