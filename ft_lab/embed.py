"""Frozen bge-small-en-v1.5 embeddings of every cell's text (CLS, L2-normalised). GPU if free.

Run:  ft_lab/.venv/Scripts/python.exe -m ft_lab.embed
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
import torch
from transformers import AutoModel, AutoTokenizer

from ft_lab import config as C

MODEL = "BAAI/bge-small-en-v1.5"


def main(batch: int = 128, max_len: int = 256) -> None:
    cells = pd.read_parquet(C.WORK / "cells.parquet", columns=["symbol", "entry_date", "text"])
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    if dev == "cuda":
        torch.cuda.set_per_process_memory_fraction(C.VRAM_FRACTION)
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModel.from_pretrained(MODEL, torch_dtype=torch.float16 if dev == "cuda" else torch.float32).to(dev)
    model.train(False)
    texts = cells["text"].tolist()
    out = np.zeros((len(texts), model.config.hidden_size), dtype=np.float32)
    t0 = time.time()
    with torch.no_grad():
        for i in range(0, len(texts), batch):
            enc = tok(texts[i:i + batch], padding=True, truncation=True, max_length=max_len,
                      return_tensors="pt").to(dev)
            h = model(**enc).last_hidden_state[:, 0]
            h = torch.nn.functional.normalize(h.float(), dim=-1)
            out[i:i + batch] = h.cpu().numpy()
    dt = time.time() - t0
    np.save(C.WORK / "emb_bge.npy", out)
    cells[["symbol", "entry_date"]].to_parquet(C.WORK / "emb_keys.parquet", index=False)
    print(f"embedded {len(texts)} texts in {dt:.0f}s on {dev} = {len(texts) / dt * 60:.0f} texts/min")


if __name__ == "__main__":
    main()
