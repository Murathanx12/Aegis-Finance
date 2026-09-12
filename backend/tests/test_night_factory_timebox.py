"""The night factory's time box, which for one night could not go red.

On 2026-09-11 `N3_frozen_embedding_head` ran 40,569.7 s -- 11h16m -- under a
declared `<= 60 min` box and `scripts.night_factory.run_job` took its SUCCESS
branch: the receipt carries `exit_code 0` and no TIMEOUT was ever written. The
machine was in Modern Standby from 15:58Z to 00:09Z, so awake time was still
about 3h05m against the hour it was allowed.

A probe that copied `run_job`'s subprocess call verbatim -- the venv
`sys.executable`, a file-handle stdout, `stderr=STDOUT`, `text=True`, the same
env dict -- with a 20 s box and a 90 s sleeper raised `TimeoutExpired` at
20.01 s and killed the real grandchild with it. So the SHAPE was never the
defect, and "it works when I try it" is exactly why a box like that is
untrustworthy: it depended on `WaitForSingleObject` surviving a standby
transition that cannot be summoned on demand.

The box now owns its clock (`await_within_box`), counts AWAKE seconds only,
and kills the process TREE by PID. These tests run it against
`scripts/night_smoke_job.py`, a job that does nothing but sleep, so the box
finally has something cheap to be exercised against -- every real job in the
queue costs hours.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import night_factory as NF                       # noqa: E402
from scripts import night_smoke_job as SMOKE                   # noqa: E402


# --------------------------------------------------------------- the dispatch

def test_smoke_ids_route_to_the_smoke_job_and_nothing_else_does():
    assert NF._job_module("SMOKE_sleeper") == "scripts.night_smoke_job"
    assert NF._job_module("D1_reaction_book") == "scripts.night_factory_jobs"
    assert NF._job_module("G3_evolve_v2") == "scripts.night_factory_jobs"
    assert NF.SMOKE_PREFIX == SMOKE.SMOKE_PREFIX == "SMOKE_"


def test_no_smoke_job_is_in_a_real_queue():
    """The fake job exists to be killed. It must never be scheduled for real."""
    from scripts.night_factory_jobs import JOBS

    offenders = [j for j, _ in NF.QUEUE if j.startswith(NF.SMOKE_PREFIX)]
    offenders += [j for j in JOBS if j.startswith(NF.SMOKE_PREFIX)]
    assert offenders == [], f"a SMOKE_ job reached a real queue: {offenders}"


def test_the_smoke_job_refuses_a_name_that_is_not_its_own(tmp_path: Path):
    rc = SMOKE.main(["D1_reaction_book", "--out", str(tmp_path / "r.json"), "--sleep-s", "0"])
    assert rc == 2 and not (tmp_path / "r.json").exists()


# ------------------------------------------------------- the box, for real

@pytest.fixture()
def night(tmp_path: Path, monkeypatch):
    """Point the factory's OUT at a tmp dir so no real receipt is touched."""
    out = tmp_path / "night_factory_test"
    out.mkdir()
    monkeypatch.setattr(NF, "OUT", out)
    monkeypatch.setattr(NF, "STOP", out / "STOP")
    monkeypatch.setattr(NF, "LEADERBOARD", out / "LEADERBOARD.md")
    return out


def test_a_sleeper_is_killed_within_the_box_and_the_receipt_says_so(night: Path):
    """A 90 s sleeper under a 6 s box. Before the fix this is the shape that,
    for one night, simply returned."""
    started = time.time()
    payload = NF.run_job("SMOKE_sleeper", 1, 0.1, ["--sleep-s", "90"])
    elapsed = time.time() - started

    assert payload["verdict"] == "TIMEOUT"
    # killed within the box plus the grace the kill itself is allowed
    assert elapsed < 6 + NF.KILL_GRACE_S + 30, f"the box did not fire: {elapsed:.1f}s"
    assert payload["awake_s"] >= 6
    assert payload["box_s"] == pytest.approx(6.0)
    assert payload["killed_pids"], "a TIMEOUT receipt with no PIDs proves nothing"
    assert payload["child_pid"] in payload["killed_pids"]
    assert "killed after" in payload["headline"]
    assert not payload.get("tree_survived_the_kill")

    # the receipt is on disk, with the same shape
    on_disk = json.loads((night / "SMOKE_sleeper_run01.json").read_text(encoding="utf-8"))
    assert on_disk["verdict"] == "TIMEOUT"
    assert on_disk["licence"] == "PRODUCT_EXPERIMENT"
    for key in ("elapsed_s", "awake_s", "slept_s", "box_s", "killed_pids",
                "wall_minus_monotonic_s", "sleep_gaps", "written_utc"):
        assert key in on_disk, f"the TIMEOUT receipt is missing {key}"


