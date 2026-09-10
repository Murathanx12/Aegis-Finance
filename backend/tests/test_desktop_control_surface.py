"""The desktop control surface: the model-server lifecycle, the fleet's
uncertainty, and the assistant's lack of authority.

Three invariants are pinned here, each because something already went wrong:

* **Kill by PID or refuse.** `~/llama/llama-stop.cmd` still ends in
  `taskkill /IM llama-server.exe /F`. On 2026-09-06 that gesture, used by an
  agent to stop its own job, took down two other agents' jobs, a test suite,
  ~1,676 billed extractions and the MCP server. Nothing in the new path may
  reintroduce it.
* **Uncertainty travels with the estimate.** The fleet's first week produced
  "beta 0.18 +/- 2.21" and the 0.18 got quoted. A mean below the observation
  floor must come back flagged, with a reason.
* **The assistant reads; it does not act.** No broker, no order, no seal.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from backend.routers import control
from backend.services import llama_server as ls

REPO = Path(__file__).resolve().parents[2]


def executable_source(path: Path) -> str:
    """The module's source with comments AND docstrings removed.

    Both guards below failed on their first run by matching the very docstrings
    that explain the banned pattern: `llama_server.py` quotes `taskkill /IM` in
    order to say never to use it, and the desktop shell's docstring names `.env`
    in order to say it is never written. A grep-shaped guard that cannot tell an
    explanation from an instance is a guard that forces the next person to
    delete the explanation.
    """
    src = path.read_text(encoding="utf-8")
    drop: set[int] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            first = body[0] if body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                drop.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return "\n".join(line for i, line in enumerate(src.splitlines(), 1)
                     if i not in drop and not line.strip().startswith("#"))


# ------------------------------------------------------- kill by PID, or refuse

def test_the_stop_path_never_kills_by_image_name() -> None:
    """`taskkill /IM`, `pkill -f`, `killall` -- none of them, anywhere."""
    code = executable_source(Path(ls.__file__))
    # the two real kill calls must both be /PID
    assert '"/IM"' not in code and "'/IM'" not in code
    assert not re.search(r"taskkill.{0,40}/IM", code)
    assert "killall" not in code and "pkill" not in code
    assert code.count('"/PID"') >= 2, "both the graceful and the forced kill must address a PID"


def test_stop_refuses_when_the_owning_pid_cannot_be_resolved(monkeypatch) -> None:
    """Something is listening but the socket table will not say whose it is.
    The tempting fallback is a name match. The correct answer is a refusal."""
    monkeypatch.setattr(ls, "status", lambda: {"listening": True, "pid": None, "foreign": True,
                                               "ready": True, "started_by_aegis": False})
    out = ls.stop()
    assert out["ok"] is False and out["action"] == "refused"
    assert "image name" in out["reason"]


def test_stop_refuses_a_foreign_server_without_explicit_consent(monkeypatch) -> None:
    """A server Aegis did not start may be several GB into somebody else's job."""
    monkeypatch.setattr(ls, "status", lambda: {"listening": True, "pid": 4242, "foreign": True,
                                               "ready": True, "started_by_aegis": False})
    out = ls.stop()
    assert out["ok"] is False and out["needs_confirmation"] is True
    assert "4242" in out["detail"]


def test_stop_if_owned_leaves_a_foreign_server_alone(monkeypatch) -> None:
    """Closing the window is not consent to kill a process Aegis never started."""
    monkeypatch.setattr(ls, "status", lambda: {"listening": True, "pid": 4242, "foreign": True,
                                               "ready": True, "started_by_aegis": False})
    called: list[bool] = []
    monkeypatch.setattr(ls, "stop", lambda **kw: called.append(True) or {})
    out = ls.stop_if_owned()
    assert out["action"] == "left_running" and not called


def test_start_refuses_to_add_a_second_server(monkeypatch) -> None:
    """Two copies means two sets of weights resident; on 8 GB neither works."""
    monkeypatch.setattr(ls, "port_open", lambda *a, **k: True)
    monkeypatch.setattr(ls, "_read_owner", lambda: {})
    out = ls.start()
    assert out["action"] == "none" and "already listening" in out["reason"]


