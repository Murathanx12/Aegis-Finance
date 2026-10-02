"""hyp_cells: the parameterised test designs hyp_lab can run without a human.

Three cell types. Each takes a params dict (declared in a receipt BEFORE it runs), reads only
data on disk, and returns a result dict with a design-fold reading, a confirm-fold reading and a
verdict computed by the SAME rule for every hypothesis of that type:

* ``macro_lead_lag``   a driver shock at close t (oil, the 10-year yield, a stock basket) ->
                       does a target basket move from open t+1 to close t+h BEYOND its market
                       beta, in the declared direction? The same-day response (ordinary beta)
                       is printed beside it so "the link exists" and "the link is slow" are
                       never confused.
* ``event_readthrough`` a big earnings reaction of a source name on session t -> do LINKED names
                       (co-mentioned in documents published before t, or the 252-session
                       return-correlation peers as the factor-beta control) move more than
                       their own volatility on t+1, and which way, against vol-matched unlinked
                       names on the same dates?
* ``size_feature_increment`` a cell-level feature known before the entry open -> does it add
                       rank IC for |next-session move| over the trailing priors + TF-IDF model
                       (T2, the bar to beat), paired per date, SE over weekly blocks?

Verdict vocabulary (CLAUDE.md "explore dirty, promote clean"): CONDITIONAL_POSITIVE,
FAILED_VARIANT, CANNOT_DISTINGUISH, REFUSED. MDE = 2.8 x SE beside every t.
Licence PRODUCT_EXPERIMENT. Nothing here trades.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from backend import config as C

REPO = C.PROJECT_ROOT  # honours AEGIS_REPO_ROOT (frozen-path family)
OPT = C.DATA_DIR / "optimus"
BARS = OPT / "prices_deep" / "bars.parquet"
PANEL = OPT / "text_return_panel" / "news_returns_2025_26.parquet"
MACRO = OPT / "hyp_lab" / "macro_daily_yf.parquet"
FT_WORK = REPO / "ft_lab" / "data"
CELLS = FT_WORK / "cells.parquet"
BULK = FT_WORK / "bulk_events.jsonl"
PREDS_2026 = FT_WORK / "preds_baselines.parquet"
HYP_WORK = OPT / "hyp_lab" / "work"
EPS = 1e-4

#: folds for the size cells (inclusive entry_date bounds). F2026 is ft_lab's primary fold
#: (its T2 predictions are on disk); F2025 is ft_lab's early fold (T2 refit here, cached).
FOLDS = {
    "F2025": {"fit": ("2025-01-02", "2025-05-31"), "val": ("2025-06-16", "2025-08-15"),
              "test": ("2025-09-02", "2025-12-31")},
    "F2026": {"fit": ("2025-01-02", "2025-12-31"), "val": ("2026-01-16", "2026-04-30"),
              "test": ("2026-05-15", "2026-09-28")},
}

CELL_TYPES = ("macro_lead_lag", "event_readthrough", "size_feature_increment")


# ============================================================== statistics
def block_stats(values: pd.Series, blocks) -> dict:
    """Mean of per-observation values with SE from block means (weeks or months)."""
    s = pd.Series(np.asarray(values, dtype=float))
    b = pd.Series(np.asarray(blocks))
    ok = s.notna().values
    s, b = s[ok], b[ok]
    if len(s) == 0:
        return {"mean": None, "se": None, "t": None, "mde": None, "n": 0, "n_blocks": 0}
    bm = s.groupby(b.values).mean()
    nb = len(bm)
    se = float(bm.std(ddof=1) / np.sqrt(nb)) if nb > 1 else None
    m = float(s.mean())
    return {"mean": round(m, 6), "se": None if se is None else round(se, 6),
            "t": None if not se else round(m / se, 2),
            "mde": None if se is None else round(2.8 * se, 6), "n": int(len(s)), "n_blocks": int(nb)}


def by_period(values, dates, fmt: str = "%Y") -> dict:
    s = pd.Series(np.asarray(values, dtype=float), index=pd.to_datetime(pd.Index(dates)))
    s = s.dropna()
    if s.empty:
        return {}
    g = s.groupby(s.index.strftime(fmt)).agg(["mean", "count"])
    return {k: {"mean": round(float(v["mean"]), 6), "n": int(v["count"])} for k, v in g.iterrows()}


def loo_worst(values, dates, fmt: str = "%Y") -> float | None:
    s = pd.Series(np.asarray(values, dtype=float), index=pd.to_datetime(pd.Index(dates))).dropna()
    keys = s.index.strftime(fmt)
    uk = sorted(set(keys))
    if len(uk) < 2:
        return None
    return round(float(min(s[keys != k].mean() for k in uk)), 6)


def verdict(design: dict, confirm: dict, min_effect: float) -> dict:
    """One rule for every cell: the design fold only fixes the sign and the effect to look for;
    the confirm fold decides.

    CONDITIONAL_POSITIVE  confirm mean > 0, confirm t >= 2 and design mean > 0.
    FAILED_VARIANT        confirm mean <= 0, or confirm t < 2 with confirm MDE <= the effect
                          size worth having (max(design mean, min_effect)).
    CANNOT_DISTINGUISH    otherwise (the confirm fold cannot see an effect of that size).
    """
    dm, cm, ct, cmde = design.get("mean"), confirm.get("mean"), confirm.get("t"), confirm.get("mde")
    if cm is None or ct is None or cmde is None:
        return {"verdict": "REFUSED", "reason": "confirm fold has no usable estimate"}
    worth = max(float(dm) if dm is not None else 0.0, float(min_effect))
    if cm > 0 and ct >= 2 and (dm is not None and dm > 0):
        return {"verdict": "CONDITIONAL_POSITIVE", "reason": f"confirm {cm:+.5f} t {ct} and design {dm:+.5f} > 0"}
    if cm <= 0:
        return {"verdict": "FAILED_VARIANT", "reason": f"confirm mean {cm:+.5f} <= 0"}
    if cmde <= worth:
        return {"verdict": "FAILED_VARIANT",
                "reason": f"confirm t {ct} < 2 and MDE {cmde:.5f} <= effect worth having {worth:.5f}"}
    return {"verdict": "CANNOT_DISTINGUISH",
            "reason": f"confirm {cm:+.5f} t {ct}; MDE {cmde:.5f} > effect worth having {worth:.5f}"}


# ============================================================== data (cached per process)
@lru_cache(maxsize=2)
def load_bars(start: str = "2015-06-01") -> pd.DataFrame:
    b = pd.read_parquet(BARS, columns=["symbol", "date", "open", "close"])
    b = b[b["date"] >= pd.Timestamp(start)]
    return b.sort_values(["symbol", "date"]).reset_index(drop=True)


@lru_cache(maxsize=2)
def wide(start: str = "2015-06-01") -> dict:
    """Wide open/close matrices (dates x symbols) and derived daily series."""
    b = load_bars(start)
    op = b.pivot(index="date", columns="symbol", values="open").sort_index()
    cl = b.pivot(index="date", columns="symbol", values="close").sort_index()
    rcc = cl.pct_change(fill_method=None)
    roc = cl / op - 1.0
    spy_oc = roc["SPY"]
    xoc = roc.sub(spy_oc, axis=0)
    absx = xoc.abs()
    vol21 = absx.shift(1).rolling(21, min_periods=10).mean()     # known before session t opens
    return {"open": op, "close": cl, "rcc": rcc, "roc": roc, "xoc": xoc, "vol21": vol21}


@lru_cache(maxsize=1)
def bar_symbols() -> frozenset:
    """The symbols a cell can use (bars panel), cached in a small file next to the ledger."""
    cache = HYP_WORK / "bar_symbols.json"
    if cache.exists() and cache.stat().st_mtime >= BARS.stat().st_mtime:
        return frozenset(json.loads(cache.read_text(encoding="utf-8")))
    syms = sorted(pd.read_parquet(BARS, columns=["symbol"])["symbol"].unique().tolist())
    HYP_WORK.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(syms), encoding="utf-8")
    return frozenset(syms)


def load_macro(path: Path | None = None) -> pd.DataFrame:
    m = pd.read_parquet(path or MACRO)
    m.index = pd.to_datetime(m.index).tz_localize(None)
    return m.sort_index()


# ============================================================== cell 1: macro lead-lag
def _driver_series(driver: str, W: dict, macro: pd.DataFrame | None) -> pd.Series:
    """Daily driver change known at close t. '^TNX' -> yield change (points); a price series or
    'basket:A,B,C' -> equal-weight close-to-close return."""
    if driver.startswith("basket:"):
        syms = [s for s in driver.split(":", 1)[1].split(",") if s in W["rcc"].columns]
        if not syms:
            raise ValueError(f"no basket symbol in bars: {driver}")
        return W["rcc"][syms].mean(axis=1)
    if macro is None or driver not in macro.columns:
        raise ValueError(f"driver {driver!r} not in the macro file")
    s = macro[driver].dropna()
    return s.diff() if driver.startswith("^") else s.pct_change(fill_method=None)


def _target_matrix(targets: list[str], W: dict, macro: pd.DataFrame | None) -> tuple[pd.DataFrame, pd.DataFrame, list]:
    """Open and close of each target on the bars calendar: bar symbols first, 'etf:X' from the
    macro file (close only: its 'open' is the previous close, so an etf: target's t+1 window is
    close t -> close t+h and is flagged)."""
    op, cl, used = {}, {}, []
    for t in targets:
        if t.startswith("etf:"):
            k = t[4:]
            if macro is not None and k in macro.columns:
                s = macro[k].reindex(W["close"].index).ffill(limit=2)
                cl[t], op[t] = s, s.shift(1)
                used.append(t)
        elif t in W["close"].columns:
            op[t], cl[t] = W["open"][t], W["close"][t]
            used.append(t)
    return pd.DataFrame(op), pd.DataFrame(cl), used


def macro_lead_lag(params: dict, W: dict | None = None, macro: pd.DataFrame | None = None) -> dict:
    """params: driver, targets, expected_sign (+1/-1 = target move per driver move), h (1 or 5),
    shock_z (default 2), design_end, confirm_start, cost_bps_round_trip (default 20)."""
    W = W or wide()
    if macro is None and MACRO.exists():
        macro = load_macro()
    h = int(params.get("h", 1))
    z_cut = float(params.get("shock_z", 2.0))
    esign = int(params["expected_sign"])
    design_end = pd.Timestamp(params.get("design_end", "2022-12-31"))
    confirm_start = pd.Timestamp(params.get("confirm_start", "2023-01-01"))
    cost = float(params.get("cost_bps_round_trip", 20)) / 1e4

    cal = W["close"].index
    d = _driver_series(params["driver"], W, macro).reindex(cal)
    sd = d.shift(1).rolling(63, min_periods=40).std()                # known before t
    z = d / sd
    op, cl, used = _target_matrix(list(params["targets"]), W, macro)
    if not used:
        return {"verdict": "REFUSED", "reason": "no target in bars or macro file"}
    spy_o, spy_c = W["open"]["SPY"], W["close"]["SPY"]
    # window open(t+1) -> close(t+h), aligned to t
    tgt = (cl.shift(-h) / op.shift(-1) - 1.0).mean(axis=1)
    spy = spy_c.shift(-h) / spy_o.shift(-1) - 1.0
    same = (cl / cl.shift(1) - 1.0).mean(axis=1)                        # close t-1 -> close t
    spy_same = spy_c / spy_c.shift(1) - 1.0
    # beta of the basket to SPY on DESIGN days only (no confirm information)
    dz = pd.DataFrame({"t": same, "s": spy_same}).dropna()
    dz = dz[dz.index <= design_end]
    beta = float(np.cov(dz["t"], dz["s"])[0, 1] / np.var(dz["s"], ddof=1)) if len(dz) > 100 else 1.0
    resid_next = tgt - beta * spy
    resid_same = same - beta * spy_same
    df = pd.DataFrame({"z": z, "d": d, "next": resid_next, "same": resid_same}).dropna()
    shocks = df[df["z"].abs() >= z_cut].copy()
    shocks["signed_next"] = np.sign(shocks["d"]) * esign * shocks["next"]
    shocks["signed_same"] = np.sign(shocks["d"]) * esign * shocks["same"]
    shocks["month"] = shocks.index.strftime("%Y-%m")
    placebo = df.copy()
    placebo["signed_next"] = np.sign(placebo["d"]) * esign * placebo["next"]

    def fold(mask):
        s = shocks[mask(shocks.index)]
        p = placebo[mask(placebo.index)]
        prim = block_stats(s["signed_next"], s["month"])
        return {"primary_signed_next_resid": prim,
                "net_of_cost": None if prim["mean"] is None else round(prim["mean"] - cost, 6),
                "same_day_signed_resid (ordinary beta, not tradable)": block_stats(s["signed_same"], s["month"]),
                "placebo_all_days_signed_next": block_stats(p["signed_next"], p.index.strftime("%Y-%m")),
                "n_shocks": int(len(s)), "by_year": by_period(s["signed_next"], s.index),
                "loo_year_worst": loo_worst(s["signed_next"], s.index),
                "span": [str(s.index.min().date()) if len(s) else None,
                         str(s.index.max().date()) if len(s) else None]}

    des = fold(lambda ix: ix <= design_end)
    con = fold(lambda ix: ix >= confirm_start)
    v = verdict(des["primary_signed_next_resid"], con["primary_signed_next_resid"],
                min_effect=float(params.get("min_effect", cost)))
    return {"cell_type": "macro_lead_lag", "params": params, "targets_used": used,
            "beta_to_spy_design": round(beta, 3),
            "window": f"open(t+1) -> close(t+{h}), residual of beta x SPY; etf: targets use close t -> close t+{h}",
            "design": des, "confirm": con, **v}


# ============================================================== cell 2: event read-through
@lru_cache(maxsize=1)
def student_labels() -> pd.DataFrame:
    rows = []
    with open(BULK, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("source") != "panel_cell_first_doc" or not r.get("valid"):
                continue
            rows.append((r["symbol"], r["entry_date"], r.get("event_type"), r.get("direction")))
    lab = pd.DataFrame(rows, columns=["symbol", "entry_date", "event_type", "direction"])
    return lab.drop_duplicates(["symbol", "entry_date"], keep="last")


@lru_cache(maxsize=1)
def comention_docs() -> pd.DataFrame:
    """(uid, symbol, first_date) for documents that name 2+ symbols. first_date = the earliest of
    publication and first-seen, as a date; a link may only be used from the NEXT session on."""
    p = pd.read_parquet(PANEL, columns=["uid", "symbol", "published_utc", "first_seen_utc", "pit_grade"])
    p = p[p["pit_grade"].fillna("") != "archive"]
    n = p.groupby("uid")["symbol"].transform("nunique")
    p = p[n >= 2].copy()
    pub = pd.to_datetime(p["published_utc"], errors="coerce", utc=True)
    seen = pd.to_datetime(p["first_seen_utc"], errors="coerce", utc=True)
    known = pd.concat([pub, seen], axis=1).max(axis=1)      # the LATER of the two: known by then for sure
    p["known_date"] = known.dt.tz_convert(None).dt.normalize()
    return p.dropna(subset=["known_date"])[["uid", "symbol", "known_date"]]


def comention_links(src: str, t: pd.Timestamp, docs: pd.DataFrame, lookback_days: int, k: int) -> list[str]:
    """Symbols co-mentioned with `src` in documents known strictly BEFORE t (by >= 1 day), within
    the lookback. Ranked by count of distinct documents."""
    lo = t - pd.Timedelta(days=lookback_days)
    u = docs[(docs["symbol"] == src) & (docs["known_date"] < t) & (docs["known_date"] >= lo)]["uid"]
    if u.empty:
        return []
    o = docs[docs["uid"].isin(set(u)) & (docs["symbol"] != src) & (docs["known_date"] < t)]
    return o.groupby("symbol")["uid"].nunique().sort_values(ascending=False).index[:k].tolist()


def corr_links(src: str, t: pd.Timestamp, rcc: pd.DataFrame, k: int, window: int = 252) -> list[str]:
    ix = rcc.index
    pos = ix.searchsorted(t)                      # rows strictly before t
    blk = rcc.iloc[max(0, pos - window):pos]
    if src not in blk.columns or blk[src].notna().sum() < window // 2:
        return []
    ok = blk.notna().sum() >= window // 2
    blk = blk.loc[:, ok]
    x = blk[src]
    Z = blk.sub(blk.mean()).div(blk.std(ddof=0))
    zx = (x - x.mean()) / x.std(ddof=0)
    c = Z.mul(zx, axis=0).mean().drop(labels=[src, "SPY", "QQQ", "IWM", "DIA"], errors="ignore")
    return c.dropna().sort_values(ascending=False).index[:k].tolist()


def event_readthrough(params: dict, W: dict | None = None, cells: pd.DataFrame | None = None,
                      labels: pd.DataFrame | None = None, docs: pd.DataFrame | None = None,
                      seed: int = 20260930) -> dict:
    """params: link ('comention' | 'corr_peer'), event_type (default earnings_report),
    min_ratio (|x_oc| / vol21 of the source, default 3), min_source_dv_pct (default 0.5 = the
    source's trailing dollar volume above the date's cell median), lookback_days (180), k (5),
    design (2025 bounds), confirm (2026 bounds), n_controls (10)."""
    W = W or wide("2024-01-01")
    cells = cells if cells is not None else pd.read_parquet(
        CELLS, columns=["symbol", "entry_date", "x_oc", "vol21_absx", "dv21", "split"])
    labels = labels if labels is not None else student_labels()
    link = params.get("link", "comention")
    if link == "comention" and docs is None:
        docs = comention_docs()
    ev = cells.merge(labels, on=["symbol", "entry_date"], how="inner")
    ev = ev[ev["event_type"] == params.get("event_type", "earnings_report")].copy()
    ev["ratio"] = ev["x_oc"].abs() / ev["vol21_absx"]
    dv_med = cells.groupby("entry_date")["dv21"].transform("median")
    cells = cells.assign(dv_med=dv_med)
    ev = ev.merge(cells[["symbol", "entry_date", "dv_med"]], on=["symbol", "entry_date"], how="left")
    ev = ev[(ev["ratio"] >= float(params.get("min_ratio", 3.0)))]
    if float(params.get("min_source_dv_pct", 0.5)) > 0:
        ev = ev[ev["dv21"] >= ev["dv_med"]]
    ev["t"] = pd.to_datetime(ev["entry_date"])
    ev = ev[ev["t"].isin(W["close"].index)]
    xoc, vol = W["xoc"], W["vol21"]
    cal = W["close"].index
    rng = np.random.default_rng(seed)
    k, look = int(params.get("k", 5)), int(params.get("lookback_days", 180))
    ncon = int(params.get("n_controls", 10))
    rows = []
    for e in ev.itertuples():
        pos = cal.searchsorted(e.t)
        if pos + 1 >= len(cal):
            continue
        t1 = cal[pos + 1]
        links = (comention_links(e.symbol, e.t, docs, look, k) if link == "comention"
                 else corr_links(e.symbol, e.t, W["rcc"], k))
        links = [s for s in links if s in xoc.columns]
        if not links:
            continue
        # outcomes on t+1: relative size log(|x| / vol21) and signed move (source's sign)
        v1 = vol.loc[t1]
        x1 = xoc.loc[t1]
        rel1 = np.log(x1.abs() + EPS) - np.log(v1 + EPS)
        x0 = xoc.loc[e.t]
        rel0 = np.log(x0.abs() + EPS) - np.log(vol.loc[e.t] + EPS)
        ok = rel1.notna() & rel0.notna()
        lk = [s for s in links if ok.get(s, False)]
        if not lk:
            continue
        # vol-matched controls: same date, same vol21 decile at t+1, not linked, not the source
        dec = pd.qcut(v1[ok].rank(method="first"), 10, labels=False)
        pool = dec.index.difference(pd.Index(lk + [e.symbol]))
        ctrl = []
        for s in lk:
            same = pool[dec.reindex(pool).values == dec.get(s)]
            if len(same):
                ctrl.extend(rng.choice(same, size=min(ncon, len(same)), replace=False).tolist())
        if not ctrl:
            continue
        sgn = float(np.sign(e.x_oc))
        rows.append({
            "t": e.t, "source": e.symbol, "n_links": len(lk), "links": ",".join(lk),
            "size_t1": float(rel1[lk].mean() - rel1[ctrl].mean()),
            "size_t0": float(rel0[lk].mean() - rel0[ctrl].mean()),
            "signed_t1": float(sgn * (x1[lk].mean() - x1[ctrl].mean())),
            "signed_t0": float(sgn * (x0[lk].mean() - x0[ctrl].mean())),
        })
    R = pd.DataFrame(rows)
    if R.empty:
        return {"cell_type": "event_readthrough", "params": params, "verdict": "REFUSED",
                "reason": "no event with a usable link", "n_events_candidate": int(len(ev))}
    R["week"] = R["t"].dt.to_period("W-FRI").astype(str)
    dz = params.get("design", ["2025-01-01", "2025-12-31"])
    cz = params.get("confirm", ["2026-01-01", "2026-12-31"])

    def fold(lo, hi):
        s = R[(R["t"] >= pd.Timestamp(lo)) & (R["t"] <= pd.Timestamp(hi))]
        return {"primary_size_t1_vs_volmatched": block_stats(s["size_t1"], s["week"]),
                "signed_t1_vs_volmatched (direction, reported)": block_stats(s["signed_t1"], s["week"]),
                "size_t0_same_session (reported)": block_stats(s["size_t0"], s["week"]),
                "signed_t0_same_session (reported)": block_stats(s["signed_t0"], s["week"]),
                "n_events": int(len(s)), "mean_links": round(float(s["n_links"].mean()), 2) if len(s) else None,
                "by_month_size_t1": by_period(s["size_t1"], s["t"], "%Y-%m"),
                "loo_month_worst_size_t1": loo_worst(s["size_t1"], s["t"], "%Y-%m")}

    des, con = fold(*dz), fold(*cz)
    v = verdict(des["primary_size_t1_vs_volmatched"], con["primary_size_t1_vs_volmatched"],
                min_effect=float(params.get("min_effect", 0.05)))
    # the direction line gets its own verdict, reported, never deciding
    vd = verdict(des["signed_t1_vs_volmatched (direction, reported)"],
                 con["signed_t1_vs_volmatched (direction, reported)"],
                 min_effect=float(params.get("min_effect_dir", 0.002)))
    return {"cell_type": "event_readthrough", "params": params,
            "outcome_units": "size: log(|x_oc|/vol21) linked minus vol-matched unlinked, same date; "
                             "signed: sign(source move) x (x_oc linked - x_oc controls)",
            "n_events_candidate": int(len(ev)), "design": des, "confirm": con, **v,
            "direction_verdict_reported": vd,
            "examples": R.sort_values("size_t1", ascending=False).head(5)[["t", "source", "links", "size_t1"]]
            .astype(str).to_dict("records")}


# ============================================================== cell 3: size-feature increment
_POS = set("""beat beats surge surges surged soar soars soared record upgrade upgraded upgrades raise raises raised
strong stronger strength growth profit profitable gain gains gained jump jumps jumped rally rallies rallied
outperform outperforms exceed exceeds exceeded boost boosts boosted approval approved approves win wins won
bullish rise rises rising rose expand expands expansion accelerate accelerates breakthrough buyback
optimistic upbeat robust momentum tops topped climbs climbed higher best improve improved improves""".split())
_NEG = set("""miss misses missed plunge plunges plunged fall falls fell falling drop drops dropped cut cuts
downgrade downgraded downgrades weak weaker weakness loss losses decline declines declined lawsuit probe
investigation recall bearish lower warn warns warned warning halt halted delay delays delayed layoffs
bankruptcy default fraud slump slumps tumble tumbles tumbled sink sinks sank disappoint disappoints
disappointing concern concerns selloff sell-off worst slide slides slid crash crashes pressure pressured
lawsuit subpoena dilution offering shortfall""".split())
_TOK = re.compile(r"[a-z][a-z\-]+")


def lexicon_tone(text: str) -> float:
    w = _TOK.findall((text or "").lower())
    p = sum(1 for x in w if x in _POS)
    n = sum(1 for x in w if x in _NEG)
    return (p - n) / (p + n + 1.0)


def attention_features(cells: pd.DataFrame, panel: pd.DataFrame | None = None) -> pd.DataFrame:
    """abn_attention: log1p(documents in the cell) minus log1p(the symbol's mean daily document
    count over the previous 60 calendar days, zeros included); src_prior5: distinct sources in
    the 5 days before the entry date; both from documents dated BEFORE or in the cell (the cell's
    own documents are published before its entry open by construction of the panel)."""
    p = panel if panel is not None else pd.read_parquet(PANEL, columns=["symbol", "entry_date", "source", "pit_grade"])
    p = p[p["pit_grade"].fillna("") != "archive"]
    daily = p.groupby(["symbol", "entry_date"]).agg(n=("source", "size"), ns=("source", "nunique")).reset_index()
    daily["d"] = pd.to_datetime(daily["entry_date"])
    out = []
    for sym, g in daily.groupby("symbol", sort=False):
        s = g.set_index("d")["n"].asfreq("D", fill_value=0)
        prev60 = s.shift(1).rolling(60, min_periods=1).mean()
        ns = g.set_index("d")["ns"].asfreq("D", fill_value=0)
        prev5 = ns.shift(1).rolling(5, min_periods=1).sum()
        out.append(pd.DataFrame({"symbol": sym, "entry_date": s.index.strftime("%Y-%m-%d"),
                                 "prev60": prev60.values, "prev5_src": prev5.values}))
    a = pd.concat(out)
    c = cells[["symbol", "entry_date", "n_docs"]].merge(a, on=["symbol", "entry_date"], how="left")
    c["abn_attention"] = np.log1p(c["n_docs"]) - np.log1p(c["prev60"].fillna(0))
    c["src_prior5"] = np.log1p(c["prev5_src"].fillna(0))
    return c[["symbol", "entry_date", "abn_attention", "src_prior5"]]


def tone_features(cells: pd.DataFrame, panel: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per-document lexicon tone over every non-archive document in the cell; the cell gets the
    sd across documents (0 with one document), |mean|, share of documents whose sign opposes the
    mean, and a multi-document flag."""
    p = panel if panel is not None else pd.read_parquet(
        PANEL, columns=["symbol", "entry_date", "title", "body", "pit_grade"])
    p = p[p["pit_grade"].fillna("") != "archive"].copy()
    p["tone"] = [lexicon_tone(f"{a} {b}") for a, b in zip(p["title"].fillna(""), p["body"].fillna("").str[:1500])]
    g = p.groupby(["symbol", "entry_date"])["tone"]
    f = pd.DataFrame({"tone_mean": g.mean(), "tone_sd": g.std(ddof=0), "n": g.size()}).reset_index()
    opp = p.merge(f[["symbol", "entry_date", "tone_mean"]], on=["symbol", "entry_date"])
    opp["opp"] = (np.sign(opp["tone"]) * np.sign(opp["tone_mean"]) < 0).astype(float)
    f = f.merge(opp.groupby(["symbol", "entry_date"])["opp"].mean().rename("tone_oppose").reset_index(),
                on=["symbol", "entry_date"])
    f["tone_abs"] = f["tone_mean"].abs()
    f["tone_sd"] = f["tone_sd"].fillna(0.0)
    f["multi_doc"] = (f["n"] > 1).astype(float)
    return cells[["symbol", "entry_date"]].merge(
        f[["symbol", "entry_date", "tone_sd", "tone_abs", "tone_oppose", "multi_doc"]],
        on=["symbol", "entry_date"], how="left")


