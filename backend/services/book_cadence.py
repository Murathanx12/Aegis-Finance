"""LANE B4 — the pass that marks every book and lets the due ones decide.

WHAT A PASS IS
==============
One call per cadence bucket. It marks every `holding` book of that cadence from
the local bars, lets the ones whose period has turned over decide, writes one
`paper_nav` row per (book, timestamp) under the `book:` namespace, and writes a
receipt — **including when it did nothing** (invariant 15: a pass with nothing
to do writes "nothing to do", because a silent pass and a dead scheduler are
the same observation).

`run_one` IS BACKTEST-ONLY, AND THIS IS THE HONEST CONSEQUENCE
==============================================================
`backend/strategy/run.py::run_one` requires a `Window` and dispatches to engines
that REPLAY one (`series` grades a return series someone else already built;
`arena_composite` and `growth_lab` replay history). There is no registered
engine that answers "what would this contract hold at the close of today", and
inventing a `Window` ending today to get one would be a backtest wearing a
decision's clothes.

So a book decides through `decide_weights` below: the simplest selector that is
FAITHFUL to the contract — the declared universe, the declared signal, the
declared construction rule, k, weighting and single-name cap, the declared
gross cap. It supports a small, named set of signals computable from daily bars
and **refuses by name** for anything else (`UnsupportedSignal`), which is
recorded on the receipt. A selector that silently substituted a ranking it
could compute for the one the contract declared would produce a NAV series
belonging to a strategy nobody wrote down.

THE CLOCK
=========
A decision is taken AT THE CLOSE of `asof` and executed at that close. The pass
is scheduled after the close for exactly this reason; a pass run intraday would
be deciding on a bar that has not finished forming, and the receipt records the
bar date it used so that is checkable rather than assumed.

GRANULARITY IS SAID, NOT ASSUMED
================================
Minute bars do not exist on this machine. A `30m` book is therefore marked from
the latest available DAILY bar and the mark says
`granularity="daily_close"` with `intraday_bars_available=False`. The pass does
not pretend to a resolution it does not have; lane D (chunk 5b) is where the
intraday mark is built.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence

from backend.services import paper_books as PB
from backend.services.paper_books import PaperBook

logger = logging.getLogger(__name__)

#: The cash leg of a book, held in `paper_positions` as a position whose
#: "shares" are dollars and whose price is 1.0. `paper_positions` has no cash
#: column and adding one would touch the reference lanes' table shape; a
#: namespaced synthetic row does not.
CASH = "$CASH"

#: Signals the live selector can compute from daily bars. Anything else is a
#: REFUSAL, not a substitution.
SUPPORTED_SIGNALS: tuple[str, ...] = (
    "mom_12_1",            # t-252 .. t-21 return (the 12-1 momentum of the arena)
    "mom_21",              # 21-session return
    "rev_5",               # 5-session return (a reversal book declares direction=-1)
    "overnight_gap",       # mean overnight return over 21 sessions
    "vol_21",              # 21-session realised volatility
    "random_genome_null",  # the random twin: a fresh uniform draw each period
    "beta_matched_index_sleeve",  # the beta twin: equal weight over its own draw
    "overnight_only",      # the lane D twin: the overnight leg, marked separately
)


class UnsupportedSignal(PB.BookError):
    """The contract declares a ranking this selector cannot compute.

    A refusal rather than a fallback: a book whose NAV came from a signal other
    than the one it declares is a book nobody wrote down.
    """


class CannotMark(PB.BookError):
    """A holding could not be priced, so the book was not marked at all.

    Partial marking is worse than no mark: a NAV that silently omits a position
    is a NAV that reports a loss the book did not take, and it enters a forward
    record that nothing later can correct.
    """


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def receipt_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "book_cadence"


def enabled_on_deployment() -> bool:
    """Railway runs the cadence pass only when asked. Desktop always does."""
    return os.getenv("AEGIS_BOOK_CADENCE", "").strip() == "1"


# --------------------------------------------------------------------------
# the price panel


def _wide_close(bars, symbols: Sequence[str], asof: date, *, field: str = "close"):
    import pandas as pd
    ts = pd.Timestamp(asof)
    sub = bars[(bars["date"] <= ts) & (bars["symbol"].isin(list(symbols)))]
    if sub.empty:
        return pd.DataFrame()
    return sub.pivot_table(index="date", columns="symbol", values=field,
                           aggfunc="last").sort_index()


def latest_prices(bars, symbols: Sequence[str], asof: date,
                  *, fallback: Callable[[list[str]], dict] | None = None
                  ) -> tuple[dict[str, float], dict[str, str]]:
    """({symbol: price}, {symbol: source}). Missing names are simply absent.

    The SOURCE of every price is returned beside it, so a receipt can say which
    names came from the local bars and which from the network — "priced" and
    "priced from where" are different facts and the second one is the one that
    goes stale.
    """
    import pandas as pd

    wide = _wide_close(bars, symbols, asof)
    out: dict[str, float] = {}
    src: dict[str, str] = {}
    if not wide.empty:
        last = wide.ffill().iloc[-1]
        for sym in wide.columns:
            v = last.get(sym)
            if v is not None and pd.notna(v):
                out[str(sym)] = float(v)
                src[str(sym)] = "local_bars"
    missing = [s for s in symbols if s not in out and s != CASH]
    if missing and fallback is not None:
        try:
            got = fallback(missing) or {}
        except Exception as exc:                                   # noqa: BLE001
            logger.warning("book cadence: price fallback failed (%s) — %d name(s) "
                           "stay unpriced and are named on the receipt",
                           exc, len(missing))
            got = {}
        for sym, px in got.items():
            if px is not None:
                out[str(sym)] = float(px)
                src[str(sym)] = "yfinance"
    return out, src


def yfinance_fallback(symbols: list[str]) -> dict[str, float]:
    """Last adjusted close per symbol. Network; never called by the fast suite.

    The fast suite is network-blocked, so this is passed IN by the caller that
    is allowed to reach the network rather than being reached for by default.
    """
    import yfinance as yf
    df = yf.download(symbols, period="5d", auto_adjust=True, progress=False,
                     timeout=30)["Close"]
    if hasattr(df, "columns"):
        return {str(c): float(df[c].dropna().iloc[-1])
                for c in df.columns if df[c].dropna().size}
    s = df.dropna()
    return {symbols[0]: float(s.iloc[-1])} if s.size else {}


# --------------------------------------------------------------------------
# the selector


def _signal_frame(book: PaperBook, bars, symbols: Sequence[str], asof: date):
    """{symbol: signal value} for the book's declared signal, or a refusal."""
    import numpy as np
    import pandas as pd

    name = book.strategy.signal.name
    if name not in SUPPORTED_SIGNALS:
        raise UnsupportedSignal(
            f"book {book.book_id} declares signal {name!r}; this selector can "
            f"compute {list(SUPPORTED_SIGNALS)}. The book is marked but does "
            f"NOT decide: a NAV produced by a different ranking than the "
            f"contract declares belongs to a strategy nobody wrote down.")

    if name == "random_genome_null":
        # A fresh draw each period, seeded by the twin's own recorded seed and
        # the date -- deterministic for a given (twin, date) and different every
        # period, which is what a random-genome null is.
        seed = int((book.strategy.engine_params.get("twin") or {}).get("seed", 0))
        rng = np.random.default_rng(seed + int(asof.strftime("%Y%m%d")))
        return {s: float(v) for s, v in zip(sorted(symbols),
                                            rng.random(len(symbols)))}
    if name in ("beta_matched_index_sleeve", "overnight_only"):
        # Both hold their whole declared draw, equally weighted: the control is
        # the DRAW, not a ranking inside it.
        return {s: 1.0 for s in sorted(symbols)}

    close = _wide_close(bars, symbols, asof)
    if close.empty:
        return {}
    out: dict[str, float] = {}
    if name == "mom_12_1":
        if len(close) < 253:
            raise UnsupportedSignal(
                f"mom_12_1 needs 253 sessions ending {asof}; the local bars hold "
                f"{len(close)}. A 12-1 momentum computed on a shorter window is "
                f"a different signal wearing the same name.")
        w = close.iloc[-253:]
        ratio = w.iloc[-22] / w.iloc[0] - 1.0
        out = {str(k): float(v) for k, v in ratio.items() if pd.notna(v)}
    elif name in ("mom_21", "rev_5"):
        n = 21 if name == "mom_21" else 5
        if len(close) < n + 1:
            raise UnsupportedSignal(
                f"{name} needs {n + 1} sessions ending {asof}; the local bars "
                f"hold {len(close)}")
        w = close.iloc[-(n + 1):]
        ratio = w.iloc[-1] / w.iloc[0] - 1.0
        out = {str(k): float(v) for k, v in ratio.items() if pd.notna(v)}
    elif name == "vol_21":
        if len(close) < 22:
            raise UnsupportedSignal(f"vol_21 needs 22 sessions; bars hold {len(close)}")
        rets = close.iloc[-22:].pct_change(fill_method=None).iloc[1:]
        sd = rets.std()
        out = {str(k): float(v) for k, v in sd.items() if pd.notna(v)}
    elif name == "overnight_gap":
        opens = _wide_close(bars, symbols, asof, field="open")
        if len(close) < 22 or opens.empty:
            raise UnsupportedSignal(f"overnight_gap needs 22 sessions; bars hold {len(close)}")
        cols = [c for c in close.columns if c in opens.columns]
        gap = (opens[cols].iloc[-21:].to_numpy()
               / close[cols].iloc[-22:-1].to_numpy() - 1.0)
        means = np.nanmean(gap, axis=0)
        out = {str(c): float(m) for c, m in zip(cols, means) if np.isfinite(m)}
    return out