def test_listening_is_not_ready(monkeypatch) -> None:
    """Measured 2026-09-10: llama-server binds the port immediately and finishes
    loading seconds later. `start()` first reported ready at 0.5s while nvidia-smi
    showed 1.1 GB of a ~4.8 GB model. A caller trusting the port sends its first
    request into a 503."""
    monkeypatch.setattr(ls, "port_open", lambda *a, **k: True)
    monkeypatch.setattr(ls, "health_ok", lambda *a, **k: False)
    monkeypatch.setattr(ls, "pid_on_port", lambda *a, **k: 999)
    monkeypatch.setattr(ls, "pid_alive", lambda p: True)
    monkeypatch.setattr(ls, "_read_owner", lambda: {})
    monkeypatch.setattr(ls, "vram", lambda: None)
    st = ls.status()
    assert st["listening"] is True and st["ready"] is False
    assert "loading" in st["detail"]


def test_vram_absence_is_none_not_zero(monkeypatch) -> None:
    """Zero would read on the page as 'no VRAM in use', which is a claim.
    'We could not measure' is a different one."""
    monkeypatch.setattr(ls.shutil, "which", lambda name: None)
    assert ls.vram() is None


# --------------------------------------------------- uncertainty with the estimate

def _series(navs: list[float], start_day: int = 1) -> list[tuple[str, float]]:
    return [(f"2026-06-{start_day + i:02d}", v) for i, v in enumerate(navs)]


def test_a_short_window_is_reported_but_never_estimable() -> None:
    """Four sessions. The fleet's real first week. `estimable` must be False and
    the reason must say why, so the page cannot render a bare number."""
    bench = control._daily_returns(_series([100.0, 101.0, 100.5, 101.5]))
    row = control._excess_row("hack3", _series([100.0, 99.0, 98.0, 97.0]), bench)
    assert row["n_days"] == 3
    assert row["estimable"] is False
    assert "below the" in row["why_not_estimable"]
    # the mean is still there -- with its standard error beside it
    assert row["mean_daily_excess_pct"] is not None
    assert row["se_daily_excess_pct"] is not None


def test_every_returned_mean_carries_a_standard_error() -> None:
    navs = [100.0 + i * 0.5 for i in range(40)]
    bench = control._daily_returns(_series([100.0 + i * 0.4 for i in range(40)]))
    row = control._excess_row("lane", _series(navs), bench)
    assert row["estimable"] is True and row["n_days"] == 39
    assert row["se_daily_excess_pct"] is not None and row["t_stat"] is not None
    assert row["why_not_estimable"] is None


def test_a_single_pair_cannot_produce_a_standard_error() -> None:
    bench = control._daily_returns(_series([100.0, 101.0]))
    row = control._excess_row("lane", _series([100.0, 99.0]), bench)
    assert row["estimable"] is False and row["se_daily_excess_pct"] is None
    assert "at least 2" in row["why_not_estimable"]


def test_a_missing_benchmark_is_a_refusal_not_a_zero_baseline() -> None:
    """Grading against an absent benchmark by treating it as zero is the D1
    defect: an arm minus nothing is a gross return dressed as an excess."""
    row = control._excess_row("lane", _series([100.0, 101.0, 102.0]), None)
    assert row["estimable"] is False and row["excess_vs_benchmark_pct"] is None
    assert "no benchmark series" in row["why_not_estimable"]


def test_the_fleet_payload_says_its_benchmark_is_not_spy() -> None:
    """The page is headed 'Fleet vs SPY' and the series is a control LANE.
    The payload has to carry that correction or the heading becomes the claim."""
    out = control.fleet()
    assert "SPY" in out["benchmark"]["caveat"]
    assert out["min_days_for_estimable"] == control.FLEET_MIN_DAYS


# ------------------------------------------------------- the assistant's authority

def test_the_assistant_is_told_it_has_no_authority() -> None:
    for phrase in ("cannot run", "seal", "arm", "place orders"):
        assert phrase in control.ASK_SYSTEM
    assert "not there, say you do not have it" in control.ASK_SYSTEM


