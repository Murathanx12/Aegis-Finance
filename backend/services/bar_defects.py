"""Broken price histories in the daily bars: found from the data, cut at the reader.

WHY (2026-09-29)
================
The strategy library's panel showed LINE on 2024-09-30 at 89,574% annual
volatility and +46,000% 12-1 momentum, and 172 of 2,080 momentum top-20 slots
sat on rows like it (`docs/research_notes/2026-09-29/sizing_on_move_size_2026-09-29.md`
§7). `stitched_tickers` did not cut LINE because the vendor never left a GAP:
it served Linn Energy's last price ($0.1641) as a ZERO-VOLUME bar on every
session from 2016-05-24 to 2024-07-24, and Lineage Inc's IPO at $73.66 the next
day. 278,017 such zero-volume rows sit in the survivorship-free panel. A gap
detector that counts bars cannot see a hole the vendor filled.

WHAT THIS MODULE DECIDES, FROM THE BARS ALONE (no network, no second file)
=========================================================================
A  DARK       a zero-volume bar is not a trade. Zero-volume rows in a run of at
              least `DARK_RUN_MIN` sessions are removed, and so is any single
              zero-volume row whose close moved more than `NONTRADE_PRINT_TOL`
              from the last traded close (a price nobody paid). After this the
              hole is a real gap and `stitched_tickers.detect` judges it with its
              own evidence (registrant, inactive source, price jump). A symbol
              whose volume is never positive carries no volume information and
              is left alone.
B  SPIKE      a one-day move of at least `SPIKE_RATIO`x that reverses to within
              `SPIKE_RESIDUAL` of where it started inside `SPIKE_WINDOW`
              sessions is a bad print: the rows between the jump and the
              reversal are removed.
C  QUIET      a level change of at least `BREAK_RATIO`x on volume below
              `QUIET_VOL_MULT` x the trailing median volume is not a market
              move (a real 3x day trades 10-500x its normal volume; measured
              against CRSP below) but an unadjusted corporate action or a
              re-issued equity -> the symbol is CUT there.
D  GAP JUMP   a level change of at least `BREAK_RATIO`x across a missing
              session (after A) -> CUT there (bankruptcy re-emergence: VAL, GPOR,
              CBL, XOG, WLL traded new equity after a dark run under the old
              ticker).

A cut works as in `stitched_tickers`: the earlier segment becomes `SYM#k` (a dead
name that takes the delisting fill), the symbol starts again at the break, and
every trailing feature that would straddle it is NaN until the new segment has
its own history. No price is changed; A and B remove rows that were never trades.

CALIBRATION (the second source)
===============================
Every rule was checked against CRSP daily (`wrds/crsp_dsf_<y>.parquet`,
2016-2024, linked by ticker and name dates): of the moves >= 3x in one day that
CRSP also covers and no zero-volume bar precedes, 78 were real and 23 were vendor defects; no real move had
volume below 2x its trailing median (the lowest was GPOR at 2.2x), and five
defects did. Rule C is therefore precise on what it cuts and incomplete by
design: spin-offs booked as price drops on heavy volume (CNX 2017-11-29, RTX
2020-04-03, IAC 2020-07-01) are NOT separable from real crashes by price and
volume alone, are NOT cut, and are counted by the audit CLI against CRSP.

THE BOOK REFUSAL
================
What the screen cannot prove it keeps and names: a >= `BREAK_RATIO`x move on
`QUIET_VOL_MULT`-`SUSPECT_VOL_MULT`x volume is a SUSPECT (on CRSP, nine of the
residual defects -- the spin-offs, CUR, RMGN -- sit there, beside one real move).
`flagged_keys(panel)` marks every (date, name) whose 12-1 window or hold window
contains a suspect, and `assert_book_clean(holdings, flagged)` REFUSES a book
when more than `BOOK_MAX_SHARE` of its slots sit on them. `implausible_rows`
(vol_63 > 3, |12-1| > 20) is DESCRIPTIVE only: after the screen the rows it
marks in a momentum top-20 are GME, QUBT, MARA, NVAX, SNDK -- real.

    python -m backend.services.bar_defects          # audit + receipt (reads CRSP, frozen books)
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from backend import config as _cfg

logger = logging.getLogger(__name__)

DARK_RUN_MIN = int(getattr(_cfg, "BAR_DEFECT_DARK_RUN_MIN", 5))
NONTRADE_PRINT_TOL = float(getattr(_cfg, "BAR_DEFECT_NONTRADE_PRINT_TOL", 0.01))
SPIKE_RATIO = float(getattr(_cfg, "BAR_DEFECT_SPIKE_RATIO", 4.0))
SPIKE_RESIDUAL = float(getattr(_cfg, "BAR_DEFECT_SPIKE_RESIDUAL", 0.25))
SPIKE_WINDOW = int(getattr(_cfg, "BAR_DEFECT_SPIKE_WINDOW", 3))
BREAK_RATIO = float(getattr(_cfg, "BAR_DEFECT_BREAK_RATIO", 3.0))
QUIET_VOL_MULT = float(getattr(_cfg, "BAR_DEFECT_QUIET_VOL_MULT", 2.0))
SUSPECT_VOL_MULT = float(getattr(_cfg, "BAR_DEFECT_SUSPECT_VOL_MULT", 10.0))
QUIET_VOL_LOOKBACK = 63
QUIET_VOL_MIN_OBS = 10
IMPLAUSIBLE_VOL = float(getattr(_cfg, "BAR_DEFECT_IMPLAUSIBLE_VOL", 3.0))
IMPLAUSIBLE_MOM = float(getattr(_cfg, "BAR_DEFECT_IMPLAUSIBLE_MOM", 20.0))
BOOK_MAX_SHARE = float(getattr(_cfg, "BAR_DEFECT_BOOK_MAX_SHARE", 0.02))

#: Module switch for A/B audits ONLY (the triplet's `--bar-screen off` leg). The
#: reader default is ON; nothing in a decision path sets it off.
ENABLED = bool(getattr(_cfg, "BAR_DEFECT_SCREEN", True))

#: The last audit `screen` produced (for receipts that want to print it).
LAST_AUDIT: dict = {}

RECEIPT_SUBDIR = "bar_defects"


class BarDefectRefusal(Exception):
    """A book leans on rows the screen could not clean (`assert_book_clean`)."""


# ─────────────────────────────── the screen ──────────────────────────────────

def _run_lengths(flag: np.ndarray, new_sym: np.ndarray) -> np.ndarray:
    """Length of the run of True that each True row belongs to (0 for False),
    runs never crossing a symbol boundary."""
    n = len(flag)
    if not n:
        return np.zeros(0, dtype=np.int64)
    brk = np.ones(n, dtype=bool)
    brk[1:] = (flag[1:] != flag[:-1]) | new_sym[1:]
    rid = np.cumsum(brk) - 1
    size = np.bincount(rid)
    out = size[rid]
    out[~flag] = 0
    return out


def _session_index(dates: np.ndarray, cal: Optional[np.ndarray]) -> np.ndarray:
    """Position of each date on the market calendar (business days if none)."""
    if cal is not None and len(cal):
        return np.searchsorted(cal, dates, side="left").astype(np.int64)
    d = dates.astype("datetime64[D]")
    return np.busday_count(np.datetime64("1970-01-01"), d).astype(np.int64)


def screen(bars: pd.DataFrame, *, market: str = "SPY") -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Rules A and B remove rows; rules C and D return cuts.

    Returns (bars_without_non_trades, cuts, audit). `cuts` has columns
    symbol, first_after (the first date of the NEW segment), reason, ratio,
    volume_ratio. `bars` must have symbol, date, close; `volume` enables A and C.
    Input row order is irrelevant; output is sorted by (symbol, date)."""
    global LAST_AUDIT
    cut_cols = ["symbol", "first_after", "last_before", "reason", "ratio", "volume_ratio"]
    empty_cuts = pd.DataFrame(columns=cut_cols)
    if bars is None or not len(bars) or not ENABLED:
        audit = {"enabled": ENABLED, "rows_in": 0 if bars is None else int(len(bars))}
        LAST_AUDIT = audit
        return bars, empty_cuts, audit
    b = bars.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)
    dates = pd.to_datetime(b["date"]).to_numpy()
    sym = b["symbol"].astype(str).to_numpy()
    close = b["close"].to_numpy(dtype=float)
    n = len(b)
    new_sym = np.ones(n, dtype=bool)
    new_sym[1:] = sym[1:] != sym[:-1]
    has_volume = "volume" in b.columns
    drop = np.zeros(n, dtype=bool)
    reason = np.full(n, "", dtype=object)

    # ── A: dark rows (zero volume) ──
    dark_runs: list = []
    nontrade_prints = 0
    if has_volume:
        vol = pd.to_numeric(b["volume"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        sym_codes = np.cumsum(new_sym) - 1
        any_vol = np.bincount(sym_codes, weights=(vol > 0).astype(float)) > 0
        zero = (vol <= 0) & any_vol[sym_codes]
        rl = _run_lengths(zero, new_sym)
        dark = zero & (rl >= DARK_RUN_MIN)
        # the last traded close before each row (a zero-volume row is not a trade)
        traded_close = np.where(zero, np.nan, close)
        seg_first = np.flatnonzero(new_sym)
        ltc = pd.Series(traded_close).groupby(sym_codes).ffill().to_numpy()
        prev_ltc = np.full(n, np.nan)
        prev_ltc[1:] = ltc[:-1]
        prev_ltc[seg_first] = np.nan
        with np.errstate(invalid="ignore", divide="ignore"):
            moved = np.abs(close / prev_ltc - 1.0) > NONTRADE_PRINT_TOL
        nontrade = zero & ~dark & moved
        nontrade_prints = int(nontrade.sum())
        drop |= dark | nontrade
        reason[dark] = "DARK_RUN"
        reason[nontrade] = "NONTRADE_PRINT"
        if dark.any():
            st = dark.copy()
            st[1:] &= ~(dark[:-1] & ~new_sym[1:])
            for i in np.flatnonzero(st):
                L = int(rl[i])
                dark_runs.append({"symbol": sym[i], "start": str(pd.Timestamp(dates[i]).date()),
                                  "end": str(pd.Timestamp(dates[i + L - 1]).date()), "sessions": L,
                                  "close": float(close[i])})
    else:
        vol = None

    # the remaining (traded) rows
    keep = ~drop
    k_idx = np.flatnonzero(keep)
    ks, kd, kc = sym[k_idx], dates[k_idx], close[k_idx]
    kn = np.ones(len(k_idx), dtype=bool)
    kn[1:] = ks[1:] != ks[:-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        lr = np.full(len(k_idx), np.nan)
        lr[1:] = np.log(kc[1:] / kc[:-1])
    lr[kn] = np.nan
    lr[~np.isfinite(lr)] = np.nan

    # ── B: spike-and-revert prints ──
    spikes: list = []
    spike_drop = np.zeros(len(k_idx), dtype=bool)
    thr_s = math.log(SPIKE_RATIO)
    for i in np.flatnonzero(np.abs(np.nan_to_num(lr)) >= thr_s):
        if spike_drop[i]:
            continue
        cum = lr[i]
        for j in range(i + 1, min(i + 1 + SPIKE_WINDOW, len(k_idx))):
            if kn[j] or not np.isfinite(lr[j]):
                break
            cum += lr[j]
            if abs(cum) <= SPIKE_RESIDUAL * abs(lr[i]):
                spike_drop[i:j] = True
                spikes.append({"symbol": ks[i], "start": str(pd.Timestamp(kd[i]).date()),
                               "end": str(pd.Timestamp(kd[j - 1]).date()), "rows": int(j - i),
                               "spike_ratio": float(math.exp(lr[i])),
                               "residual_ratio": float(math.exp(cum))})
                break
    drop[k_idx[spike_drop]] = True
    reason[k_idx[spike_drop]] = "SPIKE_PRINT"

    # recompute the traded series after B
    keep = ~drop
    k_idx = np.flatnonzero(keep)
    ks, kd, kc = sym[k_idx], dates[k_idx], close[k_idx]
    kn = np.ones(len(k_idx), dtype=bool)
    kn[1:] = ks[1:] != ks[:-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        lr = np.full(len(k_idx), np.nan)
        lr[1:] = np.log(kc[1:] / kc[:-1])
    lr[kn] = np.nan
    lr[~np.isfinite(lr)] = np.nan
    thr_b = math.log(BREAK_RATIO)
    big = np.abs(np.nan_to_num(lr)) >= thr_b

    # ── C: quiet level breaks ──
    cuts: list = []
    if has_volume and big.any():
        kv = vol[k_idx]
        seg_start = np.maximum.accumulate(np.where(kn, np.arange(len(k_idx)), 0))
        vr = np.full(len(k_idx), np.nan)
        for i in np.flatnonzero(big):
            lo = max(int(seg_start[i]), i - QUIET_VOL_LOOKBACK)
            w = kv[lo:i]
            if len(w) >= QUIET_VOL_MIN_OBS:
                md = float(np.median(w))
                vr[i] = kv[i] / md if md > 0 else np.inf
        quiet = big & np.isfinite(vr) & (vr < QUIET_VOL_MULT)
        suspect_rows = big & np.isfinite(vr) & (vr >= QUIET_VOL_MULT) & (vr < SUSPECT_VOL_MULT)
        for i in np.flatnonzero(quiet):
            cuts.append({"symbol": ks[i], "first_after": pd.Timestamp(kd[i]),
                         "last_before": pd.Timestamp(kd[i - 1]), "reason": "QUIET_LEVEL_BREAK",
                         "ratio": float(math.exp(lr[i])), "volume_ratio": float(vr[i])})
    else:
        vr = np.full(len(k_idx), np.nan)
        suspect_rows = np.zeros(len(k_idx), dtype=bool)

    # ── D: level break across a missing session ──
    if big.any():
        cal = None
        if market is not None:
            m = b.loc[b["symbol"].astype(str) == str(market), "date"]
            if len(m) > 50:
                cal = np.sort(pd.to_datetime(m).to_numpy())
        pos = _session_index(kd, cal)
        gap = np.zeros(len(k_idx), dtype=np.int64)
        gap[1:] = pos[1:] - pos[:-1]
        gap[kn] = 0
        already = {(c["symbol"], c["first_after"]) for c in cuts}
        for i in np.flatnonzero(big & (gap >= 2)):
            key = (ks[i], pd.Timestamp(kd[i]))
            if key in already:
                continue
            cuts.append({"symbol": ks[i], "first_after": pd.Timestamp(kd[i]),
                         "last_before": pd.Timestamp(kd[i - 1]), "reason": "GAP_LEVEL_BREAK",
                         "ratio": float(math.exp(lr[i])),
                         "volume_ratio": float(vr[i]) if np.isfinite(vr[i]) else None})

    # ── SUSPECT (kept, not cut): a >= BREAK_RATIO move on 2-10x volume is where the
    # vendor defects CRSP confirms and the real moves overlap; the book check reads these
    cut_keys = {(c["symbol"], c["first_after"]) for c in cuts}
    suspects = [{"symbol": ks[i], "date": str(pd.Timestamp(kd[i]).date()),
                 "ratio": float(math.exp(lr[i])), "volume_ratio": float(vr[i])}
                for i in np.flatnonzero(suspect_rows)
                if (ks[i], pd.Timestamp(kd[i])) not in cut_keys]

    out = b.loc[~drop].reset_index(drop=True)
    cut_df = pd.DataFrame(cuts, columns=cut_cols) if cuts else empty_cuts
    dropped = b.loc[drop, ["symbol", "date"]].assign(reason=reason[drop])
    years = pd.to_datetime(dropped["date"]).dt.year
    audit = {
        "enabled": True,
        "rules": {"dark_run_min_sessions": DARK_RUN_MIN, "nontrade_print_tol": NONTRADE_PRINT_TOL,
                  "spike_ratio": SPIKE_RATIO, "spike_residual": SPIKE_RESIDUAL,
                  "spike_window_sessions": SPIKE_WINDOW, "break_ratio": BREAK_RATIO,
                  "quiet_volume_mult": QUIET_VOL_MULT},
        "volume_available": has_volume,
        "rows_in": int(n), "rows_removed": int(drop.sum()),
        "rows_removed_by_reason": {k: int(v) for k, v in dropped["reason"].value_counts().items()},
        "rows_removed_by_year": {int(k): int(v) for k, v in years.value_counts().sort_index().items()},
        "symbols_with_rows_removed": int(dropped["symbol"].nunique()),
        "dark_runs": dark_runs, "n_dark_runs": len(dark_runs),
        "nontrade_prints": nontrade_prints,
        "spikes": spikes, "n_spikes": len(spikes),
        "cuts": [{**c, "first_after": str(c["first_after"].date()),
                  "last_before": str(c["last_before"].date())} for c in cuts],
        "n_cuts": len(cuts),
        "suspects": suspects, "n_suspects": len(suspects),
        "cuts_by_reason": dict(pd.Series([c["reason"] for c in cuts]).value_counts().astype(int))
        if cuts else {},
    }
    audit["cuts_by_reason"] = {k: int(v) for k, v in audit["cuts_by_reason"].items()}
    LAST_AUDIT = audit
    return out, cut_df, audit


def summary(audit: dict) -> dict:
    """The audit without its per-event lists (for embedding in other receipts)."""
    return {k: v for k, v in (audit or {}).items()
            if k not in ("dark_runs", "spikes", "cuts", "suspects")}


# ─────────────────────────────── the book refusal ────────────────────────────

def implausible_rows(panel: pd.DataFrame, *, vol_col: str = "vol_63",
                     mom_col: str = "mom_252_21") -> pd.Series:
    """Boolean per panel row: features no listed stock produces (a defect the
    screen did not catch). Missing columns contribute False, never True."""
    flag = pd.Series(False, index=panel.index)
    if vol_col in panel.columns:
        flag |= pd.to_numeric(panel[vol_col], errors="coerce").fillna(0) > IMPLAUSIBLE_VOL
    if mom_col in panel.columns:
        flag |= pd.to_numeric(panel[mom_col], errors="coerce").abs().fillna(0) > IMPLAUSIBLE_MOM
    return flag


def flagged_keys(panel: pd.DataFrame, suspects: Optional[Iterable[dict]] = None, *,
                 before_days: int = 366, after_days: int = 95) -> set:
    """{(Timestamp date, symbol)} of panel rows whose name has a SUSPECT level
    break (kept by the screen, not proven) within `before_days` before the
    decision date (the 12-1 window) or `after_days` after it (the hold). Names
    match on the base symbol (`JAN#1` -> `JAN`). `suspects` defaults to the
    last screen's list."""
    sus = list(suspects if suspects is not None else (LAST_AUDIT.get("suspects") or []))
    if not sus or panel is None or not len(panel):
        return set()
    sd = pd.DataFrame(sus)
    sd["date"] = pd.to_datetime(sd["date"])
    by = {s: np.sort(g["date"].to_numpy()) for s, g in sd.groupby("symbol")}
    out = set()
    pd_ = panel[["date", "symbol"]].copy()
    pd_["base"] = pd_["symbol"].astype(str).str.split("#").str[0]
    pd_ = pd_[pd_["base"].isin(by)]
    lo_d, hi_d = np.timedelta64(before_days, "D"), np.timedelta64(after_days, "D")
    for d, s, base in pd_.itertuples(index=False):
        ev = by[base]
        t = np.datetime64(pd.Timestamp(d))
        j = np.searchsorted(ev, t - lo_d, side="right")
        if j < len(ev) and ev[j] <= t + hi_d:
            out.add((pd.Timestamp(d), str(s)))
    return out


def book_defect_share(holdings: Iterable[dict], flagged: set) -> dict:
    """Share of a book's slots (date x held name) on flagged rows. `holdings` is
    `strategy_library.run_strategy`'s list of {date, symbols, weights}."""
    slots = hit = 0
    hits: list = []
    for h in holdings or []:
        d = pd.Timestamp(h.get("date"))
        for s in h.get("symbols") or []:
            slots += 1
            if (d, str(s)) in flagged:
                hit += 1
                hits.append({"date": str(d.date()), "symbol": str(s)})
    share = hit / slots if slots else 0.0
    return {"slots": slots, "flagged_slots": hit, "share": share, "limit": BOOK_MAX_SHARE,
            "refuse": bool(share > BOOK_MAX_SHARE), "hits": hits[:50]}


def assert_book_clean(holdings: Iterable[dict], flagged: set, *, label: str = "book") -> dict:
    """Raise `BarDefectRefusal` when more than `BOOK_MAX_SHARE` of the book's
    slots sit on flagged rows (`flagged_keys`); return the count otherwise."""
    # a book is never certified clean against a screen that was not handed in
    # (`flagged=None`), nor a book with no held slot (a check that did not run
    # is not a check that passed). An EMPTY set is a screen that found nothing.
    if flagged is None:
        raise BarDefectRefusal(f"{label}: no flagged-row set (the defect screen's result) "
                               f"was supplied; cannot certify the book clean")
    r = book_defect_share(holdings, flagged)
    if not r["slots"]:
        raise BarDefectRefusal(f"{label}: the book holds no slot; nothing was checked")
    if r["refuse"]:
        raise BarDefectRefusal(
            f"{label}: {r['flagged_slots']} of {r['slots']} slots ({r['share']:.1%}) sit on a name "
            f"with an unproven level break in its signal or hold window (limit {BOOK_MAX_SHARE:.0%}); "
            f"first: {r['hits'][:5]}")
    return r


# ─────────────────────────────── the audit CLI ───────────────────────────────

def _out_dir() -> Path:
    return Path(_cfg.OPTIMUS_LEDGER_DIR) / RECEIPT_SUBDIR


def crsp_crosscheck(events: pd.DataFrame, *, wrds_dir: Optional[Path] = None,
                    tol: float = 0.25) -> pd.DataFrame:
    """For each (symbol, date, lr) event, CRSP's log return that day for the
    permno that carried the ticker then. Adds `crsp_lr` and `crsp_agrees`
    (|lr - crsp_lr| < tol). Rows CRSP does not cover keep NaN. Read-only."""
    W = Path(wrds_dir or (Path(_cfg.OPTIMUS_LEDGER_DIR) / "wrds"))
    ev = events.copy()
    ev["date"] = pd.to_datetime(ev["date"])
    ev["base"] = ev["symbol"].astype(str).str.split("#").str[0]
    names_p = W / "bulk" / "crsp__dsenames.parquet"
    if not names_p.exists() or not len(ev):
        ev["crsp_lr"] = np.nan
        ev["crsp_agrees"] = np.nan
        return ev
    nm = pd.read_parquet(names_p, columns=["permno", "namedt", "nameendt", "ticker"])
    nm["namedt"], nm["nameendt"] = pd.to_datetime(nm["namedt"]), pd.to_datetime(nm["nameendt"])
    m = ev.reset_index().merge(nm, left_on="base", right_on="ticker", how="left")
    m = m[(m["date"] >= m["namedt"]) & (m["date"] <= m["nameendt"])]
    frames = []
    for y in sorted(m["date"].dt.year.unique()):
        p = W / f"crsp_dsf_{int(y)}.parquet"
        if p.exists():
            d = pd.read_parquet(p, columns=["permno", "date", "ret"])
            d["date"] = pd.to_datetime(d["date"])
            frames.append(d.merge(m.loc[m["date"].dt.year == y, ["permno", "date"]].drop_duplicates()))
    if frames:
        dsf = pd.concat(frames, ignore_index=True)
        m = m.merge(dsf, on=["permno", "date"], how="left").dropna(subset=["ret"])
        m = m.drop_duplicates("index")
        cl = pd.Series(np.log1p(m["ret"].to_numpy(dtype=float)), index=m["index"].to_numpy())
    else:
        cl = pd.Series(dtype=float)
    ev["crsp_lr"] = cl.reindex(ev.index)
    ev["crsp_agrees"] = np.where(ev["crsp_lr"].notna(),
                                 (ev["lr"] - ev["crsp_lr"]).abs() < tol, np.nan)
    return ev


def main(argv=None) -> int:        # pragma: no cover - reads the real panel
    import argparse
    from backend.services import stitched_tickers as ST
    from backend.services import xs_ranker as XR
    ap = argparse.ArgumentParser()
    ap.parse_args(argv)
    t_run = datetime.now(timezone.utc)
    run_id = t_run.strftime("%Y-%m-%dT%H%M%SZ")
    out = _out_dir()
    out.mkdir(parents=True, exist_ok=True)
    rp = out / f"bar_defects_{run_id}.json"
    if rp.exists():
        print(f"REFUSED: {rp.name} exists")
        return 2
    paths = XR.survivorship_free_paths()
    cols = ["symbol", "date", "open", "high", "low", "close", "volume"]
    frames = [ST.tag_source(pd.read_parquet(p, columns=cols), Path(p).stem) for p in paths]
    raw = pd.concat(frames, ignore_index=True)
    raw["date"] = pd.to_datetime(raw["date"])
    raw = raw.drop_duplicates(subset=["symbol", "date"], keep="first")
    print(f"bars {len(raw):,} rows, {raw['symbol'].nunique():,} symbols from {[p.name for p in paths]}")
    cut = ST.cut_reader_bars(raw)
    a = dict(ST.LAST_AUDIT.get("defect_screen") or LAST_AUDIT)
    # every event the screen acted on, with CRSP's view where CRSP covers it
    ev_rows = []
    for c in a.get("cuts", []):
        ev_rows.append({"symbol": c["symbol"], "date": c["first_after"], "lr": math.log(c["ratio"]),
                        "kind": c["reason"]})
    for s in a.get("spikes", []):
        ev_rows.append({"symbol": s["symbol"], "date": s["start"], "lr": math.log(s["spike_ratio"]),
                        "kind": "SPIKE_PRINT"})
    ev = pd.DataFrame(ev_rows)
    if len(ev):
        ev = crsp_crosscheck(ev)
        cov = ev[ev["crsp_lr"].notna()]
        a["crsp_crosscheck"] = {
            "events": int(len(ev)), "covered_by_crsp": int(len(cov)),
            "crsp_confirms_defect": int((cov["crsp_agrees"] == 0).sum()),
            "crsp_says_real_move": int((cov["crsp_agrees"] == 1).sum()),
            "real_moves_cut": cov.loc[cov["crsp_agrees"] == 1, ["symbol", "date", "kind", "lr", "crsp_lr"]]
            .assign(date=lambda d: d["date"].dt.date.astype(str)).to_dict("records")}
    # residual: large moves the screen left in place, against CRSP
    c2 = cut.sort_values(["symbol", "date"]).reset_index(drop=True)
    same = c2["symbol"].to_numpy()[1:] == c2["symbol"].to_numpy()[:-1]
    cc = c2["close"].to_numpy(dtype=float)
    lr = np.full(len(c2), np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        lr[1:] = np.where(same, np.log(cc[1:] / cc[:-1]), np.nan)
    big = np.abs(np.nan_to_num(lr)) >= math.log(BREAK_RATIO)
    res = c2.loc[big, ["symbol", "date"]].assign(lr=lr[big])
    res = crsp_crosscheck(res)
    rc = res[res["crsp_lr"].notna()]
    a["residual_moves_ge_break_ratio"] = {
        "rows": int(len(res)), "covered_by_crsp": int(len(rc)),
        "crsp_says_real": int((rc["crsp_agrees"] == 1).sum()),
        "crsp_says_defect_left_in": int((rc["crsp_agrees"] == 0).sum()),
        "defects_left_in": rc.loc[rc["crsp_agrees"] == 0, ["symbol", "date", "lr", "crsp_lr"]]
        .assign(date=lambda d: d["date"].dt.date.astype(str)).to_dict("records")}
    doc = {"schema": "bar_defects/1", "run_id": run_id, "licence": "PRODUCT_EXPERIMENT",
           "written_utc": t_run.isoformat(timespec="seconds"), "llm_spend_usd": 0.0,
           "inputs": {p.name: int(len(f)) for p, f in zip(paths, frames)},
           "stitched": {k: v for k, v in ST.LAST_AUDIT.items() if k != "defect_screen"},
           "defect_screen": a}
    tmp = rp.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    tmp.replace(rp)
    s = summary(a)
    print(json.dumps({k: s[k] for k in ("rows_removed", "rows_removed_by_reason",
                                        "symbols_with_rows_removed", "n_cuts", "cuts_by_reason")},
                     default=str))
    print(f"-> {rp}")
    return 0


if __name__ == "__main__":         # pragma: no cover
    raise SystemExit(main())
