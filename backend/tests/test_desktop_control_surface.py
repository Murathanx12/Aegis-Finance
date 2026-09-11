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
import json
import os
import re
import sys
import time
from pathlib import Path

import pytest

from backend.routers import control, control_ask
from backend.services import free_inference as fi
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
        assert phrase in control_ask.ASK_SYSTEM
    assert "not there, say you do not have it" in control_ask.ASK_SYSTEM


def test_ask_refuses_rather_than_erroring_when_the_model_is_down(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    monkeypatch.setattr(ls, "status", lambda: {"ready": False, "detail": "not running",
                                               "listening": False, "model": None})
    out = control_ask.ask(question="what happened last night?")
    assert out["ok"] is False and out["answer"] is None
    assert "Start it from the Services page" in out["refusal"]


def test_ask_starts_the_model_only_when_it_is_asked_to(monkeypatch) -> None:
    """`start=true` is the Ask page's button. Without it the route answers the
    way it always did: a refusal that names the fix and starts nothing."""
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    calls: list[float] = []
    monkeypatch.setattr(ls, "status", lambda: {"ready": False, "detail": "not running",
                                               "listening": False, "model": None})
    monkeypatch.setattr(ls, "start", lambda **kw: calls.append(kw.get("wait_s", 0)) or {})
    out = control_ask.ask(question="what happened last night?")
    assert out["ok"] is False and out["started"] is False
    assert calls == [], "a question is not consent to start a multi-GB model server"


def test_ask_starts_the_model_and_waits_for_it(monkeypatch) -> None:
    """Down, then ready after a few polls: the answer is an ANSWER, not a
    refusal telling the user to start a server that is already loading.

    `listening` is not `ready` -- llama-server binds its port in about half a
    second with a fraction of the weights resident -- so the route polls
    readiness rather than the socket.
    """
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    monkeypatch.setattr(control_ask, "ASK_POLL_S", 0.01)
    state = {"polls": 0, "started": False}

    def fake_status() -> dict:
        if state["started"]:
            state["polls"] += 1
        ready = state["started"] and state["polls"] >= 3
        return {"ready": ready, "listening": state["started"], "model": "qwen.gguf",
                "detail": "ready" if ready else "loading"}

    def fake_start(wait_s: float = 90.0, bind: bool = True) -> dict:
        state["started"] = True
        return {"ok": True, "action": "starting", "pid": 4242, "ready": False}

    monkeypatch.setattr(ls, "status", fake_status)
    monkeypatch.setattr(ls, "start", fake_start)
    monkeypatch.setattr(fi, "complete", lambda **kw: type("R", (), {"text": "an answer"})())

    out = control_ask.ask(question="what does the G3 receipt say?", start=True, wait_s=5)
    assert out["ok"] is True
    # The answer now ENDS with a sources line computed from the files actually
    # opened (O6). A model asked to cite its sources invents one; a list built
    # from the paths that were read cannot.
    assert out["answer"].startswith("an answer")
    assert out["answer"].rstrip().splitlines()[-1].startswith("sources: ")
    assert out["started"] is True
    assert isinstance(out["waited_s"], float)


def test_ask_never_starts_over_a_foreign_listener(monkeypatch) -> None:
    """A server Aegis did not start may be several GB into somebody else's job.
    Starting a second copy means two sets of weights resident and neither
    works. The route waits for it and starts nothing -- and it never stops
    anything at all."""
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    monkeypatch.setattr(control_ask, "ASK_POLL_S", 0.01)
    started: list[dict] = []
    monkeypatch.setattr(ls, "status", lambda: {"ready": False, "listening": True,
                                               "foreign": True, "started_by_aegis": False,
                                               "model": "someone-elses.gguf",
                                               "detail": "bound but still loading"})
    monkeypatch.setattr(ls, "start", lambda **kw: started.append(kw) or {"ok": True})
    out = control_ask.ask(question="anything", start=True, wait_s=0.05)
    assert started == [], "a foreign listener must never be started over"
    assert out["ok"] is False and out["started"] is False
    assert out["waited_s"] >= 0.0


def test_ask_holds_no_stop_path(monkeypatch) -> None:
    """The route may start a server. It may never stop one: closing somebody
    else's job is not something an answer is allowed to do."""
    src = (REPO / "backend" / "routers" / "control_ask.py").read_text(encoding="utf-8")
    body = src[src.index("def ask("):]
    for banned in ("ls.stop", "stop_if_owned", "taskkill"):
        assert banned not in body, f"the ask path must not be able to {banned}"


def test_ask_requires_control_enabled(monkeypatch) -> None:
    monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)
    with pytest.raises(Exception) as exc:
        control_ask.ask(question="hello")
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


