"""J2_missed_opportunity — the screen, the PIT precursor check, the paired
read, and the cap.

NO NETWORK, NO PROVIDER, NO `backend/data` WRITE. Every fixture is built in
`tmp_path`; the readers are functions passed in; the ledger is a file in
`tmp_path`. The paid path is exercised by MOCK and the run-level refusals are
shown to have teeth rather than being vacuously true.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import night_missed_opportunity as J2          # noqa: E402

pd = pytest.importorskip("pandas")


# ══════════════════════════════════════════════════════ fixtures

def _sessions(n: int, *, start: str = "2026-01-05") -> list:
    """`n` weekday sessions. DERIVED, never a literal calendar: a fixture that
    encodes a moment fails the day after that moment passes."""
    out, d = [], pd.Timestamp(start)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += pd.Timedelta(days=1)
    return out


def _bars(spec: dict, *, n: int = 30, dollar_vol: float = 50e6):
    """`{symbol: [close, ...]}` -> the bar frame `load_bars()` returns."""
    days = _sessions(n)
    rows = []
    for sym, closes in spec.items():
        assert len(closes) == n, f"{sym}: {len(closes)} closes for {n} sessions"
        for d, c in zip(days, closes):
            rows.append({"symbol": sym, "date": d, "open": c, "high": c,
                         "low": c, "close": c,
                         "volume": max(1.0, dollar_vol / max(c, 0.01)),
                         "vwap": c, "trades": 1})
    return pd.DataFrame(rows)


def _flat(n: int, start: float = 100.0) -> list:
    return [start] * n


def _one_jump(n: int, at: int, pct: float, start: float = 100.0) -> list:
    """Flat, then one session's jump, then flat again at the new level."""
    out, px = [], start
    for i in range(n):
        if i == at:
            px *= (1.0 + pct)
        out.append(px)
    return out


# ══════════════════════════════════════════════════════ 1. the screen

def test_the_screen_ranks_by_the_best_subwindow_and_names_the_benchmark():
    n = 30
    bars = _bars({"SPY": _flat(n), "BIG": _one_jump(n, 20, 0.40),
                  "SMALL": _one_jump(n, 20, 0.05), "QUIET": _flat(n)}, n=n)
    out = J2.rank_missed(bars, window=21, top_k=3, sub=5, floor_usd=0.0)
    tickers = [m["ticker"] for m in out["moves"]]
    assert tickers[0] == "BIG" and tickers[1] == "SMALL"
    assert out["screen"]["benchmark"] == "SPY"
    assert out["screen"]["subwindow_sessions"] == 5
    assert out["moves"][0]["direction"] == "UP"
    assert out["moves"][0]["abs_excess_pct"] > out["moves"][1]["abs_excess_pct"]


def test_a_panel_with_no_benchmark_refuses_rather_than_reporting_raw_returns():
    n = 30
    bars = _bars({"BIG": _one_jump(n, 20, 0.40)}, n=n)
    with pytest.raises(ValueError, match="no SPY rows"):
        J2.rank_missed(bars, window=21, top_k=3, sub=5, floor_usd=0.0)


def test_the_dollar_volume_floor_removes_the_illiquid_tape_and_is_printed():
    n = 30
    liquid = _bars({"SPY": _flat(n), "BIG": _one_jump(n, 20, 0.40)}, n=n,
                   dollar_vol=50e6)
    penny = _bars({"PENNY": _one_jump(n, 20, 3.00)}, n=n, dollar_vol=1e4)
    bars = pd.concat([liquid, penny], ignore_index=True)

    no_floor = J2.rank_missed(bars, window=21, top_k=5, sub=5, floor_usd=0.0)
    assert no_floor["moves"][0]["ticker"] == "PENNY", (
        "without a floor the sub-dollar tape wins — that is why there is one")

    with_floor = J2.rank_missed(bars, window=21, top_k=5, sub=5,
                                floor_usd=5_000_000.0)
    assert [m["ticker"] for m in with_floor["moves"]] == ["BIG"]
    assert with_floor["screen"]["dollar_vol_floor"] == 5_000_000.0
    assert with_floor["screen"]["n_over_the_floor"] == 1


def test_the_window_start_is_the_first_session_of_the_subwindow_not_the_last():
    """THE CORPSE OF THE FIRST SMOKE RUN.

    `roll` is sliced at `iloc[sub-1:]`, so row `i` sums `ex` rows `i..i+sub-1`.
    The first version took `dates[max(0, i - sub + 1)]`, which for `i = 0`
    clamps to `dates[0]` — the window's END — and made the move look like a
    one-session event. It is not cosmetic: `window_start` is what the ENTIRE
    PIT precursor check is anchored on, so the bug let the check read rows
    from INSIDE the move and call them precursors.
    """
    n = 30
    bars = _bars({"SPY": _flat(n), "EARLY": _one_jump(n, 10, 0.40)}, n=n)
    out = J2.rank_missed(bars, window=21, top_k=1, sub=5, floor_usd=0.0)
    m = out["moves"][0]
    assert m["window_start"] < m["window_end"], (
        f"a {5}-session window that starts and ends on the same day is the "
        f"clamping bug: {m}")
    span = (pd.Timestamp(m["window_end"]) - pd.Timestamp(m["window_start"])).days
    assert 4 <= span <= 8, f"five sessions is 4-8 calendar days, got {span}"


