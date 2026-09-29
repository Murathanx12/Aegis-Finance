"""Retrain the extractor adapter on the CLEANED psychology targets (2 dp, NaN -> null), into a
NEW directory, then re-grade the psychology student on the same 400 test cells.

Nothing existing is overwritten: the frozen adapter `extract_qwen15_lora/last` (the one every
bulk_events row and TRIAL-PT-REVERSAL-1 refer to) stays as it is; this writes
`extract_qwen15_lora_v2/last`. The eval output goes to
`ft_lab/data/gen_student_v2_psych_psych_test.jsonl` and the v1 file is restored untouched.
Same data, same hyper-parameters, same seed as the first run; only the target formatting changed.

A wall-clock deadline (--until HH:MM local) touches ft_lab/runs/STOP (train stops at the next
optimizer step, after a save); the STOP file this wrapper created is removed on exit.

    ft_lab/.venv/Scripts/python.exe -m ft_lab.retrain_v2 --minutes 33 --until 20:30
"""
from __future__ import annotations

import argparse
import json
import shutil
import threading
import time
from datetime import datetime

from ft_lab import config as C
from ft_lab import safety as S

V2 = C.MODELS / "extract_qwen15_lora_v2"


def _deadline(until: str, created: list) -> None:
    hh, mm = (int(x) for x in until.split(":"))
    while True:
        now = datetime.now()
        if (now.hour, now.minute) >= (hh, mm):
            if not S.STOP_FILE.exists():
                S.STOP_FILE.write_text(f"deadline {until} local, retrain_v2\n", encoding="utf-8")
                created.append(True)
            return
        time.sleep(15)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=33.0)
    ap.add_argument("--until", default="20:30")
    ap.add_argument("--skip-train", action="store_true")
    a = ap.parse_args(argv)
    created: list = []
    threading.Thread(target=_deadline, args=(a.until, created), daemon=True).start()
    try:
        if not a.skip_train:
            from ft_lab import train_extract as T
            T.OUT = V2
            T.main(["--minutes", str(a.minutes)])
            S.trim_working_set()
            import torch
            torch.cuda.empty_cache()
        if S.STOP_FILE.exists():
            print("STOP present after training: eval skipped", flush=True)
            return 0
        from ft_lab import infer as I
        I.ADAPTER = V2 / "last"
        v1 = C.WORK / "gen_student_psych_psych_test.jsonl"
        keep = C.WORK / "gen_student_psych_psych_test.v1_keep.jsonl"
        shutil.copyfile(v1, keep)
        try:
            I.main(["--model", "student", "--task", "psych", "--set", "psych_test", "--n", "0"])
            shutil.move(v1, C.WORK / "gen_student_v2_psych_psych_test.jsonl")
        finally:
            shutil.move(keep, v1)
        with open(C.RECEIPTS / "infer_runs.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"note": "the row above is the v2 adapter (extract_qwen15_lora_v2/last), "
                                         "file gen_student_v2_psych_psych_test.jsonl"}) + "\n")
    finally:
        if created and S.STOP_FILE.exists():
            S.STOP_FILE.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
