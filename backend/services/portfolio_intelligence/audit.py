"""
Aegis Finance — Audit & Explanation Generator
================================================

Creates human-readable rebalance events and audit log entries.
Pure functions for event creation; DB writes are separate.

Usage:
    from backend.services.portfolio_intelligence.audit import (
        create_rebalance_explanation, format_trade_summary,
    )
"""

import logging

logger = logging.getLogger(__name__)


def format_trade_summary(trades: list[dict], max_trades: int = 5) -> str:
    """Format top trades into a human-readable string."""
    if not trades:
        return "No trades executed."

    sorted_trades = sorted(trades, key=lambda t: abs(t.get("dollar_amount", 0)), reverse=True)
    top = sorted_trades[:max_trades]

    parts = []
    for t in top:
        direction = "bought" if t["side"] == "buy" else "sold"
        pct = abs(t["weight_change"]) * 100
        parts.append(f"{direction} {pct:.1f}% {t['ticker']}")

    summary = "Top trades: " + ", ".join(parts)
    if len(sorted_trades) > max_trades:
        summary += f" (+{len(sorted_trades) - max_trades} more)"
    return summary


def _compute_sleeve_pcts(weights: dict[str, float]) -> dict[str, float]:
    """Compute equity/bond/alt percentages from weights."""
    from backend.services.portfolio_intelligence.rules import classify_asset

    sleeves = {"equity": 0.0, "bond": 0.0, "alternative": 0.0}
    for t, w in weights.items():
        ac = classify_asset(t)
        sleeves[ac] = sleeves.get(ac, 0.0) + w
    return sleeves


def create_rebalance_explanation(
    portfolio_id: str,
    trigger_reason: str,
    pre_weights: dict[str, float],
    post_weights: dict[str, float],
    trades: list[dict],
    crash_prob_3m: float | None = None,
    regime: str | None = None,
    lane_config: dict | None = None,
    total_cost: float = 0.0,
) -> str:
    """Generate a human-readable explanation for a rebalance event.

    Examples:
        "Monthly rebalance. Crash overlay armed (3m prob = 32%, threshold = 30%).
         Cut equity from 72% to 61%. Top trades: sold 4% XLK, bought 5% TLT."

        "Drift rebalance. Max drift: NVDA at 8.2% (threshold: 5%).
         No crash overlay. Top trades: sold 3% NVDA, bought 2% AGG."

        "Checked balanced at 2026-04-26. Drift 2.3% < threshold 5%. No rebalance."
    """
    parts = []

    # Trigger
    reason_labels = {
        "monthly": "Monthly scheduled rebalance.",
        "weekly_aggressive": "Weekly aggressive-lane rebalance.",
        "drift": "Drift-triggered rebalance.",
        "crash_overlay": "Crash overlay triggered rebalance.",
        "initialization": "Initial portfolio construction.",
        "manual": "Manual trigger.",
    }
    parts.append(reason_labels.get(trigger_reason, f"Rebalance ({trigger_reason})."))

    # Crash overlay status
    if crash_prob_3m is not None:
        threshold = None
        if lane_config:
            threshold = lane_config.get("crash_overlay", {}).get("crash_prob_threshold")

        if threshold and crash_prob_3m > threshold:
            pre_sleeves = _compute_sleeve_pcts(pre_weights)
            post_sleeves = _compute_sleeve_pcts(post_weights)
            parts.append(
                f"Crash overlay armed (3m prob = {crash_prob_3m:.0%}, "
                f"threshold = {threshold:.0%}). "
                f"Cut equity from {pre_sleeves['equity']:.0%} to {post_sleeves['equity']:.0%}."
            )
        else:
            parts.append(f"Crash probability {crash_prob_3m:.0%} — overlay not triggered.")

    # Regime
    if regime:
        parts.append(f"Regime: {regime}.")

    # Trade summary
    parts.append(format_trade_summary(trades))

    # Cost
    if total_cost > 0:
        parts.append(f"Estimated cost: ${total_cost:.2f}.")

    return " ".join(parts)


def create_no_rebalance_explanation(
    portfolio_id: str,
    max_drift: float,
    drift_threshold: float,
    days_since_last: int | None = None,
    frequency: str = "monthly",
) -> str:
    """Explain why no rebalance was triggered."""
    parts = [f"Checked {portfolio_id}."]
    parts.append(f"Max drift {max_drift:.1%} < threshold {drift_threshold:.0%}.")

    if days_since_last is not None:
        if frequency == "weekly":
            parts.append(f"{days_since_last}d since last check (weekly schedule).")
        else:
            parts.append(f"{days_since_last}d since last rebalance (monthly schedule).")

    parts.append("No rebalance needed.")
    return " ".join(parts)