def event_prior_features(cells: pd.DataFrame, fit_mask: pd.Series, labels: pd.DataFrame | None = None) -> pd.DataFrame:
    """Student event type -> target-encoded mean `rel` (log |move| / trailing vol) on the FIT block
    only (types with < 30 fit cells pooled to 'other'), plus an earnings flag."""
    labels = labels if labels is not None else student_labels()
    c = cells[["symbol", "entry_date", "rel"]].merge(labels[["symbol", "entry_date", "event_type"]],
                                                     on=["symbol", "entry_date"], how="left")
    c["event_type"] = c["event_type"].fillna("unlabelled")
    fit = c[fit_mask.values]
    cnt = fit["event_type"].value_counts()
    keep = set(cnt[cnt >= 30].index)
    c["et"] = np.where(c["event_type"].isin(keep), c["event_type"], "other")
    enc = fit.assign(et=np.where(fit["event_type"].isin(keep), fit["event_type"], "other")) \
        .groupby("et")["rel"].mean()
    base = float(fit["rel"].mean())
    c["event_prior"] = c["et"].map(enc).fillna(base) - base
    c["earnings_flag"] = (c["event_type"] == "earnings_report").astype(float)
    return c[["symbol", "entry_date", "event_prior", "earnings_flag"]]


def _in(d: pd.Series, lo: str, hi: str) -> pd.Series:
    return (d >= lo) & (d <= hi)


