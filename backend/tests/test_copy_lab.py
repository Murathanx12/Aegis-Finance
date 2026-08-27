"""COPY-LAB: forward paper lanes that cannot invent a history.

These lanes are PRODUCT_EXPERIMENT / NOT VALIDATED ALPHA and may run before any
hypothesis is certified. What they may never do is manufacture a track record —
so the tests that matter here are the ones about what the engine REFUSES:
a retroactive fill, a same-session fill, a fill at a price nobody printed, a
position size derived from a disclosed RANGE, and a liquidity floor that passes
a name because its price is missing.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from backend.services.copy_lab import engine as E
from backend.services.copy_lab import lanes as L
from backend.services.copy_lab import store as S
from backend.services.copy_lab.execution import (NotExecutable,
                                                 first_executable_session,
                                                 to_ny_date)
from backend.services.teacher_library.events import TeacherEvent


# ── fixtures ────────────────────────────────────────────────────────────────
SESSIONS = [date(2026, 8, 3) + timedelta(days=i) for i in range(40)]
SESSIONS = [d for d in SESSIONS if d.weekday() < 5]


class FakePrices:
    """A price panel with holes in it, because real ones have holes."""

    def __init__(self, px=50.0, adv=5e8, missing=(), no_open=(), dark_from=None):
        self.px, self.adv = px, adv
        self.missing = set(missing)          # tickers with no price at all
        self.no_open = set(no_open)          # (ticker, date) with no open print
        self.dark_from = dark_from or {}     # ticker -> date it goes dark

    def sessions(self):
        return list(SESSIONS)

    def _dark(self, ticker, day):
        d = self.dark_from.get(ticker)
        return d is not None and day >= d

    def open_price(self, ticker, day):
        if ticker in self.missing or self._dark(ticker, day):
            return None
        if (ticker, day) in self.no_open:
            return None
        return self.px

    def close_price(self, ticker, day):
        if ticker in self.missing or self._dark(ticker, day):
            return None
        return self.px

    def adv20(self, ticker, day):
        if ticker in self.missing:
            return None
        return self.adv


def _event(ticker="AAPL", actor="INSIDER-1", public_at="2026-08-11T14:00:00+00:00",
           action="BUY", actor_type="CORPORATE_INSIDER", status="OK_DATA",
           **kw):
    return TeacherEvent(
        source="sec_form4", source_event_id=f"{ticker}-{actor}-{public_at}",
        actor_id=actor, actor_type=actor_type, action_type=action,
        ticker_at_event=ticker, public_at=public_at,
        transaction_at=kw.pop("transaction_at", None), status=status, **kw)


@pytest.fixture
def lane(tmp_path):
    spec = L.load_lanes()["CORPORATE_INSIDER_CLUSTER"]
    S.seed_lane(spec, root=tmp_path, seeded_at="2026-08-10T00:00:00+00:00")
    return spec, tmp_path


@pytest.fixture
def activist(tmp_path):
    spec = L.load_lanes()["ACTIVIST_13D"]
    S.seed_lane(spec, root=tmp_path, seeded_at="2026-08-10T00:00:00+00:00")
    return spec, tmp_path


# ── the configuration ───────────────────────────────────────────────────────
def test_two_lanes_active_and_twelve_created_inactive():
    lanes = L.load_lanes()
    active = sorted(k for k, v in lanes.items() if v.active)
    assert active == ["ACTIVIST_13D", "CORPORATE_INSIDER_CLUSTER"]
    assert len(lanes) == 14
    assert len([v for v in lanes.values() if not v.active]) == 12


def test_every_inactive_lane_says_what_blocks_it():
    for name, spec in L.load_lanes().items():
        if not spec.active:
            assert spec.blocked_by, f"{name} is inactive with no reason"


def test_calacanis_is_source_unavailable_rather_than_guessed():
    spec = L.load_lanes()["CALACANIS_PUBLIC_COPY"]
    assert not spec.active
    assert "SOURCE_UNAVAILABLE" in spec.blocked_by


def test_both_cramer_directions_are_declared_in_advance():
    """Choosing the direction after seeing performance is outcome-shopping."""
    lanes = L.load_lanes()
    assert "CRAMER_FOLLOW" in lanes and "CRAMER_INVERSE" in lanes
    assert not lanes["CRAMER_FOLLOW"].active
    assert not lanes["CRAMER_INVERSE"].active


def test_every_lane_carries_the_experimental_label():
    for spec in L.load_lanes().values():
        assert spec.validation_status == "PRODUCT_EXPERIMENT"
        assert spec.label == "PRODUCT_LANE"


def test_a_lane_cannot_be_activated_by_editing_the_yaml(tmp_path):
    """Two independent guards, and an edit has to get past both.

    Flipping `active` alone trips the blocked-source guard. Removing the
    blocker as well trips the authorised-set guard, which lives in Python and
    not in the file being edited.
    """
    src = L.CONFIG_PATH.read_text(encoding="utf-8")
    flipped = src.replace("  CRAMER_FOLLOW:\n    active: false",
                          "  CRAMER_FOLLOW:\n    active: true")
    p = tmp_path / "flipped.yaml"
    p.write_text(flipped, encoding="utf-8")
    with pytest.raises(L.LaneConfigError, match="never ran"):
        L.load_lanes(p)

    unblocked = flipped.replace(
        "    blocked_by: SOURCE_UNAVAILABLE — no timestamped feed ingested\n",
        "", 1)
    p2 = tmp_path / "unblocked.yaml"
    p2.write_text(unblocked, encoding="utf-8")
    with pytest.raises(L.LaneConfigError, match="authorised"):
        L.load_lanes(p2)


def test_an_active_lane_with_a_blocker_is_refused(tmp_path):
    src = L.CONFIG_PATH.read_text(encoding="utf-8")
    hacked = src.replace(
        "  ACTIVIST_13D:\n    active: true",
        "  ACTIVIST_13D:\n    active: true\n    blocked_by: adapter missing")
    p = tmp_path / "hacked.yaml"
    p.write_text(hacked, encoding="utf-8")
    with pytest.raises(L.LaneConfigError, match="never ran"):
        L.load_lanes(p)


def test_the_config_hash_is_over_the_bytes(tmp_path):
    """A comment carries frozen policy here; a hash that ignored it would lie."""
    src = L.CONFIG_PATH.read_bytes()
    p = tmp_path / "commented.yaml"
    p.write_bytes(src + b"\n# one more comment\n")
    assert L.config_hash(p) != L.config_hash()


def test_a_full_run_leaves_the_research_books_config_byte_identical(lane):
    """The ten lanes accruing since 2026-06-08 must be untouchable from here.

    Checked as bytes rather than by grepping the source: what matters is that
    the file is unchanged, not that a string is absent from a docstring.
    """
    import hashlib
    from backend import config as _cfg
    book = _cfg.BACKEND_DIR / "data" / "paper_portfolios.yaml"
    before = hashlib.sha256(book.read_bytes()).hexdigest() if book.exists() else None

    spec, root = lane
    E.run_lane(spec, prices=FakePrices(), events=_cluster_events(),
               as_of=date(2026, 8, 20), root=root)

    after = hashlib.sha256(book.read_bytes()).hexdigest() if book.exists() else None
    assert before == after


# ── the execution policy ────────────────────────────────────────────────────
def test_a_filing_during_market_hours_fills_the_next_session():
    d = first_executable_session("2026-08-11T14:00:00+00:00", SESSIONS)
    assert d == date(2026, 8, 12)


def test_a_filing_after_the_close_fills_the_next_session():
    """21:55 UTC is 16:55 ET. Same rule, no special case, and it is correct."""
    assert to_ny_date("2026-08-11T21:55:49+00:00") == date(2026, 8, 11)
    assert first_executable_session("2026-08-11T21:55:49+00:00",
                                    SESSIONS) == date(2026, 8, 12)


def test_a_friday_evening_filing_fills_on_monday():
    assert first_executable_session("2026-08-14T22:30:00+00:00",
                                    SESSIONS) == date(2026, 8, 17)


def test_a_weekend_filing_fills_on_monday():
    assert first_executable_session("2026-08-15T12:00:00+00:00",
                                    SESSIONS) == date(2026, 8, 17)


def test_there_is_never_a_same_session_fill():
    for day in SESSIONS[:10]:
        got = first_executable_session(f"{day}T13:31:00+00:00", SESSIONS)
        assert got > day


def test_a_signal_with_no_session_yet_refuses_rather_than_inventing_one():
    with pytest.raises(NotExecutable):
        first_executable_session("2099-01-01T00:00:00+00:00", SESSIONS)


# ── seeding ─────────────────────────────────────────────────────────────────
def test_seeding_writes_the_inception_and_the_mandate(tmp_path):
    spec = L.load_lanes()["ACTIVIST_13D"]
    rec = S.seed_lane(spec, root=tmp_path)
    for key in ("lane_id", "seeded_at", "source", "actor_type", "entry_rule",
                "exit_rule", "holding_days", "benchmark", "sizing_rule",
                "transaction_cost_bps", "slippage_bps", "min_price",
                "min_dollar_volume_20d", "max_single_name", "config_hash",
                "label", "validation_status", "paper_only"):
        assert key in rec, key
    assert rec["paper_only"] is True and rec["real_capital"] is False


def test_seeding_twice_is_a_no_op(tmp_path):
    spec = L.load_lanes()["ACTIVIST_13D"]
    a = S.seed_lane(spec, root=tmp_path)
    b = S.seed_lane(spec, root=tmp_path)
    assert a["seeded_at"] == b["seeded_at"]


def test_a_changed_config_may_not_reuse_an_inception(tmp_path):
    spec = L.load_lanes()["ACTIVIST_13D"]
    S.seed_lane(spec, root=tmp_path)
    drifted = L.LaneSpec(**{**spec.as_dict(),
                            "action_types": tuple(spec.action_types),
                            "config_hash": "0" * 64})
    with pytest.raises(S.SeedRefused, match="NEW lane"):
        S.seed_lane(drifted, root=tmp_path)


def test_a_lane_refuses_to_run_under_a_config_it_was_not_seeded_with(tmp_path):
    spec = L.load_lanes()["ACTIVIST_13D"]
    S.seed_lane(spec, root=tmp_path)
    drifted = L.LaneSpec(**{**spec.as_dict(),
                            "action_types": tuple(spec.action_types),
                            "config_hash": "1" * 64})
    with pytest.raises(S.ConfigDrift, match="Segment identity"):
        E.run_lane(drifted, prices=FakePrices(), events=[], root=tmp_path)


# ── eligibility fails CLOSED ────────────────────────────────────────────────
def _eligible(spec, ev, prices, root, seeded="2026-08-10T00:00:00+00:00"):
    book = E.LaneBook(lane_id=spec.lane_id, cash=100000.0)
    return E.eligibility(ev, spec, seeded_at=seeded, prices=prices, book=book,
                         held_or_pending=set())


def test_an_event_public_before_the_inception_is_never_eligible(activist):
    spec, root = activist
    ok, why = _eligible(spec, _event(public_at="2026-08-05T14:00:00+00:00",
                                     actor_type="ACTIVIST_INVESTOR",
                                     action="ACTIVIST_STAKE"),
                        FakePrices(), root)
    assert not ok and "not after the lane's inception" in why


def test_a_missing_price_is_a_rejection_not_a_pass(activist):
    """The inverted guard once reported '182 eligible, 0 excluded'."""
    spec, root = activist
    ok, why = _eligible(spec, _event(ticker="GONE",
                                     actor_type="ACTIVIST_INVESTOR",
                                     action="ACTIVIST_STAKE"),
                        FakePrices(missing={"GONE"}), root)
    assert not ok and "price unavailable" in why


def test_a_penny_stock_is_rejected(activist):
    spec, root = activist
    ok, why = _eligible(spec, _event(actor_type="ACTIVIST_INVESTOR",
                                     action="ACTIVIST_STAKE"),
                        FakePrices(px=1.0), root)
    assert not ok and "min_price" in why


def test_an_illiquid_name_is_rejected(activist):
    spec, root = activist
    ok, why = _eligible(spec, _event(actor_type="ACTIVIST_INVESTOR",
                                     action="ACTIVIST_STAKE"),
                        FakePrices(adv=1000.0), root)
    assert not ok and "dollar volume" in why


def test_an_unusable_status_is_rejected(activist):
    spec, root = activist
    ok, why = _eligible(spec, _event(actor_type="ACTIVIST_INVESTOR",
                                     action="ACTIVIST_STAKE",
                                     status="UNAVAILABLE"),
                        FakePrices(), root)
    assert not ok and "not usable" in why


def test_an_ambiguous_security_mapping_is_rejected(activist):
    spec, root = activist
    ok, why = _eligible(spec, _event(actor_type="ACTIVIST_INVESTOR",
                                     action="ACTIVIST_STAKE",
                                     mapping_quality="AMBIGUOUS"),
                        FakePrices(), root)
    assert not ok and "ambiguous" in why


# ── the cluster rule ────────────────────────────────────────────────────────
def test_one_insider_is_not_a_cluster(lane):
    spec, _root = lane
    assert E.cluster_qualified([_event()], spec) == {}


def test_the_same_insider_buying_twice_is_not_a_cluster(lane):
    spec, _root = lane
    evs = [_event(public_at="2026-08-11T14:00:00+00:00"),
           _event(public_at="2026-08-12T14:00:00+00:00")]
    assert E.cluster_qualified(evs, spec) == {}


def test_two_distinct_insiders_qualify_at_the_completing_event(lane):
    spec, _root = lane
    a = _event(actor="INSIDER-1", public_at="2026-08-11T14:00:00+00:00")
    b = _event(actor="INSIDER-2", public_at="2026-08-12T14:00:00+00:00")
    got = E.cluster_qualified([a, b], spec)
    assert list(got) == ["AAPL"]
    # The SIGNAL is the event that completed the cluster, not the first buy.
    assert got["AAPL"][-1].actor_id == "INSIDER-2"


def test_buyers_outside_the_window_do_not_form_a_cluster(lane):
    spec, _root = lane
    a = _event(actor="INSIDER-1", public_at="2026-06-01T14:00:00+00:00")
    b = _event(actor="INSIDER-2", public_at="2026-08-12T14:00:00+00:00")
    assert E.cluster_qualified([a, b], spec) == {}


# ── the run ─────────────────────────────────────────────────────────────────
def _cluster_events(ticker="AAPL", d1="2026-08-11", d2="2026-08-12"):
    return [_event(ticker=ticker, actor="INSIDER-1",
                   public_at=f"{d1}T14:00:00+00:00"),
            _event(ticker=ticker, actor="INSIDER-2",
                   public_at=f"{d2}T14:00:00+00:00")]


def test_a_run_fills_at_the_next_session_open_and_writes_a_receipt(lane):
    spec, root = lane
    r = E.run_lane(spec, prices=FakePrices(), events=_cluster_events(),
                   as_of=date(2026, 8, 20), root=root)
    assert r["fills"] == 1
    assert r["open_positions"] == 1
    assert r["validation_status"] == "PRODUCT_EXPERIMENT"

    sig = [s for s in S.read_signals(spec.lane_id, root)
           if s.get("state") == "FILLED"][0]
    assert sig["fill_session"] == "2026-08-13"      # the day AFTER 08-12
    assert sig["fill_price_after_costs"] > sig["fill_price"]   # costs are real


def test_historical_events_produce_no_fills_at_all(lane):
    """The whole point. A new lane's NAV is boring, and that is honest."""
    spec, root = lane
    old = _cluster_events(d1="2026-01-05", d2="2026-01-06")
    r = E.run_lane(spec, prices=FakePrices(), events=old,
                   as_of=date(2026, 8, 20), root=root)
    assert r["fills"] == 0
    assert r["open_positions"] == 0
    assert any("not after the lane's inception" in k
               for k in r["ineligible_reasons"])