def test_the_whole_tree_dies_not_just_the_venv_redirector(night: Path):
    """`.venv/Scripts/python.exe` is a REDIRECTOR that starts the real
    interpreter and waits, so the job is a grandchild. An orphaned grandchild
    keeps running and overwrites the receipt that said it was killed."""
    beat = night / "beat.txt"
    NF.run_job("SMOKE_tree", 1, 0.1, ["--sleep-s", "120", "--heartbeat", str(beat)])
    assert beat.exists(), "the sleeper never started"
    first = beat.read_text(encoding="utf-8")
    time.sleep(5)
    assert beat.read_text(encoding="utf-8") == first, "the grandchild survived the kill"


def test_a_job_inside_its_box_is_not_touched(night: Path):
    payload = NF.run_job("SMOKE_quick", 1, 1.0, ["--sleep-s", "1"])
    assert payload["verdict"] == "SMOKE"
    assert payload["exit_code"] == 0
    assert payload["killed_pids"] == []
    assert payload["slept_s"] == 0.0
    assert payload["awake_s"] < 60


def test_a_job_that_exits_nonzero_keeps_its_code_and_a_log_tail(night: Path):
    payload = NF.run_job("SMOKE_angry", 1, 1.0, ["--sleep-s", "0", "--exit-code", "9"])
    # the smoke job writes its receipt before returning the exit code, so this
    # is the "receipt exists, rc non-zero" branch
    assert payload["exit_code"] == 9
    assert payload["verdict"] != "TIMEOUT"
    assert payload["log_tail"]


# ------------------------------------------ the box counts AWAKE time only

class _FakeProc:
    """A child that never exits, driven by a scripted clock."""

    def __init__(self, pid: int = 4242):
        self.pid = pid
        self.waited = False

    def poll(self):
        return None

    def wait(self, timeout=None):
        self.waited = True
        return -9


def _scripted_clock(deltas: list[float]):
    """A wall clock that advances by `deltas` on each successive read."""
    t = [1_000_000.0]
    seq = iter(deltas)

    def clock():
        try:
            t[0] += next(seq)
        except StopIteration:
            t[0] += 1.0
        return t[0]
    return clock


def test_eight_hours_of_standby_do_not_spend_a_sixty_minute_box():
    """The N3 shape, in miniature: a short awake stretch, a huge gap, then more
    awake time -- and the kill must come from the AWAKE total, never the wall."""
    killed: list[int] = []
    # 0, then 20 x 60s awake (1200s), one 8h gap, then 20 x 60s awake -> 2400s awake
    deltas = [0.0] + [60.0] * 20 + [8 * 3600.0] + [60.0] * 60
    proc = _FakeProc()
    rc, box = NF.await_within_box(proc, 3600, poll_s=0, gap_s=300,
                                  killer=lambda pid: killed.append(pid) or [pid],
                                  clock=_scripted_clock(deltas), sleeper=lambda _s: None)
    assert rc is None
    assert killed == [4242]
    assert box["awake_s"] == pytest.approx(3600.0)          # killed on awake, exactly
    assert box["slept_s"] == pytest.approx(8 * 3600.0)      # the standby, excluded
    assert box["elapsed_s"] == pytest.approx(3600.0 + 8 * 3600.0)
    assert len(box["sleep_gaps"]) == 1
    assert box["sleep_gaps"][0]["gap_s"] == pytest.approx(28800.0)
    assert proc.waited is True


def test_a_job_that_only_slept_is_never_killed():
    """Nine hours of wall clock, thirty seconds of them the job's."""
    killed: list[int] = []
    deltas = [0.0, 10.0, 9 * 3600.0, 10.0, 10.0]

    class _Exits(_FakeProc):
        def __init__(self):
            super().__init__()
            self.n = 0

        def poll(self):
            self.n += 1
            return None if self.n < 4 else 0

    rc, box = NF.await_within_box(_Exits(), 3600, poll_s=0, gap_s=300,
                                  killer=lambda pid: killed.append(pid) or [pid],
                                  clock=_scripted_clock(deltas), sleeper=lambda _s: None)
    assert rc == 0 and killed == []
    assert box["awake_s"] == pytest.approx(30.0)
    assert box["slept_s"] == pytest.approx(9 * 3600.0)


