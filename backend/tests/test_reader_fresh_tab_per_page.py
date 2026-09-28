"""A read tab is CLOSED after its read on the dedicated instance (2026-09-28).

Murat, 2026-09-28: "openclaw opens a website then it goes blank, but if it
clicks on go back to the previous webpage they launch back to the intended
website". The reader navigated every lane tab to `about:blank` after each read
(a renderer-memory rule) and also parked a listing page blank "for its turn",
so the owner watched pages load and vanish, with the real page one step back
in the tab's history. On the dedicated Chrome the tab is now closed after its
read and the next page load opens a FRESH tab at its URL:

* no `navigate about:blank` is ever sent on the dedicated profile;
* on every tab, the text is read BEFORE that tab is closed;
* every tab the run opened is closed (no orphans), and the owner's tab is
  never touched;
* a BLANK / empty page gives its throttle slot back (it does not count against
  the hourly, daily or per-host caps);
* a profile that is not dedicated keeps the old blank-after-read behaviour.

Test doubles only: no network, browser or CLI; fake clock; tmp_path.
"""
from __future__ import annotations

import pytest

from backend.services import web_reader as WR
from backend.tests.test_dowjones_chunk_j import (  # noqa: F401 -- fixtures reused on purpose
    Clock, MultiStub, _clock_throttle, ledger)
from backend.tests.test_reader_direct_open import DirectStub

A1 = "https://www.wsj.com/articles/one-story-11aa22bb"
A2 = "https://www.wsj.com/articles/two-story-33cc44dd"
LISTING = "https://www.wsj.com/news/heard-on-the-street"


def _lines(path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def _no_blank_navigation(calls) -> bool:
    return not any(c[0] == "navigate" and c[2] and c[2][0] == WR.BLANK_URL for c in calls)


def _read_before_close(calls) -> bool:
    """Every tab that was read was read before it was closed."""
    closed_at = {c[1]: i for i, c in enumerate(calls) if c[0] == "close"}
    return all(closed_at.get(c[1], 10 ** 9) > i for i, c in enumerate(calls)
               if c[0] == "read_text")


def test_dedicated_reader_closes_after_read_and_opens_fresh_tabs(ledger):
    drv = DirectStub()
    _, th = _clock_throttle(ledger / "thr.log")
    op = WR.open_lane_tab(drv, "muratclaw", LISTING, throttle=th, host="wsj.com")
    rd = WR.Reader(profile="muratclaw", tab=op["new_tab"], throttle=th, driver=drv,
                   lock=False, direct_open=True)
    a1 = rd.read_article(A1, store=False)
    a2 = rd.read_article(A2, store=False)
    assert a1["url"] == A1 and a2["url"] == A2 and a1["page_class"] == "OK"
    assert _no_blank_navigation(drv.calls) and _read_before_close(drv.calls)
    # page 1 in the listing's tab (navigate), page 2 in a FRESH tab opened at A2
    opens = [c for c in drv.calls if c[0] == "open_tab"]
    assert [c[2] for c in opens] == [LISTING, A2]
    assert rd.closes_after_read == 2 and rd.blanks == 0 and rd.retired
    assert sorted(drv.closed) == sorted(c[3] for c in opens)
    assert rd.orphans() == [] and "OWNER1" not in drv.closed
    assert rd.rotations[-1]["why"] == "fresh_tab_per_page"
    assert len(_lines(ledger / "thr.log")) == 3            # open + navigate + reopen


def test_a_blank_page_gives_its_slot_back(ledger):
    drv = DirectStub(pages={A1: "", A2: "x"})
    _, th = _clock_throttle(ledger / "thr.log")
    op = WR.open_lane_tab(drv, "muratclaw", LISTING, throttle=th, host="wsj.com")
    rd = WR.Reader(profile="muratclaw", tab=op["new_tab"], throttle=th, driver=drv,
                   lock=False, direct_open=True)
    with pytest.raises(WR.ReaderRefused, match="REFUSED_EMPTY_READ"):
        rd.read_article(A1, store=False)                  # no text at all
    with pytest.raises(WR.ReaderRefused, match="PAGE_BLANK"):
        rd.read_article(A2, store=False)                  # a page with (almost) no text
    assert len(_lines(ledger / "thr.log")) == 1            # only the listing's open counts
    assert len(rd.slot_refunds) == 2
    assert rd.page_classes["wsj.com"]["BLANK"] == 2
    assert _no_blank_navigation(drv.calls) and rd.orphans() == []


def test_run_plan_on_the_dedicated_instance_never_blanks_a_tab(ledger):
    from scripts import dowjones_pull as DP
    drv = DirectStub()
    _, th = _clock_throttle(ledger / "thr.log")
    lanes = DP.parse_plan("wsj:heard_on_the_street:2,marketwatch:analyst_estimates:MU|DKNG")
    parents = DP.resolve_parent_tabs(["wsj", "marketwatch"], [], direct=True)
    rc = DP.run_plan(lanes, parents=parents, driver=drv, throttle=th, stored={})
    assert rc["n_articles"] == 3 and not rc["stopped"]    # the WSJ listing shows 1 link
    assert _no_blank_navigation(drv.calls) and _read_before_close(drv.calls)
    assert rc["blanks"] == 0 and rc["closes_after_read"] >= 3
    assert rc["orphaned_tabs"] == [] and "OWNER1" not in drv.closed
    assert all(c[0] != "open_from_tab" for c in drv.calls)


def test_a_profile_that_is_not_dedicated_still_blanks_after_read(ledger):
    drv = MultiStub()
    _, th = _clock_throttle(ledger / "thr.log")
    rd = WR.Reader(profile="muratclaw", tab="t20", throttle=th, driver=drv, lock=False)
    rd.read_article(A1, store=False)
    assert rd.blanks == 1 and rd.closes_after_read == 0
    assert any(c[0] == "navigate" and c[2] and c[2][0] == WR.BLANK_URL for c in drv.calls)
