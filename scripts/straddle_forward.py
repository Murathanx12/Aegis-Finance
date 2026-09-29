"""TRIAL-STRADDLE-FWD-1 runner: the forward, $0, paper-only straddle log.

    python -m scripts.straddle_forward                     # the scheduled pass (grade; enter if in the window)
    python -m scripts.straddle_forward --dry-run           # quotes now, labelled DRY_RUN_NOT_AN_ENTRY; no frozen row
    python -m scripts.straddle_forward --dry-run --limit 40
    python -m scripts.straddle_forward --grade             # grade what has expired + print book vs twin
    python -m scripts.straddle_forward --freeze-contract   # freeze contract_v1.json (refuses a changed body)
    python -m scripts.straddle_forward --status
    python -m scripts.straddle_forward --schtasks          # print the AegisStraddleForward registration

PRODUCT_EXPERIMENT. No broker, no orders, no LLM. yfinance chains (free, delayed ~15 min).

THE SCHEDULED PASS (every 30 minutes, windowless via pythonw, log in
`backend/data/optimus/straddle_forward/straddle_forward.log`):
1. STOP file present -> exit with a STOPPED receipt.
2. Grade every frozen straddle whose expiry close is in the bars file.
3. If now is inside the ENTRY window (10:45-15:30 America/New_York, an XNYS session) and
   this session has no frozen entry and no observation yet:
   * a standard monthly expiry 21-35 calendar days out exists -> ENTRY (frozen, hash-chained);
   * none exists (about half the days: monthlies are 28-35 days apart) -> OBSERVE_ONLY
     snapshot on the nearest monthly (cost and coverage data; never graded, never an entry).

STOP: create `backend/data/optimus/straddle_forward/STOP`.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                                   # noqa: E402
from backend.services import straddle_forward as SF                  # noqa: E402

TASK_NAME = "AegisStraddleForward"
ROOT = SF.ROOT
STOP = ROOT / "STOP"
LOG = ROOT / "straddle_forward.log"
LOCK = ROOT / "run.lock"
RUNS = ROOT / "runs"
OBS = ROOT / "observations"
EARN_CACHE = ROOT / "earnings_cache.json"
BARS = REPO / "backend" / "data" / "optimus" / "prices_2025_26" / "bars.parquet"
EARN_CACHE_DAYS = 7
N_THREADS = 4
HISTORY_SESSIONS = 300


def _ensure_streams() -> None:
    """pythonw gives None for stdout/stderr (a windowless process has no stdout)."""
    if sys.stdout is None or sys.stderr is None:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        fh = open(LOG, "a", encoding="utf-8")                        # noqa: SIM115
        if sys.stdout is None:
            sys.stdout = fh
        if sys.stderr is None:
            sys.stderr = fh
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")          # type: ignore[union-attr]
        except Exception:                                            # noqa: BLE001
            pass


def _p(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}] {msg}", flush=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp() -> str:
    return _now().strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=_json_default), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    tmp.replace(path)


def _json_default(o):
    if isinstance(o, (np.floating,)):
        v = float(o)
        return v if math.isfinite(v) else None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp, datetime, date)):
        return o.isoformat()
    return str(o)


def _clean(o):
    """NaN / inf -> None, numpy -> python, recursively (frozen rows are canonical JSON)."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        v = float(o)
        return v if math.isfinite(v) else None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp, datetime, date)):
        return o.isoformat()
    return o


class RunLock:
    """One run at a time; a lock older than 2 h is a dead run's and is taken over."""

    def __enter__(self):
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 7200:
            raise RuntimeError(f"another run holds {LOCK.name} (pid {LOCK.read_text(encoding='utf-8')[:20]})")
        LOCK.write_text(str(os.getpid()), encoding="utf-8")
        return self

    def __exit__(self, *a):
        try:
            LOCK.unlink()
        except OSError:
            pass


# ═════════════════════════ bars + universe ════════════════════════════════════

def load_bars() -> dict:
    b = pd.read_parquet(BARS, columns=["symbol", "date", "close", "volume"])
    b["date"] = pd.to_datetime(b["date"]).dt.normalize()
    dates = np.sort(b["date"].unique())[-HISTORY_SESSIONS:]
    b = b[b["date"].isin(dates)]
    close = b.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").sort_index()
    dv = (b.assign(dv=b["close"] * b["volume"])
          .pivot_table(index="date", columns="symbol", values="dv", aggfunc="last").sort_index())
    return {"close": close, "dv": dv, "newest": pd.Timestamp(close.index[-1]).date(), "rows": int(len(b))}


