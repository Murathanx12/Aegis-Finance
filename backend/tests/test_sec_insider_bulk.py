"""
I1 — tests for the SEC Insider Transactions bulk loader.

Every test here is OFFLINE. The fast suite blocks sockets (and curl_cffi), and
a loader whose only proof is "it worked on the live SEC once" is a loader
nobody can re-verify on a Sunday. The fixture below builds a REAL quarterly
ZIP — same member names, same DD-MON-YYYY dates, same four-way boolean
encoding of AFF10B5ONE that the live 2025q1 file actually carries — in a
tmpdir, and the parser is driven against it.

The two tests that matter most:

  * `test_pit_test_goes_red_on_a_lookahead_join` — the guard the lane brief
    asks for. It builds the table the natural WRONG way (observed_at from
    TRANS_DATE) and asserts the guard raises.
  * `test_fabrication_guard_*` — no Form 4 row can be invented.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.services import cmp_insider
from backend.services import sec_insider_bulk as S


# ------------------------------------------------------------------ fixture

SUBMISSION_COLS = [
    "ACCESSION_NUMBER", "FILING_DATE", "PERIOD_OF_REPORT", "DATE_OF_ORIG_SUB",
    "NO_SECURITIES_OWNED", "NOT_SUBJECT_SEC16", "FORM3_HOLDINGS_REPORTED",
    "FORM4_TRANS_REPORTED", "DOCUMENT_TYPE", "ISSUERCIK", "ISSUERNAME",
    "ISSUERTRADINGSYMBOL", "REMARKS", "AFF10B5ONE",
]
OWNER_COLS = [
    "ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNERNAME", "RPTOWNER_RELATIONSHIP",
    "RPTOWNER_TITLE", "RPTOWNER_TXT", "RPTOWNER_STREET1", "RPTOWNER_STREET2",
    "RPTOWNER_CITY", "RPTOWNER_STATE", "RPTOWNER_ZIPCODE", "RPTOWNER_STATE_DESC",
    "FILE_NUMBER",
]
NONDERIV_COLS = [
    "ACCESSION_NUMBER", "NONDERIV_TRANS_SK", "SECURITY_TITLE", "SECURITY_TITLE_FN",
    "TRANS_DATE", "TRANS_DATE_FN", "DEEMED_EXECUTION_DATE", "DEEMED_EXECUTION_DATE_FN",
    "TRANS_FORM_TYPE", "TRANS_CODE", "EQUITY_SWAP_INVOLVED", "EQUITY_SWAP_TRANS_CD_FN",
    "TRANS_TIMELINESS", "TRANS_TIMELINESS_FN", "TRANS_SHARES", "TRANS_SHARES_FN",
    "TRANS_PRICEPERSHARE", "TRANS_PRICEPERSHARE_FN", "TRANS_ACQUIRED_DISP_CD",
    "TRANS_ACQUIRED_DISP_CD_FN", "SHRS_OWND_FOLWNG_TRANS", "SHRS_OWND_FOLWNG_TRANS_FN",
    "VALU_OWND_FOLWNG_TRANS", "VALU_OWND_FOLWNG_TRANS_FN", "DIRECT_INDIRECT_OWNERSHIP",
    "DIRECT_INDIRECT_OWNERSHIP_FN", "NATURE_OF_OWNERSHIP", "NATURE_OF_OWNERSHIP_FN",
]
DERIV_COLS = NONDERIV_COLS[:1] + ["DERIV_TRANS_SK"] + NONDERIV_COLS[2:]
FOOTNOTE_COLS = ["ACCESSION_NUMBER", "FOOTNOTE_ID", "FOOTNOTE_TXT"]


def _tsv(cols: list[str], rows: list[dict]) -> str:
    out = ["\t".join(cols)]
    for r in rows:
        out.append("\t".join(str(r.get(c, "")) for c in cols))
    return "\n".join(out) + "\n"


def _sub(acc: str, filing: str, *, symbol: str = "ACME", cik: str = "0000012345",
         doc: str = "4", aff: str = "0", period: str | None = None) -> dict:
    return {"ACCESSION_NUMBER": acc, "FILING_DATE": filing,
            "PERIOD_OF_REPORT": period or filing, "DOCUMENT_TYPE": doc,
            "ISSUERCIK": cik, "ISSUERNAME": "Acme Corp",
            "ISSUERTRADINGSYMBOL": symbol, "AFF10B5ONE": aff}


def _owner(acc: str, cik: str, rel: str = "Officer", name: str = "Doe John") -> dict:
    return {"ACCESSION_NUMBER": acc, "RPTOWNERCIK": cik, "RPTOWNERNAME": name,
            "RPTOWNER_RELATIONSHIP": rel, "RPTOWNER_TITLE": "CFO"}


def _trans(acc: str, sk: str, trans_date: str, code: str, ad: str,
           shares: str = "1000.0", price: str = "10.0") -> dict:
    return {"ACCESSION_NUMBER": acc, "NONDERIV_TRANS_SK": sk, "DERIV_TRANS_SK": sk,
            "SECURITY_TITLE": "Common Stock", "TRANS_DATE": trans_date,
            "TRANS_FORM_TYPE": "4", "TRANS_CODE": code, "TRANS_SHARES": shares,
            "TRANS_PRICEPERSHARE": price, "TRANS_ACQUIRED_DISP_CD": ad,
            "SHRS_OWND_FOLWNG_TRANS": "50000.0", "DIRECT_INDIRECT_OWNERSHIP": "D"}


#: One purchase, one grant, one sale, one option exercise, one 10b5-1 sale,
#: one pre-2023-style filing whose plan flag is only in the footnote, and one
#: future-dated transaction (the SEC's own tail, 20 of 150,789 rows in the
#: real 2025q1 file).
FIXTURE_SUBS = [
    _sub("0000012345-20-000001", "05-FEB-2020"),
    _sub("0000012345-20-000002", "06-FEB-2020"),
    _sub("0000012345-20-000003", "07-FEB-2020", aff="true"),
    _sub("0000012345-20-000004", "10-FEB-2020", aff=""),      # pre-checkbox shape
    _sub("0000012345-20-000005", "11-FEB-2020", symbol="ZZZZ"),
    _sub("0000012345-20-000006", "12-FEB-2020", doc="4/A"),
]
FIXTURE_OWNERS = [
    _owner("0000012345-20-000001", "0000999001"),
    _owner("0000012345-20-000002", "0000999002", rel="Director"),
    _owner("0000012345-20-000003", "0000999003", rel="Director,Officer"),
    _owner("0000012345-20-000004", "0000999004", rel="TenPercentOwner"),
    _owner("0000012345-20-000005", "0000999005", rel="Other"),
    _owner("0000012345-20-000006", "0000999006"),
]
FIXTURE_NONDERIV = [
    _trans("0000012345-20-000001", "1", "03-FEB-2020", "P", "A"),   # open-market buy
    _trans("0000012345-20-000002", "2", "04-FEB-2020", "A", "A"),   # grant
    _trans("0000012345-20-000003", "3", "05-FEB-2020", "S", "D"),   # 10b5-1 sale
    _trans("0000012345-20-000004", "4", "08-FEB-2020", "P", "A"),   # footnote 10b5-1 buy
    _trans("0000012345-20-000005", "5", "09-FEB-2020", "S", "D"),   # open-market sale
    _trans("0000012345-20-000006", "6", "20-DEC-2020", "P", "A"),   # FUTURE-DATED
]
FIXTURE_DERIV = [
    _trans("0000012345-20-000001", "7", "03-FEB-2020", "M", "A"),   # option exercise
    _trans("0000012345-20-000002", "8", "04-FEB-2020", "P", "A"),   # deriv 'P' - NOT stock
]
FIXTURE_FOOTNOTES = [
    {"ACCESSION_NUMBER": "0000012345-20-000004", "FOOTNOTE_ID": "F1",
     "FOOTNOTE_TXT": "Shares acquired pursuant to a Rule 10b5-1 trading plan."},
    {"ACCESSION_NUMBER": "0000012345-20-000001", "FOOTNOTE_ID": "F1",
     "FOOTNOTE_TXT": "Open market purchase with personal funds."},
]


@pytest.fixture()
def quarter_zip(tmp_path):
    p = tmp_path / "2020q1_form345.zip"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(S.SUBMISSION_TSV, _tsv(SUBMISSION_COLS, FIXTURE_SUBS))
        z.writestr(S.REPORTINGOWNER_TSV, _tsv(OWNER_COLS, FIXTURE_OWNERS))
        z.writestr(S.NONDERIV_TRANS_TSV, _tsv(NONDERIV_COLS, FIXTURE_NONDERIV))
        z.writestr(S.DERIV_TRANS_TSV, _tsv(DERIV_COLS, FIXTURE_DERIV))
        z.writestr(S.FOOTNOTES_TSV, _tsv(FOOTNOTE_COLS, FIXTURE_FOOTNOTES))
    return p


# ------------------------------------------------------------ date handling

def test_parse_sec_date_handles_the_ddmonyyyy_the_files_actually_use():
    assert S.parse_sec_date("31-MAR-2025") == date(2025, 3, 31)
    assert S.parse_sec_date("2025-03-31") == date(2025, 3, 31)
    assert S.parse_sec_date("") is None
    assert S.parse_sec_date(None) is None
    assert S.parse_sec_date("garbage") is None
    assert S.parse_sec_date("31-XXX-2025") is None


def test_observed_at_is_after_the_filing_day_and_derived_from_today_not_a_literal():
    """A fixture must never encode a calendar moment (CLAUDE.md rule 5), so the
    bound is checked relative to `today`, not to a date that ages."""
    today = date.today()
    obs = S.observed_at_utc(today)
    assert obs > datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    assert obs <= datetime(today.year, today.month, today.day,
                           tzinfo=timezone.utc) + timedelta(days=2)
    assert S.next_tradable_session_bound(today) == today + timedelta(days=1)
    assert S.observed_at_utc(None) is None


# --------------------------------------------------------- the code mapping

def test_every_documented_sec_transaction_code_is_mapped():
    """The SEC's Form 345 code table, in full. A code that falls out of the map
    silently becomes UNKNOWN_CODE and is invisible in a book."""
    for code in "PSVADFIMCEHOXGLWZJKU":
        assert code in S.TRANS_CODE_MAP, code
    assert S.classify_trans_code("P")[0] == "OPEN_MARKET_PURCHASE"
    assert S.classify_trans_code("A")[0] == "GRANT_AWARD"
    assert S.classify_trans_code("M")[0] == "OPTION_EXERCISE"
    assert S.classify_trans_code("F")[0] == "TAX_OR_EXERCISE_WITHHOLDING"
    assert S.classify_trans_code("G")[0] == "GIFT"


def test_an_unmapped_code_is_reported_not_dropped():
    cls, label = S.classify_trans_code("Q")
    assert cls == S.UNKNOWN_CODE_CLASS
    assert "Q" in label


def test_only_code_P_acquired_nonderivative_is_a_discretionary_purchase():
    base = {"table": "NONDERIV", "trans_class": "OPEN_MARKET_PURCHASE",
            "acquired_disposed": "A", "plan_10b5_1": S.PLAN_NO, "shares": 100.0}
    assert S.is_discretionary_open_market_purchase(base)
    # a grant is not a purchase
    assert not S.is_discretionary_open_market_purchase({**base, "trans_class": "GRANT_AWARD"})
    # an option exercise is not a purchase
    assert not S.is_discretionary_open_market_purchase({**base, "trans_class": "OPTION_EXERCISE"})
    # buying a DERIVATIVE is not buying the stock
    assert not S.is_discretionary_open_market_purchase({**base, "table": "DERIV"})
    # a 10b5-1 plan trade carries no decision
    assert not S.is_discretionary_open_market_purchase({**base, "plan_10b5_1": S.PLAN_YES})
    # disposed, not acquired
    assert not S.is_discretionary_open_market_purchase({**base, "acquired_disposed": "D"})
    # zero shares is a footnote artefact
    assert not S.is_discretionary_open_market_purchase({**base, "shares": 0.0})


def test_10b5_1_is_never_a_silent_false():
    assert S.resolve_10b5_1("1", False) == (S.PLAN_YES, S.PLAN_SOURCE_CHECKBOX)
    assert S.resolve_10b5_1("true", False) == (S.PLAN_YES, S.PLAN_SOURCE_CHECKBOX)
    assert S.resolve_10b5_1("0", False) == (S.PLAN_NO, S.PLAN_SOURCE_CHECKBOX)
    assert S.resolve_10b5_1("false", False) == (S.PLAN_NO, S.PLAN_SOURCE_CHECKBOX)
    # pre-2023q2: the checkbox does not exist. Absence of the footnote phrase
    # is NOT evidence of absence, so it stays UNKNOWN, never NO.
    assert S.resolve_10b5_1("", False) == (S.PLAN_UNKNOWN, S.PLAN_SOURCE_ABSENT)
    assert S.resolve_10b5_1(None, False) == (S.PLAN_UNKNOWN, S.PLAN_SOURCE_ABSENT)
    assert S.resolve_10b5_1("", True) == (S.PLAN_YES, S.PLAN_SOURCE_FOOTNOTE)


def test_the_four_way_boolean_encoding_of_the_real_files_is_handled():
    """2025q1's AFF10B5ONE column carries '0', '1', 'true', 'false' and ''
    in the SAME column. A parser that only knew 0/1 would read 'false' as
    truthy garbage."""
    assert S.normalise_flag("0") is False
    assert S.normalise_flag("false") is False
    assert S.normalise_flag("1") is True
    assert S.normalise_flag("true") is True
    assert S.normalise_flag("") is None


# --------------------------------------------------------------- the parser

def test_parse_quarter_zip_end_to_end(quarter_zip):
    rows, receipt = S.parse_quarter_zip(quarter_zip)
    assert receipt["quarter"] == "2020q1"
    assert receipt["submissions"] == 6
    assert len(rows) == len(FIXTURE_NONDERIV) + len(FIXTURE_DERIV)
    assert receipt["unknown_codes"] == []
    assert receipt["distinct_issuers"] == 1
    assert receipt["distinct_insiders"] == 6

    by_acc = {(r["accession"], r["table"], r["trans_sk"]): r for r in rows}
    buy = by_acc[("0000012345-20-000001", "NONDERIV", "1")]
    assert buy["is_open_market_purchase"] is True
    assert buy["trans_class"] == "OPEN_MARKET_PURCHASE"
    assert buy["dollar_value"] == pytest.approx(10_000.0)
    assert buy["owner_cik"] == "999001"          # leading zeros stripped
    assert buy["is_officer"] and not buy["is_director"]

    grant = by_acc[("0000012345-20-000002", "NONDERIV", "2")]
    assert grant["is_open_market_purchase"] is False

    plan_sale = by_acc[("0000012345-20-000003", "NONDERIV", "3")]
    assert plan_sale["plan_10b5_1"] == S.PLAN_YES
    assert plan_sale["is_open_market_sale"] is False   # excluded, it is a plan

    deriv_p = by_acc[("0000012345-20-000002", "DERIV", "8")]
    assert deriv_p["is_open_market_purchase"] is False  # a derivative P is not stock

    amendment = by_acc[("0000012345-20-000006", "NONDERIV", "6")]
    assert amendment["is_amendment"] is True


def test_a_pre_checkbox_filing_gets_its_plan_flag_from_the_footnote(quarter_zip):
    rows, receipt = S.parse_quarter_zip(quarter_zip)
    r = next(r for r in rows if r["accession"] == "0000012345-20-000004"
             and r["table"] == "NONDERIV")
    assert r["plan_10b5_1"] == S.PLAN_YES
    assert r["plan_10b5_1_source"] == S.PLAN_SOURCE_FOOTNOTE
    assert r["is_open_market_purchase"] is False
    assert receipt["footnote_10b5_1_accessions"] == 1


def test_footnote_scan_can_be_skipped_and_then_the_flag_stays_unknown(quarter_zip):
    rows, _ = S.parse_quarter_zip(quarter_zip, scan_footnotes=False)
    r = next(r for r in rows if r["accession"] == "0000012345-20-000004"
             and r["table"] == "NONDERIV")
    assert r["plan_10b5_1"] == S.PLAN_UNKNOWN


def test_a_missing_member_is_a_refusal_not_an_empty_quarter(tmp_path):
    p = tmp_path / "2020q1_form345.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(S.SUBMISSION_TSV, _tsv(SUBMISSION_COLS, FIXTURE_SUBS))
    with pytest.raises(S.SecInsiderBulkError, match="REPORTINGOWNER"):
        S.parse_quarter_zip(p)


# ------------------------------------------------------------ THE PIT TESTS

def test_pit_check_passes_on_the_parser_output(quarter_zip):
    rows, _ = S.parse_quarter_zip(quarter_zip)
    out = S.assert_pit_sane(rows)
    assert out["violations"] == 0
    # the one deliberately future-dated row is COUNTED, not fatal
    assert out["future_dated_transactions"] == 1


def test_pit_test_goes_red_on_a_lookahead_join(quarter_zip):
    """THE test the lane exists for.

    Rebuild `observed_at_utc` from TRANS_DATE — the natural mistake, because
    the transaction date is the column that *feels* like the event — and the
    guard must refuse. If this test ever passes with the lookahead in place,
    the guard is decorative.
    """
    rows, _ = S.parse_quarter_zip(quarter_zip)
    lookahead = []
    for r in rows:
        bad = dict(r)
        bad["observed_at_utc"] = S.observed_at_utc(r["trans_date"])
        lookahead.append(bad)
    with pytest.raises(S.SecInsiderBulkError, match="not the filing_date-derived bound"):
        S.assert_pit_sane(lookahead)


def test_pit_test_goes_red_when_observed_at_is_the_transaction_day_itself(quarter_zip):
    rows, _ = S.parse_quarter_zip(quarter_zip)
    bad = [dict(r, observed_at_utc=datetime(r["trans_date"].year, r["trans_date"].month,
                                            r["trans_date"].day, tzinfo=timezone.utc))
           for r in rows if r["trans_date"]]
    with pytest.raises(S.SecInsiderBulkError):
        S.assert_pit_sane(bad)


def test_pit_check_refuses_a_quarter_that_is_mostly_future_dated(quarter_zip):
    """A handful of future-dated rows is the SEC's tail; a table full of them
    is a month/day swap in OUR parser and must not be waved through."""
    rows, _ = S.parse_quarter_zip(quarter_zip)
    template = next(r for r in rows if r["trans_date"] and r["filing_date"])
    swapped = [dict(template, trans_date=template["filing_date"] + timedelta(days=30))
               for _ in range(S.MIN_ROWS_FOR_FRACTION_CHECK)]
    with pytest.raises(S.SecInsiderBulkError, match="future-dated"):
        S.assert_pit_sane(swapped)


def test_the_future_dated_cap_is_not_applied_to_a_table_too_small_to_mean_it():
    """A ratio floor must be checked against its own denominator: 1 of 6 rows
    is 17% and says nothing about a parser. Below the row floor the count is
    still REPORTED — it is just not fatal."""
    fd = date(2020, 2, 12)
    rows = [{"accession": "0000012345-20-000006", "filing_date": fd,
             "trans_date": date(2020, 12, 20), "observed_at_utc": S.observed_at_utc(fd)}]
    out = S.assert_pit_sane(rows)
    assert out["future_dated_transactions"] == 1 and out["violations"] == 0


def test_observed_at_is_never_earlier_than_the_filing_day(quarter_zip):
    rows, _ = S.parse_quarter_zip(quarter_zip)
    for r in rows:
        fd = r["filing_date"]
        assert r["observed_at_utc"] > datetime(fd.year, fd.month, fd.day,
                                               tzinfo=timezone.utc)
        assert r["observed_at_basis"] == S.OBSERVED_AT_BASIS
        assert r["acceptance_datetime_utc"] is None   # declared absence


# --------------------------------------------------- THE FABRICATION GUARD

def test_fabrication_guard_passes_on_the_parser_output(quarter_zip):
    rows, _ = S.parse_quarter_zip(quarter_zip)
    assert S.assert_not_fabricated(rows)["violations"] == 0


def test_fabrication_guard_rejects_an_invented_accession(quarter_zip):
    rows, _ = S.parse_quarter_zip(quarter_zip)
    rows[0] = dict(rows[0], accession="TOTALLY-MADE-UP")
    with pytest.raises(S.SecInsiderBulkError, match="not an EDGAR accession"):
        S.assert_not_fabricated(rows)


def test_fabrication_guard_rejects_an_invented_column(quarter_zip):
    rows, _ = S.parse_quarter_zip(quarter_zip)
    rows[0] = dict(rows[0], insider_conviction_score=0.87)
    with pytest.raises(S.SecInsiderBulkError, match="outside the declared schema"):
        S.assert_not_fabricated(rows)


def test_fabrication_guard_rejects_a_transaction_with_no_filing_date(quarter_zip):
    rows, _ = S.parse_quarter_zip(quarter_zip)
    rows[0] = dict(rows[0], filing_date=None)
    with pytest.raises(S.SecInsiderBulkError, match="cannot be PIT-stamped"):
        S.assert_not_fabricated(rows)


def test_fabrication_guard_rejects_a_doctored_dollar_value(quarter_zip):
    rows, _ = S.parse_quarter_zip(quarter_zip)
    rows[0] = dict(rows[0], dollar_value=1_000_000.0)
    with pytest.raises(S.SecInsiderBulkError, match="not shares x price"):
        S.assert_not_fabricated(rows)


def test_source_and_derived_fields_do_not_overlap():
    """A reader must be able to say, of any column, whether it is the SEC's or
    ours. A field in both sets would make that unanswerable."""
    assert not (S.SOURCE_FIELDS & S.DERIVED_FIELDS)


# ------------------------------------------------ routine vs opportunistic

def _history(years, months):
    return {"years": sorted(years), "year_months": sorted(months)}


def test_routine_requires_the_same_month_three_years_running():
    hist = {"999001": _history([2017, 2018, 2019],
                               ["2017-02", "2018-02", "2019-02"])}
    assert S.classify_routine_opportunistic("999001", date(2020, 2, 10), hist) == S.ROUTINE


def test_opportunistic_has_three_years_but_no_month_pattern():
    hist = {"999001": _history([2017, 2018, 2019],
                               ["2017-03", "2018-07", "2019-11"])}
    assert S.classify_routine_opportunistic("999001", date(2020, 2, 10), hist) == S.OPPORTUNISTIC


def test_a_short_history_is_unclassifiable_never_defaulted_to_opportunistic():
    """The defaulting mistake would silently double the 'opportunistic' count
    with every insider who simply had not traded for three years."""
    hist = {"999001": _history([2018, 2019], ["2018-02", "2019-02"])}
    assert S.classify_routine_opportunistic("999001", date(2020, 2, 10), hist) == S.UNCLASSIFIABLE
    assert S.classify_routine_opportunistic("999001", None, hist) == S.UNCLASSIFIABLE
    assert S.classify_routine_opportunistic(None, date(2020, 2, 10), hist) == S.UNCLASSIFIABLE
    assert S.classify_routine_opportunistic("nobody", date(2020, 2, 10), hist) == S.UNCLASSIFIABLE


def test_classification_only_ever_looks_at_strictly_prior_years():
    """PIT: a purchase in the classified year itself must not make the insider
    routine. Same month, but only in 2020 -> no three prior years -> refused."""
    hist = {"999001": _history([2020], ["2020-02"])}
    assert S.classify_routine_opportunistic("999001", date(2020, 2, 10), hist) == S.UNCLASSIFIABLE


@pytest.mark.parametrize("years,months,expected", [
    ([2017, 2018, 2019], ["2017-02", "2018-02", "2019-02"], "routine"),
    ([2017, 2018, 2019], ["2017-02", "2018-02", "2019-05"], "opportunistic"),
    ([2018, 2019], ["2018-02", "2019-02"], "unclassifiable"),
])
def test_bulk_classifier_agrees_with_the_live_cmp_scorer(years, months, expected):
    """The live scorer (`cmp_insider.classify_buy`, the one behind
    TRIAL-CMP-INSIDER-IC) and this bulk classifier must not drift apart —
    a tape classified one way and a live buy classified another is two
    different signals wearing one name."""
    hist = {"999001": _history(years, months)}
    bulk = S.classify_routine_opportunistic("999001", date(2020, 2, 10), hist)
    live = cmp_insider.classify_buy("999001", "2020-02-10", {"history": hist})
    assert bulk == live == expected


def test_build_purchase_history_counts_only_open_market_purchases(quarter_zip):
    rows, _ = S.parse_quarter_zip(quarter_zip)
    hist = S.build_purchase_history(rows)
    # only accession ...0001 is a discretionary open-market buy in the fixture
    # whose owner is 999001; the grant, the plan buy and the deriv P are out.
    assert set(hist) == {"999001", "999006"}
    assert hist["999001"]["year_months"] == ["2020-02"]


# ------------------------------------------------------------- permno link

def _crsp_index():
    return {"ACME": [(date(2015, 1, 1), date(2024, 12, 31), 10001, 11)],
            "DUAL": [(date(2015, 1, 1), date(2024, 12, 31), 20001, 11),
                     (date(2015, 1, 1), date(2024, 12, 31), 20002, 11)]}


def test_link_permno_matches_inside_the_name_interval():
    permno, method = S.link_permno("ACME", date(2020, 2, 5), _crsp_index(),
                                   date(2024, 12, 31))
    assert (permno, method) == (10001, S.LINK_OK)


def test_an_unlinked_row_is_a_counted_refusal_with_a_reason():
    idx, ve = _crsp_index(), date(2024, 12, 31)
    assert S.link_permno("ACME", date(2025, 3, 1), idx, ve)[1] == S.LINK_NO_VINTAGE
    assert S.link_permno("NOPE", date(2020, 2, 5), idx, ve)[1] == S.LINK_NO_MATCH
    assert S.link_permno("", date(2020, 2, 5), idx, ve)[1] == S.LINK_NO_SYMBOL
    assert S.link_permno("ACME", None, idx, ve)[1] == S.LINK_NO_SYMBOL
    assert S.link_permno("DUAL", date(2020, 2, 5), idx, ve)[1] == S.LINK_AMBIGUOUS
    # every refusal is a NAMED reason, never a bare None
    for sym, on in (("ACME", date(2025, 3, 1)), ("NOPE", date(2020, 2, 5))):
        permno, method = S.link_permno(sym, on, idx, ve)
        assert permno is None and method.startswith("REFUSED_")


def test_a_ticker_outside_its_name_interval_does_not_link():
    idx = {"ACME": [(date(2021, 1, 1), date(2024, 12, 31), 10001, 11)]}
    assert S.link_permno("ACME", date(2020, 2, 5), idx, date(2024, 12, 31))[1] == S.LINK_NO_MATCH


# --------------------------------------------------------------- quarters

def test_quarters_between_is_inclusive_and_ordered():
    assert S.quarters_between("2006q1", "2006q4") == ["2006q1", "2006q2", "2006q3", "2006q4"]
    assert S.quarters_between("2006q4", "2007q2") == ["2006q4", "2007q1", "2007q2"]
    assert S.quarters_between("2006q1", "2006q1") == ["2006q1"]
    assert len(S.quarters_between("2006q1", "2026q2")) == 82


def test_a_malformed_or_reversed_quarter_range_is_refused():
    with pytest.raises(S.SecInsiderBulkError):
        S.quarters_between("2006q5", "2007q1")
    with pytest.raises(S.SecInsiderBulkError):
        S.quarters_between("2007q1", "2006q1")
    with pytest.raises(S.SecInsiderBulkError):
        S.quarters_between("06q1", "2007q1")


# ----------------------------------------------------- the loader, offline

def test_loader_imports_and_declares_its_cursor_and_receipt_paths():
    """The whole point of I1's shape: a cursor, a log and a PER-QUARTER
    receipt. A loader without all three is the news backfill that died at
    83.6% with nothing to resume from."""
    from scripts import sec_insider_bulk_load as L
    assert L.CURSOR_PATH.name == "_cursor.json"
    assert L.LOG_PATH.name == "_load.log"
    assert L.RECEIPT_DIR.name == "receipts"
    assert set(L.EVENT_FAMILIES) >= {"insider_open_market_buy",
                                     "insider_opportunistic_buy",
                                     "insider_routine_buy"}


def test_loader_cursor_roundtrips_atomically(tmp_path, monkeypatch):
    from scripts import sec_insider_bulk_load as L
    monkeypatch.setattr(L, "DATA_DIR", tmp_path)
    monkeypatch.setattr(L, "CURSOR_PATH", tmp_path / "_cursor.json")
    monkeypatch.setattr(L, "LOG_PATH", tmp_path / "_load.log")
    cur = L.load_cursor()
    assert cur["done"] == []
    cur["done"].append("2006q1")
    L.save_cursor(cur)
    again = L.load_cursor()
    assert again["done"] == ["2006q1"]
    assert again["updated_utc"]


def test_loader_starts_fresh_on_a_cursor_from_an_older_version(tmp_path, monkeypatch):
    from scripts import sec_insider_bulk_load as L
    monkeypatch.setattr(L, "DATA_DIR", tmp_path)
    monkeypatch.setattr(L, "CURSOR_PATH", tmp_path / "_cursor.json")
    monkeypatch.setattr(L, "LOG_PATH", tmp_path / "_load.log")
    (tmp_path / "_cursor.json").write_text(
        json.dumps({"version": 1, "done": ["2006q1"]}), encoding="utf-8")
    cur = L.load_cursor()
    assert cur["version"] == L.CURSOR_VERSION and cur["done"] == []
    assert (tmp_path / "_cursor.v1.json").exists()   # the old one is KEPT
