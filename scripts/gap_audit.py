"""Where is Aegis blind? A freshness and coverage audit of every input it has.

    python -m scripts.gap_audit

WHY THIS, AND WHY NOW
=====================
2026-09-22 produced two findings that only make sense together:

* `NEGATIVE_RESULTS.md` §59 -- price/volume cannot rank the US cross-section at
  21 sessions. The ordering carries a real signal (IC +0.0227, t +7.56) worth
  +0.28% gross, earned in names that cost ~35 bps to trade. The edge is 28 bps
  and the toll is 35.
* The amplitude test -- fundamentals carry **38.4-39.5 bps/month**, stable at
  every book size, against a 20 bps floor. GO.

So the binding constraint is not the model. It is **what the model is allowed to
see**, and the only way to know that is to ask every input on disk how old it
is. The morning of the same day had already shown what happens when nobody
asks: the decision funnel had been a static file since 2026-08-11, and every
ranking for six weeks ran over forty tickers nobody had refreshed.

The rule this encodes, from CLAUDE.md:

    Before diagnosing a ranking, print the AGE and SIZE of the candidate set it
    ranked.

This does that for every source at once, and prints a gap even when a file
exists -- because a file existing is not the same as a file being current, and
that distinction is the whole point.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                          # noqa: E402

OPT = _cfg.OPTIMUS_LEDGER_DIR

#: source -> (what it is, how stale before it BLOCKS work, how to refresh it)
SOURCES: dict[str, dict] = {
    "price_bars_deep": {
        "path": OPT / "prices_deep" / "bars.parquet",
        "what": "daily OHLCV, 2016->now, survivor half",
        "stale_days": 3,
        "refresh": "python -m scripts.pull_deep_bars --start 2016-01-01",
        "feeds": "xs_ranker, every backtest",
    },
    "price_bars_delisted": {
        "path": OPT / "prices_deep" / "bars_delisted.parquet",
        "what": "the DEAD names, without which every small-cap result is biased",
        "stale_days": 30,
        "refresh": "python -m scripts.pull_delisted_bars --start 2016-01-01",
        "feeds": "xs_ranker survivorship correction",
    },
    "fundamentals": {
        "path": OPT / "aegis_panel" / "aegis_panel_v2.parquet",
        "what": "JKP factor panel, 444 columns",
        "stale_days": 120,
        "refresh": "NO REFRESH EXISTS — this is the gap the amplitude test priced",
        "feeds": "nothing live; it ends 2024-12-31 and carries no ticker",
    },
    "decision_funnel": {
        "path": _cfg.BACKEND_DIR / "data" / "funnel_night10.json",
        "what": "the candidate set every decision ranks",
        "stale_days": 7,
        "refresh": "backend/services/opportunity_funnel.py (no scheduled caller)",
        "feeds": "investment_committee, decision_contract, EXPLOIT/EXPLORE/PROBE",
    },
    "web_events": {
        "path": OPT / "web_events",
        "what": "typed evidence from the browser (8-K, IR, attention)",
        "stale_days": 2,
        "refresh": "python -m scripts.openclaw_collector --job edgar_8k",
        "feeds": "nothing yet — the feature join is owed",
    },
    "pc_book_nav": {
        "path": OPT / "pc_book",
        "what": "the broker's own equity curve",
        "stale_days": 2,
        "refresh": "scripts.live_market_loop / scripts.sim_run",
        "feeds": "the morning brief, all P&L attribution",
    },
    "xs_ranking": {
        "path": OPT / "xs_ranker",
        "what": "the ranked opportunity set and its bake-offs",
        "stale_days": 3,
        "refresh": "python -m scripts.night_rank_bakeoff --survivorship-free",
        "feeds": "the book the live loop would hold",
    },
    "analyst_snapshots": {
        "path": OPT / "analyst_snapshots",
        "what": "targets / consensus / revisions",
        "stale_days": 7,
        "refresh": "the daily pass's analyst step",
        "feeds": "the tracker screen, revision signals",
    },
    "insider": {
        "path": OPT / "sec_insider",
        "what": "Form 4 opportunistic-buy scores",
        "stale_days": 14,
        "refresh": "the insider collector",
        "feeds": "insider_opportunistic (calibrated WEAK on 2026-09-22)",
    },
    "events_typed": {
        "path": OPT / "events",
        "what": "L2 typed news events",
        "stale_days": 7,
        "refresh": "scripts.night_l2_typed_events",
        "feeds": "the text lane",
    },
    "calibration": {
        "path": OPT / "calibration",
        "what": "rank -> realised return maps per signal",
        "stale_days": 7,
        "refresh": "the C7 calibration job",
        "feeds": "decision_authority's EXPLOIT gate",
    },
}


def _newest(p: Path) -> tuple[datetime | None, int, str]:
    """(newest mtime, file count, note). A directory is as fresh as its newest file."""
    if not p.exists():
        return None, 0, "ABSENT"
    if p.is_file():
        return datetime.fromtimestamp(p.stat().st_mtime, timezone.utc), 1, ""
    files = [f for f in p.rglob("*") if f.is_file()]
    if not files:
        return None, 0, "EMPTY DIRECTORY"
    newest = max(files, key=lambda f: f.stat().st_mtime)
    return (datetime.fromtimestamp(newest.stat().st_mtime, timezone.utc),
            len(files), newest.name)


def _content_asof(name: str, p: Path) -> str | None:
    """The date the CONTENT claims, which is the honest number.

    A file's mtime is when it was written, and on a fresh checkout everything is
    "written today" — the 2026-09-07 CI failure. Where a source can state its
    own asof, that is what gets reported.
    """
    try:
        if name.startswith("price_bars") and p.exists():
            import pandas as pd
            d = pd.read_parquet(p, columns=["date"])
            return str(d["date"].max())[:10]
        if name == "decision_funnel" and p.exists():
            return json.loads(p.read_text(encoding="utf-8")).get("generated_at", "")[:10]
        if name == "fundamentals" and p.exists():
            import pyarrow.parquet as pq
            f = pq.ParquetFile(p)
            d = f.read_row_group(f.num_row_groups - 1, columns=["eom"]).to_pandas()
            return str(d["eom"].max())[:10]
    except Exception as exc:                                   # noqa: BLE001
        return f"unreadable: {type(exc).__name__}"
    return None


def audit() -> dict:
    today = datetime.now(timezone.utc)
    rows = []
    for name, spec in SOURCES.items():
        p = Path(spec["path"])
        mtime, n, note = _newest(p)
        asof = _content_asof(name, p)
        age_days = None
        basis = "absent"
        if asof and len(asof) == 10 and asof[:2] == "20":
            age_days = (today.date() - date.fromisoformat(asof)).days
            basis = "content asof"
        elif mtime:
            age_days = (today - mtime).days
            basis = "file mtime (content carries no asof)"
        blocking = (age_days is None) or (age_days > spec["stale_days"])
        rows.append({
            "source": name, "what": spec["what"],
            "exists": p.exists(), "n_files": n, "note": note,
            "asof": asof, "age_days": age_days, "age_basis": basis,
            "stale_after_days": spec["stale_days"],
            "BLOCKING": blocking,
            "feeds": spec["feeds"], "refresh": spec["refresh"],
        })
    rows.sort(key=lambda r: (not r["BLOCKING"], -(r["age_days"] or 9999)))
    blocking = [r for r in rows if r["BLOCKING"]]
    return {
        "receipt": "gap_audit", "at": today.isoformat(timespec="seconds"),
        "n_sources": len(rows), "n_blocking": len(blocking),
        "blocking": [r["source"] for r in blocking],
        "rows": rows,
        "read_me_first": (
            "Age is reported from the CONTENT's own asof where a source states "
            "one, and from the file mtime otherwise — a distinction that matters "
            "because on a fresh checkout every file is 'written today'."),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    res = audit()

    print(f"{'source':>20} {'asof':>12} {'age':>6} {'lim':>5}  {'':<3} what")
    print("-" * 96)
    for r in res["rows"]:
        flag = "!!" if r["BLOCKING"] else "ok"
        age = "—" if r["age_days"] is None else f"{r['age_days']}d"
        print(f"{r['source']:>20} {str(r['asof'] or '—'):>12} {age:>6} "
              f"{r['stale_after_days']:>4}d  {flag:<3} {r['what'][:46]}")
    print(f"\n{res['n_blocking']} of {res['n_sources']} sources are BLOCKING:")
    for r in res["rows"]:
        if r["BLOCKING"]:
            print(f"  · {r['source']}: feeds {r['feeds']}")
            print(f"      fix: {r['refresh']}")

    out = Path(a.out) if a.out else OPT / f"gap_audit_{date.today()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
