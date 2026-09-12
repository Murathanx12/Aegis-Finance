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


def evaluate_genome(dev: pd.DataFrame, g: dict, min_months: int = 150) -> dict:
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
    if r.get("months", 0) < min_months:
        # this floor was written for the 202-month DEV window. The holdout is 107
        # months, so a hard-coded 150 refuses EVERY genome on the sealed window --
        # a gate that cannot go green. It travels with the window now.
        return {"verdict": "REFUSED", "why": f"{r.get('months')} months < {min_months}", "fitness": -9.0}
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
    min_m = int(os.getenv("NIGHT_G2_MIN_MONTHS", "96"))     # 8 years of the 107 on offer
    null = [evaluate_genome(hold, random_genome(rng), min_months=min_m) for _ in range(n_null)]
    null_t = np.array([v["t_beta_matched"] or 0.0 for v in null if v.get("verdict") == "OK"])
    null_tw = np.array([v["terminal_wealth_net"] for v in null if v.get("verdict") == "OK"])
    out_rows = []
    for row in (g1.get("top10_dev") or []) + (g1.get("pareto_dev") or []):
        if not row.get("genome"):
            continue
        h = evaluate_genome(hold, row["genome"], min_months=min_m)
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
            "verdict": (("REFUSED: the null bar is EMPTY -- every random genome was rejected before a "
                         f"statistic was computed (min_months={min_m} vs a {len(hold['month'].unique()) if 'month' in hold else '?'}-month "
                         "holdout). Nothing was read; this is not a holdout result.")
                        if len(null_t) == 0 else
                        "see archive_on_holdout: a genome whose holdout t sits below the random p95 learned the exam"),
            "family_max_p": None}


# ------------------------------------------------- D3 / N1 shared book helpers

def _synth(net, gross, n_open, n_positions=0, mean_hold=0.0) -> dict:
    return {"net": np.asarray(net, dtype="float64"), "gross": np.asarray(gross, dtype="float64"),
            "n_open": np.asarray(n_open, dtype="float64"),
            "n_positions": int(n_positions), "mean_hold_sessions": float(mean_hold)}


def _diff_book(a: dict, b: dict) -> dict:
    """a - b on the sessions where BOTH legs are live.

    Both legs are built by the SAME construction (same entry convention, same
    equal weighting, same 25 bps, same universe), so whatever drag the
    construction itself carries appears in both and cancels here. What survives
    is the part attributable to the thing that differs between the legs.
    """
    both = (a["n_open"] > 0) & (b["n_open"] > 0)
    return _synth(np.where(both, a["net"] - b["net"], 0.0),
                  np.where(both, a["gross"] - b["gross"], 0.0),
                  np.where(both, np.minimum(a["n_open"], b["n_open"]), 0.0),
                  a["n_positions"] + b["n_positions"],
                  (a["mean_hold_sessions"] + b["mean_hold_sessions"]) / 2.0)


def _select_bottom(df: pd.DataFrame, share: float, floor: float | None = FLOOR_USD, col="rank") -> pd.DataFrame:
    m = df[col].notna() & (df[col] <= share)
    if floor is not None:
        m &= df["dv21"] >= floor
    return df[m]


def _select_all(df: pd.DataFrame, floor: float | None = FLOOR_USD, col="rank") -> pd.DataFrame:
    m = df[col].notna()
    if floor is not None:
        m &= df["dv21"] >= floor
    return df[m]


def _common_window(tape: Tape, a: pd.DataFrame, b: pd.DataFrame) -> tuple[int, int]:
    fa, la = _window(tape, a, None, None)
    fb, lb = _window(tape, b, None, None)
    return max(fa, fb), min(la, lb)


# ------------------------------------------------------------------------ D3