def decide_weights(book: PaperBook, bars, asof: date) -> tuple[dict[str, float], dict]:
    """Target weights at the close of `asof`, faithful to the contract.

    Honours, in order: the declared universe, the declared signal and its
    direction, the construction rule (`threshold_coverage` abstains to the
    declared fallback when coverage is empty), `k`, the weighting, the
    single-name cap and the gross cap. Returns (weights, detail) where `detail`
    is what the receipt prints.
    """
    universe = PB.resolve_universe(book.strategy, bars, asof)
    if not universe:
        return {}, {"reason": "universe resolved to no names", "n_universe": 0}
    values = _signal_frame(book, bars, universe, asof)
    if not values:
        return {}, {"reason": "the signal produced no values", "n_universe": len(universe)}

    direction = int(book.strategy.signal.direction)
    ranked = sorted(values.items(), key=lambda kv: kv[1] * direction, reverse=True)
    detail: dict = {"n_universe": len(universe), "n_scored": len(ranked),
                    "signal": book.strategy.signal.name, "direction": direction,
                    "rule": book.strategy.construction.rule}

    cons = book.strategy.construction
    if cons.rule == "threshold_coverage":
        ab = dict((book.strategy.engine_params or {}).get("abstain") or {})
        floor = ab.get("min_signal")
        min_names = int(ab.get("min_names", 1))
        fallback = str(ab.get("fallback", CASH))
        if floor is None:
            raise UnsupportedSignal(
                f"book {book.book_id} declares construction 'threshold_coverage' "
                f"with no `engine_params['abstain']['min_signal']`. The threshold "
                f"IS the decision for an abstention book; without it the book "
                f"cannot say when it is out.")
        cleared = [(s, v) for s, v in ranked if v * direction >= float(floor) * direction]
        detail["n_cleared"] = len(cleared)
        detail["threshold"] = float(floor)
        if len(cleared) < min_names:
            detail["abstained"] = True
            detail["fallback"] = fallback
            return ({} if fallback == CASH else {fallback: 1.0}), detail
        ranked = cleared

    picked = ranked[: int(cons.k)]
    if not picked:
        return {}, {**detail, "reason": "no name survived the construction"}

    if cons.weighting == "ew":
        raw = {s: 1.0 for s, _ in picked}
    elif cons.weighting == "rank":
        raw = {s: float(len(picked) - i) for i, (s, _) in enumerate(picked)}
    elif cons.weighting == "inverse_vol":
        close = _wide_close(bars, [s for s, _ in picked], asof)
        sd = close.iloc[-22:].pct_change(fill_method=None).iloc[1:].std()
        raw = {s: (1.0 / float(sd[s]) if s in sd.index and float(sd.get(s) or 0) > 0
                   else 0.0)
               for s, _ in picked}
        if not any(raw.values()):
            raise UnsupportedSignal(
                "inverse_vol weighting: no name had a positive realised "
                "volatility over the trailing 21 sessions. Falling back to "
                "equal weight would silently produce a different book.")
    else:
        raise UnsupportedSignal(
            f"weighting {cons.weighting!r} is declared by the contract and not "
            f"implemented by this selector; the book is marked but does not "
            f"decide rather than being weighted some other way")

    total = sum(raw.values())
    weights = {s: v / total for s, v in raw.items() if v > 0}
    cap = float(cons.max_single_name)
    if cap > 0:
        weights = {s: min(w, cap) for s, w in weights.items()}
        t = sum(weights.values())
        if t > 0:
            weights = {s: w / t for s, w in weights.items()}
    gross = float(cons.gross_cap)
    weights = {s: w * gross for s, w in weights.items()}
    detail["n_picked"] = len(weights)
    detail["gross"] = round(sum(weights.values()), 6)
    return weights, detail


