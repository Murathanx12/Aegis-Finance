"""C16 (2026-10-07) + review fixes F1-F12: public-flow SENSORS -- USAspending, Senate
LDA, crypto risk appetite, Kalshi storage, the task_keeper owner, the fiscal cells.
Offline: every HTTP call is served from saved fixtures (`fixtures/public_flow/`;
the USAspending and crypto files are trimmed LIVE responses, the LDA page is
constructed from the documented schema because the host answered 403 -- its
`_note` says so)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend import config
from backend.services import crypto_market as CM
from backend.services import lobbying_lda as LDA
from backend.services import public_flow_common as PF
from backend.services import usaspending_awards as USA

FX = Path(__file__).parent / "fixtures" / "public_flow"
WEEKDAY = datetime(2026, 10, 7, 20, 0, tzinfo=timezone.utc)     # Wednesday, US evening
SATURDAY = datetime(2026, 10, 10, 20, 0, tzinfo=timezone.utc)
HOLIDAY = datetime(2026, 10, 12, 20, 0, tzinfo=timezone.utc)     # Columbus Day (Monday)


def _fx(name: str) -> bytes:
    return (FX / name).read_bytes()


def _cw():
    return PF.load_crosswalk()


def _serve(body: bytes, status: int = 200, calls: list | None = None):
    def http(method, url, headers, json_body, timeout):
        if calls is not None:
            calls.append((method, url, json_body))
        return status, body, "application/json"
    return http


def _page(results=None, **meta) -> dict:
    d = json.loads(_fx("usaspending_transactions_page.json"))
    if results is not None:
        d["results"] = results
    d["page_metadata"] = {**d["page_metadata"], "hasNext": False, **meta}
    return d


def _usa(pages: list[dict] | dict, count: int | None = None, calls: list | None = None,
         asc_pages: list[dict] | None = None):
    """Serve transaction pages (by page number and order) and the count endpoint."""
    pages = pages if isinstance(pages, list) else [pages]

    def http(method, url, headers, body, timeout):
        if calls is not None:
            calls.append((url, body))
        if url.endswith("spending_by_transaction_count/"):
            n = count if count is not None else sum(len(p["results"]) for p in pages)
            return 200, json.dumps({"results": {"contracts": n}}).encode(), "application/json"
        src = asc_pages if (asc_pages is not None and body.get("order") == "asc") else pages
        return 200, json.dumps(src[body["page"] - 1]).encode(), "application/json"
    return http


def _txn(gid: str, mod: str, date: str = "2026-09-30", amount: float = 100.0,
         name: str = "LOCKHEED MARTIN CORP", agency: str = "Department of Defense") -> dict:
    return {"Award ID": gid, "Recipient Name": name, "Recipient UEI": None, "Action Date": date,
            "Action Type": "B", "Transaction Amount": amount, "Awarding Agency": agency,
            "Awarding Sub Agency": agency, "Award Type": "DEFINITIVE CONTRACT", "Mod": mod,
            "generated_internal_id": f"CONT_AWD_{gid}", "internal_id": 1, "PSC": {"code": "1820"}}


# ───────────────────────────── crosswalk ─────────────────────────────────────

class TestCrosswalk:
    def test_the_shipped_crosswalk_loads_dated(self):
        cw = _cw()
        assert len(cw) >= 60 and {e["confidence"] for e in cw} == {"high", "medium", "low"}
        assert any(e["valid_from"] for e in cw) and any(e["valid_to"] for e in cw)

    def test_missing_empty_bad_confidence_and_bad_date_refuse(self, tmp_path):
        with pytest.raises(PF.PublicFlowRefused, match="NO_CROSSWALK"):
            PF.load_crosswalk(tmp_path / "nope.yaml")
        (tmp_path / "e.yaml").write_text("entries: []\n", encoding="utf-8")
        with pytest.raises(PF.PublicFlowRefused, match="EMPTY_CROSSWALK"):
            PF.load_crosswalk(tmp_path / "e.yaml")
        (tmp_path / "b.yaml").write_text(
            "entries:\n  - {ticker: X, confidence: certain, recipient_patterns: [X CORP]}\n", encoding="utf-8")
        with pytest.raises(PF.PublicFlowRefused, match="confidence"):
            PF.load_crosswalk(tmp_path / "b.yaml")
        (tmp_path / "d.yaml").write_text(
            "entries:\n  - {ticker: X, confidence: high, valid_from: soon, recipient_patterns: [X CORP]}\n",
            encoding="utf-8")
        with pytest.raises(PF.PublicFlowRefused, match="not a date"):
            PF.load_crosswalk(tmp_path / "d.yaml")

    def test_confidence_propagates_from_the_matched_entry(self):
        cw = _cw()
        m = PF.match_entity("NATIONAL TECHNOLOGY & ENGINEERING SOLUTIONS OF SANDIA, LLC", cw, on="2025-01-01")
        assert (m["ticker"], m["crosswalk_confidence"]) == ("HON", "low")
        m = PF.match_entity("HONEYWELL FEDERAL MANUFACTURING & TECHNOLOGIES, LLC", cw, on="2025-01-01")
        assert (m["ticker"], m["crosswalk_confidence"]) == ("HON", "low")
        assert PF.match_entity("FLUOR MARINE PROPULSION LLC", cw, on="2025-01-01")["crosswalk_confidence"] == "low"
        assert PF.match_entity("LOCKHEED MARTIN CORP", cw, on="2025-01-01")["crosswalk_confidence"] == "high"

    def test_dates_decide_the_owner(self):
        cw = _cw()
        assert PF.match_entity("RAYTHEON COMPANY", cw, on="2019-05-01")["match_status"] == "NOT_MAPPED"
        assert PF.match_entity("RAYTHEON COMPANY", cw, on="2021-05-01")["ticker"] == "RTX"
        assert PF.match_entity("SCIENCE APPLICATIONS INTERNATIONAL CORP", cw, on="2012-01-01")["ticker"] == "LDOS"
        assert PF.match_entity("SCIENCE APPLICATIONS INTERNATIONAL CORP", cw, on="2020-01-01")["ticker"] == "SAIC"
        assert PF.match_entity("JACOBS TECHNOLOGY INC", cw, on="2024-01-01")["ticker"] == "J"
        assert PF.match_entity("JACOBS TECHNOLOGY INC", cw, on="2025-01-01")["ticker"] == "AMTM"
        assert PF.match_entity("AEROJET ROCKETDYNE INC", cw, on="2020-01-01")["match_status"] == "NOT_MAPPED"
        assert PF.match_entity("DYNETICS, INC.", cw, on="2026-09-01")["ticker"] == "LDOS"

    def test_prefix_false_positives_are_gone(self):
        cw = _cw()
        assert PF.match_entity("LOCKHEEDVILLE WATER DISTRICT", cw, on="2025-01-01")["match_status"] == "NOT_MAPPED"
        assert PF.match_entity("ANTHEM ARCHITECTS LLC", cw, on="2025-01-01")["match_status"] == "NOT_MAPPED"
        assert PF.match_entity("MERCK KGAA", cw, "lda_client_patterns", on="2026-06-30")["match_status"] == "NOT_MAPPED"
        assert PF.match_entity("JACOBS ARCHITECTURE", cw, "lda_client_patterns",
                               on="2026-06-30")["match_status"] == "NOT_MAPPED"

    def test_tie_between_tickers_is_ambiguous_and_lower_confidence_binds(self):
        cw = [{"ticker": "AAA", "confidence": "high", "recipient_patterns": ["ACME"], "uei": []},
              {"ticker": "BBB", "confidence": "high", "recipient_patterns": ["ACME"], "uei": []}]
        assert PF.match_entity("ACME INC", cw)["match_status"] == "AMBIGUOUS"
        cw2 = [{"ticker": "AAA", "confidence": "high", "recipient_patterns": ["ACME"], "uei": []},
               {"ticker": "AAA", "confidence": "low", "recipient_patterns": ["ACME"], "uei": []}]
        assert PF.match_entity("ACME INC", cw2)["crosswalk_confidence"] == "low"

    def test_a_known_uei_wins_only_in_the_uei_era(self):
        m = PF.match_entity("SOME RENAMED ENTITY", _cw(), uei="fyhna5wc8xd7", on="2025-01-01")
        assert (m["ticker"], m["crosswalk_pattern"]) == ("LMT", "UEI:FYHNA5WC8XD7")
        assert PF.match_entity("SOME RENAMED ENTITY", _cw(), uei="fyhna5wc8xd7",
                               on="2019-01-01")["match_status"] == "NOT_MAPPED"


# ───────────────────────────── USAspending ───────────────────────────────────

class TestUSAspending:
    def test_parser_on_a_saved_live_page(self):
        rows = USA.parse_transactions(json.loads(_fx("usaspending_transactions_page.json")), _cw())
        assert len(rows) == 5 and {r["ticker"] for r in rows} == {"GD"}
        assert all(r["identity"].startswith("usaspending:CONT_") and "|" in r["identity"] for r in rows)
        assert any((r["obligation_usd"] or 0) < 0 for r in rows)
        assert all(r["public_ts_basis"] == "FIRST_SEEN_BY_COLLECTOR" for r in rows)

    def test_identity_is_award_plus_mod_never_the_amount(self):
        a = USA.identity_of({"generated_internal_id": "CONT_AWD_X", "Mod": "P00011", "Transaction Amount": 1})
        b = USA.identity_of({"generated_internal_id": "CONT_AWD_X", "Mod": "P00011", "Transaction Amount": 9})
        c = USA.identity_of({"generated_internal_id": "CONT_AWD_X", "Mod": "P00012", "Transaction Amount": 1})
        assert a == b != c

    def test_a_corrected_amount_is_a_revision_not_a_second_row(self, tmp_path):
        kw = dict(mode="action", days=90, limit_recipients=1, base=tmp_path, sleep_fn=lambda s: None)
        USA.pull(http=_usa(_page([_txn("A1", "1", amount=100.0)])), now=WEEKDAY, **kw)
        r = USA.pull(http=_usa(_page([_txn("A1", "1", amount=250.0)])), now=WEEKDAY, **kw)
        assert r["revisions"] == 1 and r["rows_added"] == 0
        rows = PF.read_table(USA.TABLE, tmp_path)
        assert len(rows) == 2 and rows[1]["supersedes"] == rows[0]["row_id"]
        latest = USA.latest_rows(tmp_path)
        assert len(latest) == 1 and latest[0]["obligation_usd"] == 250.0
        assert sum(a["obligation_usd"] for a in USA.aggregate_month_agency(rows)) == 250.0
        same = USA.pull(http=_usa(_page([_txn("A1", "1", amount=250.0)])), now=WEEKDAY, **kw)
        assert same["unchanged"] == 1 and same["revisions"] == 0

    def test_receipt_dollars_equal_table_dollars(self, tmp_path):
        page = _page([_txn("A1", "1", amount=100.0), _txn("A2", "1", amount=50.5)])
        r = USA.pull(mode="action", days=90, limit_recipients=1, base=tmp_path,
                     http=_usa(page), sleep_fn=lambda s: None, now=WEEKDAY)
        table = sum(x["obligation_usd"] for x in USA.latest_rows(tmp_path) if x["match_status"] == "MAPPED")
        assert r["obligation_usd_mapped_this_pull"] == table == 150.5

    def test_unstable_paging_is_reconciled_by_a_reverse_read(self, tmp_path):
        """The GD case: page 2 repeats a row of page 1 and one row is never served."""
        t = [_txn(f"A{i}", "1") for i in range(4)]
        desc = [_page(t[0:2], hasNext=True), _page([t[1], t[2]])]           # t[3] never served, t[1] twice
        asc = [_page([t[3], t[2]], hasNext=True), _page([t[1], t[0]])]
        calls: list = []
        r = USA.pull(mode="action", days=90, limit_recipients=1, base=tmp_path,
                     http=_usa(desc, count=4, calls=calls, asc_pages=asc), sleep_fn=lambda s: None, now=WEEKDAY)
        rec = next(iter(r["per_recipient"].values()))
        assert rec["repeats_in_first_read"] == 1 and rec["retried_opposite_order"]
        assert rec["status"] == "OK" and rec["distinct_read"] == rec["api_count"] == 4
        assert len(PF.read_table(USA.TABLE, tmp_path)) == 4

    def test_a_recipient_that_does_not_reconcile_is_refused_and_writes_nothing(self, tmp_path):
        page = _page([_txn("A1", "1"), _txn("A2", "1")])
        r = USA.pull(mode="action", days=90, limit_recipients=1, base=tmp_path,
                     http=_usa(page, count=3), sleep_fn=lambda s: None, now=WEEKDAY)
        rec = next(iter(r["per_recipient"].values()))
        assert rec["status"] == "REFUSED_UNRECONCILED" and r["status"] != "OK"
        assert PF.read_table(USA.TABLE, tmp_path) == []

    def test_modified_mode_filters_on_last_modified_and_keeps_old_actions(self, tmp_path):
        """F1: a DoD action ~90 days old published today is seen and stored."""
        calls: list = []
        page = _page([_txn("D1", "1", date="2026-07-15"), _txn("D2", "1", date="2026-01-02")])
        r = USA.pull(mode="modified", limit_recipients=1, base=tmp_path, http=_usa(page, calls=calls),
                     sleep_fn=lambda s: None, now=WEEKDAY)
        tp = calls[0][1]["filters"]["time_period"][0]
        assert tp["date_type"] == "last_modified_date"
        assert calls[0][1]["sort"] == config.USASPENDING_SORT == "Award ID"
        stored = PF.read_table(USA.TABLE, tmp_path)
        assert [x["action_date"] for x in stored] == ["2026-07-15"]        # inside the 120-day window
        assert r["outside_action_window"] == 1

    def test_backfill_rows_carry_no_latency_and_later_rows_do(self, tmp_path):
        """F3: a first contact's rows all share one first_seen; only later rows measure latency."""
        kw = dict(mode="modified", limit_recipients=1, base=tmp_path, sleep_fn=lambda s: None)
        first = USA.pull(http=_usa(_page([_txn("B1", "1", date="2026-09-20")])), now=WEEKDAY, **kw)
        assert first["latency_first_seen_minus_action"] == {"n": 0, "n_backfill_not_measurable": 1}
        assert PF.read_table(USA.TABLE, tmp_path)[0]["latency"] == PF.BACKFILL_LATENCY
        later = datetime(2026, 10, 8, 20, 0, tzinfo=timezone.utc)
        second = USA.pull(http=_usa(_page([_txn("B1", "1", date="2026-09-20"),
                                           _txn("B2", "1", date="2026-09-25")])), now=later, **kw)
        lat = second["latency_first_seen_minus_action"]
        assert lat["n"] == 1 and lat["median_days"] == 13.0

    def test_zero_new_rows_weekday_degraded_weekend_and_holiday_ok(self, tmp_path):
        kw = dict(mode="action", days=90, limit_recipients=1, base=tmp_path, sleep_fn=lambda s: None)
        USA.pull(http=_usa(_page()), now=WEEKDAY, **kw)
        assert USA.pull(http=_usa(_page()), now=WEEKDAY, **kw)["status"] == "DEGRADED"
        assert USA.pull(http=_usa(_page()), now=SATURDAY, **kw)["status"] == "OK"
        assert USA.pull(http=_usa(_page()), now=HOLIDAY, **kw)["status"] == "OK"
        assert not PF.is_us_weekday(HOLIDAY) and PF.is_us_weekday(WEEKDAY)

    def test_a_zero_row_target_with_expected_activity_is_degraded(self, tmp_path):
        """F12: HUMANA's case -- a long first contact that returns nothing."""
        r = USA.pull(mode="action", days=90, limit_recipients=2, base=tmp_path,
                     http=_usa(_page([])), sleep_fn=lambda s: None, now=SATURDAY)
        assert r["status"] == "DEGRADED"
        assert set(r["degraded_targets"].values()) == {"DEGRADED_ZERO_ROWS"}

    def test_an_action_date_after_first_seen_is_refused_not_written(self, tmp_path):
        early = datetime(2026, 9, 1, tzinfo=timezone.utc)
        r = USA.pull(mode="action", days=90, limit_recipients=1, base=tmp_path, http=_usa(_page()),
                     sleep_fn=lambda s: None, now=early)
        assert r["pit_refused"] == 5 and PF.read_table(USA.TABLE, tmp_path) == []

    def test_access_denied_is_named_and_stops_asking(self, tmp_path):
        calls: list = []
        r = USA.pull(mode="action", days=90, limit_recipients=5, base=tmp_path,
                     http=_serve(b"<html>Access Denied</html>", 403, calls), sleep_fn=lambda s: None,
                     now=WEEKDAY)
        assert r["status"] == "REFUSED" and len(calls) == 1
        assert r["refusals"][0]["why"].startswith("ACCESS_DENIED")

    def test_429_is_rate_limited_fatal_and_stops(self, tmp_path):
        calls: list = []
        r = USA.pull(mode="action", days=90, limit_recipients=5, base=tmp_path,
                     http=_serve(b"slow down", 429, calls), sleep_fn=lambda s: None, now=WEEKDAY)
        assert r["status"] == "REFUSED" and len(calls) == 1
        assert r["refusals"][0]["why"].startswith("RATE_LIMITED") and r["refusals"][0]["fatal"]

    def test_the_rate_limit_is_honoured_with_a_sleep(self, tmp_path):
        slept: list = []
        USA.pull(mode="action", days=90, limit_recipients=2, base=tmp_path, http=_usa(_page()),
                 sleep_fn=slept.append, now=WEEKDAY)
        assert len(slept) >= 3 and all(0 < s <= config.USASPENDING_MIN_GAP_S for s in slept)