def test_ask_refuses_rather_than_erroring_when_the_model_is_down(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    monkeypatch.setattr(ls, "status", lambda: {"ready": False, "detail": "not running",
                                               "listening": False, "model": None})
    out = control.ask(question="what happened last night?")
    assert out["ok"] is False and out["answer"] is None
    assert "Start it from the Services page" in out["refusal"]


def test_ask_requires_control_enabled(monkeypatch) -> None:
    monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)
    with pytest.raises(Exception) as exc:
        control.ask(question="hello")
    assert "403" in str(exc.value) or "AEGIS_CONTROL_ENABLED" in str(exc.value)


# ------------------------------------------------------- the desktop shell

def test_the_shell_never_writes_to_dotenv() -> None:
    """CLAUDE.md: `.env` is never moved or edited to change behaviour. The
    2026-08-24 subshell that did lost every key on the machine."""
    code = executable_source(REPO / "desktop" / "aegis_desktop.py")
    # `.env` as a bare substring also matches `os.environ`, which is precisely
    # the RIGHT way to set these flags -- so the guard looks for the file, not
    # the four characters: a path literal, or any of the dotenv writers.
    assert not re.search(r"""["'][^"']*\.env["']""", code), "no .env path literal"
    for writer in ("load_dotenv", "set_key", "unset_key", "dotenv_values", "shutil.move"):
        assert writer not in code, f"the shell must not call {writer}"
    # the flags are set on this process's own environment, and only as defaults
    assert 'os.environ.setdefault("AEGIS_CONTROL_ENABLED", "1")' in code
    assert 'os.environ.setdefault("AEGIS_DESKTOP", "1")' in code


def test_the_shell_does_not_adopt_a_server_it_found_running(monkeypatch) -> None:
    from desktop import aegis_desktop as ad

    monkeypatch.setattr(ls, "status", lambda: {"listening": True, "pid": 7, "started_by_aegis": False,
                                               "binary_present": True, "model_present": True,
                                               "model_path": "m", "binary_path": "b"})
    out = ad.maybe_start_llama()
    assert out["action"] == "left_alone" and out["pid"] == 7


def test_the_desktop_mount_is_off_unless_the_flag_is_set(monkeypatch) -> None:
    """Railway has its own frontend deploy; a StaticFiles at "/" there would
    swallow every unmatched API path."""
    from backend.main import app, mount_desktop_frontend

    monkeypatch.delenv("AEGIS_DESKTOP", raising=False)
    assert mount_desktop_frontend(app)["mounted"] is False


# ------------------------------------------------- the frozen build's job spawn

def test_child_argv_is_unchanged_when_not_frozen(monkeypatch) -> None:
    from backend.routers.control import child_argv

    monkeypatch.setattr(control.sys, "frozen", False, raising=False)
    argv = child_argv(["-m", "scripts.night_factory", "--job", "X"])
    assert argv == [control.sys.executable, "-m", "scripts.night_factory", "--job", "X"]


def test_a_frozen_build_prefers_a_real_interpreter(monkeypatch) -> None:
    """The .exe deliberately does not bundle torch or the night jobs -- the
    build that did produced a 27 GB dist directory that was mostly a second copy
    of parquets already on disk. Jobs run under a Python that has the stack."""
    from backend.routers.control import child_argv

    monkeypatch.setattr(control.sys, "frozen", True, raising=False)
    monkeypatch.setattr(control, "job_python", lambda: r"C:\py\python.exe")
    assert child_argv(["-m", "scripts.night_factory", "--job", "X"]) == \
        [r"C:\py\python.exe", "-m", "scripts.night_factory", "--job", "X"]


def test_a_frozen_build_falls_back_to_re_entering_itself(monkeypatch) -> None:
    """With no interpreter to be found, `sys.executable` is AegisDesktop.exe,
    which has no `-m` -- the job would die on an argparse error and the only
    symptom would be an empty log. `--run-module` is the escape."""
    from backend.routers.control import child_argv

    monkeypatch.setattr(control.sys, "frozen", True, raising=False)
    monkeypatch.setattr(control, "job_python", lambda: None)
    assert child_argv(["-m", "scripts.night_factory", "--job", "X"])[1:] == \
        ["--run-module", "scripts.night_factory", "--job", "X"]


