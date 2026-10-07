"""PC-PAPER named EXPLOIT sleeves that mirror a FROZEN book (owner, 2026-10-07).

Owner, 2026-10-07 17:05 HKT: *"dont stay cash on pc. lets do the best decision
and profit maximizing strat"*. The leading paper account that day was the
frozen book `revision_flow_v0` (book id cb8d492bb8bf9ade, analyst revision
flow, +7.14% vs SPY +1.40% over 7 sessions since 09-28, random twin -0.01%;
OBSERVED(7), a PRODUCT_EXPERIMENT, never a claim). This module lets
`sim_run.u_plan` hold that book as one named sleeve of PC-PAPER.

* `load_revision_flow` reads the frozen book from the llm_portfolio store
  (the book of record) and the hack2 v2 contract's copy of it, and REFUSES
  when the two ticker sets differ, the book is missing or voided, or a
  weight is not the book's equal weight. It never re-selects a name.
* `sleeve_worst_case` is session protocol item 4 for the sleeve: the one-day
  k-sigma loss with rho = 1 across names (`FLEET_V3_MAX_K_SIGMA_DAY_LOSS_FRAC`
  rule) and, when a bars panel is given, the basket's worst 21-session return
  and worst day, in dollars.
* `choose_gross` picks the sleeve's gross from the worst case, NOT from
  conviction: the largest gross, rounded DOWN to 5%, that satisfies BOTH
  bounds (coordinator, 2026-10-07):
    1. the whole book's one-day k-sigma loss, rho = 1 (PROBE at its largest
       admissible + this sleeve + the SPY core on the remainder) <= `limit`
       (FLEET_V3_MAX_K_SIGMA_DAY_LOSS_FRAC, 0.10) and total gross <= 100%;
    2. gross x |the basket's worst historical 21-session return| <=
       `window_limit` (PC_SLEEVE_MAX_WORST_21_SESSION_LOSS_FRAC, 0.10).
  On 2026-10-07: bound 1 alone allows 60% (9.95%); bound 2 with the worst
  21 sessions -19.05% allows 50% (9.53%; 55% = 10.48% fails) => 50%.

PURE except the two loaders, which only READ files. Never an order.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from backend import config as _cfg

SLEEVE_STATE = "REVISION_FLOW"
BOOK_NAME = "revision_flow_v0"


class SleeveRefused(RuntimeError):
    """The frozen book cannot be mirrored safely; the sleeve stays cash/core."""


def _contract_positions(path: Path) -> tuple[str, list[dict]]:
    c = json.loads(Path(path).read_text(encoding="utf-8"))
    sel = c.get("selection") or {}
    return str(sel.get("book_id") or ""), list(sel.get("positions") or [])


def load_revision_flow(*, book_id: Optional[str] = None, books_path: Optional[Path] = None,
                       contract_path: Optional[Path] = None) -> dict:
    """The frozen revision_flow_v0 positions, cross-checked against hack2_v2.

    Returns {book_id, name, frozen_utc, asof, tickers, book_weight, source,
    cross_check}. Raises SleeveRefused with the reason."""
    from backend.services import llm_portfolio as LP               # noqa: PLC0415
    bid = str(book_id or _cfg.PC_SLEEVE_REVISION_FLOW_BOOK_ID)
    books = LP.read_books(books_path)
    rec = next((b for b in books if b.get("book_id") == bid), None)
    if rec is None:
        voided = {v["book_id"] for v in LP.voided_before_entry(books_path)}
        raise SleeveRefused(f"book {bid} is " + ("VOIDED" if bid in voided else
                                                 "not in the llm_portfolio store"))
    pos = [p for p in rec.get("positions") or [] if p.get("ticker")]
    if not pos:
        raise SleeveRefused(f"book {bid} carries no positions")
    tickers = [str(p["ticker"]).upper() for p in pos]
    if len(set(tickers)) != len(tickers):
        raise SleeveRefused(f"book {bid} lists a ticker twice")
    ws = [float(p.get("weight") or 0.0) for p in pos]
    if max(ws) - min(ws) > 1e-9:
        raise SleeveRefused(f"book {bid} is not equal-weight ({min(ws):.4f}..{max(ws):.4f}); "
                            f"the mirror only scales an equal-weight book")
    cpath = Path(contract_path or _cfg.PC_SLEEVE_REVISION_FLOW_CONTRACT)
    try:
        c_bid, c_pos = _contract_positions(cpath)
    except (OSError, ValueError) as exc:
        raise SleeveRefused(f"cross-check contract unreadable ({cpath.name}): "
                            f"{type(exc).__name__}: {exc}") from exc
    c_tickers = sorted(str(p.get("ticker")).upper() for p in c_pos if p.get("ticker"))
    if c_bid != bid:
        raise SleeveRefused(f"{cpath.name} mirrors book {c_bid!r}, not {bid}")
    if c_tickers != sorted(tickers):
        only_b = sorted(set(tickers) - set(c_tickers))
        only_c = sorted(set(c_tickers) - set(tickers))
        raise SleeveRefused(f"ticker sets differ: book-only {only_b}, {cpath.name}-only {only_c}")
    return {"book_id": bid, "name": rec.get("name"), "frozen_utc": rec.get("frozen_utc"),
            "asof": rec.get("asof"), "tickers": tickers, "book_weight": ws[0],
            "licence": "PRODUCT_EXPERIMENT", "mechanism": "analyst revision flow "
            "(backend/services/revision_flow.py): net target raises x distinct firms, 90 days",
            "source": "llm_portfolio/books.jsonl (the book of record)",
            "cross_check": f"{cpath.name} selection.positions: same {len(tickers)} tickers"}


def sleeve_loss_frac(names: list[str], gross: float, sigmas: dict, *, k: float,
                     fallback: float) -> tuple[float, int]:
    """One-day k-sigma loss of an equal-weight sleeve, rho = 1, as a fraction of equity."""
    if not names or gross <= 0:
        return 0.0, 0
    w = gross / len(names)
    tot, n_fb = 0.0, 0
    for s in names:
        sig = sigmas.get(s)
        if not (isinstance(sig, (int, float)) and sig > 0):
            sig, n_fb = fallback, n_fb + 1
        tot += w * k * float(sig)
    return tot, n_fb


def basket_history(names: list[str], bars_path: Path, *, window: int = 21) -> dict:
    """The equal-weight (daily-rebalanced) basket's worst `window`-session return
    and worst day on the bars panel. {} fields when unreadable."""
    try:
        import pandas as pd                                        # noqa: PLC0415
        df = pd.read_parquet(bars_path, columns=["symbol", "date", "close"])
        df = df[df["symbol"].isin(list(names))]
        wide = df.pivot_table(index="date", columns="symbol", values="close").sort_index()
        r = wide.pct_change(fill_method=None)
        bk = r.mean(axis=1, skipna=True).dropna()
        cum = (1.0 + bk).cumprod()
        roll = (cum / cum.shift(window) - 1.0).dropna()
        return {"window_sessions": window, "first": str(bk.index.min().date()),
                "last": str(bk.index.max().date()), "n_days": int(len(bk)),
                "n_names_priced": int(r.count().gt(0).sum()),
                "worst_window_return": float(roll.min()),
                "worst_window_end": str(roll.idxmin().date()),
                "worst_day_return": float(bk.min()), "worst_day": str(bk.idxmin().date()),
                "daily_sd": float(bk.std())}
    except Exception as exc:                                       # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"[:200]}


def book_loss_frac(*, rf_names: list[str], rf_gross: float, probe_gross: float,
                   probe_sigma: float, core_sigma: float, sigmas: dict, k: float,
                   fallback: float, cash_buffer: float) -> dict:
    """Whole-book one-day k-sigma loss (rho = 1): PROBE + this sleeve + SPY core."""
    rf, n_fb = sleeve_loss_frac(rf_names, rf_gross, sigmas, k=k, fallback=fallback)
    pr = probe_gross * k * probe_sigma
    core_w = max(0.0, 1.0 - probe_gross - rf_gross - cash_buffer)
    co = core_w * k * core_sigma
    return {"rf_frac": rf, "probe_frac": pr, "core_frac": co, "core_weight": core_w,
            "total_frac": rf + pr + co, "gross": probe_gross + rf_gross + core_w,
            "n_sigma_fallback": n_fb}


def choose_gross(*, rf_names: list[str], probe_gross: float, probe_sigma: float,
                 core_sigma: float, sigmas: dict, k: float, limit: float, fallback: float,
                 cash_buffer: float, worst_window_return: float | None,
                 window_limit: float, step: float = 0.05, floor: float = 0.20) -> dict:
    """The largest sleeve gross (multiple of `step`, rounded DOWN) passing BOTH
    bounds: (1) the whole book's rho=1 k-sigma day <= `limit` with gross <= 1;
    (2) gross x |worst_window_return| <= `window_limit` (the basket's worst
    historical 21-session return). An UNKNOWN worst window (None) fails bound 2
    at every gross: a bound that cannot be computed does not pass. Below `floor`
    -> says so and returns `floor` only if `floor` passes both, else 0."""
    def _passes(g: float) -> tuple[bool, bool, dict]:
        b = book_loss_frac(rf_names=rf_names, rf_gross=g, probe_gross=probe_gross,
                           probe_sigma=probe_sigma, core_sigma=core_sigma, sigmas=sigmas,
                           k=k, fallback=fallback, cash_buffer=cash_buffer)
        one = b["total_frac"] <= limit + 1e-12 and b["gross"] <= 1.0 + 1e-12
        two = (worst_window_return is not None
               and g * abs(float(worst_window_return)) <= window_limit + 1e-12)
        return one, two, b
    best1 = best2 = best = 0.0
    g = 0.0
    hi = max(0.0, 1.0 - probe_gross - cash_buffer)
    while g <= hi + 1e-9:
        one, two, _ = _passes(g)
        if one:
            best1 = g
        if two:
            best2 = g
        if one and two:
            best = g
        g = round(g + step, 10)
    note = None
    if best < floor:
        one, two, _ = _passes(floor)
        note = (f"the worst case allows only {best:.0%} (< {floor:.0%}); "
                + (f"stopping at {floor:.0%}" if one and two else
                   "even the floor fails: sleeve OFF"))
        best = floor if one and two else 0.0
    return {"gross": best, "step": step, "note": note,
            "bound_one_day_k_sigma": best1, "bound_worst_21_session": best2,
            "binding": ("worst_21_session" if best2 < best1 else
                        "one_day_k_sigma" if best1 < best2 else "both"),
            "worst_window_return": worst_window_return}


def sleeve_worst_case(*, equity: float, names: list[str], gross: float, sigmas: dict,
                      k: float, fallback: float, history: Optional[dict] = None,
                      label: str = "revision_flow sleeve") -> dict:
    """Session protocol item 4 for one sleeve, in dollars."""
    frac, n_fb = sleeve_loss_frac(names, gross, sigmas, k=k, fallback=fallback)
    avg = (frac / (k * gross)) if gross > 0 else 0.0
    eq = float(equity)
    out = {"label": label, "equity_usd": eq, "n_names": len(names), "gross": gross,
           "weight_each": (gross / len(names)) if names else 0.0, "k_sigma": k,
           "avg_daily_sigma": avg, "k_sigma_frac": frac, "k_sigma_usd": -frac * eq,
           "n_sigma_fallback": n_fb, "no_stop_ceiling_usd": -gross * eq}
    line = (f"{label}: {len(names)} x {out['weight_each']:.2%} = {gross:.0%} gross; "
            f"rho=1 {k:g}-sigma day {gross:.0%} x {k:g} x {avg:.2%} = -${frac * eq:,.0f} "
            f"({frac:.2%} of ${eq:,.0f})")
    if history and "worst_window_return" in history:
        out["worst_21_session_usd"] = gross * history["worst_window_return"] * eq
        out["worst_day_usd"] = gross * history["worst_day_return"] * eq
        line += (f"; basket's worst {history['window_sessions']}-session return "
                 f"{history['worst_window_return']:.2%} (to {history['worst_window_end']}) = "
                 f"-${abs(out['worst_21_session_usd']):,.0f}; worst day "
                 f"{history['worst_day_return']:.2%} ({history['worst_day']}) = "
                 f"-${abs(out['worst_day_usd']):,.0f}")
    out["history"] = history
    out["line"] = line
    return out
