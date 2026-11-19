"""CH-59: `scripts.universe_refresh` rebuilds the funnel candidate set and the universe graph
out of process and exits non-zero unless each answer moved or was already fresh.

Children here are a small fake script under tmp_path, injected through `commands=`; the
real builders are never started. Every stamp is derived from the clock at test time, no
network is touched (the DNS gate is injected) and the live data folder is never read.
"""

from __future__ import annotations

import json
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import config as C
from backend.services import system_health as SH
from backend.services import task_receipts as TR
from backend.services import universe_refresh as UR
from scripts import universe_refresh as CLI

FAKE = r'''
import json, sys, time
from datetime import datetime, timezone
from pathlib import Path
kind, mode, out, n = sys.argv[1], sys.argv[2], Path(sys.argv[3]), int(sys.argv[4])
stamp = sys.argv[5] if len(sys.argv) > 5 else datetime.now(timezone.utc).isoformat(timespec="seconds")
marker = Path(sys.argv[0]).with_name("started.log")
with open(marker, "a", encoding="utf-8") as fh:
    fh.write(f"{kind} {mode} {out}\n")
if mode == "refuse":
    print("REFUSED: Stage 0 could not retrieve a universe (HTTP 503)")
    print("the previous snapshot is untouched")
    sys.exit(2)
if mode == "crash":
    print("Traceback: boom")
    sys.exit(7)
if mode == "noop":
    sys.exit(0)
if mode == "sleep":
    time.sleep(60)
if kind == "funnel":
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"generated_at": stamp, "stages": {"stage4_candidates": n}, "failures": {},
                               "candidates": [{"ticker": f"T{i}"} for i in range(n)]}), encoding="utf-8")
    sys.exit(0)
build = f"ug_{time.time_ns()}"
(out / build).mkdir(parents=True)
(out / build / "receipt.json").write_text(json.dumps(
    {"build_id": build, "built_utc": stamp, "as_of": stamp[:10], "status": "DEGRADED",
     "degraded_inputs": ["event_response weights"], "panel_last_session": stamp[:10],
     "counts": {"n_nodes": n, "n_edges": n * 10}}), encoding="utf-8")
(out / "latest.json").write_text(json.dumps({"build_id": build, "as_of": stamp[:10], "built_utc": stamp}),
                                 encoding="utf-8")
sys.exit(3)
'''


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def _ago(hours: float) -> str:
    return _iso(datetime.now(timezone.utc) - timedelta(hours=hours))


class World:
    """A synthetic data root: a live funnel, a live graph, a receipt folder, a fake builder."""

    def __init__(self, tmp: Path, *, funnel_stamp, graph_stamp, n_cands: int = 25, n_nodes: int = 500):
        self.tmp = tmp
        self.root = tmp / "data" / "optimus"
        self.out = tmp / "receipts"
        self.funnel = tmp / "data" / "funnel_night10.json"
        self.graph = self.root / "universe_graph"
        self.fake = tmp / "fake" / "fake_builder.py"
        self.fake.parent.mkdir(parents=True)
        self.fake.write_text(FAKE, encoding="utf-8")
        self.root.mkdir(parents=True)
        self.funnel.write_text(json.dumps({"generated_at": funnel_stamp,
                                           "candidates": [{"ticker": f"O{i}"} for i in range(n_cands)]}),
                               encoding="utf-8")
        build = self.graph / "ug_old"
        build.mkdir(parents=True)
        (build / "receipt.json").write_text(json.dumps(
            {"build_id": "ug_old", "built_utc": graph_stamp, "counts": {"n_nodes": n_nodes, "n_edges": n_nodes * 10}}),
            encoding="utf-8")
        (self.graph / "latest.json").write_text(json.dumps({"build_id": "ug_old", "built_utc": graph_stamp}),
                                                encoding="utf-8")

    def funnel_cmd(self, mode: str = "ok", n: int = 25, stamp: str | None = None):
        return lambda out: [sys.executable, str(self.fake), "funnel", mode, str(out), str(n)] + ([stamp] if stamp else [])

    def graph_cmd(self, mode: str = "ok", n: int = 500, n_live: int | None = None, stamp: str | None = None):
        def cmd(data_root: Path, out: Path) -> list[str]:
            size = n if (n_live is None or "graph_rehearsal" in str(out)) else n_live
            return [sys.executable, str(self.fake), "graph", mode, str(out), str(size)] + ([stamp] if stamp else [])
        return cmd

    def started(self) -> list[str]:
        p = self.fake.with_name("started.log")
        return p.read_text(encoding="utf-8").splitlines() if p.exists() else []

    def run(self, *, funnel=None, graph=None, network=lambda: (True, {"unresolved": {}}), **kw) -> dict:
        return UR.refresh(data_root=self.root, out=self.out, funnel_path=self.funnel, graph_dir=self.graph,
                          commands={"funnel": funnel or self.funnel_cmd(), "graph": graph or self.graph_cmd()},
                          network=network, **kw)


