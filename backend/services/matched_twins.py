"""Characteristic-matched random twins (DGTW-style) for strategy-library books.

Licence: PRODUCT_EXPERIMENT diagnostics ($0, no LLM). Reviewer idea 2,
`docs/reviews/REVIEW_2026-09-27_SIGNAL_STRUCTURE_ROUND2_BRIDGE.md`: SPY and the
uniform random panel cannot separate "the rule SELECTS" from "the rule buys a
STYLE". A twin that holds, for every name the rule holds, a random name from the
SAME size band x 63-session volatility tercile x 12-1 past-return tercile cell at
the same rebalance can: rule - matched twin is what the selection adds beyond
its characteristics; rule - random_1 is what it adds beyond a random draw from
the whole panel. The difference between the two is how much of a rule's excess
the style explains.

Conventions, identical to the factory (`scripts/night_backtest_factory.py`):
- size band = the factory's cost band on 63-session median dollar volume
  (mega >= 1e9, large >= 1e8, mid >= 2e7, small below);
- terciles of `vol_63` and `mom_252_21` are taken among the ELIGIBLE names of the
  decision date; a name with no 12-1 return gets its own "na" bucket;
- the forward return is the factory's: enter at the next session's open, exit at
  the open of the session after the next month-end, a name whose bars stop inside
  the period filled at its last close x (1 + STRATEGY_LIB_DELIST_RETURN);
- between rebalances the weights are HELD CONSTANT (`strategy_library.run_strategy`
  applies the rebalance weights to every month of the hold, untraded and
  uncharged); a name with no return that month (dead, halted) earns 0.

The twin is drawn at every rebalance (every date in the rule's
`held_symbols_by_date`), from the same panel, excluding the rule's own holdings
and without replacement within the date; the RNG is seeded from the rule id. A
cell with no candidate falls back to band x vol, then band, then any eligible
name, and the fallbacks are counted on the receipt.
"""
from __future__ import annotations

import hashlib
import math
from typing import Iterable, Optional

import numpy as np
import pandas as pd

#: the factory's cost bands on median 63-session dollar volume
SIZE_BANDS = (("mega", 1e9), ("large", 1e8), ("mid", 2e7), ("small", -np.inf))
FALLBACK_LEVELS = ("cell", "band_vol", "band", "any")
N_EXTRA_DRAWS = 20


class TwinInputMissing(RuntimeError):
    """A rule or panel input the twin needs is absent: the receipt refuses."""


# ── characteristics ─────────────────────────────────────────────────────────

def size_band(mdv) -> np.ndarray:
    x = np.asarray(mdv, dtype=float)
    out = np.full(x.shape, "na", dtype=object)
    done = np.zeros(x.shape, dtype=bool)
    for name, lo in SIZE_BANDS:
        m = np.isfinite(x) & (x >= lo) & ~done
        out[m] = name
        done |= m
    return out


def _tercile(x: pd.Series) -> pd.Series:
    r = x.rank(pct=True, method="average")
    t = np.ceil(r * 3.0).clip(1, 3)
    return t.map(lambda v: "na" if not np.isfinite(v) else str(int(v)))


def cell_table(panel_d: pd.DataFrame) -> pd.DataFrame:
    """Eligible names of ONE decision date -> band, vol tercile, mom tercile.

    `panel_d`: columns symbol, eligible, median_dollar_vol, vol_63, mom_252_21.
    The tercile cut points ride on `.attrs` so a held name that is not eligible
    that day can still be placed."""
    e = panel_d[panel_d["eligible"].astype(bool)].copy()
    e = e.drop_duplicates("symbol").set_index("symbol")
    e["band"] = size_band(e["median_dollar_vol"])
    e["vt"] = _tercile(e["vol_63"].astype(float))
    e["mt"] = _tercile(e["mom_252_21"].astype(float))
    out = e[["band", "vt", "mt"]].copy()
    out.attrs["cuts"] = {c: np.nanquantile(e[c].astype(float), [1 / 3, 2 / 3])
                         if e[c].notna().any() else None for c in ("vol_63", "mom_252_21")}
    return out


def seed_for(rule_id: str, draw: int = 0) -> int:
    key = rule_id if draw == 0 else f"{rule_id}#{draw}"
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:12], 16)


def _cell_of(sym: str, cells: pd.DataFrame, panel_d: pd.DataFrame) -> tuple:
    if sym in cells.index:
        r = cells.loc[sym]
        return r["band"], r["vt"], r["mt"]
    # held but not eligible on the panel (rare): place it by its own values
    row = panel_d[panel_d["symbol"] == sym]
    if not len(row):
        return None, None, None
    row = row.iloc[0]
    band = size_band([row.get("median_dollar_vol", np.nan)])[0]
    cuts = cells.attrs.get("cuts") or {}

    def pos(col):
        v, q = row.get(col, np.nan), cuts.get(col)
        if q is None or v is None or not np.isfinite(v):
            return "na"
        return "1" if v <= q[0] else ("2" if v <= q[1] else "3")
    return band, pos("vol_63"), pos("mom_252_21")


