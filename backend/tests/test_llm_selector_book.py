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


def _reply(picks: list, model: str = "deepseek-flash") -> MP.Reply:
    return MP.Reply(provider="deepseek", model=model, text=json.dumps({"picks": picks}),
                    latency_s=0.1, prompt_tokens=1000, completion_tokens=200,
                    budget_accounting={"cost_usd": 0.0003})


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
    assert row["model_id"] == "deepseek-flash"
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
    assert rows[0]["prompt_hash"] and rows[0]["packet_hash"] and rows[0]["model_id"]
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