@pytest.fixture
def stale(tmp_path) -> World:
    return World(tmp_path, funnel_stamp=_ago(80), graph_stamp=_ago(200))


def _live_funnel(w: World) -> dict:
    return json.loads(w.funnel.read_text(encoding="utf-8"))


# ───────────────────────────── REFRESHED, read back from the live file

def test_both_stages_refresh_and_the_receipt_states_before_and_after(stale):
    before_f = _live_funnel(stale)["generated_at"]
    r = stale.run()
    f, g = r["stages"]["funnel"], r["stages"]["graph"]
    assert (f["status"], g["status"], r["overall_rc"]) == ("REFRESHED", "REFRESHED", 0)
    assert f["stamp_before"] == before_f and f["stamp_after"] == _live_funnel(stale)["generated_at"] != before_f
    assert (f["count_before"], f["count_after"], f["child_rc"]) == (25, 25, 0)
    assert Path(f["archive"]).exists() and Path(f["archive"]).parent.name == "funnel_history"
    latest = json.loads((stale.graph / "latest.json").read_text(encoding="utf-8"))
    assert g["stamp_after"] == latest["built_utc"] and g["build_id_after"] == latest["build_id"] != "ug_old"
    assert (g["count_before"], g["count_after"], g["edges_after"]) == (500, 500, 5000)
    # rc 3 (written, an input degraded) is a written graph, and what was degraded is recorded
    assert (g["rehearsal_rc"], g["child_rc"], g["degraded_inputs"]) == (3, 3, ["event_response weights"])
    for s in (f, g):
        assert isinstance(s["seconds"], float) and s["freshness"]["verdict"] == "STALE"
    disk = json.loads(Path(r["receipt_path"]).read_text(encoding="utf-8"))
    assert disk["overall_rc"] == 0 and disk["stages"]["funnel"]["status"] == "REFRESHED"
    assert disk["llm_spend_usd"] == 0.0 and Path(disk["paths"]["log"]).exists()
    assert not (stale.out / "work").exists()                 # staging is removed after a clean run
    assert not list(stale.funnel.parent.glob("*.tmp"))


def test_fresh_answers_are_skipped_and_no_child_starts(tmp_path):
    w = World(tmp_path, funnel_stamp=_ago(1), graph_stamp=_ago(2))
    raw = w.funnel.read_bytes()
    r = w.run(network=lambda: pytest.fail("the network gate ran for a fresh answer"))
    assert [s["status"] for s in r["stages"].values()] == ["SKIPPED_FRESH", "SKIPPED_FRESH"]
    assert r["overall_rc"] == 0 and w.started() == [] and w.funnel.read_bytes() == raw
    assert r["stages"]["funnel"]["stamp_before"] == r["stages"]["funnel"]["stamp_after"]


def test_force_rebuilds_a_fresh_answer(tmp_path):
    w = World(tmp_path, funnel_stamp=_ago(1), graph_stamp=_ago(2))
    r = w.run(force=True)
    assert [s["status"] for s in r["stages"].values()] == ["REFRESHED", "REFRESHED"] and r["overall_rc"] == 0


@pytest.mark.parametrize("stamp", [None, "", "last tuesday", 20261116])
def test_an_undateable_stamp_is_unknown_and_rebuilt_never_fresh(tmp_path, stamp):
    w = World(tmp_path, funnel_stamp=stamp, graph_stamp=stamp)
    r = w.run()
    for s in r["stages"].values():
        assert s["freshness"]["verdict"] == "UNKNOWN" and s["status"] == "REFRESHED"


