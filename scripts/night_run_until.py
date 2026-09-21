"""The night, with a hard stop -- the wrapper that ends at a wall-clock time.

    python -m scripts.night_run_until --date 2026-09-22 --stop-at 07:30 \
        --first "P6_bars_and_regret:60" \
        --queue "J1_error_dataset:20,C7_signal_calibration:60,..." --lab --paid

Murat, 2026-09-21 21:40 HKT: "make everything ready for the night and run it,
make it stop at 7.30 am." `scripts.night_factory` has a STOP file and awake-time
boxes but no clock; `scripts.always_on_lab` has a STOP file and no clock. This
wrapper is the clock, and it owns every PID it starts.

THE SCHEDULE (all local time, `--stop-at` = T):
  start      dotenv is loaded HERE (children inherit the key VALUES through the
             environment and are launched with AEGIS_IGNORE_DOTENV=1, which is how
             X4 gets its FRED key and P6 its data credential -- last night both
             ran without one); power plan checked; model server started and its
             PID written down; provider balance snapshot taken.
  phase 1    `--first` jobs (the bars refresh) under night_factory.
  grading    reality first: `forecast_grader.grade_due` and
             `decision_ledger.score_due`, receipts into the night folder.
  phase 2    `--lab` starts `scripts.always_on_lab` (news, typing, the 06:30 pass);
             `--queue` runs under night_factory. Both write into the SAME night
             folder (NIGHT_RUN_DATE), so ONE STOP file ends both.
  T - 30 min STOP file written: no new job starts after this (night_factory and
             the lab both check it between jobs / ticks).
  T - 5 min  the running job tree is killed BY PID (`night_factory.kill_tree`).
  T - 3 min  the lab tree, if still alive, the same way.
  T          the model server is stopped by the PID written at start (refused if
             the socket's PID is not that PID); the morning report is written;
             `NIGHT_STOPPED.json` carries the process census and the GPU line.

Nothing here is killed by image name (CLAUDE.md protocol 6). Every exit path
writes `NIGHT_STOPPED.json`; a crash of this wrapper is the one thing it cannot
report, so it logs a heartbeat line every tick.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Loading config loads dotenv into THIS process's environment. Children are
# started with AEGIS_IGNORE_DOTENV=1 and inherit the values; nothing below ever
# prints one.
from backend import config as _config                       # noqa: E402,F401

#: key NAMES the night's jobs read; printed as present/absent, never as values
KEY_NAMES: tuple[str, ...] = ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY",
                              "FRED_API_KEY", "DEEPSEEK_API_KEY")
#: P6 reads the venue's own names; the repo's .env carries the ALPACA_ ones.
KEY_ALIASES: tuple[tuple[str, str], ...] = (("APCA_API_KEY_ID", "ALPACA_API_KEY_ID"),
                                            ("APCA_API_SECRET_KEY", "ALPACA_API_SECRET_KEY"))
STOP_LEAD_MIN = 30
KILL_JOBS_LEAD_MIN = 5
KILL_LAB_LEAD_MIN = 3
TICK_S = 30


def _now() -> datetime:
    return datetime.now()


def _iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Night:
    def __init__(self, a: argparse.Namespace) -> None:
        self.date = a.date
        self.out = REPO / "backend" / "data" / "optimus" / f"night_factory_{a.date}"
        self.out.mkdir(parents=True, exist_ok=True)
        self.stop_file = self.out / "STOP"
        self.log_path = self.out / f"night_run_until_{a.date}.log"
        self.stop_at = self._resolve(a.stop_at)
        self.first = a.first
        self.queue = a.queue
        self.lab = a.lab
        self.paid = a.paid
        self.pids: dict[str, int | None] = {"night_factory_phase1": None,
                                            "night_factory_phase2": None,
                                            "lab": None, "llama_server": None}
        self.events: list[dict] = []
        self.children: dict[str, subprocess.Popen] = {}
        self.stopped_written = False
        self.jobs_killed = False
        self.lab_killed = False

    # ------------------------------------------------------------ plumbing
    def _resolve(self, hhmm: str) -> datetime:
        h, m = (int(x) for x in hhmm.split(":"))
        now = _now()
        t = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if t <= now:
            t += timedelta(days=1)
        return t

    def log(self, msg: str) -> None:
        line = f"[{_iso()}] {msg}"
        print(line, flush=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        self.events.append({"t": _iso(), "msg": msg})

    def env(self) -> dict:
        e = {**os.environ, "AEGIS_IGNORE_DOTENV": "1", "PYTHONIOENCODING": "utf-8",
             "NIGHT_RUN_DATE": self.date}
        for want, have in KEY_ALIASES:
            if not e.get(want) and e.get(have):
                e[want] = e[have]
        if self.paid:
            e["AEGIS_NIGHT_PAID_OK"] = "1"
        else:
            e.pop("AEGIS_NIGHT_PAID_OK", None)
        return e

    def key_census(self) -> dict:
        e = self.env()
        return {k: ("present" if e.get(k) else "ABSENT") for k in KEY_NAMES}

    def _popen(self, name: str, args: list[str], extra_env: dict | None = None) -> subprocess.Popen:
        log = self.out / f"{name}_{self.date}.log"
        fh = log.open("a", encoding="utf-8")
        env = self.env()
        if extra_env:
            env.update(extra_env)
        p = subprocess.Popen([sys.executable, *args], cwd=str(REPO), stdout=fh,
                             stderr=subprocess.STDOUT, text=True, env=env)
        self.children[name] = p
        self.pids[name] = p.pid
        self.log(f"started {name} pid {p.pid}: {' '.join(args)} -> {log.name}")
        return p

    def _alive(self, name: str) -> bool:
        p = self.children.get(name)
        return p is not None and p.poll() is None

    def _wait_until(self, name: str, deadline: datetime) -> int | None:
        """Wait for a child until `deadline`, ticking the clock rules meanwhile."""
        p = self.children[name]
        while p.poll() is None:
            if _now() >= deadline:
                return None
            self.tick()
            time.sleep(TICK_S)
        self.log(f"{name} exited {p.returncode}")
        return p.returncode

    # --------------------------------------------------------------- steps
    def power_check(self) -> None:
        from scripts import night_factory as NF
        refusal = NF.refuse_if_the_machine_may_sleep()
        if refusal:
            self.log(refusal)
            raise SystemExit(3)
        self.log("power plan: the machine will stay up")

    def start_model(self) -> None:
        from backend.services import llama_server as LS
        st = LS.status()
        if st.get("listening"):
            self.log(f"model server already listening, pid {st.get('pid')} -- NOT ours; will not stop it")
            self.pids["llama_server"] = None
            return
        r = LS.start(bind=False, wait_s=240)
        st = LS.status()
        self.pids["llama_server"] = st.get("pid") if r.get("ok") else None
        self.log(f"model server: {r.get('action')} {r.get('reason') or ''} pid {self.pids['llama_server']} "
                 f"ready={st.get('ready')}")

    def balance(self, label: str) -> None:
        try:
            r = subprocess.run([sys.executable, "-m", "scripts.llm_cost_audit", "--snapshot"],
                               cwd=str(REPO), capture_output=True, text=True, timeout=120,
                               env=self.env())
            head = [ln for ln in r.stdout.splitlines() if "balance now" in ln]
            self.log(f"balance snapshot ({label}): {head[0].strip() if head else 'CANNOT DETERMINE'}")
        except (OSError, subprocess.SubprocessError) as exc:
            self.log(f"balance snapshot ({label}) failed: {exc}")

    def grade_reality(self) -> None:
        code = (
            "import json,sys\n"
            "from pathlib import Path\n"
            "from backend.services import forecast_grader as FG, decision_ledger as DL\n"
            f"out=Path(r'{self.out}')\n"
            "res={}\n"
            "try:\n"
            "    res['grade_forecasts']=FG.grade_due()  # NIGHT_RUN_DATE in the env routes its receipt into the night folder\n"
            "except Exception as e: res['grade_forecasts']={'status':'FAILED','error':f'{type(e).__name__}: {e}'}\n"
            "try:\n"
            "    res['score_due']=DL.score_due()\n"
            "except Exception as e: res['score_due']={'status':'FAILED','error':f'{type(e).__name__}: {e}'}\n"
            "p=out/'REALITY_GRADING_night.json'\n"
            "p.write_text(json.dumps(res,indent=1,default=str),encoding='utf-8')\n"
            "print({k:(v.get('status') or v.get('headline') or v.get('error')) for k,v in res.items()})\n"
        )
        self.log("reality grading: forecast_grader.grade_due + decision_ledger.score_due")
        try:
            r = subprocess.run([sys.executable, "-c", code], cwd=str(REPO), capture_output=True,
                               text=True, timeout=1800, env=self.env())
            self.log(f"reality grading -> rc {r.returncode}: {(r.stdout or r.stderr).strip()[-400:]}")
        except (OSError, subprocess.SubprocessError) as exc:
            self.log(f"reality grading failed to run: {exc}")

    def run_factory(self, name: str, queue: str, deadline: datetime) -> None:
        self._popen(name, ["-m", "scripts.night_factory"], {"NIGHT_QUEUE": queue})
        rc = self._wait_until(name, deadline)
        if rc is None:
            self.log(f"{name} still running at its deadline; the clock rules take it from here")

    # --------------------------------------------------------------- clock
    def tick(self) -> None:
        now = _now()
        left = (self.stop_at - now).total_seconds() / 60.0
        if not self.stopped_written and left <= STOP_LEAD_MIN:
            self.stop_file.write_text(f"night_run_until: STOP at {_iso()}, T-{STOP_LEAD_MIN} min\n",
                                      encoding="utf-8")
            self.stopped_written = True
            self.log(f"STOP file written ({self.stop_file}); no new job starts")
        if not self.jobs_killed and left <= KILL_JOBS_LEAD_MIN:
            self.jobs_killed = True
            self._kill("night_factory_phase1")
            self._kill("night_factory_phase2")
        if not self.lab_killed and left <= KILL_LAB_LEAD_MIN:
            self.lab_killed = True
            self._kill("lab")
        if int(now.timestamp()) % 600 < TICK_S:
            self.log(f"heartbeat: {left:.0f} min to stop; alive: "
                     f"{[n for n in self.children if self._alive(n)]}")

    def _kill(self, name: str) -> None:
        if not self._alive(name):
            return
        from scripts import night_factory as NF
        pid = self.pids[name]
        asked = NF.kill_tree(int(pid))
        self.log(f"killed {name} tree by PID: {asked}")

    def stop_model(self) -> dict:
        from backend.services import llama_server as LS
        want = self.pids.get("llama_server")
        st = LS.status()
        if not st.get("listening"):
            return {"action": "none", "reason": "nothing listening"}
        if want is None or st.get("pid") != want:
            return {"action": "left_running",
                    "reason": f"socket pid {st.get('pid')} is not the pid this wrapper started ({want})"}
        r = LS.stop()
        return {"action": r.get("action"), "reason": r.get("reason"), "pid": want}

    def census(self) -> dict:
        from scripts import night_factory as NF
        mine = {}
        for name, pid in self.pids.items():
            if pid is None:
                continue
            kids = NF._descendants(int(pid))
            alive = self._alive(name) if name in self.children else None
            mine[name] = {"pid": pid, "alive": alive, "descendants_alive": kids}
        return {"ours": mine, "gpu": NF.gpu_line()}

    def morning_report(self) -> dict:
        try:
            r = subprocess.run([sys.executable, "-m", "scripts.night_morning_report", "--date", self.date],
                               cwd=str(REPO), capture_output=True, text=True, timeout=600, env=self.env())
            return {"rc": r.returncode, "tail": (r.stdout or r.stderr)[-600:]}
        except (OSError, subprocess.SubprocessError) as exc:
            return {"rc": None, "error": str(exc)}

    def finish(self, why: str) -> None:
        # order: jobs, lab, model, report, census -- every path, once.
        self._kill("night_factory_phase1")
        self._kill("night_factory_phase2")
        self._kill("lab")
        model = self.stop_model()
        self.log(f"model server: {model}")
        self.balance("end")
        report = self.morning_report()
        self.log(f"morning report: rc {report.get('rc')}")
        cen = self.census()
        payload = {"receipt": "NIGHT_STOPPED", "date": self.date, "why": why,
                   "stop_at": self.stop_at.isoformat(timespec="minutes"),
                   "stopped_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "pids": self.pids, "model_server": model, "morning_report": report,
                   "census": cen, "keys": self.key_census(), "events": self.events[-60:]}
        (self.out / "NIGHT_STOPPED.json").write_text(json.dumps(payload, indent=1, default=str),
                                                     encoding="utf-8")
        self.log(f"NIGHT_STOPPED.json written; census {json.dumps(cen['ours'])[:300]}")

    # ---------------------------------------------------------------- main
    def run(self) -> int:
        self.log(f"night {self.date}: stop at {self.stop_at.isoformat(timespec='minutes')}; "
                 f"first={self.first!r} queue={self.queue!r} lab={self.lab} paid={self.paid}")
        self.log(f"keys (names only): {self.key_census()}")
        if self.stop_file.exists():
            self.log(f"a STOP file already sits at {self.stop_file}; removing it (this wrapper writes its own)")
            self.stop_file.unlink()
        try:
            self.power_check()
            self.start_model()
            self.balance("start")
            if self.first:
                self.run_factory("night_factory_phase1", self.first,
                                 self.stop_at - timedelta(minutes=KILL_JOBS_LEAD_MIN))
            self.grade_reality()
            if self.lab:
                self._popen("lab", ["-m", "scripts.always_on_lab"])
            if self.queue:
                self.run_factory("night_factory_phase2", self.queue,
                                 self.stop_at - timedelta(minutes=KILL_JOBS_LEAD_MIN))
            while _now() < self.stop_at:
                self.tick()
                time.sleep(TICK_S)
            self.finish("stop_at reached")
            return 0
        except KeyboardInterrupt:
            self.finish("KeyboardInterrupt")
            return 130
        except SystemExit as exc:
            self.finish(f"SystemExit {exc.code}")
            raise
        except Exception as exc:                                     # noqa: BLE001
            self.log(f"wrapper error: {type(exc).__name__}: {exc}")
            self.finish(f"error {type(exc).__name__}")
            return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="night folder date (default: tomorrow if after 18:00)")
    ap.add_argument("--stop-at", default="07:30")
    ap.add_argument("--first", default="", help="NIGHT_QUEUE for phase 1 (before grading)")
    ap.add_argument("--queue", default="", help="NIGHT_QUEUE for phase 2")
    ap.add_argument("--lab", action="store_true")
    ap.add_argument("--paid", action="store_true", help="export AEGIS_NIGHT_PAID_OK=1 to the jobs")
    a = ap.parse_args(argv)
    if not a.date:
        d = date.today() + (timedelta(days=1) if _now().hour >= 18 else timedelta())
        a.date = d.isoformat()
    return Night(a).run()


if __name__ == "__main__":
    raise SystemExit(main())