# --------------------------------------------------------------------------
# positions, marks and decisions


def _positions(conn: sqlite3.Connection, book_id: str) -> dict[str, float]:
    rows = conn.execute(
        "SELECT ticker, shares FROM paper_positions "
        "WHERE portfolio_id = ? AND closed_at IS NULL", (book_id,)).fetchall()
    return {str(r["ticker"]): float(r["shares"]) for r in rows}


def _write_positions(conn: sqlite3.Connection, book_id: str,
                     shares: dict[str, float], prices: dict[str, float],
                     when: str) -> None:
    from backend.db import _write_lock
    with _write_lock:
        conn.execute("UPDATE paper_positions SET closed_at = ? "
                     "WHERE portfolio_id = ? AND closed_at IS NULL", (when, book_id))
        for ticker, sh in shares.items():
            if abs(sh) < 1e-12:
                continue
            conn.execute(
                "INSERT INTO paper_positions "
                "(portfolio_id, ticker, shares, cost_basis, opened_at, closed_at) "
                "VALUES (?,?,?,?,?,NULL)",
                (book_id, ticker, float(sh),
                 float(prices.get(ticker, 1.0)), when))
        conn.commit()


def book_nav(conn: sqlite3.Connection, book: PaperBook, prices: dict[str, float]
             ) -> float:
    """Cash plus mark-to-market. Raises `CannotMark` if a holding is unpriced."""
    held = _positions(conn, book.book_id)
    if not held:
        return PB.INCEPTION_VALUE
    dark = [t for t in held if t != CASH and t not in prices]
    if dark:
        raise CannotMark(
            f"{book.book_id}: {len(dark)} holding(s) could not be priced "
            f"({dark[:8]}). The book is NOT marked this pass — a NAV that omits "
            f"a position reports a loss the book did not take.")
    return sum(sh if t == CASH else sh * prices[t] for t, sh in held.items())