def test_a_future_stamp_is_unknown_not_fresh(tmp_path):
    w = World(tmp_path, funnel_stamp=_ago(-48), graph_stamp=_ago(-48))
    r = w.run(only=("funnel",))
    f = r["stages"]["funnel"]
    # rebuilt; the new stamp is OLDER than the bogus future one, so the run cannot claim it moved
    assert f["freshness"]["verdict"] == "UNKNOWN" and f["status"] == "UNMOVED" and r["overall_rc"] != 0


# ───────────────────────────── UNMOVED: rc 0 is not a refresh

def test_rc0_with_nothing_written_is_unmoved_and_red(stale):
    raw = stale.funnel.read_bytes()
    r = stale.run(funnel=stale.funnel_cmd("noop"), only=("funnel",))
    f = r["stages"]["funnel"]
    assert (f["status"], f["child_rc"]) == ("UNMOVED", 0) and r["overall_rc"] == C.UNIVERSE_REFRESH_RC_FAILED
    assert stale.funnel.read_bytes() == raw and f["stamp_after"] == f["stamp_before"]


def test_rc0_with_the_same_stamp_is_unmoved(stale):
    old = _live_funnel(stale)["generated_at"]
    r = stale.run(funnel=stale.funnel_cmd("ok", stamp=old), graph=stale.graph_cmd("noop"))
    assert r["stages"]["funnel"]["status"] == "UNMOVED" and "still" in r["stages"]["funnel"]["detail"]
    assert r["stages"]["graph"]["status"] == "UNMOVED" and r["overall_rc"] == C.UNIVERSE_REFRESH_RC_FAILED
    assert _live_funnel(stale)["generated_at"] == old


def test_a_stamp_older_than_the_run_is_unmoved(stale):
    r = stale.run(funnel=stale.funnel_cmd("ok", stamp=_ago(3)), only=("funnel",))
    assert r["stages"]["funnel"]["status"] == "UNMOVED" and "predates" in r["stages"]["funnel"]["detail"]


# ───────────────────────────── REFUSED / FAILED children

def test_a_refusing_builder_is_refused_with_its_own_line_and_the_old_file_stays(stale):
    raw = stale.funnel.read_bytes()
    r = stale.run(funnel=stale.funnel_cmd("refuse"), graph=stale.graph_cmd("refuse"))
    f, g = r["stages"]["funnel"], r["stages"]["graph"]
    assert f["status"] == g["status"] == "REFUSED(CHILD_REFUSED)" and f["child_rc"] == 2 and g["rehearsal_rc"] == 2
    assert "Stage 0 could not retrieve a universe" in f["detail"]
    assert r["overall_rc"] == C.UNIVERSE_REFRESH_RC_REFUSED and stale.funnel.read_bytes() == raw
    assert all("graph_rehearsal" in ln for ln in stale.started() if ln.startswith("graph"))


def test_a_crashing_builder_is_failed(stale):
    r = stale.run(funnel=stale.funnel_cmd("crash"), only=("funnel",))
    assert r["stages"]["funnel"]["status"] == "FAILED(CHILD_RC_7)" and r["overall_rc"] == C.UNIVERSE_REFRESH_RC_FAILED


def test_a_hung_builder_is_killed_at_its_timeout(stale, monkeypatch):
    monkeypatch.setattr(C, "UNIVERSE_REFRESH_FUNNEL_TIMEOUT_S", 1.0)
    r = stale.run(funnel=stale.funnel_cmd("sleep"), only=("funnel",))
    f = r["stages"]["funnel"]
    assert f["status"] == "FAILED(TIMEOUT)" and f["seconds"] < 30 and r["overall_rc"] == C.UNIVERSE_REFRESH_RC_FAILED


def test_a_builder_that_cannot_start_is_failed(stale):
    r = stale.run(funnel=lambda out: [str(stale.tmp / "no_such_interpreter.exe"), "-m", "x"], only=("funnel",))
    assert r["stages"]["funnel"]["status"] == "FAILED(CHILD_NOT_STARTED)" and r["overall_rc"] != 0


# ───────────────────────────── the shrink guard

@pytest.mark.parametrize("n,reason", [(0, "EMPTY"), (5, "SHRINK"), (12, "SHRINK")])
def test_a_smaller_or_empty_candidate_set_never_replaces_the_live_file(stale, n, reason):
    raw = stale.funnel.read_bytes()
    r = stale.run(funnel=stale.funnel_cmd("ok", n=n), only=("funnel",))
    f = r["stages"]["funnel"]
    assert f["status"] == f"REFUSED({reason})" and r["overall_rc"] == C.UNIVERSE_REFRESH_RC_REFUSED
    assert stale.funnel.read_bytes() == raw and (f["count_before"], f["count_after"]) == (25, 25)
    assert f["staged"]["count"] == n and Path(f["staged_path"]).exists()      # kept for inspection
    assert not (stale.funnel.parent / "funnel_history").exists()


