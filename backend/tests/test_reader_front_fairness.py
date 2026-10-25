"""Actual dequeue/chooser tests with in-memory queues; no browser or data jobs."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, RLock
from types import SimpleNamespace

import pytest

from backend.services import reader_front_fairness as RF
from backend.services import reader_scheduler as RS
from scripts import reader_pool as RP

HOST = "wsj.com"
NOW = datetime.now(timezone.utc)


def front(seq=1, host=HOST, kind="front"):
    return dict(kind=kind, host=host, seq=seq, blane="front", tier=0)


def article(seq=1, host=HOST, **extra):
    return dict(
        kind="article",
        host=host,
        seq=seq,
        blane="news",
        tier=1,
        parent_url="fixture:front",
        **extra,
    )


def pool(items, *, streak=0, budget_filter=None):
    # Skip corpus/config initialization: exercise the actual locked Pool.take.
    p = RP.Pool.__new__(RP.Pool)
    p.lock = RLock()
    p.now_fn = lambda: NOW
    p.gov = SimpleNamespace(target=2, may_open=lambda n: n < 2)
    p.pending = list(items)
    p.front_dispatch_streak = Counter({HOST: streak})
    p.inflight = Counter()
    p.per_host = {HOST: 2, "barrons.com": 2}
    p.thr = SimpleNamespace(_rows=lambda: [], global_gap_s=(1.0, 1.0))
    p.cooling = SimpleNamespace(active=lambda now: {})
    p.host_blocked_until = {}
    p.books, p.fresh, p.last_read = set(), set(), {}
    p.budget_on = budget_filter is not None
    if budget_filter is not None:
        p._budget_filter = budget_filter
    p.budget_grants = Counter()
    p.budget_block = {}
    p.lane_inflight = Counter()
    # Native preimage-bound candidate also keeps its existing carry receipt.
    p.carry_receipts = SimpleNamespace(note=lambda *args: None)
    p._carry_id = lambda it: str(it.get("seq"))
    return p


def finish_dispatch(p, it):
    with p.lock:
        p.inflight[it["host"]] -= 1
        p.lane_inflight[it["blane"]] -= 1


def test_continuous_fronts_now_dispatch_waiting_articles():
    p = pool([article()])
    kinds = []
    for i in range(32):
        p.pending.append(front(i + 1))
        it = p.take(0)
        kinds.append(it["kind"])
        finish_dispatch(p, it)
        if it["kind"] == "article":
            p.pending.append(article(i + 2))
    assert kinds[:9] == ["front", "front", "article"] * 3
    assert kinds.count("article") == 10


def test_two_actual_threads_cannot_dispatch_third_consecutive_front():
    p = pool([front(1), front(2), article()], streak=1)
    ready = Barrier(3)

    def take(slot):
        ready.wait(timeout=5)
        return p.take(slot)

    with ThreadPoolExecutor(max_workers=2) as workers:
        a, b = workers.submit(take, 0), workers.submit(take, 1)
        ready.wait(timeout=5)
        picked = [a.result(timeout=5), b.result(timeout=5)]
    assert Counter(it["kind"] for it in picked) == {"front": 1, "article": 1}
    assert p.inflight[HOST] == 2
    assert len(p.pending) == 1
    assert p.front_dispatch_streak[HOST] in (0, 1)


@pytest.mark.parametrize("kind", ["front", "front_text"])
def test_no_discovered_article_never_idles_or_overflows_counter(kind):
    p = pool([], streak=2)
    for i in range(20):
        item = front(i, kind=kind)
        p.pending.append(item)
        assert p.take(0) is item
        finish_dispatch(p, item)
    assert p.front_dispatch_streak[HOST] == 2


def test_article_filtered_out_by_budget_cannot_trigger_or_bypass_fairness():
    f, a = front(), article()
    seen = []

    def budget_filter(by_host, **kw):
        seen.append(by_host[HOST][:])
        return {HOST: [f]}

    p = pool([f, a], streak=2, budget_filter=budget_filter)
    assert p.take(0) is f
    assert seen == [[f, a]]
    assert p.pending == [a]
    assert p.front_dispatch_streak[HOST] == 2


def test_empty_budget_filter_preserves_queue_and_counter():
    items = [front(), article()]
    p = pool(items, streak=2, budget_filter=lambda *a, **kw: {})
    assert p.take(0) is None
    assert p.pending == items
    assert p.front_dispatch_streak[HOST] == 2


@pytest.mark.parametrize("hold", ["cooling", "host_blocked", "slots", "governor"])
def test_existing_dispatch_holds_remain_in_force(hold):
    items = [front(), article()]
    p = pool(items, streak=2)
    if hold == "cooling":
        p.cooling = SimpleNamespace(active=lambda now: {HOST: "held"})
    elif hold == "host_blocked":
        p.host_blocked_until[HOST] = NOW + timedelta(minutes=1)
    elif hold == "slots":
        p.per_host[HOST] = 0
    else:
        p.gov = SimpleNamespace(target=0, may_open=lambda n: False)
    assert p.take(0) is None
    assert p.pending == items
    assert p.front_dispatch_streak[HOST] == 2


def test_other_kinds_and_article_priority_preserved_without_mutating_inputs():
    f = front()
    old, best = article(2, position=2), article(1, position=1)
    robots = dict(kind="robots", tier=0, host=HOST, seq=10, blane="news")
    original = {HOST: [f, old, best, robots]}
    filtered = RF.filter_front_streaks(original, {HOST: 2})
    assert original[HOST] == [f, old, best, robots]
    assert filtered[HOST] == [old, best, robots]
    assert filtered[HOST][0] is old
    p = pool(original[HOST], streak=2)
    assert p.take(0) is robots  # Never suppress the existing robots prerequisite.
    assert p.front_dispatch_streak[HOST] == 0
    articles = RF.filter_front_streaks({HOST: [f, old, best]}, {HOST: 2})
    assert min(articles[HOST], key=p._key) is best


def test_undiscovered_or_other_host_articles_do_not_suppress_fronts():
    f, a = front(), article(host="barrons.com")
    unknown_parent = dict(kind="article", host=HOST, tier=1)
    items = {HOST: [f, unknown_parent], "barrons.com": [a]}
    assert RF.filter_front_streaks(items, {HOST: 2}) == items


def test_failed_choice_has_no_dequeue_accounting(monkeypatch):
    p = pool([front(), article()], streak=2)

    def fail(*args, **kwargs):
        raise RuntimeError("fixture")

    monkeypatch.setattr(RS, "choose", fail)
    with pytest.raises(RuntimeError, match="fixture"):
        p.take(0)
    assert len(p.pending) == 2
    assert p.front_dispatch_streak[HOST] == 2
    # Exception released the actual pool lock for another thread.
    with ThreadPoolExecutor(max_workers=1) as workers:

        def acquire():
            with p.lock:
                return True

        assert workers.submit(acquire).result(timeout=5)


def test_host_readiness_and_inflight_preference_remain_the_normal_chooser():
    f, a = front(), article()
    other = front(host="barrons.com")
    eligible = RF.filter_front_streaks({HOST: [f, a], "barrons.com": [other]}, {HOST: 2})
    p = pool([])
    kwargs = dict(free_slots={HOST: 1, "barrons.com": 1}, blocked=set(), now=NOW, key=p._key)
    assert RS.choose(eligible, free_at={HOST: NOW + timedelta(minutes=1)}, **kwargs) is other
    assert RS.choose(eligible, free_at={}, in_flight={HOST: 1}, **kwargs) is other
