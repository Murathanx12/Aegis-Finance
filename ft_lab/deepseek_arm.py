"""DeepSeek zero-shot on a small sample: news psychology -> numbers, plus a size-of-move bucket.

Two uses of one prompt:
  * TEST sample (post DeepSeek's measured 2025-12 cutoff): the paid zero-shot size baseline,
    and "do DeepSeek's psychology fields predict size beyond the prior?"
  * TRAIN sample: teacher rows for the student's psychology task (distillation). A teacher
    label is DeepSeek's reading, not ground truth.

Runs with the PROJECT interpreter (it needs backend.services.llm_analyzer):
    .venv/Scripts/python.exe -m ft_lab.deepseek_arm --n-train 1200 --n-test 600
Own dollar cap (config.DEEPSEEK_CAP_USD) on max(ledger cost, peak-list-price estimate).
Rows are flushed every 50 calls; a rerun skips keys already written.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ft_lab import config as C

PURPOSE = "ft_lab_psych_size"
OUT = C.WORK / "deepseek_psych.jsonl"

EMOTIONS = ["fear", "anxiety", "anger", "neutral", "optimism", "excitement", "relief"]

SYSTEM = """You convert one financial news item about a listed company into numbers that describe its psychology.
Return ONLY one JSON object, no prose, with exactly these keys:
"tone": number from -1 to 1 (negative to positive for the company's shareholders)
"emotion": one of ["fear","anxiety","anger","neutral","optimism","excitement","relief"] (the dominant emotion the item conveys)
"uncertainty": number 0 to 1 (how uncertain, hedged or ambiguous the situation described is)
"surprise": number 0 to 1 (how unexpected this is relative to what investors most likely expected)
"mgmt_confidence": number 0 to 1, or null when no management statement is quoted or paraphrased
"novelty": number 0 to 1 (0 = recap of known facts, 1 = genuinely new information)
"attention": number 0 to 1 (how likely traders are to notice this item today)
"expected_move": one of ["NEGLIGIBLE","SMALL","MODERATE","LARGE","EXTREME"], your forecast of the size (not direction) of the stock's move relative to the S&P 500 from the next session's open to its close: NEGLIGIBLE <0.5%, SMALL 0.5-2%, MODERATE 2-5%, LARGE 5-10%, EXTREME >10%."""

USER = "Ticker: {symbol}\nNews:\n{text}"


def parse(text: str | None) -> dict | None:
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):]
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        o = json.loads(t[a:b + 1])
    except json.JSONDecodeError:
        return None
    try:
        out = {
            "tone": float(np.clip(float(o["tone"]), -1, 1)),
            "emotion": o["emotion"] if o["emotion"] in EMOTIONS else None,
            "uncertainty": float(np.clip(float(o["uncertainty"]), 0, 1)),
            "surprise": float(np.clip(float(o["surprise"]), 0, 1)),
            "mgmt_confidence": None if o.get("mgmt_confidence") is None else float(np.clip(float(o["mgmt_confidence"]), 0, 1)),
            "novelty": float(np.clip(float(o["novelty"]), 0, 1)),
            "attention": float(np.clip(float(o["attention"]), 0, 1)),
            "expected_move": o["expected_move"] if o["expected_move"] in C.MAG_NAMES else None,
        }
    except (KeyError, TypeError, ValueError):
        return None
    if out["emotion"] is None or out["expected_move"] is None:
        return None
    return out


def sample(cells: pd.DataFrame, split: str, n: int, seed: int) -> pd.DataFrame:
    """Stratified by week: the same number of cells from every week of the split."""
    c = cells[cells["split"] == split]
    weeks = sorted(c["week"].unique())
    per = int(np.ceil(n / len(weeks)))
    rng = np.random.default_rng(seed)
    parts = []
    for w in weeks:
        g = c[c["week"] == w]
        k = min(per, len(g))
        parts.append(g.iloc[rng.choice(len(g), size=k, replace=False)])
    s = pd.concat(parts)
    return s.iloc[rng.permutation(len(s))[:n]]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-train", type=int, default=1200)
    ap.add_argument("--n-test", type=int, default=600)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--cap", type=float, default=C.DEEPSEEK_CAP_USD)
    a = ap.parse_args(argv)
    sys.path.insert(0, str(C.REPO))
    from backend.services import llm_analyzer as LA  # noqa: PLC0415

    cells = pd.read_parquet(C.WORK / "cells.parquet")
    todo = pd.concat([sample(cells, "test", a.n_test, C.SEED), sample(cells, "train", a.n_train, C.SEED + 1)])
    done = set()
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            done.add((r["symbol"], r["entry_date"]))
    todo = todo[[(s, d) not in done for s, d in zip(todo["symbol"], todo["entry_date"])]]
    print(f"todo {len(todo)} (already {len(done)})", flush=True)

    lock = threading.Lock()
    spend = {"ledger": 0.0, "own": 0.0, "calls": 0, "ok": 0, "parsed": 0, "tin": 0, "tout": 0,
             "served": {}}
    buf: list[dict] = []
    stop = threading.Event()
    t0 = time.time()

    def one(row):
        if stop.is_set():
            return None
        r = LA.call_named("deepseek", SYSTEM, USER.format(symbol=row.symbol, text=row.text),
                          purpose=PURPOSE, max_tokens=200, temperature=0.0, production_budget=False)
        p = parse(r.get("text"))
        own = (r.get("tokens_in") or 0) * C.DEEPSEEK_PRICE_IN / 1e6 + (r.get("tokens_out") or 0) * C.DEEPSEEK_PRICE_OUT / 1e6
        rec = {"symbol": row.symbol, "entry_date": row.entry_date, "split": row.split,
               "ok": bool(r.get("ok")), "status": r.get("status"), "served_model": r.get("served_model"),
               "tokens_in": r.get("tokens_in"), "tokens_out": r.get("tokens_out"),
               "cost_usd_ledger": r.get("cost_usd"), "cost_usd_own_peak": round(own, 6),
               "latency_s": r.get("latency_s"), "parsed": p is not None, **(p or {}),
               "raw": (r.get("text") or "")[:400] if p is None else None,
               "called_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        with lock:
            spend["calls"] += 1
            spend["ok"] += int(rec["ok"])
            spend["parsed"] += int(rec["parsed"])
            spend["ledger"] += float(r.get("cost_usd") or 0)
            spend["own"] += own
            spend["tin"] += r.get("tokens_in") or 0
            spend["tout"] += r.get("tokens_out") or 0
            sm = str(r.get("served_model"))
            spend["served"][sm] = spend["served"].get(sm, 0) + 1
            buf.append(rec)
            if max(spend["ledger"], spend["own"]) >= a.cap:
                stop.set()
            if len(buf) >= 50:
                _flush(buf)
            if spend["calls"] == 5 or spend["calls"] % 200 == 0:
                print(f"{spend['calls']} calls ok {spend['ok']} parsed {spend['parsed']} "
                      f"ledger ${spend['ledger']:.4f} own ${spend['own']:.4f} served {spend['served']} "
                      f"{time.time() - t0:.0f}s", flush=True)
                if spend["calls"] == 5 and spend["ok"] == 0:
                    stop.set()
        return rec

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(one, r) for r in todo.itertuples()]
        for _ in as_completed(futs):
            pass
    with lock:
        _flush(buf)
    summary = {"job": "ft_lab.deepseek_arm", "purpose": PURPOSE, "calls": spend["calls"], "ok": spend["ok"],
               "parsed": spend["parsed"], "cost_usd_ledger": round(spend["ledger"], 4),
               "cost_usd_own_peak_estimate": round(spend["own"], 4), "tokens_in": spend["tin"],
               "tokens_out": spend["tout"], "served_models": spend["served"], "cap_usd": a.cap,
               "stopped_by_cap": stop.is_set(), "wall_s": round(time.time() - t0, 1),
               "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    C.RECEIPTS.mkdir(parents=True, exist_ok=True)
    with open(C.RECEIPTS / "deepseek_arm_runs.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary) + "\n")
    print(json.dumps(summary, indent=1))
    return 0


def _flush(buf: list[dict]) -> None:
    if not buf:
        return
    C.WORK.mkdir(parents=True, exist_ok=True)
    with open(OUT, "a", encoding="utf-8") as fh:
        for r in buf:
            fh.write(json.dumps(r, default=str) + "\n")
    buf.clear()


if __name__ == "__main__":
    raise SystemExit(main())
