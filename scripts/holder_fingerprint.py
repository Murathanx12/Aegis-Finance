"""HOLDER FINGERPRINT — a PIT panel of what each 13F filer *habitually does*.

Licence: PRODUCT_EXPERIMENT (docs/IDEA_2026-08-31_HOLDER_PROVENANCE_TO_THE_ROOTS.md §6).
Grain:   FILER (mgrno), never vehicle. BlackRock consolidated its subsidiary
         mgrnos into 9385 at 2017Q1, so a post-2017 BlackRock duration is a
         blended index+active duration. The active/passive split is NOT
         observable in entitled WRDS (idea doc §4a) — recorded UNKNOWN.

What this builds
----------------
1. CRSP artefacts (calendar, per-permno cumulative log-return blocks, EW and VW
   market series, quarter-end snapshots with momentum / cap tercile / SIC).
2. A PIT HolderFingerprint panel keyed (mgrno, as_of_quarter).  The fingerprint
   stamped for as_of_quarter q is computed from filings through q-1 ONLY, so it
   may be used to condition an event observed at q.  Nothing in it ever reads a
   quarter >= q.
3. A "material position change" transitions cache (one parquet per quarter)
   which scripts/holder_h2_h3_test.py turns into events.

PIT rule (the one that matters)
-------------------------------
Thomson s34 has NO SEC filing timestamp.  `rdate` is the report quarter-end and
`fdate` is Thomson's vintage quarter (>= rdate; a stale manager is carried
forward at later vintages).  We therefore take the CONSERVATIVE public date

    public_date = quarter_end(max(rdate, first_fdate_seen)) + 45 calendar days

which is the statutory 13F deadline applied to the *later* of report quarter and
first vintage.  Every forward return starts at the first trading close on or
after that date.  No return, no control, and no fingerprint field ever reads
information dated after its own stamp.

Run:  python -m scripts.holder_fingerprint            (full 1996-2024)
      python -m scripts.holder_fingerprint --start-year 2005
"""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parents[1]
WRDS = ROOT / "backend" / "data" / "optimus" / "wrds"
BULK = WRDS / "bulk"
TRACKER = ROOT / "backend" / "data" / "optimus" / "tracker_backtest"
TRANS_DIR = WRDS / "holder_transitions"
FP_PATH = WRDS / "holder_fingerprints.parquet"
QSNAP_PATH = WRDS / "holder_qsnap.parquet"
RECEIPT = TRACKER / "holder_fingerprint_summary.json"

# ---------------------------------------------------------------- constants
Q0_YEAR = 1995                     # qidx 0 == 1995Q1
FILING_LAG_DAYS = 45               # statutory 13F deadline
DSF_FIRST_YEAR = 1994              # need 252 sessions of history before 1996Q2
DSF_LAST_YEAR = 2024
S34_FIRST_YEAR = 1996
S34_LAST_YEAR = 2024

# transitions cache keeps only positions that MOVED — the event definitions in
# holder_h2_h3_test.py use +-50%, so 40% is a deliberate margin.
MATERIAL_REL_CHANGE = 0.40

# histogram supports for the manager's own-history distributions
PCTCO_EDGES = np.logspace(-7.0, 0.0, 71)       # position as % of company shares
PCTPF_EDGES = np.logspace(-6.0, 0.0, 61)       # position as % of portfolio value
DUR_MAX_BIN = 41                                # spells >= 41 quarters censored

FAMOUS = {
    "BERKSHIRE": "BERKSHIRE HATHAWAY",
    "CITADEL": "CITADEL",
    "RENAISSANCE": "RENAISSANCE TECHNOLOGIES",
    "ARK": "ARK INVESTMENT MANAGEMENT",
    "BLACKROCK": "BLACKROCK INC",
    "VANGUARD": "VANGUARD GROUP",
    "STATE_STREET": "STATE STREET",
    "FIDELITY_FMR": "FIDELITY MGMT & RESEARCH",
    "GEODE": "GEODE CAPITAL",
    "T_ROWE": "T. ROWE PRICE ASSOCIATES",
    "BRIDGEWATER": "BRIDGEWATER",
    "TIGER_GLOBAL": "TIGER",
    "SOROS": "SOROS FUND",
}


# ---------------------------------------------------------------- quarters
def qidx_of(y: int, q: int) -> int:
    return (y - Q0_YEAR) * 4 + (q - 1)


def quarter_end(qidx: int) -> date:
    y = Q0_YEAR + qidx // 4
    q = qidx % 4 + 1
    return date(y, [3, 6, 9, 12][q - 1], [31, 30, 30, 31][q - 1])


