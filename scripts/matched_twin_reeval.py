"""CH-11: the leading (and the worst) paper books against N same-band random twins.

    python -m scripts.matched_twin_reeval --out <dir>                 # newest book_dna pair
    python -m scripts.matched_twin_reeval --out <dir> --run-id 2026-11-11T000105Z --n-twins 1000

Licence: PRODUCT_EXPERIMENT, descriptive. Reads receipts, ledgers and bars from
disk only; no broker, no network, no LLM. Writes ONE receipt
`<out>/matched_twin_reeval_<run>_<stamp>.json` and nothing else.

Why it exists. `book_dna.evidence_label` awards REPLICATED when a book beats ONE
random twin draw. One draw is not a distribution: this script reconstructs each
book's holdings from its own ledger and draws N twins at three levels, which
decomposes the excess over SPY into additive pieces:

    book - SPY = cash        ((1-c) SPY - SPY: the book's cash in this window)
               + panel       (random live stocks, same weights, minus cash-matched SPY)
               + band        (same liquidity band  - panel)
               + sector      (same band AND sector - same band)
               + selection   (the book             - same band AND sector)

Every piece is printed with a block-counted SE and the MDE beside it, by hold
month, leave-one-month-out (every window here is under a year), the bet-count
curve, and the sessions a selection effect of the observed size would need
before it could clear its MDE. Books whose holdings history is not on disk
(website lanes live on Railway) get a regression-only decomposition and the
twin columns say CANNOT DETERMINE with the reason.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config  # noqa: E402

SCHEMA = "matched_twin_reeval/1"
LEVELS = ("panel", "band", "band_sector")
CASH = "CASH"
FAMILIES_LLM = ("llm_portfolio:personal", "llm_portfolio:lib")


def _cfg(name: str, default: Any) -> Any:
    return getattr(_config, name, default)


def params() -> dict:
    return {
        "n_twins": int(_cfg("MATCHED_TWIN_REEVAL_N_TWINS", 1000)),
        "seed": int(_cfg("MATCHED_TWIN_REEVAL_SEED", 20261112)),
        "block_sessions": int(_cfg("MATCHED_TWIN_REEVAL_BLOCK_SESSIONS", 5)),
        "alpha": float(_cfg("MATCHED_TWIN_REEVAL_ALPHA", 0.05)),
        "power": float(_cfg("MATCHED_TWIN_REEVAL_POWER", 0.80)),
        "lookback_days": int(_cfg("MATCHED_TWIN_REEVAL_LOOKBACK_DAYS", 140)),
        "max_recon_gap_pp": float(_cfg("MATCHED_TWIN_REEVAL_MAX_RECON_GAP_PP", 1.0)),
    }


# ───────────────────────────── statistics (pure) ────────────────────────────

def block_sums(x: np.ndarray, block: int) -> np.ndarray:
    """Consecutive date blocks of `block` sessions; a short tail is its own block."""
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return np.array([])
    idx = np.arange(len(x)) // max(1, int(block))
    return np.bincount(idx, weights=x)


def block_se(x: np.ndarray, block: int) -> tuple[Optional[float], int]:
    """SE of the SUM of `x`, counted on date blocks, never on rows."""
    s = block_sums(x, block)
    nb = len(s)
    if nb < 2:
        return None, nb
    return float(np.std(s, ddof=1) * math.sqrt(nb)), nb


def mde(se: Optional[float], n_blocks: int, alpha: float = 0.05, power: float = 0.80) -> Optional[float]:
    """Minimum detectable effect of a sum: (t_{1-a/2} + t_{power}) x SE on n_blocks-1 df."""
    if se is None or n_blocks < 2:
        return None
    df = max(1, n_blocks - 1)
    try:
        from scipy import stats
        k = float(stats.t.ppf(1 - alpha / 2, df) + stats.t.ppf(power, df))
    except ImportError:                                   # pragma: no cover
        k = 1.959964 + 0.841621
    return float(k * se)


def xs_mde(twin_returns: np.ndarray, alpha: float = 0.05, power: float = 0.80) -> Optional[float]:
    """Cross-sectional MDE: a book is ONE draw, the twins are its null."""
    t = np.asarray(twin_returns, dtype=float)
    t = t[np.isfinite(t)]
    if len(t) < 10:
        return None
    from statistics import NormalDist
    z = NormalDist().inv_cdf(1 - alpha / 2) + NormalDist().inv_cdf(power)
    return float(z * np.std(t, ddof=1))


def sessions_needed(effect: Optional[float], mde_now: Optional[float], sessions: int) -> Optional[int]:
    """Sessions at which an effect that keeps its per-session size clears its MDE.

    The effect grows ~T, the MDE ~sqrt(T): clears when T' >= T (MDE/effect)^2."""
    if effect is None or mde_now is None or sessions <= 0 or effect == 0:
        return None
    return int(math.ceil(sessions * (mde_now / abs(effect)) ** 2))


def percentile_of(x: float, arr: np.ndarray) -> Optional[float]:
    a = np.asarray(arr, dtype=float)
    a = a[np.isfinite(a)]
    if len(a) == 0 or not np.isfinite(x):
        return None
    return float(((a < x).sum() + 0.5 * (a == x).sum()) / len(a))


def ols_beta(r: np.ndarray, m: np.ndarray) -> dict:
    r, m = np.asarray(r, float), np.asarray(m, float)
    ok = np.isfinite(r) & np.isfinite(m)
    r, m = r[ok], m[ok]
    n = len(r)
    if n < 10 or np.var(m) == 0:
        return {"beta": None, "se": None, "n": n}
    X = np.column_stack([np.ones(n), m])
    coef, *_ = np.linalg.lstsq(X, r, rcond=None)
    resid = r - X @ coef
    s2 = float(resid @ resid) / max(1, n - 2)
    cov = s2 * np.linalg.inv(X.T @ X)
    return {"beta": float(coef[1]), "se": float(math.sqrt(cov[1, 1])), "alpha_daily": float(coef[0]), "n": n}