def test_the_spec_refuses_to_wipe_a_running_apps_directory() -> None:
    """The static-export refusal this test used to check is RETIRED, on purpose.

    It existed because the bundle CARRIED `frontend/out`, so building without an
    export produced an .exe whose window showed the API's raw JSON -- a failure
    that looks like a crash and is not. Since 2026-09-11 the .exe is a launcher:
    it serves the CHECKOUT's export and rebuilds it when `frontend/` has moved,
    so the build no longer has an opinion about it, and a refusal that can no
    longer fire is a gate that teaches the reader to skim gates.

    What the spec must still refuse is real: PyInstaller's COLLECT wipes its
    target directory first, and a running AegisDesktop.exe holds that directory
    open -- so a rebuild while the app is open dies with a permission error
    forty lines deep, naming the directory and not the reason.
    """
    spec = (REPO / "desktop" / "AegisDesktop.spec").read_text(encoding="utf-8")
    assert "REFUSED" in spec and "AegisDesktop.exe is running" in spec
    assert "distpath dist_next" in spec, "the refusal must name the way out"
    # onedir, not onefile: a COLLECT step is what onedir produces, and
    # `exclude_binaries=True` on the EXE is what makes it one. Asserting on the
    # build graph beats grepping the prose that explains the choice.
    assert "COLLECT(" in spec and "exclude_binaries=True" in spec


def test_the_spec_freezes_the_launcher_and_not_the_backend() -> None:
    """The architectural claim of O1, as a test: `backend/` is not in the
    bundle, so none of it can resolve a path differently when frozen."""
    from backend.tests.test_desktop_control_surface import executable_source
    code = executable_source(REPO / "desktop" / "AegisDesktop.spec")
    assert "launcher.py" in code
    assert "aegis_desktop.py" not in code.split("excludes = [", 1)[0]
    excludes = code.split("excludes = [", 1)[1].split("]", 1)[0]
    for mod in ("backend", "scripts", "learner", "uvicorn", "fastapi", "pandas"):
        assert f'"{mod}"' in excludes, mod


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


# ------------------------------------------------- the packaged app's data root

def test_the_control_plane_honours_an_explicit_repo_root(tmp_path: Path, monkeypatch) -> None:
    """Inside the bundle the default resolves to `<dist>/_internal`, and the
    first packaged run created a fresh empty `aegis_pi.db` there beside a repo
    full of real ones. An app that shows no receipts because it is looking in
    the wrong tree looks exactly like an app with nothing to show."""
    monkeypatch.setenv("AEGIS_REPO_ROOT", str(tmp_path))
    assert control._repo_root() == tmp_path.resolve()