def _per_date_ic(df: pd.DataFrame, pred: str, target: str = "y", min_cells: int = 8) -> pd.Series:
    out = {}
    for d, g in df.groupby("entry_date"):
        g = g[[pred, target]].dropna()
        if len(g) < min_cells or g[pred].nunique() < 2:
            continue
        out[d] = g[pred].rank().corr(g[target].rank())
    return pd.Series(out, dtype=float)


def ic_increment(df: pd.DataFrame, a: str, b: str) -> dict:
    pa, pb = _per_date_ic(df, a), _per_date_ic(df, b)
    common = pa.index.intersection(pb.index)
    d = pa[common] - pb[common]
    wk = pd.to_datetime(pd.Index(common)).to_period("W-FRI").astype(str)
    res = block_stats(d.values, wk)
    bm = d.groupby(pd.Index(common).str[:7]).mean()
    res["by_month"] = {k: round(float(v), 4) for k, v in bm.items()}
    res["months_positive"] = f"{int((bm > 0).sum())}/{len(bm)}"
    res["loo_month_worst"] = loo_worst(d.values, common, "%Y-%m")
    return res


def t2_predictions(fold: str) -> pd.DataFrame:
    """T2 (trailing priors + news meta + TF-IDF on the residual) for every cell of the fold.
    F2026 is read from ft_lab's saved predictions; F2025 is refit once with ft_lab's own
    recipe (ft_lab.baselines.run_fold via `python -m ft_lab.export_fold_t2`) and read from its cache."""
    if fold == "F2026":
        p = pd.read_parquet(PREDS_2026, columns=["symbol", "entry_date", "B2_trailing_meta", "T2_trailing_meta_tfidf"])
        return p.rename(columns={"B2_trailing_meta": "B2", "T2_trailing_meta_tfidf": "T2"})
    cache = t2_cache_path(fold)
    if cache.exists():
        return pd.read_parquet(cache)
    # 2026-09-30: the refit moved to `ft_lab/export_fold_t2.py` -- a backend
    # module importing ft_lab broke the firewall ft_lab's tests pin.
    raise FileNotFoundError(f"REFUSED: no T2 predictions for {fold} at {cache}; run "
                            f"`python -m ft_lab.export_fold_t2 --fold {fold}` (offline, $0)")


