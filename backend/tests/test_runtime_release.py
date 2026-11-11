"""CH-05 release planner (`scripts/runtime_release.py`): refusals, step order, task table.

Temp directories only; no real clone of the repository is made and no scheduled task is read
or touched. The one execute test (Windows) fakes every git call and makes real junctions
inside the temp directory.
"""
from __future__ import annotations

import os
import sqlite3
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
    """A live checkout at <tmp>/home/aegis-finance; clones go BESIDE it (<tmp>/home/aegis-runtime-<tag>)."""
    live = tmp_path / "home" / "aegis-finance"
    (live / "backend" / "data" / "optimus").mkdir(parents=True)
    (live / ".venv").mkdir()
    (live / "nn_lab" / ".venv").mkdir(parents=True)
    db = live / "backend" / "data" / "aegis_pi.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE paper_nav (portfolio_id TEXT, computed_at TEXT)")
    con.execute("INSERT INTO paper_nav VALUES ('b', '2026-11-10T23:58:02+00:00')")
    con.commit()
    con.close()
    return {"AEGIS_LIVE_ROOT": str(live), "AEGIS_LIVE_OPTIMUS": str(live / "backend" / "data" / "optimus"),
            "AEGIS_LIVE_PI_DB": str(db),
            "AEGIS_DOTENV_PATH": str(live / ".env"), "AEGIS_VENV_DIR": str(live / ".venv"),
            "AEGIS_NN_LAB_VENV_DIR": str(live / "nn_lab" / ".venv"),
            "AEGIS_PUBLICATION_ROOT": str(tmp_path / "home" / "aegis-finance-publication")}


def dest_of(cfg: dict, tag: str = "runtime-20261115") -> Path:
    return Path(cfg["AEGIS_LIVE_ROOT"]).parent / f"aegis-runtime-{tag}"


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
    dest_of(cfg).mkdir(parents=True)
    with pytest.raises(RR.ReleaseRefused, match="already exists"):
        RR.build_plan("runtime-20261115", cfg, here=tmp_path / "dev")


def test_running_from_inside_a_production_clone_refuses(tmp_path):
    cfg = cfg_for(tmp_path)
    here = dest_of(cfg, "runtime-20261101") / "scripts"
    here.mkdir(parents=True)
    with pytest.raises(RR.ReleaseRefused, match="production"):
        RR.build_plan("runtime-20261115", cfg, here=here)


def test_the_plan_checks_out_before_any_junction_and_preflights_last(tmp_path):
    cfg = cfg_for(tmp_path)
    plan = RR.build_plan("runtime-20261115", cfg, here=tmp_path / "dev")
    kinds = [s["kind"] for s in plan["steps"]]
    assert kinds == ["ancestry", "git", "git", "resolve_tag", "git", "verify_head", "remove_tracked_optimus",
                     "junction", "junction", "junction", "junction", "preflight"]
    checkout = plan["steps"][4]["argv"]
    assert checkout[-3:] == ["checkout", "--detach", "refs/tags/runtime-20261115"]
    dest = Path(plan["dest"])
    assert dest == dest_of(cfg)                                    # B2: beside the live checkout
    assert dest.parent == Path(cfg["AEGIS_LIVE_ROOT"]).parent
    j = [(s["link"], s["target"]) for s in plan["steps"] if s["kind"] == "junction"]
    assert j[0] == (str(dest / "backend" / "data" / "optimus"), cfg["AEGIS_LIVE_OPTIMUS"])
    pf = plan["steps"][-1]["argv"]
    assert pf[2] == str(dest / "scripts" / "runtime_task.py") and "scripts.runtime_preflight" in pf
    assert pf[pf.index("--expect-commit") + 1] == "runtime-20261115"
    assert pf[pf.index("--expect-pi-db") + 1] == cfg["AEGIS_LIVE_PI_DB"]       # B1
    assert pf[pf.index("--live-root") + 1] == cfg["AEGIS_LIVE_ROOT"]
    for e in ("scripts.alert_pass", "scripts.daily_pass", "nn_lab.nightly", "scripts.telegram_agent",
              "scripts.task_keeper", "scripts.fleet_manager_run"):
        assert e in plan["preflight_entries"]
    # nothing was created
    assert not dest.exists()