def draw_twins(held: Iterable[str], cells: pd.DataFrame, panel_d: pd.DataFrame,
               rng: np.random.Generator) -> tuple[list, dict]:
    """[(held, twin or None, level)] and fallback counts for one rebalance."""
    held = list(held)
    taken = set(held)
    out, counts = [], {lv: 0 for lv in FALLBACK_LEVELS}
    counts["none"] = 0
    idx = cells.index.to_numpy()
    band, vt, mt = (cells[c].to_numpy() for c in ("band", "vt", "mt"))
    for s in held:
        b, v, m = _cell_of(s, cells, panel_d)
        masks = []
        if b is not None:
            if v is not None and m is not None:
                masks.append(("cell", (band == b) & (vt == v) & (mt == m)))
            if v is not None:
                masks.append(("band_vol", (band == b) & (vt == v)))
            masks.append(("band", band == b))
        masks.append(("any", np.ones(len(idx), dtype=bool)))
        pick, level = None, "none"
        for lv, mk in masks:
            cand = [x for x in idx[mk] if x not in taken]
            if cand:
                pick = cand[int(rng.integers(len(cand)))]
                level = lv
                break
        if pick is not None:
            taken.add(pick)
        counts[level] += 1
        out.append((s, pick, level))
    return out, counts


# ── returns ─────────────────────────────────────────────────────────────────

def _book_return(w: dict, fwd: dict) -> tuple[float, dict]:
    """One month of a drifting book: weights {sym: w}, returns r (NaN = cash).
    Returns (portfolio return, next month's weights)."""
    tot = sum(w.values())
    if tot <= 0:
        return 0.0, w
    ret, nxt = 0.0, {}
    for s, wi in w.items():
        r = fwd.get(s, np.nan) if s is not None else np.nan
        r = float(r) if r is not None and np.isfinite(r) else 0.0
        ret += wi / tot * r
        nxt[s] = wi * (1.0 + r)
    return ret, nxt


def panel_by_date(panel: pd.DataFrame) -> dict:
    """{"YYYY-MM-DD": rows of that decision date} -- group once, draw many times."""
    return {str(d.date()): g for d, g in panel.groupby(pd.DatetimeIndex(panel["date"]))}


def twin_series(rule: dict, panel: pd.DataFrame, *, seed: int,
                by_date: Optional[dict] = None, cache: Optional[dict] = None,
                drift: bool = False) -> pd.DataFrame:
    """Month by month: the rule's own gross (reconstructed from its holdings on
    this panel, a check against the stored series) and its matched twin's gross.

    `rule`: `held_symbols_by_date`, `weights_by_date`, `monthly_return_series`
    (each row: date, gross, cost, net, rebalanced), optional `risk_off_dates`.
    `panel`: long frame with date, symbol, eligible, median_dollar_vol, vol_63,
    mom_252_21, fwd_ret."""
    held = rule.get("held_symbols_by_date") or {}
    wts = rule.get("weights_by_date") or {}
    months = rule.get("monthly_return_series") or []
    if not held or not months:
        raise TwinInputMissing(f"{rule.get('id')}: no holdings or no monthly series")
    risk_off = {str(d)[:10] for d in rule.get("risk_off_dates") or []}
    rng = np.random.default_rng(seed)
    if by_date is None:
        by_date = panel_by_date(panel)
    fwd_cache: dict = cache if cache is not None else {}   # per-date returns + cells, shareable
    rows = []
    w_rule: dict = {}
    w_twin: dict = {}
    for mrow in months:
        d = str(mrow["date"])[:10]
        g = by_date.get(d)
        if d not in fwd_cache:
            fwd_cache[d] = (g.drop_duplicates("symbol").set_index("symbol")["fwd_ret"].to_dict()
                            if g is not None else {})
        fwd = fwd_cache[d]
        counts = None
        if d in held:
            if g is None:
                raise TwinInputMissing(f"{rule.get('id')}: rebalance {d} is not on the panel")
            syms = list(held[d])
            ws = list(wts.get(d) or [1.0 / len(syms)] * len(syms))
            ck = ("__cells__", d)
            if ck not in fwd_cache:
                fwd_cache[ck] = cell_table(g)
            pairs, counts = draw_twins(syms, fwd_cache[ck], g, rng)
            w_rule = {s: float(x) for s, x in zip(syms, ws)}
            w_twin = {}
            for (s, t, _lv), x in zip(pairs, ws):
                key = t if t is not None else f"__cash_{s}"
                w_twin[key] = w_twin.get(key, 0.0) + float(x)
        if d in risk_off:
            rows.append({"date": d, "rule_gross_recon": 0.0, "twin_gross": 0.0,
                         "stored_gross": mrow.get("gross"), "cost": mrow.get("cost"),
                         "stored_net": mrow.get("net"), "fallbacks": counts})
            continue
        rr, w_rule_n = _book_return(w_rule, fwd)
        tr, w_twin_n = _book_return(w_twin, fwd)
        if drift:                      # off by default: the factory holds weights constant
            w_rule, w_twin = w_rule_n, w_twin_n
        rows.append({"date": d, "rule_gross_recon": rr, "twin_gross": tr,
                     "stored_gross": mrow.get("gross"), "cost": mrow.get("cost"),
                     "stored_net": mrow.get("net"), "fallbacks": counts})
    out = pd.DataFrame(rows)
    out["date"] = pd.to_datetime(out["date"])
    return out.set_index("date")


