"""CH-11: every paper strategy book against >= 500 same-band random twins, on one ruler.

    python -m scripts.matched_twin_reeval --data-root C:/Users/mrthn/aegis-finance/backend/data/optimus \
        --out <dir>                                  # newest roi_<run> + book_dna_<run> pair
    python -m scripts.matched_twin_reeval --data-root <optimus> --out <dir> --run-id 2026-11-11T235431Z

Licence: PRODUCT_EXPERIMENT, descriptive. Reads receipts, ledgers and bars from
disk only (a copy of aegis_pi.db, never the file itself); no broker, no network,
no LLM. Writes `<out>/matched_twin_reeval_<run>_<stamp>.json` and `.md`, nothing
else, and refuses an `--out` inside the data root's parent.

What it answers. `book_dna.evidence_label` awards REPLICATED when a book beats ONE
random twin draw. One draw is not a distribution. For every strategy account of
the roi file (collapsed into distinct bets at holdings Jaccard >= 0.8, as
`results_voice` does) whose holdings history is on disk, this script rebuilds
the book from its own ledger and draws N twins: the same number of names, the
same weights, the same cash, the same decision and fill sessions, the same cost
model, each name replaced by a random LIVE name of the same liquidity band x
volatility tercile, measured on bars strictly BEFORE the decision date. Three
twin levels are printed (panel, band, band_sector); the verdict is read at the
band level, sector-matched twins are printed beside it.

Per book: return, SPY over the same window (raw line beside excess), the twin
distribution (median, p05, p95, the book's percentile), excess over the twin
median with a t on DATE BLOCKS and the MDE beside it at every block origin, by
month / by year, leave-one-month-out worst case, top-5 dates and names share of
the P&L, the curve of the result as the top contributors are removed, a pairwise
table of books (holdings Jaccard and daily-excess correlation), and one verdict
word from VERDICTS with its scope.

Panel caveat printed on the receipt: `prices_2025_26` holds names alive when it
was built (survivor-selected); dead names are absent from the twin pool, which
LIFTS the twins. A BEATS verdict is conservative under that bias; a LAGS or
BAND_EFFECT verdict is not.
"""
from __future__ import annotations

import argparse
import bisect
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

SCHEMA = "matched_twin_reeval/2"
LEVELS = ("panel", "band", "band_sector")
PRIMARY_LEVEL = "band"
CASH = "CASH"
FAMILIES_LLM = ("llm_portfolio:personal", "llm_portfolio:lib", "llm_portfolio:competition")
VERDICTS = ("BEATS_TWINS_IN_SCOPE", "CANNOT_DISTINGUISH", "BAND_EFFECT", "LAGS_TWINS_IN_SCOPE")
NOT_EVALUATED = "NOT_EVALUATED"
INDEX_PROXIES = frozenset({"SPY", "QQQ", "IWM", "RSP", "DIA", "VTI", "VOO"})


class Refused(RuntimeError):
    """A required input is missing or unusable; main() turns this into rc 2."""


def _cfg(name: str, default: Any) -> Any:
    return getattr(_config, name, default)


def params() -> dict:
    return {
        "n_twins": int(_cfg("MATCHED_TWIN_REEVAL_N_TWINS", 1000)),
        "min_twins": int(_cfg("MATCHED_TWIN_REEVAL_MIN_TWINS", 500)),
        "seed": int(_cfg("MATCHED_TWIN_REEVAL_SEED", 20261112)),
        "block_sessions": int(_cfg("MATCHED_TWIN_REEVAL_BLOCK_SESSIONS", 5)),
        "alpha": float(_cfg("MATCHED_TWIN_REEVAL_ALPHA", 0.05)),
        "power": float(_cfg("MATCHED_TWIN_REEVAL_POWER", 0.80)),
        "lookback_days": int(_cfg("MATCHED_TWIN_REEVAL_LOOKBACK_DAYS", 140)),
        "band_window": int(_cfg("MATCHED_TWIN_REEVAL_BAND_WINDOW", 63)),
        "live_days": int(_cfg("MATCHED_TWIN_REEVAL_LIVE_DAYS", 10)),
        "min_price": float(_cfg("MATCHED_TWIN_REEVAL_MIN_PRICE", 3.0)),
        "bet_jaccard": float(_cfg("MATCHED_TWIN_REEVAL_BET_JACCARD", 0.8)),
        "max_recon_gap_pp": float(_cfg("MATCHED_TWIN_REEVAL_MAX_RECON_GAP_PP", 1.0)),
        "cost_bps_by_band": dict(_cfg("MATCHED_TWIN_REEVAL_COST_BPS",
                                      {"mega": 6.0, "large": 10.0, "mid": 18.0, "small": 35.0})),
    }


def liquidity_band(median_dollar_vol: Optional[float]) -> str:
    """The same cut-offs as `xs_ranker.liquidity_band` (kept local: no import cost in tests)."""
    if median_dollar_vol is None or not np.isfinite(median_dollar_vol):
        return "small"
    if median_dollar_vol >= 1e9:
        return "mega"
    if median_dollar_vol >= 1e8:
        return "large"
    if median_dollar_vol >= 2e7:
        return "mid"
    return "small"


def is_etf(sym: str) -> bool:
    try:
        from backend.services import llm_portfolio as LP
        return bool(LP.is_etf(sym))
    except Exception:                                    # pragma: no cover - import failure
        return False


# ───────────────────────────── statistics (pure) ────────────────────────────

def block_sums(x: np.ndarray, block: int, origin: int = 0) -> np.ndarray:
    """Consecutive date blocks of `block` sessions. `origin` o>0 makes the first
    block o sessions long, so every origin 0..block-1 is a different cut."""
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return np.array([])
    b = max(1, int(block))
    shift = (b - int(origin) % b) % b
    idx = (np.arange(len(x)) + shift) // b
    return np.bincount(idx, weights=x)


def t_crit(df: int, alpha: float, power: Optional[float] = None) -> float:
    try:
        from scipy import stats
        k = float(stats.t.ppf(1 - alpha / 2, df))
        if power is not None:
            k += float(stats.t.ppf(power, df))
        return k
    except ImportError:                                   # pragma: no cover
        return 1.959964 + (0.841621 if power is not None else 0.0)


def block_test(x: np.ndarray, block: int, origin: int, alpha: float, power: float) -> dict:
    """t of the SUM of `x` on date blocks (never rows), with its MDE beside it."""
    s = block_sums(x, block, origin)
    nb = len(s)
    tot = float(np.sum(x))
    if nb < 3:
        return {"origin": origin, "n_blocks": nb, "sum": tot, "se": None, "t": None, "mde": None,
                "t_crit": None, "why": f"{nb} blocks (< 3): no t"}
    sd = float(np.std(s, ddof=1))
    se = sd * math.sqrt(nb)
    t = tot / se if se > 0 else None
    return {"origin": origin, "n_blocks": nb, "sum": tot, "se": se, "t": t,
            "mde": t_crit(nb - 1, alpha, power) * se, "t_crit": t_crit(nb - 1, alpha)}


def origin_sweep(x: np.ndarray, block: int, alpha: float, power: float) -> list[dict]:
    return [block_test(x, block, o, alpha, power) for o in range(max(1, int(block)))]


def xs_mde(twin_returns: np.ndarray, alpha: float = 0.05, power: float = 0.80) -> Optional[float]:
    """Cross-sectional MDE: the book is ONE draw, the twins are its null."""
    t = np.asarray(twin_returns, dtype=float)
    t = t[np.isfinite(t)]
    if len(t) < 10:
        return None
    from statistics import NormalDist
    z = NormalDist().inv_cdf(1 - alpha / 2) + NormalDist().inv_cdf(power)
    return float(z * np.std(t, ddof=1))