# ══════════════════════════════════════════════════════ 2. what AEGIS did

def _contract(tmp_path: Path, day: str, rows: list[dict]) -> Path:
    root = tmp_path / "decisions"
    root.mkdir(exist_ok=True)
    (root / f"{day}.json").write_text(
        json.dumps({"date": day, "rows": rows}), encoding="utf-8")
    return root


def test_a_name_no_contract_mentions_is_not_in_the_universe_and_says_so(tmp_path):
    day = _sessions(1)[0].date().isoformat()
    root = _contract(tmp_path, day, [{"ticker": "AAA", "verdict": "BUY",
                                      "authority": "EXPLOIT"}])
    c = J2._contract_rows([day], root)
    got = J2.what_aegis_did("ZZZ", c)
    assert got["in_universe"] is False and got["direction"] == "absent"
    assert "not in the universe" in got["summary"]

    got = J2.what_aegis_did("AAA", c)
    assert got["in_universe"] is True and got["direction"] == "BUY"
    assert got["authority"] == "EXPLOIT"


def test_the_agency_book_pseudo_tickers_are_not_treated_as_names(tmp_path):
    day = _sessions(1)[0].date().isoformat()
    root = _contract(tmp_path, day, [
        {"ticker": "AGENCY_BOOK:balanced", "verdict": "BUY"},
        {"ticker": "AAA", "verdict": "REFUSED",
         "refusal_class": "EDGE_BELOW_BAR", "refusal_sentence": "no edge"}])
    c = J2._contract_rows([day], root)
    assert "AGENCY_BOOK:balanced" not in c["by_ticker"]
    row = J2.what_aegis_did("AAA", c)
    assert row["direction"] == "REFUSED"
    assert row["refusal_class"] == "EDGE_BELOW_BAR"
    assert row["summary"] == "no edge"


def test_the_ledger_is_read_beside_the_day_contracts(tmp_path):
    day = _sessions(1)[0].date().isoformat()
    root = tmp_path / "decisions"
    root.mkdir()
    (root / "ledger.jsonl").write_text(
        json.dumps({"asof": day, "ticker": "LLL", "verdict": "PROBE",
                    "authority": "EXPLORE"}) + "\n", encoding="utf-8")
    c = J2._contract_rows([day], root)
    assert c["ledger_rows_in_window"] == 1
    assert J2.what_aegis_did("LLL", c)["direction"] == "PROBE"
    assert day in c["days_with_no_contract"]


# ══════════════════════════════════════════════════════ 3. the precursors

