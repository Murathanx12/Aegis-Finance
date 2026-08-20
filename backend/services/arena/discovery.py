"""DISCOVERY_UNIVERSE + the frozen daily information state.

This module is the caller the 16 descriptive collectors never had: it reads
their PIT scores (leak-free, `observed_at <= decision_ts`) and joins them with
price-derived state into one snapshot per session, frozen write-once before
any decision is made. The snapshot hash is the `information_state_hash` every
decision and experience record carries.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Protocol

from backend import config as _config
from backend.db import get_connection, get_series_observable
from backend.services.arena import store

logger = logging.getLogger(__name__)

#: PIT key prefixes joined into the snapshot. Every one of these accrues daily
#: from `_daily_check` and previously had no consumer.
SCORE_PREFIXES: dict[str, str] = {
    "multifactor": "multifactor_score:",
    "insider_opp": "insider_opp:",
    "insider_cmp": "insider_cmp:",
    "revisions": "revisions_score:",
    "pead": "pead_score:",
    "quality": "quality_score:",
}


class PricePanel(Protocol):
    """What the engine needs from prices. Injected, so tests stay offline."""

    def sessions(self) -> list[date]: ...
    def open_price(self, ticker: str, day: date) -> float | None: ...
    def close_price(self, ticker: str, day: date) -> float | None: ...
    def close_history(self, ticker: str, day: date,
                      n: int) -> list[float]: ...


class ArenaPanel:
    """Adjusted daily bars via yfinance, with trailing-history access.

    Same conventions as copy_lab's panel: holes are holes, sessions come from
    the benchmark's own index, NaN is unavailable rather than a value.
    """

    def __init__(self, tickers: list[str], start: str,
                 end: str | None = None, benchmark: str = "SPY"):
        import pandas as pd
        import yfinance as yf
        self.benchmark = benchmark
        names = sorted(set(t.upper() for t in tickers) | {benchmark})
        end = end or str(date.today() + timedelta(days=1))
        self._open: dict = {}
        self._close: dict = {}
        try:
            df = yf.download(names, start=start, end=end, auto_adjust=True,
                             progress=False, group_by="ticker", timeout=30)
        except Exception as exc:  # noqa: BLE001
            logger.error("ARENA price panel fetch failed (%s) — every name "
                         "reads UNAVAILABLE (ineligible, never a pass)", exc)
            df = pd.DataFrame()
        for t in names:
            try:
                sub = df[t] if isinstance(df.columns, pd.MultiIndex) else df
                o = pd.to_numeric(sub["Open"], errors="coerce").dropna()
                c = pd.to_numeric(sub["Close"], errors="coerce").dropna()
            except Exception:  # noqa: BLE001
                continue
            if c.empty:
                continue
            self._open[t] = o
            self._close[t] = c

    def sessions(self) -> list[date]:
        import pandas as pd
        s = self._close.get(self.benchmark)
        if s is None or s.empty:
            logger.error("ARENA: no %s history — no sessions to mark against",
                         self.benchmark)
            return []
        return [d.date() for d in pd.to_datetime(s.index)]

    def _at(self, store_: dict, ticker: str, day: date):
        import pandas as pd
        s = store_.get(ticker.upper())
        if s is None or s.empty:
            return None
        idx = pd.to_datetime(s.index)
        hit = s[idx.date == day]
        if len(hit) == 0:
            return None
        v = float(hit.iloc[0])
        return v if v == v else None

    def open_price(self, ticker: str, day: date):
        return self._at(self._open, ticker, day)

    def close_price(self, ticker: str, day: date):
        return self._at(self._close, ticker, day)

    def close_history(self, ticker: str, day: date, n: int) -> list[float]:
        import pandas as pd
        s = self._close.get(ticker.upper())
        if s is None or s.empty:
            return []
        idx = pd.to_datetime(s.index)
        upto = s[idx.date <= day]
        return [float(v) for v in upto.tail(n).tolist() if v == v]


# ── universe ────────────────────────────────────────────────────────────────
def candidate_universe(extra: list[str] | None = None) -> list[str]:
    """Watchlist + sector names + whatever the books currently hold."""
    su = _config.config.get("stock_universe", {})
    names: set[str] = {t.upper() for t in su.get("default_watchlist", [])}
    for sect in (su.get("sector_stocks") or {}).values():
        names.update(t.upper() for t in sect)
    names.update(t.upper() for t in (extra or []))
    return sorted(names)


# ── feature computation (pure given inputs) ─────────────────────────────────
MOM_LOOKBACK = 252   # sessions in the 12-1 momentum window
MOM_SKIP = 21        # most recent sessions EXCLUDED — the anti-chase month


def _mom_12_1(closes: list[float]) -> float | None:
    """Classic 12-1 momentum: return from t-252 to t-21. The last month is
    excluded by construction, which is exactly what the streak/factor-chase
    anti-signal results demand of any momentum the arena uses."""
    if len(closes) < MOM_LOOKBACK:
        return None
    a, b = closes[-(MOM_SKIP + 1)], closes[-MOM_LOOKBACK]
    return (a / b - 1.0) if b else None


def _trailing_features(closes: list[float]) -> dict:
    out: dict = {"vol63": None, "ret21": None, "streak_up": 0}
    if len(closes) >= 2:
        rets = [closes[i] / closes[i - 1] - 1.0
                for i in range(1, len(closes)) if closes[i - 1]]
        if len(rets) >= 21:
            out["ret21"] = closes[-1] / closes[-22] - 1.0
        if len(rets) >= 40:  # enough for a usable vol estimate
            window = rets[-63:]
            m = sum(window) / len(window)
            var = sum((r - m) ** 2 for r in window) / max(len(window) - 1, 1)
            out["vol63"] = var ** 0.5
        streak = 0
        for r in reversed(rets):
            if r > 0:
                streak += 1
            else:
                break
        out["streak_up"] = streak
    return out


def build_day_state(day: date, panel: PricePanel,
                    universe: list[str], *, db_path=None) -> dict:
    """One frozen information state: per-name prices, trailing state, and the
    latest PIT score of every family, read leak-free as of end of ``day``."""
    as_of_ts = f"{day}T23:59:59+00:00"
    conn = get_connection(db_path) if db_path is not None else get_connection()
    try:
        return _build_day_state_with_conn(day, panel, universe, conn, as_of_ts)
    finally:
        conn.close()


def _build_day_state_with_conn(day, panel, universe, conn,
                               as_of_ts: str) -> dict:
    names: dict[str, dict] = {}
    for t in universe:
        close = panel.close_price(t, day)
        if close is None:
            names[t] = {"status": "no_price"}
            continue
        closes = panel.close_history(t, day, MOM_LOOKBACK + 10)
        feats = _trailing_features(closes)
        scores: dict[str, float | None] = {"mom_12_1": _mom_12_1(closes)}
        for label, prefix in SCORE_PREFIXES.items():
            try:
                series = get_series_observable(conn, prefix + t, as_of_ts)
            except Exception as exc:  # noqa: BLE001
                logger.warning("ARENA: PIT read failed for %s%s: %s",
                               prefix, t, exc)
                series = []
            scores[label] = (float(series[-1]["value"])
                             if series and series[-1].get("value") is not None
                             else None)
        names[t] = {"status": "ok", "close": close, **feats,
                    "scores": scores}
    _add_arena_composite(names)
    n_scored = sum(1 for v in names.values()
                   if v.get("scores", {}).get("arena_composite") is not None)
    return {"date": str(day), "as_of_ts": as_of_ts, "universe_n": len(universe),
            "scored_n": n_scored, "names": names}


#: The arena's OWN composite over the arena's OWN universe. The registered
#: collectors (multifactor etc.) score only the ~12-name book cross-section,
#: and widening THEM would change their z-scores mid-trial — so the arena
#: blends its own price-derived 12-1 momentum with whatever PIT families a
#: name has, using the same frozen pure estimator (z-score each factor
#: cross-sectionally, weighted mean of the AVAILABLE factors per name).
COMPOSITE_WEIGHTS: dict[str, float] = {
    "mom_12_1": 1.0,
    "multifactor": 1.0,   # itself momentum+insider+revisions on book names
    "revisions": 0.5,
    "insider_opp": 0.5,
    "pead": 0.5,
    "quality": 0.5,
}


def _add_arena_composite(names: dict) -> None:
    from backend.services.portfolio_intelligence.multifactor import (
        compute_multifactor_scores,  # pure function — no IO, no NAV path
    )

    components: dict[str, dict[str, float]] = {}
    for factor in COMPOSITE_WEIGHTS:
        col = {t: row["scores"][factor] for t, row in names.items()
               if row.get("status") == "ok"
               and row.get("scores", {}).get(factor) is not None}
        if col:
            components[factor] = col
    composite = compute_multifactor_scores(components, COMPOSITE_WEIGHTS)
    for t, row in names.items():
        if row.get("status") == "ok":
            row["scores"]["arena_composite"] = composite.get(t)


def freeze_day_state(day: date, panel: PricePanel, universe: list[str],
                     *, root=None, db_path=None) -> dict:
    existing = store.read_snapshot(str(day), root)
    if existing is not None:
        return existing
    state = build_day_state(day, panel, universe, db_path=db_path)
    if state["scored_n"] == 0:
        # A snapshot with zero scores would make every book silently hold
        # forever while looking scheduled and green. Freeze it anyway (it IS
        # the day's truth) but say so loudly in the log and the state itself.
        logger.warning("ARENA: %s snapshot has ZERO multifactor-scored names "
                       "out of %d — selection cannot refresh from this state",
                       day, state["universe_n"])
    return store.freeze_snapshot(str(day), state, root)
