"""TRIAL-STRADDLE-FWD-1: a forward, $0, paper-only log of straddle SELECTION by our
size forecast against the option market's implied move.

Licence: PRODUCT_EXPERIMENT. No broker, no orders, no LLM anywhere in a decision.
Trial doc: `docs/TRIALS/TRIAL-STRADDLE-FWD-1-size-forecast-vs-implied-move.md`.
Runner: `scripts/straddle_forward.py` (the only caller; it owns every network call).

WHY. On 2014-2024 (CRSP x OptionMetrics) the point-in-time size forecast carried
information the option market had not priced (+0.21 rank coefficient beyond implied
vol, t 20.8, positive every year). Choosing which straddles to buy / sell by it beat
choosing them by trailing volatility by +8.2 bp of equity a month at 100 names per leg
(t 4.75) -- on SYNTHETIC at-the-money premia with an ASSUMED 10% cost, in a breadth
cell chosen after the 20-name read (which was CANNOT_DISTINGUISH), and on data that
ends 2024-12. A candidate, not a result. The two unknowns that decide it are the real
quoted cost and whether the relative edge holds forward; both need live chains.

WHAT THIS MODULE HOLDS (pure, offline-testable; the runner does the I/O):
* ET session logic (XNYS calendar via `market_sessions`, DST via zoneinfo) and the
  standard-monthly expiry rule;
* the quote filter (stale, crossed, wide, thin, off-the-money, unpriceable) with a
  recorded reason for every refusal;
* the straddle build (nearest common strike, entry at the ASK for a long and the BID
  for a short, implied vol inverted from the MID under a declared r and q = 0);
* the live size features (the CRSP spec, recomputed from the repo's daily bars) and the
  frozen ridge;
* ranking (log gap = log(forecast / implied move)), leg selection at each breadth,
  and the trailing-vol TWIN;
* the frozen contract (policy hash), the append-only hash-chained entry log;
* the grader (intrinsic value at the expiry close) and the book-vs-twin statistics
  by expiry block with MDE;
* the worst-case print for an (unbounded) short straddle leg.
"""
from __future__ import annotations

import hashlib
import json
import math
import warnings
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from backend import config as _cfg
from backend.services import move_size_sizing as MS
from backend.services.option_implier import implied_vol

ET = ZoneInfo("America/New_York")
# the ledger root from config (override-aware: AEGIS_REPO_ROOT in the packaged app),
# never rebuilt from `__file__`
ROOT = Path(_cfg.OPTIMUS_LEDGER_DIR) / "straddle_forward"
MODEL_PATH = ROOT / "model_ridge_pit_v1.json"
CONTRACT_PATH = ROOT / "contract_v1.json"
ENTRIES_PATH = ROOT / "entries.jsonl"
GRADES_PATH = ROOT / "grades.jsonl"
TRIAL_ID = "TRIAL-STRADDLE-FWD-1"
H = 21                                                  # the size model's horizon, sessions
ATM_FACTOR = math.sqrt(2.0 / math.pi)                   # E|Z|


def _c(name: str, default):
    return getattr(_cfg, name, default)


BREADTHS: tuple = tuple(_c("STRADDLE_FWD_BREADTHS", (20, 50, 100)))
DTE_MIN = int(_c("STRADDLE_FWD_DTE_MIN", 21))
DTE_MAX = int(_c("STRADDLE_FWD_DTE_MAX", 35))
ENTRY_START_ET = str(_c("STRADDLE_FWD_ENTRY_START_ET", "10:45"))
ENTRY_END_ET = str(_c("STRADDLE_FWD_ENTRY_END_ET", "15:30"))
MAX_STRADDLE_SPREAD = float(_c("STRADDLE_FWD_MAX_STRADDLE_SPREAD", 0.20))
MAX_LEG_SPREAD = float(_c("STRADDLE_FWD_MAX_LEG_SPREAD", 0.50))
MAX_STRIKE_DIST = float(_c("STRADDLE_FWD_MAX_STRIKE_DIST", 0.05))
MIN_OI = int(_c("STRADDLE_FWD_MIN_OI", 100))
LEG_STALE_DAYS = float(_c("STRADDLE_FWD_LEG_STALE_DAYS", 5.0))
UNDERLYING_STALE_MIN = float(_c("STRADDLE_FWD_UNDERLYING_STALE_MIN", 30.0))
RATE = float(_c("STRADDLE_FWD_RATE", 0.04))
BUDGET = float(_c("STRADDLE_FWD_BUDGET", 0.02))
EQUITY_NOTIONAL = float(_c("STRADDLE_FWD_EQUITY_NOTIONAL", 1_000_000.0))
N_CANDIDATES = int(_c("STRADDLE_FWD_UNIVERSE_CANDIDATES", 400))
MIN_PRICE = float(_c("STRADDLE_FWD_MIN_PRICE", 5.0))
SPLIT_FACTOR_TOL = 0.05
MIN_BLOCKS_KILL = 6
FIRST_READ_BLOCKS = 12