def _insider(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "insider.parquet"
    pd.DataFrame(rows).to_parquet(p)
    return p


def test_an_insider_cluster_is_two_filers_and_one_filer_is_not(tmp_path):
    before = "2026-06-10"
    base = {"symbol": "AAA", "event_type": "insider_open_market_buy",
            "insider_trans_code": "P", "insider_dollar_value": 100000.0}
    two = _insider(tmp_path, [
        {**base, "observed_at_utc": pd.Timestamp("2026-06-01", tz="UTC"),
         "insider_cik": "1"},
        {**base, "observed_at_utc": pd.Timestamp("2026-06-02", tz="UTC"),
         "insider_cik": "2"}])
    got = J2.precursor_insider("AAA", before, lookback_days=30, path=two)
    assert got["state"] == J2.PRESENT and got["n_filers"] == 2
    assert str(two) == got["source"]

    one = _insider(tmp_path, [
        {**base, "observed_at_utc": pd.Timestamp("2026-06-01", tz="UTC"),
         "insider_cik": "1"},
        {**base, "observed_at_utc": pd.Timestamp("2026-06-02", tz="UTC"),
         "insider_cik": "1"}])
    assert J2.precursor_insider("AAA", before, lookback_days=30,
                                path=one)["state"] == J2.ABSENT


def test_the_insider_check_is_PIT_on_the_FILING_not_the_trade(tmp_path):
    """A trade done before the move but FILED after it was not knowable."""
    before = "2026-06-10"
    base = {"symbol": "AAA", "event_type": "insider_open_market_buy",
            "insider_trans_code": "P", "insider_dollar_value": 100000.0}
    p = _insider(tmp_path, [
        {**base, "observed_at_utc": pd.Timestamp("2026-06-12", tz="UTC"),
         "insider_cik": "1"},
        {**base, "observed_at_utc": pd.Timestamp("2026-06-12", tz="UTC"),
         "insider_cik": "2"}])
    got = J2.precursor_insider("AAA", before, lookback_days=30, path=p)
    assert got["state"] == J2.ABSENT, "a filing after the move is not a precursor"
    assert "observed_at_utc" in got["anchor"]


def test_a_source_that_is_not_on_disk_is_NOT_HELD_and_names_the_path(tmp_path):
    missing = tmp_path / "nope.parquet"
    got = J2.precursor_insider("AAA", "2026-06-10", lookback_days=30,
                               path=missing)
    assert got["state"] == J2.NOT_HELD
    assert got["source"] == str(missing)
    assert J2.precursor_short_interest("AAA", "2026-06-10",
                                       tmp_path / "si.parquet")["state"] == J2.NOT_HELD
    assert J2.precursor_supplier("AAA", "2026-06-10",
                                 tmp_path / "sg.parquet")["state"] == J2.NOT_HELD


def test_NOT_HELD_is_not_a_soft_ABSENT_for_the_analyst_ledger(tmp_path):
    """One observation cannot make a revision, and saying ABSENT would claim
    we looked and found nothing. We did not look — there is nothing to look at."""
    p = tmp_path / "analyst.jsonl"
    p.write_text(json.dumps({"ticker": "AAA", "observed_at": "2026-06-01T00:00:00",
                             "target_median": 10.0, "n_analysts": 4}) + "\n",
                 encoding="utf-8")
    rev, cov = J2.precursor_analyst("AAA", "2026-06-10", lookback_days=30, path=p)
    assert rev["state"] == J2.NOT_HELD and cov["state"] == J2.NOT_HELD
    assert "two" in rev["detail"]


def test_two_straddling_analyst_snapshots_produce_a_measured_revision(tmp_path):
    p = tmp_path / "analyst.jsonl"
    p.write_text("\n".join(
        json.dumps(r) for r in [
            {"ticker": "AAA", "observed_at": "2026-06-01T00:00:00",
             "target_median": 10.0, "n_analysts": 4},
            {"ticker": "AAA", "observed_at": "2026-06-05T00:00:00",
             "target_median": 13.0, "n_analysts": 7}]) + "\n", encoding="utf-8")
    rev, cov = J2.precursor_analyst("AAA", "2026-06-10", lookback_days=30, path=p)
    assert rev["state"] == J2.PRESENT and rev["delta_pct"] == pytest.approx(30.0)
    assert cov["state"] == J2.PRESENT and cov["delta"] == pytest.approx(3.0)


def test_a_news_burst_is_measured_against_the_names_own_base_rate(tmp_path):
    """Ten stories is a quiet week for a mega-cap and a klaxon for a micro-cap."""
    rows = []
    # LOUD: 400 days of history at ~1 row/month, then 6 rows in the week before
    for i in range(12):
        rows.append({"symbol": "LOUD", "entry_date": f"2025-{i % 12 + 1:02d}-01",
                     "first_seen_utc": "", "title": "t", "body": "b",
                     "source": "s"})
    for i in range(6):
        rows.append({"symbol": "LOUD", "entry_date": f"2026-06-0{i + 1}",
                     "first_seen_utc": "", "title": "t", "body": "b",
                     "source": "s"})
    # CHATTY: the same 6 rows in the window, but it prints every day anyway
    for i in range(300):
        rows.append({"symbol": "CHATTY",
                     "entry_date": (pd.Timestamp("2025-01-01")
                                    + pd.Timedelta(days=i)).date().isoformat(),
                     "first_seen_utc": "", "title": "t", "body": "b",
                     "source": "s"})
    for i in range(6):
        rows.append({"symbol": "CHATTY", "entry_date": f"2026-06-0{i + 1}",
                     "first_seen_utc": "", "title": "t", "body": "b",
                     "source": "s"})
    panel = pd.DataFrame(rows)
    loud = J2.precursor_news_volume("LOUD", "2026-06-10", lookback_days=30,
                                    panel=panel, path=tmp_path / "p.parquet")
    chatty = J2.precursor_news_volume("CHATTY", "2026-06-10", lookback_days=30,
                                      panel=panel, path=tmp_path / "p.parquet")
    assert loud["state"] == J2.PRESENT
    assert chatty["state"] == J2.ABSENT
    assert loud["n_rows"] == chatty["n_rows"] == 6, (
        "the identical raw count is the point: only the base rate separates them")


def test_a_symbol_the_panel_never_carries_is_NOT_HELD_not_zero_news(tmp_path):
    panel = pd.DataFrame([{"symbol": "AAA", "entry_date": "2026-06-01",
                           "first_seen_utc": "", "title": "t", "body": "b",
                           "source": "s"}])
    got = J2.precursor_news_volume("ZZZ", "2026-06-10", lookback_days=30,
                                   panel=panel, path=tmp_path / "p.parquet")
    assert got["state"] == J2.NOT_HELD
    assert "unmeasured, not zero" in got["detail"]


def test_a_typed_event_dated_on_the_move_itself_is_not_a_precursor(tmp_path):
    root = tmp_path / "typed"
    root.mkdir()
    (root / "2026-06-20.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"tickers": ["AAA"], "document_date": "2026-06-10",
         "event_type": "guidance_raise", "magnitude_bucket": "LARGE",
         "direction": 1},
        {"tickers": ["BBB"], "document_date": "2026-06-05",
         "event_type": "guidance_raise", "magnitude_bucket": "LARGE",
         "direction": 1},
    ]) + "\n", encoding="utf-8")
    on_the_day = J2.precursor_typed_event("AAA", "2026-06-10", lookback_days=30,
                                          root=root)
    before = J2.precursor_typed_event("BBB", "2026-06-10", lookback_days=30,
                                      root=root)
    assert on_the_day["state"] == J2.ABSENT, "`< before`, never `<=`"
    assert before["state"] == J2.PRESENT and before["n_events"] == 1


