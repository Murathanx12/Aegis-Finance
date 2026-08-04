"""GDELT stability canary — the pre-registered gate for T4/T5 attention data.

Question (verdicts doc §6): are GDELT DOC-API historical article counts
STABLE, i.e. does querying the same fixed window twice, weeks apart, return
the same numbers? Trends SVI failed PIT (renormalized/repainted); GDELT's
counts are anchored to fixed article timestamps and SHOULD be stable — that
claim is tested here, not assumed.

Protocol (fixed before the first run):
  - 8 fixed queries (6 tickers + 2 macro phrases), fixed window 2024-01-01 ..
    2024-06-30, DOC 2.0 API timelinevol.
  - baseline run stores per-day volume series + sha256 per query.
  - a compare run >= 14 days later recomputes and reports per-query drift:
    identical | minor (<1% mean abs rel diff) | MATERIAL (>=1%).
  - PASS = all queries identical/minor -> GDELT counts usable as the T4/T5
    attention series. Any MATERIAL drift -> GDELT is also out; T4/T5 need
    forward accrual (already the registered fallback).

Usage:
  .venv/Scripts/python.exe scripts/gdelt_stability_canary.py            # baseline
  .venv/Scripts/python.exe scripts/gdelt_stability_canary.py --compare  # later
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parents[1] / "docs" / "canaries"
BASELINE = OUT / "gdelt_stability_baseline.json"
COMPARE_MIN_DAYS = 14

QUERIES = [
    '"AAPL" OR "Apple Inc"',
    '"NVDA" OR "Nvidia"',
    '"XOM" OR "Exxon Mobil"',
    '"JPM" OR "JPMorgan"',
    '"regional banks"',
    '"PLTR" OR "Palantir"',
    '"stock market crash"',
    '"recession fears"',
]
WINDOW = ("20240101000000", "20240630235959")
API = "https://api.gdeltproject.org/api/v2/doc/doc"


def fetch_series(query: str) -> list[list]:
    last = None
    for attempt, wait in enumerate((0, 30, 75, 150)):
        if wait:
            print(f"    429 — backing off {wait}s (attempt {attempt + 1})")
            time.sleep(wait)
        r = requests.get(API, params={
            "query": query, "mode": "timelinevol", "format": "json",
            "startdatetime": WINDOW[0], "enddatetime": WINDOW[1],
        }, timeout=60)
        if r.status_code == 429:
            last = r
            continue
        r.raise_for_status()
        break
    else:
        last.raise_for_status()
    data = r.json()
    tl = data.get("timeline", [])
    if not tl or not tl[0].get("data"):
        raise ValueError(f"empty timeline for {query!r} — canary cannot run "
                         "on a query with no coverage")
    return [[p["date"], p["value"]] for p in tl[0]["data"]]


def series_hash(series: list[list]) -> str:
    return hashlib.sha256(
        json.dumps(series, separators=(",", ":")).encode()
    ).hexdigest()


def run() -> dict[str, dict]:
    out = {}
    for q in QUERIES:
        s = fetch_series(q)
        out[q] = {"n": len(s), "hash": series_hash(s), "series": s}
        print(f"  {q}: {len(s)} points, hash {out[q]['hash'][:12]}")
        time.sleep(2)  # be polite to the API
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    # --auto (for the scheduled workflow): baseline if none exists, compare
    # once the baseline is >= COMPARE_MIN_DAYS old, clean no-op in between.
    if "--auto" in sys.argv:
        if not BASELINE.exists():
            sys.argv = [a for a in sys.argv if a != "--compare"]
        else:
            base = json.loads(BASELINE.read_text(encoding="utf-8"))
            age = (now - datetime.fromisoformat(base["recorded_utc"])).days
            if age < COMPARE_MIN_DAYS:
                print(f"auto: baseline {age}d old (< {COMPARE_MIN_DAYS}d) — "
                      "nothing to do yet")
                return 0
            if "--compare" not in sys.argv:
                sys.argv.append("--compare")

    if "--compare" not in sys.argv:
        if BASELINE.exists():
            print(f"baseline already exists ({BASELINE}) — refusing to "
                  "overwrite; run with --compare, or delete it deliberately")
            return 1
        print("GDELT canary — recording baseline...")
        data = run()
        BASELINE.write_text(json.dumps({
            "recorded_utc": now.isoformat(timespec="seconds"),
            "window": WINDOW, "queries": data,
        }, indent=1), encoding="utf-8")
        print(f"baseline written -> {BASELINE}")
        print(f"re-run with --compare on or after "
              f"{now.date().toordinal() + COMPARE_MIN_DAYS} ordinal "
              f"(>= {COMPARE_MIN_DAYS} days from now)")
        return 0

    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    age_days = (now - datetime.fromisoformat(base["recorded_utc"])).days
    if age_days < COMPARE_MIN_DAYS:
        print(f"baseline is only {age_days}d old — the protocol requires "
              f">= {COMPARE_MIN_DAYS}d between reads; refusing an early read")
        return 1

    print(f"GDELT canary — comparing against baseline ({age_days}d old)...")
    fresh = run()
    material = []
    lines = []
    for q, b in base["queries"].items():
        f = fresh.get(q)
        if f is None:
            material.append(q)
            lines.append(f"  {q}: MISSING on re-query")
            continue
        if f["hash"] == b["hash"]:
            lines.append(f"  {q}: identical")
            continue
        bmap = dict(map(tuple, b["series"]))
        fmap = dict(map(tuple, f["series"]))
        common = set(bmap) & set(fmap)
        rel = [abs(fmap[d] - bmap[d]) / max(abs(bmap[d]), 1e-9) for d in common]
        madr = sum(rel) / len(rel) if rel else 1.0
        verdict = "MATERIAL" if madr >= 0.01 else "minor"
        if verdict == "MATERIAL":
            material.append(q)
        lines.append(f"  {q}: {verdict} drift (mean abs rel {madr:.4f}, "
                     f"{len(common)} common days)")
    print("\n".join(lines))
    verdict = ("FAIL — GDELT counts are NOT stable; T4/T5 need forward accrual"
               if material else
               "PASS — GDELT historical counts stable; usable for T4/T5")
    print(verdict)
    (OUT / "gdelt_stability_compare.json").write_text(json.dumps({
        "compared_utc": now.isoformat(timespec="seconds"),
        "baseline_utc": base["recorded_utc"],
        "results": lines, "material": material, "verdict": verdict,
    }, indent=1), encoding="utf-8")
    return 0 if not material else 1


if __name__ == "__main__":
    sys.exit(main())
