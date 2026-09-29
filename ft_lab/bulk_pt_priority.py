"""Convert the remaining 2025 (train) cells with price-target stories FIRST, for TRIAL-PT-REVERSAL-1.

The ordering uses the TEXT ONLY (a keyword regex over the first document's title + body); no
outcome is read. The event itself is defined later by the student's label, never by the regex.
Rows go to the same ft_lab/data/bulk_events.jsonl as ft_lab.bulk_events (same keys, same model
tag), so a later plain `python -m ft_lab.bulk_events` skips everything done here.

Queue: remaining train cells, regex-matched first, then the rest, each group in the existing
queue's (random) order. Progress: receipts/bulk_events_pt2025_progress.json (the main
bulk_events_progress.json is left for the full queue).

A wall-clock deadline (--until HH:MM local) touches ft_lab/runs/STOP so the run ends after the
current chunk; the STOP file this wrapper created is removed on exit.

    ft_lab/.venv/Scripts/python.exe -m ft_lab.bulk_pt_priority --minutes 95 --until 20:27
"""
from __future__ import annotations

import argparse
import json
import re
import threading
import time
from datetime import datetime

import pandas as pd

from ft_lab import bulk_events as B
from ft_lab import config as C
from ft_lab import safety as S

PT_CI = re.compile(
    r"price[- ]target|target price|price objective|"
    r"\b(raise[sd]?|lift(s|ed)?|boost(s|ed)?|hike[sd]?|increase[sd]?|lower(s|ed)?|cut(s)?|trim(s|med)?|"
    r"reduce[sd]?|slash(es|ed)?)\b[^.]{0,40}\btarget\b|"
    r"\btarget\b[^.]{0,30}\b(raised|lowered|cut|increased|reduced|trimmed|boosted|lifted)\b",
    re.IGNORECASE)
PT_CS = re.compile(r"\bPT\b")   # case-sensitive: "pt" in lower case is noise
PT_QUEUE = C.WORK / "bulk_queue_pt2025.parquet"
PT_PROGRESS = C.RECEIPTS / "bulk_events_pt2025_progress.json"


def pt_match(title: str, body: str) -> bool:
    t = f"{title or ''} {body or ''}"
    return bool(PT_CI.search(t) or PT_CS.search(t))


def build_pt_queue() -> pd.DataFrame:
    q = pd.read_parquet(B.QUEUE)
    q = q[(q["source"] == "panel_cell_first_doc") & (q["split"] == "train")].copy()
    q["pt_kw"] = [pt_match(a, b) for a, b in zip(q["title"], q["body"])]
    q = pd.concat([q[q["pt_kw"]], q[~q["pt_kw"]]], ignore_index=True)
    q["order"] = range(len(q))
    q.to_parquet(PT_QUEUE, index=False)
    return q


def _deadline(until: str, created: list) -> None:
    hh, mm = (int(x) for x in until.split(":"))
    while True:
        now = datetime.now()
        if (now.hour, now.minute) >= (hh, mm):
            if not S.STOP_FILE.exists():
                S.STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
                S.STOP_FILE.write_text(f"deadline {until} local, bulk_pt_priority\n", encoding="utf-8")
                created.append(True)
            return
        time.sleep(15)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=95.0)
    ap.add_argument("--until", default="20:27", help="local HH:MM; touches the STOP file")
    ap.add_argument("--chunk", type=int, default=1024)
    a = ap.parse_args(argv)
    q = build_pt_queue()
    done = B.done_keys()
    print(f"pt2025 queue {len(q)} (keyword-matched {int(q['pt_kw'].sum())}), already done "
          f"{int(q['key'].isin(done).sum())}", flush=True)
    created: list = []
    threading.Thread(target=_deadline, args=(a.until, created), daemon=True).start()
    B.QUEUE, B.PROGRESS = PT_QUEUE, PT_PROGRESS
    try:
        rc = B.main(["--minutes", str(a.minutes), "--chunk", str(a.chunk)])
    finally:
        done = B.done_keys()
        rec = json.loads(PT_PROGRESS.read_text(encoding="utf-8")) if PT_PROGRESS.exists() else {}
        rec["pt_keyword"] = {"matched": int(q["pt_kw"].sum()),
                             "matched_done": int(q.loc[q["pt_kw"], "key"].isin(done).sum()),
                             "train_total": int(len(q)), "train_done": int(q["key"].isin(done).sum())}
        rec["resume_command"] = "ft_lab\\.venv\\Scripts\\python.exe -m ft_lab.bulk_pt_priority --minutes 95 --until HH:MM"
        PT_PROGRESS.write_text(json.dumps(rec, indent=1), encoding="utf-8")
        if created and S.STOP_FILE.exists():
            S.STOP_FILE.unlink()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