def test_sizing_never_reads_a_disclosed_amount_range(lane):
    """A reported interval is not a position size, however tempting."""
    spec, root = lane
    evs = _cluster_events()
    for e in evs:
        e.amount_low, e.amount_high = 1_000_000.0, 5_000_000.0
    E.run_lane(spec, prices=FakePrices(), events=evs,
               as_of=date(2026, 8, 20), root=root)
    sig = [s for s in S.read_signals(spec.lane_id, root)
           if s.get("state") == "FILLED"][0]
    assert sig["amount_range_used"] is False
    # 5% of a 100k book, not a fraction of the disclosed band.
    assert sig["notional"] == pytest.approx(5000.0, rel=0.02)


def test_a_thin_name_is_sized_down_by_its_own_volume(lane):
    spec, root = lane
    E.run_lane(spec, prices=FakePrices(adv=6_000_000.0), events=_cluster_events(),
               as_of=date(2026, 8, 20), root=root)
    sig = [s for s in S.read_signals(spec.lane_id, root)
           if s.get("state") == "FILLED"][0]
    assert sig["notional"] <= 6_000_000.0 * 0.01 + 1


def test_a_halted_open_waits_rather_than_filling_at_a_later_price(lane):
    spec, root = lane
    prices = FakePrices(no_open={("AAPL", date(2026, 8, 13))})
    E.run_lane(spec, prices=prices, events=_cluster_events(),
               as_of=date(2026, 8, 20), root=root)
    sig = [s for s in S.read_signals(spec.lane_id, root)
           if s.get("state") == "FILLED"][0]
    assert sig["fill_session"] == "2026-08-14"        # the next real open


