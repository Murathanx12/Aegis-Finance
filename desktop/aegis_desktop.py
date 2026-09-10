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
import json
import os
import socket
import sys
import threading
import time
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

    def run() -> None:
        import uvicorn

        from backend.main import app, mount_desktop_frontend
        mount_desktop_frontend(app)          # after every API route is registered
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

    th = threading.Thread(target=run, name="aegis-uvicorn", daemon=True)
    th.start()
    return th


def maybe_start_llama(enabled: bool = True) -> dict:
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
    return ls.start(wait_s=0.0) | {"action_note": "started in the background; poll /api/control/llama"}


def stop_llama_if_owned() -> dict:
    try:
        from backend.services import llama_server as ls
    except Exception as exc:  # noqa: BLE001
        return {"action": "unavailable", "reason": f"{type(exc).__name__}: {exc}"}
    return ls.stop_if_owned()


def dispatch_module(argv: list[str]) -> int:
    """`AegisDesktop.exe --run-module scripts.night_factory --job X` -> run it.

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
    ap.add_argument("--page", default="/desktop", help="path to open in the window")
    a = ap.parse_args(argv)

    t0 = time.time()
    port = a.port or free_port()
    start_backend(port)
    llama = maybe_start_llama(enabled=not a.no_llama)

    report = {"utc": _now(), "port": port, "llama": llama}

    if a.headless:
        ok, waited = wait_for_health(port)
        report |= {"health_ok": ok, "cold_start_s": waited,
                   "total_s": round(time.time() - t0, 2), "mode": "headless"}
        if not a.keep_llama:
            report["llama_stop"] = stop_llama_if_owned()
        print(json.dumps(report, indent=1, default=str))
        return 0 if ok else 1

    import webview

    window = webview.create_window("Aegis", html=SPLASH, width=1440, height=920,
                                   min_size=(900, 620), background_color="#0b0d10")

    def when_ready() -> None:
        ok, waited = wait_for_health(port)
        report["health_ok"] = ok
        report["cold_start_s"] = waited
        if ok:
            window.load_url(f"http://127.0.0.1:{port}{a.page}")
        else:
            window.load_html(
                "<body style='background:#0b0d10;color:#e6e8ea;font:14px system-ui;padding:32px'>"
                f"<h2>The engine did not answer within the timeout ({waited}s).</h2>"
                "<p>Nothing was started that needs stopping. Run "
                "<code>python -m desktop.aegis_desktop --headless</code> from the repo to see why.</p>")

    threading.Thread(target=when_ready, name="aegis-splash", daemon=True).start()

    def on_closing() -> None:
        # Murat 2026-09-10: auto-close the model server when the app shuts.
        # `stop_if_owned` leaves a server Aegis did not start alone.
        if not a.keep_llama:
            out = stop_llama_if_owned()
            print(json.dumps({"llama_stop": out}, default=str), flush=True)

    window.events.closing += on_closing
    webview.start()
    # a belt-and-braces stop: `closing` does not fire on every platform/teardown
    # path, and leaving 5 GB of VRAM mapped after the window is gone is the exact
    # complaint this app was asked to fix
    if not a.keep_llama:
        stop_llama_if_owned()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
