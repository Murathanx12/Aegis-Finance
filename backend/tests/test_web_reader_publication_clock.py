"""Publication instants from article text, with no browser or network calls."""

from backend.services import web_reader as WR


def test_yahoo_viewer_offset_precedes_issuer_date_only_dateline():
    article = ("ASML Netherlands BV\n"
               "Wed, 14 October 2026 at 1:00 pm GMT+8 9 min read\n"
               "VELDHOVEN, the Netherlands, October 14, 2026 - Today, ASML published results.")
    assert WR.parse_published(article) == "2026-10-14T05:00:00+00:00"


def test_yahoo_offsets_cross_utc_date_and_keep_minute_precision():
    assert WR.parse_published("Wed, 14 October 2026 at 12:15 am GMT+08:30") == (
        "2026-10-13T15:45:00+00:00")
    assert WR.parse_published("Wed, 14 October 2026 at 11:59 pm GMT-04:00") == (
        "2026-10-15T03:59:00+00:00")


def test_yahoo_invalid_or_conflicting_headers_fail_closed():
    dateline = "\nOctober 14, 2026"
    for header in ("Wed, 14 October 2026 at 1:00 pm GMT+25",
                   "Wed, 14 October 2026 at 1:00 pm GMT+8:60",
                   "Wed, 14 October 2026 at 13:00 pm GMT+8",
                   "Tue, 14 October 2026 at 1:00 pm GMT+8"):
        assert WR.parse_published(header + dateline) is None
    assert WR.parse_published(
        "Wed, 14 October 2026 at 1:00 pm GMT+8\n"
        "Wed, 14 October 2026 at 2:00 pm GMT+8" + dateline) is None


def test_dow_jones_eastern_daylight_and_standard_time():
    assert WR.parse_published("Published Oct 14, 2026, 1:00 p.m. ET") == (
        "2026-10-14T17:00:00+00:00")
    assert WR.parse_published("Published Jan 14, 2026, 1:00 p.m. ET") == (
        "2026-01-14T18:00:00+00:00")


def test_date_only_and_eastern_dst_transition_clocks_have_no_instant():
    assert WR.parse_published("October 14, 2026") is None
    assert WR.parse_published("Published Nov 1, 2026, 1:30 a.m. ET") is None
    assert WR.parse_published("Published Mar 8, 2026, 2:30 a.m. ET") is None