def test_a_signal_that_cannot_fill_expires_loudly(lane):
    spec, root = lane
    prices = FakePrices(missing=set())
    prices.no_open = {("AAPL", d) for d in SESSIONS}
    E.run_lane(spec, prices=prices, events=_cluster_events(),
               as_of=date(2026, 8, 20), root=root)
    states = [s["state"] for s in S.read_signals(spec.lane_id, root)]
    assert "EXPIRED_UNFILLED" in states


def test_nav_is_written_for_every_session_and_carries_the_label(lane):
    spec, root = lane
    E.run_lane(spec, prices=FakePrices(), events=_cluster_events(),
               as_of=date(2026, 8, 20), root=root)
    nav = S.read_nav(spec.lane_id, root)
    assert nav and all(r["validation_status"] == "PRODUCT_EXPERIMENT"
                       for r in nav)
    assert [r["session"] for r in nav] == sorted(r["session"] for r in nav)


def test_nav_history_never_predates_the_inception(lane):
    """The first real run wrote 124 NAV rows dated from February for a lane
    seeded that afternoon — a six-month track record for a strategy that had
    not been declared. Flat and harmless-looking, and still a fabricated
    history. Caught by reading what the engine wrote, not by review.
    """
    spec, root = lane                       # inception 2026-08-10
    E.run_lane(spec, prices=FakePrices(), events=_cluster_events(),
               as_of=date(2026, 8, 20), root=root)
    nav = S.read_nav(spec.lane_id, root)
    assert nav
    assert min(r["session"] for r in nav) >= "2026-08-10"
    # ...even though the price panel reaches back much further.
    assert min(SESSIONS) < date(2026, 8, 10)