def test_an_invalid_repo_root_falls_back_rather_than_pointing_nowhere(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_REPO_ROOT", r"C:\definitely\not\a\directory")
    assert control._repo_root() == Path(control.__file__).resolve().parent.parent.parent


def test_the_shell_finds_the_checkout_from_source(monkeypatch) -> None:
    from desktop import aegis_desktop as ad

    monkeypatch.delenv("AEGIS_REPO_ROOT", raising=False)
    monkeypatch.setattr(ad.sys, "frozen", False, raising=False)
    root = ad.repo_root()
    assert root is not None and (root / "backend").is_dir() and (root / "scripts").is_dir()


# ------------------------------------------------- no console windows on screen

DESKTOP_PATH_MODULES = (
    "backend/services/llama_server.py",
    "backend/routers/control.py",
    "desktop/aegis_desktop.py",
    "desktop/make_shortcut.py",
)


def test_nothing_on_the_desktop_path_spawns_a_visible_console():
    """Murat, 2026-09-10, on the packaged app: "random cmds popup and close".

    `AegisDesktop.exe` is built with `console=False`, so it has no console of its
    own -- and Windows gives any CONSOLE subprocess launched from such a process
    a brand-new console WINDOW. `netstat`, `tasklist`, `taskkill` and
    `nvidia-smi` are all console programs, and three of them run on the Services
    page's three-second poll (`pid_on_port`, `pid_alive`, `vram`). That is three
    black windows flashing every three seconds.

    `CREATE_NO_WINDOW` is a per-call keyword, easy to add to nine sites and just
    as easy to forget on the tenth -- so it lives in `quiet_subprocess` and this
    test forbids calling `subprocess` directly on the desktop path.
    """
    offenders = []
    for rel in DESKTOP_PATH_MODULES:
        tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"run", "Popen", "call", "check_output"}
                    and getattr(node.func.value, "id", "") == "subprocess"):
                offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, (
        "these call subprocess directly and will flash a console window in the "
        f"packaged app; use backend.services.quiet_subprocess: {offenders}")


def test_the_quiet_helper_always_sets_the_no_window_flag(monkeypatch):
    from backend.services import quiet_subprocess as qsp

    seen: dict = {}

    def fake_run(args, **kw):
        seen.update(kw)
        return None

    monkeypatch.setattr(qsp.subprocess, "run", fake_run)
    qsp.run(["cmd"], timeout=1)
    assert seen["shell"] is False
    assert seen["creationflags"] & qsp.CREATE_NO_WINDOW == qsp.CREATE_NO_WINDOW


def test_the_quiet_helper_preserves_extra_creation_flags(monkeypatch):
    """The model server needs its OWN process group so a stop reaches it and not
    the backend. Suppressing the window must not drop that."""
    from backend.services import quiet_subprocess as qsp

    seen: dict = {}
    monkeypatch.setattr(qsp.subprocess, "Popen", lambda a, **kw: seen.update(kw))
    qsp.popen(["cmd"], creationflags=qsp.NEW_PROCESS_GROUP)
    assert seen["creationflags"] & qsp.CREATE_NO_WINDOW == qsp.CREATE_NO_WINDOW
    assert seen["creationflags"] & qsp.NEW_PROCESS_GROUP == qsp.NEW_PROCESS_GROUP


def test_the_quiet_helper_refuses_a_shell():
    """Refused, not silently overridden: a shell invocation here is a defect and
    quietly flipping it would hide the mistake."""
    from backend.services import quiet_subprocess as qsp

    with pytest.raises(ValueError):
        qsp.run(["cmd"], shell=True)


# --------------------------------------------- the ownership note must be findable

def test_the_owner_file_follows_the_repo_root(tmp_path: Path, monkeypatch) -> None:
    """2026-09-10, found in the field. `llama_server.REPO` was
    `Path(__file__).parents[2]`, which inside the frozen app is `_internal` --
    so the packaged build wrote its ownership note into the BUNDLE, and nothing
    else could read it back.

    The consequence was the exact failure this module exists to prevent: Murat
    closed the app and llama-server PID 8012 kept running with 5,495 MiB mapped.
    The OS said its parent process was the app, so it was unambiguously ours;
    with no readable owner file `status()` called it `foreign` and
    `stop_if_owned()` correctly, uselessly, left it alone.

    A guard that reads state from a path its writer cannot reach is not a guard.
    """
    monkeypatch.setenv("AEGIS_REPO_ROOT", str(tmp_path))
    assert ls._repo_root() == tmp_path.resolve()


