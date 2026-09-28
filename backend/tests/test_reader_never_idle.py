"""Never idle, never blank (Murat 2026-09-28 17:00: "opening blanks or 404
pages ... it should always work and shouldnt be standing idle").

* every page load is CLASSIFIED; only OK is stored; a CHALLENGE stops the lane;
* a ticker whose page is NOT_FOUND once is recorded and not retried;
* share-class tickers are spelled with a dot in site URLs;
* the supervisor builds its own next queue (oldest newest-read first), waits
  on the daily cap instead of ending the night, and writes a status file.

Test doubles only.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.services import web_reader as WR
from backend.tests.test_dowjones_chunk_j import (  # noqa: F401 -- fixtures reused on purpose
    MultiStub, _clock_throttle, _no_parent_marker, ledger)
from backend.tests.test_reader_direct_open import DirectStub

ARTICLE = ("Palantir stock rose on Monday after the company won a contract. " * 20).strip()


@pytest.mark.parametrize("url,final,title,raw,want", [
    ("https://www.wsj.com/a-1a2b3c4d", None, "Story", ARTICLE, "OK"),
    ("https://www.wsj.com/a-1a2b3c4d", "about:blank", "", "", "BLANK"),
    ("https://www.wsj.com/a-1a2b3c4d", None, "Story", "short", "BLANK"),
    ("https://www.marketwatch.com/investing/stock/zzzz", None, "Page Not Found | MarketWatch",
     "We can't find the page you are looking for. " * 10, "NOT_FOUND"),
    ("https://www.barrons.com/articles/x-1a2b3c4d", None, "Access Denied",
     "Please verify you are a human. Press & Hold to confirm. " * 6, "CHALLENGE"),
    ("https://www.barrons.com/articles/x-1a2b3c4d", None, "Story",
     "Sign In | Subscribe. Continue reading your article with a Barron's subscription. " * 4,
     "SIGNED_OUT"),
    ("https://www.wsj.com/a-1a2b3c4d", None, "Story",
     "Headline. " * 30 + " This article is for subscribers only.", "PAYWALL_STUB"),
    ("https://www.wsj.com/a-1a2b3c4d", "https://evil.example/x", "Story", ARTICLE,
     "REDIRECTED_OFF_HOST"),
])
def test_every_page_is_classified(url, final, title, raw, want):
    assert WR.classify_page(url=url, final_url=final, title=title, raw=raw) == want


def test_a_long_article_that_mentions_404_is_ok():
    raw = ARTICLE * 5 + " The error 404 page not found was on a rival's site."
    assert WR.classify_page(url="https://www.wsj.com/a-1a2b3c4d", final_url=None,
                            title="Story", raw=raw) == "OK"


class PagesStub(DirectStub):
    def __init__(self, pages, **kw):
        super().__init__(**kw)
        self.pages_by_url = pages

    def read_text(self, tab, profile_name=None):
        u = self.cur.get(tab)
        title, text = self.pages_by_url.get(u, ("Story", ARTICLE))
        return {"url": u, "title": title, "text": text}


def test_only_ok_pages_are_stored_and_classes_reach_the_receipt(ledger):
    from scripts import dowjones_pull as DP
    nf = "https://www.marketwatch.com/investing/stock/zzzz/analystestimates"
    drv = PagesStub({nf: ("Page Not Found", "We can't find the page you are looking for. " * 9)})
    _, th = _clock_throttle(ledger / "thr.log")
    lanes = DP.parse_plan("marketwatch:analyst_estimates:ZZZZ|MU")
    rc = DP.run_plan(lanes, parents=DP.resolve_parent_tabs(["marketwatch"], [], direct=True),
                     driver=drv, throttle=th, stored={})
    arts = rc["lanes"]["marketwatch:analyst_estimates"]["articles"]
    assert [a.get("ticker") for a in arts] == ["MU"]
    assert rc["page_classes"]["marketwatch.com"] == {"NOT_FOUND": 1, "OK": 1}
    # recorded once, and the next run does not load it again
    assert "ZZZZ" in DP.not_found_tickers("marketwatch")
    drv2 = PagesStub({})
    rc2 = DP.run_plan(lanes, parents=DP.resolve_parent_tabs(["marketwatch"], [], direct=True),
                      driver=drv2, throttle=th, stored={}, fresh_since="2999-01-01")
    loaded = [c[2] for c in drv2.calls if c[0] == "open_tab"] + \
        [c[2][0] for c in drv2.calls if c[0] == "navigate" and c[2]]
    assert not any("zzzz" in u for u in loaded)
    assert rc2["lanes"]["marketwatch:analyst_estimates"]["skipped_not_found"] == ["ZZZZ"]
    log = [json.loads(x) for x in (ledger / "dowjones" / "page_log.jsonl")
           .read_text(encoding="utf-8").splitlines()]
    assert {r["class"] for r in log} == {"OK", "NOT_FOUND"}


def test_a_challenge_stops_the_lane_and_stores_nothing(ledger):
    from scripts import dowjones_pull as DP
    drv = PagesStub({}, )
    drv.pages_by_url = type("D", (dict,), {"get": lambda self, u, d=None: (
        "Access Denied", "Please verify you are a human. Press & Hold. " * 6)})()
    _, th = _clock_throttle(ledger / "thr.log")
    rc = DP.run_plan(DP.parse_plan("marketwatch:analyst_estimates:MU|DKNG"),
                     parents=DP.resolve_parent_tabs(["marketwatch"], [], direct=True),
                     driver=drv, throttle=th, stored={})
    st = rc["lanes"]["marketwatch:analyst_estimates"]
    assert st["articles"] == [] and "REFUSED_CHALLENGE" in str(st["dropped"])
    assert rc["page_classes"]["marketwatch.com"] == {"CHALLENGE": 1}


def test_share_class_tickers_take_a_dot_in_site_urls():
    from scripts import dowjones_pull as DP
    assert DP.lane_url("marketwatch", "analyst_estimates", "BRK-B").endswith("/stock/brk.b/"
                                                                            "analystestimates")
    assert DP.lane_url("wsj", "search", "BRK/B").endswith("/quotes/BRK.B")


# ── the next queue, built by the supervisor ──────────────────────────────────

def test_the_rolling_queue_puts_never_read_and_oldest_first():
    from scripts import dowjones_pull as DP
    today = datetime.now(timezone.utc).date()
    last = {"A": today.isoformat(), "B": "", "C": (today - timedelta(days=3)).isoformat()}
    txt = DP.build_rolling_queue_text(["A", "B", "C"], last, day=today.isoformat())
    plan = next(ln for ln in txt.splitlines() if ln.startswith("--plan"))
    assert "analyst_estimates:B|C|A," in plan and "wsj:search:B|C|A" in plan
    assert DP.parse_plan(plan.split('"')[1])[0]["tickers"] == ["B", "C", "A"]


def test_queue_exhausted_reads_the_done_markers(tmp_path):
    from scripts import dowjones_pull as DP
    q = tmp_path / "Q.txt"
    q.write_text('# c\n--plan "marketwatch:analyst_estimates:MU"\n--claims\n', encoding="utf-8")
    assert not DP.queue_exhausted(q)
    (n, ln), = [x for x in DP.queue_lines(q) if x[1].startswith("--plan")]
    dd = DP.queue_done_dir(q)
    dd.mkdir()
    (dd / f"{DP._line_key(n, ln)}.done").write_text("{}", encoding="utf-8")
    assert DP.queue_exhausted(q)


def test_the_daily_cap_is_a_wait_not_the_end_of_the_night():
    from scripts import night_reader_supervisor as S
    assert S.caps_reached("POLICY_STOP", "... REFUSED_THROTTLE_DAY: 120 page loads in 24 h")
    assert not S.caps_reached("POLICY_STOP", "REFUSED_PAYMENT_URL")
    assert not S.caps_reached("READER_CRASH", "REFUSED_THROTTLE_DAY")


def test_the_status_file_counts_ok_pages_and_names_the_last_bad_one(tmp_path, monkeypatch):
    from scripts import night_reader_supervisor as S
    now = datetime.now(timezone.utc)
    rows = [{"t": (now - timedelta(minutes=m)).isoformat(timespec="seconds"), "host": h,
             "class": c, "url": u, "worker": w}
            for m, h, c, u, w in [(70, "wsj.com", "OK", "https://www.wsj.com/old", "wsj"),
                                  (30, "barrons.com", "OK", "https://www.barrons.com/a", "barrons"),
                                  (5, "marketwatch.com", "NOT_FOUND", "https://mw/x", "mw"),
                                  (2, "barrons.com", "OK", "https://www.barrons.com/b", "barrons")]]
    log = tmp_path / "page_log.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    monkeypatch.setattr(S, "PAGE_LOG", log)
    st = S.write_status("reading", next_action="keep reading", path=tmp_path / "status.json",
                        now=now)
    assert st["pages_ok_10m"] == 1 and st["pages_ok_60m"] == 2
    assert st["classes_60m"] == {"barrons.com": {"OK": 2}, "marketwatch.com": {"NOT_FOUND": 1}}
    assert st["last_not_ok_page"]["class"] == "NOT_FOUND"
    assert st["current_url_by_worker"]["barrons"] == "https://www.barrons.com/b"
    assert json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))["state"] == "reading"


def test_the_rolling_launcher_only_swaps_the_queue_file(tmp_path, monkeypatch):
    from scripts import night_reader_supervisor as S
    monkeypatch.setattr(S, "DJ", tmp_path)
    tpl = tmp_path / "queue_run.cmd"
    tpl.write_text("@echo off\r\npy.exe -m scripts.dowjones_pull --queue old\\Q.txt --handoff "
                   "--profile muratclaw --workers 3 >> x.log\r\n", encoding="utf-8")
    from scripts import dowjones_pull as DP
    monkeypatch.setattr(DP, "last_read_days", lambda names, **k: {n: "" for n in names})
    r = S.rolling_queue(tpl, day="2026-01-02", names=["MU", "BRK-B"])
    cmd = r["cmd"].read_text(encoding="utf-8")
    assert f"--queue {tmp_path / 'QUEUE_rolling_2026-01-02.txt'} --handoff" in cmd
    assert ">> x.log" in cmd and r["n_unread_today"] == 2


def test_the_wsj_stock_page_takes_sister_site_article_links():
    """Live 2026-09-28: the WSJ PLTR page listed Barron's and MarketWatch articles
    and no wsj.com article; a wsj.com-only pattern found 0 on every page."""
    import re
    from scripts import dowjones_pull as DP
    pat = re.compile(DP.SECTIONS["wsj"]["search"][1])
    assert pat.search("https://www.barrons.com/articles/palantir-stock-ai-faa-373cce03")
    assert pat.search("https://www.marketwatch.com/story/palantirs-stock-heading-a5fd451d")
    assert pat.search("https://www.wsj.com/finance/stocks/micron-memory-boom-1a2b3c4d")
    assert not pat.search("https://www.wsj.com/market-data/stock/pltr")
    assert not pat.search("https://www.investors.com/research/palantir-stock-buy-signal/")


def test_a_crashed_runs_blank_tab_is_closed_on_the_dedicated_instance_only():
    """The blank tabs piling up in the MuratClaw window: a killed run's blanked
    lane tabs (named in its receipt) were skipped as 'not on a Dow Jones host'."""
    class Drv(DirectStub):
        def tabs(self, profile_name=None):
            return [{"targetId": "0ADC0116C893CB1F4CF9474E76B43035", "url": "about:blank"},
                    {"targetId": "OWNER1", "url": "https://www.wsj.com/"}]
    d = Drv()
    res = WR.close_leftover_tabs(d, "muratclaw", ["0ADC0116C893CB1F4CF9474E76B43035"])
    assert res["closed"] == ["0ADC0116C893CB1F4CF9474E76B43035"] and d.closed == ["0ADC0116C893CB1F4CF9474E76B43035"]
    # not dedicated: a blank tab may be the owner's -> skipped
    class Plain(MultiStub):
        def tabs(self, profile_name=None):
            return [{"targetId": "0ADC0116C893CB1F4CF9474E76B43035", "url": "about:blank"}]
    p = Plain()
    res = WR.close_leftover_tabs(p, "muratclaw", ["0ADC0116C893CB1F4CF9474E76B43035"])
    assert res["closed"] == [] and p.closed == []
