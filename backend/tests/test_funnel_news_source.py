"""CH-14a: news and filings add names to the funnel; every candidate carries sources.

Offline and synthetic: a synthetic digest, filings table and price panel under
tmp_path; the funnel's network stages are monkeypatched. Dates derive from now.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from backend import config as cfg
from backend.services import funnel_news_source as FNS
from backend.services import opportunity_funnel as F


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _stamp(t: datetime) -> str:
    return t.strftime("%Y%m%dT%H%M%SZ")


def _write_digest(root, made: datetime, themes, *, dry_run=False):
    root.mkdir(parents=True, exist_ok=True)
    d = {"stamp": _stamp(made), "themes": themes, "dry_run": dry_run,
         "world_state": {"as_of": (made + timedelta(minutes=2)).isoformat()}}
    (root / f"world_digest_{_stamp(made)}.json").write_text(json.dumps(d), encoding="utf-8")


def _theme(tickers, impl):
    return {"title": "synthetic theme", "top_tickers": tickers,
            "implications": [{"subject": t, "subject_type": "ticker", "direction": "up",
                              "order": 1} for t in impl]
            + [{"subject": "banks", "subject_type": "sector", "direction": "up", "order": 2}]}


def _panel(spec: dict, n: int = 260):
    """spec: ticker -> (price, daily volume). Business days ending yesterday."""
    idx = pd.bdate_range(end=pd.Timestamp(_now().date()) - pd.Timedelta(days=1), periods=n)
    rng = np.random.default_rng(7)
    close, vol = {}, {}
    for t, (px, v) in spec.items():
        close[t] = pd.Series(px * np.exp(np.cumsum(rng.normal(0, 0.01, n)) * 0.01), index=idx)
        vol[t] = pd.Series(float(v), index=idx)
    return pd.DataFrame(close), pd.DataFrame(vol)


def _cand(t, score, q=0.3):
    c = F.Candidate(ticker=t, price=50.0, median_dollar_vol=5e7, vol_annual=0.3,
                    quality=q, score=score, stage=4)
    return c


def _ranker(n4=5, n3=7):
    s3 = [_cand(f"R{i}", 1.0 - i / 10) for i in range(n3)]
    return s3, s3[:n4]


def _screen_from(close, vol):
    return lambda names: {t: F.eligibility(t, close, vol) for t in names}


def _enrich_ok(cands):
    for c in cands:
        c.quality, c.stage = 0.25, 3
    return list(cands)


# ───────────────────────────── flag off ─────────────────────────────

def _fake_funnel(monkeypatch, close, vol, universe_tickers):
    monkeypatch.setattr(F, "universe", lambda force=False, extra=None: {
        "tickers": list(universe_tickers), "n": len(universe_tickers), "source": "synthetic"})
    monkeypatch.setattr(F, "_batch_history", lambda tickers, period="1y": {
        "close": close[[t for t in tickers if t in close.columns]],
        "volume": vol[[t for t in tickers if t in vol.columns]], "failed_batches": 0})
    monkeypatch.setattr(F, "_fundamentals", lambda t: (
        {"sector": "X", "market_cap": 1e10, "gross_profitability": 0.1 + (hash(t) % 7) / 20,
         "target": None, "n_analysts": None}, "ok"))
    monkeypatch.setattr(F, "_insider", lambda t: (None, "synthetic"))


def test_flag_off_output_identical(monkeypatch, tmp_path):
    spec = {f"A{i}": (20.0 + i, 5e6) for i in range(12)}
    spec["NEWSA"] = (30.0, 5e6)
    close, vol = _panel(spec)
    _fake_funnel(monkeypatch, close, vol, list(spec))
    _write_digest(tmp_path / "digest", _now() - timedelta(hours=2), [_theme(["NEWSA"], [])])
    monkeypatch.setattr(FNS, "digest_dir", lambda: tmp_path / "digest")
    monkeypatch.setattr(FNS, "filings_path", lambda: tmp_path / "none.jsonl")
    monkeypatch.setattr(cfg, "FUNNEL_NEWS_SOURCE_ENABLED", False)

    def strip(p):
        p = dict(p)
        p.pop("generated_at"), p.pop("runtime_secs")
        return json.dumps(p, sort_keys=True, default=str)

    a = F.run(stage1_keep=10, stage2_keep=6, stage3_keep=4, stage4_keep=3)
    b = F.run(stage1_keep=10, stage2_keep=6, stage3_keep=4, stage4_keep=3)
    assert strip(a) == strip(b)
    assert "news_source" not in a and "stage3_candidates" not in a
    assert all("sources" not in c for c in a["candidates"])
    assert set(a["stages"]) == {"stage1_eligible", "stage2_shortlist", "stage3_enriched",
                                "stage4_candidates"}


def test_flag_on_run_tags_every_candidate(monkeypatch, tmp_path):
    spec = {f"A{i}": (20.0 + i, 5e6) for i in range(12)}
    spec["NEWSA"] = (30.0, 5e6)
    close, vol = _panel(spec)
    _fake_funnel(monkeypatch, close, vol, list(spec))
    _write_digest(tmp_path / "digest", _now() - timedelta(hours=2), [_theme(["NEWSA"], [])])
    monkeypatch.setattr(FNS, "digest_dir", lambda: tmp_path / "digest")
    monkeypatch.setattr(FNS, "filings_path", lambda: tmp_path / "none.jsonl")
    monkeypatch.setattr(cfg, "FUNNEL_NEWS_SOURCE_ENABLED", True)
    p = F.run(stage1_keep=10, stage2_keep=6, stage3_keep=4, stage4_keep=3)
    assert all(c["sources"] for c in p["candidates"])
    assert len(p["candidates"]) == 3
    assert any("news" in c["sources"] for c in p["candidates"])
    assert p["news_source"]["digest"]["status"] == "FRESH"
    assert "news_source" in p["failures"]          # FILINGS_MISSING is a named degradation


# ───────────────────────────── admit ─────────────────────────────

def test_news_name_passing_screens_appears_with_source_news(tmp_path):
    close, vol = _panel({"NEWSA": (30.0, 5e6), "R0": (50.0, 5e6)})
    _write_digest(tmp_path, _now() - timedelta(hours=3), [_theme(["NEWSA"], ["NEWSA"])])
    news = FNS.collect(_now(), digest_root=tmp_path, filings_enabled=False)
    s3, s4 = _ranker()
    res = FNS.admit(news, s3, s4, universe=["NEWSA"] + [c.ticker for c in s3],
                    screen_fn=_screen_from(close, vol), enrich_fn=_enrich_ok, stage4_keep=5)
    final = {c.ticker: c.sources for c in res["final"]}
    assert final["NEWSA"] == ["news"]
    assert len(res["final"]) == 5
    assert all(final[t] == ["ranker"] for t in final if t != "NEWSA")
    r = res["receipt"]
    assert r["final"]["entered_only_by_news_or_filing"] == 1
    assert r["final"]["displaced_ranker_names"] == ["R4"]
    assert r["offered"]["total"] == 1 and r["final"]["news_names"] == 1
    ev = news["names"]["NEWSA"]["evidence"]
    assert ev and all(e["stamp_used"] <= news["build_time"] for e in ev)
    assert news["names"]["NEWSA"]["issuer_id"] == "company:NEWSA"


def test_news_name_failing_a_screen_is_dropped_with_screen_name(tmp_path):
    close, vol = _panel({"CHEAP": (1.0, 5e7), "THIN": (30.0, 1000.0)})
    _write_digest(tmp_path, _now() - timedelta(hours=3),
                  [_theme(["CHEAP", "THIN"], ["NOTL", "NOBR"])])
    news = FNS.collect(_now(), digest_root=tmp_path, filings_enabled=False)
    s3, s4 = _ranker()
    res = FNS.admit(news, s3, s4, universe=["CHEAP", "THIN", "NOBR"],
                    screen_fn=_screen_from(close, vol), enrich_fn=_enrich_ok, stage4_keep=5)
    d = res["receipt"]["dropped"]
    assert d == {"CHEAP": "price_band", "THIN": "min_median_dollar_vol",
                 "NOTL": "stage0_universe", "NOBR": "no_price_history"}
    assert [c.ticker for c in res["final"]] == [c.ticker for c in s4]
    assert res["receipt"]["final"]["news_share"] == 0.0


def test_fundamentals_failure_is_a_named_drop(tmp_path):
    close, vol = _panel({"NEWSA": (30.0, 5e6)})
    _write_digest(tmp_path, _now() - timedelta(hours=3), [_theme(["NEWSA"], [])])
    news = FNS.collect(_now(), digest_root=tmp_path, filings_enabled=False)
    s3, s4 = _ranker()
    res = FNS.admit(news, s3, s4, universe=["NEWSA"], screen_fn=_screen_from(close, vol),
                    enrich_fn=lambda cands: [], stage4_keep=5)
    assert res["receipt"]["dropped"] == {"NEWSA": "stage3_fundamentals"}


@pytest.mark.parametrize("themes,status", [
    ([{"title": "t", "top_tickers": ["NEWSA"], "implications": []}], "EMPTY"),
    ([_theme(["NEWSA"], ["NEWSA"])], "STALE"),
])
def test_empty_or_stale_digest_adds_nothing_and_is_reported(tmp_path, themes, status):
    age = 2 if status == "EMPTY" else float(cfg.FUNNEL_NEWS_DIGEST_MAX_AGE_HOURS) + 5
    _write_digest(tmp_path, _now() - timedelta(hours=age), themes)
    news = FNS.collect(_now(), digest_root=tmp_path, filings_enabled=False)
    assert news["names"] == {}
    assert news["digest"]["status"] == status
    assert any(d.startswith(f"NEWS_DIGEST_{status}") for d in news["degradations"])


def test_missing_digest_is_a_named_degradation(tmp_path):
    news = FNS.collect(_now(), digest_root=tmp_path / "nothing", filings_enabled=False)
    assert news["names"] == {} and news["digest"]["status"] == "MISSING"
    assert news["degradations"][0].startswith("NEWS_DIGEST_MISSING")


def test_digest_stamped_after_build_time_is_refused(tmp_path):
    now = _now()
    _write_digest(tmp_path, now + timedelta(hours=1), [_theme(["FUTURE"], ["FUTURE"])])
    _write_digest(tmp_path, now - timedelta(hours=3), [_theme(["PAST"], [])])
    news = FNS.collect(now, digest_root=tmp_path, filings_enabled=False)
    assert "FUTURE" not in news["names"] and "PAST" in news["names"]
    assert news["digest"]["refused_after_build"] == [_stamp(now + timedelta(hours=1))]
    # a digest that STARTED before but FINISHED after the build is also the future
    _write_digest(tmp_path / "b", now - timedelta(minutes=1), [_theme(["LATE"], [])])
    late = FNS.collect(now, digest_root=tmp_path / "b", filings_enabled=False)
    assert late["names"] == {} and late["digest"]["status"] == "MISSING"


def test_filing_after_build_time_is_refused_and_window_is_overnight(tmp_path):
    build = _now()
    start, end = FNS.overnight_window(build)
    assert start < end <= build
    inside = start + (end - start) / 2
    rows = [
        {"form_type": "8-K", "ticker": "FILA", "public_utc": inside.isoformat(),
         "first_seen_utc": inside.isoformat(), "accession": "a1", "items": ["2.02"]},
        {"form_type": "8-K", "ticker": "LATE", "public_utc": (build + timedelta(minutes=5)).isoformat(),
         "first_seen_utc": (build + timedelta(minutes=6)).isoformat(), "accession": "a2"},
        {"form_type": "8-K", "ticker": "SEENLATE", "public_utc": inside.isoformat(),
         "first_seen_utc": (build + timedelta(hours=1)).isoformat(), "accession": "a3"},
        {"form_type": "8-K", "ticker": "OLD", "public_utc": (start - timedelta(hours=2)).isoformat(),
         "first_seen_utc": (start - timedelta(hours=1)).isoformat(), "accession": "a4"},
        {"form_type": "13F-HR", "ticker": "FUND", "public_utc": inside.isoformat()},
    ]
    p = tmp_path / "filing_events.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    news = FNS.collect(build, digest_root=tmp_path / "nod", filings=p, filings_enabled=True)
    assert list(news["names"]) == ["FILA"]
    assert news["names"]["FILA"]["sources"] == ["filing"]
    assert news["filings"]["refused_after_build"] == 2
    assert news["filings"]["n_8k_rows"] == 4


def test_overnight_window_on_a_weekday_evening_and_morning():
    # derived, not literal: the most recent Wednesday before today
    today = _now().date()
    wed = today - timedelta(days=(today.weekday() - 2) % 7 or 7)
    eve = pd.Timestamp(f"{wed} 20:00", tz="America/New_York").to_pydatetime()
    s, e = FNS.overnight_window(eve)
    assert pd.Timestamp(s).tz_convert("America/New_York").hour == 16 and e == eve
    mid = pd.Timestamp(f"{wed} 11:00", tz="America/New_York").to_pydatetime()
    s, e = FNS.overnight_window(mid)
    s_et, e_et = (pd.Timestamp(x).tz_convert("America/New_York") for x in (s, e))
    assert s_et.date() == wed - timedelta(days=1) and (e_et.hour, e_et.minute) == (9, 30)