# ── comparison ──────────────────────────────────────────────────────────────

def cagr(r: pd.Series) -> Optional[float]:
    r = pd.Series(r).dropna()
    if not len(r):
        return None
    g = float(np.prod(1.0 + r.to_numpy(dtype=float)))
    return g ** (12.0 / len(r)) - 1.0 if g > 0 else -1.0


def compare(rule_net: pd.Series, twin_net: pd.Series, random_net: pd.Series,
            mask: np.ndarray) -> dict:
    """Excess CAGR of the rule over its matched twin and over random_1 in one
    window, the part of the random excess the matching removes, and the mean
    monthly rule - twin difference with its plain t."""
    rn, tn = rule_net[mask], twin_net[mask]
    rd = random_net.reindex(rule_net.index)[mask]
    c_rule, c_twin, c_rand = cagr(rn), cagr(tn), cagr(rd)
    ex_twin = (c_rule - c_twin) if None not in (c_rule, c_twin) else None
    ex_rand = (c_rule - c_rand) if None not in (c_rule, c_rand) else None
    diff = (rn - tn).dropna()
    se = float(diff.std(ddof=1) / math.sqrt(len(diff))) if len(diff) > 1 else float("nan")
    removed = (ex_rand - ex_twin) if None not in (ex_rand, ex_twin) else None
    return {"n_months": int(mask.sum()), "cagr_rule": c_rule, "cagr_twin": c_twin,
            "cagr_random_1": c_rand, "rule_minus_twin": ex_twin, "rule_minus_random_1": ex_rand,
            "removed_by_matching": removed,
            "share_removed": (removed / ex_rand) if (removed is not None and ex_rand
                                                     and abs(ex_rand) > 1e-12) else None,
            "mean_monthly_rule_minus_twin": float(diff.mean()) if len(diff) else None,
            "t_monthly_rule_minus_twin": (float(diff.mean() / se)
                                          if np.isfinite(se) and se > 0 else None)}


# ── the characteristics panel from bars (light: long format, one symbol at a time)

def _month_end_positions(cal: pd.DatetimeIndex) -> np.ndarray:
    s = pd.Series(np.arange(len(cal)), index=cal)
    return s.groupby(cal.to_period("M")).max().to_numpy()


