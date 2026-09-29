"""Generation for the extraction task: base model zero-shot vs the fine-tuned student.

  --model base|student   --task events|psych   --set <name>   --n <rows>
Sets:
  events_test   DeepSeek-typed test documents (teacher rows exist -> agreement)
  psych_test    the DeepSeek psych test cells (teacher rows exist -> agreement; and size)
  psych_val     a week-stratified sample of validation cells (to FIT psych -> size)
  psych_testall a week-stratified sample of test cells (to GRADE psych -> size at scale)
Writes ft_lab/data/gen_<model>_<task>_<set>.jsonl and prints pages/minute.
"""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np
import pandas as pd
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from ft_lab import config as C
from ft_lab import prompts as P
from ft_lab import safety as S

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
ADAPTER = C.MODELS / "extract_qwen15_lora" / "last"


def rows_for(task: str, set_name: str, n: int) -> list[dict]:
    rng = np.random.default_rng(C.SEED + 7)
    if set_name == "events_test":
        ext = pd.read_parquet(C.WORK / "extract.parquet")
        ext = ext[ext["split"] == "test"]
        ext = ext.iloc[rng.permutation(len(ext))[:n]]
        return [{"key": r.panel_uid, "scope": r.scope, "date": r.document_date, "title": r.title, "body": r.body,
                 "symbol": r.scope, "text": (r.title + "\n" + (r.body or ""))[:C.TEXT_CHARS]} for r in ext.itertuples()]
    cells = pd.read_parquet(C.WORK / "cells.parquet", columns=["symbol", "entry_date", "text", "split", "week",
                                                               "title_key"])
    if set_name == "psych_test":
        ps = pd.read_json(C.WORK / "deepseek_psych.jsonl", lines=True)
        ps = ps[ps["split"] == "test"][["symbol", "entry_date"]].drop_duplicates()
        c = cells.merge(ps, on=["symbol", "entry_date"])
    else:
        split = "val" if set_name == "psych_val" else "test"
        c = cells[cells["split"] == split]
        per = int(np.ceil(n / c["week"].nunique()))
        c = c.groupby("week", group_keys=False).apply(
            lambda g: g.iloc[rng.permutation(len(g))[:per]])
    c = c.iloc[:n] if n else c
    return [{"key": f"{r.symbol}|{r.entry_date}", "symbol": r.symbol, "entry_date": r.entry_date,
             "text": r.text, "scope": r.symbol, "date": r.entry_date, "title": "", "body": ""}
            for r in c.itertuples()]


def messages(model_kind: str, task: str, r: dict) -> list[dict]:
    if task == "events":
        user = P.events_user(r["scope"], r["date"], r["title"], r["body"])
        system = P.SYSTEM_STUDENT if model_kind == "student" else P.SYSTEM_BASE_EVENTS
    else:
        user = P.psych_user(r["symbol"], r["text"])
        if model_kind == "student":
            system = P.SYSTEM_STUDENT
        else:
            from ft_lab.deepseek_arm import SYSTEM as PSYCH_SYSTEM  # the same instruction DeepSeek saw
            system = PSYCH_SYSTEM
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def load(model_kind: str):
    tok = AutoTokenizer.from_pretrained(C.EXTRACT_BASE)
    tok.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(C.EXTRACT_BASE, dtype=torch.bfloat16, device_map={"": 0})
    if model_kind == "student":
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, ADAPTER)
        model = model.merge_and_unload()
    model = model.cuda()
    model.train(False)
    return tok, model


@torch.no_grad()
def generate(tok, model, prompts: list[list[dict]], bs: int, max_new: int, max_len: int = 640):
    outs = []
    texts = [tok.apply_chat_template(m, add_generation_prompt=True, tokenize=False) for m in prompts]
    for i in range(0, len(texts), bs):
        enc = tok(texts[i:i + bs], return_tensors="pt", padding=True, truncation=True, max_length=max_len).to("cuda")
        g = model.generate(**enc, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.pad_token_id)
        outs += tok.batch_decode(g[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)
        if (i // bs) % 10 == 0:
            if S.free_ram_gb() < C.RUN_FLOOR_RAM_GB:
                S.wait_for_ram("infer", floor=C.RUN_FLOOR_RAM_GB)
            print(f"  {i + len(texts[i:i + bs])}/{len(texts)}", flush=True)
    return outs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["base", "student"], required=True)
    ap.add_argument("--task", choices=["events", "psych"], required=True)
    ap.add_argument("--set", required=True)
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--bs", type=int, default=16)
    a = ap.parse_args(argv)
    S.preflight(f"infer {a.model} {a.task} {a.set}")
    torch.cuda.set_per_process_memory_fraction(C.VRAM_FRACTION)
    rows = rows_for(a.task, a.set, a.n)
    tok, model = load(a.model)
    S.trim_working_set()
    prompts = [messages(a.model, a.task, r) for r in rows]
    max_new = 60 if a.task == "events" else 110
    torch.cuda.synchronize()
    t0 = time.time()
    outs = generate(tok, model, prompts, a.bs, max_new)
    dt = time.time() - t0
    val = P.valid_events if a.task == "events" else P.valid_psych
    path = C.WORK / f"gen_{a.model}_{a.task}_{a.set}.jsonl"
    n_ok = 0
    with open(path, "w", encoding="utf-8") as fh:
        for r, o in zip(rows, outs):
            v = val(P.parse_json(o))
            n_ok += v is not None
            fh.write(json.dumps({"key": r["key"], "symbol": r.get("symbol"), "entry_date": r.get("entry_date"),
                                 "valid": v is not None, **(v or {}), "raw": None if v else o[:300]}) + "\n")
    info = {"model": a.model, "task": a.task, "set": a.set, "n": len(rows), "valid": n_ok,
            "valid_rate": round(n_ok / max(1, len(rows)), 4), "seconds": round(dt, 1),
            "pages_per_min": round(len(rows) / dt * 60, 1), "batch": a.bs,
            "peak_vram_mib": round(torch.cuda.max_memory_allocated() / 2**20)}
    with open(C.RECEIPTS / "infer_runs.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(info) + "\n")
    print(json.dumps(info), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