def test_no_git_verb_that_rewrites_a_working_tree_runs_except_the_one_fresh_checkout(tmp_path):
    plan = RR.build_plan("runtime-20261115", cfg_for(tmp_path), here=tmp_path / "dev")
    verbs = [s["argv"] for s in plan["steps"] if s["kind"] in ("git", "resolve_tag", "verify_head", "ancestry")]
    flat = " ".join(" ".join(a) for a in verbs)
    for bad in (" pull", " reset", " clean", " stash", " sparse-checkout", " merge "):
        assert bad not in flat
    assert flat.count(" merge-base --is-ancestor ") == 1          # a read (review 5 m7)
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
    assert not dest_of(cfg).exists()


def test_main_refusal_is_exit_2(tmp_path, monkeypatch, capsys):
    cfg = cfg_for(tmp_path)
    for k, v in cfg.items():
        monkeypatch.setenv(k, v)
    assert RR.main(["--tag", "../escape", "--dry-run"]) == 2
    assert "REFUSED" in capsys.readouterr().err


# ───────────────────────────────────────────────────────────── review 5 fixes

def test_the_committed_config_has_the_new_keys_and_no_runtime_root():
    cfg = RT.read_config(Path(RR.REPO) / "scripts" / "runtime_task.config", environ={})
    assert cfg["AEGIS_LIVE_PI_DB"].endswith("aegis_pi.db")
    assert "AEGIS_RUNTIME_ROOT" not in cfg                     # clones go beside the live root


def test_cfg_for_matches_the_config_keys(tmp_path):
    assert set(cfg_for(tmp_path)) == set(RT.CONFIG_KEYS)


def test_the_world_digest_row_runs_phase_auto():                 # M3
    row = next(t for t in RR.TASKS if t.name == "AegisWorldDigest")
    assert row.wrapper[-3:] == ("-m", "scripts.world_digest", "--phase-auto")
    assert "--hours" not in row.wrapper and row.wrapper[0] == "--pythonw"
    assert "every 30 minutes" in row.note and "IgnoreNew" in row.note


def test_only_the_tasks_that_start_long_lived_processes_allow_breakaway():   # M1
    allowed = {t.name for t in RR.TASKS if t.wrapper and "--allow-breakaway" in t.wrapper}
    assert allowed == {"AegisReaderSupervisor", "AegisSimOwner"}


def test_blocked_rows_are_printed_commented_out(tmp_path):
    plan = RR.build_plan("runtime-20261115", cfg_for(tmp_path), here=tmp_path / "dev")
    text = RR.render(plan, dry_run=True)
    for name in ("AegisDailyPass", "AegisAlerts", "AegisSimOwner"):
        lines = [ln for ln in text.splitlines() if f"Set-ScheduledTask -TaskName '{name}'" in ln]
        assert lines and all(ln.startswith("# BLOCKED (") for ln in lines), (name, lines)
    live = [ln for ln in text.splitlines() if ln.startswith("Set-ScheduledTask -TaskName 'AegisStraddleForward'")]
    assert len(live) == 1


def test_backups_live_in_the_shared_data_dir_never_in_a_clone(tmp_path):      # M4
    cfg = cfg_for(tmp_path)
    plan = RR.build_plan("runtime-20261115", cfg, here=tmp_path / "dev")
    bdir = Path(plan["backup_dir"])
    assert RR._inside(bdir, Path(cfg["AEGIS_LIVE_OPTIMUS"]))
    assert not RR._inside(bdir, Path(plan["dest"]))
    with pytest.raises(RR.ReleaseRefused, match="inside the clone"):
        RR.build_plan("runtime-20261115", cfg, here=tmp_path / "dev",
                      backup_dir=dest_of(cfg) / "task_xml_backup")