def _overnight_nav(conn, book: PaperBook, bars, asof: date, prev_nav: float
                   ) -> tuple[float, dict]:
    """The overnight-only twin's mark: last close -> this open, flat intraday.

    Computable at DAILY resolution because the parquet carries `open`. It is a
    separate path on purpose: running this book through the close-to-close mark
    would silently turn it into buy-and-hold, which is the exact thing the twin
    exists to be different from.
    """
    import numpy as np
    import pandas as pd

    symbols = list((book.strategy.engine_params or {}).get("symbols") or [])
    if not symbols:
        raise CannotMark(f"{book.book_id}: the overnight twin carries no draw")
    close = _wide_close(bars, symbols, asof)
    opens = _wide_close(bars, symbols, asof, field="open")
    cols = [c for c in close.columns if c in opens.columns]
    if len(close) < 2 or not cols:
        raise CannotMark(f"{book.book_id}: fewer than two sessions of bars")
    gap = (opens[cols].iloc[-1].to_numpy() / close[cols].iloc[-2].to_numpy() - 1.0)
    r = float(np.nanmean(gap)) if np.isfinite(gap).any() else 0.0
    if not np.isfinite(r):
        r = 0.0
    detail = {"overnight_return": r, "n_names": len(cols),
              "granularity": "daily open vs previous close (the overnight leg only)",
              "bar_date": str(pd.Timestamp(close.index[-1]).date())}
    return prev_nav * (1.0 + r), detail


