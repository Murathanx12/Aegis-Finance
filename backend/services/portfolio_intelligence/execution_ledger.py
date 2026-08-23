"""What the fill actually cost, per order, against what we assumed it would.

WHY EQUITY CURVES CANNOT ANSWER THIS
====================================
The external paper account gives us an independently computed equity curve, and
that is worth having. It cannot answer the question the account exists to ask:

    signal return - assumed cost - REAL execution cost = captured edge

Two NAV series diverging tells you the strategies differ. It does not tell you
whether the difference is slippage, a partial fill, an order that never filled
at all, or the strategy itself. Only per-order records separate those, and they
have to be written WHEN THE ORDER RESOLVES -- a fill nobody recorded cannot be
reconstructed a month later from an equity curve.

THE ASSUMPTION BEING TESTED
===========================
Every arena book prices its own fills at the next session's OPEN plus a declared
`cost_bps + slippage_bps`. That is an assumption with a number attached, and it
has never been checked against a broker. This ledger checks it: the internal
synthetic fill and the broker's real fill are the same intended trade at the
same intended open, so their difference is execution and nothing else.

WHAT IS DELIBERATELY RECORDED RATHER THAN DROPPED
=================================================
* an order that was submitted and **never filled**. A ledger of successes makes
  captured edge look better than it was, and "we never got the trade" is the
  most expensive execution outcome there is;
* a **partial** fill, with the fraction, because a half-filled position is not
  the position the book thinks it holds;
* an order the broker cannot account for at all -- as `UNKNOWN`, with the
  reason. A missing row and a bad fill must never look identical.

SIGN CONVENTION
===============
`slippage_bps` is always a COST when positive, for both sides: a buy that filled
above the internal price and a sell that filled below it both read positive.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend import config as _config

logger = logging.getLogger(__name__)

ROOT = _config.OPTIMUS_LEDGER_DIR / "execution"
SCHEMA_VERSION = "execution-ledger-1.0.0"

_LOCK = threading.Lock()

#: Beyond this, a submitted order that still has no broker resolution is
#: recorded as EXPIRED_UNRESOLVED rather than waited on forever. A day order
#: that did not fill at the open is not going to.
UNRESOLVED_AFTER_DAYS = 5


class ExecutionLedgerRefused(RuntimeError):
    """Captured edge asked for over a ledger that cannot support it."""


def _slug(target_id: str) -> str:
    return target_id.replace(":", "_")


def _path(target_id: str, root: Path | None = None) -> Path:
    return (root or ROOT) / f"{_slug(target_id)}.jsonl"


def _read(target_id: str, root: Path | None = None) -> list[dict]:
    p = _path(target_id, root)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            logger.error("execution_ledger: unparseable line in %s — skipped", p)
    return out


def _append(target_id: str, rows: list[dict], root: Path | None = None) -> int:
    if not rows:
        return 0
    p = _path(target_id, root)
    with _LOCK:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, default=str) + "\n")
    return len(rows)


def _order_key(row: dict) -> tuple:
    """What makes two rows the SAME order.

    The ledger is append-only, so a resolved order leaves a PENDING row AND a
    FILLED one. Counting rows whose state is PENDING therefore counts every
    resolved order forever -- which made `health` go DEGRADED five days after
    the first successful reconciliation and stay there, reporting a stuck
    pipeline that was working perfectly.
    """
    return (row.get("ticker"), row.get("submitted_at"), row.get("decided_for"))


def open_orders(rows: list[dict]) -> list[dict]:
    """PENDING rows that have no resolution row of their own."""
    resolved = {_order_key(r) for r in rows
                if r.get("state") not in (None, "PENDING")}
    return [r for r in rows
            if r.get("state") == "PENDING" and _order_key(r) not in resolved]


def record_submission(target, trades: list[dict], *, decided_for: str | None,
                      basis: str, submitted_at: datetime | None = None,
                      root: Path | None = None) -> dict:
    """One PENDING row per submitted order, written at submission time.

    Written BEFORE the outcome is known, on purpose. A row created only once an
    order filled would make the ledger a record of fills rather than of
    intentions, and the gap between those two is exactly what this measures.
    """
    ts = (submitted_at or datetime.now(timezone.utc)).isoformat(
        timespec="seconds")
    rows = []
    for t in trades:
        rows.append({
            "schema_version": SCHEMA_VERSION,
            "state": "PENDING",
            "target_id": target.target_id,
            "book_id": target.source_id,
            "decided_for": decided_for,
            "basis": basis,
            "ticker": t.get("symbol"),
            "action": t.get("action"),
            "intended_qty": t.get("qty"),
            "submitted_at": ts,
            "reconciled_at": None,
        })
    n = _append(target.target_id, rows, root)
    logger.info("execution ledger: %d submission(s) recorded for %s (%s)",
                n, target.target_id, decided_for)
    return {"written": n, "decided_for": decided_for}


def _internal_fills(book_id: str, decision_date: str | None,
                    arena_root: Path | None = None) -> dict[str, dict]:
    """The book's OWN synthetic fills for one decision, keyed by ticker."""
    from backend.services.arena import store

    out: dict[str, dict] = {}
    for row in store.read_orders(book_id, arena_root):
        if decision_date and row.get("decision_date") != decision_date:
            continue
        if row.get("status") != "filled":
            continue
        t = row.get("ticker")
        if t:
            out[t] = row
    return out


