"""X2 (LANE X, 2026-09-28): a StockBench-style check of OUR OWN LLM, small scale.

StockBench (arXiv:2510.02209, github.com/ChenYXxxx/stockbench, Apache-2.0) asks
whether LLM agents trade profitably on a window AFTER the models' training
cutoffs. We do not install it. We reproduce its IDEA with our stack:

  * the model actually answering (`usage.model`; since 2026-09-14 the
    `deepseek-chat` alias is served as `deepseek-flash` = DeepSeek-V4.1-Flash,
    whose knowledge cutoff is NOT published) is PROBED for its cutoff first:
    month-end closes of five no-split tickers, asked with nothing in context;
  * 40 names x 12 weekly decision dates AFTER that measured cutoff, each with a
    fixed PIT packet (return/vol summary with NO price levels, headlines and
    typed events published before the decision close);
  * two arms per prompt: NAMED (ticker, company, real dates) and BLINDED
    (ticker + company name -> a code, dates shifted +3653 days);
  * a FAMOUS pre-cutoff set (the largest mega-cap 5-session moves before the
    cutoff) in both arms: the NAMED - BLINDED hit-rate gap there is the
    leakage measure; on post-cutoff dates the arms should agree.

Every call goes through `llm_analyzer._call_llm(purpose=...)` so spend lands in
the ledger. Eight names per call (the production path caps a process at 150
calls; 40x12x2 single-name calls would be 960). HARD CAP $1.50, priced at the
SERVED model's row; an unpriced served model refuses (a cap that cannot price a
call cannot bind). Stage `first` makes TWO calls (the same 8 names, NAMED and BLINDED: 16 rows) and stops so the
first flush is read before the rest is paid for.

    python -m scripts.exp_llm_blind_gap_2026_09_28 --stage probe  --run-id ID
    python -m scripts.exp_llm_blind_gap_2026_09_28 --stage first  --run-id ID
    python -m scripts.exp_llm_blind_gap_2026_09_28 --stage run    --run-id ID
    python -m scripts.exp_llm_blind_gap_2026_09_28 --stage analyze --run-id ID
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ───────────────────────── constants (a script, not a service) ─────────────
OUT_DIR = ROOT / "backend/data/optimus/experiments_2026-09-28"
BARS = ROOT / "backend/data/optimus/prices_deep/bars.parquet"
NEWS = ROOT / "backend/data/optimus/text_return_panel/news_returns_2025_26.parquet"
TYPED_DIR = ROOT / "backend/data/optimus/typed_events"
COMPANY_TICKERS = ROOT / "backend/data/optimus/edgar_8k/company_tickers.json"

PURPOSE = "exp_x2_blind_gap_2026_09_28"
PURPOSE_PROBE = "exp_x2_cutoff_probe_2026_09_28"
CAP_USD = 1.50
N_NAMES = 40
N_DATES = 12
PER_CALL = 8               # 8 x ~40 output tokens fits _MAX_TOKENS=500; 10 would not reliably
N_FAMOUS = 30
HORIZON = 5
DATE_SHIFT_DAYS = 3653
MAX_HEADLINES = 8
HEADLINE_LOOKBACK_DAYS = 14
DECISION_UTC_HOUR = 20          # 16:00 ET in EDT; headlines strictly before it
MIN_MDV_NAMES = 1e8
SEED = 20260928
PROBE_TICKERS = ("SPY", "QQQ", "AAPL", "MSFT", "META")
PROBE_MONTHS = pd.period_range("2024-01", "2026-08", freq="M")
PROBE_TOL = 0.06                # |log error| counted as "knows the month"
CUTOFF_BUFFER_MONTHS = 1
FREE_GB_REQUIRED = 40.0

SYSTEM_PROMPT = (
    "You are an equity analyst making short-horizon forecasts. For EACH stock "
    "item you are given, forecast its total return over the next 5 trading "
    "sessions, from the close on the decision date to the close 5 sessions later.\n"
    "Use only the information provided. Reply with ONLY a JSON array (no prose, "
    "no markdown fence), one object per item, in the order given, with exactly "
    "these keys:\n"
    '{"id": "<the item id, e.g. S1>", "direction": "up" or "down", '
    '"ret_low_pct": <number>, "ret_high_pct": <number>, "confidence": <number>}\n'
    "direction: the sign you expect for the 5-session return. ret_low_pct and "
    "ret_high_pct: a range, in percent, that you believe has an 80% chance of "
    "containing the 5-session return (ret_low_pct < ret_high_pct). confidence: "
    "the probability, between 0.5 and 1.0, that your direction is right."
)
RESPONSE_KEYS = ("id", "direction", "ret_low_pct", "ret_high_pct", "confidence")

PROBE_SYSTEM = (
    "Answer from memory only. Reply with ONLY a JSON object (no prose, no "
    "markdown fence) mapping each month 'YYYY-MM' asked to the closing price "
    "in US dollars on that month's last trading day, or null if you do not "
    "know it. Do not guess: null is better than a guess."
)

_SUFFIXES = {"INC", "INC.", "CORP", "CORP.", "CORPORATION", "CO", "CO.", "LTD", "LTD.",
             "PLC", "HOLDINGS", "HOLDING", "GROUP", "COMPANY", "THE", "N.V.", "NV",
             "S.A.", "SA", "AG", "SE", "LP", "L.P.", "CLASS", "A", "B", "C", "/DE/",
             "/DE", "&", "TRUST", "INTERNATIONAL", "TECHNOLOGIES", "SYSTEMS"}
_COMMON = {"AMERICAN", "GENERAL", "UNITED", "FIRST", "NATIONAL", "GLOBAL", "BANK",
           "ENERGY", "HEALTH", "DATA", "REAL", "NEW", "WESTERN", "SOUTHERN", "APPLIED",
           "ADVANCED", "DIGITAL", "CAPITAL", "FINANCIAL", "MEDICAL", "PACIFIC", "BUSINESS"}
#: Tickers of 1-2 letters (A, S, F, T) collide with words and "S&P"; they cannot be
#: blinded without mangling text, so they are left out of the sample (said here).
MIN_TICKER_LEN = 3


# ───────────────────────── pure functions (tested) ──────────────────────────
def wilson(k: int, n: int, z: float = 1.96) -> tuple:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def name_aliases(ticker: str, title: Optional[str]) -> list:
    """Strings that identify the company: the ticker and the SEC title stripped
    of legal suffixes, plus its first distinctive word (>= 4 letters)."""
    out = [ticker]
    if title:
        words = [w for w in re.split(r"\s+", title.replace(",", " ").strip()) if w]
        core = [w for w in words if w.upper() not in _SUFFIXES]
        if core:
            full = " ".join(core)
            out.append(full)
            first = core[0].strip(".")
            if len(first) >= 4 and first.upper() not in _COMMON:
                out.append(first)
    seen, res = set(), []
    for a in sorted(out, key=len, reverse=True):
        if a.upper() not in seen:
            seen.add(a.upper())
            res.append(a)
    return res


def blind_text(text: str, aliases: list, code: str) -> str:
    """Replace every alias (whole word, case-insensitive) by the code. Tickers
    of 1-2 letters are only replaced in their exact case (A, F, T are words)."""
    out = text
    for a in aliases:
        flags = 0 if (len(a) <= 2 and a.isupper()) else re.IGNORECASE
        out = re.sub(rf"(?<![A-Za-z0-9]){re.escape(a)}(?![A-Za-z0-9])", code, out, flags=flags)
    return out


def leaks(text: str, aliases: list) -> list:
    """Aliases still present after blinding (should be empty)."""
    bad = []
    for a in aliases:
        flags = 0 if (len(a) <= 2 and a.isupper()) else re.IGNORECASE
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(a)}(?![A-Za-z0-9])", text, flags=flags):
            bad.append(a)
    return bad


def shift_date(d: str, days: int = DATE_SHIFT_DAYS) -> str:
    return (pd.Timestamp(d) + pd.Timedelta(days=days)).strftime("%Y-%m-%d")


def unshift_date(d: str, days: int = DATE_SHIFT_DAYS) -> str:
    return shift_date(d, -days)


def make_codes(tickers: list, seed: int = SEED) -> dict:
    """ticker -> code, a bijection (reversible), codes carry no ticker letters."""
    rng = np.random.default_rng(seed)
    nums = rng.choice(np.arange(100, 1000), size=len(tickers), replace=False)
    return {t: f"STOCK_{int(n)}" for t, n in zip(sorted(tickers), nums)}


def invert(m: dict) -> dict:
    inv = {v: k for k, v in m.items()}
    if len(inv) != len(m):
        raise ValueError("code map is not a bijection")
    return inv


def headlines_before(news: pd.DataFrame, symbol: str, t, max_n: int = MAX_HEADLINES,
                     lookback_days: int = HEADLINE_LOOKBACK_DAYS) -> list:
    """Titles published STRICTLY before the decision close of t (20:00 UTC),
    within `lookback_days`, newest first. Never an outcome column."""
    cut = pd.Timestamp(t).tz_localize("UTC") + pd.Timedelta(hours=DECISION_UTC_HOUR) \
        if pd.Timestamp(t).tzinfo is None else pd.Timestamp(t) + pd.Timedelta(hours=DECISION_UTC_HOUR)
    lo = cut - pd.Timedelta(days=lookback_days)
    g = news[(news["symbol"] == symbol) & (news["pub"] < cut) & (news["pub"] >= lo)]
    g = g.sort_values("pub", ascending=False).drop_duplicates("title").head(max_n)
    return [(p.strftime("%Y-%m-%d"), str(ti)) for p, ti in zip(g["pub"], g["title"])]


def price_summary(closes: np.ndarray, volumes: np.ndarray) -> dict:
    """Levels-free summary from bars dated <= t (the caller slices)."""
    c = np.asarray(closes, dtype=float)
    v = np.asarray(volumes, dtype=float)

    def r(n):
        return float(c[-1] / c[-1 - n] - 1) * 100 if len(c) > n else float("nan")
    lr = np.diff(np.log(c))
    return {"ret_1d_pct": r(1), "ret_5d_pct": r(5), "ret_21d_pct": r(21),
            "ret_63d_pct": r(63), "ret_252d_pct": r(252),
            "vol_21d_daily_pct": float(np.std(lr[-21:], ddof=1) * 100) if len(lr) >= 21 else float("nan"),
            "vol_63d_daily_pct": float(np.std(lr[-63:], ddof=1) * 100) if len(lr) >= 63 else float("nan"),
            "pct_below_52w_high": float((1 - c[-1] / np.max(c[-252:])) * 100),
            "volume_5d_vs_63d": float(np.mean(v[-5:]) / np.mean(v[-63:])) if len(v) >= 63 else float("nan")}


def render_item(item_id: str, label: str, summ: dict, heads: list, events: list) -> str:
    lines = [f"[{item_id}] {label}",
             "  price action to the decision close (no price levels): " +
             ", ".join(f"{k}={v:.2f}" for k, v in summ.items() if np.isfinite(v))]
    if heads:
        lines.append("  headlines (published before the decision close):")
        lines += [f"    {d}: {h}" for d, h in heads]
    else:
        lines.append("  headlines: none on file")
    if events:
        lines.append("  typed events: " + "; ".join(events))
    return "\n".join(lines)


def parse_reply(text: Optional[str], ids: list) -> dict:
    """-> {id: row} for rows that carry every key with valid values."""
    if not text:
        return {}
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    m = re.search(r"\[.*\]", s, flags=re.S)
    if not m:
        return {}
    try:
        arr = json.loads(m.group(0))
    except ValueError:
        return {}
    out = {}
    for o in arr if isinstance(arr, list) else []:
        if not isinstance(o, dict) or not all(k in o for k in RESPONSE_KEYS):
            continue
        if o["id"] not in ids or o["direction"] not in ("up", "down"):
            continue
        try:
            lo, hi, cf = float(o["ret_low_pct"]), float(o["ret_high_pct"]), float(o["confidence"])
        except (TypeError, ValueError):
            continue
        if not (lo < hi) or not (0.0 <= cf <= 1.0):
            continue
        out[o["id"]] = {"direction": o["direction"], "ret_low_pct": lo, "ret_high_pct": hi,
                        "confidence": cf}
    return out


def cap_allows(spent_usd: Optional[float], next_est_usd: float, cap: float = CAP_USD) -> bool:
    """A call may proceed only when spend is KNOWN and spend + next <= cap.
    Unknown spend (an unpriced model) refuses: a cap that cannot price cannot bind."""
    if spent_usd is None or not np.isfinite(spent_usd):
        return False
    return spent_usd + max(next_est_usd, 0.0) <= cap


def implied_sd_pct(lo: float, hi: float) -> float:
    """An 80% central interval -> normal sd (z_0.9 = 1.2816)."""
    return (hi - lo) / (2 * 1.2815516)


def qlike_sq(r_pct, sd_pct):
    """QLIKE with the squared return as the variance proxy: r2/f - log(r2/f) - 1
    is undefined at r=0, so the standard loss is used: log f + r2/f."""
    f = np.asarray(sd_pct, dtype=float) ** 2
    r2 = np.asarray(r_pct, dtype=float) ** 2
    return np.log(f) + r2 / f


def estimate_cutoff(errors: dict, tol: float = PROBE_TOL, need: int = 3) -> Optional[str]:
    """errors: {month: [abs log error or None per ticker]}. The last month in
    which >= `need` tickers were answered within `tol`."""
    last = None
    for m in sorted(errors):
        ok = sum(1 for e in errors[m] if e is not None and e <= tol)
        if ok >= need:
            last = m
    return last


# ───────────────────────── LLM plumbing ─────────────────────────────────────
class Wire:
    """Calls `_call_llm` and captures the SERVED model + usage from the
    telemetry hook (the ledger row itself records the requested alias)."""

    def __init__(self, prior_spent: Optional[float] = 0.0, ledger: Optional[Path] = None):
        from backend.services import llm_analyzer as LA             # noqa: PLC0415
        from backend.services import llm_telemetry as TEL           # noqa: PLC0415
        self.LA, self.TEL = LA, TEL
        self.calls: list = []
        # The cap binds on the RUN, not the process: probe, first and run are
        # separate processes, so spend already on disk is carried in. Unknown
        # prior spend (None) refuses, like an unpriced call.
        self.prior_spent = prior_spent
        self.ledger = ledger
        self._orig = LA._record

        def rec(provider, model, purpose, *, resp=None, **kw):
            served = getattr(resp, "model", None) if resp is not None else None
            usage = TEL.extract_usage(resp, provider) if resp is not None else {}
            cost = (TEL.price_call(served, usage.get("tokens_in", 0), usage.get("tokens_out", 0),
                                   usage.get("cached_tokens", 0)) if served else None)
            self.calls.append({"provider": provider, "requested_model": model,
                               "served_model": served, "purpose": purpose, **usage,
                               "cost_usd_served_row": cost,
                               "error": str(kw.get("error")) if kw.get("error") else None})
            if self.ledger is not None:          # flushed per call, not at exit
                with open(self.ledger, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(self.calls[-1]) + "\n")
            return self._orig(provider, model, purpose, resp=resp, **kw)
        LA._record = rec

    def spent(self) -> Optional[float]:
        if self.prior_spent is None or not np.isfinite(self.prior_spent):
            return None
        tot = float(self.prior_spent)
        for c in self.calls:
            if c["error"] is None and c["cost_usd_served_row"] is None:
                return None
            tot += c["cost_usd_served_row"] or 0.0
        return tot

    def next_est(self) -> float:
        costs = [c["cost_usd_served_row"] for c in self.calls if c["cost_usd_served_row"]]
        return 2 * max(costs) if costs else 0.01

    def call(self, system: str, user: str, purpose: str) -> tuple:
        if not cap_allows(self.spent(), self.next_est()):
            raise RuntimeError(f"CAP REFUSAL: spent={self.spent()} next~{self.next_est():.4f} "
                               f"cap={CAP_USD}")
        n0 = len(self.calls)
        text = self.LA._call_llm(system, user, purpose=purpose)
        served = self.calls[-1]["served_model"] if len(self.calls) > n0 else None
        return text, served


def prior_spend(run_id: str) -> Optional[float]:
    """Served-row-priced spend of this run already on disk (probe + calls
    ledger). None when any recorded successful call could not be priced."""
    tot = 0.0
    pp = OUT_DIR / f"x2_{run_id}_probe.json"
    if pp.exists():
        s = json.loads(pp.read_text(encoding="utf-8")).get("spent_usd_served_row")
        if s is None:
            return None
        tot += float(s)
    cp = OUT_DIR / f"x2_{run_id}_calls.jsonl"
    if cp.exists():
        for ln in cp.read_text(encoding="utf-8").splitlines():
            c = json.loads(ln)
            if c.get("error") is None and c.get("cost_usd_served_row") is None:
                return None
            tot += c.get("cost_usd_served_row") or 0.0
    return tot


def read_balance_safe() -> dict:
    try:
        from backend.services import deepseek_balance as B          # noqa: PLC0415
        b = B.read_balance()
        return {"total_usd": b.get("total_usd"), "read_at": datetime.now(timezone.utc).isoformat()}
    except Exception as e:                                          # noqa: BLE001
        return {"total_usd": None, "error": f"{type(e).__name__}: {e}"[:200]}


# ───────────────────────── data ─────────────────────────────────────────────
def load_bars(symbols=None) -> pd.DataFrame:
    cols = ["symbol", "date", "close", "volume"]
    f = [("date", ">=", pd.Timestamp("2022-06-01"))]
    if symbols is not None:
        f.append(("symbol", "in", list(symbols)))
    return pd.read_parquet(BARS, columns=cols, filters=f).sort_values(["symbol", "date"])


def load_news() -> pd.DataFrame:
    n = pd.read_parquet(NEWS, columns=["symbol", "published_utc", "title"])
    n["pub"] = pd.to_datetime(n["published_utc"], utc=True, errors="coerce")
    return n.dropna(subset=["pub", "title"])


def load_typed() -> pd.DataFrame:
    rows = []
    for f in sorted(TYPED_DIR.glob("20*.jsonl")):
        if "refusal" in f.name:
            continue
        with open(f, encoding="utf-8") as fh:
            for ln in fh:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if (r.get("published_utc") or "") < "2024":
                    continue
                if r.get("event_type") in (None, "no_event"):
                    continue
                for tk in r.get("tickers") or []:
                    rows.append({"symbol": tk, "pub": r["published_utc"],
                                 "event_type": r["event_type"], "direction": r.get("direction")})
    d = pd.DataFrame(rows, columns=["symbol", "pub", "event_type", "direction"])
    d["pub"] = pd.to_datetime(d["pub"], utc=True, errors="coerce")
    return d.dropna(subset=["pub"])


def load_titles() -> dict:
    raw = json.loads(COMPANY_TICKERS.read_text(encoding="utf-8"))
    return {v["ticker"]: v["title"] for v in raw.values()}


# ───────────────────────── stages ───────────────────────────────────────────
def stage_probe(run_id: str) -> dict:
    wire = Wire(prior_spent=0.0)
    bal0 = read_balance_safe()
    bars = pd.read_parquet(BARS, columns=["symbol", "date", "close"],
                           filters=[("symbol", "in", list(PROBE_TICKERS)),
                                    ("date", ">=", pd.Timestamp("2023-12-01"))])
    bars["m"] = bars["date"].dt.to_period("M")
    truth = bars.sort_values("date").groupby(["symbol", "m"])["close"].last()
    months = [str(m) for m in PROBE_MONTHS]
    answers, errors = {}, {m: [] for m in months}
    for tk in PROBE_TICKERS:
        user = (f"Ticker: {tk}. Months: {', '.join(months)}. Give each month's last-trading-day "
                f"close (split-adjusted to today's share count), or null.")
        text, served = wire.call(PROBE_SYSTEM, user, PURPOSE_PROBE)
        try:
            obj = json.loads(re.search(r"\{.*\}", text or "", flags=re.S).group(0))
        except (AttributeError, ValueError):
            obj = {}
        answers[tk] = {"served_model": served, "raw": (text or "")[:3000], "parsed": obj}
        for m in months:
            v = obj.get(m)
            tv = truth.get((tk, pd.Period(m, "M")))
            e = (abs(math.log(float(v) / float(tv))) if isinstance(v, (int, float)) and v
                 and tv is not None and tv > 0 else None)
            errors[m].append(e)
    self_text, served = wire.call("Reply in one short sentence.",
                                  "What is the most recent month and year covered by your "
                                  "training data?", PURPOSE_PROBE)
    table = {m: {"answered": sum(e is not None for e in errors[m]),
                 "within_tol": sum(1 for e in errors[m] if e is not None and e <= PROBE_TOL),
                 "median_abs_log_err": (float(np.median([e for e in errors[m] if e is not None]))
                                        if any(e is not None for e in errors[m]) else None)}
             for m in months}
    cutoff = estimate_cutoff(errors)
    rec = {"experiment": "X2 cutoff probe", "run_id": run_id,
           "generated_at": datetime.now(timezone.utc).isoformat(),
           "tickers": PROBE_TICKERS, "tolerance_abs_log": PROBE_TOL,
           "truth": "prices_deep bars (split+dividend adjusted: older months read LOW by the "
                    "dividends since, ~1-2%/yr for SPY)",
           "measured_cutoff_month": cutoff, "self_report": self_text,
           "served_models": sorted({c["served_model"] for c in wire.calls if c["served_model"]}),
           "per_month": table, "answers": answers, "calls": wire.calls,
           "spent_usd_served_row": wire.spent(), "balance_before": bal0,
           "balance_after": read_balance_safe()}
    from backend.services import disk_guard as DG                  # noqa: PLC0415
    DG.atomic_write_json(OUT_DIR / f"x2_{run_id}_probe.json", rec)
    return rec


def weekly_sessions(cal: pd.DatetimeIndex) -> list:
    s = pd.Series(cal)
    return list(s.groupby(s.dt.to_period("W-SUN")).max())


def build_plan(run_id: str, cutoff_month: str) -> dict:
    """Names, dates, famous set and every packet, frozen to disk BEFORE any call."""
    titles = load_titles()
    news = load_news()
    typed = load_typed()
    bars = load_bars()
    cal = pd.DatetimeIndex(sorted(bars["date"].unique()))
    first_ok = (pd.Period(cutoff_month, "M") + CUTOFF_BUFFER_MONTHS + 1).start_time
    weeks = [t for t in weekly_sessions(cal) if t >= first_ok and (cal > t).sum() >= HORIZON]
    dates = weeks[-N_DATES:]
    groups = {s: g.reset_index(drop=True) for s, g in bars.groupby("symbol", sort=False)}

    def mdv_at(g, t):
        g = g[g["date"] <= t].tail(63)
        return float(np.median(g["close"] * g["volume"])) if len(g) >= 63 else 0.0
    # names: liquid at the first date, in the SEC title map, >= 20 headlines in window
    win = news[(news["pub"] >= pd.Timestamp(dates[0]).tz_localize("UTC") - pd.Timedelta(days=14))
               & (news["pub"] < pd.Timestamp(dates[-1]).tz_localize("UTC") + pd.Timedelta(hours=20))]
    nh = win.groupby("symbol").size()
    cand = sorted(s for s in groups if s in titles and nh.get(s, 0) >= 20
                  and len(s) >= MIN_TICKER_LEN
                  and s not in ("SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "RSP")
                  and mdv_at(groups[s], dates[0]) >= MIN_MDV_NAMES)
    rng = np.random.default_rng(SEED)
    names = sorted(rng.choice(cand, size=min(N_NAMES, len(cand)), replace=False).tolist())
    # famous pre-cutoff: largest |5-session| moves of mega caps before the cutoff
    last_pre = pd.Period(cutoff_month, "M").end_time - pd.Timedelta(days=45)
    pre_weeks = [t for t in weekly_sessions(cal) if pd.Timestamp("2025-01-17") <= t <= last_pre]
    fam = []
    for s, g in groups.items():
        if s not in titles or len(s) < MIN_TICKER_LEN or s in ("SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "RSP"):
            continue
        d = g["date"].to_numpy()
        c = g["close"].to_numpy(dtype=float)
        for t in pre_weeks:
            i = int(np.searchsorted(d, np.datetime64(t), side="right"))
            if i < 253 or d[i - 1] != np.datetime64(t) or i + HORIZON > len(c):
                continue
            if mdv_at(g, t) < 1e9:
                continue
            fam.append((abs(c[i - 1 + HORIZON] / c[i - 1] - 1), s, t))
    fam.sort(key=lambda x: -x[0])
    seen, famous = set(), []
    for _, s, t in fam:                   # one event per name
        if s in seen:
            continue
        seen.add(s)
        famous.append((s, t))
        if len(famous) >= N_FAMOUS:
            break
    all_syms = sorted(set(names) | {s for s, _ in famous})
    codes = make_codes(all_syms)
    items = []
    for set_name, pairs in (("post", [(s, t) for t in dates for s in names]),
                            ("famous", famous)):
        for s, t in pairs:
            g = groups[s]
            i = int(np.searchsorted(g["date"].to_numpy(), np.datetime64(t), side="right"))
            past = g.iloc[:i]
            assert past["date"].iloc[-1] == t
            fut = g.iloc[i:i + HORIZON]
            summ = price_summary(past["close"].to_numpy(), past["volume"].to_numpy())
            heads = headlines_before(news, s, t)
            cut = pd.Timestamp(t).tz_localize("UTC") + pd.Timedelta(hours=DECISION_UTC_HOUR)
            ev = typed[(typed["symbol"] == s) & (typed["pub"] < cut)
                       & (typed["pub"] >= cut - pd.Timedelta(days=HEADLINE_LOOKBACK_DAYS))]
            evs = [f"{p.strftime('%Y-%m-%d')} {e} dir={dr}" for p, e, dr in
                   zip(ev["pub"], ev["event_type"], ev["direction"])][-3:]
            fwd = float(fut["close"].iloc[-1] / past["close"].iloc[-1] - 1) * 100
            items.append({"set": set_name, "symbol": s, "date": str(pd.Timestamp(t).date()),
                          "summary": summ, "headlines": heads, "events": evs,
                          "fwd_ret_pct": fwd, "prior_sd_pct": summ["vol_21d_daily_pct"] * math.sqrt(HORIZON)})
    plan = {"run_id": run_id, "cutoff_month": cutoff_month,
            "dates": [str(pd.Timestamp(t).date()) for t in dates], "names": names,
            "famous": [(s, str(pd.Timestamp(t).date())) for s, t in famous],
            "codes": codes, "titles": {s: titles.get(s) for s in all_syms}, "items": items}
    return plan


def prompts_for(plan: dict) -> list:
    """Every call, both arms, deterministic. Items grouped by (set, date) for
    `post`; famous items grouped in tens (each keeps its own date line)."""
    calls = []
    by = {}
    for it in plan["items"]:
        key = (it["set"], it["date"] if it["set"] == "post" else "famous")
        by.setdefault(key, []).append(it)
    for (set_name, _), its in sorted(by.items()):
        its = sorted(its, key=lambda x: (x["date"], x["symbol"]))
        for k in range(0, len(its), PER_CALL):
            chunk = its[k:k + PER_CALL]
            for arm in ("NAMED", "BLINDED"):
                parts, ids, item_texts = [], [], []
                for j, it in enumerate(chunk):
                    iid = f"S{j + 1}"
                    ids.append(iid)
                    s = it["symbol"]
                    heads = it["headlines"]
                    evs = it["events"]
                    d = it["date"]
                    if arm == "NAMED":
                        label = f"{s} ({plan['titles'].get(s)}), decision date {d}"
                    else:
                        code = plan["codes"][s]
                        al = name_aliases(s, plan["titles"].get(s))
                        label = f"{code}, decision date {shift_date(d)}"
                        heads = [(shift_date(hd), blind_text(ht, al, code)) for hd, ht in heads]
                        evs = [shift_date(e[:10]) + e[10:] for e in evs]
                    parts.append(render_item(iid, label, it["summary"], heads, evs))
                    item_texts.append(parts[-1])
                user = ("Stocks to forecast (each item states its own decision date):\n\n"
                        + "\n\n".join(parts))
                calls.append({"call_key": f"{set_name}|{chunk[0]['date']}|{k}|{arm}",
                              "set": set_name, "arm": arm, "ids": ids,
                              "items": [(it["symbol"], it["date"]) for it in chunk],
                              "item_texts": item_texts,
                              "user": user})
    return calls


def run_calls(run_id: str, plan: dict, calls: list, limit: Optional[int]) -> dict:
    rows_path = OUT_DIR / f"x2_{run_id}_rows.jsonl"
    done = set()
    if rows_path.exists():
        for ln in rows_path.read_text(encoding="utf-8").splitlines():
            done.add(json.loads(ln)["call_key"])
    wire = Wire(prior_spent=prior_spend(run_id), ledger=OUT_DIR / f"x2_{run_id}_calls.jsonl")
    lookup = {(it["symbol"], it["date"], it["set"]): it for it in plan["items"]}
    n = 0
    for c in calls:
        if c["call_key"] in done:
            continue
        if limit is not None and n >= limit:
            break
        text, served = wire.call(SYSTEM_PROMPT, c["user"], PURPOSE)
        parsed = parse_reply(text, c["ids"])
        with open(rows_path, "a", encoding="utf-8") as f:
            for iid, (s, d) in zip(c["ids"], c["items"]):
                it = lookup[(s, d, c["set"])]
                p = parsed.get(iid)
                f.write(json.dumps({"call_key": c["call_key"], "set": c["set"], "arm": c["arm"],
                                    "symbol": s, "date": d, "id": iid, "model": served,
                                    "parsed": p is not None, **(p or {}),
                                    "fwd_ret_pct": it["fwd_ret_pct"],
                                    "prior_sd_pct": it["prior_sd_pct"],
                                    "raw_head": None if p else (text or "")[:400]}) + "\n")
        n += 1
        print(f"{c['call_key']} served={served} parsed={len(parsed)}/{len(c['ids'])} "
              f"spent=${wire.spent()}", flush=True)
    return {"n_calls": n, "spent_usd_served_row": wire.spent()}


# ───────────────────────── analysis ─────────────────────────────────────────
def grade(rows: pd.DataFrame) -> dict:
    r = rows[rows["parsed"]].copy()
    r = r[r["fwd_ret_pct"] != 0]
    r["hit"] = ((r["direction"] == "up") == (r["fwd_ret_pct"] > 0)).astype(int)
    r["sd_llm"] = implied_sd_pct(r["ret_low_pct"], r["ret_high_pct"])
    r["covered"] = ((r["fwd_ret_pct"] >= r["ret_low_pct"]) & (r["fwd_ret_pct"] <= r["ret_high_pct"])).astype(int)
    out = {}
    for (st, arm), g in r.groupby(["set", "arm"]):
        k, n = int(g["hit"].sum()), int(len(g))
        ok = g[(g["sd_llm"] > 0) & (g["prior_sd_pct"] > 0)]
        ql = qlike_sq(ok["fwd_ret_pct"], ok["sd_llm"]) - qlike_sq(ok["fwd_ret_pct"], ok["prior_sd_pct"])
        by_date = g.groupby("date")["hit"].mean()
        bins = pd.cut(g["confidence"], [0, 0.6, 0.7, 0.8, 1.01], right=False)
        cal = {str(b): {"n": int(len(x)), "mean_conf": float(x["confidence"].mean()),
                        "hit": float(x["hit"].mean())} for b, x in g.groupby(bins, observed=True)}
        base = float((g["fwd_ret_pct"] > 0).mean())
        p_up = np.where(g["direction"] == "up", g["confidence"], 1 - g["confidence"])
        y = (g["fwd_ret_pct"] > 0).astype(float)
        out[f"{st}|{arm}"] = {
            "n": n, "hits": k, "hit_rate": k / n if n else float("nan"),
            "wilson95": wilson(k, n), "share_up_called": float((g["direction"] == "up").mean()),
            "base_rate_up": base,
            "always_up_hit": base, "hit_by_date_sd": float(by_date.std(ddof=1)) if len(by_date) > 1 else None,
            "n_dates": int(g["date"].nunique()),
            # rows on one date share the market's move: the honest n is the DATE
            "hit_date_block": _date_block(by_date - 0.5),
            "magnitude": {"n": int(len(ok)), "qlike_llm_minus_prior_mean": float(ql.mean()),
                          "qlike_diff_se": float(ql.std(ddof=1) / math.sqrt(len(ql))) if len(ql) > 1 else None,
                          "rankcorr_sd_llm_vs_abs_ret": float(ok["sd_llm"].corr(ok["fwd_ret_pct"].abs(), method="spearman")),
                          "rankcorr_sd_prior_vs_abs_ret": float(ok["prior_sd_pct"].corr(ok["fwd_ret_pct"].abs(), method="spearman")),
                          "median_sd_llm_over_prior": float((ok["sd_llm"] / ok["prior_sd_pct"]).median()),
                          "coverage_80": float(g["covered"].mean())},
            "calibration": {"bins": cal, "mean_confidence": float(g["confidence"].mean()),
                            "brier": float(np.mean((p_up - y) ** 2)),
                            "brier_base_rate": float(np.mean((base - y) ** 2)),
                            "brier_coin": 0.25}}
    # arm agreement (paired, same symbol+date)
    agree = {}
    for st, g in r.groupby("set"):
        pv = g.pivot_table(index=["symbol", "date"], columns="arm", values="hit", aggfunc="first")
        dv = g.pivot_table(index=["symbol", "date"], columns="arm", values="direction", aggfunc="first")
        if {"NAMED", "BLINDED"} <= set(pv.columns):
            both = pv.dropna()
            d = both["NAMED"] - both["BLINDED"]
            agree[st] = {"n_pairs": int(len(both)),
                         "same_direction_share": float((dv.dropna()["NAMED"] == dv.dropna()["BLINDED"]).mean()),
                         "hit_named_minus_blinded": float(d.mean()),
                         "se_paired": float(d.std(ddof=1) / math.sqrt(len(d))) if len(d) > 1 else None}
    return {"by_set_arm": out, "arm_gap": agree}


def _date_block(x: pd.Series) -> dict:
    x = pd.Series(x).dropna().astype(float)
    n = len(x)
    if n < 2:
        return {"n_dates": n}
    se = float(x.std(ddof=1) / math.sqrt(n))
    return {"n_dates": n, "mean_excess_over_half": float(x.mean()), "se": se,
            "t": float(x.mean() / se) if se > 0 else float("nan"), "mde_80": 2.8 * se}


#: DECLARED BEFORE THE FIRST PAID CALL (2026-09-28), read on post|BLINDED:
#:  DIR   : Wilson95 low > 0.5 AND date-block t(hit - 0.5) >= 2
#:  BETA  : DIR holds but hit <= the always-up hit on the same rows (it called drift)
#:  VOL   : mean QLIKE(llm sd) - QLIKE(trailing-21d prior) < 0 with t <= -2
#:  verdict: DIR and not BETA -> ALPHA_DETECTED (a PRODUCT_EXPERIMENT reading,
#:           not a claim); DIR and BETA -> BETA_EXPLAINS; neither DIR nor VOL and
#:           Wilson95 high < 0.55 (a 5-point edge excluded) -> FAILED_VARIANT;
#:           otherwise CANNOT_DISTINGUISH. Leakage = famous NAMED - BLINDED hit gap.
X2_RULE = ("post|BLINDED: DIR = wilson_lo > 0.5 and date-block t >= 2; BETA = DIR and "
           "hit <= always-up hit; VOL = qlike diff < 0 with t <= -2; ALPHA_DETECTED if DIR "
           "and not BETA; BETA_EXPLAINS if DIR and BETA; FAILED_VARIANT if not DIR, not VOL "
           "and wilson_hi < 0.55; else CANNOT_DISTINGUISH")


def decide_x2(g: dict) -> dict:
    b = g.get("by_set_arm", {}).get("post|BLINDED")
    if not b:
        return {"rule": X2_RULE, "verdict": "NO_POST_BLINDED_ROWS"}
    lo, hi = b["wilson95"]
    db = b.get("hit_date_block", {})
    dir_ok = bool(lo > 0.5 and db.get("t", float("nan")) >= 2)
    beta = bool(dir_ok and b["hit_rate"] <= b["always_up_hit"])
    m = b["magnitude"]
    se = m.get("qlike_diff_se")
    vt = m["qlike_llm_minus_prior_mean"] / se if se else float("nan")
    vol_ok = bool(m["qlike_llm_minus_prior_mean"] < 0 and vt <= -2)
    if dir_ok and not beta:
        v = "ALPHA_DETECTED"
    elif dir_ok:
        v = "BETA_EXPLAINS"
    elif not vol_ok and hi < 0.55:
        v = "FAILED_VARIANT"
    else:
        v = "CANNOT_DISTINGUISH"
    return {"rule": X2_RULE, "direction_beats_half": dir_ok, "beta_explains": beta,
            "vol_beats_prior": vol_ok, "vol_qlike_t": vt, "verdict": v}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["probe", "plan", "first", "run", "analyze"], required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--cutoff-month", default=None, help="override; default = the probe's")
    a = ap.parse_args(argv)
    from backend.services import disk_guard as DG                  # noqa: PLC0415
    DG.require_free(FREE_GB_REQUIRED, "exp_x2", path=OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = a.run_id
    plan_path = OUT_DIR / f"x2_{run_id}_plan.json"
    if a.stage == "probe":
        rec = stage_probe(run_id)
        print(json.dumps({k: rec[k] for k in ("measured_cutoff_month", "self_report",
                                              "served_models", "spent_usd_served_row")}))
        print(json.dumps(rec["per_month"]))
        return 0
    if a.stage == "plan":
        cm = a.cutoff_month or json.loads((OUT_DIR / f"x2_{run_id}_probe.json")
                                          .read_text(encoding="utf-8"))["measured_cutoff_month"]
        plan = build_plan(run_id, cm)
        calls = prompts_for(plan)
        # the leak check runs on the frozen prompts, before a cent is spent
        bad = []
        for c in calls:
            if c["arm"] != "BLINDED":
                continue
            for (s, _), txt in zip(c["items"], c["item_texts"]):
                lk = leaks(txt, name_aliases(s, plan["titles"].get(s)))
                if lk:
                    bad.append({"call": c["call_key"], "symbol": s, "leaks": lk})
        plan["n_calls"] = len(calls)
        plan["blind_leaks"] = bad
        plan["system_prompt"] = SYSTEM_PROMPT
        plan["system_prompt_sha256"] = hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()
        DG.atomic_write_json(plan_path, plan)
        print(f"plan: {len(plan['names'])} names x {len(plan['dates'])} dates "
              f"({plan['dates'][0]}..{plan['dates'][-1]}), famous {len(plan['famous'])}, "
              f"{len(calls)} calls, blind leaks {len(bad)}")
        return 0
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    calls = prompts_for(plan)
    if a.stage in ("first", "run"):
        bal0 = read_balance_safe()
        res = run_calls(run_id, plan, calls, limit=2 if a.stage == "first" else None)
        bal1 = read_balance_safe()
        with open(OUT_DIR / f"x2_{run_id}_balance.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"stage": a.stage, "before": bal0, "after": bal1, **res}) + "\n")
        print(json.dumps({"before": bal0, "after": bal1, **res}))
        return 0
    rows = pd.DataFrame([json.loads(l) for l in
                         (OUT_DIR / f"x2_{run_id}_rows.jsonl").read_text(encoding="utf-8").splitlines()])
    g = grade(rows)
    calls_rows = [json.loads(l) for l in
                  (OUT_DIR / f"x2_{run_id}_calls.jsonl").read_text(encoding="utf-8").splitlines()]
    bals = [json.loads(l) for l in
            (OUT_DIR / f"x2_{run_id}_balance.jsonl").read_text(encoding="utf-8").splitlines()]
    probe = json.loads((OUT_DIR / f"x2_{run_id}_probe.json").read_text(encoding="utf-8"))
    spent_ledger = sum(c.get("cost_usd_served_row") or 0 for c in calls_rows) + \
        (probe.get("spent_usd_served_row") or 0)
    receipt = {"experiment": "X2 StockBench-style blind-gap check, LANE X, 2026-09-28",
               "run_id": run_id, "licence": "PRODUCT_EXPERIMENT (no claim)",
               "generated_at": datetime.now(timezone.utc).isoformat(),
               "stockbench": "arXiv:2510.02209; github.com/ChenYXxxx/stockbench (Apache-2.0); "
                             "idea reproduced, framework NOT installed",
               "served_models": sorted({c.get("served_model") for c in calls_rows if c.get("served_model")}),
               "measured_cutoff_month": probe.get("measured_cutoff_month"),
               "cutoff_self_report": probe.get("self_report"),
               "decision_dates": plan["dates"], "names": plan["names"], "famous": plan["famous"],
               "horizon_sessions": HORIZON, "per_call": PER_CALL,
               "n_rows": int(len(rows)), "n_parsed": int(rows["parsed"].sum()),
               "parse_rate": float(rows["parsed"].mean()),
               "rows_by_model": rows["model"].value_counts(dropna=False).to_dict(),
               "blind_leaks_in_plan": len(plan.get("blind_leaks", [])),
               "system_prompt_sha256": plan.get("system_prompt_sha256"),
               "spend": {"cap_usd": CAP_USD, "served_row_priced_usd": spent_ledger,
                         "n_calls_total": len(calls_rows) + len(probe.get("calls", [])),
                         "balance_probe": [probe.get("balance_before"), probe.get("balance_after")],
                         "balance_runs": bals},
               **g,
               "verdict": decide_x2(g)}
    DG.atomic_write_json(OUT_DIR / f"x2_{run_id}_receipt.json", receipt)
    print(json.dumps({k: receipt[k] for k in ("n_rows", "n_parsed", "served_models")}))
    for k, v in g["by_set_arm"].items():
        print(k, v["n"], round(v["hit_rate"], 3), [round(x, 3) for x in v["wilson95"]],
              "brier", round(v["calibration"]["brier"], 4), "base", round(v["calibration"]["brier_base_rate"], 4),
              "qlike", round(v["magnitude"]["qlike_llm_minus_prior_mean"], 3))
    print(json.dumps(g["arm_gap"]))
    print(json.dumps(receipt["verdict"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