def test_a_candidate_set_at_the_fraction_is_accepted(stale):
    r = stale.run(funnel=stale.funnel_cmd("ok", n=13), only=("funnel",))
    assert r["stages"]["funnel"]["status"] == "REFRESHED" and r["stages"]["funnel"]["count_after"] == 13


@pytest.mark.parametrize("n,reason", [(0, "EMPTY"), (100, "SHRINK")])
def test_a_smaller_graph_is_refused_at_the_rehearsal_and_the_live_build_never_starts(stale, n, reason):
    raw = (stale.graph / "latest.json").read_bytes()
    r = stale.run(graph=stale.graph_cmd("ok", n=n), only=("graph",))
    g = r["stages"]["graph"]
    assert g["status"] == f"REFUSED({reason})" and g["child_rc"] is None and g["rehearsal_rc"] == 3
    assert (stale.graph / "latest.json").read_bytes() == raw
    assert sorted(p.name for p in stale.graph.iterdir()) == ["latest.json", "ug_old"]
    assert len(stale.started()) == 1 and r["overall_rc"] == C.UNIVERSE_REFRESH_RC_REFUSED


def test_a_live_graph_build_that_shrank_after_a_good_rehearsal_is_rolled_back(stale):
    raw = (stale.graph / "latest.json").read_bytes()
    r = stale.run(graph=stale.graph_cmd("ok", n=500, n_live=40), only=("graph",))
    g = r["stages"]["graph"]
    assert g["status"] == "REFUSED(SHRINK_AFTER_WRITE)" and r["overall_rc"] == C.UNIVERSE_REFRESH_RC_REFUSED
    assert (stale.graph / "latest.json").read_bytes() == raw
    assert (g["build_id_after"], g["count_after"], g["stamp_after"]) == ("ug_old", 500, g["stamp_before"])
    assert g["rolled_back_from"].startswith("ug_") and (stale.graph / g["rolled_back_from"]).exists()


def test_a_first_graph_build_has_nothing_to_shrink_from(stale):
    import shutil
    shutil.rmtree(stale.graph)
    r = stale.run(graph=stale.graph_cmd("ok", n=7), only=("graph",))
    g = r["stages"]["graph"]
    assert g["status"] == "REFRESHED" and (g["count_before"], g["count_after"]) == (None, 7)


# ───────────────────────────── the network gate

def test_no_dns_is_refused_as_no_network_and_the_builder_never_starts(stale):
    net = {"hosts": ["finnhub.io"], "unresolved": {"finnhub.io": "gaierror"}, "waited_s": 180.0}
    r = stale.run(network=lambda: (False, net))
    f = r["stages"]["funnel"]
    assert f["status"] == "REFUSED(NO_NETWORK)" and f["reason"] == "NO_NETWORK" and f["child_rc"] is None
    assert "finnhub.io" in f["detail"] and "no credential was tested" in f["detail"]
    assert not any(ln.startswith("funnel") for ln in stale.started())
    # the graph reads local files only: it still runs, and the run is still red
    assert r["stages"]["graph"]["status"] == "REFRESHED" and r["overall_rc"] == C.UNIVERSE_REFRESH_RC_REFUSED


def test_wait_for_dns_gives_up_after_a_bounded_wait():
    clock = {"t": 0.0}
    slept = []

    def sleep(s: float) -> None:
        slept.append(s)
        clock["t"] += s

    def dead(host: str) -> None:
        raise socket.gaierror(11001, "getaddrinfo failed")

    ok, info = UR.wait_for_dns(("a.example", "b.example"), wait_s=30, poll_s=10, resolver=dead, sleep=sleep,
                               clock=lambda: clock["t"])
    assert ok is False and sorted(info["unresolved"]) == ["a.example", "b.example"]
    assert sum(slept) <= 30 and info["tries"] == len(slept) + 1 and "credentials were not tested" in info["check"]


