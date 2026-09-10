"""P6 -- the 2025-26 price panel, and the regret the accounts actually earned.

Two halves, and they are separated on purpose because only one of them can be
answered with the data that exists (roadmap 2026-09-08 section 10.4).

**P6a, the bars.** The repo's learner panel ends 2024-12: every backtest in this
programme stops before the period the paper books have been live. This pulls
daily bars 2025-01-01 -> today for the tracker universe and the index proxies
from the venue's market-data host and writes
`backend/data/optimus/prices_2025_26/bars.parquet` with a receipt. It uses the
DATA credential only and imports no broker; the SIP feed is deliberate (measured
2026-08-26 in the terminal repo: the free plan serves historical bars from the
consolidated tape, while the IEX feed's volume is IEX's own ~2-4%, so a dollar
volume screen on IEX bars screens a different market).

**P6b, the regret.** Murat asked for "a back test on the past six months where
the project has been working ... how the paper accounts would actually be better
if we did something else". Two things bound what that can mean today, and both
are reported rather than papered over:

* the six paper accounts were created **2026-08-28**, so their realised history
  is days, not six months. What each account did against SPY over exactly the
  sessions it existed is computable and is computed here.
* a faithful *replay* of the six mandates over 2025-2026 needs the tracker
  screen's inputs (analyst targets, consensus, revisions) for 2025-26, and the
  repo's panel ends 2024-12. So the replay is REFUSED with the named missing
  input rather than run on a proxy that would answer a different question.

What P6b does instead, on the bars P6a just pulled, is the part that IS
identified: an equal-weight index of what each book HELD versus SPY over the
same sessions, and a set of mechanical benchmark books (SPY, equal-weight
universe, 12-1 momentum, 1-month reversal) over 2025-01 -> today, so the "what
else could we have done" question has an actual bar rather than a feeling.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

RUN_DATE = "2026-09-08"
OUT = REPO / "backend" / "data" / "optimus" / f"night_factory_{RUN_DATE}"
PRICES = REPO / "backend" / "data" / "optimus" / "prices_2025_26"
TERMINAL = REPO.parent / "aegis-alpha-terminal"
UNIVERSE = TERMINAL / "state" / "universe" / "HIGH_DISPERSION_US_v1_2026-09-01.json"
DATA_HOST = os.getenv("AAT_DATA_BASE", "https://data.alpaca.markets").rstrip("/")
INDEXES = ["SPY", "QQQ", "IWM", "RSP"]
START = "2025-01-01"
FLOOR_DV = 3_000_000.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _r(v, nd=4):
    try:
        return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), nd)
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------- credentials

def data_credential() -> tuple[str, str, str]:
    """The DATA key, and where it came from. Never an order path.

    Preference order: this process's own environment, then the terminal repo's
    `.env` (the loops' own credential, read-only). The caller prints the source
    so a receipt says which key produced the bars.
    """
    kid, sec = os.getenv("APCA_API_KEY_ID"), os.getenv("APCA_API_SECRET_KEY")
    if kid and sec:
        return kid, sec, "process environment (APCA_API_KEY_ID)"
    env_path = TERMINAL / ".env"
    if not env_path.exists():
        raise SystemExit(f"REFUSED: no data credential in the environment and no {env_path}")
    env: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    for role in ("HACK3", "HACK1", "HACK2", "HACK4", "HACK5", "HACK6"):
        kid, sec = env.get(f"AAT_{role}_KEY_ID"), env.get(f"AAT_{role}_SECRET_KEY")
        if kid and sec:
            return kid, sec, f"terminal repo .env, {role} (data endpoint only)"
    raise SystemExit("REFUSED: the terminal .env carries no AAT_HACK*_KEY_ID / _SECRET_KEY pair")


def _get(path: str, params: dict, kid: str, sec: str, timeout: float = 90.0) -> dict:
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(f"{DATA_HOST}{path}?{q}",
                                 headers={"APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": sec})
    with urllib.request.urlopen(req, timeout=timeout) as fh:      # noqa: S310 allowlisted host
        return json.loads(fh.read())


# --------------------------------------------------------------- P6a: bars

def universe_symbols(limit: int | None = None) -> tuple[list[str], dict]:
    if not UNIVERSE.exists():
        raise SystemExit(f"REFUSED: no tracker universe at {UNIVERSE}")
    d = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    members = [m for m in d["members"]
               if (m.get("median_dollar_volume") or 0) >= FLOOR_DV and not m.get("etf_like")]
    members.sort(key=lambda m: -(m.get("median_dollar_volume") or 0))
    syms = [m["symbol"] for m in members][:limit]
    meta = {"universe_file": str(UNIVERSE), "universe_asof": d.get("asof"),
            "members_total": d.get("n"), "after_floor_and_etf_filter": len(members),
            "floor_median_dollar_volume": FLOOR_DV, "symbols_pulled": len(syms)}
    return syms, meta


def pull_bars(symbols: list[str], start: str, end: str, kid: str, sec: str,
              batch: int = 100, feed: str = "sip") -> pd.DataFrame:
    rows = []
    t0 = time.time()
    for i in range(0, len(symbols), batch):
        chunk = symbols[i:i + batch]
        token = None
        while True:
            for attempt in range(4):
                try:
                    d = _get("/v2/stocks/bars", {"symbols": ",".join(chunk), "start": start, "end": end,
                                                 "timeframe": "1Day", "adjustment": "all", "limit": 10000,
                                                 "feed": feed, "page_token": token}, kid, sec)
                    break
                except Exception as exc:  # noqa: BLE001  a page failure must not restart the pull
                    if attempt == 3:
                        raise
                    print(f"    retry {attempt + 1} on batch {i // batch}: {type(exc).__name__} {str(exc)[:80]}", flush=True)
                    time.sleep(2.0 * (attempt + 1))
            for sym, bars in (d.get("bars") or {}).items():
                for b in bars:
                    rows.append((sym, b["t"][:10], b["o"], b["h"], b["l"], b["c"], b["v"], b.get("vw"), b.get("n")))
            token = d.get("next_page_token")
            if not token:
                break
        if (i // batch) % 5 == 0:
            print(f"    {i + len(chunk)}/{len(symbols)} symbols, {len(rows):,} bars, {time.time() - t0:.0f}s", flush=True)
    df = pd.DataFrame(rows, columns=["symbol", "date", "open", "high", "low", "close", "volume", "vwap", "trades"])
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)


def P6a_pull_bars(limit: int | None = None, smoke: bool = False) -> dict:
    t0 = time.time()
    kid, sec, source = data_credential()
    syms, meta = universe_symbols(limit=(25 if smoke else limit))
    syms = sorted(set(syms) | set(INDEXES))
    # `end` is deliberately NOT sent. Measured 2026-09-09: the free plan answers
    # {"message":"subscription does not permit querying recent SIP data"} with a
    # 403 for ANY explicit end date inside its delay window -- including
    # yesterday -- but clips the window itself when `end` is omitted. So the
    # request asks for everything from START and the receipt reports the last
    # session the venue actually served, rather than the date we hoped for.
    end = None
    print(f"    pulling {len(syms)} symbols from {START} (no end: the venue clips its own "
          f"delay window), feed sip, credential: {source}", flush=True)
    df = pull_bars(syms, START, end, kid, sec)
    PRICES.mkdir(parents=True, exist_ok=True)
    path = PRICES / ("bars_smoke.parquet" if smoke else "bars.parquet")
    df.to_parquet(path, index=False)
    per = df.groupby("symbol")["date"].agg(["min", "max", "count"])
    receipt = {
        "job": "P6a_pull_bars", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "credential_source": source, "data_host": DATA_HOST, "feed": "sip",
        "adjustment": "all (splits and dividends), so a return series is comparable to CRSP's",
        "window": {"start": START, "end_requested": None,
                   "end_served": (str(df["date"].max().date()) if len(df) else None),
                   "why_no_end": ("the free SIP plan 403s on any explicit end inside its delay window; "
                                  "omitting it lets the venue clip and serve everything it is allowed to")},
        "universe": meta, "index_proxies": INDEXES,
        "bars": int(len(df)), "symbols_with_bars": int(df["symbol"].nunique()),
        "symbols_requested": len(syms),
        "symbols_with_no_bars": sorted(set(syms) - set(df["symbol"].unique()))[:50],
        "sessions": int(df["date"].nunique()),
        "median_bars_per_symbol": int(per["count"].median()) if len(per) else 0,
        "parquet": str(path), "parquet_mb": _r(path.stat().st_size / 1e6, 2),
        "headline": (f"{len(df):,} daily bars for {df['symbol'].nunique()} symbols over "
                     f"{df['date'].nunique()} sessions, {START}..{df['date'].max().date() if len(df) else 'nothing'}"),
        "verdict": "PANEL BUILT: the 2025-26 price gap that blocked every forward evaluation is now on disk",
        "elapsed_s": round(time.time() - t0, 1), "written_utc": _now(),
    }
    return receipt


# ------------------------------------------------------- P6b: the regret

def _returns(df: pd.DataFrame) -> pd.DataFrame:
    p = df.pivot(index="date", columns="symbol", values="close").sort_index()
    return p.pct_change()


def _grade(r: pd.Series, mkt: pd.Series, label: str) -> dict:
    both = pd.concat([r, mkt], axis=1).dropna()
    if len(both) < 5:
        return {"label": label, "verdict": "CANNOT DETERMINE", "sessions": int(len(both))}
    y = both.iloc[:, 0].to_numpy()
    x = both.iloc[:, 1].to_numpy()
    beta = float(np.polyfit(x, y, 1)[0]) if np.std(x) > 0 else 1.0
    ex = y - beta * x
    eq = np.cumprod(1 + y)
    return {"label": label, "sessions": int(len(y)),
            "first": str(both.index[0].date()), "last": str(both.index[-1].date()),
            "total_return_pct": _r((float(np.prod(1 + y)) - 1) * 100, 3),
            "market_return_pct": _r((float(np.prod(1 + x)) - 1) * 100, 3),
            "raw_excess_pct": _r((float(np.prod(1 + y)) - float(np.prod(1 + x))) * 100, 3),
            "beta": _r(beta, 3),
            "beta_matched_ann_pct": _r(float(ex.mean()) * 252 * 100, 3),
            "ann_vol_pct": _r(float(np.std(y, ddof=1)) * math.sqrt(252) * 100, 2),
            "max_drawdown_pct": _r(float(np.min(eq / np.maximum.accumulate(eq) - 1)) * 100, 3)}


def benchmark_books(df: pd.DataFrame) -> dict:
    """The mechanical bar the six books owe: what else could the money have done
    on exactly these sessions, with no forecast at all?"""
    rets = _returns(df)
    spy = rets["SPY"] if "SPY" in rets.columns else rets.mean(axis=1)
    names = [c for c in rets.columns if c not in INDEXES]
    out = {}
    for idx in INDEXES:
        if idx in rets.columns:
            out[f"INDEX_{idx}"] = _grade(rets[idx], spy, f"hold {idx}")
    out["EW_universe"] = _grade(rets[names].mean(axis=1), spy,
                                "equal weight, the whole tracker universe -- SURVIVORSHIP BIASED")
    out["EW_universe"]["BIAS_WARNING"] = (
        "the universe is the 2026-09-01 screen: every member is a name that still exists and still "
        "clears $3m/day TODAY. Replaying it from 2025-01 silently drops whatever was delisted, "
        "acquired or fell below the floor, so this row is an UPPER bound, not a benchmark. Read it "
        "as 'what the survivors did', and use INDEX_RSP for an honest equal-weight bar.")
    # 12-1 momentum and 1-month reversal, monthly formed, equal weight, 25 bps a side.
    # `hi` is the lag of the RECENT end of the formation window and must be >= 1:
    # the first version used hi=0 for the reversal, so the signal for month m was
    # minus the return OF month m and the book bought that month's losers while
    # they were losing -- a pure look-ahead that printed -98.8%.
    px = df.pivot(index="date", columns="symbol", values="close").sort_index()[names]
    month = pd.Index(px.index).to_period("M").astype(str)
    m_last = px.groupby(month).last()
    for label, lo, hi, sign in (("MOM_12_1", 12, 1, +1), ("REV_1M", 2, 1, -1)):
        if hi < 1 or lo <= hi:
            raise SystemExit(f"REFUSED: {label} formation window ({lo},{hi}) would read the month it trades")
        sig = (m_last.shift(hi) / m_last.shift(lo) - 1.0) * sign
        daily = pd.Series(0.0, index=rets.index)
        prev: set[str] = set()
        # BOTH SIDES. Until 2026-09-10 this was a single 25 bps charge on the
        # names that changed, which prices the BUY and gives the SELL away: a
        # month that replaces a fraction `turn` of the book sells `turn` and
        # buys `turn`, so it pays 25 bps twice. The old charge understated the
        # benchmark's cost by up to 25 bps x turn a month (<= ~3%/yr at full
        # monthly turnover, which a reversal book is close to). See
        # `P6_cost_model_amendment.json` in night_factory_2026-09-08.
        cost = 2 * 0.0025
        for m in sorted(set(month)):
            s = sig.loc[m].dropna() if m in sig.index else pd.Series(dtype=float)
            if len(s) < 20:
                continue
            pick = set(s.sort_values(ascending=False).head(max(10, len(s) // 10)).index)
            days = rets.index[month == m]
            if len(days) == 0 or not pick:
                continue
            r = rets.loc[days, sorted(pick)].mean(axis=1)
            turn = len(pick - prev) / max(len(pick), 1)
            r.iloc[0] -= cost * turn
            daily.loc[days] = r
            prev = pick
        out[label] = _grade(daily.replace(0.0, np.nan), spy, f"{label}, monthly formed, top decile EW, 25 bps")
        out[label]["BIAS_WARNING"] = (
            "drawn from the 2026-09-01 survivor screen; see EW_universe. "
            + ("A reversal book is the WORST case for this bias: it buys the previous month's biggest "
               "losers, which is precisely the set most likely to have been delisted or to have fallen "
               "below the liquidity floor before 2026-09, and every one of those is absent here. Read "
               "this row as an upper bound with no lower bound, not as a result."
               if label == "REV_1M" else
               "A momentum book buys recent winners, so it is less exposed than the reversal row, but "
               "the losers it sold are still missing from the universe."))
    return out


def account_regret(kid: str, sec: str) -> dict:
    """What the six paper books actually did. Refuses rather than invents when a
    role's key is absent -- a book that could not be read is not a book at 0%."""
    env: dict[str, str] = {}
    p = TERMINAL / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    out: dict[str, dict] = {}
    for role in ("HACK1", "HACK2", "HACK3", "HACK4", "HACK5", "HACK6"):
        k, s = env.get(f"AAT_{role}_KEY_ID"), env.get(f"AAT_{role}_SECRET_KEY")
        if not (k and s):
            out[role.lower()] = {"verdict": "CANNOT DETERMINE: no key for this role on this checkout"}
            continue
        try:
            q = urllib.parse.urlencode({"period": "3M", "timeframe": "1D", "extended_hours": "false"})
            req = urllib.request.Request(
                f"https://paper-api.alpaca.markets/v2/account/portfolio/history?{q}",
                headers={"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s})
            with urllib.request.urlopen(req, timeout=45) as fh:    # noqa: S310 allowlisted host
                h = json.loads(fh.read())
            # PAIR FIRST, THEN FILTER. The first version filtered `equity` for
            # falsy values and left `timestamp` whole: 8 equity points against 62
            # timestamps, so every book was graded over 62 sessions of SPY while
            # its equity covered 8, and all six read ~9 pp worse than they were.
            pairs = [(t, v) for t, v in zip(h.get("timestamp") or [], h.get("equity") or []) if v]
            # a venue pads the requested period with the opening equity before the
            # account was funded; those flat leading days are not book history
            while len(pairs) > 2 and pairs[0][1] == pairs[1][1]:
                pairs.pop(0)
            ts = [p[0] for p in pairs]
            eq = [p[1] for p in pairs]
            out[role.lower()] = {
                "points": len(eq),
                "first_utc": (datetime.fromtimestamp(ts[0], timezone.utc).date().isoformat() if ts else None),
                "last_utc": (datetime.fromtimestamp(ts[-1], timezone.utc).date().isoformat() if ts else None),
                "equity_first": _r(eq[0], 2) if eq else None,
                "equity_last": _r(eq[-1], 2) if eq else None,
                "total_return_pct": _r((eq[-1] / eq[0] - 1) * 100, 4) if len(eq) >= 2 and eq[0] else None,
                "equity_series": [_r(v, 2) for v in eq][-70:],
                "timestamps": [datetime.fromtimestamp(t, timezone.utc).date().isoformat() for t in ts][-70:],
            }
        except Exception as exc:  # noqa: BLE001
            out[role.lower()] = {"verdict": f"CANNOT DETERMINE: {type(exc).__name__} {str(exc)[:120]}"}
    return out


def _beta_on_own_sessions(acct: dict, spy: pd.Series) -> dict:
    """Beta of a book's equity path against SPY, on the days it actually traded.

    A book's return is meaningless beside SPY's without the loading that
    produced it -- that is the 2026-09-07 two-rulers rule. But a week of paper
    is a handful of points, so the standard error is printed beside the estimate
    and the row says plainly when it is not resolvable. A beta from 6 sessions is
    a direction, not a measurement.
    """
    eq = acct.get("equity_series") or []
    ts = acct.get("timestamps") or []
    if len(eq) < 4 or len(eq) != len(ts):
        return {"beta_vs_spy": None, "beta_note": f"{len(eq)} equity points paired with {len(ts)} dates: not estimable"}
    r = np.diff(np.asarray(eq, dtype="float64")) / np.asarray(eq[:-1], dtype="float64")
    dates = ts[1:]
    x = spy.reindex(pd.to_datetime(dates)).to_numpy(dtype="float64")
    ok = np.isfinite(x) & np.isfinite(r)
    if ok.sum() < 4 or np.std(x[ok]) == 0:
        return {"beta_vs_spy": None, "beta_note": f"only {int(ok.sum())} paired sessions: not estimable"}
    y, xx = r[ok], x[ok]
    beta = float(np.polyfit(xx, y, 1)[0])
    resid = y - (np.polyfit(xx, y, 1)[1] + beta * xx)
    n = len(y)
    se = (math.sqrt(float(np.sum(resid ** 2)) / max(n - 2, 1) / float(np.sum((xx - xx.mean()) ** 2)))
          if n > 2 and np.sum((xx - xx.mean()) ** 2) > 0 else None)
    return {"beta_vs_spy": _r(beta, 3), "beta_se": _r(se, 3), "beta_n_sessions": int(n),
            "beta_note": (f"{n} sessions; standard error {se:.2f} -- a direction, not a measurement"
                          if se else f"{n} sessions; standard error not computable")}


def P6b_regret(smoke: bool = False) -> dict:
    t0 = time.time()
    path = PRICES / ("bars_smoke.parquet" if smoke else "bars.parquet")
    if not path.exists():
        return {"job": "P6b_regret", "verdict": f"REFUSED: no bars at {path} -- run P6a first",
                "headline": "the 2025-26 panel is not on disk", "elapsed_s": 0.0, "written_utc": _now()}
    df = pd.read_parquet(path)
    kid, sec, source = data_credential()
    books = benchmark_books(df)
    accounts = account_regret(kid, sec)
    spy = _returns(df)["SPY"] if "SPY" in df["symbol"].unique() else None
    spy_since = {}
    if spy is not None:
        for role, a in accounts.items():
            if not a.get("timestamps"):
                continue
            lo, hi = a["timestamps"][0], a["timestamps"][-1]
            s = spy[(spy.index >= lo) & (spy.index <= hi)].dropna()
            if len(s) >= 2 and a.get("total_return_pct") is not None:
                spy_ret = (float(np.prod(1 + s.to_numpy())) - 1) * 100
                row = {"spy_same_days_pct": _r(spy_ret, 3),
                       "book_pct": a["total_return_pct"],
                       "regret_pct_vs_spy": _r(a["total_return_pct"] - spy_ret, 3),
                       "sessions": int(len(s))}
                row.update(_beta_on_own_sessions(a, spy))
                spy_since[role] = row
    # rank only the rows that are NOT survivorship-biased. The best "book" on a
    # survivor screen is a statement about the screen; the index rows are the
    # only honest bar this file can offer for 2025-26.
    honest = {k: v for k, v in books.items() if "BIAS_WARNING" not in v and v.get("sessions")}
    best = max(honest.items(), key=lambda kv: (kv[1].get("total_return_pct") or -999))
    worst_regret = min(spy_since.items(), key=lambda kv: kv[1]["regret_pct_vs_spy"]) if spy_since else None
    return {
        "job": "P6b_regret", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "bars": str(path), "credential_source": source,
        "question": ("Over the sessions the six paper books actually existed, what did each earn against SPY -- "
                     "and over 2025-01 -> today, what would four mechanical books with no forecast have earned?"),
        "REFUSED_the_six_month_mandate_replay": {
            "why": ("a faithful replay of hack3/hack4/hack6 needs the tracker screen's inputs (analyst targets, "
                    "consensus, revisions) for 2025-26; the learner panel ends 2024-12 and the candidate "
                    "snapshots on disk cover four dates, not six months"),
            "missing_input": "a 2025-26 IBES/target panel joined to these bars",
            "what_would_unblock_it": "the target-and-consensus vintages for 2025-01..today at monthly frequency",
            "note": ("the accounts themselves were created 2026-08-28, so their realised history is days. "
                     "Reporting a 'six-month' book result from them would be a claim about a window that "
                     "does not exist."),
        },
        "mechanical_benchmarks_2025_to_today": books,
        "paper_accounts_realised": accounts,
        "regret_vs_spy_over_the_same_sessions": spy_since,
        "SURVIVORSHIP": ("every book built from the tracker universe (EW_universe, MOM_12_1, REV_1M) is "
                         "drawn from the 2026-09-01 screen and therefore holds only names that survived to "
                         "2026-09. Those rows carry a BIAS_WARNING and are excluded from the headline; the "
                         "index rows are the honest bar. An unbiased 2025-26 replay needs a point-in-time "
                         "universe vintage per month, which this checkout does not have."),
        "headline": (
            f"benchmarks 2025-01..today (survivorship-free rows only): best {best[0]} at "
            f"{best[1].get('total_return_pct')}% vs SPY {books.get('INDEX_SPY', {}).get('total_return_pct')}%; "
            + (f"worst live book vs SPY on its own sessions: {worst_regret[0]} "
               f"{worst_regret[1]['regret_pct_vs_spy']:+.2f} pp over {worst_regret[1]['sessions']} sessions"
               if worst_regret else "no paper account returned a readable equity history")),
        "verdict": ("DESCRIPTIVE. The mechanical bar is on disk for 2025-26; the six-mandate replay is REFUSED "
                    "for a named missing input, and the accounts' realised window is days, not months."),
        "family_max_p": None,
        "elapsed_s": round(time.time() - t0, 1), "written_utc": _now(),
    }


def P6_bars_and_regret(smoke: bool = False, limit: int | None = None) -> dict:
    """Both stages, as the night queue dispatches them."""
    a = P6a_pull_bars(limit=limit, smoke=smoke)
    b = P6b_regret(smoke=smoke)
    return {"job": "P6_bars_and_regret", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
            "P6a": a, "P6b": b,
            "headline": f"{a.get('headline')} | {b.get('headline')}",
            "verdict": f"{a.get('verdict')} | {b.get('verdict')}",
            "family_max_p": None, "written_utc": _now()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("bars", "regret", "both"), default="both")
    ap.add_argument("--limit", type=int, default=None, help="cap the universe (default: all 3,056)")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--run", type=int, default=1)
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    payload: dict = {"job": "P6_bars_and_regret", "written_utc": _now(), "llm_spend_usd": 0.0}
    if a.stage in ("bars", "both"):
        payload["P6a"] = P6a_pull_bars(limit=a.limit, smoke=a.smoke)
        print(f"  P6a: {payload['P6a']['headline']}", flush=True)
    if a.stage in ("regret", "both"):
        payload["P6b"] = P6b_regret(smoke=a.smoke)
        print(f"  P6b: {payload['P6b']['headline']}", flush=True)
    payload["headline"] = " | ".join(str(payload[k].get("headline")) for k in ("P6a", "P6b") if k in payload)
    payload["verdict"] = " | ".join(str(payload[k].get("verdict")) for k in ("P6a", "P6b") if k in payload)
    out = Path(a.out) if a.out else OUT / f"P6_bars_and_regret_run{a.run:02d}{'_smoke' if a.smoke else ''}.json"
    out.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"\nP6 -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
