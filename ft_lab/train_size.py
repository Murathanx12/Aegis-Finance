"""SIZE: LoRA-tune Qwen2.5-0.5B with a regression head on text -> what the text adds to size.

Target = ly - B2 (the residual of the trailing-prior + news-metadata ridge from baselines),
so the language model is asked only for what the numeric prior cannot see. Graded on the
test block as B2 + a * lm, with `a` fitted on the validation block (never on test).

Safety: VRAM cap, RAM floor, awake-time box, checkpoint every N steps, STOP file.
Run (Start-Process with a log):  ft_lab/.venv/Scripts/python.exe -m ft_lab.train_size
"""
from __future__ import annotations

import argparse
import os
import json
import math
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import torch
from peft import LoraConfig, PeftModel, TaskType, get_peft_model
from scipy.stats import spearmanr
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from ft_lab import config as C
from ft_lab import safety as S

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

OUT = C.MODELS / "size_qwen05_lora"


def load_frame() -> pd.DataFrame:
    cells = pd.read_parquet(C.WORK / "cells.parquet", columns=["symbol", "entry_date", "text", "split", "ly", "y",
                                                               "rel", "week", "mag_bucket"])
    pb = pd.read_parquet(C.WORK / "preds_baselines.parquet")
    df = cells.merge(pb[["symbol", "entry_date", "B0_vol_prior", "B2_trailing_meta", "T2_trailing_meta_tfidf",
                         "E1_trailing_meta_bge"]], on=["symbol", "entry_date"], how="inner")
    df["resid"] = df["ly"] - df["B2_trailing_meta"]
    return df


def batches(df, tok, bs, max_len, shuffle, rng=None):
    idx = np.arange(len(df))
    if shuffle:
        rng.shuffle(idx)
    texts = df["text"].values
    for i in range(0, len(idx), bs):
        j = idx[i:i + bs]
        enc = tok([f"{t}" for t in texts[j]], padding=True, truncation=True, max_length=max_len,
                  return_tensors="pt")
        yield j, enc


@torch.no_grad()
def predict(model, tok, df, bs, max_len, clock=None) -> np.ndarray:
    model.train(False)
    out = np.zeros(len(df), dtype=np.float32)
    for j, enc in batches(df, tok, bs, max_len, False):
        enc = {k: v.cuda() for k, v in enc.items()}
        with torch.autocast("cuda", dtype=torch.bfloat16):
            out[j] = model(**enc).logits.float().squeeze(-1).cpu().numpy()
        if clock:
            clock.tick()
    model.train(True)
    return out


