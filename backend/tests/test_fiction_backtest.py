"""scripts/fiction_backtest.py (AMNESIA-2, 2026-09-28): the fiction layer,
the PIT packet, the strict parse, the file arm's confinement and the cap.

Synthetic data only; every date derives from today; no network, no LLM.
"""

from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd
import pytest

from scripts import fiction_backtest as F

TODAY = pd.Timestamp.today().normalize()
T = str((TODAY - pd.Timedelta(days=30)).date())          # the decision date
REAL_TICKER = "ZRBX"
REAL_NAME = "ZORBLAX QUANTUM HOLDINGS INC"
ALIASES = ["ZORBLAX QUANTUM", "Zorblax", "ZRBX"]
Y0, Y1 = pd.Timestamp(T).year, pd.Timestamp(T).year - 1


def _d(days_before: int) -> str:
    return str((pd.Timestamp(T) - pd.Timedelta(days=days_before)).date())


def _packet() -> dict:
    rng = np.random.default_rng(1)
    closes = 50 * np.exp(np.cumsum(rng.normal(0, 0.02, 300)))
    vols = rng.uniform(1e6, 2e6, 300)
    pb = F.price_block(closes, vols)
    return {
        "symbol": REAL_TICKER, "decision_date": T, "company": REAL_NAME,
        "sector": "information technology", "size_bucket": "mid cap", "price": pb,
        "fundamentals": {"filed": _d(40), "revenue_q": 1.2e9, "net_income_q": 1.5e8,
                         "operating_income_q": 2.0e8, "revenue_yoy_pct": 12.0,
                         "op_margin_pct": 16.7, "net_margin_pct": 12.5, "revenue_ttm": 4.5e9,
                         "assets": 9e9, "cash": 1e9, "debt": 2e9, "equity": 5e9, "shares": 1e8},
        "analyst": {"n_90d": 3, "upgrades_90d": 1, "downgrades_90d": 0, "target_raises_90d": 2,
                    "target_cuts_90d": 0, "median_target_vs_price_pct": 10.0,
                    "actions": [{"date": _d(5), "firm": "Goldman Sachs", "action": "up",
                                 "from": "Neutral", "to": "Buy", "target_change_pct": 8.0,
                                 "target": 60.0}]},
        "events": [{"date": _d(3), "event_type": "guidance_raise", "direction": "positive"}],
        "headlines": [
            {"date": _d(2), "title": f"Zorblax (NASDAQ: {REAL_TICKER}) jumps after {Y1} guidance",
             "snippet": f"Zorblax Quantum shares closed at $52.10; revenue of $1.2 billion in {Y0}; "
                        f"${REAL_TICKER} is up"},
            {"date": _d(6), "title": f"Analysts see ZRBX margin expanding into {Y0}",
             "snippet": ""},
        ],
        "past_reactions": [(_d(100), 4.2), (_d(190), -3.1)],
    }


def _render(level: str):
    pk = _packet()
    m = F.case_mapping("clean|ZRBX|" + T, level, frozenset({"ZRBX", "AAPL"}), 1234)
    if level == "A2_MASKED":
        m["k_price"] = 100.0 / pk["price"]["last_close"]
    text, dropped = F.render_case(pk, level, m, ALIASES, "abcdef012345")
    return pk, m, text, dropped


# ── the fiction transform ───────────────────────────────────────────────────
@pytest.mark.parametrize("level", ["A2_MASKED", "A3_SYNTHETIC"])
def test_fiction_removes_every_real_name_ticker_and_year(level):
    pk, m, text, _ = _render(level)
    assert F.X2.leaks(text, ALIASES) == []
    for tok in (REAL_TICKER, "Zorblax", "ZORBLAX", "Goldman", T):
        assert tok not in text, tok
    assert not re.search(r"\b(?:19|20)\d{2}\b", text), re.findall(r"\b(?:19|20)\d{2}\b", text)
    assert "Goldman" not in text and "Broker 1" in text
    # the house scanner agrees (a leak would refuse the case, not repair it)
    assert F.scan_case(text, level, pk, ALIASES) == []


