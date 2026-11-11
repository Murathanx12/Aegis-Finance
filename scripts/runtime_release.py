"""Make a production clone of a release tag, and print (never run) each task's repoint.

    python -m scripts.runtime_release --tag runtime-20261115 --dry-run   # the plan, nothing made
    python -m scripts.runtime_release --tag runtime-20261115             # clone + junctions + preflight
    python -m scripts.runtime_release --retire runtime-20261115 --dry-run   # what a retire removes
    python -m scripts.runtime_release --retire runtime-20261115             # the ONLY safe delete

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

`--retire <tag>` (review 5 M4) is the only supported way to delete a clone. Every clone holds
junctions to LIVE state (the ~82 GB data dir among them), and a recursive delete that follows a
junction deletes the live target. Retire refuses unless the clone is a real directory named
`aegis-runtime-<tag>` beside the live checkout, no scheduled task action names it (read-only
`schtasks /Query /XML`) and no running process names it in its command line. It then removes
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
            "tasks": [task_lines(t, dest=dest, cfg=cfg, backup_dir=backup_dir) for t in tasks]}


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


def plan_retire(tag: str, cfg: Mapping[str, str], *, here: Path = REPO,
                task_xml: Optional[Callable[[], str]] = None,
                processes: Optional[Callable[[], list[str]]] = None) -> dict:
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
    return {"schema": "runtime_retire/1", "tag": tag, "dest": str(dest), "links": points,
            "tasks_naming_clone": tasks, "processes_naming_clone": procs,
            "refused": bool(tasks or procs)}


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
    L.append("# verdict: " + ("REFUSED (see above)" if plan["refused"] else
                              "would remove the links, re-walk for reparse points, then delete the tree"))
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
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="runtime_release", description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--tag", help="release this tag to a new clone")
    g.add_argument("--retire", metavar="TAG", help="safely delete the clone of this tag")
    ap.add_argument("--dry-run", action="store_true", help="print the plan; create/remove nothing")
    ap.add_argument("--source", type=Path, default=None,
                    help="where to clone from (default AEGIS_LIVE_ROOT's object store)")
    ap.add_argument("--repo-url", default=GITHUB_URL)
    ap.add_argument("--backup-dir", type=Path, default=None)
    ap.add_argument("--json", action="store_true", help="print the plan as JSON")
    a = ap.parse_args(argv)
    try:
        cfg = RT.read_config()
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