def test_the_plan_names_the_delete_rule(tmp_path):
    text = RR.render(RR.build_plan("runtime-20261115", cfg_for(tmp_path), here=tmp_path / "dev"), dry_run=True)
    assert "--retire" in text and "Remove-Item -Recurse" in text


def test_a_tag_not_on_origin_main_refuses(tmp_path):                           # m7
    plan = RR.build_plan("runtime-20261115", cfg_for(tmp_path), here=tmp_path / "dev")
    assert plan["steps"][0]["argv"][-4:] == ["merge-base", "--is-ancestor",
                                             "refs/tags/runtime-20261115^{commit}", "refs/remotes/origin/main"]

    def run(argv, **kw):
        return subprocess.CompletedProcess(argv, 1 if "merge-base" in argv else 0, "", "")

    with pytest.raises(RR.ReleaseRefused, match="not on origin/main"):
        RR.execute(plan, run=run, out=lambda *_: None)
    assert not Path(plan["dest"]).exists()


def test_a_refusal_after_a_junction_says_how_to_delete(tmp_path):
    plan = RR.build_plan("runtime-20261115", cfg_for(tmp_path), here=tmp_path / "dev")
    dest = Path(plan["dest"])

    def run(argv, **kw):
        if argv[:2] == ["git", "clone"]:
            (dest / "backend" / "data").mkdir(parents=True)
        if argv[0] == "cmd":                                    # the junction "fails"
            return subprocess.CompletedProcess(argv, 1, "", "mklink failed")
        return subprocess.CompletedProcess(argv, 0, "abc\n" if "rev-parse" in argv else "", "")

    with pytest.raises(RR.ReleaseRefused, match="--retire"):
        RR.execute(plan, run=run, out=lambda *_: None)


def test_tasks_naming_matches_the_clone_and_not_a_longer_sibling(tmp_path):
    dest = Path(r"C:\Users\mrthn\aegis-runtime-runtime-20261115") if WIN else Path("/h/aegis-runtime-r1")
    other = str(dest) + "2"
    xml = "\n".join([
        "<!-- \\AegisAlerts -->",                       # Windows paths compare case-insensitively
        f"<Arguments>-I \"{str(dest).upper() if WIN else str(dest)}{os.sep}scripts{os.sep}runtime_task.py\"</Arguments>",
        "<!-- \\AegisOther -->", f"<WorkingDirectory>{other}</WorkingDirectory>",
        "<!-- \\AegisSlash -->", f"<Command>{str(dest).replace(chr(92), '/')}/x</Command>",
    ])
    got = RR.tasks_naming(dest, xml)
    assert "\\AegisAlerts" in got and "\\AegisOther" not in got
    if WIN:
        assert "\\AegisSlash" in got


# ───────────────────────────────────────────────────────────── retire (M4)