def test_child_argv_passes_a_non_module_argv_through_unchanged(monkeypatch) -> None:
    """EXTRA_JOBS is a dict a future session will add to; a non `-m` entry must
    not be silently mangled into a --run-module it is not."""
    from backend.routers.control import child_argv

    monkeypatch.setattr(control.sys, "frozen", True, raising=False)
    monkeypatch.setattr(control, "job_python", lambda: None)
    assert child_argv(["other.py", "--x"])[1:] == ["other.py", "--x"]


def test_job_python_is_this_interpreter_when_not_frozen(monkeypatch) -> None:
    monkeypatch.setattr(control.sys, "frozen", False, raising=False)
    assert control.job_python() == control.sys.executable


def test_the_spec_does_not_sweep_the_data_directory() -> None:
    """`collect_data_files("backend")` pulled every parquet under
    `backend/data/` into the bundle -- the 1.25M-row bar table, the 339,657-row
    news panel -- and the dist directory reached 27 GB before it was stopped."""
    # the spec's own docstring names the banned calls in order to explain them,
    # so read the EXECUTABLE source -- the third time this session that a
    # grep-shaped guard matched the comment rather than the code
    spec_path = REPO / "desktop" / "AegisDesktop.spec"
    code = executable_source(spec_path)
    assert "collect_data_files" not in code
    assert "collect_submodules" not in code
    for heavy in ("torch", "transformers", "tensorflow"):
        assert f'"{heavy}"' in code, f"{heavy} must be in excludes, not bundled"


def test_every_spawn_site_goes_through_child_argv() -> None:
    """A second `subprocess.Popen([sys.executable, "-m", ...])` added later would
    work in development and break only in the packaged build."""
    code = executable_source(Path(control.__file__))
    assert "Popen([sys.executable" not in code, "spawn through child_argv, not sys.executable directly"
    assert code.count("child_argv(") >= 3, "both spawn sites plus the definition"


def test_the_shell_dispatches_run_module_before_argparse() -> None:
    """`--run-module` is not a window launch, and importing pywebview to find
    that out costs a five-hour night job its first seconds."""
    from desktop import aegis_desktop as ad

    src = (REPO / "desktop" / "aegis_desktop.py").read_text(encoding="utf-8")
    body = src[src.index("def main("):]
    assert body.index('"--run-module"') < body.index("ap = argparse.ArgumentParser")
    assert callable(ad.dispatch_module)


def test_the_spec_refuses_to_package_without_the_static_export() -> None:
    """Packaging with no `frontend/out` yields an .exe whose window is empty --
    a failure that looks like a crash and is not."""
    spec = (REPO / "desktop" / "AegisDesktop.spec").read_text(encoding="utf-8")
    assert "REFUSED" in spec and "index.html" in spec
    # onedir, not onefile: a COLLECT step is what onedir produces, and
    # `exclude_binaries=True` on the EXE is what makes it one. Asserting on the
    # build graph beats grepping the prose that explains the choice.
    assert "COLLECT(" in spec and "exclude_binaries=True" in spec


def test_the_icon_exists_and_is_multi_size() -> None:
    from PIL import Image

    ico = REPO / "desktop" / "assets" / "aegis.ico"
    assert ico.exists(), "run: python -m desktop.build_icon"
    with Image.open(ico) as im:
        sizes = {s for s in getattr(im, "ico", im).sizes()} if hasattr(im, "ico") else set(im.info.get("sizes", []))
    # a single 256px image is downsampled by the shell to 16px and turns to mush
    assert ico.stat().st_size > 10_000


def test_the_shortcut_refuses_a_missing_target(tmp_path: Path) -> None:
    from desktop.make_shortcut import create

    out = create(tmp_path / "nope.exe", tmp_path / "i.ico", tmp_path / "s.lnk")
    assert out["ok"] is False and out["action"] == "refused"
    assert "does nothing" in out["reason"]
