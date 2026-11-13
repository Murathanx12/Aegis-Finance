"""CH-38: the conditional dip study ("down 30% on the 52-week chart, I bought it").

    python -m scripts.ch38_dip_study --data-root C:/Users/mrthn/aegis-finance/backend/data/optimus \
        --out <dir> [--run-id <id>] [--years 1991-2024] [--no-oop]

Licence: PRODUCT_EXPERIMENT, descriptive. $0, no LLM, no network, no broker. Reads
licensed CRSP/WRDS parquet where it already lives (never copied); writes ONLY
`<out>/ch38_dip_study_<run>.json`, `.md` and `_DECLARATION.json`, and refuses an
`--out` inside the data root.

QUESTION. Unconditionally, names far below their 52-week high keep lagging
(George & Hwang 2004). The owner's version is conditional: a high-beta rebound
bet that pays when a fallen MARKET recovers. Which cells, if any, may a frozen
10-name x 5% paper book hold?

DESIGN (every threshold in `backend/config.py` CH38_*, hashed into the
declaration written BEFORE any forward return is computed):
* panel: CRSP daily 1990-2024, every permno of the PIT universe files (dead names
  in), total-return index with the CRSP delisting return booked on the session
  after the last trade (`crsp_rebuild.wide_from_crsp`, unchanged). Survivorship
  audit printed first.
* signal date d = the last session of each month. Dip: close / max(trailing 252
  closes) - 1 <= -CH38_DIP_DRAWDOWN. Liquid: price >= CH38_MIN_PRICE and in the top
  CH38_LIQUID_TOP_N by 63-session median dollar volume.
* arm A: the FF value-weighted market (TR index) >= CH38_MARKET_DRAWDOWN below its
  trailing 252-session high at d; arm B: the market was not.
* entry at the NEXT close (d + 1 session); horizons CH38_HORIZONS sessions; a name
  that dies inside the hold carries its delisting value as cash.
* costs: one round trip per event, max(Corwin-Schultz at d capped 20%, flat
  6/10/18/35 bps band) -- `matched_twins.round_trip_spread`, the CRSP boards' rule.
* controls: (1) same-band x same-vol-tercile random twins drawn on the same date
  from the liquid non-dip names (`matched_twins.draw_twins`, the CH-11 verdict
  level), CH38_TWIN_DRAWS draws, each twin paying its own round trip; a band x
  vol x 12-1 tercile twin is printed beside it. (2) a beta-matched market line:
  rf + beta x (market - rf) over the same hold, beta = the name's trailing 252-
  session cov/var on the market (`book_dna.beta_of`'s formula), costless.
* exit rule: hold-only versus a stop at CH38_STOP_SIGMA x the name's trailing
  63-session daily sigma below entry (exit at the close AFTER the first close at
  or below the level, cash at rf after); no averaging down by construction (one
  buy per event, no adds).
* statistics, in this order: by entry year, leave-one-year-out, worst year,
  share of the total by date, THEN the t on NON-OVERLAPPING date blocks (one
  signal month every ceil(H/21) months, every origin) with the MDE beside it.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                           # noqa: E402
from backend.services import matched_twins as MT                # noqa: E402

SCHEMA = "ch38_dip_study/1"
JOB = "ch38_dip_study"
ARMS = ("A_market_fell", "B_company_fell")
VOL_CELLS = ("v1", "v2", "v3", "all", "v3_unprofitable", "v3_profitable")
VERDICT_WORDS = ("ADMIT", "CANNOT_DISTINGUISH", "REJECT")
#: printed on every receipt; every variant that was RUN is counted here
VARIANTS_NOTE = ("one primary specification (thresholds fixed in config before any return was read); labelled "
                 "sweeps: dip 20%/40%, market 5%/15%, nominal 20 M USD floor; one stop rule (3 sigma); two twin "
                 "levels (band x vol = verdict, band x vol x 12-1 = printed)")


class Refused(RuntimeError):
    """An input the study needs is missing or inconsistent: the run exits non-zero."""


def say(*a: Any) -> None:
    print(*a, flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def params() -> dict:
    c = _config
    return {
        "dip_drawdown": float(c.CH38_DIP_DRAWDOWN),
        "market_drawdown": float(c.CH38_MARKET_DRAWDOWN),
        "min_price": float(c.CH38_MIN_PRICE),
        "liquid_top_n": int(c.CH38_LIQUID_TOP_N),
        "nominal_dollar_volume": float(c.CH38_NOMINAL_DOLLAR_VOLUME),
        "horizons": [int(h) for h in c.CH38_HORIZONS],
        "vol_window": int(c.CH38_VOL_WINDOW),
        "beta_window": int(c.CH38_BETA_WINDOW),
        "high_window": 252,
        "min_history": 200,
        "stop_sigma": float(c.CH38_STOP_SIGMA),
        "twin_draws": int(c.CH38_TWIN_DRAWS),
        "twin_draws_sweep": 10,
        "seed": int(c.CH38_SEED),
        "sweep_dip_drawdown": [float(x) for x in c.CH38_SWEEP_DIP_DRAWDOWN],
        "sweep_market_drawdown": [float(x) for x in c.CH38_SWEEP_MARKET_DRAWDOWN],
        "alpha": float(c.CH38_ALPHA),
        "power": float(c.CH38_POWER),
        "first_year": int(c.CH38_FIRST_YEAR),
        "last_year": int(c.CH38_LAST_YEAR),
        "cost_bps_by_band": dict(MT_COST_BPS),
        "cs_cap": float(MT.CS_CAP),
    }


#: the flat band (round trip, bps) -- `xs_ranker.COST_BPS_BY_BAND`, read through
#: matched_twin_reeval's own default so the CH-11 ruler and this study agree
MT_COST_BPS = {"mega": 6.0, "large": 10.0, "mid": 18.0, "small": 35.0}

DECISION_RULE = (
    "Per cell (arm x vol cell x horizon), on per-signal-date basket excess (equal weight over the cell's names): "
    "ADMIT iff (i) mean excess over the band x vol twins > 0 AND mean excess over the beta-matched line > 0; "
    "(ii) the twin-excess t >= t_crit(alpha two-sided) at EVERY origin of the non-overlapping date blocks, each "
    "origin with >= 8 blocks; (iii) the leave-one-year-out WORST twin-excess mean > 0; (iv) >= 60% of entry years "
    "with a positive twin excess; (v) the dip-threshold sweep's WORST twin-excess mean for the same arm x cell x "
    "horizon > 0. REJECT iff the twin-excess t <= -t_crit at every origin, OR (twin-excess mean <= 0 AND "
    "beta-excess mean <= 0 AND the leave-one-year-out BEST twin-excess mean <= 0, i.e. no single year's removal "
    "turns it positive). Otherwise CANNOT_DISTINGUISH. Sweeps never admit on their own.")


# ───────────────────────────── statistics (pure) ────────────────────────────

def t_crit(df: int, alpha: float, power: Optional[float] = None) -> float:
    """`matched_twin_reeval.t_crit` (imported lazily: no import cost at module load)."""
    from scripts.matched_twin_reeval import t_crit as _tc            # noqa: PLC0415
    return float(_tc(df, alpha, power))


def block_months(h: int) -> int:
    """Signal months per non-overlapping block for an h-session hold (21 sessions a month)."""
    return max(1, int(math.ceil(int(h) / 21.0)))


def nonoverlap_t(x: pd.Series, pos: pd.Series, k: int, alpha: float, power: float,
                 min_blocks: int = 3) -> list[dict]:
    """t of the mean on NON-OVERLAPPING signal dates, at every origin.

    `x`: one value per signal date (NaN = the cell was empty that date); `pos`:
    the date's index on the full monthly grid. Origin o keeps the dates with
    pos % k == o, so two kept dates are >= k months apart and an h-session hold
    (h <= 21 k) never overlaps the next. The MDE is (t_crit + t_power) x SE."""
    out = []
    xv = np.asarray(x, dtype=float)
    pv = np.asarray(pos, dtype=int)
    for o in range(max(1, int(k))):
        v = xv[(pv % k == o) & np.isfinite(xv)]
        n = int(len(v))
        row: dict = {"origin": o, "n_blocks": n, "mean": float(v.mean()) if n else None,
                     "se": None, "t": None, "mde": None, "t_crit": None}
        if n >= min_blocks:
            sd = float(np.std(v, ddof=1))
            se = sd / math.sqrt(n)
            row.update(se=se, t=(float(v.mean()) / se if se > 0 else None),
                       mde=t_crit(n - 1, alpha, power) * se, t_crit=t_crit(n - 1, alpha))
        out.append(row)
    return out


def by_year(x: pd.Series) -> dict:
    """{entry year: mean of the per-date values, n dates} (keyed on the SIGNAL date's year;
    an h-session hold from a late-year signal is earned partly in the next year)."""
    s = pd.Series(np.asarray(x, dtype=float), index=pd.DatetimeIndex(x.index)).dropna()
    out = {}
    for y, g in s.groupby(s.index.year):
        out[str(int(y))] = {"mean": float(g.mean()), "n": int(len(g)), "sum": float(g.sum())}
    return out


def leave_one_year_out(x: pd.Series) -> dict:
    """Mean of the per-date values with each entry year removed: worst, best, and all."""
    s = pd.Series(np.asarray(x, dtype=float), index=pd.DatetimeIndex(x.index)).dropna()
    yrs = s.index.year
    loo = {}
    for y in sorted(set(yrs.tolist())):
        rest = s[yrs != y]
        if len(rest):
            loo[str(int(y))] = float(rest.mean())
    if not loo:
        return {"worst": None, "worst_dropped": None, "best": None, "best_dropped": None, "all": {}}
    kw = min(loo, key=loo.get)
    kb = max(loo, key=loo.get)
    return {"worst": loo[kw], "worst_dropped": kw, "best": loo[kb], "best_dropped": kb, "all": loo}


def share_by_date(x: pd.Series) -> dict:
    """`crsp_rebuild.share_of_total_by_date` (top 1/5/10% of dates' share of the sum)."""
    from backend.services import crsp_rebuild as CR                  # noqa: PLC0415
    return CR.share_of_total_by_date(pd.Series(np.asarray(x, dtype=float), index=pd.DatetimeIndex(x.index)))


def series_stats(x: pd.Series, pos: pd.Series, h: int, alpha: float, power: float) -> dict:
    """Everything printed for one per-date series, in the order the brief asks: by year, LOO,
    worst year, share by date, then the non-overlapping t with the MDE."""
    s = pd.Series(np.asarray(x, dtype=float), index=pd.DatetimeIndex(x.index))
    ok = s.dropna()
    by = by_year(s)
    worst = min(by.items(), key=lambda kv: kv[1]["mean"]) if by else (None, {"mean": None})
    k = block_months(h)
    org = nonoverlap_t(s, pos, k, alpha, power)
    ts = [o["t"] for o in org if o["t"] is not None]
    return {"n_dates": int(len(ok)), "mean": float(ok.mean()) if len(ok) else None,
            "by_year": by, "years": len(by), "years_positive": int(sum(1 for v in by.values() if v["mean"] > 0)),
            "loo": leave_one_year_out(s), "worst_year": worst[0], "worst_year_mean": worst[1]["mean"],
            "share_by_date": share_by_date(ok) if len(ok) else {},
            "block_months": k, "origins": org,
            "min_blocks": min((o["n_blocks"] for o in org), default=0),
            "t_min": min(ts) if ts else None, "t_max": max(ts) if ts else None,
            "mde_max": max((o["mde"] for o in org if o["mde"] is not None), default=None)}


def verdict(twin: dict, beta: dict, sweep_worst_mean: Optional[float], alpha: float,
            min_blocks: int = 8) -> tuple[str, str]:
    """The declared rule (DECISION_RULE). Returns (word, the numbers that decide it)."""
    mt, mb = twin.get("mean"), beta.get("mean")
    org = twin.get("origins") or []
    if mt is None or mb is None or not org:
        return "CANNOT_DISTINGUISH", "empty cell"
    tt = [o for o in org if o.get("t") is not None]
    all_t = len(tt) == len(org)
    all_up = all_t and all(o["t"] >= o["t_crit"] for o in tt)
    all_dn = all_t and all(o["t"] <= -o["t_crit"] for o in tt)
    enough = all_t and all(o["n_blocks"] >= min_blocks for o in org)
    loo = twin.get("loo") or {}
    yrs, ypos = twin.get("years") or 0, twin.get("years_positive") or 0
    nums = (f"twin {mt * 100:+.2f}% (t {_fmt(twin.get('t_min'))}..{_fmt(twin.get('t_max'))}, "
            f"MDE<= {_pct(twin.get('mde_max'))}, blocks>= {twin.get('min_blocks')}), beta-line {mb * 100:+.2f}%, "
            f"LOO worst {_pct(loo.get('worst'))} (-{loo.get('worst_dropped')}), LOO best {_pct(loo.get('best'))}, "
            f"years+ {ypos}/{yrs}, sweep worst {_pct(sweep_worst_mean)}")
    if all_dn:
        return "REJECT", "twin t <= -t_crit at every origin; " + nums
    if mt <= 0 and mb <= 0 and loo.get("best") is not None and loo["best"] <= 0:
        return "REJECT", "loses to both controls and no single year's removal turns it positive; " + nums
    if (mt > 0 and mb > 0 and all_up and enough and loo.get("worst") is not None and loo["worst"] > 0
            and yrs and ypos / yrs >= 0.6 and sweep_worst_mean is not None and sweep_worst_mean > 0):
        return "ADMIT", nums
    why = []
    if not (mt > 0 and mb > 0):
        why.append("a control mean <= 0")
    if not all_up:
        why.append("twin t below t_crit at some origin")
    if not enough:
        why.append(f"fewer than {min_blocks} blocks at some origin")
    if not (loo.get("worst") is not None and loo["worst"] > 0):
        why.append("LOO worst <= 0")
    if not (yrs and ypos / yrs >= 0.6):
        why.append("< 60% years positive")
    if not (sweep_worst_mean is not None and sweep_worst_mean > 0):
        why.append("sweep worst <= 0")
    return "CANNOT_DISTINGUISH", "; ".join(why) + "; " + nums


def _fmt(x: Optional[float]) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x:+.2f}"


