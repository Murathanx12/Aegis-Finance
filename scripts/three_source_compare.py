"""One stock, three sources (2026-09-28): what MarketWatch's analyst consensus,
WSJ and Barron's each say about the SAME ticker, side by side.

Reads only what the reader already stored. No browser, no LLM, no network, $0.
The table carries consensus targets, which are Dow Jones / FactSet content, so
it is written beside the structured rows (GITIGNORED) and never into docs/.

    python -m scripts.three_source_compare            # every ticker with any row
    python -m scripts.three_source_compare --tickers NVDA,MU
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.services import dowjones_claims as C
from backend.services import web_reader as WR
from backend.services.disk_guard import atomic_write_json


class ThreeSourceRefused(RuntimeError):
    """No stored row of any kind: refuse by name rather than print an empty table."""


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for ln in path.open(encoding="utf-8", errors="replace"):
        ln = ln.strip()
        if not ln.startswith("{"):
            continue
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def _f(x: Any) -> float | None:
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _site(source_id: str, url: str) -> str | None:
    s = f"{source_id} {url}".lower()
    for k in ("marketwatch", "barrons", "wsj"):
        if k in s or (k == "marketwatch" and "mw_" in s):
            return k
    return None


RATING_DIR = {"buy": "up", "overweight": "up", "hold": "neutral", "underweight": "down",
              "sell": "down"}


def build(corpus_root: Path | None = None, tickers: list[str] | None = None) -> dict:
    root = corpus_root or WR.corpus_root()
    mw = _jsonl(root / "_structured" / "mw_analyst_snapshot.jsonl")
    claims: list[dict] = []
    for p in sorted((root / "_claims").glob("*.jsonl")):
        claims += _jsonl(p)
    if not mw and not claims:
        raise ThreeSourceRefused(f"REFUSED_NO_ROWS: no analyst snapshot and no claim under {root}")
    per: dict[str, dict] = defaultdict(lambda: {"marketwatch": None, "wsj": [], "barrons": []})
    for r in mw:                                   # the newest snapshot per ticker wins
        t = str(r.get("ticker") or "").upper()
        if not t:
            continue
        cur = per[t]["marketwatch"]
        if cur is None or str(r.get("first_seen_utc")) > str(cur.get("first_seen_utc")):
            per[t]["marketwatch"] = r
    for r in claims:
        t = str(r.get("ticker") or "").upper()
        site = _site(str(r.get("source_id") or ""), str(r.get("url") or ""))
        if t and site in ("wsj", "barrons"):
            per[t][site].append(r)
    want = {x.upper() for x in tickers} if tickers else None
    rows = []
    for t in sorted(per):
        if want and t not in want:
            continue
        d = per[t]
        m = d["marketwatch"] or {}
        price, tgt = _f(m.get("current_price")), _f(m.get("target_mean"))
        upside = round(tgt / price - 1, 4) if price and tgt and price > 0 else None
        rating = str(m.get("consensus_rating") or "").strip()
        views: dict[str, str | None] = {"marketwatch": RATING_DIR.get(rating.lower()) if rating else None}
        counts = {}
        for site in ("wsj", "barrons"):
            up = sum(1 for c in d[site] if c.get("direction") == "up")
            dn = sum(1 for c in d[site] if c.get("direction") == "down")
            counts[site] = {"claims": len(d[site]), "up": up, "down": dn,
                            "latest": max((str(c.get("published_utc") or c.get("first_seen_utc"))
                                           for c in d[site]), default=None)}
            views[site] = None if not d[site] else ("up" if up > dn else "down" if dn > up else "neutral")
        have = {k: v for k, v in views.items() if v}
        dirs = set(have.values())
        if not have:
            verdict = "NO_VIEW"
        elif len(have) == 1:
            verdict = "ONE_SOURCE"
        elif len(dirs) == 1:
            verdict = f"{len(have)}_AGREE_{next(iter(dirs)).upper()}"
        else:
            verdict = "SPLIT"
        rows.append({"ticker": t, "verdict": verdict, "n_sources": len(have), "views": views,
                     "mw_rating": rating or None, "mw_upside_to_mean_target": upside,
                     "mw_n_analysts": _f(m.get("n_analysts")), "mw_seen": m.get("first_seen_utc"),
                     "wsj": counts["wsj"], "barrons": counts["barrons"]})
    by = defaultdict(int)
    for r in rows:
        by[r["verdict"]] += 1
    return {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "n_tickers": len(rows), "by_verdict": dict(by),
            "three_source_tickers": [r["ticker"] for r in rows if r["n_sources"] == 3],
            "note": ("views are NOT graded here; scripts.source_scorecard grades them. A consensus "
                     "rating is a level, a claim is an event: agreement is a description, not a signal."),
            "rows": rows}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tickers", default="")
    a = ap.parse_args(argv)
    try:
        out = build(tickers=[t for t in a.tickers.split(",") if t.strip()] or None)
    except ThreeSourceRefused as e:
        print(str(e))
        return 2
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    dest = WR.corpus_root() / "_structured" / f"three_source_{stamp}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(dest, out)
    print(json.dumps({k: out[k] for k in ("n_tickers", "by_verdict", "three_source_tickers")}, indent=1))
    print("->", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
