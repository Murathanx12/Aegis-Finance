"""Frozen synthetic/metadata regression corpus. PRODUCT_EXPERIMENT; no trading authority.

This is not the current Qwen7B article pilot and has no model runner. Gold was
frozen before inference and never model-graded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from ft_lab import prompts

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ft_lab" / "news_pilot_v1.json"
SCHEMA_VERSION = "news_pilot/v1"
PROMPT_VERSION = "ft_lab.events_user/v1"
MAX_SECONDS = 120


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def load_manifest(path: Path = MANIFEST) -> dict:
    m = json.loads(path.read_text(encoding="utf-8"))
    expected = m.pop("freeze_sha256", None)
    actual = digest(canonical(m))
    if expected != actual or m.get("schema") != SCHEMA_VERSION:
        raise ValueError("pilot manifest freeze hash/schema mismatch")
    docs = m["documents"]
    if len(docs) != 40 or sum(d["split"] == "dev" for d in docs) != 20 or sum(d["split"] == "heldout" for d in docs) != 20:
        raise ValueError("pilot split must be 20/20")
    if len({d["id"] for d in docs}) != 40 or len({d["content_sha256"] for d in docs}) != 40:
        raise ValueError("duplicate pilot identity/content")
    for d in docs:
        content = d["title"] + "\n" + d["body"]
        if digest(content.encode("utf-8")) != d["content_sha256"]:
            raise ValueError(f"changed source snippet: {d['id']}")
        g = d["gold"]
        if g["event_type"] not in prompts.EVENT_IDS or g["direction"] not in (-1, 0, 1):
            raise ValueError(f"invalid gold: {d['id']}")
        if any(span not in content for span in g["evidence_spans"]):
            raise ValueError(f"gold span absent from snippet: {d['id']}")
        if any(number not in content for number in g["numbers"]):
            raise ValueError(f"gold number absent from snippet: {d['id']}")
    m["freeze_sha256"] = expected
    return m


def cache_key(doc: dict, model_version: str) -> str:
    return digest(canonical({"content": doc["content_sha256"], "model": model_version,
                             "prompt": PROMPT_VERSION, "schema": SCHEMA_VERSION}))


def score(manifest: dict, state: dict, split: str) -> dict:
    docs = [d for d in manifest["documents"] if d["split"] == split]
    rows = [r for r in state.get("rows", {}).values() if r["split"] == split]
    by_id = {r["id"]: r["result"] for r in rows}
    counts = {"n": len(docs), "evaluated": len(rows), "event_correct": 0, "direction_correct": 0,
              "entity_correct": 0, "date_correct": 0, "number_correct": 0,
              "evidence_correct": 0, "abstentions": 0, "critical_errors": 0,
              "duplicate_consistent": True}
    errors = []
    for d in docs:
        r = by_id.get(d["id"], {})
        p = r.get("prediction") or {}
        g = d["gold"]
        if not p:
            counts["abstentions"] += 1
            continue
        for name, got, want in (("event", p.get("event_type"), g["event_type"]),
                                 ("direction", p.get("direction"), g["direction"]),
                                 ("entity", p.get("entity"), d["entity"]),
                                 ("date", p.get("event_date"), g.get("event_date")),
                                 ("number", sorted(p.get("numbers") or []), sorted(g["numbers"]))):
            if got == want:
                counts[name + "_correct"] += 1
            else:
                errors.append({"id": d["id"], "field": name})
        spans = p.get("evidence_spans")
        supports = g["evidence_spans"]
        valid_spans = isinstance(spans, list) and all(isinstance(s, str) and s and
            s in d["title"] + "\n" + d["body"] and any(s in gold or gold in s for gold in supports)
            for s in spans)
        if valid_spans and ((supports and spans) or (not supports and not spans)):
            counts["evidence_correct"] += 1
        else:
            errors.append({"id": d["id"], "field": "evidence"})
        if (p.get("entity") not in (None, d["entity"]) or
            (p.get("event_date") is not None and p["event_date"] != g.get("event_date")) or
            (g.get("event_date") and p.get("event_date") != g["event_date"]) or
            any(n not in g["numbers"] for n in (p.get("numbers") or [])) or
            (p.get("event_type") == "no_event") != (g["event_type"] == "no_event") or
            (g["direction"] and p.get("direction") == -g["direction"])):
            counts["critical_errors"] += 1
    groups = {}
    for d in docs:
        root = d["gold"].get("root_event_id")
        if root:
            groups.setdefault(root, []).append(d["id"])
    for ids in groups.values():
        if len(ids) > 1:
            labels = [(by_id.get(i, {}).get("prediction") or {}).get("event_type") for i in ids]
            if not labels[0] or len(set(labels)) != 1:
                counts["duplicate_consistent"] = False
    counts["errors"] = errors
    a = manifest["acceptance"]
    counts["regression_quality_pass"] = bool(len(rows) == 20 and counts["duplicate_consistent"]
        and counts["critical_errors"] <= a["maximum_critical_errors"]
        and counts["entity_correct"] >= a["minimum_entity_correct"]
        and counts["date_correct"] >= a["minimum_date_correct"]
        and counts["number_correct"] >= a["minimum_number_correct"]
        and counts["evidence_correct"] >= a["minimum_evidence_correct"]
        and counts["event_correct"] >= a["minimum_event_correct"]
        and counts["abstentions"] <= a["maximum_abstentions"])
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true", required=True)
    a = ap.parse_args(argv)
    m = load_manifest()
    print(json.dumps({"status": "REGRESSION_ONLY", "sha256": m["freeze_sha256"], "n": 40}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