def date_ic(df, pred, target="resid"):
    vals = []
    for _, g in df.assign(_p=pred).groupby("entry_date"):
        if len(g) >= 8:
            vals.append(spearmanr(g["_p"], g[target]).statistic)
    return float(np.nanmean(vals))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-train", type=int, default=64000)
    ap.add_argument("--bs", type=int, default=16)
    ap.add_argument("--max-len", type=int, default=256)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--minutes", type=float, default=35.0)
    ap.add_argument("--eval-every", type=int, default=400)
    ap.add_argument("--val-n", type=int, default=4000)
    a = ap.parse_args(argv)
    pre = S.preflight("train_size")
    torch.cuda.set_per_process_memory_fraction(C.VRAM_FRACTION)
    torch.manual_seed(C.SEED)
    rng = np.random.default_rng(C.SEED)

    df = load_frame()
    tr = df[df["split"] == "train"]
    tr = tr.iloc[rng.permutation(len(tr))[:a.max_train]].reset_index(drop=True)
    va = df[df["split"] == "val"]
    va_s = va.iloc[rng.permutation(len(va))[:a.val_n]].reset_index(drop=True)
    mu, sd = float(tr["resid"].mean()), float(tr["resid"].std())

    tok = AutoTokenizer.from_pretrained(C.SIZE_BASE)
    tok.padding_side = "left"
    model = AutoModelForSequenceClassification.from_pretrained(C.SIZE_BASE, num_labels=1, dtype=torch.bfloat16, device_map={"": 0})
    model.config.pad_token_id = tok.pad_token_id
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    lcfg = LoraConfig(task_type=TaskType.SEQ_CLS, r=16, lora_alpha=32, lora_dropout=0.05,
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
    model = get_peft_model(model, lcfg).cuda()
    # the score head is trained in fp32 for a stable regression
    for n, p in model.named_parameters():
        if p.requires_grad:
            p.data = p.data.float()
    params = [p for p in model.parameters() if p.requires_grad]
    S.trim_working_set()
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.01)
    steps_total = math.ceil(len(tr) / a.bs)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=a.lr, total_steps=steps_total, pct_start=0.05)
    clock = S.AwakeClock()
    log = {"job": "ft_lab.train_size", "base": C.SIZE_BASE, "preflight": pre, "args": vars(a),
           "n_train": len(tr), "n_val_sample": len(va_s), "target": "(ly - B2) standardised",
           "resid_mean": mu, "resid_sd": sd, "evals": [], "started_utc": datetime.now(timezone.utc).isoformat()}
    best = (-9.0, -1)
    step, t0, losses = 0, time.time(), []
    model.train(True)
    stopped = "completed_one_epoch"
    for j, enc in batches(tr, tok, a.bs, a.max_len, True, rng):
        enc = {k: v.cuda() for k, v in enc.items()}
        y = torch.tensor(((tr["resid"].values[j] - mu) / sd), dtype=torch.float32, device="cuda")
        with torch.autocast("cuda", dtype=torch.bfloat16):
            out = model(**enc).logits.float().squeeze(-1)
        loss = torch.nn.functional.huber_loss(out, y, delta=1.0)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        sched.step()
        opt.zero_grad(set_to_none=True)
        losses.append(float(loss))
        step += 1
        aw = clock.tick()
        if step % 50 == 0:
            S.trim_working_set()
            print(f"step {step}/{steps_total} loss {np.mean(losses[-50:]):.4f} awake {aw / 60:.1f}m "
                  f"vram {torch.cuda.max_memory_allocated() / 2**20:.0f}MiB ram {S.free_ram_gb():.1f}GB "
                  f"rate {step * a.bs / (time.time() - t0):.1f}/s", flush=True)
            if S.free_ram_gb() < C.RUN_FLOOR_RAM_GB:
                model.save_pretrained(OUT / "last")
                S.wait_for_ram("train", clock=clock, floor=C.RUN_FLOOR_RAM_GB)
        if step % a.eval_every == 0 or stopped != "completed_one_epoch":
            p = predict(model, tok, va_s, 64, a.max_len, clock)
            v = date_ic(va_s, p)
            log["evals"].append({"step": step, "val_ic_resid": round(v, 4), "awake_min": round(aw / 60, 1)})
            print(f"EVAL step {step} val IC(resid) {v:+.4f}", flush=True)
            if v > best[0]:
                best = (v, step)
                model.save_pretrained(OUT / "best")
            model.save_pretrained(OUT / "last")
        if aw > a.minutes * 60:
            stopped = "time_box"
        if S.STOP_FILE.exists():
            stopped = "stop_file"
        if stopped != "completed_one_epoch":
            break
    if stopped == "completed_one_epoch":
        p = predict(model, tok, va_s, 64, a.max_len, clock)
        v = date_ic(va_s, p)
        log["evals"].append({"step": step, "val_ic_resid": round(v, 4)})
        if v > best[0]:
            best = (v, step)
            model.save_pretrained(OUT / "best")
    log.update({"stopped": stopped, "steps": step, "best": {"val_ic_resid": best[0], "step": best[1]},
                "awake_min": round(clock.awake / 60, 1), "sleep_gaps": clock.sleep_gaps,
                "train_rate_per_s": round(step * a.bs / (time.time() - t0), 1),
                "peak_vram_mib": round(torch.cuda.max_memory_allocated() / 2**20),
                "finished_utc": datetime.now(timezone.utc).isoformat()})
    tok.save_pretrained(OUT / "best")
    (OUT / "train_log.json").write_text(json.dumps(log, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: log[k] for k in ("stopped", "steps", "best", "awake_min", "train_rate_per_s", "peak_vram_mib")}))

    # ---------------- score val (all) + test (all) with the best adapter ----------------
    del model
    torch.cuda.empty_cache()
    base = AutoModelForSequenceClassification.from_pretrained(C.SIZE_BASE, num_labels=1, dtype=torch.bfloat16, device_map={"": 0})
    base.config.pad_token_id = tok.pad_token_id
    model = PeftModel.from_pretrained(base, OUT / "best").cuda()
    ev = df[df["split"].isin(["val", "test"])].reset_index(drop=True)
    t1 = time.time()
    ev["lm_size"] = predict(model, tok, ev, 64, a.max_len, clock)
    rate = len(ev) / (time.time() - t1) * 60
    ev[["symbol", "entry_date", "split", "lm_size"]].to_parquet(C.WORK / "preds_lm_size.parquet", index=False)
    info = {"scored": len(ev), "score_rate_per_min": round(rate)}
    (OUT / "score_log.json").write_text(json.dumps(info), encoding="utf-8")
    print(json.dumps(info))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
