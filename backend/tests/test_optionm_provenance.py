"""The OptionMetrics cache is month-end because WE filtered it. Pin that.

Twice now a property of our own extraction has been written down as a property
of the data:

1. "~87 rows/secid-year, so it is not daily" — row count cannot identify
   sampling frequency when each date carries eight surface coordinates. Right
   conclusion, invalid route.
2. "vsurf_me is month-end, so the implied-vol rung is monthly" — measured the
   cache correctly and then stated a conclusion about the entitlement. The
   month-end restriction is a WHERE clause in our own pull script, against
   `optionm.vsurfd<year>`, which is the DAILY table.

The second error is the expensive one: it would have sent the next session to
build a monthly ladder that cannot be compared like-for-like against N11's
daily rungs, when a daily rung was available the whole time.

So the provenance is asserted against the pull script itself. If someone
changes the extraction, this test is where the registry's claim gets rechecked.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MODULE = Path("C:/Users/mrthn/Aegis module")
PULL = MODULE / "scripts" / "fetch_wrds_optionm.py"
REGISTRY = Path(__file__).resolve().parents[1] / "data" / "signal_registry.yaml"

pytestmark = pytest.mark.skipif(
    not PULL.exists(),
    reason="the sibling Aegis module repo is not present on this machine")


def _pull_text() -> str:
    return PULL.read_text(encoding="utf-8", errors="replace")


def test_the_source_table_is_the_daily_surface():
    """`vsurfd` — the d is the point."""
    assert re.search(r"from\s+optionm\.vsurfd", _pull_text()), (
        "the pull no longer reads optionm.vsurfd; the registry's claim that "
        "the entitled source is DAILY needs re-checking")


def test_the_month_end_restriction_is_ours_and_not_the_data():
    """The filter that makes the cache monthly, quoted from our own SQL."""
    text = _pull_text()
    assert "date_trunc('month', date)" in text, (
        "the month-end filter is gone from the pull; if the cache is still "
        "month-end, the reason is now something else and the registry entry "
        "is describing a world that no longer exists")
    assert "max(date)" in text


def test_the_grid_restriction_is_ours_too():
    """days and delta are filtered by us; the surface is wider than the cache."""
    text = _pull_text()
    assert re.search(r"days\s+in\s*\(\s*30\s*,\s*91\s*\)", text)
    assert re.search(r"delta\s+in\s*\(", text)


def test_the_registry_does_not_call_the_rung_monthly():
    """The specific sentence that was wrong, kept out by name.

    Not a style check: "the implied-vol rung is monthly" is a scope claim that
    changes what the next trial builds.
    """
    reg = REGISTRY.read_text(encoding="utf-8", errors="replace").lower()
    for banned in ("defines its own monthly ladder",
                   "it defines its own monthly"):
        assert banned not in reg, (
            f"signal_registry.yaml still says {banned!r}. The cached EXTRACT "
            "is month-end; the ENTITLED SOURCE is daily.")


def test_the_registry_records_the_entitlement_as_proven_not_assumed():
    reg = REGISTRY.read_text(encoding="utf-8", errors="replace")
    assert "optionm.vsurfd" in reg, (
        "the registry no longer names the daily source table, so a reader "
        "cannot tell that the monthly cache is a choice")
