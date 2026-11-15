"""CH-56 loop map: one status per declared link, from receipts and config only.

Every fixture is synthetic and under tmp_path; every date is derived from `now`.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import config as C
from backend.services import loop_map as LM
from scripts import loop_map as CLI

NOW = datetime.now(timezone.utc).replace(microsecond=0)
LIMITS = {"h1": 1, "h24": 24}


def iso(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat()


def wj(p: Path, obj) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


def wl(p: Path, rows: list) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def link(id_: str, producer: dict, consumer: dict, limit: str = "h24", **kw) -> dict:
    return {"id": id_, "from": kw.get("frm", "SENSE"), "to": kw.get("to", "UNIVERSE"), "src": id_ + " src",
            "dst": id_ + " dst", "roadmap": "CH-56", "limit": limit, "producer": producer,
            "consumer": consumer, "objects": kw.get("objects", ("EVENT", "DECISION", "run"))}


def prod(path: str, kind: str = "json", **kw) -> dict:
    return {"task": "T", "path": path, "kind": kind, "stamp": kw.get("stamp", ["utc"]), "id": kw.get("id", ["run"])}


def cites(path: str, kind: str = "json", cite=("cites",)) -> dict:
    return {"module": "m.consumer", "proof": "cites", "path": path, "kind": kind, "stamp": ["utc"],
            "cite": list(cite)}


NONE = {"module": None, "proof": "none"}


@pytest.fixture()
def world(tmp_path: Path) -> dict:
    """A data root at <tmp>/repo/backend/data, a release clone the journal points at, and
    a fallback config that DISAGREES with the clone (so reading the wrong one shows)."""
    root = tmp_path / "repo" / "backend" / "data"
    (root / "optimus").mkdir(parents=True)
    clone = tmp_path / "aegis-runtime-test"
    (clone / "backend").mkdir(parents=True)
    (clone / "backend" / "config.py").write_text(
        "import os\nFLAG_OFF = False\nFLAG_ON = True\nFLAG_ENV = os.getenv('X') == '1'\n", encoding="utf-8")
    (tmp_path / "repo" / "backend" / "config.py").write_text("FLAG_OFF = True\nFLAG_DC = False\n", encoding="utf-8")
    fallback = tmp_path / "fallback_config.py"
    fallback.write_text("FLAG_OFF = True\nFLAG_ON = False\nFLAG_ONLY_FALLBACK = False\n", encoding="utf-8")
    wl(root / "optimus" / "runtime_switch" / "runtime_task_runs.jsonl",
       [{"clone": str(clone), "utc": iso(2), "event": "end", "module": "scripts.consumer", "rc": 0}])
    LM._FLAG_CACHE.clear()
    return {"root": root, "clone": clone, "fallback": fallback, "tmp": tmp_path}


def run(world: dict, links: list[dict]) -> dict:
    rec = LM.build(world["root"], now=NOW, links=tuple(links), limits=LIMITS, fallback_config=world["fallback"])
    return {r["id"]: r for r in rec["links"]} | {"_rec": rec}


def test_one_link_of_each_status(world):
    root = world["root"]
    wj(root / "p" / "flow_1.json", {"utc": iso(2), "run": "run-aaaa-0001"})
    wj(root / "c" / "flow.json", {"utc": iso(1), "cites": "run-aaaa-0001"})
    wj(root / "p" / "stale.json", {"utc": iso(30), "run": "run-bbbb-0001"})
    wj(root / "p" / "fresh.json", {"utc": iso(1), "run": "run-cccc-0001"})
    wj(root / "p" / "nostamp.json", {"run": "run-dddd-0001"})
    out = run(world, [
        link("flowing", prod("p/flow_*.json"), cites("c/flow.json")),
        link("stale", prod("p/stale.json"), NONE),
        link("off", prod("p/fresh.json"), {"module": "m", "proof": "flag", "flag": "FLAG_OFF",
                                          "flag_module": "scripts.consumer", "flag_home": "release"}),
        link("no_consumer", prod("p/fresh.json"), NONE),
        link("absent", prod("p/never_written.json"), NONE),
        link("cannot", prod("p/nostamp.json"), NONE),
    ])
    assert {k: v["status"] for k, v in out.items() if k != "_rec"} == {
        "flowing": "FLOWING", "stale": "STALE", "off": "OFF", "no_consumer": "NO_CONSUMER",
        "absent": "ABSENT", "cannot": "CANNOT_DETERMINE"}
    rec = out["_rec"]
    assert rec["top_line"] == ("6 links: 1 flowing, 1 stale, 1 off, 1 no consumer, 1 absent, 1 cannot determine")
    assert rec["n_open"] == 5 and rec["loop_closed"] is False
    for r in rec["links"]:                       # every status carries its evidence path and a reason
        assert r["evidence_path"] and r["reason"] and r["reason_code"]
    assert "30.0 h" in out["stale"]["reason"]    # the age is printed
    assert "FLAG_OFF" in out["off"]["reason"] and str(world["clone"]) in out["off"]["reason"]
    assert out["no_consumer"]["reason_code"] == "NO_CONSUMER_DECLARED"


def test_consumer_citing_a_missing_producer_id_is_not_flowing(world):
    root = world["root"]
    wj(root / "p" / "a_1.json", {"utc": iso(1), "run": "run-real-0001"})
    wj(root / "c" / "a.json", {"utc": iso(1), "cites": "run-that-nobody-wrote"})
    wj(root / "c" / "b.json", {"utc": iso(1), "other": 1})
    out = run(world, [link("ghost", prod("p/a_*.json"), cites("c/a.json")),
                      link("nofield", prod("p/a_*.json"), cites("c/b.json")),
                      link("noreceipt", prod("p/a_*.json"), cites("c/never.jsonl", "jsonl")),
                      link("silent", prod("p/a_*.json"), {"module": "m.reader", "proof": "none", "note": "counts only"})])
    assert out["ghost"]["status"] == "NO_CONSUMER" and out["ghost"]["reason_code"] == "CITED_ID_NOT_FOUND"
    assert out["nofield"]["status"] == "NO_CONSUMER" and out["nofield"]["reason_code"] == "CONSUMER_CITES_NOTHING"
    assert out["noreceipt"]["status"] == "NO_CONSUMER" and out["noreceipt"]["reason_code"] == "CONSUMER_RECEIPT_ABSENT"
    assert out["silent"]["status"] == "NO_CONSUMER" and "consumer cites nothing" in out["silent"]["reason"]
    assert out["_rec"]["counts"]["FLOWING"] == 0


def test_consumer_citing_an_old_producer_receipt_is_stale_not_flowing(world):
    root = world["root"]
    wl(root / "p" / "runs.jsonl", [{"utc": iso(40), "run": "run-old-00001"}, {"utc": iso(1), "run": "run-new-00001"}])
    wj(root / "c" / "old.json", {"utc": iso(1), "cites": ["see run-old-00001 for details"]})
    wj(root / "c" / "new.json", {"utc": iso(1), "nested": [{"id": "run-new-00001"}]})
    out = run(world, [link("lagging", prod("p/runs.jsonl", "jsonl"), cites("c/old.json")),
                      link("current", prod("p/runs.jsonl", "jsonl"), cites("c/new.json", cite=("nested[*].id",)))])
    assert out["lagging"]["status"] == "STALE" and out["lagging"]["reason_code"] == "CITED_PRODUCER_STALE"
    assert out["current"]["status"] == "FLOWING"
    assert out["current"]["consumer"]["cited_producer"]["id"] == "run-new-00001"


def test_a_receipt_is_never_dated_by_file_time(world):
    """Both files are written NOW (fresh mtime). One says it is old, one says nothing."""
    root = world["root"]
    old = wj(root / "p" / "old.json", {"utc": iso(100), "run": "r1-00000001"})
    bare = wj(root / "p" / "bare.json", {"run": "r2-00000002"})
    wj(root / "p" / "future.json", {"utc": (NOW + timedelta(hours=5)).isoformat(), "run": "r3-00000003"})
    for p in (old, bare):
        os.utime(p, None)
    out = run(world, [link("old", prod("p/old.json"), NONE), link("bare", prod("p/bare.json"), NONE),
                      link("future", prod("p/future.json"), NONE)])
    assert out["old"]["status"] == "STALE"
    assert out["bare"]["status"] == "CANNOT_DETERMINE" and out["bare"]["reason_code"] == "PRODUCER_UNDATED"
    assert "never dated by file time" in out["bare"]["reason"]
    assert out["future"]["status"] == "CANNOT_DETERMINE"


def test_unreadable_newest_receipt_does_not_fall_back_to_an_older_one(world):
    root = world["root"]
    wj(root / "p" / "r_1.json", {"utc": iso(1), "run": "run-good-0001"})
    (root / "p" / "r_2.json").write_text("{ truncated", encoding="utf-8")
    wj(root / "p" / "empty.jsonl", {}).write_text("", encoding="utf-8")
    out = run(world, [link("torn", prod("p/r_*.json"), NONE), link("empty", prod("p/empty.jsonl", "jsonl"), NONE),
                      link("nolimit", prod("p/r_1.json"), NONE, limit="undeclared")])
    assert out["torn"]["status"] == "CANNOT_DETERMINE" and out["torn"]["reason_code"] == "PRODUCER_UNREADABLE"
    assert out["empty"]["status"] == "ABSENT"
    assert out["nolimit"]["status"] == "CANNOT_DETERMINE" and out["nolimit"]["reason_code"] == "NO_LIMIT"


def flag_link(id_: str, flag: str, **kw) -> dict:
    return link(id_, prod("p/fresh.json"), {"module": "m", "proof": "flag", "flag": flag,
                                            "flag_module": kw.get("module", "scripts.consumer"),
                                            "flag_home": kw.get("home", "release"), **kw.get("extra", {})})


def test_flag_is_read_from_the_checkout_the_task_ran_from(world):
    root = world["root"]
    wj(root / "p" / "fresh.json", {"utc": iso(1), "run": "run-cccc-0001"})
    wj(root / "c" / "k.json", {"utc": iso(1), "cites": "run-cccc-0001"})
    out = run(world, [
        flag_link("off_in_clone", "FLAG_OFF"),                       # clone False; data checkout + fallback True
        flag_link("on_no_cite", "FLAG_ON"),                          # clone True; fallback False
        flag_link("on_cited", "FLAG_ON", extra={"path": "c/k.json", "kind": "json", "stamp": ["utc"],
                                                "cite": ["cites"]}),
        flag_link("env", "FLAG_ENV"),
        flag_link("undefined", "FLAG_NOWHERE"),
        flag_link("data_home", "FLAG_OFF", home="data_checkout", module=None),
        flag_link("unknown_module", "FLAG_OFF", module="scripts.never_ran"),
    ])
    F = out["off_in_clone"]["consumer"]["flag"]
    assert out["off_in_clone"]["status"] == "OFF" and F["source"] == "release_of_module"
    assert Path(F["config"]) == world["clone"] / "backend" / "config.py"
    assert {o["source"]: o["value"] for o in F["others"]}["data_checkout"] is True   # the disagreement is printed
    assert out["on_no_cite"]["status"] == "NO_CONSUMER"              # a flag that is on proves nothing by itself
    assert out["on_cited"]["status"] == "FLOWING"
    assert out["env"]["status"] == "CANNOT_DETERMINE" and out["env"]["reason_code"] == "FLAG_NOT_LITERAL"
    assert out["undefined"]["status"] == "OFF" and "undefined" in out["undefined"]["reason"]
    assert out["data_home"]["status"] == "NO_CONSUMER"               # the data checkout says FLAG_OFF = True
    assert out["data_home"]["consumer"]["flag"]["source"] == "data_checkout"
    assert out["unknown_module"]["consumer"]["flag"]["source"] == "newest_release"
    assert out["unknown_module"]["status"] == "OFF"


def test_flag_falls_back_to_this_checkout_only_when_no_runtime_is_found_and_says_so(tmp_path):
    root = tmp_path / "somewhere" / "dataroot"
    wj(root / "p" / "fresh.json", {"utc": iso(1), "run": "run-cccc-0001"})
    fallback = tmp_path / "cfg.py"
    fallback.write_text("FLAG_ONLY_FALLBACK = False\n", encoding="utf-8")
    LM._FLAG_CACHE.clear()
    rec = LM.build(root, now=NOW, links=(flag_link("fb", "FLAG_ONLY_FALLBACK"),), limits=LIMITS,
                   fallback_config=fallback)
    r = rec["links"][0]
    assert r["status"] == "OFF" and r["consumer"]["flag"]["source"] == "FALLBACK_THIS_CHECKOUT"
    assert f"per {fallback}" in r["reason"] and "FALLBACK" in r["reason"]
    missing = LM.build(root, now=NOW, links=(flag_link("fb", "X"),), limits=LIMITS,
                       fallback_config=tmp_path / "no_such_config.py")
    assert missing["links"][0]["status"] == "CANNOT_DETERMINE"


def test_release_from_status_receipt_when_the_journal_is_absent(world):
    root = world["root"]
    (root / "optimus" / "runtime_switch" / "runtime_task_runs.jsonl").unlink()
    wj(root / "p" / "fresh.json", {"utc": iso(1), "run": "run-cccc-0001"})
    wj(root / "optimus" / "system_status" / "status.json",
       {"generated_utc": iso(0.2), "repo": str(world["clone"]),
        "sections": {"tasks": {"rows": [{"name": "AegisWorldDigest", "status": "OK", "extra": {"state": "Enabled"}},
                                        {"name": "AegisSomethingNew", "status": "DOWN", "extra": {}}]}}})
    out = run(world, [flag_link("off", "FLAG_OFF")])
    assert out["off"]["status"] == "OFF"
    assert out["off"]["consumer"]["flag"]["source"] == "newest_release"
    rec = out["_rec"]
    assert rec["status_receipt"]["state"] == "OK"
    by = {L["code"]: L for L in rec["layers"]}
    assert {"task": "AegisWorldDigest", "status": "OK"}.items() <= by["M1"]["tasks"][1].items()
    assert [t["task"] for t in by["UNASSIGNED"]["tasks"]] == ["AegisSomethingNew"]   # nothing is hidden
    assert "AegisSomethingNew: DOWN" in LM.mermaid_layers(rec)


def test_diagrams_and_markdown_are_generated_from_the_same_record(world):
    root = world["root"]
    wj(root / "p" / "flow_1.json", {"utc": iso(2), "run": "run-aaaa-0001"})
    wj(root / "c" / "flow.json", {"utc": iso(1), "cites": "run-aaaa-0001"})
    out = run(world, [link("a", prod("p/flow_*.json"), cites("c/flow.json"), objects=("EVENT", "DECISION", "run")),
                      link("b", prod("p/none.json"), NONE, frm="LEARN", to="DECIDE",
                           objects=("OUTCOME_GRADE", "DECISION", None))])
    rec = out["_rec"]
    fb, ob, md = LM.mermaid_feedback(rec), LM.mermaid_objects(rec), LM.render_markdown(rec)
    assert fb.startswith("flowchart LR") and '==>|"FLOWING"|' in fb and '-.->|"ABSENT"|' in fb
    assert 'EVENT }o--o{ DECISION : "run [FLOWING] a"' in ob
    assert 'OUTCOME_GRADE }o--o{ DECISION : "no id written [ABSENT] b"' in ob
    assert rec["top_line"] in md and md.count("```mermaid") == 3
    assert [p for p in rec["pairs"] if (p["from"], p["to"]) == ("SENSE", "UNIVERSE")][0]["n_flowing"] == 1
    assert "LEARN->DECIDE" in rec["open_pairs"]


def test_declared_links_are_well_formed():
    ids = [l["id"] for l in LM.LINKS]
    assert len(ids) == len(set(ids)) and len(ids) >= 20
    entities = {"EVENT", "NODE_ISSUER", "UNIVERSE_CANDIDATE", "BOOK", "DECISION", "ORDER", "OUTCOME_GRADE",
                "LEARNED_WEIGHT"}
    seen = set()
    for l in LM.LINKS:
        assert l["from"] in LM.STAGES and l["to"] in LM.STAGES, l["id"]
        assert l["limit"] in C.LOOP_MAP_LIMITS_H, l["id"]
        assert l["producer"]["stamp"], l["id"]
        assert "mtime" not in json.dumps(l)
        c = l["consumer"]
        assert c["proof"] in ("cites", "flag", "none"), l["id"]
        if c["proof"] == "cites":
            assert c["path"] and c["cite"], l["id"]
        if c["proof"] == "flag":
            assert hasattr(C, c["flag"]), f"{l['id']}: flag {c['flag']} is not in backend/config.py"
        if l["objects"]:
            assert set(l["objects"][:2]) <= entities, l["id"]
            seen |= set(l["objects"][:2])
    assert seen == entities                       # every object of the owner's list is on the diagram
    for a, b in LM.LOOP_PAIRS:                    # every pair of the loop has at least one declared link
        assert any(l["from"] == a and l["to"] == b for l in LM.LINKS), (a, b)


def test_cli_exit_codes(world, tmp_path, capsys):
    out = tmp_path / "out"
    empty = tmp_path / "empty"
    empty.mkdir()
    assert CLI.main(["--data-root", str(empty), "--out", str(out)]) == 2          # empty root
    assert CLI.main(["--data-root", str(tmp_path / "nope"), "--out", str(out)]) == 2   # missing root
    wrong = tmp_path / "wrong"
    wj(wrong / "readme.json", {"x": 1})
    assert CLI.main(["--data-root", str(wrong), "--out", str(out)]) == 2          # no declared receipt at all
    assert not out.exists()                                                         # a refusal writes nothing
    root = world["root"]
    wj(root / "funnel_night10.json", {"generated_at": iso(24)})
    wj(root / "optimus" / "decisions" / f"{(NOW - timedelta(hours=3)).date().isoformat()}.json",
       {"written_utc": iso(3), "candidate_set": {"candidates_generated_at": iso(24)}})
    before = sorted(str(p) for p in root.rglob("*"))
    capsys.readouterr()
    assert CLI.main(["--data-root", str(root), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert sorted(str(p) for p in root.rglob("*")) == before                        # read-only on the data root
    names = sorted(p.name for p in out.iterdir())
    assert len(names) == 5 and [n.rsplit(".", 1)[1] for n in names] == ["json", "md", "mmd", "mmd", "mmd"]
    rec = json.loads((out / names[0]).read_text(encoding="utf-8"))
    by = {r["id"]: r for r in rec["links"]}
    assert by["funnel->decision_contract"]["status"] == "FLOWING"
    assert by["news_overlay_book->grades"]["status"] == "ABSENT"
    assert rec["top_line"] in printed and "open links:" in printed
    assert rec["counts"]["FLOWING"] == 1 and sum(rec["counts"].values()) == len(LM.LINKS)
    assert CLI.main(["--data-root", str(root), "--out", str(out), "--now", "not a time"]) == 3
