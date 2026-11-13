"""CH-20a -- does a monthly index / SMH PUT SPREAD hedge beat simply holding less?

    python -m scripts.ch20a_hedge_replay --out <dir>
    python -m scripts.ch20a_hedge_replay --out <dir> --symbols SPY --data-dir <quotes dir>

THE QUESTION
============
The owner asked how to hedge. The only listed option quotes we hold are
OptionMetrics best bid / best offer for SPY, QQQ, IWM and SMH (pulled by
`scripts/wrds_pull_etf_option_quotes.py`). Single-name puts cannot be replayed,
so this is an index-shaped hedge laid over the index itself: the base book is
the underlying ETF at 100% (SPY for the SPY hedge, and so on). A high-beta stock
book's hedge is index-shaped too; this replay prices that shape, not a stock's.

The research prior is that systematic put buying loses money on average, so the
expected answer is that a cheaper construction wins. A clean negative is a
wanted result.

WHAT IS COMPARED (all on the SAME roll-period grid)
===================================================
    hedged         the ETF at 100% + a put spread bought every roll
    unhedged       the ETF at 100%                                 (twin 1)
    hold_less      the ETF at gross g, rest in cash at 0%, g chosen so its
                   AVERAGE drawdown equals the hedged book's        (twin 2)
    trend          the ETF when its total-return index closed above its
                   200-session mean the day before, else cash; scaled down to
                   the hedged book's average drawdown if it has more (twin 3)
    inverse_ctrl   the ETF at 100% + a daily -1x fund (modelled from the ETF's
                   own daily total return less a fee) at weight w, w chosen for
                   equal average drawdown                         (control)

The spec is frozen in `backend/config.py` (CH20A_HEDGE_*) and was committed
before the first run read a result.

EXECUTION -- NEVER THE MID
==========================
Buy the long put at BEST OFFER, sell the short put at BEST BID. Held to expiry
and settled at intrinsic on the last session's close (ETF options are
PM-settled, physically; American exercise is irrelevant to a long put held to
expiry, and an early assignment of the short leg pays the same intrinsic the
settlement does, so no exit quote is ever needed and no exit price is
invented). A long leg that is missing or crossed SKIPS the day, the day is
counted, and the next session retries. A missing short leg (the pull keeps
best_bid > 0 only, so a zero-bid far put is absent) buys the long put alone;
that is counted too, because it changes the payoff shape.

REUSED, AND FROM WHERE
======================
`scripts/optionmetrics_core_replay.py`: the data directory, the verified SECIDS,
the standard-settlement filter (`ss_flag == "0"`), the 100x multiplier and the
bid/offer crossing rule. `scripts/wrds_pull_etf_option_quotes.py`: strike
already divided by 1000; the file holds DTE 14..45 and moneyness 0.55..1.45, so
"1-3 months to expiry" is about ONE month here. Dividends: the book's return is
OptionMetrics `secprd.return` (total return, distributions included); strikes
and settlement use the raw close, rescaled by `cfadj` across a split.
`backend/services/option_implier.py` and `options_calibrator.py` are NOT used:
a real quote exists for every fill, so no pricing model is needed.

The receipt is aggregated (by year, by construction). No quote row is copied:
the quotes are licensed.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as C  # noqa: E402
from scripts.optionmetrics_core_replay import DATA as DEFAULT_DATA  # noqa: E402
from scripts.optionmetrics_core_replay import SECIDS  # noqa: E402

SPEC_KEYS = [
    "CH20A_HEDGE_SYMBOLS", "CH20A_HEDGE_LONG_MONEYNESS", "CH20A_HEDGE_LONG_BAND",
    "CH20A_HEDGE_SHORT_MONEYNESS", "CH20A_HEDGE_SHORT_BAND", "CH20A_HEDGE_DTE_TARGET",
    "CH20A_HEDGE_DTE_MIN", "CH20A_HEDGE_DTE_MAX", "CH20A_HEDGE_MULT",
    "CH20A_HEDGE_BUDGET_PER_YEAR", "CH20A_HEDGE_TREND_SMA", "CH20A_HEDGE_SWITCH_COST_BPS",
    "CH20A_HEDGE_INVERSE_FEE", "CH20A_HEDGE_CRASH_YEARS", "CH20A_HEDGE_BOOK_USD",
]
MIN_FREE_RAM_GB = 2.5
VARIANTS = ("base", "budget")
TWINS = ("hold_less", "trend", "inverse_ctrl")


class HedgeReplayRefused(RuntimeError):
    """A precondition failed; the run exits non-zero instead of writing a receipt."""


# ------------------------------------------------------------------- spec / env
def frozen_spec() -> dict[str, Any]:
    spec = {k: getattr(C, k) for k in SPEC_KEYS}
    spec = {k: (list(v) if isinstance(v, tuple) else v) for k, v in spec.items()}
    blob = json.dumps(spec, sort_keys=True).encode()
    return {"values": spec, "sha256": hashlib.sha256(blob).hexdigest()}


def free_ram_gb() -> float:
    """Free physical RAM in GB (Windows); NaN where it cannot be read."""
    try:
        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))  # type: ignore[attr-defined]
        return m.ullAvailPhys / 1e9
    except Exception:                                                # noqa: BLE001
        return float("nan")


def wait_for_ram(label: str, *, tries: int = 10, sleep_s: float = 60.0) -> float:
    for _ in range(tries):
        g = free_ram_gb()
        if not np.isfinite(g) or g >= MIN_FREE_RAM_GB:
            print(f"  free RAM before {label}: {g:.1f} GB", flush=True)
            return g
        print(f"  free RAM {g:.1f} GB < {MIN_FREE_RAM_GB} GB before {label}; waiting",
              flush=True)
        time.sleep(sleep_s)
    raise HedgeReplayRefused(f"free RAM stayed below {MIN_FREE_RAM_GB} GB before {label}")


def _git_head() -> dict:
    try:
        h = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=20).stdout.strip()
        d = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--",
                            "scripts/ch20a_hedge_replay.py", "backend/config.py"],
                           capture_output=True, text=True, timeout=20).stdout.strip()
        return {"head": h, "spec_or_script_dirty": bool(d)}
    except Exception as exc:                                         # noqa: BLE001
        return {"head": None, "error": str(exc)}


# ------------------------------------------------------------------- inventory
def _years(data_dir: Path, prefix: str) -> list[int]:
    out = []
    for f in data_dir.glob(f"{prefix}_*.parquet"):
        try:
            out.append(int(f.stem.split("_")[1]))
        except ValueError:
            continue
    return sorted(out)


def inventory(data_dir: Path, secids: dict[str, int]) -> dict:
    """Files, years, row counts and newest date -- printed before anything is replayed."""
    rows = []
    for y in sorted(set(_years(data_dir, "quotes")) | set(_years(data_dir, "under"))):
        fq, fu = data_dir / f"quotes_{y}.parquet", data_dir / f"under_{y}.parquet"
        meta_f = data_dir / f"quotes_{y}.meta.json"
        rec: dict[str, Any] = {"year": y, "quotes_file": fq.exists(), "under_file": fu.exists()}
        if meta_f.exists():
            m = json.loads(meta_f.read_text(encoding="utf-8"))
            rec["quote_rows"] = m.get("rows")
            rec["quote_rows_by_symbol"] = m.get("by_secid")
            rec["quote_dates"] = m.get("dates")
        elif fq.exists():
            import pyarrow.parquet as pq
            rec["quote_rows"] = pq.ParquetFile(fq).metadata.num_rows
        if fu.exists():
            u = pd.read_parquet(fu, columns=["secid", "date"])
            rec["under_rows_by_symbol"] = {
                s: int((u["secid"] == v).sum()) for s, v in secids.items()}
            rec["under_last_date"] = str(pd.to_datetime(u["date"]).max().date())
        rows.append(rec)
    newest = max((r.get("under_last_date", "") for r in rows), default="")
    first_by_sym = {}
    for s in secids:
        ys = [r["year"] for r in rows if (r.get("under_rows_by_symbol") or {}).get(s)]
        first_by_sym[s] = [min(ys), max(ys)] if ys else None
    return {"data_dir": str(data_dir), "n_files": len(list(data_dir.glob("*"))),
            "years": rows, "newest_date": newest, "years_by_symbol": first_by_sym}


# ------------------------------------------------------------------- loading
def load_under(data_dir: Path, secid: int) -> pd.DataFrame:
    parts = []
    for y in _years(data_dir, "under"):
        u = pd.read_parquet(data_dir / f"under_{y}.parquet",
                            columns=["secid", "date", "close", "cfadj", "return"],
                            filters=[("secid", "=", float(secid))])
        if len(u):
            parts.append(u)
    if not parts:
        return pd.DataFrame()
    u = pd.concat(parts, ignore_index=True)
    u["date"] = pd.to_datetime(u["date"])
    u = u.drop_duplicates("date").sort_values("date").reset_index(drop=True)
    u = u[np.isfinite(u["close"].astype(float)) & (u["close"].astype(float) > 0)]
    u = u.reset_index(drop=True)
    adj = u["close"].astype(float) * u["cfadj"].astype(float)
    pr = adj.pct_change()
    tr = u["return"].astype(float)
    u["ret_filled_from_price"] = ~np.isfinite(tr)
    u["ret"] = tr.where(np.isfinite(tr), pr).fillna(0.0)
    u.loc[0, "ret"] = 0.0
    u["price_ret"] = pr.fillna(0.0)
    return u


def load_puts(data_dir: Path, secid: int, lo_m: float, hi_m: float) -> pd.DataFrame:
    """Standard-settlement puts in the moneyness window, one year file at a time."""
    cols = ["date", "exdate", "strike", "best_bid", "best_offer", "ss_flag", "moneyness"]
    parts = []
    for y in _years(data_dir, "quotes"):
        q = pd.read_parquet(data_dir / f"quotes_{y}.parquet", columns=cols,
                            filters=[("secid", "=", float(secid)), ("cp_flag", "=", "P"),
                                     ("moneyness", ">=", lo_m), ("moneyness", "<=", hi_m)])
        if len(q):
            q = q[q["ss_flag"].astype(str) == "0"].drop(columns=["ss_flag", "moneyness"])
            parts.append(q)
    if not parts:
        return pd.DataFrame(columns=cols)
    q = pd.concat(parts, ignore_index=True)
    q["date"] = pd.to_datetime(q["date"])
    q["exdate"] = pd.to_datetime(q["exdate"])
    return q


# ------------------------------------------------------------------- the roll engine
def _valid(bid: float, ask: float, *, need_bid: bool) -> bool:
    if not (np.isfinite(ask) and ask > 0):
        return False
    if need_bid and not (np.isfinite(bid) and bid > 0):
        return False
    if np.isfinite(bid) and bid > ask:          # crossed
        return False
    return True


def run_rolls(under: pd.DataFrame, puts: pd.DataFrame, spec: dict) -> dict:
    """Walk the calendar: settle at expiry, buy the next spread the same session.

    Returns the rolls (entry/settle indices into `under`, cost and payoff as a
    fraction of the entry spot) and every skipped day with its reason.
    """
    dates = under["date"].to_numpy()
    close = under["close"].astype(float).to_numpy()
    cfadj = under["cfadj"].astype(float).to_numpy()
    by_date = {pd.Timestamp(d): g for d, g in puts.groupby("date")} if len(puts) else {}
    n = len(dates)
    lo_l, hi_l = spec["CH20A_HEDGE_LONG_BAND"]
    lo_s, hi_s = spec["CH20A_HEDGE_SHORT_BAND"]
    tgt_l, tgt_s = spec["CH20A_HEDGE_LONG_MONEYNESS"], spec["CH20A_HEDGE_SHORT_MONEYNESS"]
    dmin, dmax, dtgt = (spec["CH20A_HEDGE_DTE_MIN"], spec["CH20A_HEDGE_DTE_MAX"],
                        spec["CH20A_HEDGE_DTE_TARGET"])

    rolls: list[dict] = []
    skipped: list[dict] = []
    first_quote = min(by_date) if by_date else None
    if first_quote is None:
        return {"rolls": rolls, "skipped": skipped, "end_reason": "no quotes"}
    k = int(np.searchsorted(dates, np.datetime64(first_quote)))
    end_reason = "data exhausted"
    while k < n:
        d = pd.Timestamp(dates[k])

        def skip(why: str) -> None:
            skipped.append({"date": d, "reason": why})

        g = by_date.get(d)
        if g is None or g.empty:
            skip("no_quotes_that_day")
            k += 1
            continue
        dte = (g["exdate"] - d).dt.days
        ok = g[(dte >= dmin) & (dte <= dmax)]
        if ok.empty:
            skip("no_expiry_in_dte_window")
            k += 1
            continue
        exps = sorted(ok["exdate"].unique())
        ex = min(exps, key=lambda e: (abs((pd.Timestamp(e) - d).days - dtgt), pd.Timestamp(e)))
        ex = pd.Timestamp(ex)
        j = int(np.searchsorted(dates, np.datetime64(ex), side="right")) - 1
        if ex > pd.Timestamp(dates[-1]) or j <= k:
            end_reason = f"next expiry {ex.date()} is beyond the last session in the file"
            break
        chain = ok[ok["exdate"] == ex]
        spot = close[k]
        m = chain["strike"].astype(float) / spot
        lband = chain[(m >= lo_l) & (m <= hi_l)]
        if lband.empty:
            skip("long_leg_missing")
            k += 1
            continue
        li = (lband["strike"].astype(float) - tgt_l * spot).abs().idxmin()
        L = lband.loc[li]
        if not _valid(float(L["best_bid"]), float(L["best_offer"]), need_bid=False):
            skip("long_leg_crossed_or_no_ask")
            k += 1
            continue
        sband = chain[(m >= lo_s) & (m <= hi_s) & (chain["strike"] < L["strike"])]
        short_ok = False
        S = None
        if not sband.empty:
            si = (sband["strike"].astype(float) - tgt_s * spot).abs().idxmin()
            S = sband.loc[si]
            short_ok = _valid(float(S["best_bid"]), float(S["best_offer"]), need_bid=True)
        kl = float(L["strike"])
        ks = float(S["strike"]) if short_ok else float("nan")
        debit = float(L["best_offer"]) - (float(S["best_bid"]) if short_ok else 0.0)
        s1 = close[j] * cfadj[j] / cfadj[k]       # settlement spot in ENTRY units
        pay = max(kl - s1, 0.0) - (max(ks - s1, 0.0) if short_ok else 0.0)
        rolls.append({
            "entry_i": k, "settle_i": j, "entry": d, "settle": pd.Timestamp(dates[j]),
            "expiry": ex, "dte": int((ex - d).days),
            "long_m": kl / spot, "short_m": (ks / spot) if short_ok else None,
            "long_only": not short_ok,
            "short_reason": None if short_ok else (
                "short_leg_missing" if sband.empty else "short_leg_crossed_or_no_bid"),
            "cost": debit / spot, "pay": pay / spot,
            "split_in_hold": bool(cfadj[j] != cfadj[k]),
        })
        k = j                                      # next entry attempt: settlement day
    return {"rolls": rolls, "skipped": skipped, "end_reason": end_reason}


# ------------------------------------------------------------------- the book
def daily_indices(under: pd.DataFrame, spec: dict) -> dict[str, np.ndarray]:
    ret = under["ret"].to_numpy(float)
    tr = np.cumprod(1.0 + ret)
    sma = pd.Series(tr).rolling(int(spec["CH20A_HEDGE_TREND_SMA"])).mean().to_numpy()
    # position applied to day t's return = signal at the close of t-1.
    above = np.where(np.isfinite(sma), tr > sma, True)
    pos = np.concatenate([[1.0], above[:-1].astype(float)])
    switch = np.concatenate([[0.0], (np.diff(pos) != 0).astype(float)])
    trend_r = pos * ret - switch * spec["CH20A_HEDGE_SWITCH_COST_BPS"] / 1e4
    inv_r = -ret - spec["CH20A_HEDGE_INVERSE_FEE"] / 252.0
    inv_r[0] = 0.0
    return {"tr": tr, "trend": np.cumprod(1.0 + trend_r), "inv": np.cumprod(1.0 + inv_r),
            "pos": pos, "n_switches": int(switch.sum()),
            "sma_defined_from": int(np.argmax(np.isfinite(sma))) if np.isfinite(sma).any()
            else -1}


def period_returns(under: pd.DataFrame, roll: dict, idx: dict, spec: dict,
                   variant: str) -> pd.DataFrame:
    """One row per roll period [previous settlement, this settlement]."""
    tr, trend, inv = idx["tr"], idx["trend"], idx["inv"]
    rows = []
    prev = None
    for r in roll["rolls"]:
        a = prev if prev is not None else r["entry_i"]
        te, b = r["entry_i"], r["settle_i"]
        cost = r["cost"]
        h = 1.0
        if variant == "budget":
            cap = spec["CH20A_HEDGE_BUDGET_PER_YEAR"] * r["dte"] / 365.0
            h = min(1.0, cap / cost) if cost > 0 else 1.0
        g_pre, g_hold = tr[te] / tr[a], tr[b] / tr[te]
        hedged = g_pre * ((1.0 - h * cost) * g_hold + h * r["pay"])
        rows.append({
            "start": pd.Timestamp(under["date"].iloc[a]), "end": r["settle"],
            "year": r["settle"].year,
            "hedged": hedged - 1.0, "unhedged": tr[b] / tr[a] - 1.0,
            "trend_raw": trend[b] / trend[a] - 1.0, "inv_leg": inv[b] / inv[a] - 1.0,
            "hedge_ratio": h, "cost_pct": h * cost, "pay_pct": h * r["pay"],
            "long_only": r["long_only"], "skipped_days_before_entry": te - a,
        })
        prev = b
    return pd.DataFrame(rows)


# ------------------------------------------------------------------- statistics
def equity(r: np.ndarray) -> np.ndarray:
    return np.concatenate([[1.0], np.cumprod(1.0 + np.asarray(r, float))])


def drawdowns(r: np.ndarray) -> np.ndarray:
    e = equity(r)
    return 1.0 - e / np.maximum.accumulate(e)


def avg_dd(r: np.ndarray) -> float:
    return float(drawdowns(r).mean())


def solve_scale(build, target_add: float, lo: float = 0.0, hi: float = 1.0,
                steps: int = 2000) -> tuple[float, float]:
    """The scale in [lo, hi] whose series' average drawdown is nearest the target."""
    best = (hi, float("inf"))
    for s in np.linspace(lo, hi, steps + 1):
        d = abs(avg_dd(build(s)) - target_add)
        if d < best[1]:
            best = (float(s), d)
    return best


