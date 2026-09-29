"""EXTRACTION: LoRA SFT of Qwen2.5-1.5B-Instruct to reproduce DeepSeek's typed fields (distillation).

Two tasks in one adapter, both TRAIN-split only:
  events  text -> {event_type, direction, magnitude, confidence}   teacher: typed_events panel rows (DeepSeek)
  psych   text -> {tone, emotion, uncertainty, surprise, mgmt_confidence, novelty, attention, expected_move}
          teacher: ft_lab/data/deepseek_psych.jsonl train rows (DeepSeek, this run)
A teacher label is DeepSeek's reading, not ground truth. Loss on the answer tokens only.

Safety: VRAM cap, RAM floor, awake-time box, checkpoint every N steps, STOP file.
Run (Start-Process with a log):  ft_lab/.venv/Scripts/python.exe -m ft_lab.train_extract
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

from ft_lab import config as C
from ft_lab import prompts as P
from ft_lab import safety as S

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
OUT = C.MODELS / "extract_qwen15_lora"


def build_examples(split: str = "train") -> list[dict]:
    ext = pd.read_parquet(C.WORK / "extract.parquet")
    ext = ext[ext["split"] == split]
    ex = [{"task": "events", "key": r.panel_uid,
           "user": P.events_user(r.scope, r.document_date, r.title, r.body),
           "target": P.events_target(r.event_type, r.direction, r.magnitude_bucket, r.confidence)}
          for r in ext.itertuples()]
    ps = pd.read_json(C.WORK / "deepseek_psych.jsonl", lines=True)
    ps = ps[(ps["split"] == split) & ps["parsed"]]
    cells = pd.read_parquet(C.WORK / "cells.parquet", columns=["symbol", "entry_date", "text"])
    ps = ps.merge(cells, on=["symbol", "entry_date"], how="inner")
    ex += [{"task": "psych", "key": f"{r['symbol']}|{r['entry_date']}", "user": P.psych_user(r["symbol"], r["text"]),
            "target": P.psych_target(r)} for r in ps.to_dict("records")]
    return ex


def encode(tok, ex: dict, max_len: int) -> tuple[list[int], list[int]]:
    msgs = [{"role": "system", "content": P.SYSTEM_STUDENT}, {"role": "user", "content": ex["user"]}]
    prompt_ids = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True)
    if isinstance(prompt_ids, dict) or hasattr(prompt_ids, "input_ids"):
        prompt_ids = prompt_ids["input_ids"]
    ans_ids = tok(ex["target"] + "<|im_end|>", add_special_tokens=False)["input_ids"]
    room = max_len - len(ans_ids)
    prompt_ids = prompt_ids[:room - 6] + prompt_ids[-6:] if len(prompt_ids) > room else prompt_ids
    ids = list(prompt_ids) + ans_ids
    labels = [-100] * len(prompt_ids) + ans_ids
    return ids, labels


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--micro-bs", type=int, default=4)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--max-len", type=int, default=512)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--minutes", type=float, default=45.0)
    ap.add_argument("--max-examples", type=int, default=0)
    a = ap.parse_args(argv)
    pre = S.preflight("train_extract")
    torch.cuda.set_per_process_memory_fraction(C.VRAM_FRACTION)
    torch.manual_seed(C.SEED)
    rng = np.random.default_rng(C.SEED)

    tok = AutoTokenizer.from_pretrained(C.EXTRACT_BASE)
    exs = build_examples("train")
    if a.max_examples:
        exs = [exs[i] for i in rng.permutation(len(exs))[:a.max_examples]]
    enc = [encode(tok, e, a.max_len) for e in exs]
    order = rng.permutation(len(enc))
    n_task = pd.Series([e["task"] for e in exs]).value_counts().to_dict()
    print(f"examples {len(enc)} {n_task} mean len {np.mean([len(x[0]) for x in enc]):.0f}", flush=True)

    model = AutoModelForCausalLM.from_pretrained(C.EXTRACT_BASE, dtype=torch.bfloat16, device_map={"": 0})
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    model.config.use_cache = False
    lcfg = LoraConfig(task_type="CAUSAL_LM", r=16, lora_alpha=32, lora_dropout=0.05,
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
    model = get_peft_model(model, lcfg).cuda()
    params = [p for p in model.parameters() if p.requires_grad]
    S.trim_working_set()
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.0)
    n_opt_steps = int(np.ceil(len(enc) / (a.micro_bs * a.accum)))
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=a.lr, total_steps=n_opt_steps, pct_start=0.05)
    clock = S.AwakeClock()
    log = {"job": "ft_lab.train_extract", "base": C.EXTRACT_BASE, "preflight": pre, "args": vars(a),
           "n_examples": len(enc), "by_task": n_task, "started_utc": datetime.now(timezone.utc).isoformat(),
           "teacher": "DeepSeek (deepseek-chat typed rows 2026-09-13; deepseek-flash psych rows this run)",
           "loss_curve": []}
    model.train(True)
    t0 = time.time()
    micro, opt_step, losses, stopped = 0, 0, [], "completed_one_epoch"
    pad = tok.pad_token_id
    for i in range(0, len(order), a.micro_bs):
        batch = [enc[k] for k in order[i:i + a.micro_bs]]
        L = max(len(x[0]) for x in batch)
        ids = torch.full((len(batch), L), pad, dtype=torch.long)
        lab = torch.full((len(batch), L), -100, dtype=torch.long)
        att = torch.zeros((len(batch), L), dtype=torch.long)
        for r, (x, y) in enumerate(batch):
            ids[r, :len(x)] = torch.tensor(x)
            lab[r, :len(y)] = torch.tensor(y)
            att[r, :len(x)] = 1
        with torch.autocast("cuda", dtype=torch.bfloat16):
            loss = model(input_ids=ids.cuda(), attention_mask=att.cuda(), labels=lab.cuda()).loss / a.accum
        loss.backward()
        losses.append(float(loss) * a.accum)
        micro += 1
        if micro % a.accum == 0:
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            opt_step += 1
            aw = clock.tick()
            if opt_step % 25 == 0:
                S.trim_working_set()
                ml = float(np.mean(losses[-25 * a.accum:]))
                log["loss_curve"].append({"step": opt_step, "loss": round(ml, 4), "awake_min": round(aw / 60, 1)})
                print(f"step {opt_step}/{n_opt_steps} loss {ml:.4f} awake {aw / 60:.1f}m "
                      f"vram {torch.cuda.max_memory_allocated() / 2**20:.0f}MiB ram {S.free_ram_gb():.1f}GB "
                      f"rate {micro * a.micro_bs / (time.time() - t0):.1f} ex/s", flush=True)
                if S.free_ram_gb() < C.RUN_FLOOR_RAM_GB:
                    model.save_pretrained(OUT / "last")
                    S.wait_for_ram("train", clock=clock, floor=C.RUN_FLOOR_RAM_GB)
            if opt_step % C.CHECKPOINT_EVERY == 0:
                model.save_pretrained(OUT / "last")
            if aw > a.minutes * 60:
                stopped = "time_box"
            if S.STOP_FILE.exists():
                stopped = "stop_file"
            if stopped != "completed_one_epoch":
                break
    model.save_pretrained(OUT / "last")
    tok.save_pretrained(OUT / "last")
    log.update({"stopped": stopped, "opt_steps": opt_step, "examples_seen": micro * a.micro_bs,
                "awake_min": round(clock.awake / 60, 1), "sleep_gaps": clock.sleep_gaps,
                "train_rate_ex_per_s": round(micro * a.micro_bs / (time.time() - t0), 2),
                "peak_vram_mib": round(torch.cuda.max_memory_allocated() / 2**20),
                "finished_utc": datetime.now(timezone.utc).isoformat()})
    (OUT / "train_log.json").write_text(json.dumps(log, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: log[k] for k in ("stopped", "opt_steps", "examples_seen", "awake_min",
                                          "train_rate_ex_per_s", "peak_vram_mib")}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