def test_a_negligible_typed_event_is_not_a_precursor(tmp_path):
    root = tmp_path / "typed"
    root.mkdir()
    (root / "2026-06-20.jsonl").write_text(json.dumps(
        {"tickers": ["AAA"], "document_date": "2026-06-05",
         "event_type": "earnings_report", "magnitude_bucket": "NEGLIGIBLE",
         "direction": 0}) + "\n", encoding="utf-8")
    assert J2.precursor_typed_event("AAA", "2026-06-10", lookback_days=30,
                                    root=root)["state"] == J2.ABSENT


# ══════════════════════════════════════════════════════ the digest

def test_the_digest_is_masked_and_carries_only_pre_move_rows(tmp_path):
    panel = pd.DataFrame([
        {"symbol": "AAA", "entry_date": "2026-06-05", "first_seen_utc": "",
         "title": "Acme Corp beats", "body": "Acme said AAA is strong",
         "source": "s"},
        {"symbol": "AAA", "entry_date": "2026-06-20", "first_seen_utc": "",
         "title": "AFTER THE MOVE", "body": "this must not appear",
         "source": "s"}])
    got = J2.build_digest("AAA", "2026-06-10", panel=panel,
                          name_tokens={"AAA": {"acme"}}, lookback_days=30)
    assert got["n_rows"] == 1
    assert "after the move" not in got["digest"].lower()
    assert "acme" not in got["digest"].lower() and "aaa" not in got["digest"].lower()
    assert "[co]" in got["digest"] and got["any_mask"] is True
    assert got["digest"].startswith("- 2026-06-05:"), "the digest is DATED"


def test_a_name_with_no_pre_move_rows_refuses_by_name_rather_than_asking(tmp_path):
    panel = pd.DataFrame([
        {"symbol": "AAA", "entry_date": "2026-06-20", "first_seen_utc": "",
         "title": "t", "body": "b", "source": "s"}])
    got = J2.build_digest("AAA", "2026-06-10", panel=panel, name_tokens={})
    assert got["refused"] == "NO_PRE_MOVE_ROWS" and got["n_rows"] == 0


# ══════════════════════════════════════════════════════ the frozen schema

def test_the_schema_travels_in_the_system_message():
    fp = J2.prompt_fingerprint()
    assert fp["schema_in_system"] is True, (
        "2026-09-13, paid for at 54% refusals: a prompt that REFERS to a "
        "schema it never sends is a prompt whose enum the model invents")
    for c in J2.PRECURSOR_CLASSES:
        assert f'"{c}"' in J2.SYSTEM
    for f in J2.ANSWER_SCHEMA["required"]:
        assert f'"{f}"' in J2.SYSTEM
    assert fp["temperature"] == 0.0


def test_an_invented_enum_member_is_refused_and_the_refusal_names_the_field():
    ok, why = J2.parse_answer(json.dumps({
        "foreseeable": "yes", "precursor_class": "vibes",
        "which_of_our_sources_would_have_carried_it": [],
        "confidence": 0.5, "one_sentence_mechanism": "m"}))
    assert ok is None and any("precursor_class" in w for w in why)

    ok, why = J2.parse_answer(json.dumps({
        "foreseeable": "yes", "precursor_class": "news_volume",
        "which_of_our_sources_would_have_carried_it": ["news_volume", "vibes"],
        "confidence": 1.7, "one_sentence_mechanism": "m"}))
    assert ok is None and any("confidence" in w for w in why)

    ok, why = J2.parse_answer("blah " + json.dumps({
        "foreseeable": "no", "precursor_class": "none",
        "which_of_our_sources_would_have_carried_it": ["news_volume", "vibes"],
        "confidence": 0.25, "one_sentence_mechanism": "m"}) + " blah")
    assert why == [] and ok["precursor_class"] == "none"
    assert ok["which_of_our_sources_would_have_carried_it"] == ["news_volume"]


# ══════════════════════════════════════════════════════ the grader

def test_none_is_a_HIT_when_nothing_was_PRESENT_and_a_MISS_when_something_was():
    said_none = {"precursor_class": "none"}
    assert J2.grade(said_none, [])["hit"] is True
    assert J2.grade(said_none, ["news_volume"])["hit"] is False
    said_news = {"precursor_class": "news_volume"}
    assert J2.grade(said_news, ["news_volume", "typed_event"])["hit"] is True
    assert J2.grade(said_news, ["typed_event"])["hit"] is False
    assert J2.grade(None, [])["hit"] is None


def test_an_unadjudicable_class_is_a_MISS_and_the_receipt_declares_which():
    """`supplier_readthrough` is in the reader's vocabulary and has no on-disk
    source. It is graded a miss — and the fact that it CANNOT be a hit is
    declared, because a grader that silently scores an unanswerable class is a
    broken grader."""
    assert J2.grade({"precursor_class": "supplier_readthrough"},
                    ["news_volume"])["hit"] is False
    assert "supplier_readthrough" in J2.ADJUDICABLE


