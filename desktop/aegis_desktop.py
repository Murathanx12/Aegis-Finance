"""Aegis Desktop -- one window, one click, one process.

    python -m desktop.aegis_desktop            # run from the repo
    AegisDesktop.exe                           # the frozen build

What it does, in order:

1. picks a free localhost port and starts uvicorn on it IN THIS PROCESS,
   with `AEGIS_CONTROL_ENABLED=1` and `AEGIS_DESKTOP=1` set on **this process's
   own environment only** -- never written to `.env`. (CLAUDE.md: `.env` is
   never moved or edited to change behaviour; the 2026-08-24 subshell that did
   lost every key on the machine.)
2. opens a pywebview window on a splash page and swaps to the app as soon as
   `/api/health` answers, so a cold start that imports pandas, lightgbm and
   pyarrow does not look like a hang;
3. starts `llama-server` **only if nothing is listening on its port**, and
   records that Aegis owns it;
4. on close, stops the model server **if Aegis started it**, by PID.

Point 4 is Murat's ask of 2026-09-10, and point 3 is the reason it is
conditional: a server that was already up may be mid-job holding several GB, and
closing a window is not consent to kill somebody else's work. The Services page
has an explicit button for that case.

This shell places no orders and holds no book. It starts a web server and a
model server, and it stops the one it started.
"""

from __future__ import annotations