def _broker_orders(target, *, since: datetime) -> dict[str, list[dict]]:
    """Closed broker orders since `since`, grouped by symbol."""
    from backend.services.portfolio_intelligence import alpaca_mirror as AM

    after = since.astimezone(timezone.utc).isoformat(timespec="seconds")
    path = (f"/v2/orders?status=closed&limit=500&direction=asc"
            f"&after={after}")
    rows = AM._request("GET", path, target=target) or []
    out: dict[str, list[dict]] = {}
    for o in rows:
        out.setdefault(o.get("symbol"), []).append(o)
    return out


def _slippage_bps(action: str, internal_px: float, broker_px: float
                  ) -> float | None:
    """Positive is always a COST, for buys and sells alike."""
    if not internal_px or internal_px <= 0 or not broker_px or broker_px <= 0:
        return None
    raw = (broker_px - internal_px) / internal_px * 10_000.0
    return round(raw if str(action).lower() in ("open", "buy") else -raw, 2)


def reconcile(target, *, arena_root: Path | None = None,
              root: Path | None = None, now: datetime | None = None) -> dict:
    """Resolve every PENDING row whose two sides now both exist.

    Runs after the arena pass, which is the first moment BOTH exist: the pass
    has just recorded the book's synthetic fill at today's open, and the broker
    filled the same intended order at the same open this morning.
    """
    now = now or datetime.now(timezone.utc)
    rows = _read(target.target_id, root)
    pending = open_orders(rows)
    if not pending:
        return {"status": "nothing_pending", "target_id": target.target_id}

    # An unconfigured account is not an unreadable broker. Without this the
    # nightly job would log an ERROR every pass while the account is simply
    # not seeded yet, and a real outage would be one line among many identical
    # ones. `paper_broker.health` already reports the missing credentials.
    from backend.services.portfolio_intelligence import alpaca_mirror as _AM

    if not _AM.alpaca_available(target):
        return {"status": "not_configured", "target_id": target.target_id,
                "n_pending": len(pending)}

    oldest = min(datetime.fromisoformat(r["submitted_at"]) for r in pending)
    try:
        broker = _broker_orders(target, since=oldest - timedelta(days=1))
    except Exception as e:                                      # noqa: BLE001
        # A broker we cannot read is NOT an execution finding. Leave the rows
        # PENDING and say so, rather than writing a ledger full of UNKNOWNs
        # that would later read as "the fills went missing".
        logger.error("execution ledger: broker unreadable for %s: %s",
                     target.target_id, e)
        return {"status": "broker_unreadable", "target_id": target.target_id,
                "error": str(e), "n_pending": len(pending)}

    by_decision: dict[str | None, dict[str, dict]] = {}
    resolved: list[dict] = []

    for r in pending:
        dd = r.get("decided_for")
        if dd not in by_decision:
            by_decision[dd] = _internal_fills(r["book_id"], dd, arena_root)
        internal = by_decision[dd].get(r["ticker"])
        cand = broker.get(r["ticker"]) or []
        filled = [o for o in cand
                  if float(o.get("filled_qty") or 0) > 0
                  and o.get("filled_at")]

        out = dict(r)
        out["reconciled_at"] = now.isoformat(timespec="seconds")

        if not filled:
            age = (now - datetime.fromisoformat(r["submitted_at"])).days
            if age < UNRESOLVED_AFTER_DAYS:
                continue                      # still legitimately in flight
            # THE MOST EXPENSIVE OUTCOME, AND THE EASIEST TO LOSE. An order
            # that never filled leaves no fill to record, so a ledger built
            # from fills would simply not contain it -- and captured edge
            # would be computed as though we always got the trade.
            out.update(state="NEVER_FILLED", broker_status="unfilled",
                       note=("submitted and never filled — the book acted on a "
                             "position the account never held"))
            resolved.append(out)
            continue

        o = filled[-1]
        bpx = float(o.get("filled_avg_price") or 0) or None
        bqty = float(o.get("filled_qty") or 0)
        want = float(r.get("intended_qty") or 0)
        out.update(
            state="FILLED",
            broker_order_id=o.get("id"),
            broker_status=o.get("status"),
            broker_filled_qty=bqty,
            broker_fill_price=bpx,
            broker_filled_at=o.get("filled_at"),
            partial=bool(want and bqty < want - 1e-9),
            fill_fraction=round(bqty / want, 4) if want else None,
        )
        if internal:
            ipx = float(internal.get("fill_price") or 0) or None
            out.update(
                internal_fill_price=ipx,
                internal_fill_date=internal.get("fill_date"),
                internal_cost_usd=internal.get("cost_usd"),
                assumed_cost_bps=(float(internal.get("cost_bps") or 0)
                                  + float(internal.get("slippage_bps") or 0)),
                slippage_bps=_slippage_bps(r.get("action"), ipx, bpx),
            )
            if out.get("slippage_bps") is not None:
                out["realized_vs_assumed_bps"] = round(
                    out["slippage_bps"] - out["assumed_cost_bps"], 2)
        else:
            # Filled at the broker with no matching internal fill: the two
            # sides disagree about what was traded, which is a finding in its
            # own right and must not be silently averaged away.
            out.update(internal_fill_price=None,
                       note=("broker filled an order the book has no synthetic "
                             "fill for — the two sides disagree about what was "
                             "traded"))
        resolved.append(out)

    if not resolved:
        return {"status": "in_flight", "target_id": target.target_id,
                "n_pending": len(pending)}

    # Append-only: resolutions are NEW rows carrying the same submitted_at, so
    # the PENDING row stays on disk as the record of what was intended.
    _append(target.target_id, resolved, root)
    filled_rows = [r for r in resolved if r["state"] == "FILLED"]
    slips = [r["slippage_bps"] for r in filled_rows
             if r.get("slippage_bps") is not None]
    return {
        "status": "reconciled",
        "target_id": target.target_id,
        "n_resolved": len(resolved),
        "n_filled": len(filled_rows),
        "n_never_filled": sum(1 for r in resolved
                              if r["state"] == "NEVER_FILLED"),
        "n_partial": sum(1 for r in filled_rows if r.get("partial")),
        "mean_slippage_bps": (round(sum(slips) / len(slips), 2)
                              if slips else None),
    }


