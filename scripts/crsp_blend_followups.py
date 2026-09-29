"""Two follow-ups the 2026-09-29 CRSP_BLEND review named ($0, no LLM, no network).

    python -m scripts.crsp_blend_followups --part daily --run-id <id>   # skip-day ratios + Corwin-Schultz spreads
    python -m scripts.crsp_blend_followups --part run --run-id <id> --daily-run <id>   # experiments A and B

Licence PRODUCT_EXPERIMENT. Reads the CRSP library panel and fundamentals of run
LIB_2026-09-29T0802Z (panel 2026-09-29T075640Z, fund 2026-09-29T041550Z), the CRSP
daily files and the WRDS ratio file; writes only under crsp_rebuild/ with the run id
in every name. Engine unchanged: `calendar_offset_triplet.run_one` (21-draw matched
twin, two seed sets). No book, ledger or past receipt is touched.

A. co03_reversal_in_high_margin, decision line stated BEFORE running (DECISION_LINE_A).
   (1) entry one trading day later: open of session t+2 (close of t+1 when no open),
       exit likewise one session later;
   (2) per-name, per-month round-trip cost = Corwin-Schultz (2012) high-low spread,
       mean of the two-day estimates over the 20 pairs ending at the decision date,
       overnight-adjusted, negative two-day estimates set to 0, capped at CS_CAP;
       charged as a FULL round trip each month to every held name of book and twin
       alike (book turnover ~92%/mo, twin redrawn every month): on top of the flat
       band schedule, and instead of it;
   (3) fundamentals lag: a WRDS ratio row is usable only from
       max(public_date, qdate + FUND_LAG_DAYS) (qdate = the fiscal period end it rests on).
B. px_vs_ma200 and mom_12_1 inside a RANK band: the eligible universe on each date is
   cut to the top 300 / top 500 names by trailing 63-session median dollar volume, so
   the rule and its twin draw from the same rank band.
"""
from __future__ import annotations

import argparse
import dataclasses
import gc
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OPT = REPO / "backend" / "data" / "optimus"
WRDS = OPT / "wrds"
OUT = OPT / "crsp_rebuild"
PANEL_RUN = "2026-09-29T075640Z"
FUND_RUN = "2026-09-29T041550Z"
BOARD_RUN = "LIB_2026-09-29T0802Z"
CS_CAP = 0.20
FUND_LAG_DAYS = 122          # ~4 months after the fiscal period end
WINDOWS = {"1991-2024": (None, None), "2001-2024": ("2001-01-01", "2024-12-31"),
           "2017-2024": ("2017-01-01", "2024-12-31"), "2020s": ("2020-01-01", "2024-12-31")}
DECISION_LINE_A = ("rule - twin21 with all three changes, 2001-2024: >= +0.40%/mo at t >= 2 -> remains a "
                   "candidate; <= +0.10%/mo -> FAILED_VARIANT; otherwise CANNOT_DISTINGUISH")


def say(*a) -> None:
    print(*a, flush=True)


# ── pure helpers (tested offline) ────────────────────────────────────────────

def corwin_schultz_pairs(hi, lo, close) -> np.ndarray:
    """Two-day Corwin-Schultz spread for each (t, t+1) pair of ONE name, stored at t+1.
    Overnight adjustment: day t+1's range is shifted when close_t lies outside it.
    Negative estimates -> 0 (the paper's convention). NaN when a range is unusable."""
    hi, lo, close = (np.asarray(x, dtype=float) for x in (hi, lo, close))
    n = len(hi)
    out = np.full(n, np.nan)
    if n < 2:
        return out
    h0, l0, c0 = hi[:-1], lo[:-1], close[:-1]
    h1, l1 = hi[1:], lo[1:]
    shift = np.where(c0 < l1, l1 - c0, np.where(c0 > h1, h1 - c0, 0.0))
    shift = np.nan_to_num(shift)
    h1, l1 = h1 - shift, l1 - shift
    with np.errstate(invalid="ignore", divide="ignore"):
        ok = (h0 > 0) & (l0 > 0) & (h1 > 0) & (l1 > 0) & (h0 >= l0) & (h1 >= l1)
        beta = np.log(h0 / l0) ** 2 + np.log(h1 / l1) ** 2
        gamma = np.log(np.maximum(h0, h1) / np.minimum(l0, l1)) ** 2
        k = 3.0 - 2.0 * math.sqrt(2.0)
        alpha = (np.sqrt(2.0 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
        s = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))
    out[1:] = np.where(ok, np.maximum(s, 0.0), np.nan)
    return out


