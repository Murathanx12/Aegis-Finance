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


class CellIndex:
    """One decision date's cells, grouped once: the candidate lists of every
    (band, vol, mom), (band, vol) and band key IN `cells.index` ORDER, so a draw
    from a group is the same draw as from the boolean mask over the index (the
    seeded results do not move), at a dict lookup instead of three object-array
    comparisons per held name. Built per date and cached by `twin_series`."""

    def __init__(self, cells: pd.DataFrame):
        self.cells = cells
        self.idx = cells.index.to_numpy()
        self.pos = {s: (b, v, m) for s, b, v, m in zip(self.idx, cells["band"].to_numpy(),
                                                        cells["vt"].to_numpy(), cells["mt"].to_numpy())}
        g: dict = {}
        for s, (b, v, m) in self.pos.items():
            for key in (("cell", b, v, m), ("band_vol", b, v), ("band", b)):
                g.setdefault(key, []).append(s)
        self.groups = g
        self.cuts = cells.attrs.get("cuts") or {}

    def cell_of(self, sym: str, panel_d: pd.DataFrame) -> tuple:
        if sym in self.pos:
            return self.pos[sym]
        return _cell_of(sym, self.cells, panel_d)

    def candidates(self, level: str, b, v, m) -> list:
        if level == "any":
            return list(self.idx)
        key = {"cell": ("cell", b, v, m), "band_vol": ("band_vol", b, v), "band": ("band", b)}[level]
        return self.groups.get(key, [])


def draw_twins(held: Iterable[str], cells: pd.DataFrame, panel_d: pd.DataFrame,
               rng: np.random.Generator, index: Optional[CellIndex] = None) -> tuple[list, dict]:
    """[(held, twin or None, level)] and fallback counts for one rebalance."""
    held = list(held)
    taken = set(held)
    out, counts = [], {lv: 0 for lv in FALLBACK_LEVELS}
    counts["none"] = 0
    ci = index if index is not None else CellIndex(cells)
    for s in held:
        b, v, m = ci.cell_of(s, panel_d)
        levels = []
        if b is not None:
            if v is not None and m is not None:
                levels.append("cell")
            if v is not None:
                levels.append("band_vol")
            levels.append("band")
        levels.append("any")
        pick, level = None, "none"
        for lv in levels:
            cand = [x for x in ci.candidates(lv, b, v, m) if x not in taken]
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


def check_months(rule: dict, grid: Iterable) -> None:
    """A cell's monthly series must sit on the decision-date grid with NO hole
    between its first and last month. A hole (a value rule's refused period, a
    lost row) would let the twin carry a stale book across it while the rule's
    stored series skips it: the two would no longer be the same months, and
    "rule - twin" would compare different things. Refuses by the cell's name."""
    rid = rule.get("id")
    months = [str(m["date"])[:10] for m in rule.get("monthly_return_series") or []]
    if not months:
        raise TwinInputMissing(f"{rid}: no monthly series")
    g = [str(pd.Timestamp(x).date()) for x in grid]
    pos = {d: i for i, d in enumerate(g)}
    off = [d for d in months if d not in pos]
    if off:
        raise TwinInputMissing(f"{rid}: month(s) {off[:3]} not on the decision-date grid")
    have = set(months)
    missing = [d for d in g[pos[months[0]]:pos[months[-1]] + 1] if d not in have]
    if missing:
        raise TwinInputMissing(f"{rid}: {len(missing)} month(s) missing from the monthly series "
                               f"inside its span (first {missing[0]}); the twin would not cover "
                               "the same months")


def twin_series(rule: dict, panel: pd.DataFrame, *, seed: int,
                by_date: Optional[dict] = None, cache: Optional[dict] = None,
                drift: bool = False, grid: Optional[Iterable] = None) -> pd.DataFrame:
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
    if grid is not None:
        check_months(rule, grid)
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
        if g is None:
            raise TwinInputMissing(f"{rule.get('id')}: month {d} of its series is not on the panel "
                                   "(its forward returns are unknown; a twin would earn 0 there)")
        if d not in fwd_cache:
            fwd_cache[d] = (g.drop_duplicates("symbol").set_index("symbol")["fwd_ret"].to_dict()
                            if g is not None else {})
        fwd = fwd_cache[d]
        counts = None
        if d in held:
            if g is None:
                raise TwinInputMissing(f"{rule.get('id')}: rebalance {d} is not on the panel")
            syms = list(held[d])
            ws = list(wts.get(d) or ([1.0 / len(syms)] * len(syms) if syms else []))
            ck = ("__cells__", d)
            if ck not in fwd_cache:
                ct = cell_table(g)
                fwd_cache[ck] = (ct, CellIndex(ct))
            ct, ci = fwd_cache[ck]
            pairs, counts = draw_twins(syms, ct, g, rng, index=ci)
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


