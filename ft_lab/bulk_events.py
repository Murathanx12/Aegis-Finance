"""Bulk conversion: the typed-event student over the news panel and the reader's stored pages.

Resumable. A queue is built once (ft_lab/data/bulk_queue.parquet) in priority order:
  1. test cells   -- the FIRST document of every test-block (symbol, entry_date) cell
  2. val cells    -- same, validation block (fit block for the size / drift tests)
  3. reader       -- every page the reader stored (news_corpus/dowjones/*/*/*.json + social rows)
  4. train cells  -- same, 2025 block
  5. rest         -- every other (uid, symbol) row of the 348k-row panel, newest first
Output rows are appended to ft_lab/data/bulk_events.jsonl every chunk (a checkpoint); a rerun
skips every key already written. Progress receipt:
backend/data/optimus/ft_lab/receipts/bulk_events_progress.json (rewritten every chunk).

Stops at: the awake-minute box (--minutes), ft_lab/runs/STOP, or the end of the queue.
Rows carry `model` (base + adapter) so a reader can never mistake a student row for DeepSeek's.

    ft_lab/.venv/Scripts/python.exe -m ft_lab.bulk_events --minutes 80
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ft_lab import config as C
from ft_lab import prompts as P
from ft_lab import safety as S

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
QUEUE = C.WORK / "bulk_queue.parquet"
OUT = C.WORK / "bulk_events.jsonl"
PROGRESS = C.RECEIPTS / "bulk_events_progress.json"
ADAPTER = C.MODELS / "extract_qwen15_lora" / "last"
MODEL_TAG = "qwen2.5-1.5b-instruct+ft_lab/extract_qwen15_lora/last"
READER_ROOT = C.DATA_ROOT / "news_corpus"


def _norm(s) -> str:
    return " ".join(str(s or "").split())


def reader_rows(root: Path = READER_ROOT) -> list[dict]:
    out = []
    dj = root / "dowjones"
    for p in sorted(dj.glob("*/*/*.json")) if dj.exists() else []:
        if p.parts[-3].startswith("_"):
            continue
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        text = _norm(r.get("text"))
        if len(text) < 200:
            continue
        tick = r.get("tickers_named") or []
        scope = tick[0] if tick and isinstance(tick[0], str) else (r.get("publisher") or "market")
        out.append({"key": "reader|" + str(r.get("sha") or p.stem), "source": "reader", "scope": scope,
                    "date": str(r.get("published_utc") or r.get("first_seen_utc") or "")[:10],
                    "title": _norm(r.get("title")), "body": text, "symbol": scope, "entry_date": None,
                    "split": "reader"})
    soc = root / "social"
    for p in sorted(soc.glob("*/*.jsonl")) if soc.exists() else []:
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines()):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            text = _norm(r.get("text"))
            if len(text) < 100:
                continue
            scope = r.get("ticker") or "market"
            out.append({"key": f"social|{p.parent.name}|{p.stem}|{i}", "source": "reader_social", "scope": scope,
                        "date": str(r.get("read_utc") or "")[:10], "title": _norm(r.get("title")), "body": text,
                        "symbol": scope, "entry_date": None, "split": "reader"})
    return out


def build_queue() -> pd.DataFrame:
    panel = pd.read_parquet(C.PANEL, columns=["uid", "symbol", "published_utc", "entry_date", "title", "body",
                                              "pit_grade"])
    panel = panel[panel["pit_grade"].fillna("") != "archive"]
    cells = pd.read_parquet(C.WORK / "cells.parquet", columns=["symbol", "entry_date", "first_uid", "split"])
    panel["key"] = panel["uid"].astype(str) + "|" + panel["symbol"].astype(str)
    panel = panel.drop_duplicates("key")
    cells["key"] = cells["first_uid"].astype(str) + "|" + cells["symbol"].astype(str)
    first = panel.merge(cells[["key", "split"]], on="key", how="inner")

    def fmt(df: pd.DataFrame, source: str) -> pd.DataFrame:
        return pd.DataFrame({"key": df["key"], "source": source, "scope": df["symbol"],
                             "date": df["published_utc"].fillna("").astype(str).str[:10].where(
                                 df["published_utc"].notna(), df["entry_date"]),
                             "title": df["title"].map(_norm), "body": df["body"].map(_norm),
                             "symbol": df["symbol"], "entry_date": df["entry_date"],
                             "split": df.get("split", "rest")})

    rng = np.random.default_rng(C.SEED + 11)
    parts = []
    for s in ("test", "val"):
        f = first[first["split"] == s]
        parts.append(fmt(f.iloc[rng.permutation(len(f))], "panel_cell_first_doc"))
    parts.append(pd.DataFrame(reader_rows()))
    f = first[first["split"] == "train"]
    parts.append(fmt(f.iloc[rng.permutation(len(f))], "panel_cell_first_doc"))
    rest = panel[~panel["key"].isin(set(first["key"]))].sort_values("entry_date", ascending=False)
    rest = rest.assign(split="rest")
    parts.append(fmt(rest, "panel_other_doc"))
    q = pd.concat(parts, ignore_index=True).drop_duplicates("key")
    q["order"] = np.arange(len(q))
    q.to_parquet(QUEUE, index=False)
    return q


def done_keys() -> set[str]:
    if not OUT.exists():
        return set()
    ks = set()
    with open(OUT, encoding="utf-8") as fh:
        for line in fh:
            try:
                ks.add(json.loads(line)["key"])
            except (ValueError, KeyError):
                continue   # a torn last line from a hard stop is skipped, and redone
    return ks


def write_progress(q: pd.DataFrame, done: set[str], extra: dict) -> None:
    by = {}
    for src_split, g in q.groupby(["source", "split"]):
        k = f"{src_split[0]}:{src_split[1]}"
        by[k] = {"queued": int(len(g)), "done": int(g["key"].isin(done).sum())}
    rec = {"job": "ft_lab.bulk_events", "licence": C.LICENCE, "model": MODEL_TAG,
           "updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "queue_rows": int(len(q)), "done_rows": int(len(done)), "by_source_split": by,
           "resume_command": "ft_lab\\.venv\\Scripts\\python.exe -m ft_lab.bulk_events --minutes 80",
           **extra}
    C.RECEIPTS.mkdir(parents=True, exist_ok=True)
    tmp = PROGRESS.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    tmp.replace(PROGRESS)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=80.0, help="awake GPU minutes for this run")
    ap.add_argument("--chunk", type=int, default=2048)
    ap.add_argument("--bs", type=int, default=32)
    ap.add_argument("--rebuild-queue", action="store_true")
    a = ap.parse_args(argv)

    q = build_queue() if (a.rebuild_queue or not QUEUE.exists()) else pd.read_parquet(QUEUE)
    done = done_keys()
    todo = q[~q["key"].isin(done)]
    print(f"queue {len(q)} done {len(done)} todo {len(todo)}", flush=True)
    write_progress(q, done, {"state": "starting"})
    if todo.empty:
        return 0

    pre = S.preflight("bulk_events")
    import torch
    from ft_lab.infer import load
    torch.cuda.set_per_process_memory_fraction(C.VRAM_FRACTION)
    tok, model = load("student")
    S.trim_working_set()
    clock = S.AwakeClock()
    t_start = time.time()
    n_run = 0
    stop_reason = "queue_end"
    for i in range(0, len(todo), a.chunk):
        if S.STOP_FILE.exists():
            stop_reason = "STOP_file"
            break
        if clock.tick() / 60 >= a.minutes:
            stop_reason = "time_box"
            break
        if S.free_ram_gb() < C.RUN_FLOOR_RAM_GB:
            S.wait_for_ram("bulk_events", floor=C.RUN_FLOOR_RAM_GB, clock=clock)
        chunk = todo.iloc[i:i + a.chunk]
        msgs = [[{"role": "system", "content": P.SYSTEM_STUDENT},
                 {"role": "user", "content": P.events_user(r.scope, r.date, r.title, r.body)}]
                for r in chunk.itertuples()]
        texts = [tok.apply_chat_template(m, add_generation_prompt=True, tokenize=False) for m in msgs]
        lens = np.array([len(t) for t in texts])
        order = np.argsort(lens)          # length-sorted batches: little padding
        outs = [None] * len(texts)
        with torch.no_grad():
            for j in range(0, len(order), a.bs):
                idx = order[j:j + a.bs]
                enc = tok([texts[k] for k in idx], return_tensors="pt", padding=True, truncation=True,
                          max_length=640).to("cuda")
                g = model.generate(**enc, max_new_tokens=60, do_sample=False, pad_token_id=tok.pad_token_id)
                dec = tok.batch_decode(g[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)
                for k, d in zip(idx, dec):
                    outs[k] = d
                clock.tick()   # tick per BATCH: a chunk takes minutes, and a >60 s gap reads as sleep
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with open(OUT, "a", encoding="utf-8") as fh:
            for r, o in zip(chunk.itertuples(), outs):
                v = P.valid_events(P.parse_json(o))
                fh.write(json.dumps({"key": r.key, "source": r.source, "split": r.split, "symbol": r.symbol,
                                     "entry_date": r.entry_date, "doc_date": r.date, "valid": v is not None,
                                     **(v or {}), "raw": None if v else (o or "")[:200], "model": MODEL_TAG,
                                     "extracted_utc": now}) + "\n")
                done.add(r.key)
        n_run += len(chunk)
        el = time.time() - t_start
        rate = n_run / max(el, 1) * 60
        g = S.gpu_state()
        print(f"{n_run}/{len(todo)} rows, {rate:.0f}/min, awake {clock.awake / 60:.1f} min, "
              f"free RAM {S.free_ram_gb():.1f} GB, vram {g.get('used_mib')} MiB, temp {g.get('temp_c')}", flush=True)
        write_progress(q, done, {"state": "running", "rows_this_run": n_run, "pages_per_min_this_run": round(rate, 1),
                                 "awake_min_this_run": round(clock.awake / 60, 1), "preflight": pre,
                                 "peak_vram_mib": round(torch.cuda.max_memory_allocated() / 2**20)})
    write_progress(q, done, {"state": "stopped", "stop_reason": stop_reason, "rows_this_run": n_run,
                             "pages_per_min_this_run": round(n_run / max(time.time() - t_start, 1) * 60, 1),
                             "awake_min_this_run": round(clock.awake / 60, 1),
                             "peak_vram_mib": round(torch.cuda.max_memory_allocated() / 2**20)})
    print(f"stopped: {stop_reason}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
