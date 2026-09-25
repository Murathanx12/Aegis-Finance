"""Thesis cards (Builder O5, 2026-09-25): engine side, quest, parse, synthesis,
the card file, and the CLI's resume / refusal behaviour.

Every test is offline: the OpenClaw quest and the DeepSeek synthesis are
injected as fakes, and fixture dates are derived from a fixed `asof` that the
fixtures are BUILT around (never a calendar moment that can pass).
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from backend.services import thesis_card as TC

ASOF = "2026-09-25"


def _bars(ticker="AAA", n=130, start_px=10.0, drift=0.002, vol=1_000_000):
    end = pd.Timestamp(ASOF)
    dates = pd.bdate_range(end=end, periods=n)
    rng = np.random.default_rng(7)
    rets = drift + rng.normal(0, 0.01, n)
    px = start_px * np.exp(np.cumsum(rets))
    return pd.DataFrame({"symbol": ticker, "date": dates, "open": px, "high": px,
                         "low": px, "close": px, "volume": vol})


def _revisions():
    a = pd.Timestamp(ASOF)
    rows = [
        # inside 90d
        ("AAA", a - pd.Timedelta(days=5), "Firm1", "Raises", 0.10, True),
        ("AAA", a - pd.Timedelta(days=20), "Firm2", "Raises", 0.20, True),
        ("AAA", a - pd.Timedelta(days=40), "Firm1", "Lowers", -0.05, True),
        # outside 90d
        ("AAA", a - pd.Timedelta(days=200), "Firm3", "Raises", 0.5, True),
        # FUTURE row: must never be read
        ("AAA", a + pd.Timedelta(days=3), "Firm9", "Raises", 0.9, True),
        # not PIT-safe: must never be read
        ("AAA", a - pd.Timedelta(days=2), "Firm8", "Raises", 0.9, False),
        ("BBB", a - pd.Timedelta(days=2), "Firm1", "Lowers", -0.1, True),
    ]
    return pd.DataFrame([{
        "ticker": t, "event_date": str(d), "firm": f, "target_action": ta,
        "target_change": tc, "pit_safe": ps, "from_grade": "Hold",
        "to_grade": "Buy", "action": "main", "prior_target": 10.0,
        "current_target": 11.0} for t, d, f, ta, tc, ps in rows])


def _news():
    a = date.fromisoformat(ASOF)
    return [
        {"source": "yfinance_ticker_news",
         "published_utc": f"{a - timedelta(days=1)}T10:00:00+00:00",
         "title": "AAA wins order", "url": "https://x/1", "tickers": ["AAA"]},
        {"source": "alpaca_benzinga_news",
         "published_utc": f"{a - timedelta(days=3)}T10:00:00+00:00",
         "title": "AAA guidance", "url": "https://x/2", "tickers": ["AAA", "BBB"]},
        # duplicate url -> counted once
        {"source": "gdelt_doc_v2",
         "published_utc": f"{a - timedelta(days=3)}T11:00:00+00:00",
         "title": "AAA guidance", "url": "https://x/2", "tickers": ["AAA"]},
        # too old
        {"source": "yfinance_ticker_news",
         "published_utc": f"{a - timedelta(days=45)}T10:00:00+00:00",
         "title": "old", "url": "https://x/3", "tickers": ["AAA"]},
        # published after asof -> not knowable at asof
        {"source": "yfinance_ticker_news",
         "published_utc": f"{a + timedelta(days=1)}T10:00:00+00:00",
         "title": "future", "url": "https://x/4", "tickers": ["AAA"]},
    ]


def _catalysts():
    a = date.fromisoformat(ASOF)
    return [
        {"date": str(a + timedelta(days=30)), "ticker": "AAA", "kind": "earnings",
         "what": "Q3", "source_url": "https://ir/aaa", "verified_from": "primary"},
        {"date": str(a + timedelta(days=10)), "ticker": "AAA", "kind": "pdufa",
         "what": "drug X", "source_url": "https://agg", "verified_from": "aggregator"},
        {"date": str(a - timedelta(days=10)), "ticker": "AAA", "kind": "earnings",
         "what": "past", "source_url": "", "verified_from": "primary"},
    ]


def _preds():
    return [
        {"ticker": "AAA", "specialist": "investigator:evidence_v3", "horizon_days": 1,
         "probability": 0.55, "made_at": f"{ASOF}T01:00:00+00:00"},
        {"ticker": "AAA", "specialist": "investigator:evidence_v3", "horizon_days": 1,
         "probability": 0.48, "made_at": "2026-09-20T01:00:00+00:00"},
        {"ticker": "AAA", "specialist": "investigator:evidence_v3", "horizon_days": 5,
         "probability": 0.52, "made_at": f"{ASOF}T01:00:00+00:00"},
        # persona row: never used
        {"ticker": "AAA", "specialist": "geopolitical", "horizon_days": 1,
         "probability": 0.99, "made_at": f"{ASOF}T02:00:00+00:00"},
    ]


# ─────────────────────────────── engine side ────────────────────────────────

def test_engine_side_every_key_present_even_with_no_inputs():
    e = TC.engine_side("ZZZ", asof=ASOF, bars=None, revisions=None,
                       news_rows=None, catalysts=None, predictions=None)
    for k in TC.ENGINE_KEYS:
        assert k in e, k
        assert e[k] is None, k
    assert e["news_30d_count"] is None      # unknown, not zero
    assert set(e["engine_unavailable"]) >= {"bars", "revisions", "news", "predictions"}


def test_engine_side_on_fixtures():
    e = TC.engine_side("AAA", asof=ASOF, bars=_bars(), revisions=_revisions(),
                       news_rows=_news(), catalysts=_catalysts(),
                       predictions=_preds(),
                       fundamentals={"rev_qoq": 0.1, "gross_margin": 0.5,
                                     "gross_margin_chg": 0.02, "inflection_flag": True})
    assert e["engine_px"] > 0
    for k in ("engine_mom_21", "engine_mom_63", "engine_vol_63"):
        assert isinstance(e[k], float)
    assert e["engine_band"] in ("mega", "large", "mid", "small")
    assert e["engine_cost_bps"] > 0
    # PIT: the future row and the non-PIT row are excluded; 200d row excluded
    assert e["engine_net_raises_90d"] == 1          # 2 raises - 1 lower
    assert e["engine_n_firms_90d"] == 2
    assert e["engine_median_target_change_90d"] == pytest.approx(0.10)
    assert e["engine_rev_qoq"] == 0.1 and e["engine_inflection_flag"] is True
    assert e["engine_forecast_p_up_1d"] == 0.55      # latest investigator row
    assert e["engine_forecast_p_up_5d"] == 0.52
    assert e["news_30d_count"] == 2                  # dedup by url, window, PIT
    assert len(e["news_30d_top"]) == 2
    assert e["news_30d_top"][0].startswith(
        str(date.fromisoformat(ASOF) - timedelta(days=1)))
    assert all(s.count(" | ") == 3 for s in e["news_30d_top"])
    # only FUTURE catalysts, sorted
    ud = e["engine_upcoming_dates"]
    assert len(ud) == 2 and ud[0].split(" | ")[1] == "pdufa"
    assert ud[0].endswith("aggregator")
    assert len(e["engine_analyst_actions_90d"]) == 3


def test_engine_side_bars_too_short_gives_none_not_garbage():
    e = TC.engine_side("AAA", asof=ASOF, bars=_bars(n=30), revisions=None,
                       news_rows=[], catalysts=[], predictions=[])
    assert e["engine_px"] is not None
    assert e["engine_mom_21"] is not None
    assert e["engine_mom_63"] is None
    assert e["news_30d_count"] == 0                   # measured zero


def test_engine_side_ignores_bars_after_asof():
    b = _bars(n=130)
    late = b.iloc[[-1]].copy()
    late["date"] = pd.Timestamp(ASOF) + pd.Timedelta(days=3)
    late["close"] = 9999.0
    e = TC.engine_side("AAA", asof=ASOF, bars=pd.concat([b, late]),
                       revisions=None, news_rows=[], catalysts=[], predictions=[])
    assert e["engine_px"] != 9999.0


def test_engine_side_ticker_with_no_revision_rows_is_none():
    e = TC.engine_side("CCC", asof=ASOF, bars=None, revisions=_revisions(),
                       news_rows=[], catalysts=[], predictions=[])
    assert e["engine_n_firms_90d"] is None


# ───────────────────────────── quest prompt / parse ─────────────────────────

def test_quest_prompt_carries_questions_keys_and_policy():
    e = TC.engine_side("AAA", asof=ASOF, bars=_bars(), revisions=None,
                       news_rows=[], catalysts=_catalysts(), predictions=[])
    p = TC.quest_prompt("AAA", e)
    assert "AAA" in p
    assert len(TC.TEN_QUESTIONS) == 10
    for q in TC.TEN_QUESTIONS:
        assert q in p
    for k in TC.WEB_KEYS:
        assert f'"{k}"' in p, k
    assert "FLAT JSON" in p
    assert "analyst action" in p.lower() and "investor relations" in p.lower()
    assert "blog" in p.lower()


def test_parse_reply_clean_json_keeps_only_known_keys():
    body = {k: None for k in TC.WEB_KEYS}
    body.update({"name": "Triple A",
                 "analyst_actions": ["2026-09-20 | GS | raise | 10->12"],
                 "sources": ["https://ir/aaa"], "consensus_n": 12,
                 "invented_key": "x"})
    out = TC.parse_reply("chatter\n" + json.dumps(body) + "\nbye")
    assert out["parse"] == "ok"
    assert out["name"] == "Triple A"
    assert "invented_key" not in out
    assert out["parse_dropped_keys"] == ["invented_key"]


def test_parse_reply_refuses_nested_objects():
    out = TC.parse_reply(json.dumps({"name": "A", "demand": {"x": 1},
                                     "analyst_actions": [{"firm": "GS"}]}))
    assert out["demand"] is None
    assert out["analyst_actions"] is None
    assert set(out["parse_rejected_nested"]) == {"demand", "analyst_actions"}


def test_parse_reply_degraded_lifts_scalars_and_invents_nothing():
    txt = ('{"name": "Triple A", "consensus_n": 7, "demand": "strong "unquoted" '
           'demand", "product": "widgets", "sources": ["https://a", "https://b"]')
    out = TC.parse_reply(txt + "}")
    assert out["parse"] == "degraded"
    assert out["name"] == "Triple A"
    assert out["consensus_n"] == 7
    assert out["product"] == "widgets"
    assert out["sources"] == ["https://a", "https://b"]
    assert out["demand"] is None               # unreadable -> None, not guessed
    for k in TC.WEB_KEYS:
        assert k in out


def test_parse_reply_no_json_is_refused():
    out = TC.parse_reply("I could not browse today.")
    assert out["parse"] == "refused"
    out = TC.parse_reply("")
    assert out["parse"] == "refused"


# ───────────────────────────────── synthesis ────────────────────────────────

def test_synthesize_flat_reply_and_standing_findings_in_prompt():
    seen = {}

    def fake(system, user, **kw):
        seen["system"], seen["user"], seen["kw"] = system, user, kw
        return json.dumps({"bull": "b", "bear": "r", "falsifier": "f",
                           "verdict": "supports", "confidence": "med"})
    e = TC.engine_side("AAA", asof=ASOF, bars=None, revisions=None,
                       news_rows=[], catalysts=[], predictions=[])
    s = TC.synthesize(e, {"name": "A", "demand": "d"}, model="deepseek-chat",
                      call_fn=fake)
    assert s["verdict"] == "supports" and s["confidence"] == "med"
    assert s["synth_status"] == "OK"
    for tag in ("§17", "§59", "§63", "§64"):
        assert tag in seen["system"]
    assert "FLAT JSON" in seen["system"]
    assert seen["kw"]["purpose"] == TC.SYNTH_PURPOSE


def test_synthesize_rejects_out_of_vocabulary_verdict():
    s = TC.synthesize({}, {}, model="m", call_fn=lambda *a, **k: json.dumps(
        {"bull": "b", "bear": "r", "falsifier": "f", "verdict": "BUY NOW",
         "confidence": "extreme"}))
    assert s["verdict"] is None and s["confidence"] is None
    assert s["synth_status"] == "INVALID_VOCAB"


def test_synthesize_none_reply_is_a_status_not_a_crash():
    s = TC.synthesize({}, {}, model="m", call_fn=lambda *a, **k: None)
    assert s["synth_status"] == "NO_REPLY" and s["verdict"] is None


# ────────────────────────────── the card file ───────────────────────────────

def _card(**over):
    e = TC.engine_side("AAA", asof=ASOF, bars=_bars(), revisions=_revisions(),
                       news_rows=_news(), catalysts=_catalysts(), predictions=_preds())
    web = TC.parse_reply(json.dumps({
        "name": "Triple A", "consensus_n": 10, "consensus_mean_target": 20.0,
        "consensus_source": "https://c",
        "analyst_actions": ["2026-09-21 | MS | raise | 10->12"],
        "upcoming_dates": ["2026-10-30 | earnings | Q3 | https://ir | primary"],
        "sources": ["https://ir/aaa"]}))
    syn = {"bull": "b", "bear": "r", "falsifier": "f", "verdict": "neutral",
           "confidence": "low", "synth_status": "OK"}
    c = TC.build_card("AAA", kind="holding", asof=ASOF, engine=e, web=web,
                      synth=syn, meta={"openclaw_log_path": "x.log",
                                       "openclaw_elapsed_s": 12.0,
                                       "deepseek_cost_usd": 0.001})
    c.update(over)
    return c


def test_build_card_has_every_spec_key_and_valid():
    c = _card()
    for k in TC.CARD_KEYS:
        assert k in c, k
    assert TC.validate_card(c) == []
    assert c["consensus_implied_upside"] == pytest.approx(
        20.0 / c["engine_px"] - 1, rel=1e-3)
    assert len(c["analyst_actions"]) <= 10
    # parquet actions + web action merged
    assert any("MS" in a for a in c["analyst_actions"])
    assert any("Firm1" in a for a in c["analyst_actions"])
    assert c["upcoming_dates"][0].split(" | ")[0] <= c["upcoming_dates"][-1].split(" | ")[0]


def test_card_hash_is_stable_and_detects_edits():
    c = _card()
    h = c["card_hash"]
    assert TC.card_hash(c) == h
    c2 = dict(c, bull="changed")
    assert TC.card_hash(c2) != h
    assert any("card_hash" in p for p in TC.validate_card(c2))


def test_validate_reports_drift_without_rewriting():
    c = _card()
    del c["team"]
    c["verdict"] = "bullish"
    c["news_30d_top"] = "not a list"
    before = json.dumps(c, sort_keys=True, default=str)
    probs = TC.validate_card(c)
    assert json.dumps(c, sort_keys=True, default=str) == before
    joined = " ".join(probs)
    assert "missing key: team" in joined
    assert "verdict" in joined and "news_30d_top" in joined


def test_write_read_cards_roundtrip(tmp_path):
    c = _card()
    p = TC.write_card(c, root=tmp_path)
    assert p == tmp_path / ASOF / "AAA.json"
    got = TC.read_cards(ASOF, root=tmp_path)
    assert len(got) == 1 and got[0]["ticker"] == "AAA"
    (tmp_path / ASOF / "BROKEN.json").write_text("{nope", encoding="utf-8")
    got = TC.read_cards(ASOF, root=tmp_path)
    assert any(g.get("_unreadable") for g in got)


def test_refusal_card_is_valid_and_keeps_engine_side():
    e = TC.engine_side("AAA", asof=ASOF, bars=_bars(), revisions=None,
                       news_rows=[], catalysts=[], predictions=[])
    c = TC.refusal_card("AAA", kind="personal", asof=ASOF, engine=e,
                        verdict="REFUSED_EMPTY_LOG", why="empty",
                        meta={"openclaw_log_path": "l", "openclaw_elapsed_s": 3.0})
    assert c["verdict"] == "REFUSED_EMPTY_LOG"
    assert c["engine_px"] == e["engine_px"]
    assert TC.validate_card(c) == []


def test_digest_one_line_per_card(tmp_path):
    TC.write_card(_card(), root=tmp_path)
    b = _card(ticker="BBB")
    b["card_hash"] = TC.card_hash(b)
    TC.write_card(b, root=tmp_path)
    p = TC.write_digest(ASOF, root=tmp_path)
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines()
             if ln.startswith("| ")]
    body = [ln for ln in lines if not ln.startswith("| ticker")]
    assert len(body) == 2
    assert "neutral" in body[0]


# ─────────────────────────────── the CLI runner ─────────────────────────────

def _fake_inputs():
    return {"bars": _bars(), "revisions": _revisions(), "news_rows": _news(),
            "catalysts": _catalysts(), "predictions": _preds(), "fundamentals": {}}


def test_run_resumes_and_refuses_empty_log(tmp_path):
    from scripts import thesis_cards as S

    calls = {"quest": [], "synth": 0}

    def quest(ticker, prompt, *, model, timeout, log_dir):
        calls["quest"].append(ticker)
        log = log_dir / f"{ticker}.openclaw.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        if ticker == "EMPTY":
            log.write_text("", encoding="utf-8")
            return {"status": "EMPTY_LOG", "reply": "", "elapsed_s": 1.0,
                    "log_path": str(log), "cost_usd": 0.0}
        reply = json.dumps({"name": ticker, "sources": ["https://ir"]})
        log.write_text(reply, encoding="utf-8")
        return {"status": "OK", "reply": reply, "elapsed_s": 2.0,
                "log_path": str(log), "cost_usd": 0.01}

    def synth(engine, web, *, model):
        calls["synth"] += 1
        return {"bull": "b", "bear": "r", "falsifier": "f", "verdict": "neutral",
                "confidence": "low", "synth_status": "OK"}

    # a seed card already there for AAA -> skipped
    TC.write_card(_card(), root=tmp_path)
    uni = [{"ticker": "AAA", "kind": "holding", "source": "murat_book"},
           {"ticker": "EMPTY", "kind": "personal", "source": "x"},
           {"ticker": "BBB", "kind": "competition", "source": "y"}]
    res = S.run(universe=uni, asof=ASOF, root=tmp_path, max_quests=10,
                cap_usd=5.0, parallel=1, model="m", inputs=_fake_inputs(),
                quest_fn=quest, synth_fn=synth, spend_fn=lambda day: 0.0)
    assert calls["quest"] == ["EMPTY", "BBB"]
    assert calls["synth"] == 1                    # no synthesis on a refusal
    cards = {c["ticker"]: c for c in TC.read_cards(ASOF, root=tmp_path)}
    assert cards["EMPTY"]["verdict"] == "REFUSED_EMPTY_LOG"
    assert cards["BBB"]["kind"] == "competition"
    assert TC.validate_card(cards["BBB"]) == []
    assert res["n_skipped_existing"] == 1
    assert (tmp_path / ASOF / "DIGEST.md").exists()
    # second run: everything exists -> nothing asked
    calls["quest"].clear()
    S.run(universe=uni, asof=ASOF, root=tmp_path, max_quests=10, cap_usd=5.0,
          parallel=1, model="m", inputs=_fake_inputs(), quest_fn=quest,
          synth_fn=synth, spend_fn=lambda day: 0.0)
    assert calls["quest"] == []


def test_run_refuses_over_cap_and_unknown_spend(tmp_path):
    from scripts import thesis_cards as S
    asked = []

    def quest(ticker, prompt, **kw):
        asked.append(ticker)
        return {"status": "OK", "reply": "{}", "elapsed_s": 0, "log_path": "",
                "cost_usd": 0}

    uni = [{"ticker": "AAA", "kind": "holding", "source": "s"}]
    r = S.run(universe=uni, asof=ASOF, root=tmp_path, max_quests=5, cap_usd=1.0,
              parallel=1, model="m", inputs=_fake_inputs(), quest_fn=quest,
              synth_fn=lambda *a, **k: {}, spend_fn=lambda day: 1.5)
    assert asked == [] and r["state"] == "REFUSED_CAP"
    r = S.run(universe=uni, asof=ASOF, root=tmp_path, max_quests=5, cap_usd=1.0,
              parallel=1, model="m", inputs=_fake_inputs(), quest_fn=quest,
              synth_fn=lambda *a, **k: {}, spend_fn=lambda day: None)
    assert asked == [] and r["state"] == "REFUSED_CAP"
    assert "UNKNOWN" in r["why"]


def test_run_respects_max_quests(tmp_path):
    from scripts import thesis_cards as S
    asked = []

    def quest(ticker, prompt, *, model, timeout, log_dir):
        asked.append(ticker)
        return {"status": "OK", "reply": "{}", "elapsed_s": 0, "log_path": "",
                "cost_usd": 0}

    uni = [{"ticker": t, "kind": "personal", "source": "s"} for t in ("A1", "A2", "A3")]
    S.run(universe=uni, asof=ASOF, root=tmp_path, max_quests=2, cap_usd=5,
          parallel=2, model="m", inputs=_fake_inputs(), quest_fn=quest,
          synth_fn=lambda e, w, *, model: {"verdict": "neutral", "confidence": "low",
                                           "bull": "", "bear": "", "falsifier": "",
                                           "synth_status": "OK"},
          spend_fn=lambda day: 0.0)
    assert len(asked) == 2


def test_default_universe_order_dedup_and_kinds(tmp_path):
    from scripts import thesis_cards as S
    book = tmp_path / "murat_book.yaml"
    book.write_text("positions:\n  - ticker: DKNG\n  - ticker: NTLA\n",
                    encoding="utf-8")
    draft = tmp_path / "draft.json"
    draft.write_text(json.dumps({"positions": [{"ticker": "VRT"}, {"ticker": "NTLA"},
                                               {"ticker": "CASH"}]}),
                     encoding="utf-8")
    pharma = tmp_path / "pharma.md"
    pharma.write_text(
        "## Suggested candidate list (17 names, weight-ordered within bucket)\n\n"
        "**Bucket 1**: VRTX 4%, GILD 3% (NVO\nresearched and rejected, 0%)\n"
        "**Bucket 3**: WST 5%, NTLA 1% (TMO 2%, CATX 1% if a\nspeculative sleeve)\n\n"
        "---\n", encoding="utf-8")
    glob_ = tmp_path / "global.md"
    glob_.write_text(
        "### Book A — x\n| # | Ticker | Weight |\n|---|---|---|\n"
        "| 1 | 000660 KS (SK Hynix) | 10% |\n| 2 | 2330 TT (TSMC) | 9% |\n"
        "| 3 | NOVO B DC (Novo) | 9% |\n| 4 | ARGX (argenx) | 9% |\n"
        "| 5 | KAP LI (Kazatomprom) | 9% |\n| 6 | 1772 HK (Ganfeng) | 9% |\n"
        "### Book B — y\n| # | Ticker | Weight |\n|---|---|---|\n"
        "| 1 | SAAB B SS (Saab) | 10% |\n| 2 | 000660 KS (SK Hynix) | 10% |\n"
        "| 3 | 7011 JP (MHI) | 9% |\n| 4 | ENR GY (Siemens Energy) | 9% |\n\n---\n",
        encoding="utf-8")
    u = S.default_universe(murat_book=book, draft=draft, pharma=pharma,
                           global_notes=glob_)
    ts = [r["ticker"] for r in u]
    assert ts[:2] == ["DKNG", "NTLA"]
    assert ts.count("NTLA") == 1 and "CASH" not in ts
    kinds = {r["ticker"]: r["kind"] for r in u}
    assert kinds["DKNG"] == "holding" and kinds["VRT"] == "personal"
    assert kinds["VRTX"] == "personal"
    assert "TMO" not in ts and "NVO" not in ts
    for t in ("000660.KS", "2330.TW", "NOVO-B.CO", "ARGX", "KAP.IL", "1772.HK",
              "SAAB-B.ST", "7011.T", "ENR.DE"):
        assert t in ts, t
    assert kinds["000660.KS"] == "competition"
    assert ts.count("000660.KS") == 1


def test_dry_run_builds_prompt_without_calling(tmp_path, capsys):
    from scripts import thesis_cards as S

    def boom(*a, **k):
        raise AssertionError("dry run must not call anything")
    uni = [{"ticker": "AAA", "kind": "holding", "source": "s"}]
    r = S.run(universe=uni, asof=ASOF, root=tmp_path, max_quests=5, cap_usd=5,
              parallel=1, model="m", inputs=_fake_inputs(), quest_fn=boom,
              synth_fn=boom, spend_fn=boom, dry_run=True)
    out = capsys.readouterr().out
    assert r["state"] == "DRY_RUN"
    assert "AAA" in out and "FLAT JSON" in out
    assert not (tmp_path / ASOF / "AAA.json").exists()