def test_wait_for_dns_returns_as_soon_as_every_host_resolves():
    calls = {"n": 0}

    def flaky(host: str) -> None:
        calls["n"] += 1
        if calls["n"] < 3:
            raise socket.gaierror(11001, "getaddrinfo failed")

    ok, info = UR.wait_for_dns(("a.example",), wait_s=60, poll_s=1, resolver=flaky, sleep=lambda s: None,
                               clock=lambda: 0.0)
    assert ok is True and info["tries"] == 3 and info["unresolved"] == {}


# ───────────────────────────── the receipt name and the rc contract

def test_a_second_run_never_overwrites_the_first_receipt(stale):
    now = datetime.now(timezone.utc)
    a = stale.run(funnel=stale.funnel_cmd("refuse"), graph=stale.graph_cmd("refuse"), now=now)
    first = Path(a["receipt_path"]).read_bytes()
    b = stale.run(funnel=stale.funnel_cmd("refuse"), graph=stale.graph_cmd("refuse"), now=now)
    assert a["receipt_path"] != b["receipt_path"] and a["run_id"] != b["run_id"]
    assert Path(a["receipt_path"]).read_bytes() == first and Path(b["receipt_path"]).exists()
    assert a["run_id"] in Path(a["receipt_path"]).name and len(list(stale.out.glob("refresh_*.json"))) == 2


def test_write_new_json_takes_a_new_name_when_the_stem_exists(tmp_path):
    a = UR.write_new_json(tmp_path, "refresh_x", {"n": 1})
    b = UR.write_new_json(tmp_path, "refresh_x", {"n": 2})
    assert a != b and json.loads(a.read_text(encoding="utf-8")) == {"n": 1}
    assert json.loads(b.read_text(encoding="utf-8")) == {"n": 2} and not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("kinds,rc", [
    (("REFRESHED", "REFRESHED"), 0), (("SKIPPED_FRESH", "REFRESHED"), 0), (("SKIPPED_FRESH", "SKIPPED_FRESH"), 0),
    (("REFUSED", "REFRESHED"), 2), (("REFRESHED", "UNMOVED"), 1), (("FAILED", "SKIPPED_FRESH"), 1),
    (("REFUSED", "FAILED"), 1), (("REFUSED", "UNMOVED"), 1), (("SOMETHING_NEW", "REFRESHED"), 1), ((), 1)])
def test_overall_rc_is_zero_only_when_every_stage_is_green(kinds, rc):
    assert UR.overall_rc({f"s{i}": {"status_kind": k} for i, k in enumerate(kinds)}) == rc


def test_one_stage_failing_does_not_stop_the_other_and_a_raise_is_a_failed_stage(stale):
    def boom(out):
        raise RuntimeError("command builder broke")
    r = stale.run(funnel=boom)
    assert r["stages"]["funnel"]["status"] == "FAILED(STAGE_RAISED)" and r["stages"]["graph"]["status"] == "REFRESHED"
    assert r["overall_rc"] == C.UNIVERSE_REFRESH_RC_FAILED and Path(r["receipt_path"]).exists()


# ───────────────────────────── paths and the CLI

def test_the_live_funnel_is_the_sibling_of_the_resolved_data_root(tmp_path):
    root = tmp_path / "backend" / "data" / "optimus"
    root.mkdir(parents=True)
    p = UR.default_paths(root)
    assert p["funnel_path"] == root.resolve().parent / "funnel_night10.json"
    assert p["graph_dir"] == root / "universe_graph" and p["out"] == root / C.UNIVERSE_REFRESH_DIRNAME


def test_the_real_child_commands_run_the_builders_out_of_process(tmp_path):
    f = UR.funnel_command(tmp_path / "f.json")
    g = UR.graph_command(tmp_path / "root", tmp_path / "g")
    assert f[:3] == [sys.executable, "-m", "backend.services.opportunity_funnel"] and f[3] == "--out"
    assert g[:4] == [sys.executable, "-m", "backend.services.universe_graph", "build"]
    assert "--data-root" in g and "--out" in g
    assert not {"backend.services.opportunity_funnel", "backend.services.universe_graph"} & {
        v.__name__ for v in vars(UR).values() if hasattr(v, "__spec__") and hasattr(v, "__name__")}


def _cli_args(w: World) -> list[str]:
    return ["--data-root", str(w.root), "--out", str(w.out), "--funnel-path", str(w.funnel),
            "--graph-dir", str(w.graph)]