def by_month(dates: list[str], diff: np.ndarray) -> dict:
    out: dict = {}
    for d, x in zip(dates, diff):
        out[str(d)[:7]] = out.get(str(d)[:7], 0.0) + float(x)
    return {k: round(v * 100, 3) for k, v in sorted(out.items())}


def leave_one_month_out(dates: list[str], diff: np.ndarray) -> dict:
    tot = float(np.sum(diff))
    bm = by_month(dates, diff)
    return {k: round(tot * 100 - v, 3) for k, v in bm.items()}


def bet_count_curve(book_contrib: dict, twin_contrib: dict) -> dict:
    """Selection per slot = book slot P&L - mean twin P&L in the same slot; the
    curve removes the top contributors one at a time."""
    sel = {k: float(book_contrib.get(k, 0.0)) - float(twin_contrib.get(k, 0.0))
           for k in set(book_contrib) | set(twin_contrib)}
    order = sorted(sel, key=lambda k: -sel[k])
    tot = sum(sel.values())
    curve = [{"removed": 0, "name": None, "remaining_pp": round(tot * 100, 3)}]
    run = tot
    k_zero = 0 if tot <= 0 else None
    for i, k in enumerate(order, 1):
        run -= sel[k]
        curve.append({"removed": i, "name": k, "remaining_pp": round(run * 100, 3)})
        if k_zero is None and run <= 0:
            k_zero = i
    pos = sum(v for v in sel.values() if v > 0)
    top = order[0] if order else None
    return {
        "selection_by_slot_pp": {k: round(sel[k] * 100, 3) for k in order},
        "curve": curve[:min(len(curve), 16)],
        "names_until_selection_le_zero": k_zero,
        "n_slots": len(sel),
        "top1": top, "top1_share_of_positive": (round(sel[top] / pos, 3) if top and pos > 0 else None),
    }


# ───────────────────────────── prices (wide arrays) ─────────────────────────

class Panel:
    """Wide close/open arrays over a session calendar (SPY's dates).

    Close is forward-filled after a name's last bar: a name that dies is held at
    its last close (no delisting return), stated on the receipt."""

    def __init__(self, bars: pd.DataFrame, calendar: Optional[list[str]] = None):
        b = bars[["symbol", "date", "open", "close"]].copy()
        b["date"] = pd.to_datetime(b["date"]).dt.strftime("%Y-%m-%d")
        b = b.drop_duplicates(["symbol", "date"], keep="first")
        close = b.pivot(index="date", columns="symbol", values="close").sort_index()
        opn = b.pivot(index="date", columns="symbol", values="open").sort_index()
        if calendar is None:
            calendar = list(close["SPY"].dropna().index) if "SPY" in close.columns else list(close.index)
        close = close.reindex(calendar)
        opn = opn.reindex(calendar)
        self.last_real = {s: (close[s].last_valid_index()) for s in close.columns}
        self.first_real = {s: (close[s].first_valid_index()) for s in close.columns}
        self.dates = list(calendar)
        self.row = {d: i for i, d in enumerate(self.dates)}
        self.syms = list(close.columns)
        self.col = {s: j for j, s in enumerate(self.syms)}
        self.close = close.ffill().to_numpy(dtype=float)
        o = opn.to_numpy(dtype=float)
        prev_close = np.vstack([np.full((1, o.shape[1]), np.nan), self.close[:-1]])
        self.open = np.where(np.isfinite(o), o, prev_close)

    def session_on_or_after(self, d: str) -> Optional[int]:
        d = str(d)[:10]
        for i, x in enumerate(self.dates):
            if x >= d:
                return i
        return None

    def session_on_or_before(self, d: str) -> Optional[int]:
        d = str(d)[:10]
        best = None
        for i, x in enumerate(self.dates):
            if x <= d:
                best = i
        return best

    def has(self, s: str) -> bool:
        return s in self.col