# ══════════════════════════════════════════════════════ the paired statistics

def test_mcnemar_is_paired_and_concordant_cases_carry_no_evidence():
    rows = [{"local_gguf": {"hit": True}, "deepseek": {"hit": True}}] * 20
    got = J2.mcnemar(rows, "local_gguf", "deepseek")
    assert got["p_exact"] is None and got["n_paired"] == 20
    assert "no discordant pair" in got["note"]

    rows = ([{"local_gguf": {"hit": False}, "deepseek": {"hit": True}}] * 10
            + [{"local_gguf": {"hit": True}, "deepseek": {"hit": False}}] * 0
            + [{"local_gguf": {"hit": True}, "deepseek": {"hit": True}}] * 5)
    got = J2.mcnemar(rows, "local_gguf", "deepseek")
    assert got["n_only_deepseek"] == 10 and got["n_only_local_gguf"] == 0
    assert got["p_exact"] == pytest.approx(2 / 1024, abs=1e-6)


def test_a_case_only_one_reader_answered_is_excluded_from_the_paired_test():
    rows = [{"local_gguf": {"hit": True}, "deepseek": {"hit": None}},
            {"local_gguf": {"hit": True}, "deepseek": {"hit": False}}]
    assert J2.mcnemar(rows, "local_gguf", "deepseek")["n_paired"] == 1


def test_brier_scores_the_readers_own_confidence_against_its_hits():
    rows = [{"r": {"hit": True, "confidence": 1.0}},
            {"r": {"hit": False, "confidence": 0.0}}]
    assert J2.brier(rows, "r")["brier"] == pytest.approx(0.0)
    rows = [{"r": {"hit": False, "confidence": 1.0}},
            {"r": {"hit": True, "confidence": 0.0}}]
    assert J2.brier(rows, "r")["brier"] == pytest.approx(1.0)
    assert J2.brier([], "r")["brier"] is None


# ══════════════════════════════════════════════════════ the env gate

@pytest.mark.parametrize("env,flag,runs", [
    ({}, None, False),
    ({"AEGIS_NIGHT_PAID_OK": "1"}, None, False),          # no key name
    ({"DEEPSEEK_API_KEY": "x"}, None, False),             # no paid-ok
    ({"DEEPSEEK_API_KEY": "x"}, "deepseek", False),       # a flag is NOT enough
    ({"AEGIS_NIGHT_PAID_OK": "1", "DEEPSEEK_API_KEY": "x"}, None, True),
    ({"AEGIS_NIGHT_PAID_OK": "1", "DEEPSEEK_API_KEY": "x"}, "deepseek", True),
    ({"AEGIS_NIGHT_PAID_OK": "0", "DEEPSEEK_API_KEY": "x"}, "deepseek", False),
])
def test_the_paid_leg_is_gated_by_the_environment_not_by_a_flag(env, flag, runs):
    """THE NIGHT QUEUE PASSES NO PER-JOB ARGUMENTS. A leg that can only be
    switched on with `--backend deepseek` can never run in the queue, and a
    flag that could switch it on WITHOUT the key check would be a second
    door."""
    got = J2.paid_leg_intent(flag, env)
    assert got["run"] is runs
    if not runs:
        assert got["refused"] and got["refused"].startswith("REFUSED")


def test_the_gate_checks_the_key_NAME_and_never_reads_its_value():
    got = J2.paid_leg_intent(None, {"AEGIS_NIGHT_PAID_OK": "1",
                                    "DEEPSEEK_API_KEY": "sk-secret-value"})
    assert got["run"] is True and got["value_read"] is False
    assert "sk-secret-value" not in json.dumps(got)


# ══════════════════════════════════════════════════════ the end-to-end run

_ROW_N = {"i": 0}


def _ledger_row(ts: str, *, usd: float | None, purpose: str,
                model: str = "deepseek-chat") -> dict:
    """One call-ledger row.

    `call_id` is UNIQUE per row and that is not decoration: `llm_telemetry`
    folds amendments into their base row by `call_id`, so rows that share one
    are DEDUPED — six $0.01 rows read back as $0.01, and a cap test would pass
    for the wrong reason (or, as here, fail for a real one).
    """
    _ROW_N["i"] += 1
    return {"ts": ts, "purpose": purpose, "provider": "deepseek",
            "call_id": f"test-{_ROW_N['i']:06d}",
            "model": model, "cost_usd": usd, "tokens_in": 500,
            "tokens_out": 100, "cost_is_estimate": True}


