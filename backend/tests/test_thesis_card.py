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
    assert len(TC.TWELVE_QUESTIONS) == 12 and len(TC.ANSWER_KEYS) == 12
    for q in TC.QUESTIONS:
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
    out = TC.parse_reply(json.dumps({"name": "A", "bottleneck": {"x": 1},
                                     "analyst_actions": [{"firm": "GS"}]}))
    assert out["bottleneck"] is None
    assert out["analyst_actions"] is None
    assert set(out["parse_rejected_nested"]) == {"bottleneck", "analyst_actions"}


def test_parse_reply_degraded_lifts_scalars_and_invents_nothing():
    txt = ('{"name": "Triple A", "consensus_n": 7, "bottleneck": "strong "unquoted" '
           'demand", "demand_product": "widgets 2026-09-01", '
           '"sources": ["https://a", "https://b"]')
    out = TC.parse_reply(txt + "}")
    assert out["parse"] == "degraded"
    assert out["name"] == "Triple A"
    assert out["consensus_n"] == 7
    assert out["demand_product"] == "widgets 2026-09-01"
    assert out["sources"] == ["https://a", "https://b"]
    assert out["bottleneck"] is None           # unreadable -> None, not guessed
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


# ── review 2026-09-25 row 8: every card becomes forecast rows ────────────────

@pytest.mark.parametrize("verdict,conf,p", [
    ("supports", "high", 0.60), ("supports", "med", 0.56), ("supports", "low", 0.53),
    ("neutral", "high", 0.50), ("neutral", "low", 0.50),
    ("against", "high", 0.40), ("against", "med", 0.44), ("against", "low", 0.47),
])
def test_forecast_probability_maps_verdict_and_shrinks_by_confidence(verdict, conf, p):
    assert TC.forecast_probability(verdict, conf) == pytest.approx(p)


def test_forecast_rows_shape():
    c = _card(verdict="supports", confidence="med", falsifier="Q3 misses")
    rows = TC.forecast_rows(c, today=ASOF)
    assert [r["horizon_days"] for r in rows] == list(TC.FORECAST_HORIZONS)
    for r in rows:
        assert r["specialist"] == "thesis_card:v1"
        assert r["observable"] == "beats_benchmark" and r["benchmark"] == "SPY"
        assert r["probability"] == pytest.approx(0.56)
        assert r["counter_thesis"] == "Q3 misses"
        assert r["licence"] == "PRODUCT_EXPERIMENT"
        assert r["inputs_used"]["card_hash"] == c["card_hash"]
        assert r["decision_date"] == ASOF
    snap = TC.forecast_snapshot(c)
    assert snap["card_hash"] == c["card_hash"]
    assert all(k in snap for k in TC.ENGINE_KEYS)


@pytest.mark.parametrize("over", [
    {"verdict": "REFUSED_EMPTY_LOG"}, {"verdict": "maybe"}, {"confidence": None},
    {"asof": "2026-09-26"},                                    # after `today`
])
def test_a_card_that_is_not_a_forecast_writes_no_row(over):
    assert TC.forecast_rows(_card(**over), today=ASOF) == []
    assert TC.forecast_rows({"_unreadable": "x.json"}, today=ASOF) == []


def test_refusal_card_writes_no_row():
    e = TC.engine_side("AAA", asof=ASOF, bars=_bars(), revisions=_revisions(),
                       news_rows=_news(), catalysts=_catalysts(), predictions=_preds())
    c = TC.refusal_card("AAA", kind="holding", asof=ASOF, engine=e,
                        verdict="REFUSED_EMPTY_LOG", why="empty")
    assert TC.forecast_rows(c, today=ASOF) == []


def test_write_forecasts_is_idempotent_per_card_hash(tmp_path):
    from backend.services import belief_state as B
    led = tmp_path / "predictions.jsonl"
    a = _card(verdict="supports", confidence="high")
    b = _card(ticker="BBB", verdict="REFUSED_EMPTY_LOG")
    r1 = TC.write_forecasts([a, b], today=ASOF, path=led)
    assert r1["n_rows_written"] == 2 and r1["n_not_a_forecast"] == 1
    r2 = TC.write_forecasts([a, b], today=ASOF, path=led)       # same day, again
    assert r2["n_rows_written"] == 0 and r2["n_already_written"] == 2
    r3 = TC.write_forecasts([a], today="2026-09-26", path=led)  # a later backfill
    assert r3["n_rows_written"] == 0
    rows = B.read_predictions(led)
    assert len(rows) == 2 and {r["probability"] for r in rows} == {0.6}