class TestAgencyMonths:
    def test_partial_and_settled_per_row(self):
        rows = USA.parse_agency_months(json.loads(_fx("usaspending_agency_months.json")),
                                       "Department of Defense", "2026-10-07")
        oct26 = [r for r in rows if r["calendar_month"] == "2026-10"][0]
        sep26 = [r for r in rows if r["calendar_month"] == "2026-09"][0]
        assert oct26["partial"] and not sep26["partial"]
        assert not sep26["settled"] and sep26["settle_days"] == 100
        oct25 = [r for r in rows if r["calendar_month"] == "2025-10"][0]
        assert oct25["settled"]                                   # 2025-10-31 + 100 d < 2026-10-07
        other = USA.parse_agency_months(json.loads(_fx("usaspending_agency_months.json")),
                                        "Department of Energy", "2026-10-07")
        assert [r for r in other if r["calendar_month"] == "2026-07"][0]["settled"]   # +45 d

    def test_fiscal_calendar_and_q4_share_of_one_snapshot(self):
        rows = USA.parse_agency_months(json.loads(_fx("usaspending_agency_months.json")),
                                       "Department of Energy", "2026-10-07")
        assert USA.fiscal_to_calendar(2026, 1) == (2025, 10) and USA.fiscal_to_calendar(2026, 12) == (2026, 9)
        q = USA.q4_share(rows)["Department of Energy"]["2026"]
        assert q["complete"] and not q["settled"] and 0 < q["q4_share"] < 1

    def test_q4_share_refuses_mixed_snapshots(self):
        a = USA.parse_agency_months(json.loads(_fx("usaspending_agency_months.json")), "X", "2026-10-07")
        b = USA.parse_agency_months(json.loads(_fx("usaspending_agency_months.json")), "X", "2026-10-08")
        with pytest.raises(PF.PublicFlowRefused, match="MIXED_SNAPSHOTS"):
            USA.q4_share(a + b)

    def test_as_of_reader_cannot_be_changed_by_a_later_snapshot(self):
        a = USA.parse_agency_months(json.loads(_fx("usaspending_agency_months.json")), "X", "2026-10-07")
        later = [{**r, "snapshot_date": "2026-11-20", "contract_obligations_usd": 1e12} for r in a]
        before = USA.agency_months_as_of("2026-10-10", rows=a)
        after = USA.agency_months_as_of("2026-10-10", rows=a + later)
        assert before == after and {r["snapshot_date"] for r in after} == {"2026-10-07"}
        assert USA.agency_months_as_of("2026-10-06", rows=a + later) == []
        with pytest.raises(PF.PublicFlowRefused, match="NO_AS_OF"):
            USA.agency_months_as_of("someday", rows=a)


