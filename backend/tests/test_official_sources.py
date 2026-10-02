"""The OFFICIAL sources (2026-09-30): SEC EDGAR, House disclosures, CFTC COT,
FINRA, Federal Register, central banks -- read through their own APIs and
feeds, landed as point-in-time typed rows.

What is pinned: every row's `public_utc` is when the world could know it
(acceptance / disclosure / release time), never the trade or period date; a
robots.txt that disallows a path means the page is never requested; a bot
check cools the source instead of retrying; each source's daily cap binds;
tables are append-only and deduplicated.

Offline: every HTTP call goes through an injected fake transport. No literal
calendar dates: every date is derived from now.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.services import official_sources as OS

NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _weekday_before(d: date, weekday: int) -> date:
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


# ───────────────────────────── the time rules ────────────────────────────────

def test_an_edgar_filing_inside_the_window_is_public_at_acceptance():
    d = _weekday_before(NOW.date() - timedelta(days=3), 2)          # a Wednesday
    acc = datetime.combine(d, datetime.min.time()).replace(hour=14, minute=5)
    pub, basis = OS.edgar_public_utc(acc, d)
    assert basis == "EDGAR_ACCEPTANCE"
    assert pub == OS.et_to_utc(acc)
    assert pub.astimezone(OS.ET_TZ).hour == 14


def test_an_after_hours_filing_is_public_at_six_on_its_filing_date():
    d = _weekday_before(NOW.date() - timedelta(days=3), 2)
    acc = datetime.combine(d, datetime.min.time()).replace(hour=19, minute=40)
    fd = OS.next_business_day(d)
    pub, basis = OS.edgar_public_utc(acc, fd)
    assert basis == "EDGAR_AFTER_HOURS_FILING_DATE_0600ET"
    loc = pub.astimezone(OS.ET_TZ)
    assert loc.date() == fd and loc.hour == 6
    assert pub > OS.et_to_utc(acc)                   # later than acceptance: never earlier


def test_cot_is_public_on_the_friday_after_its_tuesday():
    tue = _weekday_before(NOW.date() - timedelta(days=7), 1)
    pub = OS.cot_public_utc(tue).astimezone(OS.ET_TZ)
    assert pub.weekday() == 4 and (pub.date() - tue).days == 3
    assert (pub.hour, pub.minute) == (15, 30)


def test_a_disclosure_is_tradable_only_at_the_next_session():
    d = _weekday_before(NOW.date() - timedelta(days=3), 4)          # a Friday
    pub = OS.disclosure_public_utc(d)
    t = OS.tradable_from_utc(pub).astimezone(OS.ET_TZ)
    assert t.weekday() == 0 and (t.hour, t.minute) == (9, 30)      # Monday's open
    assert OS.tradable_from_utc(pub) > pub


def test_short_interest_is_public_eight_business_days_after_settlement():
    sd = _weekday_before(NOW.date() - timedelta(days=20), 2)
    pub = OS.short_interest_public_utc(sd)
    assert pub.date() == OS.add_business_days(sd, 8)
    assert pub > datetime.combine(sd, datetime.min.time()).replace(tzinfo=timezone.utc)


# ───────────────────────────────── parsers ───────────────────────────────────

def _atom(entries: list[tuple[str, str, str, str, datetime, str]]) -> str:
    body = []
    for form, company, cik, acc, upd, extra in entries:
        nod = acc.replace("-", "")
        body.append(
            f"<entry><title>{form} - {company} ({cik}) (Reporting)</title>"
            f'<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/'
            f'{int(acc[:10])}/{nod}/{acc}-index.htm"/>'
            f'<summary type="html"> &lt;b&gt;Filed:&lt;/b&gt; {upd.date()} &lt;b&gt;AccNo:&lt;/b&gt; '
            f"{acc} &lt;b&gt;Size:&lt;/b&gt; 5 KB{extra}</summary>"
            f"<updated>{upd.astimezone(OS.ET_TZ).isoformat()}</updated>"
            f'<category scheme="https://www.sec.gov/" label="form type" term="{form}"/>'
            f"<id>urn:tag:sec.gov,2008:accession-number={acc}</id></entry>")
    return ('<?xml version="1.0" encoding="ISO-8859-1" ?><feed xmlns="http://www.w3.org/2005/Atom">'
            "<title>Latest Filings</title>" + "".join(body) + "</feed>")


def test_the_atom_feed_is_parsed_with_its_items_and_acceptance_time():
    upd = NOW - timedelta(minutes=10)
    xml = _atom([("8-K", "ACME CORP", "0000012345", "0000012345-26-000001", upd,
                  "&lt;br&gt;Item 2.02: Results&lt;br&gt;Item 9.01: Exhibits"),
                 ("424B2", "BANK NOTES", "0000099999", "0000099999-26-000002", upd, "")])
    es = OS.parse_edgar_atom(xml)
    assert [e["form"] for e in es] == ["8-K", "424B2"]
    assert es[0]["items"] == ["2.02", "9.01"] and es[0]["cik"] == "12345"
    assert es[0]["updated_utc"] == upd and es[0]["accession"] == "0000012345-26-000001"


def test_the_index_page_gives_acceptance_filing_date_and_the_raw_xml():
    d = NOW.date() - timedelta(days=1)
    html = (f'<div class="infoHead">Filing Date</div>\n<div class="info">{d.isoformat()}</div>'
            f'<div class="infoHead">Accepted</div>\n<div class="info">{d.isoformat()} 16:02:11</div>'
            '<a href="/Archives/edgar/data/1/2/xslF345X05/form4.xml">x</a>'
            '<a href="/Archives/edgar/data/1/2/form4.xml">y</a>')
    ip = OS.parse_index_page(html)
    assert ip["accepted_et"] == datetime.combine(d, datetime.min.time()).replace(
        hour=16, minute=2, second=11)
    assert ip["filing_date"] == d
    assert ip["xml_docs"] == ["/Archives/edgar/data/1/2/form4.xml"]


def _form4_xml(ticker: str, code: str, plan: bool, title: str = "Chief Executive Officer") -> str:
    tdate = (NOW.date() - timedelta(days=2)).isoformat()
    aff = "<aff10b5One>1</aff10b5One>" if plan else "<aff10b5One>0</aff10b5One>"
    return (f"<ownershipDocument><documentType>4</documentType><periodOfReport>{tdate}"
            f"</periodOfReport>{aff}<issuer><issuerCik>0000012345</issuerCik><issuerName>Acme"
            f"</issuerName><issuerTradingSymbol>{ticker}</issuerTradingSymbol></issuer>"
            "<reportingOwner><reportingOwnerId><rptOwnerCik>0000077777</rptOwnerCik>"
            "<rptOwnerName>Doe Jane</rptOwnerName></reportingOwnerId><reportingOwnerRelationship>"
            f"<isOfficer>1</isOfficer><officerTitle>{title}</officerTitle>"
            "</reportingOwnerRelationship></reportingOwner><nonDerivativeTable>"
            "<nonDerivativeTransaction><securityTitle><value>Common</value></securityTitle>"
            f"<transactionDate><value>{tdate}</value></transactionDate><transactionCoding>"
            f"<transactionCode>{code}</transactionCode></transactionCoding><transactionAmounts>"
            "<transactionShares><value>10000</value></transactionShares><transactionPricePerShare>"
            "<value>25.5</value></transactionPricePerShare><transactionAcquiredDisposedCode>"
            f"<value>{'A' if code == 'P' else 'D'}</value></transactionAcquiredDisposedCode>"
            "</transactionAmounts><postTransactionAmounts><sharesOwnedFollowingTransaction>"
            "<value>50000</value></sharesOwnedFollowingTransaction></postTransactionAmounts>"
            "<ownershipNature><directOrIndirectOwnership><value>D</value>"
            "</directOrIndirectOwnership></ownershipNature></nonDerivativeTransaction>"
            "</nonDerivativeTable></ownershipDocument>")


def test_a_form4_line_becomes_a_typed_row_dated_by_acceptance_not_trade():
    from backend.services.ownership_forms import parse_ownership_form
    xml = _form4_xml("ACME", "P", plan=False)
    parsed = parse_ownership_form(xml)
    pub = NOW - timedelta(hours=1)
    rows = OS.insider_rows(parsed, accession="0000012345-26-000009", public_utc=pub,
                           basis="EDGAR_ACCEPTANCE", plan_flag=OS.aff10b5_flag(xml))
    assert len(rows) == 1
    r = rows[0]
    assert r["ticker"] == "ACME" and r["side"] == "buy" and r["role"] == "CEO"
    assert r["value_usd"] == pytest.approx(255000.0) and r["rule_10b5_1"] is False
    assert r["public_utc"] == OS.iso(pub)
    assert r["transaction_date"] != r["public_utc"][:10]
    assert r["rule_10b5_1_basis"] == "aff10b5One_filing_box"
    assert set(OS.SCHEMAS["insider_tx"]) <= set(r)          # the declared schema is on the row
    planned = OS.insider_rows(parse_ownership_form(_form4_xml("ACME", "S", plan=True)),
                              accession="x", public_utc=pub, basis="EDGAR_ACCEPTANCE",
                              plan_flag=OS.aff10b5_flag(_form4_xml("ACME", "S", plan=True)))
    assert planned[0]["rule_10b5_1"] is True and planned[0]["side"] == "sell"


def test_the_house_index_and_a_ptr_text_are_parsed():
    d = NOW.date() - timedelta(days=5)
    txt = ("Prefix\tLast\tFirst\tSuffix\tFilingType\tStateDst\tYear\tFilingDate\tDocID\n"
           f"Hon.\tDoe\tJohn\t\tP\tXX01\t{d.year}\t{d.month}/{d.day}/{d.year}\t20099999\n"
           f"\tRoe\tJane\t\tO\tXX02\t{d.year}\t{d.month}/{d.day}/{d.year}\t10099999\n")
    fs = OS.parse_house_index(txt)
    assert len(fs) == 2 and fs[0]["filing_type"] == "P" and fs[0]["disclosure_date"] == d
    td = (d - timedelta(days=30)).strftime("%m/%d/%Y")
    nd = (d - timedelta(days=2)).strftime("%m/%d/%Y")
    ptr = ("ID Owner Asset Transaction Type Date Notification Date Amount Cap. Gains > $200? "
           f"SP Apple Inc. - Common Stock (AAPL) [ST] P {td}{nd}$1,001 - $15,000 "
           f"F S : New S O : Family Trust JT Boston Scientific (BSX) [ST] S (partial) {td} "
           f"{nd} $50,001 -\n$100,000")
    tx = OS.parse_ptr_text(ptr)
    assert [(t["ticker"], t["owner"], t["tx_type"]) for t in tx] == [
        ("AAPL", "SP", "P"), ("BSX", "JT", "S (partial)")]
    assert tx[1]["amount_lo"] == 50001.0 and tx[1]["amount_hi"] == 100000.0
    assert "Family Trust" not in tx[1]["asset"]
    assert OS.parse_ptr_text("") == []                  # a scanned PTR: no text, no rows


def _cot_records(n: int, code: str = "13874A") -> list[dict]:
    tue = _weekday_before(NOW.date() - timedelta(days=7), 1)
    out = []
    for i in range(n):
        d = tue - timedelta(weeks=n - 1 - i)
        lev_long = 100_000 + (i * 1000 + (i % 3) * 700 if i < n - 1 else 900_000)  # last: extreme
        out.append({"cftc_contract_market_code": code, "market_and_exchange_names": "E-MINI S&P 500",
                    "report_date_as_yyyy_mm_dd": f"{d.isoformat()}T00:00:00.000",
                    "open_interest_all": "2000000",
                    "lev_money_positions_long": str(lev_long), "lev_money_positions_short": "300000",
                    "asset_mgr_positions_long": "900000", "asset_mgr_positions_short": "100000",
                    "dealer_positions_long_all": "1", "dealer_positions_short_all": "1",
                    "other_rept_positions_long": "1", "other_rept_positions_short": "1",
                    "nonrept_positions_long_all": "1", "nonrept_positions_short_all": "1"})
    return out


def test_cot_rows_carry_net_change_percentile_and_their_release_time():
    rows = OS.cot_rows(list(reversed(_cot_records(60))), "tff")    # any order in
    assert len(rows) == 60
    last = max(rows, key=lambda r: r["report_date"])
    assert last["headline_group"] == "lev_money"
    assert last["headline_pctile_3y"] == 1.0 and last["headline_chg_z"] > 2
    assert last["groups"]["lev_money"]["net"] == last["groups"]["lev_money"]["long"] - 300000
    assert last["public_utc"] == OS.iso(OS.cot_public_utc(date.fromisoformat(last["report_date"])))
    first = min(rows, key=lambda r: r["report_date"])
    assert first["headline_pctile_3y"] is None                     # too little history


def test_finra_short_interest_rows_are_dated_by_publication():
    sd = _weekday_before(NOW.date() - timedelta(days=25), 2)
    csv_text = ("accountingYearMonthNumber,symbolCode,issueName,issuerServicesGroupExchangeCode,"
                "marketClassCode,currentShortPositionQuantity,previousShortPositionQuantity,"
                "stockSplitFlag,averageDailyVolumeQuantity,daysToCoverQuantity,revisionFlag,"
                "changePercent,changePreviousNumber,settlementDate\n"
                f"0,ACME,Acme Inc,A,NYSE,5000000,4000000,,500000,10.0,,25.0,1000000,{sd.isoformat()}\n"
                f"0,THIN,Thin Co,S,OTC,10,10,,0,999.99,,0,0,{sd.isoformat()}\n")
    rows = OS.finra_si_rows(csv_text, now=NOW)
    assert rows[0]["public_utc"] == OS.iso(OS.short_interest_public_utc(sd))
    assert rows[0]["days_to_cover"] == 10.0 and rows[1]["days_to_cover"] is None


def test_federal_register_public_inspection_is_public_at_filing():
    filed = (NOW - timedelta(hours=20)).astimezone(OS.ET_TZ)
    pi = [{"document_number": "X-1", "filed_at": filed.isoformat(), "type": "Presidential Document",
           "agency_names": ["Executive Office of the President"], "title": "Tariff adjustment",
           "publication_date": (NOW.date() + timedelta(days=1)).isoformat()}]
    rows = OS.fedreg_rows(pi, pi=True, now=NOW)
    assert rows[0]["public_utc"] == OS.iso(filed) and rows[0]["relevant"] is True
    pub = [{"document_number": "X-2", "type": "Notice", "agency_names": ["Railroad Retirement Board"],
            "title": "Sunshine Act", "publication_date": NOW.date().isoformat()}]
    r2 = OS.fedreg_rows(pub, pi=False, now=NOW)[0]
    assert r2["relevant"] is False and r2["public_ts_basis"] == "FEDREG_ISSUE_0600ET"


def test_an_rss_item_dated_in_the_future_is_stamped_when_seen():
    from email.utils import format_datetime
    fut = format_datetime(NOW + timedelta(days=2))
    past = format_datetime(NOW - timedelta(hours=3))
    xml = ("<rss><channel><item><title>Rate decision</title><link>https://ex.org/a</link>"
           f"<pubDate>{past}</pubDate><description>&lt;p&gt;Held&lt;/p&gt;</description></item>"
           f"<item><title>Embargoed</title><link>https://ex.org/b</link><pubDate>{fut}</pubDate>"
           "</item></channel></rss>")
    rows = OS.rss_rows(xml, "fed_press", now=NOW)
    assert rows[0]["public_ts_basis"] == "RSS_PUBDATE" and rows[0]["summary"] == "Held"
    assert rows[1]["public_ts_basis"] == "FIRST_SEEN_FUTURE_DATED"
    assert rows[1]["public_utc"] == OS.iso(NOW)


# ───────────────────────── the fetcher: refusals and caps ────────────────────

class FakeHTTP:
    def __init__(self, pages: dict[str, tuple[int, bytes]]):
        self.pages, self.calls = pages, []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append(url)
        st, b = self.pages.get(url, (404, b"not found"))
        return st, b, "text/plain"


def _fx(tmp_path, pages):
    http = FakeHTTP(pages)
    return OS.Fetcher(base=tmp_path, http=http, now_fn=lambda: NOW, sleep_fn=lambda s: None), http


def test_a_robots_disallow_means_the_page_is_never_requested(tmp_path):
    fx, http = _fx(tmp_path, {
        "https://www.boj.or.jp/robots.txt": (200, b"User-agent: *\nDisallow: /en/rss/\n")})
    with pytest.raises(OS.SourceRefused, match="ROBOTS_DISALLOWED"):
        fx.get("boj_rss", "https://www.boj.or.jp/en/rss/whatsnew.xml")
    assert http.calls == ["https://www.boj.or.jp/robots.txt"]
    log = (tmp_path / "requests.jsonl").read_text(encoding="utf-8")
    assert "ROBOTS_DISALLOWED" in log


def test_a_bot_check_cools_the_source_and_nothing_retries(tmp_path):
    url = "https://api.hkma.gov.hk/public/press-releases?lang=en&pagesize=50"
    fx, http = _fx(tmp_path, {url: (403, b"<html><title>Access Denied</title></html>")})
    with pytest.raises(OS.SourceRefused, match="BOT_CHECK"):
        fx.get("hkma_api", url)
    n = len(http.calls)
    with pytest.raises(OS.SourceRefused, match="COOLING"):
        fx.get("hkma_api", url)
    assert len(http.calls) == n                          # the second call never left
    assert fx.cooling_until("hkma_api") is not None


def test_each_source_has_its_own_daily_cap(tmp_path, monkeypatch):
    monkeypatch.setitem(OS.SOURCES, "ecb_rss", {**OS.SOURCES["ecb_rss"], "day_cap": 3})
    url = "https://www.ecb.europa.eu/rss/press.html"
    fx, http = _fx(tmp_path, {url: (200, b"<rss><channel></channel></rss>")})
    for _ in range(2):                                   # robots.txt + 2 pages = 3 requests
        fx.get("ecb_rss", url)
    with pytest.raises(OS.SourceRefused, match="DAY_CAP"):
        fx.get("ecb_rss", url)
    assert fx.day_count("fed_rss") == 0                  # another source is not charged


def test_classify_response_tells_a_block_from_a_page():
    assert OS.classify_response(200, b"<rss>" + b"x" * 3000) == "OK"
    assert OS.classify_response(403, b"Access Denied") == "BOT_CHECK"
    assert OS.classify_response(429, b"slow down") == "RATE_LIMITED"
    assert OS.classify_response(200, b"<title>Just a moment...</title>") == "BOT_CHECK"
    assert OS.classify_response(404, b"") == "NOT_FOUND"


def test_tables_are_append_only_and_deduplicated(tmp_path):
    r = {"row_id": "a:1", "source": "t", "public_utc": OS.iso(NOW)}
    assert OS.append_rows("policy_events", [r, r], tmp_path) == 1
    assert OS.append_rows("policy_events", [dict(r, title="changed")], tmp_path) == 0
    assert OS.append_rows("policy_events", [{"row_id": "a:2", "source": "t"}], tmp_path) == 0
    rows = OS.read_table("policy_events", tmp_path)
    assert len(rows) == 1 and rows[0]["first_seen_utc"] and "title" not in rows[0]


def test_form4_end_to_end_lands_typed_rows(tmp_path, monkeypatch):
    from backend.services import edgar_events
    monkeypatch.setattr(edgar_events._RATE_LIMITER, "wait", lambda: None)
    upd = NOW - timedelta(minutes=20)
    acc = "0000012345-26-000077"
    idx = "https://www.sec.gov/Archives/edgar/data/12345/000001234526000077/" + acc + "-index.htm"
    acc_et = upd.astimezone(OS.ET_TZ).replace(tzinfo=None)
    html = (f'<div class="infoHead">Filing Date</div><div class="info">{acc_et.date()}</div>'
            f'<div class="infoHead">Accepted</div><div class="info">'
            f'{acc_et.strftime("%Y-%m-%d %H:%M:%S")}</div>'
            '<a href="/Archives/edgar/data/12345/000001234526000077/doc4.xml">x</a>')
    pages = {OS.ATOM_URL.format(t="4", s=0): (200, _atom([
                 ("4", "Doe Jane", "0000077777", acc, upd, ""),
                 ("424B2", "Notes", "0000099999", "0000099999-26-000001", upd, "")]).encode()),
             OS.ATOM_URL.format(t="4", s=100): (200, _atom([]).encode()),
             idx: (200, html.encode()),
             "https://www.sec.gov/Archives/edgar/data/12345/000001234526000077/doc4.xml":
                 (200, _form4_xml("ACME", "P", plan=False).encode())}
    fx, http = _fx(tmp_path, pages)
    rec = OS.collect_sec_form4(fx, max_pages=2)
    assert rec["parsed"] == 1 and rec["rows"] == 1, rec
    row = OS.read_table("insider_tx", tmp_path)[0]
    assert row["public_ts_basis"] == "EDGAR_ACCEPTANCE" and row["ticker"] == "ACME"
    # a second run fetches nothing new
    n = len(http.calls)
    assert OS.collect_sec_form4(fx, max_pages=2)["filings_new"] == 0
    assert all("-index.htm" not in u for u in http.calls[n:])


def test_due_sources_follow_their_intervals():
    last = {s: OS.iso(NOW) for s in OS.COLLECTORS}
    assert OS.due_sources(last, NOW) == []
    last["fed_rss"] = OS.iso(NOW - timedelta(hours=2))
    assert OS.due_sources(last, NOW) == ["fed_rss"]
    assert set(OS.due_sources({}, NOW)) == set(OS.COLLECTORS)


def test_no_brokerage_bank_payment_or_mail_host_is_a_source():
    bad = ("broker", "bank.com", "paypal", "stripe", "mail.", "gmail", "robinhood", "schwab",
           "fidelity", "alpaca", "interactivebrokers", "coinbase.com")
    hosts = [s["host"] for s in OS.SOURCES.values()]
    urls = [u for feeds in OS.RSS_FEEDS.values() for _, u in feeds]
    assert not [h for h in hosts + urls if any(b in h.lower() for b in bad)]
    # bankofengland is a central bank's public feed, not a bank account host
    assert all(json.dumps(OS.REFUSED_SOURCES[k]).count("why") for k in OS.REFUSED_SOURCES)