def _last_nav(conn: sqlite3.Connection, book_id: str) -> float | None:
    row = conn.execute(
        "SELECT nav FROM paper_nav WHERE portfolio_id = ? ORDER BY date DESC LIMIT 1",
        (book_id,)).fetchone()
    return float(row["nav"]) if row else None


def _last_decision(conn: sqlite3.Connection, book_id: str) -> str | None:
    row = conn.execute(
        "SELECT asof_date FROM paper_book_decisions WHERE book_id = ? "
        "ORDER BY asof_date DESC LIMIT 1", (book_id,)).fetchone()
    return str(row["asof_date"]) if row else None


def _period_key(cadence: str, d: date) -> str:
    """The label of the period `d` falls in. A decision is due when this changes.

    Calendar boundaries rather than a session count, because a session count
    depends on which bars a machine happens to hold and two machines would then
    disagree about whether a book had decided.
    """
    if cadence in ("30m", "daily"):
        return d.isoformat()
    if cadence == "weekly":
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if cadence == "monthly":
        return f"{d.year}-{d.month:02d}"
    if cadence == "quarterly":
        return f"{d.year}-Q{(d.month - 1) // 3 + 1}"
    raise PB.BookError(f"no period rule for cadence {cadence!r}")


def decision_due(book: PaperBook, conn: sqlite3.Connection, asof: date) -> bool:
    last = _last_decision(conn, book.book_id)
    if last is None:
        return True
    return _period_key(book.cadence, date.fromisoformat(last)) != _period_key(
        book.cadence, asof)


def latest_bar_date(bars, on_or_before: date | None = None) -> date | None:
    import pandas as pd
    d = bars["date"]
    if on_or_before is not None:
        d = d[d <= pd.Timestamp(on_or_before)]
    if d.empty:
        return None
    return pd.Timestamp(d.max()).date()


# --------------------------------------------------------------------------
# the pass