# ───────────────────────────── LDA ───────────────────────────────────────────

class TestLDA:
    def test_parser_keeps_filing_date_and_period_apart(self):
        rows = LDA.parse_filings(json.loads(_fx("lda_filings_page.json")), _cw())
        a, b, c = rows
        assert (a["period_start"], a["period_end"]) == ("2026-04-01", "2026-06-30")
        assert a["dt_posted"] == "2026-07-18T18:02:11+00:00" and a["public_ts_basis"] == "LDA_DT_POSTED"
        assert a["self_filer"] and a["amount_kind"] == "expenses" and a["amount_usd"] == 3250000.0
        assert not b["self_filer"] and b["amount_kind"] == "income" and b["amount_usd"] == 80000.0
        assert a["ticker"] == b["ticker"] == "LMT" and c["match_status"] == "NOT_MAPPED"

    def test_totals_do_not_add_outside_income_to_self_filer_expenses(self):
        rows = LDA.parse_filings(json.loads(_fx("lda_filings_page.json")), _cw())
        t = LDA.lobbying_totals(rows)
        assert t["LMT|2026-06-30"]["amount_usd"] == 3250000.0
        assert t["LMT|2026-06-30"]["basis"] == "self-filer expenses"

    def test_an_amendment_supersedes_its_original(self):
        rows = LDA.parse_filings(json.loads(_fx("lda_filings_page.json")), _cw())
        amend = {**rows[0], "row_id": "lda:amend", "filing_type": "2A", "amount_usd": 3500000.0,
                 "dt_posted": "2026-08-01T00:00:00+00:00"}
        assert LDA.lobbying_totals(rows + [amend])["LMT|2026-06-30"]["amount_usd"] == 3500000.0

    def test_wanted_periods_are_completed_quarters(self):
        assert LDA.wanted_periods(WEEKDAY, 2) == [(2026, "third_quarter"), (2026, "second_quarter")]
        assert LDA.wanted_periods(datetime(2026, 2, 1, tzinfo=timezone.utc), 1) == [(2025, "fourth_quarter")]

    def test_pull_on_a_fixture_is_a_backfill_and_quiet_rerun_is_ok(self, tmp_path):
        kw = dict(quarters=1, limit_clients=1, base=tmp_path, sleep_fn=lambda s: None, now=WEEKDAY)
        r = LDA.pull(http=_serve(_fx("lda_filings_page.json")), **kw)
        assert r["rows_added"] == 3 and r["status"] == "OK" and "Senate Office of Public Records" in r["citation"]
        assert r["latency_first_seen_minus_posted"]["n"] == 0
        assert r["lobbying_usd_by_ticker_period"]["LMT|2026-06-30"]["amount_usd"] == 3250000.0
        again = LDA.pull(http=_serve(_fx("lda_filings_page.json")), **kw)
        assert again["rows_added"] == 0 and again["status"] == "OK"

    def test_an_edge_403_is_access_denied_not_bot_check(self, tmp_path):
        calls: list = []
        r = LDA.pull(quarters=2, limit_clients=3, base=tmp_path,
                     http=_serve(b"<HTML><TITLE>Access Denied</TITLE></HTML>", 403, calls),
                     sleep_fn=lambda s: None, now=WEEKDAY)
        assert r["status"] == "REFUSED" and len(calls) == 1
        assert r["refusals"][0]["why"].startswith("ACCESS_DENIED")
        assert r["request_classes"] == {"ACCESS_DENIED": 1}


