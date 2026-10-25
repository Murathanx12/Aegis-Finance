"""Portable synthetic tests of actual helper/Pool.take AST/unchanged RS.choose.

No private evidence preimages, app imports, providers or native operations.
The baseline disables only the global key helper on a local fixture object.
"""
import __future__
import ast
import builtins
import importlib.util
import threading
import unittest
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

B = Path(__file__).resolve().parents[2]
NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)
A, C = "a.invalid", "b.invalid"


def item(kind, host=C, seq=1, parent=False):
    return dict(kind=kind, host=host, seq=seq, tier=1 if kind == "article" else 0,
                parent_url="fixture:front" if parent else "", blane="fixture")


def article(host=A, seq=0):
    return item("article", host, seq, True)


def key_namespace():
    ns = dict(datetime=datetime, timedelta=timedelta, timezone=timezone,
              TIER_FRONT=0, TIER_FRONT_NEWS=1, TIER_BOOK=2, TIER_FRESH=3, TIER_REST=4)
    tree = ast.parse((B / "backend/services/reader_scheduler.py").read_bytes())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name in {"choose", "priority_key", "recency_rank", "ticker_tier"}]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "actual_unchanged_scheduler", "exec",
                 flags=__future__.annotations.compiler_flag), ns)
    return ns


class Model:
    def __init__(self, before=False):
        spec = importlib.util.spec_from_file_location("private_fairness",
                  B / "backend/services/reader_front_fairness.py")
        production = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(production)  # Actual production helper, stdlib only.
        self.rf = SimpleNamespace(
            filter_front_streaks=production.filter_front_streaks,
            next_front_streak=production.next_front_streak,
            global_front_key=(lambda by_host, streak, *, key, **kw: key)
                             if before else production.global_front_key,
        )
        self.rs = SimpleNamespace(**key_namespace(), budget_lane=lambda *a, **kw: "fixture")
        self.unexpected_imports = []

        def forbidden_import(name, *args, **kwargs):
            self.unexpected_imports.append(name)
            raise AssertionError("application import forbidden")

        ns = dict(Counter=Counter, defaultdict=defaultdict, timedelta=timedelta,
                  RF=self.rf, RS=self.rs, WR=SimpleNamespace(fit_global_gap=lambda at, stamps, gap: at),
                  __builtins__={**vars(builtins), "__import__": forbidden_import})
        tree = ast.parse((B / "scripts/reader_pool.py").read_bytes())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Pool")
        methods = [n for n in cls.body if isinstance(n, ast.FunctionDef)
                   and n.name in {"take", "_key", "_blocked"}]
        selected = ast.ClassDef(name="Pool", bases=[], keywords=[], body=methods, decorator_list=[])
        exec(compile(ast.fix_missing_locations(ast.Module(body=[selected], type_ignores=[])),
                     "actual_pool_take", "exec", flags=__future__.annotations.compiler_flag), ns)
        self.Pool = ns["Pool"]
        self.key = lambda it: self.rs.priority_key(it, books=set(), fresh=set(), last_read={})

    def options(self):
        return dict(free_slots={A: 2, C: 2}, blocked=set(), free_at={}, now=NOW, in_flight={})

    def choose(self, pending, streak=2, options=None, locals_=None):
        opts = self.options() if options is None else options
        eligible = self.rf.filter_front_streaks(pending, {A: 2} if locals_ is None else locals_)
        key = self.rf.global_front_key(eligible, streak, choose=self.rs.choose, key=self.key, **opts)
        return self.rs.choose(eligible, key=key, **opts), key, eligible

    def pool(self, pending, streak=0, budget=None):
        p = self.Pool()
        p.lock = threading.RLock()
        p.pending = list(pending)
        p.global_front_dispatch_streak = streak
        p.front_dispatch_streak = Counter({A: 2})
        p.now_fn = lambda: NOW
        p.gov = SimpleNamespace(target=2, may_open=lambda n: n < 2)
        p.inflight = Counter()
        p.per_host = {A: 2, C: 2}
        p.thr = SimpleNamespace(_rows=lambda: [], global_gap_s=(1.0, 1.0))
        p.cooling = SimpleNamespace(active=lambda now: {})
        p.host_blocked_until = {}
        p.books, p.fresh, p.last_read = set(), set(), {}
        p.budget_on = budget is not None
        if budget is not None:
            p._budget_filter = budget
        p.budget_grants, p.lane_inflight = Counter(), Counter()
        p.budget_block = {}
        p.carry_receipts = SimpleNamespace(note=lambda *args: None)
        p._carry_id = lambda it: str(it["seq"])
        return p


