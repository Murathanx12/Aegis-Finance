"""CH-14a: news and filings add names to the funnel in a SEPARATE block; the
ranker's candidate list is unchanged and only gains `sources` tags.

Offline and synthetic: digest, filings, issuer table and price panel under
tmp_path; the funnel's network stages are monkeypatched. Dates derive from now.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

from backend import config as cfg
from backend.services import funnel_news_source as FNS
from backend.services import opportunity_funnel as F

#: sha256 of the canonical flag-off payload of `_fake_run` (generated_at and
#: runtime_secs removed, floats rounded to 8 places), computed with the funnel
#: as it stood on origin/main BEFORE CH-14a (039a38c5), without the news module.
EXPECTED_FLAG_OFF_SHA = "cfa1e33a0cd452189142f74e7ad445ab1bb1018dfec968bc5b5efae83cde5e66"

COMMON_WORDS = ("AI", "IT", "ON", "ALL", "NOW", "A", "GOLD")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _stamp(t: datetime) -> str:
    return t.strftime("%Y%m%dT%H%M%SZ")


def _write_digest(root, made: datetime, themes, *, dry_run=False):
    root.mkdir(parents=True, exist_ok=True)
    d = {"stamp": _stamp(made), "themes": themes, "dry_run": dry_run,
         "world_state": {"as_of": (made + timedelta(minutes=2)).isoformat()}}
    (root / f"world_digest_{_stamp(made)}.json").write_text(json.dumps(d), encoding="utf-8")


def _imp(t, direction="up", mentioned=True, conf=0.5):
    return {"subject": t, "subject_type": "ticker", "direction": direction, "order": 1,
            "mentioned": mentioned, "confidence": conf}


def _theme(tickers, impl=(), *, title="synthetic theme"):
    return {"title": title, "top_tickers": list(tickers),
            "implications": [i if isinstance(i, dict) else _imp(i) for i in impl]
            + [{"subject": "banks", "subject_type": "sector", "direction": "up", "order": 2}]}


def _issuers(*names):
    return {n: f"{n} Corp" for n in names}


def _panel(spec: dict, n: int = 260):
    """spec: ticker -> (price, daily volume). Deterministic (no rng, no exp)."""
    idx = pd.bdate_range(end=pd.Timestamp("2000-01-03") + pd.Timedelta(days=400), periods=n)
    close, vol = {}, {}
    for j, (t, (px, v)) in enumerate(spec.items()):
        k = 0.05 + 0.03 * j
        close[t] = pd.Series([px * (1.0 + 0.02 * math.sin(k * i + j)) for i in range(n)], index=idx)
        vol[t] = pd.Series(float(v), index=idx)
    return pd.DataFrame(close), pd.DataFrame(vol)


def _gp(t: str) -> float:
    return 0.1 + (sum(map(ord, t)) % 7) / 20


def _install_fakes(mod, setattr_, close, vol, universe_tickers, *, fail_tickers=()):
    setattr_(mod, "universe", lambda force=False, extra=None: {
        "tickers": list(universe_tickers), "n": len(universe_tickers), "source": "synthetic"})

    def hist(tickers, period="1y"):
        bad = [t for t in tickers if t in fail_tickers]
        ok = [t for t in tickers if t in close.columns and t not in fail_tickers]
        if bad:
            mod.STAGE_FAILURES["stage1_batches"] = f"1 batch failed of {len(tickers)} names"
        return {"close": close[ok], "volume": vol[ok], "failed_batches": 1 if bad else 0}

    setattr_(mod, "_batch_history", hist)
    setattr_(mod, "_fundamentals", lambda t: (
        {"sector": "X", "market_cap": 1e10, "gross_profitability": _gp(t),
         "target": None, "n_analysts": None}, "ok"))
    setattr_(mod, "_insider", lambda t: (None, "synthetic"))


def _spec():
    s = {f"A{c}": (20.0 + i, 5e6) for i, c in enumerate("BCDEFGHIJKLM")}
    s["NEWSA"] = (30.0, 5e6)
    return s


def _fake_run(mod):
    return mod.run(stage1_keep=10, stage2_keep=6, stage3_keep=4, stage4_keep=3)


def canonical_sha(payload: dict) -> str:
    def rnd(x):
        if isinstance(x, float):
            return round(x, 8)
        if isinstance(x, dict):
            return {k: rnd(v) for k, v in x.items()}
        if isinstance(x, list):
            return [rnd(v) for v in x]
        return x
    p = {k: v for k, v in payload.items() if k not in ("generated_at", "runtime_secs")}
    return hashlib.sha256(json.dumps(rnd(p), sort_keys=True, default=str).encode()).hexdigest()


def _news_env(monkeypatch, tmp_path, themes, issuers=("NEWSA", "AB")):
    _write_digest(tmp_path / "digest", _now() - timedelta(hours=2), themes)
    monkeypatch.setattr(FNS, "digest_dir", lambda: tmp_path / "digest")
    monkeypatch.setattr(FNS, "filings_path", lambda: tmp_path / "none.jsonl")
    csvp = tmp_path / "issuers.csv"
    csvp.write_text("symbol,primary_name\n" + "".join(f"{t},{t} Corp\n" for t in issuers),
                    encoding="utf-8")
    monkeypatch.setattr(FNS, "issuers_path", lambda: csvp)


# ───────────────────────────── flag off / on ─────────────────────────────

def test_flag_off_matches_frozen_expected_without_the_news_module(monkeypatch, tmp_path):
    close, vol = _panel(_spec())
    _install_fakes(F, monkeypatch.setattr, close, vol, list(_spec()))
    monkeypatch.setattr(cfg, "FUNNEL_NEWS_SOURCE_ENABLED", False)
    saved = sys.modules.pop("backend.services.funnel_news_source", None)
    try:
        p = _fake_run(F)
        assert "backend.services.funnel_news_source" not in sys.modules
    finally:
        if saved is not None:
            sys.modules["backend.services.funnel_news_source"] = saved
    assert canonical_sha(p) == EXPECTED_FLAG_OFF_SHA
    assert "news_source" not in p and "added_by_source" not in p


def _on_off(monkeypatch, tmp_path, themes, **kw):
    close, vol = _panel(_spec())
    _install_fakes(F, monkeypatch.setattr, close, vol, list(_spec()), **kw)
    _news_env(monkeypatch, tmp_path, themes)
    monkeypatch.setattr(cfg, "FUNNEL_NEWS_SOURCE_ENABLED", False)
    off = _fake_run(F)
    monkeypatch.setattr(cfg, "FUNNEL_NEWS_SOURCE_ENABLED", True)
    on = _fake_run(F)
    return off, on


def test_flag_on_ranker_list_unchanged_news_in_separate_block(monkeypatch, tmp_path):
    off, on = _on_off(monkeypatch, tmp_path, [_theme(["NEWSA", "AB"])])
    key = lambda p: [(c["ticker"], c["score"], c["stage"]) for c in p["candidates"]]  # noqa: E731
    assert key(on) == key(off)
    assert all(c["sources"][0] == "ranker" for c in on["candidates"])
    added = {r["ticker"]: r for r in on["added_by_source"]}
    assert "NEWSA" not in [c["ticker"] for c in on["candidates"]]
    assert added["NEWSA"]["admitted"] and added["NEWSA"]["sources"] == ["news"]
    assert added["NEWSA"]["screens"] == {"stage0_universe": "pass", "stage1_eligibility": "pass",
                                         "stage3_fundamentals": "pass"}
    assert added["NEWSA"]["stages_not_faced"] == list(FNS.RANKER_ONLY_STAGES)
    ns = on["news_source"]
    assert "ranker candidates carry a news/filing tag" in ns["both_numbers"]
    assert "names added only by news/filing" in ns["both_numbers"]
    assert on["stages"]["stage4_candidates"] == off["stages"]["stage4_candidates"]


def test_pc_own_index_membership_identical_with_flag_on_and_off(monkeypatch, tmp_path):
    from backend.services import pc_own_index as PCI
    off, on = _on_off(monkeypatch, tmp_path, [_theme(["NEWSA", "AB"])])
    content = PCI.contract_content()
    contract = {"content": content, "policy_hash": PCI.policy_hash(content)}
    out = []
    for name, p in (("off", off), ("on", on)):
        fp = tmp_path / f"funnel_{name}.json"
        fp.write_text(json.dumps(p, default=str), encoding="utf-8")
        out.append(PCI.membership(tmp_path / f"idx_{name}", contract=contract, funnel_path=fp,
                                  write=False)["members"])
    assert out[0] == out[1] and out[0]


def test_news_price_fetch_failure_has_its_own_key(monkeypatch, tmp_path):
    off, on = _on_off(monkeypatch, tmp_path, [_theme(["NEWSA"])], fail_tickers=("NEWSA",))
    added = {r["ticker"]: r for r in on["added_by_source"]}
    assert added["NEWSA"]["dropped_by"] == "news_price_fetch_failed"
    # the ranker's own failure line survives untouched; the news fetch has its own key
    assert on["failures"]["stage1_batches"] == off["failures"]["stage1_batches"]         == f"1 batch failed of {len(_spec())} names"
    assert on["failures"]["news_stage1_batches"] == "1 batch failed of 1 names"
    assert "NEWS_PRICE_FETCH_FAILED" in on["failures"]["news_source"]


# ───────────────────────────── admit ─────────────────────────────

def _cand(t, score, q=0.3):
    return F.Candidate(ticker=t, price=50.0, median_dollar_vol=5e7, vol_annual=0.3,
                       quality=q, score=score, stage=4)


def _ranker(n4=5, n3=7):
    s3 = [_cand("R" + "ABCDEFGH"[i], 1.0 - i / 10) for i in range(n3)]
    return s3, s3[:n4]


def _screen_from(close, vol):
    return lambda names: {t: F.eligibility(t, close, vol) for t in names}


def _enrich_ok(cands):
    for c in cands:
        c.quality, c.stage = 0.25, 3
    return list(cands)


def _collect(tmp_path, themes, issuers, **kw):
    _write_digest(tmp_path, _now() - timedelta(hours=3), themes)
    return FNS.collect(_now(), digest_root=tmp_path, filings_enabled=False, issuers=issuers, **kw)


def test_ranker_name_mentioned_by_news_is_tagged_not_moved(tmp_path):
    s3, s4 = _ranker()
    news = _collect(tmp_path, [_theme(["RC"])], _issuers("RC"))
    order = [c.ticker for c in s4]
    res = FNS.admit(news, s3, s4, universe=[], screen_fn=lambda n: {}, enrich_fn=_enrich_ok)
    assert [c.ticker for c in res["final"]] == order
    assert {c.ticker: c.sources for c in res["final"]}["RC"] == ["ranker", "news"]
    assert res["receipt"]["final"]["tagged_in_ranker_final"] == 1
    assert res["receipt"]["added_by_source"]["n_added"] == 0


def test_news_name_kept_at_stage3_cut_at_stage4_faced_every_stage(tmp_path):
    s3, s4 = _ranker()
    news = _collect(tmp_path, [_theme(["RG"])], _issuers("RG"))
    res = FNS.admit(news, s3, s4, universe=[], screen_fn=lambda n: {}, enrich_fn=_enrich_ok)
    row = res["added"][0]
    assert row["ticker"] == "RG" and row["admitted"] and row["stages_not_faced"] == []


def test_news_name_failing_a_screen_is_dropped_with_screen_name(tmp_path):
    close, vol = _panel({"CHEAP": (1.0, 5e7), "THIN": (30.0, 1000.0)})
    news = _collect(tmp_path, [_theme(["CHEAP", "THIN", "NOTL", "NOBR"])],
                    _issuers("CHEAP", "THIN", "NOTL", "NOBR"))
    s3, s4 = _ranker()
    res = FNS.admit(news, s3, s4, universe=["CHEAP", "THIN", "NOBR"],
                    screen_fn=_screen_from(close, vol), enrich_fn=_enrich_ok)
    d = {r["ticker"]: r["dropped_by"] for r in res["added"]}
    assert d == {"CHEAP": "price_band", "THIN": "min_median_dollar_vol",
                 "NOTL": "stage0_universe", "NOBR": "no_price_history"}
    assert [c.ticker for c in res["final"]] == [c.ticker for c in s4]
    assert res["receipt"]["added_by_source"]["n_added"] == 0


def test_fundamentals_failure_is_a_named_drop(tmp_path):
    close, vol = _panel({"NEWSA": (30.0, 5e6)})
    news = _collect(tmp_path, [_theme(["NEWSA"])], _issuers("NEWSA"))
    s3, s4 = _ranker()
    res = FNS.admit(news, s3, s4, universe=["NEWSA"], screen_fn=_screen_from(close, vol),
                    enrich_fn=lambda cands: [])
    assert res["added"][0]["dropped_by"] == "stage3_fundamentals"
    assert res["added"][0]["screens"]["stage3_fundamentals"] == "fail"


def test_empty_ranker_final_stage(tmp_path):
    close, vol = _panel({"NEWSA": (30.0, 5e6)})
    news = _collect(tmp_path, [_theme(["NEWSA"])], _issuers("NEWSA"))
    res = FNS.admit(news, [], [], universe=["NEWSA"], screen_fn=_screen_from(close, vol),
                    enrich_fn=_enrich_ok)
    r = res["receipt"]
    assert res["final"] == [] and r["final"]["news_tag_share_of_ranker_final"] is None
    assert r["added_by_source"]["n_added"] == 1
    assert FNS.both_numbers(r).startswith("0 of 0 ranker candidates")


# ───────────────────────────── direction and content ─────────────────────────────

def test_direction_is_kept_and_inferred_rows_do_not_offer(tmp_path):
    themes = [_theme(["UPP", "MIX", "DWN"], [_imp("UPP", "up"), _imp("MIX", "up"),
                                             _imp("MIX", "down"), _imp("DWN", "down"),
                                             _imp("GUESS", "up", mentioned=False)])]
    news = _collect(tmp_path, themes, _issuers("UPP", "MIX", "DWN", "GUESS"))
    n = news["names"]
    assert (n["UPP"]["net_direction"], n["MIX"]["net_direction"], n["DWN"]["net_direction"]) \
        == ("up", "mixed", "down")
    assert "GUESS" not in n and news["digest"]["inferred_only_not_offered"] == ["GUESS"]
    assert all("direction" in e for e in n["MIX"]["evidence"])


def test_common_words_need_an_issuer_mapping_and_a_mentioned_row(tmp_path):
    # model-inferred common words, even if they ARE real tickers in the issuer table
    themes = [_theme([], [_imp(w, mentioned=False) for w in COMMON_WORDS])]
    news = _collect(tmp_path, themes, _issuers(*COMMON_WORDS))
    assert news["names"] == {}
    assert sorted(news["digest"]["inferred_only_not_offered"]) == sorted(COMMON_WORDS)
    # a mentioned row for a word the issuer table does not hold is refused too
    news2 = _collect(tmp_path / "b", [_theme(list(COMMON_WORDS))], _issuers("ZZZ"))
    assert news2["names"] == {}
    assert sorted(news2["digest"]["no_issuer_mapping"]) == sorted(COMMON_WORDS)
    # no issuer table at all: nothing is offered and it says so
    news3 = _collect(tmp_path / "c", [_theme(["NEWSA"])], None)
    assert news3["names"] == {} and any(d.startswith("ISSUER_MAP_MISSING")
                                        for d in news3["degradations"])


# ───────────────────────────── freshness ─────────────────────────────

def test_stale_digest_adds_nothing_and_is_reported(tmp_path):
    _write_digest(tmp_path, _now() - timedelta(hours=float(cfg.FUNNEL_NEWS_DIGEST_MAX_AGE_HOURS) + 5),
                  [_theme(["NEWSA"])])
    news = FNS.collect(_now(), digest_root=tmp_path, filings_enabled=False,
                       issuers=_issuers("NEWSA"))
    assert news["names"] == {} and news["digest"]["status"] == "STALE"
    assert any(d.startswith("NEWS_DIGEST_STALE") for d in news["degradations"])


def test_empty_digest_falls_back_to_older_typed_one(tmp_path):
    now = _now()
    _write_digest(tmp_path, now - timedelta(hours=1),
                  [{"title": "t", "top_tickers": ["EMPT"], "implications": []}])
    _write_digest(tmp_path, now - timedelta(hours=3), [_theme(["NEWSA"])])
    news = FNS.collect(now, digest_root=tmp_path, filings_enabled=False,
                       issuers=_issuers("NEWSA", "EMPT"))
    assert list(news["names"]) == ["NEWSA"]
    assert news["digest"]["digest_id"] == _stamp(now - timedelta(hours=3))
    assert news["digest"]["skipped"][0]["digest_id"] == _stamp(now - timedelta(hours=1))
    assert any(d.startswith("NEWS_DIGEST_FALLBACK") for d in news["degradations"])


def test_only_empty_digests_report_empty(tmp_path):
    _write_digest(tmp_path, _now() - timedelta(hours=1),
                  [{"title": "t", "top_tickers": ["EMPT"], "implications": []}])
    news = FNS.collect(_now(), digest_root=tmp_path, filings_enabled=False,
                       issuers=_issuers("EMPT"))
    assert news["names"] == {} and news["digest"]["status"] == "EMPTY"
    assert any(d.startswith("NEWS_DIGEST_EMPTY") for d in news["degradations"])


def test_typed_rows_without_tickers_is_a_degradation(tmp_path):
    _write_digest(tmp_path, _now() - timedelta(hours=1), [_theme([], [])])   # one sector row
    news = FNS.collect(_now(), digest_root=tmp_path, filings_enabled=False, issuers={})
    assert news["names"] == {}
    assert any(d.startswith("NEWS_DIGEST_NO_TICKERS") for d in news["degradations"])


def test_missing_digest_is_a_named_degradation(tmp_path):
    news = FNS.collect(_now(), digest_root=tmp_path / "nothing", filings_enabled=False, issuers={})
    assert news["names"] == {} and news["digest"]["status"] == "MISSING"
    assert news["degradations"][0].startswith("NEWS_DIGEST_MISSING")


def test_digest_stamped_after_build_time_is_refused(tmp_path):
    now = _now()
    iss = _issuers("FUTUR", "PAST", "LATE")
    _write_digest(tmp_path, now + timedelta(hours=1), [_theme(["FUTUR"])])
    _write_digest(tmp_path, now - timedelta(hours=3), [_theme(["PAST"])])
    news = FNS.collect(now, digest_root=tmp_path, filings_enabled=False, issuers=iss)
    assert "FUTUR" not in news["names"] and "PAST" in news["names"]
    assert news["digest"]["refused_after_build"] == [_stamp(now + timedelta(hours=1))]
    _write_digest(tmp_path / "b", now - timedelta(minutes=1), [_theme(["LATE"])])
    late = FNS.collect(now, digest_root=tmp_path / "b", filings_enabled=False, issuers=iss)
    assert late["names"] == {} and late["digest"]["status"] == "MISSING"


def test_date_only_or_naive_stamps_are_refused():
    assert FNS._to_dt("2026-01-05") is None
    assert FNS._to_dt("2026-01-05T10:00:00") is None
    assert FNS._to_dt("20260105T100000Z") is not None
    assert FNS._to_dt("2026-01-05T10:00:00+00:00") is not None


# ───────────────────────────── filings ─────────────────────────────

def _filings(tmp_path, rows):
    p = tmp_path / "filing_events.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return p


def test_filings_window_lookahead_items_and_unstamped(tmp_path):
    build = _now()
    start, end = FNS.overnight_window(build)
    assert start < end <= build
    inside = (start + (end - start) / 2).isoformat()
    rows = [
        {"form_type": "8-K", "ticker": "FILA", "public_utc": inside, "first_seen_utc": inside,
         "accession": "a1", "items": ["2.02", "9.01"]},
        {"form_type": "8-K", "ticker": "VOTE", "public_utc": inside, "first_seen_utc": inside,
         "accession": "a5", "items": ["5.07"]},
        {"form_type": "8-K", "ticker": "LATE", "public_utc": (build + timedelta(minutes=5)).isoformat(),
         "first_seen_utc": (build + timedelta(minutes=6)).isoformat(), "items": ["2.02"]},
        {"form_type": "8-K", "ticker": "SEENL", "public_utc": inside,
         "first_seen_utc": (build + timedelta(hours=1)).isoformat(), "items": ["2.02"]},
        {"form_type": "8-K", "ticker": "NAIVE", "public_utc": inside[:19], "items": ["2.02"]},
        {"form_type": "8-K", "ticker": "OLD", "public_utc": (start - timedelta(hours=2)).isoformat(),
         "first_seen_utc": (start - timedelta(hours=1)).isoformat(), "items": ["2.02"]},
        {"form_type": "13F-HR", "ticker": "FUND", "public_utc": inside},
    ]
    news = FNS.collect(build, digest_root=tmp_path / "nod", filings=_filings(tmp_path, rows),
                       filings_enabled=True, issuers={})
    assert list(news["names"]) == ["FILA"]
    assert news["names"]["FILA"]["sources"] == ["filing"]
    f = news["filings"]
    assert f["refused_after_build"] == 2 and f["refused_unstamped"] == 1
    assert f["dropped_by_item"] == {"5.07": 1} and f["n_8k_rows"] == 6


def test_per_source_caps_and_strength_order(tmp_path):
    build = _now()
    start, end = FNS.overnight_window(build)
    inside = (start + (end - start) / 2).isoformat()
    fil = [f"F{c}" for c in "ABCDEFGH"]
    rows = [{"form_type": "8-K", "ticker": t, "public_utc": inside, "first_seen_utc": inside,
             "items": ["2.02", "1.01"] if t == "FH" else ["8.01"]} for t in fil]
    _write_digest(tmp_path / "d", build - timedelta(hours=2),
                  [_theme(["NA", "NB"], [_imp("NB", "up")])])
    news = FNS.collect(build, digest_root=tmp_path / "d", filings=_filings(tmp_path, rows),
                       filings_enabled=True, issuers=_issuers("NA", "NB"))
    names = ["NA", "NB"] + fil
    close, vol = _panel({t: (30.0, 5e6) for t in names})
    res = FNS.admit(news, [], [], universe=names, screen_fn=_screen_from(close, vol),
                    enrich_fn=_enrich_ok, max_enrich_news=1, max_enrich_filing=2)
    d = {r["ticker"]: r for r in res["added"]}
    assert d["NB"]["admitted"] and d["NA"]["dropped_by"] == "news_enrich_cap"   # 2 rows beat 1
    adm_f = [t for t in fil if d[t]["admitted"]]
    assert len(adm_f) == 2 and "FH" in adm_f                                    # 2 items first
    assert sum(1 for t in fil if d[t]["dropped_by"] == "filing_enrich_cap") == 6


def test_overnight_window_on_a_weekday_evening_and_morning():
    today = _now().date()
    wed = today - timedelta(days=(today.weekday() - 2) % 7 or 7)
    eve = pd.Timestamp(f"{wed} 20:00", tz="America/New_York").to_pydatetime()
    s, e = FNS.overnight_window(eve)
    assert pd.Timestamp(s).tz_convert("America/New_York").hour == 16 and e == eve
    mid = pd.Timestamp(f"{wed} 11:00", tz="America/New_York").to_pydatetime()
    s, e = FNS.overnight_window(mid)
    s_et, e_et = (pd.Timestamp(x).tz_convert("America/New_York") for x in (s, e))
    assert s_et.date() == wed - timedelta(days=1) and (e_et.hour, e_et.minute) == (9, 30)


# ── CH-35 slice 2: event nodes as a third source (EVENT_NODES_FUNNEL_SOURCE_ENABLED) ──

def _ev_store(tmp_path, now):
    from backend.services import event_nodes as EN

    def node(eid, primary, imp0, built, co=(), graph=()):
        fs = now - timedelta(hours=6)
        return {"event_id": eid, "primary_ticker": primary, "first_seen_utc": fs.isoformat(),
                "built_now_utc": built.isoformat(), "content_hash": eid, "version_key": eid, "n_evidence": 3,
                "importance": {"importance_0": imp0, "facts": {"n_publishers": 4}},
                "decay": {"half_life_hours": 72.0}, "parent_id": "par_" + eid[3:],
                "evidence": [{"item_key": eid, "title": "LICENSED TITLE"}],
                "connected_names": {"co_mention": [{"ticker": t, "n_items": 1} for t in co],
                                    "graph": [{"ticker": t, "link": lk, "weight": w} for t, lk, w in graph]}}
    p = tmp_path / "ev" / EN.STORE_NAME
    EN.append_rows(p, [
        node("ev_big", "EVA", 9.0, now - timedelta(hours=1), co=("EVB",),
             graph=(("EVC", "co_coverage", 0.7), ("EVD", "shared_sector", None))),
        node("ev_small", "EVS", 1.0, now - timedelta(hours=1), co=("EVT",)),         # under the threshold
        node("ev_late", "EVL", 9.0, now + timedelta(minutes=5)),                       # built after the build
    ])
    return p


def test_event_source_off_is_exactly_the_news_and_filing_collect(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "EVENT_NODES_FUNNEL_SOURCE_ENABLED", False)
    store = _ev_store(tmp_path, _now())
    a = _collect(tmp_path, [_theme(["NEWSA"])], _issuers("NEWSA"))
    b = _collect(tmp_path, [_theme(["NEWSA"])], _issuers("NEWSA"), event_store=store)
    assert a == b and "events" not in a
    s3, s4 = _ranker()
    res = FNS.admit(a, s3, s4, universe=[], screen_fn=lambda n: {}, enrich_fn=_enrich_ok)
    assert "event" not in res["receipt"]["caps"] and "event" not in res["receipt"]["offered"]


def test_event_source_on_offers_primary_and_linked_names_under_the_same_screens(tmp_path, monkeypatch):
    now = _now()
    monkeypatch.setattr(cfg, "EVENT_NODES_FUNNEL_SOURCE_ENABLED", True)
    monkeypatch.setattr(cfg, "EVENT_NODES_FUNNEL_MAX_ENRICH", 1)
    store = _ev_store(tmp_path, now)
    news = _collect(tmp_path, [_theme(["NEWSA"])], _issuers("NEWSA"), event_store=store)
    assert news["events"]["n_events_offering"] == 1 and news["events"]["n_versions_after_build_skipped"] == 1
    assert set(news["names"]) == {"NEWSA", "EVA", "EVB", "EVC"}        # shared_sector EVD is not a link
    assert news["names"]["EVB"]["sources"] == ["event"]
    e = news["names"]["EVA"]["evidence"][0]
    assert e["event_id"] == "ev_big" and e["via"] == "primary" and "title" not in e
    assert "LICENSED TITLE" not in json.dumps(news)
    close, vol = _panel({"EVA": (30.0, 5e7), "EVB": (30.0, 5e7), "EVC": (1.0, 5e7), "NEWSA": (30.0, 5e7)})
    s3, s4 = _ranker()
    res = FNS.admit(news, s3, s4, universe=["EVA", "EVB", "EVC", "NEWSA"],
                    screen_fn=_screen_from(close, vol), enrich_fn=_enrich_ok)
    d = {r["ticker"]: (r["admitted"], r["dropped_by"]) for r in res["added"]}
    assert d["EVC"] == (False, "price_band")                            # the same screen as news
    assert d["EVA"] == (True, None)                                     # primary outranks a co-mention
    assert d["EVB"] == (False, "event_enrich_cap")
    assert d["NEWSA"] == (True, None)
    assert res["receipt"]["caps"]["event"] == 1 and res["receipt"]["offered"]["event_only"] == 3
    assert [c.ticker for c in res["final"]] == [c.ticker for c in s4]