def test_a_feed_that_answers_nothing_for_every_target_is_degraded(tmp_path):
    empty = json.dumps({"results": [], "page_metadata": {"hasNext": False}, "next": None}).encode()
    q = LDA.pull(quarters=1, limit_clients=2, base=tmp_path, http=_serve(empty),
                 sleep_fn=lambda s: None, now=SATURDAY)
    assert q["status"] == "DEGRADED"


# ───────────────────────────── crypto sensor ─────────────────────────────────

def _crypto_get(fail: str | None = None):
    def get(url, params=None):
        if fail and fail in url:
            raise ConnectionError("boom")
        if "stablecoins" in url:
            return json.loads(_fx("defillama_stablecoins.json"))
        if "fundingRate" in url:
            return json.loads(_fx("binance_funding_btc.json"))
        if "funding-rate" in url:
            return json.loads(_fx("okx_funding_btc.json"))
        if "simple/price" in url:
            return json.loads(_fx("coingecko_simple_price.json"))
        raise AssertionError(url)
    return get


class TestCryptoSensor:
    def test_snapshot_ok_with_timestamps(self, tmp_path, monkeypatch):
        monkeypatch.setattr(CM, "_sensor_get", _crypto_get())
        r = CM.risk_sensor_snapshot(base=tmp_path, now=WEEKDAY)
        row = r["row"]
        assert r["status"] == "OK" and r["rows_added"] == 1
        assert row["usd_stablecoin_supply"] > 0 and row["btc_usd"] > 0 and row["btc_funding_8h_avg"] is not None
        f = row["components"]["funding"]["value"][0]
        assert f["settled_utc"] and f["venue"] == "binance"

    def test_a_failed_component_is_degraded_and_never_zero(self, tmp_path, monkeypatch):
        monkeypatch.setattr(CM, "_sensor_get", _crypto_get(fail="okx"))
        r = CM.risk_sensor_snapshot(base=tmp_path, now=WEEKDAY)
        assert r["status"] == "DEGRADED" and r["row"]["btc_funding_8h_avg"] is None
        assert r["row"]["components"]["funding"]["status"] == "REFUSED"

    def test_all_components_failing_is_refused(self, tmp_path, monkeypatch):
        def dead(url, params=None):
            raise ConnectionError("down")
        monkeypatch.setattr(CM, "_sensor_get", dead)
        assert CM.risk_sensor_snapshot(base=tmp_path, now=WEEKDAY)["status"] == "REFUSED"

    def test_the_tables_are_gitignored(self):
        gi = (Path(__file__).resolve().parents[2] / ".gitignore").read_text(encoding="utf-8")
        assert "backend/data/optimus/public_flow/tables/" in gi