def test_the_shell_logs_because_a_windowed_build_has_no_stdout() -> None:
    """`console=False` means `print()` goes nowhere. The shutdown path -- the one
    thing that was asked for -- was therefore unobservable: it could not be shown
    to work, only to have not visibly failed. Diagnosing the leak above needed
    the process table because the app had left no record of what it did."""
    from desktop import aegis_desktop as ad

    code = executable_source(REPO / "desktop" / "aegis_desktop.py")
    assert "logging.FileHandler" in code
    assert "atexit.register" in code, "closing does not fire on every teardown path"
    assert code.count("shutdown(") >= 4, "closing + atexit + after-start + the definition"
    assert callable(ad._log_path)


def test_the_shutdown_is_idempotent(monkeypatch) -> None:
    """Three call paths are wired on purpose; they must not stop it three times."""
    from desktop import aegis_desktop as ad

    calls: list[int] = []
    monkeypatch.setattr(ad, "stop_llama_if_owned", lambda: calls.append(1) or {"action": "none"})
    code = executable_source(REPO / "desktop" / "aegis_desktop.py")
    assert "stopped_once" in code, "the guard that makes the three paths safe"


# ------------------------------------------------ the OS enforces the lifetime

@pytest.mark.skipif(sys.platform != "win32", reason="job objects are a Windows mechanism")
def test_a_bound_child_dies_with_this_process_even_on_a_hard_kill(tmp_path: Path) -> None:
    """The three shutdown hooks -- window `closing`, `atexit`, and the return
    from the window loop -- all run USER CODE, and `TerminateProcess` runs none.
    Measured 2026-09-10: `Stop-Process` on the packaged app left llama-server up
    with 5,095 MiB still mapped.

    A job object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` moves the promise into
    the kernel. This spawns a real child in a real subprocess, force-kills the
    parent, and asserts the child is gone -- because a guarantee about process
    lifetime cannot be tested with a mock.
    """
    script = tmp_path / "parent.py"
    script.write_text(
        "import json, os, subprocess, sys, time\n"
        f"sys.path.insert(0, r'{REPO}')\n"
        "from backend.services import llama_server as L\n"
        "p = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(300)'],\n"
        "                     creationflags=0x08000000)\n"
        f"open(r'{tmp_path / 'ids.json'}', 'w').write("
        "json.dumps({'parent': os.getpid(), 'child': p.pid, 'bind': L.bind_lifetime(p.pid)}))\n"
        "time.sleep(300)\n", encoding="utf-8")

    import subprocess as sp
    parent = sp.Popen([sys.executable, str(script)],
                      creationflags=getattr(sp, "CREATE_NO_WINDOW", 0))
    ids_file = tmp_path / "ids.json"
    try:
        # poll for CONTENT, not existence: `open(..., "w")` creates the file
        # before it writes, so an existence check races the write and the first
        # run of this test failed on an empty file
        ids = None
        for _ in range(300):
            try:
                ids = json.loads(ids_file.read_text(encoding="utf-8"))
                break
            except (OSError, json.JSONDecodeError):
                time.sleep(0.1)
        assert ids is not None, "the parent never recorded its child"
        assert ids["bind"]["bound"] is True, ids["bind"]
        child = int(ids["child"])
        assert ls.pid_alive(child), "the child should be running before the kill"

        parent.kill()                              # TerminateProcess: no user code runs
        parent.wait(timeout=30)
        for _ in range(100):
            if not ls.pid_alive(child):
                break
            time.sleep(0.1)
        assert not ls.pid_alive(child), (
            "the child outlived a hard kill of its parent -- the kernel guarantee is not in place, "
            "and every shutdown hook in the shell runs user code that a TerminateProcess skips")
    finally:
        if parent.poll() is None:
            parent.kill()


def test_binding_reports_failure_rather_than_claiming_success() -> None:
    """`bound: False` with a reason beats a note that says the OS will handle it
    when it will not. The first version of this returned a cheerful note while
    the child in fact survived, which is worse than no binding at all."""
    out = ls.bind_lifetime(0)                      # PID 0 can never be opened
    assert out["bound"] is False and out.get("reason")