# --------------------------------------------------- the power-plan refusal

@pytest.mark.parametrize("raw,expected", [
    ("  Current AC Power Setting Index: 0x00000000", 0),
    ("  Current AC Power Setting Index: 0x00000708", 1800),
    ("  Current AC Power Setting Index: 900", 900),
])
def test_the_powercfg_parser_reads_the_ac_index(raw: str, expected: int):
    secs, evidence = NF.parse_standby_ac(
        "Power Scheme GUID: 381b4222 (Balanced)\n"
        "  Subgroup GUID: 238c9fa8 (Sleep)\n"
        f"{raw}\n"
        "  Current DC Power Setting Index: 0x00000384\n")
    assert secs == expected and "AC Power Setting Index" in evidence


def test_output_without_an_ac_index_is_CANNOT_DETERMINE():
    secs, evidence = NF.parse_standby_ac("Power Scheme GUID: 381b4222 (Balanced)\n")
    assert secs is None and "no AC setting index" in evidence


def test_the_factory_refuses_to_start_when_the_plan_allows_sleep(monkeypatch, capsys):
    monkeypatch.delenv("AEGIS_NIGHT_ALLOW_SLEEP", raising=False)
    monkeypatch.setattr(NF, "standby_timeout_ac", lambda: (1800, "Current AC Power Setting Index: 0x708"))
    refusal = NF.refuse_if_the_machine_may_sleep()
    assert refusal is not None
    assert refusal.startswith("REFUSED:")
    assert NF.POWERCFG_FIX == "powercfg /change standby-timeout-ac 0"
    assert NF.POWERCFG_FIX in refusal, "a refusal that does not print the fix is a wall"


def test_never_sleeps_and_cannot_determine_both_start(monkeypatch):
    monkeypatch.delenv("AEGIS_NIGHT_ALLOW_SLEEP", raising=False)
    monkeypatch.setattr(NF, "standby_timeout_ac", lambda: (0, "never"))
    assert NF.refuse_if_the_machine_may_sleep() is None
    # CANNOT DETERMINE must not be a gate that can never go green off Windows
    monkeypatch.setattr(NF, "standby_timeout_ac", lambda: (None, "no powercfg"))
    assert NF.refuse_if_the_machine_may_sleep() is None


def test_the_env_override_lets_a_test_start_a_sleepy_machine(monkeypatch):
    monkeypatch.setenv("AEGIS_NIGHT_ALLOW_SLEEP", "1")

    def _boom():
        raise AssertionError("the override must short-circuit before powercfg runs")

    monkeypatch.setattr(NF, "standby_timeout_ac", _boom)
    assert NF.refuse_if_the_machine_may_sleep() is None


def test_main_returns_three_and_runs_nothing_when_it_refuses(monkeypatch, capsys):
    monkeypatch.setattr(NF, "refuse_if_the_machine_may_sleep", lambda: "REFUSED: stub")
    monkeypatch.setattr(NF, "gpu_line", lambda: "GPU: --")

    def _never(*a, **k):
        raise AssertionError("a refused night must not run a job")

    monkeypatch.setattr(NF, "run_job", _never)
    assert NF.main(["--job", "D1_reaction_book"]) == 3
    assert "REFUSED: stub" in capsys.readouterr().out


# ------------------------------------------------------------- the kill gesture

def test_the_kill_names_pids_and_never_an_image_name():
    """CLAUDE.md session protocol 6. Read the AST, not the text: the module
    docstring and the comments EXPLAIN the banned gesture, and a grep-shaped
    guard that cannot tell an explanation from an instance gets the rationale
    deleted to make the suite green."""
    tree = ast.parse((REPO / "scripts" / "night_factory.py").read_text(encoding="utf-8"))
    literals: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue                                        # a docstring, not code
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            literals.append(node.value)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)
    executable = [s for s in literals if s not in docstrings]
    assert "taskkill" in executable, "the Windows kill is gone"
    for banned in ("/IM", "/im"):
        assert banned not in executable, f"kill by image name: {banned}"
    assert "/PID" in executable and "/T" in executable and "/F" in executable


def test_the_gpu_line_never_raises_even_with_no_gpu(monkeypatch):
    def _no_smi(*a, **k):
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr(subprocess, "run", _no_smi)
    assert NF.gpu_line().startswith("GPU: --")