def _etf_set() -> set:
    s = set(getattr(_cfg, "BOOK_KNOWN_ETFS", ())) | set(getattr(_cfg, "THEME_ETF_MAP", {}).values())
    s |= {"SPY", "QQQ", "IWM", "RSP", "DIA", "VTI", "VOO", "SMH", "USMV", "MTUM", "VLUE", "QUAL", "URTH"}
    try:
        from backend.services import xs_ranker as XR
        s |= set(XR.INDEX_PROXIES)
    except Exception:                                                # noqa: BLE001
        pass
    return s


def universe(bars: dict, n: int = SF.N_CANDIDATES) -> list:
    """The top-n names by 63-session median dollar volume at the decision close, price >=
    MIN_PRICE, known ETFs / index proxies excluded (the chain's quoteType removes the
    rest: a non-EQUITY underlying is refused NOT_EQUITY)."""
    c, dv = bars["close"], bars["dv"]
    last = c.iloc[-1]
    mdv = dv.iloc[-63:].median()
    ok = last.notna() & (last >= SF.MIN_PRICE) & mdv.notna() & (c.iloc[-63:].notna().sum() >= 60)
    etf = _etf_set()
    names = [s for s in mdv[ok].sort_values(ascending=False).index if s not in etf and "/" not in s]
    return names[:n]


def yf_symbol(s: str) -> str:
    return s.replace(".", "-")


# ═════════════════════════ network: chains + earnings ═════════════════════════

