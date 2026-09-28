"""LANE A alerts: frozen before sent, dedup, caps, quiet hours, levels, kill rule.

Synthetic events and bars, a fake clock, tmp_path and a fake sender. No network,
no LLM, no Telegram.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from backend import config as _cfg
from backend.services import alerts as AL
from backend.services import alerts_sources as S
from backend.tests.alerts_isolation import guard_real_data  # noqa: F401  (autouse, F5)

UTC = timezone.utc


def T(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def ev(ticker="AAA", url="https://www.sec.gov/Archives/x/1.htm",
       observed="2026-09-28T02:00:00+00:00", etype="contract_loss_or_termination",
       fact_key="8k_item:1.02", prior=-1, kind="sec_8k", lane="truth") -> dict:
    """Real-shaped (review F1): the long SEC boilerplate the collector writes,
    with the item AFTER ~90 characters, exactly as on the 2026-09-28 dry run --
    the old 60-character fixture could not catch a render that cut the item."""
    company = f"{ticker} Holdings International Corporation"
    return {"ticker": ticker, "company": company, "source_kind": kind, "lane": lane,
            "event_type_id": etype, "event_type_candidates": [etype], "direction_prior": prior,
            "fact": (f"{company} ({ticker}) filed a Form 8-K with the SEC, accepted "
                     f"{observed[:10]} {observed[11:16]} UTC, reporting Item 1.02 (Termination "
                     f"of a Material Definitive Agreement); also Item(s) 9.01."),
            "fact_line": (f"{ticker} ended a material agreement (8-K Item 1.02; also Item(s) "
                          f"9.01). {company}."),
            "headline": "8-K Item 1.02: Termination of a Material Definitive Agreement",
            "primary_item": "1.02", "typing_rule_version": S.TYPING_RULE_VERSION,
            "fact_key": fact_key, "source_url": url, "source_url_kind": "SEC filing index",
            "observed_utc": observed, "published_utc": observed, "amendment": False}


def bars_for(symbols=("SPY", "AAA", "BBB", "CCC", "DDD", "EEE", "FFF"),
             end="2026-09-25", n=300, seed=7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=end, periods=n)
    rows = []
    for i, s in enumerate(symbols):
        r = rng.normal(0.0003, 0.015 + 0.002 * i, n)
        c = 50.0 * (1 + i) * np.exp(np.cumsum(r))
        o = c * (1 + rng.normal(0, 0.002, n))
        rows.append(pd.DataFrame({"symbol": s, "date": dates, "open": o, "close": c,
                                  "volume": rng.integers(1e5, 1e6, n)}))
    return pd.concat(rows, ignore_index=True)


UNI = {"tickers": ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"], "n": 6, "n_funnel": 3,
       "n_book_tickers": 3, "n_books": 1, "funnel_generated_at": "2026-09-24T02:48:34+00:00",
       "funnel_age_days": 4.0, "funnel_stale_limit_days": 10, "books_newest_frozen_utc": None}


@pytest.fixture
def held(monkeypatch):
    monkeypatch.setattr(_cfg, "ALERTS_SEND_ENABLED", False)


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(_cfg, "ALERTS_SEND_ENABLED", True)


def run(tmp_path, events, now, *, sender=None, dry=False, bars=None):
    return AL.run_pass(now=now, dry_run=dry, root=tmp_path, events=events, universe=UNI,
                       bars=bars if bars is not None else bars_for(), sender=sender,
                       write_receipt=True)


# ───────────────────────── frozen before sent ──────────────────────────────

def test_frozen_row_exists_before_the_sender_is_called_and_survives_its_failure(tmp_path, live):
    seen_at_call = []

    def sender(text):
        seen_at_call.append([r["kind"] for r in AL.read_ledger(tmp_path)])
        raise ConnectionError("telegram down")

    now = T("2026-09-28T06:00:00")
    run(tmp_path, [ev()], now, sender=sender)
    assert seen_at_call == [["FROZEN"]]                 # frozen BEFORE the send
    rows = AL.read_ledger(tmp_path)
    assert [r["kind"] for r in rows] == ["FROZEN", "SEND_RESULT"]
    frozen, res = rows
    assert frozen["send_status"] == "PENDING" and frozen["contradicts"]
    assert res["status"] == "SEND_FAILED" and res["refers_to"] == [frozen["id"]]
    assert "ConnectionError" in res["error"]
    # the next pass retries; the frozen row is never rewritten
    run(tmp_path, [ev()], now + timedelta(minutes=30), sender=lambda t: None)
    rows2 = AL.read_ledger(tmp_path)
    assert rows2[0] == frozen
    assert rows2[-1]["status"] == "SENT"


def test_a_failed_send_gives_up_after_the_attempt_limit(tmp_path, live):
    def boom(t):
        raise OSError("x")
    now = T("2026-09-28T06:00:00")
    for k in range(_cfg.ALERT_MAX_SEND_ATTEMPTS + 1):
        run(tmp_path, [ev()], now + timedelta(minutes=30 * k), sender=boom)
    st = [r["status"] for r in AL.read_ledger(tmp_path) if r["kind"] == "SEND_RESULT"]
    assert st == ["SEND_FAILED"] * _cfg.ALERT_MAX_SEND_ATTEMPTS + ["GAVE_UP"]


def test_with_the_flag_off_the_sender_is_never_called(tmp_path, held):
    calls = []
    r = run(tmp_path, [ev(), ev("BBB", url="u2")], T("2026-09-28T06:00:00"),
            sender=lambda t: calls.append(t))
    assert calls == []
    assert r["mode"] == "HELD_NOT_ENABLED"
    st = [x["status"] for x in AL.read_ledger(tmp_path) if x["kind"] == "SEND_RESULT"]
    assert st == ["HELD_NOT_ENABLED", "HELD_NOT_ENABLED"]
    assert r["llm_calls"] == 0 and r["llm_spend_usd"] == 0.0


def test_dry_run_never_calls_the_sender_even_when_enabled(tmp_path, live):
    calls = []
    r = run(tmp_path, [ev()], T("2026-09-28T06:00:00"), sender=calls.append, dry=True)
    assert calls == [] and r["delivery"]["statuses"] == {"DRY_RUN": 1}
    assert len(r["messages"]) == 1


def test_the_send_flag_is_a_declared_bool_and_resolves_the_mode(monkeypatch):
    assert isinstance(_cfg.ALERTS_SEND_ENABLED, bool)
    monkeypatch.setattr(_cfg, "ALERTS_SEND_ENABLED", False)
    assert AL.resolve_mode(False) == AL.MODE_HELD and AL.resolve_mode(True) == AL.MODE_DRY
    monkeypatch.setattr(_cfg, "ALERTS_SEND_ENABLED", True)
    assert AL.resolve_mode(False) == AL.MODE_LIVE and AL.resolve_mode(True) == AL.MODE_DRY


# ─────────────────────────────── dedup ─────────────────────────────────────

def test_five_rewrites_of_one_fact_make_one_alert_and_the_first_publication_wins(tmp_path, held):
    base = T("2026-09-28T01:00:00")
    evs = [ev(url=f"https://x/{i}", observed=(base + timedelta(hours=5 * i)).isoformat())
           for i in range(5)]
    run(tmp_path, list(reversed(evs)), T("2026-09-28T06:00:00") + timedelta(hours=20))
    rows = AL.read_ledger(tmp_path)
    fz = AL.frozen_alerts(rows)
    fu = [r for r in rows if r["kind"] == "FOLLOWUP"]
    assert len(fz) == 1 and fz[0]["source_url"] == "https://x/0"   # earliest wins
    assert [r["cluster_count"] for r in fu] == [2, 3, 4, 5]
    assert all(r["refers_to"] == fz[0]["id"] and r["cluster_id"] == fz[0]["cluster_id"]
               for r in fu)
    assert all(r["send_status"] == "NOT_SENT_FOLLOWUP" for r in fu)


def test_the_same_publication_read_again_writes_nothing(tmp_path, held):
    now = T("2026-09-28T06:00:00")
    run(tmp_path, [ev()], now)
    n = len(AL.read_ledger(tmp_path))
    run(tmp_path, [ev()], now + timedelta(minutes=30))
    assert len(AL.read_ledger(tmp_path)) == n


def test_a_retyped_publication_is_not_a_second_alert(tmp_path, held):
    now = T("2026-09-28T06:00:00")
    run(tmp_path, [ev()], now)
    n = len(AL.read_ledger(tmp_path))
    run(tmp_path, [ev(etype="sec_8k_item_1.02", fact_key="8k_item:7.01")], now)
    assert len(AL.read_ledger(tmp_path)) == n


def test_outside_the_window_or_another_fact_is_a_new_alert(tmp_path, held):
    a = ev(url="u1", observed="2026-09-20T01:00:00+00:00")
    b = ev(url="u2", observed="2026-09-24T02:00:00+00:00")          # > 72 h after a
    c = ev(url="u3", observed="2026-09-20T02:00:00+00:00", fact_key="8k_item:2.03",
           etype="debt_issuance_or_obligation", prior=None)
    run(tmp_path, [a, b, c], T("2026-09-24T06:00:00"))
    assert len(AL.frozen_alerts(AL.read_ledger(tmp_path))) == 3


# ──────────────────────────────── caps ─────────────────────────────────────

def test_daily_cap(tmp_path, held, monkeypatch):
    monkeypatch.setattr(_cfg, "ALERT_DAILY_CAP", 8)
    tick = [f"T{i}" for i in range(10)]
    evs = [ev(t, url=f"u{t}") for t in tick]
    r = run(tmp_path, evs, T("2026-09-28T06:00:00"))
    assert r["delivery"]["statuses"] == {"HELD_NOT_ENABLED": 8, "CAPPED_DAILY": 2}
    # a later pass the same HK day delivers nothing more
    r2 = run(tmp_path, [ev("ZZ", url="uz")], T("2026-09-28T08:00:00"))
    assert r2["delivery"]["statuses"] == {"CAPPED_DAILY": 1}


def test_per_ticker_cap(tmp_path, held):
    evs = [ev("AAA", url=f"u{i}", fact_key=f"8k_item:{i}.01", etype=f"type{i}") for i in range(3)]
    r = run(tmp_path, evs, T("2026-09-28T06:00:00"))
    assert r["delivery"]["statuses"] == {"HELD_NOT_ENABLED": 2, "CAPPED_TICKER": 1}


def test_the_cap_day_is_the_owners_day_not_utcs(tmp_path, held, monkeypatch):
    monkeypatch.setattr(_cfg, "ALERT_DAILY_CAP", 1)
    # 15:00Z on 09-27 is 23:00 HKT on 09-27; 00:00Z on 09-28 is 08:00 HKT on 09-28
    run(tmp_path, [ev("AAA", url="a", observed="2026-09-27T14:00:00+00:00")],
        T("2026-09-27T15:00:00"))
    r = run(tmp_path, [ev("BBB", url="b", observed="2026-09-27T23:00:00+00:00")],
            T("2026-09-28T00:00:00"))
    assert r["delivery"]["statuses"] == {"HELD_NOT_ENABLED": 1}


# ───────────────────────────── quiet hours ─────────────────────────────────

def test_quiet_hours_are_computed_in_hong_kong_across_the_utc_date_boundary():
    assert AL.in_quiet_hours(T("2026-09-27T16:30:00"))            # 00:30 HKT 09-28
    assert AL.in_quiet_hours(T("2026-09-27T23:29:00"))            # 07:29 HKT
    assert not AL.in_quiet_hours(T("2026-09-27T16:29:00"))        # 00:29 HKT
    assert not AL.in_quiet_hours(T("2026-09-27T23:30:00"))        # 07:30 HKT
    assert AL.owner_day(T("2026-09-27T17:00:00")) == "2026-09-28"


def test_alerts_frozen_in_quiet_hours_are_held_then_delivered_as_one_digest(tmp_path, live):
    sent = []
    r1 = run(tmp_path, [ev("AAA", url="a", observed="2026-09-27T17:00:00+00:00"),
                        ev("BBB", url="b", observed="2026-09-27T18:00:00+00:00")],
             T("2026-09-27T18:05:00"), sender=sent.append)
    assert r1["delivery"]["plan_action"] == "HELD_QUIET_HOURS" and sent == []
    assert len(AL.frozen_alerts(AL.read_ledger(tmp_path))) == 2     # frozen while held
    r2 = run(tmp_path, [], T("2026-09-27T23:31:00"), sender=sent.append)
    assert len(sent) == 1 and sent[0].startswith("AEGIS alerts held over quiet hours")
    assert r2["delivery"]["statuses"] == {"SENT": 1}
    res = [x for x in AL.read_ledger(tmp_path) if x["kind"] == "SEND_RESULT"]
    assert res[0]["digest"] is True and len(res[0]["refers_to"]) == 2


# ─────────────────────────────── levels ────────────────────────────────────

@pytest.mark.parametrize("level", ["THESIS_CHANGE", "SIGNAL_CANDIDATE", "PAPER_ACTION"])
def test_higher_levels_are_refused_by_name(level):
    with pytest.raises(AL.AlertLevelRefused, match=r"needs >= 100 graded alert dates; have 7"):
        AL.require_level(level, 7)
    assert AL.require_level("INFO", 0) == "INFO"
    assert set(AL.LEVELS) == {"INFO", "THESIS_CHANGE", "SIGNAL_CANDIDATE", "PAPER_ACTION"}


def test_discovery_and_social_sources_never_originate(tmp_path, held):
    with pytest.raises(AL.AlertRefused, match="never originate"):
        AL.assert_can_originate(ev(kind="google_news_rss_en_us", lane="discovery"))
    with pytest.raises(AL.AlertRefused, match="social lane"):
        AL.assert_can_originate(ev(kind="stocktwits", lane="social"))
    r = run(tmp_path, [ev(kind="reddit", lane="social")], T("2026-09-28T06:00:00"))
    assert AL.read_ledger(tmp_path) == [] and r["freeze"]["refused"]


# ─────────────────────── grading: next-session entry ───────────────────────

def test_entry_is_the_first_session_that_opens_after_created_utc():
    from backend.services import source_scorecard as SS
    panel = SS.PricePanel(bars_for())
    rows = [{"kind": "FROZEN", "id": "A1", "level": "INFO", "source_kind": "sec_8k",
             "ticker": "AAA", "direction_prior": -1, "created_utc": ts}
            for ts in ("2026-09-23T12:00:00+00:00",      # 08:00 ET Wed: that session
                       "2026-09-23T14:00:00+00:00",      # 10:00 ET Wed: after the open
                       "2026-09-26T03:00:00+00:00")]     # Saturday: Monday (beyond bars)
    got = [panel.entry_index(u["ts"]) for u in AL.alert_units(rows)]
    cal = [str(d.date()) for d in panel.calendar]
    assert cal[got[0]] == "2026-09-23"
    assert cal[got[1]] == "2026-09-24"
    assert got[2] == len(cal)                             # OPEN: not in the bars yet
    assert AL.alert_units(rows)[0]["direction"] == "down"


def test_grade_alerts_counts_graded_dates_and_prints_the_distance(tmp_path, held):
    now = T("2026-09-10T06:00:00")
    run(tmp_path, [ev(url="a", observed="2026-09-10T01:00:00+00:00"),
                   ev("BBB", url="b", observed="2026-09-10T01:00:00+00:00")], now)
    g = AL.grade_alerts(AL.read_ledger(tmp_path), bars_for())
    assert g["state"] == "GRADED"
    assert g["n_alert_dates_graded"] == 1 and g["distance_to_min"] == 99


# ─────────────────────────────── kill rule ─────────────────────────────────

def test_kill_rule_switches_to_one_daily_digest_and_says_so(tmp_path, live):
    assert AL.kill_rule({"n_alert_dates_graded": 99, "kill_cell": {"verdict": "TOO_FEW"}})["mode"] == "LIVE"
    alive = AL.kill_rule({"n_alert_dates_graded": 100, "kill_horizon": 5,
                          "kill_cell": {"verdict": "ALPHA_DETECTED", "t_ctrl": 2.4}})
    assert alive["mode"] == "LIVE"
    k = AL.kill_rule({"n_alert_dates_graded": 100, "kill_horizon": 5,
                      "kill_cell": {"verdict": "CANNOT_DISTINGUISH", "t_ctrl": 0.3}})
    assert k["mode"] == "DIGEST_ONLY" and "switched to one daily digest" in k["why"]
    now = T("2026-09-28T02:00:00")
    AL.freeze_events([ev()], [], now=now, prices={}, n_graded_dates=100, root=tmp_path)
    sent = []
    AL.deliver(AL.read_ledger(tmp_path), now=now, mode=AL.MODE_LIVE, kill=k,
               sender=sent.append, root=tmp_path)
    assert len(sent) == 1 and sent[0].startswith("Alert stream switched to one daily digest")
    rows = AL.read_ledger(tmp_path)
    AL.freeze_events([ev("BBB", url="b")], rows, now=now + timedelta(hours=1), prices={},
                     n_graded_dates=100, root=tmp_path)
    d2 = AL.deliver(AL.read_ledger(tmp_path), now=now + timedelta(hours=1), mode=AL.MODE_LIVE,
                    kill=k, sender=sent.append, root=tmp_path)
    assert d2["plan_action"] == "HELD_DIGEST_ALREADY_TODAY" and len(sent) == 1


# ─────────────────────────── price and message ─────────────────────────────

def test_a_missing_price_is_unpriced_by_name_never_blank(tmp_path, held):
    assert AL.MODE_HELD
    p = S.price_context("QQQQ", T("2026-09-28T06:00:00"), None)
    assert p["price_state"] == "UNPRICED: no bars for QQQQ"
    stale = S.price_context("AAA", T("2026-09-28T06:00:00"),
                            S.closes_by_symbol(bars_for(end="2026-08-28"))["AAA"])
    assert stale["price_state"].startswith("UNPRICED: last AAA bar is 2026-08-28")
    r = run(tmp_path, [ev("ZZZ", url="z")], T("2026-09-28T06:00:00"), dry=True)
    fz = AL.frozen_alerts(AL.read_ledger(tmp_path))[0]
    assert fz["price_state"] == "UNPRICED: no bars for ZZZ" and fz["last_price"] is None
    assert "Price: UNPRICED: no bars for ZZZ" in r["messages"][0]


def test_priced_alert_reports_sigma_moves_and_the_message_carries_no_advice(tmp_path, held):
    r = run(tmp_path, [ev()], T("2026-09-28T06:00:00"), dry=True)
    fz = AL.frozen_alerts(AL.read_ledger(tmp_path))[0]
    assert fz["price_state"] == "PRICED" and fz["last_price_ts"].startswith("2026-09-25T20:00")
    assert isinstance(fz["move_1s_sigma"], float) and isinstance(fz["move_5s_sigma"], float)
    msg = r["messages"][0]
    import re
    assert not re.search(r"\b(buy|sell|buying|selling)\b", msg, re.I)
    assert msg.rstrip().endswith(f"(reply: analyze {fz['id']})")
    assert len(msg.splitlines()) <= AL.MAX_MESSAGE_LINES
    assert f"analyze {fz['id']}" in msg and fz["source_url"] in msg
    for k in ("id", "created_utc", "ticker", "event_type_id", "source_url", "lane", "fact",
              "last_price", "last_price_ts", "move_1s_sigma", "move_5s_sigma", "contradicts",
              "not_known", "cluster_id", "level", "send_status"):
        assert fz.get(k) not in (None, ""), k


def test_contradiction_is_named_or_says_none_found():
    e = ev(prior=-1)
    assert AL.contradictions(e, {"price_state": "PRICED", "move_5s_sigma": 1.5}, []).startswith(
        "the price moved +1.5 sigma")
    assert AL.contradictions(e, {"price_state": "PRICED", "move_5s_sigma": 0.2}, []).startswith(
        "none found (checked:")
    opp = ev(url="o", prior=1, etype="new_contract_or_partnership")
    assert "opposite-prior SEC event" in AL.contradictions(e, {"price_state": "UNPRICED: x"}, [opp])


def test_stop_file_stops_the_pass_and_writes_no_alert(tmp_path, held):
    AL.stop_file(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    AL.stop_file(tmp_path).write_text("stop", encoding="utf-8")
    r = run(tmp_path, [ev()], T("2026-09-28T06:00:00"))
    assert r["state"].startswith("STOPPED") and AL.read_ledger(tmp_path) == []


def test_no_llm_on_the_alert_path():
    import ast
    import inspect
    for mod in (AL, S):
        tree = ast.parse(inspect.getsource(mod))
        names = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                 for a in n.names} | {n.module for n in ast.walk(tree)
                                      if isinstance(n, ast.ImportFrom) and n.module}
        banned = ("llm_analyzer", "openclaw", "deepseek", "model_routing", "thesis_card",
                  "event_extraction", "anthropic", "openai")
        assert not any(b in str(x).lower() for x in names for b in banned), mod.__name__
