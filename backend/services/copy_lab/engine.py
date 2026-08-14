"""TeacherEvent → eligibility → signal → fill → position → NAV → receipt.

WHAT THIS IS AND IS NOT
=======================
It is the shadow-account machinery for COPY-LAB's forward paper lanes. It is
NOT a research harness: no hypothesis is tested here, no control is matched, and
nothing it writes may be cited as evidence. A profitable paper lane does not
make a mechanism true.

THE FOUR RULES THAT DO THE WORK
===============================
1. **`public_at` only.** `transaction_at` is never read for timing. Entry is one
   frozen policy — see `execution.py` — and the engine has no branch that could
   produce a same-session fill.
2. **No retroactive fills.** An event public before the lane's `seeded_at` is
   ineligible forever. There is no backfill path in this file, deliberately: the
   temptation is to make a new lane's NAV look interesting, and a fabricated
   history is worse than an empty one.
3. **Missing data fails CLOSED.** The liquidity floor was once written
   `if price is not None and price < MIN_PRICE`, so a name with NO price sailed
   through a check that reported "0 excluded". Here, an unmeasurable name is
   ineligible and says which measurement was missing.
4. **A range is never a midpoint.** Congressional disclosures give amount
   BANDS. Sizing is the lane's fixed target weight and never reads `amount_low`
   or `amount_high` — turning an interval into a precise number and calling it a
   position size is inventing data that was never disclosed.

SIZING
======
`target_weight × current NAV`, capped by `max_single_name` and by
`max_pct_of_adv_20d × ADV` so a paper fill stays plausible. Costs are
`transaction_cost_bps + slippage_bps` applied to the fill price. Equal-weight by
design: these lanes exist to measure whether the SIGNAL contains information,
and a conviction-weighted book confounds that with a sizing rule nobody
registered.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

from . import store
from .execution import (NotExecutable, ExecutionPolicy, first_executable_session,
                        to_ny_date)
from .lanes import LaneSpec

logger = logging.getLogger(__name__)

ENGINE_VERSION = "copy_lab_engine@v1"

# ── signal states ───────────────────────────────────────────────────────────
INELIGIBLE = "INELIGIBLE"
PENDING_FILL = "PENDING_FILL"
FILLED = "FILLED"
EXPIRED_UNFILLED = "EXPIRED_UNFILLED"
CLOSED = "CLOSED"


class PriceProvider(Protocol):
    """The only way this engine learns a price. Injected so it is testable."""

    def sessions(self) -> list[date]: ...
    def open_price(self, ticker: str, day: date) -> float | None: ...
    def close_price(self, ticker: str, day: date) -> float | None: ...
    def adv20(self, ticker: str, day: date) -> float | None: ...


@dataclass
class Position:
    ticker: str
    shares: float
    cost_basis: float
    opened_on: str
    opened_by_event: str
    holding_days: int
    last_price: float | None = None
    last_marked: str | None = None
    closed_on: str | None = None
    close_reason: str = ""
    stale_sessions: int = 0

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class LaneBook:
    lane_id: str
    cash: float
    positions: dict[str, dict] = field(default_factory=dict)
    closed: list[dict] = field(default_factory=list)
    last_nav: float | None = None
    last_marked: str | None = None

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def _iso_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    try:
        return to_ny_date(v)
    except Exception:                                          # noqa: BLE001
        return None


# ── eligibility ─────────────────────────────────────────────────────────────
def eligibility(event, spec: LaneSpec, *, seeded_at: str,
                prices: PriceProvider, book: LaneBook,
                held_or_pending: set[str]) -> tuple[bool, str]:
    """Can this event open a position? Returns (ok, reason).

    Every rejection carries a reason, and every reason names the specific thing
    that failed. "Not eligible" tells the next reader nothing.
    """
    tkr = (event.ticker_at_event or "").upper()
    if not tkr:
        return False, "no ticker on the event"
    if not event.public_at:
        return False, "no public_at — an event with no public timestamp cannot be traded"

    pub = _iso_date(event.public_at)
    seed_d = _iso_date(seeded_at)
    if pub is None or seed_d is None:
        return False, "unparseable public_at or seeded_at"
    # NO RETROACTIVE FILLS. Strictly after: an event public on the seeding day,
    # possibly hours before the flag was flipped, is not a forward observation.
    if pub <= seed_d:
        return False, (f"public_at {pub} is not after the lane's inception "
                       f"{seed_d} — historical events are research material, "
                       f"never forward paper performance")

    if spec.actor_type and event.actor_type != spec.actor_type:
        return False, f"actor_type {event.actor_type} is not this lane's"
    if spec.action_types and event.action_type not in spec.action_types:
        return False, f"action_type {event.action_type} is not this lane's"
    if event.status not in ("OK_DATA", "LATE_FILING"):
        return False, f"event status {event.status} is not usable"
    if event.mapping_quality == "AMBIGUOUS":
        return False, "security mapping ambiguous — refusing to guess the issuer"

    if tkr in held_or_pending:
        return False, "already held or pending in this lane"
    if len(book.positions) >= int(spec.params.get("max_positions", 20)):
        return False, "lane is at max_positions"

    # Liquidity floor, FAILING CLOSED. A name we cannot measure is not a name
    # that passed — that inverted test once reported "182 eligible, 0 excluded"
    # from a guard that had never fired.
    day = pub
    px = prices.close_price(tkr, day)
    if px is None:
        return False, "price unavailable at public_at — cannot verify the liquidity floor"
    if px < float(spec.params.get("min_price", 0)):
        return False, f"price {px:.2f} below min_price"
    adv = prices.adv20(tkr, day)
    if adv is None:
        return False, "20d dollar volume unavailable — cannot verify the liquidity floor"
    if adv < float(spec.params.get("min_dollar_volume_20d", 0)):
        return False, f"20d dollar volume {adv:,.0f} below the floor"
    return True, "eligible"


def cluster_qualified(events: list, spec: LaneSpec) -> dict[str, list]:
    """Group events into per-ticker clusters that satisfy the entry rule.

    For a cluster lane the SIGNAL is the moment the rule becomes true — the
    public_at of the event that completes the cluster — not the first buy. A
    cluster dated at its first member would enter on information that did not
    yet imply a cluster.
    """
    need = int(spec.min_distinct_actors or 1)
    window = int(spec.cluster_window_days or 0)
    by_ticker: dict[str, list] = {}
    for e in events:
        by_ticker.setdefault((e.ticker_at_event or "").upper(), []).append(e)

    out: dict[str, list] = {}
    for tkr, evs in by_ticker.items():
        if not tkr:
            continue
        evs = sorted(evs, key=lambda e: str(e.public_at))
        if need <= 1:
            out[tkr] = [evs[0]]
            continue
        for i, e in enumerate(evs):
            end = _iso_date(e.public_at)
            if end is None:
                continue
            start = end - timedelta(days=window)
            members = [x for x in evs[:i + 1]
                       if (_iso_date(x.public_at) or end) >= start]
            actors = {x.actor_id for x in members}
            if len(actors) >= need:
                # `e` completes the cluster: this is the signal event.
                out[tkr] = members
                break
    return out


# ── the run ─────────────────────────────────────────────────────────────────
def _cost_multiplier(spec: LaneSpec) -> float:
    bps = (float(spec.params.get("transaction_cost_bps", 0))
           + float(spec.params.get("slippage_bps", 0)))
    return 1.0 + bps / 10_000.0


def run_lane(spec: LaneSpec, *, prices: PriceProvider,
             events: Iterable, as_of: "str | date | None" = None,
             root: Path | None = None) -> dict:
    """One engine pass for one lane. Idempotent on already-processed events."""
    seed = store.assert_config_current(spec, root=root)
    seeded_at = seed["seeded_at"]
    as_of_d = _iso_date(as_of) or date.today()
    sessions = [s for s in prices.sessions() if s <= as_of_d]
    if not sessions:
        raise NotExecutable("the price panel has no sessions at or before "
                            f"{as_of_d} — nothing can be marked or filled")

    raw = store.read_positions(spec.lane_id, root)
    book = LaneBook(
        lane_id=spec.lane_id,
        cash=float(raw.get("cash", spec.params.get("notional_usd", 100000.0))),
        positions=dict(raw.get("positions") or {}),
        closed=list(raw.get("closed") or []),
        last_nav=raw.get("last_nav"),
        last_marked=raw.get("last_marked"),
    )

    prior = store.read_signals(spec.lane_id, root)
    seen_events = {r.get("event_id") for r in prior}
    held_or_pending = set(book.positions) | {
        r.get("ticker") for r in prior if r.get("state") == PENDING_FILL}

    evs = [e for e in events]
    if spec.min_distinct_actors and spec.min_distinct_actors > 1:
        clusters = cluster_qualified(evs, spec)
        candidates = [(t, m[-1], m) for t, m in clusters.items()]
    else:
        candidates = [((e.ticker_at_event or "").upper(), e, [e]) for e in evs]

    new_signals: list[dict] = []
    for tkr, sig_event, members in candidates:
        eid = sig_event.event_id()
        if eid in seen_events:
            continue
        ok, reason = eligibility(sig_event, spec, seeded_at=seeded_at,
                                 prices=prices, book=book,
                                 held_or_pending=held_or_pending)
        row = {
            "engine_version": ENGINE_VERSION,
            "execution_policy": ExecutionPolicy().policy_id,
            "lane_id": spec.lane_id,
            "event_id": eid,
            "cluster_event_ids": [m.event_id() for m in members],
            "ticker": tkr,
            "actor_id": sig_event.actor_id,
            "actor_type": sig_event.actor_type,
            "action_type": sig_event.action_type,
            "public_at": sig_event.public_at,
            "transaction_at": sig_event.transaction_at,
            "disclosure_lag_days": sig_event.disclosure_lag_days(),
            "signalled_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
            "state": PENDING_FILL if ok else INELIGIBLE,
            "reason": reason,
        }
        if ok:
            try:
                row["first_executable_session"] = str(
                    first_executable_session(sig_event.public_at, sessions))
            except NotExecutable as exc:
                # Not a rejection — the session simply has not happened yet.
                row["first_executable_session"] = None
                row["reason"] = f"awaiting a session: {exc}"
            held_or_pending.add(tkr)
        new_signals.append(row)

    if new_signals:
        store.append_signals(spec.lane_id, new_signals, root)

    # ── fills ───────────────────────────────────────────────────────────────
    all_signals = store.read_signals(spec.lane_id, root)
    pending = [r for r in all_signals if r.get("state") == PENDING_FILL]
    fills, expiries = [], []
    cost_mult = _cost_multiplier(spec)
    expiry_n = int(spec.params.get("unfilled_expiry_sessions", 3))

    for row in pending:
        tkr = row["ticker"]
        if tkr in book.positions:
            continue
        try:
            first = (date.fromisoformat(row["first_executable_session"])
                     if row.get("first_executable_session")
                     else first_executable_session(row["public_at"], sessions))
        except (NotExecutable, TypeError, ValueError):
            continue
        window = [s for s in sessions if s >= first][:expiry_n]
        if not window:
            continue                       # the session has not arrived yet

        filled = False
        for s in window:
            px = prices.open_price(tkr, s)
            if px is None or px <= 0:
                continue                   # halted, or no print: try the next
            nav = _mark_to_market(book, prices, s)
            target = float(spec.params.get("target_weight", 0.05)) * nav
            cap = float(spec.params.get("max_single_name", 0.05)) * nav
            adv = prices.adv20(tkr, s)
            if adv is not None:
                target = min(target, adv * float(
                    spec.params.get("max_pct_of_adv_20d", 1.0)))
            target = min(target, cap, book.cash)
            if target <= 0:
                continue
            fill_px = px * cost_mult
            shares = target / fill_px
            book.positions[tkr] = Position(
                ticker=tkr, shares=shares, cost_basis=fill_px,
                opened_on=str(s), opened_by_event=row["event_id"],
                holding_days=spec.holding_days, last_price=px,
                last_marked=str(s)).as_dict()
            book.cash -= shares * fill_px
            row.update({"state": FILLED, "fill_session": str(s),
                        "fill_price": px, "fill_price_after_costs": fill_px,
                        "shares": shares, "notional": shares * fill_px,
                        "sizing_rule": "target_weight x NAV, capped by "
                                       "max_single_name and max_pct_of_adv_20d",
                        "amount_range_used": False})
            fills.append(row)
            filled = True
            break
        if not filled and len(window) >= expiry_n:
            row.update({"state": EXPIRED_UNFILLED,
                        "reason": (f"no tradable open in {expiry_n} sessions "
                                   f"from {first} — halted, delisted or no "
                                   f"print; NOT filled at a later price")})
            expiries.append(row)

    if fills or expiries:
        # Append-only: the amended row is written as a new line and the reader
        # takes the newest state per event_id. Rewriting the original would
        # delete the evidence of what was believed at signal time.
        store.append_signals(spec.lane_id, fills + expiries, root)

    # ── exits and marks ─────────────────────────────────────────────────────
    inception = _iso_date(seeded_at) or as_of_d
    nav_rows = _mark_and_exit(book, spec, prices, sessions, root, inception)
    store.write_positions(spec.lane_id, book.as_dict(), root)

    receipt = {
        "receipt": "COPY-LAB engine run",
        "engine_version": ENGINE_VERSION,
        "execution_policy": ExecutionPolicy().__dict__,
        "lane_id": spec.lane_id,
        "config_hash": spec.config_hash,
        "seeded_at": seeded_at,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": str(as_of_d),
        "label": spec.label,
        "validation_status": spec.validation_status,
        "paper_only": True,
        "events_considered": len(evs),
        "signals_new": len(new_signals),
        "signals_ineligible": sum(1 for r in new_signals
                                  if r["state"] == INELIGIBLE),
        "ineligible_reasons": _tally(r["reason"] for r in new_signals
                                     if r["state"] == INELIGIBLE),
        "fills": len(fills),
        "expired_unfilled": len(expiries),
        "open_positions": len(book.positions),
        "closed_positions": len(book.closed),
        "cash": round(book.cash, 2),
        "nav": book.last_nav,
        "nav_rows_written": len(nav_rows),
        "note": ("PRODUCT_EXPERIMENT / NOT VALIDATED ALPHA. No hypothesis was "
                 "evaluated and no historical fill was written."),
    }
    store.write_receipt(spec.lane_id, receipt, root)
    return receipt


def _tally(items) -> dict:
    out: dict[str, int] = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _mark_to_market(book: LaneBook, prices: PriceProvider, day: date) -> float:
    """Cash plus the last usable price of every open position.

    A position whose price is missing is held at its LAST KNOWN price and its
    staleness counted, rather than dropped from the NAV — dropping it would make
    a data outage look like a position that went to zero, and carrying it
    silently would make a delisting look like a flat holding forever.
    """
    total = book.cash
    for tkr, p in book.positions.items():
        px = prices.close_price(tkr, day)
        if px is None:
            p["stale_sessions"] = int(p.get("stale_sessions", 0)) + 1
            px = p.get("last_price")
        else:
            p["stale_sessions"] = 0
            p["last_price"], p["last_marked"] = px, str(day)
        if px is not None:
            total += float(p["shares"]) * float(px)
    return total


def _mark_and_exit(book: LaneBook, spec: LaneSpec, prices: PriceProvider,
                   sessions: list[date], root: Path | None,
                   inception: date) -> list[dict]:
    """Mark every unmarked session forward and apply the time stop.

    MARKING STARTS AT THE INCEPTION, and that is not a detail. The first version
    marked every session in the price panel — which reaches back before the lane
    existed to price the events — and wrote 124 NAV rows dated from February for
    a lane seeded that afternoon. Flat, harmless-looking, and a six-month track
    record for a strategy that had not been declared. Caught on the first real
    run, by reading what it wrote.
    """
    start = None
    if book.last_marked:
        start = date.fromisoformat(str(book.last_marked))
    todo = [s for s in sessions
            if s >= inception and (start is None or s > start)]
    rows: list[dict] = []
    stale_limit = int(spec.params.get("unfilled_expiry_sessions", 3)) * 5

    for s in todo:
        # Time stop first, so a position that matured today is not also marked
        # as if it were still open at the close.
        for tkr in list(book.positions):
            p = book.positions[tkr]
            opened = date.fromisoformat(str(p["opened_on"]))
            held = len([d for d in sessions if opened < d <= s])
            reason = ""
            if held >= int(p["holding_days"]):
                reason = "time_stop"
            elif int(p.get("stale_sessions", 0)) >= stale_limit:
                # Delisted, renamed or permanently dark. Liquidate at the last
                # price we actually saw and SAY SO — never at a price we made up.
                reason = "delisted_or_dark: liquidated at last known price"
            if not reason:
                continue
            px = prices.close_price(tkr, s) or p.get("last_price")
            if px is None:
                continue
            proceeds = float(p["shares"]) * float(px) / _cost_multiplier(spec)
            book.cash += proceeds
            p.update({"closed_on": str(s), "close_reason": reason,
                      "exit_price": px, "proceeds": proceeds})
            book.closed.append(p)
            del book.positions[tkr]

        nav = _mark_to_market(book, prices, s)
        book.last_nav, book.last_marked = nav, str(s)
        rows.append({"lane_id": spec.lane_id, "session": str(s),
                     "nav": round(nav, 4), "cash": round(book.cash, 4),
                     "n_positions": len(book.positions),
                     "label": spec.label,
                     "validation_status": spec.validation_status})
    if rows:
        store.append_nav(spec.lane_id, rows, root)
    return rows