def metrics(r: np.ndarray, years: float, book_usd: float) -> dict:
    r = np.asarray(r, float)
    tw = float(np.prod(1.0 + r))
    dd = drawdowns(r)
    ppy = len(r) / years if years > 0 else float("nan")
    return {
        "terminal_wealth": tw,
        "cagr": float(tw ** (1.0 / years) - 1.0) if years > 0 and tw > 0 else float("nan"),
        "vol_ann": float(np.std(r, ddof=1) * math.sqrt(ppy)) if len(r) > 1 else float("nan"),
        "max_drawdown": float(dd.max()), "avg_drawdown": float(dd.mean()),
        "worst_period": float(r.min()), "best_period": float(r.max()),
        "worst_period_usd": float(r.min() * book_usd),
        "max_drawdown_usd": float(-dd.max() * book_usd),
    }


def compare(pr: pd.DataFrame, spec: dict) -> dict:
    """Twins at equal average drawdown, by-year table, crash/calm split, LOYO, verdict."""
    H = pr["hedged"].to_numpy()
    U = pr["unhedged"].to_numpy()
    TR = pr["trend_raw"].to_numpy()
    IV = pr["inv_leg"].to_numpy()
    target = avg_dd(H)
    notes = []

    if avg_dd(U) <= target:
        g, gerr = 1.0, 0.0
        notes.append("the hedge did NOT lower average drawdown: hold_less is the unhedged book")
    else:
        g, gerr = solve_scale(lambda s: s * U, target)
    if avg_dd(TR) <= target:
        st, sterr = 1.0, 0.0
        notes.append("trend at full gross already has <= the hedged book's average drawdown")
    else:
        st, sterr = solve_scale(lambda s: s * TR, target)
    w, werr = solve_scale(lambda s: U + s * IV, target)

    series = {"hedged": H, "unhedged": U, "hold_less": g * U, "trend": st * TR,
              "trend_full": TR, "inverse_ctrl": U + w * IV}
    years = (pr["end"].iloc[-1] - pr["start"].iloc[0]).days / 365.25
    book = float(spec["CH20A_HEDGE_BOOK_USD"])
    m = {k: metrics(v, years, book) for k, v in series.items()}

    by_year = []
    for y, grp in pr.groupby("year"):
        ix = grp.index.to_numpy()
        row: dict[str, Any] = {"year": int(y), "n_periods": int(len(ix)),
                               "crash": int(y) in set(spec["CH20A_HEDGE_CRASH_YEARS"]),
                               "hedge_cost_pct_equity": float(grp["cost_pct"].sum()),
                               "hedge_payoff_pct_equity": float(grp["pay_pct"].sum()),
                               "long_only_rolls": int(grp["long_only"].sum())}
        row["hedge_net_pct_equity"] = row["hedge_payoff_pct_equity"] - row["hedge_cost_pct_equity"]
        for k, v in series.items():
            row[k] = float(np.prod(1.0 + v[ix]) - 1.0)
        by_year.append(row)

    crash_mask = pr["year"].isin(spec["CH20A_HEDGE_CRASH_YEARS"]).to_numpy()
    split = {}
    for lab, mask in (("crash_years", crash_mask), ("calm_years", ~crash_mask)):
        yrs_in = sorted(set(pr.loc[mask, "year"].tolist()))
        d = {"years": yrs_in, "n_periods": int(mask.sum()),
             "hedge_cost_pct_equity": float(pr.loc[mask, "cost_pct"].sum()),
             "hedge_payoff_pct_equity": float(pr.loc[mask, "pay_pct"].sum())}
        for k, v in series.items():
            tot = float(np.prod(1.0 + v[mask])) if mask.any() else float("nan")
            d[k] = {"compounded": tot - 1.0,
                    "per_year_geo": (tot ** (1.0 / len(yrs_in)) - 1.0) if yrs_in else None}
        split[lab] = d

    # leave-one-year-out on terminal wealth, scales held at their full-sample values
    loyo = {}
    for x in TWINS:
        rows = []
        for y in sorted(pr["year"].unique()):
            keep = (pr["year"] != y).to_numpy()
            rows.append({"dropped": int(y),
                         "hedged_tw": float(np.prod(1.0 + H[keep])),
                         "twin_tw": float(np.prod(1.0 + series[x][keep]))})
        hw = [r["hedged_tw"] > r["twin_tw"] for r in rows]
        loyo[x] = {"hedge_ahead_full": bool(m["hedged"]["terminal_wealth"]
                                            > m[x]["terminal_wealth"]),
                   "hedge_ahead_in_n_of": [int(sum(hw)), len(hw)],
                   "worst_drop_for_hedge": min(rows, key=lambda r: r["hedged_tw"] - r["twin_tw"]),
                   "worst_drop_for_twin": max(rows, key=lambda r: r["hedged_tw"] - r["twin_tw"])}

    verdict = decide(m, loyo)
    return {"scales": {"hold_less_gross": g, "hold_less_add_gap": gerr,
                       "trend_scale": st, "trend_add_gap": sterr,
                       "inverse_weight": w, "inverse_add_gap": werr,
                       "target_avg_drawdown": target},
            "metrics": m, "by_year": by_year, "crash_vs_calm": split, "loyo": loyo,
            "years": years, "notes": notes, "verdict": verdict}