# ── holdings for every cell (the factory's sidecar) ─────────────────────────
#
# The factory stores, per (rule, k) cell, the held symbols and weights at every
# rebalance, and each month's gross / cost / net, as two long parquet tables
# (`holdings_<run>.parquet`, `cell_monthly_<run>.parquet`). The format lives
# here, beside its only reader, so writer and reader cannot drift apart. A
# rebalance to CASH (the regime gate off) is one row with symbol "" and
# weight NaN, `risk_off` True: it round-trips to an empty book on that date.

HOLDINGS_COLUMNS = ("rule", "k", "date", "symbol", "weight", "risk_off")
MONTHLY_COLUMNS = ("rule", "k", "date", "gross", "cost", "net", "rebalanced", "n_held")
CASH_SYMBOL = ""


def holdings_frame(records: Iterable) -> pd.DataFrame:
    """[(rule_id, k, [{date, symbols, weights, risk_off}, ...])] -> the long table."""
    rule, kk, dd, sym, w, ro = [], [], [], [], [], []
    for rid, k, hold in records:
        for h in hold or []:
            syms = list(h.get("symbols") or [])
            wts = list(h.get("weights") or [])
            if not syms:
                syms, wts = [CASH_SYMBOL], [np.nan]
            n = len(syms)
            rule += [str(rid)] * n
            kk += [int(k)] * n
            dd += [str(h["date"])[:10]] * n
            sym += [str(x) for x in syms]
            w += [float(x) for x in wts]
            ro += [bool(h.get("risk_off"))] * n
    df = pd.DataFrame({"rule": pd.Categorical(rule), "k": np.asarray(kk, dtype=np.int16),
                       "date": pd.to_datetime(pd.Series(dd, dtype=object)),
                       "symbol": pd.Categorical(sym), "weight": np.asarray(w, dtype=float),
                       "risk_off": np.asarray(ro, dtype=bool)})
    return df[list(HOLDINGS_COLUMNS)]


def monthly_frame(records: Iterable) -> pd.DataFrame:
    """[(rule_id, k, monthly DataFrame from run_strategy)] -> the long table."""
    parts = []
    for rid, k, m in records:
        if m is None or not len(m):
            continue
        x = pd.DataFrame({"rule": str(rid), "k": int(k), "date": pd.to_datetime(m["date"]),
                          "gross": m["gross"].astype(float), "cost": m["cost"].astype(float),
                          "net": m["net"].astype(float), "rebalanced": m["rebalanced"].astype(bool),
                          "n_held": m["n_held"].astype(int)})
        parts.append(x)
    if not parts:
        return pd.DataFrame({c: [] for c in MONTHLY_COLUMNS})
    df = pd.concat(parts, ignore_index=True)
    df["rule"] = df["rule"].astype("category")
    df["k"] = df["k"].astype(np.int16)
    return df[list(MONTHLY_COLUMNS)]


def cell_records(holdings: pd.DataFrame, monthly: pd.DataFrame) -> dict:
    """The long tables -> {(rule, k): the record `twin_series` reads}:
    held_symbols_by_date, weights_by_date, risk_off_dates, monthly_return_series."""
    out: dict = {}
    h = holdings.copy()
    h["rule"] = h["rule"].astype(str)
    h["symbol"] = h["symbol"].astype(str)
    for (rid, k), g in h.groupby(["rule", "k"], sort=False, observed=True):
        held, wts, ro = {}, {}, []
        for d, gd in g.groupby("date", sort=True):
            ds = str(pd.Timestamp(d).date())
            real = gd[gd["symbol"] != CASH_SYMBOL]
            held[ds] = real["symbol"].tolist()
            wts[ds] = real["weight"].astype(float).tolist()
            if bool(gd["risk_off"].any()):
                ro.append(ds)
        out[(str(rid), int(k))] = {"id": f"{rid}@k{int(k)}", "held_symbols_by_date": held,
                                   "weights_by_date": wts, "risk_off_dates": ro,
                                   "monthly_return_series": []}
    m = monthly.copy()
    m["rule"] = m["rule"].astype(str)
    for (rid, k), g in m.groupby(["rule", "k"], sort=False, observed=True):
        key = (str(rid), int(k))
        rec = out.setdefault(key, {"id": f"{rid}@k{int(k)}", "held_symbols_by_date": {},
                                   "weights_by_date": {}, "risk_off_dates": [],
                                   "monthly_return_series": []})
        g = g.sort_values("date")
        rec["monthly_return_series"] = [
            {"date": str(pd.Timestamp(d).date()), "gross": float(gr), "cost": float(c),
             "net": float(n), "rebalanced": bool(rb)}
            for d, gr, c, n, rb in zip(g["date"], g["gross"], g["cost"], g["net"], g["rebalanced"])]
    return out


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


# ── the twin's cost: ONE convention, imported by every board (2026-10-06) ───

#: How a matched twin is charged for trading. Every board that nets a twin imports this
#: constant and the functions below; none re-types the arithmetic (CHUNK C1 of
#: `ROADMAP_2026-10-06_V1_BETA`). Read `twin_cost_convention.__doc__` for the full statement.
TWIN_COST_CONVENTION = "OWN_TURNOVER_SAME_COST_MODEL"