def _run(tmp_path, *, paid_ask, cases: int = 4, max_usd: float = 4.5,
         env=None, ledger: Path | None = None, local_ask=None):
    n = 30
    spec = {"SPY": _flat(n)}
    for i in range(cases):
        spec[f"M{i}"] = _one_jump(n, 20, 0.40 - 0.01 * i)
    bars = _bars(spec, n=n)
    panel = pd.DataFrame([
        {"symbol": f"M{i}", "entry_date": d.date().isoformat(),
         "first_seen_utc": "", "title": "a report", "body": "body text",
         "source": "s"}
        for i in range(cases) for d in _sessions(n)[:18]])

    def _local(text):
        return ({"foreseeable": "no", "precursor_class": "none",
                 "which_of_our_sources_would_have_carried_it": [],
                 "confidence": 0.3, "one_sentence_mechanism": "m",
                 "reader_note": ""}, "ok", {"tokens_in": 1, "tokens_out": 1}, None)

    decisions = tmp_path / "decisions"
    decisions.mkdir(exist_ok=True)
    return J2.J2_missed_opportunity(
        bars=bars, top_k=cases, max_usd=max_usd,
        env=({"AEGIS_NIGHT_PAID_OK": "1", "DEEPSEEK_API_KEY": "x"}
             if env is None else env),
        decisions_root=decisions, ledger_path=ledger,
        local_ask=local_ask or _local, paid_ask=paid_ask), panel


def test_the_local_leg_runs_and_the_paid_leg_is_refused_by_name(tmp_path,
                                                                monkeypatch):
    monkeypatch.setattr(J2, "_panel", lambda path=None: (None, tmp_path / "p"))
    out, _ = _run(tmp_path, paid_ask=None, env={})
    assert out["legs"]["deepseek"]["refused"].startswith("REFUSED")
    assert out["legs"]["deepseek"]["n_asked"] == 0
    assert out["verdict"].startswith("NO_IMPROVEMENT")
    assert out["cap_block"]["first_flush_agreement"] is None
    assert out["balance_before"]["total_usd"] is None


def test_a_metered_run_writes_the_first_flush_agreement_block(tmp_path,
                                                              monkeypatch):
    """The cap's read beside the receipt's, after the FIRST paid row."""
    led = tmp_path / "llm_calls.jsonl"
    led.write_text("", encoding="utf-8")
    monkeypatch.setattr(J2, "_balance", lambda label: {
        "total_usd": 49.87, "read_at": "x", "label": label, "error": None})
    monkeypatch.setattr(J2, "_panel",
                        lambda path=None: (_PANEL_HOLDER["panel"], tmp_path / "p"))

    def paid(text):
        with led.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(_ledger_row(
                datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                usd=0.01, purpose=J2.PURPOSE)) + "\n")
        return ({"foreseeable": "yes", "precursor_class": "news_volume",
                 "which_of_our_sources_would_have_carried_it": ["news_volume"],
                 "confidence": 0.7, "one_sentence_mechanism": "m",
                 "reader_note": ""}, "ok", {"tokens_in": 1, "tokens_out": 1},
                None)

    out, panel = _run(tmp_path, paid_ask=paid, ledger=led, cases=3)
    blk = out["cap_block"]["first_flush_agreement"]
    assert blk is not None, "a metered run that flushed must carry the block"
    assert blk["agree"] is True
    assert blk["cap_purpose"] == blk["receipt_purpose"] == J2.PURPOSE
    assert out["legs"]["deepseek"]["n_asked"] >= 1
    assert out["balance_before"]["total_usd"] == 49.87


_PANEL_HOLDER: dict = {"panel": None}


@pytest.fixture(autouse=True)
def _panel_fixture():
    _PANEL_HOLDER["panel"] = pd.DataFrame([
        {"symbol": f"M{i}", "entry_date": d.date().isoformat(),
         "first_seen_utc": "", "title": "a report", "body": "body text here",
         "source": "s"}
        for i in range(6) for d in _sessions(30)[:18]])
    yield
    _PANEL_HOLDER["panel"] = None


def test_the_cap_stops_the_paid_leg_at_the_limit_and_keeps_what_it_bought(
        tmp_path, monkeypatch):
    """A $0.02 cap against $0.01 rows: the run stops, and every row already
    paid for is on the receipt. Refuse BEFORE the call, never refund after."""
    led = tmp_path / "llm_calls.jsonl"
    led.write_text("", encoding="utf-8")
    monkeypatch.setattr(J2, "_balance", lambda label: {
        "total_usd": 1.0, "read_at": "x", "label": label, "error": None})
    monkeypatch.setattr(J2, "_panel",
                        lambda path=None: (_PANEL_HOLDER["panel"], tmp_path / "p"))
    monkeypatch.setattr(J2.config, "MISSED_OPP_SOFT_STOP_USD", 0.02)
    monkeypatch.setattr(J2.config, "MISSED_OPP_FLUSH_EVERY", 1)

    n = {"i": 0}

    def paid(text):
        n["i"] += 1
        with led.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(_ledger_row(
                datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                usd=0.01, purpose=J2.PURPOSE)) + "\n")
        return ({"foreseeable": "no", "precursor_class": "none",
                 "which_of_our_sources_would_have_carried_it": [],
                 "confidence": 0.4, "one_sentence_mechanism": "m",
                 "reader_note": ""}, "ok", {"tokens_in": 1, "tokens_out": 1},
                None)

    out, _ = _run(tmp_path, paid_ask=paid, ledger=led, cases=6, max_usd=0.05)
    assert out["paid_stop"] and "SOFT_STOP" in out["paid_stop"]
    assert n["i"] < 6, "the cap must stop the run before the last case"
    assert out["legs"]["deepseek"]["n_ok"] == n["i"], (
        "every row already paid for stays on the receipt; nothing is refunded")
    assert out["spend"]["usd"] == pytest.approx(0.01 * n["i"])