def t2_cache_path(fold: str) -> Path:
    return HYP_WORK / f"t2_{fold}.parquet"


FEATURE_SETS = {
    "abn_attention": ["abn_attention", "src_prior5"],
    "tone_agreement": ["tone_sd", "tone_abs", "tone_oppose", "multi_doc"],
    "event_prior": ["event_prior", "earnings_flag"],
}


def _features(name: str, cells: pd.DataFrame, fit_mask: pd.Series) -> pd.DataFrame:
    if name == "abn_attention":
        return attention_features(cells)
    if name == "tone_agreement":
        return tone_features(cells)
    if name == "event_prior":
        return event_prior_features(cells, fit_mask)
    raise ValueError(f"unknown feature set {name!r}")


def _fold_increment(cells: pd.DataFrame, fold: str, feats: pd.DataFrame, cols: list[str], base: str) -> dict:
    from sklearn.linear_model import Ridge  # noqa: PLC0415
    f = FOLDS[fold]
    t2 = t2_predictions(fold)
    c = cells.merge(t2, on=["symbol", "entry_date"], how="inner").merge(feats, on=["symbol", "entry_date"], how="left")
    fit, val, test = (_in(c["entry_date"], *f[k]) for k in ("fit", "val", "test"))
    X = c[cols].astype(float)
    med = X[fit].median()
    X = X.fillna(med)
    mu, sd = X[fit].mean(), X[fit].std().replace(0, 1)
    X = ((X - mu) / sd).values
    resid = (c["ly"] - c[base]).values
    best = None
    for a in (1.0, 10.0, 100.0, 1000.0, 10000.0):
        m = Ridge(alpha=a).fit(X[fit.values], resid[fit.values])
        c["_cand"] = c[base] + m.predict(X)
        pv = _per_date_ic(c[val], "_cand").mean()
        if best is None or pv > best[0]:
            best = (pv, a, m)
    c["WITH"] = c[base] + best[2].predict(X)
    tst = c[test]
    return {"fold": fold, "base": base, "alpha": best[1], "n_test_cells": int(test.sum()),
            "coef": {k: round(float(v), 5) for k, v in zip(cols, best[2].coef_)},
            "increment": ic_increment(tst, "WITH", base)}


