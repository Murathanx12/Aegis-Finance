"""World digest: the OPTIONAL local first stage (ft_lab typed-event student).

Default OFF; DeepSeek stays the extractor of every row; any local failure falls back to
DeepSeek and names why; every new row records the model that typed it. Offline: the model
call is a fake and the local runner is a fake (or a patched subprocess), so no GPU, no child.
"""
from __future__ import annotations

import json
import subprocess

from backend import config as _cfg
from backend.services import world_digest as WD


def _item(i: str = "i1", kind: str = "article", **kw) -> WD.Item:
    base = dict(item_id=i, kind=kind, source="wsj_news", url=f"https://www.wsj.com/a/{i}",
                title="Micron (MU) beats on memory prices",
                text="Micron Technology (MU) reported results above estimates. " * 20,
                first_seen_utc="2026-09-28T12:00:00+00:00", published_utc="2026-09-28T11:00:00+00:00",
                tickers_named=["MU"])
    base.update(kw)
    return WD.Item(**base)


GOOD = {"topic": "Micron beats", "summary": "Micron beat estimates on memory pricing.",
        "event_type": "earnings", "tickers": ["MU"], "sectors": [], "countries": ["US"], "macro": [],
        "sentiment": 0.5, "fear_greed": 0.1, "mgmt_confidence": None, "uncertainty": 0.2,
        "novelty": "new_fact", "forward_claims": []}


def _llm(system, user, **kw):
    if "HEADLINES" in system:
        return {"ok": True, "text": json.dumps({"rows": [dict(GOOD, i=0)]}), "status": "OK",
                "cost_usd": 0.001, "served_model": "deepseek-flash", "tokens_in": 10, "tokens_out": 5}
    return {"ok": True, "text": json.dumps(GOOD), "status": "OK", "cost_usd": 0.001,
            "served_model": "deepseek-flash", "tokens_in": 10, "tokens_out": 5}


def test_the_flag_defaults_off():
    assert getattr(_cfg, "WORLD_DIGEST_LOCAL_EXTRACT") is False


def test_off_never_calls_the_local_runner_and_records_the_deepseek_model(tmp_path):
    called = []
    ex = WD.extract_items([_item()], WD.Meter(1.0, llm=_llm), cache={}, stage_cap=1.0, workers=1,
                          cache_file=tmp_path / "c.jsonl", local_runner=lambda items: called.append(items) or {})
    assert called == []
    assert ex["local_stage"]["status"] == "OFF"
    row = ex["rows"][0]
    assert row["extract_model"] == "deepseek:deepseek-flash"
    assert "local_event" not in row


def test_on_annotates_single_items_and_leaves_the_deepseek_fields_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(_cfg, "WORLD_DIGEST_LOCAL_EXTRACT", True)
    seen = []

    def runner(items):
        seen.extend(i.item_id for i in items)
        return {i.item_id: {"item_id": i.item_id, "model": "qwen-student-test",
                            "local_event": {"event_type": "earnings_report", "direction": 1,
                                            "magnitude": "MODERATE", "confidence": 0.8}} for i in items}

    items = [_item("a"), _item("h", kind="headline")]
    ex = WD.extract_items(items, WD.Meter(1.0, llm=_llm), cache={}, stage_cap=1.0, workers=1,
                          cache_file=tmp_path / "c.jsonl", local_runner=runner)
    assert seen == ["a"]                                  # headlines never go to the student
    assert ex["local_stage"]["status"] == "OK" and ex["local_stage"]["n_valid"] == 1
    rows = {r["item_id"]: r for r in ex["rows"]}
    assert rows["a"]["local_event"]["model"] == "qwen-student-test"
    assert rows["a"]["local_event"]["event_type"] == "earnings_report"
    assert rows["a"]["event_type"] == "earnings"          # the digest's own field is DeepSeek's
    assert rows["a"]["extract_model"] == "deepseek:deepseek-flash"
    assert rows["h"]["extract_model"] == "deepseek:deepseek-flash"
    assert "local_event" not in rows["h"]


def test_an_off_schema_local_reply_is_a_refusal_not_a_guess(monkeypatch):
    monkeypatch.setattr(_cfg, "WORLD_DIGEST_LOCAL_EXTRACT", True)
    st = WD.local_event_stage([_item("a")], runner=lambda items: {"a": {"local_event": None, "model": "m"}})
    assert st["by_item"]["a"] == {"event_type": None, "model": "m", "refused": True}
    assert st["n_valid"] == 0


def test_a_failing_local_stage_falls_back_to_deepseek(tmp_path, monkeypatch):
    monkeypatch.setattr(_cfg, "WORLD_DIGEST_LOCAL_EXTRACT", True)

    def boom(items):
        raise RuntimeError("rc 3: REFUSED free RAM 1.2 GB < 3.0")

    ex = WD.extract_items([_item()], WD.Meter(1.0, llm=_llm), cache={}, stage_cap=1.0, workers=1,
                          cache_file=tmp_path / "c.jsonl", local_runner=boom)
    assert ex["local_stage"]["status"] == "FALLBACK_DEEPSEEK"
    assert "free RAM" in ex["local_stage"]["reason"]
    assert len(ex["rows"]) == 1 and ex["rows"][0]["extract_model"] == "deepseek:deepseek-flash"
    assert ex["rows"][0]["local_event"] is None


def test_the_real_runner_refusal_is_a_fallback_and_spawns_no_model(monkeypatch):
    """With the default runner: no ft_lab interpreter -> fallback; with one, the child's
    refusal (rc 3) -> fallback. subprocess.run is patched, so no child ever starts here."""
    monkeypatch.setattr(_cfg, "WORLD_DIGEST_LOCAL_EXTRACT", True)
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 3, stdout='{"status": "REFUSED", "reason": "GPU busy"}\n',
                                           stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    st = WD.local_event_stage([_item("a")])
    assert st["status"] == "FALLBACK_DEEPSEEK"
    assert ("not installed" in st["reason"]) or ("rc 3" in st["reason"] and "GPU busy" in st["reason"])
    for c in calls:
        assert "ft_lab.local_extract" in c