def percentile_of(x: float, arr: np.ndarray) -> Optional[float]:
    a = np.asarray(arr, dtype=float)
    a = a[np.isfinite(a)]
    if len(a) == 0 or not np.isfinite(x):
        return None
    return float(((a < x).sum() + 0.5 * (a == x).sum()) / len(a))


def sessions_needed(effect: Optional[float], mde_now: Optional[float], sessions: int) -> Optional[int]:
    """Sessions at which an effect that keeps its per-session size clears its MDE
    (effect ~T, MDE ~sqrt(T): clears when T' >= T (MDE/effect)^2)."""
    if effect is None or mde_now is None or sessions <= 0 or effect == 0:
        return None
    return int(math.ceil(sessions * (mde_now / abs(effect)) ** 2))


def by_period(dates: list[str], x: np.ndarray, n_chars: int) -> dict:
    out: dict = {}
    for d, v in zip(dates, x):
        k = str(d)[:n_chars]
        out[k] = out.get(k, 0.0) + float(v)
    return {k: round(v * 100, 3) for k, v in sorted(out.items())}


def leave_one_out(dates: list[str], x: np.ndarray, n_chars: int) -> dict:
    tot = float(np.sum(x)) * 100
    per = by_period(dates, x, n_chars)
    loo = {k: round(tot - v, 3) for k, v in per.items()}
    worst = min(loo.items(), key=lambda kv: kv[1]) if loo else (None, None)
    return {"by_period_dropped_pp": loo, "worst_dropped": worst[0], "worst_pp": worst[1],
            "n_periods": len(per)}


def top_share(items: dict, total: float, k: int = 5) -> dict:
    """Top-k items by value and their share of the total (signed; > 1 means the rest lost)."""
    order = sorted(items.items(), key=lambda kv: -kv[1])[:k]
    s = sum(v for _, v in order)
    return {"top": [{"key": a, "pp": round(v * 100, 3)} for a, v in order],
            "top_sum_pp": round(s * 100, 3), "total_pp": round(total * 100, 3),
            "share_of_total": (round(s / total, 3) if abs(total) > 1e-12 else None)}


def removal_curve(book_contrib: dict, twin_contrib: dict, max_points: int = 16) -> dict:
    """The excess over the twins as a function of the number of names kept:
    selection per slot = book slot P&L - mean twin P&L in the same slot, and the
    curve removes the largest contributors one at a time."""
    sel = {k: float(book_contrib.get(k, 0.0)) - float(twin_contrib.get(k, 0.0))
           for k in set(book_contrib) | set(twin_contrib)}
    order = sorted(sel, key=lambda k: (-sel[k], k))
    tot = sum(sel.values())
    curve = [{"removed": 0, "name": None, "names_left": len(sel), "remaining_pp": round(tot * 100, 3)}]
    run = tot
    k_zero = 0 if tot <= 0 else None
    for i, k in enumerate(order, 1):
        run -= sel[k]
        curve.append({"removed": i, "name": k, "names_left": len(sel) - i, "remaining_pp": round(run * 100, 3)})
        if k_zero is None and run <= 0:
            k_zero = i
    return {"selection_by_name_pp": {k: round(sel[k] * 100, 3) for k in order},
            "curve": curve[:max_points], "names_removed_until_excess_le_zero": k_zero, "n_names": len(sel)}


def verdict_of(sweep: list[dict], pctile: Optional[float], book_vs_spy: float, twin_med_vs_spy: float,
               alpha: float) -> tuple[str, str]:
    """One word. BEATS/LAGS only when EVERY block origin clears t_crit in the same
    direction AND the book sits in the matching tail of the twin distribution."""
    ok = [s for s in sweep if s.get("t") is not None]
    if len(ok) == len(sweep) and ok:
        if all(s["t"] >= s["t_crit"] for s in ok) and pctile is not None and pctile >= 1 - alpha / 2:
            return "BEATS_TWINS_IN_SCOPE", (f"t >= t_crit at all {len(ok)} block origins and the book is at "
                                            f"percentile {pctile:.3f} of its twins")
        if all(s["t"] <= -s["t_crit"] for s in ok) and pctile is not None and pctile <= alpha / 2:
            return "LAGS_TWINS_IN_SCOPE", (f"t <= -t_crit at all {len(ok)} block origins and the book is at "
                                           f"percentile {pctile:.3f} of its twins")
    in_tail = pctile is not None and (pctile >= 1 - alpha / 2 or pctile <= alpha / 2)
    if not ok:
        why = "too few date blocks for a t"
    elif any(abs(s["t"]) >= s["t_crit"] for s in ok):
        why = "the t clears at some block origins but not all (or the percentile does not agree)"
    else:
        why = "the t is inside t_crit at every block origin"
    if in_tail:
        why += f"; the book is in a {alpha / 2:.1%} tail of its twins (percentile {pctile:.3f}) but the time-series test does not agree"
    if book_vs_spy > 0 and twin_med_vs_spy > 0 and not in_tail:
        return "BAND_EFFECT", f"book and twin median both above SPY and the book is inside its twins' distribution; {why}"
    return "CANNOT_DISTINGUISH", why


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
        self.dates = list(calendar)
        self.syms = list(close.columns)
        self.col = {s: j for j, s in enumerate(self.syms)}
        self.close = close.ffill().to_numpy(dtype=float)
        o = opn.to_numpy(dtype=float)
        prev_close = np.vstack([np.full((1, o.shape[1]), np.nan), self.close[:-1]])
        self.open = np.where(np.isfinite(o), o, prev_close)

    def session_on_or_after(self, d: str) -> Optional[int]:
        i = bisect.bisect_left(self.dates, str(d)[:10])
        return i if i < len(self.dates) else None

    def session_on_or_before(self, d: str) -> Optional[int]:
        i = bisect.bisect_right(self.dates, str(d)[:10]) - 1
        return i if i >= 0 else None

    def has(self, s: str) -> bool:
        return s in self.col


def simulate(decisions: list[dict], panel: Panel, end_row: int, rt_bps: Callable[[str], float]) -> dict:
    """Mark a sequence of decisions to the session closes up to `end_row`.

    decisions: [{"fill_row": i, "price": "open"|"close", "weights": {slot: (sym, w)}}].
    Each decision is filled at that session's open (or close); between decisions
    the shares are held (weights drift). Costs: half the round trip on every
    traded dollar, and the exit half on the final mark. Returns the NAV at each
    close from the first fill row to `end_row` (1.0 before the first fill), the
    P&L by slot, and the names that could not be priced (left as cash)."""
    first = decisions[0]["fill_row"]
    nav = np.full(end_row - first + 1, np.nan)
    cash = 1.0
    shares: dict = {}
    pnl: dict = {}
    cost_total = 0.0
    unpriced: list = []
    for k, dec in enumerate(decisions):
        r0 = dec["fill_row"]
        r1 = decisions[k + 1]["fill_row"] if k + 1 < len(decisions) else end_row
        px_arr = panel.open if dec.get("price", "open") == "open" else panel.close
        v = cash
        cur_dollar: dict = {}
        for slot, (sym, n) in shares.items():
            p = px_arr[r0, panel.col[sym]]
            if not np.isfinite(p) and r0 > 0:
                p = panel.close[r0 - 1, panel.col[sym]]
            dv = n * p if np.isfinite(p) else 0.0
            cur_dollar[sym] = cur_dollar.get(sym, 0.0) + dv
            v += dv
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
        cost = sum(abs(tgt_dollar.get(s, 0.0) - cur_dollar.get(s, 0.0)) * rt_bps(s) / 2e4
                   for s in set(cur_dollar) | set(tgt_dollar))
        cost_total += cost
        v_after = v - cost
        new_shares = {}
        invested = 0.0
        for slot, (sym, w, p) in target.items():
            new_shares[slot] = (sym, w * v_after / p)
            invested += w * v_after
        cash = v_after - invested
        last = r1 if k + 1 == len(decisions) else r1 - 1
        rows = np.arange(r0, last + 1)
        val = np.full(len(rows), cash)
        for slot, (sym, n) in new_shares.items():
            c = panel.col[sym]
            p0 = px_arr[r0, c]
            if len(rows):
                val = val + n * panel.close[rows, c]
            if k + 1 < len(decisions):
                pa = panel.open if decisions[k + 1].get("price", "open") == "open" else panel.close
                pe = pa[r1, c]
                pe = pe if np.isfinite(pe) else panel.close[r1 - 1, c]
            else:
                pe = panel.close[end_row, c]
            pnl[slot] = pnl.get(slot, 0.0) + n * (pe - p0)
        if len(rows):
            nav[rows - first] = val
        shares = new_shares
    exit_cost = sum(n * panel.close[end_row, panel.col[sym]] * rt_bps(sym) / 2e4
                    for slot, (sym, n) in shares.items())
    cost_total += exit_cost
    nav[-1] -= exit_cost
    return {"nav": nav, "pnl": pnl, "cost": cost_total, "unpriced": sorted(set(unpriced))}