def decide(m: dict, loyo: dict) -> dict:
    """Frozen rule. Hedge wins only if ahead of all three on terminal wealth in the
    full sample AND in every leave-one-year-out; a twin wins only if ahead of the
    hedge in the full sample AND in every leave-one-year-out; else CANNOT_DISTINGUISH.
    """
    if all(loyo[x]["hedge_ahead_full"] and loyo[x]["hedge_ahead_in_n_of"][0]
           == loyo[x]["hedge_ahead_in_n_of"][1] for x in TWINS):
        return {"label": "HEDGE_BEATS_TWINS", "twin": None}
    robust = [x for x in TWINS if not loyo[x]["hedge_ahead_full"]
              and loyo[x]["hedge_ahead_in_n_of"][0] == 0]
    if robust:
        best = max(robust, key=lambda x: m[x]["terminal_wealth"])
        return {"label": "TWIN_WINS", "twin": best, "all_robust_winners": robust}
    return {"label": "CANNOT_DISTINGUISH", "twin": None}


def plain_sentence(sym: str, res: dict) -> str:
    m, v, sc = res["metrics"], res["verdict"], res["scales"]
    cost = np.mean([r["hedge_cost_pct_equity"] for r in res["by_year"]])
    h = m["hedged"]["terminal_wealth"]
    hl = m["hold_less"]["terminal_wealth"]
    base = (f"{sym}: the monthly put spread cost about {cost:.1%} of the book a year; "
            f"$1 hedged became ${h:.2f}, while simply holding {sc['hold_less_gross']:.0%} "
            f"in {sym} and the rest in cash (same average drawdown) became ${hl:.2f}")
    if v["label"] == "HEDGE_BEATS_TWINS":
        return base + " -- the hedge came out ahead of every cheaper alternative in every year-dropped check."
    if v["label"] == "TWIN_WINS":
        return (base + f" -- the cheaper '{v['twin']}' alternative ended with more money, "
                f"and stayed ahead whichever single year is removed.")
    return base + " -- the gap is not stable when single years are removed, so the data cannot tell them apart."


