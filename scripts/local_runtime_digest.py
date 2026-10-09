"""Digest bounded operational metadata with the on-box model; never paid fallback.

Run from the runtime checkout: python -m scripts.local_runtime_digest
Raw logs, model output and receipts stay in the ignored local_runtime_digest folder.
This command has no browser tools, news interpretation or trading authority.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from urllib.request import urlopen


LOGS = ("dowjones/page_log.jsonl", "dowjones/night_reader_supervisor.jsonl",
        "dowjones/read_next_adopted.jsonl", "dowjones/query_planner_runs.jsonl")
STATUSES = frozenset({"ok", "success", "error", "failed", "refused", "skip", "skipped",
                      "read", "timeout", "running", "degraded", "blocked", "stored",
                      "not_due", "tick", "money_pages", "blank", "not_found",
                      "robots_disallowed", "paywall_checkout_frame", "repair_step",
                      "repair", "official_sources_launched", "query_planner_launched",
                      "reader_down", "start", "pool_mode", "relaunch",
                      "chrome_down_while_reading", "pool_stopped", "chrome_recycle"})
STAMP = re.compile(r"^20\d{2}-\d{2}-\d{2}(?:T[0-9:.+Z-]+)?$")


def snapshot(ledger: Path) -> list[dict]:
    """Only counts, enum statuses and timestamps cross the model boundary."""
    out = []
    for rel in LOGS:
        p = ledger / rel
        row = {"log": rel, "exists": p.is_file()}
        if p.is_file():
            with p.open("rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 65536))
                if size > 65536:
                    f.readline()  # drop a partial first row
                lines = f.read(65536).splitlines()[-100:]
            statuses = Counter()
            dates, invalid = [], 0
            for line in lines:
                try:
                    item = json.loads(line)
                    if not isinstance(item, dict):
                        raise ValueError("not an object")
                except (ValueError, UnicodeError):
                    invalid += 1
                    continue
                value = str(item.get("status", item.get("action", item.get("class", item.get("event", ""))))).lower()
                statuses[value if value in STATUSES else "other"] += 1
                for key in ("t", "utc", "at", "at_utc", "generated_utc", "timestamp", "ts"):
                    stamp = item.get(key)
                    if isinstance(stamp, str) and STAMP.fullmatch(stamp):
                        try:
                            dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                            if dt.tzinfo is not None:
                                dates.append(dt.astimezone(timezone.utc).isoformat())
                        except ValueError:
                            pass
            row.update(bytes=size, sampled_rows=len(lines), invalid_rows=invalid,
                       statuses=dict(statuses), latest_sample_stamp=max(dates, default=None))
        out.append(row)
    return out


def protected(now: datetime) -> bool:
    # PC-local time, matching the standing IIF protection. The launcher is untouched.
    return (16, 45) <= (now.hour, now.minute) < (17, 5)


def free_gib() -> float | None:
    # Reuse the PC's native Windows probe: the scheduled-task venv has no psutil.
    from scripts.task_keeper import _free_gb
    gb = _free_gb()
    return None if gb is None else gb * 1e9 / 2**30


def run(ledger: Path, *, metadata_only: bool = False) -> dict:
    receipt = {"schema": "local-runtime-digest/1", "generated_utc":
               datetime.now(timezone.utc).isoformat(), "inputs": snapshot(ledger),
               "scope": "sampled operational metadata; no trading authority",
               "paid_fallback": False}
    if metadata_only:
        return {**receipt, "status": "METADATA_ONLY"}
    if protected(datetime.now()):
        return {**receipt, "status": "REFUSED", "reason": "IIF_PROTECTED_WINDOW"}
    free = free_gib()
    if free is None:
        return {**receipt, "status": "REFUSED", "reason": "MEMORY_PROBE_UNAVAILABLE"}
    receipt["free_before_gib"] = round(free, 2)
    if free < 3.0:
        return {**receipt, "status": "REFUSED", "reason": "LOW_MEMORY_BEFORE_START"}

    # Native llama.cpp option, measured on this PC with the 2K context below.
    # These apply only to a newly owned process, never restart another caller's server.
    os.environ["LLAMA_ARG_MMAP"] = "0"
    os.environ["AEGIS_LLAMA_CTX"] = "2048"
    from backend.services import free_inference as fi, llama_server as ls, model_provider as mp
    base = mp.PROVIDERS["local"]["base_url"]
    if urlsplit(base).hostname not in {"127.0.0.1", "localhost", "::1"}:
        return {**receipt, "status": "REFUSED", "reason": "NONLOCAL_PROVIDER"}
    started_pid = None
    try:
        state = ls.ensure("local-runtime-digest", wait_s=45)
        if state.get("action") in {"started", "starting", "timeout"}:
            started_pid = state.get("pid")
        if not state.get("ok"):
            receipt.update(status="REFUSED", reason="LOCAL_MODEL_NOT_READY")
            return receipt
        loaded = free_gib()
        receipt["free_loaded_gib"] = None if loaded is None else round(loaded, 2)
        if loaded is None or loaded < 1.0:
            receipt.update(status="REFUSED", reason="LOW_MEMORY_AFTER_START")
            return receipt
        with urlopen(base + "/models", timeout=5) as r:
            models = json.load(r).get("data", [])
        receipt["served_models"] = [str(m.get("id", "")).replace("\\", "/").split("/")[-1]
                                    for m in models]
        prompt = ("Summarise these sampled operational counters in at most four short sentences. "
                  "Do not infer successful reads from 'other', diagnose a cause, invent a total "
                  "outside the sample, or claim investment skill. Missing stamps mean unknown "
                  "freshness. Return JSON with exactly one string field 'summary'. Data:\n" +
                  json.dumps(receipt["inputs"]))
        ls.touch("local-runtime-digest")
        t0 = time.monotonic()
        reply = fi.complete("local_gguf", prompt, system="You summarise operational metadata only.",
                            model="local", max_tokens=300, temperature=0, timeout=60)
        parsed = json.loads(reply.text.strip().removeprefix("```json").removesuffix("```").strip())
        if not isinstance(parsed, dict) or set(parsed) != {"summary"} or not isinstance(parsed["summary"], str):
            raise ValueError("model output did not match summary schema")
        receipt.update(status="OK", summary=parsed["summary"][:2000],
                       summary_label="UNVERIFIED_MODEL_SUMMARY", latency_s=round(time.monotonic()-t0, 2),
                       tokens_in=reply.tokens_in, tokens_out=reply.tokens_out, cost_usd=reply.cost_usd)
    except Exception as exc:
        # No raw exception body: an upstream response can contain log text.
        receipt.update(status="FAILED", reason=type(exc).__name__)
    finally:
        if started_pid:
            owner = ls.owning_instance()
            if owner.get("owner_pid") == os.getpid() and ls.status().get("pid") == started_pid:
                stopped = ls.stop(allow_foreign=False, stop_reason="idle", stopped_by="local-runtime-digest")
                receipt["owned_server_stopped"] = bool(stopped.get("ok"))
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", type=Path)
    ap.add_argument("--metadata-only", action="store_true")
    args = ap.parse_args()
    from backend import config
    ledger = args.ledger or config.OPTIMUS_LEDGER_DIR
    dest = ledger / "local_runtime_digest"
    dest.mkdir(parents=True, exist_ok=True)
    lock = dest / "run.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print("REFUSED: local digest already running or stale lock needs inspection")
        return 2
    try:
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        result = run(ledger, metadata_only=args.metadata_only)
        path = dest / (datetime.now().strftime("digest_%Y%m%dT%H%M%S") + ".json")
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": result["status"], "receipt": str(path),
                          "reason": result.get("reason"), "paid_fallback": False}))
        return 0 if result["status"] in {"OK", "METADATA_ONLY"} else 2
    finally:
        lock.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