import argparse
import atexit
import json
import logging
import os
import socket
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SPLASH = """<!doctype html><meta charset="utf-8"><title>Aegis</title>
<style>
 :root{color-scheme:dark}
 body{margin:0;height:100vh;display:flex;flex-direction:column;align-items:center;
      justify-content:center;background:#0b0d10;color:#e6e8ea;
      font:14px/1.5 -apple-system,Segoe UI,system-ui,sans-serif}
 h1{font-weight:600;font-size:20px;letter-spacing:.02em;margin:0 0 6px}
 p{color:#8b949e;margin:2px 0}
 .bar{width:260px;height:2px;background:#21262d;border-radius:2px;overflow:hidden;margin-top:18px}
 .bar i{display:block;height:100%;width:38%;background:#4493f8;animation:s 1.1s ease-in-out infinite}
 @keyframes s{0%{transform:translateX(-100%)}100%{transform:translateX(360%)}}
 code{color:#6e7681}
</style>
<h1>Aegis</h1><p id="m">starting the engine…</p>
<p><code id="t"></code></p><div class="bar"><i></i></div>
<script>
 const t0=Date.now();
 setInterval(()=>{document.getElementById('t').textContent=((Date.now()-t0)/1000).toFixed(1)+'s';},100);
 setTimeout(()=>{document.getElementById('m').textContent=
   'still loading — the first start imports the scientific stack';},6000);
</script>"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def repo_root() -> Path | None:
    """The real checkout, or None if it cannot be found.

    Running from source this is just the parent of `desktop/`. In the frozen
    build `REPO` above points inside the bundle, so the checkout is found from
    `AEGIS_REPO_ROOT` if set, then from the .exe's own location (the dist
    directory sits at `<repo>/dist/AegisDesktop/`), then from the working
    directory. Returning None rather than guessing lets the caller leave the
    default in place instead of pointing the app at a wrong tree.
    """
    env = os.getenv("AEGIS_REPO_ROOT")
    if env and (Path(env) / "backend").is_dir():
        return Path(env).resolve()
    if not getattr(sys, "frozen", False):
        return REPO
    here = Path(sys.executable).resolve()
    for cand in (*here.parents, Path.cwd(), *Path.cwd().parents):
        if (cand / "backend" / "data").is_dir() and (cand / "scripts").is_dir():
            return cand
    return None


#: Where the app writes what it did. A `console=False` build has nowhere for
#: stdout to go, so without this the shutdown path -- the one thing Murat asked
#: for -- is unobservable: it cannot be shown to work, only to have not visibly
#: failed. Kept beside the repo so it survives a rebuild of `dist/`.
def _log_path() -> Path:
    # `repo_root()`, not `os.getenv("AEGIS_REPO_ROOT")`: the log is opened before
    # `start_backend()` sets that variable, so reading the env here would put the
    # log inside the bundle on exactly the frozen build it exists to explain.
    base = repo_root() or REPO
    d = base / "backend" / "data" / "optimus"
    try:
        d.mkdir(parents=True, exist_ok=True)
        return d / "aegis_desktop.log"
    except OSError:
        return Path.home() / "aegis_desktop.log"


def _storage_dir() -> Path:
    """Where the window keeps `localStorage`, and why it is not the default.

    pywebview 6.2.1 starts with `private_mode=True`. That is an incognito
    window: `localStorage` is written to a temporary profile and thrown away
    when the process ends. The visible symptom, reported 2026-09-11, is that the
    desktop guide and the tour come back on EVERY launch -- the flag that says
    "you have seen this" never survived the window that set it.

    The profile also has to live in the CHECKOUT, not in the bundle. A path
    under `_internal` is deleted by the next rebuild of `dist/`, which is the
    frozen-path family again: correct from source, silently amnesiac when
    packaged. So if the base we found IS inside the bundle -- a frozen build
    that could not find its checkout -- the profile goes to the home directory
    rather than somewhere a rebuild will erase.
    """
    base = repo_root() or REPO
    meipass = getattr(sys, "_MEIPASS", None)
    in_bundle = "_internal" in base.parts
    if meipass:
        try:
            base.relative_to(Path(meipass).resolve())
            in_bundle = True
        except ValueError:
            pass
    d = (Path.home() / ".aegis" / "webview_profile" if in_bundle
         else base / "backend" / "data" / "optimus" / "webview_profile")
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        d = Path.home() / ".aegis" / "webview_profile"
        d.mkdir(parents=True, exist_ok=True)
    return d


log = logging.getLogger("aegis.desktop")

#: Filled by `start_backend`'s thread if it dies. Read by the report (and so by
#: the launcher's receipt, which embeds the report) -- a window that never
#: loaded must be able to say WHY without a second launch.
BACKEND_ERROR: dict = {}

#: What `bind_std_streams` did, for the report.
STD_STREAMS: dict = {}


def report_path() -> Path:
    """Where this shell writes what it did. Beside the log, in the checkout."""
    return _log_path().with_name("aegis_desktop_report.json")


def write_report(report: dict) -> Path | None:
    p = report_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
        return p
    except OSError:
        return None


def _init_log() -> Path:
    p = _log_path()
    try:
        h = logging.FileHandler(p, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
        log.propagate = False
    except OSError:
        pass
    return p


def free_port() -> int:
    """A port the OS just told us is free.

    Binding to 0 and reading the assignment avoids the "is 8000 taken?" race and
    means two copies of the app can run without fighting.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_for_health(port: int, timeout_s: float = 240.0) -> tuple[bool, float]:
    """Poll `/api/health` until it answers. Returns (ok, seconds waited)."""
    t0 = time.time()
    url = f"http://127.0.0.1:{port}/api/health"
    while time.time() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(url, timeout=2) as fh:  # noqa: S310 localhost only
                if fh.status == 200:
                    return True, round(time.time() - t0, 2)
        except (urllib.error.URLError, OSError, ValueError):
            pass
        time.sleep(0.25)
    return False, round(time.time() - t0, 2)


#: Passed to `uvicorn.run` beside the app and the port.
#:
#: `use_colors=False` is NOT cosmetic. uvicorn's `ColourizedFormatter` decides
#: whether to emit ANSI by calling `sys.stdout.isatty()` **unless** `use_colors`
#: is explicitly True or False -- and in a windowless process `sys.stdout` is
#: `None`, so the default asks `None.isatty()` and `Config.configure_logging()`
#: raises `AttributeError` BEFORE the socket is bound. Stating the answer means
#: the question is never asked. `log_config` is left at uvicorn's default on
#: purpose: its handlers resolve `ext://sys.stderr` at configure time, which is
#: the file we just bound, so uvicorn's own startup lines land in the app log.
UVICORN_KWARGS = {"host": "127.0.0.1", "log_level": "warning", "use_colors": False}

