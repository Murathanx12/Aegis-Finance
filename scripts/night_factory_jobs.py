"""NIGHT FACTORY 2026-09-08 -- the CPU jobs. $0 of LLM. Nothing is ordered, sealed or pushed.

    python -m scripts.night_factory_jobs D1_reaction_book --out X.json
    python -m scripts.night_factory_jobs D1_reaction_book --smoke      # 2003-2005 only
    python -m scripts.night_factory_jobs G1_evolve --hours 5

THE NIGHT'S QUESTION (Murat, 2026-09-08): "I'm not happy with the backtest
results ... we can't just claim everything we find is noise ... run
simulations throughout the whole night, back to back, and continuously learn."

Three jobs, in priority order:

  D1  THE FAITHFUL EVENT-CLOCKED EARNINGS-REACTION BOOK. R4 (2026-09-08) found
      the one signal that did not decay -- the announcement reaction, t 6.13 /
      2.97 / 3.67 across eras, placebo +40 sessions flips sign -- and then
      killed it through a MONTHLY rank book, which is not a faithful test of a
      21-session event clock. This job runs the clock the signal lives on:
      observe the two-session reaction -> enter at the close of session +1
      (PIT-safe for after-the-bell reporters) -> hold H sessions -> exit. A
      calendar-time portfolio (Jaffe 1974 / Mandelker 1974): every session the
      book is equal-weighted across every open position; 25 bps a side on
      entry and exit; beta printed FIRST; monthly date blocks (CANON section
      58); three eras; the placebo tape re-run through the SAME book.

  D2  MUTATIONS AROUND D1 on the development window 1999-2015, family
      corrected. The holdout 2016-2024 is printed beside each cell and marked;
      it was not used to choose anything.

  G1  EVOLUTIONARY CONSTRUCTION-AND-SELECTION SEARCH on the monthly long panel,
      development months only (<= 2015-12). Genome = linear selector over the
      z-scored feature menu x (k, weighting, hold band, liquidity floor).
      Fitness = the PRODUCT ruler (log terminal wealth net of 25 bps at a
      drawdown budget) with beta printed on every row. Every evaluation is
      appended to an evidence file. The holdout is NEVER evaluated here; a
      separate morning job reads the archive once.

LICENCE: PRODUCT_EXPERIMENT. Explore dirty, promote clean. What does not relax:
no information acted on before it was public (entry at s0+1 close; ranks from
a trailing window; features from sessions strictly before entry); no target
leakage; costs never omitted; nothing here places an order.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import r4_event_families as R            # noqa: E402  helpers only

RUN_DATE = "2026-09-08"
OUT = REPO / "backend" / "data" / "optimus" / f"night_factory_{RUN_DATE}"
OUT.mkdir(parents=True, exist_ok=True)
WRDS = REPO / "backend" / "data" / "optimus" / "wrds"
TAPE = REPO / "backend" / "data" / "optimus" / "r4_event_families" / "R4_earnings_events.parquet"
PLACEBO = REPO / "backend" / "data" / "optimus" / "r4_event_families" / "R4_placebo_offset40.parquet"
LONG = REPO / "backend" / "data" / "optimus" / "learner" / "train_table_long.parquet"

COST_BPS = 25.0
FLOOR_USD = 3_000_000.0          # the repo's TRADABLE_DOLLAR_VOL floor
RANK_WINDOW = 63                 # sessions of events the PIT rank is drawn from
MIN_POOL = 200
NW_LAG_M = 4
DEV_LAST_MONTH = "2015-12"       # the development window ends here, 2016-24 is the holdout
ERAS = {"1999-2007": (1999, 2007), "2008-2015": (2008, 2015), "2016-2024": (2016, 2024)}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _r(v, nd=5):
    return R._r(v, nd)


# ----------------------------------------------------------------- daily tape

def load_daily(years) -> pd.DataFrame:
    frames = []
    for y in years:
        p = WRDS / f"crsp_dsf_{y}.parquet"
        if not p.exists():
            continue
        d = pd.read_parquet(p, columns=["permno", "date", "ret", "prc", "vol", "shrout"])
        d = d[np.isfinite(d["ret"].to_numpy(dtype="float64"))]
        d["permno"] = d["permno"].astype("int32")
        for c in ("ret", "prc", "vol", "shrout"):
            d[c] = d[c].astype("float32")
        frames.append(d)
    if not frames:
        raise SystemExit("REFUSED: no CRSP daily parquet on this checkout")
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    return out.sort_values(["permno", "date"], kind="mergesort").reset_index(drop=True)


class Tape:
    """Per-permno contiguous blocks over a global session index."""

    def __init__(self, daily: pd.DataFrame):
        self.dates = np.sort(daily["date"].unique())
        self.n = len(self.dates)
        didx = pd.Series(np.arange(self.n), index=pd.DatetimeIndex(self.dates))
        self.di = didx.reindex(pd.DatetimeIndex(daily["date"])).to_numpy().astype("int64")
        self.ret = daily["ret"].to_numpy(dtype="float64")
        self.prc = np.abs(daily["prc"].to_numpy(dtype="float64"))
        self.vol = daily["vol"].to_numpy(dtype="float64")
        self.cap = self.prc * daily["shrout"].to_numpy(dtype="float64") * 1000.0
        pn = daily["permno"].to_numpy()
        starts = np.flatnonzero(np.r_[True, pn[1:] != pn[:-1]])
        ends = np.r_[starts[1:], len(pn)]
        self.blocks = {int(pn[s]): (int(s), int(e)) for s, e in zip(starts, ends)}
        # markets: EW (R4's convention) and VW on the previous session's cap
        ew = np.zeros(self.n)
        cnt = np.zeros(self.n)
        np.add.at(ew, self.di, self.ret)
        np.add.at(cnt, self.di, 1.0)
        self.mkt_ew = np.where(cnt > 0, ew / np.maximum(cnt, 1), 0.0)
        prev_cap = np.empty_like(self.cap)
        prev_cap[:] = np.nan
        for s, e in self.blocks.values():
            if e - s > 1:
                prev_cap[s + 1:e] = self.cap[s:e - 1]
        ok = np.isfinite(prev_cap) & (prev_cap > 0)
        num = np.zeros(self.n)
        den = np.zeros(self.n)
        np.add.at(num, self.di[ok], self.ret[ok] * prev_cap[ok])
        np.add.at(den, self.di[ok], prev_cap[ok])
        self.mkt_vw = np.where(den > 0, num / np.maximum(den, 1e-9), 0.0)
        self.month_of = pd.DatetimeIndex(self.dates).strftime("%Y-%m").to_numpy()

    def session_of(self, ts) -> int:
        return int(np.searchsorted(self.dates, np.datetime64(ts), side="left"))


# ----------------------------------------------------------- the event frame

def build_events(tape: Tape, ev: pd.DataFrame, *, label: str) -> pd.DataFrame:
    """Per event: entry session e = s0+1 (close), PIT features from sessions < e,
    and everything D2 needs. Skips events with no price on s0 or s0+1."""
    ev = ev.sort_values(["permno", "anndats"], kind="mergesort")
    rows = []
    skipped = {"no_block": 0, "no_s0_price": 0, "no_s1": 0}
    for permno, g in ev.groupby("permno", sort=False):
        blk = tape.blocks.get(int(permno))
        if blk is None:
            skipped["no_block"] += len(g)
            continue
        s, e_ = blk
        di = tape.di[s:e_]
        ret = tape.ret[s:e_]
        prc = tape.prc[s:e_]
        vol = tape.vol[s:e_]
        cap = tape.cap[s:e_]
        for rec in g.itertuples(index=False):
            s0 = tape.session_of(rec.anndats)
            if s0 >= tape.n:
                skipped["no_s1"] += 1
                continue
            j = int(np.searchsorted(di, s0))
            if j >= len(di) or di[j] != s0:
                skipped["no_s0_price"] += 1
                continue
            if j + 1 >= len(di) or di[j + 1] != s0 + 1:
                skipped["no_s1"] += 1
                continue
            e = s0 + 1                      # entry at the close of session +1
            lo = max(0, j - 20)
            dv = np.median(prc[lo:j + 1] * vol[lo:j + 1]) if j + 1 - lo >= 5 else np.nan
            v_lo = max(0, j - 61)
            sd60 = float(np.std(ret[v_lo:j - 1])) if j - 1 - v_lo >= 30 else np.nan
            m_lo, m_hi = max(0, j - 252), max(0, j - 21)
            mom = float(np.prod(1.0 + ret[m_lo:m_hi]) - 1.0) if m_hi - m_lo >= 120 else np.nan
            vsurge = (float((vol[j] + vol[j + 1]) / 2.0 / max(np.mean(vol[lo:j]), 1.0))
                      if j - lo >= 5 else np.nan)
            rows.append({
                "permno": int(permno), "s0": int(s0), "e": int(e), "j": int(j + 1), "blk_s": int(s),
                "reaction": float(rec.reaction_01),
                "sue": float(getattr(rec, "suescore", np.nan)) if hasattr(rec, "suescore") else np.nan,
                "dv21": float(dv), "prc_e": float(prc[j + 1]), "cap_e": float(cap[j + 1]),
                "sd60": sd60, "mom_12_1": mom, "vsurge": vsurge,
                "car21_r4": float(getattr(rec, "car_mkt_21_e2", np.nan)) if hasattr(rec, "car_mkt_21_e2") else np.nan,
            })
    df = pd.DataFrame(rows)
    df["year"] = pd.DatetimeIndex(tape.dates[df["e"].to_numpy()]).year
    df["month"] = tape.month_of[df["e"].to_numpy()]
    df["z_reaction"] = df["reaction"] / df["sd60"]
    print(f"    {label}: {len(df):,} events on the tape, skipped {skipped}", flush=True)
    return df


def pit_rank(df: pd.DataFrame, col: str = "reaction", window: int = RANK_WINDOW) -> pd.Series:
    """Percentile of `col` among events whose entry session is in the trailing
    `window` sessions INCLUDING the current one. Everything in the pool is known
    at the close of session e, which is when the rank is used."""
    df = df.sort_values("e")
    out = pd.Series(np.nan, index=df.index)
    pool: deque = deque()          # (session, values)
    for e, g in df.groupby("e", sort=True):
        while pool and pool[0][0] < e - window + 1:
            pool.popleft()
        v = g[col].to_numpy(dtype="float64")
        v = v[np.isfinite(v)]
        pool.append((e, v))
        allv = np.concatenate([p[1] for p in pool]) if pool else np.empty(0)
        if len(allv) < MIN_POOL:
            continue
        srt = np.sort(allv)
        x = g[col].to_numpy(dtype="float64")
        pct = np.searchsorted(srt, x, side="right") / len(srt)
        out.loc[g.index] = np.where(np.isfinite(x), pct, np.nan)
    return out


# ------------------------------------------------------ calendar-time book

def calendar_book(tape: Tape, sel: pd.DataFrame, horizon: int, cost_bps: float = COST_BPS) -> dict:
    """Equal-weight across every open position, every session. Positions enter
    at the close of `e` (first return at e+1) and leave at the close of e+H.
    A delisted name ends early at its last observed return. Costs on the
    first and last session of each position."""
    n = tape.n
    acc_n = np.zeros(n)
    acc_g = np.zeros(n)
    cnt = np.zeros(n)
    c = cost_bps / 10_000.0
    n_pos = 0
    held_sessions = 0
    for permno, e, j, bs in zip(sel["permno"].to_numpy(), sel["e"].to_numpy(),
                                sel["j"].to_numpy(), sel["blk_s"].to_numpy()):
        s, e_ = tape.blocks[int(permno)]
        di = tape.di[s:e_]
        ret = tape.ret[s:e_]
        k0 = int(j) + 1                      # first holding return: session e+1
        if k0 >= len(di):
            continue
        k1 = min(len(di), k0 + horizon)
        seg_di = di[k0:k1]
        seg = ret[k0:k1].copy()
        # a gap in the block (missing session) ends the position at the gap
        ok = np.flatnonzero(np.diff(np.r_[e, seg_di]) != 1)
        if len(ok):
            seg_di = seg_di[:ok[0]]
            seg = seg[:ok[0]]
        if len(seg) == 0:
            continue
        g = seg.copy()
        seg[0] -= c
        seg[-1] -= c
        np.add.at(acc_n, seg_di, seg)
        np.add.at(acc_g, seg_di, g)
        np.add.at(cnt, seg_di, 1.0)
        n_pos += 1
        held_sessions += len(seg)
    live = cnt > 0
    net = np.where(live, acc_n / np.maximum(cnt, 1), 0.0)
    gross = np.where(live, acc_g / np.maximum(cnt, 1), 0.0)
    return {"net": net, "gross": gross, "n_open": cnt, "n_positions": n_pos,
            "mean_hold_sessions": held_sessions / max(n_pos, 1)}


def _monthly(tape: Tape, daily: np.ndarray, first: int, last: int) -> pd.Series:
    s = pd.Series(daily[first:last + 1], index=tape.month_of[first:last + 1])
    return s.groupby(level=0).apply(lambda x: float(np.prod(1.0 + x.to_numpy()) - 1.0))


def _nw_t(x: np.ndarray, lag: int) -> float | None:
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 12:
        return None
    m = x.mean()
    u = x - m
    s = float(np.dot(u, u)) / n
    for L in range(1, lag + 1):
        w = 1.0 - L / (lag + 1.0)
        s += 2.0 * w * float(np.dot(u[L:], u[:-L])) / n
    se = math.sqrt(max(s, 1e-18) / n)
    return float(m / se) if se > 0 else None


def grade_daily_book(tape: Tape, bk: dict, *, label: str, first: int, last: int,
                     mkt: str = "vw") -> dict:
    """BETA FIRST. Daily book -> monthly blocks -> market model -> beta-matched excess."""
    m_net = _monthly(tape, bk["net"], first, last)
    m_gross = _monthly(tape, bk["gross"], first, last)
    m_mkt = _monthly(tape, tape.mkt_vw if mkt == "vw" else tape.mkt_ew, first, last)
    m_mkt = m_mkt.reindex(m_net.index)
    x = m_mkt.to_numpy()
    y = m_net.to_numpy()
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < 24:
        return {"label": label, "verdict": "CANNOT DETERMINE", "months": int(len(x))}
    X = np.c_[np.ones(len(x)), x]
    beta_hat = np.linalg.lstsq(X, y, rcond=None)[0]
    alpha, beta = float(beta_hat[0]), float(beta_hat[1])
    ex_bm = y - beta * x                     # beta-matched excess (rf ~ 0 on the daily tape)
    ex_raw = y - x
    dd = _max_dd(y)
    def _era(idx):
        out = {}
        for name, (a, b) in ERAS.items():
            mask = np.array([a <= int(mm[:4]) <= b for mm in idx])
            if mask.sum() >= 12:
                t = _nw_t(ex_bm[mask], NW_LAG_M)
                out[name] = {"months": int(mask.sum()), "beta_matched_ann_pct": _r(float(ex_bm[mask].mean()) * 12 * 100, 3),
                             "t": _r(t, 3), "sign": int(np.sign(ex_bm[mask].mean())),
                             "book_ann_pct": _r(float(y[mask].mean()) * 12 * 100, 3),
                             "market_ann_pct": _r(float(x[mask].mean()) * 12 * 100, 3)}
        return out
    idx = m_net.index.to_numpy()[ok]
    t_bm = _nw_t(ex_bm, NW_LAG_M)
    open_days = bk["n_open"][first:last + 1]
    return {
        "label": label,
        "beta": _r(beta, 4),
        "months": int(len(x)), "first_month": str(idx[0]), "last_month": str(idx[-1]),
        "n_positions": int(bk["n_positions"]), "mean_hold_sessions": _r(bk["mean_hold_sessions"], 2),
        "mean_open_positions": _r(float(open_days[open_days > 0].mean()) if (open_days > 0).any() else 0.0, 2),
        "share_of_sessions_invested": _r(float((open_days > 0).mean()), 4),
        "terminal_wealth_net": _r(float(np.prod(1.0 + y)), 4),
        "terminal_wealth_gross": _r(float(np.prod(1.0 + m_gross.to_numpy()[ok])), 4),
        "terminal_wealth_market_same_months": _r(float(np.prod(1.0 + x)), 4),
        "cagr_net_pct": _r((float(np.prod(1.0 + y)) ** (12.0 / len(y)) - 1.0) * 100, 3),
        "cagr_market_pct": _r((float(np.prod(1.0 + x)) ** (12.0 / len(x)) - 1.0) * 100, 3),
        "ann_vol_pct": _r(float(np.std(y, ddof=1)) * math.sqrt(12) * 100, 3),
        "sharpe_net": _r(float(np.mean(y) / max(np.std(y, ddof=1), 1e-9)) * math.sqrt(12), 3),
        "max_drawdown_pct": _r(dd * 100, 3),
        "PRIMARY_beta_matched": {"annualised_pct": _r(float(ex_bm.mean()) * 12 * 100, 3),
                                 "alpha_monthly_pct": _r(alpha * 100, 4),
                                 "t_nw": _r(t_bm, 3), "p_two_sided": R._p_two_sided(t_bm)},
        "SECONDARY_raw_market": {"annualised_pct": _r(float(ex_raw.mean()) * 12 * 100, 3),
                                 "t_nw": _r(_nw_t(ex_raw, NW_LAG_M), 3)},
        "mde_and_power": R.mde_block(pd.Series(ex_bm)),
        "eras": _era(idx),
        "_monthly": {"net": [float(v) for v in y], "market": [float(v) for v in x], "months": [str(v) for v in idx]},
    }


def _max_dd(m: np.ndarray) -> float:
    w = np.cumprod(1.0 + m)
    peak = np.maximum.accumulate(w)
    return float(np.min(w / peak - 1.0))


def _strip(cell: dict) -> dict:
    return {k: v for k, v in cell.items() if not k.startswith("_")}


# ------------------------------------------------------------------- D1 / D2

def _load_tape(smoke: bool):
    years = list(range(2002, 2007)) if smoke else list(range(1998, 2025))
    t0 = time.time()
    daily = load_daily(years)
    tape = Tape(daily)
    print(f"    daily: {len(daily):,} rows, {tape.n:,} sessions, {len(tape.blocks):,} names, "
          f"{time.time() - t0:.0f}s", flush=True)
    del daily
    return tape, years


def _events(tape: Tape, years, smoke: bool):
    cols = ["permno", "anndats", "year", "reaction_01", "suescore", "car_mkt_21_e2"]
    ev = pd.read_parquet(TAPE, columns=cols)
    ev = ev[(ev["year"] >= years[1]) & (ev["year"] <= years[-1] - (1 if smoke else 0))]
    pl = pd.read_parquet(PLACEBO, columns=["permno", "anndats", "year", "reaction_01", "suescore"])
    pl = pl[(pl["year"] >= years[1]) & (pl["year"] <= years[-1] - (1 if smoke else 0))]
    return build_events(tape, ev, label="announcements"), build_events(tape, pl, label="placebo +40")


def _select(df: pd.DataFrame, top: float, floor: float | None = FLOOR_USD, col="rank") -> pd.DataFrame:
    m = df[col].notna() & (df[col] > 1.0 - top)
    if floor is not None:
        m &= df["dv21"] >= floor
    return df[m]


def _window(tape: Tape, df: pd.DataFrame, lo_year: int | None, hi_year: int | None) -> tuple[int, int]:
    e = df["e"].to_numpy()
    first, last = int(e.min()), int(min(tape.n - 1, e.max() + 70))
    if lo_year is not None:
        first = max(first, tape.session_of(pd.Timestamp(f"{lo_year}-01-01")))
    if hi_year is not None:
        last = min(last, tape.session_of(pd.Timestamp(f"{hi_year}-12-31")))
    return first, last


def D1_reaction_book(smoke: bool = False) -> dict:
    """The one faithful test R4 said it owed (BUILD_2026-09-08_R4 section 12 item 1)."""
    out = {"job": "D1_reaction_book", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "question": ("Does the announcement REACTION, traded on the clock it lives on "
                        "(enter at the close of session +1, hold H, calendar-time EW, 25 bps a "
                        "side, $3m/day floor), beat a beta-matched market? R4 measured the "
                        "decile spread (t 7.37) and then killed it through a MONTHLY rank book."),
           "conventions": {"entry": "close of session s0+1 (PIT-safe for after-the-bell reporters)",
                           "rank": f"percentile of reaction_01 among events entering in the trailing {RANK_WINDOW} sessions (incl. today), pool >= {MIN_POOL}",
                           "floor": f"trailing 21-session median dollar volume >= ${FLOOR_USD:,.0f} at entry",
                           "book": "calendar-time, equal weight across open positions each session, cost on first and last session",
                           "market": "VW on previous-session cap (EW also carried)",
                           "blocks": "one return per MONTH (CANON section 58); Newey-West lag 4",
                           "ruler": "BETA FIRST; PRIMARY = beta-matched excess; raw excess SECONDARY"}}
    tape, years = _load_tape(smoke)
    ann, plc = _events(tape, years, smoke)
    ann["rank"] = pit_rank(ann)
    plc["rank"] = pit_rank(plc)
    out["events"] = {"announcements": int(len(ann)), "placebo": int(len(plc)),
                     "rankable_share": _r(float(ann["rank"].notna().mean()), 4),
                     "above_floor_share": _r(float((ann["dv21"] >= FLOOR_USD).mean()), 4)}
    # cross-check against R4's own event-level number on the same events
    top = _select(ann, 0.10)
    bot = ann[ann["rank"].notna() & (ann["rank"] <= 0.10) & (ann["dv21"] >= FLOOR_USD)]
    out["cross_check_vs_R4_event_level"] = {
        "mean_car_mkt_21_e2_top_decile_pct": _r(float(np.nanmean(top["car21_r4"])) * 100, 3),
        "mean_car_mkt_21_e2_bottom_decile_pct": _r(float(np.nanmean(bot["car21_r4"])) * 100, 3),
        "note": "R4's within-month deciles gave +1.804% top-minus-bottom at 21 sessions (t 7.37); this is the PIT trailing-window decile on the floored tape"}
    cells = {}
    first, last = _window(tape, ann, None, None)
    family_p = {}
    for hold in (5, 10, 21, 42):
        for name, share in (("top_decile", 0.10), ("top_quintile", 0.20)):
            sel = _select(ann, share)
            bk = calendar_book(tape, sel, hold)
            g = grade_daily_book(tape, bk, label=f"{name}|hold={hold}|25bps", first=first, last=last)
            cells[f"{name}|hold={hold}"] = g
            if g.get("PRIMARY_beta_matched", {}).get("p_two_sided") is not None:
                family_p[f"{name}|hold={hold}"] = g["PRIMARY_beta_matched"]["p_two_sided"]
            print(f"    {name:12s} H={hold:2d}: beta {g.get('beta')}  bm {g.get('PRIMARY_beta_matched',{}).get('annualised_pct')}%/yr t {g.get('PRIMARY_beta_matched',{}).get('t_nw')}  TW {g.get('terminal_wealth_net')} vs mkt {g.get('terminal_wealth_market_same_months')}  DD {g.get('max_drawdown_pct')}%", flush=True)
    # the short leg and long-short, as information (the book is long-only)
    sel_b = ann[ann["rank"].notna() & (ann["rank"] <= 0.10) & (ann["dv21"] >= FLOOR_USD)]
    bkb = calendar_book(tape, sel_b, 21)
    cells["bottom_decile|hold=21"] = grade_daily_book(tape, bkb, label="bottom_decile|hold=21|25bps", first=first, last=last)
    # the placebo through the SAME book
    pfirst, plast = _window(tape, plc, None, None)
    for hold in (5, 21):
        selp = _select(plc, 0.10)
        bkp = calendar_book(tape, selp, hold)
        cells[f"PLACEBO_top_decile|hold={hold}"] = grade_daily_book(tape, bkp, label=f"PLACEBO|hold={hold}", first=pfirst, last=plast)
    # daily series of the primary cell, for the leaderboard and the morning
    prim = calendar_book(tape, _select(ann, 0.10), 21)
    pd.DataFrame({"date": tape.dates, "net": prim["net"], "gross": prim["gross"], "n_open": prim["n_open"],
                  "mkt_vw": tape.mkt_vw, "mkt_ew": tape.mkt_ew}).to_parquet(OUT / "D1_primary_daily.parquet", index=False)
    out["cells"] = {k: _strip(v) for k, v in cells.items()}
    out["family"] = {"n_cells": len(family_p), "holm": R.holm(family_p), "bh_fdr": R.bh_fdr(family_p)}
    p = cells.get("top_decile|hold=21", {})
    out["headline"] = (f"top-decile reaction, hold 21, 25bps: beta {p.get('beta')}, beta-matched "
                       f"{p.get('PRIMARY_beta_matched', {}).get('annualised_pct')}%/yr t {p.get('PRIMARY_beta_matched', {}).get('t_nw')}, "
                       f"TW {p.get('terminal_wealth_net')} vs market {p.get('terminal_wealth_market_same_months')}, "
                       f"DD {p.get('max_drawdown_pct')}%; placebo t {cells.get('PLACEBO_top_decile|hold=21', {}).get('PRIMARY_beta_matched', {}).get('t_nw')}")
    out["family_max_p"] = max(out["family"]["holm"].values()) if family_p else None
    out["verdict"] = _verdict(p, cells.get("PLACEBO_top_decile|hold=21", {}))
    return out


def _verdict(p: dict, placebo: dict) -> str:
    if not p or "PRIMARY_beta_matched" not in p:
        return "CANNOT DETERMINE"
    t = p["PRIMARY_beta_matched"].get("t_nw") or 0.0
    eras = p.get("eras", {})
    same = sum(1 for v in eras.values() if v["sign"] > 0)
    pt = (placebo.get("PRIMARY_beta_matched") or {}).get("t_nw")
    tw_beats = (p.get("terminal_wealth_net") or 0) > (p.get("terminal_wealth_market_same_months") or 0)
    if t > 2.5 and same == len(eras) and (pt is None or pt < 1.0):
        return "PRODUCT_PROMISING: beta-matched positive, every era same sign, placebo does not reproduce it"
    if t > 1.5 and same >= 2:
        return "CONDITIONAL: positive but not in every era or not powered; not noise, not a claim"
    if tw_beats:
        return "BETA_ONLY: beats the market raw, not beta-matched"
    gross = p.get("terminal_wealth_gross") or 0
    if gross > 2 * (p.get("terminal_wealth_market_same_months") or 0):
        return ("CONSTRUCTION_SENSITIVE: the event-level effect is there GROSS and this "
                "construction's cost line eats it")
    return "FAILED_VARIANT: this construction does not carry the event-level effect"


def D2_reaction_mutations(smoke: bool = False) -> dict:
    """Variants around D1's primary on the DEV window; holdout printed and marked."""
    out = {"job": "D2_reaction_mutations", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "dev_window": f"1999..{DEV_LAST_MONTH}", "holdout": "2016-2024, printed beside every cell, used to choose NOTHING"}
    tape, years = _load_tape(smoke)
    ann, _ = _events(tape, years, smoke)
    ann["rank"] = pit_rank(ann)
    ann["rank_z"] = pit_rank(ann, col="z_reaction")
    med_cap = ann.groupby("month")["cap_e"].transform("median")
    variants = {
        "base_top_decile": (ann, "rank"),
        "z_scored_reaction_top_decile": (ann, "rank_z"),
        "x_sue_agrees": (ann[(ann["sue"] > 0) | ann["sue"].isna()], "rank"),
        "x_price_ge_5": (ann[ann["prc_e"] >= 5.0], "rank"),
        "x_small_half": (ann[ann["cap_e"] < med_cap], "rank"),
        "x_large_half": (ann[ann["cap_e"] >= med_cap], "rank"),
        "x_prior_mom_negative": (ann[ann["mom_12_1"] < 0], "rank"),
        "x_prior_mom_positive": (ann[ann["mom_12_1"] >= 0], "rank"),
        "x_volume_surge_ge_2": (ann[ann["vsurge"] >= 2.0], "rank"),
        "top_quintile": (ann, "rank"),
    }
    cells = {}
    dev_p = {}
    dev_lo, dev_hi = years[1], int(DEV_LAST_MONTH[:4])
    for name, (df, col) in variants.items():
        share = 0.20 if name == "top_quintile" else 0.10
        sel = _select(df, share, col=col)
        bk = calendar_book(tape, sel, 21)
        f, last_s = _window(tape, ann, dev_lo, dev_hi)
        g_dev = grade_daily_book(tape, bk, label=f"{name}|DEV", first=f, last=last_s)
        cell = {"DEV": _strip(g_dev)}
        if not smoke:
            f2, l2 = _window(tape, ann, 2016, 2024)
            cell["HOLDOUT_2016_2024_not_used_to_choose"] = _strip(grade_daily_book(tape, bk, label=f"{name}|HOLDOUT", first=f2, last=l2))
        cells[name] = cell
        pv = g_dev.get("PRIMARY_beta_matched", {}).get("p_two_sided")
        if pv is not None:
            dev_p[name] = pv
        print(f"    {name:32s} DEV beta {g_dev.get('beta')} bm {g_dev.get('PRIMARY_beta_matched',{}).get('annualised_pct')}%/yr t {g_dev.get('PRIMARY_beta_matched',{}).get('t_nw')}", flush=True)
    out["cells"] = cells
    out["family_dev"] = {"n": len(dev_p), "holm": R.holm(dev_p), "bh_fdr": R.bh_fdr(dev_p)}
    best = max(dev_p, key=lambda k: cells[k]["DEV"]["PRIMARY_beta_matched"]["t_nw"] or -9) if dev_p else None
    out["headline"] = (f"best DEV variant {best}: t {cells[best]['DEV']['PRIMARY_beta_matched']['t_nw']} "
                       f"(Holm {out['family_dev']['holm'].get(best)})" if best else "no cell graded")
    out["family_max_p"] = max(out["family_dev"]["holm"].values()) if dev_p else None
    out["verdict"] = "SCREEN on DEV; read the HOLDOUT column once, in the morning, for the top-3 only"
    return out


