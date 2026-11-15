"""S70: the publisher writes the PUBLIC projection of the health page, not the receipt as built.

`backend/data/public_receipts/system_health/latest.json` is tracked in a public repository. The
router already trims the payload for a public caller (`health_public.public_system_health`), but
the publisher wrote the untrimmed rows (detail / proof / where / evidence text, the receipt file
name, the task owners' receipt column) to the tracked file. The publisher now applies the same
projection before its sanitiser.

Synthetic and offline. The last test reads the tracked copy: the file is tracked and it is dated
by its own stamp inside the payload (never by mtime), and the test asserts on its shape only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.services import health_public as hp
from backend.services import legibility_sanitise as S
from backend.services import publish_receipts as PR
from backend.tests.test_health_public import assert_public_clean

MARK = "ZZPOISON"
TRACKED = Path(__file__).resolve().parents[1] / "data" / "public_receipts"


def _poisoned() -> dict:
    """Poison in values, in map keys and in nested containers. Free-text fields carry the bare
    marker; fields the projection KEEPS carry it inside an unsafe shape (a path, an env name)."""
    row = {"name": f"C:\\{MARK}\\runner", "probe": f"{MARK} probe with spaces", "where": f"{MARK} pc",
           "verdict": "DEAD", "state": {"deep": {"deeper": [f"{MARK} nested"]}},
           "detail": f"{MARK} bill held at $20", "proof": f"backend/data/{MARK}.jsonl",
           "evidence": f"~/.openclaw/{MARK}.json", "evidence_utc": "2026-01-01T00:00:00+00:00",
           "age_s_at_probe": 5, "age_s_now": 9, "same_output": False,
           "missing_because": f"Traceback {MARK}", f"{MARK}_extra": "x",
           "alarm": {"light": "RED", "reason": f"{MARK} reason", "status": f"/app/{MARK}/x.py",
                     "light_counts": {f"{MARK} key": 1}}}
    return {"schema": "legibility/2", "page": "system_health", "status": "STALE",
            "served_utc": "2026-01-01T01:00:00+00:00", "generated_utc": "2026-01-01T00:00:00+00:00",
            "exit_code": 1, "source": f"{MARK} source text", f"{MARK}_top": {"k": f"{MARK}"},
            "counts": {"DEAD": 1, "ALIVE": 2, f"{MARK} key with spaces": 3, f"AEGIS_{MARK}_TOKEN": 4},
            "state_counts": {"DEAD": 1, f"C:\\{MARK}": 1},
            "health_line": f"{MARK} line", "read_me_first": f"{MARK} see /app/x",
            "same_output_rule": f"{MARK} rule",
            "missing_because": {f"{MARK}_k": f"{MARK} v"},
            "receipts": [{"kind": "system_health", "file": f"optimus/health/{MARK}.json",
                          "line": f"{MARK} 26.9 h old", "sha256": "ab" * 32, "role": f"{MARK} role",
                          "stamp_utc": "2026-01-01T00:00:00+00:00", "age_hours": 1.0,
                          "stale_after_hours": 26.0, "status": "STALE"}],
            "alarm": {"light": "RED", "status": "BROKEN", "reason": f"{MARK}_REASON", "schema": "health_alarm/1",
                      "light_counts": {"RED": 1, f"{MARK}": 2}},
            "groups": [{"verdict": "DEAD", "n": 1, "states": {"DEAD": 1, f"{MARK} s": 1}, "rows": [row]}],
            "process_census": [row], "same_output_rows": [row],
            "task_owners": [{"task": "T", "receipt": f"night_factory_<d>/{MARK}.json", "state": "DEAD",
                             "verdict": "DEAD", "detail": f"/app/{MARK}", "cadence_h": 24.0,
                             "missing_because": f"{MARK}", "hash_rule_off": f"because {MARK}",
                             "alarm": {"light": "RED", "reason": f"{MARK}"}}]}


def _kind(build) -> PR.Kind:
    real = PR.KIND_BY_NAME["system_health"]
    return PR.Kind("system_health", real.spec, build, real.page, project=real.project)


def test_the_shipped_health_kind_carries_the_public_projection():
    assert PR.KIND_BY_NAME["system_health"].project is PR._public_system_health


def test_a_poisoned_payload_publishes_with_none_of_the_poison(tmp_path):
    out = PR.publish(out_dir=tmp_path, kinds=(_kind(_poisoned),))
    assert out["written"] and out["kinds"]["system_health"]["status"] == "OK", out
    raw = (tmp_path / "system_health" / "latest.json").read_text(encoding="utf-8")
    man = (tmp_path / "MANIFEST.json").read_text(encoding="utf-8")
    assert MARK not in raw                                          # values, map keys, nested
    assert MARK not in man                                          # the manifest is tracked too
    blob = json.loads(raw)
    assert_public_clean(blob)                                       # the branch's unsafe-shape scan
    assert PR.leak_scan(blob) == []
    assert S.sanitise(blob, S.SPEC["system_health"]) == blob        # the sanitiser still ran, after
    r = blob["groups"][0]["rows"][0]
    assert (r["detail"], r["proof"], r["where"], r["evidence"], r["missing_because"]) == (None,) * 5
    assert r["verdict"] == "DEAD" and r["alarm"]["light"] == "RED" and "reason" not in r["alarm"]
    assert blob["receipts"][0]["file"] is None and blob["receipts"][0]["line"] is None
    assert blob["receipts"][0]["stamp_utc"] == "2026-01-01T00:00:00+00:00"
    assert blob["task_owners"][0]["receipt"] is None and blob["task_owners"][0]["hash_rule_off"] is True
    assert blob["read_me_first"] is None and blob["same_output_rule"] is None
    assert blob["counts"] == {"DEAD": 1, "ALIVE": 2}
    assert blob["health_line"].startswith("health rc 1: DEAD 1, ALIVE 2")
    assert "served_from" not in blob                                # a serve-time word, never baked in
    src = out["kinds"]["system_health"]["sources"]
    assert src == [{"kind": "system_health", "file": None, "sha256": "ab" * 32,
                    "stamp_utc": "2026-01-01T00:00:00+00:00", "role": None, "status": "STALE"}]
    assert PR.verify_manifest(tmp_path) == []
    # the published copy still feeds the serve path: ages come from the receipt's own stamp
    assert PR.newest_stamp(blob) is not None


def test_a_projection_that_raises_refuses_the_kind_and_writes_nothing(tmp_path):
    def boom(_payload):
        raise ValueError(f"{MARK} text that must not reach the manifest")
    real = PR.KIND_BY_NAME["system_health"]
    out = PR.publish(out_dir=tmp_path, kinds=(PR.Kind("system_health", real.spec, _poisoned, real.page,
                                                      project=boom),))
    e = out["kinds"]["system_health"]
    assert e["status"] == "REFUSED" and "ValueError" in e["why"] and MARK not in json.dumps(out)
    assert out["written"] is False and not (tmp_path / "system_health" / "latest.json").exists()


def test_the_tracked_copy_is_the_projection_and_hashes_to_its_manifest():
    p = TRACKED / "system_health" / "latest.json"
    if not p.is_file():
        pytest.skip("no tracked system_health copy in this checkout")
    b = p.read_bytes()
    blob = json.loads(b)
    assert_public_clean(blob)
    for g in blob["groups"]:
        for r in g["rows"]:
            assert (r.get("detail"), r.get("proof"), r.get("where"), r.get("evidence")) == (None,) * 4
    assert all(r.get("file") is None and r.get("line") is None for r in blob["receipts"])
    assert all(o.get("receipt") is None and o.get("detail") is None for o in blob["task_owners"])
    assert blob.get("read_me_first") is None and blob.get("same_output_rule") is None
    # a fixed point of projection + sanitiser: publishing it again would write the same content
    again = S.sanitise(PR._public_system_health(blob), S.SPEC["system_health"])
    assert again == blob
    e = (PR.read_manifest(TRACKED) or {}).get("kinds", {}).get("system_health") or {}
    assert e.get("sha256") == PR._sha(b) and e.get("bytes") == len(b)
    assert all(s.get("file") is None and s.get("role") is None for s in e.get("sources") or [])
    assert not any(hp._unsafe(str(v)) for s in e.get("sources") or [] for v in s.values() if isinstance(v, str))