# ═════════════════════════ ET sessions and the expiry rule ═══════════════════

def _is_session_default(d: date) -> bool:
    from backend.services import market_sessions as M
    return M.is_session(d)


def to_et(now_utc: datetime) -> datetime:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(ET)


def _hm(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def entry_window(now_utc: datetime, is_session: Callable[[date], bool] = _is_session_default) -> dict:
    """Is `now` inside today's ENTRY window (after the open has settled, before the late
    session)? Computed in America/New_York, so DST moves the UTC hour, not the rule."""
    et = to_et(now_utc)
    d = et.date()
    out = {"now_et": et.isoformat(), "session_date": d.isoformat(), "is_session": bool(is_session(d)),
           "window_et": [ENTRY_START_ET, ENTRY_END_ET], "in_window": False, "reason": ""}
    if not out["is_session"]:
        out["reason"] = "NOT_A_SESSION"
    elif et.time() < _hm(ENTRY_START_ET):
        out["reason"] = "BEFORE_WINDOW"
    elif et.time() > _hm(ENTRY_END_ET):
        out["reason"] = "AFTER_WINDOW"
    else:
        out["in_window"], out["reason"] = True, "IN_WINDOW"
    return out


def third_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    first_fri = d + timedelta(days=(4 - d.weekday()) % 7)
    return first_fri + timedelta(days=14)


def monthly_expiry(year: int, month: int, is_session: Callable[[date], bool] = _is_session_default) -> date:
    """The standard monthly expiry: the third Friday, or the session before it when the
    Friday is an exchange holiday (e.g. Good Friday)."""
    d = third_friday(year, month)
    guard = 0
    while not is_session(d) and guard < 7:
        d -= timedelta(days=1)
        guard += 1
    return d


def _monthlies(today: date, is_session, n: int = 4) -> list:
    out = []
    for k in range(n):
        mm = (today.month - 1 + k) % 12 + 1
        yy = today.year + (today.month - 1 + k) // 12
        out.append(monthly_expiry(yy, mm, is_session))
    return out


def pick_expiry(today: date, is_session: Callable[[date], bool] = _is_session_default,
                dte_min: int = DTE_MIN, dte_max: int = DTE_MAX) -> Optional[date]:
    """The standard monthly expiry with calendar days-to-expiry in [dte_min, dte_max].
    Monthlies are 28 or 35 days apart, so on roughly half the days NONE qualifies and
    the day is an observation, not an entry (declared). If two qualify, the one nearer
    28 days."""
    cands = [(abs((e - today).days - 28), e) for e in _monthlies(today, is_session)
             if dte_min <= (e - today).days <= dte_max]
    return min(cands)[1] if cands else None


def nearest_monthly(today: date, is_session: Callable[[date], bool] = _is_session_default,
                    min_dte: int = 7) -> date:
    """For OBSERVATION / dry runs only: the monthly nearest 28 days with >= min_dte."""
    c = [e for e in _monthlies(today, is_session) if (e - today).days >= min_dte]
    return min(c, key=lambda e: (abs((e - today).days - 28), e))


def sessions_between(a: date, b: date, is_session: Callable[[date], bool] = _is_session_default) -> int:
    """Sessions in (a, b]."""
    n, d = 0, a + timedelta(days=1)
    while d <= b:
        n += bool(is_session(d))
        d += timedelta(days=1)
    return n


# ═════════════════════════ quotes ═════════════════════════════════════════════

def _num(x) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _ts_utc(x) -> Optional[pd.Timestamp]:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return None
    try:
        t = pd.Timestamp(x)
    except (TypeError, ValueError):
        return None
    if pd.isna(t):
        return None
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


@dataclass
class Straddle:
    symbol: str
    ok: bool
    reasons: list = field(default_factory=list)
    fields: dict = field(default_factory=dict)


def leg_fields(row) -> dict:
    def g(k):
        try:
            return row.get(k)
        except AttributeError:
            return None
    lt = _ts_utc(g("lastTradeDate"))
    return {"bid": _num(g("bid")), "ask": _num(g("ask")), "last": _num(g("lastPrice")),
            "oi": _num(g("openInterest")), "volume": _num(g("volume")),
            "vendor_iv": _num(g("impliedVolatility")),
            "last_trade_utc": lt.isoformat() if lt is not None else None,
            "contract": g("contractSymbol")}


def build_straddle(symbol: str, calls: pd.DataFrame, puts: pd.DataFrame, *, spot: float,
                   spot_time_utc, now_utc: datetime, expiry: date,
                   in_session: bool, rate: float = RATE) -> Straddle:
    """The at-the-money straddle of one name at one expiry, or a refusal WITH its reasons.

    Strike = the listed strike nearest spot that both a call and a put carry. Refusals
    (every one recorded): NO_SPOT, NO_CHAIN, NO_COMMON_STRIKE, OFF_ATM (> MAX_STRIKE_DIST),
    NO_BID_* / NO_ASK_* (a zero or missing side), CROSSED_* (ask < bid), WIDE_* (a leg's
    spread over its mid), WIDE_STRADDLE, THIN_OI_*, STALE_* (a leg's last trade older than
    LEG_STALE_DAYS), STALE_UNDERLYING (during a session, the underlying quote older than
    UNDERLYING_STALE_MIN), NO_IV (the mid is outside the no-arbitrage band)."""
    s = Straddle(symbol=symbol, ok=False)
    now = _ts_utc(now_utc)
    if spot is None or not (spot > 0):
        s.reasons.append("NO_SPOT")
        return s
    if calls is None or puts is None or len(calls) == 0 or len(puts) == 0:
        s.reasons.append("NO_CHAIN")
        return s
    cs = {float(r["strike"]): r for _, r in calls.iterrows() if _num(r.get("strike")) is not None}
    ps = {float(r["strike"]): r for _, r in puts.iterrows() if _num(r.get("strike")) is not None}
    common = sorted(set(cs) & set(ps))
    if not common:
        s.reasons.append("NO_COMMON_STRIKE")
        return s
    k = min(common, key=lambda x: (abs(x - spot), x))
    c, p = leg_fields(cs[k]), leg_fields(ps[k])
    exp_close = datetime.combine(expiry, dtime(16, 0), tzinfo=ET)
    days = (exp_close - now.to_pydatetime()).total_seconds() / 86400.0
    t_years = days / 365.0
    st = _ts_utc(spot_time_utc)
    f = {"strike": k, "spot": float(spot), "strike_dist": abs(k - spot) / spot, "expiry": expiry.isoformat(),
         "days_to_expiry": round(days, 4), "call": c, "put": p,
         "spot_time_utc": st.isoformat() if st is not None else None}
    s.fields = f
    r = s.reasons
    if f["strike_dist"] > MAX_STRIKE_DIST:
        r.append("OFF_ATM")
    for nm, leg in (("call", c), ("put", p)):
        tag = nm.upper()
        if leg["bid"] is None or leg["bid"] <= 0:
            r.append(f"NO_BID_{tag}")
        if leg["ask"] is None or leg["ask"] <= 0:
            r.append(f"NO_ASK_{tag}")
        if leg["bid"] and leg["ask"] and leg["ask"] < leg["bid"]:
            r.append(f"CROSSED_{tag}")
        if leg["bid"] and leg["ask"] and leg["ask"] >= leg["bid"] > 0:
            leg["mid"] = 0.5 * (leg["bid"] + leg["ask"])
            leg["rel_spread"] = (leg["ask"] - leg["bid"]) / leg["mid"]
            if leg["rel_spread"] > MAX_LEG_SPREAD:
                r.append(f"WIDE_{tag}")
        if leg["oi"] is None or leg["oi"] < MIN_OI:
            r.append(f"THIN_OI_{tag}")
        lt = _ts_utc(leg["last_trade_utc"])
        if lt is None or (now - lt).total_seconds() > LEG_STALE_DAYS * 86400:
            r.append(f"STALE_{tag}")
    if in_session and (st is None or (now - st).total_seconds() > UNDERLYING_STALE_MIN * 60):
        r.append("STALE_UNDERLYING")
    if t_years <= 0:
        r.append("EXPIRED")
    if "mid" in c and "mid" in p:
        f["ask_sum"] = c["ask"] + p["ask"]
        f["bid_sum"] = c["bid"] + p["bid"]
        f["mid_sum"] = c["mid"] + p["mid"]
        f["straddle_rel_spread"] = (f["ask_sum"] - f["bid_sum"]) / f["mid_sum"]
        if f["straddle_rel_spread"] > MAX_STRADDLE_SPREAD:
            r.append("WIDE_STRADDLE")
        if t_years > 0:
            ivc = implied_vol(c["mid"], spot, k, t_years, rate, 0.0, True)
            ivp = implied_vol(p["mid"], spot, k, t_years, rate, 0.0, False)
            f["iv_call"], f["iv_put"] = ivc, ivp
            if ivc is None or ivp is None:
                r.append("NO_IV")
            else:
                f["iv_atm"] = 0.5 * (ivc + ivp)
                f["implied_move"] = f["iv_atm"] * math.sqrt(t_years) * ATM_FACTOR
                f["straddle_mid_over_spot"] = f["mid_sum"] / spot
    s.ok = not r
    return s


def refusal_counts(straddles: Iterable[Straddle]) -> dict:
    out: dict = {}
    for s in straddles:
        for r in (s.reasons or []):
            out[r] = out.get(r, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


# ═════════════════════════ live size features + the frozen model ═════════════

def _tvol(R: np.ndarray, n: int, need: int) -> np.ndarray:
    x = R[-n:]
    ok = np.isfinite(x).sum(axis=0) >= need
    with warnings.catch_warnings(), np.errstate(invalid="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)
        v = np.nanstd(x, axis=0, ddof=1) * math.sqrt(252)
    return np.where(ok, v, np.nan)


def live_features(close: pd.DataFrame, dollar_vol: pd.DataFrame, market: pd.Series,
                  past_reports: dict, *, entry: date, window_end: date) -> pd.DataFrame:
    """The CRSP size spec, recomputed at the DECISION close = the last row of `close`
    (dates x symbols, adjusted closes, sessions ascending).

    `past_reports` {symbol: [report dates (ET calendar dates)]} should hold only reports
    already public at the decision close; this function re-filters (anything dated
    after the decision session is dropped and counted in attrs).
    Earnings conventions exactly as `sizing_lab_crsp.build_panel`: d0 = first session
    >= the report date; the 2-day abnormal = (1+r_d0)(1+r_d0+1) - (1+m_d0)(1+m_d0+1);
    an event is DONE when d0+1 <= the decision session; ems4 = mean |abn| of the last
    <= 4 done events (needs >= 2). The POINT-IN-TIME flag projects the last done report
    date forward in 91-day steps past `entry` and asks whether it lands on or before
    `window_end` (the straddle's expiry). The actual future report date is never read."""
    close = close.sort_index()
    idx = pd.DatetimeIndex(close.index)
    dec = idx[-1].date()
    C = close.to_numpy(dtype=float)
    T, N = C.shape
    R = np.full_like(C, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        R[1:] = C[1:] / C[:-1] - 1.0
    mk = market.reindex(idx).to_numpy(dtype=float)
    M = np.full(len(mk), np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        M[1:] = mk[1:] / mk[:-1] - 1.0
    f = {"vol_21": _tvol(R, 21, 15), "vol_63": _tvol(R, 63, 40), "vol_252": _tvol(R, 252, 120)}
    with warnings.catch_warnings(), np.errstate(invalid="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)
        f["maxabs_21"] = np.nanmax(np.abs(R[-21:]), axis=0)
        last = C[-1]
        f["absret_21"] = last / C[-22] - 1.0 if T > 21 else np.full(N, np.nan)
        f["absret_252"] = last / C[-253] - 1.0 if T > 252 else np.full(N, np.nan)
        DV = dollar_vol.reindex(index=idx, columns=close.columns).to_numpy(dtype=float)
        mdv = np.nanmedian(DV[-63:], axis=0)
        f["median_dollar_vol"] = mdv
        f["dv_log"] = np.log1p(mdv)
        f["px_log"] = np.where(last > 0, np.log(np.where(last > 0, last, 1.0)), np.nan)
    ems = np.full(N, np.nan)
    nxt = np.zeros(N)
    n_done = np.zeros(N, dtype=int)
    last_done: list = [None] * N
    dropped_future = 0
    sess = idx.normalize()
    for j, sym in enumerate(close.columns):
        reps = sorted({pd.Timestamp(d).normalize() for d in (past_reports.get(sym) or [])})
        keep = [d for d in reps if d.date() <= dec]
        dropped_future += len(reps) - len(keep)
        abns, done_dates = [], []
        for d in keep:
            d0 = int(np.searchsorted(sess, d))                 # first session >= report date
            if d0 + 1 > T - 1:
                continue                                        # window not closed at the decision
            done_dates.append(d)
            if d0 < 1:
                continue                                        # before the bars: date known, move not
            a = (1 + R[d0, j]) * (1 + R[d0 + 1, j]) - (1 + M[d0]) * (1 + M[d0 + 1])
            if np.isfinite(a):
                abns.append(abs(a))
        n_done[j] = len(abns)
        if len(abns) >= 2:
            ems[j] = float(np.mean(abns[-4:]))
        if len(done_dates) >= 2:                                # the lab projects only with >= 2 done
            nd = done_dates[-1] + pd.Timedelta(days=91)
            while nd.date() <= entry:
                nd += pd.Timedelta(days=91)
            nxt[j] = 1.0 if nd.date() <= window_end else 0.0
            last_done[j] = done_dates[-1].date().isoformat()
    f["ems4"] = ems
    f["earn_next_pit"] = nxt
    f["earn_x_ems_pit"] = nxt * ems
    out = pd.DataFrame(f, index=close.columns)
    out["n_earn_done"] = n_done
    out["last_known_report"] = last_done
    out.attrs["decision_date"] = dec.isoformat()
    out.attrs["future_reports_dropped"] = int(dropped_future)
    return out


def model_hash(body: dict) -> str:
    keep = {k: body[k] for k in ("spec", "feature_order", "alpha", "winsor_cap", "floor", "mu", "sd", "coef",
                                 "intercept", "target") if k in body}
    return hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()[:16]


def load_model(path: Path = MODEL_PATH) -> dict:
    body = json.loads(Path(path).read_text(encoding="utf-8"))
    h = model_hash(body)
    if h != body.get("model_sha"):
        raise RuntimeError(f"size model hash mismatch: file says {body.get('model_sha')}, content is {h}")
    return body


def apply_model(model: dict, feats: pd.DataFrame) -> pd.Series:
    """E|r21| for each row, the frozen ridge with the fit's floor. A missing input takes
    the training mean (exactly `move_size_sizing._predict_ridge`)."""
    spec = {k: model["spec"][k] for k in model["feature_order"]}
    X = MS._transform(feats, spec)
    pred = MS._predict_ridge((np.asarray(model["mu"]), np.asarray(model["sd"]), np.asarray(model["coef"]),
                              float(model["intercept"])), X)
    return pd.Series(np.maximum(pred, float(model["floor"])), index=feats.index)


def vol_forecast(vol_63: pd.Series) -> pd.Series:
    """The twin: trailing 63-session vol as E|r21| (exactly the lab's f_vol)."""
    return vol_63 * math.sqrt(H / 252.0) * ATM_FACTOR


# ═════════════════════════ ranking and legs ═══════════════════════════════════

def rank_legs(df: pd.DataFrame, forecast_col: str, breadth: int, *, implied_col: str = "implied_move",
              scale_col: str = "horizon_scale") -> Optional[dict]:
    """Rank usable names by gap = log(forecast * horizon_scale / implied move).
    LONG = the `breadth` largest positive gaps (the market prices the least move against
    our forecast); SHORT = the `breadth` most negative. The lab's rule: a cell needs
    >= 2*breadth + 10 usable names or it is skipped (None). Ties broken by symbol."""
    g = df[[forecast_col, implied_col, scale_col]].astype(float)
    ok = np.isfinite(g).all(axis=1) & (g[forecast_col] > 0) & (g[implied_col] > 0)
    d = df.loc[ok].copy()
    if len(d) < 2 * breadth + 10:
        return None
    d["_gap"] = np.log(d[forecast_col] * d[scale_col] / d[implied_col])
    d["_sym"] = d.index.astype(str)
    d = d.sort_values(["_gap", "_sym"], ascending=[False, True], kind="mergesort")
    return {"long": d.index[:breadth].tolist(), "short": d.index[-breadth:].tolist()[::-1],
            "n_usable": int(len(d)), "gap_long_min": float(d["_gap"].iloc[breadth - 1]),
            "gap_short_max": float(d["_gap"].iloc[-breadth])}


# ═════════════════════════ contract + frozen log ══════════════════════════════

def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))


def sha16(obj) -> str:
    return hashlib.sha256(canonical(obj).encode()).hexdigest()[:16]


def file_sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def freeze_contract(body: dict, path: Path = CONTRACT_PATH) -> dict:
    """Write the contract once. Re-freezing identical content is a no-op; different
    content REFUSES (a changed policy is a new version file, never an overwrite)."""
    h = sha16(body)
    path = Path(path)
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        if old.get("policy_hash") == h:
            return old
        raise RuntimeError(f"contract {path.name} is frozen as {old.get('policy_hash')}; "
                           f"this body hashes to {h}. A new policy is a new version file.")
    rec = {"policy_hash": h, "frozen_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "body": body}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    tmp.replace(path)
    return rec


def load_contract(path: Path = CONTRACT_PATH) -> dict:
    rec = json.loads(Path(path).read_text(encoding="utf-8"))
    if sha16(rec["body"]) != rec.get("policy_hash"):
        raise RuntimeError(f"contract hash mismatch: stored {rec.get('policy_hash')} vs content {sha16(rec['body'])}")
    return rec


def read_jsonl(path: Path) -> list:
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def entered_sessions(path: Path = ENTRIES_PATH) -> set:
    return {r["session_date"] for r in read_jsonl(path) if r.get("kind") == "SESSION"}


def _utc(x) -> pd.Timestamp:
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def append_frozen(rows: list, *, session_date: str, contract: dict, path: Path = ENTRIES_PATH) -> int:
    """Append one session's rows to the frozen log, hash-chained (each row carries the
    previous row's hash and its own). REFUSES a second write for the same session and any
    row stamped before the contract was frozen (the contract comes BEFORE the first entry)."""
    path = Path(path)
    if session_date in entered_sessions(path):
        raise RuntimeError(f"session {session_date} is already in the frozen log; entries are never rewritten")
    fz = _utc(contract["frozen_utc"])
    for r in rows:
        if _utc(r.get("quote_utc") or r.get("written_utc")) < fz:
            raise RuntimeError("a row predates the contract freeze; the contract must be frozen BEFORE the first entry")
    existing = read_jsonl(path)
    prev = existing[-1].get("row_hash") if existing else None
    lines = []
    for r in rows:
        r = {k: v for k, v in dict(r).items() if k != "row_hash"}
        r["policy_hash"] = contract["policy_hash"]
        r["session_date"] = session_date
        r["prev_hash"] = prev
        r["row_hash"] = sha16(r)
        prev = r["row_hash"]
        lines.append(canonical(r))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
        fh.flush()
    return len(lines)


def verify_chain(path: Path = ENTRIES_PATH) -> dict:
    rows = read_jsonl(path)
    prev, bad = None, []
    for i, r in enumerate(rows):
        h = r.get("row_hash")
        body = {k: v for k, v in r.items() if k != "row_hash"}
        if r.get("prev_hash") != prev or sha16(body) != h:
            bad.append(i)
        prev = h
    return {"rows": len(rows), "broken_at": bad[:10], "ok": not bad}


# ═════════════════════════ grading ════════════════════════════════════════════

def terminal_price(close_expiry_adj: float, close_decision_recorded: float,
                   close_decision_adj_now: float) -> tuple:
    """S_T in the ENTRY basis. The bars are adjusted for splits AND dividends; an option
    is adjusted for a split (OCC) but not for an ordinary dividend. So the adjusted close
    at expiry is rescaled only when the decision close's re-read differs from the one
    recorded at entry by more than SPLIT_FACTOR_TOL (a split); a small difference is a
    dividend adjustment and is ignored."""
    vals = (close_expiry_adj, close_decision_recorded, close_decision_adj_now)
    if not all(x is not None and np.isfinite(x) and x > 0 for x in vals):
        return close_expiry_adj, "unscaled (a basis input missing)"
    fct = close_decision_recorded / close_decision_adj_now
    if abs(fct - 1.0) > SPLIT_FACTOR_TOL:
        return close_expiry_adj * fct, f"split_scaled x{fct:.4f}"
    return close_expiry_adj, "unscaled"


def grade_one(row: dict, s_t: float) -> dict:
    """Marked at INTRINSIC value at the expiry close: payoff |S_T - K| per share.
    LONG return on premium = payoff / ask_sum - 1 (bought at the ask).
    SHORT return on premium = 1 - payoff / bid_sum (sold at the bid; unbounded below)."""
    k = float(row["strike"])
    pay = abs(float(s_t) - k)
    ask, bid = float(row["ask_sum"]), float(row["bid_sum"])
    return {"s_t": float(s_t), "payoff": pay, "long_ret": pay / ask - 1.0, "short_ret": 1.0 - pay / bid,
            "long_ret_mid": pay / float(row["mid_sum"]) - 1.0}


def cohort_returns(names: pd.DataFrame, books: list, *, exit_haircut: float = 0.0) -> pd.DataFrame:
    """Per (session, selector, breadth): mean long / short return on premium over the
    graded names, and ls = (long + short) / 2 -- the lab's leg arithmetic.
    `names` = graded rows (session_date, symbol, payoff, ask_sum, bid_sum).
    `exit_haircut` charges a share of the intrinsic payoff on exit (sensitivity: the
    exercise / closing cost the intrinsic mark does not charge)."""
    g = names.set_index(["session_date", "symbol"])
    out = []
    for b in books:
        rows = {}
        for leg in ("long", "short"):
            vals = []
            for s in b[leg]:
                key = (b["session_date"], s)
                if key not in g.index:
                    continue
                r = g.loc[key]
                if leg == "long":
                    vals.append(float(r["payoff"]) * (1.0 - exit_haircut) / float(r["ask_sum"]) - 1.0)
                else:
                    vals.append(1.0 - float(r["payoff"]) * (1.0 + exit_haircut) / float(r["bid_sum"]))
            rows[leg] = float(np.mean(vals)) if vals else np.nan
            rows[f"n_{leg}"] = len(vals)
        out.append({"session_date": b["session_date"], "expiry": b["expiry"], "selector": b["selector"],
                    "breadth": int(b["breadth"]), "long": rows["long"], "short": rows["short"],
                    "ls": 0.5 * (rows["long"] + rows["short"]), "n_long": rows["n_long"],
                    "n_short": rows["n_short"],
                    "complete": rows["n_long"] == len(b["long"]) and rows["n_short"] == len(b["short"])})
    return pd.DataFrame(out)


def kill_rule_state(st: dict) -> str:
    """Declared in the contract. From MIN_BLOCKS_KILL expiry blocks on: FAILED_VARIANT (the
    house rule: mean <= 0 and t <= -1) retires the selector from the current search.
    Confirmation is not possible before ~44 blocks (the contract's power statement)."""
    n = st.get("n_blocks") or 0
    if n < MIN_BLOCKS_KILL:
        return f"TOO_FEW_BLOCKS ({n} < {MIN_BLOCKS_KILL})"
    m, t = st.get("mean_monthly"), st.get("t_blocks")
    if m is not None and t is not None and m <= 0 and t <= -1.0:
        return "KILL: FAILED_VARIANT -> RETIRED_FROM_CURRENT_SEARCH"
    if n < FIRST_READ_BLOCKS:
        return "RUNNING (kill-only looks)"
    return "FIRST_READ_DUE"


def book_vs_twin(cohorts: pd.DataFrame, *, budget: float = BUDGET) -> dict:
    """The primary read: the ridge book minus the trailing-vol twin, as log utility of
    equity at `budget` of equity in premium per leg, per EXPIRY BLOCK (every cohort that
    expires on the same date shares one terminal shock, so an expiry is one independent
    observation). t / SE / MDE from `move_size_sizing.block_stats` over those blocks
    (MDE = 2.8 SE; needs >= 3 blocks for a t)."""
    if cohorts is None or not len(cohorts):
        return {"status": "NO_GRADED_COHORTS"}
    out = {}
    c = cohorts[cohorts["complete"]]
    for bth in sorted(c["breadth"].unique()):
        x = c[c["breadth"] == bth]
        piv = x.pivot_table(index=["expiry", "session_date"], columns="selector", values="ls")
        if not {"ridge", "vol"} <= set(piv.columns):
            continue
        blk = piv.groupby(level="expiry").mean()
        ix = pd.DatetimeIndex(blk.index)
        lu = pd.Series(np.log1p(budget * blk["ridge"].to_numpy()) - np.log1p(budget * blk["vol"].to_numpy()), ix)
        st = MS.block_stats(lu, block_len=1)
        cash = MS.block_stats(pd.Series(np.log1p(budget * blk["ridge"].to_numpy()), ix), 1)
        out[str(int(bth))] = {"n_expiry_blocks": int(len(blk)), "n_cohorts": int(len(piv)),
                              "ridge_ls_mean_on_premium": float(blk["ridge"].mean()),
                              "vol_ls_mean_on_premium": float(blk["vol"].mean()),
                              "diff_equity_bp_mean": float((budget * (blk["ridge"] - blk["vol"])).mean() * 1e4),
                              "log_utility_diff_by_expiry": st, "ridge_book_vs_cash_log_utility": cash,
                              "kill_rule": kill_rule_state(st)}
    return out


# ═════════════════════════ worst case, in dollars ════════════════════════════

def short_leg_worst_case(straddles: list, *, equity: float = EQUITY_NOTIONAL, budget: float = BUDGET,
                         ks: tuple = (3.0, 10.0)) -> dict:
    """The protocol-4 print for an UNBOUNDED short straddle leg.

    The leg collects `budget * equity` of premium, split equally over its names; name i
    sells q_i = credit_i / bid_sum_i straddles (per share of underlying). A k-sigma move
    over the hold is k * iv_atm * sqrt(T) * S. At expiry the short owes |S_T - K| per
    share, so its loss is q_i * (k sigma S + |S - K| - bid_sum_i). The long leg's worst
    case is its premium. `straddles` = dicts with spot, strike, bid_sum, iv_atm and
    days_to_expiry."""
    n = len(straddles)
    if not n:
        return {"n_names": 0}
    credit = budget * equity / n
    out = {"equity": equity, "premium_per_leg": budget * equity, "n_names": n, "credit_per_name": credit,
           "long_leg_worst_case": -budget * equity,
           "long_leg_note": "a long straddle can lose at most its premium (the ask paid)"}
    for k in ks:
        losses = []
        for s in straddles:
            t = max(float(s["days_to_expiry"]), 0.0) / 365.0
            pay = k * float(s["iv_atm"]) * math.sqrt(t) * float(s["spot"]) + abs(float(s["spot"]) - float(s["strike"]))
            losses.append(credit / float(s["bid_sum"]) * (pay - float(s["bid_sum"])))
        losses = np.asarray(losses)
        out[f"{k:g}_sigma"] = {"loss_per_name_max": -float(losses.max()),
                               "loss_per_name_median": -float(np.median(losses)),
                               "loss_leg_all_names_at_once": -float(losses.sum()),
                               "leg_loss_over_equity": -float(losses.sum() / equity)}
    out["unbounded"] = ("a short straddle's loss grows without limit in the move; these are sized k-sigma "
                        "moves, not bounds. The real-money form must be DEFINED-RISK: long straddles only, "
                        "or every short straddle wrapped in long wings (an iron butterfly, max loss = wing "
                        "width - credit).")
    return out
