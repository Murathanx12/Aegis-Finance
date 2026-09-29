"""CLI for an OPTIONAL local first stage (the world digest's per-article extraction).

The backend never imports torch: it writes items to a JSONL file and runs this module with the
ft_lab interpreter. Exit codes (the caller falls back to DeepSeek on anything but 0):
  0  every input row has an output row (valid dict or null = off-schema, never repaired)
  3  REFUSED before loading: adapter missing, free RAM under the floor, the GPU busy, STOP file
  1  crashed while loading or generating

    ft_lab/.venv/Scripts/python.exe -m ft_lab.local_extract --in items.jsonl --out typed.jsonl

Input rows: {"item_id", "scope", "date", "title", "body"}.
Output rows: {"item_id", "local_event": {event_type, direction, magnitude, confidence} | null,
              "model": MODEL_TAG}.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from ft_lab import config as C

MODEL_TAG = "qwen2.5-1.5b-instruct+ft_lab/extract_qwen15_lora/last"


def refuse(reason: str) -> int:
    print(json.dumps({"status": "REFUSED", "reason": reason}), flush=True)
    return 3


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-free-ram-gb", type=float, default=C.MIN_FREE_RAM_GB)
    a = ap.parse_args(argv)
    from ft_lab import safety as S
    from ft_lab.loader import ADAPTER_DIR
    if not (ADAPTER_DIR / "adapter_config.json").exists():
        return refuse(f"no adapter at {ADAPTER_DIR.name}")
    if S.STOP_FILE.exists():
        return refuse("ft_lab STOP file present")
    ram = S.free_ram_gb()
    if ram < a.min_free_ram_gb:
        return refuse(f"free RAM {ram:.1f} GB < {a.min_free_ram_gb}")
    g = S.gpu_state()
    if "used_mib" not in g:
        return refuse("no GPU state (nvidia-smi unavailable)")
    if g["used_mib"] > 0.2 * g["total_mib"]:
        return refuse(f"GPU busy: {g['used_mib']:.0f} MiB held by another process")
    rows = [json.loads(x) for x in open(a.inp, encoding="utf-8") if x.strip()]
    t0 = time.time()
    import torch
    torch.cuda.set_per_process_memory_fraction(C.VRAM_FRACTION)
    from ft_lab.loader import load_extractor
    extract = load_extractor()
    outs = extract([{"task": "events", "scope": r.get("scope") or "market", "date": r.get("date") or "",
                     "title": r.get("title") or "", "body": r.get("body") or ""} for r in rows])
    with open(a.out, "w", encoding="utf-8") as fh:
        for r, o in zip(rows, outs):
            fh.write(json.dumps({"item_id": r["item_id"], "local_event": o, "model": MODEL_TAG}) + "\n")
    print(json.dumps({"status": "OK", "n": len(rows), "valid": sum(o is not None for o in outs),
                      "seconds": round(time.time() - t0, 1), "model": MODEL_TAG}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