def D3_matched_control_grid(smoke: bool = False) -> dict:
    """Every announcement cell gets its OWN matched control, and the difference is graded.

    D1 printed `PLACEBO_top_decile` (-14.868%/yr beta-matched, t -2.672) and then
    graded every announcement cell against ZERO. The placebo carries no event
    information -- same names, same construction, same costs, announcement dates
    shifted +40 sessions -- so its -14.9%/yr IS the construction's own drag, and it
    is the baseline every cell owes a comparison to. Two consequences D1 could not
    see:

      * there is no placebo BOTTOM decile anywhere, so the -20%/yr t -4.7 that the
        proposed exit rule rests on has never met its matched control;
      * the long-short book (top decile minus bottom decile, both announcements)
        cancels the shared construction drag exactly and is TRADABLE. It is the
        product form of R4's decile spread and has never been graded with costs,
        in calendar time, with a beta.

    Nothing here is chosen on an outcome: the primary family is fixed as the four
    long-short holds before the job runs, and every other cell is labelled a
    diagnostic and kept out of the multiplicity correction.
    """
    out = {"job": "D3_matched_control_grid", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "question": ("Which of D1's negative cells are the SIGNAL and which are the "
                        "CONSTRUCTION? Difference every announcement leg against the same "
                        "leg built on placebo dates, and grade the self-financing long-short."),
           "corrects": ("D1_reaction_book_run01 graded every cell against zero while its own "
                        "placebo lost -14.868%/yr beta-matched (t -2.672) through the identical "
                        "book. Against that control the top decile is +10.7pp/yr and the bottom "
                        "decile only -5.1pp/yr, which is the opposite ordering to the one the "
                        "2026-09-08 night report drew from the same receipt."),
           "conventions": {"legs": "top decile / bottom decile, PIT trailing-63-session rank, $3m/day floor",
                           "control": "R4_placebo_offset40 -- same names, announcement dates +40 sessions",
                           "difference": "graded only on sessions where BOTH legs are live",
                           "PRIMARY_family": "LS_announcement at holds 5/10/21/42, fixed before the run",
                           "diagnostics": "every cell tagged DIAGNOSTIC / ZERO_COST / CONSTRUCTION_BASELINE is outside the family and carries no Holm"}}
    tape, years = _load_tape(smoke)
    ann, plc = _events(tape, years, smoke)
    ann["rank"] = pit_rank(ann)
    plc["rank"] = pit_rank(plc)
    first, last = _common_window(tape, ann, plc)
    out["window"] = {"first_session_date": str(tape.dates[first])[:10],
                     "last_session_date": str(tape.dates[last])[:10]}

    cells: dict[str, dict] = {}
    family_p: dict[str, float] = {}
    for hold in (5, 10, 21, 42):
        at = calendar_book(tape, _select(ann, 0.10), hold)
        ab = calendar_book(tape, _select_bottom(ann, 0.10), hold)
        pt_ = calendar_book(tape, _select(plc, 0.10), hold)
        pb = calendar_book(tape, _select_bottom(plc, 0.10), hold)
        g = grade_daily_book(tape, _diff_book(at, ab), label=f"LS_announcement|hold={hold}|25bps",
                             first=first, last=last)
        cells[f"LS_announcement|hold={hold}"] = g
        cells[f"LS_placebo|hold={hold}|DIAGNOSTIC"] = grade_daily_book(
            tape, _diff_book(pt_, pb), label=f"LS_placebo|hold={hold}", first=first, last=last)
        cells[f"placebo_bottom_decile|hold={hold}|THE_MISSING_CONTROL"] = grade_daily_book(
            tape, pb, label=f"placebo_bottom|hold={hold}", first=first, last=last)
        cells[f"top_minus_placebo_top|hold={hold}|DIAGNOSTIC"] = grade_daily_book(
            tape, _diff_book(at, pt_), label=f"top-plcTop|hold={hold}", first=first, last=last)
        cells[f"bottom_minus_placebo_bottom|hold={hold}|DIAGNOSTIC"] = grade_daily_book(
            tape, _diff_book(ab, pb), label=f"bot-plcBot|hold={hold}", first=first, last=last)
        p = g.get("PRIMARY_beta_matched", {}).get("p_two_sided")
        if p is not None:
            family_p[f"LS_announcement|hold={hold}"] = p
        bm = g.get("PRIMARY_beta_matched", {})
        pbm = cells[f"LS_placebo|hold={hold}|DIAGNOSTIC"].get("PRIMARY_beta_matched", {})
        cbm = cells[f"bottom_minus_placebo_bottom|hold={hold}|DIAGNOSTIC"].get("PRIMARY_beta_matched", {})
        print(f"    H={hold:2d}  LS_ann beta {g.get('beta')} bm {bm.get('annualised_pct')}%/yr t {bm.get('t_nw')} "
              f"TW {g.get('terminal_wealth_net')} DD {g.get('max_drawdown_pct')}% | LS_plc t {pbm.get('t_nw')} "
              f"| bot-minus-its-control {cbm.get('annualised_pct')}%/yr t {cbm.get('t_nw')}", flush=True)

    # the construction baseline: every floored announcer, no selection at all
    cells["all_announcers|hold=21|CONSTRUCTION_BASELINE"] = grade_daily_book(
        tape, calendar_book(tape, _select_all(ann), 21), label="all_announcers|hold=21",
        first=first, last=last)
    cells["all_placebo|hold=21|CONSTRUCTION_BASELINE"] = grade_daily_book(
        tape, calendar_book(tape, _select_all(plc), 21), label="all_placebo|hold=21",
        first=first, last=last)
    base = cells["all_announcers|hold=21|CONSTRUCTION_BASELINE"].get("PRIMARY_beta_matched", {})
    print(f"    construction baseline (every floored announcer, hold 21): "
          f"{base.get('annualised_pct')}%/yr t {base.get('t_nw')}", flush=True)

    # cost drag vs tilt drag: the same cells with the cost line switched off
    for nm, sel in (("ann_top", _select(ann, 0.10)), ("ann_bottom", _select_bottom(ann, 0.10)),
                    ("plc_top", _select(plc, 0.10)), ("plc_bottom", _select_bottom(plc, 0.10))):
        cells[f"ZERO_COST|{nm}|hold=21"] = grade_daily_book(
            tape, calendar_book(tape, sel, 21, cost_bps=0.0), label=f"ZERO_COST|{nm}",
            first=first, last=last)
    zc = cells["ZERO_COST|ann_top|hold=21"].get("PRIMARY_beta_matched", {})
    print(f"    zero-cost diagnostic, ann_top hold 21: {zc.get('annualised_pct')}%/yr t {zc.get('t_nw')} "
          f"(the same cell with 25 bps was -4.138%/yr)", flush=True)

    ls21 = cells["LS_announcement|hold=21"]
    lsp21 = cells["LS_placebo|hold=21|DIAGNOSTIC"]
    b21 = cells["bottom_minus_placebo_bottom|hold=21|DIAGNOSTIC"]
    out["cells"] = {k: _strip(v) for k, v in cells.items()}
    out["family"] = {"n_cells": len(family_p), "holm": R.holm(family_p), "bh_fdr": R.bh_fdr(family_p),
                     "members": "LS_announcement at 4 holds only; diagnostics excluded by design"}
    out["family_max_p"] = max(out["family"]["holm"].values()) if family_p else None
    lbm = ls21.get("PRIMARY_beta_matched", {})
    out["headline"] = (f"long-short reaction decile, hold 21, 25bps both legs: beta {ls21.get('beta')}, "
                       f"beta-matched {lbm.get('annualised_pct')}%/yr t {lbm.get('t_nw')}, "
                       f"TW {ls21.get('terminal_wealth_net')}, DD {ls21.get('max_drawdown_pct')}%; "
                       f"placebo LS t {lsp21.get('PRIMARY_beta_matched', {}).get('t_nw')}; "
                       f"bottom-vs-its-own-control {b21.get('PRIMARY_beta_matched', {}).get('annualised_pct')}%/yr "
                       f"t {b21.get('PRIMARY_beta_matched', {}).get('t_nw')}")
    out["verdict"] = _verdict_d3(ls21, lsp21, b21)
    out["what_the_morning_must_decide"] = (
        "If bottom-vs-its-own-control is flat, the proposed bottom-decile EXIT clause has no "
        "incremental content and must NOT go into hack3/hack6's next seal -- the -20%/yr was the "
        "construction, which an exit rule cannot harvest. If the long-short is positive after "
        "costs in all three eras while the placebo long-short is flat, the reaction book returns "
        "as a LONG-SHORT product experiment, not as the long-only book D1 killed.")
    return out


