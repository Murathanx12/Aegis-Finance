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

MIRRORED_LANE = "mirror"
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


def _internal_positions(db_path=None) -> dict[str, float]:
    """Open positions of the internal mirror lane: {ticker: shares}."""
    from backend.db import get_connection
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT ticker, shares FROM paper_positions "
            "WHERE portfolio_id = ? AND closed_at IS NULL",
            (MIRRORED_LANE,),
        ).fetchall()
    finally:
        conn.close()
    return {r["ticker"]: float(r["shares"]) for r in rows if float(r["shares"]) > 0}


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


def _internal_nav(db_path=None) -> float | None:
    from backend.db import get_connection
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT nav FROM paper_nav WHERE portfolio_id = ? "
            "ORDER BY date DESC LIMIT 1", (MIRRORED_LANE,),
        ).fetchone()
    finally:
        conn.close()
    return float(row["nav"]) if row else None


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


def _record_equity(divergence_pct: float | None, db_path=None) -> None:
    from backend.db import get_connection, snapshot
    acct = _request("GET", "/v2/account")
    conn = get_connection(db_path)
    try:
        snapshot(conn, EQUITY_KEY, date.today().isoformat(),
                 float(acct["equity"]),
                 source="alpaca_paper",
                 observed_at=datetime.now(timezone.utc).isoformat(),
                 payload={"cash": float(acct["cash"]),
                          "divergence_vs_internal_pct": divergence_pct})
    finally:
        conn.close()


def seed_alpaca_mirror(db_path=None) -> dict:
    """Attended, env-gated first replication. Idempotent: an account that
    already holds positions is treated as seeded and never re-seeded."""
    if os.getenv("AEGIS_SEED_ALPACA_MIRROR") != "1":
        return {"status": "not_enabled"}
    if not alpaca_available():
        return {"status": "no_keys"}

    existing = _request("GET", "/v2/positions") or []
    # Positions alone are NOT enough: while the market is closed, seed orders
    # sit accepted-but-unfilled and positions stay empty — a second deploy
    # with the flag still set would double-order (happened live 2026-07-18,
    # duplicate DKNG canceled by hand). Open orders count as seeded.
    open_orders = _request("GET", "/v2/orders?status=open") or []
    if existing or open_orders:
        return {"status": "already_seeded", "n_positions": len(existing),
                "n_open_orders": len(open_orders)}

    internal = _internal_positions(db_path)
    nav = _internal_nav(db_path)
    if not internal or not nav:
        return {"status": "no_internal_positions",
                "detail": f"lane={MIRRORED_LANE} has no open positions/nav here"}

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
    ensure_trial_registered(TRIAL_PARAM, ANNOTATION, db_path=db_path)
    _record_equity(divergence_pct=None, db_path=db_path)
    logger.info("Alpaca mirror SEEDED: %d orders placed (queue at next open "
                "if market closed)", len(placed))
    return {"status": "seeded", "orders": placed}


def sync_alpaca_mirror(db_path=None) -> dict:
    """Daily: record third-party equity + divergence; trade ONLY when the
    internal lane's position set changed. No-op until keys + seed exist."""
    if not alpaca_available():
        return {"status": "not_configured"}
    positions = _request("GET", "/v2/positions") or []
    if not positions:
        # not seeded yet (or fully cash) — still record equity for the ledger
        _record_equity(divergence_pct=None, db_path=db_path)
        return {"status": "not_seeded"}

    internal = _internal_positions(db_path)
    nav = _internal_nav(db_path)
    acct = _request("GET", "/v2/account")
    equity = float(acct["equity"])

    divergence = None
    if nav and nav > 0:
        # Both started life at 100k-scale; compare cumulative growth.
        divergence = round((equity / 100_000 - nav / 100_000) * 100, 3)

    held = {p["symbol"]: int(float(p["qty"])) for p in positions}
    prices = {p["symbol"]: float(p["current_price"]) for p in positions
              if p.get("current_price")}
    prices.update(_latest_prices([t for t in internal if t not in prices]))
    targets = _target_share_counts(internal, equity, nav or equity, prices)

    trades = []
    if set(targets) != set(held):  # the internal lane rebalanced — follow it
        for sym in sorted(set(held) - set(targets)):
            _request("DELETE", f"/v2/positions/{sym}")
            trades.append({"symbol": sym, "action": "close"})
        for sym in sorted(set(targets) - set(held)):
            _request("POST", "/v2/orders", {
                "symbol": sym, "qty": str(targets[sym]), "side": "buy",
                "type": "market", "time_in_force": "day",
            })
            trades.append({"symbol": sym, "action": "open", "qty": targets[sym]})

    _record_equity(divergence, db_path=db_path)
    return {"status": "synced", "equity": equity, "divergence_pct": divergence,
            "trades": trades, "n_positions": len(held)}


def alpaca_mirror_status(db_path=None) -> dict:
    """For /dev + health surfaces: last recorded third-party equity."""
    import json
    from backend.db import get_connection
    if not alpaca_available():
        return {"configured": False}
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT as_of, value, payload FROM pit_observations "
            "WHERE key = ? ORDER BY as_of DESC LIMIT 1", (EQUITY_KEY,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {"configured": True, "recorded": False}
    payload = json.loads(row["payload"]) if row["payload"] else {}
    return {"configured": True, "recorded": True, "as_of": row["as_of"],
            "equity": row["value"],
            "divergence_vs_internal_pct": payload.get("divergence_vs_internal_pct")}