def run_pass(cadence: str, *, today: date | None = None,
             db_path: Path | None = None,
             conn: sqlite3.Connection | None = None,
             bars=None, price_fallback: Callable[[list[str]], dict] | None = None,
             write_receipt: bool = True,
             write_forecasts: bool = True) -> dict:
    """Mark every holding book of one cadence; let the due ones decide.

    Returns the receipt. Every book is accounted for — marked, decided,
    refused-with-a-reason or nothing-to-do — and none is silently absent.
    """
    if cadence not in PB.CADENCES:
        raise PB.BookError(f"cadence {cadence!r} is not one of {list(PB.CADENCES)}")
    started = _now()
    today = today or date.today()
    own = conn is None
    conn = conn or PB._conn(db_path)
    receipt: dict = {
        "job": "book_cadence", "cadence": cadence, "ran_at": started,
        "today": str(today), "books_considered": 0, "marked": [], "decisions": [],
        "refused": [], "unpriced": [], "nothing_to_do": False,
        "granularity": "daily_close",
        "intraday_bars_available": False,
        "granularity_note": (
            "minute bars do not exist on this machine, so a 30m book is marked "
            "from the latest DAILY bar. The pass says so rather than implying a "
            "resolution it does not have; lane D (chunk 5b) builds the intraday "
            "mark."),
        "selector": ("decide_weights -- run_one is backtest-only (it requires a "
                     "Window and every registered engine replays one), so a live "
                     "decision uses the faithful selector and REFUSES any signal "
                     "or weighting it cannot compute"),
    }
    try:
        if bars is None:
            bars = PB.load_bars()
        asof = latest_bar_date(bars, today)
        if asof is None:
            receipt["nothing_to_do"] = True
            receipt["reason"] = "the local bars hold no session on or before today"
            return _finish(receipt, write_receipt)
        receipt["bar_date"] = str(asof)

        books = [b for b in PB.list_books(cadence=cadence, status="holding",
                                          conn=conn)]
        receipt["books_considered"] = len(books)
        if not books:
            receipt["nothing_to_do"] = True
            receipt["reason"] = f"no holding book declares cadence {cadence!r}"
            return _finish(receipt, write_receipt)

        # one price panel for every symbol any book of this cadence could touch
        wanted: set[str] = set()
        for b in books:
            try:
                wanted.update(PB.resolve_universe(b.strategy, bars, asof))
            except Exception as exc:                               # noqa: BLE001
                receipt["refused"].append({"book_id": b.book_id,
                                           "stage": "universe",
                                           "reason": f"{type(exc).__name__}: {exc}"[:300]})
            wanted.update(_positions(conn, b.book_id))
        wanted.discard(CASH)
        prices, sources = latest_prices(bars, sorted(wanted), asof,
                                        fallback=price_fallback)
        receipt["priced"] = {"n_wanted": len(wanted), "n_priced": len(prices),
                             "from_local_bars": sum(1 for v in sources.values()
                                                    if v == "local_bars"),
                             "from_yfinance": sum(1 for v in sources.values()
                                                  if v == "yfinance")}
        receipt["unpriced"] = sorted(s for s in wanted if s not in prices)

        forecast_rows = []
        for b in books:
            row = _one_book(conn, b, bars, asof, prices, receipt)
            if row is not None:
                forecast_rows.append(row)

        if write_forecasts and forecast_rows:
            try:
                from backend.services.book_forecasts import write_decision_forecasts
                receipt["forecasts"] = write_decision_forecasts(
                    forecast_rows, conn=conn, asof=asof)
            except Exception as exc:                               # noqa: BLE001
                logger.error("book cadence: forecast rows not written: %s", exc,
                             exc_info=True)
                receipt["forecasts"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}

        receipt["nothing_to_do"] = not (receipt["marked"] or receipt["decisions"])
        return _finish(receipt, write_receipt)
    finally:
        if own:
            conn.close()