def _verdict_d3(ls: dict, ls_plc: dict, bot_ctl: dict) -> str:
    lbm = (ls.get("PRIMARY_beta_matched") or {})
    t = lbm.get("t_nw") or 0.0
    ann = lbm.get("annualised_pct") or 0.0
    eras = ls.get("eras", {})
    same = sum(1 for v in eras.values() if v["sign"] > 0)
    pt = (ls_plc.get("PRIMARY_beta_matched") or {}).get("t_nw")
    bt = (bot_ctl.get("PRIMARY_beta_matched") or {}).get("t_nw")
    if not eras:
        return "CANNOT DETERMINE"
    if len(eras) < 2:
        # a window short enough to hold one era cannot satisfy "every era"; saying so
        # beats a green verdict that only means the sample was too short to disagree
        return (f"CANNOT DETERMINE: only {len(eras)} era on this window; "
                f"beta-matched {ann}%/yr t {t}")
    if t > 2.5 and same == len(eras) and (pt is None or abs(pt) < 1.0):
        # "every era same SIGN" is a weak test: +28.7%/yr, +17.3%/yr, +2.1%/yr all
        # score sign +1 while the effect is plainly decaying out of the window the
        # money would actually be traded in. Name the newest era before stamping.
        newest_key = sorted(eras)[-1]
        newest = eras[newest_key]
        if (newest.get("t") or 0.0) < 1.0:
            return (f"ERA_DECAYED: pooled long-short {ann}%/yr t {t} and the placebo does not "
                    f"reproduce it, but the NEWEST era ({newest_key}) is "
                    f"{newest.get('beta_matched_ann_pct')}%/yr t {newest.get('t')}. Same sign in "
                    f"every era is not the same as alive today; this is a finding about the old "
                    f"window, not a book to seal.")
        return ("PRODUCT_PROMISING: the self-financing long-short survives 25 bps on both legs in "
                "every era and the placebo long-short does not reproduce it")
    if t > 1.5 and same >= 2 and ann > 0:
        return "CONDITIONAL: long-short positive after costs but not in every era or not powered"
    if bt is not None and bt < -2.0:
        return ("CONDITIONAL: the long-short does not pay, but the bottom decile IS worse than its "
                "own matched control -- the avoid/exit reading survives differencing")
    if ann <= 0 and (bt is None or bt > -1.0):
        return ("FAILED_VARIANT: differenced against its own control the reaction rank carries "
                "neither a tradable spread nor an incremental exit rule; D1's negative cells were "
                "the construction, which both legs share")
    return "CONDITIONAL: mixed; read the cells"


# ------------------------------------------------------------------------ N1

N1_FEATSETS = {
    # everything PIT-known at the close of the entry session
    "all": ["reaction", "z_reaction", "rank", "sue", "log_dv21", "sd60", "mom_12_1",
            "vsurge", "log_cap", "prc_e", "gap_prev"],
    # the ablation that matters: strip every reaction-derived column. If this scores
    # as well, the learner was trading size/momentum/volatility and the earnings
    # event was decoration.
    "no_reaction": ["sue", "log_dv21", "sd60", "mom_12_1", "vsurge", "log_cap", "prc_e", "gap_prev"],
    # the opposite corner: only the event, no context
    "reaction_only": ["reaction", "z_reaction", "rank", "sue"],
}

#: (horizon, featset, seed). The FIRST entry is the pre-specified primary; the rest
#: are the grid. Nothing downstream is allowed to promote a later row over the first
#: one on the strength of a holdout number.
N1_PRIMARY = (21, "all", 0)


def _n1_configs() -> list[tuple[int, str, int]]:
    """The primary is always first and always the same. NIGHT_N1_SEEDS only widens
    the seed axis, so a later pass measures seed stability without ever moving the
    configuration the verdict is read from."""
    seeds = tuple(int(x) for x in os.getenv("NIGHT_N1_SEEDS", "0,1,2").split(",") if x.strip())
    cfgs = [N1_PRIMARY]
    for hold in (21, 5, 10, 42):
        for fs in ("all", "no_reaction", "reaction_only"):
            for seed in seeds:
                c = (hold, fs, seed)
                if c not in cfgs:
                    cfgs.append(c)
    return cfgs


def fwd_market_adjusted(tape: Tape, df: pd.DataFrame, horizon: int) -> np.ndarray:
    """Gross compounded return from the close of e to the close of e+H, minus the
    VW market over the SAME sessions.

    This is the TRAINING target on purpose: costs belong to the book, not to the
    label. A position that ends early (delisting, a gap in the block) is truncated
    exactly the way `calendar_book` truncates it, so the label and the tradable
    book agree on what "holding for H" means.
    """
    out = np.full(len(df), np.nan)
    mkt = tape.mkt_vw
    permno = df["permno"].to_numpy()
    jj = df["j"].to_numpy()
    ee = df["e"].to_numpy()
    order = np.argsort(permno, kind="stable")      # one block slice per name, in name order
    for pos in order:
        p = int(permno[pos])
        blk = tape.blocks.get(p)
        if blk is None:
            continue
        s, e_ = blk
        di = tape.di[s:e_]
        ret = tape.ret[s:e_]
        k0 = int(jj[pos]) + 1
        if k0 >= len(di):
            continue
        k1 = min(len(di), k0 + horizon)
        seg_di = di[k0:k1]
        seg = ret[k0:k1]
        bad = np.flatnonzero(np.diff(np.r_[int(ee[pos]), seg_di]) != 1)
        if len(bad):
            seg_di = seg_di[:bad[0]]
            seg = seg[:bad[0]]
        if len(seg) == 0:
            continue
        out[pos] = float(np.prod(1.0 + seg) - 1.0) - float(np.prod(1.0 + mkt[seg_di]) - 1.0)
    return out