# ------------------------------------------------------------------------ G1

FEATURES = ["mom_12_1__xs", "net_rev_4w__xs", "ratio__xs", "consensus_rev_1m__xs", "disagreement__xs",
            "drawdown_60d__xs", "vol_60d__xs", "log_market_cap__xs", "ret_1m__xs", "ret_6m__xs",
            "coverage__xs", "target_rev_1m__xs", "log_close__xs", "dispersion__xs"]
W_MENU = (-1.0, -0.5, 0.0, 0.5, 1.0)
K_MENU = (20, 50, 100, 200, 300)
WEIGHT_MENU = ("ew", "rank", "vw")
HOLD_MENU = (None, 2, 4, 8)
FLOOR_MENU = (None, 3e6, 1e7)
DD_BUDGET = 0.35


def _genome_key(g: dict) -> str:
    return hashlib.sha1(json.dumps(g, sort_keys=True).encode()).hexdigest()[:16]


def random_genome(rng: random.Random) -> dict:
    w = {f: rng.choice(W_MENU) for f in FEATURES}
    if all(v == 0.0 for v in w.values()):
        w[rng.choice(FEATURES)] = 1.0
    return {"w": w, "k": rng.choice(K_MENU), "weight": rng.choice(WEIGHT_MENU),
            "hold_mult": rng.choice(HOLD_MENU), "floor": rng.choice(FLOOR_MENU)}