def test_a_second_run_does_not_double_fill(lane):
    spec, root = lane
    evs = _cluster_events()
    E.run_lane(spec, prices=FakePrices(), events=evs, as_of=date(2026, 8, 20),
               root=root)
    r2 = E.run_lane(spec, prices=FakePrices(), events=evs,
                    as_of=date(2026, 8, 20), root=root)
    assert r2["fills"] == 0
    assert r2["open_positions"] == 1


def test_a_position_that_goes_dark_is_liquidated_at_the_last_seen_price(lane):
    spec, root = lane
    prices = FakePrices()
    E.run_lane(spec, prices=prices, events=_cluster_events(),
               as_of=date(2026, 8, 14), root=root)
    dark = FakePrices(dark_from={"AAPL": date(2026, 8, 17)})
    E.run_lane(spec, prices=dark, events=[], as_of=date(2026, 9, 10), root=root)
    book = S.read_positions(spec.lane_id, root)
    closed = book.get("closed") or []
    assert closed and "delisted_or_dark" in closed[0]["close_reason"]
    assert closed[0]["exit_price"] == 50.0            # the last price we SAW


def test_everything_is_written_inside_the_copy_lab_namespace(lane, tmp_path):
    spec, root = lane
    E.run_lane(spec, prices=FakePrices(), events=_cluster_events(),
               as_of=date(2026, 8, 20), root=root)
    written = {p.relative_to(root).parts[0]
               for p in root.rglob("*") if p.is_file()}
    assert written == {spec.lane_id}


