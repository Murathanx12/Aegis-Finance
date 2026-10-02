"""LANE A alert inputs: 8-K items, Form 4 clusters, the ticker set, confirmations.

Synthetic corpus files in tmp_path; no network.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from backend.services import alerts as AL
from backend.tests.alerts_isolation import guard_real_data  # noqa: F401  (autouse, F5)
from backend.services import alerts_sources as S

UTC = timezone.utc
NOW = datetime(2026, 9, 28, 6, 0, tzinfo=UTC)
CIK = {1372612: [("BOX", "BOX INC")], 1652044: [("GOOGL", "Alphabet Inc."), ("GOOG", "Alphabet Inc.")],
       999: [("OUT", "OUTSIDE CO")]}


def _atom(cik, items_text, *, seen="2026-09-28T01:00:00+00:00", acc="0001193125-26-401392",
          form="8-K"):
    return {"source": "sec_edgar_8k_current_atom", "first_seen_utc": seen,
            "published_utc": "2026-09-28T00:30:00+00:00",
            "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{acc}-index.htm",
            "title": f"{form} - CO ({cik:010d}) (Filer)", "body": f"Filed: 2026-09-28 AccNo: {acc} "
            f"Size: 1 KB {items_text}", "tickers": [], "entity_tags": [f"8-K:x", f"cik:{cik:010d}"],
            "raw_id": acc}


def _write(root, sub, day, rows):
    d = root / sub
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{day}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_parse_8k_items():
    got = S.parse_8k_items("Filed: x Item 1.02: Termination of a Material Definitive Agreement "
                           "Item 9.01: Financial Statements and Exhibits")
    assert [c for c, _ in got] == ["1.02", "9.01"]
    assert got[0][1] == "Termination of a Material Definitive Agreement"


def test_read_8k_events_types_by_item_prefers_the_press_release_and_limits_the_universe(tmp_path):
    rows = [_atom(1372612, "Item 1.02: Termination of a Material Definitive Agreement "
                           "Item 9.01: Financial Statements and Exhibits"),
            _atom(1652044, "Item 5.02: Departure of Directors or Certain Officers",
                  acc="0001652044-26-000001"),
            _atom(999, "Item 1.03: Bankruptcy or Receivership", acc="0000000999-26-000001"),
            _atom(1372612, "Item 9.01: Financial Statements and Exhibits",
                  acc="0001193125-26-499999"),
            _atom(1372612, "Item 1.02: Termination", acc="0001193125-26-400000",
                  seen="2026-09-20T01:00:00+00:00")]
    _write(tmp_path, S.ATOM_DIR, "2026-09-28", rows)
    _write(tmp_path, S.EX99_DIR, "2026-09-28", [{
        "url": "https://www.sec.gov/Archives/edgar/data/1372612/000119312526401392/pr.htm",
        "title": "8-K - BOX INC (0001372612) (Filer) — EX-99.1", "first_seen_utc": "x"}])
    evs, st = S.read_8k_events(now=NOW, universe=["BOX", "GOOGL", "GOOG"], root=tmp_path,
                               cik_map=CIK, max_age_h=72)
    by = {e["ticker"]: e for e in evs}
    assert set(by) == {"BOX", "GOOGL"}                    # OUT not in universe; GOOG deduped
    box = by["BOX"]
    assert box["event_type_id"] == "contract_loss_or_termination" and box["direction_prior"] == -1
    assert box["source_url"].endswith("/pr.htm")
    assert box["source_url_kind"].startswith("company press release")
    assert box["fact_key"] == "8k_item:1.02" and box["lane"] == "truth"
    g = by["GOOGL"]
    assert g["event_type_id"] == "sec_8k_item_5.02"
    assert set(g["event_type_candidates"]) == {"management_change_departure",
                                               "management_change_appointment"}
    assert g["direction_prior"] is None and g["sibling_tickers"] == ["GOOG"]
    assert st["ticker_not_in_universe"] == 1 and st["no_qualifying_item"] == 1
    assert st["outside_age_window"] == 1


def test_a_specific_item_outranks_the_catch_all_that_furnishes_it(tmp_path):
    _write(tmp_path, S.ATOM_DIR, "2026-09-28", [_atom(
        1372612, "Item 5.02: Departure of Directors Item 7.01: Regulation FD Disclosure "
                 "Item 9.01: Financial Statements and Exhibits")])
    evs, _ = S.read_8k_events(now=NOW, universe=["BOX"], root=tmp_path, cik_map=CIK)
    assert evs[0]["fact_key"] == "8k_item:5.02" and "also Item(s) 7.01" in evs[0]["fact"]


def test_the_official_lane_feeds_the_8k_reader_and_its_freshness(tmp_path):
    # 2026-09-30: the Atom collector refreshes ~once a day, so every US
    # afternoon the 4-filing-hour rule went DEGRADED while the official-sources
    # lane was reading the same EDGAR feed every 15 minutes. Both are read now;
    # an accession already in the Atom corpus is not read twice.
    corpus = tmp_path / "news_corpus"
    _write(corpus, S.ATOM_DIR, "2026-09-28", [_atom(
        1372612, "Item 1.02: Termination of a Material Definitive Agreement",
        seen="2026-09-27T20:00:00+00:00")])
    off = tmp_path / "official" / "tables" / "filing_events.jsonl"
    off.parent.mkdir(parents=True)
    base = {"source": "sec_8k", "form_type": "8-K", "role": "Filer",
            "public_utc": "2026-09-28T05:10:00+00:00", "first_seen_utc": "2026-09-28T05:20:00+00:00"}
    rows = [dict(base, accession="0001193125-26-401392", cik="1372612", company="BOX INC",
                 items=["1.02"], index_url="u1"),                          # same filing: not twice
            dict(base, accession="0001652044-26-000009", cik="1652044", company="Alphabet Inc.",
                 items=["5.02", "9.01"], index_url="u2"),
            dict(base, accession="0001652044-26-000009", cik="1652044", company="Alphabet Inc.",
                 items=["5.02"], index_url="u2", role="Subject"),          # a second role row
            dict(base, source="sec_13dg", accession="0000000001-26-000001", cik="1652044",
                 form_type="SC 13D", items=[], index_url="u3")]
    off.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    assert S.official_filing_events_path(corpus) == off
    evs, st = S.read_8k_events(now=NOW, universe=["BOX", "GOOGL"], root=corpus, cik_map=CIK)
    assert sorted(e["ticker"] for e in evs) == ["BOX", "GOOGL"]
    g = next(e for e in evs if e["ticker"] == "GOOGL")
    assert g["fact_key"] == "8k_item:5.02" and g["source_url"] == "u2"
    assert st["official_rows_read"] == 1
    assert st["newest_first_seen_utc"] == "2026-09-28T05:20:00+00:00"
    assert st["newest_first_seen_utc_atom"] == "2026-09-27T20:00:00+00:00"
    # a Monday 06:00Z read: the Atom row alone is within limits here, so prove
    # the freshness moves with the official row by reading 9 filing hours later
    later = datetime(2026, 9, 28, 19, 0, tzinfo=UTC)                  # 15:00 ET Monday
    assert S.source_staleness_8k(st["newest_first_seen_utc_atom"], later)["state"] == "STALE"
    fresh = datetime(2026, 9, 28, 8, 0, tzinfo=UTC)
    assert S.source_staleness_8k(st["newest_first_seen_utc"], fresh)["state"] == "OK"


def _form4(rows):
    return pd.DataFrame(rows, columns=["symbol", "event_time_utc", "observed_at_utc",
                                       "observed_at_basis", "insider_cik", "insider_trans_code",
                                       "insider_dollar_value"])


def test_form4_cluster_uses_the_filing_clock_not_the_trade_date():
    obs = pd.Timestamp("2026-09-27T02:00:00Z")
    df = _form4([
        ["AAA", pd.Timestamp("2026-09-10", tz="UTC"), obs - pd.Timedelta(days=5), "EOD", "1", "P", 1e5],
        ["AAA", pd.Timestamp("2026-09-24", tz="UTC"), obs, "EOD", "2", "P", 2e5],
        ["BBB", pd.Timestamp("2026-09-24", tz="UTC"), obs, "EOD", "3", "P", 1e5],   # one buyer
        ["CCC", pd.Timestamp("2026-09-01", tz="UTC"), obs - pd.Timedelta(days=10), "EOD", "4", "P", 1e5],
        ["CCC", pd.Timestamp("2026-09-02", tz="UTC"), obs - pd.Timedelta(days=9), "EOD", "5", "P", 1e5],
        ["DDD", pd.Timestamp("2026-09-24", tz="UTC"), obs + pd.Timedelta(days=3), "EOD", "6", "P", 1e5],
        ["DDD", pd.Timestamp("2026-09-24", tz="UTC"), obs, "EOD", "7", "P", 1e5],
    ])
    evs, st = S.read_form4_clusters(now=NOW, universe=["AAA", "BBB", "CCC", "DDD"], frame=df,
                                    max_age_h=72, min_buyers=2, lookback_days=30)
    assert [e["ticker"] for e in evs] == ["AAA"]           # CCC completed too long ago; DDD's
    e = evs[0]                                              # second filing is in the future
    assert e["observed_utc"] == "2026-09-27T02:00:00+00:00" and e["n_buyers"] == 2
    assert "purchases" in e["fact"] and "$300,000" in e["fact"]
    assert e["source_url"].startswith("https://www.sec.gov/")
    AL.assert_can_originate(e)


def test_form4_reports_a_stale_tape_by_name():
    df = _form4([["AAA", pd.Timestamp("2026-06-20", tz="UTC"),
                  pd.Timestamp("2026-07-01T03:00Z"), "EOD", "1", "P", 1e5]])
    evs, st = S.read_form4_clusters(now=NOW, universe=["AAA"], frame=df)
    assert evs == [] and st["state"].startswith("STALE_TAPE: the Form 4 bulk tape ends 2026-07-01")


def _funnel(tmp_path, gen, tickers=("AAA", "BBB")):
    p = tmp_path / "funnel.json"
    p.write_text(json.dumps({"generated_at": gen, "candidates": [{"ticker": t} for t in tickers]}),
                 encoding="utf-8")
    books = tmp_path / "books.jsonl"
    books.write_text("".join(json.dumps(b) + "\n" for b in [
        {"kind": "personal", "book_id": "b1", "frozen_utc": "2026-09-25T00:00:00+00:00",
         "positions": [{"ticker": "CCC"}, {"ticker": "CASH"}]},
        {"kind": "twin", "book_id": "b2", "positions": [{"ticker": "RANDOM"}]}]), encoding="utf-8")
    return p, books


def test_universe_is_funnel_plus_chosen_books_and_prints_its_age(tmp_path):
    p, b = _funnel(tmp_path, "2026-09-24T02:48:34+00:00")
    u = S.alert_universe(now=NOW, funnel_path=p, books_path=b)
    assert u["tickers"] == ["AAA", "BBB", "CCC"]           # the twin's random draw is not a choice
    assert u["n"] == 3 and 4.0 < u["funnel_age_days"] < 4.2 and u["funnel_stale_limit_days"] == 10


@pytest.mark.parametrize("gen", ["2026-08-11T02:33:48Z", None, "not a date"])
def test_universe_refuses_a_stale_or_undateable_candidate_set(tmp_path, gen):
    p, b = _funnel(tmp_path, gen)
    with pytest.raises(AL.AlertRefused, match="candidate set is not current"):
        S.alert_universe(now=NOW, funnel_path=p, books_path=b)


def test_discovery_headlines_confirm_but_social_is_not_read(tmp_path):
    e = {"ticker": "BOX", "observed_utc": "2026-09-28T01:00:00+00:00"}
    _write(tmp_path, "google_news_rss_en_us", "2026-09-28",
           [{"tickers": ["BOX"], "published_utc": "2026-09-28T02:00:00+00:00", "url": "g1"},
            {"tickers": ["BOX"], "published_utc": "2026-09-20T02:00:00+00:00", "url": "old"}])
    _write(tmp_path, "reddit_securityanalysis_rss", "2026-09-28",
           [{"tickers": ["BOX"], "published_utc": "2026-09-28T02:00:00+00:00", "url": "r"}])
    S.discovery_confirmations([e], now=NOW, root=tmp_path)
    assert e["confirmations"] == {"n": 1, "sources": ["google_news_rss_en_us"], "first_url": "g1"}