def test_cli_dry_run_prints_the_child_commands_and_writes_nothing(stale, capsys):
    assert CLI.main([*_cli_args(stale), "--dry-run"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["stages"]["funnel"]["would_run"] is True and plan["stages"]["graph"]["would_run"] is True
    assert plan["stages"]["funnel"]["child_cmds"][0][1:3] == ["-m", "backend.services.opportunity_funnel"]
    assert len(plan["stages"]["graph"]["child_cmds"]) == 2
    assert not stale.out.exists() and stale.started() == []


def test_cli_exit_code_is_the_receipts_overall_rc(stale, monkeypatch, capsys):
    monkeypatch.setattr(C, "UNIVERSE_REFRESH_NETWORK_HOSTS", ())          # no DNS lookup in a unit test
    monkeypatch.setattr(UR, "funnel_command", stale.funnel_cmd("refuse"))
    monkeypatch.setattr(UR, "graph_command", stale.graph_cmd("ok"))
    assert CLI.main(_cli_args(stale)) == C.UNIVERSE_REFRESH_RC_REFUSED
    out = capsys.readouterr().out
    assert "REFUSED(CHILD_REFUSED)" in out and "overall rc 2" in out
    monkeypatch.setattr(UR, "funnel_command", stale.funnel_cmd("ok"))
    # the graph was rebuilt a moment ago (stamps carry whole seconds), so only the funnel is re-run
    assert CLI.main([*_cli_args(stale), "--force", "--only", "funnel"]) == 0
    assert "graph" not in capsys.readouterr().out.split("overall")[0]
    assert len(list(stale.out.glob("refresh_*.json"))) == 2


# ───────────────────────────── the status page's reader

def _ctx(w: World) -> SH.ProbeCtx:
    return SH.ProbeCtx(optimus_dir=w.root, now=datetime.now(timezone.utc) + timedelta(seconds=1),
                       repo=w.tmp / "repo", prev_state={}, paths={"terminal_repo": w.tmp / "no_terminal"},
                       run=lambda argv, t: (None, "not installed"), pid_cmdline=lambda pid: None)


def _task() -> dict:
    return {"TaskName": "\\AegisUniverseRefresh", "Scheduled Task State": "Enabled", "Last Run Time": "-",
            "Last Result": "0", "Next Run Time": "-"}


def _run_into_default_out(w: World, **kw) -> dict:
    return UR.refresh(data_root=w.root, funnel_path=w.funnel, graph_dir=w.graph,
                      commands={"funnel": kw.pop("funnel", w.funnel_cmd()), "graph": kw.pop("graph", w.graph_cmd())},
                      network=lambda: (True, {"unresolved": {}}), **kw)


def test_the_task_is_declared_with_a_cadence_and_its_receipt_is_found(stale):
    assert C.HEALTH_TASK_CADENCE_H["AegisUniverseRefresh"] == 24.0
    assert TR.TASK_RECEIPT["AegisUniverseRefresh"].unregistered_ok
    assert TR.judge(_ctx(stale), "AegisUniverseRefresh", None).state == "UNREGISTERED"
    r = _run_into_default_out(stale)
    assert Path(r["receipt_path"]).parent == stale.root / C.UNIVERSE_REFRESH_DIRNAME
    j = TR.judge(_ctx(stale), "AegisUniverseRefresh", _task())
    assert j.state == "ALIVE_PROGRESSING" and "funnel REFRESHED 25->25" in j.detail


@pytest.mark.parametrize("funnel_mode,state", [("refuse", "REFUSED"), ("noop", "DEGRADED"), ("crash", "DEGRADED")])
def test_a_red_receipt_is_never_read_as_alive(stale, funnel_mode, state):
    _run_into_default_out(stale, funnel=stale.funnel_cmd(funnel_mode))
    j = TR.judge(_ctx(stale), "AegisUniverseRefresh", _task())
    assert j.state == state and "funnel" in j.detail


def test_a_run_that_skipped_everything_is_idle_and_no_receipt_is_stale(tmp_path):
    w = World(tmp_path, funnel_stamp=_ago(1), graph_stamp=_ago(2))
    assert TR.judge(_ctx(w), "AegisUniverseRefresh", _task()).state == "STALE"
    _run_into_default_out(w)
    assert TR.judge(_ctx(w), "AegisUniverseRefresh", _task()).state == "ALIVE_IDLE_EXPECTED"