# --------------------------------------------------------------------------
# CONFIG HASH IDENTIFIES THE CONFIGURATION, NOT THE CHECKOUT
#
# Both lanes were seeded 2026-08-14 and every pass afterwards refused with
# ConfigDrift: seeded 697ddd4e0005, disk hashes to 727963034563. The file had
# not changed -- git log shows one commit. Git's autocrlf had rewritten 247
# line endings on checkout, and config_hash hashed raw bytes, so a strategy's
# IDENTITY changed because of a platform convention. Two paper books sat at
# last_nav=null for fourteen days and nothing reported it.
# --------------------------------------------------------------------------
def test_config_hash_is_insensitive_to_line_endings(tmp_path):
    from backend.services.copy_lab import lanes as L

    body = "defaults:\n  holding_days: 126\nlanes:\n  X:\n    active: false\n"
    lf = tmp_path / "lf.yaml"
    crlf = tmp_path / "crlf.yaml"
    lf.write_bytes(body.encode())
    crlf.write_bytes(body.replace("\n", "\r\n").encode())

    assert crlf.read_bytes() != lf.read_bytes(), "the fixture must differ on disk"
    assert L.config_hash(lf) == L.config_hash(crlf), (
        "a line ending is not a configuration -- no threshold, holding period, "
        "sizing rule or universe can differ between two files equal after "
        "normalisation"
    )


def test_config_hash_still_changes_on_a_real_edit(tmp_path):
    """Normalising must not weaken the guard it was protecting."""
    from backend.services.copy_lab import lanes as L

    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_bytes(b"defaults:\n  holding_days: 126\n")
    b.write_bytes(b"defaults:\n  holding_days: 252\n")
    assert L.config_hash(a) != L.config_hash(b), (
        "changing a holding period must still make this a NEW lane"
    )