def skip_fwd(fwd, g_now, g_next) -> np.ndarray:
    """Forward return re-based one session later at BOTH ends: (1+fwd) * g_next / g_now - 1,
    g = skip-entry price / engine-entry price. Missing g -> 1 (the engine's own entry)."""
    g_now, g_next = np.asarray(g_now, dtype=float), np.asarray(g_next, dtype=float)
    gn = np.where(np.isfinite(g_now) & (g_now > 0), g_now, 1.0)
    gx = np.where(np.isfinite(g_next) & (g_next > 0), g_next, 1.0)
    return (1.0 + np.asarray(fwd, dtype=float)) * gx / gn - 1.0


def rank_band_mask(df: pd.DataFrame, n: int) -> np.ndarray:
    """eligible AND in the top `n` by median_dollar_vol among eligible names on its date."""
    el = df["eligible"].to_numpy(dtype=bool)
    r = df["median_dollar_vol"].where(df["eligible"]).groupby(df["date"]).rank(ascending=False, method="first")
    return el & (r.to_numpy() <= n)


def verdict_a(w: dict) -> str:
    m, t = w.get("mean_monthly"), w.get("t_blocks")
    if m is None:
        return "NOT_COMPUTED"
    if m >= 0.004 and (t or 0) >= 2.0:
        return "REMAINS_CANDIDATE"
    if m <= 0.001:
        return "FAILED_VARIANT"
    return "CANNOT_DISTINGUISH"


# ── part 1: daily -> per (permno, month-end) skip ratio and CS spread ─────────