def _n1_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["log_dv21"] = np.log1p(df["dv21"].clip(lower=0))
    df["log_cap"] = np.log1p(df["cap_e"].abs())
    df["prc_e"] = df["prc_e"].abs()
    df = df.sort_values(["permno", "e"], kind="mergesort")
    df["gap_prev"] = df.groupby("permno", sort=False)["e"].diff()
    return df


def _walk_forward(df: pd.DataFrame, feats: list[str], target: str, tape: Tape,
                  horizon: int, seed: int, first_test_year: int = 2004) -> tuple[np.ndarray, list[dict]]:
    """Purged walk-forward: train on every event that has already PAID OFF before
    the test year opens, predict the test year, never look forward.

    The embargo is the horizon itself. An event entered H sessions before the test
    year starts is still open when the test year begins, so its label is contaminated
    by test-period returns; those rows are dropped from training rather than trusted.
    """
    import lightgbm as lgb

    pred = np.full(len(df), np.nan)
    e = df["e"].to_numpy()
    yr = df["year"].to_numpy()
    X = df[feats].astype("float64").reset_index(drop=True)   # keep names: lgb warns on mixed input
    y = df[target].to_numpy(dtype="float64")
    years = sorted({int(v) for v in yr if v >= first_test_year})
    folds = []
    for Y in years:
        start = tape.session_of(pd.Timestamp(f"{Y}-01-01"))
        tr = (yr < Y) & (e <= start - (horizon + 5)) & np.isfinite(y)
        te = yr == Y
        if tr.sum() < 5000 or te.sum() < 50:
            continue
        m = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.05, num_leaves=31,
                              min_child_samples=200, subsample=0.8, subsample_freq=1,
                              colsample_bytree=0.8, random_state=seed, n_jobs=4, verbose=-1)
        m.fit(X.loc[tr], y[tr])
        pred[te] = m.predict(X.loc[te])
        folds.append({"test_year": int(Y), "n_train": int(tr.sum()), "n_test": int(te.sum())})
    return pred, folds


def _n1_books(tape: Tape, df: pd.DataFrame, horizon: int) -> dict:
    """Rank the PREDICTION through the identical PIT machinery the reaction rank
    uses, then trade the identical calendar-time book at the identical 25 bps."""
    d = df[np.isfinite(df["pred"].to_numpy())].copy()
    d["prank"] = pit_rank(d, col="pred")
    top = calendar_book(tape, _select(d, 0.10, col="prank"), horizon)
    bot = calendar_book(tape, _select_bottom(d, 0.10, col="prank"), horizon)
    return {"long": top, "short": bot, "LS": _diff_book(top, bot)}


def _n1_grade(tape: Tape, bks: dict, first: int, last: int, tag: str) -> dict:
    return {f"{tag}|long_top_decile": grade_daily_book(tape, bks["long"], label=f"{tag}|long",
                                                       first=first, last=last),
            f"{tag}|long_short": grade_daily_book(tape, bks["LS"], label=f"{tag}|LS",
                                                  first=first, last=last)}


def _verdict_n1(ls: dict, ctl: dict, diff: dict) -> str:
    """The learner owes the same two questions the reaction book owed: does it pay
    after costs in every era, and does the identical pipeline fed dateless events
    manufacture the same number?"""
    lbm = (ls.get("PRIMARY_beta_matched") or {})
    cbm = (ctl.get("PRIMARY_beta_matched") or {})
    dbm = (diff.get("PRIMARY_beta_matched") or {})
    t = lbm.get("t_nw") or 0.0
    ann = lbm.get("annualised_pct") or 0.0
    ct = cbm.get("t_nw")
    eras = ls.get("eras", {})
    same = sum(1 for v in eras.values() if v["sign"] > 0)
    if not eras or len(eras) < 2:
        return f"CANNOT DETERMINE: {len(eras)} era on this window; beta-matched {ann}%/yr t {t}"
    if ct is not None and abs(ct) >= 2.0:
        dt = dbm.get("t_nw")
        return (f"CONSTRUCTION_SENSITIVE: the SAME pipeline trained on dateless placebo events "
                f"produces a long-short at t {ct}, so the raw t {t} is not evidence about earnings. "
                f"The differenced cell is {dbm.get('annualised_pct')}%/yr t {dt} -- that is the number "
                f"that means anything, and it is what the morning should read.")
    if t > 2.5 and same == len(eras) and (ct is None or abs(ct) < 1.0):
        return ("PRODUCT_PROMISING: the learner's long-short survives 25 bps in every era and the "
                "placebo-trained pipeline does not reproduce it")
    if t > 1.5 and same >= 2 and ann > 0:
        return "CONDITIONAL: learner long-short positive after costs but not in every era or not powered"
    return ("FAILED_VARIANT: a learner with every PIT feature on the event does not turn the "
            "reaction into a book that pays after costs")