def mutate(g: dict, rng: random.Random) -> dict:
    g = json.loads(json.dumps(g))
    r = rng.random()
    if r < 0.6:
        f = rng.choice(FEATURES)
        g["w"][f] = rng.choice(W_MENU)
    elif r < 0.7:
        g["k"] = rng.choice(K_MENU)
    elif r < 0.8:
        g["weight"] = rng.choice(WEIGHT_MENU)
    elif r < 0.9:
        g["hold_mult"] = rng.choice(HOLD_MENU)
    else:
        g["floor"] = rng.choice(FLOOR_MENU)
    if all(v == 0.0 for v in g["w"].values()):
        g["w"][rng.choice(FEATURES)] = 1.0
    return g


def crossover(a: dict, b: dict, rng: random.Random) -> dict:
    c = json.loads(json.dumps(a))
    for f in FEATURES:
        if rng.random() < 0.5:
            c["w"][f] = b["w"][f]
    for key in ("k", "weight", "hold_mult", "floor"):
        if rng.random() < 0.5:
            c[key] = b[key]
    if all(v == 0.0 for v in c["w"].values()):
        c["w"][rng.choice(FEATURES)] = 1.0
    return c


def evaluate_genome(dev: pd.DataFrame, g: dict) -> dict:
    from learner import evaluate as E
    sig = np.zeros(len(dev))
    for f, w in g["w"].items():
        if w:
            sig += w * dev[f].fillna(0.0).to_numpy(dtype="float64")
    dev = dev.assign(_sig=sig)
    hold_k = None if g["hold_mult"] is None else int(g["k"] * g["hold_mult"])
    try:
        r = E.book(dev, "_sig", k=int(g["k"]), weight=g["weight"], cost_bps=COST_BPS,
                   hold_k=hold_k, tradable_floor=g["floor"], with_risk=True, return_series=True)
    except SystemExit as exc:
        return {"verdict": "REFUSED", "why": str(exc)[:200], "fitness": -9.0}
    if r.get("months", 0) < 150:
        return {"verdict": "REFUSED", "why": f"{r.get('months')} months", "fitness": -9.0}
    ser = r["_series"]
    net = ser["net"].astype("float64")
    mkt = ser["market"].reindex(net.index).astype("float64")
    x = mkt.to_numpy()
    y = net.to_numpy()
    beta = float(np.polyfit(x, y, 1)[0])
    ex_bm = y - beta * x
    dd = _max_dd(y)
    tw = float(np.prod(1.0 + y))
    fitness = math.log(max(tw, 1e-6)) - 2.0 * max(0.0, -dd - DD_BUDGET) * (len(y) / 12.0) / 10.0
    sub = {}
    for name, (a, b) in (("1999-2007", (1999, 2007)), ("2008-2015", (2008, 2015))):
        mask = np.array([a <= int(mm[:4]) <= b for mm in net.index])
        if mask.sum() >= 12:
            sub[name] = {"t": _r(_nw_t(ex_bm[mask], NW_LAG_M), 3), "bm_ann_pct": _r(float(ex_bm[mask].mean()) * 12 * 100, 3)}
    return {"verdict": "OK", "fitness": _r(fitness, 5), "beta": _r(beta, 4),
            "terminal_wealth_net": _r(tw, 4), "terminal_wealth_market": r.get("terminal_wealth_market_same_months"),
            "cagr_net": r.get("cagr_net"), "cagr_market": r.get("cagr_market"),
            "beta_matched_ann_pct": _r(float(ex_bm.mean()) * 12 * 100, 3), "t_beta_matched": _r(_nw_t(ex_bm, NW_LAG_M), 3),
            "t_raw_paired": r.get("t_stat_paired_vs_market"), "max_drawdown": _r(dd, 4),
            "mean_turnover": r.get("mean_turnover"), "months": r.get("months"), "eras_dev": sub}