#: The four numbers every rule-vs-twin board row prints, side by side, in this order.
#: The last is an UPPER BOUND on the twin's cost, kept for comparison with the 09-29/09-30
#: boards and never read by a verdict.
FOUR_COLUMNS = ("pure_selection", "fair_twin_net", "net_minus_market",
                "twin_full_round_trip_UPPER_BOUND")
#: the column no verdict may read
UPPER_BOUND_COLUMN = FOUR_COLUMNS[3]


def twin_cost_convention() -> str:
    """The twin pays the SAME cost model as the rule it is matched to, on ITS OWN measured
    turnover -- never a flat full round trip every month.

    * Per-trade cost model (shared by rule and twin): each traded weight |w_t - w_{t-1}|
      pays half of that name's round-trip spread; the round trip is the board's per-name
      spread (on the CRSP boards max(Corwin-Schultz at the decision date, capped, the flat
      6/10/18/35 bps band) -- the turnover-scaled Corwin-Schultz variant). `trade_cost`.
    * Turnover: the twin's OWN one-way turnover, measured on the twin held as a portfolio
      (weights drift between rebalances, a name is traded only when its weight changes).
      A twin that holds still pays nothing; a twin whose turnover equals its rule's pays
      what the rule pays on the same spreads. `turnover_cost`, `turnover_scaled_net`.
    * Why: until 2026-10-06 the bridges board charged the twin the full Corwin-Schultz
      round trip every month (Corwin-Schultz subtracted from every name's forward return)
      while the rule paid only its own 10-50% turnover. A low-turnover rule then "beat"
      its twin by the twin's cost alone: 106 of 161 rules at t >= 2, 18 on gross selection
      (`hyp_lab/twin_board_SUMMARY_TB_2026-09-30_1.json`).
    * The old charge survives ONLY as `twin_full_round_trip_upper_bound`, printed in the
      `UPPER_BOUND_COLUMN` for comparison. No verdict reads it.
    """
    return TWIN_COST_CONVENTION


def trade_cost(prev_w: dict, w: dict, spread: dict, default: float) -> tuple[float, float]:
    """(cost, one-way turnover) of moving from `prev_w` to `w`: each |dw| pays half its
    name's round-trip spread (`default` when the name has none). The ONE per-trade model
    for a rule and for its twin."""
    cost, to = 0.0, 0.0
    for s in set(prev_w) | set(w):
        dw = abs(w.get(s, 0.0) - prev_w.get(s, 0.0))
        if dw:
            sp = spread.get(s, default)
            cost += dw * (sp if np.isfinite(sp) else default) / 2.0
            to += dw
    return cost, to / 2.0


def turnover_cost(turnover, round_trip):
    """Cost of `turnover` (one-way, fraction of the book) at `round_trip` spread:
    turnover x round_trip (buying and selling `turnover` each pay half the round trip).
    Scalars or aligned Series. A missing turnover REFUSES: defaulting it to 1.0 is the
    full-round-trip charge this convention replaced."""
    if turnover is None:
        raise TwinInputMissing("turnover is missing: refusing to default it to a full round trip")
    t = turnover.astype(float) if isinstance(turnover, pd.Series) else float(turnover)
    if (np.any(np.asarray(t) < 0)) or (not isinstance(t, pd.Series) and not np.isfinite(t)):
        raise TwinInputMissing(f"turnover must be finite and >= 0, got {turnover!r}")
    return t * round_trip


def turnover_scaled_net(flat_net, full_rt_net, turnover):
    """Net under the turnover-scaled spread model from two runs of the SAME book: one at
    flat costs (`flat_net`) and one charged the full spread round trip every month
    (`full_rt_net`). The full-round-trip charge (flat - full) is scaled to the book's own
    `turnover`. Applied with the SAME function to a rule and to its twin."""
    return flat_net - turnover_cost(turnover, flat_net - full_rt_net)


def twin_full_round_trip_upper_bound(w: dict, spread: dict, default: float) -> float:
    """The old charge: one full round trip on every twin name, every month. UPPER BOUND
    only (printed in `UPPER_BOUND_COLUMN`); no verdict reads it."""
    return float(sum(v * (spread.get(s, default) if np.isfinite(spread.get(s, default)) else default)
                     for s, v in w.items()))


def four_columns(rule_gross: pd.Series, rule_cost: pd.Series, twin_gross: pd.Series,
                 twin_cost: pd.Series, twin_full_rt: pd.Series, market: pd.Series) -> pd.DataFrame:
    """The four monthly series every board row prints (`FOUR_COLUMNS`):
    pure selection (rule gross - twin gross), the fair twin (rule net - twin net, both
    under `twin_cost_convention`), rule net - market (market costless), and the UPPER
    BOUND (rule net - (twin gross - a full round trip every month))."""
    rn = rule_gross - rule_cost
    return pd.DataFrame({FOUR_COLUMNS[0]: rule_gross - twin_gross,
                         FOUR_COLUMNS[1]: rn - (twin_gross - twin_cost),
                         FOUR_COLUMNS[2]: rn - market,
                         FOUR_COLUMNS[3]: rn - (twin_gross - twin_full_rt)})


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