def N1_train_reaction_learner(hours: float = 3.0, smoke: bool = False) -> dict:
    """Train a learner on the EVENT level, then trade its score through D1's book.

    Why event level: D3 shows the calendar-time construction carries a large drag
    that both the signal book and its placebo share. A model trained on BOOK returns
    would spend its capacity learning that drag. The label here is the event's own
    forward market-adjusted return, which the construction cannot contaminate; the
    construction is then applied to the model's output, where it belongs, and the
    result is differenced against a placebo learner trained the identical way.

    DEV is 1999-2015. The holdout is printed for every configuration and used to
    choose NOTHING -- the primary configuration is fixed in `N1_PRIMARY` before the
    grid runs.
    """
    out = {"job": "N1_train_reaction_learner", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "question": ("Given everything PIT-knowable at the close of the session after an "
                        "earnings print, can a learner rank the next H sessions better than the "
                        "reaction percentile alone -- and does any of it survive the construction "
                        "and its matched control?"),
           "design": {"target": "gross compounded return e -> e+H minus VW market over the same sessions",
                      "validation": "purged walk-forward by year, embargo = the horizon, first test year 2004",
                      "model": "LightGBM regressor, 400 trees, NaN handled natively (no fillna)",
                      "book": "identical to D1: PIT rank of the PREDICTION, top decile, $3m/day floor, 25 bps a side",
                      "control": "the identical pipeline trained and traded on R4_placebo_offset40",
                      "primary": f"hold={N1_PRIMARY[0]}, featset={N1_PRIMARY[1]}, seed={N1_PRIMARY[2]} -- fixed before the run",
                      "holdout": "2016-2024 printed for every config, used to choose nothing"}}
    tape, years = _load_tape(smoke)
    ann, plc = _events(tape, years, smoke)
    ann["rank"] = pit_rank(ann)
    plc["rank"] = pit_rank(plc)
    ann = _n1_features(ann)
    plc = _n1_features(plc)
    first, last = _common_window(tape, ann, plc)
    dev_first, dev_last = _window(tape, ann, 1999, 2015)
    hold_first, hold_last = _window(tape, ann, 2016, 2024)

    # a smoke run must never poison the night's resume cache: the config key
    # ("H21|all|s0") says nothing about which tape produced it
    log_path = OUT / ("N1_configs_smoke.jsonl" if smoke else "N1_configs.jsonl")
    done: dict[str, dict] = {}
    if log_path.exists():
        for line in log_path.open(encoding="utf-8"):
            try:
                row = json.loads(line)
                done[row["key"]] = row["result"]
            except Exception:  # noqa: BLE001
                pass

    targets: dict[int, tuple[np.ndarray, np.ndarray]] = {}

    def target_for(h: int):
        if h not in targets:
            t0 = time.time()
            targets[h] = (fwd_market_adjusted(tape, ann, h), fwd_market_adjusted(tape, plc, h))
            print(f"    target H={h}: built in {time.time() - t0:.0f}s", flush=True)
        return targets[h]

    t_end = time.time() + hours * 3600.0
    ran = 0
    for hold, fs, seed in _n1_configs():
        if time.time() > t_end or (OUT / "STOP").exists():
            print("    time box or STOP reached; ending the grid", flush=True)
            break
        key = f"H{hold}|{fs}|s{seed}"
        if key in done:
            continue
        t0 = time.time()
        ya, yp = target_for(hold)
        ann["y"] = ya
        plc["y"] = yp
        feats = N1_FEATSETS[fs]
        pa, folds = _walk_forward(ann, feats, "y", tape, hold, seed)
        pp, _ = _walk_forward(plc, feats, "y", tape, hold, seed)
        ann["pred"] = pa
        plc["pred"] = pp
        ba = _n1_books(tape, ann, hold)
        bp = _n1_books(tape, plc, hold)
        cells = {}
        cells.update(_n1_grade(tape, ba, first, last, "learner_full"))
        cells.update(_n1_grade(tape, bp, first, last, "placebo_learner_full|CONTROL"))
        cells.update(_n1_grade(tape, ba, dev_first, dev_last, "learner_DEV"))
        cells.update(_n1_grade(tape, ba, hold_first, hold_last, "learner_HOLDOUT|read_not_chosen"))
        # the learner's long-short MINUS the same pipeline trained on dateless events:
        # whatever the pipeline manufactures from no information is subtracted here
        cells["learner_minus_control|long_short"] = grade_daily_book(
            tape, _diff_book(ba["LS"], bp["LS"]), label="learner-control|LS", first=first, last=last)
        ic = float(pd.Series(pa).corr(pd.Series(ann["y"].to_numpy()), method="spearman"))
        res = {"config": {"hold": hold, "featset": fs, "seed": seed, "n_features": len(feats)},
               "folds": len(folds), "n_scored": int(np.isfinite(pa).sum()),
               "spearman_ic_pooled": _r(ic, 5),
               "cells": {k: _strip(v) for k, v in cells.items()},
               "elapsed_s": round(time.time() - t0, 1)}
        done[key] = res
        ran += 1
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"key": key, "result": res, "utc": _now()}, default=str) + "\n")
        lf = cells["learner_full|long_short"].get("PRIMARY_beta_matched", {})
        cf = cells["placebo_learner_full|CONTROL|long_short"].get("PRIMARY_beta_matched", {})
        hf = cells["learner_HOLDOUT|read_not_chosen|long_short"].get("PRIMARY_beta_matched", {})
        print(f"    {key:24s} IC {ic:+.4f}  LS {lf.get('annualised_pct')}%/yr t {lf.get('t_nw')} "
              f"| control LS t {cf.get('t_nw')} | holdout LS {hf.get('annualised_pct')}%/yr t {hf.get('t_nw')} "
              f"[{time.time() - t0:.0f}s]", flush=True)

    pk = f"H{N1_PRIMARY[0]}|{N1_PRIMARY[1]}|s{N1_PRIMARY[2]}"
    prim = done.get(pk)
    out["configs_run_this_session"] = ran
    out["configs_total"] = len(done)
    out["grid"] = {k: {"ic": v.get("spearman_ic_pooled"),
                       "LS_full_ann_pct": (v["cells"].get("learner_full|long_short", {})
                                           .get("PRIMARY_beta_matched", {}).get("annualised_pct")),
                       "LS_full_t": (v["cells"].get("learner_full|long_short", {})
                                     .get("PRIMARY_beta_matched", {}).get("t_nw")),
                       "LS_control_t": (v["cells"].get("placebo_learner_full|CONTROL|long_short", {})
                                        .get("PRIMARY_beta_matched", {}).get("t_nw")),
                       "LS_holdout_t": (v["cells"].get("learner_HOLDOUT|read_not_chosen|long_short", {})
                                        .get("PRIMARY_beta_matched", {}).get("t_nw"))}
                  for k, v in sorted(done.items())}
    out["primary"] = prim
    if prim:
        ls = prim["cells"].get("learner_full|long_short", {})
        ctl = prim["cells"].get("placebo_learner_full|CONTROL|long_short", {})
        lbm = ls.get("PRIMARY_beta_matched", {})
        cbm = ctl.get("PRIMARY_beta_matched", {})
        out["headline"] = (f"primary {pk}: pooled Spearman IC {prim.get('spearman_ic_pooled')}; "
                           f"long-short beta-matched {lbm.get('annualised_pct')}%/yr t {lbm.get('t_nw')}, "
                           f"TW {ls.get('terminal_wealth_net')}, DD {ls.get('max_drawdown_pct')}%; "
                           f"placebo learner LS t {cbm.get('t_nw')}")
        out["verdict"] = _verdict_n1(ls, ctl, prim["cells"].get("learner_minus_control|long_short", {}))
    else:
        out["headline"] = f"{len(done)} configs on disk; the primary {pk} did not finish inside the time box"
        out["verdict"] = "CANNOT DETERMINE"
    out["family_max_p"] = None
    out["note_on_multiplicity"] = (
        "The grid is a SEARCH, not a family of claims: only the pre-specified primary carries a "
        "verdict. Any other row that looks good is a candidate for a future pre-registered lane, "
        "and its holdout column was read but chose nothing.")
    return out


