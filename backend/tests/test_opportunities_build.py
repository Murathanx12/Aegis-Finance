"""The Opportunity Explorer BUILDER (review 2026-10-06, F1-F6): the labels a reader acts on.

Offline. Every input is a literal fixture: the F1 numbers are the values the receipt
read on 2026-10-06 for the owner's named tickers (dated-firm counts from
target_revisions.parquet, XBRL cash and quarterly operating income from
sec_facts_history.parquet, the dated catalysts from the thesis cards), pinned here so
the rule is tested and not the machine's data. Dates are derived from a fixed `today`
passed in, never from the calendar.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.services import opportunities as O
from scripts import opportunities_build as B

TODAY = "2026-10-06"


def _runway(cash: float, op_q: float) -> dict:
    return {"cash_usd": cash, "cash_end": "2026-06-30", "op_income_q_usd": op_q, "quarter_end": "2026-06-30",
            "filed": "2026-08-10", "quarters": (round(cash / -op_q, 2) if op_q < 0 else None), "source": "fixture"}


#: ticker -> (dated firms in 180 days, catalysts, runway) as read on 2026-10-06.
OWNER_NAMES = {
    "KYTX": (2, [{"date": "2026-12-31", "kind": "regulatory", "detail": "Target completion of rolling BLA for miv-cel"}],
             _runway(31_806_000, -39_556_000)),
    "QUBT": (4, [{"date": "2026-11-09", "kind": "earnings (ESTIMATE)", "detail": "last 8-K item 2.02 + 91 days"}],
             _runway(189_150_000, -23_013_000)),
    "SLDP": (1, [{"date": "2026-12-31", "kind": "guidance", "detail": "Expect to announce a Korea JV"}],
             _runway(24_284_000, -30_289_000)),
    "SOC": (2, [{"date": "2026-11-12", "kind": "earnings", "detail": "Q3 2026 earnings date estimated"}],
            _runway(21_599_000, -66_894_000)),
    "NOVT": (1, [{"date": "2026-11-02", "kind": "earnings", "detail": "Q3 2026 earnings"}],
             _runway(718_650_000, 18_061_000)),
    "MAN": (6, [{"date": "2026-10-15", "kind": "earnings", "detail": "Q3 2026 results"}],
            _runway(180_600_000, 112_000_000)),
    "RHI": (3, [{"date": "2026-10-22", "kind": "earnings (ESTIMATE)", "detail": "last 8-K item 2.02 + 91 days"}],
            _runway(324_714_000, -62_299_000)),
}


def _flags(t: str) -> list[str]:
    n, cats, rw = OWNER_NAMES[t]
    return [k for k, v in B.risk_checks(n, cats, rw, TODAY).items() if v["on"]]


@pytest.mark.parametrize("ticker", ["KYTX", "SLDP", "SOC"])
def test_owner_named_high_risk_names_carry_the_badge(ticker):
    assert len(_flags(ticker)) >= B.BADGE_MIN_FLAGS


def test_novt_is_flagged_but_one_flag_is_not_the_badge():
    assert _flags("NOVT") == ["coverage"]


def test_qubt_carries_none_of_the_three_declared_flags():
    """Pinned as MEASURED, not as wished: 4 firms with a dated target in 180 days,
    8.2 quarters of cash on the latest operating loss, no FDA/trial event. The owner
    reads QUBT as high-risk; the three declared checks do not. That gap is reported,
    not fixed by moving a threshold until QUBT trips it."""
    assert _flags("QUBT") == []


@pytest.mark.parametrize("ticker", ["MAN", "RHI"])
def test_staffing_companies_are_not_innovation(ticker):
    assert _flags(ticker) == []


def test_binary_regex_catches_the_fda_words_and_not_agenda():
    for txt in ("rolling BLA submission", "PDUFA date", "CRL received", "sNDA filed", "topline readout",
                "Phase 3 data", "Complete Response Letter"):
        assert B.BINARY_RE.search(txt), txt
    assert not B.BINARY_RE.search("investor day agenda")


def test_binary_event_outside_the_window_does_not_flag():
    far = [{"date": "2027-06-30", "kind": "regulatory", "detail": "PDUFA"}]
    assert B.risk_checks(10, far, None, TODAY)["binary_event"]["on"] is False


def test_runway_without_xbrl_is_unknown_not_safe():
    assert B.risk_checks(10, [], None, TODAY)["runway"]["on"] is None


def test_cards_split_never_quotes_a_card_written_after_the_freeze():
    cards = [("2026-09-25", {"v": "pre"}), ("2026-09-27", {"v": "post"})]
    pre_day, pre, now_day, now = B.cards_split(cards, "2026-09-25")
    assert (pre_day, pre["v"], now_day, now["v"]) == ("2026-09-25", "pre", "2026-09-27", "post")
    assert B.cards_split(cards, "2026-09-24")[:2] == (None, None)


# ── a whole row through build_row ──

def _ctx(**over) -> dict:
    ctx = {"today": TODAY, "asof": TODAY, "cards": {}, "facts": {}, "yf": {}, "mw": {}, "identity": {},
           "px": {}, "targets": {}, "revisions": {}, "revisions_pulled": "pulled 2026-09-29", "revision_through": "2026-09-29",
           "official": {"insiders": {}, "insider_table_first_public_utc": "2026-09-18T00:00:00+00:00",
                        "issuer_names": {}, "short_interest": {}, "politicians": {}},
           "news": {}, "earn_cache": {}, "ciks": {}, "spy_dates": [], "dated_firms": {}, "dated_firms_ok": True,
           "runway": {}, "insider_window_days": 18}
    ctx.update(over)
    return ctx


LIST = {"list_id": "book_x", "kind": "book", "asof": "2026-09-25", "frozen_utc": "2026-09-25T09:58:15+00:00",
        "horizon": "126 sessions", "evidence_default": "EARLY_EVIDENCE"}


def _entry(t: str) -> dict:
    return {"ticker": t, "weight": 0.05, "thesis": "held for the theme", "falsifier": "a dated miss"}


def test_positive_stance_beside_negative_upside_is_marked_and_upside_is_low():
    ctx = _ctx(px={"EXEL": {"close": 58.85, "date": "2026-10-05", "source": "fixture", "sigma63": 0.02, "n_obs": 63}},
               targets={"EXEL": {"low": 40.0, "median": 52.5, "high": 70.0, "mean": 53.0, "snapshot_price": 57.0,
                                 "observed_utc": "2026-09-29T14:00:00+00:00"}},
               yf={"EXEL": {"n": 20, "key": "buy"}},
               revisions={"EXEL": {"net_raises": 2.0, "n_firms": 4.0, "median_target_change": 0.05, "n_events": 4.0}})
    r = B.build_row(_entry("EXEL"), LIST, ctx)
    assert r["analyst_stance"]["label"] == "POSITIVE"
    assert r["analyst_stance"]["conflicts_with_upside"] is True
    assert r["upside"]["median"] < 0 and r["upside"]["low_upside"] is True
    assert r["upside"]["targets_date"] == "2026-09-29" and r["upside"]["price_date"] == "2026-10-05"


def test_single_target_is_labelled():
    ctx = _ctx(px={"FIZZ": {"close": 29.84, "date": "2026-10-05", "source": "fixture", "sigma63": 0.02, "n_obs": 63}},
               targets={"FIZZ": {"low": 31.0, "median": 31.0, "high": 31.0, "mean": 31.0, "snapshot_price": 30.0,
                                 "observed_utc": "2026-09-29T14:00:00+00:00"}},
               yf={"FIZZ": {"n": 1, "key": "hold"}})
    r = B.build_row(_entry("FIZZ"), LIST, ctx)
    assert r["upside"]["single_target"] is True and r["upside"]["n_targets"] == 1
    assert r["upside"]["low_upside"] is True          # +3.9% < +5%


def test_why_picked_uses_only_pre_freeze_cards_and_no_fundamentals_filler():
    pre = {"ticker": "VRT", "verdict": "supports", "confidence": "med", "bull": "pre-freeze bull"}
    post = {"ticker": "VRT", "verdict": "neutral", "confidence": "med", "bull": "written later"}
    ctx = _ctx(cards={"VRT": [("2026-09-24", pre), ("2026-09-27", post)]},
               facts={"VRT": {"fund": 0.37, "n_legs": 5}})
    r = B.build_row(_entry("VRT"), LIST, ctx)
    text = " ".join(w["reason"] for w in r["why_picked"])
    assert "pre-freeze bull" in text and "written later" not in text
    assert "fundamentals" not in text
    assert r["later_commentary"]["day"] == "2026-09-27"
    assert r["card"]["day"] == "2026-09-24"


def test_insider_null_reason_states_the_real_coverage_window():
    r = B.build_row(_entry("VRT"), LIST, _ctx())
    msg = r["missing_because"]["insiders"]
    assert "since 2026-09-18" in msg and "18 days" in msg and "NOT a 180-day" in msg


def test_staleness_reads_the_receipt_stamp_and_goes_red():
    now = datetime(2026, 10, 10, tzinfo=timezone.utc)
    assert O.staleness({"generated_utc": "2026-10-06T16:00:00+00:00"}, now, 3)["status"] == "STALE"
    assert O.staleness({"generated_utc": "2026-10-09T16:00:00+00:00"}, now, 3)["status"] == "FRESH"
    assert O.staleness({}, now, 3)["status"] == "UNKNOWN"     # undateable is never fresh