def load_earn_cache() -> dict:
    try:
        return json.loads(EARN_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def fetch_past_reports(sym: str, cache: dict, now: datetime) -> tuple:
    """Report dates (ET calendar dates) strictly BEFORE the pull time, from yfinance's
    earnings calendar. The future (scheduled) row is discarded here and never stored."""
    ent = cache.get(sym)
    if ent and (now - pd.Timestamp(ent["pulled_utc"]).to_pydatetime()).days < EARN_CACHE_DAYS:
        return ent["dates"], "cache"
    import yfinance as yf
    try:
        e = yf.Ticker(yf_symbol(sym)).get_earnings_dates(limit=12)
    except Exception as exc:                                         # noqa: BLE001
        return (ent["dates"] if ent else []), f"error:{type(exc).__name__}"
    dates = []
    if e is not None and len(e):
        for ts in e.index:
            t = pd.Timestamp(ts)
            t = t.tz_localize("America/New_York") if t.tzinfo is None else t
            if t.tz_convert("UTC") < pd.Timestamp(now):
                dates.append(t.tz_convert("America/New_York").date().isoformat())
    cache[sym] = {"pulled_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "dates": sorted(set(dates))}
    return cache[sym]["dates"], "yfinance"


def fetch_chain(sym: str, expiry: date) -> dict:
    """One name's chain at `expiry` + the underlying quote the options endpoint returns."""
    import yfinance as yf
    t = yf.Ticker(yf_symbol(sym))
    out = {"symbol": sym, "fetched_utc": _now().isoformat()}
    try:
        exps = list(t.options or [])
    except Exception as exc:                                         # noqa: BLE001
        out["error"] = f"OPTIONS_LIST_ERROR:{type(exc).__name__}"
        return out
    if expiry.isoformat() not in exps:
        out["error"] = "NO_TARGET_EXPIRY" if exps else "NO_OPTIONS"
        return out
    try:
        oc = t.option_chain(expiry.isoformat())
    except Exception as exc:                                         # noqa: BLE001
        out["error"] = f"CHAIN_ERROR:{type(exc).__name__}"
        return out
    und = getattr(oc, "underlying", None) or {}
    out["calls"], out["puts"] = oc.calls, oc.puts
    out["quote_type"] = und.get("quoteType")
    out["market_state"] = und.get("marketState")
    out["spot"] = und.get("regularMarketPrice")
    rmt = und.get("regularMarketTime")
    out["spot_time_utc"] = (datetime.fromtimestamp(float(rmt), tz=timezone.utc).isoformat()
                            if rmt is not None else None)
    out["quote_source"] = und.get("quoteSourceName")
    out["fetched_utc"] = _now().isoformat()
    return out


# ═════════════════════════ one snapshot (entry / observation / dry run) ═════════

def snapshot(*, mode: str, expiry: date, limit: int | None = None) -> dict:
    """Quotes + forecasts + ranks for the universe at `expiry`. Pure except the network."""
    now = _now()
    today_et = SF.to_et(now).date()
    bars = load_bars()
    model = SF.load_model()
    names = universe(bars)
    if limit:
        names = names[:limit]
    in_session = SF.entry_window(now)["in_window"]            # enforce underlying freshness in-session
    cache = load_earn_cache()
    t0 = time.time()

    def work(sym):
        rep, src = fetch_past_reports(sym, cache, now)
        ch = fetch_chain(sym, expiry)
        return sym, rep, src, ch

    with ThreadPoolExecutor(max_workers=N_THREADS) as ex:
        got = list(ex.map(work, names))
    _write_json(EARN_CACHE, cache)
    fetch_s = round(time.time() - t0, 1)
    reports = {s: r for s, r, _, _ in got}
    earn_src = pd.Series([src.split(":")[0] for _, _, src, _ in got]).value_counts().to_dict()
    feats = SF.live_features(bars["close"][names], bars["dv"][names], bars["close"]["SPY"], reports,
                             entry=today_et, window_end=expiry)
    feats["f_ridge"] = SF.apply_model(model, feats)
    feats["f_vol"] = SF.vol_forecast(feats["vol_63"])
    n_sess = SF.sessions_between(today_et, expiry)
    scale = math.sqrt(max(n_sess, 1) / SF.H)
    rows, straddles = {}, []
    for sym, _, src, ch in got:
        if "error" in ch:
            s = SF.Straddle(symbol=sym, ok=False, reasons=[ch["error"]])
        elif ch.get("quote_type") not in (None, "EQUITY"):
            s = SF.Straddle(symbol=sym, ok=False, reasons=[f"NOT_EQUITY:{ch.get('quote_type')}"])
        else:
            s = SF.build_straddle(sym, ch["calls"], ch["puts"], spot=SF._num(ch.get("spot")),
                                  spot_time_utc=ch.get("spot_time_utc"), now_utc=pd.Timestamp(ch["fetched_utc"]),
                                  expiry=expiry, in_session=in_session)
        straddles.append(s)
        fr = feats.loc[sym]
        row = {"kind": "NAME", "symbol": sym, "ok": s.ok, "reasons": s.reasons,
               "quote_utc": ch.get("fetched_utc"), "market_state": ch.get("market_state"),
               "quote_source": ch.get("quote_source"), "earnings_source": src.split(":")[0],
               "close_decision": float(bars["close"][sym].iloc[-1]),
               "features": {k: fr[k] for k in model["feature_order"]} | {
                   "median_dollar_vol": fr["median_dollar_vol"], "n_earn_done": fr["n_earn_done"],
                   "last_known_report": fr["last_known_report"]},
               "f_ridge": fr["f_ridge"], "f_vol": fr["f_vol"], "horizon_scale": scale}
        row.update({k: v for k, v in s.fields.items()})
        if s.fields.get("implied_move"):
            im = s.fields["implied_move"]
            row["gap_ridge"] = math.log(fr["f_ridge"] * scale / im) if fr["f_ridge"] > 0 else None
            row["gap_vol"] = (math.log(fr["f_vol"] * scale / im)
                              if np.isfinite(fr["f_vol"]) and fr["f_vol"] > 0 else None)
        rows[sym] = row
    usable = pd.DataFrame({s: {"f_ridge": r["f_ridge"], "f_vol": r["f_vol"], "implied_move": r.get("implied_move"),
                               "horizon_scale": scale} for s, r in rows.items() if r["ok"]}).T
    books = []
    for sel, col in (("ridge", "f_ridge"), ("vol", "f_vol")):
        for b in SF.BREADTHS:
            legs = SF.rank_legs(usable, col, int(b)) if len(usable) else None
            books.append({"kind": "BOOK", "selector": sel, "breadth": int(b), "expiry": expiry.isoformat(),
                          "status": "OK" if legs else f"SKIPPED: {len(usable)} usable < {2 * int(b) + 10}",
                          "long": legs["long"] if legs else [], "short": legs["short"] if legs else [],
                          "n_usable": int(len(usable)), "gap_long_min": legs["gap_long_min"] if legs else None,
                          "gap_short_max": legs["gap_short_max"] if legs else None,
                          "written_utc": _now().isoformat()})
    spreads_all = [r["straddle_rel_spread"] for r in rows.values() if r.get("straddle_rel_spread") is not None]
    spreads_ok = [r["straddle_rel_spread"] for r in rows.values() if r["ok"]]
    overlap = {}
    for b in SF.BREADTHS:
        br = [x for x in books if x["breadth"] == int(b)]
        r_, v_ = (next(x for x in br if x["selector"] == "ridge"), next(x for x in br if x["selector"] == "vol"))
        if r_["long"]:
            overlap[str(b)] = {"long_shared": len(set(r_["long"]) & set(v_["long"])),
                               "short_shared": len(set(r_["short"]) & set(v_["short"]))}
    worst = {}
    for b in SF.BREADTHS:
        rb = next(x for x in books if x["selector"] == "ridge" and x["breadth"] == int(b))
        if rb["short"]:
            worst[str(b)] = SF.short_leg_worst_case([rows[s] for s in rb["short"]])
    summary = {"mode": mode, "trial": SF.TRIAL_ID, "now_utc": now.isoformat(), "now_et": SF.to_et(now).isoformat(),
               "entry_session_et": today_et.isoformat(), "decision_close": bars["newest"].isoformat(),
               "expiry": expiry.isoformat(), "calendar_dte": (expiry - today_et).days,
               "sessions_to_expiry": n_sess, "horizon_scale": scale,
               "n_candidates": len(names), "n_usable": int(sum(r["ok"] for r in rows.values())),
               "refusals": SF.refusal_counts(straddles),
               "median_straddle_spread_all_quoted": float(np.median(spreads_all)) if spreads_all else None,
               "median_straddle_spread_usable": float(np.median(spreads_ok)) if spreads_ok else None,
               "p90_straddle_spread_usable": float(np.quantile(spreads_ok, 0.9)) if spreads_ok else None,
               "median_iv_atm_usable": float(np.median([r["iv_atm"] for r in rows.values() if r["ok"]]))
               if spreads_ok else None,
               "median_implied_move_usable": float(np.median([r["implied_move"] for r in rows.values() if r["ok"]]))
               if spreads_ok else None,
               "median_f_ridge_scaled": float(np.median([r["f_ridge"] * scale for r in rows.values() if r["ok"]]))
               if spreads_ok else None,
               "ridge_vs_vol_leg_overlap": overlap,
               "earnings_sources": earn_src, "future_reports_dropped": feats.attrs.get("future_reports_dropped"),
               "model_sha": model["model_sha"], "code_sha": SF.file_sha(Path(SF.__file__)),
               "runner_sha": SF.file_sha(Path(__file__)), "fetch_seconds": fetch_s,
               "bars_rows_read": bars["rows"], "short_leg_worst_case_ridge": worst,
               "market_state_counts": pd.Series([r.get("market_state") for r in rows.values()]).value_counts()
               .to_dict()}
    return {"summary": _clean(summary), "names": [_clean(r) for r in rows.values()], "books": _clean(books)}


# ═════════════════════════ grading ════════════════════════════════════════════

def grade() -> dict:
    """Grade every frozen, usable straddle whose expiry close is in the bars file; append
    to grades.jsonl (never twice); print book vs twin by expiry block."""
    entries = SF.read_jsonl(SF.ENTRIES_PATH)
    if not entries:
        return {"status": "NO_ENTRIES"}
    done = {(g["session_date"], g["symbol"]) for g in SF.read_jsonl(SF.GRADES_PATH)}
    bars = pd.read_parquet(BARS, columns=["symbol", "date", "close"])
    bars["date"] = pd.to_datetime(bars["date"]).dt.normalize()
    newest = bars["date"].max().date()
    by = {s: g.set_index("date")["close"].sort_index() for s, g in bars.groupby("symbol")}
    sessions = {r["session_date"]: r for r in entries if r.get("kind") == "SESSION"}
    new = []
    for r in entries:
        if r.get("kind") != "NAME" or not r.get("ok") or (r["session_date"], r["symbol"]) in done:
            continue
        exp = date.fromisoformat(r["expiry"])
        if exp > newest:
            continue
        s = by.get(r["symbol"])
        if s is None or not len(s):
            continue
        at = s[s.index <= pd.Timestamp(exp)]
        if not len(at):
            continue
        basis_note = "expiry close" if at.index[-1].date() == exp else f"LAST CLOSE {at.index[-1].date()} (no expiry bar)"
        dec_date = pd.Timestamp(sessions[r["session_date"]]["decision_close"])
        dec_now = s.get(dec_date, np.nan)
        s_t, how = SF.terminal_price(float(at.iloc[-1]), r.get("close_decision"), float(dec_now))
        g = SF.grade_one(r, s_t)
        new.append(_clean({"kind": "GRADE", "session_date": r["session_date"], "symbol": r["symbol"],
                           "expiry": r["expiry"], "strike": r["strike"], "ask_sum": r["ask_sum"],
                           "bid_sum": r["bid_sum"], "mid_sum": r["mid_sum"], **g, "basis": f"{basis_note}; {how}",
                           "policy_hash": r["policy_hash"], "graded_utc": _now().isoformat()}))
    if new:
        SF.GRADES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SF.GRADES_PATH, "a", encoding="utf-8") as fh:
            fh.write("\n".join(SF.canonical(x) for x in new) + "\n")
    return report() | {"graded_now": len(new)}


def report() -> dict:
    entries = SF.read_jsonl(SF.ENTRIES_PATH)
    grades = SF.read_jsonl(SF.GRADES_PATH)
    books = [b for b in entries if b.get("kind") == "BOOK" and b.get("status") == "OK"]
    out = {"entries_sessions": len({r["session_date"] for r in entries if r.get("kind") == "SESSION"}),
           "graded_names": len(grades), "chain": SF.verify_chain()}
    if not grades or not books:
        out["book_vs_twin"] = {"status": "NO_GRADED_COHORTS"}
        return out
    g = pd.DataFrame(grades)
    out["book_vs_twin"] = SF.book_vs_twin(SF.cohort_returns(g, books))
    out["book_vs_twin_exit_haircut_5pct"] = SF.book_vs_twin(SF.cohort_returns(g, books, exit_haircut=0.05))
    return _clean(out)


# ═════════════════════════ contract ═══════════════════════════════════════════

def contract_body() -> dict:
    model = SF.load_model()
    return {
        "trial": SF.TRIAL_ID, "version": 1, "licence": "PRODUCT_EXPERIMENT",
        "what": "forward paper log of ATM straddle SELECTION by the frozen size forecast vs the option market's "
                "implied move, against a twin selected by trailing volatility. No broker, no orders, no LLM.",
        "inputs": {
            "size_model": {"file": "backend/data/optimus/straddle_forward/model_ridge_pit_v1.json",
                           "model_sha": model["model_sha"], "target": model["target"], "spec": model["spec"],
                           "train_span": model["train_span"], "n_train": model["n_train"]},
            "bars": "backend/data/optimus/prices_2025_26/bars.parquet (Alpaca SIP, adjustment=all, refreshed "
                    "nightly by scripts/pull_bars_refresh.py); decision close = its newest session",
            "earnings": "yfinance earnings calendar: report dates strictly before the pull time only; the "
                        "next-earnings flag is the POINT-IN-TIME projection (last done report + 91-day steps), "
                        "never the actual future report date",
            "chains": "yfinance option_chain (free, delayed ~15 min); the underlying quote from the same call",
            "market": "SPY from the bars file (2-day abnormal earnings moves)"},
        "universe": f"top {SF.N_CANDIDATES} bars symbols by 63-session median dollar volume at the decision close, "
                    f"price >= ${SF.MIN_PRICE:g}, known ETFs/index proxies excluded, underlying quoteType EQUITY",
        "expiry_rule": f"the standard monthly (third Friday, or the session before it) with calendar DTE in "
                       f"[{SF.DTE_MIN}, {SF.DTE_MAX}] on the entry day; no such expiry -> no entry that day "
                       f"(OBSERVE_ONLY snapshot)",
        "entry": f"one entry per XNYS session, first scheduled pass in {SF.ENTRY_START_ET}-{SF.ENTRY_END_ET} "
                 f"America/New_York; strike = the listed strike nearest spot carried by both a call and a put",
        "quote_filters": {"max_strike_dist": SF.MAX_STRIKE_DIST, "max_leg_spread_over_mid": SF.MAX_LEG_SPREAD,
                          "max_straddle_spread_over_mid": SF.MAX_STRADDLE_SPREAD, "min_open_interest_per_leg":
                          SF.MIN_OI, "leg_last_trade_max_age_days": SF.LEG_STALE_DAYS,
                          "underlying_quote_max_age_min": SF.UNDERLYING_STALE_MIN,
                          "refuse": "zero/missing bid or ask, crossed quotes, unpriceable mid (IV outside band)"},
        "implied_move": f"iv_atm = mean of call and put IV inverted from the MID (European BSM, r = {SF.RATE}, "
                        f"q = 0); implied move = iv_atm * sqrt(T_to_expiry_close) * sqrt(2/pi)",
        "ranking": "gap = log(forecast E|r21| * sqrt(sessions_to_expiry / 21) / implied move); LONG = largest "
                   "gaps, SHORT = smallest; ties by symbol; a cell needs >= 2*breadth + 10 usable names",
        "breadths_per_leg": list(SF.BREADTHS),
        "primary_breadth": "100 per leg if that cell ran (>= 210 usable names) on >= 80% of the entry sessions "
                           "in the read; otherwise 50 per leg. Declared before the first entry because the "
                           "2026-09-28 closing-quote dry run had 164 usable of 400 (the 100 cell could not run); "
                           "mechanical, not chosen after a result.",
        "twin": "the SAME usable names on the SAME quotes, ranked by trailing 63-session vol * sqrt(21/252) * "
                "sqrt(2/pi) instead of the ridge",
        "fill_convention": "LONG straddle bought at call ask + put ask; SHORT sold at call bid + put bid",
        "exit": "held to expiry; marked at INTRINSIC |S_T - K| from the bars close on the expiry session "
                "(split-rescaled, dividends not); no exit cost charged (sensitivity: 5% of intrinsic)",
        "costs": "the quoted spread paid at entry (ask for longs, bid for shorts); nothing assumed",
        "objective": f"log utility of equity with {SF.BUDGET:.0%} of equity in premium per leg: "
                     "log(1 + b*ls_ridge) - log(1 + b*ls_vol), ls = (long + short)/2 return on premium; "
                     "secondary: the ridge L/S vs cash at quoted costs",
        "statistics": "one observation per EXPIRY (cohorts sharing an expiry averaged); t / SE / MDE = 2.8 SE "
                      "over expiry blocks (move_size_sizing.block_stats, block_len 1)",
        "power": {"history": "2014-2024 100/leg diff +8.2 bp of equity/month, monthly sd ~19.5 bp "
                             "(se 1.72 bp x 3 x sqrt(43 blocks) / sqrt 3)",
                  "blocks_for_mde_equal_to_history_effect": 44,
                  "note": "the forward universe is ~300-400 names, so 100/leg is ~a tercile (the lab's 100/leg was "
                          "~6% of 1,755 names; its quintile cell was +6.8 bp, t 5.28). A forward confirmation "
                          "at the historical effect needs ~44 expiries (~3.7 years)."},
        "kill_rule": f"from {SF.MIN_BLOCKS_KILL} expiry blocks, at every grade: if the PRIMARY-cell diff has mean <= 0 "
                     "and t <= -1 (FAILED_VARIANT) the selector is RETIRED_FROM_CURRENT_SEARCH. At 6 blocks "
                     "(SE ~8 bp) the rule fires on a true zero with ~16% chance per look and on the historical "
                     "+8.2 bp with ~2%: it detects a reversal, it cannot confirm.",
        "first_read": f"after {SF.FIRST_READ_BLOCKS} graded expiry blocks (MDE ~15.8 bp, about twice the "
                      "historical effect): report, do not promote",
        "promotion": "none from this contract. CAPITAL_CANDIDATE needs matured forward evidence AND a "
                     "defined-risk form (long straddles only, or short legs wrapped in wings).",
        "no_llm": True, "no_broker": True,
        "code_at_freeze": {"backend/services/straddle_forward.py": SF.file_sha(Path(SF.__file__)),
                           "scripts/straddle_forward.py": SF.file_sha(Path(__file__)),
                           "note": "every SESSION row records the code hashes it ran; a decision-changing edit "
                                   "is a new contract version"},
        "first_entry_session": "the first XNYS session with a standard monthly 21-35 calendar days out "
                               "(from 2026-09-29: 2026-10-16 -> the 2026-11-20 expiry)",
        "first_grade": "the 2026-11-20 expiry close, graded on the first scheduled pass after the nightly "
                       "bars refresh carries that session",
        "worst_case": "printed on every snapshot for the ridge short leg at 3 and 10 sigma, $1,000,000 notional",
    }


def freeze() -> dict:
    return SF.freeze_contract(contract_body())


# ═════════════════════════ passes ═════════════════════════════════════════════

def _print_summary(s: dict) -> None:
    keys = ("mode", "entry_session_et", "decision_close", "expiry", "calendar_dte", "sessions_to_expiry",
            "n_candidates", "n_usable", "median_straddle_spread_all_quoted", "median_straddle_spread_usable",
            "p90_straddle_spread_usable", "median_iv_atm_usable", "median_implied_move_usable",
            "median_f_ridge_scaled", "fetch_seconds")
    for k in keys:
        _p(f"  {k}: {s.get(k)}")
    _p(f"  refusals: {s.get('refusals')}")
    _p(f"  overlap ridge vs vol legs: {s.get('ridge_vs_vol_leg_overlap')}")
    for b, w in (s.get("short_leg_worst_case_ridge") or {}).items():
        _p(f"  worst case short leg @{b}/leg: 3-sigma {w.get('3_sigma')}; 10-sigma {w.get('10_sigma')}")


def observe(mode: str, expiry: date, limit=None) -> dict:
    snap = snapshot(mode=mode, expiry=expiry, limit=limit)
    s = snap["summary"]
    s["label"] = ("DRY_RUN_NOT_AN_ENTRY" if mode.startswith("DRY") else "OBSERVE_ONLY_NOT_AN_ENTRY")
    p = OBS / f"{mode.lower()}_{s['entry_session_et']}_{_stamp()}.json"
    _write_json(p, snap)
    _p(f"{s['label']} -> {p}")
    _print_summary(s)
    return snap


def enter(expiry: date) -> dict:
    contract = SF.load_contract()
    model = SF.load_model()
    if contract["body"]["inputs"]["size_model"]["model_sha"] != model["model_sha"]:
        raise RuntimeError("the model on disk is not the one the contract froze")
    snap = snapshot(mode="ENTRY", expiry=expiry)
    s = snap["summary"]
    session = s["entry_session_et"]
    head = {"kind": "SESSION", "written_utc": _now().isoformat(), **s}
    rows = [head] + snap["names"] + snap["books"]
    n = SF.append_frozen(rows, session_date=session, contract=contract)
    _write_json(RUNS / f"entry_{session}_{_stamp()}.json", {"rows_frozen": n, "summary": s})
    _p(f"ENTRY frozen: {n} rows for session {session} (policy {contract['policy_hash']})")
    _print_summary(s)
    return snap


def _bars_fresh(newest: date, today: date) -> bool:
    """The decision close must be the session immediately before today's."""
    d = today - timedelta(days=1)
    guard = 0
    while not SF._is_session_default(d) and guard < 10:
        d -= timedelta(days=1)
        guard += 1
    return newest >= d


def scheduled() -> dict:
    now = _now()
    rec = {"stamp": _stamp(), "now_utc": now.isoformat()}
    if STOP.exists():
        rec["state"] = "STOPPED: STOP file present"
        _p(rec["state"])
        return rec
    try:
        rec["grade"] = {k: v for k, v in grade().items() if k in ("graded_now", "graded_names", "book_vs_twin")}
    except Exception as exc:                                         # noqa: BLE001
        rec["grade"] = {"error": f"{type(exc).__name__}: {exc}"}
    w = SF.entry_window(now)
    rec["window"] = w
    if not w["in_window"]:
        rec["state"] = f"IDLE: {w['reason']}"
        return rec
    today = date.fromisoformat(w["session_date"])
    if w["session_date"] in SF.entered_sessions():
        rec["state"] = "IDLE: session already entered"
        return rec
    if list(OBS.glob(f"observe_*_{w['session_date']}_*.json")):
        rec["state"] = "IDLE: session already observed"
        return rec
    b = load_bars()
    if not _bars_fresh(b["newest"], today):
        rec["state"] = f"REFUSED: bars newest {b['newest']} is not the previous session"
        _p(rec["state"])
        return rec
    exp = SF.pick_expiry(today)
    if exp is None:
        snap = observe("OBSERVE", SF.nearest_monthly(today))
        rec["state"] = "OBSERVE_ONLY: no standard monthly in the DTE window"
        rec["summary"] = {k: snap["summary"].get(k) for k in ("n_usable", "median_straddle_spread_usable", "expiry")}
        return rec
    if not SF.CONTRACT_PATH.exists():
        rec["state"] = "REFUSED: no frozen contract (run --freeze-contract before the first entry)"
        _p(rec["state"])
        return rec
    snap = enter(exp)
    rec["state"] = "ENTERED"
    rec["summary"] = {k: snap["summary"].get(k) for k in ("n_usable", "median_straddle_spread_usable", "expiry")}
    return rec


def status() -> int:
    out = {"stop_file": STOP.exists(), "contract": None, "model": None,
           "entered_sessions": sorted(SF.entered_sessions()), "chain": SF.verify_chain(),
           "graded": len(SF.read_jsonl(SF.GRADES_PATH)),
           "observations": sorted(p.name for p in OBS.glob("*.json"))[-5:],
           "window_now": SF.entry_window(_now())}
    if SF.CONTRACT_PATH.exists():
        c = SF.load_contract()
        out["contract"] = {"policy_hash": c["policy_hash"], "frozen_utc": c["frozen_utc"]}
    if SF.MODEL_PATH.exists():
        out["model"] = SF.load_model()["model_sha"]
    print(json.dumps(out, indent=1, default=str))
    return 0


def print_schtasks() -> int:
    py = REPO / ".venv" / "Scripts" / "pythonw.exe"
    _p("Register (PowerShell):")
    print(f"  $a = New-ScheduledTaskAction -Execute '{py}' -Argument '-m scripts.straddle_forward' "
          f"-WorkingDirectory '{REPO}'")
    print("  $t = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) "
          "-RepetitionInterval (New-TimeSpan -Minutes 30)")
    print("  $s = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew "
          "-ExecutionTimeLimit (New-TimeSpan -Minutes 45)")
    print(f"  Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $a -Trigger $t -Settings $s")
    print(f'Remove:  schtasks /Delete /TN "{TASK_NAME}" /F')
    print(f"Pause without removing: create {STOP}")
    return 0


def _receipt(rec: dict) -> None:
    try:
        _write_json(RUNS / f"pass_{rec.get('stamp', _stamp())}.json", _clean(rec))
    except Exception:                                                # noqa: BLE001
        pass


def main(argv=None) -> int:
    _ensure_streams()
    ap = argparse.ArgumentParser(prog="straddle_forward")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--grade", action="store_true")
    ap.add_argument("--freeze-contract", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--schtasks", action="store_true")
    a = ap.parse_args(argv)
    if a.schtasks:
        return print_schtasks()
    if a.status:
        return status()
    if a.freeze_contract:
        c = freeze()
        _p(f"contract {SF.CONTRACT_PATH.name}: policy_hash {c['policy_hash']} frozen {c['frozen_utc']}")
        return 0
    try:
        with RunLock():
            if a.grade:
                print(json.dumps(grade(), indent=1, default=str))
                return 0
            if a.dry_run:
                today = SF.to_et(_now()).date()
                exp = SF.pick_expiry(today) or SF.nearest_monthly(today)
                observe("DRY_RUN", exp, limit=a.limit)
                return 0
            rec = scheduled()
            _p(f"pass: {rec.get('state')}")
            if not str(rec.get("state", "")).startswith("IDLE"):
                _receipt(rec)                  # an idle pass every 30 min leaves a log line, not a file
            return 0
    except RuntimeError as exc:
        _p(f"REFUSED: {exc}")
        _receipt({"state": f"REFUSED: {exc}"})
        return 2
    except Exception as exc:                                         # noqa: BLE001
        tb = traceback.format_exc()
        _p(tb)
        _receipt({"state": f"CRASHED: {type(exc).__name__}: {exc}", "tb": tb[-2000:]})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