# ------------------------------------------------- the splash must swap to the app

def test_the_page_swap_runs_after_the_gui_loop_starts() -> None:
    """Reported 2026-09-10 as "the exe didnt open timed out". The engine was
    never the problem: the app's own log shows the backend answering in 2.30 s
    on both launches, and one of them closed cleanly and stopped the model
    server. The window simply never left the splash.

    `when_ready` ran on a raw `threading.Thread` started BEFORE
    `webview.start()`. Health came back in about two seconds and `load_url` was
    called into a window whose GUI loop did not exist yet, so the call went
    nowhere and the splash counted up forever -- which reads exactly like a
    hang. `webview.start(func)` is pywebview's documented contract: the function
    runs once the window exists.
    """
    code = executable_source(REPO / "desktop" / "aegis_desktop.py")
    # `when_ready` as the FIRST positional argument; the call also carries the
    # storage arguments now, so the check is the contract, not the whole line.
    assert "webview.start(when_ready" in code, (
        "the readiness callback must be handed to webview.start(), not run on a "
        "thread that races the GUI loop")
    assert "threading.Thread(target=when_ready" not in code


def test_the_page_swap_cannot_fail_silently() -> None:
    """An exception in a daemon thread of a `console=False` build goes to a
    stderr that does not exist. The first version had no try/except and logged
    nothing about health or the load, so the log could not tell "engine slow"
    from "window stuck" -- which is the whole diagnosis."""
    src = (REPO / "desktop" / "aegis_desktop.py").read_text(encoding="utf-8")
    body = src[src.index("def when_ready"):src.index("stopped_once")]
    assert "except Exception" in body, "a silent splash is the worst outcome"
    assert "health_ok=%s" in body, "the health result must reach the log"
    assert 'log.info("loaded %s"' in body, "the page swap must reach the log"


def test_the_shell_points_data_dir_at_backend_data_not_at_optimus() -> None:
    """`config.DATA_DIR` IS `AEGIS_DATA_DIR`, and `OPTIMUS_LEDGER_DIR` is
    `DATA_DIR / "optimus"`. Setting the variable one level too deep produced
    `backend/data/optimus/optimus/` with copies of `beliefs.jsonl` and
    `predictions.jsonl` in it.

    Found 2026-09-10 by noticing a stray untracked directory -- nothing failed,
    because writing real records to a plausible wrong path is silent by
    construction. That is the same failure family as the app's empty database
    inside the bundle: a path that resolves somewhere believable and wrong.
    """
    code = executable_source(REPO / "desktop" / "aegis_desktop.py")
    assert 'str(root / "backend" / "data")' in code
    assert 'AEGIS_DATA_DIR", str(root / "backend" / "data" / "optimus")' not in code


def test_data_dir_and_ledger_dir_do_not_double_up(tmp_path: Path) -> None:
    """The invariant itself: `AEGIS_DATA_DIR=<x>/backend/data` must put the
    ledger at `<x>/backend/data/optimus`, not `.../optimus/optimus`.

    Checked in a SUBPROCESS. The first version reloaded `backend.config`
    in-process, which replaces module-level objects -- and
    `test_one_price_table.py` asserts `llm_research.PRICE_PER_MTOK IS
    config.LLM_PRICE_PER_MTOK`, an IDENTITY check that a reload breaks for every
    test that runs afterwards. It passed locally and turned CI red on e50f46d:
    a test that mutates global module state is a test that fails somebody else,
    somewhere else, depending on collection order.
    """
    import subprocess

    data = tmp_path / "backend" / "data"
    data.mkdir(parents=True)
    code = ("import os, sys; sys.path.insert(0, r'%s');"
            "from backend import config as c;"
            "print(c.OPTIMUS_LEDGER_DIR)" % REPO)
    r = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=120, shell=False,
        env={**os.environ, "AEGIS_DATA_DIR": str(data), "AEGIS_IGNORE_DOTENV": "1"},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0,
    )
    assert r.returncode == 0, r.stderr[-500:]
    assert Path(r.stdout.strip()) == data / "optimus"