def test_a_cap_reading_another_jobs_rows_stops_as_REFUSED_CAP_READER_DISAGREES(
        tmp_path, monkeypatch):
    """THE CORPSE OF 2026-09-21, rebuilt: $0.013238 read against $10.047856
    written, same file, same instant, and the only difference was `purpose`.

    Here the ledger is stuffed with rows under ANOTHER purpose while the cap is
    pointed at it, so the two readers of one file separate — and the run must
    stop by name rather than spend the night against the wrong meter.
    """
    led = tmp_path / "llm_calls.jsonl"
    led.write_text("", encoding="utf-8")
    monkeypatch.setattr(J2, "_balance", lambda label: {
        "total_usd": 1.0, "read_at": "x", "label": label, "error": None})
    monkeypatch.setattr(J2, "_panel",
                        lambda path=None: (_PANEL_HOLDER["panel"], tmp_path / "p"))
    monkeypatch.setattr(J2.config, "MISSED_OPP_FLUSH_EVERY", 1)

    # THE TWO READERS, SEPARATED. The cap reads the real tmp_path ledger; the
    # RECEIPT's reader is replaced with the 2026-09-21 numbers verbatim
    # ($10.047856 over 8,342 calls against the cap's $0.013238 over 167 reads).
    # Nothing about the file changed — only which rows each half summed — which
    # is exactly what one missing keyword did on the night.
    def lying_receipt_read(since, *, path=None):
        return {"usd": 10.047856, "calls": 8342, "tokens_in": 0,
                "tokens_out": 0, "cached_tokens": 0, "since_utc": since,
                "purpose": "some_other_job", "source": "test"}

    monkeypatch.setattr(J2, "_spend", lying_receipt_read)

    def paid(text):
        ts = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        with led.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(_ledger_row(ts, usd=0.01,
                                            purpose=J2.PURPOSE)) + "\n")
            for _ in range(50):
                fh.write(json.dumps(_ledger_row(ts, usd=1.00,
                                                purpose="some_other_job")) + "\n")
        return ({"foreseeable": "no", "precursor_class": "none",
                 "which_of_our_sources_would_have_carried_it": [],
                 "confidence": 0.4, "one_sentence_mechanism": "m",
                 "reader_note": ""}, "ok", {"tokens_in": 1, "tokens_out": 1},
                None)

    out, _ = _run(tmp_path, paid_ask=paid, ledger=led, cases=5, max_usd=4.5)
    assert out["paid_stop"].startswith(J2.REFUSED_CAP_READER_DISAGREES)
    blk = out["cap_block"]["first_flush_agreement"]
    assert blk["agree"] is False and blk["cap_calls"] != blk["receipt_calls"]
    assert out["legs"]["deepseek"]["n_asked"] == 1, (
        "the stop is at the FIRST flush, not after the night")


def test_an_unpriced_model_id_stops_the_run_by_name(tmp_path, monkeypatch):
    """A row whose `cost_usd` is None is summed as 0.0, so the cap over it is a
    lower bound of ZERO — 424 rows once cost $0.21 under a $1.00 cap reading
    $0.00 because DeepSeek renamed the served model."""
    led = tmp_path / "llm_calls.jsonl"
    led.write_text("", encoding="utf-8")
    monkeypatch.setattr(J2, "_balance", lambda label: {
        "total_usd": 1.0, "read_at": "x", "label": label, "error": None})
    monkeypatch.setattr(J2, "_panel",
                        lambda path=None: (_PANEL_HOLDER["panel"], tmp_path / "p"))
    monkeypatch.setattr(J2.config, "MISSED_OPP_FLUSH_EVERY", 1)

    def paid(text):
        with led.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(_ledger_row(
                datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                usd=None, purpose=J2.PURPOSE,
                model="deepseek-flash")) + "\n")
        return ({"foreseeable": "no", "precursor_class": "none",
                 "which_of_our_sources_would_have_carried_it": [],
                 "confidence": 0.4, "one_sentence_mechanism": "m",
                 "reader_note": ""}, "ok", {"tokens_in": 1, "tokens_out": 1},
                None)

    out, _ = _run(tmp_path, paid_ask=paid, ledger=led, cases=5, max_usd=4.5)
    assert out["paid_stop"].startswith(J2.REFUSED_UNPRICED_CALL)
    assert "deepseek-flash" in out["paid_stop"]
    assert out["spend_is_a_lower_bound"] is True
    assert out["spend_caveat"] and "LOWER BOUND" in out["spend_caveat"]