# ------------------------------------------------------------------------ D4

def _nw_se(x: np.ndarray, lag: int = NW_LAG_M) -> float | None:
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 12:
        return None
    u = x - x.mean()
    s = float(np.dot(u, u)) / n
    for L in range(1, lag + 1):
        w = 1.0 - L / (lag + 1.0)
        s += 2.0 * w * float(np.dot(u[L:], u[:-L])) / n
    return math.sqrt(max(s, 1e-18) / n)


def _ex_bm_series(cell: dict) -> tuple[np.ndarray, np.ndarray]:
    """Monthly beta-matched excess and its month labels, from a graded cell."""
    m = cell.get("_monthly")
    if not m:
        return np.empty(0), np.empty(0)
    net = np.asarray(m["net"], dtype="float64")
    mkt = np.asarray(m["market"], dtype="float64")
    return net - (cell.get("beta") or 0.0) * mkt, np.asarray(m["months"])


def _split_test(cell: dict, split: str = DEV_LAST_MONTH) -> dict:
    """Is the newest era actually DIFFERENT, or just noisier?

    Same-sign-every-era said yes to a book that pays 28.7%/yr then 2.1%/yr. The
    honest question is whether the difference between the halves is itself
    distinguishable from zero -- a decay you cannot measure is not a decay you
    should act on, and one you can is a reason not to seal the book.
    """
    ex, months = _ex_bm_series(cell)
    if len(ex) == 0:
        return {"verdict": "CANNOT DETERMINE: no monthly series on the cell"}
    a, b = ex[months <= split], ex[months > split]
    if len(a) < 24 or len(b) < 24:
        return {"verdict": f"CANNOT DETERMINE: {len(a)} / {len(b)} months either side of {split}"}
    sa, sb = _nw_se(a), _nw_se(b)
    if sa is None or sb is None:
        return {"verdict": "CANNOT DETERMINE: Newey-West se undefined"}
    diff = float(a.mean() - b.mean())
    se = math.sqrt(sa ** 2 + sb ** 2)
    t = diff / se if se > 0 else None
    return {"early_ann_pct": _r(float(a.mean()) * 12 * 100, 3), "early_months": int(len(a)),
            "late_ann_pct": _r(float(b.mean()) * 12 * 100, 3), "late_months": int(len(b)),
            "decay_ann_pct": _r(diff * 12 * 100, 3), "t_of_difference": _r(t, 3),
            "p_two_sided": R._p_two_sided(t),
            "verdict": ("DECAY IS MEASURABLE: the two halves differ" if t is not None and t > 2.0 else
                        "DECAY NOT ESTABLISHED: the halves are not distinguishable at this power -- "
                        "the late window is weaker but the difference is inside the noise")}


