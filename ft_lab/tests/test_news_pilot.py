"""Frozen news pilot checks; fake inference only, no GPU/network/provider."""
import copy
import json

import pytest

from ft_lab import news_pilot as P


def test_frozen_sample_has_20_20_unique_source_spans_and_a_syndicated_pair():
    m = P.load_manifest()
    assert len(m["documents"]) == 40
    assert {d["kind"] for d in m["documents"]} == {"synthetic_fixture", "metadata_fixture", "synthetic_challenge"}
    pair = [d for d in m["documents"] if d["gold"].get("root_event_id") == "exampleco-guidance-range"]
    assert len(pair) == 2 and all(d["split"] == "heldout" for d in pair)


def test_freeze_fails_on_changed_gold_or_source(tmp_path):
    m = P.load_manifest()
    m["documents"][0]["gold"]["direction"] = -1
    f = tmp_path / "changed.json"
    f.write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(ValueError, match="freeze hash"):
        P.load_manifest(f)


def test_cache_key_changes_with_every_version_dimension():
    d = P.load_manifest()["documents"][0]
    assert P.cache_key(d, "model-A") != P.cache_key(d, "model-B")
    changed = copy.deepcopy(d)
    changed["content_sha256"] = "0" * 64
    assert P.cache_key(d, "model-A") != P.cache_key(changed, "model-A")


def test_legacy_student_cannot_pass_article_fact_gate():
    m = P.load_manifest()
    rows = {}
    for d in m["documents"]:
        if d["split"] != "heldout":
            continue
        p = {"event_type": d["gold"]["event_type"], "direction": d["gold"]["direction"],
             "magnitude": "SMALL", "confidence": 1.0}
        rows[d["id"]] = {"id": d["id"], "split": "heldout", "result": {"status": "OK", "prediction": p}}
    result = P.score(m, {"rows": rows}, "heldout")
    assert result["event_correct"] == 20
    assert result["entity_correct"] == 0 and result["evidence_correct"] == 0
    assert result["regression_quality_pass"] is False