# ------------------------------------------------------------------- per symbol
def replay_symbol(sym: str, data_dir: Path, secid: int, spec: dict) -> dict:
    wait_for_ram(f"{sym} load")
    under = load_under(data_dir, secid)
    if under.empty:
        return {"symbol": sym, "status": "NO_UNDERLYING"}
    lo = min(spec["CH20A_HEDGE_SHORT_BAND"][0], spec["CH20A_HEDGE_LONG_BAND"][0]) - 0.02
    hi = max(spec["CH20A_HEDGE_SHORT_BAND"][1], spec["CH20A_HEDGE_LONG_BAND"][1]) + 0.02
    puts = load_puts(data_dir, secid, lo, hi)
    print(f"  {sym}: underlying {len(under):,} sessions "
          f"{under['date'].iloc[0].date()}..{under['date'].iloc[-1].date()}; "
          f"puts in window {len(puts):,} rows", flush=True)
    roll = run_rolls(under, puts, spec)
    del puts
    if len(roll["rolls"]) < 12:
        return {"symbol": sym, "status": "TOO_FEW_ROLLS", "n_rolls": len(roll["rolls"]),
                "skipped": len(roll["skipped"])}
    idx = daily_indices(under, spec)
    sk = pd.DataFrame(roll["skipped"])
    first, last = roll["rolls"][0]["entry"], roll["rolls"][-1]["settle"]
    in_win = sk[(sk["date"] >= first) & (sk["date"] <= last)] if len(sk) else sk
    pre = sk[sk["date"] < first] if len(sk) else sk
    rolls_df = pd.DataFrame(roll["rolls"])
    out: dict[str, Any] = {
        "symbol": sym, "status": "OK", "window": [str(first.date()), str(last.date())],
        "end_reason": roll["end_reason"],
        "n_rolls": int(len(rolls_df)),
        "n_long_only_rolls": int(rolls_df["long_only"].sum()),
        "long_only_reasons": rolls_df["short_reason"].value_counts().to_dict(),
        "n_split_in_hold": int(rolls_df["split_in_hold"].sum()),
        "skipped_quote_days_in_window": int(len(in_win)),
        "skipped_by_reason": in_win["reason"].value_counts().to_dict() if len(in_win) else {},
        "skipped_days_before_first_roll": int(len(pre)),
        "skipped_in_window_by_year": (in_win.groupby(in_win["date"].dt.year).size()
                                      .astype(int).to_dict() if len(in_win) else {}),
        "dte_median": float(rolls_df["dte"].median()),
        "long_moneyness_median": float(rolls_df["long_m"].median()),
        "short_moneyness_median": float(rolls_df["short_m"].dropna().median())
        if rolls_df["short_m"].notna().any() else None,
        "cost_pct_spot_median": float(rolls_df["cost"].median()),
        "trend_switches": idx["n_switches"],
        "dividends_check": {
            "total_return_minus_price_return_per_year": float(
                (under["ret"] - under["price_ret"]).sum()
                / max(1e-9, (under["date"].iloc[-1] - under["date"].iloc[0]).days / 365.25)),
            "sessions_return_filled_from_price": int(under["ret_filled_from_price"].sum()),
        },
        "last_spot_contract_notional_usd": float(under["close"].iloc[-1] * spec["CH20A_HEDGE_MULT"]),
        "variants": {},
    }
    for v in VARIANTS:
        pr = period_returns(under, roll, idx, spec, v)
        res = compare(pr, spec)
        res["mean_hedge_ratio"] = float(pr["hedge_ratio"].mean())
        res["n_periods"] = int(len(pr))
        res["plain"] = plain_sentence(sym, res)
        out["variants"][v] = res
    return out


