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
    # the shape `opportunity_funnel.run` writes (a healthy build carries only stage1_truncated)
    d = {"generated_at": stamp, "universe": {"screened": 5319},
         "stages": {"stage1_eligible": 1500, "stage2_shortlist": 250, "stage3_enriched": 40,
                    "stage4_candidates": n},
         "failures": {"stage1_truncated": "2793 names passed eligibility; kept 1500"},
         "candidates": [{"ticker": f"T{i}", "price": 10.0 + i, "score": 0.5, "quality": 0.3, "stage": 4}
                        for i in range(n)]}
    if mode == "degraded":      # 26 of 27 price batches failed; 25 names still come out
        d["stages"]["stage1_eligible"] = 31
        d["failures"].update(stage1_batches="26 batch(es) failed",
                             stage3="38 of 40 enrichment call(s) failed (http 429 x38)")
    elif mode == "nulls":
        d["candidates"] = [None] * n
    elif mode == "nullfields":
        for c in d["candidates"]:
            c["price"] = None
    elif mode == "smalluniverse":
        d["universe"]["screened"] = 900
    elif mode == "mildloss":
        d["failures"]["stage3"] = "3 of 42 enrichment call(s) failed (finnhub had no profitability fields x3)"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(d), encoding="utf-8")
    sys.exit(0)
build = f"ug_{time.time_ns()}"
if mode == "brokenlive":        # latest.json flipped to a build folder that holds nothing
    out.mkdir(parents=True, exist_ok=True)
    (out / "latest.json").write_text(json.dumps({"build_id": build, "built_utc": stamp}), encoding="utf-8")
    sys.exit(3)
edges = {"co_coverage": n * 2, "co_mention": 3, "customer": 1, "return_response": max(0, n * 7 - 7),
         "sector_member": n, "supplier": 1, "theme_member": 2}           # sums to 10 n
inputs = [{"input": k, "status": "OK"} for k in ("sector_map", "theme_lists", "co_coverage", "co_mention")]
inputs.append({"input": "event_response weights", "status": "MISSING"})
rc = 3
if mode == "lostinputs":        # the co-coverage input went missing; total edges barely move
    inputs[2]["status"] = "MISSING"
    edges["return_response"] += edges.pop("co_coverage")
elif mode == "kindlost":        # no input reports degraded, but one edge kind is gone
    edges["return_response"] += edges.pop("co_coverage")
elif mode == "noinputs":
    inputs = None
elif mode == "rc3clean":        # exit 3 although nothing is degraded
    inputs[-1]["status"] = "OK"
degraded = [r["input"] for r in inputs or [] if r["status"] not in ("OK", "NOT_USED")]
if mode == "noinputs":
    degraded = ["event_response weights"]
(out / build).mkdir(parents=True)
for f in ("nodes.parquet", "edges.parquet"):
    (out / build / f).write_bytes(b"PAR1")
rec = {"build_id": build, "built_utc": stamp, "as_of": stamp[:10],
       "status": "DEGRADED" if degraded else "OK", "degraded_inputs": degraded,
       "panel_last_session": stamp[:10],
       "counts": {"n_nodes": n, "n_edges": sum(edges.values()), "edges": edges}}
if inputs is not None:
    rec["inputs"] = inputs
(out / build / "receipt.json").write_text(json.dumps(rec), encoding="utf-8")
(out / "latest.json").write_text(json.dumps({"build_id": build, "as_of": stamp[:10], "built_utc": stamp}),
                                 encoding="utf-8")