def qidx_from_date(d: date) -> int:
    return qidx_of(d.year, (d.month - 1) // 3 + 1)


def qlabel(qidx: int) -> str:
    return f"{Q0_YEAR + qidx // 4}Q{qidx % 4 + 1}"


def public_date_of(qidx: int) -> date:
    return quarter_end(qidx) + timedelta(days=FILING_LAG_DAYS)


# ---------------------------------------------------------------- CRSP link
def load_cusip_link() -> pd.DataFrame:
    """ncusip (8) -> permno, collapsed.  Measured 2026-09-02: 28,812 distinct
    ncusips, ZERO of which map to more than one permno, and 100% of a sampled
    13F quarter matched.  So a flat map is exact here, not an approximation."""
    n = pd.read_parquet(
        BULK / "crsp__dsenames.parquet",
        columns=["permno", "namedt", "nameendt", "ncusip", "siccd"],
    ).dropna(subset=["ncusip"])
    g = (
        n.sort_values(["ncusip", "permno", "namedt"])
        .groupby(["ncusip", "permno"], as_index=False)
        .agg(siccd=("siccd", "last"))
    )
    dupes = int((g.ncusip.value_counts() > 1).sum())
    g = g.drop_duplicates("ncusip", keep="last")
    g["permno"] = g["permno"].astype("int32")
    g.attrs["n_multi_permno_cusips"] = dupes
    return g


def load_sic_map() -> pd.Series:
    n = pd.read_parquet(BULK / "crsp__dsenames.parquet", columns=["permno", "namedt", "siccd"])
    n = n.sort_values(["permno", "namedt"]).drop_duplicates("permno", keep="last")
    return pd.Series(
        (n.siccd.values // 100).astype("int16"), index=n.permno.values.astype("int32")
    )


# ---------------------------------------------------------------- CRSP build
class CRSP:
    """Per-permno cumulative log-return blocks + market series + quarter snaps."""

    def __init__(self, cal, key, cum, ew_cum, vw_cum, qsnap, diag):
        self.cal = cal              # np.array[datetime64[D]] sorted trading days
        self.key = key              # int64 permno*100000 + dayidx, globally sorted
        self.cum = cum              # float32 cumulative log return within permno
        self.ew_cum = ew_cum        # float64 cumulative log EW market by dayidx
        self.vw_cum = vw_cum        # float64 cumulative log VW market by dayidx
        self.qsnap = qsnap          # DataFrame permno,qidx,prc,shrout,cfacshr,...
        self.diag = diag

    # -- index helpers -------------------------------------------------
    def dayidx_on_or_after(self, dates: np.ndarray) -> np.ndarray:
        """First trading-day index on/after each date (len(cal) if past the end)."""
        return np.searchsorted(self.cal, dates.astype("datetime64[D]"), side="left")

    def forward_excess(self, permno: np.ndarray, start_dayidx: np.ndarray, horizon: int,
                       market: str = "ew"):
        """Simple forward excess return over `horizon` TRADING SESSIONS of the name,
        measured from the close of the first session on/after start_dayidx, minus the
        market's return over the SAME CALENDAR WINDOW.  NaN where unavailable."""
        n = len(permno)
        out = np.full(n, np.nan, dtype="float64")
        raw = np.full(n, np.nan, dtype="float64")
        ok_start = start_dayidx < len(self.cal)
        p64 = permno.astype("int64")
        lo = np.searchsorted(self.key, p64 * 100000, side="left")
        hi = np.searchsorted(self.key, (p64 + 1) * 100000, side="left")
        j0 = np.searchsorted(self.key, p64 * 100000 + np.minimum(start_dayidx, 99999),
                             side="left")
        j1 = j0 + horizon
        good = ok_start & (j0 >= lo) & (j0 < hi) & (j1 < hi)
        if not good.any():
            return out, raw, good
        g = np.where(good)[0]
        c0 = self.cum[j0[g]]
        c1 = self.cum[j1[g]]
        d0 = (self.key[j0[g]] % 100000).astype("int64")
        d1 = (self.key[j1[g]] % 100000).astype("int64")
        mcum = self.ew_cum if market == "ew" else self.vw_cum
        stock = np.expm1(c1.astype("float64") - c0.astype("float64"))
        mkt = np.expm1(mcum[d1] - mcum[d0])
        raw[g] = stock
        out[g] = stock - mkt
        return out, raw, good


def build_crsp(first_year=DSF_FIRST_YEAR, last_year=DSF_LAST_YEAR, verbose=True) -> CRSP:
    t0 = time.time()
    years = [y for y in range(first_year, last_year + 1) if (WRDS / f"crsp_dsf_{y}.parquet").exists()]

    # pass 1 — calendar only (cheap columnar read)
    dts = []
    for y in years:
        d = pd.read_parquet(WRDS / f"crsp_dsf_{y}.parquet", columns=["date"])
        dts.append(pd.to_datetime(d["date"]).values.astype("datetime64[D]"))
    cal = np.unique(np.concatenate(dts))
    del dts
    if verbose:
        print(f"[crsp] calendar {len(cal)} sessions {cal[0]}..{cal[-1]} ({time.time()-t0:.0f}s)")

    # pass 2 — returns, market aggregates, quarter-end snapshots
    P, D, R, C = [], [], [], []
    ew_sum = np.zeros(len(cal)); ew_n = np.zeros(len(cal))
    vw_num = np.zeros(len(cal)); vw_den = np.zeros(len(cal))
    snaps = []
    n_ret_nan = 0
    for y in years:
        d = pd.read_parquet(
            WRDS / f"crsp_dsf_{y}.parquet",
            columns=["permno", "date", "prc", "ret", "shrout", "cfacshr"],
        )
        dd = pd.to_datetime(d["date"]).values.astype("datetime64[D]")
        di = np.searchsorted(cal, dd)
        pn = d["permno"].values.astype("int32")
        ret = d["ret"].values.astype("float64")
        n_ret_nan += int(np.isnan(ret).sum())
        ret = np.nan_to_num(ret, nan=0.0)
        prc = np.abs(d["prc"].values.astype("float64"))
        shr = d["shrout"].values.astype("float64")
        cap = prc * shr * 1000.0
        P.append(pn); D.append(di.astype("int32")); R.append(ret.astype("float32"))
        C.append(np.nan_to_num(cap, nan=0.0).astype("float32"))
        np.add.at(ew_sum, di, ret)
        np.add.at(ew_n, di, 1.0)
        # quarter-end snapshot: last observation inside each calendar quarter
        qi = ((pd.DatetimeIndex(dd).year - Q0_YEAR) * 4
              + (pd.DatetimeIndex(dd).month - 1) // 3).values.astype("int32")
        sn = pd.DataFrame({
            "permno": pn, "qidx": qi, "dayidx": di.astype("int32"),
            "prc": prc, "shrout": shr, "cfacshr": d["cfacshr"].values.astype("float64"),
            "mktcap": cap,
        })
        sn = sn.sort_values(["permno", "qidx", "dayidx"]).drop_duplicates(
            ["permno", "qidx"], keep="last")
        snaps.append(sn)
        del d, sn
    permno = np.concatenate(P); dayidx = np.concatenate(D)
    ret = np.concatenate(R); cap = np.concatenate(C)
    del P, D, R, C
    if verbose:
        print(f"[crsp] {len(permno):,} daily rows loaded ({time.time()-t0:.0f}s)")

    # delisting returns compounded into each permno's final observation
    dl = pd.read_parquet(BULK / "crsp__dsedelist.parquet", columns=["permno", "dlstdt", "dlret"])
    dl = dl.dropna(subset=["dlret"])
    dl = dl[dl.dlret > -1.5]
    order = np.lexsort((dayidx, permno))
    permno = permno[order]; dayidx = dayidx[order]; ret = ret[order]; cap = cap[order]
    key = permno.astype("int64") * 100000 + dayidx.astype("int64")
    n_dl_applied = 0
    if len(dl):
        blk_hi = np.searchsorted(key, (dl.permno.values.astype("int64") + 1) * 100000, side="left")
        blk_lo = np.searchsorted(key, dl.permno.values.astype("int64") * 100000, side="left")
        has = blk_hi > blk_lo
        last = blk_hi[has] - 1
        dr = dl.dlret.values[has].astype("float32")
        ret[last] = ((1.0 + ret[last].astype("float64")) * (1.0 + dr.astype("float64")) - 1.0
                     ).astype("float32")
        n_dl_applied = int(has.sum())

    # cumulative log return within permno block
    logr = np.log1p(np.clip(ret.astype("float64"), -0.999999, None))
    gcum = np.cumsum(logr)
    starts = np.searchsorted(permno, np.unique(permno), side="left")
    base = np.zeros(len(permno))
    blk_id = np.searchsorted(np.unique(permno), permno)
    base_by_blk = np.concatenate([[0.0], gcum[starts[1:] - 1]]) if len(starts) > 1 else np.array([0.0])
    base = base_by_blk[blk_id]
    cum = (gcum - base).astype("float32")
    del logr, gcum, base, blk_id, base_by_blk

    # market series.  VW uses the PREVIOUS session's cap of the same name.
    prev_cap = np.empty_like(cap)
    prev_cap[1:] = cap[:-1]
    prev_cap[0] = np.nan
    blk_start = np.zeros(len(permno), dtype=bool)
    blk_start[starts] = True
    prev_cap[blk_start] = np.nan
    w = np.nan_to_num(prev_cap.astype("float64"), nan=0.0)
    np.add.at(vw_num, dayidx, ret.astype("float64") * w)
    np.add.at(vw_den, dayidx, w)
    ew_daily = np.divide(ew_sum, np.maximum(ew_n, 1.0))
    vw_daily = np.divide(vw_num, np.maximum(vw_den, 1e-9))
    # ew_cum[i] = cumulative log market return through the CLOSE of session i
    ew_cum = np.cumsum(np.log1p(np.clip(ew_daily, -0.99, None)))
    vw_cum = np.cumsum(np.log1p(np.clip(vw_daily, -0.99, None)))
    del prev_cap, w, cap

    crsp = CRSP(cal, key, cum, ew_cum, vw_cum, None,
                {"n_daily_rows": int(len(permno)), "n_ret_nan_filled_zero": n_ret_nan,
                 "n_delisting_returns_applied": n_dl_applied,
                 "calendar_first": str(cal[0]), "calendar_last": str(cal[-1]),
                 "n_permnos": int(len(starts))})

    # quarter-end snapshot table + momentum + cap tercile + sector
    qs = pd.concat(snaps, ignore_index=True)
    del snaps
    qs = qs.sort_values(["permno", "qidx"]).drop_duplicates(["permno", "qidx"], keep="last")
    qs["permno"] = qs["permno"].astype("int32")
    qs["qidx"] = qs["qidx"].astype("int16")
    # momentum 12-1: return from t-252 to t-21 sessions of the same name
    p64 = qs.permno.values.astype("int64")
    lo = np.searchsorted(key, p64 * 100000, side="left")
    j = np.searchsorted(key, p64 * 100000 + qs.dayidx.values.astype("int64"), side="left")
    ja, jb = j - 21, j - 252
    okm = (jb >= lo) & (ja >= lo) & (j < np.searchsorted(key, (p64 + 1) * 100000, side="left"))
    mom = np.full(len(qs), np.nan)
    mom[okm] = np.expm1(cum[ja[okm]].astype("float64") - cum[jb[okm]].astype("float64"))
    qs["mom_12_1"] = mom
    qs["logcap"] = np.log(np.maximum(qs.mktcap.values, 1.0))
    qs["cap_tercile"] = (
        qs.groupby("qidx")["mktcap"]
        .transform(lambda s: pd.qcut(s.rank(method="first"), 3, labels=False))
        .astype("float32")
    )
    sic = load_sic_map()
    qs["sic2"] = qs.permno.map(sic).fillna(-1).astype("int16")
    crsp.qsnap = qs
    if verbose:
        print(f"[crsp] qsnap {len(qs):,} permno-quarters; delist rets {n_dl_applied} "
              f"({time.time()-t0:.0f}s)")
    return crsp


# ---------------------------------------------------------------- 13F loading
class S34Reader:
    """Chronological quarter reader over tr13f_s34_YYYY.parquet with a 2-year cache.

    A report quarter can appear in its own year's file AND (for 2013-2017 pulls)
    in the next year's file as a stale vintage.  We union both and keep the row
    with the EARLIEST fdate per (mgrno, permno) — the first vintage in which the
    holding was observable."""

    def __init__(self, link: pd.DataFrame):
        self.link = link.set_index("ncusip")["permno"]
        self.cache: dict[int, pd.DataFrame] = {}
        self.stats = {"rows_read": 0, "rows_unmatched_cusip": 0, "rows_after_dedupe": 0}

    def _year(self, y: int) -> pd.DataFrame | None:
        if y in self.cache:
            return self.cache[y]
        f = WRDS / f"tr13f_s34_{y}.parquet"
        if not f.exists():
            self.cache[y] = None
            return None
        d = pd.read_parquet(f, columns=["fdate", "rdate", "mgrno", "cusip", "shares"])
        d = d[d.shares > 0]
        pn = d.cusip.map(self.link)
        self.stats["rows_read"] += len(d)
        self.stats["rows_unmatched_cusip"] += int(pn.isna().sum())
        d = d.assign(permno=pn).dropna(subset=["permno"])
        rd = pd.DatetimeIndex(d.rdate)
        fd = pd.DatetimeIndex(d.fdate)
        out = pd.DataFrame({
            "rq": ((rd.year - Q0_YEAR) * 4 + (rd.month - 1) // 3).values.astype("int16"),
            "fq": ((fd.year - Q0_YEAR) * 4 + (fd.month - 1) // 3).values.astype("int16"),
            "mgrno": d.mgrno.values.astype("int32"),
            "permno": d.permno.values.astype("int32"),
            "shares": d.shares.values.astype("float64"),
        })
        for k in [k for k in self.cache if k < y - 1]:
            self.cache[k] = None
        self.cache[y] = out
        return out

    def quarter(self, q: int) -> pd.DataFrame:
        y = Q0_YEAR + q // 4
        parts = []
        for yy in (y, y + 1):
            d = self._year(yy)
            if d is not None:
                s = d[d.rq == q]
                if len(s):
                    parts.append(s)
        if not parts:
            return pd.DataFrame(columns=["mgrno", "permno", "shares", "fq"])
        c = pd.concat(parts, ignore_index=True)
        c = c.sort_values("fq").drop_duplicates(["mgrno", "permno"], keep="first")
        self.stats["rows_after_dedupe"] += len(c)
        return c[["mgrno", "permno", "shares", "fq"]]


# ---------------------------------------------------------------- histogram quantiles
def hist_quantiles(counts: np.ndarray, edges: np.ndarray, qs) -> np.ndarray:
    """Quantiles of a log-binned histogram, geometric-midpoint interpolation.
    counts shape (M, nbins); returns (M, len(qs)).  NaN where the row is empty."""
    tot = counts.sum(axis=1)
    cum = np.cumsum(counts, axis=1)
    mid = np.sqrt(edges[:-1] * edges[1:])
    out = np.full((counts.shape[0], len(qs)), np.nan)
    nz = tot > 0
    if not nz.any():
        return out
    for k, qq in enumerate(qs):
        tgt = tot[nz] * qq
        idx = (cum[nz] < tgt[:, None]).sum(axis=1)
        idx = np.clip(idx, 0, len(mid) - 1)
        out[nz, k] = mid[idx]
    return out


def dur_quantiles(counts: np.ndarray, qs) -> np.ndarray:
    tot = counts.sum(axis=1)
    cum = np.cumsum(counts, axis=1)
    vals = np.arange(1, counts.shape[1] + 1, dtype="float64")
    out = np.full((counts.shape[0], len(qs)), np.nan)
    nz = tot > 0
    if not nz.any():
        return out
    for k, qq in enumerate(qs):
        tgt = tot[nz] * qq
        idx = np.clip((cum[nz] < tgt[:, None]).sum(axis=1), 0, len(vals) - 1)
        out[nz, k] = vals[idx]
    return out


# ---------------------------------------------------------------- main build
class FingerprintState:
    def __init__(self, cap: int = 60000):
        self.idx: dict[int, int] = {}
        self.mgrno = np.zeros(cap, dtype="int32")
        self.n = 0
        z = lambda dt="int32": np.zeros(cap, dtype=dt)
        self.n_qtrs = z(); self.n_posqtr = z()
        self.n_entry = z(); self.n_exit = z(); self.n_add = z(); self.n_trim = z()
        self.n_evqtr = z()
        self.turn_sum = np.zeros(cap); self.turn_n = z()
        self.dur = np.zeros((cap, DUR_MAX_BIN), dtype="int32")
        self.n_open = z()
        self.pctco = np.zeros((cap, len(PCTCO_EDGES) - 1), dtype="int32")
        self.pctpf = np.zeros((cap, len(PCTPF_EDGES) - 1), dtype="int32")
        self.cap3 = np.zeros((cap, 3), dtype="int32")
        # last-quarter (point-in-time) fields
        self.last_q = np.full(cap, -1, dtype="int16")
        self.last_npos = z(); self.last_portval = np.zeros(cap)
        self.last_entropy = np.full(cap, np.nan)
        self.last_turnover = np.full(cap, np.nan)
        self.first_q = np.full(cap, -1, dtype="int16")

    def ensure(self, mgrnos: np.ndarray) -> np.ndarray:
        """Dense index per mgrno. mgrno is the IDENTITY; mgrname is only a label
        (idea doc 4a: a name-keyed join fragments Vanguard into three)."""
        uniq = pd.unique(mgrnos)
        for m in uniq:
            m = int(m)
            if m not in self.idx:
                if self.n >= len(self.mgrno):
                    raise RuntimeError("manager capacity exceeded")
                self.idx[m] = self.n
                self.mgrno[self.n] = m
                self.n += 1
        lut = pd.Series(self.idx, dtype="int32")
        return lut.reindex(mgrnos).values.astype("int32")


def build(start_year: int, end_year: int, verbose=True) -> dict:
    t0 = time.time()
    TRANS_DIR.mkdir(parents=True, exist_ok=True)
    for old in TRANS_DIR.glob("*.parquet"):
        old.unlink()

    link = load_cusip_link()
    crsp = build_crsp(verbose=verbose)
    crsp.qsnap.to_parquet(QSNAP_PATH, index=False)
    qk = crsp.qsnap.copy()
    qk["k"] = qk.qidx.values.astype("int64") * 1000000 + qk.permno.values.astype("int64")
    qsnap = qk.set_index("k")[["prc", "shrout", "cfacshr", "mktcap", "cap_tercile", "sic2"]]
    del qk

    rdr = S34Reader(link)
    st = FingerprintState()
    q_lo, q_hi = qidx_of(start_year, 1), qidx_of(end_year, 4)

    prev = None            # DataFrame mgrno, permno, shares_adj (previous quarter)
    prev_q = None
    act_key = np.zeros(0, dtype="int64")
    act_start = np.zeros(0, dtype="int16")
    fp_rows = []
    diag = {"quarters": 0, "quarters_no_data": 0, "mgr_quarter_gap_skips": 0,
            "mgr_quarters_without_adjacent_prior_filing": 0,
            "positions_no_price": 0, "positions_kept": 0, "pctco_clipped": 0,
            "events_written": 0}

    for q in range(q_lo, q_hi + 1):
        cur = rdr.quarter(q)
        if len(cur) == 0:
            diag["quarters_no_data"] += 1
            prev, prev_q = None, None
            continue

        # ---- join prices; drop positions with no quarter-end CRSP snapshot
        s = qsnap.reindex(np.int64(q) * 1000000 + cur.permno.values.astype("int64"))
        ok = s.prc.notna().values & (s.prc.values > 0)
        diag["positions_no_price"] += int((~ok).sum())
        cur = cur[ok].reset_index(drop=True)
        s = s[ok].reset_index(drop=True)
        diag["positions_kept"] += len(cur)
        if len(cur) == 0:
            prev, prev_q = None, None
            continue

        shares = cur.shares.values
        cfac = np.where(np.isfinite(s.cfacshr.values) & (s.cfacshr.values > 0),
                        s.cfacshr.values, 1.0)
        shares_adj = shares * cfac                    # split-comparable share count
        val = shares * s.prc.values                   # dollars, as-reported shares x price
        shrout = np.maximum(s.shrout.values, 1.0) * 1000.0
        pct_co = shares / shrout
        diag["pctco_clipped"] += int((pct_co > 1.0).sum())
        pct_co = np.clip(pct_co, 0.0, 1.0)

        cq = pd.DataFrame({
            "mgrno": cur.mgrno.values, "permno": cur.permno.values,
            "shares_adj": shares_adj, "val": val, "pct_co": pct_co,
            # split-comparable price: shares_adj * padj == shares * prc == val
            "padj": s.prc.values / cfac,
            "cap3": s.cap_tercile.values, "sic2": s.sic2.values,
            "fq": cur.fq.values,
        })
        portval = cq.groupby("mgrno")["val"].transform("sum")
        cq["pct_pf"] = np.where(portval > 0, cq.val.values / portval.values, np.nan)
        cq["mi"] = st.ensure(cq.mgrno.values)

        # ---- PIT public quarter for this manager-quarter (conservative):
        #      max(report quarter, first vintage quarter); +45d applied downstream.
        cq["pub_q"] = np.maximum(
            cq.groupby("mgrno")["fq"].transform("max").values, q).astype("int16")
        mgr_pub = cq.groupby("mgrno")["pub_q"].max()

        # =============== FINGERPRINT STAMP for as_of_quarter q ===============
        # Uses state accumulated through q-1 ONLY.  Written before any q update.
        filers_now = np.unique(cq.mi.values)
        stampable = filers_now[(st.last_q[filers_now] == q - 1)]
        if len(stampable):
            fp_rows.append(_stamp(st, stampable, q))

        # =============== events vs the immediately preceding quarter ==========
        if prev is not None and prev_q == q - 1:
            m = cq.merge(prev, on=["mgrno", "permno"], how="outer", suffixes=("", "_p"))
            # only managers present in BOTH quarters
            shared = np.intersect1d(cq.mgrno.unique(), prev.mgrno.unique())
            diag["mgr_quarters_without_adjacent_prior_filing"] += int(
                cq.mgrno.nunique() - len(shared))
            both = m.mgrno.isin(shared)
            m = m[both]
            sn = np.nan_to_num(m.shares_adj.values, nan=0.0)
            sp = np.nan_to_num(m.shares_adj_p.values, nan=0.0)
            with np.errstate(divide="ignore", invalid="ignore"):
                rel = np.where(sp > 0, sn / np.where(sp > 0, sp, 1.0) - 1.0, np.inf)
            material = (sp == 0) | (sn == 0) | (np.abs(rel) >= MATERIAL_REL_CHANGE)
            e = m[material]
            if len(e):
                pubq = e.mgrno.map(mgr_pub).fillna(q).values.astype("int16")
                out = pd.DataFrame({
                    "mgrno": e.mgrno.values.astype("int32"),
                    "permno": e.permno.values.astype("int32"),
                    "qidx": np.int16(q),
                    "public_qidx": pubq,
                    "shares_prev": np.nan_to_num(e.shares_adj_p.values, nan=0.0).astype("float32"),
                    "shares_now": np.nan_to_num(e.shares_adj.values, nan=0.0).astype("float32"),
                    "pct_pf_now": e.pct_pf.values.astype("float32"),
                    "pct_co_now": e.pct_co.values.astype("float32"),
                    "pct_pf_prev": e.pct_pf_p.values.astype("float32"),
                    "pct_co_prev": e.pct_co_p.values.astype("float32"),
                    "val_now": e.val.values.astype("float32"),
                })
                out.to_parquet(TRANS_DIR / f"q{q:03d}.parquet", index=False)
                diag["events_written"] += len(out)
            # turnover (both sides / 2), and event counters
            _accumulate_events(st, m, q, diag)
        elif prev is not None:
            diag["mgr_quarter_gap_skips"] += 1

        # =============== spell tracking (entries/exits, duration) ============
        act_key, act_start = _update_spells(st, cq, act_key, act_start, q)

        # =============== accumulate distributions through q ==================
        _accumulate_distributions(st, cq, q)
        prev = cq[["mgrno", "permno", "shares_adj", "pct_pf", "pct_co", "padj"]].rename(
            columns={"shares_adj": "shares_adj_p", "pct_pf": "pct_pf_p",
                     "pct_co": "pct_co_p", "padj": "padj_p"})
        prev_q = q
        diag["quarters"] += 1
        if verbose and q % 8 == 0:
            print(f"  {qlabel(q)}  filers={cq.mgrno.nunique():5d} pos={len(cq):8,d} "
                  f"mgrs={st.n:6d}  {time.time()-t0:6.0f}s")

    fp = pd.concat(fp_rows, ignore_index=True) if fp_rows else pd.DataFrame()
    fp.to_parquet(FP_PATH, index=False)
    diag.update(rdr.stats)
    diag["n_managers"] = int(st.n)
    diag["n_multi_permno_cusips"] = int(link.attrs.get("n_multi_permno_cusips", 0))
    diag["crsp"] = crsp.diag
    diag["seconds"] = round(time.time() - t0, 1)
    return {"fp": fp, "diag": diag, "state": st, "crsp": crsp}


def _stamp(st: FingerprintState, mi: np.ndarray, q: int) -> pd.DataFrame:
    posq = np.maximum(st.n_posqtr[mi], 1)
    dq = dur_quantiles(st.dur[mi], [0.25, 0.50, 0.75, 0.90])
    co = hist_quantiles(st.pctco[mi], PCTCO_EDGES, [0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99])
    pf = hist_quantiles(st.pctpf[mi], PCTPF_EDGES, [0.25, 0.50, 0.75, 0.90])
    c3 = st.cap3[mi].astype("float64")
    c3tot = np.maximum(c3.sum(axis=1), 1.0)
    nspell = st.dur[mi].sum(axis=1)
    top_bin = st.dur[mi][:, -1]
    return pd.DataFrame({
        "mgrno": st.mgrno[mi],
        "as_of_qidx": np.int16(q),
        "as_of_quarter": qlabel(q),
        "as_of_public_date": pd.Timestamp(public_date_of(q)),
        "hist_through_quarter": qlabel(q - 1),
        "n_quarters_filed": st.n_qtrs[mi],
        "first_quarter": [qlabel(int(x)) for x in st.first_q[mi]],
        "n_positions": st.last_npos[mi],
        "portfolio_value_usd": st.last_portval[mi],
        "n_position_quarters": st.n_posqtr[mi],
        "n_entries": st.n_entry[mi], "n_exits": st.n_exit[mi],
        "n_large_adds": st.n_add[mi], "n_large_trims": st.n_trim[mi],
        "entry_freq": st.n_entry[mi] / posq, "exit_freq": st.n_exit[mi] / posq,
        "large_add_freq": st.n_add[mi] / posq, "large_trim_freq": st.n_trim[mi] / posq,
        "dur_p25_qtrs": dq[:, 0], "dur_median_qtrs": dq[:, 1],
        "dur_p75_qtrs": dq[:, 2], "dur_p90_qtrs": dq[:, 3],
        "n_completed_spells": nspell,
        "n_open_spells_censored": st.n_open[mi],
        "dur_top_bin_censored": top_bin,
        "pct_of_portfolio_p25": pf[:, 0], "pct_of_portfolio_median": pf[:, 1],
        "pct_of_portfolio_p75": pf[:, 2], "pct_of_portfolio_p90": pf[:, 3],
        "pct_of_company_p10": co[:, 0], "pct_of_company_p25": co[:, 1],
        "pct_of_company_median": co[:, 2], "pct_of_company_p75": co[:, 3],
        "pct_of_company_p90": co[:, 4], "pct_of_company_p95": co[:, 5],
        "pct_of_company_p99": co[:, 6],
        "cap_tercile_mean": (c3[:, 0] * 0 + c3[:, 1] * 1 + c3[:, 2] * 2) / c3tot,
        "cap_tercile_modal": np.argmax(c3, axis=1).astype("int8"),
        "sector_entropy": st.last_entropy[mi],
        "turnover_last": st.last_turnover[mi],
        "turnover_mean": np.where(st.turn_n[mi] > 0,
                                  st.turn_sum[mi] / np.maximum(st.turn_n[mi], 1), np.nan),
        "active_passive": "UNKNOWN",
        "grain": "FILER",
    })


def _accumulate_events(st: FingerprintState, m: pd.DataFrame, q: int, diag: dict):
    sn = np.nan_to_num(m.shares_adj.values, nan=0.0)
    sp = np.nan_to_num(m.shares_adj_p.values, nan=0.0)
    pf = np.nan_to_num(m.pct_pf.values, nan=0.0)
    lut = pd.Series(st.idx, dtype="int32")
    mi = lut.reindex(m.mgrno.values).values.astype("int32")
    new = (sp == 0) & (sn > 0)
    ext = (sp > 0) & (sn == 0)
    add = (sp > 0) & (sn >= 1.5 * sp) & (pf >= 0.005)
    trm = (sp > 0) & (sn > 0) & (sn <= 0.5 * sp)
    np.add.at(st.n_entry, mi[new], 1)
    np.add.at(st.n_exit, mi[ext], 1)
    np.add.at(st.n_add, mi[add], 1)
    np.add.at(st.n_trim, mi[trm], 1)
    # turnover: half the absolute traded share value over portfolio value
    prc_val = np.where(np.isfinite(m.padj.values), np.nan_to_num(m.padj.values, nan=0.0),
                       np.nan_to_num(m.padj_p.values, nan=0.0))
    traded = np.abs(sn - sp) * prc_val
    val_now = np.nan_to_num(m.val.values, nan=0.0)
    val_prev = sp * np.nan_to_num(m.padj_p.values, nan=0.0)
    dfv = pd.DataFrame({"mi": mi, "traded": traded, "vn": val_now, "vp": val_prev})
    g = dfv.groupby("mi").sum()
    # denominator = AVERAGE of the two quarter-ends. Using only the current one
    # made a filer who liquidated report turnover in the hundreds of thousands.
    den = 0.5 * (g.vn.values + g.vp.values)
    tv = np.where(den > 0, 0.5 * g.traded.values / den, np.nan)
    tv = np.clip(tv, 0.0, 3.0)          # 300%/quarter cap; a filer cannot trade more
    gi = g.index.values.astype("int32")
    good = np.isfinite(tv)
    st.turn_sum[gi[good]] += tv[good]
    st.turn_n[gi[good]] += 1
    st.last_turnover[gi] = tv


def _update_spells(st, cq, act_key, act_start, q):
    mi = cq.mi.values.astype("int64")
    cur_key = np.unique(mi * 100000 + cq.permno.values.astype("int64"))
    filers = np.unique(cq.mi.values)
    act_mgr = (act_key // 100000).astype("int32")
    is_filer = np.isin(act_mgr, filers)
    in_cur = np.isin(act_key, cur_key)
    exited = is_filer & ~in_cur
    if exited.any():
        dur = np.clip(q - act_start[exited], 1, DUR_MAX_BIN)
        emi = act_mgr[exited]
        np.add.at(st.dur, (emi, dur - 1), 1)
    keep = ~exited
    new_mask = ~np.isin(cur_key, act_key)
    new_key = cur_key[new_mask]
    act_key = np.concatenate([act_key[keep], new_key])
    act_start = np.concatenate([act_start[keep],
                                np.full(len(new_key), q, dtype="int16")])
    o = np.argsort(act_key)
    act_key, act_start = act_key[o], act_start[o]
    st.n_open[:] = 0
    if len(act_key):
        u, c = np.unique((act_key // 100000).astype("int32"), return_counts=True)
        st.n_open[u] = c
    return act_key, act_start


def _accumulate_distributions(st, cq, q):
    mi = cq.mi.values.astype("int32")
    co_bin = np.clip(np.digitize(cq.pct_co.values, PCTCO_EDGES) - 1, 0, len(PCTCO_EDGES) - 2)
    pf_bin = np.clip(np.digitize(np.nan_to_num(cq.pct_pf.values), PCTPF_EDGES) - 1,
                     0, len(PCTPF_EDGES) - 2)
    np.add.at(st.pctco, (mi, co_bin), 1)
    np.add.at(st.pctpf, (mi, pf_bin), 1)
    c3 = np.nan_to_num(cq.cap3.values, nan=1.0).astype("int32")
    np.add.at(st.cap3, (mi, np.clip(c3, 0, 2)), 1)
    np.add.at(st.n_posqtr, mi, 1)
    filers = np.unique(mi)
    st.n_qtrs[filers] += 1
    fresh = filers[st.first_q[filers] < 0]
    st.first_q[fresh] = q
    st.last_q[filers] = q
    g = cq.groupby("mi")
    st.last_npos[g.size().index.values.astype("int32")] = g.size().values
    pv = g["val"].sum()
    st.last_portval[pv.index.values.astype("int32")] = pv.values
    # sector-mix entropy of value weights (SIC 2-digit)
    sw = cq.groupby(["mi", "sic2"])["val"].sum().reset_index()
    tot = sw.groupby("mi")["val"].transform("sum")
    w = np.where(tot > 0, sw.val.values / tot.values, 0.0)
    ent = pd.DataFrame({"mi": sw.mi.values,
                        "e": -np.where(w > 0, w * np.log(np.maximum(w, 1e-12)), 0.0)}
                       ).groupby("mi")["e"].sum()
    st.last_entropy[ent.index.values.astype("int32")] = ent.values


# ---------------------------------------------------------------- receipt
def write_receipt(res: dict):
    fp, diag, st = res["fp"], res["diag"], res.get("state")
    names = pd.read_parquet(BULK / "tr_13f__s34names.parquet",
                            columns=["mgrno", "mgrname", "typecode", "rdate1", "rdate2"])
    names["mgrno"] = names.mgrno.astype("int64")
    name_of = names.sort_values("rdate2").drop_duplicates("mgrno", keep="last") \
                   .set_index("mgrno")["mgrname"]

    last = fp.sort_values("as_of_qidx").drop_duplicates("mgrno", keep="last")
    famous = {}
    for tag, pat in FAMOUS.items():
        hit = names[names.mgrname.str.upper().str.contains(pat, regex=False, na=False)]
        if hit.empty:
            famous[tag] = {"resolved": False, "pattern": pat}
            continue
        # the filer with the most fingerprint history wins the name
        cand = last[last.mgrno.isin(hit.mgrno.values)]
        if cand.empty:
            famous[tag] = {"resolved": False, "pattern": pat,
                           "note": "mgrno in s34names but no fingerprint rows in kept years"}
            continue
        r = cand.sort_values("n_quarters_filed").iloc[-1]
        famous[tag] = {
            "resolved": True,
            "mgrno": int(r.mgrno),
            "mgrname": str(name_of.get(int(r.mgrno), "?")),
            "as_of_quarter": str(r.as_of_quarter),
            "n_quarters_filed": int(r.n_quarters_filed),
            "n_positions": int(r.n_positions),
            "portfolio_value_usd": float(r.portfolio_value_usd),
            "median_holding_duration_qtrs": _nn(r.dur_median_qtrs),
            "dur_p25_p75_p90_qtrs": [_nn(r.dur_p25_qtrs), _nn(r.dur_p75_qtrs),
                                     _nn(r.dur_p90_qtrs)],
            "n_completed_spells": int(r.n_completed_spells),
            "n_open_spells_censored": int(r.n_open_spells_censored),
            "median_pct_of_portfolio": _nn(r.pct_of_portfolio_median),
            "median_pct_of_company": _nn(r.pct_of_company_median),
            "p90_pct_of_company": _nn(r.pct_of_company_p90),
            "cap_tercile_mean": _nn(r.cap_tercile_mean),
            "sector_entropy_nats": _nn(r.sector_entropy),
            "turnover_mean": _nn(r.turnover_mean),
            "entry_freq": _nn(r.entry_freq), "exit_freq": _nn(r.exit_freq),
            "active_passive": "UNKNOWN (not observable in entitled WRDS; idea doc 4a)",
        }

    def dist(s):
        s = pd.Series(s).replace([np.inf, -np.inf], np.nan).dropna()
        if s.empty:
            return None
        return {k: float(np.round(v, 6)) for k, v in
                zip(["min", "p10", "p25", "p50", "p75", "p90", "p99", "max", "mean"],
                    [s.min(), *s.quantile([.10, .25, .50, .75, .90, .99]).tolist(),
                     s.max(), s.mean()])}

    receipt = {
        "artefact": "HOLDER FINGERPRINT panel",
        "built_at": pd.Timestamp.utcnow().isoformat(),
        "licence": "PRODUCT_EXPERIMENT",
        "source": "docs/IDEA_2026-08-31_HOLDER_PROVENANCE_TO_THE_ROOTS.md (H2/H3, filer level)",
        "grain": "FILER (mgrno). Vehicle-level split is NOT observable — every row "
                 "carries active_passive=UNKNOWN. BlackRock consolidated its subsidiary "
                 "mgrnos into 9385 at 2017Q1.",
        "pit_rule": {
            "public_date": "quarter_end(max(rdate, first fdate vintage)) + 45 calendar days",
            "why": "tr_13f.s34 carries NO SEC filing timestamp; fdate is Thomson's "
                   "vintage quarter, not a filing date. The statutory 13F deadline "
                   "applied to the later of report quarter and first vintage is the "
                   "conservative public date.",
            "fingerprint": "the stamp for as_of_quarter q is built from filings through "
                           "q-1 only; it never reads quarter q or later.",
        },
        "inputs": {
            "holdings": "backend/data/optimus/wrds/tr13f_s34_YYYY.parquet",
            "prices": "backend/data/optimus/wrds/crsp_dsf_YYYY.parquet (ret, incl. "
                      "compounded CRSP delisting returns)",
            "link": "bulk/crsp__dsenames.parquet ncusip->permno (1:1 after collapse)",
            "names": "bulk/tr_13f__s34names.parquet",
        },
        "outputs": {
            "panel": str(FP_PATH.relative_to(ROOT)).replace("\\", "/"),
            "quarter_snapshots": str(QSNAP_PATH.relative_to(ROOT)).replace("\\", "/"),
            "transitions_cache": str(TRANS_DIR.relative_to(ROOT)).replace("\\", "/"),
        },
        "scale": {
            "fingerprint_rows": int(len(fp)),
            "distinct_managers": int(fp.mgrno.nunique()) if len(fp) else 0,
            "quarters_covered": int(fp.as_of_qidx.nunique()) if len(fp) else 0,
            "first_quarter": str(fp.as_of_quarter.iloc[0]) if len(fp) else None,
            "last_quarter": str(fp.sort_values("as_of_qidx").as_of_quarter.iloc[-1])
                            if len(fp) else None,
            "material_position_changes_cached": int(diag["events_written"]),
        },
        "distributions_at_last_stamp_per_manager": {
            "median_holding_duration_qtrs": dist(last.dur_median_qtrs),
            "dur_p90_qtrs": dist(last.dur_p90_qtrs),
            "n_positions": dist(last.n_positions),
            "n_quarters_filed": dist(last.n_quarters_filed),
            "pct_of_portfolio_median": dist(last.pct_of_portfolio_median),
            "pct_of_company_median": dist(last.pct_of_company_median),
            "entry_freq": dist(last.entry_freq),
            "exit_freq": dist(last.exit_freq),
            "turnover_mean": dist(last.turnover_mean),
            "sector_entropy_nats": dist(last.sector_entropy),
        },
        "largest_filers_at_last_stamp": _largest_filers(last, name_of, 15),
        "duration_censoring": {
            "rule": "a spell is (entry quarter -> first quarter the filer reports and "
                    "the name is gone). Open spells at the stamp are EXCLUDED from the "
                    "duration quantiles and counted in n_open_spells_censored; spells "
                    f">= {DUR_MAX_BIN} quarters pile into the top bin and are reported "
                    f"as {DUR_MAX_BIN}.",
            "total_completed_spells": int(last.n_completed_spells.sum()),
            "spells_in_censored_top_bin": int(last.dur_top_bin_censored.sum()),
            "open_spells_at_end": int(last.n_open_spells_censored.sum()),
            "note": "totals are summed over each manager's FINAL stamp, which is "
                    "their cumulative count.",
        },
        "famous_filers": famous,
        "diagnostics": diag,
        "caveats": [
            "s34 has no `value` column in this pull: position value = as-reported "
            "shares x CRSP quarter-end price.",
            "share counts are made split-comparable with CRSP cfacshr "
            "(shrout*cfacshr is constant across splits — verified on AAPL 2014 7:1).",
            "SIC is the LAST siccd per permno from dsenames, not time-varying.",
            "the 13F pull universe CHANGES at 2013: 1996-2012 used the early-era "
            "screened CUSIP list (24,114 cusips), 2013-2024 the v1 list (11,603). "
            "Cross-era counts are therefore not comparable.",
            "market benchmark = the screened CRSP universe present in these files, "
            "not the whole CRSP tape.",
        ],
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    return receipt



def _largest_filers(last: pd.DataFrame, name_of: pd.Series, n: int) -> list:
    """Data-driven counterpart to the hand-picked FAMOUS list: whoever actually
    runs the most money at their final stamp. Guards against a name pattern
    quietly resolving to nobody (FMR is exactly that case in this s34names
    vintage — `FMR CORP` ends 1990-12-31 and no later Fidelity filer carries the
    string, so the pattern is reported UNRESOLVED rather than mis-bound)."""
    top = last.sort_values("portfolio_value_usd", ascending=False).head(n)
    return [{
        "mgrno": int(r.mgrno),
        "mgrname": str(name_of.get(int(r.mgrno), "?")),
        "as_of_quarter": str(r.as_of_quarter),
        "portfolio_value_usd": float(r.portfolio_value_usd),
        "n_positions": int(r.n_positions),
        "median_holding_duration_qtrs": _nn(r.dur_median_qtrs),
        "dur_p90_qtrs": _nn(r.dur_p90_qtrs),
        "median_pct_of_company": _nn(r.pct_of_company_median),
        "turnover_mean": _nn(r.turnover_mean),
        "entry_freq": _nn(r.entry_freq),
        "active_passive": "UNKNOWN",
    } for r in top.itertuples()]

def _nn(x):
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(f) else round(f, 8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=S34_FIRST_YEAR)
    ap.add_argument("--end-year", type=int, default=S34_LAST_YEAR)
    ap.add_argument("--receipt-only", action="store_true",
                    help="rebuild the summary receipt from the saved panel and the "
                         "diagnostics already in the receipt; no re-computation")
    a = ap.parse_args()
    if a.receipt_only:
        prev = json.loads(RECEIPT.read_text(encoding="utf-8"))
        res = {"fp": pd.read_parquet(FP_PATH), "diag": prev["diagnostics"]}
        r = write_receipt(res)
        print(json.dumps(r["scale"], indent=2))
        print("receipt ->", RECEIPT)
        return
    res = build(a.start_year, a.end_year)
    r = write_receipt(res)
    print(json.dumps(r["scale"], indent=2))
    print(json.dumps(r["diagnostics"], indent=2, default=str))
    print("receipt ->", RECEIPT)


if __name__ == "__main__":
    main()
