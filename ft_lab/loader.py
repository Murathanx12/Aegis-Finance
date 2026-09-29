"""One-function loader for the fine-tuned extractor, for a future digest job. NOT wired into
anything live; nothing in backend/, scripts/ or engine/ imports ft_lab.

    from ft_lab.loader import load_extractor
    extract = load_extractor()                       # Qwen2.5-1.5B-Instruct + ft_lab LoRA
    rows = extract([{"task": "psych", "symbol": "NVDA", "text": "..."},
                    {"task": "events", "scope": "NVDA", "date": "2026-09-29", "title": "...", "body": "..."}])

Each output row is the validated dict (prompts.valid_events / valid_psych) or None when the
reply is off-schema -- a refusal, never a repaired guess. Fields are the student's imitation of
DeepSeek's reading (a teacher label is not ground truth); see the first-run note for how well
it agrees and what, if anything, the fields predict.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from ft_lab import config as C
from ft_lab import prompts as P

ADAPTER_DIR = C.MODELS / "extract_qwen15_lora" / "last"


def load_extractor(adapter_dir: str | Path | None = None, device: str = "cuda",
                   batch_size: int = 16) -> Callable[[list[dict]], list[dict | None]]:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    path = Path(adapter_dir or ADAPTER_DIR)
    if not (path / "adapter_config.json").exists():
        raise FileNotFoundError(f"no ft_lab adapter at {path}; run ft_lab.train_extract first")
    tok = AutoTokenizer.from_pretrained(C.EXTRACT_BASE)
    tok.padding_side = "left"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    model = AutoModelForCausalLM.from_pretrained(C.EXTRACT_BASE, dtype=dtype)
    model = PeftModel.from_pretrained(model, path).merge_and_unload().to(device)
    model.train(False)

    def _messages(r: dict) -> list[dict]:
        if r["task"] == "events":
            user = P.events_user(r.get("scope", ""), r.get("date", ""), r.get("title", ""), r.get("body", ""))
        else:
            user = P.psych_user(r.get("symbol", ""), r.get("text", ""))
        return [{"role": "system", "content": P.SYSTEM_STUDENT}, {"role": "user", "content": user}]

    @torch.no_grad()
    def extract(rows: list[dict]) -> list[dict | None]:
        out: list[dict | None] = []
        for i in range(0, len(rows), batch_size):
            chunk = rows[i:i + batch_size]
            texts = [tok.apply_chat_template(_messages(r), add_generation_prompt=True, tokenize=False) for r in chunk]
            enc = tok(texts, return_tensors="pt", padding=True, truncation=True, max_length=640).to(device)
            mx = P.EVENTS_MAX_NEW_TOKENS if all(r["task"] == "events" for r in chunk) else P.PSYCH_MAX_NEW_TOKENS
            g = model.generate(**enc, max_new_tokens=mx, do_sample=False, pad_token_id=tok.pad_token_id)
            dec = tok.batch_decode(g[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)
            for r, d in zip(chunk, dec):
                v = P.valid_events if r["task"] == "events" else P.valid_psych
                out.append(v(P.parse_json(d)))
        return out

    return extract
