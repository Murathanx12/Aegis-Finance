"""The LLM selector book: stamped packets, a validated reply, two twins, a frozen contract.

Offline: a stubbed provider, synthetic candidates and bars under tmp_path, no
live data. Dates are derived from `now`, never written as literals.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from backend import config as C
from backend.services import llm_selector_book as S
from backend.services import model_provider as MP

TICKERS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "JJJ", "KKK", "LLL"]
FUTURE_CLOSE = 9999.0


@pytest.fixture(autouse=True)
def _no_real_provider(monkeypatch):
    """Any path that reaches the real provider fails the test."""
    def boom(*a, **k):
        raise AssertionError("a real provider call was attempted")
    monkeypatch.setattr(MP, "complete", boom)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _funnel(now: datetime, *, age_days: float = 2.0, added: bool = True) -> dict:
    f = {"generated_at": S.iso(now - timedelta(days=age_days)),
         "candidates": [{"ticker": t, "price": 10.0 + i, "sector": "Tech", "quality": 0.5,
                         "median_dollar_vol": 5e7, "score": 1.0 - i / 100, "stage": 4}
                        for i, t in enumerate(TICKERS)]}
    if added:
        f["added_by_source"] = {"n_added": 1, "added": [
            {"ticker": "NEWS1", "sources": ["news"], "net_direction": "up",
             "first_seen_utc": S.iso(now - timedelta(hours=10))}]}
    return f


def _bars(now: datetime) -> pd.DataFrame:
    days = pd.bdate_range(end=(now - timedelta(days=1)).date(), periods=300)
    rows = []
    rng = np.random.default_rng(7)
    for t in TICKERS + ["NEWS1"]:
        px = 20.0 * np.exp(np.cumsum(rng.normal(0, 0.01, len(days))))
        rows += [{"symbol": t, "date": d, "close": float(p), "volume": 1e6} for d, p in zip(days, px)]
        # PLANTED: a bar dated after the decision with an absurd close
        rows.append({"symbol": t, "date": pd.Timestamp((now + timedelta(days=2)).date()),
                     "close": FUTURE_CLOSE, "volume": 1e9})
    return pd.DataFrame(rows)


def _rev(now: datetime) -> pd.DataFrame:
    return pd.DataFrame([
        {"ticker": "AAA", "event_date": now - timedelta(days=10), "target_action": "Raises", "target_change": 0.1},
        {"ticker": "AAA", "event_date": now - timedelta(days=5), "target_action": "Lowers", "target_change": -0.05},
        # PLANTED: an analyst action after the decision
        {"ticker": "AAA", "event_date": now + timedelta(days=1), "target_action": "Raises", "target_change": 0.9},
    ])


def _inputs(now: datetime, *, include_added: bool = False) -> dict:
    cset = S.candidate_set(_funnel(now), now=now, include_added=include_added)
    return {"cset": cset, "bars": _bars(now), "rev": _rev(now),
            "digest_by_ticker": {"AAA": [{"stamp": S.iso(now - timedelta(hours=20)), "theme": "past theme"},
                                         {"stamp": S.iso(now + timedelta(hours=1)), "theme": "FUTURE theme"}]},
            "corpus_by_ticker": {"BBB": [{"source": "rss", "title": "past headline",
                                          "known_at": now - timedelta(hours=3)}]}}


SERVED = "stub-served-model-x"     # deliberately not the request label


def _reply(picks: list, served: str | None = SERVED, text: str | None = None) -> MP.Reply:
    return MP.Reply(provider="deepseek", model=str(C.LLM_SELECTOR_MODEL),
                    text=json.dumps({"picks": picks}) if text is None else text,
                    latency_s=0.1, prompt_tokens=1000, completion_tokens=200,
                    budget_accounting={"cost_usd": 0.0003, "reservation_id": "res-abc123",
                                       "billing_status": "SETTLED_PEAK_ESTIMATE"},
                    served_model=served)


def _good(k: int | None = None) -> list:
    k = int(C.LLM_SELECTOR_K) if k is None else k
    return [{"ticker": t, "direction": "long", "reason": f"fact about {t}"} for t in TICKERS[-k:]]


# ── the packet ──────────────────────────────────────────────────────────────

def test_packet_holds_nothing_stamped_at_or_after_the_decision():
    now = _now()
    packets = S.all_packets(_inputs(now), now)
    assert packets and len(packets) == len(TICKERS)
    for p in packets:
        for field, value, stamp, source in p["facts"]:
            assert S.parse_stamp(stamp) < now, (p["ticker"], field, stamp)
            assert value != FUTURE_CLOSE
    aaa = next(p for p in packets if p["ticker"] == "AAA")
    vals = {f[0]: f[1] for f in aaa["facts"]}
    assert vals["revisions.revisions_90d"] == 2            # the planted +1 day action is excluded
    assert vals["revisions.net_raises_90d"] == 0
    assert "FUTURE theme" not in json.dumps(aaa["facts"])
    assert aaa["n_excluded_at_or_after_decision"] == 1    # the planted digest theme
    assert vals["price.close"] < FUTURE_CLOSE / 10


def test_a_planted_future_fact_is_excluded_and_counted():
    now = _now()
    facts = [S.fact("x.past", 1, now - timedelta(minutes=1), "t"),
             S.fact("x.at", 2, now, "t"),
             S.fact("x.future", 3, now + timedelta(days=3), "t")]
    pk = S.build_packet("AAA", facts, now)
    assert [f[0] for f in pk["facts"]] == ["x.past"]
    assert pk["n_excluded_at_or_after_decision"] == 2


@pytest.mark.parametrize("stamp", [None, "", "not a time", float("nan")])
def test_a_fact_without_a_stamp_refuses_the_packet(stamp):
    now = _now()
    with pytest.raises(S.SelectorRefused) as e:
        S.build_packet("AAA", [S.fact("x.nostamp", 1, stamp, "t")], now)
    assert e.value.code == S.UNSTAMPED_FIELD
    assert e.value.exit_code != 0


def test_a_date_only_stamp_is_read_as_the_end_of_that_day():
    now = _now()
    today = now.date().isoformat()
    assert S.parse_stamp(today) >= now                     # end of today, never its midnight
    pk = S.build_packet("AAA", [S.fact("x.today", 1, today, "t")], now)
    assert pk["facts"] == [] and pk["n_excluded_at_or_after_decision"] == 1


# ── the candidate set ───────────────────────────────────────────────────────

def test_a_stale_candidate_set_is_refused_never_used():
    now = _now()
    with pytest.raises(S.SelectorRefused) as e:
        S.candidate_set(_funnel(now, age_days=11), now=now, include_added=False)
    assert e.value.code == S.CANDIDATES_STALE and e.value.exit_code != 0


@pytest.mark.parametrize("gen", [None, "", "garbage"])
def test_an_undateable_candidate_set_is_refused(gen):
    now = _now()
    f = _funnel(now)
    f["generated_at"] = gen
    with pytest.raises(S.SelectorRefused) as e:
        S.candidate_set(f, now=now, include_added=False)
    assert e.value.code == S.CANDIDATES_UNDATEABLE


def test_a_date_only_generated_at_is_undateable():
    now = _now()
    f = _funnel(now)
    f["generated_at"] = (now - timedelta(days=1)).date().isoformat()
    with pytest.raises(S.SelectorRefused) as e:
        S.candidate_set(f, now=now, include_added=False)
    assert e.value.code == S.CANDIDATES_UNDATEABLE


def test_added_by_source_joins_only_with_the_flag():
    now = _now()
    off = S.candidate_set(_funnel(now), now=now, include_added=False)
    on = S.candidate_set(_funnel(now), now=now, include_added=True)
    assert "NEWS1" not in off["tickers"] and "NEWS1" in on["tickers"]
    assert on["ranked"] == off["ranked"] == TICKERS          # ranker order kept
    assert on["candidate_set_hash"] != off["candidate_set_hash"]
    pk = S.all_packets({**_inputs(now), "cset": on}, now)
    news = next(p for p in pk if p["ticker"] == "NEWS1")
    assert ["source.added_by", "news"] == news["facts"][0][:2] or any(
        f[0] == "source.added_by" for f in news["facts"])


def test_the_default_follows_the_funnel_news_flag(monkeypatch):
    now = _now()
    monkeypatch.setattr(C, "FUNNEL_NEWS_SOURCE_ENABLED", False)
    assert "NEWS1" not in S.candidate_set(_funnel(now), now=now)["tickers"]
    monkeypatch.setattr(C, "FUNNEL_NEWS_SOURCE_ENABLED", True)
    assert "NEWS1" in S.candidate_set(_funnel(now), now=now)["tickers"]


# ── one decision ────────────────────────────────────────────────────────────

def test_a_decision_row_carries_every_hash_and_id(tmp_path):
    now = _now()
    inp = _inputs(now)
    packets = S.all_packets(inp, now)
    res = S.run_decision(cset=inp["cset"], packets=packets, decision_time=now, out_dir=tmp_path,
                         complete=lambda s, u: _reply(_good()), enabled=True)
    row = res["row"]
    for key in ("packet_hash", "model_id", "prompt_hash", "response", "candidate_set_hash"):
        assert row[key], key
    assert row["model_id"] == row["served_model"] == SERVED            # what the provider said served it
    assert row["request_model"] == str(C.LLM_SELECTOR_MODEL)
    assert row["reply_model_label"] == str(C.LLM_SELECTOR_MODEL)      # model_provider's label = request
    assert row["reservation_id"] == "res-abc123"                      # links to the budget envelope
    assert row["written_utc"]
    from backend.services import llm_language as L
    system, user = S.render(inp["cset"], packets, now)
    assert row["prompt_hash"] == S.sha16(L.pin(system) + "\n" + user)  # as SENT, pin included
    assert row["prompt_hash_rendered"] == S.sha16(system + "\n" + user)
    assert row["prompt_hash"] != row["prompt_hash_rendered"]
    assert row["packet_hash"] == S.packets_hash(packets)
    assert row["candidate_set_hash"] == inp["cset"]["candidate_set_hash"]
    assert row["contract_hash"] == S.contract_hash()
    assert json.loads(row["response"])["picks"][0]["ticker"] == TICKERS[-int(C.LLM_SELECTOR_K)]
    assert row["cost_usd"] == 0.0003
    lines = (tmp_path / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["prompt_hash"] == row["prompt_hash"]
    books = [json.loads(x) for x in (tmp_path / "books.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [b.get("twin") for b in books] == [None, "selection_random_same_set", "incumbent_ranker_top_k"]
    assert books[1]["parent_book_id"] == books[2]["parent_book_id"] == books[0]["book_id"]
    assert books[0]["prompt_hash"] == row["prompt_hash"] and books[0]["evidence_hash"] == row["packet_hash"]
    assert not (tmp_path / "refusals.jsonl").exists()


def test_a_reply_outside_the_candidate_set_is_refused_and_counted(tmp_path):
    now = _now()
    inp = _inputs(now)
    packets = S.all_packets(inp, now)
    bad = _good()
    bad[0] = {"ticker": "ZZZZ", "direction": "long", "reason": "not offered"}
    for n in (1, 2):
        with pytest.raises(S.SelectorRefused) as e:
            S.run_decision(cset=inp["cset"], packets=packets, decision_time=now, out_dir=tmp_path,
                           complete=lambda s, u: _reply(bad), enabled=True)
        assert e.value.code == S.OUT_OF_SET and e.value.exit_code != 0
        assert S.refusal_counts(tmp_path) == {S.OUT_OF_SET: n}
    rows = [json.loads(x) for x in (tmp_path / "refusals.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0]["outside"] == ["ZZZZ"] and "ZZZZ" in rows[0]["response"]   # kept, not dropped
    assert rows[0]["prompt_hash"] and rows[0]["packet_hash"] and rows[0]["served_model"] == SERVED
    assert rows[0]["reservation_id"] == "res-abc123" and rows[0]["written_utc"]
    assert not (tmp_path / "decisions.jsonl").exists()          # not repaired into a 7-name book
    assert not (tmp_path / "books.jsonl").exists()


@pytest.mark.parametrize("picks,code", [
    (_good(int(C.LLM_SELECTOR_K) - 1), S.WRONG_K),
    (_good()[:-1] + [_good()[0]], S.DUPLICATE_PICK),
    ([{**p, "direction": "short"} for p in _good()], S.BAD_DIRECTION),
    ([{**p, "reason": " "} for p in _good()], S.MISSING_REASON),
])
def test_every_reply_defect_refuses_the_whole_decision(tmp_path, picks, code):
    now = _now()
    inp = _inputs(now)
    with pytest.raises(S.SelectorRefused) as e:
        S.run_decision(cset=inp["cset"], packets=S.all_packets(inp, now), decision_time=now,
                       out_dir=tmp_path, complete=lambda s, u: _reply(picks), enabled=True)
    assert e.value.code == code
    assert S.refusal_counts(tmp_path) == {code: 1}


def test_a_non_json_reply_is_refused():
    with pytest.raises(S.SelectorRefused) as e:
        S.parse_reply("I would buy AAA", tickers=TICKERS, k=2, directions=("long",))
    assert e.value.code == S.BAD_REPLY


def test_a_budget_refusal_is_a_non_zero_exit(tmp_path, monkeypatch):
    now = _now()
    inp = _inputs(now)

    def refuse(*a, **k):
        raise MP.BudgetRefusal("DEEPSEEK BUDGET REFUSED (EXHAUSTED): spent $15.00 of $15.00")
    monkeypatch.setattr(MP, "complete", refuse)              # the DEFAULT provider path
    with pytest.raises(S.SelectorRefused) as e:
        S.run_decision(cset=inp["cset"], packets=S.all_packets(inp, now), decision_time=now,
                       out_dir=tmp_path, enabled=True)
    assert e.value.code == S.BUDGET_REFUSED and e.value.exit_code == 3
    assert S.refusal_counts(tmp_path) == {S.BUDGET_REFUSED: 1}

    # ...and through the CLI
    from scripts import llm_selector_book as CLI
    monkeypatch.setattr(C, "LLM_SELECTOR_BOOK_ENABLED", True)
    monkeypatch.setattr(S, "load_inputs", lambda root, t, **k: _inputs(t))
    rc = CLI.main(["--decide", "--data-root", str(tmp_path / "data"), "--out", str(tmp_path / "o")])
    assert rc == 3


def test_a_provider_refusal_is_red(tmp_path):
    now = _now()
    inp = _inputs(now)

    def down(s, u):
        raise MP.ProviderRefusal("deepseek unreachable")
    with pytest.raises(S.SelectorRefused) as e:
        S.run_decision(cset=inp["cset"], packets=S.all_packets(inp, now), decision_time=now,
                       out_dir=tmp_path, complete=down, enabled=True)
    assert e.value.code == S.PROVIDER_REFUSED and e.value.exit_code != 0


# ── the twins ───────────────────────────────────────────────────────────────

def test_the_selection_twin_is_drawn_by_default_rng_from_the_same_set_and_recorded(tmp_path):
    now = _now()
    inp = _inputs(now, include_added=True)
    res = S.run_decision(cset=inp["cset"], packets=S.all_packets(inp, now), decision_time=now,
                         out_dir=tmp_path, complete=lambda s, u: _reply(_good()), enabled=True)
    tw = res["row"]["twins"]
    k = int(C.LLM_SELECTOR_K)
    seed = tw["selection"]["seed"]
    assert seed == int(C.LLM_SELECTOR_SEED_BASE) + S.decision_date(now).toordinal()
    idx = np.random.default_rng(seed).choice(len(inp["cset"]["tickers"]), size=k, replace=False)
    assert tw["selection"]["tickers"] == [inp["cset"]["tickers"][int(i)] for i in idx]
    assert set(tw["selection"]["tickers"]) <= set(inp["cset"]["tickers"])
    assert len(set(tw["selection"]["tickers"])) == k
    assert tw["incumbent"]["tickers"] == TICKERS[:k]           # the ranker's own top-k
    books = res["books"]
    assert sorted(p["ticker"] for p in books[1]["positions"]) == sorted(tw["selection"]["tickers"])
    assert sorted(p["ticker"] for p in books[2]["positions"]) == sorted(TICKERS[:k])
    assert S.selection_twin(inp["cset"]["tickers"], k, seed) == tw["selection"]["tickers"]


# ── the contract ────────────────────────────────────────────────────────────

def test_the_committed_contract_matches_the_code():
    frozen = S.check_frozen()
    assert frozen["contract_hash"] == S.contract_hash()
    assert frozen["licence"] == "PRODUCT_EXPERIMENT"
    assert "no authority over real capital" in frozen["authority"]


@pytest.mark.parametrize("target,attr,value", [
    ("S", "SYSTEM_PROMPT", S.SYSTEM_PROMPT + " Also."),
    ("S", "USER_TEMPLATE", S.USER_TEMPLATE + "\n"),
    ("C", "LLM_SELECTOR_K", int(C.LLM_SELECTOR_K) + 1),
    ("C", "LLM_SELECTOR_TEMPERATURE", float(C.LLM_SELECTOR_TEMPERATURE) + 0.1),
    ("C", "LLM_SELECTOR_MODEL", "deepseek-pro"),
    ("C", "LLM_SELECTOR_HOLD_SESSIONS", int(C.LLM_SELECTOR_HOLD_SESSIONS) + 1),
    ("C", "LLM_SELECTOR_REVISION_LOOKBACK_DAYS", 30),
    ("C", "LLM_SELECTOR_SEED_BASE", int(C.LLM_SELECTOR_SEED_BASE) + 1),
])
def test_the_contract_hash_changes_with_any_prompt_or_parameter(monkeypatch, target, attr, value):
    before = S.contract_hash()
    monkeypatch.setattr(S if target == "S" else C, attr, value)
    assert S.contract_hash() != before
    with pytest.raises(S.SelectorRefused) as e:
        S.check_frozen()
    assert e.value.code == S.CONTRACT_DRIFT


# ── the flag ────────────────────────────────────────────────────────────────

def test_flag_off_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("AEGIS_LLM_SELECTOR_BOOK", raising=False)
    now = _now()
    inp = _inputs(now)
    out = tmp_path / "out"
    called = []
    with pytest.raises(S.SelectorRefused) as e:
        S.run_decision(cset=inp["cset"], packets=S.all_packets(inp, now), decision_time=now,
                       out_dir=out, complete=lambda s, u: called.append(1), enabled=False)
    assert e.value.code == S.FLAG_OFF and e.value.exit_code == 4
    assert not out.exists() and not called

    from scripts import llm_selector_book as CLI
    monkeypatch.setattr(C, "LLM_SELECTOR_BOOK_ENABLED", False)
    monkeypatch.setattr(S, "load_inputs", lambda *a, **k: pytest.fail("flag off must not read"))
    assert CLI.main(["--decide", "--data-root", str(tmp_path / "d"), "--out", str(out)]) == 4
    assert not out.exists()


def test_missing_inputs_are_a_red_exit(tmp_path):
    now = _now()
    with pytest.raises(S.SelectorRefused) as e:
        S.load_inputs(tmp_path / "optimus", now)
    assert e.value.code == S.INPUT_MISSING and e.value.exit_code != 0
    from scripts import llm_selector_book as CLI
    rc = CLI.main(["--dry-run", "--data-root", str(tmp_path / "optimus"), "--out", str(tmp_path / "o")])
    assert rc != 0


def test_dry_run_on_synthetic_inputs_makes_no_call_and_prices_the_decision(tmp_path, monkeypatch):
    from scripts import llm_selector_book as CLI
    monkeypatch.setattr(S, "load_inputs", lambda root, t, **k: {**_inputs(t), "paths": {},
                                                                 "sizes": {"bars_rows": 1}})
    out = tmp_path / "o"
    assert CLI.main(["--dry-run", "--data-root", str(tmp_path / "d"), "--out", str(out)]) == 0
    rec = json.loads(next(out.glob("llm_selector_dry_run_*Z.json")).read_text(encoding="utf-8"))
    assert rec["llm_calls_made"] == 0
    assert rec["candidate_set"]["n_ranked"] == len(TICKERS)
    row = rec["cost"]["by_price_row"]["request_model_list_price"]
    assert row["usd_per_decision"] > 0 and row["usd_per_month"] > row["usd_per_decision"]


def test_non_latin_titles_are_left_out_of_the_packet():
    now = _now()
    by = {"AAA": [{"source": "rss", "title": "English headline", "known_at": now - timedelta(hours=2)},
                  {"source": "rss_zh", "title": "黃仁勳若下台亞股殺血海",
                   "known_at": now - timedelta(hours=1)}]}
    items = S.knowable_facts(by, "AAA", 5)
    assert [f["value"] for f in items] == ["[rss] English headline"]


# ── review round 1 ──────────────────────────────────────────────────────────

def _decide(tmp_path, now=None, complete=None, cset=None, inp=None):
    now = now or _now()
    inp = inp or _inputs(now)
    return S.run_decision(cset=cset or inp["cset"], packets=S.all_packets(inp, now), decision_time=now,
                          out_dir=tmp_path, complete=complete or (lambda s, u: _reply(_good())),
                          enabled=True)


def test_decide_refuses_now_and_a_backdated_instant(tmp_path, monkeypatch):
    from scripts import llm_selector_book as CLI
    monkeypatch.setattr(C, "LLM_SELECTOR_BOOK_ENABLED", True)
    monkeypatch.setattr(S, "load_inputs", lambda *a, **k: pytest.fail("--now must refuse before reading"))
    past = S.iso(_now() - timedelta(hours=36))
    rc = CLI.main(["--decide", "--now", past, "--data-root", str(tmp_path / "d"), "--out", str(tmp_path / "o")])
    assert rc == 2 and not (tmp_path / "o").exists()
    # and the service refuses a decision instant that is not the wall clock
    with pytest.raises(S.SelectorRefused) as e:
        _decide(tmp_path / "o2", now=_now() - timedelta(hours=36))
    assert e.value.code == S.BACKDATED and e.value.exit_code == 2
    assert not (tmp_path / "o2").exists()


def test_cli_decide_uses_the_wall_clock(tmp_path, monkeypatch):
    from scripts import llm_selector_book as CLI
    monkeypatch.setattr(C, "LLM_SELECTOR_BOOK_ENABLED", True)
    seen = {}

    def fake_inputs(root, t, **k):
        seen["t"] = t
        return _inputs(t)
    monkeypatch.setattr(S, "load_inputs", fake_inputs)
    monkeypatch.setattr(S, "_default_complete", lambda s, u: _reply(_good()))
    out = tmp_path / "o"
    assert CLI.main(["--decide", "--data-root", str(tmp_path / "d"), "--out", str(out)]) == 0
    assert abs((seen["t"] - _now()).total_seconds()) < 60
    row = json.loads((out / "decisions.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert row["written_utc"] and row["decision_time"] == S.iso(seen["t"])


def test_a_revision_is_cut_on_the_later_of_event_and_pull_stamps():
    now = _now()
    rev = pd.DataFrame([
        # happened 10 days ago, but WE first saw it 2 days AFTER the decision
        {"ticker": "AAA", "event_date": S.iso(now - timedelta(days=10)), "target_action": "Raises",
         "target_change": 0.5, "first_seen_utc": S.iso(now + timedelta(days=2)),
         "pulled_at": S.iso(now + timedelta(days=2))},
        # happened 5 days ago, seen 4 days ago: knowable at the pull
        {"ticker": "AAA", "event_date": S.iso(now - timedelta(days=5)), "target_action": "Lowers",
         "target_change": -0.1, "first_seen_utc": S.iso(now - timedelta(days=4)),
         "pulled_at": S.iso(now - timedelta(days=4))},
    ])
    facts = S.revision_facts(rev, "AAA", now, 90)
    vals = {f["field"]: f for f in facts}
    assert vals["revisions.revisions_90d"]["value"] == 1
    assert vals["revisions.net_raises_90d"]["value"] == -1
    assert S.parse_stamp(vals["revisions.revisions_90d"]["stamp"]) == S.parse_stamp(S.iso(now - timedelta(days=4)))


def test_a_corpus_item_is_stamped_by_the_later_of_first_seen_and_published():
    now = _now()
    r = {"source": "rss", "title": "x", "known_at": now - timedelta(hours=5),
         "first_seen_utc_raw": S.iso(now - timedelta(hours=5)), "published_at": now + timedelta(hours=1)}
    assert S.knowable_stamp(r) == now + timedelta(hours=1)
    pk = S.build_packet("AAA", S.knowable_facts({"AAA": [r]}, "AAA", 5), now)
    assert pk["facts"] == [] and pk["n_excluded_at_or_after_decision"] == 1


def test_a_second_decision_for_the_same_date_is_refused_before_the_call(tmp_path):
    calls = []

    def stub(s, u):
        calls.append(1)
        return _reply(_good())
    _decide(tmp_path, complete=stub)
    with pytest.raises(S.SelectorRefused) as e:
        _decide(tmp_path, complete=stub)
    assert e.value.code == S.ALREADY_DECIDED and e.value.exit_code == 2
    assert len(calls) == 1                                       # no paid re-roll
    assert len((tmp_path / "decisions.jsonl").read_text(encoding="utf-8").splitlines()) == 1
    assert len((tmp_path / "books.jsonl").read_text(encoding="utf-8").splitlines()) == 3
    ref = json.loads((tmp_path / "refusals.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert ref["code"] == S.ALREADY_DECIDED and ref["written_utc"] and ref["decision_date"]


def test_a_missing_served_model_is_said_not_invented(tmp_path):
    row = _decide(tmp_path, complete=lambda s, u: _reply(_good(), served=None))["row"]
    assert row["served_model"] is None and row["model_id"] == "SERVED_MODEL_NOT_REPORTED"


def test_model_provider_reply_carries_the_served_model(monkeypatch):
    """`model_provider.complete` keeps the payload's own `model` (offline: the
    transport and the budget path are stubbed)."""
    from backend.services import provider_budget as PB
    monkeypatch.undo()                     # the real complete(), with the transport stubbed below
    mp = MP
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    payload = {"model": "deepseek-flash-served", "usage": {"prompt_tokens": 3, "completion_tokens": 2},
               "choices": [{"message": {"content": "ok, in English"}, "finish_reason": "stop"}]}
    monkeypatch.setattr(PB, "guarded_send", lambda body, **k: (payload, {"reservation_id": "r1"}))
    rep = mp.complete("deepseek", "hi", model="deepseek-chat", purpose="test")
    assert rep.model == "deepseek-chat" and rep.served_model == "deepseek-flash-served"
    assert rep.budget_accounting == {"reservation_id": "r1"}


ONE = {"ticker": "AAA", "direction": "long", "reason": "a fact"}


@pytest.mark.parametrize("text,code", [
    ("Here is my book: " + json.dumps({"picks": [ONE, {**ONE, "ticker": "BBB"}]}), S.BAD_REPLY),
    ("```json\n" + json.dumps({"picks": [ONE, {**ONE, "ticker": "BBB"}]}) + "\n```", S.BAD_REPLY),
    (json.dumps({"picks": [ONE, {**ONE, "ticker": "BBB"}]}) + " {}", S.BAD_REPLY),
    (json.dumps({"picks": [ONE, {**ONE, "ticker": "BBB"}], "note": "x"}), S.BAD_SHAPE),
    (json.dumps({"picks": [ONE, {**ONE, "ticker": "BBB", "weight": 0.5}]}), S.BAD_SHAPE),
    (json.dumps({"picks": [ONE, {**ONE, "ticker": " BBB"}]}), S.OUT_OF_SET),
    (json.dumps({"picks": [ONE, {**ONE, "ticker": "BBB", "direction": "Long"}]}), S.BAD_DIRECTION),
    (json.dumps({"picks": [ONE, {**ONE, "ticker": "BBB", "reason": "two\nlines"}]}), S.BAD_REASON),
    (json.dumps({"picks": [ONE, {**ONE, "ticker": "BBB", "reason": "x" * 301}]}), S.BAD_REASON),
    (json.dumps({"picks": [ONE, {**ONE, "ticker": 7}]}), S.BAD_SHAPE),
])
def test_the_reply_contract_is_strict(text, code):
    with pytest.raises(S.SelectorRefused) as e:
        S.parse_reply(text, tickers=TICKERS, k=2, directions=("long",))
    assert e.value.code == code


def test_upper_casing_is_the_only_normalisation():
    out = S.parse_reply(json.dumps({"picks": [{**ONE, "ticker": "aaa"}, {**ONE, "ticker": "BBB"}]}),
                        tickers=TICKERS, k=2, directions=("long",))
    assert [p["ticker"] for p in out] == ["AAA", "BBB"] and out[0]["reason"] == "a fact"


def test_a_non_latin_reason_is_refused_even_under_the_central_bar(tmp_path):
    from backend.services import llm_language as L
    picks = _good()
    picks[0] = {**picks[0], "reason": "\u9ec3\u4ec1\u52f3\u82e5\u4e0b\u53f0\u4e9e\u80a1"}
    text = json.dumps({"picks": picks}, ensure_ascii=False)
    assert L.non_latin_share(text) <= L.NON_LATIN_BAR         # the whole reply passes the central bar
    with pytest.raises(S.SelectorRefused) as e:
        _decide(tmp_path, complete=lambda s, u: _reply(picks, text=text))
    assert e.value.code == S.REASON_NOT_ENGLISH
    ref = json.loads((tmp_path / "refusals.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert ref["response"] == text                              # raw reply kept


def test_a_budget_refusal_row_carries_the_decision_context(tmp_path):
    def refuse(s, u):
        raise MP.BudgetRefusal("DEEPSEEK BUDGET REFUSED (EXHAUSTED)")
    with pytest.raises(S.SelectorRefused):
        _decide(tmp_path, complete=refuse)
    ref = json.loads((tmp_path / "refusals.jsonl").read_text(encoding="utf-8").splitlines()[0])
    for key in ("decision_date", "candidate_set_hash", "contract_hash", "written_utc", "packet_hash",
                "prompt_hash"):
        assert ref.get(key), key
    assert ref["contract_hash"] == S.contract_hash()


@pytest.mark.parametrize("attr,value", [
    ("PACKET_SCHEMA_VERSION", "llm_selector_packet/999"),
    ("FUNNEL_FIELDS", ("sector",)),
    ("ENTRY_RULE", "entered whenever"),
    ("_language_pin", lambda: " Respond in Latin only."),
])
def test_the_contract_hash_covers_the_packet_code_and_the_pin(monkeypatch, attr, value):
    before = S.contract_hash()
    monkeypatch.setattr(S, attr, value)
    assert S.contract_hash() != before


def test_too_few_candidates_is_refused_before_the_call(tmp_path):
    now = _now()
    f = _funnel(now, added=False)
    f["candidates"] = f["candidates"][: int(C.LLM_SELECTOR_K)]
    cset = S.candidate_set(f, now=now, include_added=False)
    calls = []
    with pytest.raises(S.SelectorRefused) as e:
        _decide(tmp_path, now=now, cset=cset, complete=lambda s, u: calls.append(1))
    assert e.value.code == S.TOO_FEW_CANDIDATES and not calls
    assert S.refusal_counts(tmp_path) == {S.TOO_FEW_CANDIDATES: 1}


def test_the_env_var_turns_the_flag_on_for_one_run(tmp_path, monkeypatch):
    from scripts import llm_selector_book as CLI
    monkeypatch.setattr(C, "LLM_SELECTOR_BOOK_ENABLED", False)
    monkeypatch.delenv("AEGIS_LLM_SELECTOR_BOOK", raising=False)
    assert not S.flag_on()
    monkeypatch.setenv("AEGIS_LLM_SELECTOR_BOOK", "1")
    assert S.flag_on()
    monkeypatch.setattr(S, "load_inputs", lambda root, t, **k: _inputs(t))
    monkeypatch.setattr(S, "_default_complete", lambda s, u: _reply(_good()))
    assert CLI.main(["--decide", "--data-root", str(tmp_path / "d"), "--out", str(tmp_path / "o")]) == 0
    monkeypatch.setenv("AEGIS_LLM_SELECTOR_BOOK", "0")
    assert not S.flag_on()


def test_register_is_idempotent_and_has_a_dry_run(tmp_path, monkeypatch, capsys):
    from scripts import llm_selector_book as CLI
    root = tmp_path / "optimus"
    sel = root / "llm_selector"
    target = root / "llm_portfolio" / "books.jsonl"
    target.parent.mkdir(parents=True)
    target.write_text('{"book_id": "existing", "name": "old"}\n', encoding="utf-8")
    res = _decide(sel)
    day = res["row"]["decision_date"]
    base = ["--register", "--decision-date", day, "--data-root", str(root)]
    assert CLI.main(base + ["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "WOULD APPEND 3 rows" in out and res["books"][0]["book_id"] in out
    assert target.read_text(encoding="utf-8").count("\n") == 1          # dry run wrote nothing
    assert CLI.main(base) == 0
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4 and {json.loads(x)["book_id"] for x in lines[1:]} == set(res["row"]["book_ids"].values())
    assert CLI.main(base) == 2                                            # a duplicate is refused
    assert CLI.main(base + ["--dry-run"]) == 2
    assert len(target.read_text(encoding="utf-8").splitlines()) == 4
    assert CLI.main(["--register", "--decision-date", "1999-01-01", "--data-root", str(root)]) == 2


def _a_past_session():
    from backend.services import market_sessions as MS
    d = (_now() - timedelta(days=30)).date()
    while not MS.is_session(d):
        d -= timedelta(days=1)
    nxt = d + timedelta(days=1)
    while not MS.is_session(nxt):
        nxt += timedelta(days=1)
    return d, nxt


@pytest.mark.parametrize("ny_hour", [8, 12])          # before and after the 09:30 New York open
def test_the_entry_rule_before_and_after_the_open(ny_hour):
    from datetime import datetime as _dt, time as _time
    d, nxt = _a_past_session()
    t = _dt.combine(d, _time(ny_hour, 0), tzinfo=S.NY).astimezone(timezone.utc)
    assert S.decision_date(t) == d
    assert S.entry_session(t) == str(nxt)               # never D's own open, even at 08:00
    assert S.ENTRY_RULE in S.render(S.candidate_set(_funnel(_now()), now=_now(), include_added=False),
                                    [], t)[0]
    assert S.contract()["entry_rule"] == S.ENTRY_RULE
    assert "next session's open" not in S.SYSTEM_PROMPT


# ── CH-35 slice 2: the event-node block (EVENT_NODES_SELECTOR_PACKET_ENABLED) ──

def _briefs(now):
    def b(eid, primary, role, link, built, imp):
        return {"event_id": eid, "primary_ticker": primary, "role": role, "link": link, "age_hours": 5.0,
                "importance_at": imp, "n_publishers": 3, "dated_facts_filled": None,
                "version_built_utc": S.iso(built), "first_seen_utc": S.iso(now - timedelta(hours=5))}
    return {"AAA": [b("ev_1", "AAA", "primary", "primary", now - timedelta(hours=1), 6.0),
                    b("ev_2", "ZZZ", "connected", "co_mention", now - timedelta(hours=2), 4.0),
                    # a version built AFTER the decision: the packet's admission drops it
                    b("ev_3", "YYY", "connected", "co_coverage", now + timedelta(minutes=1), 3.0),
                    b("ev_4", "XXX", "connected", "co_coverage", now - timedelta(hours=2), 1.0)]}


def test_event_block_off_leaves_contract_and_packets_exactly_as_main(monkeypatch):
    now = _now()
    monkeypatch.setattr(C, "EVENT_NODES_SELECTOR_PACKET_ENABLED", False)
    h_off = S.contract_hash()
    assert S.contract_body()["packet_schema_version"] == S.PACKET_SCHEMA_VERSION
    assert "event_nodes" not in S.contract_body()["packet"]
    inp = _inputs(now)
    base = S.packets_hash(S.all_packets(inp, now))
    assert S.packets_hash(S.all_packets({**inp, "event_by_ticker": _briefs(now)}, now)) == base
    monkeypatch.setattr(C, "EVENT_NODES_SELECTOR_PACKET_ENABLED", True)
    assert S.contract_hash() != h_off
    assert S.contract_body()["packet_schema_version"] == C.EVENT_NODES_SELECTOR_PACKET_SCHEMA


def test_event_block_on_carries_ids_and_counts_never_text(monkeypatch):
    now = _now()
    monkeypatch.setattr(C, "EVENT_NODES_SELECTOR_PACKET_ENABLED", True)
    monkeypatch.setattr(C, "EVENT_NODES_SELECTOR_TOP_K", 3)
    pk = {p["ticker"]: p for p in S.all_packets({**_inputs(now), "event_by_ticker": _briefs(now)}, now)}
    ev = [f for f in pk["AAA"]["facts"] if f[0] == "event_node"]
    assert sorted(f[1]["event_id"] for f in ev) == ["ev_1", "ev_2"]      # top-3, then ev_3 built after
    assert pk["AAA"]["n_excluded_at_or_after_decision"] >= 1
    assert set(ev[0][1]) == {"event_id", "primary", "role", "link", "age_h", "importance", "n_publishers",
                             "dated_facts"}
    assert not [f for f in pk["BBB"]["facts"] if f[0] == "event_node"]


def _sel_world(tmp_path, now):
    """A real data root on disk: funnel beside it, bars, empty digest/corpus, an event store."""
    from backend.services import event_nodes as EN
    dr = tmp_path / "optimus"
    (dr / "prices_2025_26").mkdir(parents=True)
    (dr / "digest").mkdir()
    (dr / "news_corpus").mkdir()
    (tmp_path / "funnel_night10.json").write_text(json.dumps(_funnel(now, added=False)), encoding="utf-8")
    _bars(now).to_parquet(dr / "prices_2025_26" / "bars.parquet", index=False)

    def node(imp0, built, ver):
        fs = now - timedelta(hours=6)
        return {"event_id": "ev_aaa", "primary_ticker": "AAA", "first_seen_utc": S.iso(fs),
                "built_now_utc": S.iso(built), "content_hash": ver, "version_key": ver, "n_evidence": 2,
                "importance": {"importance_0": imp0, "facts": {"n_publishers": 2}},
                "decay": {"half_life_hours": 72.0}, "parent_id": "par_aaa",
                "evidence": [{"item_key": "k", "title": "LICENSED TITLE", "url": "https://x.test/a"}],
                "connected_names": {"co_mention": [{"ticker": "BBB", "n_items": 2}], "graph": []}}
    store = dr / C.EVENT_NODES_DIRNAME / EN.STORE_NAME
    EN.append_rows(store, [node(3.0, now - timedelta(hours=2), "v1")])
    EN.append_rows(store, [node(9.0, now + timedelta(minutes=10), "v2")])     # built AFTER the decision
    return dr, store


def test_load_inputs_with_a_real_store_uses_the_version_known_at_the_decision(tmp_path, monkeypatch):
    now = _now()
    monkeypatch.setattr(C, "EVENT_NODES_SELECTOR_PACKET_ENABLED", True)
    dr, store = _sel_world(tmp_path, now)
    inp = S.load_inputs(dr, now)
    assert inp["sizes"]["event_versions_after_decision_skipped"] == 1
    assert inp["sizes"]["event_store_newest_build_utc"] == S.iso(now - timedelta(hours=2))
    assert inp["sizes"]["event_store_age_hours"] == 2.0 and inp["sizes"]["event_nodes_degradation"] is None
    pk = {p["ticker"]: p for p in S.all_packets(inp, now)}
    ev = [f for f in pk["AAA"]["facts"] if f[0] == "event_node"]
    assert len(ev) == 1 and ev[0][1]["importance"] < 3.0 and ev[0][2] == S.iso(now - timedelta(hours=2))
    assert [f[1]["role"] for f in pk["BBB"]["facts"] if f[0] == "event_node"] == ["connected"]
    assert "LICENSED TITLE" not in json.dumps(pk) and "x.test" not in json.dumps(pk)


def test_load_inputs_on_a_torn_store_degrades_by_name(tmp_path, monkeypatch):
    now = _now()
    monkeypatch.setattr(C, "EVENT_NODES_SELECTOR_PACKET_ENABLED", True)
    dr, store = _sel_world(tmp_path, now)
    store.write_bytes(store.read_bytes() + b'{"row_kind": "no')
    inp = S.load_inputs(dr, now)
    assert inp["sizes"]["event_nodes_degradation"].startswith("STORE_TORN_TAIL")
    assert not [f for p in S.all_packets(inp, now) for f in p["facts"] if f[0] == "event_node"]


def test_load_inputs_without_a_store_refuses_when_the_flag_is_on(tmp_path, monkeypatch):
    now = _now()
    monkeypatch.setattr(C, "EVENT_NODES_SELECTOR_PACKET_ENABLED", True)
    dr, store = _sel_world(tmp_path, now)
    store.unlink()
    with pytest.raises(S.SelectorRefused) as e:
        S.load_inputs(dr, now)
    assert e.value.code == S.INPUT_MISSING