def summary(target_id: str, *, root: Path | None = None) -> dict:
    """Captured-edge inputs, over everything resolved so far."""
    rows = [r for r in _read(target_id, root) if r.get("state") != "PENDING"]
    filled = [r for r in rows if r.get("state") == "FILLED"]
    slips = [r["slippage_bps"] for r in filled
             if r.get("slippage_bps") is not None]
    excess = [r["realized_vs_assumed_bps"] for r in filled
              if r.get("realized_vs_assumed_bps") is not None]
    never = sum(1 for r in rows if r.get("state") == "NEVER_FILLED")
    return {
        "target_id": target_id,
        "n_resolved": len(rows),
        "n_filled": len(filled),
        "n_never_filled": never,
        "n_partial": sum(1 for r in filled if r.get("partial")),
        "fill_rate": (round(len(filled) / len(rows), 4) if rows else None),
        "mean_slippage_bps": (round(sum(slips) / len(slips), 2)
                              if slips else None),
        "mean_realized_minus_assumed_bps": (round(sum(excess) / len(excess), 2)
                                            if excess else None),
        "note": ("positive slippage is a COST on both sides. "
                 "`realized_minus_assumed` above zero means the book's declared "
                 "cost model is OPTIMISTIC — the number every backtest in this "
                 "repository silently assumes."),
    }


