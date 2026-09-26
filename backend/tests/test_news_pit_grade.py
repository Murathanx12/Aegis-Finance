"""Wave-1 row 12: the corpus archive quarantine, graded at READ time.

A row published more than 30 days before we first saw it is `pit_grade:
archive` (36,720 pre-2015 `alpaca_benzinga_news` rows were stamped with their
2026 ingest time). It never enters a state at entry, and a forecast past its
`resolves_after` is never "visible". Offline; the corpus is never rewritten.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from backend.services import book_signals as BS
from backend.services import fast_mover_forensics as F
from backend.services import news_registry as NR

SEEN = datetime(2026, 9, 11, 14, 0, tzinfo=timezone.utc)
OLD = datetime(2015, 2, 20, tzinfo=timezone.utc)


def _row(pub: datetime, seen: datetime, **kw) -> dict:
    return {"source": "alpaca_benzinga_news", "pit_grade": "native_stamp",
            "published_utc": pub.isoformat(), "first_seen_utc": seen.isoformat(),
            "title": "x", **kw}


def test_grade_is_archive_only_past_the_lag():
    old = _row(OLD, SEEN)
    fresh = _row(SEEN - timedelta(days=29), SEEN)
    assert NR.effective_pit_grade(old) == NR.ARCHIVE_GRADE
    assert NR.effective_pit_grade(fresh) == "native_stamp"
    # a row missing a stamp cannot be proven an archive: it keeps its grade
    assert NR.effective_pit_grade({"pit_grade": "index_state"}) == "index_state"
    g = NR.grade_row(old)
    assert g["pit_grade"] == "archive" and g["declared_pit_grade"] == "native_stamp"
    assert old["pit_grade"] == "native_stamp"             # input never mutated


def test_load_news_rows_grades_at_read_time_and_the_file_is_untouched(tmp_path):
    rows = [_row(OLD, SEEN), _row(SEEN - timedelta(hours=1), SEEN)]
    f = tmp_path / "2026-09-11.jsonl"
    raw = "\n".join(json.dumps(r) for r in rows) + "\n"
    f.write_text(raw, encoding="utf-8")
    got = BS.load_news_rows(date(2026, 9, 11), corpus_dir=tmp_path)
    assert [r["pit_grade"] for r in got] == ["archive", "native_stamp"]
    assert f.read_text(encoding="utf-8") == raw


def test_archive_census_counts_per_source(tmp_path):
    d = tmp_path / "alpaca_benzinga_news"
    d.mkdir()
    (d / "2026-09-11.jsonl").write_text("\n".join(json.dumps(r) for r in [
        _row(OLD, SEEN), _row(SEEN - timedelta(hours=2), SEEN)]), encoding="utf-8")
    (tmp_path / "_receipts").mkdir()
    c = NR.archive_census(tmp_path)
    assert c["by_source"]["alpaca_benzinga_news"]["archive"] == 1
    assert c["by_source"]["alpaca_benzinga_news"]["rows"] == 2
    assert "_receipts" not in c["by_source"]


def _ctx_case():
    idx = pd.bdate_range(end=pd.Timestamp("2026-09-18"), periods=90)
    rng = np.random.default_rng(3)
    r = rng.normal(0, 0.004, (90, 2))
    S = 81
    r[S + 1, 0] += 0.08
    closes = pd.DataFrame(50 * np.cumprod(1 + r, axis=0), index=idx, columns=["POS", "SPY"])
    Sd = idx[S]
    pos = F.Position(book="book:t", family="night_books", ticker="POS", direction=1,
                     entry_ts=(F._close_utc(Sd) + timedelta(hours=2)).isoformat(),
                     entry_px=float(closes["POS"].loc[Sd]), entry_session=str(Sd.date()))
    ctx = F.Context(closes=closes)
    case = F.find_fast_movers(positions=[pos], ctx=ctx)[0]
    return case, ctx, F._utc(pos.entry_ts)


def test_archive_row_is_excluded_from_the_entry_state():
    case, ctx, t = _ctx_case()
    arch = _row(OLD, t - timedelta(days=1),
                title="PosCo raises guidance on record demand", _tickers=["POS"])
    live = _row(t - timedelta(days=2), t - timedelta(days=1),
                title="PosCo holds meeting", _tickers=["POS"])
    ctx.news = [arch, live]
    st = F.state_at_entry(case, ctx)
    assert st["news_pre_entry"]["count"] == 1
    assert st["news_pre_entry"]["excluded_archive"] == 1
    assert "guidance" not in json.dumps(st["news_pre_entry"])
    assert st["news_pre_entry"]["lexicon"]["PRODUCT_DEMAND"] == 0


def test_expired_forecast_is_not_visible_at_entry():
    case, ctx, t = _ctx_case()
    made = (t - timedelta(days=30)).isoformat()
    expired = {"ticker": "POS", "made_at": made, "observable": "return_sign",
               "probability": 0.9, "horizon_days": 5,
               "resolves_after": (t - timedelta(days=25)).date().isoformat(), "thesis": "old"}
    live = {"ticker": "POS", "made_at": made, "observable": "return_sign",
            "probability": 0.55, "horizon_days": 60,
            "resolves_after": (t + timedelta(days=30)).date().isoformat(), "thesis": "live"}
    no_stamp = {"ticker": "POS", "made_at": made, "observable": "return_sign",
                "probability": 0.9, "horizon_days": 5, "thesis": "derived"}   # made+5d < t
    ctx.predictions = [expired, live, no_stamp]
    st = F.state_at_entry(case, ctx)
    assert st["forecasts"]["n"] == 1
    assert st["forecasts"]["expired_at_entry"] == 2
    assert [p["thesis"] for p in st["forecasts"]["latest"]] == ["live"]
    ctx.predictions = [expired]
    cl = F.classify(case, ctx=ctx)
    assert not cl["predicted"]                  # the p=0.9 expired forecast predicts nothing