def simulate(decisions: list[dict], panel: Panel, end_row: int, rt_bps: Callable[[str], float]) -> dict:
    """Mark a sequence of decisions to the session closes up to `end_row`.

    decisions: [{"fill_row": i, "price": "open"|"close", "weights": {slot: (sym, w)}}].
    Each decision is filled at that session's open (or close); between decisions
    the shares are held (weights drift). Costs: half the round trip on every
    traded dollar, and the exit half on the final mark. Returns the NAV path at
    each close from the first fill row to `end_row`, starting from 1.0 before
    the first fill, plus the P&L by slot."""
    first = decisions[0]["fill_row"]
    nrow = end_row - first + 1
    nav = np.full(nrow, np.nan)
    cash = 1.0
    shares: dict = {}          # slot -> (sym, n_shares)
    pnl: dict = {}
    cost_total = 0.0
    unpriced: list = []
    for k, dec in enumerate(decisions):
        r0 = dec["fill_row"]
        r1 = decisions[k + 1]["fill_row"] if k + 1 < len(decisions) else end_row
        px_arr = panel.open if dec.get("price", "open") == "open" else panel.close
        # value at the fill price
        v = cash
        cur_dollar: dict = {}
        for slot, (sym, n) in shares.items():
            p = px_arr[r0, panel.col[sym]]
            p = p if np.isfinite(p) else panel.close[r0 - 1, panel.col[sym]] if r0 > 0 else np.nan
            dv = n * p if np.isfinite(p) else 0.0
            cur_dollar[sym] = cur_dollar.get(sym, 0.0) + dv
            v += dv
        # P&L of the previous spell up to this fill
        # (recorded when the spell started; settled here)
        target: dict = {}
        for slot, (sym, w) in dec["weights"].items():
            if not panel.has(sym):
                unpriced.append(sym)
                continue
            p = px_arr[r0, panel.col[sym]]
            if not np.isfinite(p) or p <= 0:
                unpriced.append(sym)
                continue
            target[slot] = (sym, w, p)
        tgt_dollar: dict = {}
        for slot, (sym, w, p) in target.items():
            tgt_dollar[sym] = tgt_dollar.get(sym, 0.0) + w * v
        cost = 0.0
        for sym in set(cur_dollar) | set(tgt_dollar):
            cost += abs(tgt_dollar.get(sym, 0.0) - cur_dollar.get(sym, 0.0)) * rt_bps(sym) / 2e4
        cost_total += cost
        v_after = v - cost
        new_shares = {}
        invested = 0.0
        for slot, (sym, w, p) in target.items():
            new_shares[slot] = (sym, w * v_after / p)
            invested += w * v_after
        cash = v_after - invested
        # path of this spell: closes r0..r1 (r1 inclusive only for the last spell)
        last = r1 if k + 1 == len(decisions) else r1 - 1
        rows = np.arange(r0, last + 1)
        val = np.full(len(rows), cash)
        for slot, (sym, n) in new_shares.items():
            c = panel.col[sym]
            path = panel.close[rows, c]
            p0 = px_arr[r0, c]
            val = val + n * path
            # P&L of this slot over the spell, to the next fill price (or the final close)
            if k + 1 < len(decisions):
                nxt = decisions[k + 1]
                pa = panel.open if nxt.get("price", "open") == "open" else panel.close
                pe = pa[r1, c]
                pe = pe if np.isfinite(pe) else panel.close[r1 - 1, c]
            else:
                pe = panel.close[end_row, c]
            pnl[slot] = pnl.get(slot, 0.0) + n * (pe - p0)
        nav[rows - first] = val
        shares = new_shares
    # exit half of the round trip on the final mark
    exit_cost = sum(n * panel.close[end_row, panel.col[sym]] * rt_bps(sym) / 2e4
                    for slot, (sym, n) in shares.items())
    cost_total += exit_cost
    nav[-1] -= exit_cost
    return {"nav": nav, "pnl": pnl, "cost": cost_total, "unpriced": sorted(set(unpriced))}


# ───────────────────────────── twin pools ────────────────────────────────────

class Pools:
    """Live names at an asof, indexed by liquidity band and sector."""

    def __init__(self, bars: pd.DataFrame, sector_of: dict, band_fn: Callable, live_fn: Callable):
        self.bars, self.sector_of = bars, sector_of
        self.band_fn, self.live_fn = band_fn, live_fn
        self._cache: dict = {}

    def at(self, asof: str) -> dict:
        if asof not in self._cache:
            bands = self.band_fn(self.bars, asof)
            live = self.live_fn(self.bars, asof)
            by_bs: dict = {}
            by_b: dict = {}
            for s in live:
                b = bands.get(s, "small")
                by_b.setdefault(b, []).append(s)
                sec = self.sector_of.get(s)
                if sec:
                    by_bs.setdefault((b, sec), []).append(s)
            self._cache[asof] = {"bands": bands, "live": list(live), "live_set": set(live),
                                 "by_band": by_b, "by_band_sector": by_bs}
        return self._cache[asof]


def _pick(cands: list, exclude: set, rng: np.random.Generator) -> Optional[str]:
    """Uniform over `cands` minus `exclude` (rejection first: exclusions are few)."""
    n = len(cands)
    if n == 0:
        return None
    if n > 4 * len(exclude):
        for _ in range(64):
            s = cands[int(rng.integers(n))]
            if s not in exclude:
                return str(s)
    c = [s for s in cands if s not in exclude]
    if not c:
        return None
    return str(c[int(rng.integers(len(c)))])


def draw_twin(decisions: list[dict], pools: Pools, level: str, rng: np.random.Generator,
              keep: Callable[[str], bool]) -> tuple[list[dict], dict]:
    """One twin: each stock slot replaced by a random live name matched at `level`
    on the decision's asof, SAME weight, same cash, same fill dates. A slot held
    across consecutive decisions keeps its replacement (sticky), so the twin's
    turnover is the book's. ETFs, index proxies and unpriced names are carried.

    Fallback when a cell is empty: band_sector -> band -> panel (counted)."""
    out = []
    prev: dict = {}
    fb = {"band_sector->band": 0, "band->panel": 0, "carried": 0, "drawn": 0}
    for dec in decisions:
        P = pools.at(dec["asof"])
        own = {sym for sym, _ in dec["weights"].values()}
        used: set = set()
        neww = {}
        for slot in sorted(dec["weights"]):
            sym, w = dec["weights"][slot]
            if keep(sym):
                neww[slot] = (sym, w)
                fb["carried"] += 1
                continue
            excl = own | used
            pick = None
            if slot in prev and prev[slot] in P["live_set"] and prev[slot] not in excl:
                pick = prev[slot]
            else:
                b = P["bands"].get(sym, "small")
                if level == "band_sector":
                    sec = pools.sector_of.get(sym)
                    pick = _pick(P["by_band_sector"].get((b, sec), []), excl, rng) if sec else None
                    if pick is None:
                        fb["band_sector->band"] += 1
                if level in ("band", "band_sector") and pick is None:
                    pick = _pick(P["by_band"].get(b, []), excl, rng)
                    if pick is None:
                        fb["band->panel"] += 1
                if pick is None:
                    pick = _pick(P["live"], excl, rng)
                fb["drawn"] += 1
            if pick is None:
                neww[slot] = (sym, w)
                fb["carried"] += 1
                continue
            used.add(pick)
            neww[slot] = (pick, w)
        prev = {slot: s for slot, (s, _) in neww.items()}
        out.append({**dec, "weights": neww})
    return out, fb


# ───────────────────────────── one book ──────────────────────────────────────