sys.exit(rc)
'''


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def _ago(hours: float) -> str:
    return _iso(datetime.now(timezone.utc) - timedelta(hours=hours))


def live_funnel_payload(stamp, n: int = 25, **over) -> dict:
    """A live funnel in the shape the builder writes (the 2026-11-16 file's fields)."""
    d = {"generated_at": stamp, "universe": {"screened": 5319},
         "stages": {"stage1_eligible": 1500, "stage2_shortlist": 250, "stage3_enriched": 40,
                    "stage4_candidates": n},
         "failures": {"stage1_truncated": "2793 names passed eligibility; kept 1500"},
         "candidates": [{"ticker": f"O{i}", "price": 20.0 + i, "score": 0.4, "quality": 0.2, "stage": 4}
                        for i in range(n)]}
    d.update(over)
    return d


def graph_edges(n: int) -> dict:
    return {"co_coverage": n * 2, "co_mention": 3, "customer": 1, "return_response": max(0, n * 7 - 7),
            "sector_member": n, "supplier": 1, "theme_member": 2}


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
        self.funnel.write_text(json.dumps(live_funnel_payload(funnel_stamp, n_cands)), encoding="utf-8")
        self.write_graph("ug_old", graph_stamp, n_nodes)

    def write_graph(self, build_id: str, stamp, n_nodes: int = 500, receipt: bool = True) -> None:
        build = self.graph / build_id
        build.mkdir(parents=True)
        for f in ("nodes.parquet", "edges.parquet"):
            (build / f).write_bytes(b"PAR1")
        if receipt:
            (build / "receipt.json").write_text(json.dumps(
                {"build_id": build_id, "built_utc": stamp, "status": "DEGRADED",
                 "degraded_inputs": ["event_response weights"],
                 "inputs": [{"input": "sector_map", "status": "OK"},
                            {"input": "event_response weights", "status": "MISSING"}],
                 "counts": {"n_nodes": n_nodes, "n_edges": n_nodes * 10, "edges": graph_edges(n_nodes)}}),
                encoding="utf-8")
        (self.graph / "latest.json").write_text(json.dumps({"build_id": build_id, "built_utc": stamp}),
                                                encoding="utf-8")

    def funnel_cmd(self, mode: str = "ok", n: int = 25, stamp: str | None = None):
        return lambda out: [sys.executable, str(self.fake), "funnel", mode, str(out), str(n)] + ([stamp] if stamp else [])

    def graph_cmd(self, mode: str = "ok", n: int = 500, n_live: int | None = None, stamp: str | None = None,
                  mode_live: str | None = None):
        def cmd(data_root: Path, out: Path) -> list[str]:
            rehearsal = "graph_rehearsal" in str(out)
            size = n if (n_live is None or rehearsal) else n_live
            m = mode if (mode_live is None or rehearsal) else mode_live
            return [sys.executable, str(self.fake), "graph", m, str(out), str(size)] + ([stamp] if stamp else [])
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


def test_a_future_stamp_is_unknown_not_fresh_and_does_not_block_a_good_build(tmp_path):
    # N1: the bogus future stamp was judged UNKNOWN, so the new build is not required to be
    # later than it; before the fix both stages were UNMOVED until the clock passed the stamp
    w = World(tmp_path, funnel_stamp=_ago(-48), graph_stamp=_ago(-48))
    r = w.run()
    for s in r["stages"].values():
        assert s["freshness"]["verdict"] == "UNKNOWN" and s["status"] == "REFRESHED"
    assert r["overall_rc"] == 0


def test_a_new_stamp_equal_to_an_untrusted_old_one_is_still_unmoved(tmp_path):
    future = _ago(-48)
    w = World(tmp_path, funnel_stamp=future, graph_stamp=_ago(200))
    r = w.run(funnel=w.funnel_cmd("ok", stamp=future), only=("funnel",))
    assert r["stages"]["funnel"]["status"] == "UNMOVED"


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
    r = stale.run(graph=stale.graph_cmd("ok", n=7), only=("graph",), allow_create=True)
    g = r["stages"]["graph"]
    assert g["status"] == "REFRESHED" and (g["count_before"], g["count_after"]) == (None, 7)


# ───────────────────────────── B1: a degraded funnel build never replaces a good one

def test_a_degraded_funnel_build_with_the_usual_count_is_refused(stale):
    raw = stale.funnel.read_bytes()
    r = stale.run(funnel=stale.funnel_cmd("degraded"), only=("funnel",))
    f = r["stages"]["funnel"]
    assert f["status_kind"] == "REFUSED" and f["reason"] == "DEGRADED_BUILD"
    assert f["status"].startswith("REFUSED(DEGRADED_BUILD: ") and r["overall_rc"] == C.UNIVERSE_REFRESH_RC_REFUSED
    assert "stage1_batches" in f["detail"] and "stage3" in f["detail"] and "stage1_eligible" in f["detail"]
    assert stale.funnel.read_bytes() == raw and not (stale.funnel.parent / "funnel_history").exists()
    # the builder's failure TEXT is kept in the receipt, not only its keys
    assert "26 batch(es) failed" in f["staged"]["failures"]["stage1_batches"]
    assert Path(f["staged_path"]).exists()


@pytest.mark.parametrize("mode,needle", [("nulls", "not a dict"), ("nullfields", "price"),
                                         ("smalluniverse", "screened")])
def test_a_funnel_build_with_bad_candidates_or_a_shrunken_universe_is_refused(stale, mode, needle):
    raw = stale.funnel.read_bytes()
    r = stale.run(funnel=stale.funnel_cmd(mode), only=("funnel",))
    f = r["stages"]["funnel"]
    assert f["reason"] == "DEGRADED_BUILD" and needle in f["detail"] and r["overall_rc"] != 0
    assert stale.funnel.read_bytes() == raw


def test_the_benign_failure_key_and_a_small_enrichment_loss_are_accepted(stale):
    r = stale.run(funnel=stale.funnel_cmd("mildloss"), only=("funnel",))
    assert r["stages"]["funnel"]["status"] == "REFRESHED" and r["overall_rc"] == 0


# ───────────────────────────── S1: exit 3 is accepted only for the missing event weights

@pytest.mark.parametrize("mode,needle", [("lostinputs", "co_coverage"), ("noinputs", "inputs"),
                                         ("rc3clean", "exit 3"), ("kindlost", "co_coverage")])
def test_a_graph_build_with_a_new_degradation_is_refused_at_the_rehearsal(stale, mode, needle):
    raw = (stale.graph / "latest.json").read_bytes()
    r = stale.run(graph=stale.graph_cmd(mode), only=("graph",))
    g = r["stages"]["graph"]
    assert g["status_kind"] == "REFUSED" and g["reason"] == "DEGRADED_BUILD" and needle in g["detail"]
    assert g["child_rc"] is None and len(stale.started()) == 1            # the live build never started
    assert (stale.graph / "latest.json").read_bytes() == raw and r["overall_rc"] == C.UNIVERSE_REFRESH_RC_REFUSED


def test_a_live_graph_build_that_lost_an_input_after_a_good_rehearsal_is_rolled_back(stale):
    raw = (stale.graph / "latest.json").read_bytes()
    r = stale.run(graph=stale.graph_cmd("ok", mode_live="lostinputs"), only=("graph",))
    g = r["stages"]["graph"]
    assert g["reason"] == "DEGRADED_BUILD_AFTER_WRITE" and r["overall_rc"] == C.UNIVERSE_REFRESH_RC_REFUSED
    assert (stale.graph / "latest.json").read_bytes() == raw and g["build_id_after"] == "ug_old"


def test_n3_a_live_graph_left_unreadable_is_rolled_back(stale):
    raw = (stale.graph / "latest.json").read_bytes()
    r = stale.run(graph=stale.graph_cmd("ok", mode_live="brokenlive"), only=("graph",))
    g = r["stages"]["graph"]
    assert g["status_kind"] in ("UNMOVED", "REFUSED", "FAILED") and r["overall_rc"] != 0
    assert (stale.graph / "latest.json").read_bytes() == raw and g["rolled_back_from"].startswith("ug_")
    assert UR.read_graph(stale.graph)["error"] is None


# ───────────────────────────── S2: a fresh stamp over a bad answer is rebuilt, not skipped

def test_a_fresh_but_empty_funnel_is_rebuilt(tmp_path):
    w = World(tmp_path, funnel_stamp=_ago(1), graph_stamp=_ago(1), n_cands=0)
    r = w.run(only=("funnel",))
    f = r["stages"]["funnel"]
    assert f["status"] == "REFRESHED" and f["count_after"] == 25 and "content" in f["freshness"]["why"]


def test_a_fresh_but_degraded_funnel_is_rebuilt(tmp_path):
    w = World(tmp_path, funnel_stamp=_ago(1), graph_stamp=_ago(1))
    d = json.loads(w.funnel.read_text(encoding="utf-8"))
    d["failures"]["stage1_batches"] = "20 batch(es) failed"
    w.funnel.write_text(json.dumps(d), encoding="utf-8")
    assert w.run(only=("funnel",))["stages"]["funnel"]["status"] == "REFRESHED"


@pytest.mark.parametrize("damage", ["no_receipt", "no_nodes"])
def test_a_fresh_graph_whose_build_is_incomplete_is_rebuilt(tmp_path, damage):
    w = World(tmp_path, funnel_stamp=_ago(1), graph_stamp=_ago(1))
    if damage == "no_receipt":
        (w.graph / "ug_old" / "receipt.json").unlink()
    else:
        (w.graph / "ug_old" / "nodes.parquet").unlink()
    r = w.run(only=("graph",))
    assert r["stages"]["graph"]["status"] == "REFRESHED"


def test_s6_a_second_run_after_a_success_is_a_cheap_skip(stale):
    assert stale.run()["overall_rc"] == 0
    n = len(stale.started())
    r = stale.run(network=lambda: pytest.fail("the network gate ran for a fresh answer"))
    assert [s["status"] for s in r["stages"].values()] == ["SKIPPED_FRESH", "SKIPPED_FRESH"]
    assert r["overall_rc"] == 0 and len(stale.started()) == n


# ───────────────────────────── S3: a missing live answer is never silently created

def test_a_missing_live_funnel_is_refused_and_never_created(stale):
    stale.funnel.unlink()
    r = stale.run(only=("funnel",))
    f = r["stages"]["funnel"]
    assert f["status"] == "REFUSED(LIVE_FILE_ABSENT)" and r["overall_rc"] == C.UNIVERSE_REFRESH_RC_REFUSED
    assert not stale.funnel.exists() and stale.started() == []


def test_a_missing_live_funnel_folder_is_refused(tmp_path):
    w = World(tmp_path, funnel_stamp=_ago(80), graph_stamp=_ago(200))
    typo = tmp_path / "dta" / "funnel_night10.json"
    r = UR.refresh(data_root=w.root, out=w.out, funnel_path=typo, graph_dir=w.graph, only=("funnel",),
                   commands={"funnel": w.funnel_cmd()}, network=lambda: (True, {"unresolved": {}}))
    assert r["stages"]["funnel"]["reason"] == "LIVE_FILE_ABSENT" and not typo.parent.exists()


def test_allow_create_builds_the_first_funnel(stale):
    stale.funnel.unlink()
    r = stale.run(only=("funnel",), allow_create=True)
    assert r["stages"]["funnel"]["status"] == "REFRESHED" and stale.funnel.exists()


def test_a_missing_live_graph_is_refused_unless_allowed(stale):
    import shutil
    shutil.rmtree(stale.graph)
    r = stale.run(only=("graph",))
    assert r["stages"]["graph"]["status"] == "REFUSED(LIVE_FILE_ABSENT)" and stale.started() == []
    assert not stale.graph.exists()


# ───────────────────────────── S4: bounded run time, a receipt that survives a kill

def test_the_worst_case_run_time_is_under_fifty_minutes():
    worst = (C.UNIVERSE_REFRESH_NETWORK_WAIT_S + C.UNIVERSE_REFRESH_FUNNEL_TIMEOUT_S
             + 2 * C.UNIVERSE_REFRESH_GRAPH_TIMEOUT_S
             + C.UNIVERSE_REFRESH_REPLACE_RETRIES * C.UNIVERSE_REFRESH_REPLACE_RETRY_S * 4)
    assert worst < C.UNIVERSE_REFRESH_MAX_RUN_S <= 50 * 60
    assert C.UNIVERSE_REFRESH_LOCK_MAX_AGE_S >= C.UNIVERSE_REFRESH_MAX_RUN_S


def test_a_killed_run_leaves_a_receipt_naming_the_stage_it_was_in(stale):
    def killed(cmd, log_path, timeout_s):
        raise KeyboardInterrupt("Task Scheduler stopped the task")
    with pytest.raises(KeyboardInterrupt):
        stale.run(runner=killed)
    (p,) = list(stale.out.glob("refresh_*.json"))
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["overall_status"] == "RUNNING" and d["overall_rc"] is None and d["in_progress"] == "funnel"
    assert d["stages"]["funnel"]["status_kind"] == "RUNNING" and d["updated_utc"]
    assert not (stale.out / C.UNIVERSE_REFRESH_LOCK_NAME).exists()        # released on the way out


# ───────────────────────────── S5: one instance at a time

def _lock(w: World, pid: int, started: datetime) -> Path:
    w.out.mkdir(parents=True, exist_ok=True)
    p = w.out / C.UNIVERSE_REFRESH_LOCK_NAME
    p.write_text(json.dumps({"pid": pid, "started_utc": _iso(started), "run_id": "other"}), encoding="utf-8")
    return p


def test_a_second_instance_is_refused_locked_and_starts_nothing(stale):
    import os
    lock = _lock(stale, os.getpid(), datetime.now(timezone.utc))
    raw = lock.read_bytes()
    r = stale.run()
    assert [s["status"] for s in r["stages"].values()] == ["REFUSED(LOCKED)", "REFUSED(LOCKED)"]
    assert r["overall_rc"] == C.UNIVERSE_REFRESH_RC_REFUSED and stale.started() == []
    assert lock.read_bytes() == raw and r["lock"]["held_by"]["pid"] == os.getpid()


def test_a_lock_of_a_dead_process_is_taken_over_and_recorded(stale):
    import subprocess
    p = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True)
    dead = int(p.stdout.strip())
    assert not UR.pid_alive(dead)
    _lock(stale, dead, datetime.now(timezone.utc))
    r = stale.run()
    assert r["overall_rc"] == 0 and r["lock"]["taken_over"]["pid"] == dead and "not alive" in r["lock"]["why"]
    assert not (stale.out / C.UNIVERSE_REFRESH_LOCK_NAME).exists()


def test_a_lock_older_than_the_longest_run_is_taken_over(stale):
    import os
    _lock(stale, os.getpid(), datetime.now(timezone.utc) - timedelta(seconds=C.UNIVERSE_REFRESH_LOCK_MAX_AGE_S + 60))
    r = stale.run()
    assert r["overall_rc"] == 0 and r["lock"]["taken_over"]["run_id"] == "other" and "older" in r["lock"]["why"]


# ───────────────────────────── N2: a reader holding the live file for a moment

def test_n2_a_busy_live_file_is_retried_then_promoted(stale, monkeypatch):
    monkeypatch.setattr(C, "UNIVERSE_REFRESH_REPLACE_RETRY_S", 0.01)
    real, calls = UR._os_replace, {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError(13, "the file is open in another process")
        real(src, dst)
    monkeypatch.setattr(UR, "_os_replace", flaky)
    r = stale.run(only=("funnel",))
    assert r["stages"]["funnel"]["status"] == "REFRESHED" and calls["n"] >= 3


def test_n2_a_live_file_busy_throughout_is_refused_and_nothing_is_partial(stale, monkeypatch):
    monkeypatch.setattr(C, "UNIVERSE_REFRESH_REPLACE_RETRY_S", 0.01)

    def busy(src, dst):
        raise PermissionError(13, "the file is open in another process")
    monkeypatch.setattr(UR, "_os_replace", busy)
    raw = stale.funnel.read_bytes()
    r = stale.run(only=("funnel",))
    f = r["stages"]["funnel"]
    assert f["status"] == "REFUSED(LIVE_FILE_BUSY)" and "PermissionError" in f["detail"]
    assert stale.funnel.read_bytes() == raw and not (stale.funnel.parent / "funnel_history").exists()
    assert not list(stale.funnel.parent.glob("*.tmp")) and r["overall_rc"] == C.UNIVERSE_REFRESH_RC_REFUSED


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


def test_a_second_archive_of_the_same_day_keeps_the_first(stale):
    a = stale.run(only=("funnel",))["stages"]["funnel"]
    first = Path(a["archive"]).read_bytes()
    later = _iso(UR.parse_stamp(a["stamp_after"]) + timedelta(seconds=2))
    hist = Path(a["archive"]).parent
    second = UR.archive_path(hist, later)
    assert second != Path(a["archive"]) and second.name.startswith(Path(a["archive"]).stem + "_")
    assert sorted([second.name, Path(a["archive"]).name])[-1] == second.name      # readers sort by name
    assert UR.archive_path(hist, "2001-01-01T00:00:00+00:00").name == "funnel_2001-01-01.json"
    assert Path(a["archive"]).read_bytes() == first


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
    assert f[:3] == [UR.child_python(), "-m", "backend.services.opportunity_funnel"] and f[3] == "--out"
    assert g[:4] == [UR.child_python(), "-m", "backend.services.universe_graph", "build"]
    assert "--data-root" in g and "--out" in g
    assert not {"backend.services.opportunity_funnel", "backend.services.universe_graph"} & {
        v.__name__ for v in vars(UR).values() if hasattr(v, "__spec__") and hasattr(v, "__name__")}


def test_a_windowless_parent_starts_its_children_under_python_exe(tmp_path, monkeypatch):
    (tmp_path / "python.exe").write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "pythonw.exe"))
    assert UR.child_python() == str(tmp_path / "python.exe")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "elsewhere" / "pythonw.exe"))
    assert UR.child_python() == str(tmp_path / "elsewhere" / "pythonw.exe")      # no sibling: unchanged


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


def _running_receipt(w: World, age_s: float) -> None:
    t = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    folder = w.root / C.UNIVERSE_REFRESH_DIRNAME
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"refresh_{t.strftime('%Y%m%dT%H%M%SZ')}_1.json").write_text(json.dumps(
        {"schema": UR.SCHEMA, "started_utc": _iso(t), "updated_utc": _iso(t), "finished_utc": None,
         "overall_status": "RUNNING", "overall_rc": None, "in_progress": "funnel",
         "stages": {"funnel": {"status": "RUNNING", "status_kind": "RUNNING"}}}), encoding="utf-8")


def test_a_receipt_of_a_run_in_progress_is_not_red_and_one_that_never_finished_is(stale):
    _running_receipt(stale, 60)
    j = TR.judge(_ctx(stale), "AegisUniverseRefresh", _task())
    assert j.state not in ("DEGRADED", "REFUSED", "STALE", "DEAD") and "running" in j.detail
    _running_receipt(stale, C.UNIVERSE_REFRESH_MAX_RUN_S + 600)
    for p in sorted((stale.root / C.UNIVERSE_REFRESH_DIRNAME).glob("refresh_*.json"))[1:]:
        p.unlink()                                                       # keep only the old one
    j = TR.judge(_ctx(stale), "AegisUniverseRefresh", _task())
    assert j.state == "DEGRADED" and "funnel" in j.detail


def test_cli_allow_create_reaches_the_run(stale, monkeypatch, capsys):
    monkeypatch.setattr(UR, "funnel_command", stale.funnel_cmd("ok"))
    monkeypatch.setattr(C, "UNIVERSE_REFRESH_NETWORK_HOSTS", ())
    stale.funnel.unlink()
    assert CLI.main([*_cli_args(stale), "--only", "funnel"]) == C.UNIVERSE_REFRESH_RC_REFUSED
    assert "LIVE_FILE_ABSENT" in capsys.readouterr().out and not stale.funnel.exists()
    assert CLI.main([*_cli_args(stale), "--only", "funnel", "--allow-create"]) == 0
    assert stale.funnel.exists()


def test_a_run_that_skipped_everything_is_idle_and_no_receipt_is_stale(tmp_path):
    w = World(tmp_path, funnel_stamp=_ago(1), graph_stamp=_ago(2))
    assert TR.judge(_ctx(w), "AegisUniverseRefresh", _task()).state == "STALE"
    _run_into_default_out(w)
    assert TR.judge(_ctx(w), "AegisUniverseRefresh", _task()).state == "ALIVE_IDLE_EXPECTED"