def test_a_bar_panel_that_cannot_be_read_refuses_rather_than_reporting_zero(
        tmp_path):
    out = J2.J2_missed_opportunity(bars=pd.DataFrame(), env={},
                                   decisions_root=tmp_path,
                                   ledger_path=tmp_path / "l.jsonl")
    assert out["verdict"].startswith(J2.REFUSED_NO_BARS)
    assert out["top_missed"] == []


# ══════════════════════════════════════════════════════ the registration

def test_the_job_is_registered_stamped_and_reachable_from_the_factory():
    from scripts import night_factory_jobs as nfj

    assert "J2_missed_opportunity" in nfj.JOBS
    assert nfj.JOB_STAGES["J2_missed_opportunity"] in nfj.STAGE_ORDER
    # the lazy loader resolves at CALL time; prove the target exists NOW
    assert callable(J2.J2_missed_opportunity)


def test_the_cap_names_its_purpose_at_the_call_site():
    """The repo-wide AST guard requires it; this is the local, readable form.
    Left off, `_RunCap.refresh()` falls back to L2's purpose and the cap spends
    the night summing another job's rows."""
    src = Path(J2.__file__).read_text(encoding="utf-8")
    i = src.index("_RunCap(")
    window = src[i:i + 400]
    assert "purpose=PURPOSE" in window
    assert J2.PURPOSE == "j2_missed_opportunity"


def test_the_three_run_level_refusals_are_declared():
    assert set(J2.CAP_REFUSALS) == {
        J2.REFUSED_NO_LEDGER, J2.REFUSED_UNPRICED_CALL,
        J2.REFUSED_CAP_READER_DISAGREES}
    for name in J2.CAP_REFUSALS:
        assert name in J2.__doc__, f"{name} is not in the module docstring"


def test_no_fixture_in_this_file_encodes_a_calendar_moment():
    """`_sessions` derives its dates; a literal 'next week' fails the day after
    it passes. The guard is that the screen's own window is derived from the
    bars it is handed, not from today."""
    n = 30
    bars = _bars({"SPY": _flat(n), "AAA": _one_jump(n, 20, 0.4)}, n=n)
    out = J2.rank_missed(bars, window=21, top_k=1, sub=5, floor_usd=0.0)
    assert out["screen"]["last_session"] == _sessions(n)[-1].date().isoformat()
    future = _bars({"SPY": _flat(n), "AAA": _one_jump(n, 20, 0.4)}, n=n,
                   dollar_vol=50e6)
    future["date"] = future["date"] + pd.Timedelta(days=400)
    out2 = J2.rank_missed(future, window=21, top_k=1, sub=5, floor_usd=0.0)
    assert out2["moves"][0]["ticker"] == "AAA", (
        "the same tape 400 days later must give the same answer")
    assert out2["screen"]["last_session"] != out["screen"]["last_session"]


def test_a_ledger_the_cap_cannot_see_refuses_before_the_first_paid_call(
        tmp_path, monkeypatch):
    """MEASURED 2026-09-19: N9's first probe ran fifteen minutes under a $1.00
    cap that read $0.00 the whole time. A cap that reads a ledger it cannot see
    is not a loose cap, it is NO cap — its total is a lower bound of zero and
    it can never bind."""
    monkeypatch.setattr(J2, "_panel",
                        lambda path=None: (_PANEL_HOLDER["panel"], tmp_path / "p"))
    asked = {"n": 0}

    def paid(text):                                   # pragma: no cover
        asked["n"] += 1
        raise AssertionError("no paid call may be made under an unseeable ledger")

    out, _ = _run(tmp_path, paid_ask=paid, cases=3,
                  ledger=tmp_path / "no_such_dir" / "llm_calls.jsonl")
    assert out["deepseek_leg"].startswith(J2.REFUSED_NO_LEDGER)
    assert out["legs"]["deepseek"]["n_asked"] == 0 and asked["n"] == 0
    assert out["ledger"]["ok"] is False
    assert out["balance_before"]["total_usd"] is None, (
        "a refused leg takes no balance snapshot either")


def test_every_case_on_the_receipt_carries_both_readers_and_its_hits(
        tmp_path, monkeypatch):
    """One object per missed name: ticker, window, excess, what AEGIS did, the
    precursors, and BOTH readers' answers. A receipt that makes its reader join
    two lists by hand is a receipt nobody reads."""
    monkeypatch.setattr(J2, "_panel",
                        lambda path=None: (_PANEL_HOLDER["panel"], tmp_path / "p"))
    out, _ = _run(tmp_path, paid_ask=None, env={}, cases=3)
    assert out["top_missed"]
    for c in out["top_missed"]:
        for key in ("ticker", "window_start", "window_end", "excess_pct",
                    "aegis", "precursors", "precursors_present", "readers"):
            assert key in c, f"{key} missing from a top_missed row"
        assert set(J2.PRECURSOR_CLASSES) - {"none"} == set(c["precursors"])
        for v in c["precursors"].values():
            assert v["state"] in (J2.PRESENT, J2.ABSENT, J2.NOT_HELD)
            assert v["source"], "every precursor names the path it was read from"
        assert "local_gguf" in c["readers"]
        assert "digest" not in c["digest"], (
            "the corpus text is not a finding and does not belong on the receipt")