def test_named_level_keeps_the_real_identity():
    _, _, text, _ = _render("A0_NAMED")
    assert REAL_TICKER in text and T in text


def test_fiction_preserves_every_ratio_percentage_and_rank():
    pk, m, a3, _ = _render("A3_SYNTHETIC")
    _, _, a0, _ = _render("A0_NAMED")
    _, _, a2, _ = _render("A2_MASKED")
    # every percentage line is identical at all three levels
    pct = lambda s: [ln for ln in s.splitlines() if "return 1d" in ln]      # noqa: E731
    assert pct(a0) == pct(a2) == pct(a3)
    ratio = lambda s: [ln for ln in s.splitlines() if "operating margin" in ln]  # noqa: E731
    assert ratio(a0) == ratio(a2) == ratio(a3)
    # absolute levels are rescaled by ONE factor per kind: price ratios survive
    nums = lambda s: [float(x.replace(",", "")) for x in              # noqa: E731
                      re.findall(r"\$([\d,]+\.\d+)", [ln for ln in s.splitlines() if "last close" in ln][0])]
    c0, h0, l0 = nums(a0)[:3]
    c3, h3, l3 = nums(a3)[:3]
    assert abs(c3 / h3 - c0 / h0) < 1e-3 and abs(l3 / c3 - l0 / c0) < 1e-3
    assert (np.argsort([c0, h0, l0]) == np.argsort([c3, h3, l3])).all()
    assert abs(c3 / c0 - m["k_price"]) / m["k_price"] < 1e-3
    # A2 carries no absolute dollar level in its structured blocks
    assert "rebased to 100.00" in a2 and "market value $" not in a2
    # money in TEXT is rescaled with the same factors (size amounts by k_size)
    snippet = [ln for ln in a3.splitlines() if "billion" in ln][0]
    got = float(re.search(r"\$([\d,.]+) billion", snippet).group(1).replace(",", ""))
    assert abs(got - 1.2 * m["k_size"]) < 0.01


def test_mapping_round_trips():
    rng = np.random.default_rng(7)
    for level in ("A0_NAMED", "A2_MASKED", "A3_SYNTHETIC"):
        m = F.case_mapping("k|" + T, level, frozenset(), 99)
        for d in rng.integers(0, 700, 40):
            real = _d(int(d))
            assert F.unfmt_date(F.fmt_date(real, level, T, m), level, T, m) == real
    m = F.case_mapping("k|" + T, "A3_SYNTHETIC", frozenset(), 99)
    for v in (0.37, 52.1, 4.5e9):
        for kind in ("price", "size"):
            assert F.scale_money(F.scale_money(v, kind, m), kind, m, inverse=True) == pytest.approx(v)
    # a fabricated ticker never spells a real one
    name, tic, year = F.fake_identity("x", frozenset())
    _, tic2, _ = F.fake_identity("x", frozenset({tic}))
    assert tic2 != tic and tic2.startswith(tic) and year >= 2110


# ── point in time ───────────────────────────────────────────────────────────
def test_packet_never_contains_an_item_dated_on_or_after_the_decision_date():
    t = pd.Timestamp(T)
    cut = F.et_cut(t)
    pubs = [cut - pd.Timedelta(hours=h) for h in (30, 5, 1)] + [cut, cut + pd.Timedelta(hours=3),
                                                                  cut + pd.Timedelta(days=2)]
    news = pd.DataFrame({"pub": pubs, "title": [f"h{i}" for i in range(6)], "body": ["b"] * 6})
    heads = F.headlines_pit(news, t)
    assert [h["title"] for h in heads] == ["h2", "h1", "h0"]
    ev = pd.DataFrame({"pub": pubs, "event_type": ["x"] * 6, "direction": ["up"] * 6})
    evs = F.events_pit(ev, t)
    facts = pd.DataFrame({"fact": ["revenue", "revenue", "shares"],
                          "filed": pd.to_datetime([_d(50), T, _d(-3)]),
                          "end": pd.to_datetime([_d(80), _d(10), _d(10)]),
                          "period_days": [91, 91, np.nan], "val": [1e9, 2e9, 5e7]})
    fb = F.fundamentals_block(facts, t)
    assert fb["revenue_q"] == 1e9 and "shares" not in fb
    revs = pd.DataFrame({"event_date": pd.to_datetime([_d(10), T, _d(-1)]),
                         "firm": ["A", "B", "C"], "action": ["up", "down", "up"],
                         "from_grade": ["", "", ""], "to_grade": ["", "", ""],
                         "target_action": ["Raises"] * 3, "target_change": [0.1] * 3,
                         "current_target": [10.0] * 3})
    ab = F.analyst_block(revs, t, 10.0)
    assert [a["firm"] for a in ab["actions"]] == ["A"]
    dates = pd.bdate_range(end=t + pd.Timedelta(days=20), periods=400).values
    closes = np.linspace(10, 20, len(dates))
    pr = F.past_reactions(dates, closes, [pd.Timestamp(_d(120)), pd.Timestamp(_d(3)), t], t)
    packet = {"decision_date": T, "headlines": heads, "events": evs, "analyst": ab,
              "fundamentals": fb, "past_reactions": pr}
    assert F.assert_pit(packet) == []
    assert len(pr) == 1                   # the reaction whose window ends after t is excluded
    packet["headlines"].append({"date": T, "title": "same day"})
    assert F.assert_pit(packet)           # and the guard sees a violation when one exists