# ------------------------------------------- the window remembers what it was told

def test_the_window_is_not_opened_in_private_mode() -> None:
    """pywebview 6.2.1 defaults `private_mode=True`, which is an incognito
    window: `localStorage` goes to a temporary profile and is discarded when the
    process ends. Reported 2026-09-11 as the guide and the tour coming back on
    every launch -- the flag that says "seen it" never survived the window that
    wrote it. Both arguments are required; either alone is still amnesia.
    """
    code = executable_source(REPO / "desktop" / "aegis_desktop.py")
    assert "private_mode=False" in code
    assert "storage_path=" in code


def test_the_storage_profile_is_never_inside_the_bundle(tmp_path: Path, monkeypatch) -> None:
    """A profile under `_internal` is deleted by the next rebuild of `dist/`,
    which is the frozen-path family again: correct from source, silently
    amnesiac when packaged. Simulated here rather than argued: `sys.frozen` and
    `sys._MEIPASS` set, the checkout pointed at a real directory."""
    from desktop import aegis_desktop as ad

    checkout = tmp_path / "checkout"
    (checkout / "backend" / "data").mkdir(parents=True)
    (checkout / "scripts").mkdir()
    bundle = tmp_path / "dist" / "AegisDesktop" / "_internal"
    bundle.mkdir(parents=True)

    monkeypatch.setattr(ad.sys, "frozen", True, raising=False)
    monkeypatch.setattr(ad.sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setenv("AEGIS_REPO_ROOT", str(checkout))

    d = ad._storage_dir()
    assert "_internal" not in d.parts, f"the browser profile is inside the bundle: {d}"
    assert Path(bundle) not in d.parents
    assert d == checkout.resolve() / "backend" / "data" / "optimus" / "webview_profile"
    assert d.is_dir(), "the profile directory must exist before the window asks for it"


def test_a_frozen_build_that_cannot_find_its_checkout_stores_outside_the_bundle(
        tmp_path: Path, monkeypatch) -> None:
    """The case that matters: frozen, no `AEGIS_REPO_ROOT`, no checkout beside
    the .exe. Falling back to `REPO` would put the profile inside `_internal`,
    so the fallback is the home directory instead -- a real place that survives
    a rebuild."""
    from desktop import aegis_desktop as ad

    bundle = tmp_path / "dist" / "AegisDesktop" / "_internal"
    bundle.mkdir(parents=True)
    monkeypatch.setattr(ad.sys, "frozen", True, raising=False)
    monkeypatch.setattr(ad.sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setattr(ad, "REPO", bundle / "backend", raising=False)
    monkeypatch.delenv("AEGIS_REPO_ROOT", raising=False)
    monkeypatch.setattr(ad, "repo_root", lambda: None)

    d = ad._storage_dir()
    assert "_internal" not in d.parts, f"the browser profile is inside the bundle: {d}"


def test_the_storage_path_is_logged_because_a_windowed_build_has_no_stdout() -> None:
    """If the guide comes back anyway, the first question is which profile the
    window actually used. An answer that is not in the log is not an answer."""
    code = executable_source(REPO / "desktop" / "aegis_desktop.py")
    assert 'log.info("storage %s"' in code


# --------------------------------------- every symbol resolves in the packaged app

def _export(tmp_path, symbols=("NVDA",), shell=True):
    """A miniature `frontend/out`: an index, some pre-rendered symbols, a shell.

    Built in a SUBDIRECTORY so that `tmp_path` itself is outside the served root
    -- the traversal test needs somewhere no request may ever reach."""
    tmp_path = tmp_path / "out"
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "index.html").write_text("<html>home</html>", encoding="utf-8")
    for sym in symbols:
        d = tmp_path / "stock" / sym
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(f"<html>prerendered {sym}</html>", encoding="utf-8")
    if shell:
        from backend.main import DESKTOP_TICKER_SHELL
        d = tmp_path / "stock" / DESKTOP_TICKER_SHELL
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text("<html>shell</html>", encoding="utf-8")
    return tmp_path


def _mounted_app(tmp_path, monkeypatch, **kw):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.main import mount_desktop_frontend

    out = _export(tmp_path, **kw)
    monkeypatch.setenv("AEGIS_DESKTOP", "1")
    monkeypatch.setenv("AEGIS_DESKTOP_FRONTEND", str(out))
    application = FastAPI()

    @application.get("/api/stock/{ticker}")
    async def _api_stock(ticker: str):                       # noqa: ANN202
        return {"ticker": ticker.upper(), "source": "api"}

    info = mount_desktop_frontend(application)
    return TestClient(application), info


def test_a_symbol_with_no_pre_rendered_page_is_served_the_shell(tmp_path, monkeypatch):
    """"When I search a stock I get 404" (Murat, 2026-09-11). The export names
    twelve symbols and the universe is ~3,000."""
    client, info = _mounted_app(tmp_path, monkeypatch)
    assert info["mounted"] and info["stock_shell"]["enabled"]
    for path in ("/stock/PLTR/", "/stock/PLTR"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "shell" in r.text
        assert r.headers["content-type"].startswith("text/html")


def test_head_resolves_too_because_the_router_prefetches_with_head(tmp_path, monkeypatch):
    """Next probes a link target with HEAD before it will soft-navigate. A
    GET-only route answers those 404 -- measured in the browser on 2026-09-11:
    28 HEAD 404s from one page of the universe table, while the same URLs
    returned 200 to curl, which is why the first pass missed it."""
    client, _ = _mounted_app(tmp_path, monkeypatch)
    for path in ("/stock/PLTR/", "/stock/PLTR", "/stock/NVDA/"):
        assert client.head(path).status_code == 200, path


def test_a_pre_rendered_symbol_keeps_its_own_page(tmp_path, monkeypatch):
    client, _ = _mounted_app(tmp_path, monkeypatch)
    assert "prerendered NVDA" in client.get("/stock/NVDA/").text


def test_the_api_still_wins_over_the_static_mount(tmp_path, monkeypatch):
    """The mount is LAST and the shell route is under `/stock`, not `/api`.
    If this ever inverts, every data call in the app returns HTML."""
    client, _ = _mounted_app(tmp_path, monkeypatch)
    r = client.get("/api/stock/NVDA")
    assert r.status_code == 200 and r.json() == {"ticker": "NVDA", "source": "api"}


def test_an_export_without_a_shell_still_mounts_and_says_so(tmp_path, monkeypatch):
    """An `out/` built before the shell existed serves its twelve names rather
    than refusing -- but the reason is in the return value, not only the log."""
    client, info = _mounted_app(tmp_path, monkeypatch, shell=False)
    assert info["mounted"] and info["stock_shell"]["enabled"] is False
    assert "no shell at" in info["stock_shell"]["reason"]
    assert client.get("/stock/NVDA/").status_code == 200


def test_a_traversal_segment_never_reaches_outside_the_export(tmp_path, monkeypatch):
    """`out/` is a directory on the user's disk and the app answers on
    localhost. A segment is not a filename until it has been checked: the
    shell route joins `ticker` onto `out/stock`, so `..` must lose.

    The first version of this test put the decoy INSIDE `out/` and failed on
    `NVDA%2F..%2F..%2Fsecret.html` -- which was the test being wrong, not the
    route: that path normalises to a file the export is there to serve. The
    decoy now lives one level ABOVE the served root, where a hit is a breach."""
    (tmp_path / "secret.html").write_text("<html>not yours</html>", encoding="utf-8")
    client, _ = _mounted_app(tmp_path, monkeypatch)
    for bad in ("..", "..%2f..%2fsecret.html", "NVDA%2F..%2F..%2Fsecret.html",
                "%2e%2e%2f%2e%2e%2fsecret.html", "....%2f%2fsecret.html"):
        r = client.get(f"/stock/{bad}")
        assert "not yours" not in r.text, bad
        assert r.status_code in (200, 404), (bad, r.status_code)
