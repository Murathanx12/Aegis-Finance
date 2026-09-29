"""`scripts/llm_portfolio.py grade` as the daily pass calls it (2026-09-27).

Offline and synthetic: no yfinance, no real panel, no ledger write outside
`tmp_path`.

* the bars load pushes the held-symbol filter INTO the parquet read and returns
  the same frame the full load gives for those symbols (the full read of both
  deep panels peaked at 3.7 GB in the rehearsal);
* the grade PULLS the required series (URTH, the sector-ETF twins' ETFs, the
  factor ETFs) and one that cannot be pulled is a NAMED refusal on the
  leaderboard, never an assumption;
* the pull's `today` is the day after the last CLOSED session, so the 06:30 HKT
  pass does not drop the session that just closed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend import config as C
from backend.services import llm_portfolio as LP
from backend.services import xs_ranker as XR
from scripts import llm_portfolio as CLI


def _panel(syms, days, *, seed=0, skip=()):
    rng = np.random.default_rng(seed)
    rows = []
    for s in syms:
        for d in days:
            if (s, d) in skip:
                continue
            o = float(rng.uniform(10, 100))
            rows.append({"symbol": s, "date": d, "open": o, "high": o * 1.01,
                         "low": o * 0.99, "close": o * 1.001, "volume": int(rng.integers(1e3, 1e6)),
                         "vwap": o, "trades": 10})
    return pd.DataFrame(rows)


def test_the_filtered_bars_load_equals_the_full_load_for_the_held_symbols(tmp_path, monkeypatch):
    days = pd.bdate_range("2026-08-03", "2026-09-25")
    deep = _panel(["AAA", "BBB", "CCC", "SPY"], days, seed=1)
    # the delisted panel overlaps on BBB (first occurrence -- the deep one -- wins)
    # and holds a dead name only it has
    dead = _panel(["BBB", "DDD"], days[:20], seed=2)
    p1, p2 = tmp_path / "bars.parquet", tmp_path / "bars_delisted.parquet"
    deep.to_parquet(p1, index=False)
    dead.to_parquet(p2, index=False)
    monkeypatch.setattr(XR, "survivorship_free_paths", lambda: [p1, p2])
    held = {"BBB", "DDD", "SPY", "NOPE"}
    full = CLI._us_bars()
    want = full[full["symbol"].isin(held)].reset_index(drop=True)
    got = CLI._us_bars(held)
    pd.testing.assert_frame_equal(got, want)
    assert set(got["symbol"]) == {"BBB", "DDD", "SPY"}
    # every BBB row comes from the deep panel (first occurrence wins). Rows the
    # bar-defect screen removes (this fixture's prices jump up to 10x a day, a
    # spike by design since 2026-09-29) are removed from BOTH loads alike.
    bb = got[got.symbol == "BBB"].merge(deep[deep.symbol == "BBB"], on="date",
                                        suffixes=("", "_deep"))
    assert len(bb) == (got.symbol == "BBB").sum() > 0
    assert (bb["open"].to_numpy() == bb["open_deep"].to_numpy()).all()
    assert not got["symbol"].str.contains("#").any()        # cut segments are not held names
    assert len(CLI._us_bars(set())) == 0


def _write_books(tmp_path, books):
    d = tmp_path / "optimus" / "llm_portfolio"
    d.mkdir(parents=True, exist_ok=True)
    (d / "books.jsonl").write_text("\n".join(json.dumps(b) for b in books) + "\n",
                                   encoding="utf-8")


def _book(name, positions, *, benchmark="SPY", kind="personal", asof="2026-09-25"):
    return {"schema": LP.SCHEMA_VERSION, "name": name, "book_id": name, "kind": kind,
            "asof": asof, "objective": "x", "n_positions": len(positions),
            "horizon_days": [1, 5], "benchmark": benchmark,
            "positions": [{"ticker": t, "weight": w} for t, w in positions]}


def test_the_grade_pulls_the_required_series_and_names_one_it_cannot_get(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "OPTIMUS_LEDGER_DIR", tmp_path / "optimus")
    days = pd.bdate_range("2026-08-03", "2026-09-29")
    us = _panel(["AAA", "SPY"], days, seed=3)
    books = [_book("p", [("AAA", 1.0)]),
             _book("c", [("AAA", 1.0)], benchmark="URTH", kind="competition")]
    _write_books(tmp_path, books)
    asked: dict = {}

    def _ensure(tickers, *, start, today):
        asked.update(tickers=list(tickers), start=start, today=today)
        # the vendor has URTH and the ETFs except XLB (a failed pull)
        got = _panel([t for t in tickers if t not in ("AAA", "SPY", "XLB")], days, seed=4)
        got = got[got["date"] < pd.Timestamp(today)]
        got.attrs["receipt"] = {"n_ok": got["symbol"].nunique(), "n_requested": len(tickers),
                                "n_pulled_now": len(tickers), "failed": ["XLB"]}
        return got

    now = datetime(2026, 9, 29, 22, 30, tzinfo=timezone.utc)      # 06:30 HKT Wed
    out: list[str] = []
    summary = CLI.grade_run(now=now, ensure=_ensure, us_bars=lambda syms: us,
                            out=out.append)
    for s in C.LLM_BOOK_REQUIRED_SERIES:
        assert s in asked["tickers"], s
    # the session that closed at 16:00 ET (20:00 UTC) on 09-29 is INSIDE the pull
    assert str(asked["today"]) == "2026-09-30"
    refused = {r["symbol"]: r["why"] for r in summary["series_refusals"]}
    assert set(refused) == {"XLB"} and "pull failed" in refused["XLB"]
    assert any(line.startswith("SERIES REFUSED: XLB") for line in out)
    lb = json.loads(Path(summary["leaderboard"]).read_text(encoding="utf-8"))
    assert lb["series_refusals"][0]["symbol"] == "XLB"
    assert "URTH" in lb["required_series"]
    # URTH was pulled, so the competition book is graded against it
    g = {r["name"]: r for r in lb["books"]}
    assert g["c"]["status"] == "OK" and g["c"]["benchmark_missing"] is False
    assert summary["status"] == "ok" and summary["bars_through"] == "2026-09-29"
    assert summary["grade_rule_versions"] == {"2": 2}


def test_pull_today_is_the_day_after_the_last_closed_session():
    # 22:30 UTC Monday = 18:30 ET, after the close: Monday's bar is complete
    assert str(CLI.pull_today(datetime(2026, 9, 28, 22, 30, tzinfo=timezone.utc))) == "2026-09-29"
    # 12:00 UTC Monday = 08:00 ET, before the open: the UTC date, as before
    assert str(CLI.pull_today(datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc))) == "2026-09-28"
    # a Sunday: never earlier than the UTC date
    assert str(CLI.pull_today(datetime(2026, 9, 27, 3, 0, tzinfo=timezone.utc))) == "2026-09-27"


def test_a_stale_required_series_is_named():
    days = pd.bdate_range("2026-09-01", "2026-09-29")
    bars = pd.concat([_panel(["SPY"], days), _panel(["URTH"], days[:-2])], ignore_index=True)
    r = CLI.series_refusals(bars, ["SPY", "URTH", "MTUM"])
    by = {x["symbol"]: x["why"] for x in r}
    assert set(by) == {"URTH", "MTUM"}
    assert by["URTH"].startswith("STALE: bars through 2026-09-25")
    assert by["MTUM"].startswith("NO_BARS")
