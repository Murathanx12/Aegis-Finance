"""S70 P4 (engineer D7): `runtime_release --repoint-plan <tag>`.

Temp directories and an INJECTED scheduler only: no test reads or touches a real scheduled task.
The one PowerShell run (Windows) executes the generated scripts with every scheduler cmdlet
name rewritten to a `Fake-*` function first, so even a broken mock cannot reach the scheduler.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

import pytest

from scripts import runtime_release as RR

WIN = sys.platform == "win32"
TAG, OLD, OLD2 = "t2", "t1", "t1b"
RC = {"tasks": ("AegisFleetManagerOpen", "AegisFleetManagerPreclose", "AegisSimOwner", "AegisDailyPass",
                "AegisTelegramAgent"),
      "flags": ("--live", "--execute"), "modules": ("scripts.fleet_manager_run", "scripts.task_keeper sim"),
      "declarations": {"scripts.rolling_cohorts": "rolling_cohorts"},
      "enum_timeout_s": 5.0, "snapshot_timeout_s": 5.0}
MODULES = ("scripts/task_keeper.py", "scripts/rolling_cohorts.py", "scripts/straddle_forward.py",
           "scripts/fleet_manager_run.py", "scripts/telegram_agent.py", "scripts/event_nodes.py")


def make_home(tmp_path: Path, *, verdict: str = "PASS", receipt: bool = True,
              modules: tuple[str, ...] = MODULES) -> dict:
    home = tmp_path / "home"
    live = home / "aegis-finance"
    opt = live / "backend" / "data" / "optimus"
    (opt / "runtime_switch").mkdir(parents=True)
    (live / ".venv" / "Scripts").mkdir(parents=True)
    for tag in (TAG, OLD, OLD2, "t0"):
        c = home / f"aegis-runtime-{tag}"
        (c / "scripts").mkdir(parents=True)
        (c / "scripts" / "runtime_task.py").write_text("# wrapper\n")
    for m in modules:
        p = home / f"aegis-runtime-{TAG}" / m
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# module\n")
    if receipt:
        (opt / "runtime_switch" / f"release_{TAG}_20000101T000000Z.json").write_text(json.dumps(
            {"verdict": verdict, "checkout": str(home / f"aegis-runtime-{TAG}"), "failed": [], "utc": "x"}))
    return {"AEGIS_LIVE_ROOT": str(live), "AEGIS_LIVE_OPTIMUS": str(opt),
            "AEGIS_LIVE_PI_DB": str(live / "backend" / "data" / "aegis_pi.db"),
            "AEGIS_DOTENV_PATH": str(live / ".env"), "AEGIS_VENV_DIR": str(live / ".venv"),
            "AEGIS_NN_LAB_VENV_DIR": str(live / "nn_lab" / ".venv"),
            "AEGIS_PUBLICATION_ROOT": str(home / "aegis-finance-publication")}


def clone(cfg: dict, tag: str) -> str:
    return str(Path(cfg["AEGIS_LIVE_ROOT"]).parent / f"aegis-runtime-{tag}")


def task(cfg: dict, name: str, wrapper: str, *, tag: str = OLD, state: str = "Ready") -> dict:
    c = clone(cfg, tag)
    return {"name": name, "path": "\\", "state": state, "actions": [{
        "kind": RR.EXEC_ACTION, "execute": str(Path(cfg["AEGIS_VENV_DIR"]) / "Scripts" / "pythonw.exe"),
        "arguments": f'-I "{c}\\scripts\\runtime_task.py" {wrapper}', "working_directory": c}]}


def plan(cfg: dict, tasks: list[dict], **kw) -> dict:
    kw.setdefault("snapshot", lambda d: {"K": 1})
    return RR.plan_repoint(TAG, cfg, enumerate_tasks=lambda: {"total": 200, "tasks": tasks},
                           repoint_cfg=RC, **kw)


def by_name(p: dict) -> dict:
    return {r["task"]: r for r in p["tasks"]}


def scripted(p: dict) -> tuple[str, str]:
    return RR.repoint_script(p), RR.rollback_script(p)


# ───────────────────────────────────────────────────────── per-task decisions

def test_a_running_task_is_skipped_and_never_scripted(tmp_path):
    cfg = make_home(tmp_path)
    p = plan(cfg, [task(cfg, "AegisLabNight", "--pythonw -m scripts.task_keeper brain", state="Running"),
                   task(cfg, "AegisStraddleForward", "--pythonw -m scripts.straddle_forward")])
    r = by_name(p)
    assert r["AegisLabNight"]["status"] == "SKIP_RUNNING"
    assert r["AegisStraddleForward"]["status"] == "REPOINT"
    rep, rb = scripted(p)
    assert "AegisLabNight" not in rep and "AegisLabNight" not in rb
    assert "'AegisStraddleForward'" in rep and "'AegisStraddleForward'" in rb
    # the script re-checks Running itself at run time
    assert "-eq 'Running'" in rep


@pytest.mark.parametrize("name", RC["tasks"])
def test_every_declared_attended_name_is_listed_and_excluded(tmp_path, name):
    cfg = make_home(tmp_path)
    p = plan(cfg, [task(cfg, name, "--pythonw -m scripts.event_nodes daily")])
    assert by_name(p)[name]["status"] == "ATTENDED"
    rep, rb = scripted(p)
    assert name not in rep and name not in rb


def test_an_order_flag_or_an_order_module_makes_any_task_attended(tmp_path):
    cfg = make_home(tmp_path)
    p = plan(cfg, [task(cfg, "AegisSomethingNew", "--pythonw -m scripts.event_nodes daily --live"),
                   task(cfg, "AegisOther", "--pythonw -m scripts.fleet_manager_run --pass open"),
                   task(cfg, "AegisSimTwo", "--allow-breakaway --pythonw -m scripts.task_keeper sim"),
                   task(cfg, "AegisKeeperBrain", "--pythonw -m scripts.task_keeper brain")])
    r = by_name(p)
    assert r["AegisSomethingNew"]["status"] == "ATTENDED"
    assert r["AegisOther"]["status"] == "ATTENDED"
    assert r["AegisSimTwo"]["status"] == "ATTENDED"
    assert r["AegisKeeperBrain"]["status"] == "REPOINT"     # `task_keeper` alone is not `task_keeper sim`
    rep, _ = scripted(p)
    for n in ("AegisSomethingNew", "AegisOther", "AegisSimTwo"):
        assert n not in rep


def test_attended_wins_over_running_and_both_reasons_print(tmp_path):
    cfg = make_home(tmp_path)
    p = plan(cfg, [task(cfg, "AegisTelegramAgent", "--pythonw -m scripts.telegram_agent --supervise",
                        state="Running")])
    r = by_name(p)["AegisTelegramAgent"]
    assert r["status"] == "ATTENDED"
    assert any("Running" in x for x in r["reasons"])


def test_the_default_attended_list_holds_the_briefed_five():
    rc = RR._repoint_cfg()
    assert set(RC["tasks"]) <= set(rc["tasks"])
    assert "--live" in rc["flags"]


def test_a_module_missing_in_the_target_refuses_that_task_only(tmp_path):
    cfg = make_home(tmp_path)
    p = plan(cfg, [task(cfg, "AegisGone", "--pythonw -m scripts.not_in_target"),
                   task(cfg, "AegisStraddleForward", "--pythonw -m scripts.straddle_forward")])
    r = by_name(p)
    assert r["AegisGone"]["status"] == "REFUSED_MODULE_MISSING"
    assert r["AegisStraddleForward"]["status"] == "REPOINT"
    assert "AegisGone" not in RR.repoint_script(p)


def test_a_task_already_on_the_target_is_not_scripted(tmp_path):
    cfg = make_home(tmp_path)
    p = plan(cfg, [task(cfg, "AegisSystemStatus", "--pythonw -m scripts.event_nodes", tag=TAG)])
    assert by_name(p)["AegisSystemStatus"]["status"] == "ON_TARGET"
    assert "AegisSystemStatus" not in RR.repoint_script(p)


def test_two_actions_or_two_clones_refuse(tmp_path):
    cfg = make_home(tmp_path)
    two = task(cfg, "AegisTwo", "--pythonw -m scripts.event_nodes")
    two["actions"].append(dict(two["actions"][0]))
    mixed = task(cfg, "AegisMixed", f"--pythonw -m scripts.event_nodes --out {clone(cfg, OLD2)}\\x")
    p = plan(cfg, [two, mixed])
    r = by_name(p)
    assert r["AegisTwo"]["status"] == "REFUSED"
    assert r["AegisMixed"]["status"] == "REFUSED"
    assert "AegisTwo" not in RR.repoint_script(p) and "AegisMixed" not in RR.repoint_script(p)


# ───────────────────────────────────────────────────────── declaration drift

def _declare(cfg: dict, config: dict) -> Path:
    d = Path(cfg["AEGIS_LIVE_OPTIMUS"]) / "rolling_cohorts"
    d.mkdir(parents=True)
    (d / "declaration.json").write_text(json.dumps({"config": config, "config_hash": "h"}))
    return d


def test_config_drift_against_a_running_declaration_refuses_that_task(tmp_path):
    cfg = make_home(tmp_path)
    _declare(cfg, {"ROLLING_COHORT_ALPHA": 0.05, "K": 1})
    t = task(cfg, "AegisRollingCohorts", f"--pythonw -m scripts.rolling_cohorts step --data-root {cfg['AEGIS_LIVE_OPTIMUS']}")
    p = plan(cfg, [t], snapshot=lambda d: {"ROLLING_COHORT_ALPHA": 0.10, "K": 1})
    r = by_name(p)["AegisRollingCohorts"]
    assert r["status"] == "REFUSED_CONFIG_DRIFT"
    assert "ROLLING_COHORT_ALPHA" in " ".join(r["reasons"])
    assert "AegisRollingCohorts" not in RR.repoint_script(p)


def test_a_matching_declaration_is_planned_and_says_so(tmp_path):
    cfg = make_home(tmp_path)
    _declare(cfg, {"K": 1})
    seen = []
    t = task(cfg, "AegisRollingCohorts", f"--pythonw -m scripts.rolling_cohorts step --data-root {cfg['AEGIS_LIVE_OPTIMUS']}")
    p = plan(cfg, [t], snapshot=lambda d: seen.append(d) or {"K": 1})
    r = by_name(p)["AegisRollingCohorts"]
    assert r["status"] == "REPOINT"
    assert any("matches" in n for n in r["notes"])
    assert seen == [Path(clone(cfg, TAG))]          # the TARGET clone's snapshot


def test_a_snapshot_that_cannot_be_computed_refuses_the_task_not_the_plan(tmp_path):
    cfg = make_home(tmp_path)
    _declare(cfg, {"K": 1})

    def boom(d):
        raise RR.ReleaseRefused("child rc 1")
    t = task(cfg, "AegisRollingCohorts", f"--pythonw -m scripts.rolling_cohorts step --data-root {cfg['AEGIS_LIVE_OPTIMUS']}")
    p = plan(cfg, [t, task(cfg, "AegisStraddleForward", "--pythonw -m scripts.straddle_forward")], snapshot=boom)
    r = by_name(p)
    assert r["AegisRollingCohorts"]["status"] == "REFUSED_CONFIG_DRIFT"
    assert r["AegisStraddleForward"]["status"] == "REPOINT"


def test_drift_is_the_same_comparison_the_rolling_store_refuses_on():
    assert RR.declaration_drift({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 0}) == ["b", "c"]
    assert RR.declaration_drift({"a": [1, 2]}, {"a": [1, 2]}) == []


# ───────────────────────────────────────────────────────── whole-plan refusals

def test_a_missing_preflight_receipt_refuses_the_whole_plan(tmp_path):
    cfg = make_home(tmp_path, receipt=False)
    with pytest.raises(RR.ReleaseRefused, match="no preflight receipt"):
        plan(cfg, [task(cfg, "AegisStraddleForward", "--pythonw -m scripts.straddle_forward")])


def test_a_failed_preflight_refuses_the_whole_plan(tmp_path):
    cfg = make_home(tmp_path, verdict="FAIL")
    with pytest.raises(RR.ReleaseRefused, match="not PASS"):
        plan(cfg, [])


def test_a_receipt_for_another_checkout_refuses(tmp_path):
    cfg = make_home(tmp_path)
    rs = Path(cfg["AEGIS_LIVE_OPTIMUS"]) / "runtime_switch"
    (rs / f"release_{TAG}_20990101T000000Z.json").write_text(json.dumps(
        {"verdict": "PASS", "checkout": clone(cfg, OLD)}))
    with pytest.raises(RR.ReleaseRefused, match="is for"):
        plan(cfg, [])


def test_a_missing_target_clone_refuses(tmp_path):
    cfg = make_home(tmp_path)
    with pytest.raises(RR.ReleaseRefused, match="not a directory"):
        RR.plan_repoint("nosuch", cfg, enumerate_tasks=lambda: {"total": 1, "tasks": []}, repoint_cfg=RC)


def test_an_enumeration_failure_refuses_never_an_empty_plan(tmp_path, monkeypatch):
    cfg = make_home(tmp_path)

    def boom():
        raise RR.ReleaseRefused("scheduler enumeration rc 1")
    with pytest.raises(RR.ReleaseRefused):
        RR.plan_repoint(TAG, cfg, enumerate_tasks=boom, repoint_cfg=RC)
    with pytest.raises(RR.ReleaseRefused, match="failed or empty"):
        RR.plan_repoint(TAG, cfg, enumerate_tasks=lambda: {"total": 0, "tasks": []}, repoint_cfg=RC)
    for bad in ("", "not json", "null", json.dumps({"total": 0, "tasks": []}), json.dumps({"tasks": []})):
        with pytest.raises(RR.ReleaseRefused):
            RR.parse_enumeration(bad)

    class R:
        returncode, stdout, stderr = 1, "", "Access denied"
    monkeypatch.setattr(RR.subprocess, "run", lambda *a, **k: R())
    with pytest.raises(RR.ReleaseRefused, match="rc 1"):
        RR.query_clone_tasks(1.0)

    def hang(*a, **k):
        raise subprocess.TimeoutExpired("powershell", 1.0)
    monkeypatch.setattr(RR.subprocess, "run", hang)
    with pytest.raises(RR.ReleaseRefused, match="TimeoutExpired"):
        RR.query_clone_tasks(1.0)


def test_the_enumeration_parser_accepts_a_single_row_and_no_rows():
    one = RR.parse_enumeration(json.dumps({"total": 5, "tasks": {"name": "A", "path": "\\", "state": "Ready",
                                                                 "actions": {"kind": RR.EXEC_ACTION,
                                                                             "execute": "x", "arguments": None}}}))
    assert one["tasks"][0]["actions"][0]["arguments"] == ""
    assert RR.parse_enumeration(json.dumps({"total": 5, "tasks": None}))["tasks"] == []


# ───────────────────────────────────────────────────────── the rewrite

def test_the_rewrite_touches_only_the_clone_path(tmp_path):
    cfg = make_home(tmp_path)
    live_data = cfg["AEGIS_LIVE_OPTIMUS"]
    t = task(cfg, "AegisEventNodes", f"-m scripts.event_nodes daily --data-root {live_data}")
    p = plan(cfg, [t])
    r = by_name(p)["AegisEventNodes"]
    new, cur = r["new"], r["current"]
    assert new["execute"] == cur["execute"]                        # the venv interpreter is not a clone
    assert new["working_directory"] == clone(cfg, TAG)
    assert new["arguments"] == cur["arguments"].replace(clone(cfg, OLD), clone(cfg, TAG))
    assert f"--data-root {live_data}" in new["arguments"]          # untouched
    assert clone(cfg, OLD) not in new["arguments"]


def test_the_rewrite_never_matches_a_longer_sibling_name_and_ignores_case(tmp_path):
    src, dest = Path(r"C:\h\aegis-runtime-t1"), Path(r"C:\h\aegis-runtime-t2")
    s = r'-I "C:\h\aegis-runtime-t1\scripts\runtime_task.py" --out C:\h\aegis-runtime-t1b\x --x c:/H/AEGIS-RUNTIME-T1/y'
    out = RR.rewrite_clone_path(s, src, dest)
    assert r"C:\h\aegis-runtime-t2\scripts\runtime_task.py" in out
    assert r"C:\h\aegis-runtime-t1b\x" in out                       # a different clone: untouched
    assert r"C:\h\aegis-runtime-t2/y" in out or r"C:\h\aegis-runtime-t2" in out.split("--x ")[1]


def test_a_rooted_path_keeps_exactly_one_root_and_a_longer_path_is_untouched():
    """Pure strings (both platforms): the 2026-11-15 Linux CI failure was `//tmp/...`, the
    pattern dropping the empty first part of a rooted path and matching one character late."""
    out = RR.rewrite_clone_path('-I "/tmp/h/aegis-runtime-t1/scripts/runtime_task.py" --wd /tmp/h/aegis-runtime-t1',
                                PurePosixPath("/tmp/h/aegis-runtime-t1"), PurePosixPath("/tmp/h/aegis-runtime-t2"))
    assert out == '-I "/tmp/h/aegis-runtime-t2/scripts/runtime_task.py" --wd /tmp/h/aegis-runtime-t2'
    # the same path as the TAIL of a longer one is a different path: untouched
    assert RR.rewrite_clone_path("--out /x/tmp/h/aegis-runtime-t1/y", PurePosixPath("/tmp/h/aegis-runtime-t1"),
                                 PurePosixPath("/tmp/h/aegis-runtime-t2")) == "--out /x/tmp/h/aegis-runtime-t1/y"
    # a UNC root (two leading separators) is matched whole and replaced once
    assert RR.rewrite_clone_path(r"\\srv\h\aegis-runtime-t1\s", r"\\srv\h\aegis-runtime-t1",
                                 r"\\srv\h\aegis-runtime-t2") == r"\\srv\h\aegis-runtime-t2\s"


# ───────────────────────────────────────────────────────── scripts, retire candidates, writing

def test_rollback_restores_from_exactly_the_backup_the_repoint_wrote(tmp_path):
    cfg = make_home(tmp_path)
    p = plan(cfg, [task(cfg, "AegisStraddleForward", "--pythonw -m scripts.straddle_forward"),
                   task(cfg, "AegisEventNodes", "-m scripts.event_nodes daily"),
                   task(cfg, "AegisSimOwner", "--allow-breakaway --pythonw -m scripts.task_keeper sim")])
    rep, rb = scripted(p)
    backup_line = f"$Backup = {RR.ps_quote(p['backup_dir'])}"
    assert backup_line in rep and backup_line in rb
    xml_expr = "$xmlPath = Join-Path $Backup ($Name + '.xml')"
    assert xml_expr in rep and xml_expr in rb
    assert "Export-ScheduledTask" in rep and "[IO.File]::WriteAllText($xmlPath, $xml" in rep
    assert "Register-ScheduledTask -TaskName $Name -TaskPath $TaskPath -Xml $xml -Force" in rb
    assert "[IO.File]::ReadAllText($xmlPath)" in rb
    rep_names = sorted(r["task"] for r in p["tasks"] if f"Repoint-One {RR.ps_quote(r['task'])}" in rep)
    rb_names = sorted(r["task"] for r in p["tasks"] if f"Restore-One {RR.ps_quote(r['task'])}" in rb)
    assert rep_names == rb_names == ["AegisEventNodes", "AegisStraddleForward"]
    # a second run never overwrites the first backup, so the rollback still restores the original
    assert "a backup is never overwritten" in rep
    # only the action changes: no trigger, settings or principal argument is passed
    assert "Set-ScheduledTask -TaskName $Name -TaskPath $TaskPath -Action $new" in rep
    for word in ("-Trigger", "-Settings", "-Principal", "-User", "-Password"):
        assert word not in rep


def test_clones_left_without_a_task_are_reported_not_retired(tmp_path):
    cfg = make_home(tmp_path)
    p = plan(cfg, [task(cfg, "AegisStraddleForward", "--pythonw -m scripts.straddle_forward", tag=OLD),
                   task(cfg, "AegisLabNight", "--pythonw -m scripts.event_nodes", tag=OLD2, state="Running")])
    assert p["clones_empty_after_plan"] == ["t0", OLD]              # OLD2 keeps its Running task
    assert p["clones_with_no_task_now"] == ["t0"]
    assert Path(clone(cfg, OLD)).is_dir() and Path(clone(cfg, "t0")).is_dir()


def test_write_repoint_writes_three_files_and_never_overwrites(tmp_path):
    cfg = make_home(tmp_path)
    p = plan(cfg, [task(cfg, "AegisStraddleForward", "--pythonw -m scripts.straddle_forward")])
    out = tmp_path / "out"
    w = RR.write_repoint(p, out)
    assert sorted(x.name for x in out.iterdir()) == sorted(Path(v).name for v in w["files"].values())
    assert (out / f"repoint_{TAG}.ps1").read_bytes().startswith(b"\xef\xbb\xbf")
    with pytest.raises(RR.ReleaseRefused, match="already exist"):
        RR.write_repoint(p, out)


def test_the_planner_itself_writes_nothing(tmp_path):
    cfg = make_home(tmp_path)
    before = sorted(str(x) for x in tmp_path.rglob("*"))
    plan(cfg, [task(cfg, "AegisStraddleForward", "--pythonw -m scripts.straddle_forward")])
    assert sorted(str(x) for x in tmp_path.rglob("*")) == before


def test_main_exit_codes(tmp_path, monkeypatch, capsys):
    cfg = make_home(tmp_path)
    monkeypatch.setattr(RR.RT, "read_config", lambda: cfg)
    rows = {"ok": [task(cfg, "AegisStraddleForward", "--pythonw -m scripts.straddle_forward")],
            "bad": [task(cfg, "AegisGone", "--pythonw -m scripts.not_in_target")]}
    for key, want in (("ok", 0), ("bad", 3)):
        monkeypatch.setattr(RR, "_repoint_cfg", lambda: RC)
        monkeypatch.setattr(RR, "query_clone_tasks", lambda *_a, _r=rows[key]: {"total": 9, "tasks": _r})
        assert RR.main(["--repoint-plan", TAG]) == want
    monkeypatch.setattr(RR, "query_clone_tasks", lambda *_a: (_ for _ in ()).throw(RR.ReleaseRefused("x")))
    assert RR.main(["--repoint-plan", TAG]) == 2
    assert "RUNTIME RELEASE REFUSED" in capsys.readouterr().err


# ───────────────────────────────────────────────────────── the generated PowerShell (Windows)

FAKES = r"""
$ErrorActionPreference = 'Stop'
$S = Get-Content -Raw -LiteralPath $env:FAKE_STATE | ConvertFrom-Json
function Save { $S | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $env:FAKE_STATE -Encoding UTF8 }
function Find($n) { $S.tasks | Where-Object { $_.name -eq $n } }
function Fake-GetScheduledTask { param($TaskName, $TaskPath) $t = Find $TaskName
  if (-not $t) { throw "no task $TaskName" }
  [pscustomobject]@{ State = $t.state; Actions = @([pscustomobject]@{ Execute = $t.execute;
    Arguments = $t.arguments; WorkingDirectory = $t.wd }) } }
