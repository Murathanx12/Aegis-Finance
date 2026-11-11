"""Owner calls (ROADMAP CH-01): the frozen headline rule and the call ledger.

Everything runs on a synthetic corpus and synthetic bars under `tmp_path`.
`now` and the write time are injected; dates derive from the module's own
`INCEPTION` and from each question's own fields, never from today's clock.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from backend.services import one_event as OE
from backend.services import owner_calls as OC

REPO = Path(__file__).resolve().parents[2]
INC = date.fromisoformat(OC.INCEPTION)
HIT_TITLE = {"ai_capex": "AI spending worries investors again",
             "iran_escalation": "Iran strikes a tanker near Hormuz",
             "election_policy": "Election result reshapes Congress"}


def _midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _write_day(root: Path, day: date, n_titles: int, hits: dict | None = None,
               source: str = OC.SOURCES[0]) -> None:
    hits = hits or {}
    titles = [f"{HIT_TITLE[t]} part {i}" for t, k in hits.items() for i in range(k)]
    titles += [f"Plain filler headline number {i}" for i in range(n_titles - len(titles))]
    f = root / "news_corpus" / source / f"{day.isoformat()}.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("".join(json.dumps({"title": t}) + "\n" for t in titles), encoding="utf-8")


def _write_bars(root: Path, panel: str, sessions: list[date], closes: dict,
                drop: tuple[str, date] | None = None) -> None:
    """`closes` maps symbol -> function(i) giving the close on session i."""
    rows = [{"symbol": s, "date": d.isoformat(), "close": float(fn(i))}
            for s, fn in closes.items() for i, d in enumerate(sessions) if (s, d) != drop]
    f = root / panel / "bars.parquet"
    f.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(f)


def _falling_qqq() -> dict:
    return {"SPY": lambda i: 100.0, "QQQ": lambda i: 100.0 * 0.99 ** i}


# ───────────────────────────────── contract ─────────────────────────────────

def test_contract_hashes_match_the_committed_receipt():
    """Changing a pattern, a threshold, a source or a dated question changes the
    hash, and the receipt committed with the trial documents no longer matches."""
    receipt = json.loads((REPO / "docs" / "TRIALS" / "OWNER-CALLS-CONTRACT-v1.json")
                         .read_text(encoding="utf-8"))
    assert receipt["version"] == OC.VERSION
    for theme in OC.THEMES:
        assert receipt["themes"][theme]["contract_sha256"] == OC.contract_sha256(theme)
        assert receipt["themes"][theme]["contract"]["inception"] == OC.INCEPTION
    assert set(receipt["questions"]) == set(OC.QUESTIONS)


def test_every_question_enters_on_a_session_after_inception():
    for q in OC.QUESTIONS.values():
        assert q["theme"] in OC.THEMES and q["claim"] in OC.CLAIMS
        assert OE.session_close(date.fromisoformat(q["entry_date"])) is not None
        assert q["entry_date"] >= OC.INCEPTION
        if q["rule_window"]:
            assert OC.INCEPTION <= q["rule_window"][0] <= q["rule_window"][1] < q["entry_date"]


# ────────────────────────────── headline states ─────────────────────────────

def test_iran_needs_an_escalation_word_in_the_same_title():
    assert OC.title_hits("iran_escalation", "Iran strikes a tanker near Hormuz")
    assert not OC.title_hits("iran_escalation", "Iran football team wins")
    assert not OC.title_hits("iran_escalation", "Missile strikes reported in the region")
    assert OC.title_hits("ai_capex", "Meta capex forecast jumps")
    assert not OC.title_hits("ai_capex", "Meta launches a new headset")


def test_titles_are_counted_once_per_day_across_sources(tmp_path):
    _write_day(tmp_path, INC, 120, {"ai_capex": 3})
    f = tmp_path / "news_corpus" / OC.SOURCES[1] / f"{INC.isoformat()}.jsonl"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"title": HIT_TITLE["ai_capex"].upper() + " PART 0"}) + "\n"
                 + "not json\n" + json.dumps({"title": ""}) + "\n", encoding="utf-8")
    c = OC.daily_counts(tmp_path, INC.isoformat())
    assert c["n_titles"] == 120 and c["hits"]["ai_capex"] == 3
    assert c["sources_present"] == list(OC.SOURCES[:2])


def test_state_is_unknown_on_a_thin_day_and_needs_both_hits_and_share(tmp_path):
    days = [INC + timedelta(days=i) for i in range(4)]
    _write_day(tmp_path, days[0], OC.MIN_TITLES - 1, {"ai_capex": 10})     # thin: UNKNOWN
    _write_day(tmp_path, days[1], 200, {"ai_capex": 3})                    # 1.5%: TRIGGER
    _write_day(tmp_path, days[2], 400, {"ai_capex": 3})                    # 0.75%: share fails
    _write_day(tmp_path, days[3], 100, {"ai_capex": 2})                    # 2%: hits fail
    got = [OC.theme_state(OC.daily_counts(tmp_path, d.isoformat()), "ai_capex")["state"]
           for d in days]
    assert got == ["UNKNOWN", "TRIGGER", "QUIET", "QUIET"]


def test_a_day_counts_only_once_it_has_ended_and_a_missing_file_is_unknown(tmp_path):
    _write_day(tmp_path, INC, 200)
    _write_day(tmp_path, INC + timedelta(days=2), 200)
    now = _midnight(INC + timedelta(days=2)) + timedelta(hours=23)
    rows = OC.states(tmp_path, "ai_capex", INC.isoformat(),
                     (INC + timedelta(days=2)).isoformat(), now=now)
    assert [(r["day"], r["state"]) for r in rows] == [
        (INC.isoformat(), "QUIET"), ((INC + timedelta(days=1)).isoformat(), "UNKNOWN")]


# ───────────────────────────────── theme events ─────────────────────────────

def _event_corpus(root: Path) -> None:
    _write_day(root, INC - timedelta(days=5), 200, {"ai_capex": 4})        # seen before freeze
    _write_day(root, INC, 200, {"ai_capex": 4})                            # forward event 1
    _write_day(root, INC + timedelta(days=1), 200, {"ai_capex": 4})        # absorbed by event 1
    _write_day(root, INC + timedelta(days=2), 200)                         # quiet
    _write_day(root, INC + timedelta(days=20), 200, {"ai_capex": 4})       # forward event 2


def test_forward_events_never_overlap_and_seen_triggers_are_never_forward(tmp_path):
    _event_corpus(tmp_path)
    sessions = OC.sessions_from(INC - timedelta(days=30), 30)              # ends before event 2 exits
    _write_bars(tmp_path, "prices_2025_26", sessions, _falling_qqq())
    now = _midnight(INC + timedelta(days=22)) + timedelta(hours=1)
    res = OC.theme_events(tmp_path, "ai_capex", now=now)
    assert res["contract_sha256"] == OC.contract_sha256("ai_capex")
    c = res["counts"]
    assert c["forward_days"] == 22 and c["forward_trigger"] == 3 and c["forward_absorbed"] == 1
    assert c["forward_quiet"] == 1 and c["forward_unknown"] == 18
    seen = [e for e in res["events"] if e["evidence"] == "SEEN_BEFORE_FREEZE"]
    fwd = [e for e in res["events"] if e["evidence"] == "FORWARD"]
    assert [e["trigger_day"] for e in seen] == [(INC - timedelta(days=5)).isoformat()]
    assert [e["trigger_day"] for e in fwd] == [INC.isoformat(),
                                              (INC + timedelta(days=20)).isoformat()]
    entry, exit_ = OC.event_window(INC.isoformat(), 5)
    assert entry == OC.sessions_from(INC + timedelta(days=1), 1)[0] and entry > INC
    assert fwd[0]["entry_date"] == str(entry) and fwd[0]["exit_date"] == str(exit_)
    assert fwd[0]["status"] == "GRADED" and fwd[0]["claim_true"] is True
    assert fwd[0]["outcome"] == pytest.approx(0.99 ** 5 - 1, abs=1e-6)
    assert fwd[1]["status"] == "PENDING" and "outcome" not in fwd[1]


def test_a_missing_close_inside_the_bars_is_cannot_grade_not_pending(tmp_path):
    _event_corpus(tmp_path)
    sessions = OC.sessions_from(INC - timedelta(days=30), 30)
    _, exit_ = OC.event_window(INC.isoformat(), 5)
    _write_bars(tmp_path, "prices_2025_26", sessions, _falling_qqq(), drop=("QQQ", exit_))
    now = _midnight(INC + timedelta(days=22))
    fwd = [e for e in OC.theme_events(tmp_path, "ai_capex", now=now)["events"]
           if e["evidence"] == "FORWARD"]
    assert fwd[0]["status"] == "CANNOT_GRADE"


# ───────────────────────────────── state ledger ─────────────────────────────

def _forward(root: Path, now: datetime) -> list[dict]:
    return [e for e in OC.theme_events(root, "ai_capex", now=now)["events"]
            if e["evidence"] == "FORWARD"]


def test_a_forward_day_is_pinned_once_and_the_pinned_state_stands(tmp_path):
    """A day file rewritten after its day ended must not rewrite the record."""
    _event_corpus(tmp_path)
    out = tmp_path / "owner_calls"
    one = OC.record_states(out, data_root=tmp_path, now=_midnight(INC + timedelta(days=1)))
    assert one["recorded"] == [INC.isoformat()] and one["drift_days"] == []
    _write_day(tmp_path, INC, 200)                                         # the trigger day, rewritten quiet
    now = _midnight(INC + timedelta(days=3))
    two = OC.record_states(out, data_root=tmp_path, now=now)
    assert two["recorded"] == [(INC + timedelta(days=i)).isoformat() for i in (1, 2)]
    assert two["drift_days"] == [INC.isoformat()] == two["state_changed_days"]
    assert two["rows"] == 3 and two["chain"]["ok"]
    assert OC.record_states(out, data_root=tmp_path, now=now)["recorded"] == []
    fwd = _forward(tmp_path, now)
    assert [e["trigger_day"] for e in fwd] == [INC.isoformat()]            # the pinned TRIGGER stands
    assert fwd[0]["counts_at_read"] is True
    assert fwd[0]["pinned_utc"][:10] == (INC + timedelta(days=1)).isoformat()
    rows = [json.loads(x) for x in (out / "states.jsonl").read_text(encoding="utf-8").splitlines()]
    rows[0]["states"]["ai_capex"]["state"] = "QUIET"                       # an edited row breaks the chain
    (out / "states.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows),
                                      encoding="utf-8")
    assert OC.verify_chain(out / "states.jsonl") == {"rows": 3, "ok": False, "broken_at": 1}


def test_an_unpinned_or_late_pinned_event_is_listed_but_never_counted(tmp_path):
    _event_corpus(tmp_path)
    now = _midnight(INC + timedelta(days=21))
    res = OC.theme_events(tmp_path, "ai_capex", now=now)
    fwd = [e for e in res["events"] if e["evidence"] == "FORWARD"]
    assert [(e["pinned_utc"], e["counts_at_read"]) for e in fwd] == [(None, False)] * 2
    assert res["counts"]["forward_events_not_counted"] == 2
    got = OC.record_states(tmp_path / "owner_calls", data_root=tmp_path, now=now)
    assert len(got["recorded"]) == 21
    fwd = _forward(tmp_path, now)
    # event 1 was pinned three weeks after its entry; event 2 on the day it enters
    assert [e["counts_at_read"] for e in fwd] == [False, True]
    assert all(e["pinned_utc"] for e in fwd)


def test_rule_answer_is_yes_unknown_or_abstain(tmp_path):
    q = OC.QUESTIONS["A-NVDA-CLUSTER"]
    first, last = (date.fromisoformat(x) for x in q["rule_window"])
    n = (last - first).days + 1
    after = _midnight(last + timedelta(days=1))
    for i in range(n):
        _write_day(tmp_path, first + timedelta(days=i), 200)
    assert OC.rule_answer(tmp_path, "A-NVDA-CLUSTER", now=after)["answer"] == "ABSTAIN"
    assert OC.rule_answer(tmp_path, "A-NVDA-CLUSTER",
                          now=after - timedelta(days=1))["answer"] == "UNKNOWN"   # a day not ended
    _write_day(tmp_path, first, OC.MIN_TITLES - 1)
    assert OC.rule_answer(tmp_path, "A-NVDA-CLUSTER", now=after)["answer"] == "UNKNOWN"
    _write_day(tmp_path, last, 200, {"ai_capex": 4})
    assert OC.rule_answer(tmp_path, "A-NVDA-CLUSTER", now=after)["answer"] == "YES"
    assert OC.rule_answer(tmp_path, "B-ENERGY-42", now=after)["answer"] == "NO_RULE"


# ─────────────────────────────────── the twin ───────────────────────────────

def test_base_rate_counts_non_overlapping_blocks_before_the_cut(tmp_path):
    sessions = OC.sessions_from(date(2020, 1, 2), 41)
    # QQQ loses 1% across every even 5-session block and gains 1% across every odd one
    level = lambda i: 100.0 * (0.99 if (i // 5) % 2 == 0 and i % 5 else 1.0)  # noqa: E731
    _write_bars(tmp_path, "prices_deep", sessions,
                {"SPY": lambda i: 100.0, "QQQ": lambda i: 100.0 + (i // 5) * (-1) ** (i // 5)})
    px = OC.load_px(tmp_path, ["QQQ", "SPY"], deep=True)
    full = OC.base_rate(px, ["QQQ"], "SPY", 5, "below", before=date(2099, 1, 1))
    assert full["n_blocks"] == 8 and full["by_year"] == {"2020": full["p"]}
    assert full["p"] == pytest.approx(sum(1 for b in range(8) if (b + 1) * (-1) ** (b + 1)
                                          < b * (-1) ** b) / 8, abs=1e-4)
    cut = OC.base_rate(px, ["QQQ"], "SPY", 5, "below", before=sessions[21])
    assert cut["n_blocks"] == 4 and cut["bars_through"] == str(sessions[20])
    assert OC.base_rate(px, ["QQQ"], "XOM", 5, "below", before=date(2099, 1, 1)) is None
    assert level(0) == 100.0


def test_abs_claim_and_basket_excess(tmp_path):
    sessions = OC.sessions_from(date(2020, 1, 2), 6)
    _write_bars(tmp_path, "prices_2025_26", sessions,
                {"SPY": lambda i: 100 + i, "XOM": lambda i: 100 + 2 * i,
                 "CVX": lambda i: 100.0, "COP": lambda i: 100 - i})
    px = OC.load_px(tmp_path, ["XOM", "CVX", "COP", "SPY"])
    x = OC.excess(px, ["XOM", "CVX", "COP"], "SPY", sessions[0], sessions[5])
    assert x == pytest.approx((0.10 + 0.0 - 0.05) / 3 - 0.05)
    assert OC.excess(px, ["SPY"], None, sessions[0], sessions[5]) == pytest.approx(0.05)
    assert OC.satisfied(-0.03, "abs_at_least", 0.02) and not OC.satisfied(0.01, "abs_at_least", 0.02)
    assert OC.satisfied(-0.01, "below") and OC.satisfied(0.01, "above")


# ───────────────────────────────── call ledger ──────────────────────────────

@pytest.fixture()
def priced(tmp_path):
    """A data root whose two panels price every question through its exit."""
    sessions = OC.sessions_from(INC - timedelta(days=200), 200)
    closes = {"SPY": lambda i: 100.0 + i, "QQQ": lambda i: 100.0 * 0.999 ** i,
              "XOM": lambda i: 50.0 + i, "CVX": lambda i: 80.0, "COP": lambda i: 60.0}
    _write_bars(tmp_path, "prices_deep", sessions, closes)
    _write_bars(tmp_path, "prices_2025_26", sessions, closes)
    return tmp_path


def _before_close(question: str) -> datetime:
    return OE.session_close(date.fromisoformat(OC.QUESTIONS[question]["entry_date"])) \
        - timedelta(hours=1)


def test_a_call_is_chained_twinned_and_never_revised(priced, tmp_path):
    out = tmp_path / "ledger"
    w = _before_close("B-ENERGY-42")
    a = OC.log_call(out, data_root=priced, who="owner", probability=0.6,
                    question="B-ENERGY-42", written_at=w)
    b = OC.log_call(out, data_root=priced, who="rule", probability=None,
                    question="B-ENERGY-42", written_at=w)
    assert a["prev"] == "GENESIS" and b["prev"] == a["seal"]
    assert a["twin"]["n_blocks"] >= 2 and 0.0 <= a["twin"]["p"] <= 1.0
    assert a["twin"]["bars_through"] < w.date().isoformat()
    assert a["licence"] == "PRODUCT_EXPERIMENT" and a["skill_claim"] == "none"
    assert OC.verify_chain(out / "calls.jsonl") == {"rows": 2, "ok": True, "broken_at": None}
    with pytest.raises(OC.CallRefused) as e:
        OC.log_call(out, data_root=priced, who="owner", probability=0.4,
                    question="B-ENERGY-42", written_at=w)
    assert e.value.code == "ALREADY_ANSWERED"
    # an edited probability breaks the chain at that row
    path = out / "calls.jsonl"
    path.write_text(path.read_text(encoding="utf-8").replace('"probability": 0.6',
                                                             '"probability": 0.9'), encoding="utf-8")
    assert OC.verify_chain(path)["broken_at"] == 1


@pytest.mark.parametrize("kwargs, code", [
    ({"question": "A-NVDA-CLUSTER", "probability": 0.5, "late": True}, "WINDOW_STARTED"),
    ({"question": "A-NVDA-CLUSTER", "probability": 1.0}, "BAD_PROBABILITY"),
    ({"question": "NOPE", "probability": 0.5}, "UNKNOWN_QUESTION"),
    ({"text": "free call", "long": ["ZZZZ"], "short": "SPY", "horizon": 5, "claim": "below",
      "probability": 0.5}, "NO_BARS"),
    ({"text": "free call", "long": ["QQQ"], "horizon": 5, "claim": "sideways",
      "probability": 0.5}, "INCOMPLETE"),
    ({"text": "free call", "long": ["QQQ"], "short": "SPY", "horizon": 5, "claim": "below",
      "probability": 0.5, "entry_date": "2026-11-14"}, "NOT_A_SESSION"),          # a Saturday
])
def test_refusals_write_nothing(priced, tmp_path, kwargs, code):
    kwargs = dict(kwargs)
    w = _before_close("A-NVDA-CLUSTER") + (timedelta(hours=2) if kwargs.pop("late", False)
                                           else timedelta(0))
    with pytest.raises(OC.CallRefused) as e:
        OC.log_call(tmp_path / "ledger", data_root=priced, who="owner", written_at=w, **kwargs)
    assert e.value.code == code
    assert not (tmp_path / "ledger" / "calls.jsonl").exists()


def test_grading_waits_for_the_bars_then_scores_against_the_twin(priced, tmp_path):
    out = tmp_path / "ledger"
    q = OC.QUESTIONS["A-NVDA-CLUSTER"]
    row = OC.log_call(out, data_root=priced, who="owner", probability=0.7,
                      question="A-NVDA-CLUSTER", written_at=_before_close("A-NVDA-CLUSTER"))
    entry = date.fromisoformat(q["entry_date"])
    window = OC.sessions_from(entry, q["horizon"] + 1)
    history = OC.sessions_from(INC - timedelta(days=200), 200)
    history = [d for d in history if d < entry]
    closes = {"SPY": lambda i: 100.0, "QQQ": lambda i: 100.0 * 0.999 ** i}
    now = _midnight(window[-1] + timedelta(days=1))

    _write_bars(priced, "prices_2025_26", history + window[:-1], closes)        # exit bar missing
    res = OC.grade_calls(out, data_root=priced, now=now)
    assert res["counts"]["pending"] == 1 and not (out / "grades.jsonl").exists()

    _write_bars(priced, "prices_2025_26", history + window, closes)
    res = OC.grade_calls(out, data_root=priced, now=now)
    g = res["new_grades"][0]
    assert res["counts"]["graded"] == 1 and g["call_id"] == row["call_id"]
    assert g["entry_date"] == str(window[0]) and g["exit_date"] == str(window[-1])
    assert g["claim_true"] is True and g["brier"] == pytest.approx(0.09)
    assert g["twin_brier"] == pytest.approx((row["twin"]["p"] - 1) ** 2, abs=1e-6)
    assert OC.grade_calls(out, data_root=priced, now=now)["counts"]["already"] == 1


def test_a_tampered_or_late_row_is_never_graded(priced, tmp_path):
    out = tmp_path / "ledger"
    OC.log_call(out, data_root=priced, who="owner", probability=0.7,
                question="A-NVDA-CLUSTER", written_at=_before_close("A-NVDA-CLUSTER"))
    path = out / "calls.jsonl"
    row = json.loads(path.read_text(encoding="utf-8"))
    late = dict(row, who="late", prev=row["seal"],
                written_utc=(_before_close("A-NVDA-CLUSTER") + timedelta(hours=3)).isoformat())
    late["seal"] = OC._seal(late)                                          # sealed, but after the close
    edited = dict(row, probability=0.99)                                   # seal no longer matches
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in (edited, late)),
                    encoding="utf-8")
    res = OC.grade_calls(out, data_root=priced, now=_midnight(INC + timedelta(days=400)))
    assert res["counts"]["seal_mismatch"] == 1 and res["counts"]["frozen_late"] == 1
    assert res["counts"]["graded"] == 0 and res["chain"]["ok"] is False


# ───────────────────────────────────── CLI ──────────────────────────────────

def test_cli_refusals_exit_two_and_status_reads_only(priced, tmp_path, capsys):
    from scripts import owner_calls as CLI
    assert CLI.main(["status", "--data-root", str(tmp_path / "nowhere")]) == 2
    _write_day(priced, INC, 200, {"ai_capex": 4})
    before = sorted(p.name for p in priced.rglob("*"))
    assert CLI.main(["status", "--data-root", str(priced), "--days", "3"]) == 0
    assert CLI.main(["contract", "--data-root", str(priced)]) == 0
    assert sorted(p.name for p in priced.rglob("*")) == before            # nothing written
    assert CLI.main(["contract", "--data-root", str(tmp_path / "nowhere")]) == 2
    assert CLI.main(["log", "--who", "owner", "--data-root", str(priced), "--out",
                     str(tmp_path / "l"), "--long", "ZZZZ", "--horizon", "5", "--claim", "below",
                     "--text", "x"]) == 2
    assert "REFUSED: NO_BARS" in capsys.readouterr().out
    assert CLI.main(["list", "--out", str(tmp_path / "l")]) == 0