# ───────────────────────────── Kalshi storage ────────────────────────────────

def _kalshi_rows():
    def row(ticker, mid, cat="Economics", oi=100.0):
        return {"source": "kalshi", "ticker": ticker, "mid": mid, "category": cat,
                "open_interest": oi, "title": "t", "yes_bid": mid, "yes_ask": mid}
    return [row("KXFEDDECISION-26DEC-H0", 0.6), row("KXFEDDECISION-26DEC-C25", 0.3),
            row("KXFEDDECISION-26DEC-C26", 0.05), row("KXFEDDECISION-26DEC-H25", 0.03),
            row("KXFEDDECISION-26DEC-H26", 0.02), row("KXCPI-26NOV-T3.0", 0.4, "Economics")]


class TestKalshiStorage:
    @pytest.fixture
    def pm(self, tmp_path, monkeypatch):
        from backend.services import prediction_markets as P
        monkeypatch.setattr(config, "PREDICTION_MARKET_DIR", tmp_path / "pm")
        monkeypatch.setitem(P.SOURCES, "kalshi", lambda now=None: {
            "rows": _kalshi_rows(), "events_seen": 2, "pages": 1, "pages_truncated": False})
        return P, tmp_path / "pm"

    def test_default_is_none_until_d18(self):
        assert config.PREDMARKET_KALSHI_STORAGE == "none"

    def test_none_keeps_only_the_receipt(self, pm, monkeypatch):
        P, d = pm
        monkeypatch.setattr(config, "PREDMARKET_KALSHI_STORAGE", "none")
        assert P._snapshot_source("kalshi", WEEKDAY)["status"] == "ok_receipt_only"
        assert not (d / "derived").exists() and not (d / "snapshots").exists()

    def test_derived_only_writes_no_raw_rows(self, pm, monkeypatch):
        P, d = pm
        monkeypatch.setattr(config, "PREDMARKET_KALSHI_STORAGE", "derived_only")
        r = P._snapshot_source("kalshi", WEEKDAY)
        assert r["status"] == "ok_derived_only" and r["rows_written"] == 0 and r["rows_seen"] == 6
        assert not (d / "snapshots").exists()
        doc = json.loads((d / "derived" / "2026-10-07.kalshi.json").read_text(encoding="utf-8"))
        meet = doc["regime_variables"]["fed_decision_by_meeting"]["2026-12"]
        assert meet["complete"] and abs(sum(meet["implied_distribution"].values()) - 1) < 1e-3
        assert meet["expected_change_bps"] < 0 and "KXCPI" not in json.dumps(doc)
        assert P._snapshot_source("kalshi", WEEKDAY)["status"] == "already_written"

    def test_unknown_mode_refuses_rather_than_storing_raw(self, pm, monkeypatch):
        P, _ = pm
        monkeypatch.setattr(config, "PREDMARKET_KALSHI_STORAGE", "everything")
        with pytest.raises(P.PredictionMarketFetchError):
            P._snapshot_source("kalshi", WEEKDAY)