#: The file object `bind_std_streams` installed, if it installed one. Module
#: level so a second call is a no-op and so the report can say it happened.
_STD_STREAM_FILE = None


def bind_std_streams() -> dict:
    """Give a windowless process a real stdout and stderr, or nothing starts.

    THE ROOT CAUSE OF EVERY FAILED LAUNCH OF 2026-09-11, verified twice on the
    old .exe and once under `pythonw -m desktop.aegis_desktop` at 14:40:

        AttributeError: 'NoneType' object has no attribute 'isatty'
        uvicorn/logging.py:44  self.use_colors = sys.stdout.isatty()

    `pythonw.exe` and a `console=False` PyInstaller build both hand the process
    `sys.stdout is None` and `sys.stderr is None` -- there is no console to
    write to, so CPython gives it nothing rather than a broken handle. uvicorn
    then dies inside `Config.configure_logging()`, before binding, in a daemon
    thread whose traceback has nowhere to go: the splash counted to 242 s and
    the log held the start line and nothing else.

    Two independent fixes, because either alone is one dependency change from
    silent again: bind the streams to the app log HERE, and tell uvicorn the
    answer to the question in `UVICORN_KWARGS`. Binding is also the one that
    rescues every OTHER library that assumes a stdout exists.

    One file object serves both streams: two append handles on one file
    interleave badly on Windows, and there is nothing to gain from separating
    them when both ends are the same log.
    """
    global _STD_STREAM_FILE
    missing = [n for n in ("stdout", "stderr") if getattr(sys, n, None) is None]
    if not missing:
        return {"bound": [], "reason": "stdout and stderr already exist"}
    path = _log_path()
    if _STD_STREAM_FILE is None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _STD_STREAM_FILE = open(path, "a", encoding="utf-8",  # noqa: SIM115 lives for the process
                                    errors="replace", buffering=1)
        except OSError as exc:
            return {"bound": [], "error": f"{type(exc).__name__}: {exc}", "path": str(path)}
    for name in missing:
        setattr(sys, name, _STD_STREAM_FILE)
    log.info("bound %s to %s (windowless process had none)", "+".join(missing), path)
    return {"bound": missing, "path": str(path)}