def _junction(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if WIN:
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    else:
        os.symlink(target, link, target_is_directory=True)


def _fake_clone(tmp_path):
    """A clone beside the live checkout with REAL junctions into the live data, a nested
    one deep in the tree, a read-only file (git objects are read-only), and a canary."""
    cfg = cfg_for(tmp_path)
    live_opt = Path(cfg["AEGIS_LIVE_OPTIMUS"])
    (live_opt / "canary.jsonl").write_text("precious\n", encoding="utf-8")
    (Path(cfg["AEGIS_VENV_DIR"]) / "canary.txt").write_text("venv\n", encoding="utf-8")
    dest = dest_of(cfg)
    (dest / "scripts").mkdir(parents=True)
    (dest / "scripts" / "x.py").write_text("", encoding="utf-8")
    obj = dest / ".git" / "objects" / "ab" / "cdef"
    obj.parent.mkdir(parents=True)
    obj.write_bytes(b"x")
    os.chmod(obj, 0o444)
    _junction(dest / "backend" / "data" / "optimus", live_opt)
    _junction(dest / ".venv", Path(cfg["AEGIS_VENV_DIR"]))
    _junction(dest / "deep" / "er" / "link", live_opt)            # not one the release made
    return cfg, dest, live_opt


def _nothing():
    return []


def test_retire_removes_links_first_and_the_live_data_survives(tmp_path):
    cfg, dest, live_opt = _fake_clone(tmp_path)
    rp = RR.plan_retire("runtime-20261115", cfg, here=tmp_path / "dev", task_xml=lambda: "", processes=_nothing)
    assert len(rp["links"]) == 3 and not rp["refused"]
    assert RR.execute_retire(rp, out=lambda *_: None) == 0
    assert not dest.exists()
    assert (live_opt / "canary.jsonl").read_text(encoding="utf-8") == "precious\n"
    assert (Path(cfg["AEGIS_VENV_DIR"]) / "canary.txt").exists()


def test_retire_refuses_while_a_task_names_the_clone(tmp_path):
    cfg, dest, live_opt = _fake_clone(tmp_path)
    xml = f"<!-- \\AegisAlerts -->\n<WorkingDirectory>{dest}</WorkingDirectory>\n"
    rp = RR.plan_retire("runtime-20261115", cfg, here=tmp_path / "dev", task_xml=lambda: xml, processes=_nothing)
    assert rp["refused"] and rp["tasks_naming_clone"] == ["\\AegisAlerts"]
    with pytest.raises(RR.ReleaseRefused, match="scheduled task"):
        RR.execute_retire(rp, out=lambda *_: None)
    assert dest.is_dir() and (dest / "backend" / "data" / "optimus" / "canary.jsonl").exists()


def test_retire_refuses_while_a_process_runs_from_the_clone(tmp_path):
    cfg, dest, _ = _fake_clone(tmp_path)
    rp = RR.plan_retire("runtime-20261115", cfg, here=tmp_path / "dev", task_xml=lambda: "",
                        processes=lambda: [f"4242 pythonw.exe -I {dest}\\scripts\\runtime_task.py -m x"])
    with pytest.raises(RR.ReleaseRefused, match="running process"):
        RR.execute_retire(rp, out=lambda *_: None)
    assert dest.is_dir()


def test_retire_dry_run_removes_nothing(tmp_path, monkeypatch, capsys):
    cfg, dest, live_opt = _fake_clone(tmp_path)
    for k, v in cfg.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(RR, "query_task_xml", lambda: "")
    monkeypatch.setattr(RR, "query_process_cmdlines", _nothing)
    assert RR.main(["--retire", "runtime-20261115", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "optimus" in out
    assert dest.is_dir() and RR.reparse_points(dest)


def test_retire_refuses_a_path_that_is_not_a_plain_clone(tmp_path):
    cfg = cfg_for(tmp_path)
    with pytest.raises(RR.ReleaseRefused, match="does not exist"):
        RR.plan_retire("runtime-x", cfg, here=tmp_path / "dev", task_xml=lambda: "", processes=_nothing)
    with pytest.raises(RR.ReleaseRefused, match="plain name"):
        RR.plan_retire("../aegis-finance", cfg, here=tmp_path / "dev", task_xml=lambda: "", processes=_nothing)
    # the clone itself a junction (to the LIVE checkout): never followed
    _junction(dest_of(cfg, "linked"), Path(cfg["AEGIS_LIVE_ROOT"]))
    with pytest.raises(RR.ReleaseRefused, match="link or not a directory"):
        RR.plan_retire("linked", cfg, here=tmp_path / "dev", task_xml=lambda: "", processes=_nothing)
    os.rmdir(dest_of(cfg, "linked")) if WIN else os.unlink(dest_of(cfg, "linked"))
    assert (Path(cfg["AEGIS_LIVE_OPTIMUS"])).is_dir()


def test_retire_refuses_from_inside_the_clone(tmp_path):
    cfg, dest, _ = _fake_clone(tmp_path)
    with pytest.raises(RR.ReleaseRefused, match="inside"):
        RR.plan_retire("runtime-20261115", cfg, here=dest / "scripts", task_xml=lambda: "", processes=_nothing)