# ───────────────────────────── twin pools (strictly before asof) ─────────────

class Pools:
    """Live names at an asof, keyed by liquidity band x volatility tercile and by
    sector, computed ONLY from bars dated strictly before the asof."""

    def __init__(self, bars: pd.DataFrame, sector_of: dict, p: dict):
        b = bars[["symbol", "date", "close", "volume"]].copy()
        b["date"] = pd.to_datetime(b["date"])
        self.bars = b.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)
        self.sector_of = sector_of
        self.p = p
        self._cache: dict = {}

    def at(self, asof: str) -> dict:
        asof = str(asof)[:10]
        if asof in self._cache:
            return self._cache[asof]
        a = pd.Timestamp(asof)
        b = self.bars[self.bars["date"] < a]
        bands: dict = {}
        live: list = []
        latest_bar = None
        if not b.empty:
            latest_bar = str(b["date"].max().date())
            w = b.groupby("symbol", sort=False).tail(self.p["band_window"])
            mdv = (w["close"] * w["volume"]).groupby(w["symbol"]).median()
            ret = w.groupby("symbol", sort=False)["close"].pct_change(fill_method=None)
            vol = ret.groupby(w["symbol"]).std()
            nret = ret.groupby(w["symbol"]).count()
            liq = {s: liquidity_band(float(v)) for s, v in mdv.items()}
            vt: dict = {}
            for band in set(liq.values()):
                members = [s for s, x in liq.items() if x == band and nret.get(s, 0) >= 20
                           and np.isfinite(vol.get(s, np.nan))]
                if len(members) >= 3:
                    q = np.quantile([vol[s] for s in members], [1 / 3, 2 / 3])
                    for s in members:
                        vt[s] = "v1" if vol[s] <= q[0] else ("v2" if vol[s] <= q[1] else "v3")
            bands = {s: f"{liq[s]}|{vt.get(s, 'v?')}" for s in liq}
            last = b.groupby("symbol", sort=False).tail(1)
            ok = last[(last["date"] >= a - pd.Timedelta(days=self.p["live_days"]))
                      & (last["close"] >= self.p["min_price"])]
            live = sorted(s for s in ok["symbol"] if s not in INDEX_PROXIES and s != CASH and not is_etf(s))
        by_b: dict = {}
        by_bs: dict = {}
        for s in live:
            bd = bands.get(s, "small|v?")
            by_b.setdefault(bd, []).append(s)
            sec = self.sector_of.get(s)
            if sec:
                by_bs.setdefault((bd, sec), []).append(s)
        out = {"asof": asof, "latest_bar_used": latest_bar, "bands": bands, "live": live,
               "live_set": set(live), "by_band": by_b, "by_band_sector": by_bs}
        self._cache[asof] = out
        return out


def _pick(cands: list, exclude: set, rng: np.random.Generator) -> Optional[str]:
    n = len(cands)
    if n == 0:
        return None
    if n > 4 * len(exclude):
        for _ in range(64):
            s = cands[int(rng.integers(n))]
            if s not in exclude:
                return str(s)
    c = [s for s in cands if s not in exclude]
    return str(c[int(rng.integers(len(c)))]) if c else None