def size_feature_increment(params: dict, cells: pd.DataFrame | None = None) -> dict:
    """params: feature_set (abn_attention | tone_agreement | event_prior), base (T2 default; B2
    reported), design_fold, confirm_fold, min_effect (IC, default 0.002)."""
    cells = cells if cells is not None else pd.read_parquet(
        CELLS, columns=["symbol", "entry_date", "n_docs", "y", "ly", "rel", "split"])
    name = params["feature_set"]
    cols = FEATURE_SETS[name]
    base = params.get("base", "T2")
    out = {"cell_type": "size_feature_increment", "params": params, "features": cols}
    for role in ("design_fold", "confirm_fold"):
        fold = params[role]
        fit_mask = _in(cells["entry_date"], *FOLDS[fold]["fit"])
        feats = _features(name, cells, fit_mask)
        out[role.split("_")[0]] = _fold_increment(cells, fold, feats, cols, base)
        out[role.split("_")[0] + "_over_B2 (reported)"] = _fold_increment(cells, fold, feats, cols, "B2")["increment"]
    v = verdict(out["design"]["increment"], out["confirm"]["increment"],
                min_effect=float(params.get("min_effect", 0.002)))
    out.update(v)
    return out


RUNNERS = {"macro_lead_lag": macro_lead_lag, "event_readthrough": event_readthrough,
           "size_feature_increment": size_feature_increment}


def run_cell(cell_type: str, params: dict) -> dict:
    if cell_type not in RUNNERS:
        return {"verdict": "REFUSED", "reason": f"unknown cell type {cell_type!r}"}
    return RUNNERS[cell_type](params)