# ───────────────────────────── owners and cells ──────────────────────────────

class TestOwners:
    def test_task_keeper_public_flow_logs_each_step(self, tmp_path):
        from scripts import task_keeper as K
        out = K.run_public_flow(now_utc=WEEKDAY, log_path=tmp_path / "pf.jsonl", steps={
            "usaspending": lambda: {"status": "DEGRADED", "rows_added": 0},
            "lda": None,
            "crypto": lambda: (_ for _ in ()).throw(RuntimeError("down"))})
        assert out["action"] == "degraded"
        assert out["lda"]["status"] == "NOT_DUE" and out["crypto"]["status"] == "REFUSED"

    def test_lda_is_weekly_by_its_own_receipt_stamp(self):
        from scripts import task_keeper as K
        assert K.lda_due(WEEKDAY, None)
        assert not K.lda_due(WEEKDAY, {"written_utc": "2026-10-05T00:00:00+00:00"})
        assert K.lda_due(WEEKDAY, {"written_utc": "2026-09-29T00:00:00+00:00"})
        assert "AegisPublicFlow" in K.CATCHUP_TASKS

    def test_the_fiscal_cells_are_declared_only_and_run_refuses(self, capsys):
        from scripts import hyp_theory_cells as H
        for cell in ("fiscal_year_end_spending", "fiscal_year_end_dose"):
            c = H.CELLS[cell]
            assert c["declared_only"] and c["fy_gate"] and "separation_from_beta" in c
            assert H.part_run(cell, "TEST") == 2
        assert "DECLARED ONLY" in capsys.readouterr().out
        assert "CALENDAR effect" in H.CELLS["fiscal_year_end_spending"]["precursor"]

    def test_fy_unit_gate_refuses_an_unpowered_cell_and_passes_a_powered_one(self):
        from scripts import hyp_theory_cells as H
        noisy = H.fy_unit_gate([0.03, -0.02, 0.01, -0.03, 0.02, -0.01, 0.0, 0.015], 8, 0.005)
        assert noisy["refused"] and noisy["unit"] == "fiscal year"
        quiet = H.fy_unit_gate([0.001, -0.001, 0.0005, -0.0005, 0.001, 0.0, -0.001, 0.0], 8, 0.005)
        assert not quiet["refused"]


def test_a_row_older_than_the_targets_coverage_carries_no_latency(tmp_path):
    """F3, measured live: a modified-window read returned June rows for a target whose
    backfill began 2026-07-08 -- their lag measures our coverage, not publication."""
    kw = dict(mode="modified", limit_recipients=1, base=tmp_path, sleep_fn=lambda s: None)
    USA.pull(http=_usa(_page([_txn("C1", "1", date="2026-09-01")])), now=WEEKDAY, **kw)
    later = datetime(2026, 10, 8, 20, 0, tzinfo=timezone.utc)
    r = USA.pull(http=_usa(_page([_txn("C2", "1", date="2026-07-01"),
                                  _txn("C3", "1", date="2026-09-20")])), now=later, **kw)
    lat = r["latency_first_seen_minus_action"]
    assert lat["n"] == 1 and lat["n_before_coverage_not_measurable"] == 1 and lat["median_days"] == 18.0