def draw_twin(decisions: list[dict], pools: Pools, level: str, rng: np.random.Generator,
              keep: Callable[[str], bool]) -> tuple[list[dict], dict]:
    """One twin: each stock slot replaced by a random live name matched at `level`
    on the decision's asof (bars strictly before it), SAME weight, same cash, same
    fill sessions. A slot held across consecutive decisions keeps its replacement
    (sticky), so the twin's turnover is the book's. ETFs, index proxies, CASH and
    names absent from the panel are carried unchanged (counted).

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
                bd = P["bands"].get(sym, "small|v?")
                if level == "band_sector":
                    sec = pools.sector_of.get(sym)
                    pick = _pick(P["by_band_sector"].get((bd, sec), []), excl, rng) if sec else None
                    if pick is None:
                        fb["band_sector->band"] += 1
                if level in ("band", "band_sector") and pick is None:
                    pick = _pick(P["by_band"].get(bd, []), excl, rng)
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
    """Per-session NAV-change difference a - b; sums EXACTLY to the terminal gap (both start at 1)."""
    return np.diff(np.concatenate([[1.0], a])) - np.diff(np.concatenate([[1.0], b]))


def daily_returns(nav: np.ndarray) -> np.ndarray:
    prev = np.concatenate([[1.0], nav[:-1]])
    return np.diff(np.concatenate([[1.0], nav])) / prev


def _round(x: Optional[float], k: int = 3, scale: float = 100.0) -> Optional[float]:
    return None if x is None or not np.isfinite(x) else round(float(x) * scale, k)


def _sweep_view(sweep: list[dict]) -> list[dict]:
    return [{"origin": s["origin"], "n_blocks": s["n_blocks"], "t": None if s["t"] is None else round(s["t"], 2),
             "t_crit": None if s["t_crit"] is None else round(s["t_crit"], 2),
             "mde_pp": _round(s["mde"]), "se_pp": _round(s["se"])} for s in sweep]


def evaluate_book(decisions: list[dict], panel: Panel, pools: Pools, *, end_row: int,
                  rt_bps: Callable[[str], float], keep: Callable[[str], bool],
                  n_twins: int, seed: int, p: dict) -> dict:
    """The full comparison for one book whose decisions are reconstructed."""
    first = decisions[0]["fill_row"]
    dates = panel.dates[first:end_row + 1]
    sessions = len(dates)
    book = simulate(decisions, panel, end_row, rt_bps)
    spy = simulate([{**decisions[0], "weights": {"SPY": ("SPY", 1.0)}}], panel, end_row, lambda s: 0.0)
    cash_spy = simulate([{**d, "weights": {"SPY": ("SPY", sum(w for _, w in d["weights"].values()))}}
                         for d in decisions], panel, end_row, lambda s: 0.0)
    book_ret = float(book["nav"][-1] - 1.0)
    spy_ret = float(spy["nav"][-1] - 1.0)
    levels: dict = {}
    med_paths: dict = {}
    mean_paths: dict = {}
    slot_means: dict = {}
    for li, level in enumerate(LEVELS):
        rng = np.random.default_rng([int(seed), li])
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
            # P&L keyed by SLOT (the book's own name), so twin and book compare slot by slot
            for k, v in s["pnl"].items():
                slot_pnl[k] = slot_pnl.get(k, 0.0) + v / n_twins
        ta = np.array(terms)
        P = np.vstack(paths)
        med_paths[level] = np.median(P, axis=0)
        mean_paths[level] = np.mean(P, axis=0)
        slot_means[level] = slot_pnl
        med = float(np.median(ta))
        levels[level] = {
            "n_twins": int(n_twins),
            "median_pct": _round(med), "mean_pct": _round(float(np.mean(ta))),
            "sd_pct": _round(float(np.std(ta, ddof=1)) if n_twins > 1 else None),
            "p05_pct": _round(float(np.percentile(ta, 5))), "p95_pct": _round(float(np.percentile(ta, 95))),
            "book_percentile": percentile_of(book_ret, ta),
            "excess_over_twin_median_pp": _round(book_ret - med),
            "twin_median_vs_spy_pp": _round(med - spy_ret),
            "share_twins_beating_spy": round(float((ta > spy_ret).mean()), 3),
            "xs_mde_pp": _round(xs_mde(ta, p["alpha"], p["power"])),
            "fallbacks": fb_tot,
        }
    # time-series test on the primary level: book minus the twins' median path
    out_levels: dict = {}
    for level in LEVELS:
        diff = nav_diff(book["nav"], med_paths[level])
        sweep = origin_sweep(diff, p["block_sessions"], p["alpha"], p["power"])
        word, why = verdict_of(sweep, levels[level]["book_percentile"], book_ret - spy_ret,
                               float(med_paths[level][-1] - spy["nav"][-1]), p["alpha"])
        mdes = [s["mde"] for s in sweep if s["mde"] is not None]
        out_levels[level] = {**levels[level],
                             "ts_excess_over_median_path_pp": _round(float(np.sum(diff))),
                             "origin_sweep": _sweep_view(sweep),
                             "mde_pp_max_over_origins": _round(max(mdes) if mdes else None),
                             "sessions_needed_to_clear_mde": sessions_needed(
                                 float(np.sum(diff)), max(mdes) if mdes else None, sessions),
                             "verdict": word, "verdict_why": why}
    prim = out_levels[PRIMARY_LEVEL]
    if not levels[PRIMARY_LEVEL]["fallbacks"].get("drawn"):
        for level in LEVELS:
            out_levels[level] = {**out_levels[level], "verdict": NOT_EVALUATED,
                                 "verdict_why": "every holding is an ETF, index proxy, CASH or a name absent from "
                                                "the panel, carried unchanged into the twins: no stock selection "
                                                "to compare"}
        prim = out_levels[PRIMARY_LEVEL]
    diff_p = nav_diff(book["nav"], med_paths[PRIMARY_LEVEL])
    book_daily_pnl = np.diff(np.concatenate([[1.0], book["nav"]]))
    chain_paths = [("cash", spy["nav"], cash_spy["nav"]),
                   ("panel", cash_spy["nav"], mean_paths["panel"]),
                   ("band", mean_paths["panel"], mean_paths["band"]),
                   ("sector", mean_paths["band"], mean_paths["band_sector"]),
                   ("selection", mean_paths["band_sector"], book["nav"])]
    chain = {name: _round(float(np.sum(nav_diff(b, a)))) for name, a, b in chain_paths}
    names = sorted({s for d in decisions for s, _ in d["weights"].values()})
    first_sw = prim["origin_sweep"][0]
    return {
        "sessions": sessions, "first_fill": dates[0], "last_mark": dates[-1],
        "n_decisions": len(decisions), "n_distinct_names": len(names), "names": names,
        "first_decision_cash": round(1.0 - sum(w for _, w in decisions[0]["weights"].values()), 4),
        "first_decision_weight_carried_into_twins": round(
            sum(w for _, (s, w) in decisions[0]["weights"].items() if keep(s)), 4),
        "unpriced_in_book": book["unpriced"],
        "book_pct": _round(book_ret), "book_cost_pct": _round(book["cost"]),
        "spy_pct": _round(spy_ret), "excess_vs_spy_pp": _round(book_ret - spy_ret),
        "cash_matched_spy_pct": _round(float(cash_spy["nav"][-1] - 1.0)),
        "twins": out_levels,
        "primary_level": PRIMARY_LEVEL,
        "verdict": prim["verdict"], "verdict_why": prim["verdict_why"],
        "headline_t_origin0": first_sw["t"], "headline_mde_pp_origin0": first_sw["mde_pp"],
        "headline_blocks": first_sw["n_blocks"],
        "excess_over_twin_median_by_month_pp": by_period(dates, diff_p, 7),
        "excess_over_twin_median_by_year_pp": by_period(dates, diff_p, 4),
        "leave_one_month_out": leave_one_out(dates, diff_p, 7),
        "leave_one_year_out": (leave_one_out(dates, diff_p, 4) if len({d[:4] for d in dates}) > 1
                               else {"why": "window inside one calendar year: leave-one-month-out is the LOO"}),
        "top5_dates_of_book_pnl": top_share(dict(zip(dates, book_daily_pnl)), float(np.sum(book_daily_pnl))),
        "top5_names_of_book_pnl": top_share(book["pnl"], float(sum(book["pnl"].values()))),
        "removal_curve_vs_twins": removal_curve(book["pnl"], slot_means[PRIMARY_LEVEL]),
        "decomposition_pp": {**chain, "sums_to_pp": _round(sum(v or 0 for v in chain.values()) / 100),
                             "note": "cash + panel + band + sector + selection = book - SPY, on NAV changes; "
                                     "twin MEAN paths (the median is not additive)"},
        "_daily": {"dates": list(dates), "book_ret": daily_returns(book["nav"]).tolist(),
                   "spy_ret": daily_returns(spy["nav"]).tolist()},
    }


# ───────────────────────────── regression-only (lanes) ───────────────────────

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
    return {"beta": float(coef[1]), "se": float(math.sqrt(cov[1, 1])), "n": n}


def lane_series(roi: dict, lane: str) -> list[tuple]:
    ls = roi.get("lane_nav_series") or {}
    pts = (ls.get("lanes") or {}).get(lane) or []
    spy = dict((d, v) for d, v in ls.get("spy_rebased_100k_at_2026_06_08") or [])
    pts = [(d, v) for d, v in pts if d in spy]
    out = []
    for i in range(1, len(pts)):
        d0, v0 = pts[i - 1]
        d1, v1 = pts[i]
        if v0 and spy[d0]:
            out.append((d1, v1 / v0 - 1, spy[d1] / spy[d0] - 1))
    return out


def lane_regression(series: list[tuple], p: dict) -> dict:
    if len(series) < 10:
        return {"status": "CANNOT DETERMINE", "why": f"{len(series)} daily points (< 10)"}
    r = np.array([x for _, x, _ in series], float)
    m = np.array([y for _, _, y in series], float)
    b = ols_beta(r, m)
    resid = r - b["beta"] * m
    sw = origin_sweep(resid, p["block_sessions"], p["alpha"], p["power"])
    lane_ret, spy_ret = float(np.prod(1 + r) - 1), float(np.prod(1 + m) - 1)
    bm = float(np.prod(1 + b["beta"] * m) - 1)
    return {"status": "OK", "n_days": b["n"], "beta": round(b["beta"], 3), "beta_se": round(b["se"], 3),
            "lane_pct": _round(lane_ret), "spy_pct": _round(spy_ret),
            "beta_matched_spy_plus_cash_pct": _round(bm), "low_beta_part_pp": _round(bm - spy_ret),
            "beyond_beta_pp": _round(lane_ret - bm), "beyond_beta_origin_sweep": _sweep_view(sw)}


# ───────────────────────────── pairwise + bets ───────────────────────────────

def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    a, b = set(a), set(b)
    u = a | b
    return len(a & b) / len(u) if u else 0.0


def cluster_bets(names: dict, thr: float) -> dict:
    """Connected components at holdings Jaccard >= thr (deterministic; results_voice's rule)."""
    accts = sorted(names)
    parent = {a: a for a in accts}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for i, a in enumerate(accts):
        for b in accts[i + 1:]:
            if names[a] and names[b] and jaccard(names[a], names[b]) >= thr:
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
    comps: dict = {}
    for a in accts:
        comps.setdefault(find(a), []).append(a)
    return {a: sorted(m) for m in comps.values() for a in m}


def pairwise(daily: dict, names: dict, min_common: int = 10) -> list[dict]:
    """daily: acct -> {date: excess return vs SPY}. One row per pair."""
    accts = sorted(daily)
    rows = []
    for i, a in enumerate(accts):
        for b in accts[i + 1:]:
            common = sorted(set(daily[a]) & set(daily[b]))
            corr = None
            if len(common) >= min_common:
                x = np.array([daily[a][d] for d in common])
                y = np.array([daily[b][d] for d in common])
                if np.std(x) > 0 and np.std(y) > 0:
                    corr = round(float(np.corrcoef(x, y)[0, 1]), 3)
            rows.append({"a": a, "b": b, "jaccard": round(jaccard(names.get(a, ()), names.get(b, ())), 3),
                         "n_common_days": len(common), "corr_daily_excess": corr})
    return rows


# ───────────────────────────── loaders (disk, read-only) ─────────────────────

def file_info(p: Path) -> dict:
    if not p.exists():
        return {"path": str(p), "exists": False}
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return {"path": str(p), "exists": True, "bytes": p.stat().st_size,
            "mtime_utc": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(timespec="seconds"),
            "sha256": h.hexdigest()}


def read_jsonl(p: Path) -> list[dict]:
    out = []
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def read_bars(paths: list[Path], start: str, extra_symbols: Iterable[str] = (),
              extra_path: Optional[Path] = None) -> pd.DataFrame:
    cols = ["symbol", "date", "open", "close", "volume"]
    frames = [pd.read_parquet(p, columns=cols, filters=[("date", ">=", pd.Timestamp(start))]) for p in paths]
    if extra_path is not None and extra_path.exists():
        want = sorted(set(extra_symbols))
        if want:
            frames.append(pd.read_parquet(extra_path, columns=cols,
                                          filters=[("date", ">=", pd.Timestamp(start)), ("symbol", "in", want)]))
    out = pd.concat(frames, ignore_index=True)
    d = pd.to_datetime(out["date"])
    if getattr(d.dt, "tz", None) is not None:
        d = d.dt.tz_localize(None)
    out["date"] = d
    out = out.drop_duplicates(["symbol", "date"], keep="first")
    return out.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)


