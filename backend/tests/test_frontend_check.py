"""THREE FRONTEND BUILDS THAT DO NOT AGREE, AND THE ONE THE LAUNCHER RAN.

2026-09-11, commit `bf6de3e`: two board cards each defined `STATUS_TONE`. The
DESKTOP EXPORT tolerated the duplicate, the SITE build refused it, and CI went
red on the merge. The launcher's rebuild step ran only the export, so no local
run could have caught it -- it was structurally invisible until a push.

`scripts/frontend_check.py` runs all three (`tsc --noEmit`, `next build`,
`AEGIS_DESKTOP_BUILD=1 next build`) into ONE receipt with THREE exit codes, and
`desktop.launcher.maybe_frontend` calls it -- as a SUBPROCESS of the checkout's
interpreter, never an import, because anything the launcher imports is frozen
with it.

Nothing here runs a real build: the steps are stubbed, so the suite stays fast
and offline. What is pinned is the CONTRACT -- which builds run, in what order,
which of them decides whether the export is served, and what the receipt says
when a tool is missing.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from desktop import launcher
from scripts import frontend_check as FC

REPO = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------- the contract

def test_all_three_builds_are_declared_and_the_export_runs_last():
    """`frontend/out` must be left holding the DESKTOP export, so the site
    build may not run after it."""
    names = [s[0] for s in FC.STEPS]
    assert names == ["tsc", "site", "desktop"]
    envs = {s[0]: s[2] for s in FC.STEPS}
    assert envs["desktop"] == {"AEGIS_DESKTOP_BUILD": "1"}
    assert envs["tsc"] == {} and envs["site"] == {}
    assert ["tsc", "--noEmit"] == FC.STEPS[0][1]


def _stub(monkeypatch, codes: dict[str, int]):
    def fake(name, argv, extra_env, npx, cwd):
        rc = codes[name]
        return {"step": name, "cmd": f"npx {' '.join(argv)}", "returncode": rc,
                "seconds": 1.0, "ok": rc == 0, "tail": f"{name} said {rc}"}

    monkeypatch.setattr(FC, "run_step", fake)
    monkeypatch.setattr(shutil, "which", lambda _x: "npx")


def test_three_green_builds_are_one_green_receipt(tmp_path: Path, monkeypatch):
    _stub(monkeypatch, {"tsc": 0, "site": 0, "desktop": 0})
    out = tmp_path / "r.json"
    r = FC.check(root=REPO, receipt_path=out)
    assert r["ok"] is True and r["verdict"] == "GREEN"
    assert r["exit_codes"] == {"tsc": 0, "site": 0, "desktop": 0}
    assert json.loads(out.read_text(encoding="utf-8"))["exit_codes"] == r["exit_codes"]


def test_a_green_export_beside_a_red_site_build_is_still_RED(tmp_path: Path, monkeypatch):
    """The 09-11 shape, exactly. A receipt that reported only the export would
    have said GREEN."""
    _stub(monkeypatch, {"tsc": 2, "site": 1, "desktop": 0})
    r = FC.check(root=REPO, receipt_path=tmp_path / "r.json")
    assert r["ok"] is False and r["verdict"] == "RED"
    assert "tsc" in r["headline"] and "site" in r["headline"]
    assert r["exit_codes"]["desktop"] == 0


def test_main_exits_nonzero_on_a_red_build(tmp_path: Path, monkeypatch, capsys):
    _stub(monkeypatch, {"tsc": 0, "site": 1, "desktop": 0})
    assert FC.main(["--out", str(tmp_path / "r.json")]) == 1
    assert "RED" in capsys.readouterr().out


def test_a_skipped_step_is_recorded_not_counted_green(tmp_path: Path, monkeypatch):
    _stub(monkeypatch, {"tsc": 0, "desktop": 0})
    r = FC.check(root=REPO, skip=("site",), receipt_path=tmp_path / "r.json")
    assert r["ok"] is True
    assert r["exit_codes"]["site"] is None
    site = next(s for s in r["steps"] if s["step"] == "site")
    assert site["reason"] == "skipped" and site["ok"] is None


def test_no_node_is_CANNOT_DETERMINE_not_a_red_frontend(tmp_path: Path, monkeypatch):
    """A gate that reports red for its own missing tool teaches the reader to
    skim red lines."""
    monkeypatch.setattr(shutil, "which", lambda _x: None)
    r = FC.check(root=REPO, receipt_path=tmp_path / "r.json")
    assert r["ok"] is None and r["verdict"] == "CANNOT DETERMINE"
    assert "npx" in r["headline"]


def test_a_root_with_no_frontend_is_CANNOT_DETERMINE(tmp_path: Path):
    r = FC.check(root=tmp_path, receipt_path=tmp_path / "r.json")
    assert r["ok"] is None and "no frontend directory" in r["headline"]


def test_a_build_that_hangs_becomes_a_failed_step_not_a_hung_launch(tmp_path: Path,
                                                                   monkeypatch):
    import subprocess as sp

    def boom(*a, **k):
        raise sp.TimeoutExpired(cmd="npx", timeout=1.0)

    monkeypatch.setattr(FC.subprocess, "run", boom)
    row = FC.run_step("site", ["next", "build"], {}, "npx", tmp_path)
    assert row["ok"] is False and row["returncode"] is None and "timed out" in row["error"]


# --------------------------------------------------- the launcher's wiring

def test_the_launcher_runs_the_checker_as_a_child_never_as_an_import():
    """Anything the launcher imports is FROZEN with it, and a frozen module is
    how the path-resolution defect family started."""
    src = (REPO / "desktop" / "launcher.py").read_text(encoding="utf-8")
    assert "scripts.frontend_check" in src
    assert "from scripts" not in src and "import scripts" not in src


@pytest.fixture()
def checkout(tmp_path: Path):
    (tmp_path / "frontend" / "out").mkdir(parents=True)
    (tmp_path / "backend" / "data" / "optimus").mkdir(parents=True)
    return tmp_path


def _fake_checker(monkeypatch, codes: dict, root: Path):
    """Stand in for `python -m scripts.frontend_check`: write the receipt the
    launcher reads, and return 0 the way a subprocess would."""
    report = root / "backend" / "data" / "optimus" / "frontend_check.json"

    class _R:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(argv, **kwargs):
        assert "scripts.frontend_check" in argv, argv
        report.write_text(json.dumps({
            "exit_codes": codes,
            "verdict": "GREEN" if all(v == 0 for v in codes.values()) else "RED",
            "steps": [{"step": k, "ok": v == 0, "tail": f"{k}:{v}"} for k, v in codes.items()],
        }), encoding="utf-8")
        return _R()

    monkeypatch.setattr(launcher, "git_head", lambda _r: "head2")
    monkeypatch.setattr(shutil, "which", lambda _x: "npx")
    # the `git diff` that decides whether to rebuild goes through the same
    # `subprocess.run` we are stubbing, so say outright that frontend/ moved
    monkeypatch.setattr(launcher, "frontend_changed", lambda _r, _s: (True, "stub: changed"))
    monkeypatch.setattr(launcher.subprocess, "run", fake_run)


def test_the_launcher_records_all_three_codes(checkout: Path, monkeypatch):
    _fake_checker(monkeypatch, {"tsc": 0, "site": 0, "desktop": 0}, checkout)
    step = launcher.maybe_frontend(checkout, {"export_head": "head1"}, "py.exe")
    assert step["exit_codes"] == {"tsc": 0, "site": 0, "desktop": 0}
    assert step["reason"] == "rebuilt"
    assert step["export_head"] == "head2"


def test_a_red_site_build_is_reported_and_still_serves_the_new_export(checkout: Path,
                                                                     monkeypatch):
    """The export is what the app SERVES. A red type check must be loud and
    must not keep the window shut."""
    _fake_checker(monkeypatch, {"tsc": 1, "site": 1, "desktop": 0}, checkout)
    step = launcher.maybe_frontend(checkout, {"export_head": "head1"}, "py.exe")
    assert "RED" in step["reason"] and "tsc" in step["reason"] and "site" in step["reason"]
    assert step["export_head"] == "head2"          # the export succeeded, so serve it


def test_a_failed_export_keeps_the_last_good_one(checkout: Path, monkeypatch):
    _fake_checker(monkeypatch, {"tsc": 0, "site": 0, "desktop": 1}, checkout)
    step = launcher.maybe_frontend(checkout, {"export_head": "head1"}, "py.exe")
    assert step["export_head"] == "head1"
    assert "desktop export failed" in step["reason"]


def test_without_an_interpreter_the_launcher_still_builds_the_export(checkout: Path,
                                                                    monkeypatch):
    """A launcher must open the app. No interpreter resolved is not a reason to
    refuse -- it is a reason to do what it did before."""
    seen: list = []

    class _R:
        returncode = 0
        stdout = "built"
        stderr = ""

    def fake_run(argv, **kwargs):
        seen.append((argv, (kwargs.get("env") or {}).get("AEGIS_DESKTOP_BUILD")))
        return _R()

    monkeypatch.setattr(launcher, "git_head", lambda _r: "head2")
    monkeypatch.setattr(shutil, "which", lambda _x: "npx")
    monkeypatch.setattr(launcher, "frontend_changed", lambda _r, _s: (True, "stub: changed"))
    monkeypatch.setattr(launcher.subprocess, "run", fake_run)
    step = launcher.maybe_frontend(checkout, {"export_head": "head1"}, None)
    assert step["reason"] == "rebuilt" and step["export_head"] == "head2"
    assert seen and seen[0][1] == "1", "the fallback must still set AEGIS_DESKTOP_BUILD"
    assert "exit_codes" not in step


def test_the_step_decodes_utf8_rather_than_the_console_code_page(tmp_path: Path,
                                                                monkeypatch):
    """`next build` draws box characters. With `text=True` alone they are
    decoded with cp1252 on this machine, and the `UnicodeDecodeError` is raised
    inside subprocess's reader THREAD -- where it does not propagate. The build
    is reported correctly and its output vanishes, which is worst precisely
    when the build is red."""
    seen: dict = {}

    class _R:
        returncode = 1
        stdout = "\u2502 boxed \u2500 output"
        stderr = ""

    def fake(argv, **kwargs):
        seen.update(kwargs)
        return _R()

    monkeypatch.setattr(FC.subprocess, "run", fake)
    row = FC.run_step("site", ["next", "build"], {}, "npx", tmp_path)
    assert seen.get("encoding") == "utf-8" and seen.get("errors") == "replace"
    assert "boxed" in row["tail"]
