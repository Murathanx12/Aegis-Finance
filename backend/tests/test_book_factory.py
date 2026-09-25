"""scripts/book_factory.py: evidence pack, flat JSON, degraded parse, spend cap.

Offline: the LLM, the local model and the spend ledger are stubs. Every date
derives from `today`.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from backend import config as C
from backend.services import llm_portfolio as LP
from scripts import book_factory as BF

TODAY = date.today()
REPO = Path(__file__).resolve().parents[2]


# ───────────────────────────── strategies ───────────────────────────────────

def test_ten_strategies_per_kind_with_unique_ids():
    for kind in ("competition", "personal"):
        s = BF.STRATEGIES[kind]
        assert len(s) == 10
        assert len({x["id"] for x in s}) == 10
        assert all(x["brief"] for x in s)


# ───────────────────────────── evidence pack ────────────────────────────────

def _revisions():
    d = lambda n: str(pd.Timestamp(TODAY - timedelta(days=n)))  # noqa: E731
    return pd.DataFrame([
        # counted: strictly before asof and inside 90 days
        {"ticker": "AAA", "event_date": d(1), "firm": "F1", "target_action": "Raises",
         "prior_target": 10, "current_target": 12, "target_change": 0.2, "pit_safe": True},
        {"ticker": "AAA", "event_date": d(30), "firm": "F2", "target_action": "Raises",
         "prior_target": 10, "current_target": 11, "target_change": 0.1, "pit_safe": True},
        {"ticker": "AAA", "event_date": d(60), "firm": "F3", "target_action": "Lowers",
         "prior_target": 10, "current_target": 9, "target_change": -0.1, "pit_safe": True},
        # excluded: ON asof (not strictly before), outside 90d, not pit_safe
        {"ticker": "AAA", "event_date": str(pd.Timestamp(TODAY)), "firm": "F4",
         "target_action": "Raises", "prior_target": 1, "current_target": 2,
         "target_change": 1.0, "pit_safe": True},
        {"ticker": "AAA", "event_date": d(120), "firm": "F5", "target_action": "Raises",
         "prior_target": 1, "current_target": 2, "target_change": 1.0, "pit_safe": True},
        {"ticker": "AAA", "event_date": d(2), "firm": "F6", "target_action": "Raises",
         "prior_target": 1, "current_target": 2, "target_change": 1.0, "pit_safe": False},
    ])


def test_revision_flow_is_point_in_time():
    rf = BF.revision_flow(_revisions(), asof=TODAY, window_days=90)
    a = rf["AAA"]
    assert a["n_events"] == 3
    assert a["net_raises"] == 1          # 2 raises - 1 lower
    assert a["n_firms"] == 3
    assert a["median_target_change"] == pytest.approx(0.1)


def _write_news(root: Path):
    src = root / "yfinance_ticker_news"
    src.mkdir(parents=True)
    rows = []
    for i in range(7):
        pub = datetime.now(timezone.utc) - timedelta(days=i + 1)
        rows.append({"source": "yfinance_ticker_news",
                     "first_seen_utc": pub.isoformat(), "published_utc": pub.isoformat(),
                     "title": f"AAA headline {i}", "tickers": ["AAA"]})
    old = datetime.now(timezone.utc) - timedelta(days=30)
    rows.append({"source": "yfinance_ticker_news", "first_seen_utc": old.isoformat(),
                 "published_utc": old.isoformat(), "title": "AAA ancient", "tickers": ["AAA"]})
    rows.append({"source": "yfinance_ticker_news",
                 "first_seen_utc": datetime.now(timezone.utc).isoformat(),
                 "published_utc": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                 "title": "BBB only", "tickers": ["BBB"]})
    (src / f"{TODAY}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def test_news_last_14_days_by_ticker(tmp_path):
    _write_news(tmp_path)
    n = BF.news_evidence(["AAA", "ZZZ"], asof=TODAY, root=tmp_path, days=14)
    assert n["AAA"]["n_headlines"] == 7
    assert len(n["AAA"]["top_titles"]) == 5
    assert all("ancient" not in t for t in n["AAA"]["top_titles"])
    assert n.get("ZZZ", {"n_headlines": 0})["n_headlines"] == 0


def test_bloomberg_codes_map_to_yfinance():
    assert BF.bbg_to_yf("2330 TT") == "2330.TW"
    assert BF.bbg_to_yf("NOVO B DC") == "NOVO-B.CO"
    assert BF.bbg_to_yf("RHM GY") == "RHM.DE"
    assert BF.bbg_to_yf("8035 JP") == "8035.T"
    assert BF.bbg_to_yf("ASML NA") == "ASML.AS"
    assert BF.bbg_to_yf("TSM US") == "TSM"


def test_catalyst_yaml_rows_carry_source_and_verification():
    rows = BF.load_catalysts(REPO / "backend/data/optimus/pm_catalysts/catalysts_2026-Q4.yaml")
    assert len(rows) >= 25
    for r in rows:
        assert r["source_url"], r
        assert r["verified_from"] in ("primary", "aggregator"), r
        assert r["ticker"] and r["date"] and r["kind"] and r["what"]
    assert not any(r["ticker"] == "CYTK" for r in rows), "CYTK was struck"
    assert sum(1 for r in rows if r["ticker"] == "COGT") == 2


# ───────────────────────────── parsing ──────────────────────────────────────

GOOD = {"name": "x", "strategy": "power", "objective": "o", "cash_weight": 0.0,
        "positions": [f"N{i:02d}|0.1|semis|thesis {i}|falsifier {i}" for i in range(10)],
        "what_i_did_not_buy": ["MCD|five target cuts"]}


def test_parse_clean_and_fenced_json():
    b, st = BF.parse_answer(json.dumps(GOOD))
    assert st == "ok" and len(b["positions"]) == 10
    assert b["positions"][0] == {"ticker": "N00", "weight": 0.1, "theme": "semis",
                                 "thesis": "thesis 0", "falsifier": "falsifier 0"}
    b2, st2 = BF.parse_answer("```json\n" + json.dumps(GOOD) + "\n```")
    assert st2 == "ok" and b2["positions"] == b["positions"]


def test_parse_degraded_lifts_positions():
    broken = json.dumps(GOOD)[:-40]          # truncated mid-way
    b, st = BF.parse_answer(broken)
    assert st == "degraded"
    assert len(b["positions"]) >= 8


def test_parse_failed_on_garbage():
    b, st = BF.parse_answer("I cannot help with that.")
    assert st == "failed" and b["positions"] == []


def test_to_book_competition_and_personal():
    strat = BF.STRATEGIES["competition"][0]
    b, _ = BF.parse_answer(json.dumps(GOOD))
    book = BF.to_book(b, strategy=strat, kind="competition", asof=TODAY,
                      model="deepseek-chat", parse="ok")
    assert book["kind"] == "competition"
    assert book["objective"] == C.BOOK_COMPETITION_OBJECTIVE
    rec = LP.freeze(book)
    assert rec["n_positions"] == 10
    pb = BF.to_book(b, strategy=BF.STRATEGIES["personal"][0], kind="personal",
                    asof=TODAY, model="m", parse="ok")
    assert any(p["ticker"] == "CASH" for p in pb["positions"])


def test_prompt_is_flat_json_and_names_the_strategy():
    system, user = BF.build_prompt({"candidates": [], "notes": {}}, kind="competition",
                                   strategy=BF.STRATEGIES["competition"][2])
    assert "json" in system.lower()
    assert "TICKER|weight|theme|thesis|falsifier" in system
    assert BF.STRATEGIES["competition"][2]["id"] in user
    # the shared evidence comes BEFORE the strategy (cache-friendly prefix)
    assert user.index("EVIDENCE") < user.index("YOUR STRATEGY")


# ───────────────────────────── generate ─────────────────────────────────────

def _us_bars(names, n=80):
    rng = np.random.default_rng(0)
    days = pd.bdate_range(end=pd.Timestamp(TODAY - timedelta(days=1)), periods=n)
    out = []
    for s in names:
        px = 50 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
        out.append(pd.DataFrame({"symbol": s, "date": days, "open": px, "high": px,
                                 "low": px, "close": px, "volume": 5e7 / px}))
    return pd.concat(out, ignore_index=True)


class _LLM:
    def __init__(self, answer=None):
        self.calls = 0
        self.answer = answer or json.dumps(GOOD)

    def __call__(self, system, user, *, max_tokens):
        self.calls += 1
        return {"text": self.answer, "model": "deepseek-chat",
                "served_model": "deepseek-flash", "cost_usd": 0.01,
                "tokens_in": 1000, "tokens_out": 500, "error": None}


class _Spend:
    """A ledger that sees each call the LLM stub makes."""

    def __init__(self, llm, per_call=0.01, fail=False, blind=False):
        self.llm, self.per_call, self.fail, self.blind = llm, per_call, fail, blind

    def __call__(self, since):
        if self.fail:
            return {}
        n = 0 if self.blind else self.llm.calls
        return {"n_calls": n, "total_cost_usd": n * self.per_call,
                "total_is_lower_bound": False}


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "OPTIMUS_LEDGER_DIR", tmp_path / "optimus")
    return tmp_path


def _gen(ledger, llm, spend, *, n=2, kind="competition", local=None):
    names = [f"N{i:02d}" for i in range(10)] + [f"R{i:02d}" for i in range(30)]
    return BF.generate(
        kind=kind, n=n, asof=TODAY, out_dir=ledger / "out", notes=[],
        llm=llm, local=local or (lambda s, u, *, max_tokens: None),
        spend=spend, us_bars=_us_bars(names + ["SPY"]),
        resolve=lambda ts: set(), revisions=_revisions(),
        news_root=ledger / "news", catalysts=[], briefing_rows={},
        extra_tickers=names)


def test_generate_freezes_deepseek_books_with_twins(ledger):
    llm = _LLM()
    rc = _gen(ledger, llm, _Spend(llm))
    assert rc["n_frozen"] == 2 and llm.calls == 2
    books = LP.read_books()
    parents = [b for b in books if b["kind"] == "competition"]
    assert len(parents) == 2
    assert sum(1 for b in books if b["kind"] == "twin") == 8
    assert rc["local"]["status"].startswith("SKIPPED")
    saved = list((ledger / "out").glob("*.deepseek.json"))
    assert len(saved) == 2
    assert json.loads(saved[0].read_text())["parse"] == "ok"
    assert (ledger / "out" / "evidence_pack.json").exists()
    assert (ledger / "out" / "receipt.json").exists()


def test_generate_saves_the_local_answer_but_freezes_only_deepseek(ledger):
    llm = _LLM()
    local = lambda s, u, *, max_tokens: {"text": json.dumps(GOOD), "model": "local"}  # noqa: E731
    rc = _gen(ledger, llm, _Spend(llm), n=1, local=local)
    assert len(list((ledger / "out").glob("*.local.json"))) == 1
    assert rc["n_frozen"] == 1


def test_generate_stops_at_the_cap(ledger, monkeypatch):
    monkeypatch.setattr(C, "BOOK_FACTORY_CAP_USD", 0.025)
    monkeypatch.setattr(C, "BOOK_FACTORY_EST_CALL_USD", 0.01)
    llm = _LLM()
    rc = _gen(ledger, llm, _Spend(llm, per_call=0.01), n=5)
    assert llm.calls == 2
    assert rc["stopped"].startswith("CAP")


def test_generate_refuses_when_spend_is_unknown(ledger):
    llm = _LLM()
    rc = _gen(ledger, llm, _Spend(llm, fail=True))
    assert llm.calls == 0 and rc["stopped"].startswith("SPEND UNKNOWN")


def test_generate_stops_when_the_ledger_cannot_see_the_call(ledger):
    llm = _LLM()
    rc = _gen(ledger, llm, _Spend(llm, blind=True), n=3)
    assert llm.calls == 1
    assert rc["stopped"].startswith("LEDGER BLIND")


def test_generate_degraded_parse_is_marked_on_the_book(ledger):
    llm = _LLM(answer=json.dumps(GOOD)[:-40])
    _gen(ledger, llm, _Spend(llm), n=1)
    parents = [b for b in LP.read_books() if b["kind"] == "competition"]
    assert parents and parents[0]["parse"] == "degraded"


def test_generate_refusal_is_saved_not_frozen(ledger):
    bad = dict(GOOD, positions=["N00|0.5|semis|t|f", "N01|0.5|semis|t|f"])
    llm = _LLM(answer=json.dumps(bad))
    rc = _gen(ledger, llm, _Spend(llm), n=1)
    assert rc["n_frozen"] == 0 and rc["n_refused"] == 1
    assert not [b for b in LP.read_books() if b["kind"] == "competition"]


# ───────────────────────────── the re-ask ───────────────────────────────────

class _SeqLLM(_LLM):
    """First answer incomplete (the 2026-09-25 smoke shape), then complete."""

    def __init__(self, answers):
        super().__init__()
        self.answers = list(answers)
        self.users: list[str] = []

    def __call__(self, system, user, *, max_tokens):
        self.users.append(user)
        out = super().__call__(system, user, max_tokens=max_tokens)
        out["text"] = self.answers[min(self.calls - 1, len(self.answers) - 1)]
        return out


ONE = json.dumps(dict(GOOD, cash_weight=0.02, positions=["MU|0.10|semis|t|f"]))


def test_shape_defect_names_the_problem():
    b, _ = BF.parse_answer(ONE)
    d = BF.shape_defect(b, "competition")
    assert "1 position" in d and "sum to 0.120" in d
    assert BF.shape_defect(BF.parse_answer(json.dumps(GOOD))[0], "competition") is None


def test_incomplete_answer_is_reasked_once_on_the_same_prefix(ledger):
    llm = _SeqLLM([ONE, json.dumps(GOOD)])
    rc = _gen(ledger, llm, _Spend(llm), n=1)
    assert llm.calls == 2 and rc["n_frozen"] == 1
    assert llm.users[1].startswith(llm.users[0])
    assert "UNFINISHED" in llm.users[1]
    assert rc["books"][0]["reasks"] == 1 and rc["books"][0]["shape_defect"] is None
    assert list((ledger / "out").glob("*.deepseek.first.json"))


def test_reask_does_not_loop(ledger):
    llm = _SeqLLM([ONE])
    rc = _gen(ledger, llm, _Spend(llm), n=1)
    assert llm.calls == 1 + C.BOOK_FACTORY_MAX_REASKS
    assert rc["n_frozen"] == 0 and rc["n_refused"] == 1
    assert rc["books"][0]["shape_defect"]


def test_reask_respects_the_cap(ledger, monkeypatch):
    monkeypatch.setattr(C, "BOOK_FACTORY_CAP_USD", 0.015)
    monkeypatch.setattr(C, "BOOK_FACTORY_EST_CALL_USD", 0.01)
    llm = _SeqLLM([ONE, json.dumps(GOOD)])
    _gen(ledger, llm, _Spend(llm, per_call=0.01), n=1)
    assert llm.calls == 1


# ─────────────── the 2026-09-25 smoke call: truncated at max_tokens ─────────
# The real call returned 20 complete positions and then ran out of tokens
# inside an 8,600-character `what_i_did_not_buy` (finish_reason=length).

def test_truncation_is_a_shape_defect():
    b, _ = BF.parse_answer(json.dumps(GOOD))
    assert BF.shape_defect(b, "competition") is None
    d = BF.shape_defect(b, "competition", finish_reason="length")
    assert d and "truncated" in d


def test_prompt_orders_positions_first_and_caps_what_i_did_not_buy():
    system, _ = BF.build_prompt({"candidates": [], "notes": {}}, kind="competition",
                                strategy=BF.STRATEGIES["competition"][0])
    assert system.index('"positions"') < system.index('"what_i_did_not_buy"')
    assert f"at most {C.BOOK_FACTORY_MAX_NOT_BOUGHT}" in system


class _TruncLLM(_SeqLLM):
    def __init__(self, answers, reasons):
        super().__init__(answers)
        self.reasons = list(reasons)

    def __call__(self, system, user, *, max_tokens):
        out = super().__call__(system, user, max_tokens=max_tokens)
        out["finish_reason"] = self.reasons[min(self.calls - 1, len(self.reasons) - 1)]
        return out


def test_truncated_answer_is_reasked(ledger):
    llm = _TruncLLM([json.dumps(GOOD), json.dumps(GOOD)], ["length", "stop"])
    rc = _gen(ledger, llm, _Spend(llm), n=1)
    assert llm.calls == 2 and rc["n_frozen"] == 1
    assert "truncated" in llm.users[1]