def llm_decisions(rec: dict, inception: str) -> list[dict]:
    w = {p["ticker"]: (p["ticker"], float(p["weight"])) for p in rec.get("positions") or []
         if p.get("ticker") != CASH and float(p.get("weight") or 0) > 0}
    return [{"asof": str(rec["asof"])[:10], "fill_date": str(inception)[:10], "price": "open", "weights": w}]


def night_decisions(conn: sqlite3.Connection, book_id: str) -> list[dict]:
    rows = conn.execute("SELECT asof_date, weights_json FROM paper_book_decisions WHERE book_id=? "
                        "ORDER BY asof_date", (book_id,)).fetchall()
    out = []
    for asof, wj in rows:
        w = json.loads(wj) or {}
        # book_cadence: a decision is taken AT THE CLOSE of `asof` and executed at that close.
        out.append({"asof": str(asof)[:10], "fill_date": str(asof)[:10], "price": "close",
                    "weights": {s: (s, float(x)) for s, x in w.items() if s != CASH and float(x) > 0}})
    return out


def session_of_stamp(stamp: str) -> Optional[str]:
    """book_dna's rule: after 16:00 ET -> that day; before 09:30 ET -> the previous weekday; else None."""
    from backend.services import book_dna as BD
    return BD._session_date_of_stamp(stamp)


def fleet_decisions(snapshots: list[tuple[str, dict]], role: str) -> list[dict]:
    """Alpaca fleet: EOD broker snapshots -> one decision per session whose NAME
    SET changed (weights = market value / equity at that close). Trades between
    two snapshots are invisible; the receipt prints the reconstruction gap."""
    by_session: dict = {}
    for stamp, d in snapshots:
        for a in d.get("accounts") or []:
            if a.get("role") != role or not a.get("equity"):
                continue
            sess = session_of_stamp(stamp)
            if sess is None:
                continue
            eq = float(a["equity"])
            w: dict = {}
            for q in a.get("positions") or []:
                mv = float(q.get("market_value") or 0.0)
                if q.get("symbol") and mv > 0:
                    w[str(q["symbol"])] = w.get(str(q["symbol"]), 0.0) + mv / eq
            by_session[sess] = (w, eq)
    out, prev = [], None
    for sess in sorted(by_session):
        w, eq = by_session[sess]
        if prev is None or frozenset(w) != prev:
            # decided at the close of the PREVIOUS session; the pool uses bars before `sess`
            out.append({"asof": sess, "fill_date": sess, "fill_rule": "on_or_before", "price": "close",
                        "weights": {k: (k, v) for k, v in w.items()}, "equity": eq})
            prev = frozenset(w)
    if out:
        out[-1]["last_equity"] = by_session[sorted(by_session)[-1]][1]
    return out


def _stamp_iso(name: str) -> str:
    t = name.split("_")[-1].replace(".json", "")
    return f"{t[0:4]}-{t[4:6]}-{t[6:8]}T{t[9:11]}:{t[11:13]}:{t[13:15]}+00:00"


def count_files(folder: Path) -> int:
    return sum(1 for _ in folder.rglob("*")) if folder.exists() else 0


def strategy_accounting(roi: dict, dna: dict, markers: Iterable[str]) -> tuple[list[dict], list[dict]]:
    """results_voice's filter, row by row: (strategy rows, every other row with why)."""
    books = {str(b.get("account")): b for b in dna.get("books") or []}
    strategy, dropped = [], []
    for r in roi.get("rows") or []:
        a = str(r.get("account"))
        b = books.get(a) or {}
        if r.get("status") != "LIVE":
            dropped.append({"account": a, "family": r.get("family"), "why": f"roi status {r.get('status')}"})
            continue
        if r.get("vs_spy_pp") is None:
            dropped.append({"account": a, "family": r.get("family"),
                            "why": "roi row has no vs-SPY number (results_voice skips it)"})
            continue
        why = None
        if b.get("twin_of"):
            why = f"twin_of {b['twin_of']}"
        elif b.get("category") in ("twin", "control"):
            why = f"book_dna category {b['category']}"
        else:
            for m in markers:
                if m in a:
                    why = f"name contains {m!r}"
                    break
        if why:
            dropped.append({"account": a, "family": r.get("family"), "why": f"control/twin: {why}"})
        else:
            strategy.append(r)
    return strategy, dropped


# ───────────────────────────── main ──────────────────────────────────────────