def test_run_writes_forecast_rows_beside_a_tmp_root_never_the_real_ledger(tmp_path):
    from scripts import thesis_cards as S

    def quest(ticker, prompt, *, model, timeout, log_dir):
        return {"status": "OK", "reply": json.dumps({"name": ticker}), "elapsed_s": 0,
                "log_path": "", "cost_usd": 0}

    uni = [{"ticker": "SUP", "kind": "personal", "source": "s"}]
    res = S.run(universe=uni, asof=ASOF, root=tmp_path, max_quests=5, cap_usd=5,
                parallel=1, model="m", inputs=_fake_inputs(), quest_fn=quest,
                synth_fn=lambda e, w, *, model: {"verdict": "against", "confidence": "high",
                                                 "bull": "b", "bear": "r", "falsifier": "f",
                                                 "synth_status": "OK"},
                spend_fn=lambda day: 0.0)
    assert res["forecast_rows_written"] == 2
    led = tmp_path / "_predictions.jsonl"
    rows = [json.loads(x) for x in led.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert {r["probability"] for r in rows} == {0.4}
    out = S.forecast(ASOF, root=tmp_path, path=led, today=ASOF)   # backfill: nothing new
    assert out["n_rows_written"] == 0
    assert out["ledger_rows_before"] == out["ledger_rows_after"] == 2


# ───────────────── chunk F (2026-09-26): twelve questions + X reads ─────────

RUN_UTC = f"{ASOF}T12:00:00+00:00"


def _v2_reply(**over):
    body = {k: "not found" for k in TC.ANSWER_KEYS}
    body.update({
        "name": "Triple A",
        "what_changed_30_90d": "2026-09-10 guidance raised (company PR); 2026-07-01 new fab",
        "ceo_promised": "2026-06-15 CEO promised HBM4 volume by 2026-12-31 (call transcript)",
        "bottleneck": "packaging capacity is tight",          # UNDATED answer
        "x_company_posts": ["2026-09-20 | @tripleA | We started shipping HBM4 samples | https://x.com/tripleA/status/1",
                            "last week | @tripleA | undated post"],
        "x_ceo_posts": ["2026-09-18 | @ceoA | Demand exceeds supply through 2027"],
        "x_analyst_posts": ["2026-09-21 | @semi_analyst | Raised price target to 30 on HBM share"],
        "claims": ["2026-09-10 | what_changed_30_90d | Triple A IR | https://investors.triplea.com/pr/1 | Company raised FY guidance to 12bn",
                   "2026-09-12 | bottleneck | reuters.com | https://www.reuters.com/x | Triple A says packaging lead times lengthened",
                   "2026-09-13 | who_loses | somesite | https://blog.example.com/p | Rivals look weak",
                   "no date here | bottleneck | site | https://a | an undated claim"],
        "promises": ["2026-06-15 | 2026-12-31 | OPEN | HBM4 volume shipments by year end | 2026-09-20 samples shipping"],
        "analyst_actions": [], "upcoming_dates": [], "sources": ["https://investors.triplea.com"],
    })
    body.update(over)
    return json.dumps(body)


def test_twelve_keys_parse_flat():
    out = TC.parse_reply(_v2_reply())
    assert out["parse"] == "ok"
    for k in TC.ANSWER_KEYS:
        assert k in out, k
    assert out["what_changed_30_90d"].startswith("2026-09-10")
    for k in TC.X_LIST_KEYS + ("claims", "promises", "undated_claims"):
        assert isinstance(out[k], list), k


def test_undated_claims_are_refused_into_their_bucket_not_dropped():
    out = TC.parse_reply(_v2_reply())
    und = out["undated_claims"]
    assert any(u.startswith("x_company_posts: last week") for u in und)
    assert any(u.startswith("claims: no date here") for u in und)
    # the undated ANSWER stays on the card and is flagged
    assert out["bottleneck"] == "packaging capacity is tight"
    assert any(u.startswith("bottleneck: ") for u in und)
    # "not found" is not a claim, so it is never flagged
    assert not any(u.startswith("who_loses: ") for u in und)
    # the dated items stay; the undated ones are gone from their lists
    assert len(out["x_company_posts"]) == 1 and len(out["claims"]) == 3


def test_quest_prompt_names_x_reads_prior_card_and_open_promises():
    e = TC.engine_side("AAA", asof=ASOF, bars=None, revisions=None, news_rows=[],
                       catalysts=[], predictions=[])
    prior = {"asof": "2026-09-01", "verdict": "neutral", "falsifier": "f",
             "web_bottleneck": "old bottleneck"}
    p = TC.quest_prompt("AAA", e, prior_card=prior, open_promises=[
        {"promised_utc": "2026-06-15", "due_utc": "2026-12-31",
         "promise_text": "HBM4 volume by year end"}])
    for k in TC.X_LIST_KEYS:
        assert f'"{k}"' in p
    assert "x.com" in p and "last 30 days" in p
    assert "old bottleneck" in p and "HBM4 volume by year end" in p
    assert "COPIED EXACTLY" in p


def _v2_card(reply=None, **over):
    e = TC.engine_side("AAA", asof=ASOF, bars=_bars(), revisions=None, news_rows=[],
                       catalysts=[], predictions=[])
    web = TC.parse_reply(reply or _v2_reply())
    syn = {"bull": "b", "bear": "r", "falsifier": "f", "verdict": "supports",
           "confidence": "med", "synth_status": "OK"}
    c = TC.build_card("AAA", kind="personal", asof=ASOF, engine=e, web=web, synth=syn,
                      meta={"run_utc": RUN_UTC, "trigger": "(c) catalyst", "quest_model": "m"})
    c.update(over)
    return c


def test_v2_card_is_valid_and_carries_answers_x_and_trigger():
    c = _v2_card()
    assert TC.validate_card(c) == []
    assert c["schema"] == "thesis_card/v2"
    assert c["web_ceo_promised"].startswith("2026-06-15")
    assert c["trigger"] == "(c) catalyst" and c["run_utc"] == RUN_UTC
    assert c["undated_claims"]


def test_web_events_row_per_dated_claim_with_source_id(tmp_path):
    c = _v2_card()
    ev, cl = tmp_path / "ev.jsonl", tmp_path / "cl.jsonl"
    res = TC.write_evidence(c, events_path=ev, claims_file=cl)
    claims = [json.loads(x) for x in cl.read_text(encoding="utf-8").splitlines()]
    # 3 X posts dated + 3 dated claims = 6, every one in the claims ledger
    assert len(claims) == 6 == res["claims_written"]
    for r in claims:
        assert r["source_id"].startswith("openclaw:")
        assert r["first_seen_utc"] == RUN_UTC
        assert r["claim_utc"] <= ASOF
    ids = {r["source_id"] for r in claims}
    assert {"openclaw:@tripleA".lower(), "openclaw:@ceoa", "openclaw:@semi_analyst",
            "openclaw:investors.triplea.com", "openclaw:reuters.com"} <= ids
    events = [json.loads(x) for x in ev.read_text(encoding="utf-8").splitlines()]
    typed = [r for r in claims if r["web_event_type"]]
    assert len(events) == len(typed) >= 4
    for e in events:
        assert e["retrieved_by"].startswith("openclaw:")
        assert e["observed_at"] == RUN_UTC
    by_type = {e["event_type"] for e in events}
    assert {"guidance_change", "product_launch", "analyst_revision",
            "supplier_constraint"} <= by_type
    # an untyped claim is kept in the claims ledger with the refusal beside it
    untyped = [r for r in claims if r["event_type"] == "claim"]
    assert untyped and all(r["web_event_refused"] for r in untyped)
    # idempotent
    res2 = TC.write_evidence(c, events_path=ev, claims_file=cl)
    assert res2["claims_written"] == 0 and res2["web_events"]["written"] == 0
    assert len(cl.read_text(encoding="utf-8").splitlines()) == 6


def test_a_claim_dated_after_the_run_is_refused(tmp_path):
    c = _v2_card(reply=_v2_reply(claims=[
        "2027-01-01 | bottleneck | reuters.com | https://www.reuters.com/y | future shortage"]))
    res = TC.write_evidence(c, events_path=tmp_path / "e", claims_file=tmp_path / "c")
    assert res["n_future_refused"] == 1


def test_promise_row_written_once_then_graded_and_no_p050_forecast(tmp_path):
    """Adjudication row 14: the promise:v1 forecast rows at p=0.50 are retired --
    the promise row is written, no forecast row is, ever."""
    from backend.services import belief_state as B
    pp, fp = tmp_path / "promises.jsonl", tmp_path / "pred.jsonl"
    c = _v2_card()
    r1 = TC.write_promises(c, today=ASOF, path=pp, forecast_path=fp)
    assert r1["promises_written"] == 1 and r1["forecast_rows_written"] == 0
    rows = [json.loads(x) for x in pp.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["row_type"] == "promise" and rows[0]["status"] == "OPEN"
    assert rows[0]["due_utc"] == "2026-12-31" and rows[0]["promised_utc"] == "2026-06-15"
    assert B.read_predictions(fp) == []
    assert TC.promise_forecast_records(rows[0], today=ASOF) == []
    # idempotent by hash
    r2 = TC.write_promises(c, today=ASOF, path=pp, forecast_path=fp)
    assert r2["promises_written"] == 0 and r2["forecast_rows_written"] == 0
    assert len(pp.read_text(encoding="utf-8").splitlines()) == 1
    assert B.read_predictions(fp) == []
    # the open promise is handed to the next quest
    assert [p["promise_text"] for p in TC.open_promises("AAA", path=pp)] == [
        "HBM4 volume shipments by year end"]
    # the next card addresses it: DELIVERED -> one grade row, once
    later = _v2_card(reply=_v2_reply(promises=[
        "2026-06-15 | 2026-12-31 | DELIVERED | HBM4 volume shipments by year end | 2026-12-10 volume shipments confirmed"]))
    r3 = TC.write_promises(later, today=ASOF, path=pp, forecast_path=fp)
    assert r3["grades_written"] == 1 and r3["promises_written"] == 0
    TC.write_promises(later, today=ASOF, path=pp, forecast_path=fp)
    rows = [json.loads(x) for x in pp.read_text(encoding="utf-8").splitlines()]
    assert [r["row_type"] for r in rows] == ["promise", "grade"]
    assert TC.open_promises("AAA", path=pp) == []
    assert TC.promise_state(rows)[rows[0]["promise_id"]]["status"] == "DELIVERED"


# ── numeric promises: graded by a parser over the 8-K, not by an LLM ─────────
_MU_LIKE_RELEASE = (
    "EX-99.1 2 ex991.htm EX-99.1 Micron Technology, Inc. Reports Results for the Fourth "
    "Quarter of Fiscal 2026 &nbsp; Revenue of $50.37&nbsp;billion versus $44.10 billion for the "
    "prior quarter; GAAP net income of $33.21 billion, or $29.40 per diluted share; Non-GAAP net "
    "income of $35.10 billion, or $31.12 per diluted share; GAAP gross margin of 86.2%. "
    "Business Outlook: Revenue $58.00 billion &plusmn; $1.0 billion; GAAP gross margin 88.0%; "
    "Non-GAAP diluted EPS of $36.00")


def _numeric_setup(tmp_path, body, *, due="2026-09-30", published="2026-09-30T20:05:00+00:00"):
    pp = tmp_path / "promises.jsonl"
    c = _v2_card(reply=_v2_reply(promises=[
        f"2026-06-24 | {due} | OPEN | FQ4 revenue $50.0B +/- $1.0B, GAAP GM ~86%, non-GAAP EPS $31 +/- $1 | 8-K"]))
    c["ticker"] = "MUX"
    TC.write_promises(c, today=ASOF, path=pp, forecast_path=tmp_path / "pred.jsonl")
    pid = json.loads(pp.read_text(encoding="utf-8").splitlines()[0])["promise_id"]
    r = TC.declare_targets(pid, [
        {"metric": "revenue", "op": "within", "value": 50.0, "tolerance": 1.0},
        {"metric": "eps_non_gaap", "op": "within", "value": 31.0, "tolerance": 1.0},
        {"metric": "gross_margin_gaap", "op": "within", "value": 86.0, "tolerance": 0.5}],
        declared_utc="2026-09-26T10:00:00+00:00", path=pp)
    assert r["written"] == 1
    corpus = tmp_path / "ex99"
    corpus.mkdir()
    (corpus / f"{published[:10]}.jsonl").write_text(json.dumps({
        "source": "sec_edgar_8k_ex99_body", "published_utc": published,
        "first_seen_utc": published, "url": "https://www.sec.gov/Archives/x/ex991.htm",
        "title": "8-K - MICRON-LIKE (0000000042) EX-99.1", "body": body, "tickers": [],
        "entity_tags": ["8-K:2.02", "cik:0000000042", "exhibit:EX-99.1"]}) + "\n", encoding="utf-8")
    return pp, pid, corpus


def test_release_parser_reads_results_not_the_outlook():
    n = TC.parse_release_numbers(_MU_LIKE_RELEASE)
    assert n["revenue"]["value"] == pytest.approx(50.37)
    assert n["eps_non_gaap"]["value"] == pytest.approx(31.12)
    assert n["eps_gaap"]["value"] == pytest.approx(29.40)
    assert n["gross_margin_gaap"]["value"] == pytest.approx(86.2)      # not the outlook's 88.0
    m = TC.parse_release_numbers("Revenue was $950 million. Non-GAAP EPS of $0.41.")
    assert m["revenue"]["value"] == pytest.approx(0.95) and m["eps_non_gaap"]["value"] == pytest.approx(0.41)


def test_release_parser_reads_the_micron_side_by_side_table():
    """The real FQ3-26 layout (EDGAR a2026q3ex991, 2026-06-24): GAAP and
    non-GAAP columns side by side, margins only in the table, outlook after."""
    t = ("Fiscal Q3 2026 highlights &#8226; Revenue of $41.46 billion versus $23.86 billion "
         "&#8226; GAAP net income of $28.24 billion, or $24.67 per diluted share &#8226; Non-GAAP "
         "net income of $28.86 billion, or $25.11 per diluted share. Quarterly Financial Results "
         "GAAP (1) Non-GAAP (2) FQ3-26 FQ2-26 FQ3-25 FQ3-26 FQ2-26 FQ3-25 Revenue $ 41,456 $ 23,860 "
         "$ 9,301 $ 41,456 $ 23,860 $ 9,301 Gross margin 35,056 17,755 3,508 35,199 17,876 3,623 "
         "Percent of revenue 84.6 % 74.4 % 37.7 % 84.9 % 74.9 % 39.0 % Operating expenses 1,738 "
         "Business Outlook FQ4-26 Revenue $50.0 billion Gross margin Approximately 86% "
         "Diluted earnings per share $30.73 $31.00")
    n = TC.parse_release_numbers(t)
    assert n["revenue"]["value"] == pytest.approx(41.46)
    assert n["eps_gaap"]["value"] == pytest.approx(24.67)
    assert n["eps_non_gaap"]["value"] == pytest.approx(25.11)
    assert n["gross_margin_gaap"]["value"] == pytest.approx(84.6)
    assert n["gross_margin_non_gaap"]["value"] == pytest.approx(84.9)


def test_numeric_promise_graded_delivered_from_a_synthetic_8k(tmp_path):
    pp, pid, corpus = _numeric_setup(tmp_path, _MU_LIKE_RELEASE)
    # not due yet: nothing is graded
    r0 = TC.grade_numeric_promises(path=pp, corpus_dir=corpus, cik_map={"MUX": 42}, today="2026-09-20")
    assert r0["n_not_due"] == 1 and r0["grades_written"] == 0
    r = TC.grade_numeric_promises(path=pp, corpus_dir=corpus, cik_map={"MUX": 42}, today="2026-10-01")
    assert r["grades_written"] == 1
    st = TC.promise_state(TC._read_jsonl(pp))[pid]
    assert st["status"] == "DELIVERED" and st["grader"] == TC.PROMISE_GRADER
    assert st["parsed"] == {"revenue": pytest.approx(50.37), "eps_non_gaap": pytest.approx(31.12),
                            "gross_margin_gaap": pytest.approx(86.2)}
    # idempotent
    assert TC.grade_numeric_promises(path=pp, corpus_dir=corpus, cik_map={"MUX": 42},
                                     today="2026-10-01")["grades_written"] == 0


def test_numeric_promise_missed_and_ungradeable(tmp_path):
    missed = _MU_LIKE_RELEASE.replace("86.2%", "84.9%")
    pp, pid, corpus = _numeric_setup(tmp_path, missed)
    TC.grade_numeric_promises(path=pp, corpus_dir=corpus, cik_map={"MUX": 42}, today="2026-10-01")
    st = TC.promise_state(TC._read_jsonl(pp))[pid]
    assert st["status"] == "MISSED" and st["parsed"]["gross_margin_gaap"] == pytest.approx(84.9)
    (tmp_path / "b").mkdir()
    pp2, pid2, corpus2 = _numeric_setup(tmp_path / "b", "Micron reports results. Revenue of $50.1 billion.")
    TC.grade_numeric_promises(path=pp2, corpus_dir=corpus2, cik_map={"MUX": 42}, today="2026-10-01")
    st2 = TC.promise_state(TC._read_jsonl(pp2))[pid2]
    assert st2["status"] == "UNGRADEABLE" and st2["parsed"]["revenue"] == pytest.approx(50.1)
    assert st2["parsed"]["eps_non_gaap"] is None
    # a fetch of the full exhibit fills the missing metrics and re-grades
    r2 = TC.grade_numeric_promises(path=pp2, corpus_dir=corpus2, cik_map={"MUX": 42},
                                   today="2026-10-01", fetch=lambda url: _MU_LIKE_RELEASE)
    assert r2["grades_written"] == 1
    assert TC.promise_state(TC._read_jsonl(pp2))[pid2]["status"] == "DELIVERED"


def test_a_card_cannot_grade_a_numbered_promise_and_late_targets_are_refused(tmp_path):
    pp, pid, _ = _numeric_setup(tmp_path, _MU_LIKE_RELEASE)
    assert TC.declare_targets(pid, [{"metric": "revenue", "value": 1}], path=pp)["written"] == 0
    txt = json.loads(pp.read_text(encoding="utf-8").splitlines()[0])["promise_text"]
    later = _v2_card(reply=_v2_reply(promises=[f"2026-06-24 | 2026-09-30 | DELIVERED | {txt} | card says so"]))
    later["ticker"] = "MUX"
    r = TC.write_promises(later, today=ASOF, path=pp, forecast_path=tmp_path / "p.jsonl")
    assert r["card_grade_refused_numeric"] == 1 and r["grades_written"] == 0
    TC.write_promises(_v2_card(), today=ASOF, path=pp, forecast_path=tmp_path / "p2.jsonl")
    other = [r for r in TC._read_jsonl(pp) if r.get("ticker") == "AAA"][0]["promise_id"]
    late = TC.declare_targets(other, [{"metric": "revenue", "value": 1}],
                              declared_utc="2027-01-02T00:00:00+00:00", path=pp)
    assert late["written"] == 0 and "after the print" in late["refused"]


def _closes(n=90, sd=0.01, last_ret=0.0, seed=3):
    rng = np.random.default_rng(seed)
    r = rng.normal(0, sd, n - 1)
    r[-1] = last_ret
    px = 100 * np.exp(np.concatenate([[0.0], np.cumsum(r)]))
    ds = [d.strftime("%Y-%m-%d") for d in pd.bdate_range(end=ASOF, periods=n)]
    return px, ds


def test_trigger_fires_on_a_big_move_without_a_typed_event_and_not_otherwise():
    px, ds = _closes(last_ret=0.08)
    r = TC.trig_sigma_move(px, ds, ASOF)
    assert r and r.startswith("(d)")
    assert TC.trig_sigma_move(px, ds, ASOF, typed_event_dates={ds[-1]}) is None
    px2, ds2 = _closes(last_ret=0.004)
    assert TC.trig_sigma_move(px2, ds2, ASOF) is None
    # a move long before asof is not news
    later = (date.fromisoformat(ASOF) + timedelta(days=20)).isoformat()
    assert TC.trig_sigma_move(px, ds, later) is None


def test_trigger_fires_on_a_synthetic_revision_cluster_and_not_otherwise():
    from backend.services import revision_flow as RF
    a = pd.Timestamp(ASOF)
    rows = []
    for i, f in enumerate(("F1", "F2", "F3")):        # AAA: 3 firms in 10 days
        rows.append(("AAA", a - pd.Timedelta(days=2 + i), f))
    rows += [("BBB", a - pd.Timedelta(days=2), "F1"),  # BBB: 2 firms recent,
             ("BBB", a - pd.Timedelta(days=3), "F2"),
             ("BBB", a - pd.Timedelta(days=40), "F3")]  # the 3rd outside 10 days
    rev = pd.DataFrame([{"ticker": t, "event_date": d, "firm": f, "target_action": "Raises",
                         "prior_target": 10.0, "current_target": 11.0, "pit_safe": True}
                        for t, d, f in rows])
    flow = RF.compute(rev, asof=a + pd.Timedelta(days=1), window_days=10)
    trig = TC.compute_triggers(["AAA", "BBB"], asof=ASOF, last_cards={"AAA": ASOF, "BBB": ASOF},
                               n_firms_recent=flow["n_firms"].to_dict())
    assert [t["ticker"] for t in trig] == ["AAA"]
    assert trig[0]["reasons"][0].startswith("(b) revision cluster: 3 firms")


def test_other_triggers_catalyst_entry_and_staleness():
    a = date.fromisoformat(ASOF)
    near = f"{a + timedelta(days=4)} | earnings | Q4"
    far = f"{a + timedelta(days=30)} | earnings | Q1"
    assert TC.trig_catalyst(ASOF, [near]).startswith("(c)")
    assert TC.trig_catalyst(ASOF, [far]) is None
    assert TC.trig_entered(f"{ASOF}T01:00:00+00:00", None, "book:x").startswith("(a)")
    assert TC.trig_entered("2026-09-01T00:00:00+00:00", "2026-09-10") is None
    assert TC.trig_entered("2026-09-20T00:00:00+00:00", "2026-09-10") is not None
    assert TC.trig_stale("2026-08-01", ASOF).startswith("(e)")
    assert TC.trig_stale("2026-09-20", ASOF) is None
    trig = TC.compute_triggers(["QUIET"], asof=ASOF, last_cards={"QUIET": "2026-09-20"})
    assert trig == []


def test_digest_has_what_changed_since_the_last_card(tmp_path):
    prev = _v2_card(asof="2026-09-01")
    prev["card_hash"] = TC.card_hash(prev)
    TC.write_card(prev, root=tmp_path)
    cur = _v2_card(reply=_v2_reply(bottleneck="2026-09-20 substrate shortage now"))
    TC.write_card(cur, root=tmp_path)
    d = TC.diff_cards(TC.previous_card("AAA", ASOF, root=tmp_path), cur)
    assert d["changed"] == ["bottleneck"] and d["prev_asof"] == "2026-09-01"
    md = TC.write_digest(ASOF, root=tmp_path).read_text(encoding="utf-8")
    assert "## What changed since the last card" in md
    assert "AAA** vs 2026-09-01" in md and "bottleneck: 2026-09-20 substrate" in md
    # a v1 previous card is reported as a schema change, not twelve new answers
    v1 = {"asof": "2026-08-01", "verdict": "neutral", "web_what_changed": "x"}
    assert TC.diff_cards(v1, cur)["schema_change"].startswith("thesis_card/v1")


def test_run_writes_evidence_and_promises_beside_a_tmp_root(tmp_path):
    from scripts import thesis_cards as S

    def quest(ticker, prompt, *, model, timeout, log_dir):
        assert "x_ceo_posts" in prompt
        return {"status": "OK", "reply": _v2_reply(), "elapsed_s": 1.0,
                "log_path": str(log_dir / "q.log"), "cost_usd": 0.0}

    def synth(engine, web, *, model):
        return {"bull": "b", "bear": "r", "falsifier": "f", "verdict": "neutral",
                "confidence": "low", "synth_status": "OK"}

    res = S.run(universe=[{"ticker": "AAA", "kind": "personal", "source": "trigger",
                           "trigger": "(c) catalyst within 5 sessions"}],
                asof=ASOF, root=tmp_path, max_quests=1, cap_usd=1.0, parallel=1,
                model="m", inputs=_fake_inputs(), quest_fn=quest, synth_fn=synth,
                spend_fn=lambda day: 0.0)
    assert res["state"] == "DONE"
    card = TC.read_cards(ASOF, root=tmp_path)[0]
    assert card["trigger"] == "(c) catalyst within 5 sessions"
    assert res["evidence"]["AAA"]["claims_written"] == 6
    assert res["promises"]["AAA"]["promises_written"] == 1
    for f in ("_claims.jsonl", "_web_events.jsonl", "_promises.jsonl", "_predictions.jsonl"):
        assert (tmp_path / f).exists(), f
    preds = [json.loads(x) for x in (tmp_path / "_predictions.jsonl").read_text(
        encoding="utf-8").splitlines()]
    assert {p["specialist"] for p in preds} == {"thesis_card:v1"}      # no p=0.50 promise rows


def test_a_dividend_date_is_not_a_catalyst():
    a = date.fromisoformat(ASOF)
    assert TC.trig_catalyst(ASOF, [f"{a + timedelta(days=2)} | dividend | Q3"]) is None
    assert TC.trig_catalyst(ASOF, [f"{a + timedelta(days=2)} | webcast_replay_expiry | x"]) is None
    assert TC.trig_catalyst(ASOF, [f"{a + timedelta(days=2)} | earnings | Q3"]).startswith("(c)")


# ── post-review fixes 2026-09-26 (adjudication rows 9) ──────────────────────
def _books_file(tmp_path):
    rows = [
        {"name": "personal_x", "kind": "personal", "model": "deepseek-flash",
         "frozen_utc": "2026-09-20T00:00:00+00:00", "positions": [{"ticker": "PPP"}]},
        {"name": "comp_x", "kind": "competition", "model": "deepseek-flash",
         "frozen_utc": "2026-09-20T00:00:00+00:00", "positions": [{"ticker": "CCC"}]},
        {"name": "lib_mom_12_1_q_2026-09-26", "kind": "personal",
         "model": "rule:strategy_library:mom_12_1_q",
         "frozen_utc": "2026-09-26T00:00:00+00:00", "positions": [{"ticker": "LLL"}]},
        {"name": "lib_other", "kind": "personal", "model": "rule:strategy_library:x",
         "frozen_utc": "2026-09-26T00:00:00+00:00", "positions": [{"ticker": "PPP"}]},
    ]
    p = tmp_path / "books.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def test_trigger_a_reads_personal_and_competition_books_not_the_library(tmp_path):
    from scripts import thesis_cards as S
    p = _books_file(tmp_path)
    m = S.book_members(p)
    assert set(m) == {"PPP", "CCC"}
    assert m["PPP"][1] == "book:personal_x"          # a library book never sets entry
    m = S.book_members(p, include_library=True)
    assert set(m) == {"PPP", "CCC", "LLL"}


def test_the_cli_opts_the_library_in(monkeypatch):
    from scripts import thesis_cards as S
    seen = {}

    def fake_trigger_list(day, **kw):
        seen.update(kw)
        return {"triggered": []}
    monkeypatch.setattr(S, "trigger_list", fake_trigger_list)
    assert S.main(["run", "--trigger", "--dry-run", "--date", ASOF]) == 0
    assert seen.get("include_library") is False
    assert S.main(["run", "--trigger", "--dry-run", "--include-library", "--date", ASOF]) == 0
    assert seen.get("include_library") is True


def test_untyped_claims_backfill_into_web_events_as_generic_claims(tmp_path):
    from scripts import thesis_cards as S
    cf = tmp_path / "claims.jsonl"
    ev = tmp_path / "events.jsonl"
    base = {"schema": "claim/v1", "ticker": "MU", "card_asof": ASOF,
            "first_seen_utc": f"{ASOF}T03:00:00+00:00", "claim_utc": "2026-09-24"}
    rows = [
        {**base, "claim_id": "c1", "event_type": "claim", "source_id": "openclaw:trendforce.com",
         "source_url": "https://www.trendforce.com/price/dram", "text": "DDR5 spot +4%",
         "web_event_refused": "no web_events type fits event_type 'claim'"},
        {**base, "claim_id": "c2", "event_type": "earnings_report", "source_id": "openclaw:sec.gov",
         "source_url": "https://www.sec.gov/Archives/x", "text": "FQ4 revenue $9.3B",
         "web_event_refused": "web_events source_type 'sec' may not carry 'earnings_release'"},
        {**base, "claim_id": "c3", "event_type": "claim", "source_id": "openclaw:@microntech",
         "source_url": "https://x.com/MicronTech/status/1", "text": "HBM4 sampling",
         "web_event_refused": "no web_events type fits event_type 'claim'"},
        {**base, "claim_id": "c4", "event_type": "analyst_target_change", "source_id": "openclaw:x",
         "source_url": "https://www.reuters.com/x", "text": "PT raised",
         "web_event_refused": None},                          # already typed: not touched
        {**base, "claim_id": "c5", "card_asof": "2026-09-01",
         "first_seen_utc": "2026-09-01T00:00:00+00:00", "event_type": "claim",
         "source_id": "openclaw:y", "source_url": "https://y.com/x", "text": "old",
         "claim_utc": "2026-08-30", "web_event_refused": "no type"},   # another day
    ]
    cf.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    res = S.backfill_claim_events(ASOF, claims_file=cf, events_path=ev)
    assert res["n_candidates"] == 3 and res["web_events"]["written"] == 3
    got = [json.loads(x) for x in ev.read_text(encoding="utf-8").splitlines()]
    assert {e["event_type"] for e in got} == {"claim"}
    assert {e["source_id"] for e in got} == {"openclaw:trendforce.com", "openclaw:sec.gov",
                                            "openclaw:@microntech"}
    st = {e["source_id"]: e["source_type"] for e in got}
    assert st["openclaw:sec.gov"] == "sec" and st["openclaw:@microntech"] == "x"
    assert all(e["evidence_date"] == "2026-09-24" for e in got)
    again = S.backfill_claim_events(ASOF, claims_file=cf, events_path=ev)
    assert again["web_events"]["written"] == 0                     # idempotent