# ── strict parse: refused and counted, never repaired ───────────────────────
GOOD = {"scenarios": [{"label": "a", "prob": 0.5, "ret_low_pct": 1, "ret_high_pct": 6},
                      {"label": "b", "prob": 0.3, "ret_low_pct": -2, "ret_high_pct": 1},
                      {"label": "c", "prob": 0.2, "ret_low_pct": -9, "ret_high_pct": -2}],
        "p_beat_median_5d": 0.55, "p_beat_median_21d": 0.5, "central_5d_pct": 0.5,
        "low80_5d_pct": -6, "high80_5d_pct": 7, "change_mind": "a miss on margins",
        "features": {"novelty": 0.2, "emotional_intensity": 0.4,
                     "management_confidence": 0.5, "crowdedness": 0.6}}


def test_parse_accepts_the_schema_and_a_json_fence():
    assert F.parse_forecast(json.dumps(GOOD))[1] is None
    assert F.parse_forecast("```json\n" + json.dumps(GOOD) + "\n```")[1] is None


@pytest.mark.parametrize("mut,reason", [
    (lambda g: "Sure! " + json.dumps(g), "NOT_A_SINGLE_JSON_OBJECT"),
    (lambda g: json.dumps({**g, "scenarios": g["scenarios"][:2]}), "SCENARIOS_NOT_THREE"),
    (lambda g: json.dumps({**g, "scenarios": [{**s, "prob": 0.5} for s in g["scenarios"]]}),
     "PROBS_DO_NOT_SUM_TO_1"),
    (lambda g: json.dumps({**g, "p_beat_median_5d": 1.4}), "BAD_P_BEAT_MEDIAN_5D"),
    (lambda g: json.dumps({**g, "low80_5d_pct": 9}), "BAD_CENTRAL_OR_RANGE"),
    (lambda g: json.dumps({**g, "features": {**g["features"], "novelty": "high"}}),
     "BAD_FEATURE_NOVELTY"),
    (lambda g: "", "EMPTY"),
    (lambda g: json.dumps(g)[:-5], "NOT_A_SINGLE_JSON_OBJECT"),
])
def test_unparseable_reply_is_refused(mut, reason):
    parsed, why = F.parse_forecast(mut(GOOD))
    assert parsed is None and why == reason


class _StubArm(F.Arm):
    name, model_id, paid = "stub", "stub-model", False

    def __init__(self, text):
        self.text = text

    def answer(self, system, user, case_id):
        return {"text": self.text, "ok": True, "status": "OK", "served_model": "stub-served",
                "cost_usd": 0.0}