def G1_evolve(hours: float = 5.0, pop: int = 32, seed: int = 20260908) -> dict:
    """Evolve on DEV only. Every evaluation is appended to G1_evaluations.jsonl."""
    cols = ["month", "permno", "fwd_1m", "mkt_vw_1m", "market_cap", "log_dollar_vol_20d"] + FEATURES
    df = pd.read_parquet(LONG, columns=cols)
    dev = df[df["month"] <= DEV_LAST_MONTH].copy()
    del df
    rng = random.Random(seed)
    log_path = OUT / "G1_evaluations.jsonl"
    cache: dict[str, dict] = {}
    if log_path.exists():            # resume: a night that restarts keeps its evidence
        for line in log_path.open(encoding="utf-8"):
            try:
                row = json.loads(line)
                cache[row["key"]] = row["result"]
            except Exception:  # noqa: BLE001
                pass
    n_eval = 0
    t_end = time.time() + hours * 3600.0
    best_curve = []

    def ev(g):
        nonlocal n_eval
        key = _genome_key(g)
        if key in cache:
            return cache[key]
        res = evaluate_genome(dev, g)
        res["key"] = key
        cache[key] = res
        n_eval += 1
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"key": key, "genome": g, "result": res, "utc": _now()}) + "\n")
        return res

    population = [random_genome(rng) for _ in range(pop)]
    gen = 0
    while time.time() < t_end and not (OUT / "STOP").exists():
        scored = sorted(((ev(g)["fitness"], g) for g in population), key=lambda t: -t[0])
        best = scored[0]
        best_curve.append({"gen": gen, "best_fitness": best[0], "n_eval": n_eval, "utc": _now()})
        if gen % 5 == 0:
            r0 = cache[_genome_key(best[1])]
            print(f"    gen {gen:4d}  evals {len(cache):6d}  best fitness {best[0]:.4f}  TW {r0.get('terminal_wealth_net')} "
                  f"vs mkt {r0.get('terminal_wealth_market')}  beta {r0.get('beta')}  bm t {r0.get('t_beta_matched')}  DD {r0.get('max_drawdown')}", flush=True)
        elite = [g for _, g in scored[:4]]
        nxt = list(elite)
        while len(nxt) < pop - 4:
            a = rng.choice(scored[:pop // 2])[1]
            b = rng.choice(scored[:pop // 2])[1]
            child = crossover(a, b, rng) if rng.random() < 0.5 else json.loads(json.dumps(a))
            child = mutate(child, rng) if rng.random() < 0.9 else child
            nxt.append(child)
        nxt += [random_genome(rng) for _ in range(4)]     # fresh blood every generation
        population = nxt
        gen += 1
    # the archive: top by fitness, plus the Pareto set over (fitness, t_bm, -dd)
    rows = [(k, v) for k, v in cache.items() if v.get("verdict") == "OK"]
    rows.sort(key=lambda kv: -kv[1]["fitness"])
    genomes = {}
    for line in log_path.open(encoding="utf-8"):
        try:
            row = json.loads(line)
            genomes[row["key"]] = row["genome"]
        except Exception:  # noqa: BLE001
            pass
    top = [{"key": k, "genome": genomes.get(k), **{kk: vv for kk, vv in v.items() if kk != "key"}} for k, v in rows[:10]]
    pareto = []
    for k, v in rows:
        dominated = any((o["fitness"] >= v["fitness"] and (o["t_beta_matched"] or -9) >= (v["t_beta_matched"] or -9)
                         and o["max_drawdown"] >= v["max_drawdown"] and o is not v) for _, o in rows[:400])
        if not dominated:
            pareto.append({"key": k, "genome": genomes.get(k), "fitness": v["fitness"], "beta": v["beta"],
                           "t_beta_matched": v["t_beta_matched"], "max_drawdown": v["max_drawdown"],
                           "terminal_wealth_net": v["terminal_wealth_net"], "terminal_wealth_market": v["terminal_wealth_market"]})
        if len(pareto) >= 25:
            break
    fits = np.array([v["fitness"] for _, v in rows])
    return {"job": "G1_evolve", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
            "dev_window": f"1999-03..{DEV_LAST_MONTH}", "holdout": "2016-2024 NEVER evaluated in this job",
            "search_space": {"features": FEATURES, "weights": W_MENU, "k": K_MENU, "weighting": WEIGHT_MENU,
                             "hold_mult": HOLD_MENU, "floor": FLOOR_MENU, "cost_bps": COST_BPS, "dd_budget": DD_BUDGET},
            "fitness": "log(terminal wealth net) - 2 * max(0, maxDD - budget) * years/10; beta printed on every row",
            "generations": gen, "evaluations_this_run": n_eval, "evaluations_total": len(cache),
            "fitness_distribution_all_evaluated": {"p50": _r(float(np.median(fits)), 4) if len(fits) else None,
                                                   "p90": _r(float(np.quantile(fits, 0.9)), 4) if len(fits) else None,
                                                   "max": _r(float(fits.max()), 4) if len(fits) else None},
            "top10_dev": top, "pareto_dev": pareto, "best_curve": best_curve[-50:],
            "headline": (f"{len(cache)} genomes evaluated on DEV; best fitness {rows[0][1]['fitness']} "
                         f"(TW {rows[0][1]['terminal_wealth_net']} vs mkt {rows[0][1]['terminal_wealth_market']}, "
                         f"beta {rows[0][1]['beta']}, bm t {rows[0][1]['t_beta_matched']}, DD {rows[0][1]['max_drawdown']})") if rows else "nothing evaluated",
            "verdict": "DEV ARCHIVE ONLY. The morning job G2 reads the holdout ONCE for the top-10 and the Pareto set, beside 200 random genomes' holdout as the null bar.",
            "family_max_p": None}


def G2_holdout_once(n_null: int = 200, seed: int = 7) -> dict:
    """Read the sealed window ONCE for the archive. The null bar is the holdout
    distribution of random genomes (never selected on anything)."""
    rec_path = OUT / "G1_evolve_run01.json"
    if not rec_path.exists():
        return {"job": "G2_holdout_once", "verdict": "CANNOT DETERMINE", "why": "no G1 receipt"}
    g1 = json.loads(rec_path.read_text(encoding="utf-8"))
    cols = ["month", "permno", "fwd_1m", "mkt_vw_1m", "market_cap", "log_dollar_vol_20d"] + FEATURES
    df = pd.read_parquet(LONG, columns=cols)
    hold = df[df["month"] > DEV_LAST_MONTH].copy()
    del df
    rng = random.Random(seed)
    null = [evaluate_genome(hold, random_genome(rng)) for _ in range(n_null)]
    null_t = np.array([v["t_beta_matched"] or 0.0 for v in null if v.get("verdict") == "OK"])
    null_tw = np.array([v["terminal_wealth_net"] for v in null if v.get("verdict") == "OK"])
    out_rows = []
    for row in (g1.get("top10_dev") or []) + (g1.get("pareto_dev") or []):
        if not row.get("genome"):
            continue
        h = evaluate_genome(hold, row["genome"])
        out_rows.append({"key": row["key"], "dev_fitness": row.get("fitness"), "dev_t_bm": row.get("t_beta_matched"),
                         "holdout": h,
                         "holdout_t_percentile_vs_random": _r(float((null_t < (h.get("t_beta_matched") or 0.0)).mean()), 3),
                         "holdout_tw_percentile_vs_random": _r(float((null_tw < (h.get("terminal_wealth_net") or 0.0)).mean()), 3)})
    return {"job": "G2_holdout_once", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
            "READ_ONCE": True, "holdout": f"{DEV_LAST_MONTH} < month <= 2024-12",
            "null_random_genomes": {"n": int(len(null_t)), "t_bm_p50": _r(float(np.median(null_t)), 3) if len(null_t) else None,
                                    "t_bm_p95": _r(float(np.quantile(null_t, 0.95)), 3) if len(null_t) else None,
                                    "tw_p50": _r(float(np.median(null_tw)), 4) if len(null_tw) else None},
            "archive_on_holdout": out_rows,
            "headline": f"{len(out_rows)} archive genomes read on the holdout once against {len(null_t)} random genomes",
            "verdict": "see archive_on_holdout: a genome whose holdout t sits below the random p95 learned the exam",
            "family_max_p": None}


JOBS = {"D1_reaction_book": D1_reaction_book, "D2_reaction_mutations": D2_reaction_mutations,
        "G1_evolve": G1_evolve, "G2_holdout_once": G2_holdout_once}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", choices=sorted(JOBS))
    ap.add_argument("--out", default=None)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--hours", type=float, default=float(os.getenv("NIGHT_G1_HOURS", "5")))
    a = ap.parse_args(argv)
    t0 = time.time()
    fn = JOBS[a.job]
    if a.job == "G1_evolve":
        payload = fn(hours=a.hours)
    elif a.job in ("D1_reaction_book", "D2_reaction_mutations"):
        payload = fn(smoke=a.smoke)
    else:
        payload = fn()
    payload["elapsed_s"] = round(time.time() - t0, 1)
    payload["written_utc"] = _now()
    payload["run"] = a.run
    out = Path(a.out) if a.out else OUT / f"{a.job}_run{a.run:02d}{'_smoke' if a.smoke else ''}.json"
    out.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"\n{a.job}: {payload.get('headline')}\n  verdict: {payload.get('verdict')}\n  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