# ------------------------------------------------------------------- report
def _pct(x: Any, d: int = 1) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:+.{d}f}%"


def render_md(rec: dict) -> str:
    L = [f"# CH-20a hedge replay -- run {rec['run_id']}", "",
         "Observations on real OptionMetrics quotes; no skill claim. Leaders chosen after the fact "
         "are not evidence of an edge. CLAIMS PROMOTED: none.", ""]
    L.append("## Verdicts (base spec; judged on terminal wealth at equal average drawdown)")
    for s, r in rec["symbols"].items():
        if r.get("status") != "OK":
            L.append(f"- **{s}**: {r.get('status')}")
            continue
        for v in VARIANTS:
            vd = r["variants"][v]["verdict"]
            L.append(f"- **{s}** [{v}]: `{vd['label']}`"
                     + (f" ({vd['twin']})" if vd.get("twin") else "")
                     + f" -- {r['variants'][v]['plain']}")
    L += ["", "## Quote-file inventory", "",
          f"Directory `{rec['inventory']['data_dir']}`; files {rec['inventory']['n_files']}; "
          f"newest underlying date **{rec['inventory']['newest_date']}**; years by symbol "
          f"{rec['inventory']['years_by_symbol']}.", "",
          "| year | quote rows | by symbol | quote dates |", "|---|---|---|---|"]
    for y in rec["inventory"]["years"]:
        L.append(f"| {y['year']} | {y.get('quote_rows')} | {y.get('quote_rows_by_symbol')} | "
                 f"{y.get('quote_dates')} |")
    L += ["", "## Frozen spec", "", f"sha256 `{rec['spec']['sha256']}`", "", "```",
          json.dumps(rec["spec"]["values"], indent=1), "```", "",
          "Variants tried: **2** (`base`, and the one pre-declared `budget` variant). No sweep.", ""]
    for s, r in rec["symbols"].items():
        if r.get("status") != "OK":
            continue
        L += [f"## {s}", "",
              f"Window {r['window'][0]} .. {r['window'][1]} ({r['end_reason']}). "
              f"Rolls **{r['n_rolls']}** (long-put-only {r['n_long_only_rolls']}: "
              f"{r['long_only_reasons']}); skipped quote days in window "
              f"**{r['skipped_quote_days_in_window']}** {r['skipped_by_reason']}; "
              f"before first roll {r['skipped_days_before_first_roll']}; splits inside a hold "
              f"{r['n_split_in_hold']}. Median DTE {r['dte_median']:.0f}, long strike "
              f"{r['long_moneyness_median']:.3f} x spot, short {r['short_moneyness_median']} x "
              f"spot, median spread debit {_pct(r['cost_pct_spot_median'], 2)} of spot. "
              f"Dividends: total minus price return {_pct(r['dividends_check']['total_return_minus_price_return_per_year'], 2)}/yr. "
              f"One contract = ${r['last_spot_contract_notional_usd']:,.0f} notional at the last "
              f"spot (a $35,000 book cannot match notional in whole contracts; fractional here).", ""]
        for v in VARIANTS:
            res = r["variants"][v]
            sc = res["scales"]
            L += [f"### {s} -- {v}", "",
                  f"Target average drawdown {_pct(sc['target_avg_drawdown'], 2)}; hold_less gross "
                  f"{sc['hold_less_gross']:.3f}; trend scale {sc['trend_scale']:.3f}; inverse weight "
                  f"{sc['inverse_weight']:.3f}; mean hedge ratio {res['mean_hedge_ratio']:.2f}; "
                  f"periods {res['n_periods']} over {res['years']:.1f} y. "
                  + (" ".join(res["notes"])), "",
                  "| construction | terminal $1 | CAGR | vol | max DD | avg DD | worst period | "
                  "worst period $35k | max DD $35k |", "|---|---|---|---|---|---|---|---|---|"]
            for k, mm in res["metrics"].items():
                L.append(f"| {k} | {mm['terminal_wealth']:.2f} | {_pct(mm['cagr'])} | "
                         f"{_pct(mm['vol_ann'])} | {_pct(mm['max_drawdown'])} | "
                         f"{_pct(mm['avg_drawdown'])} | {_pct(mm['worst_period'])} | "
                         f"${mm['worst_period_usd']:,.0f} | ${mm['max_drawdown_usd']:,.0f} |")
            L += ["", "| year | crash | hedge cost | payoff | net | hedged | unhedged | hold_less | "
                  "trend | inverse_ctrl |", "|---|---|---|---|---|---|---|---|---|---|"]
            for y in res["by_year"]:
                L.append(f"| {y['year']} | {'Y' if y['crash'] else ''} | "
                         f"{_pct(y['hedge_cost_pct_equity'])} | {_pct(y['hedge_payoff_pct_equity'])} | "
                         f"{_pct(y['hedge_net_pct_equity'])} | {_pct(y['hedged'])} | "
                         f"{_pct(y['unhedged'])} | {_pct(y['hold_less'])} | {_pct(y['trend'])} | "
                         f"{_pct(y['inverse_ctrl'])} |")
            L += ["", "| set | years | hedge cost | payoff | hedged /yr | unhedged /yr | "
                  "hold_less /yr | trend /yr | inverse_ctrl /yr |",
                  "|---|---|---|---|---|---|---|---|---|"]
            for lab, d in res["crash_vs_calm"].items():
                L.append(f"| {lab} | {len(d['years'])} | {_pct(d['hedge_cost_pct_equity'])} | "
                         f"{_pct(d['hedge_payoff_pct_equity'])} | "
                         + " | ".join(_pct(d[k]["per_year_geo"]) for k in
                                      ("hedged", "unhedged", "hold_less", "trend", "inverse_ctrl"))
                         + " |")
            L += ["", "Leave-one-year-out (terminal wealth, hedged vs twin):", ""]
            for x, lo in res["loyo"].items():
                L.append(f"- vs {x}: hedge ahead in full sample = {lo['hedge_ahead_full']}; "
                         f"ahead in {lo['hedge_ahead_in_n_of'][0]} of "
                         f"{lo['hedge_ahead_in_n_of'][1]} year-dropped samples; the drop that "
                         f"helps the twin most: {lo['worst_drop_for_hedge']['dropped']}, the drop "
                         f"that helps the hedge most: {lo['worst_drop_for_twin']['dropped']}")
            L.append("")
    L += ["## Method notes", "", *[f"- {n}" for n in rec["method_notes"]], ""]
    return "\n".join(L)