def build_panel(paths: Iterable, *, start: str, delist_return: float,
                decision_dates: Optional[Iterable] = None, market: str = "SPY",
                excluded: Optional[set] = None, min_price: float = 3.0,
                max_price: float = 10_000.0, min_mdv: float = 3_000_000.0,
                min_history: int = 126) -> pd.DataFrame:
    """The factory's month-end columns that the twin needs, without its dense
    (dates x symbols) arrays: read bars row group by row group into compact
    numpy columns, de-duplicate (first file wins, as the factory's concat +
    drop_duplicates), then walk one symbol at a time on the market calendar."""
    import pyarrow.parquet as pq
    start_ts = pd.Timestamp(start)
    sym_id: dict = {}
    parts = []
    order = 0
    for p in paths:
        f = pq.ParquetFile(p)
        for rg in range(f.num_row_groups):
            t = f.read_row_group(rg, columns=["symbol", "date", "open", "close", "volume"])
            df = t.to_pandas()
            del t
            df = df[pd.to_datetime(df["date"]) >= start_ts]
            if not len(df):
                continue
            cat = df["symbol"].astype("category")
            gids = np.array([sym_id.setdefault(s, len(sym_id)) for s in cat.cat.categories],
                            dtype=np.int32)
            parts.append({"sym": gids[cat.cat.codes.to_numpy()],
                          "date": pd.to_datetime(df["date"]).to_numpy(dtype="datetime64[D]"),
                          "open": df["open"].to_numpy(dtype=np.float32),
                          "close": df["close"].to_numpy(dtype=np.float32),
                          "volume": df["volume"].to_numpy(dtype=np.float32),
                          "src": np.full(len(df), order, dtype=np.int32)})
            order += 1
            del df, cat
    if not parts:
        raise TwinInputMissing("no bars on or after the start date")
    col = {k: np.concatenate([x[k] for x in parts]) for k in parts[0]}
    del parts
    symbols = np.empty(len(sym_id), dtype=object)
    for s, i in sym_id.items():
        symbols[i] = s
    if market not in sym_id:
        raise TwinInputMissing(f"market proxy {market} absent from the bars")
    mk = col["sym"] == sym_id[market]
    cal = pd.DatetimeIndex(np.unique(col["date"][mk]))
    di = np.searchsorted(cal.values.astype("datetime64[D]"), col["date"])
    on_cal = (di < len(cal)) & (cal.values.astype("datetime64[D]")[np.minimum(di, len(cal) - 1)]
                                == col["date"])
    key = col["sym"].astype(np.int64) * 100_000 + di
    ordr = np.lexsort((col["src"], key))
    ordr = ordr[on_cal[ordr]]
    k_sorted = key[ordr]
    first = np.ones(len(ordr), dtype=bool)
    first[1:] = k_sorted[1:] != k_sorted[:-1]
    ordr = ordr[first]
    S, D = col["sym"][ordr], di[ordr]
    O, C, V = col["open"][ordr], col["close"][ordr], col["volume"][ordr]
    del col, key, ordr, k_sorted, first, di, on_cal
    T = len(cal)
    me = _month_end_positions(cal)
    if decision_dates is not None:
        want = set(pd.DatetimeIndex(pd.to_datetime(list(decision_dates))).normalize())
        me_keep = np.array([cal[i] in want for i in me])
    else:
        me_keep = np.ones(len(me), dtype=bool)
    excluded = excluded or set()
    bounds = np.flatnonzero(np.diff(S)) + 1
    starts = np.concatenate([[0], bounds])
    ends = np.concatenate([bounds, [len(S)]])
    out = []
    for a, b in zip(starts, ends):
        s_id = int(S[a])
        sym = symbols[s_id]
        d0, d1 = int(D[a]), int(D[b - 1])
        L = d1 - d0 + 1
        c = np.full(L, np.nan)
        o = np.full(L, np.nan)
        v = np.zeros(L)
        loc = D[a:b] - d0
        c[loc], o[loc], v[loc] = C[a:b], O[a:b], V[a:b]
        c[~(c > 0)] = np.nan
        o[~(o > 0)] = np.nan
        cs = pd.Series(c)
        cff = cs.ffill().to_numpy()
        r = np.full(L, np.nan)
        r[1:] = c[1:] / cff[:-1] - 1.0
        r[~np.isfinite(c)] = np.nan
        vol63 = pd.Series(r).rolling(63, min_periods=40).std().to_numpy() * math.sqrt(252)
        dv = np.where(np.isfinite(c), c * v, np.nan)
        mdv = pd.Series(dv).rolling(63, min_periods=40).median().to_numpy()
        seen = np.cumsum(np.isfinite(c))
        for pos, gi in enumerate(me):
            if not me_keep[pos] or gi < d0 or gi > d1:
                continue
            i = gi - d0
            if not np.isfinite(c[i]):
                continue

            def lag(n):
                j = i - n
                return cff[j] if j >= 0 else np.nan
            mom_252_21 = lag(21) / lag(252) - 1.0
            mom_63 = cff[i] / lag(63) - 1.0
            elig = (min_price <= c[i] <= max_price and np.isfinite(mdv[i]) and mdv[i] >= min_mdv
                    and seen[i] >= min_history and sym not in excluded and sym != market
                    and np.isfinite(vol63[i]) and np.isfinite(mom_63))
            fwd = np.nan
            died = False
            if pos + 1 < len(me):
                e0, e1 = gi + 1, int(me[pos + 1]) + 1
                if e1 <= T - 1:
                    j0 = e0 - d0
                    entry = o[j0] if (j0 < L and np.isfinite(o[j0])) else c[i]
                    died = d1 < e1
                    if died:
                        ex = cff[L - 1] * (1.0 + delist_return)
                    else:
                        j1 = e1 - d0
                        ex = o[j1] if np.isfinite(o[j1]) else cff[j1]
                    fwd = ex / entry - 1.0
            out.append((cal[gi], sym, bool(elig), float(mdv[i]), float(vol63[i]),
                        float(mom_252_21), float(fwd), bool(died)))
    return pd.DataFrame(out, columns=["date", "symbol", "eligible", "median_dollar_vol", "vol_63",
                                      "mom_252_21", "fwd_ret", "delisted_in_period"])
