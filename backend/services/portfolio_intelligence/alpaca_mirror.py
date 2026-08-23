"""
Alpaca paper mirror — third-party-verified NAV for the `mirror` lane.

WHY: the forward track record's NAV is computed by our own code — honest but
self-reported. Replicating the mirror lane's positions in an Alpaca PAPER
account makes a third party's servers compute the equity curve: anyone can
audit it against our numbers. Verification infrastructure, NOT a new
strategy — the decision rules stay 100% internal; Alpaca only ever receives
copies of positions the internal lane already holds.

Discipline:
- No real money can exist here (paper API base is hardcoded-default and the
  key type is paper-only).
- Seeding is env-gated + attended: set ALPACA_API_KEY_ID /
  ALPACA_API_SECRET_KEY and AEGIS_SEED_ALPACA_MIRROR=1, deploy, then UNSET
  the seed flag (idempotent regardless — a seeded account never re-seeds).
- Daily sync only TRADES when the internal lane's open positions changed
  (mirror-the-mirror); every sync records Alpaca's own equity into the PIT
  store (`alpaca:equity`) with the divergence vs the internal lane NAV.
- The registry gets an infrastructure annotation row at seed time so the
  ledger of everything lane-adjacent stays complete.

MVP scope: whole-share replication of the `mirror` lane (fractional not
assumed on the account). With ~$100k across large caps the rounding
residual stays in cash and is measured by the divergence metric, not hidden.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)

from backend.services.portfolio_intelligence import (
    paper_broker_targets as _targets,
)

#: Legacy name. The mirrored source is now DECLARED via
#: `AEGIS_PAPER_BROKER_TARGET` and defaults to exactly this lane, so nothing
#: about the existing third-party-verified history changes.
MIRRORED_LANE = "mirror"

#: A sync that closes more than this fraction of the account in one pass is
#: treated as a liquidation signal and refused. Rebalances are incremental;
#: "close almost everything" is what a broken source looks like.
MAX_CLOSE_FRACTION = 0.5


def _resolve(target=None):
    """The declared mirror target, or the legacy lane when none is set."""
    return target if target is not None else _targets.parse_target()
TRIAL_PARAM = "alpaca-mirror-verification"
EQUITY_KEY = "alpaca:equity"
_STATE_KEY = "alpaca:mirror_state"  # PIT payload holds last synced position set

ANNOTATION = {
    "kind": "infrastructure",
    "purpose": (
        "Third-party NAV verification: Alpaca PAPER account replicates the "
        "mirror lane's open positions; Alpaca computes equity independently. "
        "No decision rule lives here; never a strategy; no buy/sell advice."
    ),
    "lane": MIRRORED_LANE,
    "doc": "backend/services/portfolio_intelligence/alpaca_mirror.py docstring",
}


def _keys() -> tuple[str, str] | None:
    k = os.getenv("ALPACA_API_KEY_ID", "").strip()
    s = os.getenv("ALPACA_API_SECRET_KEY", "").strip()
    return (k, s) if k and s else None


def _base() -> str:
    return os.getenv("ALPACA_PAPER_BASE", "https://paper-api.alpaca.markets").rstrip("/")


def alpaca_available() -> bool:
    return _keys() is not None


def _request(method: str, path: str, payload: dict | None = None):
    """Single choke point for ALL Alpaca calls (same doctrine as _sec_get)."""
    import requests
    keys = _keys()
    if keys is None:
        raise RuntimeError("Alpaca keys not configured")
    if "paper" not in _base():
        # Belt-and-braces: this module must never talk to a live-trading host.
        raise RuntimeError(f"Refusing non-paper Alpaca base: {_base()}")
    headers = {"APCA-API-KEY-ID": keys[0], "APCA-API-SECRET-KEY": keys[1]}
    resp = requests.request(method, f"{_base()}{path}", headers=headers,
                            json=payload, timeout=20)
    resp.raise_for_status()
    return resp.json() if resp.text else None


def _internal_positions(db_path=None, target=None) -> dict[str, float]:
    """Open positions of the mirrored source: {ticker: shares}.

    Delegated to `paper_broker_targets` so an arena book is as mirrorable as a
    lane. With no target declared this is byte-identical to the old lane read.
    """
    return _targets.positions(_resolve(target), db_path=db_path)


def _target_share_counts(internal: dict[str, float], equity: float,
                         internal_nav: float, prices: dict[str, float]) -> dict[str, int]:
    """Scale internal share counts to the Alpaca account's equity and round
    to whole shares. Scaling by NAV ratio (not re-deriving weights) keeps the
    replication mechanical."""
    if internal_nav <= 0:
        return {}
    scale = equity / internal_nav
    out = {}
    for t, sh in internal.items():
        if prices.get(t, 0) <= 0:
            continue
        qty = int(sh * scale)  # floor — residual stays in cash, measured not hidden
        if qty > 0:
            out[t] = qty
    return out


def _internal_nav(db_path=None, target=None) -> float | None:
    return _targets.nav(_resolve(target), db_path=db_path)


def _latest_prices(tickers: list[str]) -> dict[str, float]:
    """Last trade prices from Alpaca itself (keeps the mirror self-contained)."""
    if not tickers:
        return {}
    data = _request("GET", "/v2/positions") or []
    known = {p["symbol"]: float(p["current_price"]) for p in data
             if p.get("current_price")}
    missing = [t for t in tickers if t not in known]
    prices = dict(known)
    for t in missing:
        try:
            q = _request("GET", f"/v2/stocks/{t}/trades/latest")
            # data API lives on another host for some plans; fall back to yf
            prices[t] = float(q["trade"]["p"])
        except Exception:
            try:
                from backend.services.data_fetcher import fetch_ticker_history
                hist = fetch_ticker_history(t, period="5d")
                if hist is not None and not hist.empty:
                    prices[t] = float(hist["Close"].iloc[-1])
            except Exception as e:
                logger.warning("Alpaca mirror: no price for %s: %s", t, e)
    return prices


def _record_equity(divergence_pct: float | None, db_path=None,
                   target=None) -> None:
    from backend.db import get_connection, snapshot
    t = _resolve(target)
    acct = _request("GET", "/v2/account")
    conn = get_connection(db_path)
    try:
        snapshot(conn, t.equity_key, date.today().isoformat(),
                 float(acct["equity"]),
                 source="alpaca_paper",
                 observed_at=datetime.now(timezone.utc).isoformat(),
                 payload={"cash": float(acct["cash"]),
                          "divergence_vs_internal_pct": divergence_pct,
                          "target_id": t.target_id})
    finally:
        conn.close()


def seed_alpaca_mirror(db_path=None, target=None) -> dict:
    """Attended, env-gated first replication. Idempotent: an account that
    already holds positions is treated as seeded and never re-seeded."""
    if os.getenv("AEGIS_SEED_ALPACA_MIRROR") != "1":
        return {"status": "not_enabled"}
    if not alpaca_available():
        return {"status": "no_keys"}
    t = _resolve(target)

    existing = _request("GET", "/v2/positions") or []
    # Positions alone are NOT enough: while the market is closed, seed orders
    # sit accepted-but-unfilled and positions stay empty — a second deploy
    # with the flag still set would double-order (happened live 2026-07-18,
    # duplicate DKNG canceled by hand). Open orders count as seeded.
    open_orders = _request("GET", "/v2/orders?status=open") or []
    if existing or open_orders:
        return {"status": "already_seeded", "n_positions": len(existing),
                "n_open_orders": len(open_orders)}

    internal = _internal_positions(db_path, target=t)
    nav = _internal_nav(db_path, target=t)
    if not internal or not nav:
        return {"status": "no_internal_positions",
                "target_id": t.target_id,
                "detail": f"{t.target_id} has no open positions/nav here"}

    acct = _request("GET", "/v2/account")
    equity = float(acct["equity"])
    prices = _latest_prices(sorted(internal))
    targets = _target_share_counts(internal, equity, nav, prices)
    placed = []
    for t, qty in sorted(targets.items()):
        _request("POST", "/v2/orders", {
            "symbol": t, "qty": str(qty), "side": "buy",
            "type": "market", "time_in_force": "day",
        })
        placed.append({"symbol": t, "qty": qty})
    # Registry annotation — the lane-adjacent ledger stays complete.
    from backend.services.portfolio_intelligence.trial_registry import (
        ensure_trial_registered,
    )
    ensure_trial_registered(t.trial_param, _targets.annotation(t),
                            db_path=db_path)
    _record_equity(divergence_pct=None, db_path=db_path, target=t)
    logger.info("Alpaca paper SEEDED for %s: %d orders placed (queue at next "
                "open if market closed)", t.target_id, len(placed))
    return {"status": "seeded", "target_id": t.target_id, "orders": placed}


def sync_alpaca_mirror(db_path=None, target=None) -> dict:
    """Daily: record third-party equity + divergence; trade ONLY when the
    mirrored source's position set changed. No-op until keys + seed exist."""
    if not alpaca_available():
        return {"status": "not_configured"}
    tgt = _resolve(target)
    positions = _request("GET", "/v2/positions") or []
    if not positions:
        # not seeded yet (or fully cash) — still record equity for the ledger
        _record_equity(divergence_pct=None, db_path=db_path, target=tgt)
        return {"status": "not_seeded", "target_id": tgt.target_id}

    internal = _internal_positions(db_path, target=tgt)
    nav = _internal_nav(db_path, target=tgt)

    # REFUSE THE DESTRUCTIVE READING. An empty internal book and an UNREADABLE
    # internal book look identical here, and one of those two meanings is
    # "liquidate everything the paper account holds". The position source is
    # LOCAL (SQLite / the arena store) while the execution target is a SHARED
    # remote account, so any environment that cannot see the source — a dev
    # machine, a fresh container, a wiped volume — would otherwise close the
    # whole book on contact.
    #
    # Paid for on 2026-08-23: a smoke-test call to sync() from the dev machine
    # placed 12 real sell orders against the live paper account, because the
    # local DB has no `mirror` lane rows. They were accepted-not-filled (the
    # market was closed) and were cancelled before the open, so nothing was
    # lost — by luck of the clock, not by any check.
    #
    # A book that has genuinely gone to cash still has to be able to say so, so
    # this is a refusal to ACT on silence, not a refusal to ever go flat: an
    # explicit flag re-permits it once someone has confirmed the source is
    # really empty rather than really absent.
    if not internal and positions:
        if os.getenv("AEGIS_ALPACA_ALLOW_FULL_LIQUIDATION") != "1":
            _record_equity(divergence_pct=None, db_path=db_path, target=tgt)
            logger.error(
                "Alpaca sync REFUSED for %s: the paper account holds %d "
                "position(s) but the internal source reports NONE. That is "
                "either a real liquidation or an unreadable source, and this "
                "adapter will not guess. Set "
                "AEGIS_ALPACA_ALLOW_FULL_LIQUIDATION=1 to confirm the source "
                "is genuinely flat.",
                tgt.target_id, len(positions))
            return {"status": "refused_source_empty",
                    "target_id": tgt.target_id,
                    "n_held": len(positions),
                    "detail": ("internal source reports no positions while the "
                               "paper account holds some; refusing to "
                               "liquidate on an ambiguous signal")}

    acct = _request("GET", "/v2/account")
    equity = float(acct["equity"])

    divergence = None
    if nav and nav > 0:
        # Both sides start at the same 100k notional (lane seed and arena
        # `notional_usd` alike), so cumulative growth is directly comparable.
        # Asserted rather than assumed: a source seeded at another notional
        # would make this number silently meaningless.
        divergence = round((equity / 100_000 - nav / 100_000) * 100, 3)

    held = {p["symbol"]: int(float(p["qty"])) for p in positions}
    prices = {p["symbol"]: float(p["current_price"]) for p in positions
              if p.get("current_price")}
    prices.update(_latest_prices([k for k in internal if k not in prices]))
    want = _target_share_counts(internal, equity, nav or equity, prices)

    trades = []
    if set(want) != set(held):  # the mirrored source rebalanced — follow it
        # A rebalance that closes most of the book is the same ambiguous
        # signal in weaker form. Bound it rather than trusting it blind.
        closing = set(held) - set(want)
        if held and len(closing) / len(held) > MAX_CLOSE_FRACTION and                 os.getenv("AEGIS_ALPACA_ALLOW_FULL_LIQUIDATION") != "1":
            _record_equity(divergence, db_path=db_path, target=tgt)
            logger.error("Alpaca sync REFUSED for %s: would close %d of %d "
                         "positions (>%.0f%%), which is a liquidation, not a "
                         "rebalance.", tgt.target_id, len(closing), len(held),
                         MAX_CLOSE_FRACTION * 100)
            return {"status": "refused_mass_close", "target_id": tgt.target_id,
                    "n_would_close": len(closing), "n_held": len(held)}
        for sym in sorted(set(held) - set(want)):
            _request("DELETE", f"/v2/positions/{sym}")
            trades.append({"symbol": sym, "action": "close"})
        for sym in sorted(set(want) - set(held)):
            _request("POST", "/v2/orders", {
                "symbol": sym, "qty": str(want[sym]), "side": "buy",
                "type": "market", "time_in_force": "day",
            })
            trades.append({"symbol": sym, "action": "open", "qty": want[sym]})

    _record_equity(divergence, db_path=db_path, target=tgt)
    return {"status": "synced", "target_id": tgt.target_id, "equity": equity,
            "divergence_pct": divergence, "trades": trades,
            "n_positions": len(held)}


def alpaca_mirror_status(db_path=None, target=None) -> dict:
    """For /dev + health surfaces: last recorded third-party equity."""
    import json
    from backend.db import get_connection
    tgt = _resolve(target)
    if not alpaca_available():
        return {"configured": False, "target": _targets.describe(tgt)}
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT as_of, value, payload FROM pit_observations "
            "WHERE key = ? ORDER BY as_of DESC LIMIT 1", (tgt.equity_key,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {"configured": True, "recorded": False,
                "target": _targets.describe(tgt)}
    payload = json.loads(row["payload"]) if row["payload"] else {}
    return {"configured": True, "recorded": True, "as_of": row["as_of"],
            "equity": row["value"],
            "target": _targets.describe(tgt),
            "divergence_vs_internal_pct": payload.get("divergence_vs_internal_pct")}