def start_backend(port: int) -> threading.Thread:
    """uvicorn in a daemon thread inside this process.

    In-process rather than a child: one PID to reason about, no orphaned server
    if the window is killed, and the frozen build does not have to re-exec
    itself. The environment is set BEFORE `backend.main` is imported, because
    `mount_desktop_frontend` and the control router's guard both read it at
    import/startup time.
    """
    os.environ.setdefault("AEGIS_DESKTOP", "1")
    os.environ.setdefault("AEGIS_CONTROL_ENABLED", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    # BEFORE anything imports uvicorn. See `bind_std_streams`: without this the
    # thread below dies on `None.isatty()` and the window never loads.
    STD_STREAMS.update(bind_std_streams())
    # Point the app at the REAL checkout. Inside the frozen build `REPO` would
    # otherwise resolve to `<dist>/_internal`, and the first packaged run proved
    # it: it created a fresh empty `aegis_pi.db` inside the bundle and would
    # have shown a programme with no receipts, no lanes and no history -- an
    # empty app that looks like a working one, which is the house failure mode.
    root = repo_root()
    if root:
        os.environ.setdefault("AEGIS_REPO_ROOT", str(root))
        # `backend/data`, NOT `backend/data/optimus`. `config.DATA_DIR` is this
        # value and `OPTIMUS_LEDGER_DIR` is `DATA_DIR / "optimus"`, so pointing
        # it one level too deep created `backend/data/optimus/optimus/` and put
        # `beliefs.jsonl` and `predictions.jsonl` in it. Found 2026-09-10 by a
        # stray untracked directory, not by anything failing -- writing real
        # records to a plausible wrong path is silent by construction.
        os.environ.setdefault("AEGIS_DATA_DIR", str(root / "backend" / "data"))

    def run() -> None:
        # EVERY LINE OF THIS BODY WAS UNWRAPPED UNTIL 2026-09-11, and the frozen
        # build proved what that costs: the thread died on import, the window
        # counted to 242 s and gave up, `aegis_desktop.log` held the start line
        # and NOTHING ELSE, and diagnosing it needed a process table and two
        # more launches. A daemon thread that raises in a `console=False` build
        # writes its traceback to a stderr that does not exist. `BaseException`,
        # not `Exception`: a `SystemExit` from deep inside uvicorn's config is
        # exactly as silent and exactly as fatal.
        try:
            import uvicorn

            from backend.main import app, mount_desktop_frontend
            mount_desktop_frontend(app)      # after every API route is registered
            uvicorn.run(app, port=port, **UVICORN_KWARGS)
        except BaseException as exc:         # noqa: BLE001 - see above
            BACKEND_ERROR["error"] = f"{type(exc).__name__}: {exc}"
            BACKEND_ERROR["traceback"] = traceback.format_exc()
            log.exception("backend thread died: %s", exc)
            raise

    th = threading.Thread(target=run, name="aegis-uvicorn", daemon=True)
    th.start()
    return th


def maybe_start_llama(enabled: bool = True, keep: bool = False) -> dict:
    if not enabled:
        return {"action": "skipped", "reason": "--no-llama"}
    try:
        from backend.services import llama_server as ls
    except Exception as exc:  # noqa: BLE001
        return {"action": "unavailable", "reason": f"{type(exc).__name__}: {exc}"}
    st = ls.status()
    if st["listening"]:
        # do not adopt it, do not restart it, do not kill it on exit
        return {"action": "left_alone", "reason": "already listening", "pid": st["pid"],
                "started_by_aegis": st["started_by_aegis"]}
    if not st["binary_present"] or not st["model_present"]:
        return {"action": "unavailable",
                "reason": f"binary_present={st['binary_present']} model_present={st['model_present']}",
                "model_path": st["model_path"], "binary_path": st["binary_path"]}
    # `bind` ties the server's life to this process AT THE KERNEL, so it dies
    # with the app however the app dies -- window close, crash, or Task Manager.
    # Every shutdown hook in this file runs user code, and `TerminateProcess`
    # runs none: measured, a force-kill left the server up with 5,095 MiB mapped.
    # `--keep-llama` opts out, because then the server is meant to outlive us.
    return ls.start(wait_s=0.0, bind=not keep) | {
        "action_note": "started in the background; poll /api/control/llama"}


def stop_llama_if_owned() -> dict:
    try:
        from backend.services import llama_server as ls
    except Exception as exc:  # noqa: BLE001
        return {"action": "unavailable", "reason": f"{type(exc).__name__}: {exc}"}
    return ls.stop_if_owned()


def dispatch_module(argv: list[str]) -> int:
    """RETIRED BY THE LAUNCHER (2026-09-11); kept for one release.

    `desktop/launcher.py` is what PyInstaller freezes now, and it starts this
    shell under the CHECKOUT'S interpreter -- so `sys.executable` is a real
    python, `-m` works, and `control.child_argv`'s frozen branch is never
    reached. Deleting it in the same commit that added the launcher would mean
    the old `dist/AegisDesktop.exe` on Murat's desktop loses its job dispatch
    the moment it is next run. Delete it, and its tests, once the launcher has
    run for a week.

    `AegisDesktop.exe --run-module scripts.night_factory --job X` -> run it.

    Inside a PyInstaller build `sys.executable` is this .exe, not python.exe, so
    the control router's `[sys.executable, "-m", "scripts.night_factory", ...]`
    would hand `-m` to argparse and die instantly, leaving an empty log and a
    "job started" that never ran. `control.child_argv` rewrites it to this flag
    and this function is the other half.

    `sys.argv` is rebuilt so the module's own argparse sees exactly what it
    would have seen under `python -m`.
    """
    import runpy

    module = argv[0]
    sys.argv = [module, *argv[1:]]
    runpy.run_module(module, run_name="__main__", alter_sys=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    # BEFORE argparse: a job re-entry is not a window launch, and every second
    # spent importing pywebview here is a second of a five-hour night job.
    raw = sys.argv[1:] if argv is None else argv
    if raw[:1] == ["--run-module"]:
        return dispatch_module(raw[1:])

    ap = argparse.ArgumentParser(description="Aegis Desktop")
    ap.add_argument("--port", type=int, default=0, help="0 = ask the OS for a free one")
    ap.add_argument("--no-llama", action="store_true", help="do not start the local model server")
    ap.add_argument("--keep-llama", action="store_true",
                    help="leave the model server running when the window closes")
    ap.add_argument("--headless", action="store_true",
                    help="start everything, print the report, exit -- for smoke tests and CI")
    ap.add_argument("--serve", action="store_true",
                    help="start everything and KEEP SERVING, no window -- for verifying a "
                         "packaged build, or for running the engine on a machine with no display")
    ap.add_argument("--page", default="/desktop", help="path to open in the window")
    a = ap.parse_args(argv)

    t0 = time.time()
    logfile = _init_log()
    log.info("start argv=%s", sys.argv[1:])
    storage = _storage_dir()
    log.info("storage %s", storage)
    port = a.port or free_port()
    start_backend(port)
    llama = maybe_start_llama(enabled=not a.no_llama, keep=a.keep_llama)

    report = {"utc": _now(), "port": port, "llama": llama, "log": str(logfile),
              "storage": str(storage), "repo_root": str(repo_root() or REPO),
              "pid": os.getpid(), "frozen": bool(getattr(sys, "frozen", False)),
              "std_streams": dict(STD_STREAMS)}
    write_report(report)
    log.info("backend on %s; llama=%s", port, json.dumps(llama, default=str)[:300])

    if a.headless or a.serve:
        ok, waited = wait_for_health(port)
        report |= {"health_ok": ok, "cold_start_s": waited,
                   "total_s": round(time.time() - t0, 2),
                   "mode": "serve" if a.serve else "headless",
                   "url": f"http://127.0.0.1:{port}/desktop"}
        if BACKEND_ERROR:
            report["backend_error"] = dict(BACKEND_ERROR)
        # The acceptance line for the root fix (handoff 2026-09-11 s1.1): the
        # packaged app used to report NO configured provider, because its
        # `.env` was a file inside `_internal` that does not exist. Read it
        # here rather than inferred: `configured` is the list of keys that are
        # actually non-empty, and `declared_but_empty` is the row that once
        # read as configured and was not.
        try:
            from backend.services.llm_analyzer import llm_usage
            report["llm_providers"] = llm_usage()["providers"]
        except Exception as exc:  # noqa: BLE001 - a report that cannot be built must say why
            report["llm_providers"] = {"error": f"{type(exc).__name__}: {exc}"}
        # AFTER the provider block: the early write happens before the health
        # probe and before `llm_providers`, so a reader of the report file (the
        # launcher's receipt embeds it) would otherwise see a half-filled report
        # and conclude the shell never finished starting.
        write_report(report)
        if a.serve:
            # a packaged build cannot be probed by `--headless`, which reports and
            # exits before anything can call it -- the first attempt to verify the
            # .exe's routes got eight connection refusals for exactly that reason
            print(json.dumps(report, indent=1, default=str), flush=True)
            try:
                while True:
                    time.sleep(1.0)
            except KeyboardInterrupt:
                pass
            if not a.keep_llama:
                print(json.dumps({"llama_stop": stop_llama_if_owned()}, default=str), flush=True)
            return 0
        if not a.keep_llama:
            report["llama_stop"] = stop_llama_if_owned()
        print(json.dumps(report, indent=1, default=str))
        return 0 if ok else 1

    import webview

    window = webview.create_window("Aegis", html=SPLASH, width=1440, height=920,
                                   min_size=(900, 620), background_color="#0b0d10")

    def when_ready() -> None:
        """Swap the splash for the app. Runs AFTER the GUI loop is up.

        2026-09-10, reported as "the exe didnt open timed out". The engine was
        never the problem -- the log shows the backend answering in 2.3 s on
        both launches, and one of them closed cleanly and stopped the model. The
        window simply never left the splash.

        This used to run on a raw `threading.Thread` started BEFORE
        `webview.start()`. Health came back in about two seconds, `load_url` was
        called into a window whose GUI loop had not been created yet, and the
        call went nowhere. The splash then counted up forever, which reads
        exactly like a hang.

        `webview.start(func)` is the documented contract: pywebview runs `func`
        on its own thread once the window exists. And the body is wrapped,
        because an exception in a daemon thread of a `console=False` build goes
        to a stderr that does not exist -- which is why the first version of
        this failed in total silence.
        """
        try:
            ok, waited = wait_for_health(port)
            report["health_ok"] = ok
            report["cold_start_s"] = waited
            if BACKEND_ERROR:
                report["backend_error"] = dict(BACKEND_ERROR)
            write_report(report)
            log.info("health_ok=%s after %.2fs", ok, waited)
            if ok:
                url = f"http://127.0.0.1:{port}{a.page}"
                window.load_url(url)
                log.info("loaded %s", url)
            else:
                log.error("health never answered within %.0fs; showing the failure page", waited)
                why = (f"<pre style='white-space:pre-wrap;color:#f85149'>"
                       f"{BACKEND_ERROR.get('error')}</pre>" if BACKEND_ERROR else
                       "<p>The engine thread did not report an error, which means it is "
                       "still importing or the port was taken.</p>")
                window.load_html(
                    "<body style='background:#0b0d10;color:#e6e8ea;font:14px system-ui;padding:32px'>"
                    f"<h2>The engine did not answer within the timeout ({waited}s).</h2>"
                    f"{why}"
                    f"<p>Nothing was started that needs stopping.</p>"
                    f"<p>The app's own log is at<br><code>{_log_path()}</code></p>")
        except Exception as exc:  # noqa: BLE001 - a silent splash is the worst outcome
            log.exception("when_ready failed: %s", exc)
            try:
                window.load_html(
                    "<body style='background:#0b0d10;color:#e6e8ea;font:14px system-ui;padding:32px'>"
                    f"<h2>The window could not load the app.</h2><pre>{type(exc).__name__}: {exc}</pre>"
                    f"<p>Log: <code>{_log_path()}</code></p>")
            except Exception:  # noqa: BLE001
                pass

    stopped_once: list[bool] = []

    def shutdown(where: str) -> None:
        """Stop the model server we started. Idempotent, and it LOGS.

        2026-09-10: the app was closed and llama-server PID 8012 stayed up with
        5,495 MiB mapped. Its parent process was the app, so it was ours -- but
        the frozen build had written its ownership note inside the bundle
        (`llama_server.REPO` resolved to `_internal`), so nothing could read it
        back and `stop_if_owned` saw a "foreign" server and left it alone.

        The reason that took a forensic dig rather than a glance is that this
        function used to `print()`, and a `console=False` build has nowhere for
        stdout to go. An app whose shutdown path is invisible cannot be said to
        work; it can only be said to have not visibly failed.
        """
        if a.keep_llama or stopped_once:
            return
        stopped_once.append(True)
        try:
            out = stop_llama_if_owned()
        except Exception as exc:  # noqa: BLE001 - never block the app from closing
            out = {"action": "error", "reason": f"{type(exc).__name__}: {exc}"}
        log.info("shutdown(%s): %s", where, json.dumps(out, default=str))

    # Three paths, because they do not all fire. `closing` is the normal one;
    # the return from `webview.start()` covers a teardown that skips it; and
    # atexit covers an interpreter exit that skips both. Idempotent, so belt and
    # braces cost one no-op.
    window.events.closing += lambda: shutdown("window-closing")
    atexit.register(lambda: shutdown("atexit"))
    try:
        # `webview.start(func)` -- the func runs on pywebview's own thread once
        # the window exists. Starting it as a bare thread beforehand is what put
        # `load_url` into a window that did not exist yet and left the splash up
        # forever.
        # `private_mode=False` + an explicit `storage_path`: without both, the
        # window is incognito and every "don't show me this again" is forgotten
        # when it closes.
        webview.start(when_ready, private_mode=False, storage_path=str(storage))
    finally:
        shutdown("after-start")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