def D4_ls_robustness_and_decay(smoke: bool = False) -> dict:
    """D3 found a long-short that is clean pooled and ~zero in 2016-2024. Two
    questions decide whether that is a finding or an artefact, and both are free:

      1. Is it robust to the construction knobs nobody chose on purpose -- the
         cost rate, the liquidity floor, the decile width? A result that only
         exists at one corner of that cube is a corner, not a mechanism.
      2. Is the decay MEASURABLE, or is the newest era merely shorter and noisier?
         "Same sign in every era" cannot tell those apart; a two-sample
         Newey-West test on the halves can.

    Every cell carries its placebo twin, so nothing here is read against zero --
    which is the error this whole second queue exists to correct.
    """
    out = {"job": "D4_ls_robustness_and_decay", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "question": ("Does D3's +15.919%/yr t 3.864 long-short survive the construction knobs, "
                        "and is its decay to +2.112%/yr in 2016-2024 measurable or noise?"),
           "builds_on": "D3_matched_control_grid_run01.json / D3_verdict_amendment.json",
           "conventions": {"cell": "long top decile, short bottom decile, calendar time, PIT trailing-63 rank",
                           "control": "the identical grid on R4_placebo_offset40",
                           "split": f"early <= {DEV_LAST_MONTH}, late after it",
                           "note": "the SHORT leg's borrow cost is still not modelled anywhere in this grid"}}
    tape, years = _load_tape(smoke)
    ann, plc = _events(tape, years, smoke)
    ann["rank"] = pit_rank(ann)
    plc["rank"] = pit_rank(plc)
    first, last = _common_window(tape, ann, plc)

    def ls_cell(df, width, hold, cost, floor):
        top = calendar_book(tape, _select(df, width, floor=floor), hold, cost_bps=cost)
        bot = calendar_book(tape, _select_bottom(df, width, floor=floor), hold, cost_bps=cost)
        return _diff_book(top, bot)

    grid = {}
    hold = 21
    for cost in (0.0, 10.0, 25.0, 50.0):
        for width in (0.05, 0.10, 0.20):
            for floor in (0.0, 1_000_000.0, 3_000_000.0, 10_000_000.0):
                key = f"cost={cost:g}|width={width:g}|floor={floor/1e6:g}m"
                a = grade_daily_book(tape, ls_cell(ann, width, hold, cost, floor or None),
                                     label=f"LS|{key}", first=first, last=last)
                p = grade_daily_book(tape, ls_cell(plc, width, hold, cost, floor or None),
                                     label=f"LSplc|{key}", first=first, last=last)
                bm, pbm = a.get("PRIMARY_beta_matched", {}), p.get("PRIMARY_beta_matched", {})
                st = _split_test(a)
                grid[key] = {"beta": a.get("beta"), "ann_pct": bm.get("annualised_pct"),
                             "t_nw": bm.get("t_nw"), "p": bm.get("p_two_sided"),
                             "terminal_wealth_net": a.get("terminal_wealth_net"),
                             "max_drawdown_pct": a.get("max_drawdown_pct"),
                             "control_t": pbm.get("t_nw"), "control_ann_pct": pbm.get("annualised_pct"),
                             "eras": {e: (v["beta_matched_ann_pct"], v["t"]) for e, v in a.get("eras", {}).items()},
                             "split_test": st}
                print(f"    {key:34s} {bm.get('annualised_pct'):>8}%/yr t {bm.get('t_nw'):>7} "
                      f"| control t {pbm.get('t_nw'):>7} | late {st.get('late_ann_pct')}%/yr "
                      f"| decay t {st.get('t_of_difference')}", flush=True)

    base_key = "cost=25|width=0.1|floor=3m"
    base = grid.get(base_key, {})
    live = [k for k, v in grid.items() if (v.get("t_nw") or 0) > 2.0]
    live_ctl = [k for k, v in grid.items() if abs(v.get("control_t") or 0) > 2.0]
    # the year-by-year curve of D3's own cell, for the morning's eyes
    a = grade_daily_book(tape, ls_cell(ann, 0.10, 21, 25.0, FLOOR_USD),
                         label="LS|D3 primary", first=first, last=last)
    ex, months = _ex_bm_series(a)
    by_year = {}
    for y in sorted({m[:4] for m in months}):
        sel = np.array([m[:4] == y for m in months])
        if sel.sum() >= 6:
            by_year[y] = _r(float(ex[sel].mean()) * 12 * 100, 2)
    out["grid"] = grid
    out["cells_significant_of_total"] = f"{len(live)}/{len(grid)}"
    out["control_cells_significant"] = f"{len(live_ctl)}/{len(grid)} (a placebo cell that goes significant is a warning, not a result)"
    out["by_year_beta_matched_ann_pct"] = by_year
    out["split_test_on_D3_primary"] = _split_test(a)
    out["headline"] = (f"{len(live)}/{len(grid)} construction corners keep the long-short at |t|>2 "
                       f"(placebo: {len(live_ctl)}/{len(grid)}); at D3's own corner "
                       f"{base.get('ann_pct')}%/yr t {base.get('t_nw')}; decay "
                       f"{out['split_test_on_D3_primary'].get('decay_ann_pct')}%/yr "
                       f"t {out['split_test_on_D3_primary'].get('t_of_difference')}")
    frac = len(live) / max(len(grid), 1)
    st = out["split_test_on_D3_primary"]
    # ~5% of 48 correlated cells firing in the PLACEBO grid is chance (2.4 expected);
    # a placebo grid that lights up broadly means the construction, not the event.
    expected_ctl = max(3, int(0.10 * len(grid)))
    if len(live_ctl) > expected_ctl:
        v = (f"CONTROL_ALSO_FIRES: {len(live)}/{len(grid)} corners survive, but so do "
             f"{len(live_ctl)}/{len(grid)} PLACEBO corners (chance would be ~{0.05 * len(grid):.1f}). "
             f"The grid is measuring the construction, not the event. ")
    elif frac >= 0.7:
        v = (f"ROBUST: {len(live)}/{len(grid)} corners survive and the placebo grid stays quiet "
             f"({len(live_ctl)}/{len(grid)}). ")
    elif frac >= 0.4:
        v = (f"CONSTRUCTION_SENSITIVE: {len(live)}/{len(grid)} corners survive -- the effect "
             f"depends on knobs nobody chose on evidence. ")
    else:
        v = (f"FAILED_VARIANT: only {len(live)}/{len(grid)} corners survive; D3's cell was a corner. ")
    out["verdict"] = v + str(st.get("verdict"))
    return out


from scripts.night_rw_random_windows import RW1_random_windows   # noqa: E402  the 09-09 randomised windows


def _lazy(module: str, attr: str):
    """Resolve a job at CALL time, not at import time.

    `night_rw2_event_windows` imports this module's event machinery, so importing
    it from here at module scope makes `python -m scripts.night_rw2_event_windows`
    a circular import: the partially initialised module has no `RW2_event_windows`
    yet. Registering a loader keeps both entry points working -- the queue can
    dispatch the job, and the job's own module can still be run directly.
    """
    def call(*a, **kw):
        import importlib
        return getattr(importlib.import_module(module), attr)(*a, **kw)
    call.__name__ = attr
    return call