def health(*, root: Path | None = None) -> dict:
    """Is the ledger accruing, and is anything stuck?"""
    r = root or ROOT
    if not r.exists():
        return {"status": "ABSENT", "n_targets": 0,
                "reason": ("no execution ledger on disk — no external order "
                           "has been submitted yet")}
    out, status = {}, "ok"
    for p in sorted(r.glob("*.jsonl")):
        tid = p.stem.replace("_", ":", 1)
        rows = _read(tid, root)
        pending = open_orders(rows)
        stuck = [x for x in pending
                 if (datetime.now(timezone.utc)
                     - datetime.fromisoformat(x["submitted_at"])).days
                 >= UNRESOLVED_AFTER_DAYS]
        out[tid] = {"n_rows": len(rows), "n_pending": len(pending),
                    "n_stuck": len(stuck), **summary(tid, root=root)}
        if stuck:
            status = "DEGRADED"
            out[tid]["reason"] = (
                f"{len(stuck)} order(s) submitted more than "
                f"{UNRESOLVED_AFTER_DAYS} days ago and still unresolved — "
                f"reconciliation is not running")
    return {"status": status, "n_targets": len(out), "targets": out}


def assert_captured_edge_reportable(target_id: str, *,
                                    root: Path | None = None,
                                    max_unresolved_fraction: float = 0.2
                                    ) -> dict:
    """Refuse to report captured edge over a ledger that cannot support it.

    THE BIAS THIS REFUSES. Orders do not resolve at random. A marketable order
    in a liquid name fills at the open and lands in the ledger immediately; the
    ones that hang are the illiquid, the wide-spread and the never-filled --
    exactly the expensive ones. So a summary computed while a large fraction is
    still unresolved is a summary over the EASY subset, and it reads as good
    execution precisely when execution was worst.

    An empty ledger is refused for the same reason one level up: a mean over
    zero fills is not a small number, it is the absence of one.
    """
    rows = _read(target_id, root)
    if not rows:
        raise ExecutionLedgerRefused(
            f"no execution rows for {target_id} — captured edge over an empty "
            f"ledger is the absence of a measurement, not a measurement of "
            f"zero cost")
    pending = open_orders(rows)
    resolved = [r for r in rows if r.get("state") not in (None, "PENDING")]
    if not resolved:
        raise ExecutionLedgerRefused(
            f"{target_id} has {len(pending)} submitted order(s) and NONE "
            f"resolved — nothing here has an outcome yet")
    frac = len(pending) / max(len(pending) + len(resolved), 1)
    if frac > max_unresolved_fraction:
        raise ExecutionLedgerRefused(
            f"{frac:.0%} of {target_id}'s orders are still unresolved (bar "
            f"{max_unresolved_fraction:.0%}). Orders do not resolve at random "
            f"— the ones that hang are the illiquid and the never-filled, so "
            f"this summary would describe the easy subset and read as good "
            f"execution precisely when execution was worst.")
    return summary(target_id, root=root)