def _one_book(conn, book: PaperBook, bars, asof: date, prices: dict,
              receipt: dict) -> PaperBook | None:
    """Mark one book, and decide if its period has turned. Never raises."""
    from backend.db import insert_nav

    prev = _last_nav(conn, book.book_id)
    is_overnight = (book.strategy.signal.name == "overnight_only")
    try:
        if is_overnight:
            nav, detail = _overnight_nav(conn, book, bars, asof,
                                         prev if prev is not None else PB.INCEPTION_VALUE)
        else:
            nav, detail = book_nav(conn, book, prices), {"granularity": "daily_close"}
    except PB.BookError as exc:
        receipt["refused"].append({"book_id": book.book_id, "stage": "mark",
                                   "reason": str(exc)[:400]})
        return None

    insert_nav(conn, book.book_id, str(asof), float(nav),
               book.strategy.fingerprint, _now())
    receipt["marked"].append({"book_id": book.book_id, "nav": round(float(nav), 2),
                              "date": str(asof), "is_twin": book.is_twin,
                              **detail})

    if is_overnight:
        # The overnight twin holds its whole declared draw by construction; it
        # is marked, never re-selected, so "decided" would be a word for
        # nothing having happened.
        return book
    if not decision_due(book, conn, asof):
        return book
    try:
        weights, detail = decide_weights(book, bars, asof)
    except PB.BookError as exc:
        receipt["refused"].append({"book_id": book.book_id, "stage": "decide",
                                   "reason": str(exc)[:400]})
        return book
    if not weights:
        receipt["decisions"].append({"book_id": book.book_id, "asof": str(asof),
                                     "n_names": 0, **detail})
        return book

    dark = [s for s in weights if s not in prices and s != CASH]
    if dark:
        receipt["refused"].append({
            "book_id": book.book_id, "stage": "decide",
            "reason": (f"{len(dark)} selected name(s) have no price ({dark[:8]}); "
                       f"the book keeps its previous positions rather than "
                       f"buying at a price nobody quoted")})
        return book

    held = _positions(conn, book.book_id)
    old_notional = {t: (sh if t == CASH else sh * prices.get(t, 0.0))
                    for t, sh in held.items()}
    new_notional = {s: float(nav) * w for s, w in weights.items()}
    traded = sum(abs(new_notional.get(t, 0.0) - old_notional.get(t, 0.0))
                 for t in set(old_notional) | set(new_notional) if t != CASH)
    rate = (book.strategy.costs.transaction_cost_bps
            + book.strategy.costs.slippage_bps) / 10_000.0
    cost = traded * rate
    shares = {s: n / prices[s] for s, n in new_notional.items() if prices.get(s)}
    cash = float(nav) - sum(new_notional.values()) - cost
    if abs(cash) > 1e-9:
        shares[CASH] = cash
    _write_positions(conn, book.book_id, shares, prices, _now())

    from backend.db import _write_lock
    with _write_lock:
        conn.execute(
            "INSERT OR REPLACE INTO paper_book_decisions "
            "(book_id, decided_utc, asof_date, weights_json, nav_before, "
            " traded_notional, cost_usd, note) VALUES (?,?,?,?,?,?,?,?)",
            (book.book_id, _now(), str(asof),
             json.dumps({k: round(v, 6) for k, v in sorted(weights.items())}),
             float(nav), float(traded), float(cost), json.dumps(detail)))
        conn.commit()
    receipt["decisions"].append({
        "book_id": book.book_id, "asof": str(asof), "n_names": len(weights),
        "traded_notional": round(traded, 2), "cost_usd": round(cost, 2),
        "cost_rate_bps": round(rate * 10_000.0, 4), "nav_before": round(nav, 2),
        **detail})
    return book


def _finish(receipt: dict, write_receipt: bool) -> dict:
    receipt["finished_at"] = _now()
    receipt["n_marked"] = len(receipt.get("marked") or [])
    receipt["n_decisions"] = len(receipt.get("decisions") or [])
    receipt["n_refused"] = len(receipt.get("refused") or [])
    if receipt.get("nothing_to_do") and "reason" not in receipt:
        receipt["reason"] = ("every book of this cadence was already marked for "
                             "this bar and none was due to decide")
    if write_receipt:
        try:
            d = receipt_dir()
            d.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
            path = d / f"{stamp}_{receipt['cadence']}.json"
            path.write_text(json.dumps(receipt, indent=2, default=str),
                            encoding="utf-8")
            receipt["receipt_path"] = str(path)
        except Exception as exc:                                   # noqa: BLE001
            logger.warning("book cadence receipt not written: %s", exc)
    return receipt


def run_all(cadences: Iterable[str] | None = None, **kw) -> dict:
    """Every cadence bucket, one receipt each, plus a roll-up."""
    out = {}
    for c in (cadences or PB.CADENCES):
        try:
            out[c] = run_pass(c, **kw)
        except Exception as exc:                                   # noqa: BLE001
            logger.error("book cadence %s failed: %s", c, exc, exc_info=True)
            out[c] = {"cadence": c, "error": f"{type(exc).__name__}: {exc}"[:300]}
    return {"utc": _now(), "passes": out,
            "n_marked": sum(p.get("n_marked", 0) for p in out.values()),
            "n_decisions": sum(p.get("n_decisions", 0) for p in out.values()),
            "n_refused": sum(p.get("n_refused", 0) for p in out.values())}


__all__ = ["CASH", "CannotMark", "SUPPORTED_SIGNALS", "UnsupportedSignal",
           "book_nav", "decide_weights", "decision_due", "enabled_on_deployment",
           "latest_bar_date", "latest_prices", "receipt_dir", "run_all",
           "run_pass", "yfinance_fallback"]