JOBS = {"D1_reaction_book": D1_reaction_book, "D2_reaction_mutations": D2_reaction_mutations,
        "RW1_random_windows": RW1_random_windows,
        "RW2_event_windows": _lazy("scripts.night_rw2_event_windows", "RW2_event_windows"),
        "G3_evolve_v2": _lazy("scripts.night_g3_evolve_v2", "G3_evolve_v2"),
        "N2_learner_v3": _lazy("scripts.night_n2_learner_v3", "N2_learner_v3"),
        "P6_bars_and_regret": _lazy("scripts.night_p6_bars_and_regret", "P6_bars_and_regret"),
        "E1_news_return_panel": _lazy("scripts.night_e1_news_return_panel", "E1_news_return_panel"),
        # N-C 2026-09-11: the join as a NIGHTLY APPEND. Reads only the corpus
        # sources the registry marks `label_source: true`, anchors on the
        # `first_seen_utc` WE wrote, and refuses the whole append on a single
        # PIT violation. Cheap enough to run after every pull.
        "E1_append": _lazy("scripts.night_e1_news_return_panel", "E1_append"),
        "C2_curriculum_transfer": _lazy("scripts.night_c2_curriculum_transfer", "C2_curriculum_transfer"),
        # 2026-09-10: P7 gives the 2025-26 replay a point-in-time universe (the
        # liquidity look-ahead only -- the bar source is itself survivor-screened,
        # which its receipt says out loud). R2_widened needs llama-server UP, so
        # it belongs after the model server in any queue that includes it.
        "P7_pit_universe_vintage": _lazy("scripts.night_p7_pit_universe", "P7_pit_universe_vintage"),
        "R2_widened_panelB": _lazy("scripts.night_r2_monthly_llm", "R2_widened"),
        # N3 2026-09-10: FAILED_VARIANT on its first run (the frozen embedding
        # beats neither TF-IDF nor shuffled text). Registered anyway -- the
        # panel grows nightly and the head is refit in minutes, so this is the
        # cheapest standing check that the text ever starts carrying something.
        "N3_frozen_embedding_head": _lazy("scripts.night_n3_frozen_embedding_head",
                                          "N3_frozen_embedding_head"),
        # 2026-09-12, chunk 5b T3: the historical leg of lane B's first four
        # books. Three of the four cannot decide on the 2025-26 ticker bars
        # (their panels are CRSP-permno-keyed and CRSP ends 2024-12-31), so
        # this is where their evidence comes from. ONE job over FOUR primary
        # tests, so the family Holm runs inside it.
        "B_first_books_replay": _lazy("scripts.night_first_books_replay",
                                      "B_first_books_replay"),
        # 2026-09-12, chunk 7: lane X under the P1-P6 protocol. All four need
        # llama-server for their model legs and NONE of them start it -- each
        # writes PENDING_MODEL with its cell list frozen and hashed when the
        # reader is not answering, so the run that happens when it is up asks
        # the same question rather than a similar one. Their receipts carry a
        # P1_P6 block or `night_leaderboard_sync` refuses the row.
        # 2026-09-12, chunk 8 (E5): the stopping rules. Reads the evaluation
        # logs G3 already wrote, deflates each lineage's Sharpe for how many
        # genomes the search tried, and writes DEPRIORITIZED/ACTIVE/
        # CANNOT_DETERMINE to `G3_lineage_verdicts.jsonl`. Cheap (seconds), no
        # LLM, and it changes what the NEXT night breeds from.
        "E5_stopping_rules": _lazy("scripts.night_stopping_rules",
                                   "E5_stopping_rules"),
        # 2026-09-12, chunk 8 (roadmap 11c): decay-blended target weights swept
        # WITH the cost axis, every decayed cell beside its own lambda=0 twin.
        "E_decay_sweep": _lazy("scripts.night_decay_sweep", "E_decay_sweep"),
        "X_anon_gap": _lazy("scripts.night_x_anonymisation_gap", "X_anon_gap"),
        "L3_lookahead": _lazy("scripts.night_l3_lookahead", "L3_lookahead"),
        "X2_elasticity": _lazy("scripts.night_x2_elasticity", "X2_elasticity"),
        "X4_regime_route": _lazy("scripts.night_x4_regime_route", "X4_regime_route"),
        "D3_matched_control_grid": D3_matched_control_grid,
        "N1_train_reaction_learner": N1_train_reaction_learner,
        "D4_ls_robustness_and_decay": D4_ls_robustness_and_decay,
        "G1_evolve": G1_evolve, "G2_holdout_once": G2_holdout_once}

#: jobs that take a `--hours` time box rather than running to completion
TIMEBOXED = {"G1_evolve", "N1_train_reaction_learner", "G3_evolve_v2"}


#: jobs whose script checkpoints per unit of work and accepts `--resume`.
#: Grow this as long jobs gain checkpoints; a job NOT in here is restarted from
#: zero, which is honest but wasteful, and the receipt says which happened.
RESUMABLE = {"G3_evolve_v2"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", choices=sorted(JOBS))
    ap.add_argument("--out", default=None)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--hours", type=float, default=float(os.getenv("NIGHT_G1_HOURS", "5")))
    ap.add_argument("--seed", type=int, default=20260909, help="RW1/RW2 window draw")
    # 2026-09-10: a job that can continue a killed run. Only jobs listed in
    # `RESUMABLE` accept it -- forwarding --resume to a job whose function has no
    # such parameter is a TypeError three hours into the night, which is exactly
    # the class of failure this flag exists to prevent.
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args(argv)
    if a.resume and a.job not in RESUMABLE:
        print(f"REFUSED: {a.job} has no checkpoint to resume from "
              f"(resumable jobs: {sorted(RESUMABLE)})", flush=True)
        return 2
    t0 = time.time()
    fn = JOBS[a.job]
    if a.job == "G3_evolve_v2":
        payload = fn(hours=a.hours, resume=a.resume, run=a.run)
    elif a.job == "G1_evolve":
        payload = fn(hours=a.hours)
    elif a.job == "N1_train_reaction_learner":
        payload = fn(hours=a.hours, smoke=a.smoke)
    elif a.job in ("D1_reaction_book", "D2_reaction_mutations", "D3_matched_control_grid", "D4_ls_robustness_and_decay"):
        payload = fn(smoke=a.smoke)
    elif a.job in ("RW1_random_windows", "RW2_event_windows"):
        payload = fn(seed=a.seed, smoke=a.smoke)
    elif a.job in ("N2_learner_v3", "B_first_books_replay", "E5_stopping_rules",
                   "E_decay_sweep"):
        payload = fn(smoke=a.smoke)
    elif a.job in ("X_anon_gap", "L3_lookahead", "X2_elasticity", "X4_regime_route"):
        # the X lane takes the run number: its frozen cell list is filed under
        # it, and a second run that overwrote the first's list would destroy the
        # only thing that makes a PENDING_MODEL receipt reproducible.
        payload = fn(smoke=a.smoke, run=a.run)
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
