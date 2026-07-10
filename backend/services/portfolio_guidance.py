"""
Per-position portfolio guidance — the "manage my account" surface (Branch 4)
============================================================================

For each holding: where the position stands (P&L vs cost basis, how unusual
the recent move is), where the exit discipline sits (Chandelier trailing-stop
level and the distance to it), what the forward-collected signals currently
read (PEAD / quality / revisions / insider PIT snapshots — free reads), and
the behavioral nudges the research says retail needs most (Odean, canon
2026-06-15): the disposition effect — riding losers past their stop and
cutting winners that are still trending.

Everything here is DESCRIPTIVE guidance with named levels — never an order.
The stop level is "the discipline you pre-committed to", not a sell signal;
the nudges name the behavioral pattern, the user decides. No signal shown
here has passed a skill gate, and the labels say so.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

import pandas as pd

from backend.config import config

logger = logging.getLogger(__name__)

GUIDANCE_LABEL = ("descriptive per-position guidance — pre-committed levels and "
                  "context, not advice; no signal here has a proven forward edge")

_PIT_SIGNALS = ("pead_score", "quality_score", "revisions_score", "insider_opp",
                "multifactor_score")


# ── Pure per-position logic ───────────────────────────────────────────────────


def chandelier_stop_level(close: pd.Series, high: Optional[pd.Series] = None,
                          low: Optional[pd.Series] = None) -> Optional[dict]:
    """Current Chandelier trailing-stop level: rolling peak − mult × ATR.
    Uses the frozen exit_engine config (no per-user tuning)."""
    from backend.services.exit_engine import compute_atr
    cfg = config.get("exit_engine", {})
    period = int(cfg.get("atr_period", 14))
    mult = float(cfg.get("atr_stop_multiple", 3.0))
    s = close.dropna()
    if len(s) < period + 5:
        return None
    atr = compute_atr(s, high=high, low=low, period=period)
    lookback = min(len(s), 22)
    peak = float(s.iloc[-lookback:].max())
    stop = peak - mult * float(atr.iloc[-1])
    price = float(s.iloc[-1])
    return {
        "stop_level": round(stop, 4),
        "peak_22d": round(peak, 4),
        "atr": round(float(atr.iloc[-1]), 4),
        "atr_multiple": mult,
        "distance_pct": round(price / stop - 1.0, 4) if stop > 0 else None,
        "breached": bool(price < stop),
    }


def position_guidance(ticker: str, shares: float,
                      cost_basis: Optional[float],
                      close: pd.Series,
                      pit_signals: Optional[dict] = None) -> dict:
    """Assemble one holding's guidance. Pure given the inputs."""
    from backend.services.explain_move import compute_move_profile

    move = compute_move_profile(close)
    stop = chandelier_stop_level(close)
    price = move.get("last_price")

    pnl = None
    if cost_basis and price and cost_basis > 0:
        pnl = round(price / cost_basis - 1.0, 4)

    # Behavioral nudges — name the pattern, the user decides.
    nudges: list[dict] = []
    if stop and stop["breached"]:
        if pnl is not None and pnl > 0:
            nudges.append({
                "type": "winner_rolling_over",
                "message": (f"{ticker} is in gain ({pnl:+.0%}) but has fallen "
                            f"below its pre-committed trailing-stop level "
                            f"(${stop['stop_level']:.2f}). This is the pattern "
                            f"where winners give back their gains — review "
                            f"against your exit plan."),
            })
        elif pnl is not None and pnl < 0:
            nudges.append({
                "type": "loser_past_stop",
                "message": (f"{ticker} is at a loss ({pnl:+.0%}) and below its "
                            f"trailing-stop level (${stop['stop_level']:.2f}). "
                            f"Holding losers past the pre-committed stop is the "
                            f"disposition effect — the most measured retail "
                            f"error (~3.4pp/yr, Odean). Review deliberately."),
            })
        else:
            nudges.append({
                "type": "below_stop",
                "message": f"{ticker} is below its trailing-stop level "
                           f"(${stop['stop_level']:.2f}). Review your exit plan.",
            })
    if move.get("move_unusualness") in ("unusual", "extreme"):
        z = move.get("move_zscore_21d")
        nudges.append({
            "type": "unusual_move",
            "message": (f"{ticker}'s 21-day move is {move['move_unusualness']} "
                        f"({z}σ vs its own history) — check /explain-move for "
                        f"the evidence around it before acting on emotion."),
        })

    return {
        "ticker": ticker,
        "shares": shares,
        "price": price,
        "cost_basis": cost_basis,
        "unrealized_pnl_pct": pnl,
        "move": move,
        "trailing_stop": stop,
        "signals": pit_signals or {},
        "nudges": nudges,
        "label": GUIDANCE_LABEL,
    }


# ── Live assembly ─────────────────────────────────────────────────────────────


def _latest_pit_signals(ticker: str, db_path=None) -> dict:
    """Free PIT reads of the forward-collected signal snapshots (leak-free)."""
    from backend.db import get_connection, get_latest_observable
    out: dict = {}
    conn = get_connection(db_path)
    try:
        for name in _PIT_SIGNALS:
            row = get_latest_observable(conn, f"{name}:{ticker}")
            if row is not None and not (row.get("payload") or {}).get("error"):
                out[name] = {"value": row["value"], "as_of": row["as_of"],
                             "status": "collected"}
    except Exception as e:
        logger.warning("PIT signal read failed for %s: %s", ticker, e)
    finally:
        conn.close()
    return out


def portfolio_guidance(holdings: list[dict], db_path=None,
                       price_fetch: Optional[Callable] = None) -> dict:
    """Guidance for a whole book. ``holdings``: [{ticker, shares, cost_basis?}].
    Per-holding failures degrade that holding only."""
    def _default_fetch(ticker: str) -> pd.Series:
        import yfinance as yf
        return yf.Ticker(ticker).history(period="1y")["Close"]

    fetch = price_fetch or _default_fetch

    positions = []
    for h in holdings:
        ticker = str(h.get("ticker", "")).upper().strip()
        if not ticker:
            continue
        try:
            close = fetch(ticker)
            sig = _latest_pit_signals(ticker, db_path=db_path)
            positions.append(position_guidance(
                ticker, float(h.get("shares", 0) or 0),
                (float(h["cost_basis"]) if h.get("cost_basis") else None),
                close, pit_signals=sig))
        except Exception as e:
            logger.warning("guidance failed for %s: %s", ticker, e)
            positions.append({"ticker": ticker, "status": "unavailable",
                              "error": str(e), "label": GUIDANCE_LABEL})

    # Shared market context — fast persisted reads only.
    context: dict = {}
    try:
        from backend.services.portfolio_intelligence.fragility import (
            latest_persisted_composite,
        )
        fragility = latest_persisted_composite()
        context["fragility"] = {k: fragility.get(k) for k in
                                ("composite", "level", "evaluated_at", "status")}
    except Exception as e:
        context["fragility"] = {"status": "unavailable", "error": str(e)}

    n_nudges = sum(len(p.get("nudges", [])) for p in positions)
    return {"positions": positions, "context": context,
            "n_positions": len(positions), "n_nudges": n_nudges,
            "label": GUIDANCE_LABEL,
            "disclaimer": ("Educational guidance around YOUR pre-committed "
                           "levels — not financial advice, not orders. No "
                           "signal shown has passed a forward skill gate.")}