def test_refused_reply_is_counted_as_a_frozen_row(tmp_path):
    c = {"case_id": "abcdef012345", "canary_id": "0123456789ab", "level": "A3_SYNTHETIC",
         "part": "clean", "text": "case", "canary_text": "canary"}
    rows, raw = tmp_path / "rows.jsonl", tmp_path / "raw.jsonl"
    F.one_call(_StubArm("I think it goes up."), None, c, "forecast", rows, raw, "r")
    F.one_call(_StubArm(json.dumps(GOOD)), None, c, "forecast", rows, raw, "r")
    got = [json.loads(ln) for ln in rows.read_text().splitlines()]
    assert [g["parsed_ok"] for g in got] == [False, True]
    assert got[0]["refusal"] == "NOT_A_SINGLE_JSON_OBJECT" and got[0]["answer"] is None
    assert got[1]["model_served"] == "stub-served" and got[1]["level"] == "A3_SYNTHETIC"


# ── the file arm reads nothing outside its answers folder ───────────────────
def test_file_arm_is_confined_to_its_answers_folder(tmp_path):
    arm = F.FileArm(tmp_path, "opus", "claude-x")
    (tmp_path / "answers" / "opus").mkdir(parents=True)
    (tmp_path / "answers" / "opus" / "abcdef012345.txt").write_text("{}", encoding="utf-8")
    (tmp_path / "sealed").mkdir()
    (tmp_path / "sealed" / "abcdef012345.txt").write_text("SECRET", encoding="utf-8")
    assert arm.answer("s", "u", "abcdef012345")["text"] == "{}"
    for bad in ("../../sealed/abcdef012345", "..\\sealed\\x", "/etc/passwd",
                "C:/Windows/win.ini", "ABCDEF012345", "abc", ""):
        with pytest.raises(ValueError):
            arm.path_for(bad)
    assert arm.answer("s", "u", "0123456789ab")["status"] == "NO_ANSWER_FILE"
    with pytest.raises(ValueError):
        F.FileArm(tmp_path, "../x")


def test_local_arm_never_starts_a_server(monkeypatch):
    arm = F.LocalArm(allowed=False)
    r = arm.answer("s", "u", "abcdef012345")
    assert r["status"] == "LOCAL_UNAVAILABLE" and not r["ok"]


# ── the cap ─────────────────────────────────────────────────────────────────
def test_cap_refuses(tmp_path):
    b = F.Budget(0.01, tmp_path / "calls.jsonl")
    e = b.reserve()
    b.settle(e, {"ok": True, "cost_usd": 0.004})
    with pytest.raises(F.CapRefused):
        b.reserve()             # 0.004 spent + next estimated at 2 x 0.004 > 0.01
    # prior spend on disk binds a new process
    b2 = F.Budget(0.01, tmp_path / "calls.jsonl")
    assert b2.spent == pytest.approx(0.004)
    with pytest.raises(F.CapRefused):
        b2.reserve()
    # an unpriced successful call makes the cap refuse everything after it
    b3 = F.Budget(100.0, None)
    e = b3.reserve()
    b3.settle(e, {"ok": True, "cost_usd": None})
    with pytest.raises(F.CapRefused):
        b3.reserve()


def test_grading_on_synthetic_rows_is_alive():
    rng = np.random.default_rng(3)
    n = 200
    weeks = [f"w{i % 8}" for i in range(n)]
    r5 = rng.normal(0, 6, n)
    rows = pd.DataFrame({
        "week": weeks, "r5": r5, "beat5": (r5 > 0).astype(int), "beat21": (r5 > 0).astype(int),
        "p_beat_median_5d": np.where(r5 > 0, 0.7, 0.3), "p_beat_median_21d": 0.5,
        "mom_call": rng.integers(0, 2, n), "sd_prior_vol": 6.0, "sd_prior_earn": 6.0,
        "low80_5d_pct": -7.7, "high80_5d_pct": 7.7, "central_5d_pct": 0.0,
        "scenarios": [GOOD["scenarios"]] * n,
        "features": [{"novelty": abs(x) / 20, "emotional_intensity": 0.5,
                      "management_confidence": 0.5, "crowdedness": 0.5} for x in r5]})
    cell = F.grade_cell(rows)
    assert cell["dir5"]["hit"] == 1.0 and F.verdicts(cell)["direction"] == "ALPHA_DETECTED"
    assert cell["features"]["novelty"]["pooled_partial_spearman_vs_abs_r5_ctrl_vol"] > 0.9