def part_daily(run_id: str) -> int:
    from scripts.night_checkpoint import atomic_write_json           # noqa: PLC0415
    op = OUT / f"followups_daily_{run_id}.parquet"
    if op.exists():
        say(f"REFUSED: {op.name} exists")
        return 2
    t0 = time.time()
    me = pd.read_parquet(OUT / f"library_panel_{PANEL_RUN}.parquet", columns=["date"])["date"]
    me = pd.DatetimeIndex(sorted(pd.to_datetime(me).unique()))
    cols = ["permno", "date", "prc", "ret", "openprc", "askhi", "bidlo"]

    def rd(y):
        d = pd.read_parquet(WRDS / f"crsp_dsf_{y}.parquet", columns=cols)
        d["date"] = pd.to_datetime(d["date"])
        return d

    parts, audit = [], []
    for y in range(1990, 2025):
        frames = []
        if y > 1990:
            p = rd(y - 1)
            frames.append(p[p["date"] >= p["date"].max() - pd.Timedelta(days=45)])
        frames.append(rd(y))
        if (WRDS / f"crsp_dsf_{y+1}.parquet").exists():
            nx = rd(y + 1)
            frames.append(nx[nx["date"] <= nx["date"].min() + pd.Timedelta(days=10)])
        d = pd.concat(frames, ignore_index=True)
        del frames
        for c in ("prc", "ret", "openprc", "askhi", "bidlo"):
            d[c] = pd.to_numeric(d[c], errors="coerce").astype("float64")
        d["permno"] = pd.to_numeric(d["permno"], errors="coerce")
        d = d.dropna(subset=["permno"]).drop_duplicates(["permno", "date"]).sort_values(["permno", "date"])
        d = d.reset_index(drop=True)
        cal = pd.DatetimeIndex(sorted(d["date"].unique()))
        pos = {dt: i for i, dt in enumerate(cal)}
        yme = me[me.year == y]
        close = d["prc"].abs()
        r = d["ret"].fillna(0.0).clip(lower=-0.99)
        tr = np.exp(np.log1p(r).groupby(d["permno"]).cumsum())
        op_ = d["openprc"].abs()
        tr_open = (tr * op_ / close).where((op_ > 0) & (close > 0))
        pv = d["permno"].to_numpy()
        starts = np.r_[0, np.flatnonzero(pv[1:] != pv[:-1]) + 1, len(d)]
        hi, lo, cl = d["askhi"].abs().to_numpy(), d["bidlo"].abs().to_numpy(), close.to_numpy()
        cs = np.full(len(d), np.nan)
        for a, b in zip(starts[:-1], starts[1:]):
            cs[a:b] = corwin_schultz_pairs(hi[a:b], lo[a:b], cl[a:b])
        d["cs"] = cs
        d["cs20"] = d.groupby("permno")["cs"].transform(lambda s: s.rolling(20, min_periods=10).mean())
        d["tr"], d["tr_open"] = tr.to_numpy(), tr_open.to_numpy()
        key = d.set_index(["date", "permno"])[["tr", "tr_open", "cs20"]].sort_index()
        rows = []
        for dt in yme:
            i = pos.get(dt)
            if i is None or i + 2 >= len(cal):
                continue
            e0, e1 = cal[i + 1], cal[i + 2]
            a = key.loc[dt][["tr", "cs20"]]
            b0 = key.loc[e0][["tr", "tr_open"]].rename(columns={"tr": "tr_e0", "tr_open": "tr_open_e0"})
            b1 = key.loc[e1][["tr_open"]].rename(columns={"tr_open": "tr_open_e1"})
            j = a.join(b0, how="left").join(b1, how="left")
            eng = j["tr_open_e0"].where(j["tr_open_e0"].notna(), j["tr"])     # engine: open t+1 else close t
            skp = j["tr_open_e1"].where(j["tr_open_e1"].notna(), j["tr_e0"])  # skip: open t+2 else close t+1
            rows.append(pd.DataFrame({"date": dt, "permno": j.index.to_numpy().astype(np.int64),
                                      "g_skip": (skp / eng).to_numpy(), "cs_spread": j["cs20"].to_numpy(),
                                      "open_used": j["tr_open_e1"].notna().to_numpy()}))
        if rows:
            R = pd.concat(rows, ignore_index=True)
            parts.append(R)
            audit.append({"year": y, "rows": int(len(R)), "g_ok": float(R["g_skip"].notna().mean()),
                          "cs_ok": float(R["cs_spread"].notna().mean()),
                          "cs_median": float(R["cs_spread"].median()), "open_share": float(R["open_used"].mean())})
            say(f"  {y}: {len(R):,} rows g_ok {audit[-1]['g_ok']:.3f} cs_ok {audit[-1]['cs_ok']:.3f} "
                f"cs_med {audit[-1]['cs_median']*1e4:.0f}bp open {audit[-1]['open_share']:.2f} {time.time()-t0:.0f}s")
        del d, key
        gc.collect()
    D = pd.concat(parts, ignore_index=True)
    D.to_parquet(op, index=False)
    atomic_write_json(OUT / f"followups_daily_{run_id}.json",
                      {"schema": "crsp_rebuild/followups_daily/1", "run_id": run_id, "licence": "PRODUCT_EXPERIMENT",
                       "llm_spend_usd": 0.0, "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "g_skip": "total-return price at the skip entry (open of session t+2, else close of t+1) "
                                 "/ the engine entry (open of t+1, else close of t)",
                       "cs_spread": "Corwin-Schultz 2012 two-day high-low spread, overnight-adjusted, negatives -> 0, "
                                    "mean of the 20 pairs ending at the decision date (min 10); CRSP askhi/bidlo "
                                    "(ask/bid on no-trade days)", "by_year": audit,
                       "seconds": round(time.time() - t0, 1)}, indent=1)
    say(f"-> {op.name} {len(D):,} rows {time.time()-t0:.0f}s")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=("daily", "run"), required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--daily-run", default=None)
    a = ap.parse_args(argv)
    if a.part == "daily":
        return part_daily(a.run_id)
    from scripts.crsp_blend_followups_run import part_run          # noqa: PLC0415
    return part_run(a.run_id, a.daily_run or a.run_id)


if __name__ == "__main__":
    sys.exit(main())