def run(*, data_root: Path, out_dir: Path, run_id: Optional[str], n_twins: int, seed: int,
        only: Optional[set] = None, log: Callable = print) -> dict:
    p = params()
    p["n_twins"], p["seed"] = n_twins, seed
    if n_twins < p["min_twins"]:
        raise Refused(f"--n-twins {n_twins} < the floor {p['min_twins']} (a percentile needs >= 500 twins)")
    pa_dir = data_root / "paper_accounts"
    if not pa_dir.is_dir():
        raise Refused(f"no paper_accounts folder at {pa_dir}")
    if run_id is None:
        dna_ids = {x.stem.replace("book_dna_", "") for x in pa_dir.glob("book_dna_*.json")}
        roi_ids = {x.stem.replace("roi_", "") for x in pa_dir.glob("roi_*.json")}
        shared = sorted(dna_ids & roi_ids)
        if not shared:
            raise Refused(f"no roi_<run> + book_dna_<run> pair in {pa_dir}")
        run_id = shared[-1]
    dna_p, roi_p = pa_dir / f"book_dna_{run_id}.json", pa_dir / f"roi_{run_id}.json"
    for f in (dna_p, roi_p):
        if not f.exists():
            raise Refused(f"{f} missing")
    dna = json.loads(dna_p.read_text(encoding="utf-8"))
    roi = json.loads(roi_p.read_text(encoding="utf-8"))
    llm_dir = data_root / "llm_portfolio"
    books_p = llm_dir / "books.jsonl"
    db_path = data_root.parent / "aegis_pi.db"
    bars_paths = [x for x in (data_root / "prices_deep" / "bars.parquet",) if x.exists()] or \
        [data_root / "prices_2025_26" / "bars.parquet"]
    delisted = data_root / "prices_deep" / "bars_delisted.parquet"
    if delisted.exists():
        bars_paths.append(delisted)
    gb = llm_dir / "global_bars.parquet"
    for f in bars_paths:
        if not f.exists():
            raise Refused(f"bars panel {f} missing")
    markers = list(_cfg("RESULTS_VOICE_CONTROL_NAME_MARKERS", ("_random_twin", "comparato", "__", "-control")))
    strategy, dropped = strategy_accounting(roi, dna, markers)
    if not strategy:
        raise Refused("the roi file has no LIVE strategy row")
    dbooks = {str(b.get("account")): b for b in dna.get("books") or []}
    if only:
        strategy = [r for r in strategy if r["account"] in only]
    tickers = {r["account"]: frozenset((dbooks.get(r["account"]) or {}).get("tickers") or []) for r in strategy}
    bet_of = cluster_bets(tickers, p["bet_jaccard"])
    strategy.sort(key=lambda r: (-float(r["vs_spy_pp"]), str(r["account"])))
    leaders, seen = [], set()
    for r in strategy:
        bet = tuple(bet_of.get(r["account"], [r["account"]]))
        if bet not in seen:
            seen.add(bet)
            leaders.append(r["account"])
    recs = {r.get("book_id"): r for r in read_jsonl(books_p)}
    tmp = Path(tempfile.mkdtemp(prefix="ch11_db_"))
    conn = None
    if db_path.exists():
        dst = tmp / db_path.name
        shutil.copy2(db_path, dst)
        for suf in ("-wal", "-shm"):
            s = Path(str(db_path) + suf)
            if s.exists():
                shutil.copy2(s, Path(str(dst) + suf))
        conn = sqlite3.connect(str(dst))
    fleet_snaps: Optional[list] = None
    results: dict = {}
    plans: list = []
    for r in strategy:
        acct = r["account"]
        b = dbooks.get(acct) or {}
        fam = r.get("family") or b.get("family")
        base = {"family": fam, "roi_return_pct": r.get("roi_pct"), "roi_spy_pct": r.get("spy_same_window_pct"),
                "roi_vs_spy_pp": r.get("vs_spy_pp"), "inception": r.get("inception"),
                "last_mark": r.get("last_mark"), "bet_members": bet_of.get(acct, [acct]),
                "label": (b.get("evidence") or {}).get("label")}
        rep = bet_of.get(acct, [acct])
        if acct not in leaders:
            results[acct] = {**base, "status": NOT_EVALUATED, "verdict": NOT_EVALUATED,
                             "why": f"same bet as {[x for x in rep if x in leaders]} (holdings Jaccard >= "
                                    f"{p['bet_jaccard']}); the bet's best member is evaluated"}
            continue
        if fam in FAMILIES_LLM:
            rec = recs.get(b.get("book_id"))
            if rec is None:
                results[acct] = {**base, "status": NOT_EVALUATED, "verdict": NOT_EVALUATED,
                                 "why": f"book_id {b.get('book_id')} not in llm_portfolio/books.jsonl"}
                continue
            plans.append((acct, base, llm_decisions(rec, r.get("inception") or rec["asof"]),
                          "llm_portfolio/books.jsonl frozen entry weights; filled at the inception open"))
        elif fam == "night_books":
            decs = night_decisions(conn, b.get("book_id")) if conn is not None else []
            if not decs or not any(d["weights"] for d in decs):
                results[acct] = {**base, "status": NOT_EVALUATED, "verdict": NOT_EVALUATED,
                                 "why": "aegis_pi.db paper_book_decisions holds no position for this book (all "
                                        "cash since inception): no selection to compare"}
                continue
            plans.append((acct, base, decs, "aegis_pi.db paper_book_decisions (a copy), filled at the asof close"))
        elif fam == "alpaca_fleet":
            if fleet_snaps is None:
                fleet_snaps = []
                for f in sorted((pa_dir / "fleet_daily").glob("fleet_*.json")):
                    try:
                        fleet_snaps.append((_stamp_iso(f.stem), json.loads(f.read_text(encoding="utf-8"))))
                    except (OSError, ValueError, IndexError):
                        continue
            decs = fleet_decisions(fleet_snaps, acct)
            if not any(d["weights"] for d in decs):
                results[acct] = {**base, "status": NOT_EVALUATED, "verdict": NOT_EVALUATED,
                                 "why": "no fleet_daily snapshot carries a position for this role"}
                continue
            plans.append((acct, base, decs, "fleet_daily EOD broker snapshots (PARTIAL WINDOW from the first "
                                            "snapshot; trades between snapshots invisible)"))
        elif fam == "website_lane":
            results[acct] = {**base, "status": NOT_EVALUATED, "verdict": NOT_EVALUATED,
                             "why": "a lane's holdings history lives on the Railway deploy and this run makes no "
                                    "network call; the regression on SPY from the roi NAV series is printed",
                             "regression_on_spy": lane_regression(lane_series(roi, acct), p)}
        else:
            results[acct] = {**base, "status": NOT_EVALUATED, "verdict": NOT_EVALUATED,
                             "why": f"family {fam}: no holdings-history adapter on disk in this script"}
    if conn is not None:
        conn.close()
    shutil.rmtree(tmp, ignore_errors=True)
    if not plans:
        raise Refused("no strategy book could be reconstructed from disk")
    start = (pd.Timestamp(min(d["asof"] for _, _, ds, _ in plans for d in ds))
             - pd.Timedelta(days=p["lookback_days"])).strftime("%Y-%m-%d")
    extra = {s for _, _, ds, _ in plans for d in ds for s, _ in d["weights"].values()} | {"SPY"}
    log(f"reading bars from {start}: {[str(x) for x in bars_paths]} + global_bars for {len(extra)} book names")
    bars = read_bars(bars_paths, start, extra, gb)
    if "SPY" not in set(bars["symbol"]):
        raise Refused("SPY is not in the bars read: no calendar and no benchmark")
    from backend.services import xs_ranker as XR
    surv = XR.survivorship_audit(bars)
    log(f"bars: {len(bars):,} rows, {bars['symbol'].nunique():,} symbols, last {bars['date'].max().date()}; "
        f"{surv['verdict'][:90]}")
    panel = Panel(bars)
    sector_of, sector_src = load_sector_map(data_root / "potential_universe")
    pools = Pools(bars, sector_of, p)

    def keep(sym: str) -> bool:
        return sym in INDEX_PROXIES or is_etf(sym) or sym == CASH or not panel.has(sym)

    daily_excess: dict = {}
    names_of: dict = {}
    for acct, base, decs, src in plans:
        for d in decs:
            d["fill_row"] = (panel.session_on_or_before(d["fill_date"]) if d.get("fill_rule") == "on_or_before"
                             else panel.session_on_or_after(d["fill_date"]))
        decs = [d for d in decs if d["fill_row"] is not None]
        end_row = panel.session_on_or_before(base.get("last_mark") or panel.dates[-1])
        if not decs or end_row is None or decs[0]["fill_row"] > end_row:
            results[acct] = {**base, "status": NOT_EVALUATED, "verdict": NOT_EVALUATED,
                             "why": "no fill session inside the panel window"}
            continue
        decs = [d for d in decs if d["fill_row"] <= end_row]
        bands0 = pools.at(decs[0]["asof"])["bands"]

        def rt_bps(sym: str, _b=bands0) -> float:
            cb = p["cost_bps_by_band"]
            if sym in INDEX_PROXIES or is_etf(sym):
                return cb["mega"]
            return cb.get(_b.get(sym, "small|v?").split("|")[0], cb["small"])

        log(f"  {acct[:60]:<60} decisions={len(decs)}")
        acct_seed = seed + int(hashlib.sha256(acct.encode()).hexdigest()[:6], 16)
        ev = evaluate_book(decs, panel, pools, end_row=end_row, rt_bps=rt_bps, keep=keep,
                           n_twins=n_twins, seed=acct_seed, p=p)
        ref = base.get("roi_return_pct")
        ref_src = "roi roi_pct (inception -> last mark)"
        if decs[0].get("equity") and decs[-1].get("last_equity"):
            ref = round((decs[-1]["last_equity"] / decs[0]["equity"] - 1.0) * 100, 3)
            ref_src = "broker equity, first snapshot -> last snapshot (the partial window evaluated)"
        gap = None if ref is None or ev["book_pct"] is None else round(ev["book_pct"] - float(ref), 3)
        daily = ev.pop("_daily")
        daily_excess[acct] = {d: br - sr for d, br, sr in zip(daily["dates"], daily["book_ret"], daily["spy_ret"])}
        names_of[acct] = ev["names"]
        pool0 = pools.at(decs[0]["asof"])
        results[acct] = {**base, **ev, "status": "OK", "holdings_source": src, "seed": acct_seed,
                         "first_pool": {"asof": pool0["asof"], "latest_bar_used": pool0["latest_bar_used"],
                                        "n_live": len(pool0["live"])},
                         "recon_reference_pct": ref, "recon_reference": ref_src, "recon_gap_pp": gap,
                         "recon_flag": (None if gap is None or abs(gap) <= p["max_recon_gap_pp"] else "RECON_GAP")}
    for acct, r in results.items():
        if r.get("status") != "OK" and (r.get("regression_on_spy") or {}).get("status") == "OK":
            ser = lane_series(roi, acct)
            daily_excess[acct] = {d: x - m for d, x, m in ser}
            names_of[acct] = sorted(tickers.get(acct) or [])
    pairs = pairwise(daily_excess, names_of)
    cross = cross_book(results)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    counts: dict = {}
    for r in results.values():
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    receipt = {
        "schema": SCHEMA, "licence": "PRODUCT_EXPERIMENT (descriptive; paper books; no claim)",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_id": run_id, "params": p, "primary_level": PRIMARY_LEVEL,
        "variants_tried": {"twin_levels": list(LEVELS), "cost_models": 1, "block_origins": p["block_sessions"],
                           "note": "three twin constructions, all printed; the verdict level (band) was fixed "
                                   "before the run; one seed per book from the run seed and the account name"},
        "inputs": {"book_dna": file_info(dna_p), "roi": file_info(roi_p), "llm_books": file_info(books_p),
                   "aegis_pi_db": file_info(db_path), "bars": [file_info(x) for x in bars_paths],
                   "global_bars": file_info(gb), "bars_window_start": start, "bars_rows_read": int(len(bars)),
                   "bars_symbols": int(bars["symbol"].nunique()), "panel_last_session": panel.dates[-1],
                   "sector_map": sector_src},
        "survivorship": {**surv, "direction": (
            "the living panel holds names alive when it was built; a name that died before that is absent "
            "from every twin pool, which LIFTS the random twins (dead names are disproportionately losers). "
            "BEATS is conservative under this bias; LAGS and BAND_EFFECT are not. A name that stops trading "
            "inside a window is held at its last close (no delisting return)." if not delisted.exists()
            else "prices_deep/bars_delisted.parquet merged into the pool, so dead names can be drawn; the "
                 "audit above counts how many stop trading inside the rows read. Residual bias: any name absent "
                 "from both files is absent from every twin pool, which would LIFT the twins.")},
        "conventions": {
            "fill": "llm books at the inception open; night books at the close of the decision asof; fleet "
                    "books at the snapshot session close; twins on exactly the same fill rows",
            "twin_pool": "live names (a bar within live_days before asof, close >= min_price, no ETF/index) "
                         "measured on bars STRICTLY BEFORE the asof; band = liquidity band (median $ volume of "
                         "band_window sessions) x volatility tercile within the band",
            "costs": "half of the band's round trip per traded dollar, exit half on the final mark; ETFs/index at "
                     "the mega band; SPY legs gross",
            "carried_into_twins": "ETFs, index proxies, CASH and names absent from the bars panel",
            "verdict": "read at the band level: BEATS/LAGS need t beyond t_crit at EVERY block origin AND the "
                       "book in the matching 2.5% tail of its twins; BAND_EFFECT = not distinguishable from the "
                       "twins while book and twin median are both above SPY",
            "by_month": "keyed on the HOLD session of each NAV change"},
        "accounting": {"roi_rows": len(roi.get("rows") or []), "strategy_rows": len(strategy) if not only else None,
                       "dropped_rows": dropped, "n_dropped": len(dropped),
                       "n_distinct_bets": len(leaders), "verdict_counts": counts},
        "books": results,
        "pairwise": pairs,
        "cross_book": cross,
        "claim_line": "CLAIMS PROMOTED: none",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"matched_twin_reeval_{run_id}_{stamp}.json"
    tmpf = out.with_suffix(".json.tmp")
    tmpf.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    json.loads(tmpf.read_text(encoding="utf-8"))
    tmpf.replace(out)
    md = out.with_suffix(".md")
    md.write_text("\n".join(render_md(receipt)) + "\n", encoding="utf-8")
    receipt["_path"], receipt["_md"] = str(out), str(md)
    return receipt


def cross_book(results: dict) -> dict:
    """How much of the cross-section of book-vs-SPY the twins' band explains. The
    books share windows, so they are NOT independent draws: a description, not a test."""
    ok = [r for r in results.values() if r.get("status") == "OK"]
    if len(ok) < 3:
        return {"n_books": len(ok), "why": "fewer than 3 evaluated books"}
    ex = np.array([r["excess_vs_spy_pp"] for r in ok], float)
    out: dict = {"n_books": len(ok), "n_book_above_spy": int((ex > 0).sum()),
                 "note": "books share windows (most llm books 2026-09-28 -> last mark): not independent draws"}
    for lv in LEVELS:
        tm = np.array([r["twins"][lv]["twin_median_vs_spy_pp"] for r in ok], float)
        om = np.array([r["twins"][lv]["excess_over_twin_median_pp"] for r in ok], float)
        pc = np.array([r["twins"][lv]["book_percentile"] for r in ok], float)
        out[lv] = {"twin_median_vs_spy_pp_median": round(float(np.median(tm)), 3),
                   "share_books_whose_twin_median_beats_spy": round(float((tm > 0).mean()), 3),
                   "book_over_twin_median_pp_median": round(float(np.median(om)), 3),
                   "corr_book_vs_spy_with_twin_median_vs_spy": round(float(np.corrcoef(ex, tm)[0, 1]), 3),
                   "mean_book_percentile": round(float(np.mean(pc)), 3),
                   "n_at_or_above_0975": int((pc >= 0.975).sum()), "n_at_or_below_0025": int((pc <= 0.025).sum()),
                   "expected_each_tail_if_books_were_twins": round(0.025 * len(pc), 2)}
    D = np.array([[r["decomposition_pp"][k] for k in ("cash", "panel", "band", "sector", "selection")] for r in ok])
    out["decomposition_median_pp"] = dict(zip(("cash", "panel", "band", "sector", "selection"),
                                              np.round(np.median(D, 0), 3).tolist()))
    return out


def load_sector_map(universe_dir: Path) -> tuple[dict, str]:
    files = sorted(universe_dir.glob("*.jsonl"))
    if not files:
        return {}, f"none (no {universe_dir}/*.jsonl)"
    m = {}
    for r in read_jsonl(files[-1]):
        s = (r.get("identity") or {}).get("sector")
        if s and r.get("symbol"):
            m[r["symbol"]] = s
    return m, f"potential_universe/{files[-1].name} identity.sector ({len(m)} symbols)"


def _f(x: Any, fmt: str = "{:+.2f}") -> str:
    return "n/a" if x is None else fmt.format(x)


def book_rows(receipt: dict) -> list[dict]:
    rows = []
    for acct, r in receipt["books"].items():
        if r.get("status") != "OK":
            continue
        tw = r["twins"][receipt["primary_level"]]
        sw = tw["origin_sweep"]
        ts = [s["t"] for s in sw if s["t"] is not None]
        rows.append({"account": acct, "family": r["family"], "book": r["book_pct"], "spy": r["spy_pct"],
                     "mde0": r["headline_mde_pp_origin0"],
                     "excess": r["excess_vs_spy_pp"], "twin_median": tw["median_pct"], "p05": tw["p05_pct"],
                     "p95": tw["p95_pct"], "pct": tw["book_percentile"],
                     "over_median": tw["excess_over_twin_median_pp"], "t": r["headline_t_origin0"],
                     "t_range": (min(ts), max(ts)) if ts else None, "mde": tw["mde_pp_max_over_origins"],
                     "blocks": r["headline_blocks"], "sessions": r["sessions"], "verdict": r["verdict"],
                     "sector_verdict": r["twins"]["band_sector"]["verdict"],
                     "sector_pct": r["twins"]["band_sector"]["book_percentile"], "recon_gap": r["recon_gap_pp"]})
    rows.sort(key=lambda x: -(x["excess"] or -1e9))
    return rows


def render_md(receipt: dict) -> list[str]:
    L = [f"# Matched-twin re-evaluation, run {receipt['run_id']}", "",
         f"Licence {receipt['licence']}. Twins per book: {receipt['params']['n_twins']}; verdict level "
         f"`{receipt['primary_level']}` (liquidity band x volatility tercile, bars strictly before each decision). "
         f"Blocks of {receipt['params']['block_sessions']} sessions, every origin swept.", "",
         "| account | family | book | SPY | vs SPY | twin median [p05, p95] | pctile | over median | t (origin 0; range) "
         "| MDE origin 0 (max over origins) | blocks | verdict | sector-matched |",
         "|---|---|---:|---:|---:|---|---:|---:|---|---:|---:|---|---|"]
    for x in book_rows(receipt):
        tr = "" if not x["t_range"] else f" [{x['t_range'][0]:+.2f}, {x['t_range'][1]:+.2f}]"
        L.append(f"| {x['account'][:48]} | {x['family']} | {_f(x['book'])}% | {_f(x['spy'])}% | {_f(x['excess'])} pp "
                 f"| {_f(x['twin_median'])}% [{_f(x['p05'])}, {_f(x['p95'])}] | {_f(x['pct'], '{:.3f}')} "
                 f"| {_f(x['over_median'])} pp | {_f(x['t'])}{tr} | {_f(x['mde0'], '{:.2f}')} ({_f(x['mde'], '{:.2f}')}) pp | {x['blocks']} "
                 f"| {x['verdict']} | {x['sector_verdict']} ({_f(x['sector_pct'], '{:.3f}')}) |")
    L += ["", "## Not evaluated (each with why)", ""]
    for acct, r in receipt["books"].items():
        if r.get("status") != "OK":
            L.append(f"- {acct} ({r.get('family')}, vs SPY {_f(r.get('roi_vs_spy_pp'))} pp): {r.get('why')}")
    pw = [x for x in receipt.get("pairwise") or [] if x.get("corr_daily_excess") is not None]
    if pw:
        cs = np.array([x["corr_daily_excess"] for x in pw])
        js = np.array([x["jaccard"] for x in pw])
        L += ["", "## Pairwise (input to joining books later)", "",
              f"{len(pw)} pairs with >= 10 common days: daily-excess correlation median {np.median(cs):+.2f}, "
              f"{(cs > 0.5).mean():.0%} of pairs above +0.5; holdings Jaccard median {np.median(js):.2f}, "
              f"{(js > 0).mean():.0%} of pairs share at least one name.", "",
              "| a | b | Jaccard | corr daily excess | days |", "|---|---|---:|---:|---:|"]
        for x in sorted(pw, key=lambda x: -x["corr_daily_excess"])[:15]:
            L.append(f"| {x['a'][:40]} | {x['b'][:40]} | {x['jaccard']:.2f} | {x['corr_daily_excess']:+.2f} "
                     f"| {x['n_common_days']} |")
    acc = receipt["accounting"]
    L += ["", f"roi rows {acc['roi_rows']}; strategy rows {acc['strategy_rows']}; dropped {acc['n_dropped']} "
              f"(controls/twins/non-LIVE, each listed in the JSON); distinct bets {acc['n_distinct_bets']}.",
          "", f"Survivorship: {receipt['survivorship']['verdict']} {receipt['survivorship']['direction']}", "",
          receipt["claim_line"]]
    return L


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="matched_twin_reeval")
    ap.add_argument("--out", required=True, help="output directory (never inside the data root's parent)")
    ap.add_argument("--data-root", default=None,
                    help="the optimus data folder to READ (default: backend.config.OPTIMUS_LEDGER_DIR)")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--n-twins", type=int, default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--books", default=None, help="comma-separated accounts (default: every strategy row)")
    a = ap.parse_args(argv)
    p = params()
    root = Path(a.data_root) if a.data_root else Path(_config.OPTIMUS_LEDGER_DIR)
    out = Path(a.out)
    try:
        if out.resolve().is_relative_to(root.resolve().parent):
            print(f"REFUSED: --out {out} is inside the data folder {root.resolve().parent}")
            return 2
    except (OSError, ValueError):
        pass
    watch = [root / "paper_accounts", root / "llm_portfolio"]
    before = {str(w): count_files(w) for w in watch}
    try:
        rec = run(data_root=root, out_dir=out, run_id=a.run_id,
                  n_twins=a.n_twins or p["n_twins"], seed=a.seed if a.seed is not None else p["seed"],
                  only=set(a.books.split(",")) if a.books else None)
    except Refused as exc:
        print(f"REFUSED matched_twin_reeval: {exc}")
        return 2
    after = {str(w): count_files(w) for w in watch}
    inp = rec["inputs"]
    for k in ("roi", "book_dna", "llm_books", "aegis_pi_db", "global_bars"):
        i = inp[k]
        print(f"input {k}: {i['path']} bytes={i.get('bytes')} mtime={i.get('mtime_utc')}")
    for i in inp["bars"]:
        print(f"input bars: {i['path']} bytes={i.get('bytes')} mtime={i.get('mtime_utc')}")
    print(f"bars read from {inp['bars_window_start']}: {inp['bars_rows_read']:,} rows, {inp['bars_symbols']:,} "
          f"symbols, newest session {inp['panel_last_session']}; roi generated {rec['run_id']}")
    for x in book_rows(rec):
        print(f"{x['account'][:50]:<50} book {_f(x['book'])}% SPY {_f(x['spy'])}% twin med {_f(x['twin_median'])}% "
              f"pct {_f(x['pct'], '{:.3f}')} t {_f(x['t'])} MDE {_f(x['mde0'], '{:.2f}')} (max {_f(x['mde'], '{:.2f}')}) blocks {x['blocks']} "
              f"-> {x['verdict']}")
    print(rec["claim_line"])
    print(f"wrote {rec['_path']} and {rec['_md']}")
    for w in watch:
        print(f"live file count {w}: {before[str(w)]} -> {after[str(w)]}")
    ours = [f for w in watch for f in Path(w).rglob("matched_twin_reeval*")] if root.exists() else []
    if ours:
        print(f"REFUSED: this script's output appeared in the live folder: {ours}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