def _pct(x: Optional[float]) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:+.2f}%"


# ───────────────────────────── per-date features (pure) ─────────────────────

def ffill_cols(C: np.ndarray) -> np.ndarray:
    """Forward-fill each column down the time axis (a dead name keeps its last value = cash)."""
    return pd.DataFrame(C).ffill().to_numpy(dtype=float)


def daily_returns(C: np.ndarray, Cf: np.ndarray) -> np.ndarray:
    """Return on each session a name actually printed, from its previous printed value."""
    prev = np.vstack([np.full((1, C.shape[1]), np.nan), Cf[:-1]])
    with np.errstate(invalid="ignore", divide="ignore"):
        r = C / prev - 1.0
    return np.where(np.isfinite(C), r, np.nan)


def beta_cols(R: np.ndarray, m: np.ndarray, min_obs: int) -> np.ndarray:
    """Per column, cov(r, m) / var(m) with ddof 0 over the rows where r is finite --
    `book_dna.beta_of`'s formula, vectorised. NaN below `min_obs` rows."""
    mask = np.isfinite(R) & np.isfinite(m)[:, None]
    n = mask.sum(axis=0).astype(float)
    M = np.where(mask, m[:, None], 0.0)
    Y = np.where(mask, R, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mx = M.sum(axis=0) / n
        my = Y.sum(axis=0) / n
        dx = np.where(mask, M - mx, 0.0)
        dy = np.where(mask, Y - my, 0.0)
        cov = (dx * dy).sum(axis=0) / n
        var = (dx * dx).sum(axis=0) / n
        b = cov / var
    b[(n < min_obs) | ~(var > 0)] = np.nan
    return b


def date_features(W: dict, i: int, p: dict) -> dict:
    """Features of every column at row i (the signal date), from rows <= i only."""
    C, Cf, R, DV, P, dl = W["C"], W["Cf"], W["R"], W["DV"], W["P"], W["dl"]
    hw, vw, bw = p["high_window"], p["vol_window"], p["beta_window"]
    lo = i - hw + 1
    if lo < 0:
        raise Refused(f"row {i}: fewer than {hw} sessions of history")
    win = C[lo:i + 1]
    nfin = np.isfinite(win).sum(axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        hi = np.nanmax(win, axis=0)
        off = C[i] / hi - 1.0
        mdv = np.nanmedian(np.where(np.isfinite(DV[i - 62:i + 1]), DV[i - 62:i + 1], np.nan), axis=0)
        rv = R[i - vw + 1:i + 1]
        nv = np.isfinite(rv).sum(axis=0)
        vol = np.nanstd(rv, axis=0, ddof=1)
        vol[nv < int(0.8 * vw)] = np.nan
        mom = C[i - 21] / C[i - 251] - 1.0 if i - 251 >= 0 else np.full(C.shape[1], np.nan)
    beta = beta_cols(R[i - bw + 1:i + 1], W["m"][i - bw + 1:i + 1], int(0.6 * bw))
    elig = (np.isfinite(C[i]) & (nfin >= p["min_history"]) & np.isfinite(P[i]) & (P[i] >= p["min_price"])
            & ~dl[i] & np.isfinite(mdv) & (mdv > 0) & np.isfinite(vol) & np.isfinite(off))
    liquid = np.zeros_like(elig)
    idx = np.flatnonzero(elig)
    if len(idx):
        order = idx[np.argsort(-mdv[idx], kind="mergesort")]
        liquid[order[:p["liquid_top_n"]]] = True
    M = W["M"]
    mwin = M[lo:i + 1]
    mkt_dd = float(M[i] / np.nanmax(mwin) - 1.0)
    return {"off": off, "mdv": mdv, "vol": vol, "mom": mom, "beta": beta, "eligible": elig,
            "liquid": liquid, "mkt_dd": mkt_dd, "n_eligible": int(elig.sum()), "n_liquid": int(liquid.sum()),
            "mdv_cut": float(mdv[order[min(len(order), p["liquid_top_n"]) - 1]]) if len(idx) else None}


def forward_returns(W: dict, e: int, cols: np.ndarray, horizons: Iterable[int]) -> np.ndarray:
    """(len(cols), len(horizons)) close-to-close return from the entry close at row e; NaN
    when e + h runs past the calendar. A name that dies carries its delisting value."""
    C, Cf = W["C"], W["Cf"]
    T = C.shape[0]
    ent = C[e, cols]
    out = np.full((len(cols), len(list(horizons))), np.nan)
    for j, h in enumerate(horizons):
        if e + h <= T - 1:
            out[:, j] = Cf[e + h, cols] / ent - 1.0
    return out


def stop_returns(W: dict, e: int, cols: np.ndarray, sigma: np.ndarray, k_sigma: float,
                 horizons: Iterable[int]) -> tuple[np.ndarray, np.ndarray]:
    """Stop at entry x (1 - k_sigma x sigma): exit at the close AFTER the first close at or
    below it (or the horizon's close), cash at rf to the horizon. Returns (returns, stopped)."""
    Cf, RF = W["Cf"], W["RF"]
    T = Cf.shape[0]
    hs = list(horizons)
    ent = W["C"][e, cols]
    lvl = ent * (1.0 - k_sigma * sigma)
    ret = np.full((len(cols), len(hs)), np.nan)
    hit = np.zeros((len(cols), len(hs)), dtype=bool)
    hmax = max(hs)
    last = min(T - 1, e + hmax)
    path = Cf[e + 1:last + 1, cols]                          # rows e+1 .. last
    below = path <= lvl[None, :]
    below &= (lvl > 0)[None, :]
    first = np.where(below.any(axis=0), np.argmax(below, axis=0) + 1, 10 ** 9)   # sessions after entry
    for j, h in enumerate(hs):
        if e + h > T - 1:
            continue
        stopped = first < h
        exit_row = np.where(stopped, e + first + 1, e + h)
        exit_row = np.minimum(exit_row, e + h)
        px = Cf[exit_row, cols]
        cash = RF[e + h] / RF[exit_row]
        ret[:, j] = (px / ent) * cash - 1.0
        hit[:, j] = stopped
    return ret, hit


def tercile_labels(x: np.ndarray) -> np.ndarray:
    """`matched_twins._tercile` labels "1"/"2"/"3"/"na" over the given names."""
    return MT._tercile(pd.Series(x, dtype=float)).to_numpy(dtype=object)


def twin_draws(held: list, pool: list, band: dict, vt: dict, mt: dict, D: int,
               rng: np.random.Generator) -> tuple[np.ndarray, dict]:
    """D draws of `matched_twins.draw_twins` (no new twin maker): returns an index array
    (len(held), D) into `pool` (-1 = no twin) and the fallback counts summed over draws.
    The held order is permuted per draw so no name is always last to choose."""
    syms = list(held) + list(pool)
    cells = pd.DataFrame({"band": [band[s] for s in syms], "vt": [vt[s] for s in syms],
                          "mt": [mt[s] for s in syms]}, index=pd.Index(syms, name="symbol"))
    ci = MT.CellIndex(cells)
    empty = pd.DataFrame({"symbol": []})
    pidx = {s: j for j, s in enumerate(pool)}
    out = np.full((len(held), D), -1, dtype=np.int64)
    counts: dict = {}
    hpos = {s: j for j, s in enumerate(held)}
    for d in range(D):
        order = [held[k] for k in rng.permutation(len(held))]
        pairs, c = MT.draw_twins(order, cells, empty, rng, index=ci)
        for k, v in c.items():
            counts[k] = counts.get(k, 0) + int(v)
        for s, tw, _lv in pairs:
            if tw is not None:
                out[hpos[s], d] = pidx[tw]
    return out, counts


# ───────────────────────────── one signal date ──────────────────────────────

def date_events(W: dict, i: int, p: dict, rng: np.random.Generator, *, cs: Optional[dict] = None,
                with_sweeps: bool = True) -> tuple[Optional[dict], list[pd.DataFrame]]:
    """All dip events of signal row i at the primary and sweep thresholds, with their twins.
    Returns (date record, [event frames])."""
    T = W["C"].shape[0]
    e = i + 1
    if e >= T:
        return None, []
    f = date_features(W, i, p)
    hs = p["horizons"]
    liq = np.flatnonzero(f["liquid"])
    if not len(liq):
        return None, []
    C = W["C"]
    ent_ok = np.isfinite(C[e, liq]) & ~W["dl"][e, liq]
    fwd = forward_returns(W, e, liq, hs)
    fwd[~ent_ok] = np.nan
    syms = W["symbols"][liq]
    band = MT.size_band(f["mdv"][liq])
    flat = np.array([MT_COST_BPS.get(b, MT_COST_BPS["small"]) / 1e4 for b in band])
    csv = np.array([cs.get(s, np.nan) for s in syms], dtype=float) if cs else np.full(len(liq), np.nan)
    rt = MT.round_trip_spread(csv, flat)
    net = fwd - rt[:, None]
    vt = tercile_labels(f["vol"][liq])
    mt = tercile_labels(f["mom"][liq])
    RF, M = W["RF"], W["M"]
    rf_h = np.array([RF[e + h] / RF[e] - 1.0 if e + h <= T - 1 else np.nan for h in hs])
    mk_h = np.array([M[e + h] / M[e] - 1.0 if e + h <= T - 1 else np.nan for h in hs])
    date = pd.Timestamp(W["dates"][i])
    rec = {"date": date, "row": i, "mkt_dd": f["mkt_dd"], "n_eligible": f["n_eligible"], "n_liquid": f["n_liquid"],
           "mdv_cut": f["mdv_cut"], "n_entry_missing": int((~ent_ok).sum())}
    for j, h in enumerate(hs):
        rec[f"rf_{h}"] = float(rf_h[j])
        rec[f"mkt_{h}"] = float(mk_h[j])
    off = f["off"][liq]
    bmap = dict(zip(syms, band))
    vmap = dict(zip(syms, vt))
    mmap = dict(zip(syms, mt))
    one = {s: "x" for s in syms}
    frames = []
    thresholds = [(p["dip_drawdown"], p["twin_draws"], True)]
    if with_sweeps:
        thresholds += [(t, p["twin_draws_sweep"], False) for t in p["sweep_dip_drawdown"]]
    for thr, D, primary in thresholds:
        is_dip = (off <= -thr) & ent_ok & np.isfinite(fwd[:, 0])
        h_ix = np.flatnonzero(is_dip)
        p_ix = np.flatnonzero(~(off <= -thr) & ent_ok)
        rec[f"n_dip_{thr:.2f}"] = int(len(h_ix))
        if not len(h_ix):
            continue
        held, pool = list(syms[h_ix]), list(syms[p_ix])
        tw, counts = twin_draws(held, pool, bmap, vmap, one, D, rng)
        tnet = np.where(tw[:, :, None] >= 0, net[p_ix][np.clip(tw, 0, None)], np.nan)   # (n, D, H)
        ev = pd.DataFrame({"date": date, "thr": thr, "symbol": held, "band": band[h_ix], "vt": vt[h_ix],
                           "off": off[h_ix], "vol": f["vol"][liq][h_ix], "beta": f["beta"][liq][h_ix],
                           "mdv": f["mdv"][liq][h_ix], "rt": rt[h_ix]})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            tmean = np.nanmean(tnet, axis=1)
        for j, h in enumerate(hs):
            ev[f"net_{h}"] = net[h_ix, j]
            ev[f"twin_{h}"] = tmean[:, j]
        rec[f"twin_none_{thr:.2f}"] = int(counts.get("none", 0))
        rec[f"twin_fallback_{thr:.2f}"] = {k: int(v) for k, v in counts.items()}
        if primary:
            sr, sh = stop_returns(W, e, liq[h_ix], f["vol"][liq][h_ix], p["stop_sigma"], hs)
            for j, h in enumerate(hs):
                ev[f"stop_{h}"] = sr[:, j] - rt[h_ix]
                ev[f"stopped_{h}"] = sh[:, j]
            tw2, c2 = twin_draws(held, pool, bmap, vmap, mmap, p["twin_draws_sweep"], rng)
            t2 = np.where(tw2[:, :, None] >= 0, net[p_ix][np.clip(tw2, 0, None)], np.nan)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                t2m = np.nanmean(t2, axis=1)
            for j, h in enumerate(hs):
                ev[f"twin3_{h}"] = t2m[:, j]
            ev["_draws"] = list(tnet.astype(np.float32))         # (D, H) per event, primary only
            rec["twin3_none"] = int(c2.get("none", 0))
        frames.append(ev)
    return rec, frames


# ───────────────────────────── loaders (CRSP, prices_deep) ──────────────────

def ff_daily(root: Path) -> pd.DataFrame:
    ff = pd.read_parquet(root / "wrds" / "ff_factors_daily.parquet", columns=["date", "mktrf", "rf"])
    ff["date"] = pd.to_datetime(ff["date"])
    return ff.set_index("date").astype(float)


def crsp_years(root: Path, y0: int, y1: int, first: int = 1990, last: int = 2024) -> pd.DataFrame:
    frames = []
    for y in range(max(y0, first), min(y1, last) + 1):
        p = root / "wrds" / f"crsp_dsf_{y}.parquet"
        if not p.exists():
            raise Refused(f"missing {p}")
        frames.append(pd.read_parquet(p, columns=["permno", "date", "prc", "ret", "vol", "openprc", "cfacpr"]))
    d = pd.concat(frames, ignore_index=True)
    for c in ("prc", "ret", "vol", "openprc", "cfacpr"):
        d[c] = pd.to_numeric(d[c], errors="coerce").astype("float64")
    return d


def wide_crsp(root: Path, y: int, delist: pd.DataFrame, ff: pd.DataFrame) -> dict:
    """Decision year y: CRSP y-1..y+1 through `crsp_rebuild.wide_from_crsp` (delisting
    returns booked), split into the study's arrays."""
    from backend.services import crsp_rebuild as CR                  # noqa: PLC0415
    daily = crsp_years(root, y - 1, y + 1)
    mret = ff["mktrf"] + ff["rf"]
    Wd = CR.wide_from_crsp(daily, delist, mret)
    del daily
    gc.collect()
    return _study_arrays(Wd["dates"], Wd["symbols"][:-1], Wd["close"][:, :-1], Wd["volume"][:, :-1],
                         Wd["price"][:, :-1], Wd["dl_mask"][:, :-1], Wd["close"][:, -1],
                         ff["rf"].reindex(Wd["dates"]).fillna(0.0).to_numpy(), audit=Wd["audit"])


def _study_arrays(dates, symbols, C, V, P, dl, M, rf_daily, audit: Optional[dict] = None) -> dict:
    C = np.asarray(C, dtype=float)
    Cf = ffill_cols(C)
    R = daily_returns(C, Cf)
    DV = np.where(np.isfinite(C), C * np.asarray(V, dtype=float), np.nan)
    M = np.asarray(M, dtype=float)
    m = np.r_[np.nan, M[1:] / M[:-1] - 1.0]
    RF = np.cumprod(1.0 + np.asarray(rf_daily, dtype=float))
    return {"dates": pd.DatetimeIndex(dates), "symbols": np.asarray(symbols), "C": C, "Cf": Cf, "R": R,
            "DV": DV, "P": np.asarray(P, dtype=float), "dl": np.asarray(dl, dtype=bool), "M": M, "m": m,
            "RF": RF, "audit": audit or {}}


def month_end_rows(dates: pd.DatetimeIndex, year: Optional[int] = None) -> list[int]:
    """Row of the last session of each calendar month (optionally of one year only)."""
    d = pd.DatetimeIndex(dates)
    per = d.to_period("M")
    last = np.r_[per[1:] != per[:-1], True]
    rows = np.flatnonzero(last)
    if year is not None:
        rows = rows[d[rows].year == year]
    return [int(r) for r in rows]


def wide_deep(root: Path, start: str) -> tuple[dict, dict]:
    """prices_deep bars + bars_delisted (adjustment=all) -> the study's arrays; SPY is the
    market. No delisting returns exist there: a name whose bars stop is held at its last
    close (cash), stated on the receipt."""
    pdp = root / "prices_deep"
    frames, src = [], {}
    for name in ("bars.parquet", "bars_delisted.parquet"):
        pth = pdp / name
        if not pth.exists():
            raise Refused(f"missing {pth}")
        b = pd.read_parquet(pth, columns=["symbol", "date", "close", "volume"],
                            filters=[("date", ">=", pd.Timestamp(start))])
        src[name] = {"rows": int(len(b)), "symbols": int(b["symbol"].nunique())}
        frames.append(b)
    b = pd.concat(frames, ignore_index=True).drop_duplicates(["symbol", "date"], keep="first")
    b["date"] = pd.to_datetime(b["date"]).dt.normalize()
    if "SPY" not in set(b["symbol"]):
        raise Refused("SPY absent from prices_deep: no market line")
    cal = pd.DatetimeIndex(sorted(b.loc[b["symbol"] == "SPY", "date"].unique()))
    C = b.pivot(index="date", columns="symbol", values="close").reindex(cal)
    V = b.pivot(index="date", columns="symbol", values="volume").reindex(cal)
    M = C["SPY"].ffill().to_numpy(dtype=float)
    from scripts.matched_twin_reeval import is_etf                     # noqa: PLC0415
    keep = [s for s in C.columns if s not in ("SPY",) and not _safe_is_etf(is_etf, s)]
    C, V = C[keep], V[keep]
    last = C.apply(lambda s: s.last_valid_index())
    src["symbols_kept_after_etf_filter"] = int(len(keep))
    src["symbols_whose_bars_stop_before_calendar_end"] = int((last < cal[-1]).sum())
    src["calendar"] = [str(cal[0].date()), str(cal[-1].date()), int(len(cal))]
    Ca = C.to_numpy(dtype=float)
    W = _study_arrays(cal, np.array(keep, dtype=object), Ca, V.to_numpy(dtype=float), Ca,
                      np.zeros(Ca.shape, dtype=bool), M, np.zeros(len(cal)))
    return W, src


def _safe_is_etf(fn, s: str) -> bool:
    try:
        return bool(fn(s))
    except Exception as exc:                                           # noqa: BLE001
        raise Refused(f"is_etf failed on {s}: {exc}") from exc


def cs_by_date(root: Path) -> dict:
    """{month-end date: {permno symbol: Corwin-Schultz round trip}} from the CRSP boards' file."""
    p = root / "crsp_rebuild" / "followups_daily_FU_2026-09-29T0855Z.parquet"
    if not p.exists():
        raise Refused(f"missing {p} (the CRSP boards' Corwin-Schultz spreads)")
    D = pd.read_parquet(p, columns=["date", "permno", "cs_spread"])
    D["date"] = pd.to_datetime(D["date"])
    D = D.dropna(subset=["cs_spread"])
    out = {}
    for d, g in D.groupby("date"):
        out[pd.Timestamp(d)] = dict(zip([f"{int(x):06d}" for x in g["permno"]], g["cs_spread"].astype(float)))
    return out


def profitability(root: Path) -> pd.DataFrame:
    """WRDS ratio suite: permno, public_date (>= quarter end + 59 days), npm (TTM net income /
    sales). Unprofitable = npm < 0 at the latest public_date <= the signal date."""
    p = root / "wrds" / "bulk" / "wrdsapps__firm_ratio_ccm.parquet"
    if not p.exists():
        raise Refused(f"missing {p}")
    r = pd.read_parquet(p, columns=["permno", "public_date", "npm"])
    r = r.dropna(subset=["permno", "public_date"])
    r["public_date"] = pd.to_datetime(r["public_date"])
    r["permno"] = pd.to_numeric(r["permno"], errors="coerce").astype("int64")
    return r.sort_values("public_date").drop_duplicates(["permno", "public_date"], keep="last")


def attach_profitability(ev: pd.DataFrame, prof: pd.DataFrame, tolerance_days: int = 400) -> pd.Series:
    """1.0 unprofitable, 0.0 profitable, NaN unknown -- as known on the signal date."""
    e = ev[["date", "symbol"]].copy()
    e["permno"] = pd.to_numeric(e["symbol"], errors="coerce")
    e["_i"] = np.arange(len(e))
    e = e.dropna(subset=["permno"])
    e["permno"] = e["permno"].astype("int64")
    e = e.sort_values("date")
    m = pd.merge_asof(e, prof, left_on="date", right_on="public_date", by="permno", direction="backward",
                      tolerance=pd.Timedelta(days=tolerance_days))
    out = np.full(len(ev), np.nan)
    v = m["npm"].to_numpy(dtype=float)
    flag = np.where(np.isfinite(v), (v < 0).astype(float), np.nan)
    out[m["_i"].to_numpy()] = flag
    return pd.Series(out, index=ev.index)


# ───────────────────────────── aggregation ──────────────────────────────────

def cell_mask(ev: pd.DataFrame, cell: str) -> pd.Series:
    if cell == "all":
        return pd.Series(True, index=ev.index)
    if cell in ("v1", "v2", "v3"):
        return ev["vt"].astype(str) == cell[1]
    if cell == "v3_unprofitable":
        return (ev["vt"].astype(str) == "3") & (ev.get("unprof", pd.Series(np.nan, index=ev.index)) == 1.0)
    if cell == "v3_profitable":
        return (ev["vt"].astype(str) == "3") & (ev.get("unprof", pd.Series(np.nan, index=ev.index)) == 0.0)
    raise ValueError(cell)


def basket_series(ev: pd.DataFrame, dates: pd.DataFrame, h: int) -> pd.DataFrame:
    """Per signal date: the equal-weight basket's net, twin, twin3, stop, beta line, raw."""
    g = ev.groupby("date")
    out = pd.DataFrame({"n": g.size(), "net": g[f"net_{h}"].mean(), "twin": g[f"twin_{h}"].mean(),
                        "beta": g["beta"].mean()})
    for c in (f"twin3_{h}", f"stop_{h}", f"stopped_{h}"):
        if c in ev.columns:
            out[c.split("_")[0]] = g[c].mean()
    d = dates.set_index("date")
    rf, mk = d[f"rf_{h}"].reindex(out.index), d[f"mkt_{h}"].reindex(out.index)
    out["rf"], out["mkt"] = rf, mk
    out["line"] = rf + out["beta"] * (mk - rf)
    return out


def draws_by_cell(ev: pd.DataFrame, h_idx: int) -> Optional[np.ndarray]:
    """Mean over signal dates of each twin draw's basket: the twin distribution of the cell's
    mean (the cell is ONE draw; its percentile among these is printed)."""
    if "_draws" not in ev.columns or not len(ev):
        return None
    ev = ev[[isinstance(x, np.ndarray) for x in ev["_draws"]]]
    if not len(ev):
        return None
    per_date = []
    for _d, g in ev.groupby("date"):
        a = np.stack(g["_draws"].to_list())[:, :, h_idx]           # (n, D)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            per_date.append(np.nanmean(a, axis=0))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(np.stack(per_date), axis=0)


def evaluate(ev: pd.DataFrame, dates: pd.DataFrame, p: dict, *, mkt_thr: float, dip_thr: float,
             sweep_ev: Optional[dict] = None, liquidity: str = "top_n") -> dict:
    """Every cell of one specification: arm x vol cell x horizon."""
    grid = dates.sort_values("date").reset_index(drop=True)
    pos = pd.Series(np.arange(len(grid)), index=pd.DatetimeIndex(grid["date"]))
    arm_of = pd.Series(np.where(grid["mkt_dd"].to_numpy() <= -mkt_thr, ARMS[0], ARMS[1]),
                       index=pd.DatetimeIndex(grid["date"]))
    e = ev[ev["thr"] == dip_thr]
    if liquidity == "nominal":
        e = e[e["mdv"] >= p["nominal_dollar_volume"]]
    e = e.assign(arm=arm_of.reindex(pd.DatetimeIndex(e["date"])).to_numpy())
    out: dict = {}
    for arm in ARMS:
        for cell in VOL_CELLS:
            sub = e[(e["arm"] == arm) & cell_mask(e, cell).to_numpy()]
            for j, h in enumerate(p["horizons"]):
                key = f"{arm}|{cell}|{h}"
                s = basket_series(sub, grid, h) if len(sub) else pd.DataFrame()
                if not len(s):
                    out[key] = {"n_dates": 0, "n_events": 0}
                    continue
                s = s[s["net"].notna()]
                ps = pos.reindex(s.index)
                tw = series_stats(s["net"] - s["twin"], ps, h, p["alpha"], p["power"])
                bl = series_stats(s["net"] - s["line"], ps, h, p["alpha"], p["power"])
                rec: dict = {"n_dates": int(len(s)), "n_events": int(s["n"].sum()),
                             "mean_names_per_date": float(s["n"].mean()),
                             "raw_net_mean": float(s["net"].mean()), "twin_mean": float(s["twin"].mean()),
                             "line_mean": float(s["line"].mean()), "rf_mean": float(s["rf"].mean()),
                             "mkt_mean": float(s["mkt"].mean()), "basket_beta_mean": float(s["beta"].mean()),
                             "excess_vs_twin": tw, "excess_vs_beta_line": bl}
                if "twin3" in s.columns:
                    rec["excess_vs_twin_band_vol_mom"] = {
                        "mean": float((s["net"] - s["twin3"]).mean()),
                        "by_year": {k: v["mean"] for k, v in by_year(s["net"] - s["twin3"]).items()}}
                raw_x = rec["raw_net_mean"] - rec["rf_mean"]
                line_x = rec["line_mean"] - rec["rf_mean"]
                rec["beta_share_of_raw_excess_over_cash"] = (line_x / raw_x) if raw_x > 0 else None
                if "stop" in s.columns:
                    sv = series_stats(s["stop"] - s["net"], ps, h, p["alpha"], p["power"])
                    st = series_stats(s["stop"] - s["twin"], ps, h, p["alpha"], p["power"])
                    rec["stop_vs_hold"] = sv
                    rec["stop_vs_twin"] = {"mean": st["mean"], "t_min": st["t_min"], "t_max": st["t_max"]}
                    rec["share_stopped"] = float(s["stopped"].mean())
                    rec["stop_label"] = stop_label(sv)
                dr = draws_by_cell(sub, j) if "_draws" in sub.columns else None
                if dr is not None:
                    a = dr[np.isfinite(dr)]
                    if len(a):
                        mean_net = float(s["net"].mean())
                        rec["twin_draws"] = {"n": int(len(a)), "median": float(np.median(a)),
                                             "p05": float(np.quantile(a, 0.05)), "p95": float(np.quantile(a, 0.95)),
                                             "cell_percentile": float(((a < mean_net).sum() + 0.5 * (a == mean_net).sum())
                                                                      / len(a))}
                out[key] = rec
    if sweep_ev is not None:
        for key, rec in out.items():
            if not rec.get("n_dates"):
                continue
            vals = [sweep_ev[t].get(key, {}).get("excess_vs_twin", {}).get("mean") for t in sweep_ev]
            vals = [v for v in vals if v is not None]
            rec["sweep_dip_worst_twin_mean"] = min(vals) if vals else None
            rec["verdict"], rec["verdict_numbers"] = verdict(rec["excess_vs_twin"], rec["excess_vs_beta_line"],
                                                             rec["sweep_dip_worst_twin_mean"], p["alpha"])
    return out


def stop_label(sv: dict) -> str:
    m = sv.get("mean")
    if m is None:
        return "NOT_COMPUTED"
    org = sv.get("origins") or []
    tt = [o for o in org if o.get("t") is not None]
    sig_dn = bool(tt) and len(tt) == len(org) and all(o["t"] <= -o["t_crit"] for o in tt)
    sig_up = bool(tt) and len(tt) == len(org) and all(o["t"] >= o["t_crit"] for o in tt)
    if sig_dn:
        return "STOP_LOSES_TO_HOLD"
    if sig_up:
        return "STOP_BEATS_HOLD"
    return "STOP_BELOW_HOLD_CANNOT_DISTINGUISH" if m < 0 else "STOP_ABOVE_HOLD_CANNOT_DISTINGUISH"


# ───────────────────────────── the run ──────────────────────────────────────

def count_files(folder: Path) -> int:
    return sum(1 for q in folder.rglob("*") if q.is_file()) if folder.exists() else -1


def free_ram_gb() -> Optional[float]:
    try:
        import psutil                                                  # noqa: PLC0415
        return round(psutil.virtual_memory().available / 1e9, 2)
    except Exception:                                                  # noqa: BLE001
        pass
    try:                                                               # Windows, no psutil
        import ctypes                                                  # noqa: PLC0415

        class _MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        st = _MS()
        st.dwLength = ctypes.sizeof(_MS)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):  # type: ignore[attr-defined]
            return round(st.ullAvailPhys / 1e9, 2)
    except Exception:                                                  # noqa: BLE001
        pass
    return None


def wait_ram(min_gb: float = 2.5, tries: int = 60) -> None:
    for _ in range(tries):
        g = free_ram_gb()
        if g is None or g >= min_gb:
            return
        say(f"  free RAM {g} GB < {min_gb}: waiting 30 s")
        time.sleep(30)
    raise Refused(f"free RAM stayed below {min_gb} GB")


def survivorship(W: dict, year: int) -> dict:
    """Permnos alive in the year, how many stop trading before the window's end, and how many
    delisting returns were booked (the panel is NOT survivor-selected if these are > 0)."""
    C = W["C"]
    yr = W["dates"].year == year
    alive = np.isfinite(C[yr]).any(axis=0)
    fin = np.isfinite(C)
    last = np.where(fin.any(axis=0), C.shape[0] - 1 - np.argmax(fin[::-1], axis=0), -1)
    lastd = np.array([W["dates"][k] if k >= 0 else pd.NaT for k in last])
    stop_in_year = alive & np.array([pd.notna(x) and x.year == year and k < C.shape[0] - 1
                                     for x, k in zip(lastd, last)])
    dl_y = W["dl"][yr].any(axis=0)
    return {"year": year, "permnos_trading": int(alive.sum()), "stop_trading_in_year": int(stop_in_year.sum()),
            "delisting_returns_booked_in_year": int(dl_y.sum())}


def run(data_root: Path, out_dir: Path, run_id: str, years: tuple[int, int], oop: bool) -> int:
    p = params()
    try:
        out_dir.resolve().relative_to(data_root.resolve().parent)
        raise Refused(f"--out {out_dir} is inside the data root's parent {data_root.parent}")
    except ValueError:
        pass
    need = [data_root / "wrds" / "ff_factors_daily.parquet", data_root / "wrds" / "bulk" / "crsp__dsedelist.parquet",
            data_root / "wrds" / "bulk" / "wrdsapps__firm_ratio_ccm.parquet",
            data_root / "crsp_rebuild" / "followups_daily_FU_2026-09-29T0855Z.parquet"]
    need += [data_root / "wrds" / f"crsp_dsf_{y}.parquet" for y in range(years[0] - 1, min(years[1] + 1, 2024) + 1)]
    if oop:
        need += [data_root / "prices_deep" / "bars.parquet", data_root / "prices_deep" / "bars_delisted.parquet"]
    missing = [str(q) for q in need if not q.exists()]
    if missing:
        raise Refused(f"{len(missing)} input(s) missing, first: {missing[0]}")
    out_dir.mkdir(parents=True, exist_ok=True)
    live = {k: data_root / k for k in ("wrds", "crsp_rebuild", "prices_deep")}
    before = {k: count_files(v) for k, v in live.items()}
    say(f"live folder file counts BEFORE: {before}")
    # 1. the declaration, before any forward return exists
    decl = {"schema": SCHEMA + "/declaration", "run_id": run_id, "written_utc": _now(),
            "written_before_any_forward_return": True, "params": p, "decision_rule": DECISION_RULE,
            "arms": {"A_market_fell": f"FF VW market TR index <= -{p['market_drawdown']:.0%} from its 252-session high",
                     "B_company_fell": "the market was not"},
            "vol_cells": VOL_CELLS, "variants": VARIANTS_NOTE, "licence": "PRODUCT_EXPERIMENT"}
    decl["sha16"] = _sha({k: v for k, v in decl.items() if k != "written_utc"})
    dp = out_dir / f"ch38_dip_study_{run_id}_DECLARATION.json"
    if dp.exists():
        raise Refused(f"{dp.name} exists; a receipt is never overwritten")
    dp.write_text(json.dumps(decl, indent=1, default=str), encoding="utf-8")
    say(f"declaration {dp.name} sha {decl['sha16']}  thresholds: dip {p['dip_drawdown']:.0%}, market "
        f"{p['market_drawdown']:.0%}, liquid top {p['liquid_top_n']} & px >= {p['min_price']}, H {p['horizons']}, "
        f"stop {p['stop_sigma']} sigma, twins {p['twin_draws']}")
    t0 = time.time()
    ff = ff_daily(data_root)
    dl = pd.read_parquet(data_root / "wrds" / "bulk" / "crsp__dsedelist.parquet",
                         columns=["permno", "dlstdt", "dlstcd", "dlret"])
    dl["dlstdt"] = pd.to_datetime(dl["dlstdt"])
    for c in ("dlstcd", "dlret"):
        dl[c] = pd.to_numeric(dl[c], errors="coerce").astype("float64")
    cs = cs_by_date(data_root)
    prof = profitability(data_root)
    ev_parts, date_recs, surv, audits = [], [], [], []
    y0, y1 = years
    for y in range(y0, y1 + 1):
        wait_ram()
        ty = time.time()
        W = wide_crsp(data_root, y, dl, ff)
        surv.append(survivorship(W, y))
        audits.append(dict(W["audit"], decision_year=y))
        for i in month_end_rows(W["dates"], y):
            rng = np.random.default_rng(p["seed"] + int(pd.Timestamp(W["dates"][i]).strftime("%Y%m%d")))
            rec, frames = date_events(W, i, p, rng, cs=cs.get(pd.Timestamp(W["dates"][i])))
            if rec is None:
                continue
            rec["cs_available"] = pd.Timestamp(W["dates"][i]) in cs
            date_recs.append(rec)
            ev_parts.extend(frames)
        sv = surv[-1]
        say(f"  {y}: {sv['permnos_trading']} permnos, {sv['stop_trading_in_year']} stop trading, "
            f"{sv['delisting_returns_booked_in_year']} delisting returns booked; "
            f"{sum(1 for r in date_recs if r['date'].year == y)} signal dates; {time.time() - ty:.0f}s "
            f"RAM free {free_ram_gb()} GB")
        del W
        gc.collect()
    ev = pd.concat(ev_parts, ignore_index=True)
    dates = pd.DataFrame(date_recs)
    ev["unprof"] = attach_profitability(ev, prof)
    receipt = summarise(ev, dates, p, surv, audits, source="CRSP")
    if oop:
        receipt["out_of_panel_2025_2026"] = out_of_panel(data_root, p)
    after = {k: count_files(v) for k, v in live.items()}
    say(f"live folder file counts AFTER: {after}")
    receipt.update(schema=SCHEMA, job=JOB, run_id=run_id, written_utc=_now(), licence="PRODUCT_EXPERIMENT",
                   llm_spend_usd=0.0, declaration=dp.name, declaration_sha16=decl["sha16"],
                   decision_rule=DECISION_RULE, variants=VARIANTS_NOTE, params=p,
                   live_folder_files={"before": before, "after": after, "unchanged": before == after},
                   seconds=round(time.time() - t0, 1))
    jp = out_dir / f"ch38_dip_study_{run_id}.json"
    jp.write_text(json.dumps(_clean(receipt), indent=1, default=str), encoding="utf-8")
    mp = out_dir / f"ch38_dip_study_{run_id}.md"
    mp.write_text("\n".join(render_md(receipt)), encoding="utf-8")
    say(f"-> {jp}\n-> {mp}  ({time.time() - t0:.0f}s)")
    return 0 if before == after else 4


def summarise(ev: pd.DataFrame, dates: pd.DataFrame, p: dict, surv: list, audits: list, source: str) -> dict:
    dates = dates.sort_values("date").reset_index(drop=True)
    prim = ev[ev["thr"] == p["dip_drawdown"]]
    panel = {"source": source, "signal_dates": int(len(dates)),
             "first_signal": str(dates["date"].min().date()), "last_signal": str(dates["date"].max().date()),
             "median_liquid_per_date": float(dates["n_liquid"].median()),
             "median_eligible_per_date": float(dates["n_eligible"].median()),
             "liquid_mdv_cut_median_usd": float(pd.Series(dates["mdv_cut"]).median()),
             "primary_events": int(len(prim)), "primary_distinct_names": int(prim["symbol"].nunique()),
             "events_with_unprofitable_flag": int(prim["unprof"].notna().sum()) if "unprof" in prim else 0,
             "share_unprofitable_where_known": (float(prim["unprof"].mean()) if "unprof" in prim
                                                and prim["unprof"].notna().any() else None),
             "dates_arm_A": int((dates["mkt_dd"] <= -p["market_drawdown"]).sum()),
             "cs_spread_dates": int(dates["cs_available"].sum()) if "cs_available" in dates else 0}
    sv = {"by_year": surv, "permno_years": int(sum(s["permnos_trading"] for s in surv)),
          "stop_trading_total": int(sum(s["stop_trading_in_year"] for s in surv)),
          "delisting_returns_booked_total": int(sum(s["delisting_returns_booked_in_year"] for s in surv)),
          "audits": audits}
    say(f"SURVIVORSHIP: {sv['stop_trading_total']} permno-exits, {sv['delisting_returns_booked_total']} delisting "
        f"returns booked over {len(surv)} years -- the panel is NOT survivor-selected")
    say(f"PANEL: {panel}")
    sweeps = {t: evaluate(ev, dates, p, mkt_thr=p["market_drawdown"], dip_thr=t) for t in p["sweep_dip_drawdown"]}
    primary = evaluate(ev, dates, p, mkt_thr=p["market_drawdown"], dip_thr=p["dip_drawdown"], sweep_ev=sweeps)
    mkt_sweeps = {t: evaluate(ev, dates, p, mkt_thr=t, dip_thr=p["dip_drawdown"]) for t in p["sweep_market_drawdown"]}
    nominal = evaluate(ev, dates, p, mkt_thr=p["market_drawdown"], dip_thr=p["dip_drawdown"], liquidity="nominal")
    table = admitted_table(primary, sweeps, mkt_sweeps, nominal, p)
    return {"panel": panel, "survivorship": sv, "primary": primary,
            "sweep_dip_drawdown": {f"{t:.2f}": v for t, v in sweeps.items()},
            "sweep_market_drawdown": {f"{t:.2f}": v for t, v in mkt_sweeps.items()},
            "sensitivity_nominal_20m": nominal, "admitted_cells": table,
            "dates": dates.assign(date=dates["date"].astype(str)).drop(columns=[c for c in dates.columns
                                                                                 if c.startswith("twin_fallback")],
                                                                        errors="ignore").to_dict("records")}


def admitted_table(primary: dict, sweeps: dict, mkt_sweeps: dict, nominal: dict, p: dict) -> list[dict]:
    rows = []
    for key, r in primary.items():
        if not r.get("n_dates"):
            arm, cell, h = key.split("|")
            rows.append({"cell": key, "arm": arm, "vol_cell": cell, "h": int(h), "verdict": "CANNOT_DISTINGUISH",
                         "why": "empty cell"})
            continue
        arm, cell, h = key.split("|")
        mk = [mkt_sweeps[t].get(key, {}).get("excess_vs_twin", {}).get("mean") for t in mkt_sweeps]
        mk = [v for v in mk if v is not None]
        rows.append({"cell": key, "arm": arm, "vol_cell": cell, "h": int(h), "verdict": r.get("verdict"),
                     "n_dates": r["n_dates"], "n_events": r["n_events"],
                     "raw_net_mean": r["raw_net_mean"], "twin_excess": r["excess_vs_twin"]["mean"],
                     "beta_line_excess": r["excess_vs_beta_line"]["mean"],
                     "twin_t_min": r["excess_vs_twin"]["t_min"], "twin_t_max": r["excess_vs_twin"]["t_max"],
                     "min_blocks": r["excess_vs_twin"]["min_blocks"], "mde_max": r["excess_vs_twin"]["mde_max"],
                     "loo_worst": r["excess_vs_twin"]["loo"]["worst"],
                     "worst_year": r["excess_vs_twin"]["worst_year"],
                     "years_positive": f"{r['excess_vs_twin']['years_positive']}/{r['excess_vs_twin']['years']}",
                     "basket_beta": r["basket_beta_mean"],
                     "beta_share_of_raw_excess_over_cash": r["beta_share_of_raw_excess_over_cash"],
                     "sweep_dip_worst_twin_mean": r.get("sweep_dip_worst_twin_mean"),
                     "sweep_market_worst_twin_mean": min(mk) if mk else None,
                     "nominal_20m_twin_mean": nominal.get(key, {}).get("excess_vs_twin", {}).get("mean"),
                     "stop_minus_hold": (r.get("stop_vs_hold") or {}).get("mean"),
                     "stop_label": r.get("stop_label"), "why": r.get("verdict_numbers")})
    return rows


def out_of_panel(root: Path, p: dict) -> dict:
    """2025-2026 on prices_deep (alive on 2026-09-01 + the Alpaca inactive list), clearly labelled:
    no delisting returns, flat band costs, no profitability flag, SPY as the market."""
    wait_ram()
    say("OUT OF PANEL 2025-2026 (prices_deep; NOT survivorship-free in the CRSP sense)")
    W, src = wide_deep(root, "2023-10-01")
    recs, parts = [], []
    for i in month_end_rows(W["dates"]):
        if W["dates"][i] < pd.Timestamp("2025-01-01"):
            continue
        rng = np.random.default_rng(p["seed"] + int(pd.Timestamp(W["dates"][i]).strftime("%Y%m%d")))
        rec, frames = date_events(W, i, p, rng, cs=None)
        if rec is None:
            continue
        rec["cs_available"] = False
        recs.append(rec)
        parts.extend(frames)
    dates = pd.DataFrame(recs).sort_values("date").reset_index(drop=True)
    ev = pd.concat(parts, ignore_index=True)
    ev["unprof"] = np.nan
    sweeps = {t: evaluate(ev, dates, p, mkt_thr=p["market_drawdown"], dip_thr=t) for t in p["sweep_dip_drawdown"]}
    prim = evaluate(ev, dates, p, mkt_thr=p["market_drawdown"], dip_thr=p["dip_drawdown"], sweep_ev=sweeps)
    say(f"  {len(dates)} signal dates {dates['date'].min().date()}..{dates['date'].max().date()}, "
        f"{int((ev['thr'] == p['dip_drawdown']).sum())} primary events; arm A dates "
        f"{int((dates['mkt_dd'] <= -p['market_drawdown']).sum())}; SPY drawdown at month-ends min "
        f"{dates['mkt_dd'].min():.3f}")
    return {"label": "OUT OF PANEL: prices_deep, survivor-selected membership (alive on 2026-09-01) plus the "
                     "Alpaca inactive list; no delisting returns (a dead name is held at its last close); flat "
                     "band costs; SPY (adjustment=all) is the market; profitability NOT AVAILABLE (no "
                     "permno map); descriptive only, never admits",
            "source": src, "signal_dates": int(len(dates)),
            "mkt_dd_by_date": {str(r["date"].date()): round(float(r["mkt_dd"]), 4) for _, r in dates.iterrows()},
            "cells": {k: _slim(v) for k, v in prim.items()}}


def _slim(r: dict) -> dict:
    if not r.get("n_dates"):
        return r
    return {"n_dates": r["n_dates"], "n_events": r["n_events"], "raw_net_mean": r["raw_net_mean"],
            "twin_excess": r["excess_vs_twin"]["mean"], "beta_line_excess": r["excess_vs_beta_line"]["mean"],
            "by_year_twin": {k: v["mean"] for k, v in r["excess_vs_twin"]["by_year"].items()},
            "stop_minus_hold": (r.get("stop_vs_hold") or {}).get("mean"), "basket_beta": r["basket_beta_mean"],
            "twin_t_min": r["excess_vs_twin"]["t_min"], "min_blocks": r["excess_vs_twin"]["min_blocks"],
            "verdict_if_it_were_primary": r.get("verdict")}


def _clean(o: Any) -> Any:
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        v = float(o)
        return None if not np.isfinite(v) else round(v, 6)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return str(o.date())
    return o


# ───────────────────────────── markdown ─────────────────────────────────────

def render_md(r: dict) -> list[str]:
    p = r["params"]
    L = [f"# CH-38 dip study — {r['run_id']}", "",
         f"Licence PRODUCT_EXPERIMENT, descriptive; LLM spend 0. Declaration `{r['declaration']}` "
         f"(sha {r['declaration_sha16']}) written before any forward return was computed.", ""]
    L += ["## ADMITTED CELLS FOR THE CONTRACT", "",
          "Excess per signal date, equal-weight basket, net of costs; % over the hold. Twin = same band x vol tercile "
          "random names (40 draws); beta line = rf + basket beta x (market - rf).", "",
          "| cell | verdict | dates | names/date | raw net | vs twins | vs beta line | twin t (min..max) | blocks | MDE | "
          "LOO worst | yrs+ | beta | beta share of raw | stop - hold |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for row in r["admitted_cells"]:
        if row.get("n_dates") is None:
            L.append(f"| {row['cell']} | {row['verdict']} | 0 | | | | | | | | | | | | |")
            continue
        pr = r["primary"][row["cell"]]
        L.append(f"| {row['cell']} | **{row['verdict']}** | {row['n_dates']} | {pr['mean_names_per_date']:.0f} | "
                 f"{_pct(row['raw_net_mean'])} | {_pct(row['twin_excess'])} | {_pct(row['beta_line_excess'])} | "
                 f"{_fmt(row['twin_t_min'])}..{_fmt(row['twin_t_max'])} | {row['min_blocks']} | "
                 f"{_pct(row['mde_max'])} | {_pct(row['loo_worst'])} | {row['years_positive']} | "
                 f"{row['basket_beta']:.2f} | "
                 f"{'n/a' if row['beta_share_of_raw_excess_over_cash'] is None else format(row['beta_share_of_raw_excess_over_cash'], '.0%')} | "
                 f"{_pct(row['stop_minus_hold'])} |")
    L += ["", "Decision rule: " + r["decision_rule"], "", "Variants: " + r["variants"], ""]
    pa, sv = r["panel"], r["survivorship"]
    L += ["## Panel and survivorship (printed before any result)", "",
          f"- {pa['source']}: {pa['signal_dates']} month-end signal dates {pa['first_signal']}..{pa['last_signal']}; "
          f"median {pa['median_eligible_per_date']:.0f} eligible / {pa['median_liquid_per_date']:.0f} liquid names "
          f"per date; liquid cut (63-session median dollar volume of the {p['liquid_top_n']}th name) median "
          f"{pa['liquid_mdv_cut_median_usd'] / 1e6:.1f} M USD.",
          f"- {pa['primary_events']} primary dip events, {pa['primary_distinct_names']} distinct permnos; arm A dates "
          f"{pa['dates_arm_A']}; profitability known for {pa['events_with_unprofitable_flag']} events "
          f"(share unprofitable {_pct(pa['share_unprofitable_where_known'])}).",
          f"- Survivorship: {sv['stop_trading_total']} permno exits and {sv['delisting_returns_booked_total']} CRSP "
          f"delisting returns booked over the decision years: dead names are in the panel.", ""]
    L += ["## By year, leave-one-year-out (excess vs twins), per primary cell", ""]
    for key, rec in r["primary"].items():
        if not rec.get("n_dates"):
            continue
        tw = rec["excess_vs_twin"]
        by = ", ".join(f"{y} {v['mean'] * 100:+.1f} ({v['n']})" for y, v in tw["by_year"].items())
        sh = tw.get("share_by_date") or {}
        L.append(f"- **{key}** by entry year: {by}. LOO worst {_pct(tw['loo']['worst'])} (drop "
                 f"{tw['loo']['worst_dropped']}), best {_pct(tw['loo']['best'])} (drop {tw['loo']['best_dropped']}); "
                 f"worst year {tw['worst_year']}; top 5% of dates carry "
                 f"{'n/a' if sh.get('top_5pct_of_months') is None else format(sh['top_5pct_of_months'], '.0%')} of the sum; "
                 f"then t {_fmt(tw['t_min'])}..{_fmt(tw['t_max'])} on >= {tw['min_blocks']} non-overlapping blocks, "
                 f"MDE <= {_pct(tw['mde_max'])}.")
    oop = r.get("out_of_panel_2025_2026")
    if oop:
        L += ["", "## OUT OF PANEL 2025-2026 (descriptive, never admits)", "", oop["label"], "",
              "| cell | dates | raw net | vs twins | vs beta line | stop - hold | by year (vs twins) |", "|---|---|---|---|---|---|---|"]
        for k, v in oop["cells"].items():
            if not v.get("n_dates"):
                continue
            L.append(f"| {k} | {v['n_dates']} | {_pct(v['raw_net_mean'])} | {_pct(v['twin_excess'])} | "
                     f"{_pct(v['beta_line_excess'])} | {_pct(v['stop_minus_hold'])} | "
                     + ", ".join(f"{y} {x * 100:+.1f}" for y, x in v["by_year_twin"].items()) + " |")
    L += ["", f"Live folder files unchanged: {r['live_folder_files']['unchanged']} "
              f"(before {r['live_folder_files']['before']}, after {r['live_folder_files']['after']})."]
    return L


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-root", required=True, type=Path, help="the optimus data folder (read-only)")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--years", default=None, help="e.g. 1991-2024 (default: config)")
    ap.add_argument("--no-oop", action="store_true", help="skip the 2025-2026 out-of-panel section")
    a = ap.parse_args(argv)
    p = params()
    years = (p["first_year"], p["last_year"])
    if a.years:
        lo, hi = a.years.split("-")
        years = (int(lo), int(hi))
    rid = a.run_id or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    try:
        return run(a.data_root, a.out, rid, years, not a.no_oop)
    except Refused as exc:
        say(f"REFUSED: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