def complete(p, it):
    with p.lock:
        p.inflight[it["host"]] -= 1
        p.lane_inflight[it["blane"]] -= 1


class GlobalFrontBurstTests(unittest.TestCase):

    def setUp(self):
        self.m = Model()

    def tearDown(self):
        self.assertEqual(self.m.unexpected_imports, [])

    def test_original_cross_host_32_repro_and_fixed_first_article(self):
        old = Model(before=True)
        news = article()
        before = old.pool([news, item("front", A, 100)])
        got_before = []
        for i in range(32):
            before.pending.append(item("front", C, i + 1))
            chosen = before.take(0)
            got_before.append(chosen["kind"])
            complete(before, chosen)
        self.assertEqual(got_before, ["front"] * 32)
        self.assertIn(news, before.pending)
        current = self.m.pool([news, item("front", A, 100)])
        got_after = []
        for i in range(32):
            current.pending.append(item("front", C, i + 1))
            chosen = current.take(0)
            got_after.append(chosen["kind"])
            complete(current, chosen)
        self.assertEqual(got_after[:3], ["front", "front", "article"])
        self.assertEqual(got_after.count("article"), 1)
        self.assertEqual(old.unexpected_imports, [])

    def test_nine_original_controls(self):
        for which, expected in (
            ("b_blocked", "article"), ("b_slots", "article"), ("b_late", "article"),
            ("b_inflight", "article"), ("a_blocked", "front"), ("a_slots", "front"),
            ("a_late", "front"), ("a_inflight", "front"), ("budget_removed", "front"),
        ):
            with self.subTest(control=which):
                news = article()
                pending = {A: [item("front", A, 100), news], C: [item("front", C, 1)]}
                opts = self.m.options()
                if which.endswith("blocked"):
                    opts["blocked"] = {A if which[0] == "a" else C}
                elif which.endswith("slots"):
                    opts["free_slots"][A if which[0] == "a" else C] = 0
                elif which.endswith("late"):
                    opts["free_at"][A if which[0] == "a" else C] = NOW + timedelta(seconds=6)
                elif which.endswith("inflight"):
                    opts["in_flight"][A if which[0] == "a" else C] = 1
                else:
                    pending[A].remove(news)
                got, key, _ = self.m.choose(pending, options=opts)
                self.assertEqual(got["kind"], expected)
                if which.startswith("a_") or which == "budget_removed":
                    self.assertIs(key, self.m.key)

    def test_exact_ready_band_and_future_earliest_trap(self):
        for a_s, b_s, expected in ((5, 0, "article"), (5.000001, 0, "front"),
                                    (15, 10, "article"), (15.000001, 10, "front")):
            with self.subTest(a=a_s, b=b_s):
                options = self.m.options()
                options["free_at"] = {A: NOW + timedelta(seconds=a_s), C: NOW + timedelta(seconds=b_s)}
                got, key, eligible = self.m.choose({A: [article()], C: [item("front")]}, options=options)
                self.assertEqual(got["kind"], expected)
                self.assertIn(C, eligible)  # Ready front host was never deleted.
                if expected == "front":
                    self.assertIs(key, self.m.key)

    def test_inflight_precedence_is_outside_wrapped_key(self):
        options = self.m.options()
        options["in_flight"] = {A: 1, C: 0}
        got, key, _ = self.m.choose({A: [article()], C: [item("front")]}, options=options)
        self.assertEqual(got["kind"], "front")
        self.assertIs(key, self.m.key)

    def test_robots_search_and_nonfront_relative_order_preserved(self):
        for kind in ("robots", "search"):
            news, prerequisite = article(), item(kind, C)
            got, wrapped, _ = self.m.choose({A: [news], C: [item("front", C, 9), prerequisite]})
            self.assertIs(got, prerequisite)
            other = [news, prerequisite, item("media", A, 3), item("stock_links", C, 8)]
            self.assertEqual(sorted(other, key=self.m.key), sorted(other, key=wrapped))
            self.assertEqual(self.m.key(news)[0], 1)
            self.assertEqual(len(self.m.key(news)), 6)

    def test_original_map_list_item_identity_and_no_probe_priority_calls(self):
        news, front = article(), item("front")
        pending = {A: [news], C: [front]}
        identities = [(id(v), tuple(map(id, v))) for v in pending.values()]
        calls = []
        original = self.m.key

        def key(it):
            calls.append(it)
            return original(it)

        seen_maps = []

        def choose(mapping, **kwargs):
            seen_maps.append(mapping)
            return self.m.rs.choose(mapping, **kwargs)

        wrapped = self.m.rf.global_front_key(pending, 2, choose=choose, key=key, **self.m.options())
        self.assertEqual(calls, [])  # Binary probe never calls the original key.
        got = choose(pending, key=wrapped, **self.m.options())
        self.assertIs(got, news)
        self.assertEqual([id(m) for m in seen_maps], [id(pending), id(pending)])
        self.assertEqual(identities, [(id(v), tuple(map(id, v))) for v in pending.values()])

    def test_below_cap_no_article_and_unparented_article_baseline(self):
        for pending, streak in (({C: [item("front")]}, 2),
                                 ({A: [item("article", A)], C: [item("front")]}, 2),
                                 ({A: [article()], C: [item("front")]}, 1)):
            got, key, eligible = self.m.choose(pending, streak=streak)
            self.assertIs(key, self.m.key)
            self.assertIs(got, self.m.rs.choose(eligible, key=self.m.key, **self.m.options()))

    def test_no_article_front_text_and_finite_backlog_no_idle(self):
        p = self.m.pool([], streak=2)
        for i in range(32):
            front = item("front_text" if i % 2 else "front", C, i)
            p.pending.append(front)
            self.assertIs(p.take(0), front)
            complete(p, front)
        self.assertEqual(p.global_front_dispatch_streak, 2)
        news = article()
        p.pending.extend([news, item("front", C, 100)])
        chosen = p.take(0)
        self.assertIs(chosen, news)
        self.assertEqual(p.global_front_dispatch_streak, 0)

    def test_budget_removed_article_not_resurrected(self):
        news, front = article(), item("front")
        seen = []

        def budget(mapping, **kwargs):
            seen.append(news in mapping[A])
            return {C: [front]}

        p = self.m.pool([news, front], streak=2, budget=budget)
        self.assertIs(p.take(0), front)
        self.assertEqual(seen, [True])
        self.assertIn(news, p.pending)
        self.assertEqual(p.global_front_dispatch_streak, 2)

    def test_empty_budget_governor_slots_and_cooling_hold(self):
        for hold in ("budget", "governor", "slots", "cooling"):
            with self.subTest(hold=hold):
                pending = [article(), item("front")]
                p = self.m.pool(pending, streak=2, budget=(lambda *a, **kw: {}) if hold == "budget" else None)
                if hold == "governor":
                    p.gov.target = 0
                elif hold == "slots":
                    p.per_host = {A: 0, C: 0}
                elif hold == "cooling":
                    p.cooling = SimpleNamespace(active=lambda now: {A: "fixture", C: "fixture"})
                self.assertIsNone(p.take(0))
                self.assertEqual(p.pending, pending)
                self.assertEqual(p.global_front_dispatch_streak, 2)

    def test_nonfront_reset_and_worktree_dequeue(self):
        for kind in ("robots", "search"):
            p = self.m.pool([article(), item(kind, C)], streak=2)
            notes = []
            p.carry_receipts.note = lambda *args: notes.append(args)
            chosen = p.take(0)
            self.assertEqual(chosen["kind"], kind)
            self.assertEqual(p.global_front_dispatch_streak, 0)
            # This test is bound to the W source profile; it introduces no carry call.
            self.assertEqual(notes, [])

    def test_three_host_real_threads_with_baseline_negative_control(self):
        third = "third-front-only.invalid"
        for before in (True, False):
            for repeat in range(3):
                with self.subTest(baseline=before, repeat=repeat):
                    model = Model(before=before)
                    news = article()
                    p = model.pool([news, item("front", C, 1), item("front", third, 2),
                                    item("front", C, 3)], streak=1)
                    p.per_host[third] = 2
                    entered, release, requested = threading.Event(), threading.Event(), threading.Event()
                    original = model.rs.choose
                    snapshots = []

                    def held(mapping, **kwargs):
                        snapshots.append((p.inflight[A], p.inflight[C], p.inflight[third]))
                        if len(snapshots) == 1:
                            entered.set()
                            if not release.wait(3):
                                raise AssertionError("fixture release timed out")
                        return original(mapping, **kwargs)

                    model.rs.choose = held
                    with ThreadPoolExecutor(max_workers=2) as workers:
                        first = workers.submit(p.take, 0)
                        try:
                            self.assertTrue(entered.wait(3))

                            def second_take():
                                requested.set()
                                return p.take(1)

                            second = workers.submit(second_take)
                            self.assertTrue(requested.wait(3))
                            self.assertFalse(second.done())
                        finally:
                            release.set()
                        chosen = [first.result(timeout=3), second.result(timeout=3)]
                    self.assertEqual((chosen[0]["kind"], chosen[0]["host"]), ("front", C))
                    self.assertIn((0, 1, 0), snapshots)  # A and third BOTH zero-in-flight.
                    if before:
                        self.assertEqual((chosen[1]["kind"], chosen[1]["host"]), ("front", third))
                        self.assertEqual(p.global_front_dispatch_streak, 2)
                    else:
                        self.assertIs(chosen[1], news)
                        self.assertEqual(p.global_front_dispatch_streak, 0)
                    self.assertEqual(sum(p.inflight.values()), 2)
                    self.assertEqual(len(p.pending), 2)
                    self.assertEqual(model.unexpected_imports, [])

    def test_three_host_ready_band_not_widened_by_excluded_low_inflight(self):
        third = "third-front-only.invalid"
        for seconds, expected in ((5, "article"), (5.000001, "front")):
            opts = self.m.options()
            opts["free_slots"][third] = 2
            opts["free_at"] = {A: NOW + timedelta(seconds=seconds),
                               C: NOW, third: NOW + timedelta(seconds=10)}
            opts["in_flight"] = {A: 1, C: 1, third: 0}
            news, front, excluded = article(), item("front"), item("front", third)
            got, key, mapping = self.m.choose({A: [news], C: [front], third: [excluded]}, options=opts)
            self.assertEqual(got["kind"], expected)
            self.assertIsNot(got, excluded)
            self.assertIs(mapping[third][0], excluded)
            if expected == "front":
                self.assertIs(key, self.m.key)

    def test_probe_final_and_original_key_exceptions_do_not_dequeue(self):
        for failure in ("probe", "final", "key"):
            with self.subTest(stage=failure):
                model = Model()
                pending = [article(), item("front")]
                p = model.pool(pending, streak=2)
                original = model.rs.choose
                calls = []

                def choose(mapping, **kwargs):
                    calls.append(True)
                    if (failure == "probe" and len(calls) == 1) or (failure == "final" and len(calls) == 2):
                        raise RuntimeError("fixture choice failure")
                    return original(mapping, **kwargs)
                model.rs.choose = choose
                if failure == "key":
                    p._key = lambda it: (_ for _ in ()).throw(RuntimeError("fixture key failure"))
                with self.assertRaises(RuntimeError):
                    p.take(0)
                self.assertEqual(len(calls), 1 if failure == "probe" else 2)
                self.assertEqual(p.pending, pending)
                self.assertEqual(p.global_front_dispatch_streak, 2)
                self.assertEqual(p.inflight, Counter())
                with ThreadPoolExecutor(max_workers=1) as worker:
                    def lock_available():
                        with p.lock:
                            return True
                    self.assertTrue(worker.submit(lock_available).result(timeout=3))
                self.assertEqual(model.unexpected_imports, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
