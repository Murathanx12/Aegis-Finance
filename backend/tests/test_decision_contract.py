"""The Decision Contract, pinned (chunk 18).

Five properties, and the reason each is a test rather than a convention:

1. **Every field is present on every row.** The contract's whole purpose is to
   be gradeable tomorrow, and a row missing `falsifier` or `expiry_utc` is a
   position nobody can be wrong about.
2. **`NOT CALIBRATED` is a FIELD.** An omitted `expected_payoff` reads as an
   oversight; the string reads as a finding, and CLAUDE.md's "a headline number
   belongs in a receipt" cuts both ways.
3. **The refusal vocabulary is the execution repo's, byte for byte.** Two repos
   with two spellings of "why no trade" cannot be censused together, so the
   local tuples are sha256-pinned: a change over there is a visible red test
   here rather than a silent divergence.
4. **Zero costs are a DIAGNOSTIC, never a default** (`portfolio_farm.Policy`'s
   rule, same words).
5. **The write is atomic.** A half-written receipt cannot be told apart from a
   day on which the engine found two names.

Nothing here reads `backend/data` or the live funnel: every input is synthetic
and every write goes to `tmp_path`.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from backend import config
from backend.services import decision_contract as DC

# ── THE PINS ───────────────────────────────────────────────────────────────
# sha256 over the members in order, newline-joined. Computed from
# `aegis-alpha-terminal/alpha/refusal_classes.py` on 2026-09-19: 31 PATTERNS
# classes + UNCLASSIFIED, and its 18 TERMINAL_STATES. If either of these turns
# red, the execution repo changed its vocabulary and this repo's REFUSED rows
# stopped being joinable to its census — which is a decision, not a rebase.
#
# VERIFIED EQUAL at adoption, not merely asserted. To recompute from the other
# checkout (it is a sibling directory, not an import — the two repos move by
# hand and nothing here may depend on its presence):
#
#   from that checkout's root, in python:
#     import hashlib
#     from alpha import refusal_classes as R
#     names = tuple(x for x, _ in R.PATTERNS) + (R.UNCLASSIFIED,)
#     joined = chr(10).join(names).encode()
#     hashlib.sha256(joined).hexdigest()           # REFUSAL_CLASSES_SHA256
#     # and the same over R.TERMINAL_STATES        # TERMINAL_STATES_SHA256
#
# Both digests below came out of that command on 2026-09-19.
REFUSAL_CLASSES_SHA256 = (
    "113d812c66f6d1b9421cd997dd2ca27395041948c63f726cf35e5f9ac082605c")
TERMINAL_STATES_SHA256 = (
    "14f663566b3c4526df7074d62dcf3036774d979a4faaed5b85c254cb07918a24")


class _Leader:
    def __init__(self, signal_id="profitability_small"):
        self.signal_id = signal_id
        self.raw_value = 0.75


class _Rec:
    """The two attributes `compose_book` reads, and nothing else."""

    def __init__(self, ticker, *, recommendation="BUY", confidence="HIGH",
                 evidence_grade="SUPPORTED", ranking_score=0.9, rank=1,
                 price=10.0, signal="profitability_small"):
        self.ticker = ticker
        self.recommendation = recommendation
        self.confidence = confidence
        self.evidence_grade = evidence_grade
        self.ranking_score = ranking_score
        self.rank = rank
        self.price = price
        self.reason_for_rank = "led by the licensed picker"
        self._leader = _Leader(signal)

    def leader(self):
        return self._leader


@pytest.fixture()
def synthetic(monkeypatch):
    """A funnel state and a composed book, both invented here.

    `funnel_state` and `compose_book` are replaced at their module-level names
    rather than at the import site, which is the whole reason those
    indirections exist in `decision_contract`.
    """
    recs = [
        _Rec("AAA", rank=1),
        _Rec("BBB", rank=2, recommendation="WATCH", confidence="MEDIUM",
             ranking_score=0.5, signal="insider_opportunistic"),
        _Rec("CCC", rank=3, recommendation="HOLD", ranking_score=0.0),
        _Rec("DDD", rank=4, evidence_grade="NO_EVIDENCE",
             recommendation="NO_ACTION", ranking_score=0.0),
        _Rec("EEE", rank=5, ranking_score=0.4),
    ]
    state = {
        "available": True,
        "recs": recs,
        "candidates": {r.ticker: {"price": r.price} for r in recs},
        "funnel_generated_at": "2026-09-18T00:00:00+00:00",
        "degradation_reasons": [],
        "books": {},
    }
    book = {
        "positions": [
            {"ticker": "SPY", "weight": 0.9, "dollars": 90_000.0,
             "shares": None, "price": None, "source": "benchmark-core",
             "reason": "core", "capacity": {}},
            {"ticker": "AAA", "weight": 0.03, "dollars": 3_000.0, "shares": 300,
             "price": 10.0, "source": "evidence-led", "reason": "BUY/HIGH",
             "capacity": {"tradeable": True}},
            {"ticker": "BBB", "weight": 0.01, "dollars": 1_000.0, "shares": 100,
             "price": 10.0, "source": "evidence-led", "reason": "WATCH/MEDIUM",
             "capacity": {"tradeable": True}},
        ],
        "degradation_reasons": [
            "EEE: 3.0% tilt is untradeable at $100,000 (median dollar volume) "
            "— weight returned to the core"],
    }
    monkeypatch.setattr(DC, "funnel_state", lambda *a, **k: state)
    monkeypatch.setattr(DC, "compose_book", lambda *a, **k: book)
    monkeypatch.setattr(DC, "agency_options",
                        lambda asof: ([], "CANNOT DETERMINE: no IPS document "
                                           "is in the store (test)"))
    return state, book


def _build(tmp_path, **kw):
    kw.setdefault("asof", date(2026, 9, 19))
    kw.setdefault("out_dir", tmp_path / "decisions")
    kw.setdefault("capital", 100_000.0)
    return DC.build_daily_contracts(**kw)


# ── the pins ───────────────────────────────────────────────────────────────

def test_the_refusal_vocabulary_is_pinned_to_the_execution_repos():
    assert DC.enum_fingerprint(DC.REFUSAL_CLASSES) == REFUSAL_CLASSES_SHA256, (
        "the local copy of alpha/refusal_classes.py's class list changed. That "
        "is a cross-repo vocabulary change and must be a deliberate edit to "
        "BOTH this tuple and this pin, never a quiet one.")
    assert DC.enum_fingerprint(DC.TERMINAL_STATES) == TERMINAL_STATES_SHA256
    assert len(DC.REFUSAL_CLASSES) == 32   # 31 classes + UNCLASSIFIED
    assert len(DC.TERMINAL_STATES) == 18
    assert DC.UNCLASSIFIED in DC.REFUSAL_CLASSES
    assert DC.OTHER_TYPED in DC.TERMINAL_STATES


def test_every_local_pattern_maps_into_the_closed_sets():
    """A pattern that mapped to a class outside the enum would be a third
    vocabulary wearing the second one's name.

    The LOCAL class (chunk 23a-ii) is a FOURTH thing and is deliberately not
    pinned to the execution repo: it answers "what does this refusal mean",
    which the closed 31 cannot, because `EDGE_BELOW_BAR` covers both "no view
    at all" and "the measurement said no". It has its own closed set here.
    """
    for cls, term, _pat, basis, local in DC._LOCAL_PATTERNS:
        assert cls in DC.REFUSAL_CLASSES, cls
        assert term in DC.TERMINAL_STATES, term
        assert basis and isinstance(basis, str), cls
        assert local in DC.LOCAL_REFUSAL_CLASSES, local
    assert DC.UNTYPED in DC.LOCAL_REFUSAL_CLASSES
    for name in config.PROBE_REFUSAL_CLASSES:
        assert name in DC.LOCAL_REFUSAL_CLASSES, (
            f"{name} is probe-eligible in config and is not a local refusal "
            f"class, so no row could ever carry it")


def test_an_unrecognised_sentence_is_typed_and_never_blank():
    got = DC.classify_refusal("a gate nobody has typed yet said something new")
    assert got["refusal_class"] == DC.UNCLASSIFIED
    assert got["terminal_state"] == DC.OTHER_TYPED
    blank = DC.classify_refusal("")
    assert blank["refusal_class"] == DC.UNCLASSIFIED
    assert "CANNOT DETERMINE" in blank["refusal_reason"]


def test_the_two_kinds_of_UNCLASSIFIED_are_one_field_apart():
    """MEASURED 2026-09-20: the day's contract carried 7 UNCLASSIFIED refusals
    and a reader could not tell whether the vocabulary had no class for the
    sentence or whether nothing had matched it. The first owes nothing; the
    second owes a pattern, and only one of them should be counted as work."""
    typed = DC.classify_refusal(
        "no licensed signal speaks to this name (evidence grade NO_EVIDENCE): "
        "screened, liquid and priced, and the engine has nothing it is allowed "
        "to say about it")
    assert typed["refusal_class"] == DC.UNCLASSIFIED
    assert typed["terminal_state"] == "DATA_MISSING"
    assert not typed["refusal_class_basis"].startswith("NO PATTERN MATCHED")

    unmatched = DC.classify_refusal("a gate nobody has typed yet said something new")
    assert unmatched["refusal_class"] == DC.UNCLASSIFIED
    assert unmatched["refusal_class_basis"].startswith("NO PATTERN MATCHED")

    blob = DC.payload([
        {"direction": "REFUSED", **typed},
        {"direction": "REFUSED", **unmatched},
        {"direction": "BUY", "ticker": "AAA"},
    ], asof=date(2026, 9, 20))
    assert blob["count_by_refusal_class"][DC.UNCLASSIFIED] == 2
    assert blob["unclassified_owing_a_pattern"] == 1
    assert sum(blob["count_by_unclassified_basis"].values()) == 2


# ── the rows ───────────────────────────────────────────────────────────────

_REQUIRED = ("decision_id", "policy_id", "policy_version",
             "information_cutoff_utc", "licence", "universe_hash", "signal",
             "direction", "horizon", "expected_payoff",
             "estimated_probability", "maximum_loss", "position_budget",
             "cost_model", "falsifier", "expiry_utc", "artifact_sha256")


def test_every_declared_field_is_on_every_row(synthetic, tmp_path):
    rows = _build(tmp_path)
    assert rows
    for r in rows:
        missing = [f for f in _REQUIRED if f not in r]
        assert not missing, f"{r.get('ticker')}: {missing}"
        assert r["direction"] in DC.DIRECTIONS
        assert r["licence"] == "PRODUCT_EXPERIMENT"


def test_the_tilts_become_buy_and_watch_rows_with_the_engines_own_size(
        synthetic, tmp_path):
    rows = {r["ticker"]: r for r in _build(tmp_path)}
    assert rows["AAA"]["direction"] == "BUY"
    assert rows["BBB"]["direction"] == "WATCH"
    assert rows["AAA"]["position_budget"]["dollars"] == 3_000.0
    assert rows["AAA"]["position_budget"]["shares"] == 300
    # the worst case is the WHOLE notional, because no stop is declared
    assert rows["AAA"]["maximum_loss"]["stop_pct"] is None
    assert rows["AAA"]["maximum_loss"]["worst_case_usd"] == pytest.approx(-3_000.0)
    assert "CANNOT DETERMINE" not in rows["AAA"]["falsifier"]


def test_expected_payoff_is_a_field_and_never_a_number(synthetic, tmp_path):
    for r in _build(tmp_path):
        assert r["expected_payoff"] == DC.NOT_CALIBRATED
        assert isinstance(r["expected_payoff"], str)
        assert r["expected_payoff_basis"]


def test_a_probability_that_does_not_exist_is_null_WITH_a_reason(
        synthetic, tmp_path):
    for r in _build(tmp_path):
        assert r["estimated_probability"] is None
        assert r["estimated_probability_reason"]


def test_every_refused_row_carries_a_class_from_the_frozen_tuple(
        synthetic, tmp_path):
    rows = _build(tmp_path)
    refused = [r for r in rows if r["direction"] == "REFUSED"]
    assert refused
    for r in refused:
        assert r["refusal_class"] in DC.REFUSAL_CLASSES
        assert r["terminal_state"] in DC.TERMINAL_STATES
        assert r["local_refusal_class"] in DC.LOCAL_REFUSAL_CLASSES
        assert r["refusal_reason"]
        assert r["probe_refused"], (
            "a row that stayed REFUSED must say why it was not probed; "
            "otherwise 'not probed' and 'never considered' read the same")
    by_ticker = {r["ticker"]: r for r in refused}
    # the tape refusal is EVIDENCE about tradeability and stays refused
    assert by_ticker["EEE"]["terminal_state"] == "LIQUIDITY"
    assert by_ticker["EEE"]["local_refusal_class"] == "LIQUIDITY"
    # CHUNK 23a-ii: the two refusals that are an ABSENCE of measurement are
    # PROBE rows now, and they keep the gate's own sentence and its class.
    probe = {r["ticker"]: r for r in rows if r["direction"] == "PROBE"}
    assert set(probe) == {"CCC", "DDD"}
    assert probe["CCC"]["refusal_class"] == "EDGE_BELOW_BAR"
    assert probe["CCC"]["local_refusal_class"] == "NO_ACTION_VERDICT"
    assert "not BUY or WATCH" in probe["CCC"]["probe_basis"]
    assert probe["DDD"]["terminal_state"] == "DATA_MISSING"
    assert probe["DDD"]["local_refusal_class"] == "NO_LICENSED_SIGNAL"
    assert probe["DDD"]["position_budget"]["weight"] == 0.0


def test_the_decision_id_is_stable_and_the_seal_covers_the_row(
        synthetic, tmp_path):
    first = {r["ticker"]: r for r in _build(tmp_path)}
    second = {r["ticker"]: r for r in _build(tmp_path)}
    assert first["AAA"]["decision_id"] == second["AAA"]["decision_id"]
    row = dict(first["AAA"])
    assert DC.seal(row) == row["artifact_sha256"]
    row["position_budget"] = {**row["position_budget"], "dollars": 1.0}
    assert DC.seal(row) != row["artifact_sha256"], (
        "the seal must cover the size; a hash that a resize does not move is "
        "not a seal")


def test_a_different_day_is_a_different_decision(synthetic, tmp_path):
    a = {r["ticker"]: r for r in _build(tmp_path, asof=date(2026, 9, 19))}
    b = {r["ticker"]: r for r in _build(tmp_path, asof=date(2026, 9, 20))}
    assert a["AAA"]["decision_id"] != b["AAA"]["decision_id"]


# ── costs ──────────────────────────────────────────────────────────────────

def test_a_zero_cost_without_the_diagnostic_flag_is_refused_by_name():
    with pytest.raises(DC.CostModelRefused) as exc:
        DC.cost_model_row("some_model", round_trip_bps=0.0)
    assert "zero_cost_diagnostic" in str(exc.value)
    row = DC.cost_model_row("some_model", round_trip_bps=0.0,
                            zero_cost_diagnostic=True)
    assert row["zero_cost_diagnostic"] is True
    with pytest.raises(DC.CostModelRefused):
        DC.cost_model_row("m", round_trip_bps=5.0, zero_cost_diagnostic=True)


def test_an_unpriced_row_says_so_rather_than_claiming_zero(synthetic, tmp_path):
    rows = _build(tmp_path)
    cost = rows[0]["cost_model"]
    assert cost["priced"] is False
    assert cost["round_trip_bps"] is None
    assert cost["name"] == "CANNOT DETERMINE"
    assert cost["reason"]


# ── expiry ─────────────────────────────────────────────────────────────────

def test_the_expiry_comes_from_the_falsifiers_own_window_when_it_names_one():
    when, basis = DC.falsifier_expiry(
        "gross profitability falls below the median for two consecutive quarters",
        asof=date(2026, 1, 1), horizon_months=24)
    assert when.startswith("2026-07-02")
    assert "two consecutive quarters" in basis


def test_a_hold_rule_that_counts_sessions_expires_on_its_own_maximum():
    when, basis = DC.falsifier_expiry("Hold each name up to 21 sessions",
                                      asof=date(2026, 1, 1), horizon_months=24)
    assert when.startswith("2026-01-31")   # 21 sessions -> 30 calendar days
    assert "21 sessions" in basis


def test_a_session_horizon_names_the_calendar_that_produced_its_expiry():
    """Chunk 23a. A PROBE row's expiry is counted in TRADING SESSIONS.

    Which calendar walked them is on the row, because 126 sessions resolved on
    weekday arithmetic lands about six sessions late over a year of holidays,
    and a reader grading the row next March has no other way to know which
    ruler it was written against.
    """
    when, basis = DC.sessions_expiry(date(2026, 9, 21), 5)
    assert when.startswith("2026-09-28")        # Mon 21st + 5 sessions
    assert "5 trading sessions after 2026-09-21" in basis
    assert ("XNYS" in basis) or ("approximation" in basis)
    far, _ = DC.sessions_expiry(date(2026, 9, 21), 126)
    assert far > when


def test_a_refusal_that_is_an_absence_of_measurement_becomes_a_probe(
        synthetic, tmp_path):
    """Chunk 23a-ii, and roadmap §16.5 item 39 as a test.

    Two of the three refusals in this fixture are an ABSENCE — a HOLD verdict
    and an evidence grade of NO_EVIDENCE — and one is the tape saying the
    tilt cannot be carried. The first two become virtual rows at four horizons;
    the third stays refused. No dollar moves either way, and the census on the
    file says which class went where so a reader can check it name by name.
    """
    assert "PROBE" in DC.DIRECTIONS
    rows = _build(tmp_path)
    blob = DC.latest("2026-09-19", tmp_path / "decisions")
    n_h = len(config.PROBE_HORIZONS_SESSIONS)
    assert blob["count_by_direction"]["PROBE"] == 2 * n_h
    census = blob["probe"]
    assert census["n_names"] == 2
    assert census["n_hypotheses"] == 1, (
        "both names are led by the same signal in the same information-set "
        "month, so they are ONE hypothesis with two observations — which is "
        "the whole reason the id is not the ticker: a panel keyed per name "
        "would need thirty grades of ONE name to say anything")
    assert census["rows_by_source"] == {"contract_refusal_class": 2 * n_h}
    assert census["probed_by_local_refusal_class"] == {
        "NO_ACTION_VERDICT": 1, "NO_LICENSED_SIGNAL": 1}
    assert census["stayed_refused_by_local_refusal_class"] == {"LIQUIDITY": 1}
    assert census["rows_without_a_hypothesis_id"] == 0
    assert "a refusal to fund is not a refusal to learn" not in census["honesty"]
    assert "§16.5 item 39" in census["honesty"]

    # the capital resolution is untouched: a PROBE row holds nothing
    res = blob["capital_resolution"]
    assert res["probe_count"] == 2 * n_h
    assert res["probe_pct"] == 0.0
    without = DC.capital_resolution(
        [r for r in rows if r["direction"] != "PROBE"], capital=100_000.0)
    for key in ("benchmark_pct", "active_exploit_pct", "active_explore_pct",
                "cash_pct", "sums_to", "dollars"):
        assert res[key] == without[key], key


def test_a_view_against_and_a_measured_no_are_not_probed(synthetic, tmp_path):
    """PROBE is for the absence of a measurement, never for one we dislike.

    A SELL is a view AGAINST the name; a read that came back at or below the
    floor is evidence. Both wear sentences whose PINNED class is the same as a
    probe-eligible one, and only the local class and the verdict separate them
    — which is the whole reason both fields exist.
    """
    sell = DC.classify_refusal("verdict SELL is not BUY or WATCH, so no tilt "
                               "is licensed")
    assert sell["local_refusal_class"] == "NO_ACTION_VERDICT"
    ok, why = DC.probe_eligible(sell, "SELL")
    assert ok is False and "view AGAINST" in why

    measured = DC.classify_refusal(
        "insider_opportunistic's measured net read is -0.0726%/month, which is "
        "not above EXPLORE_MIN_NET_PCT 0 — a hypothesis with no positive "
        "expected value is not worth paper risk")
    assert measured["refusal_class"] == "EDGE_BELOW_BAR"
    assert measured["local_refusal_class"] == "MEASURED_NO_EV"
    assert not measured["refusal_class_basis"].startswith("NO PATTERN MATCHED")
    ok2, why2 = DC.probe_eligible(measured, "WATCH")
    assert ok2 is False and "MEASURED_NO_EV" in why2

    hold = DC.classify_refusal("verdict HOLD is not BUY or WATCH, so no tilt "
                               "is licensed")
    assert DC.probe_eligible(hold, "HOLD")[0] is True
    no_sig = DC.classify_refusal(
        "no licensed signal speaks to this name (evidence grade NO_EVIDENCE)")
    assert DC.probe_eligible(no_sig, "NO_ACTION")[0] is True


def test_the_sentences_this_repo_writes_all_carry_a_pattern(synthetic,
                                                             tmp_path):
    """The contract's own rule, enforced on the whole day (chunk 23a-ii).

    MEASURED 2026-09-21: the live contract carried ONE row whose basis said
    NO PATTERN MATCHED — chunk 21's `EXPLORE_MIN_NET_PCT` refusal, which had
    never been typed. Four patterns were owed and are now here.
    """
    blob = DC.latest("2026-09-19", tmp_path / "decisions") or {}
    if not blob:
        _build(tmp_path)
        blob = DC.latest("2026-09-19", tmp_path / "decisions")
    assert blob["unclassified_owing_a_pattern"] == 0
    for sentence in (
            "EXPLORE was licensed by a measured, unproven read (x +0.1%/mo, "
            "t 1.4), and the paper-risk budget is already full: the budget is "
            "a ceiling, not a guide",
            "x is a measured, unproven read worth exploring, but this name "
            "carries no usable annualised volatility (vol_annual=None)",
            "x is CALIBRATED, so this name belongs to EXPLOIT and did not win "
            "a place there. EXPLORE is for measured-but-UNPROVEN reads and "
            "does not fund a proven one as a consolation"):
        got = DC.classify_refusal(sentence)
        assert not got["refusal_class_basis"].startswith("NO PATTERN MATCHED"), (
            sentence[:60])
        assert got["local_refusal_class"] != DC.UNTYPED


def test_the_probe_cap_refusal_is_a_typed_class_not_an_unmatched_sentence():
    """A new REFUSED sentence owes a `classify_refusal` pattern (spec)."""
    got = DC.classify_refusal(
        "the day's PROBE ceiling refused this name a virtual row: it ranked "
        "#201 of 300 unmeasured candidates and config.PROBE_MAX_NAMES_PER_DAY "
        "is 200. This refuses a ROW, not a hypothesis")
    assert got["terminal_state"] == "CAPACITY"
    assert not got["refusal_class_basis"].startswith("NO PATTERN MATCHED")


def test_a_falsifier_with_no_window_falls_back_and_SAYS_which():
    when, basis = DC.falsifier_expiry("something changes", asof=date(2026, 1, 1),
                                      horizon_months=24)
    assert when.startswith("2028-01")   # 24 months at 30.44 days
    assert "policy horizon" in basis
    none_when, none_basis = DC.falsifier_expiry("", asof=date(2026, 1, 1),
                                                horizon_months=24)
    assert none_when is None
    assert "CANNOT DETERMINE" in none_basis


# ── the file ───────────────────────────────────────────────────────────────

def test_the_file_is_written_atomically_with_counts_and_a_written_utc(
        synthetic, tmp_path):
    rows = _build(tmp_path)
    path = DC.contracts_path("2026-09-19", tmp_path / "decisions")
    assert path.is_file()
    assert not list((tmp_path / "decisions").glob("*.tmp")), (
        "the temp file must be gone: an atomic write is os.replace, not a "
        "rename that leaves its scaffolding behind")
    blob = json.loads(path.read_text(encoding="utf-8"))
    assert blob["written_utc"]
    assert blob["n_rows"] == len(rows)
    assert set(blob["count_by_direction"]) == set(DC.DIRECTIONS)
    assert blob["count_by_direction"]["BUY"] == 1
    assert blob["count_by_direction"]["WATCH"] == 1
    assert blob["licence"] == "PRODUCT_EXPERIMENT"
    assert blob["read_me_first"]


def test_the_worst_case_for_the_largest_admissible_book_is_in_dollars(
        synthetic, tmp_path):
    """CLAUDE.md session protocol 4: n x notional% x stop% AND gross/equity,
    printed, not remembered."""
    _build(tmp_path)
    blob = DC.latest("2026-09-19", tmp_path / "decisions")
    w = blob["worst_case_largest_admissible_book"]
    assert w["worst_case_usd"] < 0
    assert "$" in w["verdict"]
    assert w["stop_pct"] is None
    assert w["book_gross_over_equity"] == 1.0
    assert w["tilt_gross_over_equity"] <= 1.0


def test_a_direction_nobody_produced_today_is_named_on_the_receipt(
        synthetic, tmp_path):
    _build(tmp_path)
    blob = DC.latest("2026-09-19", tmp_path / "decisions")
    assert "SELL" in blob["directions_not_produced_today"], (
        "no source in this repo emits SELL; the receipt must say so rather "
        "than leaving a reader to infer it from an absence")


def test_latest_returns_none_when_no_contract_exists(tmp_path):
    assert DC.latest("2026-09-19", tmp_path / "nothing") is None


# ── absent inputs ──────────────────────────────────────────────────────────

def test_no_funnel_is_a_named_note_and_never_a_crash(monkeypatch, tmp_path):
    monkeypatch.setattr(DC, "funnel_state",
                        lambda *a, **k: {"available": False, "recs": [],
                                         "candidates": {},
                                         "degradation_reasons": []})
    monkeypatch.setattr(DC, "compose_book",
                        lambda *a, **k: {"positions": [],
                                         "degradation_reasons": []})
    monkeypatch.setattr(DC, "agency_options", lambda asof: ([], "no IPS (test)"))
    rows = _build(tmp_path)
    assert rows == []
    blob = DC.latest("2026-09-19", tmp_path / "decisions")
    assert any("no funnel run available" in n for n in blob["notes"])


def test_a_universe_with_no_candidates_returns_the_words_not_a_digest():
    assert DC.universe_hash({}, None).startswith("CANNOT DETERMINE")
    assert DC.universe_hash({"A": {}}, "t").startswith("sha256:")


def test_the_reader_sentence_refuses_to_invent_one_when_no_contract_exists():
    text = DC.summarise_for_reader(None)
    assert "has not said what it would buy" in text
    assert "I will not invent one" in text


def test_the_reader_sentence_names_the_policy_and_the_size(synthetic, tmp_path):
    _build(tmp_path)
    blob = DC.latest("2026-09-19", tmp_path / "decisions")
    seen: list[str] = []
    text = DC.summarise_for_reader(blob, record=seen.append)
    assert "BUY AAA" in text
    assert "$3,000" in text
    assert "NOT CALIBRATED" in text
    assert "falsifier:" in text
    assert "INVESTMENT_COMMITTEE_CORE_AND_TILTS" in text
    assert len(seen) == 2, "the reader saw both actionable rows"