METHOD_NOTES = [
    "Fills: long put at BEST OFFER, short put at BEST BID; never the mid. Settled at intrinsic "
    "on the last session on/before expiry (PM-settled ETF options); no exit quote is used.",
    "A long leg missing or crossed skips that day (counted); the next session retries; the book "
    "is unhedged on skipped days. A missing short leg (the pull keeps best_bid > 0) buys the long "
    "put alone (counted).",
    "Roll-period grid: every construction is sampled at the hedge's settlement dates (about "
    "monthly), so vol, max drawdown, average drawdown and worst period are on that grid; "
    "intra-month drawdowns are not seen by any construction.",
    "Average drawdown = mean of (1 - equity / running peak) over the grid. Twins are scaled DOWN "
    "only (no leverage): hold_less gross and inverse weight solved on a 0.0005 grid.",
    "Cash and financing at 0% -- this handicaps hold_less and trend (their cash earns nothing), "
    "i.e. it points in the hedge's favour.",
    "Book return = OptionMetrics secprd total return (dividends in); strikes vs raw close; a "
    "split inside a hold rescales the settlement close by cfadj.",
    "Hedge cost/payoff by year are sums of per-roll fractions of equity at entry.",
    "Contracts sized to equity / (spot x 100), fractional. Inverse control is hypothetical for "
    "SMH (no -1x SMH fund exists); modelled as -1x daily total return less the stated fee.",
    "Verdict rule frozen in code (decide): a side wins only if it is ahead on terminal wealth in "
    "the full sample AND in every leave-one-year-out sample.",
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--data-dir", default=str(DEFAULT_DATA))
    ap.add_argument("--symbols", default=",".join(C.CH20A_HEDGE_SYMBOLS))
    args = ap.parse_args(argv)

    data_dir = Path(args.data_dir)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if not data_dir.exists():
        print(f"REFUSED: data dir {data_dir} does not exist")
        return 2
    n_before = len(list(data_dir.glob("*")))
    spec = frozen_spec()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print(f"CH-20a hedge replay  run {run_id}  spec {spec['sha256'][:12]}")
    print(f"live data folder file count BEFORE: {n_before}")
    inv = inventory(data_dir, SECIDS)
    print(f"inventory: {len(inv['years'])} years, newest date {inv['newest_date']}, "
          f"years by symbol {inv['years_by_symbol']}")
    for y in inv["years"]:
        print(f"  {y['year']}: quote rows {y.get('quote_rows')}  {y.get('quote_rows_by_symbol')}")
    if not any(y.get("quotes_file") and y.get("under_file") for y in inv["years"]):
        # A worktree carries only the tracked .meta.json files; the parquet lives in the
        # runtime checkout. Refuse BEFORE writing, so an empty receipt is never filed.
        print(f"REFUSED: no quotes_YYYY.parquet + under_YYYY.parquet pair in {data_dir} "
              f"(pass --data-dir to the folder that holds them)")
        return 2

    sym_res: dict[str, Any] = {}
    try:
        for sym in [s.strip() for s in args.symbols.split(",") if s.strip()]:
            if sym not in SECIDS:
                raise HedgeReplayRefused(f"unknown symbol {sym}")
            r = replay_symbol(sym, data_dir, SECIDS[sym], spec["values"])
            sym_res[sym] = r
            if r.get("status") == "OK":
                for v in VARIANTS:
                    vd = r["variants"][v]["verdict"]
                    print(f"  VERDICT {sym} [{v}]: {vd['label']} {vd.get('twin') or ''}", flush=True)
            else:
                print(f"  {sym}: {r.get('status')}", flush=True)
    except HedgeReplayRefused as exc:
        print(f"REFUSED: {exc}")
        return 3
    n_after = len(list(data_dir.glob("*")))
    print(f"live data folder file count AFTER: {n_after}")
    if n_after != n_before:
        print("REFUSED: the live data folder changed during a read-only run")
        return 4
    ok = [s for s, r in sym_res.items() if r.get("status") == "OK"]
    rec = {"run_id": run_id, "chunk": "CH-20a", "licence": "PRODUCT_EXPERIMENT (replay only)",
           "generated_at": datetime.now(timezone.utc).isoformat(), "git": _git_head(),
           "spec": spec, "inventory": inv, "variants_tried": list(VARIANTS),
           "symbols": sym_res, "method_notes": METHOD_NOTES,
           "live_folder_files": {"before": n_before, "after": n_after},
           "verdict_lines": {s: {v: sym_res[s]["variants"][v]["verdict"]["label"]
                                 + (f" ({sym_res[s]['variants'][v]['verdict']['twin']})"
                                    if sym_res[s]["variants"][v]["verdict"].get("twin") else "")
                                 for v in VARIANTS} for s in ok}}
    jp = out / f"ch20a_hedge_replay_{run_id}.json"
    jp.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    mp = out / f"ch20a_hedge_replay_{run_id}.md"
    mp.write_text(render_md(rec), encoding="utf-8")
    print(f"receipt -> {jp}\n         -> {mp}")
    if not ok:
        print("REFUSED: no symbol produced a replay")
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
