"""Dispatch fairness for already eligible reader queues; no acquisition authority."""

from __future__ import annotations

from collections.abc import Mapping

FRONT_DISPATCH_CAP = 2
FRONT_KINDS = frozenset({"front", "front_text"})


def filter_front_streaks(
    by_host: Mapping[str, list[dict]], streaks: Mapping[str, int]
) -> dict[str, list[dict]]:
    """Suppress fronts after two grants only where a discovered article waits.

    Input is the pool's budget-filtered candidate set. Other kinds (including
    robots work), item identities and order remain intact for the normal chooser.
    """
    out = {}
    for host, items in by_host.items():
        article_waits = any(it.get("kind") == "article" and it.get("parent_url") for it in items)
        if streaks.get(host, 0) >= FRONT_DISPATCH_CAP and article_waits:
            out[host] = [it for it in items if it.get("kind") not in FRONT_KINDS]
        else:
            out[host] = list(items)
    return out


def next_front_streak(previous: int, item: dict) -> int:
    """Count grants, including failed reads; saturate at the dispatch cap."""
    if item.get("kind") in FRONT_KINDS:
        return min(FRONT_DISPATCH_CAP, previous + 1)
    return 0
