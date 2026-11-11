"""CH-05 release planner (`scripts/runtime_release.py`): refusals, step order, task table.

Temp directories only; no real clone of the repository is made and no scheduled task is read
or touched. The one execute test (Windows) fakes every git call and makes real junctions
inside the temp directory.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import runtime_release as RR
from scripts import runtime_task as RT

WIN = sys.platform == "win32"

#: Every task in the ch05 switch plan (report section 6, rows 1-20) that this repo runs.
SWITCH_PLAN = {
    "AegisLocalRuntimeDigest", "AegisStraddleForward", "AegisContestRehearsal", "AegisContestDesk",
    "AegisBrainRefresh", "AegisAnalystPull", "AegisRawSecCollection", "AegisDailyPass",
    "AegisNNLabNightly", "AegisWorldDigest", "AegisHypLabNightly", "AegisIIF1NightLauncher",
    "AegisLocalBranchingPrivateGrade", "AegisAlerts", "AegisOwnerEventWarning",
    "AegisReaderSupervisor", "AegisTelegramAgent", "AegisDataCatalog", "AegisPublicAssetsWeekly",
    "AegisCatchUp", "AegisSimOwner", "AegisFleetManagerPreclose", "AegisFleetManagerOpen",
}


def cfg_for(tmp_path: Path) -> dict:
    live = tmp_path / "live"
    (live / "backend" / "data" / "optimus").mkdir(parents=True)
    (live / ".venv").mkdir()
    (live / "nn_lab" / ".venv").mkdir(parents=True)
    return {"AEGIS_LIVE_ROOT": str(live), "AEGIS_LIVE_OPTIMUS": str(live / "backend" / "data" / "optimus"),
            "AEGIS_DOTENV_PATH": str(live / ".env"), "AEGIS_VENV_DIR": str(live / ".venv"),
            "AEGIS_NN_LAB_VENV_DIR": str(live / "nn_lab" / ".venv"),
            "AEGIS_RUNTIME_ROOT": str(tmp_path / "aegis-runtime"),
            "AEGIS_PUBLICATION_ROOT": str(tmp_path / "pub")}


def test_the_table_covers_the_switch_plan_once_each():
    names = [t.name for t in RR.TASKS]
    assert len(names) == len(set(names))
    assert set(names) == SWITCH_PLAN


@pytest.mark.parametrize("spec", RR.TASKS, ids=lambda t: t.name)
def test_every_generated_action_parses_and_names_no_old_checkout(spec):
    if spec.wrapper is None:
        assert spec.manual, f"{spec.name}: no action and no reason"
        return
    _opt, segs = RT.parse_argv(list(spec.wrapper))
    assert segs and all(s.module.split(".")[0] in ("scripts", "nn_lab") for s in segs)
    joined = " ".join(spec.wrapper)
    assert "aegis-finance" not in joined and ":\\" not in joined   # paths are clone-relative


@pytest.mark.parametrize("tag", ["", "../x", "a/b", "a b", "-x", "x;y"])
def test_a_tag_that_is_not_a_plain_name_refuses(tmp_path, tag):
    with pytest.raises(RR.ReleaseRefused, match="plain name"):
        RR.build_plan(tag, cfg_for(tmp_path), here=tmp_path / "dev")


def test_an_existing_destination_refuses(tmp_path):
    cfg = cfg_for(tmp_path)
    (Path(cfg["AEGIS_RUNTIME_ROOT"]) / "runtime-20261115").mkdir(parents=True)
    with pytest.raises(RR.ReleaseRefused, match="already exists"):
        RR.build_plan("runtime-20261115", cfg, here=tmp_path / "dev")


def test_running_from_inside_a_production_clone_refuses(tmp_path):
    cfg = cfg_for(tmp_path)
    here = Path(cfg["AEGIS_RUNTIME_ROOT"]) / "runtime-20261101"
    here.mkdir(parents=True)
    with pytest.raises(RR.ReleaseRefused, match="production"):
        RR.build_plan("runtime-20261115", cfg, here=here)


def test_the_plan_checks_out_before_any_junction_and_preflights_last(tmp_path):
    cfg = cfg_for(tmp_path)
    plan = RR.build_plan("runtime-20261115", cfg, here=tmp_path / "dev")
    kinds = [s["kind"] for s in plan["steps"]]
    assert kinds == ["git", "git", "resolve_tag", "git", "verify_head", "remove_tracked_optimus",
                     "junction", "junction", "junction", "preflight"]
    checkout = plan["steps"][3]["argv"]
    assert checkout[-3:] == ["checkout", "--detach", "refs/tags/runtime-20261115"]
    dest = Path(plan["dest"])
    assert dest == Path(cfg["AEGIS_RUNTIME_ROOT"]) / "runtime-20261115"
    j = [(s["link"], s["target"]) for s in plan["steps"] if s["kind"] == "junction"]
    assert j[0] == (str(dest / "backend" / "data" / "optimus"), cfg["AEGIS_LIVE_OPTIMUS"])
    pf = plan["steps"][-1]["argv"]
    assert pf[2] == str(dest / "scripts" / "runtime_task.py") and "scripts.runtime_preflight" in pf
    assert pf[pf.index("--expect-commit") + 1] == "runtime-20261115"
    for e in ("scripts.alert_pass", "scripts.daily_pass", "nn_lab.nightly", "scripts.telegram_agent",
              "scripts.task_keeper", "scripts.fleet_manager_run"):
        assert e in plan["preflight_entries"]
    # nothing was created
    assert not dest.exists()


def test_no_git_verb_that_rewrites_a_working_tree_runs_except_the_one_fresh_checkout(tmp_path):
    plan = RR.build_plan("runtime-20261115", cfg_for(tmp_path), here=tmp_path / "dev")
    verbs = [s["argv"] for s in plan["steps"] if s["kind"] in ("git", "resolve_tag", "verify_head")]
    flat = " ".join(" ".join(a) for a in verbs)
    for bad in (" pull", " reset", " clean", " stash", " sparse-checkout", " merge"):
        assert bad not in flat
    assert flat.count(" checkout ") == 1


def test_task_lines_are_printed_never_run(tmp_path):
    cfg = cfg_for(tmp_path)
    plan = RR.build_plan("runtime-20261115", cfg, here=tmp_path / "dev")
    rows = {t["task"]: t for t in plan["tasks"]}
    alerts = rows["AegisAlerts"]
    assert alerts["backup"].startswith("schtasks /Query /TN 'AegisAlerts' /XML | Out-File -Encoding unicode")
    assert alerts["set"].startswith("Set-ScheduledTask -TaskName 'AegisAlerts' -Action (New-ScheduledTaskAction")
    assert str(Path(cfg["AEGIS_VENV_DIR"]) / "Scripts" / "pythonw.exe") in alerts["set"]
    assert alerts["argument"].endswith("--pythonw -m scripts.alert_pass")
    assert alerts["working_directory"] == plan["dest"]
    assert alerts["rollback"].startswith("schtasks /Create /TN 'AegisAlerts' /XML")
    assert rows["AegisDataCatalog"]["set"] is None and rows["AegisDataCatalog"]["manual"]
    text = RR.render(plan, dry_run=True)
    assert "DRY RUN" in text and "Set-ScheduledTask -TaskName 'AegisSimOwner'" in text


def test_remove_tracked_optimus_only_inside_the_new_clone(tmp_path):
    dest = tmp_path / "rt" / "tag"
    opt = dest / "backend" / "data" / "optimus"
    (opt / "sub").mkdir(parents=True)
    (opt / "sub" / "f.json").write_text("{}", encoding="utf-8")
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    with pytest.raises(RR.ReleaseRefused, match="not inside"):
        RR.remove_tracked_optimus(outside, dest)
    RR.remove_tracked_optimus(opt, dest)
    assert not opt.exists() and (dest / "backend" / "data").is_dir()


@pytest.mark.skipif(not WIN, reason="NTFS junctions")
def test_remove_tracked_optimus_never_deletes_through_a_junction(tmp_path):
    dest = tmp_path / "rt" / "tag"
    (dest / "backend" / "data").mkdir(parents=True)
    live = tmp_path / "live_optimus"
    live.mkdir()
    (live / "precious.jsonl").write_text("row\n", encoding="utf-8")
    link = dest / "backend" / "data" / "optimus"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(live)], check=True, capture_output=True)
    with pytest.raises(RR.ReleaseRefused, match="junction"):
        RR.remove_tracked_optimus(link, dest)
    assert (live / "precious.jsonl").exists()


@pytest.mark.skipif(not WIN, reason="NTFS junctions")
def test_execute_with_faked_git_makes_real_junctions(tmp_path):
    cfg = cfg_for(tmp_path)
    plan = RR.build_plan("runtime-20261115", cfg, here=tmp_path / "dev")
    dest = Path(plan["dest"])
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        if argv[0] == "cmd":                                   # mklink: real, inside tmp_path
            return subprocess.run(argv, **kw)
        if argv[:2] == ["git", "clone"]:
            (dest / "backend" / "data" / "optimus").mkdir(parents=True)
            (dest / "nn_lab").mkdir()
            (dest / "backend" / "data" / "optimus" / "tracked.json").write_text("{}", encoding="utf-8")
        out = "abc123\n" if ("rev-parse" in argv) else ""
        return subprocess.CompletedProcess(argv, 0, out, "")

    assert RR.execute(plan, run=run, out=lambda *_: None) == 0
    assert os.path.realpath(dest / "backend" / "data" / "optimus") == os.path.realpath(cfg["AEGIS_LIVE_OPTIMUS"])
    assert os.path.realpath(dest / ".venv") == os.path.realpath(cfg["AEGIS_VENV_DIR"])
    assert calls[-1][3] == "-m" and calls[-1][4] == "scripts.runtime_preflight"
    for link in (dest / "backend" / "data" / "optimus", dest / ".venv", dest / "nn_lab" / ".venv"):
        os.rmdir(link)                                         # junction only, never the target
    assert Path(cfg["AEGIS_LIVE_OPTIMUS"]).is_dir()


def test_execute_refuses_when_head_is_not_the_tag(tmp_path):
    cfg = cfg_for(tmp_path)
    plan = RR.build_plan("runtime-20261115", cfg, here=tmp_path / "dev")
    shas = iter(["tagsha\n", "othersha\n"])

    def run(argv, **kw):
        return subprocess.CompletedProcess(argv, 0, next(shas) if "rev-parse" in argv else "", "")

    with pytest.raises(RR.ReleaseRefused, match="not the tag"):
        RR.execute(plan, run=run, out=lambda *_: None)


def test_dry_run_main_creates_nothing(tmp_path, monkeypatch, capsys):
    cfg = cfg_for(tmp_path)
    for k, v in cfg.items():
        monkeypatch.setenv(k, v)
    rc = RR.main(["--tag", "runtime-20261115", "--dry-run", "--source", str(tmp_path / "no_repo")])
    out = capsys.readouterr()
    assert rc == 0
    assert "DRY RUN" in out.out and "Set-ScheduledTask -TaskName 'AegisTelegramAgent'" in out.out
    assert not (Path(cfg["AEGIS_RUNTIME_ROOT"]) / "runtime-20261115").exists()


def test_main_refusal_is_exit_2(tmp_path, monkeypatch, capsys):
    cfg = cfg_for(tmp_path)
    for k, v in cfg.items():
        monkeypatch.setenv(k, v)
    assert RR.main(["--tag", "../escape", "--dry-run"]) == 2
    assert "REFUSED" in capsys.readouterr().err