def nav_diff(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Per-session NAV-change difference; sums EXACTLY to the terminal gap (both start at 1)."""
    da = np.diff(np.concatenate([[1.0], a]))
    db = np.diff(np.concatenate([[1.0], b]))
    return da - db


def step_stats(dates: list[str], diff: np.ndarray, sessions: int, p: dict,
               xs_mde_value: Optional[float] = None) -> dict:
    tot = float(np.sum(diff))
    se, nb = block_se(diff, p["block_sessions"])
    m = mde(se, nb, p["alpha"], p["power"])
    binding = max([x for x in (m, xs_mde_value) if x is not None], default=None)

    def _v(x: Optional[float]) -> Optional[str]:
        if x is None:
            return None
        return "CANNOT DISTINGUISH" if abs(tot) < x else "CLEARS"
    return {
        "pp": round(tot * 100, 3),
        "block_se_pp": None if se is None else round(se * 100, 3),
        "n_blocks": nb,
        "mde_pp": None if m is None else round(m * 100, 3),
        "xs_mde_pp": None if xs_mde_value is None else round(xs_mde_value * 100, 3),
        "t": None if not se else round(tot / se, 2),
        "verdict_time_series": _v(m),
        "verdict_cross_section": _v(xs_mde_value),
        "verdict": ("CANNOT DISTINGUISH" if binding is None or abs(tot) < binding
                    else "CLEARS EVERY MDE PRINTED"),
        "by_hold_month_pp": by_month(dates, diff),
        "leave_one_month_out_pp": leave_one_month_out(dates, diff),
        "sessions_needed_to_clear_mde": sessions_needed(tot, binding, sessions),
    }


def evaluate_book(decisions: list[dict], panel: Panel, pools: Pools, *, end_row: int,
                  rt_bps: Callable[[str], float], keep: Callable[[str], bool],
                  n_twins: int, seed: int, p: dict) -> dict:
    """The full decomposition for one book whose decisions are reconstructed."""
    first = decisions[0]["fill_row"]
    dates = panel.dates[first:end_row + 1]
    sessions = len(dates)
    book = simulate(decisions, panel, end_row, rt_bps)
    spy_dec = [{**d, "weights": {"SPY": ("SPY", 1.0)}} for d in decisions[:1]]
    spy = simulate(spy_dec, panel, end_row, lambda s: 0.0)
    cash_dec = [{**d, "weights": {"SPY": ("SPY", sum(w for _, w in d["weights"].values()))}}
                for d in decisions]
    cash_spy = simulate(cash_dec, panel, end_row, lambda s: 0.0)
    levels: dict = {}
    mean_paths: dict = {}
    for li, level in enumerate(LEVELS):
        rng = np.random.default_rng([seed, li])
        terms, paths = [], []
        slot_pnl: dict = {}
        fb_tot: dict = {}
        for _ in range(n_twins):
            tw, fb = draw_twin(decisions, pools, level, rng, keep)
            for k, v in fb.items():
                fb_tot[k] = fb_tot.get(k, 0) + v
            s = simulate(tw, panel, end_row, rt_bps)
            terms.append(s["nav"][-1] - 1.0)
            paths.append(s["nav"])
            for k, v in s["pnl"].items():
                slot_pnl[k] = slot_pnl.get(k, 0.0) + v / n_twins
        terms_a = np.array(terms)
        mean_paths[level] = np.nanmean(np.vstack(paths), axis=0)
        levels[level] = {
            "mean_pct": round(float(np.mean(terms_a)) * 100, 3),
            "sd_pct": round(float(np.std(terms_a, ddof=1)) * 100, 3),
            "p05_pct": round(float(np.percentile(terms_a, 5)) * 100, 3),
            "p95_pct": round(float(np.percentile(terms_a, 95)) * 100, 3),
            "book_percentile": percentile_of(book["nav"][-1] - 1.0, terms_a),
            "share_twins_beating_spy": round(float((terms_a > spy["nav"][-1] - 1.0).mean()), 3),
            "fallbacks": fb_tot,
            "_terms": terms_a, "_slot_pnl": slot_pnl,
        }
    chain_paths = [("cash", spy["nav"], cash_spy["nav"]),
                   ("panel", cash_spy["nav"], mean_paths["panel"]),
                   ("band", mean_paths["panel"], mean_paths["band"]),
                   ("sector", mean_paths["band"], mean_paths["band_sector"]),
                   ("selection", mean_paths["band_sector"], book["nav"])]
    chain = {}
    for name, a, b in chain_paths:
        xs = xs_mde(levels["band_sector"]["_terms"], p["alpha"], p["power"]) if name == "selection" else None
        chain[name] = step_stats(dates, nav_diff(b, a), sessions, p, xs)
    # beta of the book and of the band_sector twin mean on SPY, daily
    r_book = np.diff(np.concatenate([[1.0], book["nav"]])) / np.concatenate([[1.0], book["nav"][:-1]])
    r_spy = np.diff(np.concatenate([[1.0], spy["nav"]])) / np.concatenate([[1.0], spy["nav"][:-1]])
    r_tw = (np.diff(np.concatenate([[1.0], mean_paths["band_sector"]]))
            / np.concatenate([[1.0], mean_paths["band_sector"][:-1]]))
    bb = ols_beta(r_book[1:], r_spy[1:])
    bt = ols_beta(r_tw[1:], r_spy[1:])
    spy_ret = float(spy["nav"][-1] - 1.0)
    beta_line = None
    if bb["beta"] is not None:
        beta_line = {"book_beta": round(bb["beta"], 3), "book_beta_se": round(bb["se"], 3), "n_days": bb["n"],
                     "twin_band_sector_beta": None if bt["beta"] is None else round(bt["beta"], 3),
                     "beta_explained_excess_pp": round((bb["beta"] - 1.0) * spy_ret * 100, 3),
                     "beta_explained_se_pp": round(bb["se"] * abs(spy_ret) * 100, 3),
                     "note": "(beta-1) x SPY over the window: what a beta-matched SPY+cash book would have "
                             "out- or under-performed by; overlaps the cash/panel/band steps, not additive"}
    book_contrib = {k: v for k, v in book["pnl"].items()}
    curve = bet_count_curve(book_contrib, levels["band_sector"]["_slot_pnl"])
    for lv in levels.values():
        lv.pop("_terms")
        lv.pop("_slot_pnl")
    names = sorted({s for d in decisions for s, _ in d["weights"].values()})
    carried_w = sum(w for _, (s, w) in decisions[0]["weights"].items() if keep(s))
    return {
        "sessions": sessions, "first_fill": dates[0], "last_mark": dates[-1],
        "n_decisions": len(decisions), "n_distinct_names": len(names),
        "first_decision_cash": round(1.0 - sum(w for _, w in decisions[0]["weights"].values()), 4),
        "first_decision_weight_carried_into_twins": round(carried_w, 4),
        "unpriced_in_book": book["unpriced"],
        "book_reconstructed_pct": round(float(book["nav"][-1] - 1.0) * 100, 3),
        "book_cost_pct": round(book["cost"] * 100, 3),
        "spy_pct": round(spy_ret * 100, 3),
        "cash_matched_spy_pct": round(float(cash_spy["nav"][-1] - 1.0) * 100, 3),
        "excess_vs_spy_reconstructed_pp": round(float(book["nav"][-1] - spy["nav"][-1]) * 100, 3),
        "twins": levels,
        "decomposition_pp": chain,
        "decomposition_sums_to_pp": round(sum(c["pp"] for c in chain.values()), 3),
        "beta": beta_line,
        "bet_count_curve": curve,
    }


# ───────────────────────────── regression-only (lanes) ───────────────────────

def lane_regression(series: list[tuple], p: dict) -> dict:
    """[(date, r_lane, r_spy)] -> beta, the beta-matched gap with its SE and MDE."""
    if len(series) < 10:
        return {"status": "CANNOT DETERMINE", "why": f"{len(series)} daily points (< 10)"}
    dates = [d for d, _, _ in series]
    r = np.array([x for _, x, _ in series], float)
    m = np.array([y for _, _, y in series], float)
    b = ols_beta(r, m)
    beta = b["beta"]
    resid = r - beta * m                                 # cash at zero rate
    st = step_stats(dates, resid, len(dates), p)
    lane_ret = float(np.prod(1 + r) - 1)
    spy_ret = float(np.prod(1 + m) - 1)
    bm = float(np.prod(1 + beta * m) - 1)
    return {"status": "OK", "n_days": b["n"], "beta": round(beta, 3), "beta_se": round(b["se"], 3),
            "lane_pct": round(lane_ret * 100, 3), "spy_pct": round(spy_ret * 100, 3),
            "beta_matched_spy_plus_cash_pct": round(bm * 100, 3),
            "low_beta_part_pp": round((bm - spy_ret) * 100, 3),
            "beyond_beta_pp": round((lane_ret - bm) * 100, 3),
            "beyond_beta_daily_sum": st}


# ───────────────────────────── loaders (disk) ────────────────────────────────

def sha256_of(p: Path, limit: int = 1 << 30) -> Optional[str]:
    if not p.exists():
        return None
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def file_info(p: Path) -> dict:
    return {"path": str(p), "exists": p.exists(),
            "bytes": p.stat().st_size if p.exists() else None,
            "sha256": sha256_of(p)}


def read_bars(paths: list[Path], start: str, extra_symbols: Iterable[str] = (),
              extra_path: Optional[Path] = None) -> pd.DataFrame:
    cols = ["symbol", "date", "open", "close", "volume"]
    frames = []
    for p in paths:
        df = pd.read_parquet(p, columns=cols, filters=[("date", ">=", pd.Timestamp(start))])
        frames.append(df)
    if extra_path is not None and extra_path.exists():
        want = sorted(set(extra_symbols))
        if want:
            g = pd.read_parquet(extra_path, columns=cols,
                                filters=[("date", ">=", pd.Timestamp(start)), ("symbol", "in", want)])
            frames.append(g)
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    out = out.drop_duplicates(["symbol", "date"], keep="first")
    return out.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)


def llm_decisions(rec: dict, inception: str) -> tuple[list[dict], str]:
    pos = rec.get("positions") or []
    w = {p["ticker"]: (p["ticker"], float(p["weight"])) for p in pos if p.get("ticker") != CASH}
    return ([{"asof": str(rec["asof"])[:10], "fill_date": str(inception)[:10], "price": "open",
              "weights": w}], "llm_portfolio/books.jsonl frozen entry weights; fill at the inception open")


def night_decisions(conn: sqlite3.Connection, book_id: str) -> list[dict]:
    rows = conn.execute("SELECT asof_date, weights_json FROM paper_book_decisions WHERE book_id=? "
                        "ORDER BY asof_date", (book_id,)).fetchall()
    out = []
    for asof, wj in rows:
        w = json.loads(wj) or {}
        # book_cadence: "A decision is taken AT THE CLOSE of `asof` and executed at that close."
        out.append({"asof": str(asof)[:10], "fill_date": str(asof)[:10], "price": "close",
                    "weights": {s: (s, float(x)) for s, x in w.items() if s != CASH and float(x) > 0}})
    return out


def fleet_decisions(snapshots: list[tuple[str, dict]], role: str,
                    session_of: Callable[[str], Optional[str]]) -> list[dict]:
    """Alpaca fleet: EOD broker snapshots -> one decision per session whose NAME
    SET changed (weights = market value / equity at that close). Trades between
    two snapshots are invisible; the receipt prints the reconstruction gap."""
    by_session: dict = {}
    for stamp, d in snapshots:
        for a in d.get("accounts") or []:
            if a.get("role") != role or a.get("equity") in (None, 0):
                continue
            sess = session_of(stamp)
            if sess is None:
                continue
            eq = float(a["equity"])
            w = {}
            for q in a.get("positions") or []:
                mv = float(q.get("market_value") or 0.0)
                if q.get("symbol") and mv > 0:
                    w[str(q["symbol"])] = w.get(str(q["symbol"]), 0.0) + mv / eq
            by_session[sess] = (w, eq)
    out, prev = [], None
    for sess in sorted(by_session):
        w, eq = by_session[sess]
        names = frozenset(w)
        if prev is None or names != prev:
            out.append({"asof": sess, "fill_date": sess, "price": "close",
                        "weights": {k: (k, v) for k, v in w.items()}, "equity": eq})
            prev = names
    if out:
        out[-1]["last_equity"] = by_session[sorted(by_session)[-1]][1]
    return out


def _stamp_iso(name: str) -> str:
    """'fleet_20261002T124304Z' -> '2026-10-02T12:43:04+00:00'."""
    t = name.split("_")[-1].replace(".json", "")
    return f"{t[0:4]}-{t[4:6]}-{t[6:8]}T{t[9:11]}:{t[11:13]}:{t[13:15]}+00:00"


def _copy_db(db: Path, tmp: Path) -> Path:
    dst = tmp / db.name
    shutil.copy2(db, dst)
    for suf in ("-wal", "-shm"):
        s = Path(str(db) + suf)
        if s.exists():
            shutil.copy2(s, Path(str(dst) + suf))
    return dst


def count_files(folder: Path) -> int:
    return sum(1 for _ in folder.rglob("*")) if folder.exists() else 0


# ───────────────────────────── main ──────────────────────────────────────────

def run(*, run_id: Optional[str], pa_dir: Path, db_path: Path, out_dir: Path, n_twins: int,
        seed: int, only: Optional[set] = None, log: Callable = print) -> dict:
    from backend.services import book_dna as BD
    from backend.services import llm_portfolio as LP
    from backend.services import xs_ranker as XR
    p = params()
    p["n_twins"], p["seed"] = n_twins, seed
    if run_id is None:
        cands = sorted(pa_dir.glob("book_dna_*.json"))
        if not cands:
            raise SystemExit(f"REFUSED: no book_dna_*.json in {pa_dir}")
        run_id = cands[-1].stem.replace("book_dna_", "")
    dna_p = pa_dir / f"book_dna_{run_id}.json"
    roi_p = pa_dir / f"roi_{run_id}.json"
    rv_p = pa_dir / f"results_voice_{run_id}.json"
    for f in (dna_p, roi_p):
        if not f.exists():
            raise SystemExit(f"REFUSED: {f} missing")
    dna = json.loads(dna_p.read_text(encoding="utf-8"))
    roi = json.loads(roi_p.read_text(encoding="utf-8"))
    rv = json.loads(rv_p.read_text(encoding="utf-8")) if rv_p.exists() else {}
    strat = [b for b in dna["books"] if b.get("category") == "strategy"]
    if only:
        strat = [b for b in strat if b["account"] in only]
    leaders = [r["account"] for r in rv.get("leaders") or []]
    losers = [r["account"] for r in rv.get("losers") or []]
    llm_dir = BD.LLM_DIR
    books_p = llm_dir / "books.jsonl"
    recs = {r.get("book_id"): r for r in BD._read_jsonl(books_p)}
    tmp = Path(tempfile.mkdtemp(prefix="ch11_db_"))
    conn = sqlite3.connect(str(_copy_db(db_path, tmp))) if db_path.exists() else None
    # earliest asof among reconstructable books
    plans: list[tuple[dict, list[dict], str]] = []
    fleet_snaps: Optional[list] = None
    results: dict = {}
    for b in strat:
        fam, acct = b.get("family"), b["account"]
        if fam in FAMILIES_LLM:
            rec = recs.get(b.get("book_id"))
            if rec is None:
                results[acct] = {"status": "CANNOT DETERMINE", "why": f"book_id {b.get('book_id')} not in books.jsonl"}
                continue
            decs, src = llm_decisions(rec, b.get("inception") or rec["asof"])
            plans.append((b, decs, src))
        elif fam == "night_books":
            if conn is None:
                results[acct] = {"status": "CANNOT DETERMINE", "why": f"no db at {db_path}"}
                continue
            decs = night_decisions(conn, b.get("book_id"))
            if not decs:
                results[acct] = {
                    "status": "NO_POSITIONS",
                    "why": "paper_book_decisions holds no decision for this book: it has been all cash since "
                           "inception, so its excess over SPY is exactly minus SPY's return (no selection to test)",
                    "excess_pp": b.get("excess_pp"), "spy_leg_pct": b.get("spy_leg_pct"),
                    "return_pct": b.get("return_pct"), "sessions": b.get("sessions_graded")}
                continue
            plans.append((b, decs, "aegis_pi.db paper_book_decisions (copied; filled at the asof close, as book_cadence does)"))
        elif fam == "website_lane":
            series = BD._lane_series(roi, acct)
            results[acct] = {"status": "TWINS CANNOT DETERMINE",
                             "why": "a lane's holdings history lives on the Railway deploy (GET /api/pi/lane/*) and "
                                    "this run makes no network call; the local aegis_pi.db stops at 2026-09-11 and "
                                    "does not carry conservative-atr; 21 of its ETF holdings are unpriced locally",
                             "regression_on_spy": lane_regression(series, p),
                             "excess_pp": b.get("excess_pp"), "sessions": b.get("sessions_graded"),
                             "cash_fraction": (b.get("cash_fraction") or {}).get("value"),
                             "book_dna_beta": (b.get("beta_vs_spy") or {}).get("value")}
        elif fam == "alpaca_fleet":
            if fleet_snaps is None:
                fleet_snaps = []
                for f in sorted((pa_dir / "fleet_daily").glob("fleet_*.json")):
                    try:
                        fleet_snaps.append((_stamp_iso(f.stem), json.loads(f.read_text(encoding="utf-8"))))
                    except (OSError, ValueError):
                        continue
            decs = fleet_decisions(fleet_snaps, acct, BD._session_date_of_stamp)
            if not any(d["weights"] for d in decs):
                results[acct] = {"status": "CANNOT DETERMINE",
                                 "why": "no fleet_daily snapshot carries a position for this role",
                                 "excess_pp": b.get("excess_pp"), "sessions": b.get("sessions_graded")}
                continue
            plans.append((b, decs, "fleet_daily EOD snapshots (PARTIAL WINDOW: from the first snapshot, "
                                   "2026-09-29; holdings between snapshots invisible)"))
        else:
            results[acct] = {"status": "CANNOT DETERMINE",
                             "why": f"family {fam}: no holdings-history adapter on disk "
                                    "(murat_book / pc_paper are not reconstructed by this script)",
                             "excess_pp": b.get("excess_pp"), "sessions": b.get("sessions_graded"),
                             "book_dna_beta": (b.get("beta_vs_spy") or {}).get("value")}
    if conn is not None:
        conn.close()
    shutil.rmtree(tmp, ignore_errors=True)
    if not plans:
        raise SystemExit("REFUSED: no book could be reconstructed")
    start = (pd.Timestamp(min(d["asof"] for _, ds, _ in plans for d in ds))
             - pd.Timedelta(days=p["lookback_days"])).strftime("%Y-%m-%d")
    paths = XR.survivorship_free_paths()
    gb = llm_dir / "global_bars.parquet"
    extra = {s for _, ds, _ in plans for d in ds for s, _ in d["weights"].values()} | {"SPY"}
    log(f"reading bars from {start}: {[str(x) for x in paths]} + global_bars for {len(extra)} book names")
    bars = read_bars(paths, start, extra, gb)
    surv = XR.survivorship_audit(bars)
    log(f"bars: {len(bars):,} rows, {bars['symbol'].nunique():,} symbols; {surv['verdict'][:90]}")
    panel = Panel(bars)
    sector_of, sector_src = BD.load_sector_map()
    band_cache: dict = {}

    def band_fn(bars_: pd.DataFrame, asof: str) -> dict:
        return LP.liquidity_bands(bars_, asof=asof)

    def live_fn(bars_: pd.DataFrame, asof: str) -> list:
        return LP._live_pool(bars_, asof, set())

    pools = Pools(bars, sector_of, band_fn, live_fn)

    def keep(sym: str) -> bool:
        return sym in XR.INDEX_PROXIES or LP.is_etf(sym) or sym == CASH or not panel.has(sym)

    for b, decs, src in plans:
        acct = b["account"]
        # band per asof for the cost of each name
        for d in decs:
            d["fill_row"] = (panel.session_on_or_after(d["fill_date"]) if "fill_date" in d
                             else (lambda i: None if i is None else i + 1)(panel.session_on_or_before(d["fill_after"])))
        decs = [d for d in decs if d["fill_row"] is not None]
        end_row = panel.session_on_or_before(b.get("last_mark") or panel.dates[-1])
        if not decs or end_row is None or decs[0]["fill_row"] > end_row:
            results[acct] = {"status": "CANNOT DETERMINE", "why": "no fill session inside the panel window"}
            continue
        decs = [d for d in decs if d["fill_row"] <= end_row]
        asof0 = decs[0]["asof"]
        if asof0 not in band_cache:
            band_cache[asof0] = pools.at(asof0)["bands"]
        bands0 = band_cache[asof0]

        def rt_bps(sym: str, _b=bands0) -> float:
            if sym in XR.INDEX_PROXIES or LP.is_etf(sym):
                return XR.COST_BPS_BY_BAND["mega"]
            return XR.COST_BPS_BY_BAND.get(_b.get(sym, "small"), XR.COST_BPS_BY_BAND["small"])

        log(f"  {acct[:50]:<50} decisions={len(decs)} names={len({s for d in decs for s, _ in d['weights'].values()})}")
        ev = evaluate_book(decs, panel, pools, end_row=end_row, rt_bps=rt_bps, keep=keep,
                           n_twins=n_twins, seed=seed + (int(hashlib.sha256(acct.encode()).hexdigest()[:6], 16)),
                           p=p)
        ref = b.get("return_pct")
        ref_src = "book_dna return_pct (inception -> last mark)"
        if decs[0].get("equity") and decs[-1].get("last_equity"):
            ref = round((decs[-1]["last_equity"] / decs[0]["equity"] - 1.0) * 100, 3)
            ref_src = "broker equity, first snapshot -> last snapshot (the partial window evaluated)"
        gap = None if ref is None else round(ev["book_reconstructed_pct"] - ref, 3)
        ev.update({"status": "OK", "holdings_source": src, "family": b.get("family"),
                   "receipt_return_pct": b.get("return_pct"), "receipt_excess_pp": b.get("excess_pp"),
                   "receipt_label": (b.get("evidence") or {}).get("label"),
                   "receipt_single_twin": b.get("fair_twin"),
                   "recon_reference_pct": ref, "recon_reference": ref_src,
                   "recon_gap_pp": gap,
                   "recon_flag": (None if gap is None or abs(gap) <= p["max_recon_gap_pp"] else "RECON_GAP")})
        results[acct] = ev
    # cross-book view of selection percentiles (same window: NOT independent)
    pct = {a: r["twins"]["band_sector"]["book_percentile"] for a, r in results.items()
           if r.get("status") == "OK" and r.get("family") in FAMILIES_LLM}
    vals = [v for v in pct.values() if v is not None]
    cross = {"n_books": len(vals),
             "n_at_or_above_p95": sum(v >= 0.95 for v in vals),
             "n_at_or_below_p05": sum(v <= 0.05 for v in vals),
             "expected_each_tail_if_no_skill": round(0.05 * len(vals), 2),
             "mean_percentile": None if not vals else round(float(np.mean(vals)), 3),
             "note": "every llm_portfolio book shares the window 2026-09-28 -> last mark, so the books are "
                     "not independent draws; this is a description, not a test"}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    receipt = {
        "schema": SCHEMA, "licence": "PRODUCT_EXPERIMENT (descriptive; paper books; no skill claim)",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_id": run_id, "params": p,
        "variants_tried": {"twin_levels": list(LEVELS), "cost_models": 1,
                           "note": "three twin constructions, each reported; none selected after the fact; "
                                   "seed fixed per book from the run seed and the account name"},
        "inputs": {"book_dna": file_info(dna_p), "roi": file_info(roi_p), "results_voice": file_info(rv_p),
                   "llm_books": file_info(books_p), "aegis_pi_db": file_info(db_path),
                   "bars": [file_info(x) for x in paths], "global_bars": file_info(gb),
                   "bars_window_start": start, "bars_rows_read": int(len(bars)),
                   "bars_symbols": int(bars["symbol"].nunique()), "panel_last_session": panel.dates[-1],
                   "sector_map": sector_src},
        "survivorship": {**surv, "note": "computed on the rows read (window start above); the living file holds "
                                         "names alive on 2026-09-01, bars_delisted the ones that died; a name "
                                         "that stops trading is held at its last close (no delisting return)"},
        "conventions": {"fill": "llm books at the inception open (book_dna's base); night books at the close of "
                                "the decision asof (book_cadence executes at that close); twins on the same fill rows",
                        "costs": "half of xs_ranker.COST_BPS_BY_BAND round trip per traded dollar, exit half "
                                 "on the final mark; ETFs/index at the mega band; SPY legs gross (as the receipt)",
                        "carried_into_twins": "ETFs, index proxies, CASH and names absent from the bars panel",
                        "sector": "potential_universe identity.sector (industry level); a name without a sector "
                                  "falls back to its band",
                        "decomposition": "cash + panel + band + sector + selection = book - SPY, exactly, on "
                                         "NAV changes",
                        "by_month": "keyed on the HOLD month (the session the NAV change happened), not the "
                                    "decision date; leave-one-month-out because every window is under a year"},
        "leaders": leaders, "losers": losers,
        "cross_book_selection_percentiles": {**cross, "by_book": pct},
        "books": results,
        "claim_line": "CLAIMS PROMOTED: none",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"matched_twin_reeval_{run_id}_{stamp}.json"
    tmpf = out.with_suffix(".json.tmp")
    tmpf.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    json.loads(tmpf.read_text(encoding="utf-8"))
    tmpf.replace(out)
    receipt["_path"] = str(out)
    return receipt


def headline(receipt: dict) -> list[str]:
    lines = []
    for acct in (receipt.get("leaders") or []) + (receipt.get("losers") or []):
        r = receipt["books"].get(acct)
        if r is None:
            lines.append(f"{acct}: not a strategy row in this run")
            continue
        if r.get("status") != "OK":
            lines.append(f"{acct}: {r['status']} — {r.get('why', '')[:140]}")
            continue
        d = r["decomposition_pp"]
        sel = d["selection"]
        lines.append(
            f"{acct}: book {r['book_reconstructed_pct']:+.2f}% vs SPY {r['spy_pct']:+.2f}% "
            f"= {r['excess_vs_spy_reconstructed_pp']:+.2f} pp = cash {d['cash']['pp']:+.2f} + panel "
            f"{d['panel']['pp']:+.2f} + band {d['band']['pp']:+.2f} + sector {d['sector']['pp']:+.2f} + "
            f"selection {sel['pp']:+.2f} (MDE {sel['mde_pp']} ts / {sel['xs_mde_pp']} xs, "
            f"pctile {r['twins']['band_sector']['book_percentile']}) -> ts {sel['verdict_time_series']}, "
            f"xs {sel['verdict_cross_section']}")
    lines.append(receipt["claim_line"])
    return lines


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="matched_twin_reeval")
    ap.add_argument("--out", required=True, help="output directory (never the live data folder)")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--pa-dir", default=None, help="paper_accounts folder (default: book_dna.PA_DIR)")
    ap.add_argument("--db", default=None, help="aegis_pi.db (copied before reading)")
    ap.add_argument("--n-twins", type=int, default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--books", default=None, help="comma-separated accounts (default: every strategy row)")
    a = ap.parse_args(argv)
    from backend.services import book_dna as BD
    p = params()
    pa = Path(a.pa_dir) if a.pa_dir else BD.PA_DIR
    db = Path(a.db) if a.db else Path(_config.OPTIMUS_LEDGER_DIR).parent / "aegis_pi.db"
    out = Path(a.out)
    if out.resolve().is_relative_to(Path(_config.OPTIMUS_LEDGER_DIR).resolve()):
        print("REFUSED: --out is inside the live data folder")
        return 2
    n_before = count_files(pa)
    rec = run(run_id=a.run_id, pa_dir=pa, db_path=db, out_dir=out,
              n_twins=a.n_twins or p["n_twins"], seed=a.seed if a.seed is not None else p["seed"],
              only=set(a.books.split(",")) if a.books else None)
    n_after = count_files(pa)
    print("\n".join(headline(rec)))
    print(f"wrote {rec['_path']}; live paper_accounts file count {n_before} -> {n_after}")
    if n_after != n_before:
        print("REFUSED: the live folder changed during the run")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