function Fake-ExportScheduledTask { param($TaskName, $TaskPath) (Find $TaskName).xml }
function Fake-NewScheduledTaskAction { param($Execute, $Argument, $WorkingDirectory)
  [pscustomobject]@{ e = $Execute; a = $Argument; w = $WorkingDirectory } }
function Fake-SetScheduledTask { param($TaskName, $TaskPath, $Action) $t = Find $TaskName
  $t.execute = $Action.e; $t.arguments = $Action.a; $t.wd = $Action.w; $t.xml = 'CHANGED'; Save }
function Fake-RegisterScheduledTask { param($TaskName, $TaskPath, $Xml, [switch]$Force) $t = Find $TaskName
  $t.xml = $Xml; $t.execute = 'restored'; $S.registered += $TaskName; Save }
& $env:FAKE_SCRIPT
exit $LASTEXITCODE
"""
CMDLETS = ("Get-ScheduledTask", "Export-ScheduledTask", "New-ScheduledTaskAction", "Set-ScheduledTask",
           "Register-ScheduledTask")


def _run_faked(script: str, tmp: Path, state: Path, name: str) -> subprocess.CompletedProcess:
    for c in CMDLETS:                                    # no real cmdlet name survives
        script = script.replace(c, "Fake-" + c.replace("-", ""))
    assert not any(c in script for c in CMDLETS)
    sp = tmp / f"{name}.ps1"
    sp.write_text(script, encoding="utf-8-sig")
    hp = tmp / f"{name}_harness.ps1"
    hp.write_text(FAKES, encoding="utf-8-sig")
    import os
    env = {**os.environ, "FAKE_STATE": str(state), "FAKE_SCRIPT": str(sp)}
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                           "-File", str(hp)], capture_output=True, text=True, timeout=60, env=env)


@pytest.mark.skipif(not WIN, reason="Windows PowerShell")
def test_the_generated_scripts_parse():
    p = {"tag": TAG, "generated_utc": "x", "dest": "C:\\d", "backup_dir": "C:\\b'q", "preflight":
         {"verdict": "PASS", "path": "p"}, "tasks": [{"status": "REPOINT", "task": "FakeA", "path": "\\",
         "from": OLD, "to": TAG, "modules": ["m"],
         "current": {"execute": "e", "arguments": '-I "C:\\o\\x.py" a', "working_directory": "C:\\o"},
         "new": {"execute": "e", "arguments": '-I "C:\\n\\x.py" a', "working_directory": "C:\\n"}}]}
    for text in scripted(p):
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "[scriptblock]::Create([Console]::In.ReadToEnd()) | Out-Null"],
                           input=text, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr


@pytest.mark.skipif(not WIN, reason="Windows PowerShell")
def test_repoint_then_rollback_restores_the_exported_xml_end_to_end(tmp_path):
    cfg = make_home(tmp_path)
    tasks = [task(cfg, "FakeRepointA", "--pythonw -m scripts.straddle_forward"),
             task(cfg, "FakeRepointB", "-m scripts.event_nodes daily")]
    p = plan(cfg, tasks, backup_dir=tmp_path / "bk")
    state = tmp_path / "state.json"
    orig = {t["name"]: f"<Task name='{t['name']}'>original</Task>" for t in tasks}
    st = {"registered": [], "tasks": [{"name": t["name"], "state": "Ready", "execute": t["actions"][0]["execute"],
                                       "arguments": t["actions"][0]["arguments"],
                                       "wd": t["actions"][0]["working_directory"], "xml": orig[t["name"]]}
                                      for t in tasks]}
    # B is Running by the time the script runs: it must be skipped at run time
    st["tasks"][1]["state"] = "Running"
    state.write_text(json.dumps(st), encoding="utf-8")
    rep, rb = scripted(p)
    r = _run_faked(rep, tmp_path, state, "rep")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK FakeRepointA" in r.stdout and "SKIP FakeRepointB : Running" in r.stdout
    s = json.loads(state.read_text(encoding="utf-8-sig"))
    a = next(t for t in s["tasks"] if t["name"] == "FakeRepointA")
    assert a["wd"] == clone(cfg, TAG) and clone(cfg, TAG) in a["arguments"]
    assert (tmp_path / "bk" / "FakeRepointA.xml").read_text(encoding="utf-16") == orig["FakeRepointA"]
    assert not (tmp_path / "bk" / "FakeRepointB.xml").exists()
    # a second run refuses to overwrite the backup (A) and still skips B
    r2 = _run_faked(rep, tmp_path, state, "rep2")
    assert "SKIP FakeRepointA" in r2.stdout
    assert (tmp_path / "bk" / "FakeRepointA.xml").read_text(encoding="utf-16") == orig["FakeRepointA"]
    r3 = _run_faked(rb, tmp_path, state, "rb")
    assert r3.returncode == 0, r3.stdout + r3.stderr
    s = json.loads(state.read_text(encoding="utf-8-sig"))
    assert s["registered"] == ["FakeRepointA"]
    assert next(t for t in s["tasks"] if t["name"] == "FakeRepointA")["xml"] == orig["FakeRepointA"]
    assert "SKIP FakeRepointB : no backup" in r3.stdout
